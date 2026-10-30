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
import re
import time
import weakref
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .dhan import IST, DhanClient, DhanError, security_map
from .indices import confirm

log = logging.getLogger("finlit.prism.candles")

PROVIDER = "Dhan"
INDEX_CODES = ("NIF50", "NIFMID100", "NIFSMA100", "NIF500")     # the site's benchmarks; ids come from indices.DHAN_INDEX, checked against dhan_indices
HISTORY_DAYS = 365 * 6 + 20          # six years, as the model's FinEdge history; the long relative-strength rule needs 505 aligned sessions
STOCK_MIN, INDEX_MIN, MAX_AGE_DAYS, MAX_ROWS = 252, 505, 10, 2000
CALL_GAP = 0.34                      # about 3 data calls a second, paced in THIS process only; Dhan's limit is per account and the quote jobs share it (DhanClient.daily does not pace)
RANGE_TOLERANCE = 0.0005             # mirrors technical_series.RANGE_TOLERANCE in the site backend: an open/close this fraction outside [low, high] is rounding, not a bad candle
MAX_DAILY_MOVE = 0.40                # a close more than 40% from the previous close is an unadjusted split or bad data: the series is not sent
MAX_QUOTE_GAP = 0.15                 # the stock's last close more than 15% from the stored quote price: not sent
DOWN_KEY = "prism:candles:down"      # set for DOWN_SECONDS after Dhan failed outright, so an outage does not add CANDLE_SECONDS to every report
DOWN_SECONDS = 300
DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
CACHE_KEY = "prism:candles:idx:"     # + index code
CACHE_SECONDS = 3 * 24 * 3600
RECHECK_SECONDS = 1800               # a cached index lacking the stock's newest session is not asked again for this long (Dhan may not have it yet)
_pace_locks: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()   # one lock per event loop (a module-level Lock fails across loops)
_last_call = 0.0
_down_until = 0.0                    # in-process fallback when Redis cannot hold DOWN_KEY


def _pace_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _pace_locks.get(loop)
    if lock is None:
        lock = _pace_locks[loop] = asyncio.Lock()
    return lock


async def is_down(redis: Any) -> bool:
    try:
        return bool(await redis.get(DOWN_KEY))
    except Exception:
        return time.monotonic() < _down_until


async def mark_down(redis: Any) -> None:
    """Remember for DOWN_SECONDS that Dhan failed outright. Best effort."""
    global _down_until
    try:
        await redis.set(DOWN_KEY, "1", ex=DOWN_SECONDS)
    except Exception:
        _down_until = time.monotonic() + DOWN_SECONDS


def expected_session(now: datetime) -> date:
    """The latest weekday whose session should be complete: today only from 16:00 IST. Holidays are not guessed (no row simply stays absent)."""
    ist = now.astimezone(IST)
    day = ist.date() if (ist.hour, ist.minute) >= (16, 0) else ist.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def collapse_repeats(rows: List[dict]) -> List[dict]:
    """Dhan now and then sends the same day twice: an exact copy, or a second record with the same open, high, low and close but a smaller volume
    (a partial record of the same session; the complete one is never smaller). Such a repeat is one session, not two: keep the record with the
    larger volume. Two records of one day whose prices differ cannot be told apart and are left as they are, so the strict check below still
    refuses the series (nothing is merged by guesswork)."""
    out: List[dict] = []
    for r in rows or []:
        prev = out[-1] if out else None
        if (isinstance(r, dict) and isinstance(prev, dict) and type(r.get("day")) is date and r.get("day") == prev.get("day")
                and all(r.get(k) == prev.get(k) for k in ("open", "high", "low", "close")) and _num(r.get("volume")) and _num(prev.get("volume"))):
            if r["volume"] > prev["volume"]:
                out[-1] = r
            continue
        out.append(r)
    return out


