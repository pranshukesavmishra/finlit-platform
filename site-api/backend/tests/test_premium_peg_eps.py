"""PEG growth (model 3.6.12): EPS growth first, split/bonus adjusted; net profit growth only when there is no usable EPS CAGR."""
import pytest
from backend.premium_engine import score_company, split_adjusted_eps
from backend.premium_model_config import MODEL_VERSION
from backend.premium_trace import build_calculation_trace

PE_INPUTS = {"price": 100.0, "eps_ttm": 10.0}      # P/E = 10


def peg(eps_y, profit_y, group="MFG", **extra):
    data = {"sales_y": profit_y, "net_profit_y": profit_y, "eps_y": eps_y, **PE_INPUTS, **extra}
    rating = score_company(data, group)
    rows = {r["metric"]: r for r in rating["metrics"]}
    return data, rating, rows.get("PEG")


def series(start, rate, n):
    return [start * (1 + rate) ** i for i in range(n)]


def test_model_version_is_3_6_12():
    assert MODEL_VERSION == "3.6.12"


def test_peg_uses_eps_growth_not_profit_growth():
    # EPS grows 20% a year; total profit grows 50% a year (new shares were issued): the shareholder's growth is the EPS growth.
    _, _, row = peg(series(10, .20, 6), series(100, .50, 6))
    assert row["details"]["growthKind"] == "eps" and row["details"]["growthYears"] == 5
    assert row["details"]["growthUsed"] == pytest.approx(20.0)
    assert row["value"] == pytest.approx(10 / 20.0)                     # P/E 10 / 20% = 0.5
    assert row["points"] == pytest.approx(100.0)                         # PEG 0.5 or less = 100 points


def test_peg_points_are_the_straight_line_2_5_to_0_5():
    _, _, row = peg(series(10, .1905, 6), series(100, .1905, 6))         # growth about 19%: the founder's example (P/E 13.31 / 19 = 0.70)
    assert row["value"] == pytest.approx(10 / 19.05, rel=1e-3)
    assert row["points"] == pytest.approx((row["value"] - 2.5) / (0.5 - 2.5) * 100, rel=1e-6)


def test_growth_is_capped_at_40_percent():
    _, _, row = peg(series(10, .60, 6), series(100, .60, 6))
    assert row["details"]["growthUsed"] == pytest.approx(40.0) and row["details"]["growthRaw"] == pytest.approx(60.0)
    assert row["value"] == pytest.approx(10 / 40.0)


def test_falls_back_to_net_profit_cagr_when_eps_history_is_missing_or_unusable():
    profit = series(100, .25, 6)
    for eps_y in ([], [10.0], [None, None, None, None, None, 10.0], [-1.0, 2.0, 3.0, 4.0, 5.0, 6.0], [0.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
        _, _, row = peg(eps_y, profit)
        assert row["details"]["growthKind"] == "profit_cagr", eps_y
        assert row["details"]["growthUsed"] == pytest.approx(25.0)
        assert "net profit" in row["details"]["growthBasis"]


def test_non_positive_eps_growth_gives_no_peg_and_zero_points_and_does_not_fall_back_to_profit():
    # EPS falls while profit rises: no PEG, and the profit growth is NOT used instead (the EPS growth exists and is negative)
    _, _, row = peg([24.0, 20.0, 16.0, 12.0, 10.0, 8.0], series(100, .30, 6))
    assert row["status"] == "Z" and row["points"] == 0
    assert "non-positive earnings growth" in row["details"]["note"]
    assert row["value"] is None


def test_loss_making_company_has_no_peg():
    _, _, row = peg(series(10, .2, 6), series(100, .2, 6), eps_ttm=-1.0)
    assert row["status"] == "Z" and row["points"] == 0


def test_bonus_issue_does_not_make_eps_growth_look_negative():
    # a 1:1 bonus (shares double) between years 3 and 4: reported EPS halves although profit keeps growing 10% a year
    profit = series(100, .10, 6)
    shares = [10, 10, 10, 20, 20, 20]
    eps_y = [p / s for p, s in zip(profit, shares)]
    assert eps_y[-1] < eps_y[0]                                           # the raw reported numbers would show a decline
    _, _, row = peg(eps_y, profit)
    assert row["status"] != "Z"
    assert row["details"]["growthKind"] == "eps" and row["details"]["growthUsed"] == pytest.approx(10.0, rel=1e-6)
    assert row["details"]["epsSplitAdjustments"] == [{"fromIndex": 2, "ratio": 2.0}]


def test_gradual_dilution_is_not_adjusted():
    profit = series(100, .10, 6)
    shares = series(10, .06, 6)                                           # about 6% more shares a year: really dilutes each holder, not a split
    eps_y = [p / s for p, s in zip(profit, shares)]
    adjusted, applied = split_adjusted_eps(eps_y, profit)
    assert applied == [] and adjusted == pytest.approx(eps_y)
    _, _, row = peg(eps_y, profit)
    assert row["details"]["growthUsed"] == pytest.approx(((eps_y[-1] / eps_y[0]) ** (1 / 5) - 1) * 100)


def test_already_restated_history_is_left_alone():
    profit = series(100, .10, 6)
    eps_y = [p / 20 for p in profit]                                       # the provider restated every year to the new share count: no step
    adjusted, applied = split_adjusted_eps(eps_y, profit)
    assert applied == [] and adjusted == pytest.approx(eps_y)


def test_split_adjustment_helper_cases():
    profit = [100.0, 100.0, 100.0, 100.0]
    # 5:1 split before the last year, and a 2:1 bonus before the one after (newest boundary first)
    shares = [10.0, 10.0, 50.0, 100.0]
    eps_y = [p / s for p, s in zip(profit, shares)]
    adjusted, applied = split_adjusted_eps(eps_y, profit)
    assert [round(a["ratio"], 2) for a in applied] == [2.0, 5.0]
    assert adjusted == pytest.approx([p / 100.0 for p in profit])
    # a reverse split (shares / 10): the older EPS is raised to the new basis
    shares = [100.0, 100.0, 10.0, 10.0]
    adjusted, applied = split_adjusted_eps([p / s for p, s in zip(profit, shares)], profit)
    assert adjusted == pytest.approx([p / 10.0 for p in profit]) and len(applied) == 1
    # a loss year hides the share count: no adjustment is guessed across it
    adjusted, applied = split_adjusted_eps([5.0, None, 2.5], [100.0, -20.0, 100.0])
    assert applied == []


def test_trace_and_review_say_earnings_growth_and_name_the_basis():
    data, rating, row = peg(series(10, .2, 6), series(100, .5, 6))
    trace = next(r for r in build_calculation_trace(data, rating, {})["metrics"] if r["metric"] == "PEG")
    assert "earnings growth" in trace["valueCalculation"] and "EPS growth over 5 years" in trace["valueCalculation"]
