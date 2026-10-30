"""Quarter results for companies the site does not hold in full (the light path).

The quarter results page reads a company's figures from its stored full report. Only the biggest companies (INGEST_LIMIT) and the ones members
opened are kept in full, so every other company that declared stayed "Declared, report being updated" for ever. This module fills the gap
with ONE provider call per company: its quarterly profit and loss (consolidated; standalone when consolidated is missing or stale). The
figures are worked out by the SAME functions the full report uses (normalize/statements.profit_and_loss for the rows, screener/compute.quarter_block
for revenue, profit, margins and growth, results.op_growth for operating profit growth), then stored as one tiny row per company per quarter in
`quarter_light` (the latest 3 quarters per company). No snapshot and no score is created. The results page prefers the full report when it
already holds the quarter, else uses this row; a row never mixes the two.

A company the provider has no new quarter for yet gets an UNFILLED row (a record that we asked, and when): the page then says so honestly, and
the next run asks again.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import results
from .calendars import why
from .finedge import FinEdgeClient, FinEdgeError, _rows_of, bundle_requests, latest_period_end, stale_reason
from .normalize import statements
from .screener.compute import _round, quarter_block

log = logging.getLogger("finlit.results_light")

MAX_AGE_DAYS = 4          # a declaration is chased for this many days
RECHECK_MINUTES = 50      # a company the provider had nothing for is asked again after this long (the hourly run therefore asks again each hour)
KEEP_QUARTERS = 3
PER_RUN = 150
MAX_IN_A_ROW = 10         # this many provider failures in a row end the run (a refusing or down provider is not asked 150 more times)
STALE_DAYS = 170          # finedge.stale_reason: standalone this much newer than consolidated means consolidated is stale
TOLERANCE = 10            # days between the quarter asked for and the provider's period end (same as the full path)
COLS = results.LIGHT_COLS   # quarter_light column -> the screener metric of the same meaning


# ------------------------------------------------------------------ figures (pure)
def quarter_figures(payload: Any, e: date) -> Optional[Dict[str, Any]]:
    """The provider's quarterly P&L payload -> the figures of the quarter ending near `e`, or None when that quarter is not in it (or has neither
    revenue nor net profit). Uses exactly the full pipeline's functions, so the same input gives the same numbers on both paths."""
    table = statements.profit_and_loss(_rows_of(payload), "quarterly")
    blk = quarter_block(table, e, TOLERANCE)
    blk = {k: _round(k, v) for k, v in blk.items()}   # the full report stores its metrics rounded to 4 decimals (compute.py): round the same way so a row reads identically
    if not blk or (blk.get("q_revenue") is None and blk.get("q_net_profit") is None):
        return None
    op_row = (table.get("rows") or {}).get("operating_profit")
    opg = results.op_growth(table["periodEnds"], op_row, e, blk.get("q_operating_profit")) if isinstance(op_row, list) else None
    if blk.get("q_operating_profit") is None:   # as build_row does: no operating profit means "not reported", not a missing prior
        opg = {"opYoY": None, "opQoQ": None, "opYoYWhy": "no_data", "opQoQWhy": "no_data"}
    return {"m": blk, "opg": opg}


async def _get(client: FinEdgeClient, symbol: str, statement: str) -> Any:
    path, params, timeout = bundle_requests(symbol, statement)["pl_quarterly"]
    try:
        return await client.get(path, params, timeout=timeout)
    except FinEdgeError as exc:
        if exc.status == 404:      # the provider has no such statements for this company: an answer, not a failure
            return None
        raise


def _has_quarter(payload: Any, e: date) -> bool:
    for r in _rows_of(payload):
        d = latest_period_end({"financials": [r]})
        if d is not None and abs((d - e).days) <= TOLERANCE:
            return True
    return False


async def fetch_quarter(client: FinEdgeClient, symbol: str, e: date) -> Dict[str, Any]:
    """One call (consolidated) in the usual case. When consolidated is missing or at least 170 days behind the quarter, one more call (standalone) decides the basis by the
    full ingest's rule: standalone when consolidated is missing or stale (finedge.stale_reason), else consolidated stays. Raises on a provider failure."""
    cons = await _get(client, symbol, "consolidated")
    basis, payload = "consolidated", cons
    cq = latest_period_end(cons)
    # Consolidated is stale only when standalone is >= 170 days ahead of it, and standalone cannot be ahead of the declared quarter: so a consolidated
    # that is less than that behind (the usual "provider has not published the quarter yet") needs no second call.
    if not _has_quarter(cons, e) and (cq is None or (e + timedelta(days=TOLERANCE) - cq).days >= STALE_DAYS):
        stand = await _get(client, symbol, "standalone")
        no_cons = not _rows_of(cons)
        if (no_cons and _rows_of(stand)) or stale_reason({"pl_quarterly": cons}, None, stand):
            basis, payload = "standalone", stand
    return {"basis": basis, "figures": quarter_figures(payload, e), "providerLatest": latest_period_end(payload)}


