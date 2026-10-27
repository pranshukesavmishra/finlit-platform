"""Commodity prices: MCX futures (Dhan), international USD prices and USD/INR (metals.dev, MetalpriceAPI), and import parity.

Two halves, joined only through Redis, as for the index strip but with a worker in place of on-demand refreshes:
  * the worker (`python -m finlit.worker refresh-commodities --loop`, started by deploy/scheduler.sh) asks Dhan for the MCX contracts every
    10 seconds while MCX trades and the vendors for international prices every minute, and writes what it got to Redis (cmd:mcx, cmd:intl,
    cmd:cfg, cmd:hb). It is the only caller of any provider; visitors never cause a provider call.
  * GET /api/commodity-prices (public) reads Redis and builds the answer at the moment of the request: states (live, delayed, closed), ages, import
    parity, premium. Prices travel as text already rounded to the digits shown; the browser only formats them.

Every contract id is resolved from Dhan's instrument file (dhan_commodity_contracts), never written into code: ids change at each expiry.

DECISIONS PENDING (the founder has not answered; each default is marked "decision pending" where it is used):
  1. metals.dev / MetalpriceAPI plans and keys: with no key the page shows the MCX price alone and says the international price is not connected.
  2. Public display of MCX prices (Dhan and MCX written permission): no MCX logo, the figure is labelled "MCX futures price (via Dhan)",
     and the word "Live" is used only when COMMODITY_MCX_DISPLAY_CLEARED is set and the price is fresh.
  3. Platinum duty (assumed, unconfirmed: no platinum parity), 22K = 22/24, MCX gold 995 scaled to 999 for the premium, statutory tariff-value
     landed cost left out (simple market-value formula only).
  4. Public page, no sign-in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Request, Response

from . import commodity_calc as calc
from .commodity_calc import D, dec, q
from .commodity_feeds import FeedError, Snapshot, fetch_metalprice, fetch_metals_dev
from .dhan import DhanClient, DhanError, _trade_time

log = logging.getLogger("finlit.commodities")
router = APIRouter(prefix="/api/commodity-prices")
IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")
MCX_SEGMENT = "MCX_COMM"
KEEP = 7 * 24 * 3600
K_CONTRACTS, K_MCX, K_INTL, K_CFG, K_HB, K_REF = "cmd:contracts", "cmd:mcx", "cmd:intl", "cmd:cfg", "cmd:hb", "cmd:ref"

# ------------------------------------------------------------------------------------------------------------------ what is shown
# code: name, tab group, MCX symbol and how its quote converts to the displayed unit, international lines, duty row.
#   mcx_div  the quote is rupees per `mcx_div` of the displayed unit's base (GOLD: Rs per 10 g -> per gram: / 10; SILVER: per kg -> per gram: / 1000)
#   dp       decimals of the displayed MCX price; intl: (code, label, unit text, decimals)
CARDS: List[Dict[str, Any]] = [
    {"code": "gold", "name": "Gold", "group": "precious", "mcx": "GOLD", "mcx_unit": "per 10 g", "div": D(10), "per": "gram", "dp": 2,
     "intl": [("gold", "Spot gold", "per troy oz", 2)], "duty": "gold"},
    {"code": "silver", "name": "Silver", "group": "precious", "mcx": "SILVER", "mcx_unit": "per kg", "div": D(1000), "per": "gram", "dp": 2,
     "intl": [("silver", "Spot silver", "per troy oz", 2)], "duty": "silver"},
    {"code": "platinum", "name": "Platinum", "group": "precious", "mcx": None, "intl": [("platinum", "Spot platinum", "per troy oz", 2)], "duty": "platinum"},
    {"code": "crude", "name": "Crude oil", "group": "energy", "mcx": "CRUDEOIL", "mcx_unit": "per barrel", "div": D(1), "per": "barrel", "dp": 0,
     "intl": [("wti", "WTI crude", "per barrel", 2), ("brent", "Brent crude", "per barrel", 2)], "duty": None},
    {"code": "natgas", "name": "Natural gas", "group": "energy", "mcx": "NATURALGAS", "mcx_unit": "per mmBtu", "div": D(1), "per": "mmBtu", "dp": 1,
     "intl": [("natgas", "Henry Hub gas", "per mmBtu", 3)], "duty": None},
    {"code": "copper", "name": "Copper", "group": "industrial", "mcx": "COPPER", "mcx_unit": "per kg", "div": D(1), "per": "kg", "dp": 2,
     "intl": [("copper", "Spot copper", "per tonne", 2)], "duty": None},
    {"code": "aluminium", "name": "Aluminium", "group": "industrial", "mcx": "ALUMINIUM", "mcx_unit": "per kg", "div": D(1), "per": "kg", "dp": 2,
     "intl": [("aluminium", "Spot aluminium", "per tonne", 2)], "duty": None},
]
MCX_SYMBOLS = [c["mcx"] for c in CARDS if c["mcx"]]
METALS_DEV_CODES = {"gold", "silver", "platinum", "copper", "aluminium"}
ENERGY_CODES = {"wti", "brent", "natgas"}
DEFAULT_HOURS = {"open": "09:00", "close": "23:30", "confirmed": False}
MAX_MOVE_PCT = D(12)               # a day move beyond this on a contract is treated as a bad quote
DUTY_RECHECK_DAYS = 120            # parity is hidden when a person last confirmed the rate longer ago than this


# ------------------------------------------------------------------------------------------------------------------ MCX hours

def _t(text: str) -> dtime:
    h, m = text.split(":")[:2]
    return dtime(int(h), int(m))


def mcx_session(now: datetime, hours: List[dict], holidays: List[dict]) -> Dict[str, Any]:
    """Is MCX trading at `now` (IST)? From the hours table (never hard-coded: US daylight saving moves the evening close) and the holiday
    list; Saturday and Sunday are closed. A day outside every row uses 09:00-23:30 and says it is unconfirmed."""
    t = now.astimezone(IST)
    day = t.date().isoformat()
    row = next((h for h in hours if h["from"] <= day <= h["to"]), None) or DEFAULT_HOURS
    opens, closes = _t(row["open"]), _t(row["close"])
    hol = next((h for h in holidays if h["day"] == day), None)
    info = {"open": False, "opens": row["open"], "closes": row["close"], "confirmed": bool(row.get("confirmed", False)), "why": None}
    if t.weekday() >= 5:
        info["why"] = "weekend"
    elif hol and hol.get("kind", "full") == "full":
        info["why"] = "holiday"
    else:
        if hol:                                   # morning session shut, evening session open
            opens = dtime(17, 0)
            info["opens"] = "17:00"
        info["open"] = opens <= t.time() < closes
        if not info["open"]:
            info["why"] = "night" if t.time() >= closes else "not yet open"
    return info


def global_open(now: datetime) -> bool:
    """Spot metals trade from Sunday 23:00 UTC to Friday 22:00 UTC."""
    u = now.astimezone(timezone.utc)
    wd, tm = u.weekday(), u.time()
    if wd == 5:
        return False
    if wd == 6:
        return tm >= dtime(23, 0)
    if wd == 4:
        return tm < dtime(22, 0)
    return True


# ------------------------------------------------------------------------------------------------------------------ MCX contracts and quotes

def candidates(rows: List[dict], symbol: str, today: date) -> List[dict]:
    """The two nearest contracts of a symbol that expire after today (a contract on its expiry day is in its delivery period and is left out)."""
    live = [r for r in rows if r["symbol"] == symbol and r["expiry"] > today.isoformat()]
    return sorted(live, key=lambda r: r["expiry"])[:2]


def choose(cands: List[dict], raw: Dict[str, dict], sticky: Optional[str]) -> Optional[dict]:
    """The active contract: the nearer one unless the next one trades more (higher volume); once the next one is chosen it is kept, so the
    card never flips back within a session. Without volume in the answer (or equal volume) the nearest expiry is used."""
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    if sticky == cands[1]["security_id"]:
        return cands[1]
    vol = lambda c: dec((raw.get(c["security_id"]) or {}).get("volume")) or D(0)   # noqa: E731
    return cands[1] if vol(cands[1]) > vol(cands[0]) else cands[0]


def read_quote(raw: dict, contract: dict) -> Tuple[Optional[dict], Optional[str]]:
    """One /marketfeed/quote entry as the figures to keep: (reading, None), or (None, why it was refused). Refused: no usable price, a price
    outside the exchange band (when the band is known; 0 means unknown), or a day move above 12%."""
    last = dec(raw.get("last_price"))
    ohlc = raw.get("ohlc") if isinstance(raw.get("ohlc"), dict) else {}
    traded = _trade_time(raw.get("last_trade_time"))
    no_trade = not last or last <= 0
    price = dec(ohlc.get("close")) if no_trade else last
    if not price or price <= 0:
        return None, "no price"
    up, lo = dec(contract.get("upper")), dec(contract.get("lower"))
    if (up and up > 0 and price > up) or (lo and lo > 0 and price < lo):
        return None, "outside the exchange price band"
    prev = None
    if not no_trade:
        net = dec(raw.get("net_change"))
        if net is not None and price - net > 0:
            prev = price - net
            if abs(net / prev * 100) > MAX_MOVE_PCT:
                return None, "day move above 12%"
    vol = dec(raw.get("volume"))
    return {"price": str(price), "prev": str(prev) if prev is not None else None, "volume": int(vol) if vol and vol > 0 else None,
            "lastTrade": traded, "noTrade": no_trade or traded is None}, None


def mcx_update(rows: List[dict], raw: Dict[Tuple[str, str], dict], prev: Dict[str, dict], today: date, now: float) -> Dict[str, dict]:
    """Next cmd:mcx items from one Dhan answer. A symbol whose answer is refused or missing keeps its previous reading (same contract) for the
    age rules to judge; it is never replaced by a guess."""
    by_sid = {sid: v for (seg, sid), v in raw.items() if seg == MCX_SEGMENT}
    out: Dict[str, dict] = {}
    for sym in MCX_SYMBOLS:
        old = prev.get(sym)
        cands = candidates(rows, sym, today)
        pick = choose(cands, by_sid, (old or {}).get("sid"))
        if pick is None:
            continue
        reading, why = read_quote(by_sid.get(pick["security_id"]) or {}, pick) if pick["security_id"] in by_sid else (None, "no answer")
        rolled = (old or {}).get("rolledOn")
        if old and old.get("sid") != pick["security_id"]:
            rolled = today.isoformat()
            log.info("MCX %s moved from %s to %s: its day change is hidden today", sym, old.get("name"), pick["display_name"])
        if reading is None:
            log.warning("MCX %s %s not updated: %s", sym, pick["display_name"], why)
            if old and old.get("sid") == pick["security_id"]:
                out[sym] = {**old, "why": why}
            continue
        nxt = next((c for c in cands if c["security_id"] != pick["security_id"]), None)
        out[sym] = {"sid": pick["security_id"], "name": pick["display_name"], "expiry": pick["expiry"], "next": nxt["display_name"] if nxt else None,
                    **reading, "fetched": now, "rolledOn": rolled, "why": None}
    return out


# ------------------------------------------------------------------------------------------------------------------ international day base

def trading_day(ts: float) -> str:
    """The international trading day of a UNIX time: 17:00 New York to 17:00 (so Sunday evening already belongs to Monday)."""
    return (datetime.fromtimestamp(ts, timezone.utc).astimezone(NY) + timedelta(hours=7)).date().isoformat()


def roll_ref(ref: Optional[dict], day: str, value: str) -> Tuple[dict, Optional[dict]]:
    """{day, last, prev} for one commodity: `last` is the newest price of the trading day (by the vendor's own time), `prev` the last price of
    the day before, the base of the day change. Returns the new state and, when a day ended, that day's last price to store. A frozen weekend
    price carries Friday's time, so it never rolls the day and Friday's change stays on show."""
    if not ref:
        return {"day": day, "last": value, "prev": None}, None
    if day > ref["day"]:
        return {"day": day, "last": value, "prev": ref["last"]}, {"day": ref["day"], "value": ref["last"]}
    if day == ref["day"]:
        return {**ref, "last": value}, None
    return ref, None


# ------------------------------------------------------------------------------------------------------------------ the worker

async def load_contracts(store) -> List[dict]:
    redis = store.redis
    try:
        raw = await redis.get(K_CONTRACTS)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT security_id, symbol, display_name, expiry, upper_limit, lower_limit FROM dhan_commodity_contracts WHERE symbol = ANY($1::text[])", MCX_SYMBOLS)
    out = [{"security_id": r["security_id"], "symbol": r["symbol"], "display_name": r["display_name"], "expiry": r["expiry"].isoformat(),
            "upper": str(r["upper_limit"]) if r["upper_limit"] is not None else None, "lower": str(r["lower_limit"]) if r["lower_limit"] is not None else None} for r in rows]
    try:
        await redis.set(K_CONTRACTS, json.dumps(out), ex=86400 if out else 6 * 3600)   # the instrument load (refresh-instruments) deletes it when the file is reloaded; an empty answer is not asked again every 5 minutes (that kept Neon awake)
    except Exception:
        pass
    return out


async def load_cfg(store) -> dict:
    """Duty rates, MCX hours and holidays from their tables, as the plain structure the API reads from Redis."""
    async with store.pool.acquire() as conn:
        duty = await conn.fetch("SELECT metal, effective_from, bcd_pct, aidc_pct, gst_pct, checked_on, confirmed, source FROM commodity_duty ORDER BY metal, effective_from")
        hours = await conn.fetch("SELECT from_date, to_date, open_time, close_time, confirmed FROM mcx_hours ORDER BY from_date")
        hol = await conn.fetch("SELECT day, kind FROM mcx_holidays WHERE day >= current_date - 7 ORDER BY day")
    return {"t": time.time(),
            "duty": [{"metal": r["metal"], "from": r["effective_from"].isoformat(), "bcd": str(r["bcd_pct"]), "aidc": str(r["aidc_pct"]), "gst": str(r["gst_pct"]),
                      "checked": r["checked_on"].isoformat(), "confirmed": r["confirmed"], "source": r["source"]} for r in duty],
            "hours": [{"from": r["from_date"].isoformat(), "to": r["to_date"].isoformat(), "open": r["open_time"].strftime("%H:%M"), "close": r["close_time"].strftime("%H:%M"),
                       "confirmed": r["confirmed"]} for r in hours],
            "holidays": [{"day": r["day"].isoformat(), "kind": r["kind"]} for r in hol]}


class Worker:
    """State and schedule of the refresh loop. `tick` runs whatever is due and never raises (a failed provider keeps the last good values)."""

    def __init__(self, settings, store, dhan: Optional[DhanClient], http: httpx.AsyncClient):
        self.s, self.store, self.dhan, self.http = settings, store, dhan, http
        self.due: Dict[str, float] = {}
        self.cfg: dict = {}
        self.mcx: dict = {"t": None, "err": None, "items": {}}
        self.intl: dict = {"quotes": {}, "fx": None, "err": {}}
        self.ref: Dict[str, dict] = {}
        self.loaded = False
        self.report: Dict[str, Any] = {}

    async def _restore(self) -> None:
        for attr, key in (("mcx", K_MCX), ("intl", K_INTL), ("ref", K_REF), ("cfg", K_CFG)):
            try:
                raw = await self.store.redis.get(key)
                if raw:
                    setattr(self, attr, json.loads(raw))
            except Exception:
                pass
        self.loaded = True

    async def _save(self, key: str, value: Any) -> None:
        try:
            await self.store.redis.set(key, json.dumps(value), ex=KEEP)
        except Exception:
            log.warning("could not save %s to Redis", key)

    def _is_due(self, job: str, every: float, now: float) -> bool:
        if now >= self.due.get(job, 0):
            self.due[job] = now + every
            return True
        return False

    async def tick(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        if not self.loaded:
            await self._restore()
        wall = now or datetime.now(IST)
        mono = time.monotonic() if now is None else wall.timestamp()
        self.report = {}
        try:
            await self.store.redis.set(K_HB, str(time.time()), ex=600)
        except Exception:
            pass
        # Duty rates, hours and holidays change a few times a year. They are kept in Redis and read from Postgres only when that copy is over a day old
        # (and then at most once an hour if the database does not answer), so this loop does not keep the free database awake.
        if (not self.cfg or time.time() - float(self.cfg.get("t") or 0) > 24 * 3600) and self._is_due("cfg", 3600, mono):
            try:
                self.cfg = await load_cfg(self.store)
                await self._save(K_CFG, self.cfg)
                self.report["cfg"] = True
            except Exception:
                log.exception("commodity settings not loaded; the last ones are kept")
        sess = mcx_session(wall, self.cfg.get("hours") or [], self.cfg.get("holidays") or [])
        if self.dhan is not None and self._is_due("mcx", 10 if sess["open"] else 600, mono):
            await self.poll_mcx(wall)
        gopen = global_open(wall)
        if getattr(self.s, "metals_dev_api_key", ""):
            if self._is_due("metals", self.s.metals_dev_poll_seconds if gopen else 900, mono):
                await self.poll_metals_dev()
        if getattr(self.s, "metalprice_api_key", ""):
            if self._is_due("energy", self.s.metalprice_poll_seconds if gopen else 900, mono):
                await self.poll_metalprice()
        return self.report

    async def poll_mcx(self, wall: datetime) -> None:
        try:
            rows = await load_contracts(self.store)
            if not rows:
                raise DhanError("no MCX contracts stored yet (the instrument file has not been loaded)")
            today = wall.astimezone(IST).date()
            ask = [(MCX_SEGMENT, c["security_id"]) for sym in MCX_SYMBOLS for c in candidates(rows, sym, today)]
            raw = await self.dhan.quotes(ask)
            items = mcx_update(rows, raw, self.mcx.get("items") or {}, today, time.time())
            self.mcx = {"t": time.time(), "err": None, "items": {**(self.mcx.get("items") or {}), **items}}
            self.report["mcx"] = len(items)
        except DhanError as e:
            log.warning("MCX prices not updated: %s", e)
            self.mcx = {**self.mcx, "err": str(e)[:120]}
        except Exception as e:
            log.exception("MCX prices failed")
            self.mcx = {**self.mcx, "err": type(e).__name__}
        await self._save(K_MCX, self.mcx)

    async def _merge(self, snap: Snapshot, poll: int, fx_ok: bool = True) -> None:
        fetched = time.time()
        stored: List[dict] = []
        for code, qt in snap.quotes.items():
            old = (self.intl["quotes"].get(code) or {})
            if old and qt.ts < old.get("ts", 0):
                continue                                  # an older vendor time than the one held: not newer data
            self.intl["quotes"][code] = {"usd": str(qt.usd), "ts": qt.ts, "vendor": snap.vendor, "fetched": fetched, "poll": poll}
            self.ref[code], done = roll_ref(self.ref.get(code), trading_day(qt.ts), str(qt.usd))
            if done:
                stored.append({"symbol": code, **done})
        if snap.usdinr is not None and fx_ok and snap.usdinr.ts >= ((self.intl.get("fx") or {}).get("ts", 0)):
            self.intl["fx"] = {"usdinr": str(snap.usdinr.usd), "ts": snap.usdinr.ts, "vendor": snap.vendor, "fetched": fetched, "poll": poll}
        self.intl["err"].pop(snap.vendor, None)
        for code in self.intl["quotes"]:
            self.intl["quotes"][code]["prev"] = (self.ref.get(code) or {}).get("prev")
        await self._save(K_INTL, self.intl)
        await self._save(K_REF, self.ref)
        if stored:
            try:
                async with self.store.pool.acquire() as conn:
                    await conn.executemany("INSERT INTO commodity_snapshots (day, symbol, kind, value) VALUES ($1,$2,'intl_usd',$3) ON CONFLICT DO NOTHING",
                                           [(date.fromisoformat(r["day"]), r["symbol"], D(r["value"])) for r in stored])
            except Exception:
                log.warning("could not store the commodity day snapshots")

    async def _fail(self, vendor: str, e: Exception) -> None:
        log.warning("%s prices not updated: %s", vendor, e)
        self.intl["err"][vendor] = str(e)[:120]
        await self._save(K_INTL, self.intl)

    async def poll_metals_dev(self) -> None:
        try:
            snap = await fetch_metals_dev(self.http, self.s.metals_dev_api_key)
        except FeedError as e:
            return await self._fail("metals.dev", e)
        await self._merge(snap, self.s.metals_dev_poll_seconds)
        self.report["metals"] = len(snap.quotes)

    async def poll_metalprice(self) -> None:
        have_metals_dev = bool(getattr(self.s, "metals_dev_api_key", ""))
        try:
            snap = await fetch_metalprice(self.http, self.s.metalprice_api_key, metals=not have_metals_dev)
        except FeedError as e:
            return await self._fail("MetalpriceAPI", e)
        await self._merge(snap, self.s.metalprice_poll_seconds, fx_ok=not have_metals_dev)
        self.report["energy"] = len(snap.quotes)


async def run(settings, store, loop: bool = False) -> Dict[str, Any]:
    """The worker command. Without --loop: one pass of everything due (for a check by hand). With it: runs until stopped."""
    dhan = DhanClient(settings, store.redis) if getattr(settings, "dhan_client_id", "") else None
    if dhan is not None and not dhan.configured:
        dhan = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as http:
        w = Worker(settings, store, dhan, http)
        try:
            if not loop:
                return {"status": "ok", "ran": await w.tick(), "dhan": bool(dhan), "metals.dev": bool(settings.metals_dev_api_key), "metalprice": bool(settings.metalprice_api_key)}
            while True:
                await w.tick()
                await asyncio.sleep(1)
        finally:
            if dhan is not None:
                await dhan.aclose()


# ------------------------------------------------------------------------------------------------------------------ the answer

def _age_text(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec} s" if sec < 90 else f"{sec // 60} min" if sec < 5400 else f"{sec // 3600} h" if sec < 172800 else f"{sec // 86400} days"


def mcx_state(now: datetime, sess: dict, r: Optional[dict], hb_age: Optional[float]) -> str:
    """live (traded in the last 2 minutes), recent (2-15 minutes), delayed (longer, or the worker/Dhan is silent), closed, waiting (open, no trade yet)."""
    if r is None:
        return "none"
    if not sess["open"]:
        return "closed"
    today = now.astimezone(IST).date().isoformat()
    traded = datetime.fromisoformat(r["lastTrade"]) if r.get("lastTrade") else None
    if traded is None or traded.astimezone(IST).date().isoformat() < today:
        opened = datetime.combine(now.astimezone(IST).date(), _t(sess["opens"]), IST)
        return "waiting" if now - opened < timedelta(minutes=10) else "closed"   # no trade 10 minutes into the session: a holiday
    if hb_age is None or hb_age > 60 or now.timestamp() - r.get("fetched", 0) > 90:
        return "delayed"
    age = (now - traded).total_seconds()
    return "live" if age <= 120 else "recent" if age <= 900 else "delayed"


def intl_state(now: float, gopen: bool, v: Optional[dict]) -> str:
    """fresh, stale (older than 3 polls, at least 5 minutes: shown dimmed with its age), unavailable (older than 6 polls, at least 30 minutes),
    closed (the global market is shut: the last price is shown as of its time, for up to 4 days)."""
    if not v:
        return "none"
    age, poll = now - v["ts"], v.get("poll", 60)
    if not gopen:
        return "closed" if age <= 4 * 86400 else "unavailable"
    return "fresh" if age <= max(300, 3 * poll) else "stale" if age <= max(1800, 6 * poll) else "unavailable"


def duty_for(cfg: dict, metal: Optional[str], today: date) -> Optional[dict]:
    rows = [r for r in (cfg.get("duty") or []) if r["metal"] == metal and r["from"] <= today.isoformat()]
    return max(rows, key=lambda r: r["from"]) if rows else None


def _chg(pct: Optional[Decimal], ab: Optional[Decimal], dp_abs: int, unit: str) -> Optional[dict]:
    return None if pct is None or ab is None else {"pct": q(pct, 2), "abs": q(ab, dp_abs), "absUnit": unit}


def build(settings, now: datetime, mcx: Optional[dict], intl: Optional[dict], cfg: Optional[dict], hb: Optional[float]) -> Dict[str, Any]:
    """The /api/commodity-prices answer from what the worker saved, at the moment of the request."""
    cfg, mcx, intl = cfg or {}, mcx or {}, intl or {}
    ts = now.timestamp()
    today = now.astimezone(IST).date()
    sess = mcx_session(now, cfg.get("hours") or [], cfg.get("holidays") or [])
    gopen = global_open(now)
    hb_age = ts - hb if hb else None
    dhan_on = bool(getattr(settings, "dhan_client_id", ""))
    md_on, mp_on = bool(getattr(settings, "metals_dev_api_key", "")), bool(getattr(settings, "metalprice_api_key", ""))
    cleared = bool(getattr(settings, "commodity_mcx_display_cleared", False))
    quotes = intl.get("quotes") or {}
    fx = intl.get("fx")
    fx_state = intl_state(ts, gopen, fx)
    usdinr = dec(fx["usdinr"]) if fx and fx_state in ("fresh", "closed") else None
    items: List[dict] = []
    values: Dict[str, Decimal] = {}
    for card in CARDS:
        item: Dict[str, Any] = {"code": card["code"], "name": card["name"], "group": card["group"], "mcx": None, "intl": [], "parity": None, "notes": []}
        # ---- MCX
        if card["mcx"]:
            r = (mcx.get("items") or {}).get(card["mcx"])
            st = mcx_state(now, sess, r, hb_age)
            m: Dict[str, Any] = {"state": st, "contract": r["name"] if r else None, "expiry": r["expiry"] if r else None, "unit": f"₹ {card['mcx_unit']}", "price": None,
                                 "extra": [], "change": None, "asOf": r.get("lastTrade") if r else None, "note": None,
                                 "label": {"live": "Live" if cleared else "Updating", "recent": "Recent trade", "delayed": "Delayed", "closed": "Closed", "waiting": "Waiting for first trade", "none": "Waiting for first price"}[st]}
            if not dhan_on:
                m.update(state="off", label="Not connected", note="MCX prices are not connected yet.")
            elif r is None:
                m["note"] = "Waiting for the first MCX price." if not mcx.get("err") else "MCX price temporarily unavailable."
            else:
                raw = dec(r["price"])
                per_unit = raw / card["div"]
                dp = card["dp"]
                unit = f"₹ per {card['per']}"
                m["price"] = {"value": q(per_unit, dp), "unit": unit}
                if card["code"] == "gold":
                    m["extra"] = [{"label": "Exchange quote, per 10 g", "value": q(raw, 0), "unit": "₹"},
                                  {"label": "22K, per gram", "value": q(calc.k22(per_unit), 2), "unit": "₹"},
                                  {"label": "18K, per gram", "value": q(calc.k18(per_unit), 2), "unit": "₹"}]
                elif card["code"] == "silver":
                    m["extra"] = [{"label": "Exchange quote, per kg", "value": q(raw, 0), "unit": "₹"}]
                if st == "closed":
                    m["note"] = "MCX is closed" + (" today" if sess["why"] in ("holiday", "weekend") else "") + ": the last traded price is shown."
                elif st == "delayed":
                    m["note"] = "Delayed: the last trade is more than 15 minutes old, or the feed is not updating. The day change is hidden."
                elif r.get("noTrade"):
                    m["note"] = "No trades yet today: the previous close is shown."
                prev = dec(r.get("prev"))
                if st in ("live", "recent", "closed") and not r.get("noTrade") and prev is not None and r.get("rolledOn") != today.isoformat():
                    c = calc.day_change(raw, prev)
                    if c:
                        m["change"] = _chg(c[1], c[0] / card["div"], dp, unit)
                elif r.get("rolledOn") == today.isoformat() and st != "delayed":
                    m["note"] = (m["note"] + " " if m["note"] else "") + "The contract changed today, so the day change is hidden."
                if per_unit > 0:
                    values[card["code"] + ":mcx"] = per_unit
            item["mcx"] = m
        # ---- international
        for code, label, unit, dp in card["intl"]:
            wanted_on = md_on if code in METALS_DEV_CODES else mp_on if code in ENERGY_CODES else False
            if code in METALS_DEV_CODES and not md_on and mp_on and code in ("gold", "silver", "platinum"):
                wanted_on = True                           # MetalpriceAPI alone also carries gold, silver and platinum
            v = quotes.get(code)
            st = intl_state(ts, gopen, v) if wanted_on or v else "off"
            line: Dict[str, Any] = {"key": code, "label": label, "unit": f"$ {unit}", "state": st, "usd": None, "changePct": None, "asOf": None, "vendor": None, "note": None}
            if st == "off":
                line["note"] = "International price not connected."
            elif v is None:
                line["state"], line["note"] = "none", "Waiting for the first international price."
            elif st == "unavailable":
                line["note"] = "International price temporarily unavailable."
            else:
                usd = dec(v["usd"])
                line.update(usd=q(usd, dp), asOf=datetime.fromtimestamp(v["ts"], timezone.utc).isoformat(timespec="seconds"), vendor=v.get("vendor"))
                if st == "stale":
                    line["note"] = f"Last update {_age_text(ts - v['ts'])} ago."
                elif st == "closed":
                    line["note"] = "Global market closed: the last price is shown."
                c = calc.day_change(usd, dec(v.get("prev")))
                if c and st in ("fresh", "closed"):
                    line["changePct"] = q(c[1], 2)
                if usd is not None:
                    values[code] = usd
            item["intl"].append(line)
        if card["intl"] and all(x["state"] == "off" for x in item["intl"]):
            item["notes"].append("International price not connected.")
        # ---- import parity
        if card["duty"]:
            item["parity"] = _parity(card, item, cfg, today, values, usdinr, fx, fx_state)
        items.append(item)
    ratio = None
    g, s = values.get("gold"), values.get("silver")
    if g and s and all((i["intl"][0]["state"] in ("fresh", "closed")) for i in items if i["code"] in ("gold", "silver")):
        ratio = q(g / s, 1)
    return {
        "asOf": now.astimezone(IST).isoformat(timespec="seconds"),
        "status": "ok" if (mcx.get("items") or quotes) else "waiting",
        "market": {"mcx": {"open": sess["open"], "opens": sess["opens"], "closes": sess["closes"], "hoursConfirmed": sess["confirmed"], "why": sess["why"]}, "global": {"open": gopen}},
        "sources": {"mcx": {"connected": dhan_on, "label": "MCX futures price (via Dhan)", "error": mcx.get("err")},
                    "intl": {"connected": md_on or mp_on, "metals": "metals.dev" if md_on else "MetalpriceAPI" if mp_on else None, "energy": "MetalpriceAPI" if mp_on else None,
                             "errors": intl.get("err") or {}}},
        "fx": {"state": fx_state if (md_on or mp_on) else "off", "usdinr": q(dec(fx["usdinr"]), 4) if fx and fx_state in ("fresh", "closed", "stale") else None,
               "asOf": datetime.fromtimestamp(fx["ts"], timezone.utc).isoformat(timespec="seconds") if fx else None, "vendor": fx.get("vendor") if fx else None},
        "assumptions": {"k22": calc.K22_CONVENTION, "mcxGoldFineness": str(calc.MCX_GOLD_FINENESS), "fineFineness": str(calc.FINE_FINENESS), "parity": "market value, simple formula"},
        "ratio": {"goldSilver": ratio},
        "items": items,
        "worker": {"ageSeconds": round(hb_age) if hb_age is not None else None},
    }


def _parity(card: dict, item: dict, cfg: dict, today: date, values: Dict[str, Decimal], usdinr: Optional[Decimal], fx: Optional[dict], fx_state: str) -> dict:
    code = card["code"]
    out: Dict[str, Any] = {"state": "hidden", "reason": None}
    line = item["intl"][0]
    d = duty_for(cfg, card["duty"], today)
    if line["state"] == "off":
        out["reason"] = "International price not connected, so import parity cannot be worked out."
        return out
    if d is None:
        out["reason"] = "The customs duty rate is not set."
        return out
    if not d["confirmed"]:
        out["reason"] = "Import parity is not shown for this metal until its customs duty rate is confirmed."
        return out
    if (today - date.fromisoformat(d["checked"])).days > DUTY_RECHECK_DAYS:
        out["reason"] = "The customs duty rate is due for a check, so import parity is hidden."
        return out
    if line["state"] not in ("fresh", "closed", "stale") or code not in values:
        out["reason"] = "Waiting for the international price."
        return out
    if usdinr is None:
        out["reason"] = "The USD/INR rate is out of date, so import parity is hidden."
        return out
    bcd, aidc, gst = (dec(d[k]) / 100 for k in ("bcd", "aidc", "gst"))
    p = calc.parity(values[code], usdinr, bcd, aidc, gst)
    out.update(state="ok", perGram=q(p.duty_paid, 2), per10g=q(p.duty_paid * 10, 0), perKg=q(p.duty_paid * 1000, 0), withGst=q(p.with_gst, 2),
               duty={"bcd": q(dec(d["bcd"]), 2).rstrip("0").rstrip("."), "aidc": q(dec(d["aidc"]), 2).rstrip("0").rstrip("."),
                     "total": q((bcd + aidc) * 100, 2).rstrip("0").rstrip("."), "gst": q(dec(d["gst"]), 2).rstrip("0").rstrip("."), "effectiveFrom": d["from"], "checkedOn": d["checked"]},
               usdinr=q(usdinr, 4), asOf=line["asOf"], premiumPct=None)
    m, mv = item.get("mcx"), values.get(code + ":mcx")
    if m and mv and m["state"] in ("live", "recent", "closed"):
        mcx_cmp = calc.mcx_to_fine(mv) if code == "gold" else mv
        pr = calc.premium_pct(mcx_cmp, p.duty_paid)
        out["premiumPct"] = q(pr, 2)
        out["premiumBasis"] = ("MCX gold is a 995 bar, so its price is scaled to 999 purity (x 999 / 995) before the comparison." if code == "gold"
                               else "Both prices are for 999 silver.")
    return out


async def _load(app) -> Tuple[Optional[dict], Optional[dict], Optional[dict], Optional[float]]:
    redis = app.state.store.redis
    out: List[Any] = []
    for key in (K_MCX, K_INTL, K_CFG, K_HB):
        try:
            raw = await redis.get(key)
        except Exception:
            raw = None
        out.append(json.loads(raw) if raw and key != K_HB else float(raw) if raw else None)
    return out[0], out[1], out[2], out[3]


@router.get("")
async def commodities(request: Request) -> Response:
    """Commodity prices for everyone (no sign-in). Built from what the worker saved in Redis; never calls a provider."""
    app = request.app
    mcx, intl, cfg, hb = await _load(app)
    now = datetime.now(IST)
    body = build(app.state.settings, now, mcx, intl, cfg, hb)
    age = 10 if body["market"]["mcx"]["open"] else 60
    return Response(json.dumps(body), media_type="application/json", headers={"Cache-Control": f"public, max-age={age}"})
