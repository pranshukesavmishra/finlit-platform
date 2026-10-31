"""Longer price history for the Leader / Laggard reliability backtest.

The reports keep weekly closes for about six years (the `price-MAX` section). The backtest needs about twenty to judge whether leadership has held, so this
job asks the data provider's daily-quotes endpoint for everything back to 2004, keeps the weekly closes only, and stores them in `price_history_long`.
It is resumable and gentle: a few hundred companies a night, biggest first, each tried once per 90 days, and it stops at a time limit.
Whatever the provider returns is what is kept; if it has nothing before 2020 the row says so and the reliability card keeps saying "Not enough history".
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .normalize import market

log = logging.getLogger("finlit.history")
FROM_YEAR = 2004
RETRY_DAYS = 90


def weekly_closes(payload: Any) -> Tuple[List[date], List[float]]:
    """Weekly closes (last trading day of each ISO week) from a daily-quotes payload, bad ticks removed, oldest first."""
    daily = market.price_history(payload)
    wk = market.weekly(daily)
    return [date.fromisoformat(d) for d in wk["t"]], [float(c) for c in wk["c"]]


def splice(recent_dates: Sequence[date], recent_closes: Sequence[float], old_dates: Sequence[date], old_closes: Sequence[float]) -> Tuple[List[date], List[float]]:
    """Older weekly closes put in front of the report's own, scaled so the two agree where they meet (so a different adjustment for splits in the older
    file cannot make a jump). Nothing is added unless the two overlap within a week of the join."""
    if not recent_dates or not old_dates:
        return list(recent_dates), list(recent_closes)
    d0, c0 = recent_dates[0], recent_closes[0]
    near = [(abs((d - d0).days), i) for i, d in enumerate(old_dates) if abs((d - d0).days) <= 7]
    if not near:
        return list(recent_dates), list(recent_closes)
    i = min(near)[1]
    if old_closes[i] <= 0:
        return list(recent_dates), list(recent_closes)
    k = c0 / old_closes[i]
    pre = [(d, c * k) for d, c in zip(old_dates, old_closes) if d < d0]
    return [d for d, _ in pre] + list(recent_dates), [c for _, c in pre] + list(recent_closes)


async def candidates(store, limit: int, results_first: bool = False) -> List[str]:
    """Companies with a stored report that have not been tried in the last 90 days, biggest first.
    `results_first` puts the companies that declared results in the last 120 days in front (the results calendar shows their all-time high)."""
    async with store.pool.acquire() as conn:
        if results_first:
            rows = await conn.fetch(
                "SELECT s.symbol FROM (SELECT DISTINCT symbol FROM snapshots WHERE section = 'price-MAX') s "
                "LEFT JOIN listing_quotes q ON q.symbol = s.symbol LEFT JOIN price_history_long h ON h.symbol = s.symbol "
                "WHERE h.symbol IS NULL OR h.tried_at < now() - make_interval(days => $1) "
                "ORDER BY (EXISTS (SELECT 1 FROM feed_items c WHERE c.kind = 'result' AND c.symbol = s.symbol AND c.item_date > current_date - 120)) DESC, "
                "q.market_cap DESC NULLS LAST, s.symbol LIMIT $2", RETRY_DAYS, limit)
            return [r["symbol"] for r in rows]
        rows = await conn.fetch(
            "SELECT s.symbol FROM (SELECT DISTINCT symbol FROM snapshots WHERE section = 'price-MAX') s "
            "LEFT JOIN listing_quotes q ON q.symbol = s.symbol LEFT JOIN price_history_long h ON h.symbol = s.symbol "
            "WHERE h.symbol IS NULL OR h.tried_at < now() - make_interval(days => $1) "
            "ORDER BY q.market_cap DESC NULLS LAST, s.symbol LIMIT $2", RETRY_DAYS, limit)
    return [r["symbol"] for r in rows]


async def backfill(client, store, *, limit: int = 300, max_minutes: float = 60.0, from_year: int = FROM_YEAR, results_first: bool = False) -> Dict[str, Any]:
    started = time.monotonic()
    year = date.today().year
    done = empty = failed = 0
    oldest: Optional[date] = None
    for sym in await candidates(store, limit, results_first):
        if time.monotonic() - started > max_minutes * 60:
            break
        try:
            payload = await client.get(f"/daily-quotes/{sym}", {"from": str(from_year), "to": str(year)}, timeout=60, retries=1)
            dates, closes = weekly_closes(payload)
        except Exception as exc:   # one company failing never stops the run; it is tried again after 90 days (or sooner when the row is deleted)
            failed += 1
            log.warning("long history for %s not stored: %s", sym, type(exc).__name__)
            continue
        first = dates[0] if dates else None
        top = max(range(len(closes)), key=closes.__getitem__) if closes else None   # the highest close: the company's all-time high on our data
        ath, ath_date = (closes[top], dates[top]) if top is not None and closes[top] > 0 else (None, None)
        async with store.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO price_history_long (symbol, dates, closes, first_date, ath, ath_date, tried_at) VALUES ($1, $2, $3, $4, $5, $6, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET dates = EXCLUDED.dates, closes = EXCLUDED.closes, first_date = EXCLUDED.first_date, "
                "ath = EXCLUDED.ath, ath_date = EXCLUDED.ath_date, tried_at = now()", sym, dates, closes, first, ath, ath_date)
        done += 1
        empty += 0 if dates else 1
        if first and (oldest is None or first < oldest):
            oldest = first
    out = {"stored": done, "empty": empty, "failed": failed, "oldest": oldest.isoformat() if oldest else None, "minutes": round((time.monotonic() - started) / 60, 1)}
    log.info("history backfill %s", out)
    return out
