"""Scores that follow their inputs (docs/REALTIME-SCORES.md): what is recomputed when, by the same code the nightly batch runs.

Three inputs move a company's scores at three different speeds, so each has its own trigger:

  * FILINGS (a new quarter): the results job rebuilds the company and the FinLit IQ is stored in the same write (worker.refresh_results). This module adds the
    other half: it queues the company's FinLit Prism rating (`enqueue_prism`), and the small `scores-live` job (`drain_prism`) recalculates it within minutes,
    one company at a time, through the same function the nightly pre-calculation uses (prism.calculate_and_store).
  * PRICE (the live quote): only the Technical pillar of the FinLit IQ looks at the price (price against its 50 and 200 day averages, RSI). The quote job
    that already patches the price into every stored summary every minute (worker.refresh_quotes) now also works the IQ out again (`apply_live_price`), with the
    very function the full build uses (snapshot.iq_view) on the very inputs it stored (summary.iqInputs, the daily closes). Same inputs, same number: a test
    builds a report at one price, moves the price, and checks the result against a full build at the new price.
  * OPENING A COMPANY: a stored rating that is behind a newer quarter, or that was calculated before the latest completed session, is recalculated in the
    background while the stored one is shown with its date (`on_open_prism`); an IQ report behind a declared result is queued for a rebuild (`report_behind_filing`).

Everything here is bounded (a queue of a few hundred, one calculation at a time, a per-company cool-down, an hourly cap for the on-open recalculations),
idempotent (it first asks whether the company still needs the work), and never raises into a request or a job. There is deliberately no switch that turns
the scheduled work off (the founder's rule); the environment knobs below only size it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import snapshot
from .analytics import indicators
from .normalize.common import parse_date

log = logging.getLogger("finlit.scorelive")

# ------------------------------------------------------------------ knobs (all optional; they size the work, none of them switches scheduled work off)


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def cohort_max() -> int:
    """How many companies one quote tick works the IQ out again for (the rest still get their price): RT_SCORE_COHORT, default 6000 (every stored report)."""
    return max(0, int(_num("RT_SCORE_COHORT", 6000)))


def prism_per_run() -> int:
    """Prism recalculations one `scores-live` run makes at most: RT_PRISM_PER_RUN, default 20 (about 5 to 15 seconds each)."""
    return max(1, int(_num("RT_PRISM_PER_RUN", 20)))


def swr_per_hour() -> int:
    """On-open Prism recalculations the web process starts per hour at most: RT_SWR_PER_HOUR, default 40."""
    return max(0, int(_num("RT_SWR_PER_HOUR", 40)))


QUEUE_MAX = 500                    # companies waiting for a Prism recalculation; a full queue drops new ones (the nightly job still finds them)
PRISM_Q = "rt:prism:q"             # sorted set "SYMBOL|statement" -> time queued
PRISM_TRY = "rt:prism:try:"        # + symbol|statement: a recalculation was made lately (not again for TRY_SECONDS unless a new quarter arrives)
TRY_SECONDS = 90 * 60
QUARTER_SLACK_DAYS = 10            # the two providers may date a quarter a few days apart: the same slack results_candidates uses
SWR_COOLDOWN = 30 * 60
SWR_HOUR = "rt:swr:hour:"
FILING_CHECK = "rt:filing:"        # + symbol|statement: the on-open filing check was made lately
FILING_CHECK_SECONDS = 600


# ------------------------------------------------------------------ the price-driven part of the FinLit IQ
def rescore(summary: Dict[str, Any], inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The FinLit IQ of a stored report worked out again for the price it now holds, exactly as snapshot.build would work it out for that quote.
    `summary` is the stored (quote-patched) summary, `inputs` the stored sections the screener numbers use (store.metric_inputs: price with the daily closes,
    financials, ownership). Returns the new score block, thesis, strengths and watch-outs, or None when the report cannot be recomputed exactly (a report
    built before summary.iqInputs existed, a first-paint partial one, no price history): the nightly build is then what refreshes it. Pure; no I/O.

    The rule it repeats from the build: the technical figures are read from the daily closes, with the live price added as today's provisional bar when the
    quote is dated after the last real bar. The stored closes may already end in such a bar (dataQuality.provisionalLastBar): it is taken off first."""
    basis = summary.get("iqInputs")
    quote = summary.get("quote") or {}
    if not isinstance(basis, dict) or not isinstance(basis.get("metrics"), dict) or (summary.get("meta") or {}).get("partial"):
        return None
    price = quote.get("price")
    daily = (inputs.get("price") or {}).get("daily") or {}
    days, closes = list(daily.get("t") or []), list(daily.get("c") or [])
    if not price or not days or len(days) != len(closes):
        return None
    if (summary.get("dataQuality") or {}).get("provisionalLastBar"):
        days.pop()
        closes.pop()
        if not days:
            return None
    live_day = parse_date(quote.get("asOf"))
    if live_day and live_day.year < 1990:       # the provider sends 0001-01-01 for a quote it has no date for
        live_day = None
    last_day = parse_date(days[-1])
    as_of = live_day or last_day
    if as_of and last_day and as_of > last_day:
        days.append(as_of.isoformat())
        closes.append(price)
    technical = indicators.technical_snapshot(closes)
    metrics: Dict[str, Optional[float]] = dict(basis["metrics"])
    metrics.update({k: technical.get(k) for k in snapshot.PRICE_KEYS})
    holding = ((inputs.get("ownership") or {}).get("latest")) or []
    score, notes, thesis = snapshot.iq_view(metrics, holding, lender=bool(basis.get("lender")), annual=int(basis.get("annual") or 0),
                                            quarterly=int(basis.get("quarterly") or 0), days=len(days))
    block = snapshot.score_block(score)
    # Integrity check: the four pillars that do not look at the price must come out exactly as stored. If they do not, the stored inputs are not the ones
    # the stored score was built from, and nothing is changed.
    stored = {p.get("key"): p.get("score") for p in (summary.get("score") or {}).get("pillars") or []}
    if any(p["score"] != stored.get(p["key"]) for p in block["pillars"] if p["key"] != "technical"):
        return None
    return {"score": block, "thesis": thesis, "strengths": notes["strengths"], "watchouts": notes["watchouts"], "technical": technical}


