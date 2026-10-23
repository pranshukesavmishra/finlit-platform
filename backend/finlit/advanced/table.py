"""Cross-section charts from the in-memory screener Table: the universe filter, the exclusion accounting (each company counted once, first
failing check wins), the statistics, and a small LRU so the same chart is not recomputed for every visitor.

Invariant (tested): universeTotal == n + sum(excluded counts).
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from . import stats as S
from .catalog import BY_ID, CAVEATS, METRICS, REASONS, Metric

NAN = float("nan")
STAGES = ("no_report", "preparing", "lender", "x", "y", "log", "fy_mismatch", "trimmed")
LRU_SIZE = 256
TRIM_Q = 0.01
SIG_IDS = {"pe_sig", "pb_sig", "g_eps_sig", "g_rev_sig", "fwd12"}
METHOD = ("Pearson's r and an ordinary least-squares line on the points shown (on log10 of the values for an axis drawn on a log scale); "
          "two-sided p-value from Student's t with n - 2 degrees of freedom; Spearman's rho on ranks (ties share the average rank); "
          "Theil-Sen slope = median of all pairwise slopes; influence by Cook's distance with a refit without the most influential company; "
          "curvature by a t-test on an added squared term. No value is winsorised or replaced; the default view hides the outer 1% at each end "
          "but the statistics use every included point.")

_cache: "OrderedDict[tuple, dict]" = OrderedDict()


def value_of(t, metric: Metric, i: int) -> float:
    col = t.ax.get(metric.col) if metric.col.startswith("ax_") else t.cols.get(metric.col)
    if col is None:
        return NAN
    return col[i]


def reason_of(t, metric: Metric, i: int) -> str:
    return (t.ax_miss[i] or {}).get(metric.id) or "no_value"


def fy_of(t, x: Metric, y: Metric, i: int) -> Optional[str]:
    if x.id in SIG_IDS or y.id in SIG_IDS:
        return t.ax_sig_fy[i]
    if x.basis in ("fy", "window") or y.basis in ("fy", "window"):
        return t.ax_fy[i]
    return None


def resolve(pair_id: Optional[str], x: Optional[str], y: Optional[str], variant: Optional[str]) -> Tuple[Optional[dict], str, str, Optional[dict]]:
    """-> (pair, x id, y id, variant) or raises KeyError / ValueError."""
    pair = None
    var = None
    if pair_id:
        pair = BY_ID[pair_id]
        if pair["status"] == "unavailable" or "cross" not in pair["modes"]:
            raise ValueError("This chart has no cross-section view.")
        x, y = pair["x"], pair["y"]
        if variant:
            var = next((v for v in pair["variants"] if v["id"] == variant), None)
            if var is None:
                raise ValueError("Unknown variant.")
            x, y = var["x"], var["y"]
    elif variant:
        raise ValueError("A variant needs a pair.")
    if not x or not y or x not in METRICS or y not in METRICS or METRICS[x].basis == "tech" or METRICS[y].basis == "tech":
        raise ValueError("Unknown metric.")
    return pair, x, y, var


def lender_mode(pair: Optional[dict], x: Metric, y: Metric, asked: str) -> Tuple[str, bool]:
    """-> (mode, forced). mode: include | exclude | only."""
    forced = x.lenders == "excluded" or y.lenders == "excluded" or bool(pair and pair.get("lenders") == "excluded")
    if pair and pair.get("lenders") == "only":
        return "only", True
    if forced:
        return "exclude", asked != "exclude"
    if asked == "auto":
        return "include", False
    return asked, False


def _preset_cats(t, pair: Optional[dict], universe: dict) -> Tuple[dict, Optional[dict]]:
    cats = {"sector": list(universe.get("sector") or []), "industry": list(universe.get("industry") or []),
            "index": list(universe.get("index") or []), "cap": list(universe.get("cap") or [])}
    pr = (pair or {}).get("preset")
    if not pr or not universe.get("preset", True) or cats["sector"] or cats["industry"] or cats["index"]:
        return cats, None
    label = pair.get("sector") if pair else None
    if pr.get("kind") == "index" and t.members.get(pr["value"]):
        cats["index"] = [pr["value"]]
        return cats, {"label": label, "matched": {"index": [pr["value"]]}}
    words = [w.lower() for w in pr.get("match") or []]
    secs = [s for s, _ in t.sectors if any(w in s.lower() for w in words)]
    inds = [s for s, _sec, _ in t.industries if any(w in s.lower() for w in words)]
    if secs:
        cats["sector"] = secs
    elif inds:
        cats["industry"] = inds
    else:
        cats["sector"] = ["(no matching sector)"]
    return cats, {"label": label, "matched": {"sector": secs} if secs else {"industry": inds}}


def universe_idx(t, cats: dict, mcap_min: Optional[float], mcap_max: Optional[float]) -> List[int]:
    idx = t.match({}, {k: v for k, v in cats.items() if v})
    if mcap_min is not None or mcap_max is not None:
        col = t.cols["market_cap"]
        idx = [i for i in idx if col[i] == col[i] and (mcap_min is None or col[i] >= mcap_min) and (mcap_max is None or col[i] <= mcap_max)]
    return sorted(idx, key=lambda i: t.symbols[i])


def _tr(scale: str):
    return (math.log10, lambda v: 10 ** v) if scale == "log" else ((lambda v: v), (lambda v: v))


def compute(t, body: dict) -> dict:
    """The highlight-independent part of a cross-section chart (cached)."""
    key = (t.loaded, _norm(body))
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    out = _compute(t, body)
    _cache[key] = out
    if len(_cache) > LRU_SIZE:
        _cache.popitem(last=False)
    return out


def _norm(body: dict) -> str:
    import json
    b = {k: v for k, v in body.items() if k != "highlight"}
    u = dict(b.get("universe") or {})
    for k in ("sector", "industry", "index", "cap"):
        u[k] = sorted(u.get(k) or [])
    b["universe"] = u
    return json.dumps(b, sort_keys=True, default=str)


def _compute(t, body: dict) -> dict:
    pair, xid, yid, var = resolve(body.get("pair"), body.get("x"), body.get("y"), body.get("variant"))
    xm, ym = METRICS[xid], METRICS[yid]
    universe = body.get("universe") or {}
    scale = body.get("scale") or (pair["scale"] if pair and not var else {"x": "lin", "y": "lin"})
    sx, sy = scale.get("x", "lin"), scale.get("y", "lin")
    if (sx == "log" and not xm.log_ok) or (sy == "log" and not ym.log_ok):
        raise ValueError("This axis cannot be drawn on a log scale.")
    mode, forced = lender_mode(pair, xm, ym, universe.get("lenders", "auto"))
    cats, preset = _preset_cats(t, pair, universe)
    idx = universe_idx(t, cats, universe.get("mcapMin"), universe.get("mcapMax"))
    need_ax = xm.col.startswith("ax_") or ym.col.startswith("ax_") or True   # missing-value reasons live with the ax figures
    bank = t.cols["is_bank"]
    status: Dict[int, Tuple[str, str, Optional[str]]] = {}   # i -> (stage, code, axis)
    alive: List[int] = []
    for i in idx:
        if not t.full[i]:
            status[i] = ("no_report", "no_report", None); continue
        if need_ax and not t.ax_ready[i]:
            status[i] = ("preparing", "preparing", None); continue
        is_l = bank[i] == bank[i] and bank[i] == 1.0
        if (mode == "exclude" and is_l) or (mode == "only" and not is_l):
            status[i] = ("lender", "lender" if is_l else "not_lender", None); continue
        xv, yv = value_of(t, xm, i), value_of(t, ym, i)
        if xv != xv:
            status[i] = ("x", reason_of(t, xm, i), "x"); continue
        if yv != yv:
            status[i] = ("y", reason_of(t, ym, i), "y"); continue
        if sx == "log" and xv <= 0:
            status[i] = ("log", "log_le0", "x"); continue
        if sy == "log" and yv <= 0:
            status[i] = ("log", "log_le0", "y"); continue
        alive.append(i)
    fys: Dict[Optional[str], int] = {}
    for i in alive:
        f = fy_of(t, xm, ym, i)
        fys[f] = fys.get(f, 0) + 1
    if universe.get("sameFy") and any(f is not None for f in fys):
        major = max((f for f in fys if f is not None), key=lambda f: (fys[f], f))
        keep = []
        for i in alive:
            if fy_of(t, xm, ym, i) != major:
                status[i] = ("fy_mismatch", "fy_mismatch", None)
            else:
                keep.append(i)
        alive = keep
    fx, bx = _tr(sx)
    fy_, by = _tr(sy)
    trimmed: List[str] = []
    if body.get("trim") and len(alive) >= 3:
        xs = sorted(fx(value_of(t, xm, i)) for i in alive)
        ys = sorted(fy_(value_of(t, ym, i)) for i in alive)
        xl, xh = S.quantile7(xs, TRIM_Q), S.quantile7(xs, 1 - TRIM_Q)
        yl, yh = S.quantile7(ys, TRIM_Q), S.quantile7(ys, 1 - TRIM_Q)
        keep = []
        for i in alive:
            a, b = fx(value_of(t, xm, i)), fy_(value_of(t, ym, i))
            if a < xl or a > xh or b < yl or b > yh:
                status[i] = ("trimmed", "trimmed", None)
                trimmed.append(t.symbols[i])
            else:
                keep.append(i)
        alive = keep
    pts = [(fx(value_of(t, xm, i)), fy_(value_of(t, ym, i)), i) for i in alive]
    st = S.analyse(pts, back_x=bx, back_y=by, name_of=lambda i: t.name[i])
    if st and st.get("influence"):
        j = st["influence"]["max"].pop("label")
        st["influence"]["max"]["s"] = t.symbols[j]
    counts: Dict[Tuple[str, str, Optional[str]], int] = {}
    for v in status.values():
        counts[v] = counts.get(v, 0) + 1
    excluded = [{"stage": s, "code": c, "axis": a, "count": n, "text": REASONS.get(c, c)}
                for (s, c, a), n in sorted(counts.items(), key=lambda kv: (STAGES.index(kv[0][0]), -kv[1], kv[0][1], kv[0][2] or ""))]
    points = [{"s": t.symbols[i], "name": t.name[i], "sector": t.sector[i], "x": value_of(t, xm, i), "y": value_of(t, ym, i), "fy": fy_of(t, xm, ym, i)} for i in alive]
    view = _view([p["x"] for p in points], [p["y"] for p in points])
    fyb: Dict[str, int] = {}
    for p in points:
        if p["fy"]:
            fyb[p["fy"]] = fyb.get(p["fy"], 0) + 1
    lenders_out = sum(1 for v in status.values() if v[0] == "lender")
    notes = list((pair or {}).get("notes") or [])
    if pair and pair.get("mechanical"):
        notes.insert(0, pair["mechanical"])
    if mode == "exclude" and lenders_out:
        notes.append(f"{lenders_out} banks/NBFCs left out: these ratios do not apply to lenders.")
    ins = sum(1 for i in alive if "insur" in (t.industry[i] or "").lower() or "insur" in (t.sector[i] or "").lower())
    if ins and mode == "exclude":
        notes.append(f"{ins} insurers included: their debt, margins and cash flows are not directly comparable with other companies'.")
    if trimmed:
        notes.append("Left out as the most extreme 1%: " + ", ".join(trimmed[:30]) + (" ..." if len(trimmed) > 30 else ""))
    if sx == "log" or sy == "log":
        notes.append("Spearman's rho is the same on linear and log scales (it uses ranks).")
    return {
        "pair": pair["id"] if pair else None, "variant": var["id"] if var else None,
        "x": {"id": xid, "label": xm.label, "unit": xm.unit, "basis": xm.basis, "scale": sx},
        "y": {"id": yid, "label": ym.label, "unit": ym.unit, "basis": ym.basis, "scale": sy},
        "n": len(points), "universeTotal": len(idx), "excluded": excluded, "points": points,
        "stats": S.round_sig(st) if st else None,
        "fyBreakdown": [{"fy": f, "n": c} for f, c in sorted(fyb.items(), key=lambda kv: (-kv[1], kv[0]))],
        "view": view, "lenders": {"mode": {"include": "included", "exclude": "excluded", "only": "only"}[mode], "forced": forced, "count": lenders_out},
        "preset": preset, "notes": notes, "caveats": list(CAVEATS),
        "coverage": {"withReport": t.n_full, "listed": t.n},
        "tableBuiltAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t.loaded)), "method": METHOD,
        "_status": status, "_universe": set(idx),
    }


def _view(xs: List[float], ys: List[float]) -> Optional[dict]:
    if not xs:
        return None
    sx, sy = sorted(xs), sorted(ys)
    vx = [S.quantile7(sx, 0.01), S.quantile7(sx, 0.99)]
    vy = [S.quantile7(sy, 0.01), S.quantile7(sy, 0.99)]
    out = sum(1 for a, b in zip(xs, ys) if a < vx[0] or a > vx[1] or b < vy[0] or b > vy[1])
    return {"x": vx, "y": vy, "outside": out}


def highlights(t, core: dict, symbols: List[str], cats_universe: Optional[set] = None) -> List[dict]:
    xm, ym = METRICS[core["x"]["id"]], METRICS[core["y"]["id"]]
    status, uni = core["_status"], core["_universe"]
    out = []
    for s in symbols:
        i = t.pos.get(s)
        if i is None:
            out.append({"s": s, "name": None, "x": None, "y": None, "fy": None, "status": "unknown", "reason": "unknown", "reasonText": REASONS["unknown"]})
            continue
        xv, yv = value_of(t, xm, i), value_of(t, ym, i)
        rec = {"s": s, "name": t.name[i], "x": None if xv != xv else xv, "y": None if yv != yv else yv, "fy": fy_of(t, xm, ym, i)}
        if not t.full[i]:
            rec.update(status="no_report", reason="no_report", reasonText=REASONS["no_report"])
        elif i not in uni:
            # outside the filters: drawn hollow for reference, its own missing value (if any) is still explained
            why = None if rec["x"] is not None and rec["y"] is not None else (reason_of(t, xm, i) if rec["x"] is None else reason_of(t, ym, i))
            rec.update(status="outside", reason="outside" if why is None else why, reasonText=REASONS["outside"] if why is None else REASONS.get(why, why))
        elif i in status:
            _, code, _ = status[i]
            rec.update(status="excluded", reason=code, reasonText=REASONS.get(code, code))
        else:
            rec.update(status="included", reason=None, reasonText=None)
        out.append(rec)
    return out


def public(core: dict, hl: List[dict]) -> dict:
    return {**{k: v for k, v in core.items() if not k.startswith("_")}, "highlights": hl}


def reset() -> None:
    _cache.clear()
