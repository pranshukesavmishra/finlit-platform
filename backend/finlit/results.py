"""Quarter results: every company's results for one quarter, newest declaration first.

Two sources are joined here:
  * WHEN a company declared (or will declare): the `result` rows of the feed table. An exchange filing that says "financial results for the
    period ended <date>" is a confirmed declaration; the provider's board-meeting calendar is the schedule for the rest.
  * WHAT it declared: the screener metrics in `scores.metrics` (q_revenue, q_net_profit ...), for the ~500 companies we load in full.

The trap this module is built around: a company whose results date has passed may not have been refreshed yet, so its q_* figures are
still LAST quarter's. Every metrics row carries `q_period_end` (the quarter-end its q_* figures belong to). A row shows numbers only when
that date is the quarter on screen; otherwise it is "awaiting" and shows the date alone. A row stored before `q_period_end` existed is
read from its stored statements once (small, cached) and never guessed.

Plan gate, on the server: Basic gets dates, names, sector, size and status with every figure withheld; Silver and Gold get everything.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, Response

from .auth.entitlements import has
from .auth.routes import NO_STORE, fail
from .auth.service import current
from .calendars import SOURCE_RESULTS, parse_date
from .screener.compute import quarter_block
from .screener.data import get_table

log = logging.getLogger("finlit.results")
router = APIRouter(prefix="/api/results")
IST = ZoneInfo("Asia/Kolkata")

GAP_FLAG = 15.0            # percentage points between revenue growth and profit growth that earns the red chip (same as the alert's default)
TTL_LATEST, TTL_OLD = 180, 3600   # seconds a quarter's rows are served before they are rebuilt in the background
DECL_TTL = 120
EXPORT_ROWS = 4000
DATE_MEANING = ("The date is the day the company announced (declared) its results: the date on the exchange filing, or the board-meeting date from the results calendar until the filing appears. "
                "It is an Indian calendar date (IST).")
PAGE = 50
INDEX_FLAGS = ("NIFTY50", "NIFTY100", "NIFTY500")
FILING_SOURCE = "Exchange filing"
FILING_CATEGORIES = ("outcome of board meeting", "result", "results", "financial results", "financial result")
QUARTER_RE = re.compile(r"^\d{4}-(03|06|09|12)$")
NUMERIC_SORTS = {"revenueYoY": "revenueYoY", "profitYoY": "profitYoY", "marginChange": "npmChange", "gap": "gap", "revenue": "revenue", "netProfit": "netProfit"}
SORTS = {"date", "marketCap", *NUMERIC_SORTS}
# every figure a row carries that Basic must not see
FIGURES = ("revenue", "revenueYoY", "revenueQoQ", "operatingProfit", "opYoY", "opQoQ", "opYoYWhy", "opQoQWhy", "opm", "netProfit", "profitYoY", "profitQoQ", "npm", "npmChange", "eps", "gap")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
METRIC_KEYS = ("q_revenue", "q_net_profit", "q_operating_profit", "q_eps", "q_sales_yoy", "q_profit_yoy", "q_sales_qoq", "q_profit_qoq", "q_opm", "q_npm", "q_period_end")


# ------------------------------------------------------------------ quarters
def quarter_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def quarter_end_before(d: date) -> date:
    """The latest quarter-end strictly before `d`: the quarter a results announcement on `d` is (by default) about."""
    cands = [quarter_end(y, m) for y in (d.year - 1, d.year) for m in (3, 6, 9, 12)]
    return max(e for e in cands if e < d)


def next_quarter_end(e: date) -> date:
    m = e.month + 3
    return quarter_end(e.year + (m - 1) // 12, (m - 1) % 12 + 1)


def snap_quarter_end(d: date) -> Optional[date]:
    """A date a filing names as its period end, snapped to the calendar quarter-end it means (None when it is not a quarter-end at all)."""
    for y, m in ((d.year, d.month), (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)):
        e = quarter_end(y, m)
        if m in (3, 6, 9, 12) and abs((e - d).days) <= 3:
            return e
    return None


def quarter_key(e: date) -> str:
    return f"{e.year}-{e.month:02d}"


def parse_quarter(key: str) -> Optional[date]:
    return quarter_end(int(key[:4]), int(key[5:])) if QUARTER_RE.match(key or "") else None


def quarter_info(e: date) -> Dict[str, Any]:
    start_month = e.month - 2
    fy_end = e.year + 1 if e.month > 3 else e.year
    q = ((e.month - 4) % 12) // 3 + 1                                       # Apr-Jun is Q1 of the financial year
    mon = lambda m: date(2000, m, 1).strftime("%b")                         # noqa: E731
    return {"key": quarter_key(e), "label": f"{mon(start_month)} to {mon(e.month)} {e.year}", "fiscal": f"Q{q} FY{str(fy_end)[2:]}", "periodEnd": e.isoformat(),
            "from": (e + timedelta(days=1)).isoformat(), "to": next_quarter_end(e).isoformat()}


MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_P1 = re.compile(r"(?:ended|ending)\s+(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?[\s,.\-/]+([A-Za-z]{3,9})[\s,.\-/]+(\d{4})", re.I)      # 30th September, 2026 / 30-Sep-2026
_P2 = re.compile(r"(?:ended|ending)\s+(?:on\s+)?([A-Za-z]{3,9})[\s.]+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)                  # September 30, 2026 / Jun 30, 2026
_P3 = re.compile(r"(?:ended|ending)\s+(?:on\s+)?(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", re.I)                                          # 30/09/2026


def period_in_title(title: str) -> Optional[date]:
    """The quarter-end an exchange filing says its results are for ('... for the period ended Jun 30, 2026'), or None."""
    t = " ".join(str(title or "").split())
    try:
        m = _P1.search(t)
        if m and m.group(2)[:3].lower() in MONTHS:
            return snap_quarter_end(date(int(m.group(3)), MONTHS.index(m.group(2)[:3].lower()) + 1, int(m.group(1))))
        m = _P2.search(t)
        if m and m.group(1)[:3].lower() in MONTHS:
            return snap_quarter_end(date(int(m.group(3)), MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2))))
        m = _P3.search(t)
        if m:
            return snap_quarter_end(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    except ValueError:
        return None
    return None


# ------------------------------------------------------------------ declarations (when)
@dataclass
class Decl:
    date: date
    confirmed: bool            # an exchange filing exists (not just a scheduled board meeting)
    company: Optional[str] = None


def is_declaration(source: Optional[str], category: Optional[str], title: Optional[str]) -> bool:
    """Exchange filings count only when they are the results themselves: not a meeting notice, a press release or a reply to a query."""
    if source != FILING_SOURCE:
        return False
    low = f"{title or ''}".lower()
    return (category or "").strip().lower() in FILING_CATEGORIES and "result" in low and "clarification" not in low and "intimation" not in low


def assign(rows: List[dict]) -> Dict[str, Dict[str, Decl]]:
    """feed rows -> {quarter key: {symbol: Decl}}. A confirmed filing beats a scheduled date; the earliest date of the kind wins."""
    best: Dict[Tuple[str, str], Decl] = {}
    for r in rows:
        sym, when = (r.get("symbol") or "").strip().upper(), r.get("item_date")
        if not sym or not isinstance(when, date):
            continue
        confirmed = is_declaration(r.get("source"), r.get("category"), r.get("title"))
        if r.get("source") == FILING_SOURCE and not confirmed:
            continue   # a notice that a board meeting will happen carries the notice's date, not the meeting's
        period = period_in_title(r.get("title")) if confirmed else None
        e = period if period and period < when and (when - period).days <= 400 else quarter_end_before(when)
        k = (quarter_key(e), sym)
        cur = best.get(k)
        new = Decl(when, confirmed, r.get("company"))
        if cur is None or (new.confirmed, -new.date.toordinal()) > (cur.confirmed, -cur.date.toordinal()):
            best[k] = new
    out: Dict[str, Dict[str, Decl]] = {}
    for (qk, sym), d in best.items():
        out.setdefault(qk, {})[sym] = d
    return out


# ------------------------------------------------------------------ rows (what)
def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _r(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None else round(v, n)


def ymd_to_date(v: Optional[float]) -> Optional[date]:
    if v is None:
        return None
    n = int(v)
    try:
        return date(n // 10000, n // 100 % 100, n % 100)
    except ValueError:
        return None


def status_of(decl_date: date, today: date, has_numbers: bool, loaded_end: Optional[date], e: date) -> str:
    """declared: figures for THIS quarter are in. awaiting: the date has passed but our figures are older. due: still to come.
    missing: our figures have moved on to a later quarter and this one was not kept."""
    if has_numbers:
        return "declared"
    if loaded_end is not None and loaded_end > e + timedelta(days=10):
        return "missing"
    return "awaiting" if decl_date <= today else "due"


def build_row(sym: str, decl: Decl, base: dict, m: Dict[str, Optional[float]], e: date, today: date, cap: Optional[str], indices: List[str], opg: Optional[Dict[str, Any]] = None) -> dict:
    """One row. `m` holds the q_* figures ALREADY checked to belong to quarter `e`; an empty/None-filled `m` means no figures."""
    rev, np_, op = m.get("q_revenue"), m.get("q_net_profit"), m.get("q_operating_profit")
    has_numbers = rev is not None or np_ is not None
    ry, py = m.get("q_sales_yoy"), m.get("q_profit_yoy")
    npm = m.get("q_npm")
    npm_change = None   # net margin now against a year ago, worked out from the two growth rates (exact: prior profit / prior revenue)
    if has_numbers and npm is not None and ry is not None and py is not None and 1 + py / 100 != 0:
        npm_change = npm - npm * (1 + ry / 100) / (1 + py / 100)
    gap = abs(ry - py) if ry is not None and py is not None else None
    loaded_end = ymd_to_date(base.get("q_period_end"))
    status = status_of(decl.date, today, has_numbers, loaded_end, e)
    row = {
        "date": decl.date.isoformat(), "symbol": sym, "name": base.get("name") or decl.company or sym, "sector": base.get("sector"), "marketCap": _r(_f(base.get("market_cap")), 0),
        "cap": cap, "indices": indices, "confirmed": decl.confirmed, "periodEnd": e.isoformat(),
        "loadedPeriodEnd": loaded_end.isoformat() if loaded_end else None, "status": status, "awaiting": status == "awaiting",
        "hasNumbers": has_numbers, "locked": False,
        "revenue": _r(rev), "revenueYoY": _r(ry, 1), "revenueQoQ": _r(m.get("q_sales_qoq"), 1), "operatingProfit": _r(op), "opYoY": None, "opQoQ": None, "opYoYWhy": None, "opQoQWhy": None, "opm": _r(m.get("q_opm"), 1),
        "netProfit": _r(np_), "profitYoY": _r(py, 1), "profitQoQ": _r(m.get("q_profit_qoq"), 1), "npm": _r(npm, 1), "npmChange": _r(npm_change, 1),
        "eps": _r(m.get("q_eps")), "gap": _r(gap, 1), "flagged": bool(gap is not None and gap >= GAP_FLAG), "loss": bool(np_ is not None and np_ < 0),
    }
    if has_numbers:
        g = opg if opg is not None else {}
        if op is None:
            g = {"opYoYWhy": "no_data", "opQoQWhy": "no_data"}
        row.update({"opYoY": _r(g.get("opYoY"), 1), "opQoQ": _r(g.get("opQoQ"), 1),
                    "opYoYWhy": OP_WHY.get(g.get("opYoYWhy") or ("" if g.get("opYoY") is not None else "no_prior")), "opQoQWhy": OP_WHY.get(g.get("opQoQWhy") or ("" if g.get("opQoQ") is not None else "no_prior"))})
    if not has_numbers:
        row.update({k: None for k in FIGURES})
        row["flagged"] = row["loss"] = False
    return row


# ------------------------------------------------------------------ operating profit growth
# Operating profit is the quarterly `operating_profit` row of the stored statements: the same line (and the same definition, see
# normalize/statements.py _operating_profit) the screener's q_operating_profit and the stock page use. Growth follows the screener's rule
# (_growth): undefined when the base period was zero or a loss, never guessed. The earlier quarter must really be a year / a quarter before.
OP_WHY = {"loss_base": "The earlier quarter's operating profit was zero or a loss, so a percentage change is not meaningful.",
          "no_prior": "The earlier quarter is not in the stored statements.", "no_data": "Operating profit is not reported for this company.",
          "mismatch": "Withheld: the stored operating profit does not match the statement for this quarter."}
_ops: Dict[Tuple[str, str], Tuple[Any, Optional[dict]]] = {}     # (symbol, statement) -> (snapshot generated_at, {"ends": [...], "op": [...]})


def _growth(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b is None or b <= 0 else (a - b) / b * 100


def op_growth(ends: List[Any], ops: List[Any], e: date, stored_op: Optional[float] = None, tolerance_days: int = 10) -> Dict[str, Any]:
    """Operating profit growth for the quarter ending `e` from a company's quarterly statement rows. Returns opYoY / opQoQ (percent or None)
    and opYoYWhy / opQoQWhy (a key of OP_WHY when the figure is missing). `stored_op` (the screener's q_operating_profit) must agree with the statement."""
    dates: List[Optional[date]] = []
    for x in ends:
        try:
            dates.append(date.fromisoformat(str(x)[:10]) if x else None)
        except ValueError:
            dates.append(None)
    best: Optional[Tuple[int, int]] = None
    for j, d in enumerate(dates):
        if d is not None and abs((d - e).days) <= tolerance_days and (best is None or abs((d - e).days) < best[0]):
            best = (abs((d - e).days), j)
    vals = [_f(v) for v in ops]
    if best is None or best[1] >= len(vals) or vals[best[1]] is None:
        return {"opYoY": None, "opQoQ": None, "opYoYWhy": "no_data", "opQoQWhy": "no_data"}
    i = best[1]
    cur = vals[i]
    if stored_op is not None and abs(stored_op - cur) > 0.01 + 0.005 * abs(cur):
        return {"opYoY": None, "opQoQ": None, "opYoYWhy": "mismatch", "opQoQWhy": "mismatch"}

    def one(back: int, lo: int, hi: int) -> Tuple[Optional[float], Optional[str]]:
        j = i - back
        if j < 0 or j >= len(vals) or vals[j] is None or dates[j] is None or dates[i] is None or not lo <= (dates[i] - dates[j]).days <= hi:   # type: ignore[operator]
            return None, "no_prior"
        g = _growth(cur, vals[j])
        return (None, "loss_base") if g is None else (g, None)
    yoy, yw = one(4, 350, 380)
    qoq, qw = one(1, 80, 105)
    return {"opYoY": yoy, "opQoQ": qoq, "opYoYWhy": yw, "opQoQWhy": qw}


async def _op_histories(conn, pairs: List[Tuple[str, str]]) -> Dict[Tuple[str, str], Optional[dict]]:
    """Quarterly period ends and operating profit per (symbol, statement), read from the stored statements as small JSON slices.
    Cached per snapshot version, so a rebuild only re-reads companies whose report was refreshed."""
    if not pairs:
        return {}
    stamps = {(r["symbol"], r["statement"]): r["generated_at"] for r in await conn.fetch(
        "SELECT symbol, statement, generated_at FROM snapshots WHERE section = 'financials' AND symbol = ANY($1::text[])", sorted({s for s, _ in pairs}))}
    stale = [k for k in pairs if k in stamps and (k not in _ops or _ops[k][0] != stamps[k])]
    if stale:
        for r in await conn.fetch(
                "SELECT symbol, statement, body::jsonb #> '{quarterly,pl,periodEnds}' AS ends, body::jsonb #> '{quarterly,pl,rows,operating_profit}' AS op FROM snapshots "
                "WHERE section = 'financials' AND symbol = ANY($1::text[])", sorted({s for s, _ in stale})):
            k = (r["symbol"], r["statement"])
            if k not in stale:
                continue
            try:
                ends = json.loads(r["ends"]) if isinstance(r["ends"], str) else r["ends"]
                op = json.loads(r["op"]) if isinstance(r["op"], str) else r["op"]
                _ops[k] = (stamps[k], {"ends": ends, "op": op} if isinstance(ends, list) and isinstance(op, list) else None)
            except (ValueError, TypeError):
                _ops[k] = (stamps[k], None)
    return {k: (_ops[k][1] if k in _ops else None) for k in pairs}


@dataclass
class Entry:
    quarter: Dict[str, Any]
    rows: List[dict]
    sectors: List[Tuple[str, int]]
    loaded: float = field(default_factory=time.time)
    ttl: int = TTL_LATEST


async def _declarations(store) -> Dict[str, Dict[str, Decl]]:
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, company, item_date, source, category, title FROM feed_items "
                                "WHERE kind = 'result' AND symbol IS NOT NULL AND item_date >= current_date - 430 LIMIT 60000")
    return assign([dict(r) for r in rows])


