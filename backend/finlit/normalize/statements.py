"""Profit & loss, balance sheet and cash flow -> compact column-oriented tables in ₹ crore.

Output shape (oldest period first, so charts can draw left to right):

    {"unit": "Cr", "periods": ["FY21", ..., "FY26"], "periodEnds": [...],
     "rows": {"revenue": [..], "net_profit": [..], ...}}
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .common import crore, fiscal_year_label, parse_date, quarter_label, rnd, sum_present, to_number

Row = Dict[str, Any]
log = logging.getLogger("finlit.statements")

# ONE set of definitions for the whole site (stock page, quarter results, screener, ratios, exports, FinLit score). They follow the
# Indian convention (the one Screener.in and company filings use), and the stock page explains them next to the numbers:
#   Revenue          = revenue from operations (a lender: interest earned plus fees; an insurer: premiums and investment income)
#   Total expenses   = every cost the company reports, INCLUDING interest and depreciation (as the provider and the filing give it)
#   Operating profit = Revenue - (Total expenses - Interest - Depreciation). Before interest, depreciation and other income: the EBITDA.
#                      Other income is NOT in it. A lender's: total income - operating expenses, before provisions.
#   Profit before tax = Total income - Total expenses + Exceptional items          (so Operating profit + Other income - Interest
#                       - Depreciation + Exceptional items)
#   Net profit       = the profit that belongs to the company's shareholders (after minorities); EPS is on the same basis.
# Signs: costs (expenses, interest, depreciation, tax) are stored as positive amounts; a tax CREDIT is negative; profits are signed
# (a loss is negative, shown with a true minus); exceptional items are signed (a loss is negative); EPS carries the sign of net profit.


def _ordered(rows: List[Row]) -> List[Row]:
    """Sort by period end ascending and keep the last row per period (FinEdge can repeat restated periods)."""
    keyed = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        end = parse_date(row.get("period_end")) or (parse_date(f"{row.get('year')}-03-31") if row.get("year") else None)
        if end:
            keyed[end] = row
    return [keyed[k] for k in sorted(keyed)]


def _table(rows: List[Row], period: str, fields: Dict[str, Callable[[Row], Optional[float]]], limit: int) -> dict:
    ordered = _ordered(rows)[-limit:]
    label = (lambda r: quarter_label(r.get("period_end"))) if period == "quarterly" else (lambda r: fiscal_year_label(r.get("period_end"), r.get("year")))
    table = {
        "unit": "Cr",
        "period": period,
        "periods": [label(r) for r in ordered],
        "periodEnds": [str(parse_date(r.get("period_end")) or "") or None for r in ordered],
        "rows": {key: [fn(r) for r in ordered] for key, fn in fields.items()},
    }
    # Drop rows that are entirely empty or zero (FinEdge sends many structural zeros).
    table["rows"] = {k: v for k, v in table["rows"].items() if any(x not in (None, 0) for x in v)}
    return table


# ---------------------------------------------------------------- profit & loss

def _revenue(r: Row) -> Optional[float]:
    value = to_number(r.get("revenueFromOperations"))
    if not value:  # banks/NBFCs report interest earned instead
        value = sum_present(r.get("interestEarned"), r.get("feesAndCommissionIncome"), r.get("otherRevenueFromOperations"))
    if not value:  # insurers report their operating income (premiums earned plus investment income)
        value = to_number(r.get("operatingIncome")) or to_number(r.get("income")) or to_number(r.get("premiumEarned")) or to_number(r.get("netPremiumIncome")) or None   # life insurers: total income
    return crore(value)


def _first(r: Row, *keys: str):
    """The first field the provider filled in: banks and companies name the same line differently."""
    for k in keys:
        v = r.get(k)
        if v not in (None, ""):
            return v
    return None


def _bank_expenses(r: Row) -> Optional[float]:
    # banks: interest paid + operating costs (+ provisions), reported as separate lines
    return crore(sum_present(r.get("expenditureExcludingProvisions"), r.get("provisionsForLoanLoss"))) if r.get("expenditureExcludingProvisions") is not None else None


def _net_profit(r: Row) -> Optional[float]:
    """Net profit attributable to the company's shareholders, in rupees (the same basis EPS is quoted on)."""
    for key in ("profitOrLossAttributableToOwners", "profitLossForPeriod", "profitLossForThePeriod", "profitLossAfterTax",
                "profitLossAfterTaxAndExtraordinaryItems", "profitLossAfterTaxBeforeExtraordinaryItems"):
        v = r.get(key)
        if v not in (None, ""):
            return to_number(v)
    return None


