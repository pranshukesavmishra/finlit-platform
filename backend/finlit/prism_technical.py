"""The daily refresh of the technical (short-term and long-term) view of every stored Prism report: `refresh-technicals`.

WHY. The technical scores are computed inside the Prism report calculation, so until now they changed only when the whole report was calculated
again: the nightly job rates only companies WITHOUT a report (or one older than `--days`, 7 by default, and the widened ones 30 days), and a member's
"Recalculate" is the only other way. A stored report therefore showed a technical view up to a week or a month old, while other platforms show
the last close. This job recomputes ONLY the technical view, once per trading day, from fresh Dhan daily candles, and writes it into the stored
report (`report.technicalAssessment`) and the small `card` (what the screener and the header dots read) with its bar date and calculation time.
Nothing else in the report changes (not the rating, not `generated_at`, not the id: a PDF link stays valid).

HOW. For each company with a stored report whose technical bar date is older than the newest completed session:
  1. the same Dhan candles a report would send (prism_candles.supplied_candles: the stock's six years and the four shared, cached index series);
  2. POST /api/premium-reports/technical on the site backend, which runs the very functions the full report runs (technical_refresh.technical_only);
  3. the answer goes through the same reader filter (prism.technical_view) and replaces the stored technical view.
A stored view is replaced only by a complete one: if today's candles give an incomplete assessment, the older complete view stays and keeps its own date.

THE SESSION. The newest completed session is the Nifty 50's last candle that Dhan holds (prism_candles.reference_session): on a market holiday, or
before Dhan has posted the day, it is the earlier date, and a company already at that date is not fetched again. The job is meant to run at 18:30 IST
(candles are final after the 15:30 close; the reports' own rule is 16:00) and again in the evening and morning windows; every run is resumable (what is at
the newest date counts as done), paced (Dhan: one call per company, about 3 a second), gives way to members, and stops at its time limit or after
five failures in a row. The result of each run is stored (`record_run`, key run:refresh-technicals) and shown, with the dates held, at GET /api/technicals/status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import prism
from .auth.routes import IST
from .prism_candles import expected_session, is_down, reference_session, supplied_candles

log = logging.getLogger("finlit.prism.technical")
router = APIRouter(prefix="/api/technicals")

RUN_NAME = "refresh-technicals"
SUB = "prism:technical"                  # the subject of the gateway token the job calls the site backend with
TARGET_KEY = "prism:tech:target"         # {"expected": day, "target": day, "at": epoch}: what the last run found to be the newest completed session
NONEW_PREFIX = "prism:tech:nonew:"       # + symbol: Dhan holds nothing newer than the stored bar for it (suspended, or no session yet): do not ask again soon
TRY_PREFIX = "prism:tech:try:"           # + symbol: a refresh of this company was started lately (the page-open refresh is rate limited by this)
NONEW_SECONDS = 20 * 3600
TRY_SECONDS = 1800
REFRESHING_SECONDS = 150                 # the page keeps asking again for this long after a refresh started
TARGET_SECONDS = 36 * 3600
CALL_SECONDS = 120.0                     # the site backend's technical call takes about a second; this is only the upper bound
CANDLE_SECONDS = prism.CANDLE_SECONDS
MEMBER_WAIT_SECONDS = 90.0               # the job waits this long, in total per company, for members' calculations to finish
FAIL_STREAK = 5
PAGE_REFRESH_SLOTS = 2                   # page-open refreshes at once, in this process
_page_tasks: "set[asyncio.Task]" = set()

STATEMENTS = ("consolidated", "standalone")


# ------------------------------------------------------------------------------------------------ what a stored row holds
def bar_date(report: Any, card: Any = None) -> Optional[str]:
    """The date of the last candle the stored technical view was calculated on (ISO), or None when there is none."""
    card = card if isinstance(card, dict) else {}
    value = card.get("technicalBarDate")
    if not isinstance(value, str):
        tech = report.get("technicalAssessment") if isinstance(report, dict) else None
        value = tech.get("asOf") if isinstance(tech, dict) else None
    return value if isinstance(value, str) and len(value) == 10 else None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def technical_state(row: Any, now: Optional[datetime] = None, target: Optional[date] = None) -> Dict[str, Any]:
    """What a stored row says about its technical view, for the page: {"asOf", "calculatedAt", "stale"}. `stale`: older than the newest completed session."""
    report, card = _json(row["report"]), _json(row["card"]) if "card" in row.keys() and row["card"] is not None else {}
    bar = bar_date(report, card)
    target = target or expected_session(now or datetime.now(IST))
    at = (card or {}).get("technicalAt") or (report.get("technicalCalculatedAt") if isinstance(report, dict) else None) or row["generated_at"].isoformat()
    return {"asOf": bar, "calculatedAt": at, "stale": bar is None or bar < target.isoformat()}


# ------------------------------------------------------------------------------------------------ selection
async def pending(store, target: date, limit: int, skip: List[str], *, force: bool = False, symbols: Optional[List[str]] = None) -> List[str]:
    """Companies with a stored report (either basis) whose technical bar date is older than `target`, the biggest first; `skip`: left out for now."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT p.symbol FROM (SELECT symbol, min(COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}', '0000-00-00')) AS bar "
            "FROM prism_reports GROUP BY symbol) p LEFT JOIN listing_quotes q ON q.symbol = p.symbol "
            "WHERE ($4::boolean OR p.bar < $1) AND NOT (p.symbol = ANY($3::text[])) AND ($5::text[] IS NULL OR p.symbol = ANY($5::text[])) "
            "ORDER BY q.market_cap DESC NULLS LAST, p.symbol LIMIT $2", target.isoformat(), limit, skip, force, symbols)
    return [r["symbol"] for r in rows if prism.SYMBOL.match(r["symbol"])]


