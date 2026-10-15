"""Ratios from FinEdge ratio families, growth metrics, basic financials and price ratios.

FinEdge returns profitability/growth ratios as fractions (0.0693) and the rest as plain
numbers. Every value leaves this module in display units (6.93 %, 0.41 x, 101 days).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import parse_date, pct, rnd, to_number
from .glossary import GLOSSARY

# FinEdge key -> (our key, transform)
_PCT = pct
_X = rnd

FAMILY_MAP = {
    "pr": {
        "grossMargin": ("gross_margin", _PCT), "operatingMargin": ("operating_margin", _PCT),
        "ebitdaMargin": ("ebitda_margin", _PCT), "ebitMargin": ("ebit_margin", _PCT),
        "preTaxMargin": ("pretax_margin", _PCT), "netMargin": ("net_margin", _PCT),
        "effectiveTaxRate": ("effective_tax_rate", _PCT), "returnOnEquity": ("roe", _PCT),
        "returnOnCapital": ("roce", _PCT), "returnOnAsset": ("roa", _PCT),
        "returnOnTangibleAssets": ("rota", _PCT),
    },
    "le": {
        "totalDebtToEquity": ("debt_to_equity", _X), "longTermDebtToEquity": ("lt_debt_to_equity", _X),
        "financialLeverage": ("financial_leverage", _X), "totalDebttoAssets": ("debt_to_assets", _X),
        "totalDebtTofcf": ("debt_to_fcf", _X),
    },
    "li": {
        "currentRatio": ("current_ratio", _X), "quickRatio": ("quick_ratio", _X),
        "interestCoverage": ("interest_coverage", _X),
    },
    "ef": {
        "assetTurnover": ("asset_turnover", _X), "inventoryDays": ("inventory_days", _X),
        "debtorDays": ("debtor_days", _X), "daysPayable": ("payable_days", _X),
        "cashConversionCycle": ("cash_conversion_cycle", _X),
    },
    "basic": {
        "dividendPayout": ("dividend_payout", _PCT), "retentionRatio": ("retention_ratio", _PCT),
    },
}

GROWTH_MAP = {
    "revenueGrowth3years": "revenue_cagr_3y", "revenueGrowth5years": "revenue_cagr_5y",
    "netIncomeGrowth3years": "profit_cagr_3y", "netIncomeGrowth5years": "profit_cagr_5y",
    "epsGrowth5years": "eps_cagr_5y", "EBITDAGrowth5years": "ebitda_cagr_5y",
    "bookValueGrowth5Years": "book_value_cagr_5y", "cfoGrowth3years": "cfo_cagr_3y",
}

GROUPS = [
    {"id": "valuation", "label": "Valuation", "pillar": "valuation"},
    {"id": "returns", "label": "Returns on capital", "pillar": "quality"},
    {"id": "margins", "label": "Margins", "pillar": "profitability"},
    {"id": "growth", "label": "Growth", "pillar": "growth"},
    {"id": "leverage", "label": "Leverage", "pillar": "balance"},
    {"id": "liquidity", "label": "Liquidity & solvency", "pillar": "balance"},
    {"id": "efficiency", "label": "Efficiency", "pillar": "profitability"},
    {"id": "shareholder", "label": "Shareholder returns", "pillar": "valuation"},
    {"id": "quality", "label": "Earnings quality", "pillar": "quality"},
]


def _items(payload: Any, key: str) -> List[dict]:
    if isinstance(payload, dict):
        value = payload.get(key)
        return value if isinstance(value, list) else []
    return payload if isinstance(payload, list) else []


def _fy(row: dict) -> Optional[str]:
    header = str(row.get("header") or "")
    if header.upper() == "TTM":
        return "TTM"
    parsed = parse_date(f"01-{header[:3]}-{header[-4:]}") if len(header) >= 8 else None
    if parsed and parsed.month == 3:
        return f"FY{parsed.year % 100:02d}"
    return None  # interim headers such as "Dec 2024" are dropped from annual history


def family_rows(family: str, payload: Any) -> Dict[str, Dict[str, Optional[float]]]:
    """-> {"TTM": {key: value}, "FY26": {...}, ...}"""
    mapping = FAMILY_MAP[family]
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for row in _items(payload, "ratios"):
        label = _fy(row)
        if not label:
            continue
        values = out.setdefault(label, {})
        for source_key, (key, transform) in mapping.items():
            if source_key in row:
                values[key] = transform(row.get(source_key))
    return out


def build_ratios(payloads: Dict[str, Any], derived: Optional[Dict[str, Optional[float]]] = None) -> dict:
    """payloads: {"pr": ..., "le": ..., "li": ..., "ef": ..., "basic": ..., "gr": ...}."""
    by_period: Dict[str, Dict[str, Optional[float]]] = {}
    for family in ("pr", "le", "li", "ef", "basic"):
        for period, values in family_rows(family, payloads.get(family)).items():
            by_period.setdefault(period, {}).update(values)

    annual = sorted((p for p in by_period if p != "TTM"), key=lambda p: int(p[2:]))[-10:]
    latest: Dict[str, dict] = {}
    keys = {k for values in by_period.values() for k in values}
    for key in keys:
        value, period = None, None
        for candidate in ["TTM", *reversed(annual)]:
            v = by_period.get(candidate, {}).get(key)
            if v is not None:
                value, period = v, candidate
                break
        if value is not None:
            latest[key] = {"value": value, "period": period}

    growth = (payloads.get("gr") or {}).get("financial_metrics") if isinstance(payloads.get("gr"), dict) else None
    for source_key, key in GROWTH_MAP.items():
        value = pct((growth or {}).get(source_key))
        if value is not None:
            latest[key] = {"value": value, "period": "TTM"}

    for key, value in (derived or {}).items():
        if key.endswith("_years"):
            continue
        if value is not None and key not in latest:
            latest[key] = {"value": round(value, 2), "period": "latest"}
        elif value is not None and key in ("pe", "pb", "ps", "pfcf", "ev_ebitda", "dividend_yield", "market_cap", "cfo_to_pat", "fcf_to_pat", "liabilities_to_assets"):
            latest[key] = {"value": round(value, 2), "period": "latest"}

    for key, entry in latest.items():
        meta = GLOSSARY.get(key, {})
        entry.update({"label": meta.get("label", key), "unit": meta.get("unit"), "better": meta.get("better"), "group": meta.get("group")})

    history_keys = sorted(k for k in keys if any(by_period.get(p, {}).get(k) is not None for p in annual))
    return {
        "latest": latest,
        "groups": [{**g, "keys": sorted(k for k, e in latest.items() if e.get("group") == g["id"])} for g in GROUPS],
        "history": {"periods": annual, "rows": {k: [by_period.get(p, {}).get(k) for p in annual] for k in history_keys}},
    }


def price_ratio_latest(daily_payload: Any) -> Dict[str, Optional[float]]:
    rows = _items(daily_payload, "price_ratios")
    rows = sorted((r for r in rows if parse_date(r.get("quote_date"))), key=lambda r: parse_date(r["quote_date"]))
    if not rows:
        return {}
    last = rows[-1]
    out = {k: rnd(last.get(k)) for k in ("pe", "pb", "ps", "pfcf")}
    # FinEdge sends 0 when a ratio is undefined (e.g. negative earnings); hide rather than show 0.
    return {k: (v if v not in (0, 0.0) else None) for k, v in out.items()}


def valuation_history(annual_payload: Any) -> dict:
    """Annual P/E, P/B, P/S history for valuation-band charts (March year-ends only)."""
    rows = []
    for row in _items(annual_payload, "price_ratios"):
        label = _fy(row)
        if label and label != "TTM":
            rows.append((label, row))
    rows.sort(key=lambda item: int(item[0][2:]))
    rows = rows[-10:]

    def clean(v):
        number = to_number(v)
        return None if not number else round(number, 2)

    return {
        "periods": [label for label, _ in rows],
        "rows": {k: [clean(r.get(k)) for _, r in rows] for k in ("pe", "pb", "ps", "average_price")},
    }
