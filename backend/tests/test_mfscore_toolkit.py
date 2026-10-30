"""FinLit Mutual Fund Health Score, part 1: the toolkit (spec Section 4), the zero rules of Appendix Z that live there, group mapping, tracking families,
risk-o-meter wording, the exit-load step table and the month-end history figures. Every expected number is worked by hand in the test."""

import math
from datetime import date

import pytest

from finlit.mfscore import exitload, history
from finlit.mfscore.groups import group_of, risk_level, tracking_key
from finlit.mfscore.toolkit import MedianBook, is_missing, median, pillar, pillar_all_n, safe_ratio, scale

from mfscore_synth import month_ends, series


# ------------------------------------------------------------------------------------------------------------ is_missing: zero is a value, a null is a gap

def test_is_missing_only_for_none_and_nan_never_for_zero():
    assert is_missing(None) and is_missing(float("nan")) and is_missing(math.nan)
    for real in (0, 0.0, -0.0, 1, -3.5, False):
        assert not is_missing(real), real          # a real zero must never be taken for a gap
    assert not is_missing("x")                      # not a number: not a NaN either


# ------------------------------------------------------------------------------------------------------------ scale, safe_ratio, pillar (spec examples)

def test_scale_matches_the_specs_examples():
    assert scale(2.2, -4, 4) == pytest.approx(77.5)             # 5-year return 2.2 points above the median
    assert scale(0.94, 1.35, 0.75) == pytest.approx(68.33, abs=0.01)   # volatility 0.94 times the median ("68")
    assert scale(0.62, 1.4, 0.3) == pytest.approx(70.9, abs=0.05)      # expense ratio 0.62%, Direct equity limits
    assert scale(3, 5, 5) == 50                                  # limits collapsed: no spread, neutral 50
    assert scale(99, 5, 5) == 50 and scale(0, 5, 5) == 50


def test_scale_clips_handles_reversed_limits_and_gaps():
    assert scale(100, 0, 10) == 100 and scale(-5, 0, 10) == 0
    assert scale(1.35, 1.35, 0.75) == 0 and scale(0.75, 1.35, 0.75) == 100     # smaller is better when worst > best
    assert scale(0, 0, 10) == 0 and scale(10, 0, 10) == 100
    assert scale(None, 0, 10) is None and scale(float("nan"), 0, 10) is None   # the caller assigns state F
    assert scale(0, -3, 3) == 50                                                # a real zero is scored (Kind A)


def test_safe_ratio_never_divides_by_zero():
    assert safe_ratio(0.15, 0, 0.2) == pytest.approx(0.75)
    assert safe_ratio(0.2, 0, 0.05) == pytest.approx(4.0)
    assert safe_ratio(0.0, 0.0, 0.1) == 0.0                     # a fund value of 0 over a floored zero: ratio 0 (best)
    assert safe_ratio(2.0, 4.0, 1.0) == 0.5 and safe_ratio(2.0, 0.5, 1.0) == 2.0


def test_pillar_weighted_mean_drops_n_and_redivides():
    assert pillar([80, 40], [3, 1]) == pytest.approx(70.0)
    assert pillar([80, None, 40], [3, 100, 1]) == pytest.approx(70.0)     # state N: weight leaves the sum
    assert pillar([None, None], [3, 1]) == 50.0 and pillar_all_n([None, None])
    assert pillar([0, 0], [1, 1]) == 0.0 and not pillar_all_n([0, 0])    # zeros are points, not N
    assert pillar([], []) == 50.0


