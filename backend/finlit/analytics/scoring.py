"""FinLit research score — model v1.

A faithful server-side port of the score the current site computes in the browser
(StockFundamentalsAdminPage.jsx `buildResearchReport`, `scoreFromThresholds`, `scoreLabel`),
so numbers do not jump when we switch over. Each input maps to 18 / 38 / 58 / 76 / 92 using
four thresholds; a pillar is the mean of its available inputs; the overall score is the mean
of available pillars. Bands: Strong ≥ 78, Healthy ≥ 62, Mixed ≥ 45, Watch < 45.

Keeping the model versioned lets the Gold "advanced model" (v2) ship alongside it.
"""

from __future__ import annotations

from typing import Dict, List, Optional

MODEL_VERSION = "v1"

# (pillar, input key, label, thresholds weak/fair/good/great, lower_is_better)
PILLARS: Dict[str, dict] = {
    "quality": {"label": "Quality", "inputs": [
        ("roe", "ROE", (6, 10, 14, 18), False),
        ("roce", "ROCE", (7, 12, 16, 22), False),
        ("cfo_to_pat", "CFO / PAT", (40, 70, 95, 120), False),
    ]},
    "growth": {"label": "Growth", "inputs": [
        ("sales_cagr", "Sales CAGR", (2, 6, 10, 16), False),
        ("profit_cagr", "Profit CAGR", (2, 8, 14, 22), False),
        ("sales_growth_latest", "Latest sales growth", (0, 5, 10, 18), False),
    ]},
    "profitability": {"label": "Profitability", "inputs": [
        ("opm", "Operating margin", (6, 10, 15, 22), False),
        ("npm", "Net margin", (4, 7, 10, 16), False),
        ("asset_turnover", "Asset turnover", (0.3, 0.6, 0.9, 1.3), False),
    ]},
    "balance": {"label": "Balance sheet", "inputs": [
        ("liabilities_to_assets", "Liabilities / assets", (80, 65, 50, 35), True),
        ("cfo_to_pat", "CFO / PAT", (40, 70, 95, 120), False),
    ]},
    "technical": {"label": "Technical", "inputs": [
        ("vsEma50Pct", "Price vs 50-day EMA", (-8, -2, 2, 8), False),
        ("vsEma200Pct", "Price vs 200-day EMA", (-12, -3, 3, 12), False),
        ("rsi14", "RSI (14)", (35, 45, 55, 65), False),
    ]},
}


def input_score(value: Optional[float], thresholds, lower_is_better: bool = False) -> Optional[int]:
    if value is None:
        return None
    weak, fair, good, great = thresholds
    if lower_is_better:
        return 92 if value <= great else 76 if value <= good else 58 if value <= fair else 38 if value <= weak else 18
    return 92 if value >= great else 76 if value >= good else 58 if value >= fair else 38 if value >= weak else 18


def band(score: Optional[float]) -> dict:
    if score is None:
        return {"key": "insufficient", "label": "Not scored yet"}
    if score >= 78:
        return {"key": "strong", "label": "Strong"}
    if score >= 62:
        return {"key": "healthy", "label": "Healthy"}
    if score >= 45:
        return {"key": "mixed", "label": "Mixed"}
    return {"key": "watch", "label": "Watch"}


def _mean(values: List[Optional[float]]) -> Optional[int]:
    usable = [v for v in values if v is not None]
    return int(sum(usable) / len(usable) + 0.5) if usable else None   # half up, the same as the website's Math.round


def score(metrics: Dict[str, Optional[float]]) -> dict:
    pillars = []
    for key, spec in PILLARS.items():
        inputs = []
        for metric, label, thresholds, lower in spec["inputs"]:
            value = metrics.get(metric)
            inputs.append({"key": metric, "label": label, "value": value,
                           "score": input_score(value, thresholds, lower),
                           "thresholds": list(thresholds), "lowerIsBetter": lower})
        pillar_score = _mean([i["score"] for i in inputs])
        pillars.append({"key": key, "label": spec["label"], "score": pillar_score, "band": band(pillar_score),
                        "inputs": inputs, "coverage": sum(i["value"] is not None for i in inputs) / len(inputs)})
    overall = _mean([p["score"] for p in pillars])
    return {"model": MODEL_VERSION, "overall": overall, "band": band(overall), "pillars": pillars}
