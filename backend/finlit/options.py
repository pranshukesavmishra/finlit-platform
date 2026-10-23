"""Option chain (Gold): every strike of an index or F&O stock for one expiry, from Dhan's option chain API, with the figures traders read
off it (put-call ratio, max pain, OI change and build-up), worked out here from Dhan's numbers and nothing else.

GET /api/options/underlyings              the five index underlyings and every NSE stock with options, with lot sizes
GET /api/options/expiries?u=NIFTY         active expiries of one underlying (Dhan POST /optionchain/expirylist)
GET /api/options/chain?u=NIFTY&expiry=…   the chain for one expiry (Dhan POST /optionchain), with its summary

Dhan allows one unique option-chain request every 3 seconds. Every process of the app takes its turn from one Redis pacer (a slot every
PACE_SECONDS, reserved atomically), so the whole site stays inside that limit however many people look. Each (underlying, expiry) is
kept in Redis: during market hours (IST 09:15-15:30 on weekdays, plus a few minutes for the closing figures) for FRESH_SECONDS, and an
answer taken after the close is kept until the next session opens. Many visitors asking together share one call (a Redis lock), and when
Dhan cannot be asked (busy or failing) the last answer is served with the time it was taken, never an error, when there is one.

Definitions (also shown on the page):
  * OI change          oi − previous_oi for each side of each strike; its percentage only when previous_oi > 0.
  * PCR (OI)           total put OI ÷ total call OI over every strike of the expiry; PCR (volume) the same with the day's volume.
  * Max pain           among the listed strikes, the settlement price S at which the total intrinsic value option buyers would receive
                       at expiry, Σ call OI × max(0, S − K) + Σ put OI × max(0, K − S), is lowest, on today's OI. A tie goes to the lower
                       strike.
  * ATM strike         the listed strike nearest the underlying's last price; exactly midway between two strikes, the higher one.
  * Build-up           per side: price change (last price − previous close) and OI change both known and non-zero.
                       price up + OI up = long build-up; price down + OI up = short build-up;
                       price up + OI down = short covering; price down + OI down = long unwinding. Otherwise no label.
Values Dhan leaves out, or sends as 0 where 0 is impossible (a last price, a previous close, an implied volatility, a quote), are
returned as null and shown as "—", never as 0. A zero open interest or volume is a real zero and is kept.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import orjson
from fastapi import APIRouter, Depends, Query, Request, Response

from .auth.entitlements import has
from .auth.routes import Ctx, fail, secure_ctx
from .background import spawn
from .dhan import IST, DhanClient, DhanError

log = logging.getLogger("finlit.options")
router = APIRouter(prefix="/api/options")

# The index underlyings, with Dhan's ids checked against its instrument file (api-scrip-master-detailed.csv, INSTRUMENT = INDEX rows,
# which Dhan's option chain takes with UnderlyingSeg IDX_I; its own example is NIFTY = 13). The option contracts themselves carry a
# different UNDERLYING_SECURITY_ID (26000 for NIFTY, 1 for SENSEX): that is the exchange's id, not what the option chain call wants.
INDICES: Tuple[dict, ...] = (
    {"key": "NIFTY", "name": "Nifty 50", "segment": "IDX_I", "securityId": 13, "exchange": "NSE"},
    {"key": "BANKNIFTY", "name": "Nifty Bank", "segment": "IDX_I", "securityId": 25, "exchange": "NSE"},
    {"key": "FINNIFTY", "name": "Nifty Financial Services", "segment": "IDX_I", "securityId": 27, "exchange": "NSE"},
    {"key": "MIDCPNIFTY", "name": "Nifty Midcap Select", "segment": "IDX_I", "securityId": 442, "exchange": "NSE"},
    {"key": "SENSEX", "name": "BSE Sensex", "segment": "IDX_I", "securityId": 51, "exchange": "BSE"},
)
INDEX_BY_KEY = {i["key"]: i for i in INDICES}
# A stock's option chain is asked with the stock's own id and segment: Dhan describes UnderlyingSeg as the "exchange & segment of the
# underlying", and a stock option's UNDERLYING_SECURITY_ID in the instrument file is the stock's NSE_EQ id (RELIANCE 2885, checked for all
# 213 stocks with options). Not verified against a live account: if Dhan refuses it, NSE_FNO is tried once and the one that answers is kept.
STOCK_SEGMENTS = ("NSE_EQ", "NSE_FNO")
STOCK_SEG_KEY = "oc:stockseg"
TEST_SYMBOL = re.compile(r"^\d+NSETEST$")      # exchange test scrips in the instrument file: futures only, never shown
UNDERLYING = re.compile(r"^[A-Z0-9&_\-]{1,24}$")
EXPIRY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PACE_KEY = "oc:pace"
PACE_SECONDS = 3.1          # Dhan: one unique option-chain request every 3 seconds; a tenth of a second to spare
MAX_QUEUE_SECONDS = 15.0    # a call that would wait longer than this for its turn is not queued: the last answer (or "busy") instead
FRESH_SECONDS = 45          # a chain is asked again after this long during market hours
STALE_SECONDS = 7 * 24 * 3600
OPEN, CLOSE = dtime(9, 15), dtime(15, 30)
SETTLE = timedelta(minutes=5)   # after the close the closing OI keeps arriving for a few minutes: still "live" until then
WAIT_FOR_PEER = 25.0        # how long a request waits for another one already asking Dhan for the same chain
FAIL_BACKOFF = 30           # after Dhan fails or refuses a chain, it is not asked for that chain again for this long

# A Lua script so the read-and-reserve is one atomic step across every process; Redis's own clock, so the processes need not agree on time.
_PACE_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local gap = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local nxt = tonumber(redis.call('GET', KEYS[1]) or '0')
local slot = math.max(now, nxt)
if slot - now > limit then
  return tostring(-(slot - now))
end
redis.call('SET', KEYS[1], tostring(slot + gap), 'PX', math.ceil((slot + gap - now) * 1000) + 1000)
return tostring(slot - now)
"""


