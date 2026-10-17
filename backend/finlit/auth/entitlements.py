"""What each plan may see, enforced on the server.

The website also locks features visually, but that is presentation only: anything a plan does not include is removed here,
before it leaves the API. Visitors and Basic accounts are treated the same. Responses that differ by plan are marked
`private` so no shared cache can hand a Gold response to someone else.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

RANK = {"basic": 0, "bronze": 1, "gold": 2}
PLANS = tuple(RANK)

# The ratio history cards (Bronze) read these five; the full multi-year table (Gold) reads all of them.
BRONZE_HISTORY_KEYS = ("gross_margin", "operating_margin", "net_margin", "roe", "roce")
GOLD_RATIO_GROUPS = {"leverage", "liquidity", "efficiency", "quality", "shareholder"}
# Technical fields a Bronze account may keep (the 50-day average and the 200-day gap show in the free stats row).
KEEP_TECHNICAL = ("price", "ema50", "vsEma200Pct")
MODEL_FIELDS = ("overall", "band", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical")

LIMITS = {
    "basic": {"watchlist_lists": 0, "watchlist_symbols": 0, "screens": 3, "compare": 2, "holdings": 0},
    "bronze": {"watchlist_lists": 3, "watchlist_symbols": 30, "screens": 20, "compare": 2, "holdings": 30},
    "gold": {"watchlist_lists": 50, "watchlist_symbols": 1000, "screens": 100, "compare": 4, "holdings": 500},
}


def has(plan: str, tier: str) -> bool:
    return RANK.get(plan, 0) >= RANK[tier]


def varies_by_plan(section: str) -> bool:
    return section in ("summary", "ratios", "segments", "stats") or section.startswith("price-")


def redact_section(section: str, data: Dict[str, Any], plan: str) -> Dict[str, Any]:
    """Return `data` with everything above `plan` removed. `data` is modified in place and returned."""
    if has(plan, "gold"):
        return data
    bronze = has(plan, "bronze")
    if section == "summary":
        if not bronze:
            score = data.get("score") or {}
            score["overall"] = None
            score["band"] = {"key": "locked", "label": "Locked"}
            for p in score.get("pillars", []):
                p["score"] = None
                p["band"] = {"key": "locked", "label": "Locked"}
            data["thesis"] = None
            data["strengths"] = []
            data["watchouts"] = []
    elif section == "ratios":
        history = data.get("history") or {}
        rows = history.get("rows") or {}
        history["rows"] = {} if not bronze else {k: v for k, v in rows.items() if k in BRONZE_HISTORY_KEYS}
        vh = data.get("valuationHistory") or {}
        vh["rows"] = {}
        vh["periods"] = []
        latest = data.get("latest") or {}
        for group in data.get("groups", []):
            if group["id"] in GOLD_RATIO_GROUPS:
                for key in group["keys"][2:]:
                    latest.pop(key, None)
                group["keys"] = group["keys"][:2]
        score = data.get("score") or {}
        if not bronze:
            score["overall"] = None
            score["band"] = {"key": "locked", "label": "Locked"}
            for p in score.get("pillars", []):
                p["score"] = None
                p["inputs"] = []
    elif section == "stats":
        if not bronze:  # the price-statistics charts are a Bronze feature
            data.clear()
            data["available"] = False
            data["locked"] = True
    elif section == "segments":
        data["segments"], data["latest"], data["periods"] = {}, [], []
    elif section.startswith("price-"):
        tech = data.get("technical")
        if tech:
            data["technical"] = {k: v for k, v in tech.items() if k in KEEP_TECHNICAL}
        series = data.get("series")
        if series:
            series.pop("ema200", None)
    return data


def redact_universe(rows: list, plan: str, showcase: set) -> list:
    """The screener list: model scores are a Bronze feature (the showcase company stays open as the free example)."""
    if has(plan, "bronze"):
        return rows
    out = []
    for r in rows:
        if r.get("symbol") in showcase:
            out.append(r)
            continue
        r = dict(r)
        for f in MODEL_FIELDS:
            r[f] = None
        out.append(r)
    return out