async def _build(store, e: date, decls: Dict[str, Decl], today: date) -> Entry:
    symbols = sorted(decls)
    keys = ", ".join(f"s.metrics->>'{k}' AS {k}" for k in METRIC_KEYS)   # fixed names from the list above, never user input
    async with store.pool.acquire() as conn:
        base: Dict[str, dict] = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, name, sector FROM companies WHERE symbol = ANY($1::text[])", symbols)}
        scored = await conn.fetch(
            "SELECT DISTINCT ON (s.symbol) s.symbol, s.statement, s.name AS sname, COALESCE(s.macro_sector, s.sector) AS ssector, s.market_cap::float8 AS market_cap, " + keys +  # nosec B608
            " FROM scores s WHERE s.model = 'v1' AND s.symbol = ANY($1::text[]) ORDER BY s.symbol, (s.statement = 'consolidated') DESC, s.updated_at DESC", symbols)
        members: Dict[str, List[str]] = {}
        for r in await conn.fetch("SELECT symbol, index_code FROM index_members WHERE symbol = ANY($1::text[]) AND index_code = ANY($2::text[])", symbols, list(INDEX_FLAGS)):
            members.setdefault(r["symbol"], []).append(r["index_code"])
        metrics: Dict[str, Dict[str, Optional[float]]] = {}
        need: List[Tuple[str, str]] = []
        lo, hi = e - timedelta(days=10), e + timedelta(days=10)
        for r in scored:
            sym = r["symbol"]
            b = base.setdefault(sym, {"symbol": sym})
            b["name"] = b.get("name") or r["sname"]
            b["sector"] = r["ssector"] or b.get("sector")
            b["market_cap"] = r["market_cap"]
            m = {k: _f(r[k]) for k in METRIC_KEYS}
            qpe = ymd_to_date(m["q_period_end"])
            b["q_period_end"] = m["q_period_end"]
            if qpe is not None and lo <= qpe <= hi:
                metrics[sym] = m                                   # the stored figures are for this very quarter
            elif qpe is not None and qpe < lo:
                metrics[sym] = {}                                  # older than this quarter: not reported (to us) yet, show the date alone
            else:
                need.append((sym, r["statement"]))                 # no stored quarter-end (older row) or a later one: read this quarter from the statements
        hist = await _op_histories(conn, [(r["symbol"], r["statement"]) for r in scored])
        if need:
            wanted = set(need)
            for r in await conn.fetch("SELECT symbol, statement, body FROM snapshots WHERE section = 'financials' AND symbol = ANY($1::text[])", [s for s, _ in need]):
                if (r["symbol"], r["statement"]) not in wanted:
                    continue
                try:
                    qpl = ((json.loads(r["body"]).get("quarterly") or {}).get("pl")) or {}
                    ends = [x for x in (qpl.get("periodEnds") or []) if x]
                    blk = quarter_block(qpl, e)
                    metrics[r["symbol"]] = {k: _f(v) for k, v in blk.items()}
                    if ends:   # which quarter we do hold: the one asked for, else the newest (so a row can say "figures are for Jun 2026")
                        base[r["symbol"]]["q_period_end"] = blk.get("q_period_end") or quarter_block(qpl).get("q_period_end")
                except (ValueError, TypeError, AttributeError):
                    continue
    try:
        table = await get_table(store)
        cap_of = lambda s: table.cap[table.pos[s]] if s in table.pos else None   # noqa: E731
    except Exception:
        log.warning("size bands unavailable for the results page")
        cap_of = lambda s: None   # noqa: E731
    stmt_of = {r["symbol"]: r["statement"] for r in scored}

    def growth(s: str) -> Optional[Dict[str, Any]]:
        m, h = metrics.get(s) or {}, hist.get((s, stmt_of.get(s, "")))
        if not h or (m.get("q_revenue") is None and m.get("q_net_profit") is None):
            return None
        return op_growth(h["ends"], h["op"], e, m.get("q_operating_profit"))
    rows = [build_row(s, d, base.get(s, {"symbol": s}), metrics.get(s, {}), e, today, cap_of(s), sorted(members.get(s, [])), growth(s)) for s, d in decls.items()]
    counts: Dict[str, int] = {}
    for r in rows:
        if r["sector"]:
            counts[r["sector"]] = counts.get(r["sector"], 0) + 1
    return Entry(quarter_info(e), rows, sorted(counts.items()), ttl=TTL_LATEST if e >= quarter_end_before(today) else TTL_OLD)


