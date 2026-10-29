"""Parameter scorers: pure functions of Inputs returning a 0-100 score, or Miss(reason) when the measure cannot be worked out.

Every scorer maps one reported figure to 0-100 by a documented linear range (lo -> 0, hi -> 100; lo > hi reads "lower is better"),
clamped. The ranges are generic, not sector-specific. They live ONLY in this file: the API and the website never show them.
A Miss is never a zero: the measure is left out and the remaining weights are renormalised (see compose.py).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple, Union

from .inputs import Inputs


@dataclass(frozen=True)
class Miss:
    reason: str   # "lender" | "no_data" | "not_meaningful" | "not_stored"


Result = Union[float, Miss]
LENDER, NO_DATA, NOT_MEANINGFUL, NOT_STORED = Miss("lender"), Miss("no_data"), Miss("not_meaningful"), Miss("not_stored")


def lin(x: float, lo: float, hi: float) -> float:
    if lo == hi:
        return 0.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100.0))


def piecewise(x: float, pts: Sequence[Tuple[float, float]]) -> float:
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def cagr(end: Optional[float], start: Optional[float], years: int) -> Optional[float]:
    """% a year between two positive figures; None when either is missing or not positive."""
    if end is None or start is None or end <= 0 or start <= 0 or years <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def yoy(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev <= 0:
        return None
    return (cur / prev - 1.0) * 100.0


def yearly_growth(i: Inputs, key: str, n: int = 5) -> List[float]:
    out = []
    for k in range(n):
        g = yoy(i.y(key, k), i.y(key, k + 1))
        if g is not None:
            out.append(g)
    return out


def quarterly_growth(i: Inputs, key: str, n: int = 8) -> List[float]:
    if not i.quarters_contiguous(min(len(i.qp), n + 4)):
        return []
    out = []
    for k in range(n):
        g = yoy(i.qv(key, k), i.qv(key, k + 4))
        if g is not None:
            out.append(g)
    return out


def stdev(xs: Sequence[float], minimum: int) -> Optional[float]:
    return statistics.pstdev(xs) if len(xs) >= minimum else None


def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    return None if num is None or den is None or den == 0 else num / den


def _avg_assets(i: Inputs) -> Optional[float]:
    a0, a1 = i.b("total_assets", 0), i.b("total_assets", 1)
    return (a0 + a1) / 2 if a0 is not None and a1 is not None else a0


def ttm(i: Inputs, key: str, back: int = 0) -> Optional[float]:
    """Sum of four consecutive quarters ending `back` quarters before the latest; None if any is missing or the run has a gap."""
    if not i.quarters_contiguous(min(len(i.qp), back + 4)) or len(i.qp) < back + 4:
        return None
    vals = [i.qv(key, back + k) for k in range(4)]
    return None if any(v is None for v in vals) else sum(vals)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ PROFIT outlook

def _margin(num_fn: Callable[[Inputs], Optional[float]], lo: float, hi: float, lender_ok: bool = False):
    def f(i: Inputs) -> Result:
        if i.lender and not lender_ok:
            return LENDER
        rev, n = i.y("revenue"), num_fn(i)
        if rev is None or rev <= 0 or n is None:
            return NO_DATA
        return lin(n / rev * 100, lo, hi)
    return f


def _ebit(i: Inputs) -> Optional[float]:
    op, dep = i.y("operating_profit"), i.y("depreciation")
    return None if op is None or dep is None else op - dep


ebitda_margin = _margin(lambda i: i.y("operating_profit"), 0, 25)
ebit_margin = _margin(_ebit, 0, 20)
net_margin = _margin(lambda i: i.y("net_profit"), 0, 15, lender_ok=True)


def gross_margin(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    v = i.r("gross_margin")
    return NO_DATA if v is None else lin(v, 10, 50)


def _cagr_score(key: str, years: int, lo: float, hi: float, lender_ok: bool = True, table: str = "y"):
    def f(i: Inputs) -> Result:
        if i.lender and not lender_ok:
            return LENDER
        end, start = i.y(key, 0), i.y(key, years)
        if end is None or start is None:
            return NO_DATA
        if end <= 0:
            return 0.0 if start > 0 else NOT_MEANINGFUL   # a loss after a profit scores nothing; loss to loss has no growth rate
        if start <= 0:
            return NOT_MEANINGFUL    # growth from a loss
        return lin(cagr(end, start, years) or 0.0, lo, hi)
    return f


pat_cagr_3y = _cagr_score("net_profit", 3, -10, 20)
pat_cagr_5y = _cagr_score("net_profit", 5, -10, 18)


def ebitda_growth(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    g = yoy(i.y("operating_profit"), i.y("operating_profit", 1))
    return NO_DATA if g is None else lin(g, -15, 25)


def profit_consistency(i: Inputs) -> Result:
    s = stdev(yearly_growth(i, "net_profit"), 3)
    return NO_DATA if s is None else lin(s, 80, 10)


def op_cost_ratio(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    rev, ex = i.y("revenue"), i.y("expenses")
    return NO_DATA if rev is None or rev <= 0 or ex is None else lin(ex / rev * 100, 98, 60)


def incremental_margin(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    r0, r3, o0, o3 = i.y("revenue"), i.y("revenue", 3), i.y("operating_profit"), i.y("operating_profit", 3)
    if None in (r0, r3, o0, o3):
        return NO_DATA
    if r0 - r3 <= 0:
        return NOT_MEANINGFUL
    return lin((o0 - o3) / (r0 - r3) * 100, 0, 25)


def cfo_to_pat(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    cfo, pat = i.c("operating"), i.y("net_profit")
    if cfo is None or pat is None:
        return NO_DATA
    return NOT_MEANINGFUL if pat <= 0 else lin(cfo / pat, 0.4, 1.2)


def accrual_ratio(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    cfo, pat, assets = i.c("operating"), i.y("net_profit"), _avg_assets(i)
    if cfo is None or pat is None or not assets:
        return NO_DATA
    return lin((pat - cfo) / assets, 0.08, -0.02)


def fcf_to_pat(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    fcf, pat = i.c("free_cash_flow"), i.y("net_profit")
    if fcf is None or pat is None:
        return NO_DATA
    return NOT_MEANINGFUL if pat <= 0 else lin(fcf / pat, 0.0, 1.0)


def net_debt_ebitda(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    debt, cash, op = i.b("borrowings"), i.b("cash"), i.y("operating_profit")
    if debt is None or cash is None or op is None:
        return NO_DATA
    nd = debt - cash
    if nd <= 0:
        return 100.0
    return 0.0 if op <= 0 else lin(nd / op, 5, 0)


def interest_coverage(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    ebit, fin = _ebit(i), i.y("finance_costs")
    if ebit is None or fin is None:
        return NO_DATA
    if fin <= 0:
        return 100.0
    return lin(ebit / fin, 1, 8)


def debt_to_equity(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    debt, eq = i.b("borrowings"), i.b("total_equity")
    if debt is None or eq is None:
        return NO_DATA
    return 0.0 if eq <= 0 else lin(debt / eq, 2, 0)


def finance_cost_ratio(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    fin, rev = i.y("finance_costs"), i.y("revenue")
    return NO_DATA if fin is None or rev is None or rev <= 0 else lin(fin / rev * 100, 8, 0)


def roce(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    pbt, fin, ta, cl = i.y("profit_before_tax"), i.y("finance_costs"), i.b("total_assets"), i.b("current_liabilities")
    if None in (pbt, fin, ta, cl) or ta - cl <= 0:   # type: ignore[operator]
        return NO_DATA
    return lin((pbt + fin) / (ta - cl) * 100, 0, 25)   # type: ignore[operator]


def roa(i: Inputs) -> Result:
    pat, assets = i.y("net_profit"), _avg_assets(i)
    if pat is None or not assets:
        return NO_DATA
    return lin(pat / assets * 100, 0, 2.0 if i.lender else 12)


def asset_turnover(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    rev, assets = i.y("revenue"), _avg_assets(i)
    return NO_DATA if rev is None or not assets else lin(rev / assets, 0.2, 1.5)


def working_capital_days(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    v = i.r("cash_conversion_cycle")
    return NO_DATA if v is None else lin(v, 100, 0)


def tax_stability(i: Inputs) -> Result:
    rates = []
    for k in range(5):
        pbt, tax = i.y("profit_before_tax", k), i.y("tax", k)
        if pbt is not None and tax is not None and pbt > 0:
            rates.append(tax / pbt * 100)
    s = stdev(rates, 3)
    return NO_DATA if s is None else lin(s, 15, 2)


def exceptional_share(i: Inputs) -> Result:
    exc, pbt = [], []
    for k in range(3):
        e, p = i.y("exceptional_items", k), i.y("profit_before_tax", k)
        if e is not None and p is not None:
            exc.append(abs(e)), pbt.append(abs(p))
    if not exc or sum(pbt) <= 0:
        return NO_DATA
    return lin(sum(exc) / sum(pbt), 0.25, 0.0)


def quarterly_pat_volatility(i: Inputs) -> Result:
    s = stdev(quarterly_growth(i, "net_profit"), 4)
    return NO_DATA if s is None else lin(s, 100, 15)


def quarterly_ebitda_volatility(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    s = stdev(quarterly_growth(i, "operating_profit"), 4)
    return NO_DATA if s is None else lin(s, 50, 10)


def capex_to_revenue(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    cap, rev = i.c("capex"), i.y("revenue")
    if cap is None or rev is None or rev <= 0:
        return NO_DATA
    return piecewise(abs(cap) / rev * 100, [(0, 20), (4, 80), (12, 100), (25, 50), (40, 0)])


def depreciation_to_revenue(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    dep, rev = i.y("depreciation"), i.y("revenue")
    return NO_DATA if dep is None or rev is None or rev <= 0 else lin(dep / rev * 100, 15, 1)


def revenue_per_capex(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    r0, r3 = i.y("revenue"), i.y("revenue", 3)
    caps = [i.c("capex", k) for k in range(3)]
    if r0 is None or r3 is None or any(c is None for c in caps):
        return NO_DATA
    total = sum(abs(c) for c in caps)   # type: ignore[arg-type]
    return NOT_MEANINGFUL if total <= 0 else lin((r0 - r3) / total, 0, 4)


# ------------------------------------------------------------------------------------------------ REVENUE outlook

rev_cagr_3y = _cagr_score("revenue", 3, -5, 20)
rev_cagr_5y = _cagr_score("revenue", 5, -5, 18)


def quarterly_revenue_growth(i: Inputs) -> Result:
    g = yoy(ttm(i, "revenue"), ttm(i, "revenue", 4))
    return NO_DATA if g is None else lin(g, -10, 25)


def revenue_volatility(i: Inputs) -> Result:
    s = stdev(yearly_growth(i, "revenue"), 3)
    return NO_DATA if s is None else lin(s, 40, 5)


def _segs(i: Inputs) -> List[Tuple[float, Optional[float]]]:
    return [(float(s["sharePct"]), s.get("growthPct")) for s in i.segments if isinstance(s.get("sharePct"), (int, float))]


def segment_growth(i: Inputs) -> Result:
    rows = [(w, g) for w, g in _segs(i) if isinstance(g, (int, float))]
    if len(rows) < 2 or sum(w for w, _ in rows) <= 0:
        return NO_DATA
    avg = sum(w * g for w, g in rows) / sum(w for w, _ in rows)
    return lin(avg, -5, 20)


def segment_concentration(i: Inputs) -> Result:
    shares = [w for w, _ in _segs(i)]
    if len(shares) < 2 or sum(shares) <= 0:
        return NO_DATA
    tot = sum(shares)
    return lin(sum((w / tot) ** 2 for w in shares), 0.95, 0.35)


def productive_capex_growth(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    def block(k: int) -> Optional[float]:
        a, b = i.b("fixed_assets", k), i.b("cwip", k)
        return None if a is None else a + (b or 0)
    now, then = block(0), block(3)
    if now is None or then is None:
        return NO_DATA
    g = cagr(now, then, 3)
    return NOT_MEANINGFUL if g is None else lin(g, -5, 20)


def receivables_turnover(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    r0, r1, rev = i.b("receivables"), i.b("receivables", 1), i.y("revenue")
    avg = (r0 + r1) / 2 if r0 is not None and r1 is not None else r0
    return NO_DATA if rev is None or not avg or avg <= 0 else lin(rev / avg, 3, 15)


def days_sales_outstanding(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    rec, rev = i.b("receivables"), i.y("revenue")
    return NO_DATA if rec is None or rev is None or rev <= 0 else lin(rec / rev * 365, 120, 15)


def cfo_to_revenue(i: Inputs) -> Result:
    if i.lender:
        return LENDER
    cfo, rev = i.c("operating"), i.y("revenue")
    return NO_DATA if cfo is None or rev is None or rev <= 0 else lin(cfo / rev, 0.0, 0.12)


def seasonality(i: Inputs) -> Result:
    """Eight consecutive quarters as two blocks of four: each quarter's share of its block's revenue, averaged by quarter of the year.
    The gap between the biggest and smallest average share is the seasonal swing (0 = flat). Lower swing scores higher."""
    if len(i.qp) < 8 or not i.quarters_contiguous(8):
        return NO_DATA
    vals = [i.qv("revenue", 7 - k) for k in range(8)]    # oldest first
    if any(v is None or v <= 0 for v in vals):
        return NO_DATA
    shares = [[], [], [], []]   # type: ignore[var-annotated]
    for block in (vals[:4], vals[4:]):
        t = sum(block)
        for pos, v in enumerate(block):
            shares[pos].append(v / t * 100)
    avg = [sum(s) / len(s) for s in shares]
    return lin(max(avg) - min(avg), 20, 2)


def quarterly_revenue_volatility(i: Inputs) -> Result:
    s = stdev(quarterly_growth(i, "revenue"), 4)
    return NO_DATA if s is None else lin(s, 30, 5)
