"""Regression cases for the owner's New_code_python_fundamental v3.6.1 (L1-L5)."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from backend import premium_engine
from backend.premium_engine import loss_profile, loss_tier, score_company
from backend.premium_model_config import GROUPS
from backend.premium_presentation import build_report_review
from backend.premium_trace import build_calculation_trace
from backend.premium_pdf import render_premium_pdf


@pytest.fixture
def inputs():
    return json.loads(Path(__file__).with_name("premium_example.json").read_text())


def metric(result, name):
    return next(row for row in result["metrics"] if row["metric"] == name)


def test_shrinking_losses_are_not_good_profit_quarters_but_turnarounds_are(inputs):
    inputs["net_profit_q"] = [-20.] * 8 + [-10.] * 6
    result = score_company(inputs, "MFG")
    assert metric(result, "PROFIT_STREAK")["value"] == 0
    assert metric(result, "PROFIT_STREAK")["points"] == 0
    inputs["net_profit_q"] = [-20.] * 10 + [10.] * 4
    row = metric(score_company(inputs, "MFG"), "PROFIT_STREAK")
    assert row["value"] == 4
    assert row["details"]["magnitudePoints"] == 70


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("latest", [-10., 0.])
def test_nonpositive_recent_and_annual_profit_score_zero_in_every_group(inputs, group, latest):
    inputs["net_profit_q"] = [-20.] * 10 + [latest] * 4
    inputs["net_profit_y"] = [-100., -80., latest]  # fewer than 3 CAGR years
    result = score_company(inputs, group)
    for name in ("PROFIT_GROWTH", "PROFIT_CAGR"):
        row = metric(result, name)
        assert row["points"] == 0
        assert row["status"] == "Z"
        assert row["details"]["latestLoss"]
    assert metric(result, "PROFIT_CAGR")["weight"] > 0


@pytest.mark.parametrize("latest_op", [-5., 0.])
def test_improving_but_nonpositive_margin_scores_zero(inputs, latest_op):
    inputs["sales_q"] = [100.] * 14
    inputs["operating_profit_q"] = [-20.] * 10 + [latest_op] * 4
    row = metric(score_company(inputs, "MFG"), "MARGIN_CHANGE")
    assert row["value"] == pytest.approx(20 + latest_op)
    assert row["points"] == 0 and row["status"] == "Z"
    assert row["details"]["opMarginNow"] == latest_op


def test_positive_margin_and_missing_comparison_keep_original_rules(inputs):
    inputs["sales_q"] = [100.] * 14
    inputs["operating_profit_q"] = [-20.] * 10 + [5.] * 4
    assert metric(score_company(inputs, "MFG"), "MARGIN_CHANGE")["points"] == 100
    inputs["operating_profit_q"][-8] = None
    row = metric(score_company(inputs, "MFG"), "MARGIN_CHANGE")
    assert row["status"] == "F"  # no invented historical margin


def test_short_loss_history_blends_profit_streak_with_zero_only(inputs):
    inputs["sales_q"] = [100., 100., 100., 100., 120., 120.]
    inputs["net_profit_q"] = [-20., -20., -20., -20., -10., 1.]
    result = score_company(inputs, "MFG")
    profit = metric(result, "PROFIT_STREAK")
    # J=2, one good quarter, base=50, turnaround magnitude=70, own=47.
    assert profit["points"] == pytest.approx(9.4)
    assert profit["details"]["fillPoints"] == 0
    assert profit["details"]["credibility"] == .2
    assert metric(result, "SALES_STREAK")["details"]["fillPoints"] == 50
    assert metric(result, "SALES_STREAK")["points"] == 60


def test_loss_without_comparable_quarters_is_known_zero_not_group_fill(inputs):
    inputs["sales_q"] = [100.] * 4
    inputs["net_profit_q"] = [-10.] * 4
    result = score_company(inputs, "MFG")
    row = metric(result, "PROFIT_STREAK")
    assert row["points"] == 0 and row["status"] == "Z"
    assert result["judgedQuarters"] == 0 and result["status"] == "PROVISIONAL"
    trace = build_calculation_trace(inputs, result, {})
    assert "loss rule assigns 0" in next(r for r in trace["metrics"] if r["metric"] == "PROFIT_STREAK")["pointsCalculation"]


def test_single_loss_quarter_does_not_replace_profitable_ttm_with_a_loss(inputs):
    inputs["net_profit_q"] = [2.] * 10 + [5., 5., 5., -1.]
    result = score_company(inputs, "MFG")
    assert result["loss"]["ttmProfit"] == 14
    assert not result["loss"]["lossNow"] and not result["lossCapped"]
    assert metric(result, "PROFIT_GROWTH")["status"] == "A"
    assert metric(result, "PROFIT_STREAK")["value"] == 3


def test_loss_quarters_no_longer_unlock_optional_peg(inputs):
    inputs["net_profit_q"] = [-20.] * 8 + [-10.] * 6
    result = score_company(inputs, "HEAVY")
    assert metric(result, "PROFIT_STREAK")["value"] == 0
    assert metric(result, "PEG")["status"] == "N"


@pytest.mark.parametrize("group,caps", [
    ("LIGHT", (55, 40, 30, 20)), ("MFG", (55, 40, 30, 20)),
    ("UTILITY", (55, 40, 30, 20)), ("HEAVY", (60, 45, 30, 20)),
    ("REALTY", (60, 45, 30, 20)), ("BANK", (50, 35, 25, 15)),
    ("NBFC", (50, 35, 25, 15)), ("INSURANCE", (50, 35, 25, 15)),
])
def test_loss_tier_caps_match_owner_table(group, caps):
    recovering, loss, persistent, chronic = caps
    data = {"sales_q": [100.] * 4, "net_profit_q": [1.] * 4, "net_profit_y": [10., 20., -1.]}
    assert loss_tier(group, loss_profile(data)) == ("recovering", recovering)
    data.update(net_profit_q=[-1.] * 4, net_profit_y=[10., 20., 1.])
    assert loss_tier(group, loss_profile(data)) == ("loss", loss)
    data["net_profit_y"] = [10., -1., -1.]
    assert loss_tier(group, loss_profile(data)) == ("persistent", persistent)
    data["net_profit_y"] = [-1., -1., -1.]
    assert loss_tier(group, loss_profile(data)) == ("chronic", chronic)
    data["net_profit_q"] = [-10.] * 4  # exactly 10% loss margin triggers deep loss
    assert loss_tier(group, loss_profile(data)) == ("chronic + deep", max(10, chronic - 10))
    data["net_profit_q"] = [-9.99] * 4
    assert loss_tier(group, loss_profile(data)) == ("chronic", chronic)


def test_four_of_five_losses_and_profit_recovery_after_two_loss_years():
    data = {"sales_q": [100.] * 4, "net_profit_q": [-1.] * 4, "net_profit_y": [-1., -1., 1., -1., -1.]}
    assert loss_tier("MFG", loss_profile(data)) == ("chronic", 20)
    data.update(net_profit_q=[1.] * 4, net_profit_y=[-1., -1., 1.])
    assert loss_tier("MFG", loss_profile(data)) == ("recovering", 55)


def test_missing_periods_do_not_invent_current_loss_or_chronic_history(inputs):
    inputs.update(net_profit_q=[-10., None, -10., -10.], net_profit_y=[-1., -1., -1.])
    result = score_company(inputs, "MFG")
    assert result["loss"]["ttmProfit"] is None and not result["lossCapped"]
    assert result["loss"]["tier"] is None
    inputs.update(net_profit_q=[-1.] * 4, net_profit_y=[-1., None, -1.])
    assert score_company(inputs, "MFG")["loss"]["tier"] == "persistent"
    inputs.update(net_profit_q=[-1.] * 3, net_profit_y=[10., 20., -1.])
    profile = loss_profile(inputs)
    assert profile["basis"] == "latest year" and profile["ttmProfit"] == -1


def capped_inputs(inputs):
    inputs.update(sales_q=[100.] * 10 + [200.] * 4, sales_y=[100., 120., 150., 180., 220., 300.],
                  net_profit_q=[-2.] * 10 + [-1.] * 4, net_profit_y=[1., 1., 1., -1., 2., -1.],
                  operating_profit_q=[10.] * 10 + [100.] * 4, eps_q=[],
                  price=1., shares=10., industry_median_ev_ebitda=10., industry_median_pb=1.)
    return inputs


def test_loss_cap_precedes_valuation_cap_and_both_reconcile(inputs):
    result = score_company(capped_inputs(inputs), "HEAVY")
    assert result["loss"]["rawFundamental"] == 49
    assert result["parts"]["fundamental"] == 30
    assert result["lossCapped"] and result["valuationCapped"]
    assert result["parts"]["valuation"] == 60
    assert [a["metric"] for a in result["adjustments"]] == ["LOSS_CAP", "WEAK_BUSINESS_CAP"]
    assert result["capPointsLost"] == pytest.approx(sum(a["pointsLost"] for a in result["adjustments"]))
    assert sum(r["pointsEarned"] for r in result["metrics"]) - result["capPointsLost"] == pytest.approx(result["final"])
    assert sum(r["pointsLost"] for r in result["metrics"]) + result["capPointsLost"] == pytest.approx(100 - result["final"])
    assert result["modelVersion"] == "3.6.9" and result["baselineVersion"] == "3.6.1-simple"
    trace = build_calculation_trace(inputs, result, {})
    assert "Loss cap (persistent)" in trace["parts"][0]["calculation"]
    json.dumps(result, allow_nan=False)


def test_caps_never_raise_a_lower_score_and_toggle_restores_old_rules(inputs, monkeypatch):
    data = capped_inputs(inputs)
    data.update(sales_q=[200.] * 10 + [100.] * 4, sales_y=[300., 220., 180., 150., 120., 100.],
                operating_profit_q=[100.] * 10 + [1.] * 4)
    result = score_company(data, "HEAVY")
    assert result["parts"]["fundamental"] < result["loss"]["cap"]
    assert not result["lossCapped"]
    monkeypatch.setattr(premium_engine, "LOSS_ADJUSTED_FUNDAMENTAL", False)
    result = score_company(data, "HEAVY")
    assert not result["lossCapped"]
    assert metric(result, "PROFIT_STREAK")["value"] > 0
    assert metric(result, "PROFIT_CAGR")["points"] == 0  # bigger loss from positive start
    assert metric(result, "PROFIT_GROWTH")["points"] == 30  # shrinking current loss


def test_report_and_pdf_explain_losses_without_weights_or_new_appendices(inputs):
    data = capped_inputs(inputs)
    rating = score_company(data, "HEAVY")
    report = {"id": "c" * 32, "state": "ready", "company": {"symbol": "LOSSCASE", "name": "Loss rules example"},
              "statementType": "consolidated", "createdAt": "2026-10-24T12:00:00+00:00", "rating": rating,
              "inputs": data, "inputMeta": {}, "trends": [], "warnings": []}
    before = deepcopy(report)
    review = build_report_review(report)
    assert report == before
    fundamental = review["parts"][0]
    assert "limited to 30/100" in fundamental["notes"][0]
    growth = next(r for r in fundamental["cons"] if r["metric"] == "PROFIT_GROWTH")
    assert "zero or negative" in growth["summary"]
    assert growth["valueText"] == "Zero or negative profit"
    report["review"] = review
    report["calculationTrace"] = build_calculation_trace(data, rating, {})
    pdf = PdfReader(BytesIO(render_premium_pdf(report)))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) == 7
    assert "Fundamental score is limited to 30/100" in text
    assert "Loss-making quarters do not count" in text
    assert "Weight" not in text and "LOSS_CAP" not in text


def test_operating_loss_commentary_does_not_present_improvement_as_strength(inputs):
    inputs.update(sales_q=[100.] * 14, operating_profit_q=[-20.] * 10 + [-5.] * 4)
    review = build_report_review({"rating": score_company(inputs, "MFG"), "statementType": "consolidated"})
    margin = next(r for r in review["parts"][0]["cons"] if r["metric"] == "MARGIN_CHANGE")
    assert "operating margin is -5.00%" in margin["summary"]
