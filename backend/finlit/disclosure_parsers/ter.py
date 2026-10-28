"""Total expense ratio (TER) of the Regular and Direct plan of each scheme, read from the fund houses' own TER pages.

Why: AMFI's TER feed (finlit.disclosure step_ter) cannot be reached from our server's address range. SEBI requires every fund house to publish
scheme-wise, plan-wise TER every day on its own website, so those public pages and files are read instead. Nothing here goes around a block:
each source is what the fund house's page offers any visitor, fetched with an ordinary request, one or two requests per house per night.
A house whose page needs a login, a token or a bot check is not read (see docs/NEXT-STEPS-FUNDS.md for each house).

Each `src_*` coroutine takes (client, index, today) and returns (rows, stats), the same shape as managers_risk:
    rows   [(family, "ter", as_of, {"regular": 1.89 | None, "direct": 1.29 | None}, source, source_url)]   percent a year, total TER
    stats  {"seen", "matched", "unmatched", "rows", "refused", "stale"}

Refused, never stored: a figure outside 0 to 3.5 percent, a Direct plan above the Regular plan of the same scheme, a row older than MAX_AGE_DAYS,
a sheet whose header is not the SEBI layout. The newest row per scheme wins (the workbooks carry one row per scheme and day).

Run: `python -m finlit.disclosure_parsers.ter [--only sbi nippon ...] [--write]`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from .managers_risk import Collector, get, make_client
from .sebi import NotAPortfolio, open_workbook

log = logging.getLogger("finlit.ter")

Row = Tuple[str, str, Optional[date], dict, str, Optional[str]]

TER_MAX = 3.5                 # percent a year; SEBI's own ceilings are lower, so anything above is a misread
MAX_AGE_DAYS = 45             # a figure older than this is not shown as the scheme's TER
MAX_BYTES = 40 * 1024 * 1024
PAUSE = 1.0                   # seconds between fund houses
EXCEL_EPOCH = date(1899, 12, 30)

SRC_SBI = "SBI Mutual Fund, scheme-wise TER (sbimf.com)"
SRC_NIPPON = "Nippon India Mutual Fund, scheme-wise TER (mf.nipponindiaim.com)"
SRC_TATA = "Tata Mutual Fund, scheme-wise TER (tatamutualfund.com)"
SRC_SUNDARAM = "Sundaram Mutual Fund, daily TER (sundarammutual.com)"
SRC_CANARA = "Canara Robeco Mutual Fund, daily TER (canararobeco.com)"
URL_SBI_PAGE = "https://www.sbimf.com/total-expense-ratio"
URL_SBI = "https://www.sbimf.com/docs/default-source/ter_allschemes/current-year-ter.xlsx"
URL_NIPPON_PAGE = "https://mf.nipponindiaim.com/investor-services/downloads/total-expense-ratio-of-mutual-fund-schemes"
URL_NIPPON = "https://mf.nipponindiaim.com/TotalExpenseRatio/TotalExpenseRatio{fy}.xlsx"
URL_TATA_PAGE = "https://www.tatamutualfund.com/expense-ratio/total-expense-ratio"
URL_SUNDARAM_PAGE = "https://www.sundarammutual.com/ter"
URL_SUNDARAM = "https://www.sundarammutual.com/ajax/Views_TER_V2,App_Web_bvj3k5zr.ashx?_method=DailyTER&_session=no"
URL_CANARA = "https://www.canararobeco.com/wp-json/ter/v1/records"

AMC_RE = {
    "sbi": re.compile(r"^SBI\b", re.I),
    "nippon": re.compile(r"^Nippon\b", re.I),
    "tata": re.compile(r"^Tata\b", re.I),
    "sundaram": re.compile(r"^Sundaram\b", re.I),
    "canara": re.compile(r"^Canara\b", re.I),
}


# ------------------------------------------------------------------------------------------------------------- values

def num(v) -> Optional[float]:
    """A percent from a cell: 1.29, '1.29', '1.29%'; None for blanks and dashes."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", "")
    if s in ("", "-", "--", "NA", "N/A", "N.A.", "NIL", "Nil"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_date(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return EXCEL_EPOCH + timedelta(days=int(v)) if 36000 < v < 80000 else None
    s = str(v or "").strip()
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return to_date(float(s))
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt).date()
        except ValueError:
            continue
    return None


def plans_ok(regular: Optional[float], direct: Optional[float]) -> Optional[str]:
    """None when the pair may be stored, else the reason it is refused."""
    if regular is None and direct is None:
        return "no figure"
    for p, v in (("Regular", regular), ("Direct", direct)):
        if v is not None and not (0 <= v <= TER_MAX):
            return f"{p} TER {v} outside 0 to {TER_MAX}"
    if regular is not None and direct is not None and direct > regular:
        return f"Direct TER {direct} above Regular {regular}"
    return None


def norm(v: float) -> float:
    return round(v + 1e-9, 2)


# ------------------------------------------------------------------------------------------------------------- the SEBI sheet layout

class TerRec:
    __slots__ = ("name", "code", "as_of", "regular", "direct")

    def __init__(self, name: str, code: str, as_of: date, regular: Optional[float], direct: Optional[float]):
        self.name, self.code, self.as_of, self.regular, self.direct = name, code, as_of, regular, direct


def _header(row: Sequence) -> Optional[dict]:
    cols: Dict[str, int] = {}
    for i, c in enumerate(row):
        t = re.sub(r"\s+", " ", str(c or "")).strip().lower()
        if "scheme name" in t:
            cols.setdefault("name", i)
        elif t.startswith("nsdl") or "scheme code" in t:
            cols.setdefault("code", i)
        elif t.startswith("ter date") or t == "date":
            cols.setdefault("date", i)
        elif "total ter" in t and t.startswith("regular plan"):
            cols.setdefault("regular", i)
        elif "total ter" in t and t.startswith("direct plan"):
            cols.setdefault("direct", i)
    return cols if {"name", "date", "regular", "direct"} <= set(cols) else None


def parse_sheet(rows: Iterable[Sequence], stats: dict, best: Dict[str, TerRec]) -> bool:
    """Reads one sheet of the layout SEBI prescribes (NSDL scheme code, scheme name, TER date, then Regular and Direct plan columns ending in 'Total TER').
    Keeps the newest valid row per scheme in `best`. False when the sheet has no such header."""
    cols = None
    for n, row in enumerate(rows):
        if cols is None:
            cols = _header(row) if n < 20 else None
            if cols is None and n >= 20:
                return False
            continue
        raw = row[cols["name"]] if cols["name"] < len(row) else None
        name = re.sub(r"\s+", " ", str(raw or "")).strip()
        d = to_date(row[cols["date"]]) if cols["date"] < len(row) else None
        if not name or d is None:
            continue
        get_ = lambda k: num(row[cols[k]]) if cols[k] < len(row) else None
        code = str(row[cols["code"]]).strip() if "code" in cols and cols["code"] < len(row) and row[cols["code"]] else name
        key = code or name
        cur = best.get(key)
        if cur is None or d >= cur.as_of:          # the newest statement stands, valid or not: an older figure never stands in for a refused newer one
            best[key] = TerRec(name, code, d, get_("regular"), get_("direct"))
    return cols is not None


def settle(best: Dict[str, TerRec], stats: dict) -> Dict[str, TerRec]:
    """Check the newest row of each scheme; a row that fails is counted and dropped."""
    out: Dict[str, TerRec] = {}
    for k, r in best.items():
        if r.regular == 0 and r.direct is not None and r.direct > 0:
            r.regular = None                       # an ETF filed with 0.00 under Regular and its real figure under Direct: the Regular plan is not offered
        why = plans_ok(r.regular, r.direct)
        if why:
            stats["refused"] = stats.get("refused", 0) + 1
            stats.setdefault("refusedWhy", []).append(f"{r.name}: {why}"[:100])
            continue
        r.regular = None if r.regular is None else norm(r.regular)
        r.direct = None if r.direct is None else norm(r.direct)
        out[k] = r
    return out


def parse_workbook(path: str, stats: dict) -> Dict[str, TerRec]:
    best: Dict[str, TerRec] = {}
    wb = open_workbook(path)
    found = False
    try:
        for i in range(len(wb.sheets)):
            found |= parse_sheet(wb.rows(i), stats, best)
    finally:
        wb.close()
    if not found:
        raise NotAPortfolio("no sheet with the SEBI TER header (scheme name, TER date, Regular and Direct 'Total TER')")
    return settle(best, stats)


def emit(c: Collector, recs: Iterable[TerRec], today: date, url: str, stats: dict) -> None:
    """Resolve each record to a scheme family and add a 'ter' row; stale rows are counted and skipped."""
    for r in recs:
        if (today - r.as_of).days > MAX_AGE_DAYS or r.as_of > today + timedelta(days=1):
            stats["stale"] = stats.get("stale", 0) + 1
            continue
        fam = c.resolve([r.name])
        if fam is not None:
            c.add(fam, "ter", r.as_of, {"regular": r.regular, "direct": r.direct}, url)


def finish(c: Collector, stats: dict) -> Tuple[List[Row], dict]:
    rows, st = c.result()
    st.update({k: v for k, v in stats.items() if k != "refusedWhy"})
    if stats.get("refusedWhy"):
        st["refusedExamples"] = stats["refusedWhy"][:5]
    st.setdefault("refused", 0)
    st.setdefault("stale", 0)
    return rows, st


async def fetch_file(client: httpx.AsyncClient, url: str) -> bytes:
    r = await get(client, url)
    if len(r.content) > MAX_BYTES:
        raise ValueError(f"file over {MAX_BYTES} bytes")
    return r.content


def _read_book(data: bytes, suffix: str, stats: dict) -> Dict[str, TerRec]:
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return parse_workbook(path, stats)
    finally:
        os.unlink(path)


async def book_source(client, idx, today: date, house: str, source: str, url: str, page_url: str, data: Optional[bytes] = None):
    stats: dict = {}
    c = Collector(idx, house, source)
    c.amc_re = AMC_RE[house]
    data = data if data is not None else await fetch_file(client, url)
    recs = await asyncio.to_thread(_read_book, data, ".xls" if url.lower().endswith(".xls") else ".xlsx", stats)
    emit(c, recs.values(), today, page_url, stats)
    return finish(c, stats)


# ------------------------------------------------------------------------------------------------------------- the houses

async def src_sbi(client, idx, today: date):
    """sbimf.com/total-expense-ratio offers 'current-year-ter.xlsx': one row per scheme and day of the financial year."""
    return await book_source(client, idx, today, "sbi", SRC_SBI, URL_SBI, URL_SBI_PAGE)


def fy_label(d: date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{y + 1}"


async def src_nippon(client, idx, today: date):
    """mf.nipponindiaim.com lists one workbook per financial year (TotalExpenseRatio2026-2027.xlsx); in early April the new file may not exist yet."""
    last = None
    for d in (today, today - timedelta(days=45)):
        url = URL_NIPPON.format(fy=fy_label(d))
        try:
            data = await fetch_file(client, url)
        except httpx.HTTPStatusError as exc:
            last = exc
            continue
        return await book_source(client, idx, today, "nippon", SRC_NIPPON, url, URL_NIPPON_PAGE, data)
    raise last or RuntimeError("no Nippon TER file")


def tata_file_url(page: str, today: date) -> Optional[str]:
    """The current financial year's workbook on Tata's TER page (the file name carries 'April2026 to Mar2027')."""
    y = today.year if today.month >= 4 else today.year - 1
    m = re.search(rf"https://www\.tatamutualfund\.com/system/files/[^\"\\\s]*TotalExpenseRatioApril{y}(?:%20|\s)to(?:%20|\s)Mar{y + 1}[^\"\\\s]*\.xlsx?", page)
    return m.group(0) if m else None


async def src_tata(client, idx, today: date):
    page = (await get(client, URL_TATA_PAGE)).text
    url = tata_file_url(page, today)
    if not url:
        raise ValueError("Tata's TER page shows no file for this financial year")
    return await book_source(client, idx, today, "tata", SRC_TATA, url, URL_TATA_PAGE)


def parse_sundaram(text: str) -> List[dict]:
    s = text.strip()
    if s[:1] == s[-1:] == "'":
        s = s[1:-1]
    data = json.loads(s.replace("\\'", "'"))
    return data if isinstance(data, list) else []


async def src_sundaram(client, idx, today: date):
    """Sundaram's TER page loads its daily table with one call (AjaxPro 'DailyTER'); the answer is JSON text with Regular (RP_) and Direct (DP_) totals."""
    r = await client.post(URL_SUNDARAM, content=b"", headers={"Content-Type": "text/plain; charset=UTF-8"})
    r.raise_for_status()
    stats: dict = {}
    c = Collector(idx, "sundaram", SRC_SUNDARAM)
    c.amc_re = AMC_RE["sundaram"]
    recs = []
    for it in parse_sundaram(r.text):
        d, reg, dr = to_date(it.get("Ter_Date_Disp")), num(it.get("RP_TOT_TER")), num(it.get("DP_TOT_TER"))
        name = str(it.get("Group_Name") or "").strip()
        if not name or d is None:
            continue
        why = plans_ok(reg, dr)
        if why:
            stats["refused"] = stats.get("refused", 0) + 1
            continue
        recs.append(TerRec(name, str(it.get("NSDL_CODE") or name), d, None if reg is None else norm(reg), None if dr is None else norm(dr)))
    emit(c, recs, today, URL_SUNDARAM_PAGE, stats)
    return finish(c, stats)


def parse_canara(items: List[dict], stats: dict) -> List[TerRec]:
    """One record per scheme, plan and day (plan_type 'Regular Plan' / 'Direct Plan', total_ter in percent); the newest day per scheme."""
    per: Dict[Tuple[str, date], dict] = {}
    for it in items:
        d, name = to_date(it.get("date")), str(it.get("scheme_name") or "").strip()
        plan = str(it.get("plan_type") or "").lower()
        v = num(it.get("total_ter"))
        if not name or d is None or v is None or ("regular" not in plan and "direct" not in plan):
            continue
        per.setdefault((name, d), {})["regular" if "regular" in plan else "direct"] = v
    best: Dict[str, Tuple[date, dict]] = {}
    for (name, d), v in per.items():
        if name not in best or d > best[name][0]:
            best[name] = (d, v)
    out = []
    for name, (d, v) in best.items():
        reg, dr = v.get("regular"), v.get("direct")
        why = plans_ok(reg, dr)
        if why:
            stats["refused"] = stats.get("refused", 0) + 1
            continue
        out.append(TerRec(name, name, d, None if reg is None else norm(reg), None if dr is None else norm(dr)))
    return out


async def src_canara(client, idx, today: date):
    """Canara Robeco's TER page reads its own public JSON (wp-json/ter/v1/records?from_date&to_date); the last week is asked, the newest day per scheme kept."""
    r = await get(client, URL_CANARA, params={"from_date": (today - timedelta(days=7)).isoformat(), "to_date": today.isoformat()})
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"unexpected answer: {str(data)[:100]}")
    stats: dict = {}
    c = Collector(idx, "canara", SRC_CANARA)
    c.amc_re = AMC_RE["canara"]
    emit(c, parse_canara(data, stats), today, "https://www.canararobeco.com/expense-ratio", stats)
    return finish(c, stats)


SOURCES = {"sbi": src_sbi, "nippon": src_nippon, "tata": src_tata, "sundaram": src_sundaram, "canara": src_canara}


async def collect(idx, today: date, only: Optional[Sequence[str]] = None, client: Optional[httpx.AsyncClient] = None,
                  skip: Iterable[str] = (), pause: float = PAUSE) -> Tuple[List[Row], Dict[str, dict]]:
    """Run each house (or `only`, minus `skip`); each fails alone. Returns (rows, {house: stats or {"error": ...}})."""
    own = client is None
    client = client or make_client()
    rows: List[Row] = []
    stats: Dict[str, dict] = {}
    skip = set(skip)
    first = True
    try:
        for name, fn in SOURCES.items():
            if (only and name not in only) or name in skip:
                continue
            if not first and pause:
                await asyncio.sleep(pause)
            first = False
            try:
                r, s = await fn(client, idx, today)
                rows += r
                stats[name] = s
            except Exception as exc:
                log.warning("TER source %s failed: %r", name, exc)
                stats[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        if own:
            await client.aclose()
    return rows, stats


async def _main(argv: Optional[Sequence[str]] = None) -> None:
    import argparse
    import asyncpg
    from ..portfolios import load_index, put_facts
    ap = argparse.ArgumentParser(description="Read fund houses' own TER pages and report coverage")
    ap.add_argument("--only", nargs="*", help=f"houses: {', '.join(SOURCES)}")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pool = await asyncpg.create_pool(os.environ.get("DATABASE_URL", "postgresql://finlit:finlit@127.0.0.1:5432/finlit_dev"), min_size=1, max_size=2)
    try:
        idx = await load_index(pool)
        rows, stats = await collect(idx, date.today(), a.only)
        for k, v in stats.items():
            print(k, json.dumps({x: y for x, y in v.items() if x != "unmatched"}), "unmatched:", (v.get("unmatched") or [])[:10])
        if a.write:
            print("stored", await put_facts(pool, rows))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
