"""Diversification card: the maths (addendum "Mode B without amounts"). No I/O: prices, sectors and Prism parts come in as plain data.

Input is share names only. Every weighted figure uses equal weights, with a market-cap-weighted view alongside, both labelled. The score is always
worked out on weekly returns over the latest 156 complete weeks, whatever horizon is shown.

It describes how a list of stocks has behaved; it gives no view on any stock. Information only, not investment advice.

numpy, pandas, scipy and scikit-learn are imported here, so the website process imports this module only when a request needs it (finlit/diversification/api.py).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

LOOKBACK_WEEKS = 156       # 3 years of complete weeks
MIN_WEEKS = 52             # minimum history for co-movement figures
MIN_STOCKS = 3             # minimum eligible stocks for co-movement figures and the score
MAX_STOCKS = 100
MATRIX_MAX = 30           # the pair-correlation grid is sent for lists of up to this many stocks
CLUSTER_CUT = 0.5          # distance 1 - rho; a group's members average a correlation of 0.5 or more
WORST_WEEKS = 10           # stress: the benchmark's worst weeks
SCORE_VERSION = "1"
SCORE_CAP_STOCKS = 15      # effective independent stocks at which co-movement scores 100
SCORE_CAP_SECTORS = 8      # effective sectors at which sector spread scores 100
SCORE_WEIGHTS = (0.6, 0.4)  # co-movement, sector spread
BANDS = [(80, "Widely spread"), (60, "Fairly spread"), (40, "Somewhat concentrated"), (0, "Concentrated")]
HORIZONS = ("weekly", "monthly", "yearly")
MONTHLY_MONTHS = 60        # monthly horizon: latest 60 complete months
MONTHLY_MIN = 36           # months of history a stock needs on the monthly horizon
YEARLY_MIN_MONTHS = 60     # months of prices a stock needs on the yearly horizon
RECENT_WEEKS = 52          # last year against the 3-year window
CHANGE_FLAG = 0.30         # a pair moved by this much or more ...
CHANGE_FLOOR = 0.50        # ... and the higher of its two correlations is at least this
TILT_HIGH, TILT_LOW = 65, 35
UNCLASSIFIED = "Not classified"
SIZE_BANDS = (("Large", 100), ("Mid", 250), ("Small", None))   # market-cap rank 1-100, 101-250, 251 and below
TILT_PARTS = [  # (field, name, wording when high, wording when low)
    ("prism_fundamental", "Growth & Profitability", "faster-growing, more profitable companies", "slower-growing, less profitable companies"),
    ("prism_valuation", "Valuation", "cheaper stocks", "more expensive stocks"),
    ("prism_quality", "Quality", "higher-quality companies", "lower-quality companies"),
    ("prism_risk", "Risk", "lower-risk companies", "higher-risk companies"),
    ("prism_st_score", "Short-term technical view", "stocks in short-term uptrends", "stocks in short-term downtrends"),
    ("prism_lt_score", "Long-term technical view", "stocks in long-term uptrends", "stocks in long-term downtrends"),
]
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class NoBenchmark(Exception):
    """The index has no usable prices, so beta, stress and the aligned sample cannot be worked out."""


# ------------------------------------------------------------------ small helpers
def round_half_up(x: float) -> int:
    return int(np.floor(x + 0.5))


def iso_week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def iso_week(dates: Iterable[str]) -> List[str]:
    return [iso_week_key(datetime.strptime(str(d)[:10], "%Y-%m-%d").date()) for d in dates]


def week_monday(week: str) -> date:
    y, w = week.split("-W")
    return date.fromisocalendar(int(y), int(w), 1)


def month_label(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.year}"


def window_label(from_d: date, to_d: date) -> str:
    return f"{month_label(from_d)} – {month_label(to_d)}"


def weekly_closes(dates: Sequence[str], closes: Sequence[float]) -> "pd.Series":
    """One close per ISO week (the last one in the week), keyed 'YYYY-Www'."""
    s = pd.Series(np.asarray(closes, dtype="float64"), index=iso_week(dates))
    return s[~s.index.duplicated(keep="last")]


def _pct(frame: "pd.DataFrame") -> "pd.DataFrame":
    try:
        return frame.pct_change(fill_method=None)
    except TypeError:       # newer pandas has no fill_method
        return frame.pct_change()


def effective_stocks(corr: np.ndarray, t_obs: float) -> float:
    """N^2 / (N + sum over i != j of max(rho^2 - 1/T, 0)). 1 = all move as one, N = no co-movement."""
    n = corr.shape[0]
    off = corr[~np.eye(n, dtype=bool)]
    return float(n ** 2 / (n + np.maximum(off ** 2 - 1.0 / t_obs, 0).sum()))


def effective_sectors(labels: Sequence[str]) -> float:
    """1 / sum of squared sector shares, counted by stocks (never by money)."""
    counts: Dict[str, int] = {}
    for x in labels:
        counts[x] = counts.get(x, 0) + 1
    n = float(len(labels))
    return float(1.0 / sum((c / n) ** 2 for c in counts.values()))


def band_for(value: int) -> str:
    return next(label for edge, label in BANDS if value >= edge)


def diversification_score(n_eff: float, s_eff: float) -> Dict[str, Any]:
    """0-100 score: 0.6 x co-movement + 0.4 x sector spread, each on a log scale with a cap. Worked out from the unrounded parts; the band comes from the ROUNDED score."""
    co = 100 * min(1.0, float(np.log(max(n_eff, 1.0)) / np.log(SCORE_CAP_STOCKS)))
    sec = 100 * min(1.0, float(np.log(max(s_eff, 1.0)) / np.log(SCORE_CAP_SECTORS)))
    raw = SCORE_WEIGHTS[0] * co + SCORE_WEIGHTS[1] * sec
    value = round_half_up(raw)
    return {"value": value, "unrounded": round(float(raw), 1), "band": band_for(value), "coMovement": round_half_up(co),
            "sectorSpread": round_half_up(sec), "effectiveSectors": round(float(s_eff), 2)}


def risk_share(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """RC_i = w_i (Sigma w)_i / (w' Sigma w); shares sum to 1."""
    return w * (cov @ w) / (w @ cov @ w)


def max_drawdown(r: "pd.Series") -> float:
    level = (1 + r).cumprod()
    return float((level / level.cummax() - 1).min())


def pair_flag(recent: float, long_run: float) -> bool:
    """A pair is flagged when its correlation moved by CHANGE_FLAG or more and the higher of the two values is CHANGE_FLOOR or more."""
    return abs(recent - long_run) >= CHANGE_FLAG - 1e-9 and max(recent, long_run) >= CHANGE_FLOOR


def size_band(rank: Optional[int]) -> Optional[str]:
    """Large: market-cap rank 1-100, Mid: 101-250, Small: 251 and below. None when the company's rank is not known."""
    if rank is None or rank < 1:
        return None
    for name, top in SIZE_BANDS:
        if top is None or rank <= top:
            return name
    return None


def _clusters(corr: np.ndarray, names: Sequence[str]) -> List[Dict[str, Any]]:
    """Average-linkage hierarchical clustering on distance 1 - rho, cut at CLUSTER_CUT. Only groups of two or more."""
    dist = 1 - corr
    np.fill_diagonal(dist, 0)
    labels = fcluster(linkage(squareform(dist, checks=False), method="average"), t=CLUSTER_CUT, criterion="distance")
    out = []
    for lab in sorted(set(labels)):
        idx = np.where(labels == lab)[0]
        if len(idx) > 1:
            sub = corr[np.ix_(idx, idx)][np.triu_indices(len(idx), 1)]
            out.append({"symbols": [names[i] for i in idx], "avgCorrelation": round(float(sub.mean()), 2)})
    return sorted(out, key=lambda c: (-len(c["symbols"]), -c["avgCorrelation"]))


def _overlap(corr: np.ndarray, names: Sequence[str]) -> List[Dict[str, Any]]:
    n = len(names)
    return sorted(({"symbol": s, "avgCorrelation": round(float((corr[i].sum() - 1) / (n - 1)), 2)} for i, s in enumerate(names)), key=lambda d: -d["avgCorrelation"])


# ------------------------------------------------------------------ spread by count (needs no prices)
def spread_by_count(symbols: Sequence[str], sectors: Dict[str, str], groups: Dict[str, str], sizes: Dict[str, Optional[str]],
                    names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Stocks per macro sector, per size band and per business group. Works for any list, with or without prices. A stock with no sector label is
    counted in the bucket 'Not classified' (named, never dropped)."""
    order: Dict[str, int] = {}
    counts: Dict[str, int] = {}
    for s in symbols:
        k = sectors.get(s) or UNCLASSIFIED
        counts[k] = counts.get(k, 0) + 1
        order.setdefault(k, len(order))
    sec = [{"name": k, "count": c} for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], order[kv[0]]))]
    size = {"Large": 0, "Mid": 0, "Small": 0}
    unknown_size = []
    for s in symbols:
        b = sizes.get(s)
        if b in size:
            size[b] += 1
        else:
            unknown_size.append(s)
    grp = [{"name": g, "symbols": [s for s in symbols if groups.get(s) == g]} for g in sorted({groups[s] for s in symbols if s in groups})]
    top = sec[0] if sec else None
    return {"sectors": sec, "size": size, "sizeUnknown": unknown_size, "groups": grp,
            "unclassified": [s for s in symbols if not sectors.get(s)],
            "largestSector": {"name": top["name"], "count": top["count"], "share": round(top["count"] / len(symbols), 3)} if top else None,
            "stocks": [{"symbol": s, "name": (names or {}).get(s, s), "sector": sectors.get(s) or UNCLASSIFIED, "size": sizes.get(s), "group": groups.get(s)} for s in symbols]}


# ------------------------------------------------------------------ weekly: the score and every co-movement figure
def weekly_frame(prices: Dict[str, Any], symbols: Sequence[str], current_week: str) -> "pd.DataFrame":
    """Weekly returns (latest LOOKBACK_WEEKS complete weeks) of every listed stock that has prices, plus '__NIFTY'. The unfinished week never enters."""
    closes = {s: weekly_closes(prices[s]["t"], prices[s]["c"]) for s in symbols if prices.get(s) and prices[s].get("t")}
    nif = (prices.get("__NIFTY") or {}).get("rows") or []
    if not nif:
        raise NoBenchmark("no index prices")
    closes["__NIFTY"] = weekly_closes([r["d"] for r in nif], [r["c"] for r in nif])
    c = pd.DataFrame(closes).sort_index()
    c = c[c.index < current_week]
    return _pct(c).iloc[1:].tail(LOOKBACK_WEEKS)


def _basket(x: "pd.DataFrame", m: "pd.Series", cov: np.ndarray, w: np.ndarray, sectors: List[str], worst) -> Dict[str, Any]:
    r = pd.Series(x.values @ w, index=x.index)
    rs = risk_share(w, cov)
    by_sector: Dict[str, float] = {}
    amount: Dict[str, float] = {}
    for lab, v, wi in zip(sectors, rs, w):
        by_sector[lab] = by_sector.get(lab, 0.0) + float(v)
        amount[lab] = amount.get(lab, 0.0) + float(wi)
    names = list(x.columns)
    return {
        "volPct": round(float(np.sqrt(w @ cov @ w) * np.sqrt(52) * 100), 1),
        "maxDrawdownPct": round(max_drawdown(r) * 100, 1),
        "beta": round(float(r.cov(m) / m.var()), 2),
        "stressAvgPct": round(float(r[worst].mean() * 100), 2),
        "riskShare": {
            "stocks": sorted(({"symbol": s, "pct": round(float(v * 100), 1), "weightPct": round(float(wi * 100), 1)} for s, v, wi in zip(names, rs, w)), key=lambda d: -d["pct"]),
            "sectors": [{"name": k, "pct": round(v * 100, 1), "amountPct": round(amount[k] * 100, 1)} for k, v in sorted(by_sector.items(), key=lambda kv: -kv[1])],
        },
    }


def weekly_view(prices: Dict[str, Any], symbols: Sequence[str], sectors: Dict[str, str], mcap: Dict[str, Optional[float]], groups: Dict[str, str],
                sizes: Dict[str, Optional[str]], current_week: str, names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Everything on the card that comes from weekly returns. prices: {symbol: {"t", "c"}, "__NIFTY": {"rows": [{"d", "c"}]}}; current_week: the ISO week
    that is not finished yet ('2026-W45'), dropped from every series."""
    symbols = list(dict.fromkeys(symbols))
    r_all = weekly_frame(prices, symbols, current_week)
    avail = r_all.drop(columns="__NIFTY").notna().sum() if len(r_all.columns) > 1 else pd.Series(dtype=int)
    eligible = [s for s in symbols if s in avail.index and avail[s] >= MIN_WEEKS]
    excluded = [{"symbol": s, "reason": "history" if prices.get(s) and prices[s].get("t") else "noPrices", "weeks": int(avail.get(s, 0))} for s in symbols if s not in eligible]
    out: Dict[str, Any] = {"horizon": "weekly", "included": len(eligible), "excluded": excluded, "scoreVersion": SCORE_VERSION,
                           "spread": spread_by_count(symbols, sectors, groups, sizes, names)}
    if len(eligible) < MIN_STOCKS:
        return out                                      # Spread by count only; no score
    r = r_all[eligible + ["__NIFTY"]].dropna()          # one common, aligned sample
    if len(r) < MIN_WEEKS:
        out["included"] = 0
        out["excluded"] = excluded + [{"symbol": s, "reason": "overlap", "weeks": int(len(r))} for s in eligible]
        return out
    x, m = r[eligible], r["__NIFTY"]
    n, t_obs = len(eligible), len(r)
    corr = x.corr().values
    upper = corr[np.triu_indices(n, 1)]
    sec_of = [sectors.get(s) or UNCLASSIFIED for s in eligible]

    cov = LedoitWolf().fit(x.values).covariance_
    worst = m.nsmallest(WORST_WEEKS).index
    w_eq = np.repeat(1.0 / n, n)
    eq = _basket(x, m, cov, w_eq, sec_of, worst)
    caps = [mcap.get(s) for s in eligible]
    mc = None
    mcap_missing = [s for s, v in zip(eligible, caps) if v is None or not v > 0]
    if not mcap_missing:
        w_mc = np.array(caps, dtype=float)
        w_mc = w_mc / w_mc.sum()
        mc = _basket(x, m, cov, w_mc, sec_of, worst)
    n_eff = effective_stocks(corr, t_obs)
    s_eff = effective_sectors(sec_of)
    bench = {"volPct": round(float(m.std() * np.sqrt(52) * 100), 1), "maxDrawdownPct": round(max_drawdown(m) * 100, 1)}
    out.update({
        "included": n,
        "asOf": {"fromWeek": x.index[0], "toWeek": x.index[-1], "weeks": t_obs, "frequency": "weekly",
                 "label": window_label(week_monday(x.index[0]), week_monday(x.index[-1]))},
        "score": diversification_score(n_eff, s_eff),
        "headline": {"effectiveStocks": round(n_eff, 2), "effectiveStocksRounded": round_half_up(n_eff), "avgCorrelation": round(float(upper.mean()), 2)},
        "clusters": _clusters(corr, eligible),
        "overlap": _overlap(corr, eligible),
        "matrix": {"symbols": eligible, "values": [[round(float(v), 2) for v in row] for row in corr]} if n <= MATRIX_MAX else None,
        "market": {"benchmark": "NIFTY 50", "betaEqual": eq["beta"], "betaMcap": mc["beta"] if mc else None,
                   "stocks": [{"symbol": s, "beta": round(float(x[s].cov(m) / m.var()), 2)} for s in eligible]},
        "stress": {"worstWeeks": WORST_WEEKS, "benchmarkAvgPct": round(float(m[worst].mean() * 100), 2), "equalAvgPct": eq["stressAvgPct"],
                   "mcapAvgPct": mc["stressAvgPct"] if mc else None,
                   "stocks": [{"symbol": s, "fellMoreThanIndex": int((x.loc[worst, s] < m[worst]).sum())} for s in eligible]},
        "riskShare": {"equal": eq["riskShare"], "mcap": mc["riskShare"] if mc else None},
        "basket": {"equal": eq, "mcap": mc, "benchmark": bench},
        "mcapMissing": mcap_missing,
        "recentVsLongRun": recent_vs_long(x, eligible),
    })
    return out


def recent_vs_long(x: "pd.DataFrame", names: Sequence[str]) -> Dict[str, Any]:
    """Effective stocks and pair correlations over the last RECENT_WEEKS weeks against the 3-year window. x: the common weekly sample."""
    r3 = x[list(names)]
    r1 = r3.tail(RECENT_WEEKS)
    c3, c1 = r3.corr().values, r1.corr().values
    n = len(names)
    iu = np.triu_indices(n, 1)
    pairs = [{"pair": [names[i], names[j]], "recent": round(float(c1[i, j]), 2), "longRun": round(float(c3[i, j]), 2), "change": round(float(c1[i, j] - c3[i, j]), 2)}
             for i, j in zip(*iu)]
    for p in pairs:
        p["flag"] = pair_flag(p["recent"], p["longRun"])
        p["direction"] = ("more" if p["recent"] > p["longRun"] else "less") if p["flag"] else None
    return {"recent": {"weeks": len(r1), "effectiveStocks": round(effective_stocks(c1, len(r1)), 2), "avgCorrelation": round(float(c1[iu].mean()), 2)},
            "longRun": {"weeks": len(r3), "effectiveStocks": round(effective_stocks(c3, len(r3)), 2), "avgCorrelation": round(float(c3[iu].mean()), 2)},
            "largestRises": sorted(pairs, key=lambda p: -p["change"])[:3], "largestFalls": sorted(pairs, key=lambda p: p["change"])[:3],
            "flagged": [p for p in pairs if p["flag"]]}


# ------------------------------------------------------------------ monthly and yearly (co-movement figures only; never the score)
def _month_end(dates: Sequence[str], closes: Sequence[float]) -> "pd.Series":
    s = pd.Series(np.asarray(closes, dtype="float64"), index=pd.to_datetime(list(dates))).sort_index()
    return s.groupby(s.index.to_period("M")).last()


def horizon_view(prices_max: Dict[str, Any], symbols: Sequence[str], horizon: str, current_month: str) -> Dict[str, Any]:
    """Co-movement figures on month-end returns (monthly, 5 years) or rolling 12-month returns (yearly, indicative). current_month: 'YYYY-MM' of the
    unfinished month, dropped. The score is NOT worked out here."""
    if horizon not in ("monthly", "yearly"):
        raise ValueError("use weekly_view() for the weekly horizon")
    symbols = [s for s in dict.fromkeys(symbols) if prices_max.get(s) and prices_max[s].get("t")]
    cur = pd.Period(current_month, "M")
    px = pd.DataFrame({s: _month_end(prices_max[s]["t"], prices_max[s]["c"]) for s in symbols}).sort_index() if symbols else pd.DataFrame()
    px = px[px.index < cur] if len(px) else px
    need = MONTHLY_MIN if horizon == "monthly" else YEARLY_MIN_MONTHS
    have = px.notna().sum() if len(px) else pd.Series(dtype=int)
    if horizon == "monthly":
        r = _pct(px).iloc[1:].tail(MONTHLY_MONTHS) if len(px) else px
        counts = r.notna().sum() if len(r) else pd.Series(dtype=int)
    else:
        r = (px / px.shift(12) - 1).iloc[12:] if len(px) > 12 else px.iloc[0:0]
        counts = have
    ok = [s for s in symbols if s in counts.index and counts[s] >= need]
    excluded = [{"symbol": s, "reason": "history", "months": int(have.get(s, 0))} for s in symbols if s not in ok]
    out: Dict[str, Any] = {"horizon": horizon, "included": len(ok), "excluded": excluded, "scoreVersion": SCORE_VERSION}
    if len(ok) < MIN_STOCKS:
        return out
    r = r[ok].dropna()
    if len(r) < 12:
        out["included"] = 0
        return out
    names = list(r.columns)
    t_eff = len(r) if horizon == "monthly" else (len(r) + 12 - 1) / 12      # yearly: overlapping windows, so months of returns / 12
    corr = r.corr().values
    upper = corr[np.triu_indices(len(names), 1)]
    out["asOf"] = {"fromMonth": str(r.index[0]), "toMonth": str(r.index[-1]), "months": len(r), "frequency": horizon,
                   "label": window_label(r.index[0].to_timestamp().date(), r.index[-1].to_timestamp().date()),
                   "effectiveObservations": round(float(t_eff), 1)}
    out["included"] = len(names)
    out["headline"] = {"effectiveStocks": round(effective_stocks(corr, t_eff), 2), "effectiveStocksRounded": round_half_up(effective_stocks(corr, t_eff)),
                       "avgCorrelation": round(float(upper.mean()), 2)}
    if horizon == "monthly":
        out["clusters"] = _clusters(corr, names)
        out["overlap"] = _overlap(corr, names)
        nif = (prices_max.get("__NIFTY") or {}).get("rows") or []
        if nif:
            nme = _month_end([q["d"] for q in nif], [q["c"] for q in nif])
            nme = nme[nme.index < cur]
            nm = _pct(nme.to_frame("b")).dropna()["b"]
            common = r.join(nm.rename("__B"), how="inner").dropna()
            if len(common) >= 12:
                b = common["__B"]
                out["market"] = {"benchmark": "NIFTY 50", "betaEqual": round(float(common[names].mean(axis=1).cov(b) / b.var()), 2), "benchmarkReturns": len(common)}
    else:
        out["indicative"] = True
        pairs = sorted(((names[i], names[j], round(float(corr[i, j]), 2)) for i, j in zip(*np.triu_indices(len(names), 1))), key=lambda p: -p[2])
        as_d = lambda p: {"pair": [p[0], p[1]], "correlation": p[2]}  # noqa: E731
        out["mostRelated"], out["leastRelated"] = [as_d(p) for p in pairs[:3]], [as_d(p) for p in reversed(pairs[-3:])]
    return out


# ------------------------------------------------------------------ style tilt
def style_tilt(universe: Sequence[Dict[str, Any]], symbols: Sequence[str]) -> Dict[str, Any]:
    """Average Prism part percentile of the list within the rated (or provisional) universe, equal weights, names only. universe: one dict per
    rated or provisional company with 'symbol' and the prism_* fields of TILT_PARTS (None where a part is missing)."""
    uni = pd.DataFrame(list(universe)).set_index("symbol")
    have = [s for s in symbols if s in uni.index]
    parts = []
    for field, name, high, low in TILT_PARTS:
        if field not in uni.columns:
            parts.append({"part": name, "listAverage": None, "universeMedian": None, "avgPercentile": None, "lean": None, "wording": None, "stocks": 0})
            continue
        col = pd.to_numeric(uni[field], errors="coerce")
        pct = col.rank(pct=True) * 100
        vals = col.loc[have].dropna()
        if vals.empty:
            parts.append({"part": name, "listAverage": None, "universeMedian": round(float(col.median()), 1), "avgPercentile": None, "lean": None, "wording": None, "stocks": 0})
            continue
        avg_pct = float(pct.loc[vals.index].mean())
        lean = "high" if avg_pct >= TILT_HIGH else "low" if avg_pct <= TILT_LOW else "typical"
        parts.append({"part": name, "listAverage": round(float(vals.mean()), 1), "universeMedian": round(float(col.median()), 1), "avgPercentile": round_half_up(avg_pct),
                      "lean": lean, "wording": high if lean == "high" else low if lean == "low" else None, "stocks": int(len(vals))})
    first = TILT_PARTS[0][0]
    return {"universe": int(uni[first].notna().sum()) if first in uni.columns else int(len(uni)), "notRated": [s for s in symbols if s not in have], "parts": parts}


def tilt_sentence(parts: Sequence[Dict[str, Any]]) -> str:
    """'This list leans towards lower-risk and higher-quality companies, and stocks in short-term uptrends. Growth & profitability, valuation and the
    long-term trend are close to typical.' Built from the data; a lean is a comparison with other rated companies, never a verdict."""
    leaning = sorted((p for p in parts if p.get("lean") in ("high", "low")), key=lambda p: -abs(p["avgPercentile"] - 50))   # the strongest lean first
    typical = [p for p in parts if p.get("lean") == "typical"]
    if not leaning and not typical:
        return ""
    short = {"Growth & Profitability": "growth & profitability", "Valuation": "valuation", "Quality": "quality", "Risk": "risk",
             "Short-term technical view": "the short-term trend", "Long-term technical view": "the long-term trend"}
    bits = []
    if leaning:
        words = [p["wording"] for p in leaning]
        companies = [w for w in words if w.endswith(("companies", "stocks")) and not w.startswith("stocks in")]
        stocks_in = [w for w in words if w.startswith("stocks in")]
        phrase = ""
        if companies:
            # "lower-risk and higher-quality companies" when several end in the same noun
            heads = [w.rsplit(" ", 1)[0] for w in companies]
            noun = companies[0].rsplit(" ", 1)[1]
            if all(w.rsplit(" ", 1)[1] == noun for w in companies):
                phrase = " and ".join(heads) + " " + noun if len(heads) < 3 else ", ".join(heads[:-1]) + " and " + heads[-1] + " " + noun
            else:
                phrase = " and ".join(companies)
        if stocks_in:
            phrase += (", and " if phrase else "") + " and ".join(stocks_in)
        bits.append(f"This list leans towards {phrase}.")
    if typical:
        names = [short[p["part"]] for p in typical]
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        verb = "is" if len(names) == 1 else "are"
        bits.append((joined[0].upper() + joined[1:]) + f" {verb} close to typical." if leaning else f"All parts are close to typical: {joined}.")
    return " ".join(bits)
