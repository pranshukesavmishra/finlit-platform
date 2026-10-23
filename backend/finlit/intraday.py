"""Intraday price charts on stock pages (1D, 5D, 1M), from Dhan's minute candles.

    GET /api/stocks/{symbol}/intraday?range=1D|5D|1M

Each range is one Dhan call per company, shared by every visitor through Redis:
  * while trades can still arrive (weekdays 09:00 to 16:00 Indian time: pre-open, the session and the closing session) the answer is kept
    for 60 seconds; outside those hours it is kept until 09:00 on the next weekday, since nothing can change before then;
  * a lock lets only one request ask Dhan when the copy has expired; the others wait a moment for its answer;
  * every call takes a slot from a counter shared by all processes (2 a second, 90,000 a day), inside Dhan's Data API limits of
    5 a second and 100,000 a day, leaving the rest for the nightly ETF history;
  * when Dhan does not answer, or the day's allowance is used, the last good copy is shown (at most 7 days old), marked stale, with the
    time it was taken.

1D is the latest session in the data, so on weekends, holidays and before the open it is the last session, with its date. A company
with no trade in that window answers `no_data`; a company Dhan does not list answers 404 `not_available`.

Plans: 1D for everyone signed in, 5D and 1M for Silver and Gold (the showcase company is open to all, as everywhere on the site).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time as _time
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

import orjson
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from .auth.entitlements import has
from .auth.service import current
from .background import etag_matches
from .dhan import IST, DhanClient, DhanError, security_map

log = logging.getLogger("finlit.intraday")
router = APIRouter()

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
SOURCE = "Dhan"
# interval: minutes per candle. sessions: how many of the latest sessions are shown, or days: calendar days back from the latest session
# (the daily chart's 1M uses the same 31 days). lookback: calendar days asked of Dhan, enough to reach that many sessions over holidays.
RANGES: Dict[str, Dict[str, int]] = {
    "1D": {"interval": 1, "sessions": 1, "lookback": 10},
    "5D": {"interval": 5, "sessions": 5, "lookback": 14},
    "1M": {"interval": 60, "days": 31, "lookback": 45},
}
TIER = {"1D": "basic", "5D": "silver", "1M": "silver"}
LIVE_FROM, LIVE_TO = time(9, 0), time(16, 0)            # trades can still arrive: pre-open (09:00) to the end of the closing session (16:00)
OPEN, CLOSE = time(9, 15), time(15, 30)                 # the continuous session
LIVE_TTL = 60
KEEP = 7 * 24 * 3600                                    # the last good copy, shown when Dhan does not answer
FAIL_TTL = 30                                           # after a failed call, Dhan is not asked again for this long
NOT_LISTED_TTL = 3600                                   # "Dhan does not list this company": the instrument file is reloaded once a day
PER_SECOND = 2
DAILY_CAP = 90_000
NO_STORE = {"Cache-Control": "no-store"}
CACHE = "private, no-cache"


def _now() -> datetime:
    return datetime.now(IST)


def phase(now: datetime) -> str:
    """"open" (weekdays 09:15 to 15:30), "pre_open" (weekdays 09:00 to 09:15) or "closed". By the clock: exchange holidays are not known
    here, which is why the chart always shows the latest session in the data and its date."""
    t = now.astimezone(IST)
    if t.weekday() >= 5:
        return "closed"
    if OPEN <= t.time() < CLOSE:
        return "open"
    if LIVE_FROM <= t.time() < OPEN:
        return "pre_open"
    return "closed"


def ttl(now: datetime) -> int:
    """Seconds a fresh answer is kept: 60 while trades can arrive, else until 09:00 on the next weekday."""
    t = now.astimezone(IST)
    if t.weekday() < 5 and LIVE_FROM <= t.time() < LIVE_TO:
        return LIVE_TTL
    day = t.date() if t.time() < LIVE_FROM else t.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    nxt = datetime.combine(day, LIVE_FROM, tzinfo=IST)
    return max(LIVE_TTL, int((nxt - t).total_seconds()))


def shape(symbol: str, rng: str, segment: str, candles: List[dict], fetched: datetime) -> dict:
    """The stored answer: the range's sessions cut from the candles (oldest first), with the source and the time Dhan was asked."""
    spec = RANGES[rng]
    base = {"symbol": symbol, "range": rng, "interval": spec["interval"], "exchange": "NSE" if segment == "NSE_EQ" else "BSE",
            "source": SOURCE, "asOf": fetched.astimezone(IST).isoformat(timespec="seconds")}
    days = sorted({c["at"].date() for c in candles})
    if not days:
        return {**base, "status": "no_data", "available": False, "session": None, "sessions": [], "lastBarAt": None,
                "detail": f"No trades in the last {spec['lookback']} days: the stock may be suspended or not traded."}
    last = days[-1]
    keep = days[-spec["sessions"]:] if "sessions" in spec else [d for d in days if d >= last - timedelta(days=spec["days"])]
    wanted = set(keep)
    rows = [c for c in candles if c["at"].date() in wanted]
    return {**base, "status": "ok", "available": True, "session": last.isoformat(), "sessions": [d.isoformat() for d in keep],
            "lastBarAt": rows[-1]["at"].isoformat(),
            "series": {"t": [c["at"].isoformat() for c in rows], "o": [c["open"] for c in rows], "h": [c["high"] for c in rows],
                       "l": [c["low"] for c in rows], "c": [c["close"] for c in rows], "v": [c["volume"] for c in rows]}}


