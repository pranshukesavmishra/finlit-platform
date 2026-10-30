"""The scoring engine: a whole universe of funds in, one Score per fund out. Pure code, no database, no clock (the run date is a parameter).

Passes
  1. history, peer-eligibility and peer scopes for every fund                                  (peers.py)
  2. each fund's metrics against its group's sheet, states A / Z / S / F / N                    (metrics.py, sheets.py)
  3. group values: per group and metric, min(median of the points of funds that have a real value, 50); 50 when fewer than 8 funds have one
  4. a metric in state F takes the group value; pillars; FINAL = weighted pillars; weak-fund cap; label; data confidence; status
  5. rank and percentile inside the category (the tracking family for index funds and ETFs)
  6. reasons: the strongest and weakest measures by weighted points against the group value

Decisions where the draft is silent (spec Sections 8 to 12 are not in the PDF) are listed in docs/mf-score/README.md and flagged there as designer
decisions pending confirmation: labels, the weak-fund cap, the confidence thresholds, how ranks are scoped."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from . import metrics as M
from .groups import NEAR_IDENTICAL_SUBS
from .model import FundIn, Res, Score
from .peers import Calc, Space, build_calc
from .reasons import explain
from .sheets import MIN_GROUP_VALUES, PILLARS, SHEETS, WEIGHTS
from .toolkit import median, pillar, pillar_all_n

LABELS = ((80.0, "Strong"), (65.0, "Healthy"), (50.0, "Average"), (35.0, "Weak"), (0.0, "Poor"))   # the words and edges of the FinLit / Prism labels
CAP_ORDER = {"Strong": 0, "Healthy": 1, "Average": 2, "Weak": 3, "Poor": 4}
WINDOW_METRICS = frozenset({"HIT_RATE", "VOL_RATIO", "DD_RATIO", "DOWN_CAPTURE", "SHARPE_REL", "SHARPE_ABS", "WORST12_REL", "WORST_MONTH", "MDD_ABS", "NEG_MONTHS", "UNDERWATER", "CALMAR"})
# weak-fund cap (design rule 6): a high return must not hide weak risk or weak foundations. Designer decision pending confirmation.
CAP_RULES = (35.0, 64.0), (50.0, 79.0)       # (pillar below, final capped at)
CONF_NOT_RATED = 0.30                        # data confidence below this: NOT RATED (designer decision pending confirmation)
CONF_PROVISIONAL = 0.60                      # below this: PROVISIONAL, the label is capped at Healthy
RANK_MIN = 3                                 # a rank needs at least this many scored funds in the scope


def label_of(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    s = round(score, 1)
    return next(w for edge, w in LABELS if s >= edge)


def cap_label(label: Optional[str], at: str = "Healthy") -> Optional[str]:
    """The label, but never above `at` (PROVISIONAL scores: at most Healthy)."""
    if label is None:
        return None
    return at if CAP_ORDER[label] < CAP_ORDER[at] else label


def weak_cap(risk: float, quality: float) -> Tuple[Optional[float], Optional[str]]:
    """(cap, text): the lowest cap that applies, from the weaker of the Risk and Quality pillars."""
    low = min(risk, quality)
    name = "Risk" if risk <= quality else "Quality"
    for below, cap in CAP_RULES:
        if low < below:
            return cap, f"{name} is below {below:.0f}, so the score is held at {cap:.0f} at most"
    return None, None


def _not_rated(f: FundIn, c: Calc, reason: str) -> Score:
    s = Score(key=f.key, kind=f.kind, group=f.group, plan=f.plan, status="NOT RATED", months=c.h.months, reason=reason, counters=dict(c.counters))
    s.near_identical = f.sub in NEAR_IDENTICAL_SUBS
    return s


def _metrics_of(c: Calc, space: Space) -> List[Res]:
    sheet = SHEETS[c.f.group]
    V = M.family_v(c, space) if c.f.group in ("OT-PASSIVE", "OT-OTHER") else 1.0
    out: List[Res] = []
    for p in PILLARS:
        for m in sheet[p]:
            out.append(M.compute_metric(c, space, p, m, V))
    return out


def group_values(per_group: Dict[str, List[List[Res]]]) -> Dict[Tuple[str, str], float]:
    """(group, metric) -> group value: min(median of the points of funds with a real value for it, 50). With fewer than 8 such funds there is no reliable
    median and the value is 50. A median that is genuinely 0 stays 0: the typical fund scores 0, so a gap may not score higher."""
    pts: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for g, fund_results in per_group.items():
        for results in fund_results:
            for r in results:
                if r.state in ("A", "Z", "S") and r.points is not None:
                    pts[(g, r.id)].append(r.points)
    out: Dict[Tuple[str, str], float] = {}
    for g in per_group:
        for mid in {m.id for p in PILLARS for m in SHEETS[g][p]}:
            vals = pts.get((g, mid), [])
            out[(g, mid)] = min(median(vals), 50.0) if len(vals) >= MIN_GROUP_VALUES else 50.0
    return out


def finish(f: FundIn, c: Calc, results: List[Res], gvals: Dict[Tuple[str, str], float]) -> Score:
    """Pillars, final score, cap, label, confidence and status of one fund whose metrics are worked out."""
    s = Score(key=f.key, kind=f.kind, group=f.group, plan=f.plan, months=c.h.months, metrics=results, counters=dict(c.counters))
    s.near_identical = f.sub in NEAR_IDENTICAL_SUBS
    wp = WEIGHTS[f.group]
    by_pillar: Dict[str, List[Res]] = {p: [] for p in PILLARS}
    for r in results:
        if r.state == "F":
            r.gv = gvals[(f.group, r.id)]
            r.points = r.gv
        by_pillar[r.pillar].append(r)
    total_w = real_w = 0.0
    final = 0.0
    for p, w_final in zip(PILLARS, wp):
        items = by_pillar[p]
        pts = [None if r.state == "N" else r.points for r in items]
        wts = [r.wt for r in items]
        value = pillar(pts, wts)
        flag = pillar_all_n(pts, wts)
        s.pillars[p] = value
        s.pillar_flags[p] = flag
        final += w_final * value / 100.0
        live = sum(wt for q, wt in zip(pts, wts) if q is not None)
        if live == 0:
            total_w += w_final      # a pillar of only N: neutral 50, counted as missing in the confidence
            continue
        for r in items:
            if r.state == "N":
                continue
            r.weight = w_final * r.wt / live
            total_w += r.weight
            if r.state in ("A", "Z", "S"):
                real_w += r.weight * (c.h.cred if r.id in WINDOW_METRICS else 1.0)
                r.cred = c.h.cred if r.id in WINDOW_METRICS else 1.0
    s.confidence = real_w / total_w if total_w else 0.0
    s.raw_final = final
    cap, cap_text = weak_cap(s.pillars["risk"], s.pillars["quality"])
    if cap is not None and final > cap:
        final, s.cap = cap, cap_text
    s.final = round(final, 1)
    s.label = label_of(s.final)
    # status: the history rows of spec Section 3, then the data confidence (designer decision)
    if c.row == "window":
        s.status = "PROVISIONAL"
        s.reason = f"only {c.h.months} months of NAV history (12 to 35): measures on a short window are trusted in proportion to its length"
    else:
        s.status = "RATED"
    if s.confidence < CONF_NOT_RATED:
        s.status, s.reason = "NOT RATED", f"only {s.confidence * 100:.0f}% of the measures behind the score had real data"
    elif s.confidence < CONF_PROVISIONAL and s.status == "RATED":
        s.status, s.reason = "PROVISIONAL", f"only {s.confidence * 100:.0f}% of the measures behind the score had real data"
    if s.status == "PROVISIONAL":
        s.label = cap_label(s.label, "Healthy")
    if s.status == "NOT RATED":
        s.final = s.label = None
        s.pillars = {p: None for p in PILLARS}
    s.peer_kind = _widest(results)
    s.peer_n = max((r.peer_n for r in results if r.scope), default=0)
    s.flags = _flags(c, s)
    s.reasons = explain(s, gvals)
    return s


def _widest(results: Sequence[Res]) -> Optional[str]:
    used = {r.scope for r in results if r.scope}
    for k in ("grp", "sub", "fam"):
        if k in used:
            return k
    return None


def _flags(c: Calc, s: Score) -> List[str]:
    out: List[str] = []
    if c.h.frozen:
        out.append("FROZEN_NAV")
    if c.h.break_flag:
        out.append("NAV_BREAK")
    if s.status == "PROVISIONAL":
        out.append("PROVISIONAL")
    if s.cap:
        out.append("WEAK_CAP")
    if any(s.pillar_flags.values()):
        out.append("PILLAR_ALL_N")
    if s.near_identical:
        out.append("NEAR_IDENTICAL")
    return out


def rank_all(scores: List[Score], funds: Dict[str, FundIn]) -> None:
    """Rank and percentile inside the category and plan (the tracking family for index funds and ETFs). Ties share a rank; funds without a score are not ranked."""
    scope_of: Dict[str, str] = {}
    members: Dict[str, List[Score]] = defaultdict(list)
    fam_size: Dict[str, int] = defaultdict(int)
    for s in scores:
        f = funds[s.key]
        if s.final is not None and f.family_key and f.group == "OT-PASSIVE":
            fam_size[f"fam:{f.family_key}|{f.kind}|{f.plan}"] += 1
    for s in scores:
        f = funds[s.key]
        if s.final is None:
            continue
        key = f"fam:{f.family_key}|{f.kind}|{f.plan}" if f.group == "OT-PASSIVE" and f.family_key and fam_size[f"fam:{f.family_key}|{f.kind}|{f.plan}"] >= RANK_MIN \
            else f"sub:{f.sub}|{f.plan}|{f.kind}"
        scope_of[s.key] = key
        members[key].append(s)
    for key, group in members.items():
        n = len(group)
        if n < RANK_MIN:
            continue
        vals = sorted(g.final for g in group)
        from bisect import bisect_left, bisect_right
        for g in group:
            g.rank = 1 + (n - bisect_right(vals, g.final))
            g.rank_of = n
            g.rank_scope = key.split(":", 1)[0]
            g.percentile = round(100.0 * bisect_left(vals, g.final) / (n - 1), 0) if n > 1 else None


def score_universe(funds: Sequence[FundIn], run_date: date, rank: bool = True) -> List[Score]:
    """Score every fund. The result keeps the order of `funds`."""
    calcs = [build_calc(f, run_date) for f in funds]
    space = Space(calcs)
    pending: List[Tuple[FundIn, Calc, List[Res]]] = []
    out: Dict[str, Score] = {}
    per_group: Dict[str, List[List[Res]]] = defaultdict(list)
    for c in calcs:
        f = c.f
        if c.row == "none":
            out[f.key] = _not_rated(f, c, f"under 12 months of NAV history ({c.h.months} month{'s' if c.h.months != 1 else ''})" if c.h.months else "no month-end NAVs held")
            continue
        results = _metrics_of(c, space)
        pending.append((f, c, results))
        per_group[f.group].append(results)
    gvals = group_values(per_group)
    for f, c, results in pending:
        out[f.key] = finish(f, c, results, gvals)
    scores = [out[f.key] for f in funds]
    if rank:
        rank_all(scores, {f.key: f for f in funds})
    return scores
