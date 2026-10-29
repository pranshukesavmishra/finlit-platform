"""The indicative growth range for the next four quarters in total, versus the same four quarters a year earlier (= the latest four reported
quarters). Deterministic and built ONLY from the company's own reported history; see docs/OUTLOOK.md.

  base      T   = sum of the latest four quarters; T0 = the four before them (needs eight consecutive quarters, T0 > 0, T > 0)
  baseline  g_t = T / T0 - 1 (trailing four quarters, year on year); g_c = 3-year CAGR of the yearly figure when both ends are positive.
            Each is limited to [CAP_LOW, CAP_HIGH] first; baseline g0 = their average (g_t alone when no CAGR).
  spread    s   = population stdev of the company's quarterly year-on-year growth rates (at least four of them, latest eight quarters).
            A four-quarter total smooths quarter noise, so the half-width is w = s / 2, kept within [W_MIN, W_MAX] points.
  tilt      mid = g0 + (score - 50) / 50 * w / 2    (the outlook score nudges the middle by at most half the half-width; no score: no tilt)
  range     low = mid - w, high = mid + w; each limited to [CAP_LOW, CAP_HIGH]; a limited end is reported in `capped`.
"""

from __future__ import annotations

from typing import Optional

from .inputs import Inputs
from .scorers import cagr, quarterly_growth, stdev, ttm

CAP_LOW, CAP_HIGH = -40.0, 60.0
W_MIN, W_MAX = 3.0, 25.0
KEYS = {"profit": ("net_profit", "net profit (PAT)"), "revenue": ("revenue", "revenue")}


def _none(reason: str) -> dict:
    return {"available": False, "reason": reason}


def growth_range(kind: str, inp: Inputs, score: Optional[float]) -> dict:
    key, label = KEYS[kind]
    if len(inp.qp) < 8 or not inp.quarters_contiguous(8):
        return _none(f"Not enough history for a range: it needs eight consecutive reported quarters of {label}.")
    t, t0 = ttm(inp, key), ttm(inp, key, 4)
    if t is None or t0 is None:
        return _none(f"Not enough history for a range: a quarter of {label} is missing.")
    if t <= 0 or t0 <= 0:
        return _none(f"No range: {label} was not positive over the last eight quarters, so a growth percentage is not meaningful.")
    rates = quarterly_growth(inp, key)
    spread = stdev(rates, 4)
    if spread is None:
        return _none("Not enough history for a range: the quarterly year-on-year growth rates cannot all be worked out.")
    clamp = lambda v: max(CAP_LOW, min(CAP_HIGH, v))  # noqa: E731
    g_t = clamp((t / t0 - 1) * 100)
    g_c = cagr(inp.y(key, 0), inp.y(key, 3), 3)
    parts = [g_t] + ([clamp(g_c)] if g_c is not None else [])
    base = sum(parts) / len(parts)
    w = max(W_MIN, min(W_MAX, spread / 2))
    mid = base + ((score - 50) / 50 * w / 2 if score is not None else 0.0)
    raw = {"low": mid - w, "mid": mid, "high": mid + w}
    capped = [k for k, v in raw.items() if v < CAP_LOW or v > CAP_HIGH]
    out = {k: clamp(v) for k, v in raw.items()}
    amounts = {k: round(t * (1 + v / 100), 0) for k, v in out.items()}
    return {
        "available": True, "label": "Indicative scenario", "metric": label,
        "baselineQuarter": inp.qp[-1], "baselineAmountCr": round(t, 0),
        "baseline": f"the four quarters ended {inp.qp[-1]}",
        "low": round(out["low"], 1), "mid": round(out["mid"], 1), "high": round(out["high"], 1),
        "lowCr": amounts["low"], "midCr": amounts["mid"], "highCr": amounts["high"],
        "capped": capped, "cappedNote": f"Limited to {CAP_LOW:.0f}% to +{CAP_HIGH:.0f}%." if capped else None,
        "tilted": score is not None, "basedOn": ("trailing four quarters" + (" and the 3-year growth rate" if g_c is not None else "")),
    }
