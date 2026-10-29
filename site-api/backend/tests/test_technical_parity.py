"""The technical engine against finlit_technicals v1.1 (the team's port of 'ST/LT Score Breakdown & Peers v1.2').

The expected values in fixtures/technical_parity_pins.json were produced by running the package on the SAME bars (the bars come from pure_bars(), plain
`random`, so this test needs no numpy). docs/technicals/PARITY.md has the wider comparison (about 260 series, all identical) and
docs/technicals/parity_check.py regenerates the pins. Where the two ever differ, the package follows the chart (Pine) and this engine follows the package.
"""
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend import technical_wording as tw
from backend.premium_technical import ST, LT, build_technical_assessment, normalise_bars, resolve_technical_prices
from backend.technical_series import ema, macd

PINS = json.loads((Path(__file__).parent / "fixtures" / "technical_parity_pins.json").read_text())
CASES = {k: v for k, v in PINS.items() if not k.startswith("_")}
ASOF = date(2026, 10, 23)
ST_MAP = {"ema_stack": "ema_stack", "price_ema20": "price_vs_ema20", "macd": "macd", "rsi": "rsi", "obv": "obv", "rs_rating": "rs_rating_short", "extension": "extension",
          "consolidation": "ema9_consolidation", "squeeze": "squeeze", "gap": "gap", "candles": "price_action", "sfp": "sfp", "leadership": "rs_leadership",
          "value_migration": "value_area_migration"}
LT_MAP = {"stage": "stage", "rs_rating": "rs_rating_long", "leadership": "rs_leadership", "price_ema200": "price_vs_ema200", "volume_persistence": "volume_persistence",
          "sfp": "major_sfp", "ema200_slope": "ema200_slope", "ema50_200": "ema50_vs_ema200", "weekly_rsi": "weekly_rsi", "weekly_macd": "weekly_macd",
          "structure": "structure_52w", "obv_trend": "obv_trend", "ema100_200": "ema100_vs_ema200"}


def sessions(n):
    out, day = [], ASOF
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return out[::-1]


def pure_bars(n, seed, drift, vol, p0=100.0):
    """Identical to pure_bars() in docs/technicals/parity_check.py."""
    rnd = random.Random(seed)
    price, rows = p0, []
    for day in sessions(n):
        ret = drift + vol * (sum(rnd.random() for _ in range(12)) - 6)
        o = price * (1 + (rnd.random() - 0.5) * 0.006)
        c = price * math.exp(ret)
        h = max(o, c) * (1 + rnd.random() * 0.008)
        l = min(o, c) * (1 - rnd.random() * 0.008)
        v = 100000 * (1 + 4 * rnd.random())
        rows.append({"date": day.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v})
        price = c
    return rows


def benchmarks():
    out = {}
    for k, (name, p0) in enumerate([("Nifty 500", 20000), ("Nifty 50", 25000), ("Nifty Midcap 100", 50000), ("Nifty Smallcap 100", 16000)]):
        out[name] = {"bars": [{"date": b["date"], "close": b["close"]} for b in pure_bars(1100, 90 + k, 0.0003, 0.01, p0)], "provider": "FinEdge"}
    return out


def assess(params):
    bars = pure_bars(params["n"], params["seed"], params["drift"], params["vol"])
    shares_cr = None if params["mcap"] is None else params["mcap"] / bars[-1]["close"]
    return build_technical_assessment({"bars": bars, "provider": "FinEdge", "notes": []}, ASOF, benchmarks(), shares_cr)


