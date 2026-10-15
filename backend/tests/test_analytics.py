from finlit.analytics import indicators, returns, scoring
from finlit.normalize import events


def test_input_score_thresholds():
    assert scoring.input_score(20, (6, 10, 14, 18)) == 92
    assert scoring.input_score(15, (6, 10, 14, 18)) == 76
    assert scoring.input_score(5, (6, 10, 14, 18)) == 18
    assert scoring.input_score(30, (80, 65, 50, 35), lower_is_better=True) == 92
    assert scoring.input_score(90, (80, 65, 50, 35), lower_is_better=True) == 18
    assert scoring.input_score(None, (1, 2, 3, 4)) is None


def test_bands():
    assert scoring.band(78)["key"] == "strong"
    assert scoring.band(77.9)["key"] == "healthy"
    assert scoring.band(62)["key"] == "healthy"
    assert scoring.band(45)["key"] == "mixed"
    assert scoring.band(44)["key"] == "watch"
    assert scoring.band(None)["key"] == "insufficient"


def test_score_with_partial_inputs():
    result = scoring.score({"roe": 20, "roce": 25})
    quality = next(p for p in result["pillars"] if p["key"] == "quality")
    assert quality["score"] == 92 and round(quality["coverage"], 2) == 0.67
    assert result["overall"] == 92  # only pillars with data count
    assert scoring.score({})["band"]["key"] == "insufficient"


def test_rsi_bounds_and_ema():
    rising = [float(i) for i in range(1, 260)]
    snap = indicators.technical_snapshot(rising)
    assert snap["rsi14"] == 100 or snap["rsi14"] > 95
    assert snap["vsEma200Pct"] > 0 and snap["rsiZone"] == "overbought"
    assert indicators.technical_snapshot([]) == {}


def test_trailing_returns_one_calculation():
    days = [f"2025-{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 15)] + ["2026-01-01"]
    history = {"t": days, "c": [100.0] * (len(days) - 1) + [110.0]}
    actions = events.corporate_actions({"dividend": [{"date": "01-Jul-2025", "amount": 2, "adj_amount": 2, "subject": "Dividend"}]})
    one_year = next(r for r in returns.trailing_returns(history, actions) if r["period"] == "1Y")
    assert one_year["price"] == 10.0 and one_year["dividend"] == 2.0 and one_year["total"] == 12.0
    five_year = next(r for r in returns.trailing_returns(history, actions) if r["period"] == "5Y")
    assert five_year["total"] is None  # no fake numbers without coverage
