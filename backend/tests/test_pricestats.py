import math

from finlit.analytics import pricestats as ps


def test_monthly_returns_use_month_end_closes():
    dates = ["2024-01-15", "2024-01-31", "2024-02-15", "2024-02-29", "2024-03-29"]
    closes = [100, 110, 115, 121, 108.9]
    m = ps.monthly_returns(dates, closes)["rows"]["2024"]
    assert m[0] == 10.0           # first month: from the first close on file
    assert m[1] == 10.0           # 110 -> 121
    assert m[2] == -10.0          # 121 -> 108.9
    assert m[3] is None


def test_drawdown_depth_and_date():
    dates = [f"2024-01-{d:02d}" for d in range(1, 11)]
    closes = [100, 120, 90, 95, 130, 100, 100, 100, 100, 104]
    d = ps.drawdown(dates, closes)
    assert d["max"]["pct"] == -25.0 and d["max"]["date"] == "2024-01-03"
    assert d["current"] == -20.0  # 104 against the 130 peak


def test_drawdown_sampling_keeps_the_trough():
    dates = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(2000 // 4)]
    closes = [100.0] * len(dates)
    closes[137] = 50.0
    d = ps.drawdown(dates, closes, max_points=40)
    assert min(d["dd"]) == -50.0 and len(d["t"]) <= 60


def test_volatility_of_constant_growth_is_zero_and_noise_is_not():
    dates = [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(120)]
    flat = [100 * 1.001 ** i for i in range(120)]
    v = ps.rolling_volatility(dates, flat)
    assert v["current"] is not None and v["current"] < 0.01
    noisy = [100 + (5 if i % 2 else -5) for i in range(120)]
    assert ps.rolling_volatility(dates, noisy)["current"] > 50


def test_histogram_counts_every_move_once_and_clips_extremes():
    closes = [100, 101, 100, 120, 119]  # +1, -0.99, +20, -0.83
    h = ps.histogram(closes)
    assert sum(h["counts"]) == h["days"] == 4 and h["clipped"] == 1
    assert h["counts"][-1] == 1 and h["best"] == 20.0 and h["upShare"] == 50.0


def test_yearly_box_quartiles_and_outliers():
    dates = [f"2023-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(100)]
    closes = [100.0]
    for i in range(1, 100):
        closes.append(closes[-1] * (1.01 if i % 2 else 0.99))
    closes[50] *= 1.3
    box = ps.yearly_box(dates, closes)["years"][0]
    assert box["year"] == 2023 and box["q1"] <= box["median"] <= box["q3"] and box["low"] <= box["q1"] and box["q3"] <= box["high"]
    assert box["outliers"]


def test_build_needs_enough_history_and_summarises(reliance_bundle):
    from finlit.normalize import market
    assert ps.build({"t": ["2024-01-01"], "c": [1.0]}) == {"available": False}
    s = ps.build(market.price_history(reliance_bundle["daily_quotes"]))
    assert s["available"] and s["sessions"] > 400 and s["monthly"]["years"] and s["histogram"]["days"] > 400
    assert s["drawdown"]["max"]["pct"] < 0 and not math.isnan(s["volatility"]["current"])
