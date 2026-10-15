"""One calculation for trailing returns, used everywhere (the old site had two that disagreed:
BPCL 1Y showed −15.41% in one panel and −16.2% in another)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from ..normalize.common import parse_date
from ..normalize.events import dividends_between

PERIODS = [("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365), ("2Y", 730), ("3Y", 1095), ("5Y", 1826)]


def _close_on_or_before(dates: List[date], closes: List[float], target: date) -> Optional[tuple]:
    lo, hi, found = 0, len(dates) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if dates[mid] <= target:
            found, lo = mid, mid + 1
        else:
            hi = mid - 1
    return (dates[found], closes[found]) if found is not None else None


def trailing_returns(history: dict, actions: List[dict]) -> List[dict]:
    """Price, dividend and total return per period, by calendar offset from the last close.
    Dividends use split/bonus-adjusted amounts with ex-date inside the window."""
    dates = [parse_date(t) for t in history.get("t", [])]
    closes = history.get("c", [])
    if not dates:
        return []
    end_date, end_close = dates[-1], closes[-1]
    out = []
    for label, days in PERIODS:
        start = _close_on_or_before(dates, closes, end_date - timedelta(days=days))
        # require real coverage: the first available close must be within a week of the target
        if not start or (end_date - timedelta(days=days)) - start[0] > timedelta(days=7) or not start[1]:
            out.append({"period": label, "price": None, "dividend": None, "total": None, "annualised": None})
            continue
        start_date, start_close = start
        price_return = (end_close / start_close - 1) * 100
        dividend_return = dividends_between(actions, start_date, end_date) / start_close * 100
        total = price_return + dividend_return
        years = days / 365.25
        annualised = ((1 + total / 100) ** (1 / years) - 1) * 100 if years > 1 and total > -100 else None
        out.append({
            "period": label,
            "price": round(price_return, 2),
            "dividend": round(dividend_return, 2),
            "total": round(total, 2),
            "annualised": round(annualised, 2) if annualised is not None else None,
        })
    return out


def dividend_yield_ttm(actions: List[dict], price: Optional[float], as_of: Optional[date]) -> Optional[float]:
    if not price or not as_of:
        return None
    paid = dividends_between(actions, as_of - timedelta(days=365), as_of)
    return round(paid / price * 100, 2) if paid else 0.0
