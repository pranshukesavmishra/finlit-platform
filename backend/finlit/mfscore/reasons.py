"""Why a fund scored what it did (spec Section 9): the strongest and weakest measures by weighted points against the group value, written in plain words
from reasons.json, plus every measure that used the group value because data was missing, each with its cause. The words describe; they never advise."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from .model import Res, Score
from .toolkit import is_missing

LEVEL_NAMES = ("Low", "Low to Moderate", "Moderate", "Moderately High", "High", "Very High")
TOP_N = 3
MIN_EFFECT = 0.05      # weighted points (of 100) a measure must move the score against the group value to be called out


@lru_cache(maxsize=1)
def texts() -> Dict[str, Any]:
    with open(os.path.join(os.path.dirname(__file__), "reasons.json"), encoding="utf-8") as fh:
        return json.load(fh)


def indian(n: float, d: int = 0) -> str:
    """12345678.9 -> '1,23,45,679' (Indian digit grouping)."""
    neg = n < 0
    s = f"{abs(n):.{d}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + whole + ("." + frac if frac else "")


def fmt(kind: str, v: Optional[float]) -> str:
    if is_missing(v):
        return "n/a"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "pct2":
        return f"{v:.2f}%"
    if kind == "pct0":
        return f"{v:.0f}%"
    if kind == "pp":
        return f"{abs(v):.1f} percentage points"
    if kind == "x":
        return f"{v:.2f} times"
    if kind == "num2":
        return f"{v:.2f}" if v >= 0 else f"{v:.2f}".replace("-", "−")
    if kind == "yrs":
        return f"{v:.1f} years"
    if kind == "cr":
        return f"₹{indian(v)} crore" if v >= 10 else f"₹{v:.2f} crore"
    if kind == "level":
        return LEVEL_NAMES[max(0, min(5, round(v)))] + ("" if float(v).is_integer() else " (between two levels)")
    if kind == "levels":
        a = abs(v)
        return f"{a:.1f} level{'s' if a != 1 else ''}" if not float(a).is_integer() else f"{int(a)} level{'s' if a != 1 else ''}"
    return str(v)


def _fields(r: Res, spec: Dict[str, Any]) -> Dict[str, str]:
    f = spec.get("fmt", {})
    why = r.why or ""
    if r.id == "EXIT_LOAD":
        why = _exit_phrase(r)
    out = {"own": fmt(f.get("own", "num2"), r.own), "peer": fmt(f.get("peer", "num2"), r.peer), "value": "", "n": str(r.peer_n), "why": why}
    v = r.value
    if v is not None and f.get("value"):
        out["value"] = fmt(f["value"], abs(v) if f["value"] in ("pp", "levels", "pct2") else v)
    if r.id == "DOWN_CAPTURE":
        out["own"], out["peer"] = fmt("pct2", r.own), fmt("pct2", r.peer)
    if r.id in ("DD_RATIO", "VOL_RATIO") and r.own is not None:
        out["own"] = fmt("pct", r.own)
    if r.id == "DD_RATIO" and r.peer is not None:
        out["peer"] = fmt("pct", r.peer)
    if r.id == "ETF_PREMIUM":
        out["value"] = fmt("pct2", abs(r.own) if r.own is not None else None)
    return out


def _exit_phrase(r: Res) -> str:
    if r.value == 0:
        return "none"
    days = r.peer
    L = f"{r.value:g}%"
    if days is None:
        return L
    d = int(days)
    span = "7 days or less" if d <= 7 else f"{d} days" if d < 365 else "a year" if d == 365 else f"{d / 365:.1f} years"
    return f"{L} if sold within {span}"


def gap_text(r: Res) -> str:
    return texts()["gaps"].get(r.why or "", "no usable value")


def explain(s: Score, gvals: Optional[Dict[Any, float]] = None) -> Dict[str, Any]:
    """strengths, watchouts (top three each), gaps (every measure that used the group value) and the measures that did not apply."""
    if s.status == "NOT RATED" or not s.metrics:
        return {"strengths": [], "watchouts": [], "gaps": [], "notApplicable": [], "substitutions": []}
    t = texts()
    rows: List[Dict[str, Any]] = []
    gaps: List[Dict[str, Any]] = []
    na: List[Dict[str, Any]] = []
    subs: List[Dict[str, Any]] = []
    for r in s.metrics:
        spec = t["metrics"][r.id]
        if r.state in ("A", "S", "Z") and r.points is not None:
            gv = (gvals or {}).get((s.group, r.id), 50.0)
            rows.append({"id": r.id, "label": spec["label"], "effect": round(r.weight * (r.points - gv) / 100.0, 2), "points": round(r.points, 1), "groupValue": round(gv, 1), "res": r, "spec": spec})
            if r.state == "S" and r.why in t["substitutes"]:
                subs.append({"id": r.id, "label": spec["label"], "text": t["substitutes"][r.why]})
        elif r.state == "F":
            gaps.append({"id": r.id, "label": spec["label"], "why": r.why, "rule": r.rule, "text": gap_text(r)})
        elif r.state == "N":
            na.append({"id": r.id, "label": spec["label"], "text": t["na"].get(r.why or "", t["na"]["not_in_sheet"])})

    def line(row: Dict[str, Any], good: bool) -> Dict[str, Any]:
        r: Res = row["res"]
        key = "strong" if good else "weak"
        if r.state == "Z":
            text = _zero_text(r)
        else:
            text = row["spec"][key].format(**_fields(r, row["spec"]))
        return {"id": row["id"], "label": row["label"], "text": text, "points": row["points"], "groupValue": row["groupValue"], "effect": row["effect"], "state": r.state}
    pos = sorted((x for x in rows if x["effect"] > MIN_EFFECT), key=lambda x: -x["effect"])[:TOP_N]
    neg = sorted((x for x in rows if x["effect"] < -MIN_EFFECT), key=lambda x: x["effect"])[:TOP_N]
    return {"strengths": [line(x, True) for x in pos], "watchouts": [line(x, False) for x in neg], "gaps": gaps, "notApplicable": na, "substitutions": subs}


def _zero_text(r: Res) -> str:
    if r.id == "FEE_SHARE":
        return "Its 3-year return was zero or negative, so the share of return paid in costs scores 0."
    if r.id == "CALMAR":
        return "Its 3-year return was zero or negative, so return against its biggest fall scores 0."
    return "This measure scores 0 because the fund's return was zero or negative."