def clean_reason(rows: List[dict], expected: date, minimum: int, quote_price: Optional[float] = None) -> Tuple[Optional[List[list]], str]:
    """Dhan's rows ({"day","open","high","low","close","volume"}) as [date, o, h, l, c, v], or (None, the reason) unless the whole series is
    complete, consistent and plausible. Rows after the last completed session are dropped (today's partial candle)."""
    if not rows or len(rows) > MAX_ROWS:
        return None, "no rows or too many"
    rows = collapse_repeats(rows)
    out: List[list] = []
    previous: Optional[date] = None
    for r in rows:
        day = r.get("day") if isinstance(r, dict) else None
        vals = [r.get(k) for k in ("open", "high", "low", "close", "volume")] if isinstance(r, dict) else []
        if type(day) is not date or not all(_num(v) for v in vals):       # type(): a datetime is not a calendar date
            return None, "a row has no date or a missing/non-finite value"
        o, h, l, c, v = vals
        if min(o, h, l, c) <= 0 or v < 0:
            return None, "a row is inconsistent"
        top, bottom = max(o, c), min(o, c)
        if not l <= bottom <= top <= h:
            slack = RANGE_TOLERANCE * max(h, top)
            if top - h > slack or bottom < l - slack:
                return None, "a row is inconsistent"
            h, l = max(h, top), min(l, bottom)       # rounding noise: the site backend fits it the same way (premium_supplied_candles.check_series)
        if previous is not None and day <= previous:
            return None, "dates are not strictly increasing"
        previous = day
        if day <= expected:
            out.append([day.isoformat(), o, h, l, c, v])
    if len(out) < minimum or not 0 <= (expected - date.fromisoformat(out[-1][0])).days <= MAX_AGE_DAYS:
        return None, "too few sessions or the last session is too old"
    for before, after in zip(out, out[1:]):
        if abs(after[4] / before[4] - 1) > MAX_DAILY_MOVE:
            return None, f"close moves more than {MAX_DAILY_MOVE:.0%} in a day on {after[0]} (unadjusted split or bad data)"
    if _num(quote_price) and quote_price > 0 and abs(out[-1][4] / quote_price - 1) > MAX_QUOTE_GAP:
        return None, f"last close is more than {MAX_QUOTE_GAP:.0%} from the quote price"
    return out, ""


def clean(rows: List[dict], expected: date, minimum: int, quote_price: Optional[float] = None) -> Optional[List[list]]:
    return clean_reason(rows, expected, minimum, quote_price)[0]


def _cache_ok(candles: Any) -> bool:
    """A cached series must still look exactly like one we stored: a corrupt entry is a miss."""
    if not isinstance(candles, list) or not 0 < len(candles) <= MAX_ROWS:
        return False
    for row in candles:
        if not (isinstance(row, list) and len(row) == 6 and isinstance(row[0], str) and DATE_TEXT.fullmatch(row[0]) and all(_num(v) for v in row[1:])):
            return False
    return True


async def _gap() -> None:
    global _last_call
    async with _pace_lock():
        wait = _last_call + CALL_GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def _fetch(client: DhanClient, segment: str, security_id: str, instrument: str, now: datetime, expected: date, minimum: int,
                 quote_price: Optional[float] = None) -> Tuple[Optional[List[list]], bool]:
    """(the clean series or None, whether the call itself failed). A series Dhan answered but that is doubtful is (None, False)."""
    start = now.astimezone(IST).date() - timedelta(days=HISTORY_DAYS)
    end = now.astimezone(IST).date() + timedelta(days=1)          # Dhan's end date is not included
    await _gap()
    try:
        rows = await client.daily(security_id, segment, start, end, instrument)
    except (DhanError, httpx.HTTPError, ValueError, TypeError, OverflowError, OSError) as exc:
        log.warning("prism candles: Dhan %s/%s failed: %s", segment, security_id, type(exc).__name__)
        return None, True
    got, reason = clean_reason(rows, expected, minimum, quote_price)
    if got is None:
        log.warning("prism candles: Dhan %s/%s not used (%d rows): %s", segment, security_id, len(rows or []), reason)
    return got, False


async def _cached(redis: Any, code: str) -> Optional[dict]:
    try:
        raw = await redis.get(CACHE_KEY + code)
        got = json.loads(raw) if raw else None
        if isinstance(got, dict) and isinstance(got.get("expected"), str) and _cache_ok(got.get("candles")):
            float(got.get("fetched") or 0)
            return got
        if got is not None:
            log.warning("prism candles: cached %s is corrupt; fetching again", code)
        return None
    except Exception:
        return None


async def _index(client: DhanClient, redis: Any, code: str, sid: str, now: datetime, expected: date, stock_through: Optional[str]) -> Tuple[Optional[List[list]], bool]:
    held = await _cached(redis, code)
    if held and held.get("expected") == expected.isoformat():
        last = held["candles"][-1][0]
        lacks_stock_session = bool(stock_through) and last < stock_through and time.time() - float(held.get("fetched") or 0) > RECHECK_SECONDS
        if not lacks_stock_session:
            return held["candles"], False
    fresh, failed = await _fetch(client, "IDX_I", sid, "INDEX", now, expected, INDEX_MIN)
    if fresh is None:
        return None, failed    # never serve an older cached series as if it were current
    try:
        await redis.set(CACHE_KEY + code, json.dumps({"expected": expected.isoformat(), "fetched": time.time(), "candles": fresh}), ex=CACHE_SECONDS)
    except Exception:
        pass
    return fresh, False


