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

from . import results, results_run
from .calendars import why
from .finedge import FinEdgeClient, FinEdgeError, _rows_of, bundle_requests, latest_period_end, stale_reason
from .normalize import statements
from .screener.compute import _round, quarter_block

log = logging.getLogger("finlit.results_light")

MAX_AGE_DAYS = 4          # a declaration is chased at the normal rate (every run, then every 3 and 5 hours) for this many days
CHASE_DAYS = 14           # after MAX_AGE_DAYS it is still asked about, but only once a day, up to this many days after the declaration
LATE_RECHECK_HOURS = 24   # a company past MAX_AGE_DAYS is asked again after this long
LATE_PER_RUN = 60         # past-the-window companies get this many places in EVERY run (a reserved share, not what is left over): 60 x ~16 runs a day clears the daily chase of a results-season backlog
ASKED_WITHIN_HOURS = 16   # "waiting for the provider" means we asked within this many hours: the longest re-ask wait (5 h, results.retry_minutes) + the quiet night (23:00-08:00, 9 h) + 2 h of slack.
                          # It was 12, which a company asked at 20:00 and due again at 01:00 broke by itself at 08:00 (12.2 h): 'ours to fix' with nothing wrong on our side
LATE_ASKED_WITHIN_HOURS = 48   # for a past-the-window company the daily question may be this old before it counts as ours to fix
RECHECK_MINUTES = 50      # a company the provider had nothing for is asked again after this long (the hourly run therefore asks again each hour)
KEEP_QUARTERS = 3
PER_RUN = 300             # companies per run. Budget arithmetic: the run stops by itself at 80% of 30 min = 24 min; at the 0.4 s pause plus ~0.5-1 s per call that is ~40-60 companies a
                          # minute, and even with the pace at its 3 s cap it is ~360 in the budget. 300 x ~16 runs in the 08:00-23:00 window = 4,800 asks a day for ~1,300 declarations
                          # (first asks) plus the re-asks (every run for 2 days, then every 3 h, every 5 h, once a day past MAX_AGE_DAYS)
CALL_TIMEOUT_S = results_run.CALL_TIMEOUT_S   # one company (1-2 provider calls) never holds the run longer than this
BUDGET_FALLBACK_MIN = 24.0   # 80% of the registry's 30-minute max_runtime (results_run.budget_minutes reads the real figure)
MAX_IN_A_ROW = 10         # this many provider failures in a row end the run (a refusing or down provider is not asked 150 more times)
MAX_THROTTLED_IN_A_ROW = 6   # this many "too many requests" answers in a row end the run; it is not a failure, the next run continues with the same companies
PAUSE_MAX = 3.0           # the pause between calls doubles after a "too many requests" answer, up to this many seconds (never more: 3 s x 300 would not fit the budget), and shrinks back after successes
CALL_RETRIES = 1          # a provider call is tried twice at most (the next run is the real retry) ...
CALL_MAX_WAIT = 3.0       # ... and never waits more than this for a Retry-After or a backoff: a throttled company is skipped now and revisited first next run
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
        return await client.get(path, params, timeout=timeout, retries=CALL_RETRIES, max_wait=CALL_MAX_WAIT)
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


