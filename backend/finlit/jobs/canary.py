"""The daily canary: re-fetch a few reference companies from the provider and compare with what we hold. It catches WRONG data (a bad quote, a stale
close, a figure that differs from the provider's), which no freshness date can. Confirmed mismatches go to /api/jobs/status (`canary`) and to the admin alert.

What is compared, and how a false alarm is avoided (each rule exists because a real one happened: FISCHER, a thin low-priced stock, 24.79 ours vs 24.58 the
provider's, 0.85% apart, raised "data differs from the provider" although nothing was wrong - two feeds, taken at different moments, on a stock that trades
a few times a day and moves in steps of 5 paise):
  reference list  only large, liquid companies (RELIANCE, TCS, HDFCBANK, INFY plus one rotating company of at least LIQUID_MIN_CAP_CR crore): a thin stock's
                  last trade legitimately differs between feeds, so it never decides whether the data is right
  tolerance       price 0.5% when the market is closed, 3% while it is open; never tighter than TICKS_FLOOR exchange ticks (so a Rs 25 stock is allowed
                  Rs 0.10), market cap 5% closed / 8% open, last close 0.5%, quarter revenue and net profit 0.5% (a restated figure is a real difference)
  like with like  after the close, a price is compared only when both figures were taken within SAME_MOMENT_MIN minutes of each other; a provider
                  quote from earlier in the session is a stale feed (the freshness check owns that), not a wrong value
  two in a row    a mismatch raises the alert only when the SAME symbol and field mismatch on two consecutive runs. The first sighting is recorded as
                  'watching' and does not alert; a value that agrees on the next run is dropped
  the message     names both figures, when each was taken, and which side is probably right (the one taken later)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .schedule import IST, expected_session, fmt_ist, ist, market_open

log = logging.getLogger("finlit.jobs.canary")
CORE = ("RELIANCE", "TCS", "HDFCBANK", "INFY")
LIQUID_MIN_CAP_CR = 50000.0   # the rotating reference company must be at least this large (Rs crore): a liquid large cap
TICK = 0.05                   # NSE equity tick (Rs); the largest step of any listed stock, so the floor is never too tight
TICKS_FLOOR = 2               # a price may differ by this many ticks before it counts, whatever the percentage says
SAME_MOMENT_MIN = 30          # minutes: two closed-market prices taken further apart than this are not the same moment
SESSION_END = dtime(15, 30)       # NSE equity session close (IST)
CONFIRM_WITHIN_H = 48         # a mismatch seen on the previous run counts as "the second time" only when that run was this recent
TOL_CLOSED = {"price": 0.005, "close": 0.005, "marketCap": 0.05, "revenue": 0.005, "netProfit": 0.005}
TOL_OPEN = {"price": 0.03, "close": 0.005, "marketCap": 0.08, "revenue": 0.005, "netProfit": 0.005}


def tolerances(now: datetime) -> Dict[str, float]:
    return TOL_OPEN if market_open(now) else TOL_CLOSED


def tick_floor(price: Optional[float]) -> float:
    """TICKS_FLOOR exchange ticks as a share of the price: 0.4% for a Rs 25 stock, 0.01% for a Rs 1,000 one."""
    return TICKS_FLOOR * TICK / float(price) if price and float(price) > 0 else 0.0


def _dt(x: Any) -> Optional[datetime]:
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=ist(datetime.now(timezone.utc)).tzinfo)
    except ValueError:
        return None


def which_side(ours_at: Any, provider_at: Any) -> Tuple[str, str]:
    """(side, sentence): the figure taken later is probably right. Unknown when a time is missing or they are the same moment."""
    a, b = _dt(ours_at), _dt(provider_at)
    when = f"ours taken {fmt_ist(a) or 'at an unknown time'}, the provider's {fmt_ist(b) or 'at an unknown time'}"
    if a is None or b is None:
        return "unknown", f"{when}; cannot tell which is newer, check both sources"
    if abs((a - b).total_seconds()) <= 60:
        return "unknown", f"{when}: the same moment, so one feed is wrong; check the exchange price"
    return ("ours", f"{when}: ours is newer, so it is probably right and the provider's feed is behind") if a > b \
        else ("provider", f"{when}: the provider's is newer, so it is probably right and ours is stale")


def compare(symbol: str, field: str, ours: Optional[float], theirs: Optional[float], tol: float, ours_at: Any = None, provider_at: Any = None) -> Optional[Dict[str, Any]]:
    """None when they agree (or either side is not there: absence is a freshness question, not a value mismatch). The tolerance for a price is never
    tighter than TICKS_FLOOR exchange ticks."""
    if ours is None or theirs is None or theirs == 0:
        return None
    if field in ("price", "lastClose"):
        tol = max(tol, tick_floor(theirs))
    diff = abs(float(ours) / float(theirs) - 1)
    if diff <= tol:
        return None
    side, sentence = which_side(ours_at, provider_at)
    m = {"symbol": symbol, "field": field, "ours": float(ours), "provider": float(theirs), "diffPercent": round(diff * 100, 2), "tolerancePercent": round(tol * 100, 2),
         "probablyRight": side, "ourAt": _dt(ours_at).isoformat(timespec="seconds") if _dt(ours_at) else None,
         "providerAt": _dt(provider_at).isoformat(timespec="seconds") if _dt(provider_at) else None}
    m["message"] = f"{symbol} {field}: ours {float(ours):g} vs the provider's {float(theirs):g}, {m['diffPercent']}% apart (allowed {m['tolerancePercent']}%); {sentence}"
    return m


def close_not_comparable(stored: Dict[str, Any], provider_at: Any) -> Optional[str]:
    """None when our stored last close and the provider's price are for the SAME finished trading session; else the sentence saying why they are not.
    Ours is the daily bar of `closeDay` (price_daily); the provider's is its quote, whose time says which session it belongs to. A close is compared only
    when (1) both are of the same session date, (2) the provider's quote was taken after the close, and (3) our bar was stored after the close (a bar
    written in the middle of the session is a price, not the close). HDFCBANK 690.0 vs 699.5 was a comparison of two different moments."""
    close_day, b = stored.get("closeDay"), _dt(provider_at)
    if stored.get("close") is None:
        return None
    if close_day is None or b is None:
        return f"ours is from {close_day.strftime('%d %b') if close_day else 'an unknown date'}, the provider's from {fmt_ist(b)[:6] if b else 'an unknown date'}"
    prov_day = ist(b).date()
    if close_day != prov_day:
        return f"ours is from {close_day.strftime('%d %b')}, the provider's from {prov_day.strftime('%d %b')}"
    closed = datetime.combine(close_day, SESSION_END, IST)
    if b < closed:
        return f"the provider's quote ({fmt_ist(b)}) was taken before the {close_day.strftime('%d %b')} close ({SESSION_END.strftime('%H:%M')} IST), so it is not the close"
    stored_at = _dt(stored.get("closeAt"))
    if stored_at is not None and stored_at < closed:
        return f"ours was stored {fmt_ist(stored_at)}, before the {close_day.strftime('%d %b')} close, so it is not the close"
    return None


def compare_company(symbol: str, stored: Dict[str, Any], fresh: Dict[str, Any], tol: Dict[str, float], skipped: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    ours_at, prov_at = stored.get("priceAt"), fresh.get("asOf")
    a, b = _dt(ours_at), _dt(prov_at)
    out: List[Optional[Dict[str, Any]]] = []
    if not stored.get("marketOpen") and a and b and abs((a - b).total_seconds()) > SAME_MOMENT_MIN * 60:
        # not the same moment: the provider's quote is from earlier in the session than ours (or the reverse). That is a stale feed, which the freshness
        # check reports; it says nothing about whether the value is right, so it is not compared.
        if skipped is not None:
            skipped.append(f"{symbol} price not compared: ours was taken {fmt_ist(a)}, the provider's {fmt_ist(b)}")
    else:
        out.append(compare(symbol, "price", stored.get("price"), fresh.get("price"), tol["price"], ours_at, prov_at))
        out.append(compare(symbol, "marketCap", stored.get("marketCap"), fresh.get("marketCapCr"), tol["marketCap"], ours_at, prov_at))
    why_not = close_not_comparable(stored, prov_at)
    if why_not is None:
        out.append(compare(symbol, "lastClose", stored.get("close"), fresh.get("price"), tol["close"], stored.get("closeAt"), prov_at))
    elif skipped is not None and stored.get("close") is not None:
        skipped.append(f"{symbol} last close not comparable: {why_not}")   # reported, never 'watching' and never an alert: two different sessions can differ by any amount
    q, fq = stored.get("quarter") or {}, fresh.get("quarter") or {}
    out += [compare(symbol, "quarterRevenue", q.get("revenue"), fq.get("revenue"), tol["revenue"], stored.get("quarterAt"), datetime.now(timezone.utc)),
            compare(symbol, "quarterNetProfit", q.get("netProfit"), fq.get("netProfit"), tol["netProfit"], stored.get("quarterAt"), datetime.now(timezone.utc))]
    return [m for m in out if m]


def confirm(found: List[Dict[str, Any]], previous: Optional[Dict[str, Any]], now: datetime) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(confirmed, watching). A mismatch is confirmed when the same symbol and field was already a mismatch or being watched on the previous run
    (at most CONFIRM_WITHIN_H hours ago); otherwise it is 'watching': recorded, shown, not alerted."""
    prev_at = _dt((previous or {}).get("checkedAt"))
    seen: Dict[Tuple[str, str], Optional[str]] = {}
    if previous and prev_at and (now - prev_at) <= timedelta(hours=CONFIRM_WITHIN_H):
        for m in list(previous.get("mismatches") or []) + list(previous.get("watching") or []):
            seen[(m.get("symbol"), m.get("field"))] = m.get("firstSeenAt") or previous.get("checkedAt")
    confirmed, watching = [], []
    for m in found:
        key = (m["symbol"], m["field"])
        if key in seen:
            m = {**m, "firstSeenAt": seen[key], "runs": 2}
            m["message"] += f" - the same on two runs in a row (first seen {fmt_ist(_dt(seen[key]))})"
            confirmed.append(m)
        else:
            watching.append({**m, "firstSeenAt": now.isoformat(timespec="seconds"), "runs": 1})
    return confirmed, watching


