"""Revenue and profit forecast model, per the team's methodology (docs/outlook/METHOD.md). Pure functions: no I/O.

  weighted growth rate   g = sum(w_i * x_i), the weights of the chosen horizon column (short 1 year, mid 3 years, long 5 years), total 100
  iterative forecast     V(t+1) = V(t) * (1 + g)   (the same weighted rate is held for every forecast year: no year-specific inputs are stored)
  inputs x_i             company growth over 1 year (year on year), 3 and 5 years (CAGR); the sector's MEDIAN of the same three; for profit also the
                         relative change of the net profit margin. Percent figures.
  data rules             a missing input drops out and the others are re-normalised to 100; every input is limited to +/- INPUT_CAP percent and says
                         when it was; profit is adjusted for one-off items first; a loss or near-zero profit base uses an absolute-change method.
Profit is forecast directly by its own growth rate. It is never also built as revenue x margin.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

INPUT_CAP = 50.0          # each growth input is limited to -50% .. +50% a year (winsorised) before it is weighted
NEAR_ZERO_MARGIN = 0.005  # a profit under 0.5% of that year's revenue counts as near zero for the growth ratio
MIN_PEERS = 5             # fewest peer companies for a sector median
ONE_OFF_SHARE = 0.10      # one-off items below this share of net profit are left in
HISTORY_YEARS = 8

HORIZONS: Dict[str, dict] = {
    "short": {"key": "short", "years": 1, "label": "Short-term", "span": "1 year (FY+1)"},
    "mid": {"key": "mid", "years": 3, "label": "Mid-term", "span": "3 years (FY+1 to FY+3)"},
    "long": {"key": "long", "years": 5, "label": "Long-term", "span": "5 years (FY+1 to FY+5)"},
}

# parameter key -> (label, who, growth window in years). Order is the order of the table.
PARAMS: Dict[str, List[Tuple[str, str, str, int]]] = {
    "revenue": [("co_1y", "Company revenue growth (1Y)", "company", 1), ("co_3y", "Company revenue CAGR (3Y)", "company", 3), ("co_5y", "Company revenue CAGR (5Y)", "company", 5),
                ("sec_1y", "Sector revenue growth (1Y)", "sector", 1), ("sec_3y", "Sector revenue CAGR (3Y)", "sector", 3), ("sec_5y", "Sector revenue CAGR (5Y)", "sector", 5)],
    "profit": [("co_1y", "Company net profit growth (1Y)", "company", 1), ("co_3y", "Company net profit CAGR (3Y)", "company", 3), ("co_5y", "Company net profit CAGR (5Y)", "company", 5),
               ("sec_1y", "Sector net profit growth (1Y)", "sector", 1), ("sec_3y", "Sector net profit CAGR (3Y)", "sector", 3), ("sec_5y", "Sector net profit CAGR (5Y)", "sector", 5),
               ("margin", "Net profit margin trend", "company", 1)],
}
# The team's proposed starting weights (percent), by horizon. Not optimised: see docs/outlook/BACKTEST.md.
WEIGHTS: Dict[str, Dict[str, Dict[str, float]]] = {
    "revenue": {"short": {"co_1y": 50, "co_3y": 10, "co_5y": 5, "sec_1y": 25, "sec_3y": 5, "sec_5y": 5},
                "mid": {"co_1y": 10, "co_3y": 40, "co_5y": 10, "sec_1y": 20, "sec_3y": 10, "sec_5y": 10},
                "long": {"co_1y": 5, "co_3y": 15, "co_5y": 40, "sec_1y": 20, "sec_3y": 5, "sec_5y": 15}},
    "profit": {"short": {"co_1y": 35, "co_3y": 10, "co_5y": 5, "sec_1y": 25, "sec_3y": 5, "sec_5y": 5, "margin": 15},
               "mid": {"co_1y": 10, "co_3y": 25, "co_5y": 10, "sec_1y": 20, "sec_3y": 10, "sec_5y": 10, "margin": 15},
               "long": {"co_1y": 5, "co_3y": 15, "co_5y": 30, "sec_1y": 20, "sec_3y": 5, "sec_5y": 15, "margin": 10}},
}
SECTOR_COLUMNS = {"revenue": {"sec_1y": "sales_growth", "sec_3y": "sales_cagr_3y", "sec_5y": "sales_cagr_5y"},
                  "profit": {"sec_1y": "profit_growth", "sec_3y": "profit_cagr_3y", "sec_5y": "profit_cagr_5y"}}


class WeightError(ValueError):
    pass


def default_weights(kind: str, horizon: str) -> Dict[str, float]:
    return dict(WEIGHTS[kind][horizon])


def validate_weights(kind: str, weights: Optional[Dict[str, float]], horizon: str, normalise: bool = False) -> Dict[str, float]:
    """None -> the model's column for the horizon. Otherwise every parameter of the kind, each 0-100, total 100 within 0.01 (or scaled to 100 when
    `normalise` is asked for, unless they are all zero)."""
    if weights is None:
        return default_weights(kind, horizon)
    keys = {p[0] for p in PARAMS[kind]}
    if set(weights) != keys:
        extra, missing = sorted(set(weights) - keys), sorted(keys - set(weights))
        raise WeightError("Unknown parameter: " + ", ".join(extra) if extra else "Missing parameter: " + ", ".join(missing))
    out: Dict[str, float] = {}
    for k, v in weights.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 100:
            raise WeightError(f"{k}: each percentage must be between 0 and 100.")
        out[k] = float(v)
    total = sum(out.values())
    if normalise:
        if total <= 0:
            raise WeightError("The percentages are all zero, so they cannot be scaled to 100.")
        return {k: round(v / total * 100, 4) for k, v in out.items()}
    if abs(total - 100) > 0.01:
        raise WeightError(f"The percentages must total 100 (they total {total:.2f}).")
    return out


# ---------------------------------------------------------------------------------------------------------- growth arithmetic
def yoy(begin: Optional[float], end: Optional[float]) -> Optional[float]:
    """Year-on-year growth in percent; undefined unless the beginning is positive."""
    if begin is None or end is None or begin <= 0:
        return None
    return (end / begin - 1) * 100


def cagr(begin: Optional[float], end: Optional[float], years: int) -> Optional[float]:
    """Compound yearly growth in percent: (end / begin) ** (1 / years) - 1. Undefined unless both ends are positive and years >= 1."""
    if begin is None or end is None or years < 1 or begin <= 0 or end <= 0:
        return None
    return ((end / begin) ** (1 / years) - 1) * 100


def cap(v: float) -> Tuple[float, bool]:
    c = max(-INPUT_CAP, min(INPUT_CAP, v))
    return c, c != v


@dataclass
class Hist:
    """One company's yearly history, oldest first: fiscal year labels, revenue, and net profit already adjusted for one-off items."""
    fy: List[str] = field(default_factory=list)
    revenue: List[Optional[float]] = field(default_factory=list)
    profit: List[Optional[float]] = field(default_factory=list)
    adjusted: List[str] = field(default_factory=list)   # years whose profit was adjusted, for the page

    def upto(self, n: int) -> "Hist":
        return Hist(self.fy[:n], self.revenue[:n], self.profit[:n], [p for p in self.adjusted if p in self.fy[:n]])


