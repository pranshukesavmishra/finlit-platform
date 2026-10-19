"""Metrics derived from statements, prices and corporate actions."""

from __future__ import annotations

from typing import Dict, List, Optional

from ..normalize.common import crore, to_number


def _pairs(table: dict, a: str, b: str):
    rows = (table or {}).get("rows", {})
    return list(zip(rows.get(a) or [], rows.get(b) or []))


def _latest_ratio(table: dict, numerator: str, denominator: str, scale: float = 100) -> Optional[float]:
    for num, den in reversed(_pairs(table, numerator, denominator)):
        if num is not None and den:
            return round(num / den * scale, 2)
    return None


def _cagr(values: List[Optional[float]], years: int) -> Optional[dict]:
    """Compound growth over up to `years` years, counted by position so a missing year is not skipped over."""
    if len(values) < 2 or values[-1] is None:
        return None
    span = min(years, len(values) - 1)
    start, end = values[-1 - span], values[-1]
    while start is None and span > 1:   # the first year is missing: use the nearest later one and count the years honestly
        span -= 1
        start = values[-1 - span]
    if start is None or start <= 0 or end <= 0 or span < 1:
        return None
    return {"value": round(((end / start) ** (1 / span) - 1) * 100, 2), "years": span}


def _growth(values: List[Optional[float]]) -> Optional[float]:
    if len(values) < 2 or values[-1] is None or values[-2] is None or values[-2] <= 0:
        return None
    return round((values[-1] / values[-2] - 1) * 100, 2)


def compute(pl: dict, bs: dict, cf: dict, ratios_latest: Dict[str, dict], basic_payload, market_cap_cr: Optional[float],
            dividend_yield: Optional[float], lender: bool = False, pl_q: Optional[dict] = None) -> Dict[str, Optional[float]]:
    rows = (pl or {}).get("rows", {})
    revenue, profit = rows.get("revenue") or [], rows.get("net_profit") or []
    base = "total_income" if lender and rows.get("total_income") else "revenue"   # a lender's profit is measured against all its income
    out: Dict[str, Optional[float]] = {
        "opm": _latest_ratio(pl, "operating_profit", base),
        "npm": _latest_ratio(pl, "net_profit", base),
        "liabilities_to_assets": None if lender else _latest_ratio(bs, "total_liabilities", "total_assets"),
        "sales_growth_latest": _growth(revenue),
        "profit_growth_latest": _growth(profit),
        "growth_basis": None,
        "market_cap": market_cap_cr,
        "dividend_yield": dividend_yield,
    }

    # A recently listed company may have a single annual result but several quarters: then growth is the latest quarter against the same
    # quarter a year earlier (and says so), rather than no growth at all.
    qrows = (pl_q or {}).get("rows", {})
    qrev, qprofit = qrows.get("revenue") or [], qrows.get("net_profit") or []
    if out["sales_growth_latest"] is None and len(qrev) >= 5 and qrev[-1] is not None and qrev[-5] is not None and qrev[-5] > 0:
        out["sales_growth_latest"] = round((qrev[-1] / qrev[-5] - 1) * 100, 2)
        out["growth_basis"] = "quarter"
    if out["profit_growth_latest"] is None and len(qprofit) >= 5 and qprofit[-1] is not None and qprofit[-5] is not None and qprofit[-5] > 0:
        out["profit_growth_latest"] = round((qprofit[-1] / qprofit[-5] - 1) * 100, 2)
        out["growth_basis"] = "quarter"
    out = {k: v for k, v in out.items() if k != "growth_basis" or v}

    # Cash conversion: align the latest year that has both CFO and PAT.
    cfo = dict(zip((cf or {}).get("periods", []), (cf or {}).get("rows", {}).get("operating") or []))
    fcf = dict(zip((cf or {}).get("periods", []), (cf or {}).get("rows", {}).get("free_cash_flow") or []))
    pat = dict(zip((pl or {}).get("periods", []), profit))
    common = [p for p in (pl or {}).get("periods", []) if cfo.get(p) is not None and pat.get(p) and pat[p] > 0]
    if common and not lender:
        year = common[-1]
        out["cfo_to_pat"] = round(cfo[year] / pat[year] * 100, 2)
        out["fcf_to_pat"] = round(fcf[year] / pat[year] * 100, 2) if fcf.get(year) is not None else None

    sales_cagr = _cagr(revenue, 5)
    profit_cagr = _cagr(profit, 5)
    # one-off gains inside profit (e.g. a tax or asset-sale gain): how much of pre-tax profit they are
    exc, pbt = rows.get("exceptional_items") or [], rows.get("profit_before_tax") or []
    if exc and pbt and exc[-1] is not None and pbt[-1]:
        out["exceptional_share"] = round(exc[-1] / abs(pbt[-1]) * 100, 1)
    # Sales growth is measured on the same sales line the statements show (for a lender, on its total income), not the provider's
    # total-income figure that sat beside a revenue table it did not match. The profit growth is the provider's attributable-profit CAGR.
    sales_series = revenue   # the Revenue line of the statements table (a lender: interest earned), so growth and table agree
    for yrs in (3, 5):
        c = _cagr(sales_series, yrs)
        if c and c["years"] == yrs:
            out[f"revenue_cagr_{yrs}y"] = c["value"]
    best = _cagr(sales_series, 5)
    out["sales_cagr"] = (best or {}).get("value") if best else (ratios_latest.get("revenue_cagr_5y") or {}).get("value")
    out["sales_cagr_years"] = (best or {}).get("years") if best else (5 if ratios_latest.get("revenue_cagr_5y") else None)
    out["profit_cagr"] = (ratios_latest.get("profit_cagr_5y") or {}).get("value") if ratios_latest.get("profit_cagr_5y") else (profit_cagr or {}).get("value")
    out["profit_cagr_years"] = 5 if ratios_latest.get("profit_cagr_5y") else (profit_cagr or {}).get("years")

    # EV/EBITDA from TTM EBITDA (basic financials, rupees) and latest balance sheet.
    ebitda = None
    for row in (basic_payload or {}).get("ratios", []) if isinstance(basic_payload, dict) else []:
        if str(row.get("header")).upper() == "TTM":
            ebitda = crore(row.get("ebitda"))
            break
    bs_rows = (bs or {}).get("rows", {})
    borrowings = next((v for v in reversed(bs_rows.get("borrowings") or []) if v is not None), 0) or 0
    cash = next((v for v in reversed(bs_rows.get("cash") or []) if v is not None), 0) or 0
    if market_cap_cr and ebitda and ebitda > 0:
        out["ev_ebitda"] = round((market_cap_cr + borrowings - cash) / ebitda, 2)
    return out