def summarise(checked: List[str], mismatches: List[Dict[str, Any]], errors: List[str], now: datetime, watching: Optional[List[Dict[str, Any]]] = None,
              skipped: Optional[List[str]] = None) -> Dict[str, Any]:
    ok: Optional[bool] = None if (errors and not checked) else not mismatches
    out = {"checkedAt": now.isoformat(timespec="seconds"), "ok": ok, "checked": checked, "mismatches": mismatches, "errors": errors[:10],
           "tolerancesPercent": {k: round(v * 100, 2) for k, v in tolerances(now).items()},
           "rules": f"large companies only; a price may differ by at least {TICKS_FLOOR} ticks; an alert needs the same mismatch on two runs in a row"}
    if watching:
        out["watching"] = watching
    if skipped:
        out["skipped"] = skipped[:10]
    return out


def alert_text(result: Dict[str, Any]) -> str:
    """The alert body: every confirmed mismatch with both figures, when each was taken and which side is probably right."""
    return " | ".join(m.get("message") or f"{m['symbol']} {m['field']}: ours {m['ours']} vs provider {m['provider']} ({m['diffPercent']}%)" for m in (result.get("mismatches") or [])[:6])


async def pick_symbols(conn: Any, today: date) -> List[str]:
    syms = list(CORE)
    large = await conn.fetchval("SELECT symbol FROM listing_quotes WHERE market_cap >= $3 AND price > 0 AND symbol NOT IN (SELECT unnest($1::text[])) "
                                "ORDER BY md5(symbol || $2) LIMIT 1", syms, today.isoformat(), LIQUID_MIN_CAP_CR)
    return syms + ([large] if large else [])