async def apply_live_price(store: Any, symbol: str, statement: str, summary: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Called by the quote job after it has put the new price into `summary` and before it saves it: works the IQ out again and writes it into `summary`
    (score, thesis, strengths, watch-outs, `score.asOf`). Returns the flat fields for the scores row (screener), or None when nothing could be recomputed.
    Never raises: a problem here must not stop a price from being stored."""
    try:
        inputs = (await store.metric_inputs([(symbol, statement)])).get((symbol, statement))
        if not inputs:
            return None
        got = rescore(summary, inputs)
        if got is None:
            return None
        stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
        before = (summary.get("score") or {}).get("asOf") or {}
        quality = summary.get("dataQuality") or {}
        summary["score"] = {**got["score"], "asOf": snapshot.score_as_of(
            before.get("fundamentalsCheckedAt") or (summary.get("meta") or {}).get("generatedAt"),
            before.get("fundamentalsPeriod") or quality.get("fundamentalsAsOf"),
            (summary.get("quote") or {}).get("asOf"), stamp, True)}
        summary["thesis"], summary["strengths"], summary["watchouts"] = got["thesis"], got["strengths"], got["watchouts"]
        pillar_technical = next((p["score"] for p in got["score"]["pillars"] if p["key"] == "technical"), None)
        return {"symbol": symbol, "statement": statement, "overall": got["score"]["overall"], "band": got["score"]["band"]["key"], "pillar_technical": pillar_technical}
    except Exception:
        log.exception("live score for %s not worked out", symbol)
        return None


# ------------------------------------------------------------------ filings: the Prism rating follows a new quarter
def _ymd(value: Any) -> Optional[date]:
    try:
        text = str(int(float(value)))
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except (TypeError, ValueError):
        return None


def stale_reason(prism_generated: Optional[datetime], prism_quarter: Any, iq_quarter: Any, model_stale: bool, now: Optional[datetime] = None) -> Optional[Tuple[str, str]]:
    """Why a stored Prism rating needs recalculating, as (kind, plain words), or None when it is current. Pure.
      filing   the FinLit IQ holds a newer quarter than the rating was calculated from
      session  a trading session has been completed since the rating was calculated (its price-based parts are older than the last close)
      model    calculated by an older version of the model
      none     no rating at all"""
    now = now or datetime.now(timezone.utc)
    if prism_generated is None:
        return "none", "no rating has been calculated yet"
    if model_stale:
        return "model", "calculated by an older version of the model"
    have, want = parse_date(prism_quarter), _ymd(iq_quarter)
    if have and want and have < want - timedelta(days=QUARTER_SLACK_DAYS):
        return "filing", f"a newer quarter ({want.isoformat()}) has been filed since this rating's latest quarter ({have.isoformat()})"
    from .jobs.schedule import latest_ready
    ready = latest_ready(now)[1]
    gen = prism_generated if prism_generated.tzinfo else prism_generated.replace(tzinfo=timezone.utc)
    if gen < ready:
        return "session", "calculated before the latest completed trading session"
    return None


async def prism_need(store: Any, symbol: str, statement: str = "consolidated", now: Optional[datetime] = None) -> Optional[Tuple[str, str]]:
    """stale_reason() for one company, from what is stored. None when current (or when there is no FinLit IQ to compare with and a rating exists)."""
    from . import prism
    row = await store.pool.fetchrow(
        "SELECT p.generated_at, p.report, (SELECT s.metrics->>'q_period_end' FROM scores s WHERE s.symbol = $1 AND s.statement = $2 AND s.model = 'v1') AS iq "
        "FROM (SELECT 1) x LEFT JOIN prism_reports p ON p.symbol = $1 AND p.statement = $2", symbol, statement)
    if row is None:
        return None
    report = row["report"]
    pq = None
    if report is not None:
        import json as _json
        try:
            pq = (_json.loads(report) if isinstance(report, (str, bytes)) else report).get("inputMeta", {}).get("quarterlyAsOf")
        except (ValueError, AttributeError):
            pq = None
    return stale_reason(row["generated_at"], pq, row["iq"], bool(report is not None and (prism.stale_model(report) or prism.stale_classification(report))), now)


async def enqueue_prism(store: Any, symbol: str, statement: str = "consolidated") -> bool:
    """Queue a company for a Prism recalculation (its results have just been stored). Bounded and de-duplicated; never raises. True when it was added."""
    try:
        if await store.redis.zcard(PRISM_Q) >= QUEUE_MAX:
            return False
        member = f"{symbol.upper()}|{statement}"
        await store.redis.delete(PRISM_TRY + member)           # a new quarter always earns a fresh try
        return bool(await store.redis.zadd(PRISM_Q, {member: time.time()}, nx=True))
    except Exception:
        log.warning("prism recalculation of %s not queued", symbol)
        return False


async def queue_depth(redis: Any) -> int:
    try:
        return int(await redis.zcard(PRISM_Q))
    except Exception:
        return 0


async def drain_prism(store: Any, settings: Any, *, max_n: Optional[int] = None, max_minutes: float = 12.0, client: Any = None,
                      stop: Any = None, clock=time.monotonic) -> Dict[str, Any]:
    """The `scores-live` job: recalculate the Prism rating of the companies whose results were stored since, oldest first, ONE AT A TIME. Each is first
    asked whether it still needs it (a company already current is dropped: idempotent), and a company is tried at most once per TRY_SECONDS unless
    a new quarter arrives. Stops at the count, the time budget or a stop request; what is left stays queued."""
    from types import SimpleNamespace
    from . import prism
    if not prism.connected(settings):
        return {"status": "skipped", "reason": prism.not_configured_reason(settings) or "not_configured"}
    max_n = max_n or prism_per_run()
    app = SimpleNamespace(state=SimpleNamespace(store=store, settings=settings, prism_client=client))
    redis = store.redis
    started = clock()
    out: Dict[str, Any] = {"status": "ok", "calculated": 0, "alreadyCurrent": 0, "failed": [], "pausedForMembers": 0, "skippedRecently": 0}
    try:
        members = [m.decode() if isinstance(m, bytes) else m for m in await redis.zrange(PRISM_Q, 0, max_n * 3 - 1)]
    except Exception:
        return {**out, "status": "skipped", "reason": "redis_unavailable"}
    streak = 0
    try:
        for member in members:
            if out["calculated"] >= max_n or streak >= 3 or clock() - started > max_minutes * 60 or (stop is not None and stop()):
                out["status"] = "partial"
                break
            symbol, _, statement = member.partition("|")
            statement = statement or "consolidated"
            try:
                need = await prism_need(store, symbol, statement)
                if need is None:
                    out["alreadyCurrent"] += 1
                    await redis.zrem(PRISM_Q, member)
                    continue
                if await redis.exists(PRISM_TRY + member):
                    out["skippedRecently"] += 1
                    await redis.zrem(PRISM_Q, member)
                    continue
                await redis.set(PRISM_TRY + member, need[0], ex=TRY_SECONDS)
                stored, code, waited = await prism.calculate_and_store(app, symbol, statement, "prism:realtime")
                out["pausedForMembers"] += waited
                await redis.zrem(PRISM_Q, member)
                if stored:
                    out["calculated"] += 1
                    streak = 0
                    still = await prism_need(store, symbol, statement)
                    if still is not None and still[0] == "filing":
                        # the rating's own data does not hold the new quarter yet (the model's provider is behind): leave it for the nightly job, do not retry tonight
                        await redis.set(f"prism:pre:fail:{statement}:{symbol}", "quarter-not-available", ex=prism.PRE_FAIL_SECONDS)
                else:
                    out["failed"].append(f"{symbol}:{code}")
                    streak = streak + 1 if code in (0, 429, 502, 503) else 0
            except Exception as exc:     # one company never stops the rest
                log.warning("prism recalculation of %s failed: %s", symbol, type(exc).__name__)
                out["failed"].append(f"{symbol}:error")
                try:
                    await redis.zrem(PRISM_Q, member)
                except Exception:   # nosec B110
                    pass
    finally:
        if client is None and getattr(app.state, "prism_client", None) is not None:
            await app.state.prism_client.aclose()
    out["failed"] = out["failed"][:10]
    out["left"] = await queue_depth(redis)
    out["seconds"] = round(clock() - started)
    try:
        await redis.set("rt:prism:last", __import__("json").dumps({**out, "at": time.time()}), ex=7 * 86400)
    except Exception:   # nosec B110
        pass
    return out


async def has_work(store: Any) -> bool:
    """The supervisor's probe: is a company waiting for a recalculation?"""
    return await queue_depth(store.redis) > 0


# ------------------------------------------------------------------ opening a company
_swr_tasks: set = set()
_swr_slot: Optional[asyncio.Semaphore] = None


def _slot() -> asyncio.Semaphore:
    global _swr_slot
    if _swr_slot is None:
        _swr_slot = asyncio.Semaphore(1)
    return _swr_slot


async def on_open_prism(app: Any, symbol: str, statement: str, row: Any) -> Dict[str, Any]:
    """A stored Prism rating is being opened: say how fresh it is and, when it is behind (a newer quarter, or a completed session since), start a
    recalculation in the background (stale-while-revalidate: the stored rating is shown now, with its date; the page asks again shortly). Bounded: one
    at a time in this process, once per company per SWR_COOLDOWN, at most swr_per_hour() an hour. Never raises. Returns {calculatedAt, stale, reason, kind, refreshing}."""
    info: Dict[str, Any] = {"calculatedAt": row["generated_at"].isoformat() if row is not None else None, "stale": False, "reason": None, "kind": None, "refreshing": False}
    try:
        store = app.state.store
        need = await prism_need(store, symbol, statement)
        if need is None:
            return info
        info.update(stale=True, kind=need[0], reason=need[1])
        from . import prism
        if need[0] == "none" or not prism.connected(app.state.settings):
            return info
        member = f"{symbol}|{statement}"
        lock = f"prism:lock:{symbol}:{statement}"
        redis = store.redis
        if await redis.exists(lock):                 # somebody (a member, the nightly job) is calculating it now
            info["refreshing"] = True
            return info
        if not await redis.set(f"rt:swr:{member}", 1, nx=True, ex=SWR_COOLDOWN):
            return info                              # tried lately; the cool-down is not an error
        hour = SWR_HOUR + datetime.now(timezone.utc).strftime("%Y%m%d%H")
        if await redis.incr(hour) > swr_per_hour():
            await redis.expire(hour, 7200)
            await redis.delete(f"rt:swr:{member}")
            return info
        await redis.expire(hour, 7200)
        token = os.urandom(8).hex()
        if not await redis.set(lock, token, nx=True, ex=prism.LOCK_SECONDS):
            info["refreshing"] = True
            return info
        task = asyncio.create_task(_revalidate(app, symbol, statement, lock, token))
        _swr_tasks.add(task)
        task.add_done_callback(_swr_tasks.discard)
        info["refreshing"] = True
    except Exception as exc:
        log.warning("prism freshness check for %s failed: %s", symbol, type(exc).__name__)
    return info


async def _revalidate(app: Any, symbol: str, statement: str, lock: str, token: str) -> None:
    from . import prism
    try:
        async with _slot():
            await asyncio.wait_for(prism.calculate_and_store(app, symbol, statement, "prism:revalidate"), prism.LOCK_SECONDS)
    except Exception as exc:
        log.warning("prism recalculation on open of %s did not finish: %s", symbol, type(exc).__name__)
    finally:
        await prism._release(app.state.store, lock, token)


async def report_behind_filing(store: Any, symbol: str, statement: str, made: datetime) -> bool:
    """True when a result has been declared for this company that the stored report (built at `made`) may not hold, so the page should queue a rebuild.
    Asked about a company at most once per FILING_CHECK_SECONDS (a Redis stamp), and answered from the declarations the results pages already keep in memory."""
    try:
        if not await store.redis.set(FILING_CHECK + f"{symbol}|{statement}", 1, nx=True, ex=FILING_CHECK_SECONDS):
            return False
        from . import results
        decls = await results.get_declarations(store)
        newest = max((by[symbol].date for by in decls.values() if symbol in by), default=None)
        if newest is None or newest > results.today_ist():
            return False
        made_day = made.astimezone(results.IST).date() if made.tzinfo else made.date()
        if made_day > newest:
            return False                              # built after the declaration day: the results job has had its turn
        row = await store.pool.fetchrow("SELECT metrics->>'q_period_end' AS q FROM scores WHERE symbol = $1 AND statement = $2 AND model = 'v1'", symbol, statement)
        have = _ymd(row["q"]) if row else None
        return have is None or have < results.quarter_end_before(newest) - timedelta(days=QUARTER_SLACK_DAYS)
    except Exception:
        return False


# ------------------------------------------------------------------ what the status page shows
async def facts(store: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Score-lag facts for jobs/freshness.py: how many Prism ratings are behind a quarter the IQ already holds (and for how long), and when the last
    live IQ recompute happened."""
    out: Dict[str, Any] = {"prism_behind": 0, "prism_behind_since": None, "live_newest": None, "queue": await queue_depth(store.redis)}
    try:
        async with store.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) AS n, min(s.updated_at) AS since FROM scores s JOIN prism_reports p ON p.symbol = s.symbol AND p.statement = s.statement "
                "WHERE s.model = 'v1' AND s.metrics->>'q_period_end' ~ '^[0-9]{8}(\\.0+)?$' AND p.report #>> '{inputMeta,quarterlyAsOf}' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' "
                "AND (p.report #>> '{inputMeta,quarterlyAsOf}')::date < to_date(left(s.metrics->>'q_period_end', 8), 'YYYYMMDD') - $1::int "
                "AND s.updated_at < now() - interval '2 hours'", QUARTER_SLACK_DAYS)
            out["prism_behind"], out["prism_behind_since"] = int(row["n"] or 0), row["since"]
            out["live_newest"] = await conn.fetchval("SELECT max(live_at) FROM scores")
    except Exception as exc:
        log.warning("score-lag facts failed: %s", type(exc).__name__)
    return out
