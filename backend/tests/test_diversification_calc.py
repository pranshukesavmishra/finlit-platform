"""Diversification card maths against the reference snapshot (addendum acceptance tests). Pure: no database."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from finlit.diversification import calc, sectors

F = Path(__file__).parent / "fixtures" / "diversification"
spec = importlib.util.spec_from_file_location("div_reference", F / "diversification_reference.py")
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)

PRICES = json.loads((F / "sample_prices.json").read_text())
PRICES_MAX = json.loads((F / "sample_prices_max.json").read_text())
PRISM = json.loads((F / "sample_prism.json").read_text())
EXPECTED = json.loads((F / "expected_output.json").read_text())
SAMPLE = ref.SAMPLE
SIZES = {s: "Large" for s in SAMPLE}
WEEK = "2026-W45"          # the unfinished week when the snapshot was taken


def weekly(symbols=SAMPLE, prices=PRICES, week=WEEK):
    return calc.weekly_view(prices, symbols, ref.SAMPLE_SECTORS, ref.SAMPLE_MCAP_CR, ref.SAMPLE_GROUPS, SIZES, week)


@pytest.fixture(scope="module")
def full():
    return weekly()


def test_sample_list_reproduces_the_addendum(full):
    assert full["score"] == EXPECTED["score"] and full["score"]["value"] == 72 and full["score"]["band"] == "Fairly spread"
    assert full["headline"] == EXPECTED["headline"]
    assert full["asOf"]["fromWeek"] == "2023-W45" and full["asOf"]["toWeek"] == "2026-W44" and full["asOf"]["weeks"] == 156
    assert full["asOf"]["label"] == "Nov 2023 – Oct 2026"
    assert full["clusters"] == EXPECTED["clusters"]
    assert full["overlap"] == EXPECTED["overlap"] and full["overlap"][-1] == {"symbol": "ITC", "avgCorrelation": 0.18}
    assert full["market"]["stocks"] == EXPECTED["market"]["stocks"]
    assert full["stress"]["stocks"] == EXPECTED["stress"]["stocks"]
    assert full["stress"]["benchmarkAvgPct"] == -3.41 and full["stress"]["equalAvgPct"] == -3.21
    assert full["market"]["betaEqual"] == 0.96
    assert full["spread"]["sectors"] == EXPECTED["spread"]["sectors"] and full["spread"]["groups"] == EXPECTED["spread"]["groups"]
    assert full["spread"]["size"] == {"Large": 15, "Mid": 0, "Small": 0}
    b = full["basket"]
    assert (b["equal"]["volPct"], b["equal"]["maxDrawdownPct"]) == (12.0, -15.1)
    assert (b["mcap"]["volPct"], b["mcap"]["maxDrawdownPct"]) == (12.1, -17.1)
    assert (b["benchmark"]["volPct"], b["benchmark"]["maxDrawdownPct"]) == (12.6, -15.5)
    eq = {d["name"]: d["pct"] for d in full["riskShare"]["equal"]["sectors"]}
    assert eq["Financial services"] == 39.5 and eq["Information technology"] == 23.7
    st = {d["symbol"]: d for d in full["riskShare"]["equal"]["stocks"]}
    assert st["HCLTECH"]["pct"] == 8.2 and st["ITC"]["pct"] == 3.8
    mc = {d["symbol"]: d for d in full["riskShare"]["mcap"]["stocks"]}
    assert mc["RELIANCE"]["pct"] == 19.1 and mc["RELIANCE"]["weightPct"] == 16.2 and mc["BHARTIARTL"]["pct"] == 11.3


def test_everything_matches_the_reference_output_within_tolerance(full):
    ref_out = ref.diversification(PRICES, SAMPLE, ref.SAMPLE_SECTORS, ref.SAMPLE_MCAP_CR, ref.SAMPLE_GROUPS, WEEK)
    assert abs(full["headline"]["effectiveStocks"] - ref_out["headline"]["effectiveStocks"]) <= 0.01
    for a, b in zip(full["market"]["stocks"], ref_out["market"]["stocks"]):
        assert a["symbol"] == b["symbol"] and abs(a["beta"] - b["beta"]) <= 0.01
    for a, b in zip(full["overlap"], ref_out["overlap"]):
        assert abs(a["avgCorrelation"] - b["avgCorrelation"]) <= 0.01
    assert abs(full["basket"]["equal"]["volPct"] - ref_out["basket"]["equal"]["volPct"]) <= 0.1


@pytest.mark.parametrize("name,syms,expected", [
    ("one per sector", ["RELIANCE", "HDFCBANK", "TCS", "ITC", "LT", "BHARTIARTL", "TATASTEEL", "SUNPHARMA"], 78),
    ("banks + IT", ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "TCS", "INFY", "HCLTECH"], 45),
    ("banks + Bajaj", ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE"], 28),
    ("three IT", ["TCS", "INFY", "HCLTECH"], 7),
])
def test_the_five_score_examples(name, syms, expected):
    assert weekly(syms)["score"]["value"] == expected


def test_score_examples_bands():
    assert weekly(["TCS", "INFY", "HCLTECH"])["score"]["band"] == "Concentrated"
    assert weekly(["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "TCS", "INFY", "HCLTECH"])["score"]["band"] == "Somewhat concentrated"


def test_headline_identity_and_all_ones():
    assert abs(calc.effective_stocks(np.eye(7), 10 ** 9) - 7) < 1e-9
    assert abs(calc.effective_stocks(np.ones((7, 7)), 10 ** 9) - 1) < 1e-9


def test_correlation_matrix_symmetric_unit_diagonal_in_range():
    r = calc.weekly_frame(PRICES, SAMPLE, WEEK)[SAMPLE].dropna()
    c = r.corr().values
    assert np.allclose(c, c.T) and np.allclose(np.diag(c), 1.0) and c.min() >= -1 and c.max() <= 1


def test_risk_shares_sum_to_100(full):
    assert abs(sum(d["pct"] for d in full["riskShare"]["equal"]["stocks"]) - 100) <= 0.05 * 15 + 1e-9
    assert abs(sum(d["pct"] for d in full["riskShare"]["equal"]["sectors"]) - 100) <= 0.5
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    assert abs(calc.risk_share(np.array([0.5, 0.5]), cov).sum() - 1) < 1e-12


def test_basket_beta_is_the_mean_of_stock_betas(full):
    assert abs(full["market"]["betaEqual"] - np.mean([d["beta"] for d in full["market"]["stocks"]])) < 0.01


def test_score_parts_at_the_caps_and_at_one():
    top = calc.diversification_score(15, 8)
    assert top["coMovement"] == 100 and top["sectorSpread"] == 100 and top["value"] == 100 and top["band"] == "Widely spread"
    bottom = calc.diversification_score(1, 1)
    assert bottom["coMovement"] == 0 and bottom["sectorSpread"] == 0 and bottom["value"] == 0 and bottom["band"] == "Concentrated"
    assert calc.diversification_score(40, 20)["value"] == 100            # past the caps still 100


def test_band_edges_come_from_the_rounded_score():
    assert calc.round_half_up(79.5) == 80 and calc.band_for(80) == "Widely spread" and calc.band_for(79) == "Fairly spread"
    # co-movement 100, sector spread 48.75 -> raw 79.5 exactly
    s_eff = float(np.exp(0.4875 * np.log(8)))
    out = calc.diversification_score(15, s_eff)
    assert out["unrounded"] == 79.5 and out["value"] == 80 and out["band"] == "Widely spread"
    assert [calc.band_for(v) for v in (0, 39, 40, 59, 60, 79, 80, 100)] == ["Concentrated", "Concentrated", "Somewhat concentrated", "Somewhat concentrated",
                                                                               "Fairly spread", "Fairly spread", "Widely spread", "Widely spread"]


def test_fewer_than_three_eligible_stocks_gives_spread_only_and_no_score():
    out = weekly(["TCS", "INFY"])
    assert "score" not in out and "headline" not in out and "clusters" not in out
    assert out["included"] == 2 and out["spread"]["sectors"] == [{"name": "Information technology", "count": 2}]


def test_short_history_stock_is_excluded_but_stays_in_spread():
    prices = {**PRICES, "NEWCO": {"t": PRICES["TCS"]["t"][-31:], "c": PRICES["TCS"]["c"][-31:]}}
    sectors_ = {**ref.SAMPLE_SECTORS, "NEWCO": "Healthcare"}
    out = calc.weekly_view(prices, SAMPLE + ["NEWCO"], sectors_, {**ref.SAMPLE_MCAP_CR, "NEWCO": 5000.0}, ref.SAMPLE_GROUPS, SIZES, WEEK)
    assert out["excluded"] == [{"symbol": "NEWCO", "reason": "history", "weeks": 29}]
    assert out["included"] == 15 and "NEWCO" not in {c for cl in out["clusters"] for c in cl["symbols"]}
    assert "NEWCO" not in [o["symbol"] for o in out["overlap"]] and "NEWCO" not in [m["symbol"] for m in out["market"]["stocks"]]
    assert {"name": "Healthcare", "count": 2} in out["spread"]["sectors"]                  # still counted by count
    assert out["score"]["value"] == 72                                                     # the score is on the eligible stocks only


def test_unfinished_week_never_enters_the_sample():
    assert weekly()["asOf"]["toWeek"] == "2026-W44"
    earlier = weekly(week="2026-W44")                       # pretend W44 is the unfinished one
    assert earlier["asOf"]["toWeek"] == "2026-W43" and earlier["asOf"]["weeks"] == 155
    frame = calc.weekly_frame(PRICES, SAMPLE, "2026-W44")
    assert frame.index.max() == "2026-W43" and "2026-W44" not in frame.index


def test_monthly_horizon():
    v = calc.horizon_view(PRICES_MAX, SAMPLE, "monthly", "2026-11")
    assert v["headline"]["avgCorrelation"] == 0.28 and v["headline"]["effectiveStocks"] == 6.4
    assert v["market"]["betaEqual"] == 0.91 and v["market"]["benchmarkReturns"] == 59
    assert [(c["symbols"], c["avgCorrelation"]) for c in v["clusters"]] == [(["TCS", "INFY", "HCLTECH"], 0.77), (["ICICIBANK", "SBIN", "AXISBANK"], 0.58), (["LT", "TATASTEEL"], 0.56)]
    assert "score" not in v


def test_yearly_horizon_is_indicative_with_no_clusters_or_score():
    v = calc.horizon_view(PRICES_MAX, SAMPLE, "yearly", "2026-11")
    assert v["headline"]["avgCorrelation"] == 0.49 and v["headline"]["effectiveStocks"] == 4.09
    assert v["asOf"]["effectiveObservations"] == 6.8 and v["indicative"] is True
    assert "clusters" not in v and "score" not in v and len(v["mostRelated"]) == 3 and len(v["leastRelated"]) == 3


def test_unfinished_month_is_dropped():
    v = calc.horizon_view(PRICES_MAX, SAMPLE, "monthly", "2026-10")
    assert v["asOf"]["toMonth"] == "2026-09"


def test_style_tilt_percentiles_and_leans():
    uni = [dict(zip(PRISM["cols"], r)) for r in PRISM["rows"]]
    t = calc.style_tilt(uni, SAMPLE)
    assert t["universe"] == 650 and t["notRated"] == []
    got = [(p["part"], p["avgPercentile"], p["lean"]) for p in t["parts"]]
    assert got == [("Growth & Profitability", 53, "typical"), ("Valuation", 61, "typical"), ("Quality", 65, "high"), ("Risk", 82, "high"),
                   ("Short-term technical view", 72, "high"), ("Long-term technical view", 48, "typical")]
    assert t["parts"][3]["wording"] == "lower-risk companies" and t["parts"][0]["wording"] is None
    assert calc.tilt_sentence(t["parts"]) == ("This list leans towards lower-risk and higher-quality companies, and stocks in short-term uptrends. "
                                              "Growth & profitability, valuation and the long-term trend are close to typical.")


def test_style_tilt_lists_unrated_stocks_and_still_counts_them_elsewhere():
    uni = [dict(zip(PRISM["cols"], r)) for r in PRISM["rows"]]
    t = calc.style_tilt(uni, SAMPLE + ["NOTRATED"])
    assert t["notRated"] == ["NOTRATED"]
    out = calc.weekly_view(PRICES, SAMPLE, ref.SAMPLE_SECTORS, ref.SAMPLE_MCAP_CR, ref.SAMPLE_GROUPS, SIZES, WEEK)
    assert out["included"] == 15
    none = calc.style_tilt(uni, ["NOTRATED"])
    assert all(p["avgPercentile"] is None for p in none["parts"])


def test_last_year_against_three_years(full):
    rl = full["recentVsLongRun"]
    assert rl["recent"]["weeks"] == 52 and rl["recent"]["effectiveStocks"] == 6.78 and rl["longRun"]["effectiveStocks"] == 6.99
    assert rl["longRun"]["weeks"] == 156 and rl["recent"]["avgCorrelation"] == 0.25 and rl["longRun"]["avgCorrelation"] == 0.26
    assert rl["largestRises"][0]["pair"] == ["KOTAKBANK", "LT"] and rl["largestRises"][0]["change"] == 0.24
    assert rl["largestFalls"][0]["pair"] == ["SBIN", "SUNPHARMA"] and rl["flagged"] == []


def test_pair_flag_rule():
    assert calc.pair_flag(0.60, 0.20) is True and calc.pair_flag(0.45, 0.20) is False
    assert calc.pair_flag(0.20, 0.60) is True                 # the reverse: "less than before"
    assert calc.pair_flag(0.10, 0.45) is False                # moved 0.35 but neither value reaches 0.50
    assert calc.pair_flag(0.50, 0.20) is True                 # exactly 0.30 and 0.50 count


def test_size_bands_by_rank():
    assert [calc.size_band(r) for r in (1, 100, 101, 250, 251, 900, None)] == ["Large", "Large", "Mid", "Mid", "Small", "Small", None]


def test_unclassified_label_gets_its_own_named_bucket():
    out = calc.spread_by_count(["A", "B", "C"], {"A": "Healthcare"}, {}, {})
    assert {"name": "Not classified", "count": 2} in out["sectors"] and out["unclassified"] == ["B", "C"]


def test_macro_sector_mapping():
    assert sectors.macro_sector("Banks", "HDFCBANK") == "Financial services"
    assert sectors.macro_sector("Oil Gas & Consumable Fuels") == "Oil & gas"
    assert sectors.macro_sector("Construction Materials") == "Cement & building materials"
    assert sectors.macro_sector("Telecommunication") == "Telecom" and sectors.macro_sector("Fast Moving Consumer Goods") == "FMCG"
    assert sectors.macro_sector("Services") == sectors.UNMAPPED and sectors.macro_sector("zzz made up") == sectors.UNMAPPED and sectors.macro_sector(None) == sectors.UNMAPPED
    assert sectors.macro_sector("anything", "LT") == "Construction"
    assert sectors.business_group("TCS") == "Tata" and sectors.business_group("TATASTEEL") == "Tata" and sectors.business_group("INFY") is None
