"""
FinLit - Diversification card (Mode B without amounts): reference calculation.

Implements the addendum "Correlation Analyzer spec - Addendum: Mode B without amounts".
Input is share names only; no quantities, amounts, prices paid or dates are accepted.

Usage:
    python diversification_reference.py sample_prices.json sample_prices_max.json sample_prism.json

sample_prices_max.json has the same shape, from GET /api/stocks/{symbol}/price?range=MAX (weekly bars from
January 2020); it feeds the monthly and yearly horizons.
sample_prism.json holds the Prism parts of every rated or provisional company (from /api/screener/universe);
it feeds the style tilt.

sample_prices.json has the shape of the site's own endpoints:
    {"<SYMBOL>": {"t": ["2023-11-03", ...], "c": [741.15, ...]},     # GET /api/stocks/{symbol}/price?range=3Y
     "__NIFTY": {"rows": [{"d": "2023-09-01", "c": 19435.3}, ...]}}  # GET /api/indices/NIF50/history?range=5Y

Requires: numpy, pandas, scipy, scikit-learn.
"""
import json
import sys

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

LOOKBACK_WEEKS = 156       # 3 years of complete weeks
MIN_WEEKS = 52             # minimum history for co-movement figures
MIN_STOCKS = 3             # minimum eligible stocks for co-movement figures
CLUSTER_CUT = 0.5          # distance 1 - rho; groups average a correlation of 0.5 or more
WORST_WEEKS = 10           # stress test: the benchmark's worst weeks
SCORE_VERSION = "1"
SCORE_CAP_STOCKS = 15      # effective independent stocks at which co-movement scores 100
SCORE_CAP_SECTORS = 8      # effective sectors at which sector spread scores 100
SCORE_WEIGHTS = (0.6, 0.4) # co-movement, sector spread
BANDS = [(80, "Widely spread"), (60, "Fairly spread"), (40, "Somewhat concentrated"), (0, "Concentrated")]
ALLOWED_FIELDS = {"symbols", "benchmark", "horizon"}
HORIZONS = {"weekly", "monthly", "yearly"}
MONTHLY_MONTHS = 60        # monthly horizon: latest 60 complete months
MONTHLY_MIN = 36
YEARLY_MIN_MONTHS = 60
RECENT_WEEKS = 52          # recent vs long-run: last 52 complete weeks against the 3-year window
CHANGE_FLAG = 0.30         # flag a pair when its 1-year correlation differs from its 3-year one by 0.30 or more
CHANGE_FLOOR = 0.50        # ...and the higher of the two correlations is at least 0.50
TILT_HIGH, TILT_LOW = 65, 35  # average percentile at or above / at or below which the list "leans"
TILT_PARTS = [  # (field, name, wording when high, wording when low)
    ("prism_fundamental", "Growth & Profitability", "faster-growing, more profitable companies", "slower-growing, less profitable companies"),
    ("prism_valuation", "Valuation", "cheaper stocks", "more expensive stocks"),
    ("prism_quality", "Quality", "higher-quality companies", "lower-quality companies"),
    ("prism_risk", "Risk", "lower-risk companies", "higher-risk companies"),
    ("prism_st_score", "Short-term technical view", "stocks in short-term uptrends", "stocks in short-term downtrends"),
    ("prism_lt_score", "Long-term technical view", "stocks in long-term uptrends", "stocks in long-term downtrends"),
]


def validate_request(body: dict) -> list:
    """Reject anything except share names: no quantity, amount, price or date fields."""
    extra = set(body) - ALLOWED_FIELDS
    if extra:
        raise ValueError(f"422: fields not accepted: {sorted(extra)}")
    if body.get("horizon", "weekly") not in HORIZONS:
        raise ValueError("422: horizon must be weekly, monthly or yearly")
    return list(dict.fromkeys(body["symbols"]))   # de-duplicate, keep order


def iso_week(dates) -> list:
    iso = pd.to_datetime(pd.Series(dates)).dt.isocalendar()
    return (iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)).tolist()


def weekly_closes(series_t, series_c) -> pd.Series:
    s = pd.Series(np.asarray(series_c, dtype="float64"), index=iso_week(series_t))
    return s[~s.index.duplicated(keep="last")]