def adjust_profit(net: Optional[float], continuing: Optional[float], exceptional: Optional[float], tax: Optional[float], pbt: Optional[float]) -> Tuple[Optional[float], bool]:
    """Net profit without one-offs: the continuing figure when stored (profit from discontinued operations taken out), then material exceptional items
    taken out after tax at the year's own tax rate (kept within 0-35%, 25% when it cannot be worked out). Returns (profit, adjusted?)."""
    base = continuing if continuing is not None else net
    changed = continuing is not None and net is not None and continuing != net
    if base is None:
        return None, False
    if exceptional not in (None, 0) and abs(exceptional) >= ONE_OFF_SHARE * abs(base):   # type: ignore[operator]
        rate = 0.25
        if tax is not None and pbt is not None and pbt > 0:
            rate = max(0.0, min(0.35, tax / pbt))
        return base - exceptional * (1 - rate), True   # type: ignore[operator]
    return base, changed


def hist_from_inputs(inp, lender_total_income: bool = True) -> Hist:
    """Hist from the stored yearly P&L (see inputs.Inputs). Banks and lenders use total income as their revenue line when it is stored."""
    h = Hist()
    rev_key = "total_income" if inp.lender and lender_total_income and inp.pl.get("total_income") else "revenue"
    for p in inp.fy:
        g = lambda k: (inp.pl.get(k) or {}).get(p)  # noqa: E731
        h.fy.append(p)
        h.revenue.append(g(rev_key))
        prof, adj = adjust_profit(g("net_profit"), g("net_profit_continuing"), g("exceptional_items"), g("tax"), g("profit_before_tax"))
        h.profit.append(prof)
        if adj:
            h.adjusted.append(p)
    return h


# ---------------------------------------------------------------------------------------------------------- company inputs
@dataclass
class Input:
    key: str
    label: str
    who: str
    value: Optional[float] = None      # percent, after the cap
    raw: Optional[float] = None        # percent, before the cap
    capped: bool = False
    method: Optional[str] = None
    reason: Optional[str] = None       # why it is blank
    detail: Optional[str] = None