def test_median_and_medianbook_leave_the_fund_itself_out():
    assert median([3, 1, 2]) == 2 and median([1, 2, 3, 4]) == 2.5 and median([]) is None and median([None, 5]) == 5
    b = MedianBook([("a", 1.0), ("b", 2.0), ("c", 3.0), ("d", 10.0), ("e", None)])
    assert len(b) == 4
    assert b.median() == (2.5, 4)
    assert b.median("a") == (3.0, 3)         # without 1.0: 2, 3, 10
    assert b.median("d") == (2.0, 3)         # without 10.0: 1, 2, 3
    assert b.median("zz") == (2.5, 4)        # a key that is not in the book changes nothing
    assert b.median("e") == (2.5, 4)         # a None value was never in
    assert MedianBook([("a", 1.0)]).median("a") == (None, 0)
    dup = MedianBook([("a", 5.0), ("b", 5.0), ("c", 1.0), ("d", 9.0)])
    assert dup.median("a") == (5.0, 3) and dup.median("c") == (5.0, 3) and dup.median("d") == (5.0, 3)


# ------------------------------------------------------------------------------------------------------------ Appendix Z.2 test cases that are pure arithmetic

def test_z2_case_1_collapsed_limits():
    assert scale(3, 5, 5) == 50


def test_z2_case_2_liquid_fund_with_a_zero_peer_median():
    ratio = safe_ratio(0.15, 0, 0.2)                    # denominator 0.2
    assert ratio == pytest.approx(0.75)
    assert scale(ratio, 1.6, 0.6) == pytest.approx(85.0)


def test_z2_case_4_peer_ter_median_zero_after_exclusions():
    ratio = safe_ratio(0.20, 0, 0.05)
    assert ratio == pytest.approx(4.0)                  # 0.20 / 0.05
    assert scale(ratio, 1.5, 0.6) == 0.0                # 0 points


def test_z2_case_9_all_metrics_of_a_pillar_are_n():
    assert pillar([None, None, None], [50, 30, 20]) == 50.0 and pillar_all_n([None, None, None], [50, 30, 20])


# ------------------------------------------------------------------------------------------------------------ groups

@pytest.mark.parametrize("tab,sub,group,typ", [
    ("equity", "large-cap", "EQ-LARGE", "Equity"), ("equity", "mid-cap", "EQ-MID", "Equity"), ("equity", "small-cap", "EQ-SMALL", "Equity"),
    ("equity", "sectoral-thematic", "EQ-THEME", "Equity"), ("equity", "flexi-cap", "EQ-BROAD", "Equity"), ("equity", "multi-cap", "EQ-BROAD", "Equity"),
    ("equity", "large-mid-cap", "EQ-BROAD", "Equity"), ("equity", "value", "EQ-BROAD", "Equity"), ("equity", "contra", "EQ-BROAD", "Equity"), ("equity", "focused", "EQ-BROAD", "Equity"),
    ("equity", "dividend-yield", "EQ-BROAD", "Equity"), ("equity", "elss", "EQ-BROAD", "Equity"), ("equity", "equity-other", "EQ-BROAD", "Equity"),
    ("debt", "overnight", "DB-CASH", "Debt"), ("debt", "liquid", "DB-CASH", "Debt"), ("debt", "money-market", "DB-CASH", "Debt"), ("debt", "ultra-short", "DB-CASH", "Debt"),
    ("debt", "low-duration", "DB-CASH", "Debt"), ("debt", "short-duration", "DB-ACCRUAL", "Debt"), ("debt", "banking-psu", "DB-ACCRUAL", "Debt"),
    ("debt", "corporate-bond", "DB-ACCRUAL", "Debt"), ("debt", "floater", "DB-ACCRUAL", "Debt"), ("debt", "debt-other", "DB-ACCRUAL", "Debt"),
    ("debt", "medium-duration", "DB-DURATION", "Debt"), ("debt", "medium-long-duration", "DB-DURATION", "Debt"), ("debt", "long-duration", "DB-DURATION", "Debt"),
    ("debt", "dynamic-bond", "DB-DURATION", "Debt"), ("debt", "gilt", "DB-DURATION", "Debt"), ("debt", "gilt-10y", "DB-DURATION", "Debt"), ("debt", "credit-risk", "DB-CREDIT", "Debt"),
    ("hybrid", "arbitrage", "HY-ARB", "Hybrid"), ("hybrid", "conservative-hybrid", "HY-CONS", "Hybrid"), ("hybrid", "equity-savings", "HY-CONS", "Hybrid"),
    ("hybrid", "aggressive-hybrid", "HY-AGGR", "Hybrid"), ("hybrid", "balanced-hybrid", "HY-AGGR", "Hybrid"), ("hybrid", "hybrid-other", "HY-AGGR", "Hybrid"),
    ("hybrid", "balanced-advantage", "HY-DYN", "Hybrid"), ("hybrid", "multi-asset", "HY-DYN", "Hybrid"),
    ("solution", "retirement", "SOL", "Solution Oriented"), ("solution", "childrens", "SOL", "Solution Oriented"),
    ("other", "index-funds", "OT-PASSIVE", "Others"), ("other", "gold-etf", "OT-PASSIVE", "Others"), ("other", "silver-etf", "OT-PASSIVE", "Others"), ("other", "etf", "OT-PASSIVE", "Others"),
    ("other", "etf-debt", "OT-PASSIVE", "Others"), ("other", "fof-overseas", "OT-OTHER", "Others"), ("other", "fof-domestic", "OT-OTHER", "Others"), ("other", "other", "OT-OTHER", "Others"),
])
def test_every_sub_category_lands_in_the_specs_group(tab, sub, group, typ):
    assert group_of(tab, sub) == (typ, group)