async def _shares_cr(conn, symbol: str, rows: List[Any]) -> Tuple[Optional[float], Optional[float]]:
    """(shares outstanding in crore, the price to check the last close against). The shares the report itself used (stored with its technical view since
    this job exists) are taken first, so the benchmark chosen cannot change between a report and its refreshes; otherwise market value / price from the listing."""
    q = await conn.fetchrow("SELECT price, market_cap FROM listing_quotes WHERE symbol = $1", symbol)
    price = float(q["price"]) if q and q["price"] is not None and float(q["price"]) > 0 else None
    for row in rows:
        tech = _json(row["report"]).get("technicalAssessment")
        stored = tech.get("sharesCr") if isinstance(tech, dict) else None
        if isinstance(stored, (int, float)) and not isinstance(stored, bool) and stored > 0:
            return float(stored), price
    if q and price and q["market_cap"] is not None and float(q["market_cap"]) > 0:
        return float(q["market_cap"]) / price, price
    return None, price


# ------------------------------------------------------------------------------------------------ one company
class Outcome:
    UPDATED, SKIPPED, FAILED, WITHHELD = "updated", "skipped", "failed", "withheld"


def withheld_reason(assessment: Dict[str, Any]) -> str:
    """Why an assessment is not complete, in one of a few words the status page counts."""
    if assessment.get("fresh") is False:
        return "stale_candles"
    if (assessment.get("usableDailyBars") or 0) < (assessment.get("dailyBars") or 0):
        return "gap_in_candles"
    if (assessment.get("usableDailyBars") or 0) < 252:
        return "short_history"
    return "incomplete_signals"


async def _post(app, payload: Dict[str, Any]) -> Optional[httpx.Response]:
    """The technical call; waits (a few seconds at a time) while the site backend says a member is waiting for a report."""
    waited = 0.0
    while True:
        try:
            r = await asyncio.wait_for(prism._call(app, "/api/premium-reports/technical", SUB, payload), CALL_SECONDS)
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            log.warning("technical refresh did not reach the site backend: %s", type(exc).__name__)
            return None
        if r.status_code == 429 and waited < MEMBER_WAIT_SECONDS:
            waited += prism.RETRY_AFTER_BACKGROUND
            await asyncio.sleep(prism.RETRY_AFTER_BACKGROUND)
            continue
        return r


