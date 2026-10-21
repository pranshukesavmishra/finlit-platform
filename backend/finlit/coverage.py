"""What the data provider sent for a company against what our report shows.

The rule this module exists to enforce: if the provider sent it, the report shows it. A gap is allowed only when the provider sent nothing, and
then the report says so in plain words instead of a bare dash. Every rebuild of a company records this comparison (`data_coverage`), the admin
Data health panel shows the totals, and any "provider sent it, report lacks it" line is a bug to fix, never a data gap.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _rows(payload: Any, *keys: str) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for k in keys + ("financials", "ratios", "price", "data", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return len(v)
    return 0


def _annual_rows(payload: Any) -> int:
    rows = (payload or {}).get("ratios") if isinstance(payload, dict) else None
    return sum(1 for r in (rows or []) if isinstance(r, dict) and str(r.get("header") or "").upper() != "TTM")


def _price(quote: Any, symbol: str) -> Optional[float]:
    q = (quote or {}).get(symbol) if isinstance(quote, dict) else None
    if not isinstance(q, dict):
        q = next((v for v in (quote or {}).values() if isinstance(v, dict)), None) if isinstance(quote, dict) else None
    try:
        v = float((q or {}).get("current_price"))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def provider_side(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """What the provider actually sent, as simple counts."""
    sym = str(bundle.get("symbol") or "").upper()
    closes = [r for r in ((bundle.get("daily_quotes") or {}).get("price") or []) if isinstance(r, dict) and (r.get("close_price") or 0) > 0] if isinstance(bundle.get("daily_quotes"), dict) else []
    sh = bundle.get("shareholding")
    return {
        "quote": _price(bundle.get("quote"), sym) is not None,
        "closes": len(closes),
        "annual": _rows(bundle.get("pl_annual")), "balance": _rows(bundle.get("bs_annual")), "cash": _rows(bundle.get("cf_annual")),
        "quarterly": _rows(bundle.get("pl_quarterly")),
        "ratios": max(_annual_rows(bundle.get(k)) for k in ("ratios_pr", "ratios_le", "ratios_li", "ratios_ef")),   # years of history (the TTM row is not a year)
        "ratios_ttm": any(_rows(bundle.get(k)) > 0 for k in ("ratios_pr", "ratios_le", "ratios_li", "ratios_ef")),
        "shareholding": _rows(sh, "rows") if isinstance(sh, dict) else _rows(sh),
        "peers": len((bundle.get("peers") or {}).get("peers") or []) if isinstance(bundle.get("peers"), dict) else 0,
    }


def report_side(sections: Dict[str, Any]) -> Dict[str, Any]:
    """The same counts, read from the finished report."""
    summary = sections.get("summary") or {}
    fin = (sections.get("financials") or {})
    yearly, quarterly = (fin.get("yearly") or {}), ((fin.get("quarterly") or {}).get("pl") or {})
    daily = (sections.get("price") or {}).get("daily") or {}
    ratios = (sections.get("ratios") or {}).get("history") or {}
    own = sections.get("ownership") or {}
    return {
        "price": (summary.get("quote") or {}).get("price") not in (None, 0),
        "bars": len(daily.get("t") or []),
        "annual": len((yearly.get("pl") or {}).get("periods") or []), "balance": len((yearly.get("bs") or {}).get("periods") or []), "cash": len((yearly.get("cf") or {}).get("periods") or []),
        "quarterly": len(quarterly.get("periods") or []),
        "ratios": len(ratios.get("periods") or []),
        "ratios_latest": len((sections.get("ratios") or {}).get("latest") or {}),
        "shareholding": len((own.get("series") or {}).get("periods") or own.get("periods") or []),
    }


def assess(bundle: Dict[str, Any], sections: Dict[str, Any]) -> Dict[str, Any]:
    """{state, reasons, mismatches, provider, report}. state: complete | partial | empty. mismatches must always be empty."""
    p, r = provider_side(bundle), report_side(sections)
    mismatches: List[str] = []
    if p["quote"] and not r["price"] and p["closes"] == 0:
        mismatches.append("the provider sent a live price but the report has none")
    for key, label in (("annual", "annual profit and loss"), ("balance", "balance sheet"), ("cash", "cash flow"), ("quarterly", "quarterly results"), ("ratios", "ratios")):
        if p[key] > 0 and r[key] == 0:
            mismatches.append(f"the provider sent {p[key]} rows of {label} but the report shows none")
    if p["ratios_ttm"] and r["ratios_latest"] == 0:
        mismatches.append("the provider sent current ratios but the report shows none")
    if p["closes"] > 0 and r["bars"] == 0:
        mismatches.append("the provider sent price history but the report has none")
    reasons: List[str] = []
    if not p["quote"]:
        reasons.append("no live price from the data provider" + ("" if p["closes"] else " and no traded prices on record") if not r["price"] else "no live quote; the last close is shown")
    if p["annual"] == 0:
        reasons.append("no annual financial statements from the data provider")
    if p["quarterly"] == 0 and p["annual"] > 0:
        reasons.append("no quarterly results from the data provider")
    if p["ratios"] == 0 and p["annual"] > 0:
        reasons.append("no ratio history from the data provider")   # only the latest (TTM) ratios, or none
    have = (p["quote"] or p["closes"] > 0, p["annual"] > 0, p["quarterly"] > 0, p["ratios"] > 0)
    state = "empty" if not any(have) else "complete" if (p["quote"] or p["closes"] > 0) and p["annual"] > 0 else "partial"
    return {"state": state, "reasons": reasons, "mismatches": mismatches, "provider": p, "report": r}