EPS_TOLERANCE = 0.25   # on 805 recorded company-years the provider's EPS x shares was within 25% of attributable profit every time


def eps_checked(r: Row) -> tuple:
    """(EPS, repaired). EPS must carry the sign of the profit it is earned on. If the provider's sign contradicts the profit (never seen on
    805 sampled company-years, but a wrong sign is the worst kind of wrong) the sign is taken from the profit, and only when the magnitude
    agrees with profit / shares, so a figure is never guessed: no share count or no agreement means the provider's figure stays as sent."""
    eps, profit, shares = to_number(r.get("eps")), _net_profit(r), to_number(r.get("dilutedOutstandingShares"))
    if eps is None:
        return None, False
    if not eps or not profit or (eps > 0) == (profit > 0):
        return round(eps, 2), False
    if shares and shares > 0:
        implied = abs(profit) / shares
        if abs(abs(eps) - implied) <= EPS_TOLERANCE * implied:
            return round(-eps, 2), True
    return round(eps, 2), False


def _operating_profit(r: Row) -> Optional[float]:
    """Revenue - operating expenses, where operating expenses exclude finance costs and depreciation
    (the Screener.in convention FinLit users already know). For banks: operating profit before provisions."""
    revenue = to_number(r.get("revenueFromOperations"))
    expenses = to_number(r.get("expenses"))
    if revenue is None and r.get("operatingProfitOrLoss") is not None:   # insurers state their operating result directly
        return crore(r.get("operatingProfitOrLoss"))
    if (revenue is None or expenses is None) and r.get("expenditureExcludingProvisions") is not None:
        income, cost = to_number(r.get("income")), to_number(r.get("expenditureExcludingProvisions"))
        return crore(income - cost) if income is not None and cost is not None else None
    if revenue is None or expenses is None:
        return None
    operating_expenses = expenses - (to_number(r.get("financeCosts")) or 0) - (to_number(r.get("depreciationAndAmortisation")) or 0)
    return crore(revenue - operating_expenses)


PL_FIELDS = {
    "revenue": _revenue,
    "other_income": lambda r: crore(r.get("otherIncome")),
    "total_income": lambda r: crore(r.get("income")),
    "expenses": lambda r: crore(_first(r, "expenses", "operatingExpenses")) if _first(r, "expenses", "operatingExpenses") is not None else _bank_expenses(r),
    "operating_profit": _operating_profit,
    "finance_costs": lambda r: crore(_first(r, "financeCosts", "interestExpended")),
    "depreciation": lambda r: crore(r.get("depreciationAndAmortisation")),
    "exceptional_items": lambda r: crore(r.get("exceptionalItemsBeforeTax")),
    "discontinued_profit": lambda r: crore(r.get("profitLossFromDiscontinuedOperationsAfterTax")),   # e.g. ITC FY25 (hotels demerger): profit that will not repeat
    "profit_before_tax": lambda r: crore(_first(r, "profitBeforeTax", "profitLossBeforeTax", "profitOrLossBeforeTax")),
    "tax": lambda r: crore(_first(r, "taxExpense", "provisionForTax")),
    "net_profit": lambda r: crore(_net_profit(r)),   # attributable to the company's shareholders, as EPS is
    "eps": lambda r: eps_checked(r)[0],
    "diluted_shares_cr": lambda r: crore(r.get("dilutedOutstandingShares")),
}


def profit_and_loss(rows: List[Row], period: str = "yearly", limit: Optional[int] = None) -> dict:
    table = with_continuing(_table(rows, period, PL_FIELDS, limit or (10 if period == "yearly" else 12)))
    ordered = _ordered(rows)[-(limit or (10 if period == "yearly" else 12)):]
    fixed = [table["periods"][i] for i, r in enumerate(ordered) if eps_checked(r)[1]]
    if fixed:   # shown nowhere to users; the quality report and the log carry it
        table["epsSignRepaired"] = fixed
        log.warning("EPS sign taken from net profit for %s", ", ".join(fixed))
    return table