def _at(xs: Sequence[Optional[float]], back: int) -> Optional[float]:
    return xs[-1 - back] if back < len(xs) else None


def revenue_growth(h: Hist, years: int) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """(percent, method, reason) for the company's revenue over `years` (1 = year on year, else CAGR)."""
    if len(h.fy) <= years:
        return None, None, f"Needs {years + 1} years of reported revenue; {len(h.fy)} stored."
    b, e = _at(h.revenue, years), _at(h.revenue, 0)
    if b is None or e is None:
        return None, None, "A year of revenue in this window is missing."
    g = yoy(b, e) if years == 1 else cagr(b, e, years)
    if g is None:
        return None, None, "Revenue was not positive at the start or end of this window."
    return g, "Year on year" if years == 1 else f"Compound yearly growth over {years} years", None


def profit_growth(h: Hist, years: int) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Net profit growth in percent. The ratio method needs positive profit at both ends and a start that is not near zero; otherwise the change is
    measured against the average size of profit across the window (a normalised base) and spread evenly over the years."""
    if len(h.fy) <= years:
        return None, None, f"Needs {years + 1} years of reported net profit; {len(h.fy)} stored."
    window = [h.profit[-1 - k] for k in range(years, -1, -1)]
    if any(p is None for p in window):
        return None, None, "A year of net profit in this window is missing."
    b, e = window[0], window[-1]
    rb = _at(h.revenue, years)
    near_zero = b is not None and rb is not None and rb > 0 and b < NEAR_ZERO_MARGIN * rb
    if b is not None and e is not None and b > 0 and e > 0 and not near_zero:
        return (yoy(b, e) if years == 1 else cagr(b, e, years)), ("Year on year" if years == 1 else f"Compound yearly growth over {years} years"), None
    base = sum(abs(p) for p in window) / len(window)   # type: ignore[arg-type]
    if base <= 0:
        return None, None, "Net profit was zero throughout this window."
    why = "a loss" if (b is not None and b <= 0) or (e is not None and e <= 0) else "near zero"
    return (e - b) / base / years * 100, f"Change in profit measured against its average size over the window, per year, because profit was {why}", None  # type: ignore[operator]


def margin_trend(h: Hist) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Relative change of the net profit margin, latest year against the year before: (m1 / m0 - 1) in percent (not percentage points)."""
    if len(h.fy) < 2:
        return None, None, "Needs two years of reported figures."
    ms = []
    for k in (1, 0):
        p, r = _at(h.profit, k), _at(h.revenue, k)
        ms.append(None if p is None or r is None or r <= 0 else p / r)
    if ms[0] is None or ms[1] is None:
        return None, None, "Revenue or net profit is missing for one of the two years."
    if ms[0] <= 0 or ms[1] <= 0:
        return None, None, "The margin was zero or negative in one of the two years, so a relative change is not meaningful."
    return (ms[1] / ms[0] - 1) * 100, "Relative change in the net profit margin, latest year against the year before", None


def company_inputs(kind: str, h: Hist) -> Dict[str, Input]:
    out: Dict[str, Input] = {}
    for key, label, who, years in PARAMS[kind]:
        if who != "company":
            continue
        if key == "margin":
            v, method, reason = margin_trend(h)
        elif kind == "revenue":
            v, method, reason = revenue_growth(h, years)
        else:
            v, method, reason = profit_growth(h, years)
        i = Input(key, label, who, method=method, reason=reason)
        if v is not None:
            i.raw = v
            i.value, i.capped = cap(v)
        out[key] = i
    return out


# ---------------------------------------------------------------------------------------------------------- sector medians
def sector_median(values: Sequence[Optional[float]], min_peers: int = MIN_PEERS) -> Tuple[Optional[float], int]:
    """(median, peers counted). The median of the peers' own figures; None when fewer than `min_peers` have one."""
    xs = [v for v in values if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]
    return (None if len(xs) < min_peers else float(median(xs)), len(xs))


def sector_inputs(kind: str, peers: Optional[Dict[str, Sequence[Optional[float]]]], groups: Optional[Dict[str, str]] = None, why: Optional[str] = None) -> Dict[str, Input]:
    """peers: {parameter key: the peers' values (the company itself left out)}; groups: {parameter key: the peer group the values came from}, for the page."""
    out: Dict[str, Input] = {}
    for key, label, who, years in PARAMS[kind]:
        if who != "sector":
            continue
        i = Input(key, label, who)
        if peers is None or key not in peers:
            i.reason = why or "No peer group is stored for this company."
        else:
            m, n = sector_median(peers[key])
            if m is None:
                i.reason = f"Only {n} peers in {(groups or {}).get(key) or 'its group'} have this figure; at least {MIN_PEERS} are needed for a median."
            else:
                i.raw = m
                i.value, i.capped = cap(m)
                i.method = f"Median of {n} peers in {(groups or {}).get(key)}"
                i.detail = f"{n} peers"
        out[key] = i
    return out