# ------------------------------------------------------------------ cache (stale-while-revalidate, like the screener table)
_decl: Optional[Tuple[float, Dict[str, Dict[str, Decl]]]] = None
_entries: Dict[str, Entry] = {}
_tasks: Dict[str, asyncio.Task] = {}
_dlock, _elock = asyncio.Lock(), asyncio.Lock()   # two locks: building a quarter reads the declarations, which may need their own lock


def reset() -> None:
    global _decl
    _decl = None
    _entries.clear()
    _tasks.clear()
    _ops.clear()


async def get_declarations(store, force: bool = False) -> Dict[str, Dict[str, Decl]]:
    global _decl
    if _decl and not force:
        if time.time() - _decl[0] >= DECL_TTL and "decl" not in _tasks:
            _tasks["decl"] = asyncio.create_task(_refresh_decl(store))
        return _decl[1]
    async with _dlock:
        if _decl is None or force:
            _decl = (time.time(), await _declarations(store))
    return _decl[1]


async def _refresh_decl(store) -> None:
    global _decl
    try:
        _decl = (time.time(), await _declarations(store))
    except Exception:
        log.exception("results declarations not refreshed")
    finally:
        _tasks.pop("decl", None)


def today_ist() -> date:
    return datetime.now(IST).date()


async def get_entry(store, qkey: str, force: bool = False) -> Entry:
    e = parse_quarter(qkey)
    assert e is not None
    cur = _entries.get(qkey)
    if cur and not force:
        if time.time() - cur.loaded >= cur.ttl and qkey not in _tasks:
            _tasks[qkey] = asyncio.create_task(_refresh_entry(store, qkey))
        return cur
    async with _elock:
        cur = _entries.get(qkey)
        if cur is None or force:
            decls = (await get_declarations(store, force)).get(qkey, {})
            _entries[qkey] = await _build(store, e, decls, today_ist())
    return _entries[qkey]