def window(rng: str, now: datetime) -> Tuple[datetime, datetime]:
    """What is asked of Dhan: from midnight `lookback` days ago to now (Indian time, whole seconds)."""
    t = now.astimezone(IST).replace(microsecond=0)
    start = datetime.combine(t.date() - timedelta(days=RANGES[rng]["lookback"]), time(0, 0), tzinfo=IST)
    return start, t


async def slot(redis, now: Optional[float] = None) -> Optional[str]:
    """None when a Dhan data call may be made now, else why not ("busy" or "budget"). The counters are shared by every process through
    Redis; a call waits up to about two seconds for a free slot in a second. Without Redis no call is made (nothing else would hold the rate)."""
    try:
        for _ in range(10):
            sec = int(now if now is not None else _time.time())
            key = f"dhan:data:sec:{sec}"
            n = await redis.incr(key)
            if n == 1:
                await redis.expire(key, 5)
            if n <= PER_SECOND:
                break
            if now is not None:
                return "busy"
            await asyncio.sleep(max(0.05, sec + 1 - _time.time()))
        else:
            return "busy"
        day = f"dhan:intraday:day:{_now().strftime('%Y%m%d')}"
        used = await redis.incr(day)
        if used == 1:
            await redis.expire(day, 2 * 86400)
        return "budget" if used > DAILY_CAP else None
    except Exception:
        return "busy"


async def _get(redis, key: str) -> Optional[bytes]:
    try:
        return await redis.get(key)
    except Exception:
        return None


async def _set(redis, key: str, value: bytes, ex: int) -> None:
    try:
        await redis.set(key, value, ex=ex)
    except Exception:
        pass


def _hit(raw: bytes) -> Tuple[dict, int, str]:
    body = orjson.loads(raw)
    return (body, 404, "not_available") if body.get("status") == "not_available" else (body, 200, "")