def effective_stocks(corr: np.ndarray, t_obs: int) -> float:
    """N^2 / (N + sum over i != j of max(rho^2 - 1/T, 0)). 1 = all move as one, N = no co-movement."""
    n = corr.shape[0]
    off = corr[~np.eye(n, dtype=bool)]
    return n ** 2 / (n + np.maximum(off ** 2 - 1.0 / t_obs, 0).sum())


def effective_sectors(sector_labels: list) -> float:
    """1 / sum of squared sector shares, counted by stocks (never by money)."""
    shares = pd.Series(sector_labels).value_counts(normalize=True)
    return float(1.0 / (shares ** 2).sum())


def diversification_score(n_eff: float, s_eff: float) -> dict:
    """0-100 score: 0.6 x co-movement + 0.4 x sector spread, each on a log scale with a cap."""
    co = 100 * min(1.0, np.log(max(n_eff, 1.0)) / np.log(SCORE_CAP_STOCKS))
    sec = 100 * min(1.0, np.log(max(s_eff, 1.0)) / np.log(SCORE_CAP_SECTORS))
    raw = SCORE_WEIGHTS[0] * co + SCORE_WEIGHTS[1] * sec
    value = int(np.floor(raw + 0.5))                  # round half up; the band uses the rounded value
    band = next(label for edge, label in BANDS if value >= edge)
    return {"value": value, "unrounded": round(float(raw), 1), "band": band,
            "coMovement": int(np.floor(co + 0.5)), "sectorSpread": int(np.floor(sec + 0.5)),
            "effectiveSectors": round(s_eff, 2)}


