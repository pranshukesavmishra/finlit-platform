"""Company and fund-house logos for search results and lists (worker `refresh-logos`, route `/api/logos/<hash>`).

Where a logo comes from: the icon the company publishes on its OWN website (the domain in its FinEdge profile; fund houses from
`AMC_SITES`), never a third-party logo service. The home page is read once (its first 256 KB: icons are declared in
its head) and the published icons are tried: apple-touch-icon, then the largest declared icon, then `/apple-touch-icon.png`, then
`/favicon.ico`; the largest that passes is kept.

Rules (the same as every other source in this repo):
- one plain, identifying user agent; robots.txt is obeyed; a refusal, a rate limit or a bot check marks the site 'blocked' for 30 days.
  Nothing spoofs a header or goes around a challenge.
- https (plain http only where a site offers nothing else), standard ports only; every address a host resolves to must be public (no
  private, loopback or link-local targets), checked again on each of at most 3 redirects; every download is streamed with a byte cap and a
  short timeout.
- an image is kept only if its bytes really are PNG, ICO, GIF, JPEG or WebP (magic bytes, not the Content-Type), 16 to 1024 px, not far
  from square and at most MAX_BYTES. SVG is never accepted (it can carry script).
- logos are served from our own origin under the image's hash, cached for a year (immutable), so a browser never asks twice.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
import struct
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

log = logging.getLogger("finlit.logos")
router = APIRouter(prefix="/api/logos")

USER_AGENT = "FinLit-logo/1.0 (+https://finlitventures.com; one request per page, robots.txt obeyed)"
MAX_HTML = 256 * 1024
MAX_BYTES = 64 * 1024
MIN_PX, MAX_PX = 16, 1024             # many company sites publish only a 16 px favicon; it is shown at its own size, never blown up
TIMEOUT = 6.0
MAX_REDIRECTS = 3
PARALLEL = 4
PAUSE = 0.5                                 # seconds between two requests to the same site
RETRY = {"ok": 60, "manual": 3650, "none": 21, "rejected": 21, "blocked": 30}   # days before a site is asked again
NAME = re.compile(r"^([0-9a-f]{16})(?:\.(?:png|ico|jpg|webp))?$")
CHALLENGE = re.compile(rb"cf-chl-|challenge-platform|/cdn-cgi/challenge|px-captcha|_Incapsula_Resource|awswaf", re.I)   # bot-check pages, not a contact form's reCAPTCHA

# Fund houses' own sites (the domains the portfolio parsers already read). Key: mf.amc_key() of AMFI's fund-house name.
AMC_SITES: Dict[str, str] = {
    "360one": "www.360.one", "adityabirlasunlife": "mutualfund.adityabirlacapital.com", "angelone": "www.angelonemf.com", "axis": "www.axismf.com",
    "bajajfinserv": "www.bajajamc.com", "bandhan": "bandhanmutual.com", "bankofindia": "www.boimf.in", "barodabnpparibas": "www.barodabnpparibasmf.in",
    "canararobeco": "www.canararobeco.com", "capitalmind": "www.capitalmindmf.com", "choice": "www.choicemf.com", "dsp": "www.dspim.com",
    "edelweiss": "www.edelweissmf.com", "franklintempleton": "www.franklintempletonindia.com", "groww": "www.growwmf.in", "hdfc": "www.hdfcfund.com",
    "helios": "www.heliosmf.in", "hsbc": "www.assetmanagement.hsbc.co.in", "iciciprudential": "www.icicipruamc.com", "invesco": "www.invescomutualfund.com",
    "jioblackrock": "www.jioblackrockamc.com", "jmfinancial": "www.jmfinancialmf.com", "kotakmahindra": "www.kotakmf.com", "lic": "www.licmf.com",
    "mahindramanulife": "www.mahindramanulife.com", "miraeasset": "www.miraeassetmf.co.in", "motilaloswal": "www.motilaloswalmf.com", "navi": "navi.com",
    "nipponindia": "mf.nipponindiaim.com", "oldbridge": "www.oldbridgemf.com", "ppfas": "amc.ppfas.com", "quant": "quantmutual.com",
    "quantum": "www.quantumamc.com", "sbi": "www.sbimf.com", "shriram": "www.shriramamc.in", "sundaram": "www.sundarammutual.com",
    "tata": "www.tatamutualfund.com", "thewealthcompany": "www.wealthcompanyamc.in", "union": "www.unionmf.com", "uti": "www.utimf.com",
    "whiteoakcapital": "mf.whiteoakamc.com",
}


class Rejected(Exception):
    """The file is not an image we accept; the message says why (stored as the note)."""


# ---------------------------------------------------------------- image checks (no image library: only headers are read)
def _png_size(b: bytes) -> Tuple[int, int]:
    if len(b) < 24 or b[12:16] != b"IHDR":
        raise Rejected("broken PNG header")
    return struct.unpack(">II", b[16:24])


def _jpeg_size(b: bytes) -> Tuple[int, int]:
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + seg
    raise Rejected("JPEG without a size")


def _webp_size(b: bytes) -> Tuple[int, int]:
    kind = b[12:16]
    if kind == b"VP8X" and len(b) >= 30:
        return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
    if kind == b"VP8L" and len(b) >= 25 and b[20] == 0x2F:
        bits = int.from_bytes(b[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8 " and len(b) >= 30 and b[23:26] == b"\x9d\x01\x2a":
        return struct.unpack("<H", b[26:28])[0] & 0x3FFF, struct.unpack("<H", b[28:30])[0] & 0x3FFF
    raise Rejected("WebP without a size")


def _ico_best(b: bytes) -> Tuple[bytes, str, int, int]:
    """The largest image inside an .ico. A PNG entry is kept on its own (smaller, sharper); otherwise the whole .ico is kept."""
    if len(b) < 6:
        raise Rejected("broken ICO header")
    count = struct.unpack("<H", b[4:6])[0]
    if not 0 < count <= 64 or len(b) < 6 + 16 * count:
        raise Rejected("broken ICO directory")
    best = None
    for k in range(count):
        e = b[6 + 16 * k: 22 + 16 * k]
        w, h = e[0] or 256, e[1] or 256
        size, offset = struct.unpack("<II", e[8:16])
        if offset + size > len(b) or size == 0:
            continue
        if best is None or w * h > best[0] * best[1]:
            best = (w, h, size, offset)
    if best is None:
        raise Rejected("empty ICO")
    w, h, size, offset = best
    inner = b[offset:offset + size]
    if inner.startswith(b"\x89PNG\r\n\x1a\n"):
        pw, ph = _png_size(inner)
        return inner, "image/png", pw, ph
    return b, "image/x-icon", w, h


def sniff(data: bytes) -> Tuple[bytes, str, int, int]:
    """(bytes to keep, MIME type, width, height) for an accepted image; raises Rejected otherwise. Decided by the bytes, never the header."""
    head = data[:64].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml", b"<!doctype", b"<html")):
        raise Rejected("not a bitmap (SVG or a web page)")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        out, mime, (w, h) = data, "image/png", _png_size(data)
    elif data.startswith(b"\x00\x00\x01\x00"):
        out, mime, w, h = _ico_best(data)
    elif data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        out, mime, (w, h) = data, "image/gif", struct.unpack("<HH", data[6:10])
    elif data.startswith(b"\xff\xd8\xff"):
        out, mime, (w, h) = data, "image/jpeg", _jpeg_size(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        out, mime, (w, h) = data, "image/webp", _webp_size(data)
    else:
        raise Rejected("unknown image format")
    if not (MIN_PX <= min(w, h) and max(w, h) <= MAX_PX):
        raise Rejected(f"size {w}x{h} outside {MIN_PX}-{MAX_PX} px")
    if not h or not 0.66 <= w / h <= 1.5:
        raise Rejected(f"not square enough ({w}x{h})")
    if len(out) > MAX_BYTES:
        raise Rejected(f"file too large ({len(out) // 1024} KB)")
    return out, mime, w, h


# ---------------------------------------------------------------- where the icons are
def site_domain(website: Optional[str]) -> Optional[str]:
    """'www.ril.com', 'https://www.tcs.com/en/' -> the host name; None for anything that is not a plain public host name."""
    if not website or not isinstance(website, str):
        return None
    w = website.strip().lower()
    if not w or " " in w:
        return None
    host = urlsplit(w if "://" in w else "https://" + w).hostname or ""
    host = host.rstrip(".")
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host) or re.fullmatch(r"[0-9.]+", host):
        return None
    return host


def _size_of(sizes: Optional[str]) -> int:
    best = 0
    for part in (sizes or "").lower().split():
        m = re.fullmatch(r"(\d+)x(\d+)", part)
        if m:
            best = max(best, min(int(m[1]), int(m[2])))
    return best


class _IconLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: List[Tuple[int, int, str]] = []   # (rank, size, href); lower rank first
        self.base: Optional[str] = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        if tag != "link" or not a.get("href"):
            return
        rel = set(a.get("rel", "").lower().split())
        href, size, typ = a["href"].strip(), _size_of(a.get("sizes")), a.get("type", "").lower()
        if href.lower().endswith(".svg") or "svg" in typ or href.lower().startswith("data:"):
            return
        if rel & {"apple-touch-icon", "apple-touch-icon-precomposed"}:
            self.found.append((0, size or 180, href))
        elif "icon" in rel:
            self.found.append((1 if size >= MIN_PX else 3, size, href))


def icon_candidates(html: str, page_url: str) -> List[str]:
    """Icon URLs to try, best first: declared apple-touch-icons (largest first), declared icons of 32 px or more, the two conventional
    paths, then any other declared icon."""
    p = _IconLinks()
    try:
        p.feed(html)
    except Exception:   # nosec B110 - a broken page simply declares nothing; the conventional paths are still tried
        pass
    base = urljoin(page_url, p.base) if p.base else page_url
    declared = sorted(p.found, key=lambda x: (x[0], -x[1]))
    root = f"{urlsplit(page_url).scheme}://{urlsplit(page_url).netloc}"
    ordered = [urljoin(base, h) for r, _, h in declared if r < 3] + [root + "/apple-touch-icon.png", root + "/favicon.ico"] + \
              [urljoin(base, h) for r, _, h in declared if r >= 3]
    out: List[str] = []
    for u in ordered:
        if urlsplit(u).scheme in ("https", "http") and u not in out:
            out.append(u)
    return out[:8]


# ---------------------------------------------------------------- careful fetching
Resolver = Callable[[str], Awaitable[List[str]]]


async def _resolve(host: str) -> List[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


class Blocked(Exception):
    """The site refused us, rate-limited us or put up a bot check: we stop asking it (for RETRY['blocked'] days)."""


class Fetcher:
    """GET with the safety rules above. `transport` and `resolver` are replaced in tests."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, resolver: Optional[Resolver] = None):
        self.http = httpx.AsyncClient(transport=transport, timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        self.resolver = resolver or _resolve
        self.robots: Dict[str, Optional[RobotFileParser]] = {}

    async def aclose(self):
        await self.http.aclose()

    async def _public(self, host: str) -> None:
        try:
            addrs = await self.resolver(host)
        except Exception as exc:
            raise Rejected(f"host does not resolve ({type(exc).__name__})") from exc
        if not addrs or any(not ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs):
            raise Rejected("host resolves to a private or reserved address")

    async def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        key = parts.netloc
        if key not in self.robots:
            rp: Optional[RobotFileParser] = RobotFileParser()
            try:
                status, _, body, _ = await self._raw(f"{parts.scheme}://{key}/robots.txt", 64 * 1024, truncate=True)
                if status >= 500:
                    rp = None                                  # robots.txt unavailable: assume no permission (RFC 9309 2.3.1.4)
                elif status >= 400:
                    rp.parse([])                               # no robots.txt: everything allowed
                else:
                    rp.parse(body.decode("utf-8", "replace").splitlines())
            except (Rejected, httpx.HTTPError):
                rp.parse([])
            self.robots[key] = rp
        rp = self.robots[key]
        return rp is not None and rp.can_fetch(USER_AGENT, url)

    async def _raw(self, url: str, cap: int, truncate: bool = False) -> Tuple[int, httpx.Headers, bytes, str]:
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("https", "http") or not parts.hostname or parts.port not in (None, 80, 443) or parts.username or parts.password:
                raise Rejected("only plain web addresses on the standard ports are fetched")
            await self._public(parts.hostname)
            async with self.http.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > cap:
                        if truncate:
                            return r.status_code, r.headers, bytes(body[:cap]), url
                        raise Rejected(f"response larger than {cap // 1024} KB")
                return r.status_code, r.headers, bytes(body), url
        raise Rejected("too many redirects")

    async def get(self, url: str, cap: int, truncate: bool = False) -> Tuple[int, httpx.Headers, bytes, str]:
        if not await self._allowed(url):
            raise Rejected("robots.txt does not allow it")
        status, headers, body, final = await self._raw(url, cap, truncate)
        if status in (401, 403, 429, 503) or (status == 200 and len(body) < 40_000 and CHALLENGE.search(body)):
            raise Blocked(f"HTTP {status}" if status != 200 else "bot check page")
        return status, headers, body, final


async def fetch_logo(f: Fetcher, domain: str) -> dict:
    """{status, mime, width, height, bytes, source_url, note} for one site. Never raises."""
    try:
        try:
            status, _, html, page = await f.get(f"https://{domain}/", MAX_HTML, truncate=True)
        except httpx.ConnectError:                                  # a site with no https at all
            status, _, html, page = await f.get(f"http://{domain}/", MAX_HTML, truncate=True)
        tries = icon_candidates(html.decode("utf-8", "replace") if status == 200 else "", page)
        notes = [] if status == 200 else [f"home page HTTP {status}"]
        best: Optional[dict] = None
        for url in tries:
            await asyncio.sleep(PAUSE)
            try:
                st, _, body, final = await f.get(url, MAX_BYTES * 4)
                if st != 200:
                    notes.append(f"{urlsplit(url).path or '/'}: HTTP {st}")
                    continue
                out, mime, w, h = sniff(body)
                if best is None or min(w, h) > min(best["width"], best["height"]):
                    best = {"status": "ok", "mime": mime, "width": w, "height": h, "bytes": out, "source_url": final, "note": None}
                if min(w, h) >= 64:
                    break                                           # sharp enough for any tile: stop asking
            except Rejected as exc:
                notes.append(f"{urlsplit(url).path or '/'}: {exc}")
        return best or {"status": "none", "note": "; ".join(notes)[:300] or "no icon declared"}
    except Blocked as exc:
        return {"status": "blocked", "note": str(exc)}
    except Rejected as exc:
        return {"status": "rejected", "note": str(exc)}
    except (httpx.HTTPError, OSError) as exc:
        return {"status": "none", "note": f"could not connect ({type(exc).__name__})"}


# ---------------------------------------------------------------- the nightly job
async def backfill_websites(store, client=None, profile_limit: int = 100) -> int:
    """companies.website from stored reports (free), then from the provider's company profile for up to `profile_limit` of the largest
    companies that still have none (one call each)."""
    n = 0
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("""SELECT DISTINCT ON (s.symbol) s.symbol, (s.body::jsonb #>> '{profile,website}') AS website
                                   FROM snapshots s JOIN companies c ON c.symbol = s.symbol
                                   WHERE s.section = 'summary' AND c.website IS NULL ORDER BY s.symbol, (s.statement = 'consolidated') DESC""")
        for r in rows:
            if site_domain(r["website"]):
                await conn.execute("UPDATE companies SET website = $2 WHERE symbol = $1", r["symbol"], r["website"].strip())
                n += 1
        if client is None or profile_limit <= 0:
            return n
        want = await conn.fetch("""SELECT c.symbol FROM companies c LEFT JOIN listing_quotes q ON q.symbol = c.symbol
                                   LEFT JOIN logos g ON g.owner_kind = 'stock' AND g.owner_key = c.symbol
                                   WHERE c.website IS NULL AND g.owner_key IS NULL
                                   ORDER BY q.market_cap DESC NULLS LAST LIMIT $1""", profile_limit)
    for r in want:
        try:
            prof = await client.get(f"/company-profile/{r['symbol']}", timeout=8, retries=1)
        except Exception:
            continue
        site = (prof or {}).get("website") if isinstance(prof, dict) else None
        async with store.pool.acquire() as conn:
            if site_domain(site):
                await conn.execute("UPDATE companies SET website = $2 WHERE symbol = $1", r["symbol"], site.strip())
                n += 1
            else:   # nothing to fetch from; remember that, so the profile is not asked for again every night
                await _save(conn, "stock", r["symbol"], None, {"status": "none", "note": "no website in the company profile"})
    return n


async def _save(conn, kind: str, key: str, domain: Optional[str], res: dict) -> None:
    data = res.get("bytes")
    sha = hashlib.sha256(data).hexdigest()[:16] if data else None
    nxt = datetime.now(timezone.utc) + timedelta(days=RETRY.get(res["status"], 21))
    await conn.execute(
        """INSERT INTO logos (owner_kind, owner_key, domain, status, mime, width, height, sha8, bytes, source_url, note, fetched_at, next_try_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, now(), $12)
           ON CONFLICT (owner_kind, owner_key) DO UPDATE SET domain = EXCLUDED.domain, status = EXCLUDED.status, mime = EXCLUDED.mime, width = EXCLUDED.width,
               height = EXCLUDED.height, sha8 = EXCLUDED.sha8, bytes = EXCLUDED.bytes, source_url = EXCLUDED.source_url, note = EXCLUDED.note,
               fetched_at = now(), next_try_at = EXCLUDED.next_try_at
           WHERE logos.status <> 'manual'""",
        kind, key, domain, res["status"], res.get("mime"), res.get("width"), res.get("height"), sha, data, res.get("source_url"), res.get("note"), nxt)


async def due_targets(store, limit: int) -> List[Tuple[str, str, str]]:
    """(kind, key, domain) whose logo is missing or due again: fund houses first, then companies largest first."""
    async with store.pool.acquire() as conn:
        seen = {(r["owner_kind"], r["owner_key"]): r["next_try_at"] for r in await conn.fetch("SELECT owner_kind, owner_key, next_try_at FROM logos")}
        stocks = await conn.fetch("""SELECT c.symbol, c.website FROM companies c LEFT JOIN listing_quotes q ON q.symbol = c.symbol
                                     WHERE c.website IS NOT NULL ORDER BY q.market_cap DESC NULLS LAST""")
    now = datetime.now(timezone.utc)
    due = lambda k: k not in seen or (seen[k] is not None and seen[k] <= now)   # noqa: E731
    out = [("amc", k, d) for k, d in AMC_SITES.items() if due(("amc", k))]
    out += [("stock", r["symbol"], site_domain(r["website"])) for r in stocks if site_domain(r["website"]) and due(("stock", r["symbol"]))]
    return out[:limit]


async def refresh(store, client=None, limit: int = 150, profile_limit: int = 100, transport: Optional[httpx.AsyncBaseTransport] = None,
                  resolver: Optional[Resolver] = None) -> dict:
    started = time.perf_counter()
    found = await backfill_websites(store, client, profile_limit)
    targets = await due_targets(store, limit)
    f = Fetcher(transport, resolver)
    counts: Dict[str, int] = {}
    by_domain: Dict[str, dict] = {}                     # group companies share a site (and so a logo): ask each site once per run
    gate = asyncio.Semaphore(PARALLEL)
    locks: Dict[str, asyncio.Lock] = {}

    async def one(kind: str, key: str, domain: str):
        async with gate:
            async with locks.setdefault(domain, asyncio.Lock()):
                res = by_domain.get(domain) or await fetch_logo(f, domain)
                by_domain[domain] = res
            async with store.pool.acquire() as conn:
                await _save(conn, kind, key, domain, res)
            counts[res["status"]] = counts.get(res["status"], 0) + 1
    try:
        await asyncio.gather(*(one(*t) for t in targets))
    finally:
        await f.aclose()
    if targets:
        await store.redis.delete(*[f"search-quotes:{lv}" for lv in ("basic", "silver")])
    return {"status": "ok", "websites": found, "tried": len(targets), **counts, "seconds": round(time.perf_counter() - started, 1)}


# ---------------------------------------------------------------- serving
_lru: "OrderedDict[str, Tuple[str, bytes]]" = OrderedDict()
LRU_SIZE = 600
CACHE_FOREVER = "public, max-age=31536000, immutable"


@router.get("/{name}")
async def logo(request: Request, name: str):
    m = NAME.match(name)
    if not m:
        return Response(status_code=404, headers={"Cache-Control": "public, max-age=3600"})
    sha = m[1]
    hit = _lru.get(sha)
    if hit is None:
        async with request.app.state.store.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT mime, bytes FROM logos WHERE sha8 = $1 AND status IN ('ok', 'manual') AND bytes IS NOT NULL LIMIT 1", sha)
        if row is None:
            return Response(status_code=404, headers={"Cache-Control": "public, max-age=3600"})
        hit = (row["mime"], bytes(row["bytes"]))
        _lru[sha] = hit
        if len(_lru) > LRU_SIZE:
            _lru.popitem(last=False)
    else:
        _lru.move_to_end(sha)
    etag = f'"{sha}"'
    headers = {"Cache-Control": CACHE_FOREVER, "ETag": etag, "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=hit[1], media_type=hit[0], headers=headers)


def logo_path(sha: Optional[str]) -> Optional[str]:
    return f"/api/logos/{sha}.png" if sha else None


def amc_logo_keys(names: List[str]) -> Dict[str, str]:
    """Fund-house name as AMFI or the exchange spells it -> the AMC_SITES key it belongs to ('Nippon India Mutual Fund', 'Nippon Life India
    Asset Management Ltd' -> 'nipponindia'). Longest key first, so 'tata' cannot take a longer house that starts the same way."""
    from .mf import amc_key
    keys = sorted(AMC_SITES, key=len, reverse=True)
    out: Dict[str, str] = {}
    for n in names:
        k = amc_key(n or "")
        hit = next((x for x in keys if k.startswith(x)), None) or next((x for x in keys if len(x) >= 4 and x in k), None)
        if hit:
            out[n] = hit
    return out


async def amc_logos(store) -> Dict[str, str]:
    """AMC_SITES key -> logo hash, for the fund-house logos the search shows."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT owner_key, sha8 FROM logos WHERE owner_kind = 'amc' AND status IN ('ok', 'manual') AND sha8 IS NOT NULL")
    return {r["owner_key"]: r["sha8"] for r in rows}

