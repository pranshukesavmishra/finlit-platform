"""The scoring toolkit of the specification (Section 4) and the zero-value rules of v1.1 (Appendix Z).

Rule 8 of the design: a zero is a value, a null is a gap. Test for a gap with is_missing(x), never `if not x`: in Python 0 is falsy, which
would silently turn every real zero (no fall, no exit load, 0% premium, risk-o-meter Low) into a gap."""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Dict, Hashable, Iterable, List, Optional, Sequence, Tuple


def is_missing(x) -> bool:
    """True for None and NaN; False for every number, zero included."""
    if x is None:
        return True
    try:
        return math.isnan(x)
    except TypeError:
        return False


def scale(value, worst, best) -> Optional[float]:
    """Points 0 to 100: worst scores 0, best scores 100, a straight line between, clipped. worst > best is fine (smaller is better).
    None for a missing value (the caller assigns state F). 50 when the limits collapse (worst == best): no spread, nothing to reward."""
    if is_missing(value):
        return None
    if best == worst:
        return 50.0
    points = (value - worst) / (best - worst) * 100
    return max(0.0, min(100.0, points))


def safe_ratio(num: float, den: float, floor: float) -> float:
    """num / max(den, floor): the denominator may be 0, the floor never is."""
    return num / max(den, floor)


def pillar(points: Sequence[Optional[float]], weights: Sequence[float]) -> float:
    """Weighted mean of the points of a pillar. A None point is state N (does not apply): its weight leaves the sum and the pillar is
    re-divided over the rest. When nothing is left the pillar is a neutral 50 (the caller flags it F in the data confidence)."""
    w = sum(wt for p, wt in zip(points, weights) if p is not None)
    if w == 0:
        return 50.0
    return sum(p * wt for p, wt in zip(points, weights) if p is not None) / w


def pillar_all_n(points: Sequence[Optional[float]], weights: Sequence[float] = ()) -> bool:
    """True when every metric of the pillar is N (the pillar is then the neutral 50)."""
    return all(p is None for p in points) or (bool(weights) and sum(wt for p, wt in zip(points, weights) if p is not None) == 0)


def median(values: Iterable[float]) -> Optional[float]:
    s = sorted(v for v in values if not is_missing(v))
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


class MedianBook:
    """Values of a set of funds, answering 'the median of everyone else' in O(log n): the fund itself is never in its own peer median
    (matters in small groups). `exclude` is the key of the fund asking; a key that is not in the book leaves the median untouched."""

    def __init__(self, items: Iterable[Tuple[Hashable, float]]):
        self.vals: Dict[Hashable, float] = {}
        for k, v in items:
            if not is_missing(v):
                self.vals[k] = v
        self.arr: List[float] = sorted(self.vals.values())

    def __len__(self) -> int:
        return len(self.arr)

    def count_excluding(self, exclude: Optional[Hashable] = None) -> int:
        return len(self.arr) - (1 if exclude is not None and exclude in self.vals else 0)

    def median(self, exclude: Optional[Hashable] = None) -> Tuple[Optional[float], int]:
        """(median of the others, how many others)."""
        arr, n = self.arr, len(self.arr)
        pos = bisect_left(arr, self.vals[exclude]) if exclude is not None and exclude in self.vals else None
        m = n - (1 if pos is not None else 0)
        if m <= 0:
            return None, 0

        def get(i: int) -> float:
            return arr[i] if pos is None or i < pos else arr[i + 1]
        mid = m // 2
        return (get(mid) if m % 2 else (get(mid - 1) + get(mid)) / 2), m
