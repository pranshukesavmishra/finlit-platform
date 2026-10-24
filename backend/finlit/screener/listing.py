"""The nightly listing refresh: every listed company's price, market cap and 52-week range from the provider's market-wide quote list.

Why it exists: the screener used to be built only from stored full reports (a few hundred of the ~5,800 listed companies, the rest are loaded
when someone opens them). This keeps a light row for every listed company, so the screener lists all of them. It costs two provider calls (the
symbol list and the market-wide quote list) and one short database write, once a night; it never touches a company's report.

Only figures the provider sent are stored. A figure it did not send stays empty (the screener shows a dash); nothing is worked out from thin air.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..normalize import market

log = logging.getLogger("finlit.listing")
MIN_QUOTES = 1000          # a quote list shorter than this is a provider hiccup, never a market: keep the last good rows
MIN_SHARE = 0.5            # ...and so is one that covers under half of the symbols we list
STALE_TRADE_DAYS = 400    # last traded over a year ago: its price and 52-week range say nothing about today, so they are not shown
STALE_AFTER_HOURS = 6      # a refresh that ran this recently is not repeated (a restarted server must not hit the database and provider again)


def parse(payload: Any, universe: Dict[str, str]) -> List[dict]:
    """Quote list -> one clean record per listed company (only symbols in `universe`; values the provider did not send stay None)."""
    if not isinstance(payload, dict):
        return []
    out: List[dict] = []
    for sym in universe:
        raw = payload.get(sym)
        if not isinstance(raw, dict):
            continue
        q = market.quote({sym: raw}, sym)
        price = q.get("price")
        if price is None or price <= 0:    # no usable price: the company is not trading today; show no price rather than a stale or zero one
            price = None
        traded = q.get("asOf")
        when = datetime.fromisoformat(traded) if traded else None
        if when is not None and when.year < 2000:     # the provider's "never traded" placeholder (0001-01-01)
            when = None
        if when is not None and datetime.now(timezone.utc) - when > timedelta(days=STALE_TRADE_DAYS):
            continue
        out.append({
            "symbol": sym, "price": price, "change_pct": q.get("changePct") if price else None,
            "market_cap": q.get("marketCapCr") if (q.get("marketCapCr") or 0) > 0 else None,
            "high52": q.get("high52") if (q.get("high52") or 0) > 0 else None, "low52": q.get("low52") if (q.get("low52") or 0) > 0 else None,
            "volume": q.get("volume"), "traded_at": when,
        })
    return out


def metrics_of(r: dict) -> Dict[str, float]:
    """The screener figures a quote alone can give, worked out the way compute.py works them from a full report (same formulas, same names)."""
    out: Dict[str, float] = {}
    price, hi, lo = r.get("price"), r.get("high52"), r.get("low52")
    price = float(price) if price is not None else None
    hi = float(hi) if hi is not None else None
    lo = float(lo) if lo is not None else None
    for k in ("market_cap", "price"):
        if r.get(k) is not None:
            out[k] = float(r[k])
    if r.get("change_pct") is not None:
        out["ret_1d"] = float(r["change_pct"])
    if r.get("volume"):
        out["volume"] = float(r["volume"])
        if price is not None:
            out["turnover_cr"] = round(price * float(r["volume"]) / 1e7, 4)
    if hi:
        out["high_52w"] = hi
    if lo:
        out["low_52w"] = lo
    if hi and price is not None:
        out["pct_from_high"] = round((hi - price) / hi * 100, 4)
        out["near_high"] = 1.0 if out["pct_from_high"] <= 3 else 0.0
    if lo and price is not None:
        out["pct_from_low"] = round((price - lo) / lo * 100, 4)
        out["near_low"] = 1.0 if out["pct_from_low"] <= 3 else 0.0
    if hi is not None and lo is not None and hi > lo and price is not None:
        out["range_pos"] = round((price - lo) / (hi - lo) * 100, 4)
    return out


async def last_refresh(store) -> Optional[datetime]:
    async with store.pool.acquire() as conn:
        return await conn.fetchval("SELECT max(updated_at) FROM listing_quotes")


async def dhan_overlay(records: List[dict], store, dhan_client) -> int:
    """Where Dhan answers, its exchange quote replaces the provider's price, day change and volume (the day change is against the exchange's own previous
    close, which is what other sites show); market cap moves with the price. A company Dhan does not match or answers implausibly for keeps the provider's."""
    from .. import dhan
    if dhan_client is None or not dhan_client.configured or not records:
        return 0
    try:
        ids = await dhan.security_map(store, [r["symbol"] for r in records])
        raw = await dhan_client.quotes(sorted(set(ids.values())))
    except Exception:
        log.exception("Dhan quotes unavailable for the listing; the provider's figures are kept")
        return 0
    n = 0
    for r in records:
        q = dhan.to_quote(raw.get(ids.get(r["symbol"])) or {}) if r["symbol"] in ids else {}
        if not q or not q.get("price") or q.get("changePct") is None or not dhan.plausible(q, {"price": r["price"]} if r["price"] else {}):
            continue
        if r["market_cap"] and r["price"]:
            r["market_cap"] = round(r["market_cap"] * q["price"] / r["price"], 2)
        r["price"], r["change_pct"] = q["price"], q["changePct"]
        if q.get("volume"):
            r["volume"] = q["volume"]
        if q.get("asOf"):
            try:
                r["traded_at"] = datetime.fromisoformat(q["asOf"])
            except ValueError:
                pass
        n += 1
    return n