async def _refresh_entry(store, qkey: str) -> None:
    try:
        decls = (await get_declarations(store)).get(qkey, {})
        _entries[qkey] = await _build(store, parse_quarter(qkey), decls, today_ist())   # type: ignore[arg-type]
    except Exception:
        log.exception("results for %s not refreshed", qkey)
    finally:
        _tasks.pop(qkey, None)


def list_quarters(decls: Dict[str, Dict[str, Decl]], today: date) -> List[Dict[str, Any]]:
    out = []
    for qk, by_sym in decls.items():
        e = parse_quarter(qk)
        if e is None:
            continue
        done = sum(1 for d in by_sym.values() if d.date <= today)
        out.append({**quarter_info(e), "total": len(by_sym), "declared": done, "due": len(by_sym) - done})
    return sorted(out, key=lambda q: q["key"], reverse=True)


def default_quarter(quarters: List[Dict[str, Any]], today: date) -> Optional[str]:
    """The latest quarter that has at least one company declared; else the latest quarter listed."""
    for q in quarters:
        if q["declared"] > 0:
            return q["key"]
    return quarters[0]["key"] if quarters else None


# ------------------------------------------------------------------ filtering, summary
def summarize(rows: List[dict], today: date) -> Dict[str, Any]:
    declared = [r for r in rows if r["status"] != "due"]   # figures in, or the date has passed
    withnum = [r for r in rows if r["hasNumbers"]]
    ry = [r["revenueYoY"] for r in withnum if r["revenueYoY"] is not None]
    py = [r["profitYoY"] for r in withnum if r["profitYoY"] is not None]
    mc = [r["npmChange"] for r in withnum if r["npmChange"] is not None]
    med = lambda xs: round(median(xs), 1) if xs else None   # noqa: E731
    share = lambda xs, ok: round(sum(1 for x in xs if ok(x)) / len(xs) * 100, 1) if xs else None   # noqa: E731
    return {"companies": len(rows), "declared": len(declared), "due": sum(1 for r in rows if r["status"] == "due"), "awaiting": sum(1 for r in rows if r["status"] == "awaiting"),
            "withNumbers": len(withnum), "medianRevenueYoY": med(ry), "medianProfitYoY": med(py), "profitUpShare": share(py, lambda x: x > 0), "marginUpShare": share(mc, lambda x: x > 0),
            "flagged": sum(1 for r in withnum if r["flagged"]), "nRevenue": len(ry), "nProfit": len(py), "nMargin": len(mc)}


