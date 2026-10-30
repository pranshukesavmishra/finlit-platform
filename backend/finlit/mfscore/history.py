"""Month-end NAVs -> everything the window metrics need (spec Sections 3 and 6, "Common definitions").

M is the fund's month-end NAVs oldest to newest (the stored series ends with the latest NAV, which can be a part month: the site's other figures
treat it the same way). r_t = M_t / M_(t-1) - 1 in percentage points. A month is INVALID when its NAV or the previous month's NAV is 0, negative or
missing (the return would divide by zero): it counts as missing in the 33-of-36 rule and raises the suspected NAV break flag.
W is the last 36 monthly returns (fewer for young funds). Nothing here touches a database."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from .sheets import FROZEN_VOL

W_LEN = 36
W_MIN_VALID = 33          # of 36: at most 3 missing months
MAX_HOLES = 3
MIN_MONTHS = 12           # under this: NOT RATED
MONTHS_ALL = 60           # at or above this: every metric
MONTHS_3Y = 36            # at or above this: the 3-year metrics (and rated)
WORST12_WINDOWS = 48


def month_key(d) -> int:
    """date or ordinal -> year * 12 + month - 1."""
    if isinstance(d, int):
        d = date.fromordinal(d)
    return d.year * 12 + d.month - 1


@dataclass
class Hist:
    months: int = 0                         # calendar months from the first to the last month-end NAV
    k: int = 0                              # returns expected in the window W (36, or fewer for a young fund)
    rets: Dict[int, float] = field(default_factory=dict)   # month key -> valid return (pp) inside W
    invalid: int = 0                        # invalid or missing months inside W
    window_ok: bool = False                 # enough valid months in W to use the window metrics
    vol_m: Optional[float] = None           # annualised standard deviation of W, pp
    frozen: bool = False                    # VOL_M < 0.01 pp: a stale or frozen NAV
    break_flag: bool = False                # suspected NAV break (invalid month in W, too many holes, or frozen)
    cred: float = 1.0                       # k / 36 for a window shorter than 36 months, else 1
    worst_month: Optional[float] = None     # pp
    neg_months: Optional[float] = None      # % of months in W with r_t < 0
    worst12: Optional[float] = None         # worst rolling 12-month return in the last 48 windows, pp
    underwater: Optional[float] = None      # % of the last 36 month-ends below the running peak
    fall: Optional[float] = None            # largest month-end fall over the last 36 months (pp, 0 or negative), own working
    all_valid: Dict[int, float] = field(default_factory=dict)   # every valid return, any age (not only W)


def _by_month(mdays: Sequence, mnavs: Sequence[float]) -> Dict[int, float]:
    by: Dict[int, float] = {}
    for d, v in zip(mdays, mnavs):
        by[month_key(d)] = v      # the stored series has one NAV per month; the last one wins if a caller sends two
    return by


def fall_from_months(by: Dict[int, float], first: int, last: int, months: int = 36) -> Optional[float]:
    """Largest fall (pp, 0 or negative) between month-end NAVs over the last `months` months (and the month before them, as the site's own month-end fall does).
    None when more than MAX_HOLES months in that stretch have no usable NAV."""
    start = max(first, last - months)
    pts = [(mk, by[mk]) for mk in range(start, last + 1) if mk in by and not math.isnan(by[mk]) and by[mk] > 0]
    span = last - start + 1
    if not pts or span - len(pts) > MAX_HOLES:
        return None
    peak, worst = pts[0][1], 0.0
    for _, v in pts:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst * 100


def compute(mdays: Sequence, mnavs: Sequence[float]) -> Hist:
    """All window figures of one fund. A series shorter than MIN_MONTHS gets `months` only: nothing else is worked out (the fund is NOT RATED)."""
    h = Hist()
    by = _by_month(mdays, mnavs)
    if not by:
        return h
    first, last = min(by), max(by)
    h.months = last - first + 1
    if h.months < MIN_MONTHS:
        return h
    ok = lambda mk: mk in by and by[mk] is not None and not math.isnan(by[mk]) and by[mk] > 0   # noqa: E731
    for mk in range(first + 1, last + 1):
        if ok(mk) and ok(mk - 1):
            h.all_valid[mk] = (by[mk] / by[mk - 1] - 1) * 100
    h.k = min(W_LEN, h.months - 1)
    slots = range(last - h.k + 1, last + 1)
    h.rets = {mk: h.all_valid[mk] for mk in slots if mk in h.all_valid}
    h.invalid = h.k - len(h.rets)
    need = W_MIN_VALID if h.k >= W_LEN else h.k - (W_LEN - W_MIN_VALID)
    h.window_ok = len(h.rets) >= max(need, MIN_MONTHS - 1)
    h.break_flag = h.invalid > 0
    h.cred = min(1.0, h.k / W_LEN)
    if h.window_ok:
        vals = list(h.rets.values())
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1) if len(vals) > 1 else 0.0
        h.vol_m = math.sqrt(var) * math.sqrt(12)
        if h.vol_m < FROZEN_VOL:
            h.frozen = True
            h.break_flag = True
        h.worst_month = min(vals)
        h.neg_months = 100.0 * sum(1 for v in vals if v < 0) / len(vals)
    else:
        h.break_flag = True    # too many holes or invalid months: the window cannot be trusted
    # worst rolling 12-month return on M within the last 48 windows
    best: Optional[float] = None
    for mk in range(max(first + 12, last - WORST12_WINDOWS + 1), last + 1):
        if ok(mk) and ok(mk - 12):
            r = (by[mk] / by[mk - 12] - 1) * 100
            best = r if best is None or r < best else best
    h.worst12 = best
    # underwater: share of the last 36 month-ends below the highest month-end NAV so far (peak counted from the start of the series)
    peak, below, seen = None, 0, 0
    lo = max(first, last - W_LEN + 1)
    for mk in range(first, last + 1):
        if not ok(mk):
            continue
        peak = by[mk] if peak is None else max(peak, by[mk])
        if mk >= lo:
            seen += 1
            below += 1 if by[mk] < peak else 0
    h.underwater = 100.0 * below / seen if seen >= 12 else None
    h.fall = fall_from_months(by, first, last)
    return h


def status_row(months: int) -> str:
    """The history rows of spec Section 3: which metrics are used and what status results."""
    if months >= MONTHS_ALL:
        return "all"
    if months >= MONTHS_3Y:
        return "three_year"
    if months >= MIN_MONTHS:
        return "window"
    return "none"