# ---------------------------------------------------------------------------------------------------------- the weighted rate and the forecast
def weighted_rate(kind: str, inputs: Dict[str, Input], weights: Dict[str, float]) -> dict:
    """g = sum(w_i x_i) over the inputs that exist, their weights re-normalised to 100. Returns the rate, each row's effective weight and contribution."""
    live = [k for k, i in inputs.items() if i.value is not None and weights.get(k, 0) > 0]
    total = sum(weights[k] for k in live)
    rows, rate = [], None
    if total > 0:
        rate = sum(weights[k] / total * inputs[k].value for k in live)   # type: ignore[operator]
    for key, label, who, _ in PARAMS[kind]:
        i = inputs[key]
        w = weights.get(key, 0.0)
        eff = (w / total * 100) if total > 0 and key in live else 0.0
        rows.append({"key": key, "label": label, "who": who, "weightPct": round(w, 2), "effectiveWeightPct": round(eff, 2),
                     "valuePct": None if i.value is None else round(i.value, 2), "rawPct": None if i.raw is None else round(i.raw, 2), "capped": i.capped,
                     "contributionPts": None if rate is None or key not in live else round(eff / 100 * i.value, 2),   # type: ignore[operator]
                     "status": "ok" if i.value is not None else "unavailable", "method": i.method, "reason": i.reason, "detail": i.detail})
    unavailable = [r["label"] for r in rows if r["status"] == "unavailable" and r["weightPct"] > 0]
    return {"ratePct": None if rate is None else round(rate, 2), "rows": rows, "unavailable": unavailable, "weightLeftPct": round(sum(weights.get(k, 0) for k in live), 2)}


def next_labels(last: Optional[str], n: int) -> List[str]:
    m = re.fullmatch(r"FY(\d{2})", last or "")
    if not m:
        return [f"FY+{k}" for k in range(1, n + 1)]
    y = int(m.group(1))
    return [f"FY{(y + k) % 100:02d}" for k in range(1, n + 1)]


def project(base: float, ratePct: float, years: int) -> List[float]:
    """Iterative: V(t+1) = V(t) * (1 + g), the same rate each year. Unrounded."""
    out, v = [], base
    for _ in range(years):
        v = v * (1 + ratePct / 100)
        out.append(v)
    return out


def forecast(kind: str, h: Hist, horizon: str, weights: Dict[str, float], sector: Dict[str, Input]) -> dict:
    """The full model result for one company, one kind and one horizon (everything the API sends except names and history)."""
    years = HORIZONS[horizon]["years"]
    inputs = {**company_inputs(kind, h), **sector}
    ordered = {k: inputs.get(k) or Input(k, label, who, reason="Not available for this company.") for k, label, who, _ in PARAMS[kind]}
    wr = weighted_rate(kind, ordered, weights)
    base = _at(h.revenue if kind == "revenue" else h.profit, 0)
    last = h.fy[-1] if h.fy else None
    fc: dict = {"available": False, "reason": None, "base": None, "years": [], "rule": "The weighted rate is held constant for every forecast year; each year starts from the one before."}
    if wr["ratePct"] is None:
        fc["reason"] = "None of the growth inputs could be worked out for this company, so there is no rate to apply."
    elif base is None:
        fc["reason"] = f"The latest year's {'revenue' if kind == 'revenue' else 'net profit'} is not stored."
    elif base <= 0:
        fc["reason"] = ("The latest year's net profit was not positive, so a growth rate cannot be applied to it. The inputs are shown for reference." if kind == "profit"
                        else "The latest year's revenue is not positive.")
    else:
        vals = project(base, wr["ratePct"], years)
        labels = next_labels(last, years)
        prev = base
        for lab, v in zip(labels, vals):
            fc["years"].append({"period": lab, "valueCr": round(v, 2), "growthPct": wr["ratePct"], "changeCr": round(v - prev, 2)})
            prev = v
        fc["available"] = True
        fc["base"] = {"period": last, "valueCr": round(base, 2)}
    return {"rate": wr, "forecast": fc, "horizon": HORIZONS[horizon], "inputCapPct": INPUT_CAP, "minPeers": MIN_PEERS}