def strip_figures(r: dict) -> dict:
    out = dict(r)
    for k in FIGURES:
        out[k] = None
    out["flagged"] = out["loss"] = False
    out["locked"] = r["hasNumbers"]
    return out


def select(rows: List[dict], *, q: str = "", sector: str = "", cap: str = "", index: str = "", symbols: Optional[set] = None, flagged: bool = False, status: str = "",
           sort: str = "date", desc: bool = True, today: str = "9999-12-31", date_from: str = "", date_to: str = "") -> List[dict]:
    out = rows
    if date_from or date_to:   # the announcement date, as ISO text (which sorts like a date)
        out = [r for r in out if (not date_from or r["date"] >= date_from) and (not date_to or r["date"] <= date_to)]
    if q.strip():
        t = q.strip().lower()
        out = [r for r in out if t in r["symbol"].lower() or t in (r["name"] or "").lower()]
    if sector:
        out = [r for r in out if r["sector"] == sector]
    if cap:
        out = [r for r in out if r["cap"] == cap]
    if index:
        out = [r for r in out if index in r["indices"]]
    if symbols is not None:
        out = [r for r in out if r["symbol"] in symbols]
    if status:
        out = [r for r in out if r["status"] == status]
    if flagged:
        out = [r for r in out if r["flagged"]]
    mcap = lambda r: r["marketCap"] if r["marketCap"] is not None else -1.0   # noqa: E731
    if sort == "date":
        # Declared companies first, newest declaration first, the biggest company first within a day (ties: symbol, so the order never wobbles).
        # Dates still to come are listed after them, soonest first: "most recently declared first" must not start with next month's schedule.
        done = [r for r in out if r["date"] <= today]
        coming = sorted((r for r in out if r["date"] > today), key=lambda r: (r["date"], -mcap(r), r["symbol"]))
        done = sorted(done, key=lambda r: (r["date"], mcap(r), r["symbol"]), reverse=True) if desc else sorted(done, key=lambda r: (r["date"], -mcap(r), r["symbol"]))
        return done + coming
    if sort == "marketCap":
        return sorted(out, key=lambda r: (mcap(r), r["date"]), reverse=desc)
    key = NUMERIC_SORTS[sort]
    known = [r for r in out if r[key] is not None]
    rest = [r for r in out if r[key] is None]   # no figure: always last
    return sorted(known, key=lambda r: (r[key], r["date"]), reverse=desc) + sorted(rest, key=lambda r: (r["date"], mcap(r)), reverse=True)