class Busy(Exception):
    """Dhan's option-chain allowance is taken for longer than a visitor should wait."""

    def __init__(self, retry_after: float):
        super().__init__(f"busy for {retry_after:.1f}s")
        self.retry_after = retry_after


# ------------------------------------------------------------------------------------------------------------------ market hours

def _ist(t: Optional[datetime] = None) -> datetime:
    return (t or datetime.now(IST)).astimezone(IST)


def live_window(t: datetime) -> bool:
    """True from 09:15 to 15:35 IST on a weekday (the session and the minutes its closing figures take to arrive). Exchange holidays are
    not known here: on one, the chain is simply asked again every FRESH_SECONDS and comes back unchanged."""
    t = _ist(t)
    start = datetime.combine(t.date(), OPEN, IST)
    end = datetime.combine(t.date(), CLOSE, IST) + SETTLE
    return t.weekday() < 5 and start <= t < end


def market_open(t: Optional[datetime] = None) -> bool:
    t = _ist(t)
    return t.weekday() < 5 and OPEN <= t.timetz().replace(tzinfo=None) < CLOSE


def last_settle(t: datetime) -> datetime:
    """The most recent weekday 15:35 IST at or before t: an answer taken after it holds the session's closing figures."""
    t = _ist(t)
    d = t.date()
    while True:
        mark = datetime.combine(d, CLOSE, IST) + SETTLE
        if d.weekday() < 5 and mark <= t:
            return mark
        d -= timedelta(days=1)


def last_mark(t: datetime) -> datetime:
    """The most recent weekday 09:15 open or 15:35 settle at or before t (the expiry list is asked again after each)."""
    t = _ist(t)
    d = t.date()
    while True:
        if d.weekday() < 5:
            for mark in (datetime.combine(d, CLOSE, IST) + SETTLE, datetime.combine(d, OPEN, IST)):
                if mark <= t:
                    return mark
        d -= timedelta(days=1)


def next_open(t: datetime) -> datetime:
    t = _ist(t)
    d = t.date()
    while True:
        mark = datetime.combine(d, OPEN, IST)
        if d.weekday() < 5 and mark > t:
            return mark
        d += timedelta(days=1)