def dhan_client(state: Any, settings: Any, redis: Any) -> Optional[DhanClient]:
    """One DhanClient per process, kept on the app state (a SimpleNamespace in the nightly worker); None when Dhan is not set up."""
    client = getattr(state, "prism_dhan", None)
    if client is None:
        if not getattr(settings, "dhan_client_id", ""):
            return None
        client = state.prism_dhan = DhanClient(settings, redis)
    return client if client.configured else None


STORED_QUOTE = object()      # "look the quote price up in the stored summary snapshot" (the default); pass a number, or None for no check, to override


async def reference_session(state: Any, now: Optional[datetime] = None) -> Optional[date]:
    """The date of the newest completed session Dhan holds for the Nifty 50 (the market's own calendar, which no weekday rule knows: a holiday
    or a day Dhan has not posted yet gives an earlier date than `expected_session`), or None when Dhan or the index id is unavailable.
    Uses the same cached index series as the reports, and asks Dhan again (at most every RECHECK_SECONDS) when the cache lacks the expected session."""
    client = dhan_client(state, state.settings, getattr(state.store, "redis", None))
    if client is None:
        return None
    redis = getattr(state.store, "redis", None)
    now = now or datetime.now(IST)
    expected = expected_session(now)
    try:
        async with state.store.pool.acquire() as conn:
            ids, _off = confirm(await conn.fetch("SELECT exch, security_id, symbol FROM dhan_indices"))
        if "NIF50" not in ids:
            return None
        rows, _failed = await _index(client, redis, "NIF50", ids["NIF50"], now, expected, expected.isoformat())
    except Exception as exc:
        log.warning("prism candles: the reference session could not be read: %s", type(exc).__name__)
        return None
    return date.fromisoformat(rows[-1][0]) if rows else None


async def supplied_candles(state: Any, symbol: str, now: Optional[datetime] = None, quote_price: Any = STORED_QUOTE) -> Optional[Dict[str, Any]]:
    """The `suppliedCandles` body field for one calculation, or None when there is nothing trustworthy to send.
    `quote_price`: the price the stock's last close is checked against (within MAX_QUOTE_GAP); the default is the stored summary snapshot's."""
    store, settings = state.store, state.settings
    client = dhan_client(state, settings, getattr(store, "redis", None))
    if client is None:
        return None
    redis = getattr(store, "redis", None)
    if await is_down(redis):
        log.warning("prism candles: Dhan failed a moment ago; not asked again for %d seconds", DOWN_SECONDS)
        return None
    now = now or datetime.now(IST)
    expected = expected_session(now)
    out: Dict[str, Any] = {}
    stock_through: Optional[str] = None
    calls = failures = 0
    # The stock and the indices are independent: whatever goes wrong with one (even an unexpected error) never cancels the other.
    try:
        try:
            sec = (await security_map(store, [symbol])).get(symbol)
        except Exception as exc:
            log.warning("prism candles: no security id for %s: %s", symbol, type(exc).__name__)
            sec = None
        if sec:
            calls += 1
            quote = await _quote_price(store, symbol) if quote_price is STORED_QUOTE else quote_price
            rows, failed = await _fetch(client, sec[0], sec[1], "EQUITY", now, expected, STOCK_MIN, quote)
            failures += failed
            if rows:
                out["stock"] = {"provider": PROVIDER, "candles": rows}
                stock_through = rows[-1][0]
    except Exception as exc:
        log.warning("prism candles: the stock series for %s failed: %s", symbol, type(exc).__name__)
    try:
        try:
            async with store.pool.acquire() as conn:
                ids, _off = confirm(await conn.fetch("SELECT exch, security_id, symbol FROM dhan_indices"))
        except Exception as exc:
            log.warning("prism candles: Dhan index ids unavailable: %s", type(exc).__name__)
            ids = {}
        indices: Dict[str, Any] = {}
        for code in INDEX_CODES:
            if code in ids:
                calls += 1
                try:
                    rows, failed = await _index(client, redis, code, ids[code], now, expected, stock_through)
                except Exception as exc:
                    log.warning("prism candles: index %s failed: %s", code, type(exc).__name__)
                    rows, failed = None, True
                failures += failed
                if rows:
                    indices[code] = {"provider": PROVIDER, "candles": rows}
        if indices:
            out["indices"] = indices
    except Exception as exc:
        log.warning("prism candles: the index series failed: %s", type(exc).__name__)
    if not out and calls and failures == calls:      # every call failed outright and nothing is cached: Dhan is down
        await mark_down(redis)
    return out or None


async def _quote_price(store: Any, symbol: str) -> Optional[float]:
    """The stored quote price of the company (summary snapshot), or None: then the last-close check is simply not made."""
    for statement in ("consolidated", "standalone"):
        try:
            got = await store.get_section(symbol, statement, "summary")
            price = ((json.loads(got[0]) or {}).get("quote") or {}).get("price") if got else None
        except Exception:
            continue
        if _num(price) and price > 0:
            return float(price)
    return None
