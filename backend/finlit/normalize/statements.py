"""Profit & loss, balance sheet and cash flow -> compact column-oriented tables in ₹ crore.

Output shape (oldest period first, so charts can draw left to right):

    {"unit": "Cr", "periods": ["FY21", ..., "FY26"], "periodEnds": [...],
     "rows": {"revenue": [..], "net_profit": [..], ...}}
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .common import crore, fiscal_year_label, parse_date, quarter_label, rnd, sum_present, to_number

Row = Dict[str, Any]


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
    return crore(value)


def _operating_profit(r: Row) -> Optional[float]:
    """Revenue - operating expenses, where operating expenses exclude finance costs and depreciation
    (the Screener.in convention FinLit users already know)."""
    revenue = to_number(r.get("revenueFromOperations"))
    expenses = to_number(r.get("expenses"))
    if revenue is None or expenses is None:
        return None
    operating_expenses = expenses - (to_number(r.get("financeCosts")) or 0) - (to_number(r.get("depreciationAndAmortisation")) or 0)
    return crore(revenue - operating_expenses)


PL_FIELDS = {
    "revenue": _revenue,
    "other_income": lambda r: crore(r.get("otherIncome")),
    "total_income": lambda r: crore(r.get("income")),
    "expenses": lambda r: crore(r.get("expenses")),
    "operating_profit": _operating_profit,
    "finance_costs": lambda r: crore(r.get("financeCosts")),
    "depreciation": lambda r: crore(r.get("depreciationAndAmortisation")),
    "exceptional_items": lambda r: crore(r.get("exceptionalItemsBeforeTax")),
    "profit_before_tax": lambda r: crore(r.get("profitBeforeTax")),
    "tax": lambda r: crore(r.get("taxExpense")),
    "net_profit": lambda r: crore(r.get("profitLossForPeriod")),
    "eps": lambda r: rnd(r.get("eps")),
    "diluted_shares_cr": lambda r: crore(r.get("dilutedOutstandingShares")),
}


def profit_and_loss(rows: List[Row], period: str = "yearly", limit: Optional[int] = None) -> dict:
    return _table(rows, period, PL_FIELDS, limit or (10 if period == "yearly" else 12))


# ---------------------------------------------------------------- balance sheet

def _borrowings(r: Row) -> Optional[float]:
    return crore(sum_present(r.get("borrowingsCurrent"), r.get("borrowingsNoncurrent")))


def _other_liabilities(r: Row) -> Optional[float]:
    """Liabilities other than borrowings. FinEdge's `liabilities` already includes borrowings,
    so subtract them to avoid double counting when the funding stack is drawn."""
    liabilities = to_number(r.get("liabilities"))
    borrowings = sum_present(r.get("borrowingsCurrent"), r.get("borrowingsNoncurrent")) or 0
    return None if liabilities is None else crore(liabilities - borrowings)


BS_FIELDS = {
    "equity_capital": lambda r: crore(r.get("equityCapital")),
    "reserves": lambda r: crore(r.get("reserves")),
    "total_equity": lambda r: crore(r.get("totalEquity") or r.get("equityAttributableToOwnersOfParent")),
    "minority_interest": lambda r: crore(r.get("nonControllingInterest")),
    "borrowings": _borrowings,
    "other_liabilities": _other_liabilities,
    "total_liabilities": lambda r: crore(r.get("liabilities")),
    "total_assets": lambda r: crore(r.get("assets") or r.get("equityAndLiabilities")),
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
    value = to_number(r.get("purchaseOfPPEClassifiedAsInvesting"))
    if not value:
        value = to_number(r.get("purchaseOfFixed&IntangibleAssets"))
    if value is None:
        return None
    return crore(-abs(value))


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
    """Banks and NBFCs report revenue as interest earned."""
    for row in _ordered(pl_rows)[-2:]:
        if (to_number(row.get("interestEarned")) or 0) > 0 and not to_number(row.get("revenueFromOperations")):
            return True
    return False