async def _symbols_of(request: Request, ctx, scope: str) -> Optional[set]:
    if scope == "all":
        return None
    if not ctx.authed:
        raise fail(401, "auth_required", "Sign in to filter by your watchlist or portfolio.")
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT watchlist, portfolio FROM user_state WHERE user_id = $1", ctx.user_id)
    if not row:
        return set()
    parse = lambda v: (json.loads(v) if isinstance(v, str) else v) or {}   # noqa: E731
    if scope == "watchlist":
        return {str(s).upper() for lst in parse(row["watchlist"]).get("lists") or [] for s in lst.get("symbols") or []}
    return {str(h.get("symbol", "")).upper() for h in parse(row["portfolio"]).get("holdings") or []}


def parse_range(on: str, frm: str, to: str, today: date) -> Optional[Tuple[date, date]]:
    """`date=` (one day) or `from=`+`to=` (a range, both ends included), as India dates. None when no date was asked for. Raises a 400 with a plain message."""
    if not (on or frm or to):
        return None
    if on and (frm or to):
        raise fail(400, "bad_request", "Use either one date or a from and to range, not both.")
    if to and not frm:
        raise fail(400, "bad_request", "A range needs a from date as well as a to date.")
    vals = []
    for label, v in (("date", on), ("from", frm), ("to", to)):
        if not v:
            continue
        try:
            if not DATE_RE.match(v):
                raise ValueError
            vals.append(date.fromisoformat(v))
        except ValueError:
            raise fail(400, "bad_request", f"The {label} must look like {today.isoformat()} (year-month-day) and be a real calendar date.")
    start = vals[0]
    end = vals[0] if on else (vals[1] if len(vals) > 1 else today)
    if max(start, end) > today:
        raise fail(400, "future_date", f"Results can be looked up for dates up to today ({today.strftime('%a %d %b %Y')}, India time). Dates still to come are listed under 'Still to declare' for the quarter.", today=today.isoformat())
    if start > end:
        raise fail(400, "bad_request", "The from date is after the to date.")
    return start, end


