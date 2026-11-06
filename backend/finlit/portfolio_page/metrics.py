"""FinLit "My portfolio" page: calculations and reading rules (ported unchanged from the design handover pack, reference/portfolio_metrics.py).

Every formula, threshold and reading is the pack's. The one addition is a size code "U" for a company whose market-value rank is not known (it is counted in the
list, in no size column). Information only, not investment advice.

This module turns a list of shares into everything the page shows:
  * where the list sits (sector and size mix, both amount modes)
  * what moves together (pair correlations, effective stocks, groups, same-sector vs cross-sector pairs)
  * share of risk, NIFTY 50 measures, diversification score
  * readings: plain-language sentences produced by the inference rules in RULES (descriptive only)

Inputs are plain pandas objects so it can sit behind any API:
  weekly_close : DataFrame, index = week-ending dates (Friday), columns = NSE symbols, adjusted closes
  nifty_close  : Series, same index, NIFTY 50 closes
  meta         : {symbol: {"name", "sector", "size" ("L"|"M"|"S"; "U" = not known), "mcap_cr", "prism": {...} (kept for the caller, not used here)}}

Requires numpy, pandas and scipy. Python 3.9+.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, leaves_list, linkage
from scipy.spatial.distance import squareform

# ---------------------------------------------------------------------------------------------------------------
# Settings (keep in one place so the page and the tests read the same numbers)
# ---------------------------------------------------------------------------------------------------------------
WEEKS = 104                 # weekly returns used (2 years). Fewer than MIN_WEEKS -> share left out of co-movement.
MIN_WEEKS = 52
FULL_EFFECTIVE_STOCKS = 15  # co-movement part scores 100 at 15 effective stocks
FULL_EFFECTIVE_SECTORS = 8  # sector-spread part scores 100 at 8 effective sectors
W_COMOVE, W_SECTOR = 0.6, 0.4
GROUP_MIN_CORR = 0.5        # a group = average-linkage cluster whose members average >= 0.5 with each other
SHORT_LIST_MAX = 15         # up to 15 shares: short layout; more: long layout
BANDS = [(80, "Widely spread"), (60, "Fairly spread"), (40, "Somewhat concentrated"), (0, "Concentrated")]
PRISM_BANDS = [(70, "green"), (50, "orange"), (0, "red")]
BANNED_WORDS = re.compile(r"\b(buy|sell|hold|add|reduce|trim|exit|avoid|should|must|recommend\w*|overweight|"
                          r"underweight|target|accumulate|switch|book profits?)\b", re.I)


def band(score: float) -> str:
    return next(name for lo, name in BANDS if score >= lo)


def prism_band(v: float) -> str:
    return next(name for lo, name in PRISM_BANDS if round(v) >= lo)


# ---------------------------------------------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------------------------------------------
def weekly_returns(weekly_close: pd.DataFrame, nifty_close: pd.Series, weeks: int = WEEKS):
    """Last `weeks` weekly returns. Shares with fewer than MIN_WEEKS returns are reported in `short_history`."""
    r = weekly_close.pct_change().iloc[1:].tail(weeks)
    rn = nifty_close.pct_change().reindex(r.index)
    counts = r.notna().sum()
    short = sorted(counts[counts < MIN_WEEKS].index)
    r = r.drop(columns=short)
    return r, rn, short


def effective_stocks(corr: np.ndarray) -> float:
    """Participation ratio of the correlation matrix: (sum of eigenvalues)^2 / sum of squared eigenvalues.
    n unrelated shares -> n; n shares that move as one -> 1."""
    lam = np.linalg.eigvalsh(corr)
    return float(lam.sum() ** 2 / (lam ** 2).sum())


def effective_sectors(sectors: List[str]) -> float:
    """1 / sum of squared sector shares, counting each share once (independent of the amount mode)."""
    s = pd.Series(sectors).value_counts(normalize=True)
    return float(1 / (s ** 2).sum())


def diversification_score(eff_stocks: float, eff_sectors: float) -> dict:
    co = min(100.0, max(0.0, math.log(max(eff_stocks, 1)) / math.log(FULL_EFFECTIVE_STOCKS) * 100))
    sp = min(100.0, max(0.0, math.log(max(eff_sectors, 1)) / math.log(FULL_EFFECTIVE_SECTORS) * 100))
    score = W_COMOVE * co + W_SECTOR * sp
    return {"score": round(score), "band": band(round(score)), "comovement": round(co), "sector_spread": round(sp),
            "effective_stocks": round(eff_stocks, 1), "effective_sectors": round(eff_sectors, 1)}


def groups_and_order(C: pd.DataFrame):
    """Average-linkage clustering on distance 1 - correlation.
    Groups = clusters of 2+ shares that average GROUP_MIN_CORR or more with each other.
    Grid order = groups first (largest first, then tighter first), each in dendrogram order, then the shares
    in no group from most to least connected with the rest. Letters follow that order: A = the first block."""
    syms = list(C.columns)
    if len(syms) < 3:
        return syms, []
    D = 1 - C.values
    np.fill_diagonal(D, 0)
    Z = linkage(squareform(np.clip(D, 0, None), checks=False), "average")
    leaf = {syms[i]: k for k, i in enumerate(leaves_list(Z))}
    labels = fcluster(Z, t=1 - GROUP_MIN_CORR, criterion="distance")
    groups = []
    for lab in sorted(set(labels)):
        g = sorted([s for s, l in zip(syms, labels) if l == lab], key=lambda s: leaf[s])
        if len(g) < 2:
            continue
        m = C.loc[g, g].values
        groups.append({"members": g, "avg_corr": round(float((m.sum() - len(g)) / (len(g) * (len(g) - 1))), 2)})
    groups.sort(key=lambda g: (-len(g["members"]), -g["avg_corr"]))
    in_group = {s for g in groups for s in g["members"]}
    rest = sorted((s for s in syms if s not in in_group), key=lambda s: -(C.loc[s].sum() - 1))
    order = [s for g in groups for s in g["members"]] + rest
    for i, g in enumerate(groups):
        g["letter"] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i] if i < 26 else str(i + 1)
    return order, groups


def pair_segments(C: pd.DataFrame, sector: Dict[str, str]) -> dict:
    """Split every pair into same-sector and cross-sector, with the numbers the page shows for each."""
    syms = list(C.columns)
    seg = {"same": [], "cross": []}
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            same = sector.get(a) and sector.get(a) == sector.get(b)
            seg["same" if same else "cross"].append((a, b, float(C.iloc[i, j])))
    edges = np.round(np.arange(-0.2, 1.0001, 0.1), 2)
    out = {}
    for k, pairs in seg.items():
        v = np.array([p[2] for p in pairs]) if pairs else np.array([])
        hist = np.histogram(np.clip(v, -0.2, 0.9999), bins=edges)[0].tolist() if len(v) else [0] * (len(edges) - 1)
        top = sorted(pairs, key=lambda p: -p[2])[:3]
        out[k] = {"pairs": len(pairs), "avg": round(float(v.mean()), 2) if len(v) else None,
                  "median": round(float(np.median(v)), 2) if len(v) else None,
                  "at_least_05": int((v >= 0.5).sum()), "share_at_least_05": round(float((v >= 0.5).mean() * 100), 1) if len(v) else None,
                  "top": [{"a": a, "b": b, "corr": round(c, 2)} for a, b, c in top], "hist": hist}
    out["bins"] = [[float(edges[i]), float(edges[i + 1])] for i in range(len(edges) - 1)]
    return out


def sector_within(C: pd.DataFrame, sector: Dict[str, str]) -> Dict[str, dict]:
    out = {}
    for sec in sorted(set(sector[s] for s in C.columns)):
        m = [s for s in C.columns if sector[s] == sec]
        if len(m) >= 2:
            sub = C.loc[m, m].values
            out[sec] = {"n": len(m), "avg": round(float((sub.sum() - len(m)) / (len(m) * (len(m) - 1))), 2)}
    return out


def risk_shares(r: pd.DataFrame, w: np.ndarray) -> np.ndarray:
    """Each share's part of the list's ups and downs: w_i (Sigma w)_i / w' Sigma w. Sums to 1."""
    cov = r.cov().values * 52
    m = cov @ w
    return w * m / float(w @ m)


