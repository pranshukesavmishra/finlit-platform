"""Finding earnings-call transcripts and turning them into text (docs/EARNINGS-CALLS.md, "Transcript collection").

Listed companies file the transcript of every earnings call with the exchanges (SEBI LODR) as a PDF. Two places tell us where it is:
  1. the announcements the site already stores (`feed_items`, filled whenever a company is loaded): free, no new request;
  2. NSE's public corporate-announcements API, for companies the stored feed does not cover (UNVERIFIED offline: the live shape and access are not tested here).
Then the PDF is downloaded from the exchange's archive and its text extracted with pypdf (pure Python).

Rules, the same as every other source in this repo (finlit/logos.py, finlit/flows.py): an identifying User-Agent, robots.txt obeyed, one request at a time with a pause,
a hard request budget per run, back-off on 429/503, a refusal (403) stops that host for the run, https only, exchange hosts only, a byte cap, at most 3 redirects.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from . import config as C

log = logging.getLogger("finlit.earnings.transcripts")

USER_AGENT = "FinLit-earnings/1.0 (+https://finlitventures.com; reads the earnings-call transcripts companies file with the exchanges; robots.txt obeyed)"
# NSE's API wants a browser-style agent and the cookie its home page sets, as the FII/DII report does (finlit/flows.py nse_json).
NSE_BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NSE_HOME = "https://www.nseindia.com/"
NSE_ANNOUNCEMENTS = "https://www.nseindia.com/api/corporate-announcements"
HOST_OK = re.compile(r"^(?:[a-z0-9-]+\.)*(?:nseindia\.com|bseindia\.com)$")
PAUSE = 1.0
MAX_REDIRECTS = 3
MAX_PAGES = 400


# ------------------------------------------------------------------------------------------------ fiscal quarters (India: April to March)
def fiscal(d: date) -> Tuple[int, int]:
    """(fiscal year, quarter) that the date FALLS in. FY27 = April 2026 to March 2027, so it is 2027."""
    q = (d.month - 4) // 3 + 1 if d.month >= 4 else 4
    return (d.year + 1 if d.month >= 4 else d.year), q


def quarter_end(fy: int, q: int) -> date:
    y, m = {1: (fy - 1, 6), 2: (fy - 1, 9), 3: (fy - 1, 12), 4: (fy, 3)}[q]
    return date(y, m, {6: 30, 9: 30, 12: 31, 3: 31}[m])


def quarter_label(fy: int, q: int) -> str:
    return f"Q{q} FY{fy % 100:02d}"


def previous_quarter(fy: int, q: int) -> Tuple[int, int]:
    return (fy, q - 1) if q > 1 else (fy - 1, 4)


def recent_quarters(today: date, n: int) -> List[Tuple[int, int]]:
    """The latest `n` quarters that ended at least 3 days before `today` (newest first): the ones whose calls can have been held."""
    fy, q = fiscal(today)
    out: List[Tuple[int, int]] = []
    while len(out) < n:
        if quarter_end(fy, q) <= today - timedelta(days=3):
            out.append((fy, q))
        fy, q = previous_quarter(fy, q)
    return out


def quarter_for_call(held: date) -> Tuple[int, int]:
    """The quarter a call held on `held` is about when the text does not say: the last quarter that ended before that day."""
    fy, q = fiscal(held)
    if quarter_end(fy, q) >= held:
        fy, q = previous_quarter(fy, q)
    return fy, q


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_Q_FY = re.compile(r"\bQ\s*([1-4])\s*[-/ ]?\s*(?:FY|F\.Y\.?)\s*[-' ]?\s*(?:(20)?(\d{2})\s*[-/]\s*(\d{2})|(20)?(\d{2}))\b", re.I)
_FY_Q = re.compile(r"\b(?:FY|F\.Y\.?)\s*[-' ]?\s*(?:(20)?(\d{2})\s*[-/]\s*(\d{2})|(20)?(\d{2}))\s*[-/ ]?\s*Q\s*([1-4])\b", re.I)
_ENDED = re.compile(r"(?:quarter|period)\s+ended\s+(?:on\s+)?(?:(\d{1,2})(?:st|nd|rd|th)?[\s,-]+([A-Za-z]{3,9})\.?,?\s+(\d{4})|([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}))", re.I)
_DATE = re.compile(r"\b(?:(\d{1,2})(?:st|nd|rd|th)?[\s,-]+([A-Za-z]{3,9})\.?,?\s+(\d{4})|([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}))\b")


def _month(s: str) -> Optional[int]:
    return _MONTHS.get((s or "")[:3].lower())


def period_from_text(text: str) -> Optional[Tuple[int, int]]:
    """(fiscal year, quarter) when the announcement names it: "Q2 FY27", "Q2FY2026-27", "FY27 Q2", or "quarter ended September 30, 2026". Otherwise None."""
    t = text or ""
    m = _Q_FY.search(t)
    if m:
        yy = m.group(4) or m.group(3) or m.group(6)
        return 2000 + int(yy), int(m.group(1))
    m = _FY_Q.search(t)
    if m:
        yy = m.group(3) or m.group(2) or m.group(5)
        return 2000 + int(yy), int(m.group(6))
    m = _ENDED.search(t)
    if m:
        try:
            d = date(int(m.group(3) or m.group(6)), _month(m.group(2) or m.group(4)) or 0, int(m.group(1) or m.group(5)))
        except ValueError:
            return None
        if d.month in (3, 6, 9, 12) and d.day >= 28:
            return fiscal(d)
    return None


def call_date_from_text(text: str, filed: Optional[date]) -> Optional[date]:
    """The day the call was held, when the announcement says it ("... call held on October 20, 2026"): the first date up to 60 days before the filing (or on it)."""
    for m in _DATE.finditer(text or ""):
        mon = _month(m.group(2) or m.group(4))
        try:
            d = date(int(m.group(3) or m.group(6)), mon or 0, int(m.group(1) or m.group(5)))
        except ValueError:
            continue
        if filed is None or filed - timedelta(days=60) <= d <= filed:
            if d.month not in (3, 6, 9, 12) or d.day < 28 or "held" in (text or "").lower():
                return d
    return None


# ------------------------------------------------------------------------------------------------ announcements -> candidates
@dataclass
class Candidate:
    symbol: str
    url: str
    filed: Optional[datetime]
    text: str
    source: str
    fiscal_year: int = 0
    quarter: int = 0
    call_date: Optional[date] = None

    @property
    def period(self) -> Tuple[int, int]:
        return self.fiscal_year, self.quarter


_TRANSCRIPT = re.compile(r"transcript", re.I)
_FUTURE = re.compile(r"(?:will|shall)\s+be\s+(?:made\s+)?(?:available|uploaded|hosted|shared|submitted)|(?:intimation|invitation|schedule)\s+of\b", re.I)


def is_transcript(text: str, url: str = "") -> bool:
    """An announcement that carries the call's TRANSCRIPT (not the invitation, the schedule or a notice that it will be filed later): the word "transcript" must be there."""
    if not _TRANSCRIPT.search(text or "") and not _TRANSCRIPT.search(url or ""):
        return False
    return not _FUTURE.search(text or "")


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).strip()
    ist = timezone(timedelta(hours=5, minutes=30))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%b-%Y"):
        for cand in (s, s[:19], s[:10], s[:11]):
            try:
                return datetime.strptime(cand, fmt).replace(tzinfo=ist)
            except ValueError:
                continue
    return None