async def stored_view(conn: Any, symbol: str, now: datetime) -> Dict[str, Any]:
    q = await conn.fetchrow("SELECT price, market_cap, traded_at FROM listing_quotes WHERE symbol = $1", symbol)
    c = await conn.fetchrow("SELECT close, day FROM price_daily WHERE symbol = $1 ORDER BY day DESC LIMIT 1", symbol)
    stored_at = await conn.fetchval("SELECT max(generated_at) FROM snapshots WHERE symbol = $1", symbol)   # price_daily is written with the snapshot, so this bounds when the bar was stored
    ql = await conn.fetchrow("SELECT revenue, net_profit, period_end, checked_at FROM quarter_light WHERE symbol = $1 AND filled ORDER BY period_end DESC NULLS LAST LIMIT 1", symbol)
    return {"price": float(q["price"]) if q and q["price"] is not None else None, "marketCap": float(q["market_cap"]) if q and q["market_cap"] is not None else None,
            "priceAt": q["traded_at"] if q else None,
            "close": float(c["close"]) if c is not None else None, "marketOpen": market_open(now),
            "closeDay": c["day"] if c is not None else None,      # the session our last daily bar is of
            "closeAt": stored_at,                                  # when that bar was stored (the report's snapshot time); None when unknown
            "closeIsLatest": bool(c is not None and c["day"] == expected_session(now) and not market_open(now)),
            "quarter": {"revenue": ql["revenue"], "netProfit": ql["net_profit"], "periodEnd": ql["period_end"]} if ql else None,
            "quarterAt": ql["checked_at"] if ql else None}


async def run(store: Any, client: Any, now: datetime, previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """`previous` is the last stored canary result: a mismatch must repeat from it to be confirmed (see the module text)."""
    from .. import results_light
    from ..normalize import market
    found: List[Dict[str, Any]] = []
    skipped: List[str] = []
    errors: List[str] = []
    checked: List[str] = []
    tol = tolerances(now)
    async with store.pool.acquire() as conn:
        symbols = await pick_symbols(conn, ist(now).date())
        views = {s: await stored_view(conn, s, now) for s in symbols}
    for s in symbols:
        try:
            fresh = market.quote(await client.get("/quote", {"symbol": s}, timeout=10), s)
            if not fresh.get("price"):
                errors.append(f"{s}: the provider sent no price")
                continue
            stored = views[s]
            q = stored.get("quarter")
            if q and q.get("periodEnd"):
                try:
                    got = await results_light.fetch_quarter(client, s, q["periodEnd"])
                    m = (got.get("figures") or {}).get("m") or {}
                    fresh["quarter"] = {"revenue": m.get("q_revenue"), "netProfit": m.get("q_net_profit")}
                except Exception as exc:
                    errors.append(f"{s}: quarter not read ({type(exc).__name__})")
            found += compare_company(s, stored, fresh, tol, skipped)
            checked.append(s)
        except Exception as exc:
            errors.append(f"{s}: {type(exc).__name__}")
    confirmed, watching = confirm(found, previous, now)
    return summarise(checked, confirmed, errors, now, watching, skipped)
