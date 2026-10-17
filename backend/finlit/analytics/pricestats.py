"""Price statistics behind the chart lab: monthly returns, drawdown, rolling volatility, the distribution of daily moves and
yearly box plots. Computed once at ingest from the cleaned daily history, so the browser only draws."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional

BIN = 0.25  # histogram bin width, in percentage points
BIN_LIMIT = 5.0  # moves beyond this fall into the two outer bins


def _r(v: Optional[float], d: int = 2) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(v, d)


def _quantile(sorted_vals: List[float], q: float) -> float:
    pos = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def daily_returns(closes: List[float]) -> List[Optional[float]]:
    return [None] + [((closes[i] / closes[i - 1]) - 1) * 100 if closes[i - 1] else None for i in range(1, len(closes))]


def monthly_returns(dates: List[str], closes: List[float]) -> dict:
    """Return of each calendar month: last close of the month against the last close of the month before."""
    last: Dict[tuple, float] = {}
    order: List[tuple] = []
    for t, c in zip(dates, closes):
        key = (int(t[:4]), int(t[5:7]))
        if key not in last:
            order.append(key)
        last[key] = c
    rows: Dict[int, List[Optional[float]]] = defaultdict(lambda: [None] * 12)
    prev = closes[0] if closes else None
    for i, key in enumerate(order):
        close = last[key]
        base = prev if i else closes[0]
        # the first month is measured from the first close on file, so it is a partial month
        if base:
            rows[key[0]][key[1] - 1] = _r(((close / base) - 1) * 100, 1)
        prev = close
    years = sorted(rows)
    return {"years": years, "rows": {str(y): rows[y] for y in years}}


def drawdown(dates: List[str], closes: List[float], max_points: int = 420) -> dict:
    peak, series = 0.0, []
    worst, worst_day = 0.0, None
    for t, c in zip(dates, closes):
        peak = max(peak, c)
        dd = (c / peak - 1) * 100 if peak else 0.0
        series.append(dd)
        if dd < worst:
            worst, worst_day = dd, t
    step = max(1, len(series) // max_points)
    # keep the deepest point inside each sampling window so a sharp fall is never smoothed away
    t_out, d_out = [], []
    for i in range(0, len(series), step):
        window = series[i:i + step]
        j = min(range(len(window)), key=lambda k: window[k])
        t_out.append(dates[i + j])
        d_out.append(_r(window[j], 2))
    return {"t": t_out, "dd": d_out, "max": {"pct": _r(worst, 1), "date": worst_day},
            "current": _r(series[-1], 1) if series else None}


def rolling_volatility(dates: List[str], closes: List[float], window: int = 60, max_points: int = 420) -> dict:
    rets = daily_returns(closes)
    vol: List[Optional[float]] = [None] * len(closes)
    for i in range(window, len(closes)):
        w = [x for x in rets[i - window + 1:i + 1] if x is not None]
        if len(w) == window:
            m = sum(w) / window
            vol[i] = math.sqrt(sum((x - m) ** 2 for x in w) / (window - 1)) * math.sqrt(252)
    step = max(1, len(vol) // max_points)
    idx = [i for i in range(0, len(vol), step) if vol[i] is not None]
    last = next((v for v in reversed(vol) if v is not None), None)
    clean = [v for v in vol if v is not None]
    return {"t": [dates[i] for i in idx], "vol": [_r(vol[i], 1) for i in idx], "window": window, "current": _r(last, 1),
            "median": _r(sorted(clean)[len(clean) // 2], 1) if clean else None}


def histogram(closes: List[float]) -> dict:
    rets = [x for x in daily_returns(closes) if x is not None]
    if not rets:
        return {"bins": [], "counts": [], "binWidth": BIN}
    n = int(round(BIN_LIMIT * 2 / BIN))
    counts = [0] * n
    for x in rets:
        counts[min(n - 1, max(0, int((max(-BIN_LIMIT, min(BIN_LIMIT - 1e-9, x)) + BIN_LIMIT) / BIN)))] += 1
    return {"binWidth": BIN, "from": -BIN_LIMIT, "counts": counts, "days": len(rets),
            "upShare": _r(sum(1 for x in rets if x > 0) / len(rets) * 100, 1), "best": _r(max(rets), 1), "worst": _r(min(rets), 1),
            "clipped": sum(1 for x in rets if abs(x) >= BIN_LIMIT)}


def yearly_box(dates: List[str], closes: List[float]) -> dict:
    by_year: Dict[int, List[float]] = defaultdict(list)
    for t, x in zip(dates, daily_returns(closes)):
        if x is not None:
            by_year[int(t[:4])].append(x)
    out = []
    for y in sorted(by_year):
        v = sorted(by_year[y])
        if len(v) < 5:
            continue
        q1, med, q3 = _quantile(v, 0.25), _quantile(v, 0.5), _quantile(v, 0.75)
        lo_fence, hi_fence = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        inside = [x for x in v if lo_fence <= x <= hi_fence]
        outliers = sorted((x for x in v if x < lo_fence or x > hi_fence), key=abs, reverse=True)[:8]
        out.append({"year": y, "q1": _r(q1), "median": _r(med), "q3": _r(q3), "low": _r(min(inside)), "high": _r(max(inside)),
                    "outliers": [_r(x, 1) for x in outliers], "days": len(v)})
    return {"years": out}


def build(history: dict) -> dict:
    dates, closes = history.get("t", []), history.get("c", [])
    if len(closes) < 30:
        return {"available": False}
    first = closes[0]
    years = max((len(closes) / 252), 0.01)
    return {
        "available": True, "sessions": len(closes), "from": dates[0], "to": dates[-1],
        "cagrPct": _r(((closes[-1] / first) ** (1 / years) - 1) * 100, 1) if first and closes[-1] > 0 else None,
        "monthly": monthly_returns(dates, closes), "drawdown": drawdown(dates, closes),
        "volatility": rolling_volatility(dates, closes), "histogram": histogram(closes), "box": yearly_box(dates, closes),
    }