@pytest.mark.parametrize("name", sorted(CASES))
def test_scores_and_every_signal_equal_the_package(name):
    pin, got = CASES[name], assess(CASES[name]["params"])
    assert got["shortTerm"]["score"] == pytest.approx(pin["st"], abs=1e-6)
    assert got["longTerm"]["score"] == pytest.approx(pin["lt"], abs=1e-6)
    for horizon, mapping, prefix in (("shortTerm", ST_MAP, "ST"), ("longTerm", LT_MAP, "LT")):
        rows = {f["key"]: f for f in got[horizon]["factors"]}
        for ours, theirs in mapping.items():
            assert rows[ours]["signal"] == pytest.approx(pin["signals"][prefix][theirs], abs=1e-9), (horizon, ours)
    assert got["observations"]["stage"] == pin["stage"] and (got["observations"]["stage"] in (3, 4)) == pin["capped"]     # the package's `capped`: the cap applies
    assert got["observations"]["benchmark"].removeprefix("Nifty ") == pin["bench"].removeprefix("Nifty ")     # the same index; this site writes "Nifty Smallcap 100"
    assert got["observations"]["adx"] == pytest.approx(pin["adx"], abs=1e-5) and got["observations"]["trendMultiplier"] == pin["mult"]
    binds = pin["capped"] and pin["uncapped"] > 19         # here `stageCapped` means the cap actually lowered the score
    assert got["longTerm"]["stageCapped"] == binds
    if binds:
        assert got["longTerm"]["uncappedScore"] == pytest.approx(pin["uncapped"], abs=1e-6)
    else:
        assert "uncappedScore" not in got["longTerm"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_points_add_up_and_the_trend_alignment_is_the_packages(name):
    """points = weight x signal x 100 / weights in use (the package's `points`); they add up to the score before the stage cap."""
    pin, got = CASES[name], assess(CASES[name]["params"])
    for horizon, mapping, prefix, cap in (("shortTerm", ST_MAP, "ST", False), ("longTerm", LT_MAP, "LT", True)):
        factors = {f["key"]: f for f in got[horizon]["factors"]}
        divisor = sum(f["weight"] for f in factors.values() if f["status"] != "disabled")
        assert divisor == (96 if prefix == "ST" else 92)
        points = {k: f["weight"] * f["signal"] * 100 / divisor for k, f in factors.items() if f["status"] == "available"}
        for ours, theirs in mapping.items():
            assert points[ours] == pytest.approx(pin["points"][f"{prefix} {theirs}"], abs=1e-5), (horizon, ours)
        total = sum(points.values())
        assert total == pytest.approx(pin["uncapped"] if prefix == "LT" else pin["st"], abs=1e-6)
    align = tw.trend_alignment(got["shortTerm"]["score"], got["longTerm"]["score"])
    assert align["label"] == pin["alignment"]
    assert sum(1 for c in align["cells"] if c["current"]) == 1 and len(align["cells"]) == 9
    assert tw.rating_word(got["shortTerm"]["rating"], got["shortTerm"]["score"]) == {"Very strong": "Strongly positive", "Strong": "Positive", "Neutral": "Neutral",
                                                                                      "Weak": "Negative", "Very weak": "Strongly negative"}[pin["stRating"]]


def test_the_nine_alignment_labels_are_the_packages_and_follow_the_band_rule():
    expect = {("positive", "positive"): "Strong on both timeframes", ("positive", "neutral"): "Short-term strength, no long-term trend",
              ("positive", "negative"): "Short-term bounce within a long-term downtrend", ("neutral", "positive"): "Long-term uptrend, short-term pause",
              ("neutral", "neutral"): "No clear trend", ("neutral", "negative"): "Long-term downtrend, short-term flat",
              ("negative", "positive"): "Short-term pullback within a long-term uptrend", ("negative", "neutral"): "Short-term weakness, no long-term trend",
              ("negative", "negative"): "Weak on both timeframes"}
    cells = {(c["st"], c["lt"]): c["label"] for c in tw.ALIGNMENT["cells"]}
    assert cells == expect and len(set(expect.values())) == 9
    assert [tw.trend_band(x) for x in (20, 19.99, -19.99, -20, 0, None, float("nan"))] == ["positive", "neutral", "neutral", "negative", "neutral", None, None]
    assert tw.trend_alignment(None, 30) is None and tw.trend_alignment(30, None) is None
    assert tw.trend_alignment(35.3, 39.3)["label"] == "Strong on both timeframes"
    assert tw.trend_alignment(-30, 25)["code"] == "st_negative_lt_positive"


def test_ema_is_pines_ta_ema():
    """No value until `length` observations, then their average, then recursive. (This engine seeded at the first value before; the package, and the chart, do not.)"""
    assert ema([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]
    assert ema([1, 2, 3, None, 4, 5, 6], 3) == [None, None, 2.0, None, None, None, 5.0]
    line, signal, hist = macd([float(i % 7) + i / 10 for i in range(60)])
    assert line[24] is None and line[25] is not None and signal[32] is None and signal[33] is not None


def row(day, open_, high, low, close, volume):
    return {"quote_date": day.isoformat(), "open_price": open_, "high_price": high, "low_price": low, "close_price": close, "volume": volume}


def test_all_zero_provider_rows_are_not_sessions():
    """FinEdge pads holidays with all-zero rows. One of them used to cut the usable history to the bars after it and withhold both scores."""
    bars = pure_bars(700, 5, 0.0006, 0.012)
    rows = [row(date.fromisoformat(b["date"]), b["open"], b["high"], b["low"], b["close"], b["volume"]) for b in bars]
    rows.insert(650, row(date.fromisoformat(bars[649]["date"]) + timedelta(days=1), 0, 0, 0, 0, 0))     # a Saturday-style padding row
    rows.insert(300, row(date.fromisoformat(bars[299]["date"]) + timedelta(days=1), 0, 0, 0, 0, 0))
    kept = normalise_bars({"price": rows}, ASOF)
    assert len(kept) == 700 and all(b["close"] is not None for b in kept)
    # a zero close beside real prices is still a bad bar (never filled), as before
    rows[10] = row(date.fromisoformat(bars[9]["date"]), 100, 101, 99, 0, 1000)
    assert [b for b in normalise_bars({"price": rows}, ASOF) if b["close"] is None]
    price = resolve_technical_prices({"price": rows[20:]}, "FinEdge", ASOF)
    result = build_technical_assessment(price, ASOF, benchmarks(), None)
    assert result["usableDailyBars"] == 680 and result["shortTerm"]["score"] is not None


def test_nothing_changes_for_the_weights_the_engine_publishes():
    assert [w for *_, w, _ in ST] == [10, 8, 6, 8, 4, 8, 4, 10, 5, 3, 4, 10, 8, 6, 6] and sum(w for *_, w, _ in LT) == 100