def risk_share(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """RC_i = w_i (Sigma w)_i / (w' Sigma w); shares sum to 1."""
    return w * (cov @ w) / (w @ cov @ w)


def max_drawdown(r: pd.Series) -> float:
    level = (1 + r).cumprod()
    return float((level / level.cummax() - 1).min())


def diversification(prices: dict, symbols: list, sectors: dict, mcap: dict, groups: dict,
                    current_week: str) -> dict:
    """prices: {symbol: {"t", "c"}, "__NIFTY": {"rows"}}; current_week: ISO week to drop (unfinished)."""
    closes = {s: weekly_closes(prices[s]["t"], prices[s]["c"]) for s in symbols if s in prices}
    nif = pd.DataFrame(prices["__NIFTY"]["rows"])
    closes["__NIFTY"] = weekly_closes(nif["d"], nif["c"])
    C = pd.DataFrame(closes).sort_index()
    C = C[C.index < current_week]                      # never use the unfinished week
    R_all = C.pct_change(fill_method=None).iloc[1:].tail(LOOKBACK_WEEKS)

    weeks_avail = R_all.drop(columns="__NIFTY").notna().sum()
    eligible = [s for s in symbols if s in weeks_avail and weeks_avail[s] >= MIN_WEEKS]
    excluded = [{"symbol": s, "reason": "history", "weeks": int(weeks_avail.get(s, 0))}
                for s in symbols if s not in eligible]

    spread = {
        "sectors": [{"name": k, "count": int(v)} for k, v in
                    pd.Series([sectors.get(s, "Not listed") for s in symbols]).value_counts().items()],
        "groups": [{"name": g, "symbols": [s for s in symbols if groups.get(s) == g]}
                   for g in sorted({groups[s] for s in symbols if s in groups})],
    }
    out = {"included": len(eligible), "excluded": excluded, "spread": spread}
    if len(eligible) < MIN_STOCKS:
        return out                                      # spread by count only

    R = R_all[eligible + ["__NIFTY"]].dropna()          # one common, aligned sample
    X, m = R[eligible], R["__NIFTY"]
    n, t_obs = len(eligible), len(R)
    corr = X.corr().values
    upper = corr[np.triu_indices(n, 1)]

    # clusters: average linkage on 1 - rho, cut at CLUSTER_CUT
    dist = 1 - corr
    np.fill_diagonal(dist, 0)
    labels = fcluster(linkage(squareform(dist, checks=False), method="average"),
                      t=CLUSTER_CUT, criterion="distance")
    clusters = []
    for lab in sorted(set(labels)):
        idx = np.where(labels == lab)[0]
        if len(idx) > 1:
            sub = corr[np.ix_(idx, idx)][np.triu_indices(len(idx), 1)]
            clusters.append({"symbols": [eligible[i] for i in idx], "avgCorrelation": round(float(sub.mean()), 2)})
    clusters.sort(key=lambda c: (-len(c["symbols"]), -c["avgCorrelation"]))

    overlap = sorted(({"symbol": s, "avgCorrelation": round(float((corr[i].sum() - 1) / (n - 1)), 2)}
                      for i, s in enumerate(eligible)), key=lambda d: -d["avgCorrelation"])

    # covariance with Ledoit-Wolf shrinkage for risk share and volatility
    cov = LedoitWolf().fit(X.values).covariance_
    w_eq = np.repeat(1.0 / n, n)
    mc = np.array([mcap[s] for s in eligible], dtype=float)
    w_mc = mc / mc.sum()

    def basket(w):
        r = pd.Series(X.values @ w, index=X.index)
        rs = risk_share(w, cov)
        by_sector = pd.Series(rs, index=[sectors.get(s, "Not listed") for s in eligible]).groupby(level=0).sum()
        return {
            "volPct": round(float(np.sqrt(w @ cov @ w) * np.sqrt(52) * 100), 1),
            "maxDrawdownPct": round(max_drawdown(r) * 100, 1),
            "beta": round(float(r.cov(m) / m.var()), 2),
            "stressAvgPct": round(float(r[m.nsmallest(WORST_WEEKS).index].mean() * 100), 2),
            "riskShare": {
                "stocks": sorted(({"symbol": s, "pct": round(float(v * 100), 1)} for s, v in zip(eligible, rs)),
                                 key=lambda d: -d["pct"]),
                "sectors": [{"name": k, "pct": round(float(v * 100), 1)}
                            for k, v in by_sector.sort_values(ascending=False).items()],
            },
        }

    worst = m.nsmallest(WORST_WEEKS).index
    n_eff = effective_stocks(corr, t_obs)
    s_eff = effective_sectors([sectors.get(s, "Not listed") for s in eligible])
    out.update({
        "asOf": {"fromWeek": X.index[0], "toWeek": X.index[-1], "weeks": t_obs, "frequency": "weekly"},
        "scoreVersion": SCORE_VERSION,
        "score": diversification_score(n_eff, s_eff),
        "headline": {"effectiveStocks": round(float(n_eff), 2),
                     "effectiveStocksRounded": int(np.floor(n_eff + 0.5)),
                     "avgCorrelation": round(float(upper.mean()), 2)},
        "clusters": clusters,
        "overlap": overlap,
        "market": {"benchmark": "NIFTY 50",
                   "stocks": [{"symbol": s, "beta": round(float(X[s].cov(m) / m.var()), 2)} for s in eligible]},
        "stress": {"worstWeeks": WORST_WEEKS, "benchmarkAvgPct": round(float(m[worst].mean() * 100), 2),
                   "stocks": [{"symbol": s, "fellMoreThanIndex": int((X.loc[worst, s] < m[worst]).sum())}
                              for s in eligible]},
        "basket": {"equal": basket(w_eq), "mcap": basket(w_mc),
                   "benchmark": {"volPct": round(float(m.std() * np.sqrt(52) * 100), 1),
                                 "maxDrawdownPct": round(max_drawdown(m) * 100, 1)}},
    })
    return out


def style_tilt(prism: dict, symbols: list) -> dict:
    """Average Prism parts of the list against all rated or provisional companies (equal weights, names only)."""
    uni = pd.DataFrame(prism["rows"], columns=prism["cols"]).set_index("symbol")
    have = [s for s in symbols if s in uni.index]
    parts = []
    for field, name, high, low in TILT_PARTS:
        col = pd.to_numeric(uni[field], errors="coerce")
        pct = col.rank(pct=True) * 100
        vals = col.loc[have].dropna()
        avg_pct = float(pct.loc[vals.index].mean())
        lean = "high" if avg_pct >= TILT_HIGH else "low" if avg_pct <= TILT_LOW else "typical"
        parts.append({"part": name, "listAverage": round(float(vals.mean()), 1),
                      "universeMedian": round(float(col.median()), 1),
                      "avgPercentile": int(np.floor(avg_pct + 0.5)), "lean": lean,
                      "wording": high if lean == "high" else low if lean == "low" else None,
                      "stocks": int(len(vals))})
    return {"universe": int(uni[TILT_PARTS[0][0]].notna().sum()), "asOf": prism.get("asOf"),
            "notRated": [s for s in symbols if s not in have], "parts": parts}


def pair_flag(recent: float, long_run: float) -> bool:
    """Flag a pair when its correlation moved by CHANGE_FLAG or more and the higher value is CHANGE_FLOOR or more."""
    return abs(recent - long_run) >= CHANGE_FLAG - 1e-9 and max(recent, long_run) >= CHANGE_FLOOR


def recent_vs_long(prices: dict, symbols: list, current_week: str) -> dict:
    """Effective stocks and pair correlations over the last 52 weeks against the 3-year window."""
    closes = pd.DataFrame({s: weekly_closes(prices[s]["t"], prices[s]["c"]) for s in symbols}).sort_index()
    closes = closes[closes.index < current_week]
    R3 = closes.pct_change(fill_method=None).iloc[1:].tail(LOOKBACK_WEEKS).dropna()
    R1 = R3.tail(RECENT_WEEKS)
    c3, c1 = R3.corr().values, R1.corr().values
    n = len(symbols)
    iu = np.triu_indices(n, 1)
    pairs = [{"pair": [symbols[i], symbols[j]], "recent": round(float(c1[i, j]), 2),
              "longRun": round(float(c3[i, j]), 2), "change": round(float(c1[i, j] - c3[i, j]), 2)}
             for i, j in zip(*iu)]
    for p in pairs:
        p["flag"] = pair_flag(p["recent"], p["longRun"])
    up = sorted(pairs, key=lambda p: -p["change"])[:3]
    down = sorted(pairs, key=lambda p: p["change"])[:3]
    return {"recent": {"weeks": len(R1), "effectiveStocks": round(float(effective_stocks(c1, len(R1))), 2),
                       "avgCorrelation": round(float(c1[iu].mean()), 2)},
            "longRun": {"weeks": len(R3), "effectiveStocks": round(float(effective_stocks(c3, len(R3))), 2),
                        "avgCorrelation": round(float(c3[iu].mean()), 2)},
            "largestRises": up, "largestFalls": down, "flagged": [p for p in pairs if p["flag"]]}


def _clusters(corr: np.ndarray, names: list) -> list:
    dist = 1 - corr
    np.fill_diagonal(dist, 0)
    labels = fcluster(linkage(squareform(dist, checks=False), method="average"),
                      t=CLUSTER_CUT, criterion="distance")
    out = []
    for lab in sorted(set(labels)):
        idx = np.where(labels == lab)[0]
        if len(idx) > 1:
            sub = corr[np.ix_(idx, idx)][np.triu_indices(len(idx), 1)]
            out.append({"symbols": [names[i] for i in idx], "avgCorrelation": round(float(sub.mean()), 2)})
    return sorted(out, key=lambda c: (-len(c["symbols"]), -c["avgCorrelation"]))


def horizon_view(prices_max: dict, symbols: list, horizon: str, current_month: str) -> dict:
    """Co-movement figures on monthly (5 years) or yearly (rolling 12-month, indicative) returns.
    current_month: 'YYYY-MM' of the unfinished month to drop. The score is NOT computed here."""
    px = pd.DataFrame({s: pd.Series(np.asarray(prices_max[s]["c"], dtype="float64"),
                                    index=pd.to_datetime(prices_max[s]["t"])) for s in symbols}).sort_index()
    me = px.groupby(px.index.to_period("M")).last()
    me = me[me.index < pd.Period(current_month, "M")]
    nif = pd.DataFrame(prices_max["__NIFTY"]["rows"])
    nser = pd.Series(nif["c"].values, index=pd.to_datetime(nif["d"])).sort_index()
    nme = nser.groupby(nser.index.to_period("M")).last()
    nme = nme[nme.index < pd.Period(current_month, "M")]
    if horizon == "monthly":
        R = me.pct_change(fill_method=None).iloc[1:].tail(MONTHLY_MONTHS)
        R = R[[s for s in symbols if R[s].notna().sum() >= MONTHLY_MIN]].dropna()
        t_eff = len(R)
    elif horizon == "yearly":
        R = (me / me.shift(12) - 1).iloc[12:]
        enough = [s for s in symbols if me[s].notna().sum() >= YEARLY_MIN_MONTHS]
        R = R[enough].dropna()
        t_eff = (len(R) + 12 - 1) / 12      # months of monthly returns / 12
    else:
        raise ValueError("use diversification() for the weekly horizon")
    names = list(R.columns)
    corr = R.corr().values
    upper = corr[np.triu_indices(len(names), 1)]
    out = {"horizon": horizon, "observations": len(R), "effectiveObservations": round(float(t_eff), 1),
           "fromMonth": str(R.index[0]), "toMonth": str(R.index[-1]),
           "headline": {"effectiveStocks": round(float(effective_stocks(corr, t_eff)), 2),
                        "avgCorrelation": round(float(upper.mean()), 2)}}
    if horizon == "monthly":
        out["clusters"] = _clusters(corr, names)
        nm = nme.pct_change().dropna()
        common = R.join(nm.rename("__B"), how="inner").dropna()
        b = common["__B"]
        out["market"] = {"betaEqual": round(float(common[names].mean(axis=1).cov(b) / b.var()), 2),
                         "benchmarkReturns": len(common)}
    else:
        out["indicative"] = True
        pairs = sorted(((names[i], names[j], round(float(corr[i, j]), 2))
                        for i, j in zip(*np.triu_indices(len(names), 1))), key=lambda x: -x[2])
        out["mostRelated"], out["leastRelated"] = pairs[:3], pairs[-3:]
    return out


# ---------------- sample list from the addendum ----------------
SAMPLE = ["RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "TCS", "INFY",
          "HCLTECH", "ITC", "LT", "BHARTIARTL", "TATASTEEL", "SUNPHARMA"]
SAMPLE_SECTORS = {"RELIANCE": "Oil & gas", "HDFCBANK": "Financial services", "ICICIBANK": "Financial services",
                  "SBIN": "Financial services", "KOTAKBANK": "Financial services", "AXISBANK": "Financial services",
                  "BAJFINANCE": "Financial services", "TCS": "Information technology",
                  "INFY": "Information technology", "HCLTECH": "Information technology", "ITC": "FMCG",
                  "LT": "Construction", "BHARTIARTL": "Telecom", "TATASTEEL": "Metals & mining",
                  "SUNPHARMA": "Healthcare"}
SAMPLE_GROUPS = {"TCS": "Tata", "TATASTEEL": "Tata"}
SAMPLE_MCAP_CR = {"RELIANCE": 1742855.66, "HDFCBANK": 1110447.42, "ICICIBANK": 1016438.67, "SBIN": 920307.45,
                  "KOTAKBANK": 455115.56, "AXISBANK": 383295.20, "BAJFINANCE": 604228.86, "TCS": 900939.95,
                  "INFY": 463008.83, "HCLTECH": 389492.39, "ITC": 337948.06, "LT": 542102.62,
                  "BHARTIARTL": 1265768.52, "TATASTEEL": 220034.63, "SUNPHARMA": 425234.13}


def self_tests():
    assert abs(effective_stocks(np.eye(5), 10**9) - 5) < 1e-9
    assert abs(effective_stocks(np.ones((5, 5)), 10**9) - 1) < 1e-9
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    assert abs(risk_share(np.array([0.5, 0.5]), cov).sum() - 1) < 1e-12
    assert diversification_score(15, 8)["coMovement"] == 100 and diversification_score(15, 8)["sectorSpread"] == 100
    assert diversification_score(1, 1)["value"] == 0
    assert pair_flag(0.60, 0.20) and not pair_flag(0.45, 0.20)
    try:
        validate_request({"symbols": ["TCS"], "horizon": "daily"})
        raise AssertionError("unknown horizon must be rejected")
    except ValueError:
        pass
    assert diversification_score(15, 2.4)["band"] in {lab for _, lab in BANDS}
    try:
        validate_request({"symbols": ["TCS"], "quantity": [10]})
        raise AssertionError("amount fields must be rejected")
    except ValueError:
        pass


if __name__ == "__main__":
    self_tests()
    prices = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "sample_prices.json"))
    prices_max = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "sample_prices_max.json"))
    prism = json.load(open(sys.argv[3] if len(sys.argv) > 3 else "sample_prism.json"))
    symbols = validate_request({"symbols": SAMPLE, "benchmark": "NIF50"})
    result = diversification(prices, symbols, SAMPLE_SECTORS, SAMPLE_MCAP_CR, SAMPLE_GROUPS,
                             current_week="2026-W45")
    eq = result["basket"]["equal"]
    # displayed shares are rounded to 0.1, so their sum may differ from 100 by up to 0.05 per stock
    assert abs(sum(d["pct"] for d in eq["riskShare"]["stocks"]) - 100) <= 0.05 * len(symbols) + 1e-9
    betas = [d["beta"] for d in result["market"]["stocks"]]
    assert abs(eq["beta"] - np.mean(betas)) < 0.01
    # the score examples table in the addendum
    examples = {
        "Sample list (15)": (SAMPLE, 72),
        "One per sector (8)": (["RELIANCE", "HDFCBANK", "TCS", "ITC", "LT", "BHARTIARTL", "TATASTEEL", "SUNPHARMA"], 78),
        "Banks + IT (9)": (["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "TCS", "INFY", "HCLTECH"], 45),
        "Banks and Bajaj Finance (6)": (["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE"], 28),
        "TCS, Infosys, HCL Technologies (3)": (["TCS", "INFY", "HCLTECH"], 7),
    }
    for name, (syms, expected) in examples.items():
        sc = diversification(prices, syms, SAMPLE_SECTORS, SAMPLE_MCAP_CR, SAMPLE_GROUPS, "2026-W45")["score"]
        assert sc["value"] == expected, (name, sc)
        print(f"{name}: {sc['value']}, {sc['band']} (co-movement {sc['coMovement']}, sector spread {sc['sectorSpread']})")
    # horizon table in the addendum
    monthly = horizon_view(prices_max, SAMPLE, "monthly", current_month="2026-11")
    assert monthly["headline"] == {"effectiveStocks": 6.4, "avgCorrelation": 0.28}, monthly["headline"]
    assert monthly["market"] == {"betaEqual": 0.91, "benchmarkReturns": 59}, monthly["market"]
    yearly = horizon_view(prices_max, SAMPLE, "yearly", current_month="2026-11")
    assert yearly["headline"] == {"effectiveStocks": 4.09, "avgCorrelation": 0.49}, yearly["headline"]
    assert yearly["effectiveObservations"] == 6.8 and "clusters" not in yearly
    print("Monthly, 5 years:", monthly["headline"], monthly["clusters"], monthly["market"])
    print("Yearly, indicative:", yearly["headline"], "T =", yearly["effectiveObservations"])
    # style tilt
    tilt = style_tilt(prism, SAMPLE)
    got = {p["part"]: (p["avgPercentile"], p["lean"]) for p in tilt["parts"]}
    assert got == {"Growth & Profitability": (53, "typical"), "Valuation": (61, "typical"),
                   "Quality": (65, "high"), "Risk": (82, "high"),
                   "Short-term technical view": (72, "high"), "Long-term technical view": (48, "typical")}, got
    assert tilt["universe"] == 650 and tilt["notRated"] == []
    print("Style tilt:", got)
    # recent vs long-run
    rl = recent_vs_long(prices, SAMPLE, current_week="2026-W45")
    assert rl["recent"]["effectiveStocks"] == 6.78 and rl["longRun"]["effectiveStocks"] == 6.99, rl
    assert rl["largestRises"][0]["change"] == 0.24 and rl["flagged"] == []
    print("Recent vs long-run:", rl["recent"], rl["longRun"], [(p["pair"], p["longRun"], p["recent"]) for p in rl["largestRises"]])
    print(json.dumps(result, indent=1, default=str))