def test_the_real_category_rules_feed_the_group_table():
    """AMFI's own category names (both spellings) through finlit.mf.classify, then the group table."""
    from finlit import mf
    cases = {"Equity Scheme - Large Cap Fund": "EQ-LARGE", "Equity Schemes - Mid Cap Fund": "EQ-MID", "Equity Scheme - Small Cap Fund": "EQ-SMALL",
             "Equity Scheme - Sectoral/Thematic": "EQ-THEME", "Equity Scheme - ELSS": "EQ-BROAD", "Equity Scheme - Large & Mid Cap Fund": "EQ-BROAD",
             "Debt Scheme - Liquid Fund": "DB-CASH", "Debt Scheme - Overnight Fund": "DB-CASH", "Debt Scheme - Corporate Bond Fund": "DB-ACCRUAL",
             "Debt Scheme - Gilt Fund with 10 year constant duration": "DB-DURATION", "Debt Scheme - Credit Risk Fund": "DB-CREDIT",
             "Hybrid Scheme - Arbitrage Fund": "HY-ARB", "Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage": "HY-DYN",
             "Hybrid Scheme - Aggressive Hybrid Fund": "HY-AGGR", "Solution Oriented Scheme - Retirement Fund": "SOL", "Other Scheme - Index Funds": "OT-PASSIVE",
             "Other Scheme - Gold ETF": "OT-PASSIVE", "Other Scheme - FoF Overseas": "OT-OTHER", "Other Scheme - FoF Domestic": "OT-OTHER"}
    for category, want in cases.items():
        tab, sub, _ = mf.classify(category)
        assert group_of(tab, sub)[1] == want, (category, tab, sub)


def test_tracking_family_key_agrees_across_benchmark_and_name_spellings():
    nifty = {tracking_key("NIFTY 50 TRI"), tracking_key("Nifty 50 Index"), tracking_key("Nifty 50 Total Return Index"), tracking_key("nifty-50"),
             tracking_key(None, "HDFC Nifty 50 Index Fund - Direct Plan - Growth Option", "HDFC Mutual Fund"),
             tracking_key(None, "ICICI Prudential Nifty 50 Index Fund - Regular Plan - IDCW", "ICICI Prudential Mutual Fund"),
             tracking_key("", "SBI Nifty 50 ETF", "SBI Mutual Fund")}
    assert nifty == {"nifty50"}
    assert tracking_key("NIFTY Next 50 TRI") == "niftynext50" != tracking_key("NIFTY 50 TRI")
    assert tracking_key(None, "UTI Gold ETF", "UTI Mutual Fund") == "gold"
    assert tracking_key(None, None) is None and tracking_key("  ", "") is None
    assert tracking_key("Index", None) is None                          # nothing left after the stripped words