def market_measures(r: pd.DataFrame, rn: pd.Series, w: np.ndarray) -> dict:
    port = (r * w).sum(axis=1)
    worst = rn.nsmallest(10).index
    cum = (1 + port).cumprod()
    ncum = (1 + rn).cumprod()
    return {"beta": round(float(np.cov(port, rn)[0, 1] / np.var(rn, ddof=1)), 2),
            "worst10_list": round(float(port.loc[worst].mean() * 100), 1), "worst10_nifty": round(float(rn.loc[worst].mean() * 100), 1),
            "vol": round(float(port.std() * math.sqrt(52) * 100), 1), "vol_nifty": round(float(rn.std() * math.sqrt(52) * 100), 1),
            "max_fall": round(float((cum / cum.cummax() - 1).min() * 100), 1), "max_fall_nifty": round(float((ncum / ncum.cummax() - 1).min() * 100), 1)}


# ---------------------------------------------------------------------------------------------------------------
# Inference rules. Each rule reads the computed figures and returns readings:
#   {"rule", "section", "priority", "text", "mode"}   mode = "eq" | "mc" | "both"
# Sections: where | together | risk | market | data. The summary box shows the 5 highest priorities for the
# current mode, at most 1 per rule. Every text passes the wording check (no advice words).
# ---------------------------------------------------------------------------------------------------------------
def pct(v: float) -> str:
    return "under 0.1%" if 0 < v < 0.1 else f"{v:.1f}%"