# ---------------------------------------------------------------- cross-checks (used by the tests, the audit and the ingest log)

def reconcile_row(r: Row, tolerance: float = 0.02) -> Dict[str, Any]:
    """Recompute operating profit, profit before tax, profit after tax and EPS from the company's own components and compare them with
    what the provider states. Returns {check: {"computed", "reported", "ok"}} in rupees (EPS in rupees per share), only for the checks the
    row has the data for. Lenders (no revenue from operations / total expenses) are skipped."""
    def f(key):
        return to_number(r.get(key)) or 0.0
    out: Dict[str, Any] = {}
    revenue, expenses, income = to_number(r.get("revenueFromOperations")), to_number(r.get("expenses")), to_number(r.get("income"))
    if revenue is None or expenses is None:
        return out

    def close(a, b, floor=2e5):
        return abs(a - b) <= max(tolerance * abs(b), floor)
    # Operating profit is a FinLit-defined line (no provider figure to compare with): it must tie to PBT through the stated identity.
    op = revenue - (expenses - f("financeCosts") - f("depreciationAndAmortisation"))
    pbt_reported = to_number(r.get("profitBeforeTax"))
    if pbt_reported is not None:
        via_op = op + f("otherIncome") - f("financeCosts") - f("depreciationAndAmortisation") + f("exceptionalItemsBeforeTax")
        out["operating_profit"] = {"computed": op, "reported": None, "ok": close(via_op, pbt_reported)}
        computed_pbt = (income if income is not None else revenue + f("otherIncome")) - expenses + f("exceptionalItemsBeforeTax")
        out["profit_before_tax"] = {"computed": computed_pbt, "reported": pbt_reported, "ok": close(computed_pbt, pbt_reported)}
        tax, pat = to_number(r.get("taxExpense")), to_number(r.get("profitLossForPeriod"))
        if tax is not None and pat is not None:
            computed_pat = pbt_reported - tax + f("profitOrLossOfAssociates") + f("profitLossFromDiscontinuedOperationsAfterTax")
            # some filers show the share of associates' profit above the "profit for the period" line, some only in the owners' line
            without_associates = pbt_reported - tax + f("profitLossFromDiscontinuedOperationsAfterTax")
            out["profit_after_tax"] = {"computed": computed_pat, "reported": pat, "ok": close(computed_pat, pat) or close(without_associates, pat) or close(pbt_reported - tax, pat)}
    profit, shares, eps = _net_profit(r), to_number(r.get("dilutedOutstandingShares")), to_number(r.get("eps"))
    if profit is not None and shares and eps is not None:
        computed_eps = profit / shares
        out["eps"] = {"computed": round(computed_eps, 2), "reported": eps,
                      "ok": ((eps > 0) == (computed_eps > 0) or not eps or abs(computed_eps) < 0.005) and abs(abs(eps) - abs(computed_eps)) <= EPS_TOLERANCE * abs(computed_eps) + 0.01}
    return out


def reconcile(rows: List[Row], tolerance: float = 0.02) -> List[dict]:
    """Every period whose statements do not tie out: [{"period": "FY25", "check": "eps", "computed": .., "reported": ..}]."""
    problems: List[dict] = []
    for r in _ordered(rows):
        for check, v in reconcile_row(r, tolerance).items():
            if not v["ok"]:
                problems.append({"period": fiscal_year_label(r.get("period_end"), r.get("year")), "check": check, "computed": v["computed"], "reported": v["reported"]})
    return problems


REVENUE_BASIS_GAP = 0.01   # consolidated and standalone revenue further apart than this is flagged