def chain_fresh(fetched: float, now: Optional[datetime] = None) -> bool:
    """A chain is fresh for FRESH_SECONDS while the market is live; outside it, an answer taken after the last close is kept until the
    next session (nothing changes overnight), and one taken earlier is asked again once."""
    now = _ist(now)
    if live_window(now):
        return now.timestamp() - fetched < FRESH_SECONDS
    return fetched >= last_settle(now).timestamp()


def expiries_fresh(fetched: float, now: Optional[datetime] = None) -> bool:
    return fetched >= last_mark(_ist(now)).timestamp()


# ------------------------------------------------------------------------------------------------------------------ numbers

def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pos(v: Any) -> Optional[float]:
    """A price-like value: Dhan sends 0 for "none" (no trade, no quote, no previous close), and none of these can really be 0."""
    x = _num(v)
    return x if x is not None and x > 0 else None


def _count(v: Any) -> Optional[int]:
    """Open interest or volume: a count, 0 included (0 is a real "none open" or "none traded"). Negative or junk is unknown."""
    x = _num(v)
    return int(round(x)) if x is not None and x >= 0 else None


def _paise(v: float) -> int:
    return int(round(v * 100))


def buildup(price_change: Optional[float], oi_change: Optional[int]) -> Optional[str]:
    """OI build-up from the price change and the OI change of one option (both against the previous session). Zero or unknown: no label."""
    if price_change is None or oi_change is None or price_change == 0 or oi_change == 0:
        return None
    if oi_change > 0:
        return "long_buildup" if price_change > 0 else "short_buildup"
    return "short_covering" if price_change > 0 else "long_unwinding"


BUILDUP_TEXT = {"long_buildup": "Long build-up", "short_buildup": "Short build-up", "short_covering": "Short covering", "long_unwinding": "Long unwinding"}


def side(raw: Any) -> Optional[dict]:
    """One call or put of a strike, as Dhan sends it, with the changes worked out. None when the side is absent."""
    if not isinstance(raw, dict) or not raw:
        return None
    oi, prev_oi = _count(raw.get("oi")), _count(raw.get("previous_oi"))
    ltp, prev = _pos(raw.get("last_price")), _pos(raw.get("previous_close_price"))
    oi_change = oi - prev_oi if oi is not None and prev_oi is not None else None
    oi_pct = round(oi_change / prev_oi * 100, 2) if oi_change is not None and prev_oi else None
    change = (_paise(ltp) - _paise(prev)) / 100 if ltp is not None and prev is not None else None
    change_pct = round((_paise(ltp) - _paise(prev)) / _paise(prev) * 100, 2) if ltp is not None and prev is not None else None
    g = raw.get("greeks") if isinstance(raw.get("greeks"), dict) else {}
    greeks = {k: _num(g.get(k)) for k in ("delta", "gamma", "theta", "vega")}
    if all(v in (None, 0) for v in greeks.values()):   # all four zero: Dhan did not compute them (no trade, or past expiry)
        greeks = {k: None for k in greeks}
    sid = _num(raw.get("security_id"))
    return {
        "securityId": int(sid) if sid is not None and sid > 0 else None,
        "oi": oi, "prevOi": prev_oi, "oiChange": oi_change, "oiChangePct": oi_pct,
        "volume": _count(raw.get("volume")), "prevVolume": _count(raw.get("previous_volume")),
        "iv": _pos(raw.get("implied_volatility")), "ltp": ltp, "prevClose": prev, "change": change, "changePct": change_pct,
        "avgPrice": _pos(raw.get("average_price")),
        "bid": _pos(raw.get("top_bid_price")), "bidQty": _count(raw.get("top_bid_quantity")) or None,
        "ask": _pos(raw.get("top_ask_price")), "askQty": _count(raw.get("top_ask_quantity")) or None,
        **greeks, "buildup": buildup(change, oi_change),
    }


