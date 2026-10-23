"""Fund facts from AMFI's own published files: fund size (average AUM), expense ratio (TER, Regular and Direct plan) and launch date,
for mutual funds and ETFs alike (an ETF is an AMFI scheme too). Read by finlit/mf.py and finlit/etf.py; written by the
`refresh-facts` worker command.

Sources (each checked by hand against the live site, October 2026, and recorded in tests/fixtures/disclosure):
  scheme master  portal.amfiindia.com/DownloadSchemeData_Po.aspx  every scheme code: its scheme name and launch date (its minimum amount is
                                                                  stored, not shown: out of date for some schemes)
  TER            amfiindia.com/ter-of-mf-schemes (its Excel export)  one row per scheme and day: Regular and Direct plan TER, in percent a year
  average AUM    amfiindia.com average AUM, scheme-wise              every scheme code's average assets over the latest quarter, rupees lakh

Rules: each step stands alone (one failing leaves the others and the stored figures as they were); an answer that fails its checks is refused
and nothing is stored from it; a quarter of AUM figures replaces the previous quarter whole, never mixed. A fact with no verified free source
says so instead of showing a guess. Information only, never advice.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from . import mf

log = logging.getLogger("finlit.disclosure")
IST = ZoneInfo("Asia/Kolkata")

URL_MASTER = "https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0"
URL_TER_MONTHS = "https://www.amfiindia.com/api/populate-ter-month"
URL_TER = "https://www.amfiindia.com/api/populate-te-rdata-revised"
URL_AUM = "https://www.amfiindia.com/api/average-aum-schemewise"
SRC_MASTER = "AMFI scheme master"
SRC_TER = "AMFI, TER of mutual fund schemes"
SRC_AUM = "AMFI, average AUM scheme-wise"
SRC_EXCHANGE = "NSE trading rules"

# Below these an answer is not the whole industry (a partial file, an error page that parsed): it is refused and nothing is stored.
MIN_MASTER_ROWS = 8000
MIN_TER_SCHEMES = 1500
MIN_AUM_CODES = 3000
TER_MAX = 5.0          # percent a year; SEBI's caps keep every real TER well under this
AUM_PERIODS = ((1, 1), (1, 2), (2, 1), (2, 2))   # (fyId, periodId), newest first: AMFI may not have filled the newest quarter yet

NO_EXIT_LOAD = ("Exit load is stated in each scheme's own documents (PDF, a different layout at every fund house); no free machine-readable "
                "official source was found, so none is shown.")
NO_MANAGERS = ("Fund managers are named in each scheme's factsheet (PDF); no free machine-readable official source was found, so none is shown.")
NO_BENCHMARK = "AMFI publishes the benchmark on its fund performance page, which our server cannot read yet; see the scheme's factsheet."
NO_RISKOMETER = "AMFI publishes the risk-o-meter on its fund performance page, which our server cannot read yet; see the scheme's factsheet."
NO_TRACKING = "Tracking error is published in the fund house's monthly factsheet (PDF); no free machine-readable official source was found."
NOT_LOADED = "AMFI's figures have not been loaded yet; they appear after the next nightly update."


def name_key(name: str) -> str:
    """A scheme name as a comparison key: letters and digits only, lower case ("Axis Children's Fund" and "AXIS CHILDRENS FUND" agree)."""
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", name or "").lower())


def parse_amfi_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def inr(n: float) -> str:
    """Indian digit grouping: 147064 -> '1,47,064'."""
    s = str(int(round(n)))
    neg, s = s.startswith("-"), s.lstrip("-")
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail, head = head[-2:] + "," + tail, head[:-2]
    return ("-" if neg else "") + (head + "," + tail if head else tail)


def aum_text(lakh: float) -> str:
    """Rupees lakh as people read fund sizes: '₹1,47,064 crore', '₹45.30 crore', '₹82.50 lakh'."""
    crore = lakh / 100
    if crore >= 100:
        return f"₹{inr(crore)} crore"
    if crore >= 1:
        return f"₹{crore:,.2f} crore"
    return f"₹{lakh:,.2f} lakh"


MIN_PLAUSIBLE = 100   # rupees: AMFI's master lists a bare "5" or "10" for some schemes (e.g. ICICI Prudential Gilt Fund); no real minimum is that low


def min_text(raw: str) -> Optional[str]:
    """AMFI's minimum amount: a plain amount ("5000", "Rs. 5000/-") as '₹5,000'; any longer wording as AMFI wrote it. None when there is none,
    or when a plain amount is below MIN_PLAUSIBLE (a figure that cannot be a real minimum is not shown)."""
    t = re.sub(r"\s+", " ", (raw or "").strip())
    if not t or t.upper() in ("NA", "N.A.", "N/A", "0"):
        return None
    m = re.fullmatch(r"(?:Rs\.?\s*|INR\s*|₹\s*)?(\d+(?:\.\d+)?)\s*(?:/-)?", t, re.I)
    if m:
        v = float(m.group(1))
        if v < MIN_PLAUSIBLE:
            return None
        return f"₹{inr(v)}" if v == int(v) else f"₹{v:,.2f}"
    return t


# ------------------------------------------------------------------------------------------------------------- parsing

@dataclass(frozen=True)
class MasterRow:
    code: int
    base_name: str
    launch: Optional[date]
    minimum: Optional[str]


def parse_master(text: str) -> Dict[int, MasterRow]:
    """AMFI's scheme master CSV -> {scheme code: row}. Empty when the header is not the one checked (so a changed file is refused, not misread)."""
    rd = csv.reader(io.StringIO(text.lstrip("﻿")))
    head = [h.strip().lower() for h in next(rd, [])]
    need = {"code": "code", "scheme name": "scheme name", "launch date": "launch date", "scheme minimum amount": "scheme minimum amount"}
    if not all(k in head for k in need):
        return {}
    ci, ni, li, mi = head.index("code"), head.index("scheme name"), head.index("launch date"), head.index("scheme minimum amount")
    out: Dict[int, MasterRow] = {}
    for r in rd:
        if len(r) <= max(ci, ni, li, mi):
            continue
        code = r[ci].strip()
        if not code.isdigit() or not r[ni].strip():
            continue
        out[int(code)] = MasterRow(int(code), re.sub(r"\s+", " ", r[ni].strip()), parse_amfi_date(r[li]), min_text(r[mi]))
    return out


