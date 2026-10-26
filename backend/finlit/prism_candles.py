"""Daily candles for the Prism technical (ST/LT) assessment, fetched from Dhan and handed to the site backend.

The site backend (a separate codebase) has no Dhan token. For each calculation this module fetches, through the same DhanClient the
rest of FinLit uses (token renewed daily from DHAN_PIN + DHAN_TOTP_SECRET), split/bonus-adjusted daily open/high/low/close/volume for

  * the stock                         one /charts/historical call per calculation, and
  * the four benchmark indices        NIF50, NIFMID100, NIFSMA100, NIF500, shared by every company: kept in Redis and fetched again only
                                      when a newer session has completed (or the stock has a session the cached index lacks),

and `Prism` sends them in the body of POST /api/premium-reports as `suppliedCandles`:

    {"stock":   {"provider": "Dhan", "candles": [[ "YYYY-MM-DD", open, high, low, close, volume ], ...]},
     "indices": {"NIF50": {"provider": "Dhan", "candles": [...]}, ...}}

The site backend (site-api/backend/premium_supplied_candles.py) validates them again and uses a supplied series first, otherwise
FinEdge/Upstox exactly as before. Here, anything doubtful means that series is NOT sent: Dhan not configured, no security id, a failed
call, a missing/zero/inconsistent value, unsorted or repeated dates, too few sessions, or a last session more than 10 days old. Nothing is
filled, guessed or taken from another source. The unfinished session of the day is never sent (the last completed session is today's only
after 16:00 IST on a weekday; the site backend's own 16:00 rule still applies). Only exception names are logged, never request headers or tokens.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from .dhan import IST, DhanClient, DhanError, security_map
from .indices import confirm

log = logging.getLogger("finlit.prism.candles")

PROVIDER = "Dhan"
INDEX_CODES = ("NIF50", "NIFMID100", "NIFSMA100", "NIF500")     # the site's benchmarks; ids come from indices.DHAN_INDEX, checked against dhan_indices
HISTORY_DAYS = 365 * 6 + 20          # six years, as the model's FinEdge history; the long relative-strength rule needs 505 aligned sessions
STOCK_MIN, INDEX_MIN, MAX_AGE_DAYS, MAX_ROWS = 252, 505, 10, 2000
CALL_GAP = 0.34                      # about 3 data calls a second (Dhan allows 5; etf.py paces the same way); the quote jobs share the account
CACHE_KEY = "prism:candles:idx:"     # + index code
CACHE_SECONDS = 3 * 24 * 3600
RECHECK_SECONDS = 1800               # a cached index lacking the stock's newest session is not asked again for this long (Dhan may not have it yet)
_pace_lock = asyncio.Lock()
_last_call = 0.0


def expected_session(now: datetime) -> date:
    """The latest weekday whose session should be complete: today only from 16:00 IST. Holidays are not guessed (no row simply stays absent)."""
    ist = now.astimezone(IST)
    day = ist.date() if (ist.hour, ist.minute) >= (16, 0) else ist.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean(rows: List[dict], expected: date, minimum: int) -> Optional[List[list]]:
    """Dhan's rows ({"day","open","high","low","close","volume"}) as [date, o, h, l, c, v], or None unless the whole series is complete and
    consistent. Rows after the last completed session are dropped (today's partial candle)."""
    if not rows or len(rows) > MAX_ROWS:
        return None
    out: List[list] = []
    previous: Optional[date] = None
    for r in rows:
        day = r.get("day") if isinstance(r, dict) else None
        vals = [r.get(k) for k in ("open", "high", "low", "close", "volume")] if isinstance(r, dict) else []
        if not isinstance(day, date) or not all(_num(v) for v in vals):
            return None
        o, h, l, c, v = vals
        if min(o, h, l, c) <= 0 or v < 0 or not l <= min(o, c) <= max(o, c) <= h:
            return None
        if previous is not None and day <= previous:
            return None
        previous = day
        if day <= expected:
            out.append([day.isoformat(), o, h, l, c, v])
    if len(out) < minimum or not 0 <= (expected - date.fromisoformat(out[-1][0])).days <= MAX_AGE_DAYS:
        return None
    return out


async def _gap() -> None:
    global _last_call
    async with _pace_lock:
        wait = _last_call + CALL_GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def _fetch(client: DhanClient, segment: str, security_id: str, instrument: str, now: datetime, expected: date, minimum: int) -> Optional[List[list]]:
    start = now.astimezone(IST).date() - timedelta(days=HISTORY_DAYS)
    end = now.astimezone(IST).date() + timedelta(days=1)          # Dhan's end date is not included
    await _gap()
    try:
        rows = await client.daily(security_id, segment, start, end, instrument)
    except (DhanError, httpx.HTTPError, ValueError, TypeError) as exc:
        log.warning("prism candles: Dhan %s/%s failed: %s", segment, security_id, type(exc).__name__)
        return None
    got = clean(rows, expected, minimum)
    if got is None:
        log.warning("prism candles: Dhan %s/%s gave %d rows that are not a complete series", segment, security_id, len(rows or []))
    return got


async def _cached(redis: Any, code: str) -> Optional[dict]:
    try:
        raw = await redis.get(CACHE_KEY + code)
        got = json.loads(raw) if raw else None
        return got if isinstance(got, dict) and isinstance(got.get("candles"), list) and got["candles"] else None
    except Exception:
        return None


async def _index(client: DhanClient, redis: Any, code: str, sid: str, now: datetime, expected: date, stock_through: Optional[str]) -> Optional[List[list]]:
    held = await _cached(redis, code)
    if held and held.get("expected") == expected.isoformat():
        last = held["candles"][-1][0]
        lacks_stock_session = bool(stock_through) and last < stock_through and time.time() - float(held.get("fetched") or 0) > RECHECK_SECONDS
        if not lacks_stock_session:
            return held["candles"]
    fresh = await _fetch(client, "IDX_I", sid, "INDEX", now, expected, INDEX_MIN)
    if fresh is None:
        return None            # never serve an older cached series as if it were current
    try:
        await redis.set(CACHE_KEY + code, json.dumps({"expected": expected.isoformat(), "fetched": time.time(), "candles": fresh}), ex=CACHE_SECONDS)
    except Exception:
        pass
    return fresh


def dhan_client(state: Any, settings: Any, redis: Any) -> Optional[DhanClient]:
    """One DhanClient per process, kept on the app state (a SimpleNamespace in the nightly worker); None when Dhan is not set up."""
    client = getattr(state, "prism_dhan", None)
    if client is None:
        if not getattr(settings, "dhan_client_id", ""):
            return None
        client = state.prism_dhan = DhanClient(settings, redis)
    return client if client.configured else None


async def supplied_candles(state: Any, symbol: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The `suppliedCandles` body field for one calculation, or None when there is nothing trustworthy to send."""
    store, settings = state.store, state.settings
    client = dhan_client(state, settings, getattr(store, "redis", None))
    if client is None:
        return None
    now = now or datetime.now(IST)
    expected = expected_session(now)
    out: Dict[str, Any] = {}
    stock_through: Optional[str] = None
    try:
        sec = (await security_map(store, [symbol])).get(symbol)
    except Exception as exc:
        log.warning("prism candles: no security id for %s: %s", symbol, type(exc).__name__)
        sec = None
    if sec:
        rows = await _fetch(client, sec[0], sec[1], "EQUITY", now, expected, STOCK_MIN)
        if rows:
            out["stock"] = {"provider": PROVIDER, "candles": rows}
            stock_through = rows[-1][0]
    try:
        async with store.pool.acquire() as conn:
            ids, _off = confirm(await conn.fetch("SELECT exch, security_id, symbol FROM dhan_indices"))
    except Exception as exc:
        log.warning("prism candles: Dhan index ids unavailable: %s", type(exc).__name__)
        ids = {}
    indices: Dict[str, Any] = {}
    for code in INDEX_CODES:
        if code in ids:
            rows = await _index(client, store.redis, code, ids[code], now, expected, stock_through)
            if rows:
                indices[code] = {"provider": PROVIDER, "candles": rows}
    if indices:
        out["indices"] = indices
    return out or None