def parse_rows(oc: Any) -> List[dict]:
    """Dhan's {"25650.000000": {"ce": {...}, "pe": {...}}} as rows sorted by strike. Strikes with neither side are left out."""
    rows = []
    for key, val in (oc or {}).items() if isinstance(oc, dict) else []:
        k = _num(key)
        if k is None or k <= 0 or not isinstance(val, dict):
            continue
        ce, pe = side(val.get("ce")), side(val.get("pe"))
        if ce is None and pe is None:
            continue
        rows.append({"strike": round(k, 2), "ce": ce, "pe": pe})
    rows.sort(key=lambda r: r["strike"])
    return rows


def atm_strike(strikes: List[float], spot: Optional[float]) -> Optional[float]:
    """The strike nearest spot; exactly midway between two, the higher (ordinary rounding half up). Compared in paise, so exactly."""
    if not strikes or spot is None or spot <= 0:
        return None
    s = _paise(spot)
    return min(strikes, key=lambda k: (abs(_paise(k) - s), -k))


def max_pain(rows: List[dict]) -> Optional[dict]:
    """The listed strike S at which Σ call OI × max(0, S − K) + Σ put OI × max(0, K − S) (₹ option buyers would receive at expiry, on
    today's OI) is lowest; a tie goes to the lower strike. Worked in paise with whole OI, so the payouts are exact. None without any OI."""
    ks = [(_paise(r["strike"]), (r["ce"] or {}).get("oi") or 0, (r["pe"] or {}).get("oi") or 0) for r in rows]
    if not ks or not any(c or p for _, c, p in ks):
        return None
    best: Optional[Tuple[int, int]] = None
    curve = []
    for s, _, _ in ks:
        pay = sum(c * max(0, s - k) + p * max(0, k - s) for k, c, p in ks)
        curve.append({"strike": s / 100, "payout": pay / 100})
        if best is None or pay < best[1]:
            best = (s, pay)
    return {"strike": best[0] / 100, "payout": best[1] / 100, "curve": curve}


def _total(rows: List[dict], side_key: str, field: str) -> Tuple[Optional[int], int]:
    """Sum of one field over every present side, and how many present sides did not carry it."""
    vals = [r[side_key].get(field) for r in rows if r[side_key] is not None]
    known = [v for v in vals if v is not None]
    return (sum(known) if known else None), len(vals) - len(known)


def ratio(num: Optional[int], den: Optional[int]) -> Optional[float]:
    return round(num / den, 4) if num is not None and den else None


def summarize(data: Any) -> dict:
    """The page's whole answer from Dhan's `data` object: rows, ATM, ITM flags, totals, PCR and max pain."""
    data = data if isinstance(data, dict) else {}
    spot = _pos(data.get("last_price"))
    rows = parse_rows(data.get("oc"))
    atm = atm_strike([r["strike"] for r in rows], spot)
    for r in rows:
        r["atm"] = r["strike"] == atm
        r["ceItm"] = spot is not None and r["strike"] < spot     # a call is in the money below spot, a put above it
        r["peItm"] = spot is not None and r["strike"] > spot
    totals: Dict[str, dict] = {}
    gaps: Dict[str, int] = {}
    for sk in ("ce", "pe"):
        totals[sk] = {"strikes": sum(1 for r in rows if r[sk] is not None)}
        for f in ("oi", "oiChange", "volume", "prevOi"):
            totals[sk][f], gaps[f"{sk}.{f}"] = _total(rows, sk, f)
    notes: List[str] = []
    missing = {k: v for k, v in gaps.items() if v}
    if missing.get("ce.oi") or missing.get("pe.oi"):
        notes.append("Some strikes came without open interest; the totals, PCR and max pain use the strikes that have it.")
    if spot is None:
        notes.append("Dhan did not send the underlying's last price, so the ATM strike and in-the-money shading are not shown.")
    mp = max_pain(rows)
    return {
        "spot": spot, "atm": atm, "rows": rows,
        "summary": {
            "pcrOi": ratio(totals["pe"]["oi"], totals["ce"]["oi"]), "pcrVolume": ratio(totals["pe"]["volume"], totals["ce"]["volume"]),
            "maxPain": {"strike": mp["strike"], "payout": mp["payout"]} if mp else None,
            "totals": totals, "strikes": len(rows), "missing": missing,
        },
        "maxPainCurve": mp["curve"] if mp else [],
        "notes": notes,
    }