def two(v: float) -> str:
    return f"{v:.2f}"


def join_names(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def rules(f: dict) -> List[dict]:
    out: List[dict] = []

    def say(rule, section, priority, text, mode="both"):
        out.append({"rule": rule, "section": section, "priority": priority, "text": text, "mode": mode})

    n = f["n"]
    # --- Data quality ---------------------------------------------------------------------------------------
    for s in f["short_history"]:
        say("D1", "data", 95, f"{s} has less than a year of weekly prices, so it is left out of the co-movement figures.")
    for s in f["unclassified"]:
        say("D2", "data", 90, f"{s} has no NSE sector yet, so it counts as a sector of its own.")
    for s in f.get("no_mcap", []):
        say("D4", "data", 88, f"{s} has no company value yet, so it is left out when amounts are sized by company value.", "mc")
    if f["n_corr"] < 3:
        say("D3", "data", 99, "How shares move together shows once the list has 3 shares with a year of prices.")
        return out
    # --- Where the list sits --------------------------------------------------------------------------------
    for mode in ("eq", "mc"):
        secw = sorted(f["sector_weight"][mode].items(), key=lambda t: -t[1])
        top, w = secw[0]
        tie = [k for k, v in secw if abs(v - w) < 0.05]
        if len(tie) > 1:                       # never name one "largest" sector in a tie
            pr = 84 if w >= 40 else 70 if w >= 25 else 0
            if pr:
                say("C1", "where", pr, f"{join_names(tie)} are the largest sectors at {pct(w)} each.", mode)
        elif w >= 50:
            say("C1", "where", 88, f"{top} is half the list or more ({pct(w)}).", mode)
        elif w >= 40:
            say("C1", "where", 84, f"{top} is {pct(w)} of the list, close to half.", mode)
        elif w >= 25:
            say("C1", "where", 70, f"{top} is the largest sector at {pct(w)} of the list.", mode)
        if len(secw) > 1 and secw[0][1] + secw[1][1] >= 50 and w < 40:
            say("C5", "where", 60, f"{top} and {secw[1][0]} together are {pct(secw[0][1] + secw[1][1])} of the list.", mode)
        if mode == "mc":
            big = [(s, v) for s, v in sorted(f["share_weight"]["mc"].items(), key=lambda t: -t[1]) if v >= 10]
            for s, v in big[:2]:
                say("C2", "where", 80, f"{s} alone is {pct(v)} of the list.", mode)
            lc = f["size_weight"]["mc"].get("L", 0)
            if lc >= 90:
                say("C4", "where", 50, f"Large caps are {pct(lc)} of the list when sized by company value.", mode)
    if f["sector_count"] <= 2:
        say("C3", "where", 85, f"All {n} shares are in {f['sector_count']} sector{'s' if f['sector_count'] > 1 else ''}.")
    if n >= 8:
        missing = [nm for k, nm in (("M", "mid caps"), ("S", "small caps"), ("L", "large caps")) if f["size_count"].get(k, 0) == 0]
        if missing:
            say("C4", "where", 30, f"There are no {join_names(missing)} in the list.", "eq")
    # --- What moves together --------------------------------------------------------------------------------
    say("M1", "together", 62, f"{f['n_corr']} shares move like {f['effective_stocks']:.1f} independent ones.")
    seg = f["segments"]
    if seg["same"]["pairs"] >= 3 and seg["cross"]["pairs"] >= 3:
        s, c = seg["same"]["avg"], seg["cross"]["avg"]
        if s - c >= 0.15:
            say("M2", "together", 71, f"Shares in the same sector move together much more than shares in different sectors ({two(s)} against {two(c)} on average).")
        elif s - c < 0.08:
            say("M2", "together", 66, f"Shares move about as much with other sectors as with their own ({two(s)} against {two(c)}), so sector labels say little about spread here.")
        else:
            say("M2", "together", 36, f"Same-sector pairs move a little more alike than cross-sector pairs ({two(s)} against {two(c)}).")
    for sec, v in sorted(f["within"].items(), key=lambda t: -t[1]["avg"]):
        if v["n"] >= 3 and v["avg"] >= 0.6:
            say("M3", "together", 76, f"The {v['n']} {sec} shares move almost as one ({two(v['avg'])} on average).")
        elif v["n"] >= 3 and v["avg"] < 0.35:
            say("M4", "together", 40, f"The {v['n']} {sec} shares share a sector but move fairly independently ({two(v['avg'])}).")
    for g in f["groups"]:
        secs = sorted(set(f["sector"][s] for s in g["members"]))
        if len(secs) > 1:
            say("M5", "together", 72, f"Group {g['letter']}: {join_names(g['members'])} are in different sectors but move together ({two(g['avg_corr'])}).")
    if not f["groups"]:
        say("M8", "together", 50, "No set of shares moves closely together.")
    twins = f["near_duplicates"]
    if twins:
        a = twins[0]
        extra = f" {len(twins)} pairs are at 0.75 or more." if len(twins) > 1 else ""
        say("M6", "together", 55, f"{a['a']} and {a['b']} moved almost identically ({two(a['corr'])}).{extra}")
    lone = [s for s, v in sorted(f["avg_with_rest"].items(), key=lambda t: t[1]) if v < 0.15]
    if lone:
        say("M7", "together", 45, f"{join_names(lone[:3])} mostly move{'s' if len(lone) == 1 else ''} on {'its' if len(lone) == 1 else 'their'} own (under 0.15 with the rest).")
    # --- Share of risk ---------------------------------------------------------------------------------------
    for mode in ("eq", "mc"):
        rs, am = f["share_risk"][mode], f["share_weight"][mode]
        heavy = [(s, rs[s], am[s]) for s in sorted(rs, key=lambda s: -rs[s]) if rs[s] >= 3 and rs[s] >= 1.5 * am[s]]
        for s, r_, a_ in heavy[:2]:
            say("K1", "risk", 72, f"{s} is {pct(a_)} of the amount but {pct(r_)} of the risk.", mode)
        sr, sa = f["sector_risk"][mode], f["sector_weight"][mode]
        members = pd.Series(list(f["sector"].values())).value_counts()
        gap = sorted(((k, sr[k] - sa[k]) for k in sr if members.get(k, 0) >= 2), key=lambda t: -t[1])  # one-share sectors repeat K1
        if gap and gap[0][1] >= 4:
            k = gap[0][0]
            say("K2", "risk", 68, f"{k} is {pct(sa[k])} of the amount but {pct(sr[k])} of the risk.", mode)
        top3 = sorted(rs.items(), key=lambda t: -t[1])[:3]
        t3 = sum(v for _, v in top3)
        if n >= 6 and t3 >= 40:
            say("K3", "risk", 74, f"Three shares carry {pct(t3)} of the risk: {join_names([s for s, _ in top3])}.", mode)
    # --- Against the NIFTY 50 --------------------------------------------------------------------------------
    for mode in ("eq", "mc"):
        m = f["market"][mode]
        if m["beta"] >= 1.1:
            say("B1", "market", 50, f"The list has moved more than the NIFTY 50 (beta {m['beta']:.2f}).", mode)
        elif m["beta"] <= 0.9:
            say("B1", "market", 50, f"The list has moved less than the NIFTY 50 (beta {m['beta']:.2f}).", mode)
        if m["worst10_list"] > m["worst10_nifty"] + 0.4:
            say("B2", "market", 45, f"In the NIFTY 50's 10 worst weeks the list fell {abs(m['worst10_list']):.1f}% on average, against {abs(m['worst10_nifty']):.1f}% for the index.", mode)
        elif m["worst10_list"] < m["worst10_nifty"] - 0.4:
            say("B2", "market", 45, f"In the NIFTY 50's 10 worst weeks the list fell more than the index: {abs(m['worst10_list']):.1f}% against {abs(m['worst10_nifty']):.1f}% on average.", mode)
    for x in out:
        assert not BANNED_WORDS.search(x["text"]), x["text"]
    return out


def summary_readings(readings: List[dict], mode: str, k: int = 5, per_rule: int = 1) -> List[dict]:
    picked, seen = [], {}
    for x in sorted(readings, key=lambda x: -x["priority"]):
        if x["mode"] not in ("both", mode) or x["section"] == "market":
            continue
        if seen.get(x["rule"], 0) >= per_rule:
            continue
        seen[x["rule"]] = seen.get(x["rule"], 0) + 1
        picked.append(x)
        if len(picked) == k:
            break
    return picked


# ---------------------------------------------------------------------------------------------------------------
# Whole page
# ---------------------------------------------------------------------------------------------------------------
def build_page(weekly_close: pd.DataFrame, nifty_close: pd.Series, meta: Dict[str, dict]) -> dict:
    syms = list(meta)
    r, rn, short = weekly_returns(weekly_close[syms], nifty_close)
    sector = {s: (meta[s].get("sector") or f"{s} (not classified)") for s in syms}
    unclassified = [s for s in syms if not meta[s].get("sector")]
    n = len(syms)
    cs = list(r.columns)
    C = r.corr()
    eff = effective_stocks(C.values) if len(cs) >= 3 else float(len(cs))
    effsec = effective_sectors([sector[s] for s in syms])
    order, groups = groups_and_order(C)
    seg = pair_segments(C, sector)
    within = sector_within(C, sector)
    avg_rest = {s: round(float((C.loc[s].sum() - 1) / (len(cs) - 1)), 2) for s in cs} if len(cs) > 1 else {}
    twins = sorted(({"a": cs[i], "b": cs[j], "corr": round(float(C.iloc[i, j]), 2)}
                    for i in range(len(cs)) for j in range(i + 1, len(cs)) if C.iloc[i, j] >= 0.75), key=lambda p: -p["corr"])
    cap = lambda s: float(meta[s].get("mcap_cr") or 0)
    no_mcap = [s for s in syms if cap(s) <= 0]
    mc = np.array([cap(s) for s in cs])
    weights = {"eq": np.ones(len(cs)) / len(cs), "mc": mc / mc.sum() if mc.sum() > 0 else np.ones(len(cs)) / len(cs)}
    w_all = {"eq": {s: 100 / n for s in syms}}
    mc_all = np.array([cap(s) for s in syms])
    w_all["mc"] = {s: float(v) for s, v in zip(syms, mc_all / mc_all.sum() * 100)} if mc_all.sum() > 0 else dict(w_all["eq"])
    share_risk, market, sector_risk = {}, {}, {}
    for k, w in weights.items():
        rs = risk_shares(r, w) * 100
        share_risk[k] = {s: round(float(v), 2) for s, v in zip(cs, rs)}
        market[k] = market_measures(r, rn, w)
        sector_risk[k] = {}
        for s, v in share_risk[k].items():
            sector_risk[k][sector[s]] = round(sector_risk[k].get(sector[s], 0) + v, 2)
    sector_weight = {k: {} for k in w_all}
    size_weight = {k: {} for k in w_all}
    for k in w_all:
        for s in syms:
            sector_weight[k][sector[s]] = round(sector_weight[k].get(sector[s], 0) + w_all[k][s], 2)
            size_weight[k][meta[s]["size"]] = round(size_weight[k].get(meta[s]["size"], 0) + w_all[k][s], 2)
    size_count = pd.Series([meta[s]["size"] for s in syms]).value_counts().to_dict()
    score = diversification_score(eff, effsec)
    figures = {"n": n, "n_corr": len(cs), "short_history": short, "unclassified": unclassified, "no_mcap": no_mcap, "sector": sector,
               "sector_count": len(set(sector.values())), "effective_stocks": eff, "segments": seg, "within": within,
               "groups": groups, "near_duplicates": twins, "avg_with_rest": avg_rest, "share_risk": share_risk,
               "share_weight": {k: {s: round(v, 2) for s, v in w_all[k].items()} for k in w_all}, "sector_risk": sector_risk,
               "sector_weight": sector_weight, "size_weight": size_weight, "size_count": size_count, "market": market}
    readings = rules(figures)
    layout = "short" if n <= SHORT_LIST_MAX else "long"
    return {"layout": layout, "weeks": len(r), "from": str(r.index[0].date()), "to": str(r.index[-1].date()),
            "score": score, "order": order, "corr": C.loc[order, order].round(2).values.tolist(), "groups": groups,
            "segments": seg, "within": within, "avg_with_rest": avg_rest, "near_duplicates": twins,
            "sector_weight": sector_weight, "size_weight": size_weight, "size_count": size_count,
            "share_weight": figures["share_weight"], "share_risk": share_risk, "sector_risk": sector_risk, "market": market,
            "readings": readings, "summary": {m: summary_readings(readings, m) for m in ("eq", "mc")},
            "together_open_by_default": layout == "short", "short_history": short}
