"""Mutual fund industry insights: where India's fund money sits and where it moved, from AMFI's monthly category report.

Source (checked by hand against the live site, October 2026; samples in tests/fixtures/mf_industry):
  amfiindia.com/research-information/amfi-monthly        the page that lists every monthly report (links to the files below)
  portal.amfiindia.com/spages/am<mon><yyyy>repo.xls       one workbook a month: per scheme category, the number of schemes and folios, funds
                                                          mobilised, redemptions, net inflow, assets at the month end and average assets, in
                                                          rupees crore. A corrected file is sometimes published as ...reporevised.xls.
The category-wise layout began with April 2019 (SEBI's scheme categories); the reports before it are by fund-house type and are not read.
Since then the layout has changed in small ways (9 columns until 2020, 11 after; new group headings from August 2026; some files are real .xls,
some are .xlsx under an .xls name), so columns are found by their header words and groups by their heading words, never by position.

Rules: a report is stored only when every check passes (the right month, the expected columns, enough categories, and the categories adding up
to AMFI's own Grand Total); a report that fails is recorded as refused and nothing is stored from it, and a month already stored keeps its
figures. The newest month is asked again each day with its ETag, so a corrected file replaces it and an unchanged one costs a tiny 304.
Written by the `refresh-industry` worker command; read by GET /api/mf/insights. Information only, never advice.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request, Response

from . import mf
from .background import etag_matches
from .disclosure_parsers.xls import XlsWorkbook
from .disclosure_parsers.xlsx import Workbook as XlsxWorkbook
from .store import dumps, etag_for

log = logging.getLogger("finlit.mf_insights")
IST = ZoneInfo("Asia/Kolkata")
router = APIRouter(prefix="/api/mf")

LISTING_URL = "https://www.amfiindia.com/research-information/amfi-monthly"
FILE_BASE = "https://portal.amfiindia.com/spages/"
SOURCE = "AMFI Monthly Category Report"
FIRST_MONTH = date(2019, 4, 1)      # the first report in the category-wise layout
PAUSE = 1.5                         # seconds between downloads: one small file at a time
MAX_FILE = 5_000_000                # a monthly report is 40-120 KB; anything far bigger is not one
MIN_CATEGORIES = 25                 # every real report has 40 or more category rows
RETRY_MISSING_DAYS = 7              # an older month AMFI does not list is asked again after this long (the newest is asked daily)
CACHE_TTL = 6 * 3600
VERSION_KEY = "mfi:ver"
CACHE_HEADER = "public, max-age=600, stale-while-revalidate=3600"
DISCLAIMER = "Information only, never advice. Industry totals as AMFI reports them; they say nothing about any one scheme."
NOT_LOADED = "AMFI's monthly category report has not been loaded yet; the figures appear after the next daily update."

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
GROUPS = (("equity", "Equity"), ("debt", "Debt"), ("hybrid", "Hybrid"), ("solution", "Solution oriented"),
          ("other", "Other: index funds, ETFs, FoF"))
SECTIONS = {"A": "open", "B": "close", "C": "interval"}
SECTION_LABELS = {"open": "Open ended", "close": "Close ended", "interval": "Interval", "fof_domestic": "Fund of funds (domestic)"}
NUM_COLS = ("schemes", "folios", "mobilized", "redemption", "net_flow", "aum", "aaum")


class ReportRejected(ValueError):
    """The file is not a report this parser can vouch for: nothing from it is stored."""


# ------------------------------------------------------------------------------------------------------------- months

def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    k = d.year * 12 + d.month - 1 + n
    return date(k // 12, k % 12 + 1, 1)


def month_end(m: date) -> date:
    return date.fromordinal(add_months(m, 1).toordinal() - 1)


def parse_month(s: str) -> date:
    """'2019-04' -> 2019-04-01 (the worker's --since)."""
    try:
        y, m = s.strip().split("-")[:2]
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        raise ValueError(f"not a month (YYYY-MM): {s!r}") from None


def file_url(m: date, revised: bool = False) -> str:
    return f"{FILE_BASE}am{MONTHS[m.month - 1]}{m.year}repo{'revised' if revised else ''}.xls"


_LINK = re.compile(r"https?://portal\.amfiindia\.com/spages/am([a-z]{3})[a-z]*?(\d{4})repo(revised)?\.(xls|xlsx)\b", re.I)


def listing_links(html: str) -> Dict[date, str]:
    """{month: report URL} from AMFI's listing page. A revised file wins over the first one of the same month; .xls is preferred over .xlsx
    (the page has only ever linked .xls since 2018; .xlsx is taken when it is the only one)."""
    found: Dict[date, Tuple[int, str]] = {}
    for m in _LINK.finditer(html or ""):
        mon = m.group(1).lower()
        if mon not in MONTHS:
            continue
        d = date(int(m.group(2)), MONTHS.index(mon) + 1, 1)
        rank = (2 if m.group(3) else 0) + (1 if m.group(4).lower() == "xls" else 0)
        url = m.group(0).replace("http://", "https://")
        if d not in found or rank > found[d][0]:
            found[d] = (rank, url)
    return {d: u for d, (_, u) in found.items()}


# ------------------------------------------------------------------------------------------------------------- parsing

Cell = object


def read_rows(data: bytes) -> List[List[Cell]]:
    """The rows of the report's sheet. AMFI's files are real .xls (BIFF8) in some years and .xlsx under an .xls name in others; both are read
    with the site's own small readers. The sheet is the first one with a 'folio' column header."""
    if data[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        wb = XlsWorkbook(data)
    elif data[:2] == b"PK":
        try:
            wb = XlsxWorkbook(io.BytesIO(data))
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ReportRejected(f"not a readable workbook ({exc.__class__.__name__})") from None
    else:
        raise ReportRejected("not an Excel workbook (AMFI answered with something else, perhaps a web page)")
    try:
        for i in range(len(wb.sheets)):
            rows = [list(r) for r in wb.rows(i)]
            if any(_has_header(r) for r in rows[:15]):
                return rows
    finally:
        wb.close()
    raise ReportRejected("no sheet has the report's header row (scheme, folios, net inflow ...)")


def _text(c: Cell) -> str:
    if c is None:
        return ""
    if isinstance(c, float):
        return str(int(c)) if c == int(c) else str(c)
    return re.sub(r"\s+", " ", str(c)).strip()


_NUM = re.compile(r"[#*@\s]*(-?)\s*(\d[\d,]*(?:\.\d+)?)\s*[#*@]*")


def _num(c: Cell) -> Optional[float]:
    """A figure cell: a number, or text that is one (AMFI writes '# 158' for a count with a footnote). Blank, '-', '@' and words are None."""
    if isinstance(c, (int, float)):
        return float(c)
    m = _NUM.fullmatch(_text(c))
    return float(m.group(1) + m.group(2).replace(",", "")) if m else None


def _has_header(row: List[Cell]) -> bool:
    j = " | ".join(_text(c).lower() for c in row)
    return "folio" in j and ("net inflow" in j or "outflow" in j)


def _header_kind(h: str) -> Optional[str]:
    h = h.lower()
    if not h or "segregated" in h:
        return None
    if "folio" in h:
        return "folios"
    if re.match(r"no\.?\s*of\s*schemes|number of schemes", h):
        return "schemes"
    if "mobili" in h:
        return "mobilized"
    if "redemption" in h or "repurchase" in h:
        return "redemption"
    if "net inflow" in h or "outflow" in h:
        return "net_flow"
    if "average" in h or "aaum" in h:
        return "aaum"
    if "under management" in h or h.startswith("aum"):
        return "aum"
    if "scheme name" in h or "scheme category" in h or h == "category":
        return "label"
    return None


_MONTH_IN_TEXT = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[\s,\-]*(?:\d{1,2}(?:st|nd|rd|th)?[\s,\-]+)?((?:19|20)\d{2})\b", re.I)


def months_named(texts: Iterable[str]) -> set:
    return {date(int(m.group(2)), MONTHS.index(m.group(1).lower()) + 1, 1) for t in texts for m in _MONTH_IN_TEXT.finditer(t)}


def group_of(section: str, heading: str) -> Optional[str]:
    """Our group for a heading AMFI prints: equity, debt, hybrid, solution (incl. life cycle funds), other (index funds, ETFs, overseas fund
    of funds). None for a heading not seen before: the report is then refused rather than guessed at."""
    h = heading.lower()
    if section == "fof_domestic":
        return "fof_domestic"
    if re.search(r"other|index|exchange traded|\betf|fund of funds", h):
        return "other"
    if "solution" in h or "life cycle" in h:
        return "solution"
    if "hybrid" in h:
        return "hybrid"
    if "debt" in h or "income" in h:
        return "debt"
    if "equity" in h or "growth" in h:
        return "equity"
    return None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


@dataclass
class Row:
    key: str
    pos: int
    section: str
    heading: str
    category: str
    grp: str
    values: Dict[str, Optional[float]]


@dataclass
class Report:
    month: date
    rows: List[Row]
    total: Dict[str, Optional[float]]
    released: Optional[date] = None


def _tolerance(col: str, ref: float, n: int) -> float:
    """How far a sum may be from AMFI's printed total: counts must agree exactly; amounts are printed to 2 decimals, so each row may be off by
    half a paisa-crore, plus a hair of relative slack."""
    if col in ("schemes", "folios"):
        return 0.5
    return 0.006 * max(n, 1) + abs(ref) * 1e-6


_RELEASED = re.compile(r"released\s+on\s*:?\s*(\d{1,2})[.\-/\s]+([a-z]{3,9}|\d{1,2})[.\-/\s]+(\d{4})", re.I)


def _released(text: str) -> Optional[date]:
    m = _RELEASED.search(text)
    if not m:
        return None
    mon = m.group(2).lower()
    try:
        mm = int(mon) if mon.isdigit() else MONTHS.index(mon[:3]) + 1
        return date(int(m.group(3)), mm, int(m.group(1)))
    except (ValueError, IndexError):
        return None


def parse_report(data: bytes, month: date) -> Report:
    """One month's report -> its category rows and Grand Total. Raises ReportRejected (with the reason in words) when any check fails."""
    if len(data) > MAX_FILE:
        raise ReportRejected(f"the file is {len(data)} bytes, far bigger than a monthly report")
    rows = read_rows(data)
    hi = next((i for i, r in enumerate(rows) if _has_header(r)), None)
    if hi is None:
        raise ReportRejected("no header row (scheme, folios, net inflow ...)")
    cols: Dict[str, int] = {}
    for ci, c in enumerate(rows[hi]):
        k = _header_kind(_text(c))
        if k and k not in cols:
            cols[k] = ci
    missing = [k for k in ("label", *NUM_COLS) if k not in cols]
    if missing:
        raise ReportRejected("the header lacks the column(s) " + ", ".join(missing))

    named = months_named(" ".join(_text(c) for c in r) for r in rows[:hi + 1])
    if named != {month}:
        said = ", ".join(sorted(d.strftime("%b %Y") for d in named)) or "no month"
        raise ReportRejected(f"the file names {said}, not {month.strftime('%b %Y')}")

    lc = cols["label"]
    section, heading = "", ""
    out: List[Row] = []
    keys: set = set()
    total: Optional[Dict[str, Optional[float]]] = None
    released: Optional[date] = None
    sums: Dict[str, Dict[str, float]] = {"heading": {}, "section": {}, "all": {}}
    counts = {"heading": 0, "section": 0, "all": 0}

    def check(scope: str, printed: Dict[str, Optional[float]], what: str) -> None:
        for c in NUM_COLS:
            p = printed.get(c)
            if p is None:
                continue
            got = sums[scope].get(c, 0.0)
            if abs(got - p) > _tolerance(c, p, counts[scope]):
                raise ReportRejected(f"{what}: the categories add up to {got:,.2f} {c.replace('_', ' ')}, AMFI's total says {p:,.2f}")

    def reset(scope: str) -> None:
        sums[scope], counts[scope] = {}, 0

    for r in rows[hi + 1:]:
        marker = _text(r[0]) if r else ""
        label = re.sub(r"[\s*#@$]+$", "", _text(r[lc]) if len(r) > lc else "")   # "Solution Oriented Schemes **": footnote marks are not part of the name
        line = " ".join(_text(c) for c in r)
        if total is not None:                                    # after the Grand Total: the domestic fund of funds line and notes
            released = released or _released(line)
            if re.search(r"fund of funds scheme \(domestic\)", label, re.I):
                vals = {c: _num(r[cols[c]]) if len(r) > cols[c] else None for c in NUM_COLS}
                if vals["aum"] is not None:
                    out.append(Row("fofdomestic", len(out), "fof_domestic", "Fund of Funds Scheme (Domestic)", "Fund of funds (domestic)",
                                   "fof_domestic", vals))
            continue
        if not label and not marker:
            continue
        vals = {c: _num(r[cols[c]]) if len(r) > cols[c] else None for c in NUM_COLS}
        has_vals = vals["aum"] is not None or vals["net_flow"] is not None
        low = label.lower()
        if low.startswith("grand total"):
            if not has_vals:
                raise ReportRejected("the Grand Total row has no figures")
            total = vals
            check("all", vals, "Grand Total")
            continue
        if re.match(r"(sub[\s-]*)?total\b", low):
            if not has_vals:
                continue
            if low.startswith("sub"):
                check("heading", vals, f"{label} ({heading or 'no heading'})")
            else:
                check("section", vals, label)
            continue
        if marker in SECTIONS and not has_vals:                   # A / B / C: open ended, close ended, interval
            section, heading = SECTIONS[marker], ""
            reset("section"); reset("heading")
            continue
        if not section:
            continue
        if re.fullmatch(r"[IVX]+", marker):                       # a group heading; in parts B and C a heading may carry figures itself
            heading = label
            reset("heading")
            if not has_vals:
                continue
            category = label
        elif has_vals and label:
            category = label
        else:
            continue
        if not heading:                                           # since August 2026 part C lists "i Income/Debt Oriented Schemes" with no heading
            if group_of(section, category) is None:
                raise ReportRejected(f"the category {category!r} comes before any group heading")
            heading = category
        grp = group_of(section, heading)
        if grp is None:
            raise ReportRejected(f"an unknown group heading {heading!r}: the report's layout has changed")
        if vals["aum"] is None:
            raise ReportRejected(f"the category {category!r} has no assets figure")
        key = "/".join((section, _slug(heading), _slug(category)))
        while key in keys:
            key += "+"
        keys.add(key)
        out.append(Row(key, len(out), section, heading, category, grp, vals))
        for scope in ("heading", "section", "all"):
            counts[scope] += 1
            for c in NUM_COLS:
                if vals[c] is not None:
                    sums[scope][c] = sums[scope].get(c, 0.0) + vals[c]

    if total is None:
        raise ReportRejected("no Grand Total row")
    n = sum(1 for x in out if x.section != "fof_domestic")
    if n < MIN_CATEGORIES:
        raise ReportRejected(f"only {n} categories (a real report has at least {MIN_CATEGORIES})")
    if not total.get("aum") or total["aum"] <= 0 or not total.get("folios"):
        raise ReportRejected("the Grand Total has no assets or folios")
    if {c for c, v in total.items() if v is None} - {"aaum"}:
        raise ReportRejected("the Grand Total lacks a figure")
    flow = (total["mobilized"] or 0) - (total["redemption"] or 0)
    if abs(flow - (total["net_flow"] or 0)) > 1.0 + abs(flow) * 1e-6:
        raise ReportRejected(f"the Grand Total's net inflow {total['net_flow']:,.2f} is not mobilised minus redeemed ({flow:,.2f})")
    return Report(month, out, total, released)


# ------------------------------------------------------------------------------------------------------------- fetching

@dataclass
class Got:
    status: int                 # 200, 304 (unchanged since the ETag we sent) or 404 (not published)
    url: str
    data: bytes = b""
    etag: Optional[str] = None


async def _download(client: httpx.AsyncClient, url: str, etag: Optional[str] = None) -> Got:
    """One report file. Transient failures (timeouts, resets, 5xx) are retried with growing waits; 304 and 404 are answers, not errors."""
    async def go():
        r = await client.get(url, headers={"If-None-Match": etag} if etag else None)
        if r.status_code not in (304, 404):
            r.raise_for_status()
        return r
    r = await mf._retry(go)
    if r.status_code in (304, 404):
        return Got(r.status_code, url)
    return Got(200, url, r.content, r.headers.get("etag"))


async def fetch_month(client: httpx.AsyncClient, m: date, url: Optional[str], etag: Optional[str] = None) -> Got:
    """The month's file: the URL AMFI's listing gives, else the usual name and then the 'revised' name."""
    got = Got(404, url or file_url(m))
    for u in ([url] if url else [file_url(m), file_url(m, revised=True)]):
        got = await _download(client, u, etag)
        if got.status != 404:
            return got
    return got


async def fetch_listing(client: httpx.AsyncClient) -> Dict[date, str]:
    async def go():
        r = await client.get(LISTING_URL)
        r.raise_for_status()
        return r
    return listing_links((await mf._retry(go)).content.decode("utf-8", "replace"))


# ------------------------------------------------------------------------------------------------------------- writing

ROW_INSERT = ("INSERT INTO mf_industry (month, key, pos, section, heading, category, grp, schemes, folios, mobilized, redemption, net_flow, aum, aaum) "
              "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)")
MONTH_UPSERT = """INSERT INTO mf_industry_months (month, status, why, schemes, folios, mobilized, redemption, net_flow, aum, aaum, released, source_url, etag,
                                                  sha256, n_rows, fetched_at)
                  VALUES ($1, 'ok', NULL, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
                  ON CONFLICT (month) DO UPDATE SET status = 'ok', why = NULL, schemes = EXCLUDED.schemes, folios = EXCLUDED.folios,
                      mobilized = EXCLUDED.mobilized, redemption = EXCLUDED.redemption, net_flow = EXCLUDED.net_flow, aum = EXCLUDED.aum,
                      aaum = EXCLUDED.aaum, released = EXCLUDED.released, source_url = EXCLUDED.source_url, etag = EXCLUDED.etag,
                      sha256 = EXCLUDED.sha256, n_rows = EXCLUDED.n_rows, fetched_at = now()"""


def _int(v: Optional[float]) -> Optional[int]:
    return None if v is None else int(round(v))


async def save_report(conn, rep: Report, url: str, etag: Optional[str], sha: str) -> None:
    """One month replaces whatever was stored for it, in one transaction: a reader never sees two versions of a month mixed."""
    t = rep.total
    async with conn.transaction():
        await conn.execute("DELETE FROM mf_industry WHERE month = $1", rep.month)
        await conn.executemany(ROW_INSERT, [(rep.month, r.key, r.pos, r.section, r.heading, r.category, r.grp, _int(r.values["schemes"]),
                                             _int(r.values["folios"]), r.values["mobilized"], r.values["redemption"], r.values["net_flow"],
                                             r.values["aum"], r.values["aaum"]) for r in rep.rows])
        await conn.execute(MONTH_UPSERT, rep.month, _int(t["schemes"]), _int(t["folios"]), t["mobilized"], t["redemption"], t["net_flow"], t["aum"],
                           t["aaum"], rep.released, url, etag, sha, len(rep.rows))


async def _mark(conn, m: date, status: str, why: str, url: Optional[str]) -> None:
    """A month with no stored figures: why (not published yet, or refused). A stored month is never downgraded: its figures stay."""
    await conn.execute("INSERT INTO mf_industry_months (month, status, why, source_url, fetched_at) VALUES ($1, $2, $3, $4, now()) "
                       "ON CONFLICT (month) DO UPDATE SET status = EXCLUDED.status, why = EXCLUDED.why, source_url = EXCLUDED.source_url, fetched_at = now() "
                       "WHERE mf_industry_months.status <> 'ok'", m, status, why[:300], url)


async def bump(store) -> None:
    """New figures landed: cached answers built from older ones stop being served (their key includes the version)."""
    try:
        await store.redis.set(VERSION_KEY, str(int(time.time() * 1000)))
    except Exception:
        log.warning("could not publish the industry data version to Redis")


def plan(known: Dict[date, dict], links: Dict[date, str], first: date, last: date, now: datetime) -> List[Tuple[date, Optional[str], Optional[str]]]:
    """Which months to ask for, oldest first: (month, URL or None for the usual names, ETag to send or None).
      never tried                       -> ask
      stored, AMFI now links a new file -> ask (a 'revised' report)
      stored, the newest one            -> ask with its ETag (a corrected file replaces it; an unchanged one answers 304)
      missing / refused                 -> ask daily when it is one of the two newest months or AMFI links a new file, else after RETRY_MISSING_DAYS"""
    newest_ok = max((m for m, k in known.items() if k["status"] == "ok"), default=None)
    out = []
    m = first
    while m <= last:
        k, link = known.get(m), links.get(m)
        if k is None:
            out.append((m, link, None))
        elif k["status"] == "ok":
            if link and link != k["source_url"]:
                out.append((m, link, None))
            elif m == newest_ok:
                out.append((m, k["source_url"], k["etag"]))
        elif m >= add_months(last, -1) or (link and link != k["source_url"]) or (now - k["fetched_at"]).total_seconds() > RETRY_MISSING_DAYS * 86400:
            out.append((m, link, None))
        m = add_months(m, 1)
    return out


async def refresh(store, settings=None, *, since: Optional[date] = None, client: Optional[httpx.AsyncClient] = None, today: Optional[date] = None,
                  pause: float = PAUSE) -> dict:
    """Load every month from `since` (default: April 2019, the first category-wise report) to last month that is not stored yet, and ask for
    the newest stored month again with its ETag. Resumable: a stopped run loses nothing, the next one carries on. One file at a time, paced."""
    today = today or datetime.now(IST).date()
    last = add_months(month_start(today), -1)
    first = max(month_start(since), FIRST_MONTH) if since else FIRST_MONTH
    own = client is None
    client = client or mf.make_client()
    stored: List[str] = []
    unchanged: List[str] = []
    missing: List[str] = []
    refused: Dict[str, str] = {}
    failed: Dict[str, str] = {}
    try:
        async with store.pool.acquire() as conn:
            known = {r["month"]: dict(r) for r in await conn.fetch("SELECT month, status, source_url, etag, sha256, fetched_at FROM mf_industry_months")}
        try:
            links = await fetch_listing(client)
            listing = f"{len(links)} reports listed"
        except Exception as exc:    # the files have stable names: carry on without the page
            links = {}
            listing = f"unavailable ({exc.__class__.__name__}); the usual file names were tried"
        todo = plan(known, links, first, last, datetime.now(timezone.utc))
        for i, (m, url, etag) in enumerate(todo):
            if i and pause:
                await asyncio.sleep(pause)
            label = m.strftime("%Y-%m")
            try:
                got = await fetch_month(client, m, url, etag)
                if got.status == 304:
                    unchanged.append(label)
                    continue
                async with store.pool.acquire() as conn:
                    if got.status == 404:
                        missing.append(label)
                        await _mark(conn, m, "missing", "AMFI has not published this month's report (yet)", got.url)
                        continue
                    sha = hashlib.sha256(got.data).hexdigest()
                    if known.get(m, {}).get("sha256") == sha:
                        unchanged.append(label)
                        await conn.execute("UPDATE mf_industry_months SET etag = $2, source_url = $3, fetched_at = now() WHERE month = $1",
                                           m, got.etag, got.url)
                        continue
                    try:
                        rep = await asyncio.to_thread(parse_report, got.data, m)
                    except ReportRejected as exc:
                        kept = known.get(m, {}).get("status") == "ok"
                        refused[label] = str(exc) + (" (the stored figures were kept)" if kept else "")
                        log.warning("AMFI monthly report %s refused: %s", label, exc)
                        await _mark(conn, m, "refused", str(exc), got.url)
                        continue
                    await save_report(conn, rep, got.url, got.etag, sha)
                    stored.append(label)
            except Exception as exc:     # one month failing (network, a broken file) never stops the others
                log.warning("AMFI monthly report %s failed: %r", label, exc)
                failed[label] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
    finally:
        if own:
            await client.aclose()
    if stored:
        await bump(store)
    async with store.pool.acquire() as conn:
        latest = await conn.fetchval("SELECT max(month) FROM mf_industry_months WHERE status = 'ok'")
        n = await conn.fetchval("SELECT count(*) FROM mf_industry_months WHERE status = 'ok'")
    bad = len(failed) + len(refused)
    status = "failed" if todo and bad == len(todo) else ("partial" if bad else "ok")
    return {"status": status, "latest": latest.strftime("%Y-%m") if latest else None, "months": n, "stored": stored, "unchanged": unchanged,
            "missing": missing, "refused": refused, "failed": failed, "listing": listing}


# ------------------------------------------------------------------------------------------------------------- reading

def _r(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None else round(float(v), n)


def _kpi(cur: Optional[float], prev: Optional[float], ratio: bool = True) -> dict:
    """A figure with its change against the month before (None when there is no month before)."""
    out = {"value": _r(cur), "prev": _r(prev), "change": None, "changePct": None}
    if cur is not None and prev is not None:
        out["change"] = _r(cur - prev)
        if ratio and prev:
            out["changePct"] = _r((cur / prev - 1) * 100)
    return out


def _item(r) -> dict:
    return {"name": r["category"], "heading": r["heading"], "section": r["section"], "sectionLabel": SECTION_LABELS.get(r["section"], r["section"]),
            "schemes": r["schemes"], "folios": r["folios"], "mobilized": _r(r["mobilized"]), "redemption": _r(r["redemption"]),
            "netFlow": _r(r["net_flow"]), "aum": _r(r["aum"]), "aaum": _r(r["aaum"])}


def _sum(rows, col: str) -> Optional[float]:
    vals = [r[col] for r in rows if r[col] is not None]
    return sum(vals) if vals else None


def _gaps(months: List[date]) -> List[str]:
    have, out = set(months), []
    m = months[0]
    while m < months[-1]:
        if m not in have:
            out.append(m.strftime("%Y-%m"))
        m = add_months(m, 1)
    return out


async def build_insights(pool) -> dict:
    """Everything the insights page shows, from the stored months. Amounts in rupees crore; folios and schemes are counts."""
    base = {"source": SOURCE, "sourcePage": LISTING_URL, "disclaimer": DISCLAIMER, "unit": "crore",
            "coverage": "AMFI's category-wise monthly report began in April 2019; earlier reports use another layout and are not shown."}
    async with pool.acquire() as conn:
        months = await conn.fetch("SELECT month, schemes, folios, mobilized, redemption, net_flow, aum, aaum, released, source_url, fetched_at "
                                  "FROM mf_industry_months WHERE status = 'ok' ORDER BY month")
        if not months:
            return {**base, "status": "empty", "reason": NOT_LOADED}
        latest = months[-1]
        prev = months[-2] if len(months) > 1 and months[-2]["month"] == add_months(latest["month"], -1) else None
        eq = {r["month"]: r["aum"] for r in await conn.fetch("SELECT month, sum(aum) AS aum FROM mf_industry WHERE grp = 'equity' GROUP BY month")}
        rows = await conn.fetch("SELECT * FROM mf_industry WHERE month = $1 ORDER BY pos", latest["month"])
        prev_rows = await conn.fetch("SELECT grp, aum, net_flow FROM mf_industry WHERE month = $1", prev["month"]) if prev else []
    pm = prev["month"] if prev else None
    total_aum = latest["aum"] or 0.0
    groups = []
    for key, label in GROUPS:
        g = [r for r in rows if r["grp"] == key]
        if not g:
            continue
        gp = [r for r in prev_rows if r["grp"] == key]
        aum = _sum(g, "aum")
        groups.append({"key": key, "label": label, "schemes": _sum(g, "schemes"), "folios": _sum(g, "folios"), "netFlow": _r(_sum(g, "net_flow")),
                       "aum": _r(aum), "aaum": _r(_sum(g, "aaum")), "share": _r((aum or 0) / total_aum * 100) if total_aum else None,
                       "prevAum": _r(_sum(gp, "aum")) if gp else None, "prevNetFlow": _r(_sum(gp, "net_flow")) if gp else None,
                       "items": [_item(r) for r in g]})
    fof = next((r for r in rows if r["grp"] == "fof_domestic"), None)
    return {
        **base, "status": "ok", "month": latest["month"].strftime("%Y-%m"), "asOf": month_end(latest["month"]).isoformat(),
        "prevMonth": pm.strftime("%Y-%m") if pm else None, "released": latest["released"].isoformat() if latest["released"] else None,
        "updatedAt": latest["fetched_at"].isoformat(timespec="seconds"), "sourceUrl": latest["source_url"],
        "kpis": {
            "aum": _kpi(latest["aum"], prev["aum"] if prev else None),
            "netFlow": {**_kpi(latest["net_flow"], prev["net_flow"] if prev else None, ratio=False),
                        "mobilized": _r(latest["mobilized"]), "redemption": _r(latest["redemption"])},
            "folios": _kpi(latest["folios"], prev["folios"] if prev else None),
            "equityAum": _kpi(eq.get(latest["month"]), eq.get(pm) if pm else None),
        },
        "series": {"t": [month_end(r["month"]).isoformat() for r in months], "aum": [_r(r["aum"]) for r in months],
                   "netFlow": [_r(r["net_flow"]) for r in months], "folios": [r["folios"] for r in months],
                   "equityAum": [_r(eq.get(r["month"])) for r in months]},
        "gaps": _gaps([r["month"] for r in months]),
        "groups": groups,
        "fofDomestic": None if fof is None else {**_item(fof), "note": "AMFI leaves domestic fund of funds out of its totals: the money they invest "
                                                                        "is already counted in the schemes they buy."},
    }


async def _version(redis) -> str:
    try:
        v = await redis.get(VERSION_KEY)
        return v.decode() if isinstance(v, bytes) else (v or "0")
    except Exception:
        return "0"


@router.get("/insights")
async def insights(request: Request) -> Response:
    """The Mutual Fund Insights page: the latest month with the month before, the monthly series, the category table and the group split.
    Rendered once per data version and kept in Redis (refresh-industry bumps the version when a month lands), with ETag / 304."""
    store = request.app.state.store
    rk = f"mfi:{await _version(store.redis)}:insights"
    try:
        hit = await store.redis.hmget(rk, ["body", "etag"])
    except Exception:
        hit = [None, None]
    if hit[0] is None:
        body = dumps(await build_insights(store.pool))
        etag = etag_for(body)
        try:
            await store.redis.hset(rk, mapping={"body": body, "etag": etag})
            await store.redis.expire(rk, CACHE_TTL)
        except Exception:
            pass
    else:
        body, etag = hit[0], hit[1].decode() if isinstance(hit[1], bytes) else hit[1]
    headers = {"ETag": etag, "Cache-Control": CACHE_HEADER}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