async def save(conn, symbol: str, qkey: str, got: Dict[str, Any], at: Optional[datetime] = None) -> bool:
    """Store one company's result (filled or unfilled) and keep only its latest 3 quarters. A filled row is never replaced by an unfilled one."""
    fig = got["figures"]
    async with conn.transaction():
        if fig:
            m, g = fig["m"], fig["opg"] or {}
            end = results.ymd_to_date(m.get("q_period_end"))
            await conn.execute(
                "INSERT INTO quarter_light (symbol, quarter, statement, filled, period_end, provider_latest, revenue, operating_profit, net_profit, eps, sales_yoy, profit_yoy, sales_qoq, "
                "profit_qoq, opm, npm, op_yoy, op_qoq, op_yoy_why, op_qoq_why, checked_at) VALUES ($1,$2,$3,true,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19, COALESCE($20::timestamptz, now())) "
                "ON CONFLICT (symbol, quarter) DO UPDATE SET statement = EXCLUDED.statement, filled = true, period_end = EXCLUDED.period_end, provider_latest = EXCLUDED.provider_latest, "
                "revenue = EXCLUDED.revenue, operating_profit = EXCLUDED.operating_profit, net_profit = EXCLUDED.net_profit, eps = EXCLUDED.eps, sales_yoy = EXCLUDED.sales_yoy, "
                "profit_yoy = EXCLUDED.profit_yoy, sales_qoq = EXCLUDED.sales_qoq, profit_qoq = EXCLUDED.profit_qoq, opm = EXCLUDED.opm, npm = EXCLUDED.npm, op_yoy = EXCLUDED.op_yoy, "
                "op_qoq = EXCLUDED.op_qoq, op_yoy_why = EXCLUDED.op_yoy_why, op_qoq_why = EXCLUDED.op_qoq_why, checked_at = COALESCE($20::timestamptz, now())",
                symbol, qkey, got["basis"], end, got["providerLatest"], *(m.get(q) for q in COLS.values()), g.get("opYoY"), g.get("opQoQ"), g.get("opYoYWhy"), g.get("opQoQWhy"), at)
        else:
            await conn.execute(
                "INSERT INTO quarter_light (symbol, quarter, statement, filled, provider_latest, checked_at) VALUES ($1,$2,$3,false,$4, COALESCE($5::timestamptz, now())) "
                "ON CONFLICT (symbol, quarter) DO UPDATE SET statement = EXCLUDED.statement, provider_latest = EXCLUDED.provider_latest, checked_at = COALESCE($5::timestamptz, now()) WHERE NOT quarter_light.filled",
                symbol, qkey, got["basis"], got["providerLatest"], at)
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
        out[r["symbol"]] = {"source": src, "mcap": r["mcap"], "checkedAt": r["checked_at"], "quarter": r["quarter"], "providerLatest": r["provider_latest"]}
    return out


def fair_key(s: Dict[str, Any], now: datetime) -> Tuple[int, float, str]:
    """Order of asking, smaller first: never asked, then the longest unasked (in FAIR_BAND_H-hour bands), and only inside a band the bigger company first
    (unknown size last), the symbol as the tie-break so the order never wobbles. Biggest-first alone starved every small company behind the same big ones."""
    ch = s["checkedAt"]
    age_h = None if ch is None else (now - ch).total_seconds() / 3600
    return (results_run.fair_band(age_h), -(s["mcap"] if s["mcap"] is not None else -1.0), s["symbol"])


async def plan(store, today: Optional[date] = None, recheck_minutes: int = RECHECK_MINUTES, max_age_days: int = MAX_AGE_DAYS, chase_days: int = CHASE_DAYS,
               late_per_run: int = LATE_PER_RUN, limit: Optional[int] = None, now: Optional[datetime] = None) -> Tuple[List[Tuple[str, str]], int]:
    """([(symbol, quarter key)] to ask this run, how many are due in all). Due = declared in the last `max_age_days` and not asked within its re-ask wait
    (every run for two days, then every 3 hours, then every 5), or declared up to `chase_days` ago and not asked for LATE_RECHECK_HOURS (the daily chase).
    Figures not in the full report, no filled light row. Both groups are in fair order (fair_key); with a `limit` the past-the-window group has a RESERVED
    share of `late_per_run` places (it used to come after the declared-lately group, so with a long list of those the daily chase was never reached)."""
    today = today or results.today_ist()
    recent = await recent_declarations(store, today, max(chase_days, max_age_days))
    st = await states(store, recent)
    now = now or datetime.now().astimezone()
    todo, late = [], []
    for sym, s in st.items():
        if s["source"] in ("full", "light"):
            continue
        decl = recent[sym][1]
        item = (fair_key({**s, "symbol": sym}, now), sym, s["quarter"])
        if (today - decl).days > max_age_days:
            # given up chasing every run: asked once a day, so a provider that publishes a week late still gets picked up
            if s["checkedAt"] is None or (now - s["checkedAt"]) >= timedelta(hours=LATE_RECHECK_HOURS):
                late.append(item)
            continue
        # asked again every run for the first two days, then every 3 hours, then every 5 (results.retry_minutes): a late provider is not hammered
        if s["checkedAt"] is not None and (now - s["checkedAt"]) < timedelta(minutes=results.retry_minutes(recheck_minutes, decl, today)):
            continue
        todo.append(item)
    todo.sort()
    late.sort()
    take_late = late[:late_per_run]
    take_todo = todo if limit is None else todo[:max(0, limit - len(take_late))]
    if limit is not None and len(take_todo) + len(take_late) < limit:   # the declared-lately group is short: the unused places go to more of the daily chase
        take_late = late[:max(late_per_run, limit - len(take_todo))]
    return [(sym, qk) for _, sym, qk in take_todo + take_late], len(todo) + len(late)


