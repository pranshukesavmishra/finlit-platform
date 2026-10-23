"""Index reference points for the cross-section charts (NIFTY 50, NIFTY 100, ... and the sector indices in screener INDEX_LISTS).

An index point is computed ONLY from the stored figures of its member companies (index membership from NSE Indices' public lists,
table `index_members`); nothing is fetched or estimated. Two methods:
  * "ratio_of_sums" where a sound aggregate exists, e.g. index P/E = sum of market caps / sum of latest-FY net profits over ALL used members,
    loss-makers included (the way NSE computes index P/E, so losses lower the index's earnings); margins = sum of numerators / sum of revenue;
    growth = sum of this year's values / sum of last year's values - 1 over members that have both years;
  * "median" of the members' own values for everything without a sound aggregate (current/quick ratio, days, interest cover, per-share items,
    returns, volatility, multiples at a past date).
A point is returned with a value only when the members used cover at least 80% of the eligible members' market cap; otherwise the value is
null with the reason. Index points are reference markers: they are never part of the regression statistics or of n.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import stats as S
from .catalog import Metric
from .derive import AGG_GROWTH

NAN = float("nan")
MIN_COVERAGE = 80.0
MAX_INDICES = 3

# metric id -> (numerator, denominator, scale, formula text)
ROS: Dict[str, Tuple[str, str, float, str]] = {
    "pe": ("mcap", "np", 1.0, "Sum of market caps / sum of latest-FY net profits of all used members (loss-makers included, as NSE does)."),
    "pb": ("mcap", "equity", 1.0, "Sum of market caps / sum of latest-FY shareholders' equity (negative equity included)."),
    "ev_ebitda": ("ev", "ebitda", 1.0, "Sum of enterprise values / sum of latest-FY EBITDA (company points use the provider's trailing-12-month EBITDA)."),
    "ev_sales": ("ev", "revenue", 1.0, "Sum of enterprise values / sum of latest-FY revenue."),
    "ev_cfo": ("ev", "cfo", 1.0, "Sum of enterprise values / sum of latest-FY operating cash flow."),
    "dy": ("div", "mcap", 100.0, "Sum of dividends paid in the last 12 months (dividend yield x market cap) / sum of market caps x 100."),
    "fcf_yield": ("fcf", "mcap", 100.0, "Sum of latest-FY free cash flow / sum of market caps x 100."),
    "cfo_yield": ("cfo", "mcap", 100.0, "Sum of latest-FY operating cash flow / sum of market caps x 100."),
    "opm": ("ebitda", "base", 100.0, "Sum of operating profit / sum of revenue (lenders: total income) x 100."),
    "npm": ("np", "base", 100.0, "Sum of net profit / sum of revenue (lenders: total income) x 100."),
    "ebit_margin": ("ebit", "revenue", 100.0, "Sum of (profit before tax + finance costs) / sum of revenue x 100."),
    "roe": ("np", "equity", 100.0, "Sum of net profit / sum of shareholders' equity x 100 (latest FY)."),
    "roa": ("np", "ta", 100.0, "Sum of net profit / sum of total assets x 100 (latest FY)."),
    "roce": ("ebit", "ce", 100.0, "Sum of (profit before tax + finance costs) / sum of (total assets - current liabilities) x 100 (latest FY)."),
    "de": ("debt", "equity", 1.0, "Sum of borrowings / sum of shareholders' equity (latest FY)."),
    "debt_assets": ("debt", "ta", 1.0, "Sum of borrowings / sum of total assets (latest FY)."),
    "nd_ebitda": ("nd", "ebitda", 1.0, "Sum of (borrowings - cash) / sum of EBITDA (latest FY)."),
    "cfo_debt": ("cfo", "debt", 1.0, "Sum of operating cash flow / sum of borrowings (latest FY)."),
    "cl_tl": ("cl", "tl", 100.0, "Sum of current liabilities / sum of total liabilities x 100."),
    "wc_rev": ("wc", "revenue", 100.0, "Sum of (current assets - current liabilities) / sum of revenue x 100."),
    "ca_ta": ("ca", "ta", 100.0, "Sum of current assets / sum of total assets x 100."),
    "cash_ratio": ("cash", "cl", 1.0, "Sum of cash / sum of current liabilities."),
    "cfo_pat": ("cfo", "np", 100.0, "Sum of operating cash flow / sum of net profit x 100."),
    "oi_np": ("oi", "np", 100.0, "Sum of other income / sum of net profit x 100."),
    "exc_np": ("exc", "np", 100.0, "Sum of exceptional items / sum of net profit x 100."),
}
for _g in AGG_GROWTH:
    ROS[_g] = (f"gc_{_g}", f"gp_{_g}", 0.0, "Sum of this year's values / sum of last year's values - 1, x 100, over members that report both years.")


def _comp(t, name: str) -> Callable[[int], float]:
    cols = t.cols
    if name == "mcap":
        return lambda i: cols["market_cap"][i]
    if name == "ev":
        return lambda i: cols["enterprise_value"][i]
    if name == "div":
        return lambda i: cols["dividend_yield"][i] * cols["market_cap"][i] / 100.0
    if name in ("np", "ebitda", "revenue", "cfo", "fcf"):
        col = t.ax[f"ax_{name}"]
        return lambda i: col[i]
    if name == "ce":
        a, b = t.ax["ax_c_ta"], t.ax["ax_c_cl"]
        return lambda i: a[i] - b[i]
    if name == "nd":
        a, b = t.ax["ax_c_debt"], t.ax["ax_c_cash"]
        return lambda i: a[i] - b[i]
    if name == "wc":
        a, b = t.ax["ax_c_ca"], t.ax["ax_c_cl"]
        return lambda i: a[i] - b[i]
    if name.startswith(("gc_", "gp_")):
        col = t.ax[f"ax_{name}"]
        return lambda i: col[i]
    col = t.ax[f"ax_c_{name}"]
    return lambda i: col[i]


def _known(v: float) -> bool:
    return v == v and not math.isinf(v)


class _Axis:
    def __init__(self, t, m: Metric, value_of: Callable[[Any, Metric, int], float]):
        self.m = m
        if m.id in ROS:
            num, den, scale, text = ROS[m.id]
            self.method, self.formula = "ratio_of_sums", text
            self.num, self.den, self.scale = _comp(t, num), _comp(t, den), scale
        else:
            self.method = "median"
            self.formula = f"Median of the members' own {m.short} (no sound market-cap aggregate exists for this figure)."
            self.val = lambda i: value_of(t, m, i)

    def has(self, i: int) -> bool:
        if self.method == "median":
            return _known(self.val(i))
        return _known(self.num(i)) and _known(self.den(i))

    def value(self, used: List[int]) -> Tuple[Optional[float], Optional[str]]:
        if not used:
            return None, "no_members"
        if self.method == "median":
            return S.median([self.val(i) for i in used]), None
        n, d = math.fsum(self.num(i) for i in used), math.fsum(self.den(i) for i in used)
        if d <= 0:
            return None, "den_le0"
        if self.scale == 0.0:   # growth
            return (n / d - 1.0) * 100.0, None
        return n / d * self.scale, None


INDEX_REASONS = {
    "no_members": "No member of this index has the figures for this chart.",
    "den_le0": "The members' combined denominator is zero or negative, so the aggregate is not meaningful.",
    "low_coverage": "Only {pct}% of the index (by market cap) has stored figures for this chart; at least 80% is needed.",
    "log_le0": "Zero or negative: cannot be placed on a log scale.",
    "no_list": "The member list of this index is not stored.",
}


def point(t, code: str, label: str, xm: Metric, ym: Metric, lender_mode: str, scale: Dict[str, str],
          value_of: Callable[[Any, Metric, int], float], fy_of: Callable[[Any, Metric, Metric, int], Optional[str]]) -> Dict[str, Any]:
    members = sorted(t.members.get(code) or (), key=lambda s: s)
    base = {"code": code, "label": label, "x": None, "y": None, "membersTotal": len(members), "membersEligible": 0, "membersUsed": 0,
            "mcapCoveragePct": None, "fyBreakdown": [], "lossMembers": None, "lenders": {"include": "included", "exclude": "excluded", "only": "only"}[lender_mode],
            "reason": None, "reasonText": None, "inStats": False}
    if not members:
        return {**base, "method": None, "formula": None, "reason": "no_list", "reasonText": INDEX_REASONS["no_list"]}
    ax, ay = _Axis(t, xm, value_of), _Axis(t, ym, value_of)
    base["method"] = {"x": ax.method, "y": ay.method}
    base["formula"] = {"x": ax.formula, "y": ay.formula}
    mc, bank = t.cols["market_cap"], t.cols["is_bank"]
    eligible, used = [], []
    for s in members:
        i = t.pos[s]
        if not _known(mc[i]) or mc[i] <= 0:
            continue
        is_l = bank[i] == 1.0
        if (lender_mode == "exclude" and is_l) or (lender_mode == "only" and not is_l):
            continue
        eligible.append(i)
        if t.full[i] and t.ax_ready[i] and ax.has(i) and ay.has(i):
            used.append(i)
    total = math.fsum(mc[i] for i in eligible)
    cov = math.fsum(mc[i] for i in used) / total * 100.0 if total > 0 else 0.0
    fyb: Dict[str, int] = {}
    for i in used:
        f = fy_of(t, xm, ym, i)
        if f:
            fyb[f] = fyb.get(f, 0) + 1
    np_col = t.ax["ax_np"]
    base.update(membersEligible=len(eligible), membersUsed=len(used), mcapCoveragePct=round(cov, 1),
                fyBreakdown=[{"fy": f, "n": c} for f, c in sorted(fyb.items(), key=lambda kv: (-kv[1], kv[0]))],
                lossMembers=sum(1 for i in used if _known(np_col[i]) and np_col[i] <= 0) if "pe" in (xm.id, ym.id) else None)
    if cov < MIN_COVERAGE:
        pct = f"{cov:.0f}"
        return {**base, "reason": "low_coverage", "reasonText": INDEX_REASONS["low_coverage"].format(pct=pct)}
    xv, xr = ax.value(used)
    yv, yr = ay.value(used)
    why = xr or yr
    if why is None and ((scale.get("x") == "log" and xv is not None and xv <= 0) or (scale.get("y") == "log" and yv is not None and yv <= 0)):
        why = "log_le0"
    if why:
        return {**base, "x": None if xr else xv, "y": None if yr else yv, "reason": why, "reasonText": INDEX_REASONS[why]}
    return {**base, "x": float(f"{xv:.10g}"), "y": float(f"{yv:.10g}")}
