"""The model's groups and parameters with the founder's default weights (each group's parameters sum to the group weight; each table to 100).

Parameter names stay in this file. The API returns group names, percentages and scores only.

Measurable from the stored report sections (fn set) vs not (fn None, reason "not_stored"):
  PROFIT   not stored: employee expenses / revenue and other operating expenses / revenue (the statements hold one total-expenses line).
  REVENUE  not stored: geographic revenue growth, recurring revenue share (segments are business lines, not geographies; no recurring split),
           order book, order inflow, book-to-bill, customer/unit growth, capacity utilisation, sales volume, average selling price, product mix,
           unbilled revenue, industry revenue growth (peers are a list of symbols; their reports may not be stored), market share.
           Seasonal pattern and revenue volatility ARE derived, from the eight to twelve stored quarters.
Lenders (finlit.normalize.statements.is_bank): the stored sections flag them (summary.dataQuality.isBank); EBITDA/EBIT/gross margin, operating
costs, leverage, working capital, cash-flow and capex measures are excluded (see scorers.py), the rest are scored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from . import scorers as s


@dataclass(frozen=True)
class Param:
    key: str
    weight: float
    fn: Optional[Callable]


@dataclass(frozen=True)
class Group:
    letter: str
    name: str
    weight: float
    params: tuple
    unavailable: str   # shown when no measure of the group can be worked out and the cause is "not in our data"


P = Param
PROFIT: List[Group] = [
    Group("A", "Profitability and margins", 25, (P("ebitda_margin", 8, s.ebitda_margin), P("ebit_margin", 6, s.ebit_margin), P("net_margin", 6, s.net_margin), P("gross_margin", 5, s.gross_margin)), "Margins could not be worked out from the reported figures."),
    Group("B", "Historical profit growth", 15, (P("pat_cagr_3y", 5, s.pat_cagr_3y), P("pat_cagr_5y", 4, s.pat_cagr_5y), P("ebitda_growth", 3, s.ebitda_growth), P("profit_consistency", 3, s.profit_consistency)), "Not enough reported profit history."),
    Group("C", "Cost efficiency and operating leverage", 15, (P("op_cost", 4, s.op_cost_ratio), P("employee_cost", 3, None), P("other_opex", 3, None), P("incremental_margin", 5, s.incremental_margin)), "Cost lines could not be worked out from the reported figures."),
    Group("D", "Cash conversion and earnings quality", 10, (P("cfo_pat", 4, s.cfo_to_pat), P("accrual", 3, s.accrual_ratio), P("fcf_pat", 3, s.fcf_to_pat)), "Cash flow figures could not be worked out."),
    Group("E", "Leverage and interest burden", 10, (P("nd_ebitda", 3, s.net_debt_ebitda), P("coverage", 3, s.interest_coverage), P("de", 2, s.debt_to_equity), P("fin_cost", 2, s.finance_cost_ratio)), "Borrowing figures could not be worked out."),
    Group("F", "Capital and asset efficiency", 10, (P("roce", 4, s.roce), P("roa", 2, s.roa), P("asset_turnover", 2, s.asset_turnover), P("wc_days", 2, s.working_capital_days)), "Balance sheet figures could not be worked out."),
    Group("G", "Tax and exceptional items", 5, (P("tax_stability", 2, s.tax_stability), P("exceptional", 3, s.exceptional_share)), "Tax and one-off figures could not be worked out."),
    Group("H", "Earnings volatility", 5, (P("q_pat_vol", 3, s.quarterly_pat_volatility), P("q_ebitda_vol", 2, s.quarterly_ebitda_volatility)), "Not enough quarterly history."),
    Group("I", "Capital expenditure and depreciation", 5, (P("capex_rev", 2, s.capex_to_revenue), P("dep_rev", 2, s.depreciation_to_revenue), P("rev_per_capex", 1, s.revenue_per_capex)), "Capital spending figures could not be worked out."),
]
REVENUE: List[Group] = [
    Group("A", "Historical revenue trend", 25, (P("rev_cagr_3y", 10, s.rev_cagr_3y), P("rev_cagr_5y", 8, s.rev_cagr_5y), P("q_growth", 5, s.quarterly_revenue_growth), P("growth_vol", 2, s.revenue_volatility)), "Not enough reported revenue history."),
    Group("B", "Segment performance", 15, (P("segment_growth", 8, s.segment_growth), P("concentration", 3, s.segment_concentration), P("geo_growth", 2, None), P("recurring", 2, None)), "This company does not report enough business segments."),
    Group("C", "Demand visibility", 15, (P("order_book", 6, None), P("order_inflow", 4, None), P("book_to_bill", 3, None), P("customers", 2, None)), "These figures are not in our data."),
    Group("D", "Operational scale and capacity", 10, (P("capacity", 4, None), P("asset_turnover", 3, s.asset_turnover), P("capex_growth", 3, s.productive_capex_growth)), "Capacity and asset figures could not be worked out."),
    Group("E", "Pricing and volume", 10, (P("volume", 5, None), P("price", 3, None), P("mix", 2, None)), "These figures are not in our data."),
    Group("F", "Sales conversion and quality", 10, (P("rec_turnover", 3, s.receivables_turnover), P("dso", 3, s.days_sales_outstanding), P("cfo_rev", 2, s.cfo_to_revenue), P("unbilled", 2, None)), "Receivable and cash figures could not be worked out."),
    Group("G", "Industry and market", 10, (P("industry", 6, None), P("share", 4, None)), "These figures are not in our data."),
    Group("H", "Seasonality and volatility", 5, (P("seasonal", 3, s.seasonality), P("q_rev_vol", 2, s.quarterly_revenue_volatility)), "Not enough quarterly history."),
]
GROUPS: Dict[str, List[Group]] = {"profit": PROFIT, "revenue": REVENUE}

for _kind, _gs in GROUPS.items():   # the table must add up: checked at import so a typo cannot ship
    assert abs(sum(g.weight for g in _gs) - 100) < 1e-9, _kind
    for _g in _gs:
        assert abs(sum(p.weight for p in _g.params) - _g.weight) < 1e-9, (_kind, _g.letter)


def default_weights(kind: str) -> Dict[str, float]:
    return {g.letter: g.weight for g in GROUPS[kind]}