def date_facts(decls: Dict[str, Dict[str, Decl]], rng: Tuple[date, date], qkey: Optional[str]) -> Dict[str, Any]:
    """What the date filter found in the declarations (before any other filter): per quarter in range, and the nearest days with results around it."""
    lo, hi = rng
    in_range: Dict[str, int] = {}
    per_day: Dict[date, int] = {}
    for qk, by_sym in decls.items():
        for d in by_sym.values():
            if lo <= d.date <= hi:
                in_range[qk] = in_range.get(qk, 0) + 1
            if qk == qkey:
                per_day[d.date] = per_day.get(d.date, 0) + 1
    quarters = []
    for qk, n in sorted(in_range.items(), reverse=True):
        e = parse_quarter(qk)
        if e is not None:
            quarters.append({"key": qk, "label": quarter_info(e)["label"], "fiscal": quarter_info(e)["fiscal"], "n": n})
    before = max((d for d in per_day if d < lo), default=None)
    after = min((d for d in per_day if d > hi), default=None)
    every = [d.date for by in decls.values() for d in by.values()]
    return {"from": lo.isoformat(), "to": hi.isoformat(), "single": lo == hi, "quarters": quarters, "inQuarter": sum(1 for d in per_day if lo <= d <= hi) > 0,
            "nearest": [{"date": d.isoformat(), "n": per_day[d]} for d in (before, after) if d is not None],
            "coverage": {"earliest": min(every).isoformat() if every else None, "latest": max(every).isoformat() if every else None}}


async def _answer(request: Request, quarter: str, q: str, sector: str, cap: str, index: str, scope: str, flagged: bool, status: str, sort: str, dir_: str,
                  on: str = "", frm: str = "", to: str = ""):
    ctx = await current(request)
    plan = ctx.plan if ctx.authed else "basic"
    silver = has(plan, "silver")
    if (sort in NUMERIC_SORTS or flagged) and not silver:
        raise fail(403, "plan_required", "Sorting and filtering by results figures is part of the Silver plan.", plan="silver")
    store = request.app.state.store
    today = today_ist()
    rng = parse_range(on, frm, to, today)
    decls = await get_declarations(store)
    quarters = list_quarters(decls, today)
    qkey = quarter or None
    if qkey is None and rng is not None:
        # no quarter chosen: the quarter most of the range's announcements belong to (a late-October day is mostly about the September quarter)
        counts: Dict[str, int] = {}
        for qk, by_sym in decls.items():
            counts[qk] = sum(1 for d in by_sym.values() if rng[0] <= d.date <= rng[1])
        best = max(counts.items(), key=lambda kv: (kv[1], kv[0]), default=(None, 0))
        qkey = best[0] if best[1] else None
        if qkey is None:
            guess = quarter_key(quarter_end_before(rng[1]))
            qkey = guess if guess in {x["key"] for x in quarters} else None
    qkey = qkey or default_quarter(quarters, today)
    if qkey is None:
        return ctx, plan, quarters, None, [], [], today, None
    if parse_quarter(qkey) is None:
        raise fail(400, "bad_request", "Quarter must look like 2026-09 (a quarter-end month: 03, 06, 09 or 12).")
    entry = await get_entry(store, qkey)
    syms = await _symbols_of(request, ctx, scope)
    rows = select(entry.rows, q=q, sector=sector, cap=cap, index=index, symbols=syms, flagged=flagged, status=status, sort=sort, desc=dir_ == "desc", today=today.isoformat(),
                  date_from=rng[0].isoformat() if rng else "", date_to=rng[1].isoformat() if rng else "")
    return ctx, plan, quarters, entry, rows, entry.rows, today, (date_facts(decls, rng, qkey) if rng else None)