def _apply(report: Dict[str, Any], card: Optional[Dict[str, Any]], view: Dict[str, Any], at: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The stored report and card with the new technical view; nothing else in them changes."""
    report = {**report, "technicalAssessment": view, "technicalCalculatedAt": at}
    card = dict(card or {})

    def horizon(key: str) -> Dict[str, Any]:
        part = view.get(key) if isinstance(view.get(key), dict) else {}
        return {"score": part.get("score"), "rating": part.get("rating")}
    card.update(st=horizon("shortTerm"), lt=horizon("longTerm"), technicalAt=at, technicalBarDate=view.get("asOf"))
    return report, card


async def refresh_symbol(app, symbol: str, now: datetime, target: Optional[date] = None) -> Tuple[str, str]:
    """Recalculate and store one company's technical view. (outcome, reason). Never raises."""
    store = app.state.store
    try:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT statement, report, card FROM prism_reports WHERE symbol = $1", symbol)
            if not rows:
                return Outcome.SKIPPED, "no_report"
            shares, price = await _shares_cr(conn, symbol, rows)
        try:
            candles = await asyncio.wait_for(supplied_candles(app.state, symbol, now, price), CANDLE_SECONDS)
        except Exception as exc:
            log.warning("technical refresh: candles for %s not fetched: %s", symbol, type(exc).__name__)
            return Outcome.FAILED, "candles_error"
        if not candles or "stock" not in candles:
            return Outcome.FAILED, "no_candles"
        stored_bar = min((bar_date(_json(r["report"]), r["card"] and _json(r["card"])) or "0000-00-00") for r in rows)
        if target is not None and candles["stock"]["candles"][-1][0] <= stored_bar and stored_bar != "0000-00-00":
            await store.redis.set(NONEW_PREFIX + symbol, stored_bar, ex=NONEW_SECONDS)       # Dhan has nothing newer for it: not asked again until tomorrow
            return Outcome.SKIPPED, "no_new_bar"
        r = await _post(app, {"suppliedCandles": candles, "sharesCr": shares, "priority": "background"})
        if r is None or r.status_code != 200:
            code = r.status_code if r is not None else 0
            if r is not None:
                log.warning("technical refresh %s: the site backend answered %s: %s", symbol, code, (prism._upstream_detail(r) or "")[:200])
            return Outcome.FAILED, "unusable_candles" if code == 422 else f"site_backend_{code}"
        try:
            assessment = r.json()["technicalAssessment"]
        except (ValueError, KeyError, TypeError):
            return Outcome.FAILED, "bad_answer"
        view = prism.technical_view(assessment)
        if view is None:
            return Outcome.FAILED, "bad_answer"
        ready = assessment.get("status") == "ready"
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        updated = 0
        async with store.pool.acquire() as conn:
            async with conn.transaction():
                for row in await conn.fetch("SELECT statement, report, card FROM prism_reports WHERE symbol = $1 FOR UPDATE", symbol):
                    report = _json(row["report"])
                    old = report.get("technicalAssessment") if isinstance(report, dict) else None
                    if not ready and isinstance(old, dict) and old.get("status") == "ready":
                        continue                       # an incomplete view never replaces a complete one (it keeps its own date)
                    report, card = _apply(report, _json(row["card"]) if row["card"] is not None else None, view, at)
                    await conn.execute("UPDATE prism_reports SET report = $3::jsonb, card = $4::jsonb WHERE symbol = $1 AND statement = $2",
                                       symbol, row["statement"], json.dumps(report, allow_nan=False), json.dumps(card, allow_nan=False))
                    updated += 1
        if not ready:
            return Outcome.WITHHELD, withheld_reason(assessment)
        return (Outcome.UPDATED, "ok") if updated else (Outcome.SKIPPED, "no_report")
    except Exception as exc:        # one company must never stop the run
        log.warning("technical refresh %s failed: %s", symbol, type(exc).__name__)
        return Outcome.FAILED, f"error_{type(exc).__name__}"


# ------------------------------------------------------------------------------------------------ the run
async def refresh(store, settings, *, limit: int = 2500, max_minutes: float = 45.0, shard: Optional[Tuple[int, int]] = None,
                  symbols: Optional[List[str]] = None, force: bool = False, client=None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Refresh the technical view of every stored report that is behind. Returns the counts (also stored for /api/technicals/status)."""
    app = SimpleNamespace(state=SimpleNamespace(store=store, settings=settings, prism_client=client))
    if not prism.connected(settings):
        return {"status": "skipped", "reason": "not_configured"}
    redis = store.redis
    started, now = time.monotonic(), now or datetime.now(IST)
    expected = expected_session(now)
    out: Dict[str, Any] = {"status": "ok", "expectedSession": expected.isoformat(), "updated": 0, "skipped": 0, "failed": 0, "withheld": 0,
                           "reasons": {}, "paused_for_members": 0}
    try:
        newest = await reference_session(app.state, now)
        if newest is None:
            out.update(status="skipped", reason="dhan_unavailable")
            return await _finish(store, out, started)
        target = min(newest, expected)
        out["targetSession"] = target.isoformat()
        try:
            await redis.set(TARGET_KEY, json.dumps({"expected": expected.isoformat(), "target": target.isoformat(), "at": time.time()}), ex=TARGET_SECONDS)
        except Exception:
            pass
        skip: List[str] = []
        try:
            async for key in redis.scan_iter(match=NONEW_PREFIX + "*", count=200):
                skip.append((key.decode() if isinstance(key, bytes) else key).rsplit(":", 1)[1])
        except Exception:
            skip = []
        todo = prism.in_shard(await pending(store, target, limit, [] if force else skip, force=force, symbols=symbols), shard)
        out["queued"] = len(todo)
        streak = 0
        for symbol in todo:
            if time.monotonic() - started > max_minutes * 60:
                out["status"] = "partial"
                break
            if streak >= FAIL_STREAK:
                out.update(status="partial", stopped="five failures in a row (Dhan or the site backend is not answering)")
                break
            if await prism._members_busy(redis):         # a member is calculating a report: the machine is theirs for now
                out["paused_for_members"] += 1
                await asyncio.sleep(prism.RETRY_AFTER_BACKGROUND)
            outcome, reason = await refresh_symbol(app, symbol, now, target)
            out[outcome] += 1
            if outcome != Outcome.UPDATED:
                out["reasons"][reason] = out["reasons"].get(reason, 0) + 1
            streak = streak + 1 if outcome == Outcome.FAILED and reason in ("no_candles", "candles_error", "site_backend_0", "site_backend_502", "site_backend_503") else 0
            await asyncio.sleep(0.05)
        if out["failed"] and not out["updated"] and out["status"] == "ok":
            out["status"] = "failed"
        elif out["failed"] and out["status"] == "ok":
            out["status"] = "partial"
    finally:
        if client is None and getattr(app.state, "prism_client", None) is not None:
            await app.state.prism_client.aclose()
        if getattr(app.state, "prism_dhan", None) is not None:
            await app.state.prism_dhan.aclose()
    return await _finish(store, out, started)


async def _finish(store, out: Dict[str, Any], started: float) -> Dict[str, Any]:
    out["seconds"] = round(time.monotonic() - started)
    try:
        from .mf import record_run
        await record_run(store, RUN_NAME, out)
    except Exception:
        log.warning("could not record the %s result", RUN_NAME)
    return out


# ------------------------------------------------------------------------------------------------ opening a page
async def current_target(redis, now: Optional[datetime] = None) -> date:
    """The newest completed session the last run found (it knows holidays), when that run was for today's expected session; else the weekday rule."""
    now = now or datetime.now(IST)
    expected = expected_session(now)
    try:
        raw = await redis.get(TARGET_KEY)
        got = json.loads(raw) if raw else None
        if isinstance(got, dict) and got.get("expected") == expected.isoformat():
            return min(date.fromisoformat(got["target"]), expected)
    except Exception:
        pass
    return expected


async def refresh_on_open(app, symbol: str, state: Dict[str, Any]) -> bool:
    """A company page was opened whose stored technical view is behind the newest session: refresh just that company in the background, at most once
    in TRY_SECONDS per company and PAGE_REFRESH_SLOTS at a time, and only when Dhan was not found down. True when a refresh was started."""
    if not state.get("stale") or not prism.connected(app.state.settings):
        return False
    redis = app.state.store.redis
    try:
        earlier = await redis.get(TRY_PREFIX + symbol)
        if earlier:                                      # started lately: still "refreshing" for a couple of minutes (the page asks again), never started twice
            return time.time() - float(earlier) < REFRESHING_SECONDS
        if len(_page_tasks) >= PAGE_REFRESH_SLOTS or await is_down(redis) or await redis.exists(NONEW_PREFIX + symbol):
            return False
        if not await redis.set(TRY_PREFIX + symbol, str(time.time()), nx=True, ex=TRY_SECONDS):
            return False
    except Exception:
        return False

    async def run() -> None:
        try:
            now = datetime.now(IST)
            await refresh_symbol(app, symbol, now, await current_target(redis, now))
        finally:
            _page_tasks.discard(asyncio.current_task())    # type: ignore[arg-type]

    task = asyncio.get_running_loop().create_task(run())
    _page_tasks.add(task)
    return True


# ------------------------------------------------------------------------------------------------ the public status
async def status_report(store, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Read-only, public, no symbols or scores: what a browser needs to see whether the technical views are current."""
    from .mf import _meta
    now = now or datetime.now(IST)
    today = now.astimezone(IST).date()
    expected = expected_session(now)
    async with store.pool.acquire() as conn:
        last = await _meta(conn, "run:" + RUN_NAME)
        rows = await conn.fetch(
            "SELECT symbol, min(COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}')) AS bar, "
            "max(COALESCE(card->>'technicalAt', report->>'technicalCalculatedAt')) AS at FROM prism_reports GROUP BY symbol")
    bars = sorted(r["bar"] for r in rows if r["bar"])
    ages = sorted((today - date.fromisoformat(b)).days for b in bars)
    target = await current_target(store.redis, now)
    behind = sum(1 for b in bars if b < target.isoformat())
    by_date: Dict[str, int] = {}
    for b in bars:
        by_date[b] = by_date.get(b, 0) + 1
    calculated = sorted(r["at"] for r in rows if r["at"])
    skipped = None
    try:
        raw = await store.redis.get("wake:note:technicals")
        skipped = json.loads(raw) if raw else None
    except Exception:
        skipped = None
    return {
        "todayIST": today.isoformat(), "expectedSession": expected.isoformat(), "newestSessionFound": target.isoformat(),
        "companiesWithReport": len(rows), "withTechnicalView": len(bars), "withoutTechnicalView": len(rows) - len(bars),
        "newestBarDate": bars[-1] if bars else None, "oldestBarDate": bars[0] if bars else None,
        "medianAgeDays": statistics.median(ages) if ages else None, "maxAgeDays": ages[-1] if ages else None,
        "behindNewestSession": behind, "upToDate": len(bars) - behind,
        "barDates": dict(sorted(by_date.items(), reverse=True)[:8]),
        "newestCalculatedAt": calculated[-1] if calculated else None, "oldestCalculatedAt": calculated[0] if calculated else None,
        "lastRun": last, "lastSkipped": skipped,
        "howToRead": "newestBarDate should equal newestSessionFound by about 19:30 IST on a trading day, and behindNewestSession should be small "
                     "(companies Dhan has no candles for). lastRun shows the job's counts: updated, skipped, failed, withheld, with reasons.",
    }


@router.get("/status")
async def technicals_status(request: Request) -> JSONResponse:
    try:
        body = await status_report(request.app.state.store)
    except Exception as exc:
        log.warning("technicals status not read: %s", type(exc).__name__)
        return JSONResponse({"status": "unavailable"}, status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=60"})