@dataclass(frozen=True)
class TerRow:
    key: str
    name: str
    category: Optional[str]
    regular: Optional[float]
    direct: Optional[float]
    day: date


TER_HEAD = ("Scheme Name", "Scheme Category", "TER Date", "Regular Plan - Total TER (%)", "Direct Plan - Total TER (%)")


def _pct(v) -> Optional[float]:
    """A TER cell: a positive percent, or None. AMFI writes 0 for a plan the scheme does not offer, so 0 is 'no such plan', never 0%."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 4) if 0 < f <= TER_MAX else None


def parse_ter_xlsx(path: str) -> Dict[str, TerRow]:
    """AMFI's TER workbook -> {scheme name key: the scheme's row for the latest day in the file}. Empty when the columns are not the checked ones."""
    import openpyxl   # parses the workbook's XML through defusedxml (installed with it, see requirements.txt)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(rows, ())]
        if not all(h in head for h in TER_HEAD):
            return {}
        ni, ci, di, ri, xi = (head.index(h) for h in TER_HEAD)
        out: Dict[str, TerRow] = {}
        for r in rows:
            if not r or len(r) <= max(ni, ci, di, ri, xi) or not r[ni]:
                continue
            d = r[di].date() if isinstance(r[di], datetime) else (r[di] if isinstance(r[di], date) else parse_amfi_date(str(r[di] or "")))
            if d is None:
                continue
            k = name_key(str(r[ni]))
            if k and (k not in out or d >= out[k].day):
                out[k] = TerRow(k, re.sub(r"\s+", " ", str(r[ni]).strip()), str(r[ci] or "").strip() or None, _pct(r[ri]), _pct(r[xi]), d)
        return out
    finally:
        wb.close()


_PERIOD = re.compile(r"([A-Za-z]+)\s*-\s*([A-Za-z]+)\s+(\d{4})")


def period_end(label: str) -> Optional[date]:
    """'July - September 2026' -> 2026-09-30 (the last day of the period's last month)."""
    m = _PERIOD.search(label or "")
    if not m:
        return None
    try:
        last = datetime.strptime(f"1 {m.group(2)[:3]} {m.group(3)}", "%d %b %Y").date()
    except ValueError:
        return None
    nxt = date(last.year + (last.month == 12), last.month % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def parse_aum(payload) -> Tuple[Optional[str], Optional[date], Dict[int, float]]:
    """(period label, period end, {scheme code: average AUM in rupees lakh}). A fund of funds' domestic AUM sits in its own column; the two are added."""
    if not isinstance(payload, dict):
        return None, None, {}
    label = payload.get("selectedPeriod")
    out: Dict[int, float] = {}
    houses = payload.get("data")
    for house in houses if isinstance(houses, list) else []:
        schemes = house.get("schemes") if isinstance(house, dict) else None
        for s in schemes if isinstance(schemes, list) else []:
            if not isinstance(s, dict):
                continue
            code, a = s.get("AMFI_Code"), s.get("AverageAumForTheMonth")
            a = a if isinstance(a, dict) else {}
            vals = []
            for k in ("ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas", "FundOfFundsDomestic"):
                try:
                    vals.append(float(a.get(k)))
                except (TypeError, ValueError):
                    pass
            if isinstance(code, int) and vals and all(v >= 0 for v in vals):
                out[code] = out.get(code, 0.0) + sum(vals)
    return label, period_end(label or ""), out


def fiscal_year(d: date) -> str:
    """India's financial year containing `d`, as AMFI's TER page names it: 22 Oct 2026 -> '2026-2027', 10 Mar 2026 -> '2025-2026'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{start + 1}"


# ------------------------------------------------------------------------------------------------------------- fetching

async def _get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    async def go():
        r = await client.get(url, **kw)
        r.raise_for_status()
        return r
    return await mf._retry(go)


async def fetch_master(client: httpx.AsyncClient) -> str:
    return (await _get(client, URL_MASTER)).content.decode("utf-8", "replace")


async def fetch_ter(client: httpx.AsyncClient, today: date) -> Tuple[Optional[str], Dict[str, TerRow]]:
    """(month, rows) of the newest month AMFI lists. The workbook (about 3 MB) goes through a temporary file, so it is never held twice in memory."""
    months: List[dict] = []
    for fy in (fiscal_year(today), fiscal_year(date(today.year - 1, today.month, 1))):   # early April the new year may still be empty
        got = (await _get(client, URL_TER_MONTHS, params={"year": fy})).json()
        months = [m for m in (got if isinstance(got, list) else []) if isinstance(m, dict) and m.get("MonthNumber")]
        if months:
            break
    if not months:
        return None, {}
    month = months[0]["MonthNumber"]             # AMFI lists the newest month first
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as fh:
        async with client.stream("GET", URL_TER, params={"MF_ID": "All", "Month": month, "strCat": "-1", "strType": "-1", "excel": "true"}) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                fh.write(chunk)
        fh.flush()
        rows = await asyncio.to_thread(parse_ter_xlsx, fh.name)
    return month, rows


RETRY_PAUSE = 15.0  # seconds, growing with each attempt (tests set it to 0). AMFI answers an empty quarter for minutes at a time, then the full one
AUM_TRIES = 6       # per period: about five minutes of asking for the newest quarter before an older one is tried


async def fetch_aum(client: httpx.AsyncClient, min_codes: int = MIN_AUM_CODES) -> Tuple[Optional[str], Optional[date], Dict[int, float]]:
    """The newest quarter that AMFI has filled in. AMFI sometimes answers an empty list for a moment: each period is asked up to three times."""
    for fy, per in AUM_PERIODS:
        for attempt in range(AUM_TRIES):
            label, end, codes = parse_aum((await _get(client, URL_AUM, params={"strType": "Typewise", "fyId": fy, "periodId": per})).json())
            if len(codes) >= min_codes:
                return label, end, codes
            await asyncio.sleep(RETRY_PAUSE * (attempt + 1))
    return None, None, {}


# ------------------------------------------------------------------------------------------------------------- writing

async def step_master(store, client, *, min_rows: int = MIN_MASTER_ROWS) -> dict:
    rows = parse_master(await fetch_master(client))
    if len(rows) < min_rows:
        return {"status": "refused", "why": f"AMFI's scheme master gave {len(rows)} schemes (expected at least {min_rows})"}
    async with store.pool.acquire() as conn:
        known = {r["code"] for r in await conn.fetch("SELECT code FROM mf_schemes")}
        items = [(r.code, r.base_name, name_key(r.base_name), r.launch, r.minimum) for r in rows.values() if r.code in known]
        async with conn.transaction():
            await conn.executemany(
                "INSERT INTO mf_facts (code, base_name, name_key, launch_date, min_text) VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (code) DO UPDATE SET base_name = EXCLUDED.base_name, name_key = EXCLUDED.name_key, launch_date = EXCLUDED.launch_date, "
                "min_text = EXCLUDED.min_text, updated_at = now()", items)
    return {"status": "ok", "schemes": len(items)}


async def step_ter(store, client, today: date, *, min_schemes: int = MIN_TER_SCHEMES) -> dict:
    month, rows = await fetch_ter(client, today)
    if len(rows) < min_schemes:
        return {"status": "refused", "why": f"AMFI's TER file for {month or 'the newest month'} gave {len(rows)} schemes (expected at least {min_schemes})"}
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM mf_ter")
            await conn.executemany("INSERT INTO mf_ter (name_key, name, category, ter_regular, ter_direct, ter_date) VALUES ($1, $2, $3, $4, $5, $6)",
                                   [(r.key, r.name, r.category, r.regular, r.direct, r.day) for r in rows.values()])
    return {"status": "ok", "month": month, "schemes": len(rows), "day": max(r.day for r in rows.values()).isoformat()}


async def step_aum(store, client, *, min_codes: int = MIN_AUM_CODES) -> dict:
    label, end, codes = await fetch_aum(client, min_codes)
    if len(codes) < min_codes or end is None:
        return {"status": "refused", "why": f"AMFI's average AUM gave {len(codes)} scheme codes for {label or 'no period'} (expected at least {min_codes})"}
    total_crore = sum(codes.values()) / 100
    async with store.pool.acquire() as conn:
        known = {r["code"] for r in await conn.fetch("SELECT code FROM mf_schemes")}
        items = [(c, v, end, label) for c, v in codes.items() if c in known]
        async with conn.transaction():   # one quarter replaces the other whole: a code AMFI no longer lists has no figure, never last quarter's
            await conn.execute("UPDATE mf_facts SET aum_lakh = NULL, aum_end = NULL, aum_label = NULL WHERE aum_lakh IS NOT NULL")
            await conn.executemany(
                "INSERT INTO mf_facts (code, aum_lakh, aum_end, aum_label) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (code) DO UPDATE SET aum_lakh = EXCLUDED.aum_lakh, aum_end = EXCLUDED.aum_end, aum_label = EXCLUDED.aum_label, updated_at = now()",
                items)
    return {"status": "ok", "period": label, "codes": len(items), "industryCrore": round(total_crore)}


async def refresh(store, settings=None, *, client: Optional[httpx.AsyncClient] = None, today: Optional[date] = None, **limits) -> dict:
    """Run the three steps; each one failing (network, refused answer) leaves the others and the stored figures as they were."""
    today = today or datetime.now(IST).date()
    own = client is None
    client = client or mf.make_client()
    out: Dict[str, dict] = {}
    try:
        pick = lambda *names: {k: v for k, v in limits.items() if k in names}   # noqa: E731  (tests pass smaller minimums)
        for name, run in (("master", lambda: step_master(store, client, **pick("min_rows"))),
                          ("ter", lambda: step_ter(store, client, today, **pick("min_schemes"))),
                          ("aum", lambda: step_aum(store, client, **pick("min_codes")))):
            try:
                out[name] = await run()
            except Exception as exc:
                log.warning("fund facts step %s failed: %r", name, exc)
                out[name] = {"status": "failed", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    finally:
        if own:
            await client.aclose()
    statuses = {v.get("status") for v in out.values()}
    summary = {"status": "ok" if statuses == {"ok"} else ("failed" if "ok" not in statuses else "partial"), **out}
    await mf.record_run(store, "refresh-facts", summary)
    if "ok" in statuses:
        await mf._bump(store, None)   # cached fund pages are rebuilt with the new facts
    return summary


# ------------------------------------------------------------------------------------------------------------- reading

async def _facts_rows(conn, code: int):
    me = await conn.fetchrow("SELECT s.code, s.family, s.plan, f.name_key, f.launch_date, f.min_text FROM mf_schemes s "
                             "LEFT JOIN mf_facts f ON f.code = s.code WHERE s.code = $1", code)
    if me is None:
        return None, None, None
    fam = await conn.fetch("SELECT s.code, f.name_key, f.aum_lakh, f.aum_end, f.aum_label FROM mf_schemes s LEFT JOIN mf_facts f ON f.code = s.code "
                           "WHERE s.family = $1", me["family"])
    keys = [me["name_key"]] + [r["name_key"] for r in fam if r["name_key"] and r["name_key"] != me["name_key"]]
    ter = None
    for k in keys:   # every plan and option of a scheme shares its TER row; a code filed under an older name uses a sibling's match
        if k:
            ter = await conn.fetchrow("SELECT name, ter_regular, ter_direct, ter_date FROM mf_ter WHERE name_key = $1", k)
            if ter:
                break
    return me, fam, ter


def _aum_fact(fam, loaded: bool) -> dict:
    have = [r for r in fam if r["aum_lakh"] is not None]
    if not have:
        if not loaded:
            return {"unavailable": NOT_LOADED}
        return {"unavailable": "Not in AMFI's latest quarterly AUM report (a scheme launched after that quarter, or one AMFI does not report)."}
    end = max(r["aum_end"] for r in have)
    lakh = sum(r["aum_lakh"] for r in have if r["aum_end"] == end)
    label = next(r["aum_label"] for r in have if r["aum_end"] == end)
    return {"value": aum_text(lakh), "asOf": end.isoformat(), "source": SRC_AUM,
            "note": f"Average over {label}, all plans of the scheme together."}


def _ter_fact(ter, plan: str) -> dict:
    if ter is None:
        return {"unavailable": "This scheme is not in AMFI's latest expense ratio (TER) file."}
    v = ter["ter_regular"] if plan == "Regular" else ter["ter_direct"]
    if v is None:
        return {"unavailable": f"AMFI's TER file shows no figure for the {plan} plan (the scheme may not offer it)."}
    return {"value": f"{v:.2f}% a year", "asOf": ter["ter_date"].isoformat(), "source": SRC_TER}


def _etf_ter_fact(ter) -> dict:
    """An ETF has one plan. AMFI files its TER under Regular for most ETFs and under Direct for others (checked: 251 and 108 of 361, never both)."""
    if ter is None:
        return {"unavailable": "This ETF is not in AMFI's latest expense ratio (TER) file."}
    v = ter["ter_regular"] if ter["ter_regular"] is not None else ter["ter_direct"]
    if v is None:
        return {"unavailable": "AMFI's TER file shows no figure for this ETF."}
    return {"value": f"{v:.2f}% a year", "asOf": ter["ter_date"].isoformat(), "source": SRC_TER}


# The scheme master's minimum amount is stored (mf_facts.min_text) but not shown: it is out of date for some schemes (every SBI Liquid Fund plan,
# retail ones included, is listed at an old ₹5 crore institutional minimum) and no second official source tells which. A wrong minimum is worse
# than none.
NO_MINIMUM = ("The minimum amount AMFI lists is out of date for some schemes, so none is shown; the scheme's own documents and the fund house's "
              "site give the current minimum.")


def _launch_fact(me) -> dict:
    if me["launch_date"]:
        return {"value": me["launch_date"].isoformat(), "source": SRC_MASTER}
    return {"unavailable": NOT_LOADED if me["name_key"] is None else "AMFI's scheme master gives no launch date for this scheme."}


async def get_facts(pool, key) -> Optional[dict]:
    """Facts of one scheme: `key` is an AMFI scheme code (fund pages) or an ISIN (ETF pages). Each fact is {value, asOf?, source, note?} or
    {unavailable: reason}. None when the scheme is unknown."""
    async with pool.acquire() as conn:
        code = key if isinstance(key, int) else (int(key) if str(key).isdigit() else
                                                 await conn.fetchval("SELECT code FROM mf_schemes WHERE isin = $1 OR isin_reinvest = $1 ORDER BY active DESC LIMIT 1", str(key)))
        if code is None:
            return None
        me, fam, ter = await _facts_rows(conn, int(code))
        loaded = bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM mf_facts WHERE aum_lakh IS NOT NULL)")) if me else False
    if me is None:
        return None
    try:   # holdings-side facts (finlit.portfolios): exit load, benchmark, risk-o-meter, managers; missing ones keep their reason
        from . import portfolios
        extra = await portfolios.extra_facts(pool, key) or {}
    except Exception:
        log.warning("portfolio facts unavailable for %s", key, exc_info=True)
        extra = {}
    aum = _aum_fact(fam, loaded)
    if "unavailable" in aum and extra.get("monthEndAum"):
        m = extra["monthEndAum"]
        aum = {"value": aum_text(m["lakh"]), "asOf": m["asOf"], "source": m["source"], "note": "Net assets at the end of the month, all plans of the scheme together."}
    launch = _launch_fact(me)
    if "unavailable" in launch and extra.get("launchDate"):
        launch = extra["launchDate"]
    out = {"aum": aum, "launchDate": launch, "benchmark": extra.get("benchmark") or {"unavailable": NO_BENCHMARK},
           "riskometer": extra.get("riskometer") or {"unavailable": NO_RISKOMETER}, "managers": extra.get("managers") or {"unavailable": NO_MANAGERS}}
    if isinstance(key, int) or str(key).isdigit():     # a mutual fund page: both plans' TER, the scheme's minimum, exit load unknown
        out.update(terRegular=_ter_fact(ter, "Regular"), terDirect=_ter_fact(ter, "Direct"), minInvestment={"unavailable": NO_MINIMUM},
                   exitLoad=extra.get("exitLoad") or {"unavailable": NO_EXIT_LOAD})
    else:                                              # an ETF page: one plan (AMFI files it as Regular), bought and sold on the exchange
        out.update(ter=_etf_ter_fact(ter), trackingError={"unavailable": NO_TRACKING},
                   minInvestment={"value": "1 unit, bought on the stock exchange", "source": SRC_EXCHANGE},
                   exitLoad={"value": "None when sold on the stock exchange", "source": SRC_EXCHANGE})
    return out


async def top_by_aum(pool, n: int) -> List[int]:
    """Scheme codes of the n largest schemes by the latest quarter's average AUM (all plans of a scheme added together), one code per scheme:
    its Direct Growth option, else its Regular Growth option, among active schemes with a 5-year figure (what the hot list can show)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH q AS (SELECT max(aum_end) AS e FROM mf_facts WHERE aum_lakh IS NOT NULL),
                    fam AS (SELECT s.family, sum(f.aum_lakh) AS aum FROM mf_facts f JOIN mf_schemes s ON s.code = f.code, q
                            WHERE f.aum_end = q.e GROUP BY s.family),
                    pick AS (SELECT DISTINCT ON (s.family) s.family, s.code FROM mf_schemes s
                             WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.r5y IS NOT NULL
                             ORDER BY s.family, (s.plan = 'Direct') DESC, s.code)
               SELECT pick.code FROM pick JOIN fam ON fam.family = pick.family ORDER BY fam.aum DESC, pick.code LIMIT $1""", n)
    return [r["code"] for r in rows]


async def get_portfolio(pool, key) -> Optional[dict]:
    """The latest monthly portfolio of a scheme (code) or ETF (ISIN): see finlit.portfolios."""
    from . import portfolios
    return await portfolios.get_portfolio(pool, key)
