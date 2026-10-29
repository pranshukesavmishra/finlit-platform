"""Owner-spec boundary tests and fail-closed technical-report contracts."""
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import json

import pytest
from pypdf import PdfReader

from backend.premium_technical import (
    ST, LT, build_technical_assessment, combine_verdict, ema, normalise_bars,
    resolve_technical_prices, rsi, score_rating, summarise_signals, weekly_closes,
)
from backend.premium_snapshot import issue, verify
from backend.premium_pdf import render_premium_pdf

ASOF = date(2026, 10, 23)


def candles(count=600):
    days, current = [], ASOF
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return [{"date": day.isoformat(), "open": 99 + i, "high": 102 + i,
             "low": 98 + i, "close": 100 + i, "volume": 1000 + i}
            for i, day in enumerate(reversed(days))]


def benchmarks(bars):
    return {name:{"bars":[{"date":row["date"], "close":100+i*.1+(i%7)*.03} for i,row in enumerate(bars)], "provider":"FinEdge"}
            for name in ("Nifty 500","Nifty 50","Nifty Midcap 100","Nifty Smallcap 100")}


def test_pdf_component_weights_and_explicit_optional_denominators():
    assert len(ST) == 15 and sum(row[2] for row in ST) == 100
    assert len(LT) == 14 and sum(row[2] for row in LT) == 100
    signals = {key: (1, "Known") for key, *_ in ST}
    assert summarise_signals(ST, signals)["score"] == 100
    assert summarise_signals(ST, signals, value_enabled=False)["requiredCount"] == 13
    signals["candles"] = (None, "Missing")
    result = summarise_signals(ST, signals)
    assert result["score"] is None and result["rating"] == "Unavailable"
    assert result["requiredCount"] == 14  # Missing does not disable the factor.


def test_long_term_stage_cap_applies_before_rating_and_verdict():
    signals = {key: (1, "Known") for key, *_ in LT}
    capped = summarise_signals(LT, signals, stage=3)
    assert capped["score"] == 19 and capped["stageCapped"]
    assert capped["rating"] == "Hold"
    assert combine_verdict(100, capped["score"])["label"] == "BUY"
    assert summarise_signals(LT, signals, stage=2)["score"] == 100
    assert summarise_signals(LT, signals)["score"] is None


@pytest.mark.parametrize("score,rating", [(50,"Strong Buy"),(20,"Buy"),(19.99,"Hold"),(-19.99,"Hold"),(-20,"Reduce"),(-50,"Sell"),(-50.01,"Sell"),(None,"Unavailable")])
def test_rating_boundaries(score, rating):
    assert score_rating(score) == rating


@pytest.mark.parametrize("st,lt,label", [
    (20,20,"STRONG BUY"),(20,0,"BUY"),(20,-20,"BOUNCE ONLY, DON'T INVEST"),
    (0,20,"ACCUMULATE ON DIPS"),(0,0,"HOLD"),(0,-20,"REDUCE"),
    (-20,20,"BUY THE DIP, WAIT FOR ST TURN"),(-20,0,"REDUCE"),(-20,-20,"SELL / AVOID"),
    (None,20,"Unavailable"),
])
def test_all_verdict_combinations(st, lt, label):
    assert combine_verdict(st, lt)["label"] == label


def test_no_fabricated_ohlc_no_future_observations_and_invalid_values_retained():
    rows = [{"date":"2026-10-23", "close":100, "volume":0},
            {"date":"2026-10-22", "open":100, "high":90, "low":80, "close":105},
            {"date":"2026-10-21", "close":float("nan")},
            {"date":"2026-10-26", "close":200}]
    result = normalise_bars(rows, ASOF)
    assert len(result) == 3
    assert result[-1]["open"] is result[-1]["high"] is result[-1]["low"] is None
    assert result[-1]["volume"] == 0
    assert result[-2]["high"] is None and result[0]["close"] is None


def test_complete_primary_avoids_secondary_and_close_only_uses_one_secondary_series():
    def forbidden():
        pytest.fail("A complete primary series must not trigger fallback")
    assert resolve_technical_prices(candles(), "FinEdge", ASOF, forbidden)["provider"] == "FinEdge"
    primary = [{"date":row["date"], "close":1} for row in candles()]
    result = resolve_technical_prices(primary, "FinEdge", ASOF, candles)
    assert result["provider"] == "Upstox" and result["bars"][-1]["close"] == 699
    assert result["notes"]
    def failed():
        raise ValueError("secret provider URL must never leak")
    result = resolve_technical_prices(primary, "FinEdge", ASOF, failed)
    assert "secret" not in json.dumps(result)
    assert result["bars"][-1]["high"] is None


def test_indicator_history_has_explicit_warmup_and_gaps_are_not_compressed():
    # Pine's ta.ema: nothing until `length` consecutive observations, then their average, then recursive; a gap restarts the warm-up
    # (the values are the ones finlit_technicals v1.1 gives, which follows the chart).
    assert ema([1,2,3,4], 3) == [None,None,2.0,3.0]
    assert ema([1,2,3,None,4,5,6], 3) == [None,None,2.0,None,None,None,5.0]
    assert rsi(list(range(1,17)))[-1] == 100
    assert rsi([1]*20)[-1] is None


def test_weekly_indicators_exclude_an_unfinished_week_and_retain_invalid_weeks():
    bars = normalise_bars(candles(), ASOF)
    # Pine's weekly [1] excludes the daily bar's week, even on Friday.
    assert weekly_closes(bars, date(2026,10,22))[-1] == 694
    assert weekly_closes(bars, ASOF)[-1] == 694
    bars[-7]["close"] = None
    assert weekly_closes(bars, ASOF)[-1] is None