async def refresh_listing(client, store, force: bool = False, dhan_client=None) -> Dict[str, Any]:
    """Refresh the symbol list and every company's quote. Safe to run twice; refuses to replace good rows with a short or empty answer."""
    if not force:
        last = await last_refresh(store)
        if last is not None and (datetime.now(last.tzinfo) - last).total_seconds() < STALE_AFTER_HOURS * 3600:
            return {"skipped": "refreshed recently", "at": last.isoformat()}
    from ..worker import refresh_universe     # the symbol list first, so a newly listed company appears the same night
    await refresh_universe(client, store)
    async with store.pool.acquire() as conn:
        universe = {r["symbol"]: r["name"] for r in await conn.fetch("SELECT symbol, name FROM companies")}
    payload = await client.get("/quote", {}, timeout=90)   # with no symbol the provider answers with the whole market in one go
    records = parse(payload, universe)
    if len(records) < MIN_QUOTES or len(records) < MIN_SHARE * len(universe):
        log.warning("listing refresh refused: the provider sent %d quotes for %d listed companies; keeping the last good rows", len(records), len(universe))
        return {"refused": True, "quotes": len(records), "listed": len(universe)}
    from_dhan = await dhan_overlay(records, store, dhan_client)
    rows = [(r["symbol"], r["price"], r["change_pct"], r["market_cap"], r["high52"], r["low52"], r["volume"], r["traded_at"]) for r in records]
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("CREATE TEMP TABLE _lq (LIKE listing_quotes INCLUDING DEFAULTS) ON COMMIT DROP")
            await conn.copy_records_to_table("_lq", records=rows, columns=["symbol", "price", "change_pct", "market_cap", "high52", "low52", "volume", "traded_at"])
            await conn.execute(
                "INSERT INTO listing_quotes (symbol, price, change_pct, market_cap, high52, low52, volume, traded_at, updated_at) "
                "SELECT symbol, price, change_pct, market_cap, high52, low52, volume, traded_at, now() FROM _lq "
                "ON CONFLICT (symbol) DO UPDATE SET price = EXCLUDED.price, change_pct = EXCLUDED.change_pct, market_cap = EXCLUDED.market_cap, "
                "high52 = EXCLUDED.high52, low52 = EXCLUDED.low52, volume = EXCLUDED.volume, traded_at = EXCLUDED.traded_at, updated_at = now()")
            await conn.execute("DELETE FROM listing_quotes WHERE updated_at < now()")   # not in tonight's list: no price rather than an old one
    with_price = sum(1 for r in records if r["price"] is not None)
    log.info("listing refreshed: %d listed, %d quoted, %d with a price", len(universe), len(records), with_price)
    return {"listed": len(universe), "quoted": len(records), "withPrice": with_price, "fromDhan": from_dhan}
