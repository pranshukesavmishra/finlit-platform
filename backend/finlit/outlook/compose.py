"""Weights validation, the group and overall scores, renormalisation, bands. Pure."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from .inputs import Inputs
from .registry import GROUPS, Group, default_weights
from .scorers import Miss

MIN_COVERAGE = 0.5   # share of the (chosen) total weight that must be measurable for a score


class WeightError(ValueError):
    pass


def validate_weights(kind: str, weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """None -> the model's defaults. Otherwise every group of the tab, each 0-100, total 100 within 0.01."""
    if weights is None:
        return default_weights(kind)
    letters = {g.letter for g in GROUPS[kind]}
    if set(weights) != letters:
        extra, missing = sorted(set(weights) - letters), sorted(letters - set(weights))
        raise WeightError("Unknown group: " + ", ".join(extra) if extra else "Missing group: " + ", ".join(missing))
    out = {}
    for k, v in weights.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 100:
            raise WeightError(f"Group {k}: each percentage must be between 0 and 100.")
        out[k] = float(v)
    if abs(sum(out.values()) - 100) > 0.01:
        raise WeightError(f"The percentages must total 100 (they total {sum(out.values()):.2f}).")
    return out


def band(score: Optional[float]) -> dict:
    """The site's shared rule (frontend scoreBands.ts): green from 70, orange 50-69, red under 50. The word describes the outlook, not a rating."""
    if score is None:
        return {"key": "na", "color": "grey", "word": "Not available"}
    if score >= 70:
        return {"key": "hi", "color": "green", "word": "Supportive"}
    if score >= 50:
        return {"key": "mid", "color": "orange", "word": "Mixed"}
    return {"key": "lo", "color": "red", "word": "Subdued"}


@dataclass
class GroupResult:
    group: Group
    score: Optional[float]
    measured: int
    total: int
    measurable_weight: float   # sum of default weights of the measured parameters
    reasons: List[str]


def score_group(g: Group, inp: Inputs) -> GroupResult:
    num = den = 0.0
    measured, reasons = 0, []
    for p in g.params:
        r = p.fn(inp) if p.fn else Miss("not_stored")
        if isinstance(r, Miss):
            reasons.append(r.reason)
            continue
        num += p.weight * r
        den += p.weight
        measured += 1
    return GroupResult(g, num / den if den else None, measured, len(g.params), den, reasons)


def group_reason(r: GroupResult) -> Optional[str]:
    if r.score is not None:
        return None
    if "lender" in r.reasons:
        return "Not meaningful for banks and lenders."
    return r.group.unavailable


def compose(kind: str, inp: Inputs, weights: Dict[str, float]) -> dict:
    results = [score_group(g, inp) for g in GROUPS[kind]]
    total_measures = sum(r.total for r in results)
    measured = sum(r.measured for r in results)
    # share of the chosen total weight that can be worked out (a half-measured group counts for the half of its weight that is measured)
    cover = sum(weights[r.group.letter] * (r.measurable_weight / r.group.weight) for r in results) / 100.0
    live = [r for r in results if r.score is not None]
    live_w = sum(weights[r.group.letter] for r in live)
    score: Optional[float] = None
    reason: Optional[str] = None
    if cover < MIN_COVERAGE or live_w <= 0:
        reason = (f"Only {cover * 100:.0f}% of the model's weight can be worked out for this company; an outlook needs at least {MIN_COVERAGE * 100:.0f}%."
                  + (" Banks and lenders are measured on fewer of these figures." if inp.lender else ""))
    else:
        score = sum(weights[r.group.letter] * r.score for r in live) / live_w  # type: ignore[operator]
    groups = []
    for r in results:
        w = weights[r.group.letter]
        groups.append({
            "letter": r.group.letter, "name": r.group.name, "weightPct": round(w, 2),
            "effectiveWeightPct": round(w / live_w * 100, 2) if score is not None and r.score is not None and live_w else 0,
            "score": None if r.score is None else round(r.score, 1), "band": band(r.score),
            "coverage": {"measured": r.measured, "total": r.total},
            "status": "ok" if r.score is not None else "unavailable", "reason": group_reason(r),
        })
    return {
        "score": {"value": None if score is None else round(score, 1), "band": band(score), "reason": reason},
        "coverage": {"measured": measured, "total": total_measures, "weightPct": round(cover * 100, 1)},
        "groups": groups, "_raw_score": score,
    }