# ------------------------------------------------------------------ database
def _ymd(d: date) -> float:
    return float(d.year * 10000 + d.month * 100 + d.day)


async def save(conn, symbol: str, qkey: str, got: Dict[str, Any]) -> bool:
    """Store one company's result (filled or unfilled) and keep only its latest 3 quarters. A filled row is never replaced by an unfilled one."""
    fig = got["figures"]
    async with conn.transaction():
        if fig:
            m, g = fig["m"], fig["opg"] or {}
            end = results.ymd_to_date(m.get("q_period_end"))
            await conn.execute(
                "INSERT INTO quarter_light (symbol, quarter, statement, filled, period_end, provider_latest, revenue, operating_profit, net_profit, eps, sales_yoy, profit_yoy, sales_qoq, "
                "profit_qoq, opm, npm, op_yoy, op_qoq, op_yoy_why, op_qoq_why, checked_at) VALUES ($1,$2,$3,true,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19, now()) "
                "ON CONFLICT (symbol, quarter) DO UPDATE SET statement = EXCLUDED.statement, filled = true, period_end = EXCLUDED.period_end, provider_latest = EXCLUDED.provider_latest, "
                "revenue = EXCLUDED.revenue, operating_profit = EXCLUDED.operating_profit, net_profit = EXCLUDED.net_profit, eps = EXCLUDED.eps, sales_yoy = EXCLUDED.sales_yoy, "
                "profit_yoy = EXCLUDED.profit_yoy, sales_qoq = EXCLUDED.sales_qoq, profit_qoq = EXCLUDED.profit_qoq, opm = EXCLUDED.opm, npm = EXCLUDED.npm, op_yoy = EXCLUDED.op_yoy, "
                "op_qoq = EXCLUDED.op_qoq, op_yoy_why = EXCLUDED.op_yoy_why, op_qoq_why = EXCLUDED.op_qoq_why, checked_at = now()",
                symbol, qkey, got["basis"], end, got["providerLatest"], *(m.get(q) for q in COLS.values()), g.get("opYoY"), g.get("opQoQ"), g.get("opYoYWhy"), g.get("opQoQWhy"))
        else:
            await conn.execute(
                "INSERT INTO quarter_light (symbol, quarter, statement, filled, provider_latest, checked_at) VALUES ($1,$2,$3,false,$4, now()) "
                "ON CONFLICT (symbol, quarter) DO UPDATE SET statement = EXCLUDED.statement, provider_latest = EXCLUDED.provider_latest, checked_at = now() WHERE NOT quarter_light.filled",
                symbol, qkey, got["basis"], got["providerLatest"])
        await conn.execute("DELETE FROM quarter_light WHERE symbol = $1 AND quarter NOT IN (SELECT quarter FROM quarter_light WHERE symbol = $1 ORDER BY quarter DESC LIMIT $2)", symbol, KEEP_QUARTERS)
    return bool(fig)


STATE_SQL = (
    "SELECT x.symbol, x.quarter, (SELECT s.metrics->>'q_period_end' FROM scores s WHERE s.symbol = x.symbol AND s.model = 'v1' "
    "ORDER BY (s.statement = 'consolidated') DESC, s.updated_at DESC LIMIT 1) AS qpe, q.filled, q.checked_at, q.provider_latest, "
    "COALESCE(NULLIF(l.market_cap, 0), (SELECT s.market_cap FROM scores s WHERE s.symbol = x.symbol AND s.market_cap IS NOT NULL ORDER BY s.updated_at DESC LIMIT 1))::float8 AS mcap "
    "FROM unnest($1::text[], $2::text[]) AS x(symbol, quarter) LEFT JOIN quarter_light q ON q.symbol = x.symbol AND q.quarter = x.quarter "
    "LEFT JOIN listing_quotes l ON l.symbol = x.symbol")


async def recent_declarations(store, today: date, days: int = MAX_AGE_DAYS, force: bool = True) -> Dict[str, Tuple[str, date]]:
    """{symbol: (quarter key, declaration date)} for everyone who declared (a filing, or a board-meeting date that has passed) in the last `days`
    days. A company with two such quarters keeps the newest."""
    decls = await results.get_declarations(store, force=force)
    out: Dict[str, Tuple[str, date]] = {}
    for qk, by_sym in decls.items():
        for sym, d in by_sym.items():
            if d.date <= today and (today - d.date).days <= days and (sym not in out or (qk, d.date) > out[sym]):
                out[sym] = (qk, d.date)
    return out