def _dump(body: dict) -> Response:
    return Response(content=json.dumps(body, separators=(",", ":")), media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


@router.get("/quarter")
async def quarter_results(request: Request, quarter: str = Query("", max_length=7), q: str = Query("", max_length=60), sector: str = Query("", max_length=80),
                          cap: str = Query("", pattern="^(Large|Mid|Small)?$"), index: str = Query("", pattern="^(NIFTY50|NIFTY100|NIFTY500)?$"),
                          scope: str = Query("all", pattern="^(all|watchlist|portfolio)$"), flagged: bool = False,
                          status: str = Query("", pattern="^(declared|awaiting|due|missing)?$"), sort: str = Query("date", max_length=20), dir: str = Query("desc", pattern="^(asc|desc)$"),
                          offset: int = Query(0, ge=0, le=20000), limit: int = Query(PAGE, ge=1, le=100),
                          on: str = Query("", alias="date", max_length=10), from_: str = Query("", alias="from", max_length=10), to: str = Query("", max_length=10)):
    """One quarter's results, newest declaration first. Without `quarter` the latest quarter with declarations is used."""
    if sort not in SORTS:
        raise fail(400, "bad_request", "Unknown sort.")
    started = time.perf_counter()
    ctx, plan, quarters, entry, rows, all_rows, today, dates = await _answer(request, quarter, q, sector, cap, index, scope, flagged, status, sort, dir, on, from_, to)
    silver = has(plan, "silver")
    if entry is None:
        return _dump({"plan": plan, "locked": not silver, "today": today.isoformat(), "quarter": None, "quarters": quarters, "rows": [], "total": 0, "offset": 0, "limit": limit,
                      "summary": summarize([], today), "totals": summarize([], today), "days": [], "facets": {"sectors": [], "indices": []}, "dates": dates})
    page = rows[offset: offset + limit]
    out_rows = page if silver else [strip_figures(r) for r in page]
    summary = summarize(rows, today)
    totals = summarize(all_rows, today)
    if not silver:   # the headline counts are free; every average, share and flag is a figure
        for k in ("medianRevenueYoY", "medianProfitYoY", "profitUpShare", "marginUpShare", "flagged", "nRevenue", "nProfit", "nMargin"):
            summary[k] = totals[k] = None
    per_day: Dict[str, int] = {}
    for r in rows:
        per_day[r["date"]] = per_day.get(r["date"], 0) + 1
    idx_counts = {c: sum(1 for r in entry.rows if c in r["indices"]) for c in INDEX_FLAGS}
    return _dump({"plan": plan, "locked": not silver, "today": today.isoformat(), "quarter": entry.quarter, "quarters": quarters, "total": len(rows), "offset": offset, "limit": limit,
                  "summary": summary, "totals": totals, "rows": out_rows, "days": [{"date": d, "n": n} for d, n in sorted(per_day.items(), reverse=True)], "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(entry.loaded)),
                  "facets": {"sectors": [{"name": n, "n": c} for n, c in entry.sectors], "indices": [{"code": c, "n": n} for c, n in idx_counts.items()]},
                  "dates": dates, "dateMeaning": DATE_MEANING, "gapFlag": GAP_FLAG, "took": round((time.perf_counter() - started) * 1000, 1)})


@router.get("/quarter/export")
async def quarter_export(request: Request, quarter: str = Query("", max_length=7), q: str = Query("", max_length=60), sector: str = Query("", max_length=80),
                         cap: str = Query("", pattern="^(Large|Mid|Small)?$"), index: str = Query("", pattern="^(NIFTY50|NIFTY100|NIFTY500)?$"),
                         scope: str = Query("all", pattern="^(all|watchlist|portfolio)$"), flagged: bool = False,
                         status: str = Query("", pattern="^(declared|awaiting|due|missing)?$"), sort: str = Query("date", max_length=20), dir: str = Query("desc", pattern="^(asc|desc)$"),
                         on: str = Query("", alias="date", max_length=10), from_: str = Query("", alias="from", max_length=10), to: str = Query("", max_length=10)):
    """The same rows without paging, as JSON the website turns into a CSV (Silver and Gold)."""
    if sort not in SORTS:
        raise fail(400, "bad_request", "Unknown sort.")
    ctx = await current(request)
    if not has(ctx.plan if ctx.authed else "basic", "silver"):
        raise fail(403, "plan_required", "Downloading the quarter's results is part of the Silver plan.", plan="silver")
    _, _, _, entry, rows, _, today, _ = await _answer(request, quarter, q, sector, cap, index, scope, flagged, status, sort, dir, on, from_, to)
    return _dump({"quarter": entry.quarter if entry else None, "today": today.isoformat(), "rows": rows[:EXPORT_ROWS]})