def candidate_from(symbol: str, text: str, url: str, filed: Optional[datetime], source: str) -> Optional[Candidate]:
    """One announcement -> a candidate call, or None when it is not a transcript, has no https link, or its quarter cannot be worked out."""
    if not url or not url.lower().startswith("https://") or not is_transcript(text, url):
        return None
    filed_day = filed.date() if filed else None
    per = period_from_text(text)
    held = call_date_from_text(text, filed_day)
    if per is None:
        anchor = held or filed_day
        if anchor is None:
            return None
        per = quarter_for_call(anchor)
    return Candidate(symbol.upper(), url, filed, " ".join((text or "").split())[:300], source, per[0], per[1], held)


def from_provider_json(items: Iterable[dict]) -> List[Candidate]:
    """FinEdge's /corp-announcements shape (tests/fixtures/finedge/corp_announcements.json): stock_symbol, category, description, announcement_date, pdf_file_link."""
    out = []
    for a in items or []:
        c = candidate_from(a.get("nse_code") or a.get("stock_symbol") or "", f"{a.get('category') or ''} {a.get('description') or ''}", a.get("pdf_file_link") or a.get("pdf_file_link_hist") or "",
                           _parse_ts(a.get("announcement_date")), "feed")
        if c and c.symbol:
            out.append(c)
    return out


def from_nse_json(items: Iterable[dict]) -> List[Candidate]:
    """NSE's corporate-announcements shape: symbol, desc, attchmntText, attchmntFile, an_dt ("23-Oct-2026 18:22:10"). UNVERIFIED against the live API."""
    out = []
    for a in items or []:
        c = candidate_from(a.get("symbol") or "", f"{a.get('desc') or ''} {a.get('attchmntText') or ''}", a.get("attchmntFile") or "", _parse_ts(a.get("an_dt") or a.get("sort_date")), "nse")
        if c and c.symbol:
            out.append(c)
    return out


