"""The daily canary: re-fetch a few reference companies from the provider and compare with what we hold. It catches WRONG data (a bad quote, a stale
close, a figure that differs from the provider's), which no freshness date can. Mismatches go to /api/jobs/status (`canary`) and to the admin alert.

Tolerances (stated, and returned with the result):
  price          0.5% when the market is closed, 3% while it is open (it moves between the two reads)
  last close     0.5%
  market cap     5% closed / 8% open (shares outstanding are rounded differently by providers)
  quarter figures (revenue, net profit)  0.5%  (exact up to rounding; a restated figure is a real difference worth knowing about)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .schedule import expected_session, ist, market_open

log = logging.getLogger("finlit.jobs.canary")
CORE = ("RELIANCE", "TCS", "HDFCBANK", "INFY")
TOL_CLOSED = {"price": 0.005, "close": 0.005, "marketCap": 0.05, "revenue": 0.005, "netProfit": 0.005}
TOL_OPEN = {"price": 0.03, "close": 0.005, "marketCap": 0.08, "revenue": 0.005, "netProfit": 0.005}


def tolerances(now: datetime) -> Dict[str, float]:
    return TOL_OPEN if market_open(now) else TOL_CLOSED


def compare(symbol: str, field: str, ours: Optional[float], theirs: Optional[float], tol: float) -> Optional[Dict[str, Any]]:
    """None when they agree (or either side is not there: absence is a freshness question, not a value mismatch)."""
    if ours is None or theirs is None or theirs == 0:
        return None
    diff = abs(float(ours) / float(theirs) - 1)
    if diff <= tol:
        return None
    return {"symbol": symbol, "field": field, "ours": float(ours), "provider": float(theirs), "diffPercent": round(diff * 100, 2), "tolerancePercent": round(tol * 100, 2)}


def compare_company(symbol: str, stored: Dict[str, Any], fresh: Dict[str, Any], tol: Dict[str, float]) -> List[Dict[str, Any]]:
    out = [compare(symbol, "price", stored.get("price"), fresh.get("price"), tol["price"]),
           compare(symbol, "marketCap", stored.get("marketCap"), fresh.get("marketCapCr"), tol["marketCap"]),
           compare(symbol, "lastClose", stored.get("close") if stored.get("closeIsLatest") else None, fresh.get("price"), tol["close"])]   # only when our newest bar IS the latest session's
    q, fq = stored.get("quarter") or {}, fresh.get("quarter") or {}
    out += [compare(symbol, "quarterRevenue", q.get("revenue"), fq.get("revenue"), tol["revenue"]),
            compare(symbol, "quarterNetProfit", q.get("netProfit"), fq.get("netProfit"), tol["netProfit"])]
    return [m for m in out if m]


def summarise(checked: List[str], mismatches: List[Dict[str, Any]], errors: List[str], now: datetime) -> Dict[str, Any]:
    ok: Optional[bool] = None if (errors and not checked) else not mismatches
    return {"checkedAt": now.isoformat(timespec="seconds"), "ok": ok, "checked": checked, "mismatches": mismatches, "errors": errors[:10],
            "tolerancesPercent": {k: round(v * 100, 2) for k, v in tolerances(now).items()}}


async def pick_symbols(conn: Any, today: date) -> List[str]:
    syms = list(CORE)
    small = await conn.fetchval("SELECT symbol FROM listing_quotes WHERE market_cap BETWEEN 200 AND 2000 AND price > 0 AND symbol NOT IN (SELECT unnest($1::text[])) "
                                "ORDER BY md5(symbol || $2) LIMIT 1", syms, today.isoformat())
    recent = await conn.fetchval("SELECT i.symbol FROM ipos i JOIN listing_quotes q ON q.symbol = i.symbol WHERE i.listing_date <= $1 AND i.symbol IS NOT NULL "
                                 "ORDER BY i.listing_date DESC LIMIT 1", today)
    return syms + [s for s in (small, recent) if s and s not in syms]


async def stored_view(conn: Any, symbol: str, now: datetime) -> Dict[str, Any]:
    q = await conn.fetchrow("SELECT price, market_cap FROM listing_quotes WHERE symbol = $1", symbol)
    c = await conn.fetchrow("SELECT close, day FROM price_daily WHERE symbol = $1 ORDER BY day DESC LIMIT 1", symbol)
    ql = await conn.fetchrow("SELECT revenue, net_profit, period_end FROM quarter_light WHERE symbol = $1 AND filled ORDER BY period_end DESC NULLS LAST LIMIT 1", symbol)
    return {"price": float(q["price"]) if q and q["price"] is not None else None, "marketCap": float(q["market_cap"]) if q and q["market_cap"] is not None else None,
            "close": float(c["close"]) if c is not None else None, "marketOpen": market_open(now),
            "closeIsLatest": bool(c is not None and c["day"] == expected_session(now) and not market_open(now)),
            "quarter": {"revenue": ql["revenue"], "netProfit": ql["net_profit"], "periodEnd": ql["period_end"]} if ql else None}


async def run(store: Any, client: Any, now: datetime) -> Dict[str, Any]:
    from .. import results_light
    from ..normalize import market
    mism: List[Dict[str, Any]] = []
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
            mism += compare_company(s, stored, fresh, tol)
            checked.append(s)
        except Exception as exc:
            errors.append(f"{s}: {type(exc).__name__}")
    return summarise(checked, mism, errors, now)