def basis_gaps(consolidated: List[Row], standalone: List[Row], tolerance: float = REVENUE_BASIS_GAP) -> List[dict]:
    """Years where consolidated and standalone revenue differ by more than `tolerance` (1%). A parent with subsidiaries legitimately differs:
    this is not an error, but a screen that mixes the two bases (one year consolidated, the next standalone) is wrong, so every such year is
    reported and the ingest logs it. [{"period": "FY24", "consolidated": 247.82, "standalone": 189.61, "gapPct": 30.7}], oldest first."""
    stand = {parse_date(r.get("period_end")) or None: r for r in _ordered(standalone)}
    gaps: List[dict] = []
    for r in _ordered(consolidated):
        end = parse_date(r.get("period_end"))
        other = stand.get(end)
        if other is None:
            continue
        a, b = _revenue(r), _revenue(other)
        if a is None or b is None or not a or not b:
            continue
        gap = abs(a - b) / max(abs(a), abs(b))
        if gap > tolerance:
            gaps.append({"period": fiscal_year_label(r.get("period_end"), r.get("year")), "consolidated": a, "standalone": b, "gapPct": round(gap * 100, 1)})
    return gaps


MATERIAL_DISCONTINUED = 0.15   # profit from discontinued operations this large against net profit changes what the year's profit means


def with_continuing(table: dict) -> dict:
    """Adds `net_profit_continuing` (net profit without profit from discontinued operations, such as the gain when Tata Motors split off its
    commercial-vehicle business) when a period's discontinued profit is material. Reported net profit is left untouched: it is what the company
    announced. Ratios that judge the business (P/E, return on equity, margins, growth, score) use the continuing figure."""
    rows = table.get("rows") or {}
    np_, disc = rows.get("net_profit"), rows.get("discontinued_profit")
    if not np_ or not disc:
        return table
    cont, material = [], False
    for n, d in zip(np_, disc):
        if n is not None and d not in (None, 0) and abs(d) >= MATERIAL_DISCONTINUED * abs(n):
            cont.append(round(n - d, 2)); material = True
        else:
            cont.append(n)
    if material:
        rows["net_profit_continuing"] = cont
    return table


def calc_view(table: dict) -> dict:
    """The same table with net profit replaced by the continuing figure, for the calculations that judge the business."""
    rows = table.get("rows") or {}
    if "net_profit_continuing" not in rows:
        return table
    return {**table, "rows": {**rows, "net_profit": rows["net_profit_continuing"]}}


# ---------------------------------------------------------------- balance sheet

def _equity(r: Row) -> Optional[float]:
    """Equity that belongs to the company's own shareholders. Banks report share capital plus reserves instead."""
    owners = to_number(r.get("equityAttributableToOwnersOfParent"))
    if owners:   # the provider sends 0 for "not reported" on many small companies: that must not hide the total
        return crore(owners)
    total = to_number(r.get("totalEquity"))
    if total:
        return crore(total - (to_number(r.get("nonControllingInterest")) or 0))
    capital = _first(r, "capital", "equityCapital")      # banks say `capital`, other companies `equityCapital`; the older years often have only these two
    banked = sum_present(capital, r.get("reserves")) if capital is not None and r.get("reserves") is not None else None
    return crore(banked)


def _debt(r: Row) -> Optional[float]:
    """Everything the company has borrowed: bank loans, bonds and debentures, subordinated debt and (for a lender such as an NBFC,
    which funds itself that way) deposits. A bank's deposits are its raw material, not debt, so they are left out for banks."""
    parts = [r.get("borrowingsCurrent"), r.get("borrowingsNoncurrent"), r.get("borrowings"), r.get("debtSecurities"), r.get("subordinatedLiabilities")]
    if r.get("advances") in (None, 0):
        parts.append(r.get("deposits"))
    return sum_present(*parts)


def _borrowings(r: Row) -> Optional[float]:
    return crore(_debt(r))


def _liabilities(r: Row) -> Optional[float]:
    value = to_number(r.get("liabilities"))
    if value is None:   # banks give total assets and equity, not liabilities
        assets, equity = to_number(r.get("assets") or r.get("capitalAndLiabilities")), _equity(r)
        return crore(assets - equity * 1e7) if assets is not None and equity is not None else None
    return crore(value)


def _other_liabilities(r: Row) -> Optional[float]:
    """Liabilities other than borrowings. FinEdge's `liabilities` already includes borrowings,
    so subtract them to avoid double counting when the funding stack is drawn."""
    liabilities = to_number(r.get("liabilities"))
    borrowings = _debt(r) or 0
    return None if liabilities is None else crore(liabilities - borrowings)