async def load(app, symbol: str, rng: str) -> Tuple[Optional[dict], int, str]:
    """(stored answer or None, HTTP status, why) for one company and range: Redis first, else one Dhan call under a lock."""
    store, settings = app.state.store, app.state.settings
    redis = store.redis
    key, keep, lock, failed = f"intra:{symbol}:{rng}", f"intra:keep:{symbol}:{rng}", f"intra:lock:{symbol}:{rng}", f"intra:fail:{symbol}:{rng}"
    raw = await _get(redis, key)
    if raw:
        return _hit(raw)

    async def stale(why: str, status: int) -> Tuple[Optional[dict], int, str]:
        old = await _get(redis, keep)
        if old:
            return {**orjson.loads(old), "stale": True}, 200, why
        return None, status, why

    if not await store.company(symbol):
        return None, 404, "not_found"
    client = DhanClient(settings, redis)
    try:
        if not client.configured:
            return None, 503, "not_connected"
        if await _get(redis, failed):
            return await stale("source_down", 503)
        ids = await security_map(store, [symbol])
        if symbol not in ids:
            body = {"status": "not_available", "symbol": symbol, "range": rng, "source": SOURCE}
            await _set(redis, key, orjson.dumps(body), NOT_LISTED_TTL)
            return body, 404, "not_available"
        segment, sid = ids[symbol]
        try:
            got = bool(await redis.set(lock, b"1", nx=True, ex=20))
        except Exception:
            return None, 503, "busy"
        if not got:                                        # another request is asking Dhan: wait a moment for its answer
            for _ in range(12):
                await asyncio.sleep(0.25)
                raw = await _get(redis, key)
                if raw:
                    return _hit(raw)
            return await stale("preparing", 202)
        try:
            raw = await _get(redis, key)                   # filled between our miss and the lock
            if raw:
                return _hit(raw)
            why = await slot(redis)
            if why:
                return await stale(why, 503)
            now = _now()
            start, end = window(rng, now)
            try:
                candles = await client.intraday(sid, segment, RANGES[rng]["interval"], start, end)
            except DhanError as e:
                log.warning("intraday %s %s: %s", symbol, rng, e)
                await _set(redis, failed, b"1", FAIL_TTL)
                return await stale("source_down", 503)
            body = shape(symbol, rng, segment, candles, now)
            packed = orjson.dumps(body)
            await _set(redis, key, packed, ttl(now))
            if body["status"] == "ok":
                await _set(redis, keep, packed, KEEP)
            return body, 200, ""
        finally:
            try:
                await redis.delete(lock)
            except Exception:
                pass
    finally:
        await client.aclose()


WHY = {
    "not_found": "No company with this symbol.",
    "not_connected": "Intraday prices are not connected right now.",
    "not_available": "Intraday prices are not available for this company: our intraday source (Dhan) does not list it.",
    "source_down": "The intraday price source did not answer. Please try again shortly.",
    "busy": "Intraday prices are busy right now. Please try again shortly.",
    "budget": "Today's allowance of intraday price requests has been used. Daily charts are unaffected.",
    "preparing": "The intraday chart is being prepared.",
}
STALE_NOTE = {"source_down": "The intraday price source did not answer, so this is the last copy we have.",
              "busy": "Intraday prices are busy right now, so this is the last copy we have.",
              "budget": "Today's allowance of intraday price requests has been used, so this is the last copy we have.",
              "preparing": "This is the last copy we have; a newer one is being prepared."}


@router.get("/api/stocks/{symbol}/intraday")
async def intraday(request: Request, symbol: str, range: str = Query("1D")):
    sym, rng = symbol.strip().upper(), range.strip().upper()
    if not SYMBOL.match(sym):
        return JSONResponse({"status": "invalid_symbol"}, status_code=400, headers=NO_STORE)
    if rng not in RANGES:
        return JSONResponse({"status": "bad_range", "detail": "Range must be one of " + ", ".join(RANGES) + "."}, status_code=400, headers=NO_STORE)
    settings = request.app.state.settings
    if sym not in settings.showcase_symbols:
        who = await current(request)
        if not who.authed:
            return JSONResponse({"status": "auth_required", "detail": "Sign in to see intraday charts.", "plan": "basic"}, status_code=401, headers=NO_STORE)
        tier = TIER[rng]
        if who.role != "admin" and not has(who.plan, tier):
            return JSONResponse({"status": "plan_required", "plan": tier, "detail": f"The {rng} intraday chart is part of the {tier.title()} plan."},
                                status_code=403, headers=NO_STORE)
    body, status, why = await load(request.app, sym, rng)
    if body is None or status != 200:
        out = {"status": why or "error", "symbol": sym, "range": rng, "detail": WHY.get(why, "Intraday prices are unavailable right now.")}
        headers = {**NO_STORE, "Retry-After": "2"} if status in (202, 503) else ({"Cache-Control": CACHE, "Vary": "Cookie"} if status == 404 else NO_STORE)
        return JSONResponse(out, status_code=status, headers=headers)
    now = _now()
    body = {**body, "phase": phase(now), "today": now.date().isoformat()}
    if body.get("stale"):
        body["detail"] = STALE_NOTE.get(why, STALE_NOTE["source_down"])
    payload = orjson.dumps(body)
    etag = '"' + hashlib.sha1(payload).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
    headers = {"ETag": etag, "Cache-Control": NO_STORE["Cache-Control"] if body.get("stale") else CACHE, "Vary": "Cookie"}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=payload, media_type="application/json", headers=headers)