async def candidates(store, today: Optional[date] = None, recheck_minutes: int = RECHECK_MINUTES, max_age_days: int = MAX_AGE_DAYS, chase_days: int = CHASE_DAYS,
                     late_per_run: int = LATE_PER_RUN) -> List[Tuple[str, str]]:
    """The list `plan` gives without a run limit (see there)."""
    return (await plan(store, today, recheck_minutes, max_age_days, chase_days, late_per_run))[0]


def throttled(exc: BaseException) -> bool:
    """True for the provider's "too many requests" / "busy" answers (429, 503): slow down and carry on next run; not a failure of the company."""
    return bool(getattr(exc, "throttled", False)) or getattr(exc, "status", None) in (429, 503)


async def refresh_light(client: FinEdgeClient, store, limit: int = PER_RUN, today: Optional[date] = None, pause: float = 0.4, max_minutes: Optional[float] = None,
                        recheck_minutes: int = RECHECK_MINUTES, clock=time.monotonic, now_fn=lambda: datetime.now().astimezone()) -> Dict[str, Any]:
    """One run: up to `limit` companies, sequential, one provider call each (two when consolidated lacks the quarter). Resumable by construction: a filled
    company is never asked again, an unfilled one only after `recheck_minutes`.

    Bounded: the run stops by itself at `max_minutes` (default: 80% of the job's max_runtime, results_run.budget_minutes) or when the supervisor asks it to
    end (SIGTERM), and says so (`stoppedBy`, `left`); a single company never holds it longer than CALL_TIMEOUT_S; no wait is longer than the pace cap.
    Pacing: the pause between calls starts at `pause`, doubles (up to PAUSE_MAX, or the provider's Retry-After if shorter) after every "too many requests"
    answer and shrinks back by a third after each success. Such an answer is not a failure: it is counted as `throttled`, the company is SKIPPED (not waited
    on), nothing is stored, so it is first in line next run, and it does not count toward MAX_IN_A_ROW; only MAX_THROTTLED_IN_A_ROW of them in a row end the
    run. A real error (anything else, a call that did not answer in time included) is counted, listed under `errors`, and ends the run only after
    MAX_IN_A_ROW in a row."""
    started = clock()
    budget_s = (max_minutes if max_minutes is not None else results_run.budget_minutes("results-light", BUDGET_FALLBACK_MIN)) * 60
    deadline = started + budget_s
    todo, due = await plan(store, today, recheck_minutes, limit=limit, now=now_fn())
    out: Dict[str, Any] = {"candidates": due, "planned": len(todo), "tried": 0, "filled": 0, "providerPending": 0, "failed": 0, "throttled": 0, "timedOut": 0}
    errors: Dict[str, int] = {}
    deferred: List[str] = []
    in_a_row = throttled_in_a_row = 0
    gap = pause
    redis = getattr(store, "redis", None)
    prog = results_run.Progress(redis, "refresh-results-light", budget_s, len(todo)) if redis is not None else None
    stop = ""
    for sym, qk in todo:
        if results_run.Stop.requested:
            stop = f"told to stop ({results_run.Stop.signal_name or 'signal'}) after {out['tried']} companies; the next run continues"
            out["stoppedBy"] = "signal"
            break
        if clock() >= deadline:
            stop = f"the time budget of {budget_s / 60:.0f} minutes was reached after {out['tried']} companies; the next run continues"
            out["stoppedBy"] = "budget"
            break
        e = results.parse_quarter(qk)
        if e is None:
            continue
        out["tried"] += 1
        if prog:
            await prog.step(sym, "asking the provider", done=out["tried"] - 1)
        try:
            got = await asyncio.wait_for(fetch_quarter(client, sym, e), CALL_TIMEOUT_S)
            if prog:
                await prog.step(sym, "storing", done=out["tried"] - 1)
            async with store.pool.acquire() as conn:
                filled = await save(conn, sym, qk, got, at=now_fn())
            out["filled" if filled else "providerPending"] += 1
            in_a_row = throttled_in_a_row = 0
            gap = max(pause, gap * 0.67)
        except Exception as exc:   # one company never stops the run
            if throttled(exc):
                out["throttled"] += 1
                throttled_in_a_row += 1
                deferred.append(sym)
                gap = min(PAUSE_MAX, max(gap * 2, pause * 2, getattr(exc, "retry_after", None) or 0.0))
                log.warning("results-light %s: the provider asked us to slow down (%s); pause is now %.1fs", sym, why(exc), gap)
                if throttled_in_a_row >= MAX_THROTTLED_IN_A_ROW:
                    stop = "the provider kept answering 'too many requests'; the next run continues with the same companies"
                    out["stoppedBy"] = "throttled"
                    break
            else:
                out["failed"] += 1
                in_a_row += 1
                throttled_in_a_row = 0
                if isinstance(exc, asyncio.TimeoutError):
                    out["timedOut"] += 1
                    reason = f"no answer within {CALL_TIMEOUT_S:g} s"
                else:
                    reason = why(exc)
                errors[reason] = errors.get(reason, 0) + 1
                log.warning("results-light %s failed: %s", sym, reason)
                if in_a_row >= MAX_IN_A_ROW:   # the provider is refusing or down: stop here, the next run starts again
                    log.warning("results-light stopped after %d failures in a row (last: %s)", in_a_row, reason)
                    stop = f"{in_a_row} failures in a row (last: {reason}); the next run starts again"
                    out["stoppedBy"] = "failures"
                    break
        if gap:
            await asyncio.sleep(min(gap, max(0.0, deadline - clock())))   # the pause never runs past the budget
    if stop:
        out["stoppedEarly"], out["stopReason"] = True, stop
    # still to ask: everything due that this run did not settle (a company the provider has no quarter for yet is settled: it is asked again after its wait)
    out["left"] = max(0, due - out["filled"] - out["providerPending"])
    if errors:
        out["errors"] = dict(sorted(errors.items(), key=lambda kv: -kv[1])[:4])
    if deferred:
        out["deferred"] = deferred[:10]    # told to wait by the provider; they are first in line next run
    if out["throttled"]:
        out["pauseSeconds"] = round(gap, 2)    # where the adaptive pause ended
    out["durationSeconds"] = int(clock() - started)
    if prog:
        await prog.finish("partial" if stop else "done", done=out["tried"], stopReason=stop or None)
    log.info("refresh-results-light: %s", out)
    return out