def from_feed_rows(rows: Iterable[dict]) -> List[Candidate]:
    """Rows of the stored feed (`feed_items`): symbol, title, summary, category, link, item_date."""
    out = []
    for r in rows:
        d = r["item_date"]
        c = candidate_from(r["symbol"] or "", f"{r.get('category') or ''} {r.get('title') or ''} {r.get('summary') or ''}", r.get("link") or "",
                           datetime(d.year, d.month, d.day, 12, tzinfo=timezone(timedelta(hours=5, minutes=30))) if d else None, "feed")
        if c:
            out.append(c)
    return out


def best_per_period(cands: Iterable[Candidate], wanted: Sequence[Tuple[int, int]]) -> Dict[Tuple[str, int, int], Candidate]:
    """One candidate per (company, fiscal year, quarter) among the wanted quarters: the latest filed."""
    best: Dict[Tuple[str, int, int], Candidate] = {}
    for c in cands:
        if c.period not in wanted:
            continue
        k = (c.symbol, c.fiscal_year, c.quarter)
        old = best.get(k)
        if old is None or (c.filed and (old.filed is None or c.filed > old.filed)):
            best[k] = c
    return best


# ------------------------------------------------------------------------------------------------ the polite fetcher
class BudgetSpent(Exception):
    """The run's request budget is used up: stop, the next run continues."""


class Blocked(Exception):
    """The host refused us (robots.txt, 403): nothing more is asked of it in this run."""


class FetchFailed(Exception):
    pass


def relay_settings(env: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, str]]:
    """(address, key) of the free Cloudflare relay that fetches exchange pages for this server, or None. NSE and BSE answer the AWS server's address with 403, so the
    company brief reads them through the relay (deploy/amfi-relay). EXCHANGE_RELAY_URL / EXCHANGE_RELAY_KEY, else the same AMFI_RELAY_URL / AMFI_RELAY_KEY (one worker serves both)."""
    env = os.environ if env is None else env
    url = (env.get("EXCHANGE_RELAY_URL") or env.get("AMFI_RELAY_URL") or "").strip().rstrip("/")
    key = (env.get("EXCHANGE_RELAY_KEY") or env.get("AMFI_RELAY_KEY") or "").strip()
    return (url, key) if url.startswith("https://") and key else None