# ------------------------------------------------------------------------------------------------------------------ lot sizes (instrument file)

class LotCollector:
    """Gathers the lot size of every option series (underlying × expiry) while dhan.parse_instruments streams the instrument file."""

    def __init__(self) -> None:
        self._lots: Dict[Tuple[str, str, str, str], Counter] = {}
        self._ids: Dict[Tuple[str, str, str, str], str] = {}

    def add(self, r: dict) -> None:
        inst = r.get("INSTRUMENT")
        if inst not in ("OPTIDX", "OPTSTK") or r.get("EXCH_ID") not in ("NSE", "BSE"):
            return
        sym, exp, lot = (r.get("UNDERLYING_SYMBOL") or "").strip(), (r.get("SM_EXPIRY_DATE") or "").strip()[:10], _num(r.get("LOT_SIZE"))
        if not sym or not EXPIRY.match(exp) or not lot or lot <= 0:
            return
        key = (r["EXCH_ID"], inst, sym, exp)
        self._lots.setdefault(key, Counter())[int(lot)] += 1
        self._ids.setdefault(key, (r.get("UNDERLYING_SECURITY_ID") or "").strip())

    def rows(self) -> List[dict]:
        out = []
        for (exch, inst, sym, exp), c in self._lots.items():
            lot, _ = c.most_common(1)[0]
            out.append({"exch": exch, "instrument": inst, "underlying": sym, "underlying_id": self._ids[(exch, inst, sym, exp)],
                        "expiry": date.fromisoformat(exp), "lot_size": lot, "mixed": len(c) > 1})
        return out