@pytest.mark.parametrize("text,level", [("Low", 0), ("low", 0), ("Low to Moderate", 1), ("Low - to - Moderate", 1), ("Moderate", 2), ("Moderately High", 3), ("High", 4), ("Very High", 5),
                                         ("VERY HIGH", 5), ("Very  High Risk", 5), ("Riskometer: High", 4)])
def test_risk_level_wording(text, level):
    assert risk_level(text) == level


def test_risk_level_unreadable_is_none_and_low_is_zero_not_none():
    for bad in (None, "", "  ", "n/a", "Level 3", "Moderately", "Highly"):
        assert risk_level(bad) is None
    assert risk_level("Low") == 0 and risk_level("Low") is not None


# ------------------------------------------------------------------------------------------------------------ exit load step table

@pytest.mark.parametrize("text,points", [
    ("Nil", 100), ("NIL", 100), ("No exit load", 100), ("nil", 100), ("0%", 100), ("Entry Load: Nil Exit Load: Nil", 100),
    ("0.25% for 7 days", 90), ("0.1% if redeemed within 7 days", 90), ("1% if redeemed within 1 week", 90),
    ("0.1% for 15 days", 80), ("0.25% if redeemed within 30 days", 80), ("0.5% within 1 month", 80),
    ("1% if redeemed within 1 year", 60), ("1% for redemption within 12 months from the date of allotment", 60), ("0.50% if redeemed within 90 days; Nil thereafter", 60),
    ("1% within 365 days", 60), ("0.5% if redeemed within 6 months", 60),
    ("2% if redeemed within 1 year", 30), ("1.5% within 180 days", 30), ("2% before 6 months, 1% 6 to 12 months, nil after", 30),
    ("1% for 2 years", 10), ("3% within 3 years; 2% within 4 years", 10), ("1% if redeemed within 366 days", 10),
    ("Up to 10% of units can be redeemed without load within 1 year; 1% for excess", 60),     # the 10% is a free allowance, not a load
    ("Nil for 10% of units; 1% on the rest within 12 months", 60),
    ("0.25% within one week", 90), ("1% within twelve months", 60),
])
def test_exit_load_step_table(text, points):
    assert exitload.parse(text).points == points, exitload.parse(text)


@pytest.mark.parametrize("text", ["", "   ", None, "As per scheme document", "Refer SID", "1.00%", "0.5%", "Applicable", "see website"])
def test_exit_load_unreadable_is_none_so_the_metric_is_filled(text):
    assert exitload.parse(text).points is None                       # a load above 0% with no holding period, or text without any rule: never a guess


def test_exit_load_reads_the_highest_load_and_the_longest_period():
    p = exitload.parse("1% if redeemed within 30 days; 0.5% within 1 year")
    assert (p.load, p.days, p.points) == (1.0, 365, 60)
    p = exitload.parse("0.25% for 7 days")
    assert (p.load, p.days) == (0.25, 7)
    assert exitload.parse("Nil").load == 0.0


# ------------------------------------------------------------------------------------------------------------ history

def alt(n, a=1.0):
    return [a if i % 2 == 0 else -a for i in range(n)]


def hist(rets, start=100.0):
    navs = series(len(rets) + 1, 0, 0, 0, start=start, rets=rets)
    return history.compute(month_ends(len(navs)), navs)


def test_volatility_is_the_sample_standard_deviation_times_root_twelve():
    h = hist(alt(60, 1.0))
    # 36 returns of +-1 with mean 0: sample variance = 36 / 35
    assert h.vol_m == pytest.approx(math.sqrt(36 / 35) * math.sqrt(12), rel=1e-6)
    assert h.window_ok and not h.frozen and h.invalid == 0 and h.k == 36 and h.cred == 1.0
    assert h.neg_months == pytest.approx(50.0) and h.worst_month == pytest.approx(-1.0, abs=1e-6)