def test_missing_benchmark_data_blocks_totals_without_discarding_other_factors():
    source = resolve_technical_prices(candles(), "FinEdge", ASOF)
    result = build_technical_assessment(source, ASOF)
    assert result["shortTerm"]["availableCount"] == 12
    assert result["longTerm"]["availableCount"] == 11
    assert result["shortTerm"]["score"] is result["longTerm"]["score"] is None
    assert result["verdict"]["label"] == "Unavailable"
    assert "history is insufficient" in next(row for row in result["shortTerm"]["factors"] if row["key"] == "rs_rating")["detail"]
    json.dumps(result, allow_nan=False)
    stale = build_technical_assessment(source, ASOF + timedelta(days=20))
    # throughDate is the historical cutoff; current-date freshness must still apply.
    assert not stale["fresh"]
    assert stale["shortTerm"]["availableCount"] == 0


def test_snapshot_signature_covers_new_assessment():
    report = {"state":"ready", "technicalAssessment":build_technical_assessment({}, ASOF)}
    secret = "test-secret-at-least-thirty-two-characters"
    snapshot = issue(report, "admin", secret)
    receipt = snapshot.pop("snapshotReceipt")
    assert verify(snapshot, receipt, "admin", secret) == snapshot
    tampered = deepcopy(snapshot)
    tampered["technicalAssessment"]["shortTerm"]["score"] = 100
    with pytest.raises(ValueError):
        verify(tampered, receipt, "admin", secret)


def test_full_model_has_every_enabled_factor_and_totals_match_source_weights():
    bars = candles()
    result = build_technical_assessment(resolve_technical_prices(bars,"FinEdge",ASOF),ASOF,benchmarks(bars),1000)
    assert result["status"] == "ready"
    assert result["shortTerm"]["availableCount"] == 14
    assert result["longTerm"]["availableCount"] == 13
    for key, denominator in (("shortTerm",96),("longTerm",92)):
        # Source ST denominator is 100 minus sector's 4 (value migration stays on).
        part = result[key]
        expected = 100*sum(row["weight"]*row["signal"] for row in part["factors"] if row["status"]=="available")/denominator
        if key=="longTerm" and result["observations"]["stage"] in (3,4):
            expected = min(expected,19)
        assert part["score"] == pytest.approx(expected)
    assert result["verdict"] == combine_verdict(result["shortTerm"]["score"],result["longTerm"]["score"])
    assert all(term not in result for term in ("entry","stop","target","positionSize","backtest"))


def test_short_term_can_be_ready_while_long_term_history_is_incomplete():
    bars = candles(220)
    result = build_technical_assessment(resolve_technical_prices(bars,"FinEdge",ASOF),ASOF,benchmarks(bars),1000)
    assert result["shortTerm"]["score"] is not None
    assert result["longTerm"]["score"] is None
    assert result["verdict"]["label"] == "Unavailable"


def test_percentile_ties_and_market_cap_crossings_do_not_mix_index_returns():
    from backend.technical_series import percentrank,relative_strength
    assert percentrank([1,1,1,1],3)[-1] == 100
    assert percentrank([4,3,2,1],3)[-1] == 0
    bars = [{"date":f"2026-10-{i+1:02}","close":p} for i,p in enumerate((100,108,30))]
    packs = {name:{row["date"]:{"close":close,"ret":ret} for row in bars} for name,close,ret in (("Nifty 500",100,.001),("Nifty 50",200,.002),("Nifty Midcap 100",300,.003),("Nifty Smallcap 100",400,.004))}
    picked,names,*_ = relative_strength(bars,packs,1000)
    assert names == ["Nifty Midcap 100","Nifty 50","Nifty Smallcap 100"]
    assert [row["ret"] for row in picked] == [.003,.002,.004]


def test_sfp_confirmation_invalidation_and_profile_volume_allocation():
    from backend.technical_patterns import swing_patterns,volume_profile,pivot
    bars = [{"open":100,"high":101,"low":99,"close":100,"volume":100} for _ in range(80)]
    bars[60] = {**bars[60],"low":90}
    bars[70] = {"open":95,"high":100,"low":89,"close":95,"volume":100}
    bars[71] = {"open":101,"high":102,"low":100,"close":101,"volume":100}
    bars[72] = {"open":88,"high":90,"low":87,"close":88,"volume":100}
    result = swing_patterns(bars,[100]*len(bars))
    assert result[70]["sfp_s"] == .75
    assert result[71]["sfp_s"] == 1
    assert result[72]["sfp_s"] == 0
    assert pivot([3,2,1,1,2],4,2) is None  # Newer equal low has priority.
    profile = volume_profile([{"low":100,"high":124,"volume":1200}]*2)
    assert profile == {"poc":100.5,"val":100,"vah":117}


def test_pdf_includes_the_same_incomplete_assessment_without_weights():
    # Reuse the minimal public report contract; no environment or provider requests.
    from backend.tests.test_premium_reports import sample_report
    from pathlib import Path
    example = json.loads(Path(__file__).with_name("premium_example.json").read_text())
    report = sample_report(example)
    report["technicalAssessment"] = build_technical_assessment(resolve_technical_prices(candles(), "FinEdge", ASOF), ASOF)
    content = "\n".join(page.extract_text() for page in PdfReader(BytesIO(render_premium_pdf(report))).pages)
    assert "Short & long-term assessment" in content
    assert "Combined verdict: Unavailable" in content
    assert "Relative strength rating" in content
    assert "weight" not in content.lower()
