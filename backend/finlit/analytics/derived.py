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
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    span = min(years, len(clean) - 1)
    start, end = clean[-1 - span], clean[-1]
    if start <= 0 or end <= 0:
        return None
    return {"value": round(((end / start) ** (1 / span) - 1) * 100, 2), "years": span}


def _growth(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if len(clean) < 2 or not clean[-2] or clean[-2] <= 0:
        return None
    return round((clean[-1] / clean[-2] - 1) * 100, 2)


def compute(pl: dict, bs: dict, cf: dict, ratios_latest: Dict[str, dict], basic_payload, market_cap_cr: Optional[float],
            dividend_yield: Optional[float]) -> Dict[str, Optional[float]]:
    rows = (pl or {}).get("rows", {})
    revenue, profit = rows.get("revenue") or [], rows.get("net_profit") or []
    out: Dict[str, Optional[float]] = {
        "opm": _latest_ratio(pl, "operating_profit", "revenue"),
        "npm": _latest_ratio(pl, "net_profit", "revenue"),
        "liabilities_to_assets": _latest_ratio(bs, "total_liabilities", "total_assets"),
        "sales_growth_latest": _growth(revenue),
        "profit_growth_latest": _growth(profit),
        "market_cap": market_cap_cr,
        "dividend_yield": dividend_yield,
    }

    # Cash conversion: align the latest year that has both CFO and PAT.
    cfo = dict(zip((cf or {}).get("periods", []), (cf or {}).get("rows", {}).get("operating") or []))
    fcf = dict(zip((cf or {}).get("periods", []), (cf or {}).get("rows", {}).get("free_cash_flow") or []))
    pat = dict(zip((pl or {}).get("periods", []), profit))
    common = [p for p in (pl or {}).get("periods", []) if cfo.get(p) is not None and pat.get(p)]
    if common:
        year = common[-1]
        out["cfo_to_pat"] = round(cfo[year] / pat[year] * 100, 2)
        out["fcf_to_pat"] = round(fcf[year] / pat[year] * 100, 2) if fcf.get(year) is not None else None

    sales_cagr = _cagr(revenue, 5)
    profit_cagr = _cagr(profit, 5)
    out["sales_cagr"] = (ratios_latest.get("revenue_cagr_5y") or {}).get("value") if ratios_latest.get("revenue_cagr_5y") else (sales_cagr or {}).get("value")
    out["sales_cagr_years"] = 5 if ratios_latest.get("revenue_cagr_5y") else (sales_cagr or {}).get("years")
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
