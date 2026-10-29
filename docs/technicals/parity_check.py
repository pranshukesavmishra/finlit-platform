"""Parity check: our ST/LT engine (site-api/backend/premium_technical.py) against finlit_technicals v1.1 (the team's package) on IDENTICAL daily bars.

Not part of the test suite and not run in production (it needs numpy and pandas, which the Docker image does not have).
    python3 docs/technicals/parity_check.py /path/to/finlit_technicals_repo_root [--json out.json]
prints a table: scenario, short-term and long-term score of both engines, the difference, and every component whose signal differs.
Bars are deterministic (seeded) synthetic series in several regimes plus the recorded daily quotes of five stocks in
site-api/backend/tests/fixtures/premium_replay (real bars; the index is the equal-weighted mean of the five, since no index bars are recorded).
"""
import gzip
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(Path(sys.argv[1])))
sys.path.insert(0, str(ROOT / "site-api"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from finlit_technicals import stlt as S  # noqa: E402
from backend import premium_technical as OURS  # noqa: E402

ASOF = date(2026, 10, 23)
ST_MAP = {"ema_stack": "ema_stack", "price_ema20": "price_vs_ema20", "macd": "macd", "rsi": "rsi", "obv": "obv", "rs_rating": "rs_rating_short",
          "extension": "extension", "consolidation": "ema9_consolidation", "squeeze": "squeeze", "gap": "gap", "candles": "price_action",
          "sfp": "sfp", "leadership": "rs_leadership", "value_migration": "value_area_migration"}
LT_MAP = {"stage": "stage", "rs_rating": "rs_rating_long", "leadership": "rs_leadership", "price_ema200": "price_vs_ema200",
          "volume_persistence": "volume_persistence", "sfp": "major_sfp", "ema200_slope": "ema200_slope", "ema50_200": "ema50_vs_ema200",
          "weekly_rsi": "weekly_rsi", "weekly_macd": "weekly_macd", "structure": "structure_52w", "obv_trend": "obv_trend", "ema100_200": "ema100_vs_ema200"}
IDX = {"Nifty 500": "NSE:CNX500", "Nifty 50": "NSE:NIFTY", "Nifty Midcap 100": "NSE:CNXMIDCAP", "Nifty Smallcap 100": "NSE:CNXSMALLCAP"}


def sessions(n):
    out, d = [], ASOF
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def synth(n, seed, drift=0.0004, vol=0.018, p0=100.0, vmean=13.0, gaps=()):
    r = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(sessions(n))
    ret = r.normal(drift, vol, n)
    c = p0 * np.exp(np.cumsum(ret))
    o = np.r_[c[0], c[:-1]] * np.exp(r.normal(0, 0.004, n))
    for i, g in gaps:
        o[i] = c[i - 1] * (1 + g)
        c[i] = max(c[i], o[i] * 1.01) if g > 0 else min(c[i], o[i] * 0.99)
    h = np.maximum(o, c) * np.exp(np.abs(r.normal(0, 0.006, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(r.normal(0, 0.006, n)))
    v = r.lognormal(vmean, 0.5, n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def bench_frames(n=1800):
    out = {}
    for k, (name, seed, p0) in enumerate([("Nifty 500", 901, 20000), ("Nifty 50", 902, 25000), ("Nifty Midcap 100", 903, 50000), ("Nifty Smallcap 100", 904, 16000)]):
        out[name] = synth(n, seed, drift=0.0003, vol=0.010, p0=p0)
    return out


def scenarios():
    b = bench_frames()
    sc = []
    sc.append(("strong uptrend (900 bars)", synth(900, 1, 0.0018, 0.011), b, None))
    sc.append(("downtrend (900 bars)", synth(900, 2, -0.0018, 0.013), b, None))
    sc.append(("sideways (900 bars)", synth(900, 3, 0.0, 0.008), b, None))
    sc.append(("volatile (900 bars)", synth(900, 4, 0.0003, 0.035), b, None))
    sc.append(("gap up on last bar", synth(900, 5, 0.001, 0.012, gaps=[(899, 0.04)]), b, None))
    sc.append(("gap down on last bar", synth(900, 6, -0.0005, 0.012, gaps=[(899, -0.04)]), b, None))
    sc.append(("small cap, rs vs Smallcap 100", synth(900, 7, 0.001, 0.02), b, 4500))
    sc.append(("mid cap, rs vs Midcap 100", synth(900, 8, 0.0008, 0.015), b, 50000))
    sc.append(("large cap, rs vs Nifty 50", synth(900, 9, 0.0006, 0.012), b, 200000))
    for n in (30, 60, 150, 230, 260, 400):
        sc.append((f"short history ({n} bars)", synth(n, 40 + n, 0.001, 0.018), b, None))
    # real recorded bars (the provider pads holidays with all-zero rows: kept in the RAW variant, dropped in the CLEAN variant)
    raw_real, real = {}, {}
    for s in ("TCS", "HDFCBANK", "SKIPPER", "BAJFINANCE", "HDFCLIFE"):
        d = json.load(gzip.open(ROOT / f"site-api/backend/tests/fixtures/premium_replay/{s}.json.gz"))
        for k, v in d["recorded"].items():
            if k.startswith(f'["/daily-quotes/{s}"'):
                rows = sorted(v["price"], key=lambda r: r["quote_date"])
                frame = lambda rs: pd.DataFrame({"open": [r["open_price"] for r in rs], "high": [r["high_price"] for r in rs], "low": [r["low_price"] for r in rs],
                                                 "close": [r["close_price"] for r in rs], "volume": [r["volume"] for r in rs]}, index=pd.to_datetime([r["quote_date"] for r in rs]))
                raw_real[s] = frame(rows)
                real[s] = frame([r for r in rows if any(r[x] for x in ("open_price", "high_price", "low_price", "close_price", "volume"))])
    common = sorted(set.intersection(*[set(df.index) for df in real.values()]))
    comp = pd.concat([df.loc[common, "close"] / df.loc[common[0], "close"] for df in real.values()], axis=1).mean(axis=1) * 10000
    rb = {n: pd.DataFrame({"open": comp, "high": comp, "low": comp, "close": comp, "volume": 0.0}, index=comp.index) for n in IDX}
    for s, df in real.items():
        sc.append((f"REAL {s} clean ({len(df.loc[common])} bars)", df.loc[common], rb, None))
    for s, df in raw_real.items():
        sc.append((f"REAL {s} raw rows ({len(df)} bars)", df, rb, None))
    return sc


def bars_of(df):
    return [{"date": d.date().isoformat(), "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close), "volume": float(r.volume)} for d, r in df.iterrows()]


def run_ours(df, bench, mcap):
    rows = [{"quote_date": b["date"], "open_price": b["open"], "high_price": b["high"], "low_price": b["low"], "close_price": b["close"], "volume": b["volume"]} for b in bars_of(df)]
    price = OURS.resolve_technical_prices({"price": rows}, "FinEdge", df.index[-1].date())   # the production path: provider rows -> normalise_bars
    bm = {n: {"bars": [{"date": d.date().isoformat(), "close": float(c)} for d, c in f["close"].items()], "provider": "x"} for n, f in bench.items()}
    shares_cr = None if mcap is None else mcap / float(df["close"].iloc[-1])
    asof = df.index[-1].date()
    return OURS.build_technical_assessment(price, asof, bm, shares_cr)


def run_pkg(df, bench, mcap):
    benches = {IDX[n]: f for n, f in bench.items()}
    shares = None if mcap is None else mcap * 1e7 / float(df["close"].iloc[-1])
    return S.compute(df, benches, shares=shares)


def compare(name, df, bench, mcap):
    o, p = run_ours(df, bench, mcap), run_pkg(df, bench, mcap)
    row = {"scenario": name, "bars": len(df)}
    row["st_ours"] = o["shortTerm"]["score"]; row["lt_ours"] = o["longTerm"]["score"]
    row["st_pkg"], row["lt_pkg"] = p.st_score, p.lt_score
    diffs = []
    pst = {r.key: r for r in p.st_rows}; plt_ = {r.key: r for r in p.lt_rows}
    for horizon, mp, prow in (("ST", ST_MAP, pst), ("LT", LT_MAP, plt_)):
        factors = {f["key"]: f for f in o["shortTerm" if horizon == "ST" else "longTerm"]["factors"]}
        for ok, pk in mp.items():
            f = factors[ok]
            a, b = f["signal"], prow[pk].signal
            if a is None or abs(a - b) > 1e-9:
                diffs.append(f"{horizon} {pk}: ours {a if a is not None else 'unavailable'} / pkg {b:g}")
    row["diffs"] = diffs
    row["stage_ours"] = o["observations"].get("stage"); row["stage_pkg"] = p.stage
    row["capped_pkg"] = p.gated; row["capped_ours"] = o["longTerm"]["stageCapped"]
    row["adx_pkg"] = p.adx
    row["mult_pkg"] = p.trend_mult
    row["bench_ours"] = o["observations"].get("benchmark"); row["bench_pkg"] = p.bench_name
    row["rating_ours"] = o["shortTerm"]["rating"] + " / " + o["longTerm"]["rating"]
    row["rating_pkg"] = S.rate(p.st_score) + " / " + S.rate(p.lt_score)
    row["align_pkg"] = p.alignment
    return row


# ---- the pinned cases of site-api/backend/tests/test_technical_parity.py: bars made with plain `random` (no numpy), so the test needs nothing extra
import math  # noqa: E402
import random  # noqa: E402


def pure_bars(n, seed, drift, vol, p0=100.0):
    rnd = random.Random(seed)
    days = sessions(n)
    price, rows = p0, []
    for day in days:
        ret = drift + vol * (sum(rnd.random() for _ in range(12)) - 6)
        o = price * (1 + (rnd.random() - 0.5) * 0.006)
        c = price * math.exp(ret)
        h = max(o, c) * (1 + rnd.random() * 0.008)
        l = min(o, c) * (1 - rnd.random() * 0.008)
        v = 100000 * (1 + 4 * rnd.random())
        rows.append((day, o, h, l, c, v))
        price = c
    return rows


PINS = {"stage3_capped": (900, 11, 0.0016, 0.011, None), "bounce_in_downtrend": (900, 12, -0.0015, 0.012, None), "weak_short_term": (900, 13, 0.0, 0.009, None), "smallcap_stage2": (700, 14, 0.0007, 0.02, 4500),
        "largecap_stage4": (800, 15, 0.0009, 0.013, 200000), "stage3_cap_binds": (900, 53, 0.0006, 0.012, None)}


def pin_frames():
    b = {name: pd.DataFrame([(d, c, c, c, c, 0.0) for d, _, _, _, c, _ in pure_bars(1100, 90 + k, 0.0003, 0.01, p0)], columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
         for k, (name, p0) in enumerate([("Nifty 500", 20000), ("Nifty 50", 25000), ("Nifty Midcap 100", 50000), ("Nifty Smallcap 100", 16000)])}
    for f in b.values():
        f.index = pd.DatetimeIndex(f.index)
    return b


def print_pins(path=None):
    b = pin_frames()
    pins = {"_source": "finlit_technicals v1.1 (stlt.compute) on the bars of pure_bars() in docs/technicals/parity_check.py; regenerate with --pins <file>"}
    for name, (n, seed, drift, vol, mcap) in PINS.items():
        df = pd.DataFrame([(d, o, h, l, c, v) for d, o, h, l, c, v in pure_bars(n, seed, drift, vol)], columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
        df.index = pd.DatetimeIndex(df.index)
        p = run_pkg(df, b, mcap)
        sig = {"ST": {r.key: r.signal for r in p.st_rows}, "LT": {r.key: r.signal for r in p.lt_rows}}
        pins[name] = {"params": {"n": n, "seed": seed, "drift": drift, "vol": vol, "mcap": mcap}, "st": round(p.st_score, 9), "lt": round(p.lt_score, 9), "stage": p.stage,
                      "capped": p.gated, "uncapped": round(p.lt_norm, 9), "adx": round(p.adx, 6), "mult": p.trend_mult, "bench": p.bench_name, "alignment": p.alignment,
                      "stRating": S.rate(p.st_score), "ltRating": S.rate(p.lt_score),
                      "points": {**{"ST " + r.key: round(r.points, 6) for r in p.st_rows}, **{"LT " + r.key: round(r.points, 6) for r in p.lt_rows}}, "signals": sig}
    if path:
        Path(path).write_text(json.dumps(pins, indent=1, sort_keys=True))
    return pins


if __name__ == "__main__":
    if "--pins" in sys.argv:
        print_pins(sys.argv[sys.argv.index("--pins") + 1])
        sys.exit(0)
    out = []
    for name, df, bench, mcap in scenarios():
        out.append(compare(name, df, bench, mcap))
    f = lambda x: "none" if x is None else f"{x:+.3f}"
    for r in out:
        print(f"{r['scenario']:<36} ST ours {f(r['st_ours']):>9} pkg {f(r['st_pkg']):>9} | LT ours {f(r['lt_ours']):>9} pkg {f(r['lt_pkg']):>9} | stage {r['stage_ours']}/{r['stage_pkg']} | {r['bench_ours']}/{r['bench_pkg']}")
        for d in r["diffs"]:
            print("      ", d)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(out, default=str, indent=1))