async def save_option_lots(store, rows: List[dict]) -> int:
    """Replace the table in one transaction; a short answer (a broken download) keeps what was stored."""
    if len(rows) < 100:
        raise DhanError(f"option series look incomplete ({len(rows)}); kept what was stored")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM dhan_option_lots")
            await conn.executemany(
                "INSERT INTO dhan_option_lots (exch, instrument, underlying, underlying_id, expiry, lot_size, mixed) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                [(r["exch"], r["instrument"], r["underlying"], r["underlying_id"], r["expiry"], r["lot_size"], r["mixed"]) for r in rows])
    return len(rows)


# ------------------------------------------------------------------------------------------------------------------ underlyings

async def stock_underlyings(store) -> List[dict]:
    """Every NSE stock with options: the F&O equities of Dhan's instrument file, kept to those with option series when those are loaded."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, name, security_id, lot_size FROM dhan_instruments WHERE exch = 'NSE' AND fno ORDER BY symbol")
        with_options = {r["underlying"] for r in await conn.fetch("SELECT DISTINCT underlying FROM dhan_option_lots WHERE exch = 'NSE' AND instrument = 'OPTSTK'")}
    return [{"key": r["symbol"], "name": r["name"] or r["symbol"], "securityId": int(r["security_id"]), "lotSize": r["lot_size"]}
            for r in rows if not TEST_SYMBOL.match(r["symbol"]) and (not with_options or r["symbol"] in with_options) and r["security_id"].isdigit()]


async def resolve(store, key: str) -> dict:
    """{"key", "name", "kind", "segment", "securityId", "exchange", "lotSize"} for an index key or an NSE F&O symbol; 404 otherwise."""
    key = (key or "").strip().upper()
    if not UNDERLYING.match(key):
        raise fail(400, "bad_request", "Choose an index or an F&O stock.")
    if key in INDEX_BY_KEY:
        return {**INDEX_BY_KEY[key], "kind": "index", "lotSize": None}
    async with store.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT symbol, name, security_id, lot_size FROM dhan_instruments WHERE exch = 'NSE' AND fno AND symbol = $1", key)
    if r is None or TEST_SYMBOL.match(key) or not r["security_id"].isdigit():
        raise fail(404, "not_found", f"{key} has no options on NSE (or the instrument list is not loaded yet).")
    return {"key": r["symbol"], "name": r["name"] or r["symbol"], "segment": "NSE_EQ", "securityId": int(r["security_id"]), "exchange": "NSE",
            "kind": "stock", "lotSize": r["lot_size"]}


async def lot_for(store, u: dict, expiry: str) -> dict:
    """The lot size of this underlying's options for this expiry, from the instrument file; for a stock, its futures' lot if the series
    are not loaded yet (the same in every case checked); none for an index then (lot sizes change, so none is written into the code)."""
    async with store.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT lot_size, mixed FROM dhan_option_lots WHERE exch = $1 AND underlying = $2 AND expiry = $3 "
                                "AND instrument = $4", u["exchange"], u["key"], date.fromisoformat(expiry), "OPTIDX" if u["kind"] == "index" else "OPTSTK")
    if r:
        return {"lotSize": r["lot_size"], "mixed": r["mixed"], "source": "instrument file, this expiry"}
    if u.get("lotSize"):
        return {"lotSize": u["lotSize"], "mixed": False, "source": "instrument file, the stock's futures"}
    return {"lotSize": None, "mixed": False, "source": None}


# ------------------------------------------------------------------------------------------------------------------ Dhan calls, paced

async def take_turn(redis, gap: Optional[float] = None, limit: Optional[float] = None) -> float:
    """Reserve the next option-chain slot shared by every process; returns how long to wait for it. Busy when it is too far away."""
    gap = PACE_SECONDS if gap is None else gap
    limit = MAX_QUEUE_SECONDS if limit is None else limit
    wait = float(await redis.eval(_PACE_LUA, 1, PACE_KEY, str(gap), str(limit)))
    if wait < 0:
        raise Busy(-wait)
    return wait


def _client(app) -> DhanClient:
    c = getattr(app.state, "options_dhan", None)
    if c is None:
        c = app.state.options_dhan = DhanClient(app.state.settings, app.state.store.redis)
    return c


async def _ask(app, path: str, body: dict) -> Any:
    """One option-chain call in the app's shared turn, attempted once (DhanClient._post retries on its own clock, which would step outside
    the shared pace); a refused token is renewed and the call made once more, in a new turn. Dhan's error code is kept, never the token."""
    c = _client(app)
    renewed = False
    while True:
        wait = await take_turn(app.state.store.redis)
        if wait > 0:
            await asyncio.sleep(wait)
        headers = {"access-token": await c.token(), "client-id": c.settings.dhan_client_id, "Content-Type": "application/json", "Accept": "application/json"}
        try:
            r = await c._http.post(c.settings.dhan_base_url.rstrip("/") + path, json=body, headers=headers)
        except Exception as e:   # httpx errors: the text never carries the URL or headers
            raise DhanError(f"{path}: {type(e).__name__}") from None
        if r.status_code in (401, 403) and not renewed and c.settings.dhan_pin and c.settings.dhan_totp_secret:
            renewed = True
            await c.token(force=True)
            continue
        try:
            answer = r.json()
        except ValueError:
            answer = None
        if r.status_code != 200 or not isinstance(answer, dict) or answer.get("status") not in (None, "success"):
            code = answer.get("errorCode") or answer.get("status") if isinstance(answer, dict) else None
            raise DhanError(f"{path}: HTTP {r.status_code}" + (f" {str(code)[:20]}" if code else ""))
        return answer.get("data")


def clean_expiries(raw: Any, today: date) -> List[str]:
    out = set()
    for e in raw if isinstance(raw, list) else []:
        s = str(e).strip()[:10]
        if EXPIRY.match(s):
            try:
                if date.fromisoformat(s) >= today:
                    out.add(s)
            except ValueError:
                continue
    return sorted(out)