# ------------------------------------------------------------------ buckets: why a declared company has no figures yet
FILLED, WAITING, GAVE_UP, OURS, QUEUED = "filled", "waiting_for_provider", "gave_up", "ours_to_fix", "queued"


def bucket_of(s: Dict[str, Any], declared: date, today: date, now: datetime) -> Dict[str, Any]:
    """Which explicit bucket one declared company is in, and why. Returns {bucket, reason, severity, askedHoursAgo, declared}.
      filled                figures held (full report or light row)
      waiting_for_provider  we asked within ASKED_WITHIN_HOURS and the provider has no new quarter yet (declared at most MAX_AGE_DAYS ago): information, not an alarm
      queued                declared today and not asked yet (the next hourly run asks)
      gave_up               declared more than MAX_AGE_DAYS ago: no longer chased every run, asked once a day until CHASE_DAYS; listed, not an alarm
      ours_to_fix           the provider HAS the quarter and we did not fill it, or we did not ask in time: this is the alarm (severity stale | late)"""
    age = (today - declared).days
    checked = s.get("checkedAt")
    asked_h = round((now - checked).total_seconds() / 3600, 1) if checked is not None else None
    base = {"askedHoursAgo": asked_h, "declared": declared}
    if s["source"] in ("full", "light"):
        return {**base, "bucket": FILLED, "reason": "figures held", "severity": None}

    def ours(reason: str, stale: bool) -> Dict[str, Any]:
        return {**base, "bucket": OURS, "reason": reason, "severity": "stale" if stale else "late"}

    if age > MAX_AGE_DAYS:
        if checked is None:
            return {**base, "bucket": GAVE_UP, "reason": f"declared {age} days ago, the provider has not published it; the daily check has not reached it yet", "severity": None}
        if asked_h is not None and asked_h <= LATE_ASKED_WITHIN_HOURS:
            return {**base, "bucket": GAVE_UP, "reason": f"declared {age} days ago, the provider has not published it; asked {asked_h:g} h ago, then once a day", "severity": None}
        return ours(f"declared {age} days ago and the daily check has not asked for {asked_h:g} h", False)
    if s["source"] == "provider":
        if asked_h is not None and asked_h <= ASKED_WITHIN_HOURS:
            return {**base, "bucket": WAITING, "reason": f"asked {asked_h:g} h ago, the provider has not published the quarter yet", "severity": None}
        return ours(f"not asked for {asked_h:g} h (it should be asked at least every {ASKED_WITHIN_HOURS} h)", age >= 2)
    # source == "ours": no row at all, or the provider has the quarter (or newer data) and we did not fill it
    if checked is None:
        if age == 0:
            return {**base, "bucket": QUEUED, "reason": "declared today, not asked yet", "severity": None}
        return ours(f"declared {age} day(s) ago and never asked", age >= 2)
    pl = s.get("providerLatest")
    return ours(f"the provider has data up to {pl.isoformat()} but the quarter was not filled" if pl else "the provider answered but the quarter could not be read", age >= 2)