class Fetcher:
    def __init__(self, budget: int = C.REQUEST_BUDGET_PER_RUN, transport: Optional[httpx.AsyncBaseTransport] = None,
                 sleep: Callable[[float], Any] = asyncio.sleep, pause: float = PAUSE, relay: Optional[Tuple[str, str]] = None):
        self.budget, self.requests, self.pause, self._sleep = budget, 0, pause, sleep
        self.relay = relay if relay is not None else relay_settings()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0), transport=transport, follow_redirects=False, headers={"User-Agent": USER_AGENT})
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self.blocked: Dict[str, str] = {}
        self._nse_cookie = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_once(self, url: str, headers: dict) -> httpx.Response:
        """One GET. Straight to the host first: the exchanges' archive hosts (nsearchives.nseindia.com) answer the AWS server directly. Only when an exchange host
        answers 403 and a relay is set is it asked again through the relay (a browser-like request from another address). If the relay cannot help, the host's own
        403 stands, so a real refusal is still a refusal (Blocked)."""
        r = await self._client.get(url, headers=headers)
        host = urlsplit(url).hostname or ""
        if r.status_code != 403 or not (self.relay and HOST_OK.match(host)):
            return r
        base, key = self.relay
        fwd = {"X-Relay-Key": key}
        for name in ("User-Agent", "Accept", "Referer"):
            if headers.get(name):
                fwd["X-Fwd-" + name] = headers[name]
        try:
            via = await self._client.get(base + "/fetch", params={"u": url}, headers=fwd)
        except httpx.TransportError:
            return r
        if via.headers.get("x-relay-error") or not via.headers.get("x-relay"):    # the relay's own failure, or an answer it did not write: not the exchange's word
            return r
        return via

    # -- one request: budget, pause, back-off on 429 / 503
    async def _send(self, url: str, headers: Optional[dict] = None, stream_cap: Optional[int] = None) -> httpx.Response:
        for attempt in range(3):
            if self.requests >= self.budget:
                raise BudgetSpent()
            self.requests += 1
            await self._sleep(self.pause)
            try:
                r = await self._get_once(url, headers or {})
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise FetchFailed(f"network: {type(exc).__name__}") from None
                await self._sleep(2 * (attempt + 1))
                continue
            if r.status_code in (429, 503) and attempt < 2:
                try:
                    wait = min(60.0, float(r.headers.get("retry-after", 0)))
                except ValueError:
                    wait = 0.0
                await self._sleep(max(wait, 5.0 * (3 ** attempt)))
                continue
            if stream_cap is not None and len(r.content) > stream_cap:
                raise FetchFailed("the file is larger than the cap")
            return r
        raise FetchFailed("did not answer")

    @staticmethod
    def host_ok(url: str) -> bool:
        p = urlsplit(url)
        return p.scheme == "https" and bool(p.hostname) and bool(HOST_OK.match(p.hostname)) and (p.port in (None, 443))

    async def _allowed(self, url: str, agent: str) -> bool:
        p = urlsplit(url)
        host = p.hostname or ""
        if host in self.blocked:
            raise Blocked(self.blocked[host])
        if host not in self._robots:
            rp: Optional[RobotFileParser] = None
            try:
                r = await self._send(f"https://{host}/robots.txt")
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401, 403):
                    self.blocked[host] = f"robots.txt refused ({r.status_code})"
                    raise Blocked(self.blocked[host])
                # 404 and other statuses: no rules to obey
            except FetchFailed:
                self.blocked[host] = "robots.txt unreadable"
                raise Blocked(self.blocked[host]) from None
            self._robots[host] = rp
        rp = self._robots[host]
        if rp is not None and not rp.can_fetch(agent, url):
            raise Blocked(f"robots.txt disallows {p.path}")
        return True

    async def _get(self, url: str, agent: str, headers: Optional[dict] = None, cap: Optional[int] = None) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            if not self.host_ok(url):
                raise FetchFailed("host is not an exchange archive")
            await self._allowed(url, agent)
            r = await self._send(url, {"User-Agent": agent, **(headers or {})}, cap)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = str(httpx.URL(url).join(r.headers["location"]))
                continue
            if r.status_code in (401, 403):
                host = urlsplit(url).hostname or ""
                self.blocked[host] = f"{host} refused the request ({r.status_code})"
                raise Blocked(self.blocked[host])
            return r
        raise FetchFailed("too many redirects")

    # -- the two things we ask for
    async def pdf(self, url: str) -> bytes:
        r = await self._get(url, USER_AGENT, {"Accept": "application/pdf, */*"}, C.MAX_PDF_BYTES)
        if r.status_code != 200:
            raise FetchFailed(f"HTTP {r.status_code}")
        if not r.content.startswith(b"%PDF"):
            raise FetchFailed("not a PDF")
        return r.content

    async def nse_announcements(self, symbol: str, since: date, until: date) -> List[dict]:
        """NSE's announcements for one company between two dates. UNVERIFIED offline."""
        hdr = {"Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"}
        if not self._nse_cookie:
            await self._get(NSE_HOME, NSE_BROWSER_UA, hdr)       # sets the session cookie (the page itself may be refused: the cookie is still set)
            self._nse_cookie = True
        url = f"{NSE_ANNOUNCEMENTS}?index=equities&symbol={symbol}&from_date={since.strftime('%d-%m-%Y')}&to_date={until.strftime('%d-%m-%Y')}"
        r = await self._get(url, NSE_BROWSER_UA, hdr)
        if r.status_code != 200:
            raise FetchFailed(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise FetchFailed("the announcement list was not JSON") from None
        return data if isinstance(data, list) else (data.get("data") or [] if isinstance(data, dict) else [])


# ------------------------------------------------------------------------------------------------ PDF -> text
def extract_pages(pdf: bytes, max_pages: int = MAX_PAGES) -> List[str]:
    """The text of each page (pypdf, pure Python). An empty list when nothing readable is in the file (a scan, a password, a broken file)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:                                  # pragma: no cover - pypdf is in requirements.txt
        raise RuntimeError("pypdf is not installed") from exc
    try:
        rd = PdfReader(io.BytesIO(pdf), strict=False)
        if rd.is_encrypted and not rd.decrypt(""):
            return []
        pages = []
        for i, p in enumerate(rd.pages):
            if i >= max_pages:
                break
            try:
                pages.append((p.extract_text() or "").replace("\x00", ""))
            except Exception:
                pages.append("")
        return pages
    except Exception as exc:
        log.info("could not read a transcript PDF: %s", type(exc).__name__)
        return []


def join_pages(pages: Sequence[str]) -> str:
    return "\f".join(pages)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