async def states(store, recent: Dict[str, Tuple[str, date]]) -> Dict[str, Dict[str, Any]]:
    """For each symbol: where its figures for the declared quarter come from. source = full (the stored report holds the quarter), light (a filled
    row), provider (we asked, the provider has nothing yet), ours (not asked yet / our own lag)."""
    if not recent:
        return {}
    syms = sorted(recent)
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(STATE_SQL, syms, [recent[s][0] for s in syms])
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        e = results.parse_quarter(r["quarter"])
        try:
            have = results.ymd_to_date(float(r["qpe"])) if r["qpe"] else None
        except ValueError:
            have = None
        if have is not None and e is not None and have >= e - timedelta(days=TOLERANCE):
            src = "full"
        elif r["filled"]:
            src = "light"
        elif r["filled"] is False and (r["provider_latest"] is None or e is None or r["provider_latest"] <= e + timedelta(days=TOLERANCE)):
            src = "provider"
        else:
            src = "ours"
        out[r["symbol"]] = {"source": src, "mcap": r["mcap"], "checkedAt": r["checked_at"], "quarter": r["quarter"]}
    return out


async def candidates(store, today: Optional[date] = None, recheck_minutes: int = RECHECK_MINUTES, max_age_days: int = MAX_AGE_DAYS) -> List[Tuple[str, str]]:
    """(symbol, quarter key) to fetch: declared in the last `max_age_days`, figures not in the full report, no filled light row, and not asked in the
    last `recheck_minutes`. Biggest market cap first (unknown last), symbol as the tie-break so the order never wobbles."""
    today = today or results.today_ist()
    recent = await recent_declarations(store, today, max_age_days)
    st = await states(store, recent)
    now = datetime.now().astimezone()
    todo = []
    for sym, s in st.items():
        if s["source"] in ("full", "light"):
            continue
        # asked again every run for the first two days, then every 3 hours, then every 5 (results.retry_minutes): a late provider is not hammered
        if s["checkedAt"] is not None and (now - s["checkedAt"]) < timedelta(minutes=results.retry_minutes(recheck_minutes, recent[sym][1], today)):
            continue
        todo.append((-(s["mcap"] if s["mcap"] is not None else -1.0), sym, s["quarter"]))
    return [(sym, qk) for _, sym, qk in sorted(todo)]


async def refresh_light(client: FinEdgeClient, store, limit: int = PER_RUN, today: Optional[date] = None, pause: float = 0.4, max_minutes: float = 25.0,
                        recheck_minutes: int = RECHECK_MINUTES) -> Dict[str, Any]:
    """One run: up to `limit` companies, sequential, one provider call each (two when consolidated lacks the quarter). A per-company error is counted and
    skipped; the company is asked again next run. Resumable by construction: a filled company is never asked again, an unfilled one only after
    `recheck_minutes`."""
    todo = (await candidates(store, today, recheck_minutes))
    out: Dict[str, Any] = {"candidates": len(todo), "tried": 0, "filled": 0, "providerPending": 0, "failed": 0}
    errors: Dict[str, int] = {}
    in_a_row = 0
    deadline = time.monotonic() + max_minutes * 60
    for sym, qk in todo[:limit]:
        if time.monotonic() > deadline:
            break
        e = results.parse_quarter(qk)
        if e is None:
            continue
        out["tried"] += 1
        try:
            got = await fetch_quarter(client, sym, e)
            async with store.pool.acquire() as conn:
                filled = await save(conn, sym, qk, got)
            out["filled" if filled else "providerPending"] += 1
            in_a_row = 0
        except Exception as exc:   # one company never stops the run
            out["failed"] += 1
            in_a_row += 1
            reason = why(exc)
            errors[reason] = errors.get(reason, 0) + 1
            log.warning("results-light %s failed: %s", sym, reason)
            if in_a_row >= MAX_IN_A_ROW:   # the provider is refusing or down: stop here, the next run starts again
                log.warning("results-light stopped after %d failures in a row (last: %s)", in_a_row, reason)
                out["stoppedEarly"] = True
                break
        if pause:
            await asyncio.sleep(pause)
    if errors:
        out["errors"] = dict(sorted(errors.items(), key=lambda kv: -kv[1])[:4])
    log.info("refresh-results-light: %s", out)
    return out


async def coverage(store, today: Optional[date] = None, days: int = 3) -> Dict[str, Any]:
    """Admin data-health: of the companies that declared in the last `days` days, how many have figures (full report or light row), how many wait
    for the provider, how many wait for us."""
    today = today or results.today_ist()
    recent = await recent_declarations(store, today, days - 1, force=False)
    st = await states(store, recent)
    n = {"full": 0, "light": 0, "provider": 0, "ours": 0}
    for s in st.values():
        n[s["source"]] += 1
    return {"days": days, "declared": len(st), "filled": n["full"] + n["light"], "fromFullReport": n["full"], "fromLightRow": n["light"],
            "awaitingProvider": n["provider"], "awaitingOurs": n["ours"]}
