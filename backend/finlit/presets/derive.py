"""The nightly numbers behind the screens (spec p6 and p16): the momentum score, the growth score and the outlier caps. Pure functions of the screener Table.

Universe for every percentile: stocks with a market cap of Rs 1,000 Cr or more (the liquidity floor of the spec's ground rules).
Percentile of a value = its average rank among the universe's known values, scaled to 0..1 (lowest 0, highest 1; ties share the average rank; a single
known value is 0.5). A stock with a missing figure has no percentile for it (it is never treated as zero).
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

UNIVERSE_FLOOR = 1000.0         # Rs crore
MOMENTUM_W = (("ret_3m", 0.3), ("ret_6m", 0.4), ("ret_1y", 0.3))
GROWTH_PARTS = ("sales_cagr_3y", "profit_cagr_3y", "q_sales_yoy", "q_profit_yoy")
QUARTER_PARTS = ("q_sales_yoy", "q_profit_yoy")
QUARTER_CAP = 200.0             # quarter growth is capped at 200 %
QUARTER_MIN_SALES = 50.0        # ...and needs latest-quarter sales of Rs 50 Cr or more (small bases give values like 1,797,150 %)
GROWTH_WINSOR = (0.05, 0.95)    # each growth number is capped at its 5th and 95th percentile before it is ranked
OUTLIER_P = (0.01, 0.99)        # screens 5, 9, 14, 16: capped at the 1st and 99th percentile before ranking
MIN_GROWTH_PARTS = 2            # a growth score needs at least two of its four numbers (the two quarter ones drop out for a small quarterly base)
OUTLIER_FIELDS = ("roce", "q_profit_yoy", "q_sales_yoy", "volatility", "sales_cagr_3y", "profit_cagr_3y")


def _known(v) -> bool:
    return v is not None and v == v


def quantile(sorted_xs: Sequence[float], p: float) -> float:
    """Linear-interpolated quantile of an ascending list (p in 0..1)."""
    n = len(sorted_xs)
    if n == 0:
        return float("nan")
    if n == 1:
        return float(sorted_xs[0])
    pos = min(max(p, 0.0), 1.0) * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return float(sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo))


def pct_ranks(values: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Percentile 0..1 of every known value among the known values (average rank for ties); unknown stays None."""
    idx = [i for i, v in enumerate(values) if _known(v)]
    n = len(idx)
    out: List[Optional[float]] = [None] * len(values)
    if n == 0:
        return out
    if n == 1:
        out[idx[0]] = 0.5
        return out
    order = sorted(idx, key=lambda i: values[i])
    pos = 0
    while pos < n:
        end = pos
        while end + 1 < n and values[order[end + 1]] == values[order[pos]]:
            end += 1
        avg_rank = (pos + end) / 2.0          # 0-based average rank of the tied block
        for j in range(pos, end + 1):
            out[order[j]] = avg_rank / (n - 1)
        pos = end + 1
    return out


def winsorize(values: Sequence[Optional[float]], lo_p: float, hi_p: float) -> List[Optional[float]]:
    """Known values clipped to the lo_p and hi_p quantiles of the known values."""
    xs = sorted(v for v in values if _known(v))
    if not xs:
        return list(values)
    lo, hi = quantile(xs, lo_p), quantile(xs, hi_p)
    return [min(max(v, lo), hi) if _known(v) else None for v in values]


def universe(table, floor: float = UNIVERSE_FLOOR) -> List[int]:
    mc = table.cols["market_cap"]
    return [i for i in range(table.n) if _known(mc[i]) and mc[i] >= floor]


def _col(table, key: str, idx: Sequence[int]) -> List[Optional[float]]:
    c = table.cols[key]
    return [c[i] if c[i] == c[i] else None for i in idx]


def momentum_scores(table, floor: float = UNIVERSE_FLOOR) -> Dict[str, float]:
    """100 x (0.3 x P3M + 0.4 x P6M + 0.3 x P12M); needs all three returns. Returns symbol -> score for the universe."""
    idx = universe(table, floor)
    pcts = {k: pct_ranks(_col(table, k, idx)) for k, _ in MOMENTUM_W}
    out: Dict[str, float] = {}
    for n, i in enumerate(idx):
        ps = [pcts[k][n] for k, _ in MOMENTUM_W]
        if all(p is not None for p in ps):
            out[table.symbols[i]] = round(100.0 * sum(w * p for (_, w), p in zip(MOMENTUM_W, ps)), 2)
    return out


def growth_scores(table, floor: float = UNIVERSE_FLOOR) -> Dict[str, float]:
    """Average percentile (x100) of the four growth numbers, each capped at its 5th/95th percentile first. Quarter growth is capped at 200 % and counts
    only when the latest quarter's sales are Rs 50 Cr or more. Needs at least MIN_GROWTH_PARTS of the four."""
    idx = universe(table, floor)
    qsales = _col(table, "q_revenue", idx)
    cols: Dict[str, List[Optional[float]]] = {}
    for k in GROWTH_PARTS:
        vals = _col(table, k, idx)
        if k in QUARTER_PARTS:
            vals = [min(v, QUARTER_CAP) if (_known(v) and _known(q) and q >= QUARTER_MIN_SALES) else None for v, q in zip(vals, qsales)]
        cols[k] = pct_ranks(winsorize(vals, *GROWTH_WINSOR))
    out: Dict[str, float] = {}
    for n, i in enumerate(idx):
        ps = [cols[k][n] for k in GROWTH_PARTS if cols[k][n] is not None]
        if len(ps) >= MIN_GROWTH_PARTS:
            out[table.symbols[i]] = round(100.0 * sum(ps) / len(ps), 2)
    return out


def outlier_caps(table, fields: Iterable[str] = OUTLIER_FIELDS, floor: float = UNIVERSE_FLOOR) -> Dict[str, Tuple[float, float]]:
    """field -> (1st percentile, 99th percentile) over the universe. Applied when ranking (the stored figure is never altered). Quarter growth is
    also held to 200 %."""
    idx = universe(table, floor)
    out: Dict[str, Tuple[float, float]] = {}
    for k in fields:
        if k not in table.cols:
            continue
        xs = sorted(v for v in _col(table, k, idx) if _known(v))
        if not xs:
            continue
        lo, hi = quantile(xs, OUTLIER_P[0]), quantile(xs, OUTLIER_P[1])
        if k in QUARTER_PARTS:
            hi = min(hi, QUARTER_CAP)
            lo = min(lo, hi)
        out[k] = (round(lo, 4), round(hi, 4))
    return out