async def _fetch_expiries(app, u: dict) -> dict:
    redis = app.state.store.redis
    segs = [u["segment"]]
    if u["kind"] == "stock":
        try:
            known = await redis.get(STOCK_SEG_KEY)
        except Exception:
            known = None
        first = known.decode() if isinstance(known, bytes) else known
        segs = [first] + [s for s in STOCK_SEGMENTS if s != first] if first in STOCK_SEGMENTS else list(STOCK_SEGMENTS)
    err: Optional[Exception] = None
    for seg in segs:
        try:
            data = await _ask(app, "/optionchain/expirylist", {"UnderlyingScrip": u["securityId"], "UnderlyingSeg": seg})
        except DhanError as e:
            err = e
            continue
        exp = clean_expiries(data, _ist().date())
        if exp:
            if u["kind"] == "stock":
                try:
                    await redis.set(STOCK_SEG_KEY, seg, ex=30 * 24 * 3600)
                except Exception:
                    pass
            return {"segment": seg, "expiries": exp}
    if err is not None:
        raise err
    return {"segment": segs[0], "expiries": []}


async def cached(app, key: str, fresh: Callable[[float], bool], fetch: Callable[[], Awaitable[Any]], wait_if_stale: bool = False) -> Tuple[dict, str]:
    """(entry, state) where entry = {"t": taken at, "body": ...} and state is "fresh", "stale" or "refreshing".

    One request per key asks Dhan at a time (a Redis lock); the others wait for its answer, or, when an older answer exists, get that
    at once while the refresh runs. A failed or refused refresh leaves the older answer in place and it is served as "stale"."""
    redis = app.state.store.redis
    try:
        raw = await redis.get(key)
        entry = json.loads(raw) if raw else None
    except Exception:
        entry = None
    if entry and fresh(entry["t"]):
        return entry, "fresh"
    lock, failed = key + ":lock", key + ":failed"
    try:
        backoff = await redis.get(failed)
    except Exception:
        backoff = None
    if backoff:   # Dhan refused or failed this one moments ago (or the turns were all taken): not asked again yet, whoever is looking
        if entry:
            return entry, "stale"
        if backoff == b"busy":
            raise Busy(PACE_SECONDS)
        raise DhanError("failed moments ago")

    async def refresh() -> dict:
        try:
            try:
                body = await fetch()
            except (DhanError, Busy) as e:
                try:
                    if isinstance(e, Busy):
                        await redis.set(failed, b"busy", ex=max(1, math.ceil(e.retry_after)))
                    else:
                        await redis.set(failed, b"error", ex=FAIL_BACKOFF)
                except Exception:
                    pass
                raise
            got = {"t": time.time(), "body": body}
            try:
                await redis.set(key, orjson.dumps(got), ex=STALE_SECONDS)
            except Exception:
                pass
            return got
        finally:   # only after the answer is stored, so a request waiting on the lock finds it
            try:
                await redis.delete(lock)
            except Exception:
                pass

    try:
        mine = bool(await redis.set(lock, b"1", nx=True, ex=40))
    except Exception:
        mine = True
    if entry and not wait_if_stale:
        if mine:
            spawn(refresh())
        return entry, "refreshing"
    if mine:
        try:
            return await refresh(), "fresh"
        except (DhanError, Busy):
            if entry:
                return entry, "stale"
            raise
    since = entry["t"] if entry else 0.0
    deadline = time.monotonic() + WAIT_FOR_PEER
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        try:
            raw = await redis.get(key)
            cur = json.loads(raw) if raw else None
            if cur and cur["t"] > since:
                return cur, "fresh"
            if not await redis.exists(lock):
                break
        except Exception:
            break
    if entry:
        return entry, "stale"
    raise Busy(PACE_SECONDS)


# ------------------------------------------------------------------------------------------------------------------ routes

async def gold_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "gold"):
        raise fail(403, "plan_required", "The option chain is part of the Gold plan.", plan="gold")
    return ctx


def _json(body: Any, status: int = 200, headers: Optional[Dict[str, str]] = None) -> Response:
    return Response(content=orjson.dumps(body), status_code=status, media_type="application/json",
                    headers={"Cache-Control": "private, no-store", "Vary": "Cookie", **(headers or {})})


def _connected(app) -> None:
    if not _client(app).configured:
        raise fail(503, "not_connected", "The option chain is not connected to its market-data provider yet.")


def _when(t: float) -> str:
    return datetime.fromtimestamp(t, IST).isoformat(timespec="seconds")


