"""The Funds category dashboard: per sub-category, the median Health score of its scored Direct-plan funds, how many were scored and how they split into the
site's three colour bands (green 70 and over, orange 50 to under 70, red under 50). Pure functions; the route is in api.py.
A "scored" fund is one with a final score (RATED or PROVISIONAL); NOT RATED funds have none and are not counted, and neither are funds not scored yet."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

GREEN, ORANGE = 70.0, 50.0


def median(vals: List[float]) -> Optional[float]:
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def band_of(score: float) -> str:
    return "green" if score >= GREEN else "orange" if score >= ORANGE else "red"


def summarize(rows: Iterable[Tuple[str, Optional[float]]]) -> Dict[str, dict]:
    """(sub-category key, final score or None) -> {key: {median, n, green, orange, red}} (counts, not shares). A key with no scored fund is left out."""
    by: Dict[str, List[float]] = {}
    for sub, final in rows:
        if final is not None:
            by.setdefault(sub, []).append(float(final))
    out: Dict[str, dict] = {}
    for sub, vals in by.items():
        c = {"green": 0, "orange": 0, "red": 0}
        for v in vals:
            c[band_of(v)] += 1
        out[sub] = {"median": round(median(vals), 1), "n": len(vals), **c}
    return out
