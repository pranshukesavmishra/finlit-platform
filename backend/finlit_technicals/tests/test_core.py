"""Tests for the Pine built-ins (pine.py), the ST/LT scores (stlt.py) and the peer label (peers.py).
Run: python tests/run_tests.py   (or python -m pytest -q tests)"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from finlit_technicals import pine as P
from finlit_technicals import peers as PR
from finlit_technicals import stlt as S
from finlit_technicals.api import DEFAULT_GROUPS

try:
    import pytest
except ImportError:  # the bundled runner (tests/run_tests.py) works without pytest
    class pytest:  # type: ignore
        @staticmethod
        def fixture(f):
            return f

GROUPS = Path(DEFAULT_GROUPS)                     # the peer lists that ship with the package
NAN = float("nan")


# ─── data helpers ─────────────────────────────────────────────────────────────────────────────────────────
def synth(n, seed, start="2017-01-02", drift=0.0004, vol=0.018, p0=100.0, vmean=13.0):
    r = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    c = p0 * np.exp(np.cumsum(r.normal(drift, vol, n)))
    o = c * np.exp(r.normal(0, 0.006, n))
    h = np.maximum(o, c) * np.exp(np.abs(r.normal(0, 0.008, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(r.normal(0, 0.008, n)))
    v = r.lognormal(vmean, 0.5, n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def trend(n, daily, start="2019-01-01", p0=100.0, vol_shares=2e6, noise=0.0, seed=0):
    """Smooth trend: close = p0 * exp(daily * t) (+ optional noise)."""
    r = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    c = p0 * np.exp(daily * np.arange(n) + (r.normal(0, noise, n).cumsum() if noise else 0))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * 1.004
    l = np.minimum(o, c) * 0.996
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": np.full(n, vol_shares)}, index=idx)


def close_enough(a, b, tol=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    both_nan = np.isnan(a) & np.isnan(b)
    return bool(np.all(both_nan | (np.abs(a - b) <= tol * np.maximum(1.0, np.abs(b)))))


# ─── reference implementations written straight from the Pine reference (slow loops) ─────────────────────
def ref_sma(x, n):
    out = np.full(len(x), NAN)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if not np.isnan(w).any():
            out[i] = sum(w) / n
    return out


def ref_seeded(x, n, alpha):
    # sum := na(sum[1]) ? ta.sma(src, length) : alpha * src + (1 - alpha) * nz(sum[1])
    s = ref_sma(x, n)
    out = np.full(len(x), NAN)
    for i in range(len(x)):
        prev = out[i - 1] if i > 0 else NAN
        out[i] = s[i] if math.isnan(prev) else alpha * x[i] + (1 - alpha) * prev
    return out


def ref_rsi(x, n):
    u = np.full(len(x), NAN)
    d = np.full(len(x), NAN)
    for i in range(1, len(x)):
        u[i] = max(x[i] - x[i - 1], 0.0)
        d[i] = max(x[i - 1] - x[i], 0.0)
    ru, rd = ref_seeded(u, n, 1 / n), ref_seeded(d, n, 1 / n)
    out = np.full(len(x), NAN)
    for i in range(len(x)):
        if math.isnan(ru[i]) or math.isnan(rd[i]):
            continue
        out[i] = 100.0 if rd[i] == 0 else 0.0 if ru[i] == 0 else 100 - 100 / (1 + ru[i] / rd[i])
    return out


def ref_percentrank(x, n):
    out = np.full(len(x), NAN)
    for i in range(n, len(x)):
        if math.isnan(x[i]):
            continue
        cnt = sum(1 for j in range(1, n + 1) if not math.isnan(x[i - j]) and x[i - j] <= x[i])
        out[i] = 100.0 * cnt / n
    return out


def ref_pivot(src, left, right, high):
    out = np.full(len(src), NAN)
    for i in range(left + right, len(src)):
        j = i - right
        p = src[j]
        ok = all((src[j - k] < p) if high else (src[j - k] > p) for k in range(1, left + 1))
        ok = ok and all((src[j + k] <= p) if high else (src[j + k] >= p) for k in range(1, right + 1))
        if ok:
            out[i] = p
    return out


# ─── pine.py ──────────────────────────────────────────────────────────────────────────────────────────────
def test_pine_averages_match_the_reference():
    x = synth(400, 3)["close"].to_numpy()
    xn = x.copy()
    xn[:7] = NAN                     # leading na, as a MACD line has
    for n in (1, 3, 9, 20, 50):
        assert close_enough(P.sma(x, n), ref_sma(x, n))
        assert close_enough(P.sma(xn, n), ref_sma(xn, n))
        assert close_enough(P.ema(xn, n), ref_seeded(xn, n, 2 / (n + 1)))
        assert close_enough(P.rma(xn, n), ref_seeded(xn, n, 1 / n))
    assert np.isnan(P.ema(x, 20)[18]) and not np.isnan(P.ema(x, 20)[19])
    assert abs(P.ema(x, 20)[19] - x[:20].mean()) < 1e-9                # seeded with the SMA
    s = pd.Series(x)
    assert close_enough(P.stdev(x, 20), s.rolling(20).std(ddof=0).to_numpy(), 1e-7)
    assert close_enough(P.median(x, 13), s.rolling(13).median().to_numpy())
    y = synth(400, 4)["close"].to_numpy()
    assert close_enough(P.correlation(x, y, 30), s.rolling(30).corr(pd.Series(y)).to_numpy(), 1e-7)
    assert close_enough(P.highest(x, 20), s.rolling(20).max().to_numpy())
    assert close_enough(P.lowest(x, 20), s.rolling(20).min().to_numpy())
    xg = x.copy()
    xg[50] = NAN
    assert P.highest(xg, 5)[52] == np.nanmax(xg[48:53])                  # na inside the window is skipped


def test_pine_rsi_textbook_and_reference():
    # Wilder's RSI, the StockCharts worked example (14 periods)
    closes = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931,
              46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521,
              45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314]
    expect = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42, 39.99, 41.46,
              41.87, 45.46, 37.30, 33.08, 37.77]
    r = P.rsi(closes, 14)
    assert np.isnan(r[13]) and not np.isnan(r[14])
    assert np.allclose(r[14:], expect, atol=0.01), np.round(r[14:], 2)
    x = synth(300, 5)["close"].to_numpy()
    assert close_enough(P.rsi(x, 14), ref_rsi(x, 14))
    flat = np.full(40, 10.0)
    assert P.rsi(flat, 14)[-1] == 100.0          # no losses at all


def test_pine_atr_dmi_macd_obv():
    d = synth(300, 6)
    h, l, c, v = (d[k].to_numpy() for k in ("high", "low", "close", "volume"))
    tr = np.r_[h[0] - l[0], [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]]
    assert close_enough(P.atr(h, l, c, 14), ref_seeded(tr, 14, 1 / 14))
    _, _, adx = P.dmi(h, l, c, 14, 14)
    assert np.isnan(adx[26]) and not np.isnan(adx[27])
    assert np.nanmin(adx) >= 0 and np.nanmax(adx) <= 100
    t = trend(200, 0.01)
    _, _, adx_t = P.dmi(t["high"], t["low"], t["close"], 14, 14)
    assert adx_t[-1] > 90                          # a straight-line trend has a very high ADX
    m, s, hist = P.macd(c)
    assert np.isnan(m[24]) and not np.isnan(m[25]) and np.isnan(s[32]) and not np.isnan(s[33])
    assert close_enough(hist, m - s)
    o = P.obv(c, v)
    assert o[0] == 0 and o[1] == (v[1] if c[1] > c[0] else -v[1] if c[1] < c[0] else 0)


def test_pine_percentrank_linreg_pivots_barssince():
    x = synth(400, 7)["close"].to_numpy()
    xn = x.copy()
    xn[:100] = NAN
    for arr_ in (x, xn):
        assert close_enough(P.percentrank(arr_, 126), ref_percentrank(arr_, 126))
    lr = P.linreg(x, 20)
    for i in (19, 100, 399):
        k, b = np.polyfit(np.arange(20), x[i - 19:i + 1], 1)
        assert abs(lr[i] - (k * 19 + b)) < 1e-8
    h = synth(400, 8)["high"].to_numpy().round(0)      # rounded: plenty of equal highs
    assert close_enough(P.pivothigh(h, 5, 5), ref_pivot(h, 5, 5, True))
    assert close_enough(P.pivotlow(h, 5, 5), ref_pivot(h, 5, 5, False))
    tie = np.array([1, 2, 3, 5, 5, 3, 2, 1, 0, 0, 0], float)
    ph = P.pivothigh(tie, 2, 2)
    assert ph[5] == 5 and np.isnan(ph[6])               # the first of two equal highs is the pivot
    bs = P.barssince([False, True, False, False, True, False])
    assert np.isnan(bs[0]) and list(bs[1:]) == [0, 1, 2, 0, 1]


# ─── stlt.py ──────────────────────────────────────────────────────────────────────────────────────────────
def test_scores_add_up_and_alignment_follows_the_bands():
    st, b = synth(2400, 1), synth(2400, 2, vol=0.01, p0=10000)
    for seed in range(4):
        st = synth(2400, 10 + seed, drift=0.0008 * (seed - 1.5))
        res = S.compute(st, {"NSE:CNX500": b}, symbol="T")
        assert abs(sum(r.points for r in res.st_rows) - res.st_score) < 1e-9
        assert abs(sum(r.points for r in res.lt_rows) - res.lt_norm) < 1e-9
        assert -100 <= res.st_score <= 100 and -100 <= res.lt_score <= 100
        assert res.alignment == S.alignment(S.band(res.st_score), S.band(res.lt_score))
        assert sum(r.weight for r in res.st_rows) == 96 and sum(r.weight for r in res.lt_rows) == 92
        assert len(res.st_rows) == 15 and len(res.lt_rows) == 14
        if res.gated:
            assert res.lt_score <= 19 and res.stage in (3, 4)
        txt = S.breakdown_text(res)
        assert "TREND ALIGNMENT" in txt and res.alignment in txt
    # sector RS and value migration switched off change the divisors as in Pine
    res = S.compute(st, {"NSE:CNX500": b}, S.StltParams(use_va_mig=False, use_sector=True), sector=b)
    assert res.st_div == 94 and res.lt_div == 100
    assert abs(sum(r.points for r in res.st_rows) - res.st_score) < 1e-9


def test_descriptive_labels():
    grid = {(1, 1): "Strong on both timeframes", (1, 0): "Short-term strength, no long-term trend",
            (1, -1): "Short-term bounce within a long-term downtrend", (0, 1): "Long-term uptrend, short-term pause",
            (0, 0): "No clear trend", (0, -1): "Long-term downtrend, short-term flat",
            (-1, 1): "Short-term pullback within a long-term uptrend", (-1, 0): "Short-term weakness, no long-term trend",
            (-1, -1): "Weak on both timeframes"}
    for (sb, lb), v in grid.items():
        assert S.alignment(sb, lb) == v
    assert len(set(grid.values())) == 9                               # every cell has its own label
    assert S.alignment_code(1, -1) == "st_positive_lt_negative"
    assert [S.band(x) for x in (20, 19.99, -19.99, -20)] == [1, 0, 0, -1]
    assert [S.rate(x) for x in (50, 20, 0, -20, -50)] == ["Very strong", "Strong", "Neutral", "Weak", "Very weak"]
    assert [S.rating_code(x) for x in (50, 49.9, 20, 19.9, -19.9, -20, -49.9, -50)] == [2, 1, 1, 0, 0, -1, -1, -2]
    assert S.pround(2.5) == 3 and S.pround(-2.5) == -3 and S.pround(-13.54) == -14


def test_uptrend_is_stage_2_and_downtrend_is_capped():
    b = trend(700, 0.0003, p0=10000)
    up = S.compute(trend(700, 0.002, noise=0.004, seed=1), {"NSE:CNX500": b})
    assert up.stage == 2 and up.lt_score > 20
    dn = S.compute(trend(700, -0.002, noise=0.004, seed=2), {"NSE:CNX500": b})
    assert dn.stage == 4 and dn.gated and dn.lt_score <= 19 and dn.lt_score < -20


def test_short_and_young_histories_run():
    b = synth(2400, 2, vol=0.01, p0=10000)
    for n in (2, 5, 30, 60, 150, 260):
        d = synth(n, 20 + n, start="2026-01-05")
        res = S.compute(d, {"NSE:CNX500": b})
        assert len(res.st_rows) == 15 and not math.isnan(res.st_score)
        if n < 200:
            assert any("daily bars" in nt for nt in res.notes)
    one = synth(1, 1)
    try:
        S.compute(one, {})
        raise AssertionError("one bar should be refused")
    except ValueError:
        pass


def test_awkward_bars_run():
    d = synth(500, 30)
    d.iloc[100:110, :4] = 50.0          # flat bars: zero range
    d.iloc[200:205, 4] = 0.0            # no volume
    d = d.drop(d.index[300:320])        # a suspension
    res = S.compute(d, {"NSE:CNX500": synth(600, 31, p0=9000)})
    assert not math.isnan(res.st_score) and not math.isnan(res.lt_score)
    res2 = S.compute(d, {})             # no benchmark at all: RS rows read na and count -1
    assert any("no Nifty 500 prices" in nt for nt in res2.notes)
    rs = [r for r in res2.st_rows if r.name == "RS rating (short)"][0]
    assert rs.signal == -1.0 and rs.reading.startswith("NaN")


def test_benchmark_buckets():
    st = synth(800, 40)
    benches = {"NSE:CNX500": synth(800, 41, p0=20000), "NSE:NIFTY": synth(800, 42, p0=20000),
               "NSE:CNXMIDCAP": synth(800, 43, p0=40000), "NSE:CNXSMALLCAP": synth(800, 44, p0=15000)}
    assert S.compute(st, benches, cap_class=3).bench_name == "Smallcap 100"
    assert S.compute(st, benches, cap_class=2).bench_name == "Midcap 100"
    assert S.compute(st, benches, cap_class=1).bench_name == "Nifty 50"
    assert S.compute(st, benches).bench_name == "Nifty 500"
    big = 1e12 / st["close"].iloc[-1]                        # Rs 1 lakh crore+: large cap from the share count
    assert S.compute(st, benches, shares=big * 1.2).bench_name == "Nifty 50"
    no_small = {k: v for k, v in benches.items() if k != "NSE:CNXSMALLCAP"}
    assert S.compute(st, no_small, cap_class=3).bench_name == "Nifty 500"     # na -> falls back, as f_pick does
    assert S.compute(st, benches, S.StltParams(bench_choice="nifty50")).bench_name == "Nifty 50"


def test_weekly_values_are_the_last_completed_week():
    d = synth(600, 50)
    d = d[d.index <= "2019-04-17"]                            # a Wednesday
    res = S.compute(d, {"NSE:CNX500": synth(600, 51, p0=9000)})
    w = S.weekly(S.clean(d))
    assert w.index[-1] == pd.Timestamp("2019-04-15")          # the current, unfinished week
    wr = P.rsi(w["close"].to_numpy(), 14)[-2]                  # the week before it
    row = [r for r in res.lt_rows if r.name == "Weekly RSI 14"][0]
    assert row.reading.startswith(f"RSI {wr:.1f}")


def _sfp_bars():
    """A swing high at 110 (bar 20), then bar 30 trades to 112 and closes back at 108 on heavy volume."""
    n = 34
    idx = pd.bdate_range("2024-01-01", periods=n)
    c = np.array([100 + 3 * math.sin(i / 2.0) for i in range(n)])
    c[15:26] = [101, 102, 103, 104, 105, 108, 105, 104, 103, 102, 101]
    c[26:30] = [102, 103, 104, 105]
    h, l, o = c + 1.0, c - 1.0, c - 0.2
    h[20] = 110.0
    h[21:30] = np.minimum(h[21:30], 106.0)
    h[30], c[30], l[30], o[30] = 112.0, 108.0, 106.5, 109.0
    c[31], h[31], l[31], o[31] = 105.0, 107.0, 104.0, 106.0          # closes below the SFP bar's low: confirmed
    c[32:], h[32:], l[32:], o[32:] = 104.0, 105.0, 103.0, 104.5
    v = np.full(n, 1e6)
    v[30] = 3e6
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def test_swing_failure_pattern():
    d = _sfp_bars()
    bench = synth(60, 1, start="2023-12-01", p0=1000)
    sig = lambda k: [r for r in S.compute(d.iloc[:k], {"NSE:CNX500": bench}).st_rows if r.name == "Swing failure (SFP)"][0]
    r30, r31 = sig(31), sig(32)
    assert r30.signal == -0.75 and "Bear SFP 110.00" in r30.reading
    assert r31.signal == -1.0 and "(confirmed)" in r31.reading
    quiet = d.copy()
    quiet.iloc[30, 4] = 1e5                                          # same bar on thin volume: not counted
    r = [x for x in S.compute(quiet.iloc[:31], {"NSE:CNX500": bench}).st_rows if x.name == "Swing failure (SFP)"][0]
    assert r.signal == 0.0


def test_volume_profile():
    h = np.array([10, 11, 12, 11, 10.5, 20.0])
    l = np.array([9, 10, 11, 10, 10.0, 19.0])
    v = np.array([1, 1, 1, 1, 50, 1.0])
    poc, vah, val = S.volume_profile(h, l, v, 5, 6, 24)
    assert 10.0 <= poc <= 10.5 and val <= poc <= vah
    assert all(math.isnan(x) for x in S.volume_profile(h, l, v, 5, 1, 24))
    flat = np.full(6, 10.0)
    assert all(math.isnan(x) for x in S.volume_profile(flat, flat, v, 5, 6, 24))


# ─── peers.py ─────────────────────────────────────────────────────────────────────────────────────────────
def _db():
    return PR.PeerDB.from_groups(json.loads(GROUPS.read_text(encoding="utf-8")))


def test_peer_group_resolution_matches_the_scripts():
    db = _db()
    g = PR.resolve("SAMBHV", db, PR.PeerParams(max_peers=30))
    assert (g.idx, g.name, g.sec_sym, g.sec_name) == (6, "Steel", "NSE:CNXMETAL", "Nifty Metal")
    assert len(g.symbols) == 31 and g.symbols[0] == "NSE:SAMBHV" and "NSE:SAMBHV" not in g.symbols[1:]
    assert len(PR.resolve("SAMBHV", db, PR.PeerParams(max_peers=37)).symbols) == 35     # the whole list of 35
    g = PR.resolve("TCS", db, PR.PeerParams())
    assert (g.idx, g.name, g.sec_sym) == (1, "IT", "NSE:CNXIT")
    g = PR.resolve("HDFCBANK", db, PR.PeerParams())
    assert (g.idx, g.sec_name) == (3, "Nifty Pvt Bank")
    g = PR.resolve("M&M", db, PR.PeerParams())
    assert g.idx == 5 and g.sec_sym == "NSE:CNXAUTO"
    g = PR.resolve("RELIANCE", db, PR.PeerParams())
    assert (g.name, g.sec_name) == ("Oil Refining/Marketing", "Nifty Energy")
    g = PR.resolve("ITC", db, PR.PeerParams())                         # only in a sector list
    assert (g.idx, g.name, g.sec_sym) == (7, "Consumer Non-Durables sector", "NSE:CNXFMCG")
    g = PR.resolve("SAMBHV", db, PR.PeerParams(preset="TradingView sector (wider)"))
    assert g.idx == 7 and g.sec_sym == "NSE:CNXMETAL"
    g = PR.resolve("NOSUCH", db, PR.PeerParams())
    assert g.idx == 0 and g.symbols == ["NSE:NOSUCH"]
    g = PR.resolve("NOSUCH", db, PR.PeerParams(custom="tcs, infy;NSE:WIPRO\nnosuch"))
    assert g.symbols == ["NSE:NOSUCH", "NSE:TCS", "NSE:INFY", "NSE:WIPRO"] and g.sec_sym == ""
    g = PR.resolve("NEWCO", db, PR.PeerParams(), industry="Steel")     # a stock outside the lists
    assert g.name == "Steel" and g.symbols[0] == "NSE:NEWCO" and len(g.symbols) == 36
    assert PR.index_for("I", "Food: Specialty/Candy") == "NSE:CNXFMCG" and PR.index_for("I", "Textiles") == ""


def _peer_world(n_peers=11, weeks=160, seed=0):
    """Peers with steady but different trends; the sector index is flat."""
    r = np.random.default_rng(seed)
    days = weeks * 5
    syms = ["NSE:STK"] + [f"NSE:P{k}" for k in range(n_peers)]
    rates = {s: 0.0004 * (k - n_peers / 2) for k, s in enumerate(syms)}
    rates["NSE:STK"] = 0.004                                          # the strongest one
    daily = {s: trend(days, rates[s], start="2022-01-03", vol_shares=1e6, noise=0.003, seed=int(r.integers(1e6)))
             for s in syms}
    grp = PR.Group(0, ",".join(s[4:] for s in syms[1:]), "test", "NSE:SEC", "Test index", "", "", syms)
    sec = trend(days, 0.0, start="2022-01-03", p0=1000)
    return grp, daily, sec


def test_peer_ranking_labels_and_benchmarks():
    grp, daily, sec = _peer_world()
    p = PR.PeerParams()
    res = PR.compute(daily["NSE:STK"], {s: d for s, d in daily.items() if s != "NSE:STK"}, grp, p, sector_daily=sec)
    r = res.last
    assert r.state == 0 and r.ranked == 12 and r.k == math.ceil(0.3 * 12)
    assert r.rank == 1 and res.pub == 1 and r.bench_name == "Test index"
    assert abs(r.rel52 - r.rows[0].r52) < 1e-9                        # flat index: relative = own return
    order = PR.ordered(r.rows)
    r52 = [r.rows[i].r52 for i in order]
    assert r52 == sorted(r52, reverse=True)
    tbl = PR.table_rows(res, full=True)
    labs = [t[2].split(" ")[0] for t in tbl if t[0].isdigit()]
    assert labs[:r.k].count("Leader") >= 1 and labs[-1] in ("Laggard", "In line")
    # no sector index: the equal-weighted average of the ranked peers
    res2 = PR.compute(daily["NSE:STK"], {s: d for s, d in daily.items() if s != "NSE:STK"},
                      PR.Group(0, "", "test", "", "peer average", "", "", grp.symbols), p)
    r2 = res2.last
    avg = sum(x.r52 for x in r2.rows if x.status == 0) / r2.ranked
    assert r2.bench_name == "peer average" and abs(r2.rel52 - (r2.rows[0].r52 - avg)) < 1e-12
    assert "Leader" in PR.status_text(res) and "Peers · test" in PR.peers_table_text(res)


def test_peer_exclusions_and_too_few():
    grp, daily, sec = _peer_world()
    d = {s: x for s, x in daily.items() if s != "NSE:STK"}
    d["NSE:P0"] = d["NSE:P0"].iloc[:-12]                              # stopped trading 2+ weeks ago: stale
    d["NSE:P1"] = d["NSE:P1"].assign(volume=10.0)                     # thin
    d["NSE:P2"] = d["NSE:P2"].iloc[-200:]                             # under 52 weeks
    del d["NSE:P3"]                                                   # no data
    res = PR.compute(daily["NSE:STK"], d, grp, PR.PeerParams(), sector_daily=sec)
    st = {row.symbol: row.status for row in res.last.rows}
    assert (st["NSE:P0"], st["NSE:P1"], st["NSE:P2"], st["NSE:P3"]) == (4, 3, 2, 1)
    assert res.last.ranked == 8 and any("no prices for 1 peer" in nt for nt in res.notes)
    few = PR.compute(daily["NSE:STK"], d, grp, PR.PeerParams(min_n=10), sector_daily=sec)
    assert few.last.state == 4 and few.pub is None and "Too few comparable" in few.line()
    thin_self = PR.compute(daily["NSE:STK"].assign(volume=1.0), d, grp, PR.PeerParams(), sector_daily=sec)
    assert thin_self.last.state == 3 and thin_self.pub is None
    lone = PR.compute(daily["NSE:STK"], {}, PR.Group(0, "", "custom-list", "", "peer average", "", "", ["NSE:STK"]), PR.PeerParams())
    assert lone.last.state == 1 and "No peer group" in lone.line()


def _check_two_run_rule(res):
    prev_pub, prev_raw = None, None
    for r in res.runs:
        if r.raw is None:
            if r.state in (2, 3, 4):
                assert r.pub is None
        elif prev_pub is None:
            assert r.pub == r.raw                                     # the first label shows at once
        elif r.raw != prev_pub:
            assert r.pub == (r.raw if r.raw == prev_raw else prev_pub)
        else:
            assert r.pub == prev_pub
        prev_pub, prev_raw = r.pub, r.raw


def test_label_needs_two_weekly_runs():
    grp, daily, sec = _peer_world(seed=3)
    stk = daily["NSE:STK"].copy()
    # crash the stock late so its label walks from Leader down
    n = len(stk)
    f = np.ones(n)
    f[n - 260:] = np.exp(-0.009 * np.arange(260))
    for k in ("open", "high", "low", "close"):
        stk[k] = stk[k] * f
    res = PR.compute(stk, {s: d for s, d in daily.items() if s != "NSE:STK"}, grp, PR.PeerParams(), sector_daily=sec)
    raws = [r.raw for r in res.runs if r.raw is not None]
    assert 1 in raws and -1 in raws
    _check_two_run_rule(res)
    flips = [k for k in range(1, len(res.runs)) if res.runs[k].pub != res.runs[k - 1].pub and res.runs[k - 1].pub is not None]
    assert flips and all(res.runs[k].raw == res.runs[k - 1].raw for k in flips)
    fast = PR.compute(stk, {s: d for s, d in daily.items() if s != "NSE:STK"}, grp, PR.PeerParams(stable=False), sector_daily=sec)
    assert all(r.pub == r.raw for r in fast.runs if r.raw is not None)


def test_weekly_runs_use_completed_weeks():
    grp, daily, sec = _peer_world()
    stk = daily["NSE:STK"]
    stk = stk[stk.index <= "2024-06-12"]                              # a Wednesday
    res = PR.compute(stk, {s: d for s, d in daily.items() if s != "NSE:STK"}, grp, PR.PeerParams(), sector_daily=sec)
    assert res.last.ref_week == pd.Timestamp("2024-06-03") and res.last.date == pd.Timestamp("2024-06-10")
    w = S.weekly(stk)
    c = w["close"].to_numpy()
    assert abs(res.last.rows[0].r52 - (c[-2] / c[-2 - 52] - 1)) < 1e-12