def _public(u: dict) -> dict:
    return {k: u[k] for k in ("key", "name", "kind", "segment", "securityId", "exchange")}


async def _expiries(app, u: dict) -> Tuple[dict, str]:
    return await cached(app, f"oc:exp:{u['key']}", expiries_fresh, lambda: _fetch_expiries(app, u), wait_if_stale=True)


def _busy(e: Busy) -> Response:
    secs = max(1, math.ceil(e.retry_after))
    return _json({"status": "busy", "detail": "Many people are reading option chains right now. This one is next; please try again in a few seconds.",
                  "retryAfter": secs}, 503, {"Retry-After": str(secs)})


@router.get("/underlyings")
async def underlyings(request: Request, _ctx: Ctx = Depends(gold_ctx)):
    stocks = await stock_underlyings(request.app.state.store)
    return _json({"indices": [{**_public({**i, "kind": "index"})} for i in INDICES], "stocks": stocks,
                  "connected": _client(request.app).configured})


@router.get("/expiries")
async def expiries(request: Request, u: str = Query(..., max_length=24), _ctx: Ctx = Depends(gold_ctx)):
    app = request.app
    und = await resolve(app.state.store, u)
    _connected(app)
    try:
        entry, state = await _expiries(app, und)
    except Busy as e:
        return _busy(e)
    except DhanError as e:
        log.warning("option expiries for %s failed: %s", und["key"], e)
        raise fail(502, "provider_unavailable", "Dhan did not answer for this underlying's expiries. Please try again in a moment.")
    today = _ist().date()
    exp = [e for e in entry["body"]["expiries"] if date.fromisoformat(e) >= today]
    return _json({"underlying": {**_public(und), "segment": entry["body"]["segment"]}, "expiries": exp, "asOf": _when(entry["t"]), "state": state})


@router.get("/chain")
async def chain(request: Request, u: str = Query(..., max_length=24), expiry: str = Query(..., max_length=10), _ctx: Ctx = Depends(gold_ctx)):
    app = request.app
    store = app.state.store
    if not EXPIRY.match(expiry):
        raise fail(400, "bad_request", "Use an expiry date like 2026-10-27.")
    und = await resolve(store, u)
    _connected(app)
    try:
        exp_entry, _ = await _expiries(app, und)
    except Busy as e:
        return _busy(e)
    except DhanError:
        raise fail(502, "provider_unavailable", "Dhan did not answer for this underlying's expiries. Please try again in a moment.")
    # Only listed, unexpired dates are asked: an arbitrary date would spend one of the app's turns for nothing.
    if expiry not in exp_entry["body"]["expiries"] or date.fromisoformat(expiry) < _ist().date():
        raise fail(404, "no_such_expiry", f"{und['key']} has no active option expiry on {expiry}.")
    seg = exp_entry["body"]["segment"]
    lot = await lot_for(store, und, expiry)

    async def fetch() -> dict:
        return summarize(await _ask(app, "/optionchain", {"UnderlyingScrip": und["securityId"], "UnderlyingSeg": seg, "Expiry": expiry}))

    try:
        entry, state = await cached(app, f"oc:chain:{und['key']}:{expiry}", chain_fresh, fetch)
    except Busy as e:
        return _busy(e)
    except DhanError as e:
        log.warning("option chain %s %s failed: %s", und["key"], expiry, e)
        raise fail(502, "provider_unavailable", "Dhan did not answer for this option chain. Please try again in a moment.")
    now = _ist()
    return _json({
        **entry["body"], "underlying": {**_public(und), "segment": seg}, "expiry": expiry,
        "lotSize": lot["lotSize"], "lotSource": lot["source"], "lotMixed": bool(lot["mixed"]),
        "daysToExpiry": (date.fromisoformat(expiry) - now.date()).days,
        "asOf": _when(entry["t"]), "ageSeconds": max(0, int(now.timestamp() - entry["t"])), "state": state,
        "marketOpen": market_open(now), "nextOpen": None if market_open(now) else next_open(now).isoformat(timespec="minutes"),
        "refreshSeconds": FRESH_SECONDS,
    })