def summarise_buckets(recent: Dict[str, Tuple[str, date]], st: Dict[str, Dict[str, Any]], today: date, now: datetime) -> Dict[str, Any]:
    """Counts per bucket with the oldest declaration, and the reasons for ours_to_fix: the facts the freshness rule and the status text are built from."""
    names = (FILLED, WAITING, QUEUED, GAVE_UP, OURS)
    b: Dict[str, Any] = {n: {"count": 0, "oldest": None} for n in names}
    ours: List[Dict[str, Any]] = []
    for sym, s in st.items():
        v = bucket_of(s, recent[sym][1], today, now)
        e = b[v["bucket"]]
        e["count"] += 1
        d = v["declared"]
        if e["oldest"] is None or d < e["oldest"]:
            e["oldest"] = d
        if v["bucket"] == OURS:
            ours.append({"symbol": sym, "declared": d, "reason": v["reason"], "severity": v["severity"]})
    ours.sort(key=lambda x: (x["declared"], x["symbol"]))
    for n in names:
        b[n]["oldest"] = b[n]["oldest"].isoformat() if b[n]["oldest"] else None
    reasons: Dict[str, int] = {}
    for o in ours:
        k = " ".join("".join("#" if c.isdigit() else c for c in o["reason"].split(" (")[0]).split())   # one reason with different numbers is one reason
        reasons[k] = reasons.get(k, 0) + 1
    b["declared"] = len(st)
    b["oursSeverity"] = "stale" if any(o["severity"] == "stale" for o in ours) else "late" if ours else None
    b["oursReasons"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:4])
    b["oursSample"] = [{"symbol": o["symbol"], "declared": o["declared"].isoformat(), "reason": o["reason"]} for o in ours[:10]]
    return b


async def bucket_facts(store, today: date, now: datetime) -> Dict[str, Any]:
    """The bucket summary for everyone who declared in the last CHASE_DAYS days (read-only; uses the cached declarations)."""
    recent = await recent_declarations(store, today, CHASE_DAYS, force=False)
    return summarise_buckets(recent, await states(store, recent), today, now)


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