def test_frozen_nav_below_001_pp():
    h = hist(alt(60, 0.0011))        # volatility = 0.0011 * 3.51 = 0.0039 pp
    assert h.vol_m == pytest.approx(0.0039, abs=0.0003) and h.vol_m < 0.01
    assert h.frozen and h.break_flag
    assert not hist(alt(60, 0.5)).frozen


def test_z2_case_13_vol_0004_marks_the_nav_frozen_and_raises_the_break_flag():
    h = hist(alt(60, 0.0011))
    assert round(h.vol_m, 3) == 0.004 and h.frozen and h.break_flag


def test_z2_case_10_a_zero_nav_makes_the_return_invalid_and_raises_the_break_flag():
    navs = series(61, 0, 0, 0, rets=alt(60, 1.0))
    navs[45] = 0.0                                                      # NAV of 0 in month t-1 = 45: r_45 and r_46 cannot be worked out
    days = month_ends(61)
    h = history.compute(days, navs)
    assert h.break_flag and h.invalid == 2
    mk = lambda i: history.month_key(days[i])                           # noqa: E731
    assert mk(45) not in h.rets and mk(46) not in h.rets and mk(47) in h.rets
    assert h.window_ok                                                  # 34 of 36 valid: at least 33
    assert len(h.rets) == 34


def test_too_many_invalid_months_break_the_window():
    navs = series(61, 0, 0, 0, rets=alt(60, 1.0))
    for i in (40, 42, 44, 46):                                          # 8 invalid returns
        navs[i] = float("nan")
    h = history.compute(month_ends(61), navs)
    assert h.invalid == 8 and not h.window_ok and h.break_flag and h.vol_m is None


def test_history_rows_of_the_spec():
    for months, row in ((70, "all"), (60, "all"), (59, "three_year"), (36, "three_year"), (35, "window"), (12, "window"), (11, "none"), (1, "none"), (0, "none")):
        assert history.status_row(months) == row
    short = history.compute(month_ends(11), series(11, 1, 1, 3))
    assert short.months == 11 and short.vol_m is None and not short.rets      # under 12 months: nothing is worked out
    young = hist(alt(23, 1.0))                                          # 24 NAVs
    assert young.months == 24 and young.k == 23 and young.cred == pytest.approx(23 / 36) and young.window_ok


def test_worst_12_month_return_and_underwater_share():
    rets = [0.0] * 60
    rets[50] = -20.0                                                    # one 20% fall, 10 months before the end
    rets[30] = 5.0
    h = hist(rets)
    assert h.worst12 == pytest.approx(-20.0, abs=1e-6)
    # month-ends 25..60 (the last 36): the peak is reached at month-end 31 (after the +5%), the fall starts at month-end 51 (rets[50] is the return INTO NAV 51)
    # NAVs below the running peak from index 51 to 60 = 10 month-ends of the last 36
    assert h.underwater == pytest.approx(100 * 10 / 36, abs=1e-6)
    assert hist([0.5] * 60).underwater == 0.0 and hist([0.5] * 60).worst12 == pytest.approx((1.005 ** 12 - 1) * 100)


def test_own_fall_over_the_last_36_months():
    rets = [1.0] * 60
    rets[40] = -10.0
    h = hist(rets)
    peak = 100 * 1.01 ** 40                                              # NAV 40, the month before the fall
    trough = peak * 0.9
    assert h.fall == pytest.approx(-10.0, abs=1e-6) and trough < peak


def test_history_gaps_inside_a_window_are_tolerated_up_to_three():
    days = month_ends(61)
    navs = series(61, 0, 0, 0, rets=alt(60, 1.0))
    keep = [i for i in range(61) if i not in (30, 31)]                    # two months missing from the stored series
    h = history.compute([days[i] for i in keep], [navs[i] for i in keep])
    assert h.months == 61 and h.invalid == 3 and h.window_ok and h.break_flag