BS_FIELDS = {
    "equity_capital": lambda r: crore(_first(r, "equityCapital", "capital")),
    "reserves": lambda r: crore(r.get("reserves")),
    "total_equity": _equity,
    "minority_interest": lambda r: crore(r.get("nonControllingInterest")),
    "borrowings": _borrowings,
    "other_liabilities": _other_liabilities,
    "total_liabilities": _liabilities,
    "total_assets": lambda r: crore(r.get("assets") or r.get("equityAndLiabilities") or r.get("capitalAndLiabilities")),
    "fixed_assets": lambda r: crore(r.get("propertyPlantAndEquipment") or r.get("fixedAssets")),
    "cwip": lambda r: crore(r.get("capitalWorkInProgress")),
    "investments": lambda r: crore(sum_present(r.get("currentInvestments"), r.get("noncurrentInvestments"))),
    "inventories": lambda r: crore(r.get("inventories")),
    "receivables": lambda r: crore(sum_present(r.get("tradeReceivablesCurrent"), r.get("tradeReceivablesNoncurrent"))),
    "cash": lambda r: crore(r.get("cashAndCashEquivalents")),
    "current_assets": lambda r: crore(r.get("currentAssets")),
    "current_liabilities": lambda r: crore(r.get("currentLiabilities")),
}


def balance_sheet(rows: List[Row], period: str = "yearly", limit: Optional[int] = None) -> dict:
    return _table(rows, period, BS_FIELDS, limit or 10)


# ---------------------------------------------------------------- cash flow

def _capex(r: Row) -> Optional[float]:
    values = [abs(v) for v in (to_number(r.get("purchaseOfPPEClassifiedAsInvesting")), to_number(r.get("purchaseOfFixed&IntangibleAssets"))) if v]
    if not values:
        return None if to_number(r.get("purchaseOfPPEClassifiedAsInvesting")) is None and to_number(r.get("purchaseOfFixed&IntangibleAssets")) is None else 0.0
    return crore(-max(values))


def _free_cash_flow(r: Row) -> Optional[float]:
    operating = to_number(r.get("cashFlowsFromOperatingActivities"))
    capex = _capex(r)
    if operating is None or capex is None:
        return None
    return round(operating / 1e7 + capex, 2)


CF_FIELDS = {
    "operating": lambda r: crore(r.get("cashFlowsFromOperatingActivities")),
    "investing": lambda r: crore(r.get("cashFlowsFromInvestingActivities")),
    "financing": lambda r: crore(r.get("cashFlowsFromFinancingActivities")),
    "net_cash_flow": lambda r: crore(r.get("netCashFlow")),
    "capex": _capex,
    "free_cash_flow": _free_cash_flow,
    "dividends_paid": lambda r: crore(r.get("dividendsPaidClassifiedAsFinancing")),
}


def cash_flow(rows: List[Row], period: str = "yearly", limit: Optional[int] = None) -> dict:
    return _table(rows, period, CF_FIELDS, limit or 10)


# ---------------------------------------------------------------- helpers for analytics

def series(table: dict, key: str) -> List[Optional[float]]:
    return list((table or {}).get("rows", {}).get(key) or [])


def latest(table: dict, key: str) -> Optional[float]:
    values = [v for v in series(table, key) if v is not None]
    return values[-1] if values else None


def is_bank(pl_rows: List[Row]) -> bool:
    """A lender: a bank, or an NBFC such as Bajaj Finance. Their income is mostly interest earned, their 'debt' is their raw material
    and their working capital, gross margin and asset turnover mean nothing, so those are not shown or scored for them."""
    for row in _ordered(pl_rows)[-2:]:
        interest = to_number(row.get("interestEarned")) or 0
        base = max(to_number(row.get("revenueFromOperations")) or 0, to_number(row.get("income")) or 0)
        if interest > 0 and (not to_number(row.get("revenueFromOperations")) or interest >= 0.5 * base):
            return True
    return False


def fiscal_year_end_month(table: dict) -> int:
    """The month the company's financial year ends, from its yearly statement dates (the most common month of the last five years). March when unknown."""
    months = []
    for end in (table.get("periodEnds") or [])[-5:]:
        d = parse_date(end) if end else None
        if d:
            months.append(d.month)
    return max(set(months), key=months.count) if months else 3
