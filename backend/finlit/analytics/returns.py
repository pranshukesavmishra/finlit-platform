"""One calculation for trailing returns, used everywhere (the old site had two that disagreed:
BPCL 1Y showed −15.41% in one panel and −16.2% in another)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from ..normalize.common import parse_date
from ..normalize.events import dividends_between

# (label, months back): by the calendar, so 3 years back from 19 Oct 2026 is 19 Oct 2023 whatever leap days lie between
PERIODS = [("1M", 1), ("3M", 3), ("6M", 6), ("1Y", 12), ("2Y", 24), ("3Y", 36), ("5Y", 60)]


def _months_back(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


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
    for label, months in PERIODS:
        target = _months_back(end_date, months)
        start = _close_on_or_before(dates, closes, target)
        # require real coverage: the first available close must be within a week of the target
        if not start or target - start[0] > timedelta(days=7) or not start[1]:
            out.append({"period": label, "price": None, "dividend": None, "total": None, "annualised": None})
            continue
        start_date, start_close = start
        price_return = (end_close / start_close - 1) * 100
        dividend_return = dividends_between(actions, start_date, end_date) / start_close * 100
        total = price_return + dividend_return
        years = months / 12
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
