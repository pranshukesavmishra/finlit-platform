"""FinLit Prism on the Advanced score screener: the newest stored rating of every company, shaped into screener row fields.

Reads only the small `card` column and the rating columns of prism_reports (migration 070), never the report json. The technical words are the
site's descriptive ones (finlit/technical_wording.py), never the model's own. Plan rules are applied by the caller (auth/entitlements.redact_universe).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from .technical_wording import rating_word

PARTS = ("fundamental", "valuation", "quality", "risk")


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") else None


def shape(row: Dict[str, Any]) -> Dict[str, Any]:
    """One prism_reports row (symbol, final, label, status, generated_at, card) as the fields a screener row carries."""
    card = row.get("card")
    card = json.loads(card) if isinstance(card, str) else (card or {})
    parts = card.get("parts") if isinstance(card.get("parts"), dict) else {}
    out: Dict[str, Any] = {"prism_state": "stored", "prism_final": _num(row.get("final")), "prism_label": row.get("label"), "prism_status": row.get("status"),
                           "prism_at": row["generated_at"].date().isoformat() if row.get("generated_at") else None}
    for k in PARTS:
        out["prism_" + k] = _num(parts.get(k))
    for key, name in (("st", "prism_st"), ("lt", "prism_lt")):
        h = card.get(key) if isinstance(card.get(key), dict) else {}
        score = _num(h.get("score"))
        out[name + "_score"] = round(score, 1) if score is not None else None
        out[name] = rating_word(h.get("rating"), score) if score is not None else None      # no score: no word (the page says why)
    return out


def cards(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {r["symbol"]: shape(r) for r in rows}


def blank() -> Dict[str, Any]:
    """The fields of a company with no stored rating: present and empty, state 'none' (the page explains and offers to start one)."""
    return {"prism_state": "none", "prism_final": None, "prism_label": None, "prism_status": None, "prism_at": None, "prism_fundamental": None,
            "prism_valuation": None, "prism_quality": None, "prism_risk": None, "prism_st": None, "prism_lt": None, "prism_st_score": None, "prism_lt_score": None}


def coverage(rows: List[Dict[str, Any]], total: int) -> Dict[str, Any]:
    """Counts for 'rated X of Y companies', over all stored ratings (no company is named)."""
    rated = sum(1 for r in rows if r["status"] == "RATED")
    provisional = sum(1 for r in rows if r["status"] == "PROVISIONAL")
    return {"rated": rated, "provisional": provisional, "not_rated": len(rows) - rated - provisional, "stored": len(rows), "total": total}
