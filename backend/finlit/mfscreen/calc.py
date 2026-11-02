"""The pure arithmetic of the nightly screener job. No database, no I/O: every function takes lists and returns numbers (or None when a figure cannot be worked out).

All risk figures read MONTH-END NAVs (mf_monthly) up to the last full calendar month, so every fund is on the same ruler and the figures describe the past only:
  window(by, end_mk, n)       n+1 month-end NAVs for the months end_mk-1-n .. end_mk-1 (a missing or stale month makes the whole window None)
  volatility                  sample standard deviation of the monthly returns x sqrt(12), in percent a year
  worst_loss                  the worst single month as a loss in percent (0 when no month fell)
  worst_rolling               the worst rolling 12 months as a loss in percent
  neg_share / below_high      share of months with a negative return / share of month-ends below an earlier high, percent
  down_capture                the fund's average return in the months the peer median fell, as a percentage of the peers' average in those months
  sharpe                      (3-year return - 6) / volatility with the assumed 6% the head-to-head page uses
  biggest_gain                the the largest single-month return in percent (negative when every month fell)
  downside_dev                downside deviation: root mean square of the monthly returns below 0 (others count as 0) x sqrt(12), in percent a year
  calendar_return             one calendar year: December month-end NAV over the previous December's, in percent
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Dict, List, Optional, Sequence

MIN_PEERS = 3
RISK_FREE = 6.0
MAX_STALE_DAYS = 7      # a month-end NAV may be this many days before the month's last day (weekends, holidays), as mf.MAX_STALE


def month_key(d: date) -> int:
    return d.year * 12 + d.month - 1


def month_last(mk: int) -> date:
    y, m = divmod(mk, 12)
    nxt = date(y + (m + 1) // 12, (m + 1) % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def by_month(days: Sequence[date], navs: Sequence[float]) -> Dict[int, float]:
    """{month key: month-end NAV} of the stored series, dropping any month whose NAV is far from the month's end or not positive."""
    out: Dict[int, float] = {}
    for d, v in zip(days, navs):
        if v is None or not v > 0:
            continue
        mk = month_key(d)
        if (month_last(mk) - d).days <= MAX_STALE_DAYS:
            out[mk] = v
    return out


def window(by: Dict[int, float], end_mk: int, n: int) -> Optional[List[float]]:
    """The n+1 month-end NAVs of the months end_mk-1-n .. end_mk-1, or None when any is missing."""
    pts = []
    for mk in range(end_mk - 1 - n, end_mk):
        v = by.get(mk)
        if v is None:
            return None
        pts.append(v)
    return pts


def returns(navs: Sequence[float]) -> List[float]:
    return [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))]


def volatility(rets: Sequence[float]) -> Optional[float]:
    if len(rets) < 3:
        return None
    return statistics.stdev(rets) * math.sqrt(12) * 100


def worst_loss(rets: Sequence[float]) -> Optional[float]:
    return None if not rets else max(0.0, -min(rets)) * 100


def worst_rolling(navs: Sequence[float], months: int = 12) -> Optional[float]:
    """Worst rolling `months`-month return over a window of month-end NAVs, as a loss in percent (0 when none was negative)."""
    if len(navs) <= months:
        return None
    worst = min(navs[i] / navs[i - months] - 1 for i in range(months, len(navs)))
    return max(0.0, -worst) * 100


def biggest_gain(rets: Sequence[float]) -> Optional[float]:
    return None if not rets else max(rets) * 100


def downside_dev(rets: Sequence[float]) -> Optional[float]:
    """Like volatility, but only the months that fell count (a month that rose counts as 0), measured from 0 rather than from the average."""
    if len(rets) < 3:
        return None
    return math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets)) * math.sqrt(12) * 100


def calendar_return(by: Dict[int, float], year: int) -> Optional[float]:
    """Return over the calendar `year` from the stored month-end NAVs of December `year`-1 and December `year`; None when either is missing."""
    a, b = by.get((year - 1) * 12 + 11), by.get(year * 12 + 11)
    return None if a is None or b is None else (b / a - 1) * 100


def neg_share(rets: Sequence[float]) -> Optional[float]:
    return None if not rets else sum(1 for r in rets if r < 0) / len(rets) * 100


def below_high(navs: Sequence[float]) -> Optional[float]:
    """Of the month-ends after the first, the share that closed below the highest month-end before them."""
    if len(navs) < 2:
        return None
    high, below = navs[0], 0
    for v in navs[1:]:
        if v < high:
            below += 1
        high = max(high, v)
    return below / (len(navs) - 1) * 100


def median(vals: Sequence[float]) -> Optional[float]:
    v = [x for x in vals if x is not None and not math.isnan(x)]
    return statistics.median(v) if v else None


def peer_median_months(rets_by_scheme: Sequence[Dict[int, float]]) -> Dict[int, float]:
    """{month: median monthly return of the peers that have that month}, for months with at least MIN_PEERS peers."""
    pool: Dict[int, List[float]] = {}
    for r in rets_by_scheme:
        for mk, v in r.items():
            pool.setdefault(mk, []).append(v)
    return {mk: statistics.median(v) for mk, v in pool.items() if len(v) >= MIN_PEERS}


def down_capture(own: Dict[int, float], peer: Dict[int, float]) -> Optional[float]:
    """Average own return in the months the peer median was negative, over the peer median's average in those months, in percent.
    100 means the fund fell as much as its peers in their bad months, below 100 less. Needs three bad months."""
    bad = [mk for mk, m in peer.items() if m < 0 and mk in own]
    if len(bad) < 3:
        return None
    pm = sum(peer[mk] for mk in bad) / len(bad)
    if pm >= 0:
        return None
    return sum(own[mk] for mk in bad) / len(bad) / pm * 100


def consistency(own: Dict[int, float], peer: Dict[int, float], need: int = 30) -> Optional[float]:
    """Share of the months the fund beat the peer median, among the months both have a figure."""
    both = [mk for mk in peer if mk in own]
    if len(both) < need:
        return None
    return sum(1 for mk in both if own[mk] > peer[mk]) / len(both) * 100


def sharpe(r3y: Optional[float], vol: Optional[float]) -> Optional[float]:
    if r3y is None or vol is None or vol <= 0:
        return None
    return (r3y - RISK_FREE) / vol


def rank_desc(value: float, values: Sequence[float]) -> int:
    """1 + how many are strictly greater: ties share the better rank."""
    return 1 + sum(1 for v in values if v > value)


def fee_share(ter: Optional[float], r3y: Optional[float]) -> Optional[float]:
    if ter is None or r3y is None or ter < 0 or r3y + ter <= 0:
        return None
    return ter / (r3y + ter) * 100
