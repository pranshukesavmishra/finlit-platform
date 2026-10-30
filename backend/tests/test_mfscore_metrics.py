"""FinLit Mutual Fund Health Score, part 2: every metric of spec Section 6 with a hand-computed example (each comment shows the arithmetic), the states
A / Z / S / F / N, the zero rules of Appendix Z (Z.2 cases 3 to 13), and the peer-set rules (leave-one-out, widening to S, filling with F)."""

from datetime import date

import pytest

from finlit.mfscore.engine import score_universe
from finlit.mfscore.model import FundIn
from finlit.mfscore.sheets import Metric, SHEETS
from finlit.mfscore.toolkit import scale

from mfscore_synth import END, fund, month_ends, series

RUN = date(2026, 10, 29)


def alt(n, a=1.0, b=None):
    """Alternating month returns +a, -b (b defaults to a)."""
    b = a if b is None else b
    return [a if i % 2 == 0 else -b for i in range(n)]


def peers(n, group="EQ-LARGE", sub="large-cap", plan="Direct", rets=None, **kw):
    """n identical funds: the same monthly returns (so the same peer median every month), the same stored figures."""
    out = []
    for i in range(n):
        f = fund(f"p{i}", group, sub, plan=plan, drift=0.8, vol=2.0, seed=100 + i, **kw)
        if rets is not None:
            f.mnavs = series(61, 0, 0, 0, rets=rets)
        out.append(f)
    return out


def metric(sc, fund_key, mid):
    s = next(x for x in sc if x.key == fund_key)
    return next(r for r in s.metrics if r.id == mid)


def run(target: FundIn, others, **_):
    return score_universe([target] + list(others), RUN, rank=False)


def put(f: FundIn, **kw) -> FundIn:
    for k, v in kw.items():
        setattr(f, k, v)
    return f


# ------------------------------------------------------------------------------------------------------------ 6.1 performance

def test_ret_1y_3y_5y_rel_are_excess_over_the_peer_median():
    others = peers(9, r1y=10.0, r3y=12.0, r5y=14.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r1y=14.0, r3y=13.5, r5y=14.0)
    sc = run(t, others)
    m = metric(sc, "t", "RET_1Y_REL")
    assert (m.state, m.scope, m.peer_n, m.own, m.peer) == ("A", "sub", 9, 14.0, 10.0)
    assert m.value == pytest.approx(4.0) and m.points == pytest.approx(scale(4.0, -6, 6)) == pytest.approx(83.333, abs=0.001)     # (4 + 6) / 12
    m = metric(sc, "t", "RET_3Y_REL")
    assert m.value == pytest.approx(1.5) and m.points == pytest.approx(75.0)          # (1.5 + 3) / 6
    m = metric(sc, "t", "RET_5Y_REL")
    assert m.value == pytest.approx(0.0) and m.points == pytest.approx(50.0)           # a real zero excess is scored


def test_the_fund_is_never_in_its_own_peer_median():
    others = peers(8, r1y=10.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r1y=50.0)                       # an outlier: with itself in the median of 9 it would still be 10; check the count
    m = metric(run(t, others), "t", "RET_1Y_REL")
    assert m.peer_n == 8 and m.peer == 10.0
    # as a peer of a bigger set the same fund is excluded from its own median, included in the others'
    sc = score_universe([t] + others, RUN, rank=False)
    assert metric(sc, "t", "RET_1Y_REL").peer_n == 8 and metric(sc, "p0", "RET_1Y_REL").peer_n == 8


def test_zero_peer_median_of_a_return_is_used_as_it_is():
    others = peers(8, r1y=0.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r1y=2.0)
    m = metric(run(t, others), "t", "RET_1Y_REL")
    assert m.peer == 0.0 and m.value == pytest.approx(2.0) and m.points == pytest.approx(66.667, abs=0.001)    # Kind A: a subtraction cannot divide by zero


def test_too_few_peers_widen_to_the_group_state_s_then_fill_state_f():
    mid = peers(5, "EQ-BROAD", "multi-cap", r1y=10.0)
    flexi = peers(5, "EQ-BROAD", "flexi-cap", r1y=6.0)
    for i, f in enumerate(flexi):
        f.key = f"q{i}"
    t = put(fund("t", "EQ-BROAD", "flexi-cap", seed=5), r1y=8.0)
    sc = run(t, mid + flexi)
    m = metric(sc, "t", "RET_1Y_REL")                      # only 5 flexi peers: widen to the 10 funds of the group; median of {10 x5, 6 x5} = 8
    assert (m.state, m.scope, m.peer_n, m.peer) == ("S", "grp", 10, 8.0) and m.points == pytest.approx(50.0)
    few = run(t, flexi[:3] + mid[:2])                       # 5 funds in the whole group: no peer set of 8 anywhere
    m = metric(few, "t", "RET_1Y_REL")
    assert m.state == "F" and m.why == "no_peers" and m.peer_n < 8


def test_plans_are_scored_against_their_own_plan_only():
    direct = peers(9, plan="Direct", r1y=10.0)
    regular = peers(9, plan="Regular", r1y=2.0)
    for i, f in enumerate(regular):
        f.key = f"r{i}"
    t = put(fund("t", "EQ-LARGE", "large-cap", plan="Regular", seed=5), r1y=3.0)
    m = metric(run(t, direct + regular), "t", "RET_1Y_REL")
    assert m.peer == 2.0 and m.peer_n == 9                 # the Regular peers, not the Direct ones


def test_peers_need_12_months_and_no_nav_break():
    good = peers(8, r1y=10.0)
    young = [fund(f"y{i}", "EQ-LARGE", "large-cap", months=11, seed=300 + i, r1y=99.0) for i in range(5)]
    broken = [put(fund(f"b{i}", "EQ-LARGE", "large-cap", seed=400 + i, r1y=99.0)) for i in range(5)]
    for b in broken:
        b.mnavs = list(b.mnavs)
        b.mnavs[45] = 0.0
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r1y=12.0)
    m = metric(run(t, good + young + broken), "t", "RET_1Y_REL")
    assert m.peer_n == 8 and m.peer == 10.0                # the 99s never entered


def test_ret_abs_uses_5_year_then_3_year_for_equity_and_3_year_then_1_year_for_debt():
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r5y=15.0, r3y=9.0)
    m = metric(run(t, peers(9)), "t", "RET_ABS")
    assert m.state == "A" and m.points == pytest.approx(100.0)                         # (15 - 6) / (15 - 6)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r5y=None, r3y=12.0)
    m = metric(run(t, peers(9)), "t", "RET_ABS")
    assert m.state == "S" and m.why == "r3y" and m.points == pytest.approx(66.667, abs=0.001)    # (12 - 6) / 9
    t = put(fund("t", "DB-ACCRUAL", "short-duration", seed=5), r3y=None, r1y=6.5, r5y=None)
    others = peers(9, "DB-ACCRUAL", "short-duration")
    m = metric(run(t, others), "t", "RET_ABS")
    assert m.state == "S" and m.why == "r1y" and m.points == pytest.approx(50.0)       # debt: (6.5 - 5) / (8 - 5)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r5y=None, r3y=None, r1y=20.0)
    assert metric(run(t, peers(9)), "t", "RET_ABS").state == "F"                          # nothing long enough: filled


def test_ret_abs_is_not_applicable_to_passive_funds():
    t = put(fund("t", "OT-PASSIVE", "index-funds", seed=5, family_key="nifty50"))
    assert metric(run(t, peers(4, "OT-PASSIVE", "index-funds", family_key="nifty50")), "t", "RET_ABS").state == "N"


def test_a_zero_return_is_a_real_value_unless_the_nav_is_frozen():
    others = peers(9, r1y=-2.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r1y=0.0, r3y=0.0, r5y=0.0)
    sc = run(t, others)
    m = metric(sc, "t", "RET_1Y_REL")
    assert m.state == "A" and m.value == pytest.approx(2.0)
    assert metric(sc, "t", "RET_ABS").state == "A" and metric(sc, "t", "RET_ABS").points == 0.0       # 0% a year on limits 6 -> 15
    frozen = put(fund("f", "EQ-LARGE", "large-cap", seed=5, r1y=0.0, r3y=0.0, r5y=0.0))
    frozen.mnavs = series(61, 0, 0, 0, rets=alt(60, 0.0011))
    sc = run(frozen, others)
    assert metric(sc, "f", "RET_1Y_REL").state == "F" and metric(sc, "f", "RET_1Y_REL").why == "frozen_nav"
    assert metric(sc, "f", "RET_ABS").state == "F"


def test_sip_rel_prefers_5_years_and_falls_back_to_3_years_state_s():
    others = peers(9, sip3y=8.0, sip5y=9.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), sip5y=11.0, sip3y=7.0)
    m = metric(run(t, others), "t", "SIP_REL")
    assert m.state == "A" and m.value == pytest.approx(2.0) and m.points == pytest.approx(83.333, abs=0.001)    # (2 + 3) / 6
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), sip5y=None, sip3y=10.0)
    m = metric(run(t, others), "t", "SIP_REL")
    assert m.state == "S" and m.why == "sip3y" and m.value == pytest.approx(2.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), sip5y=None, sip3y=None)
    assert metric(run(t, others), "t", "SIP_REL").state == "F"


def monthly_peers(pattern, n=9, group="EQ-LARGE", sub="large-cap", **kw):
    return peers(n, group, sub, rets=pattern, **kw)


def test_hit_rate_is_the_share_of_months_at_least_equal_to_the_peer_median():
    pattern = alt(60, 2.0, 0.0)                                   # peers: +2, 0, +2, 0 ...  (their median each month is the pattern itself)
    others = monthly_peers(pattern)
    rets = list(pattern)
    for i in range(60):                                            # the last 36 returns are indexes 24..59: beat the median in 18 of them, trail in 18
        rets[i] = pattern[i] + (0.5 if (i - 24) % 2 == 0 else -0.5) if i >= 24 else pattern[i]
    t = fund("t", "EQ-LARGE", "large-cap", seed=5)
    t.mnavs = series(61, 0, 0, 0, rets=rets)
    m = metric(run(t, others), "t", "HIT_RATE")
    assert m.state == "A" and m.why == "36 months compared"
    assert m.value == pytest.approx(50.0) and m.points == pytest.approx(40.0)             # 18 / 36 = 50%; (50 - 40) / 25


def test_hit_rate_needs_12_compared_months():
    pattern = alt(60, 2.0, 0.0)
    others = monthly_peers(pattern)
    t = fund("t", "EQ-LARGE", "large-cap", seed=5, months=12)        # 12 NAVs = 11 returns
    t.mnavs = series(12, 0, 0, 0, rets=pattern[:11])
    m = metric(run(t, others), "t", "HIT_RATE")
    assert m.state == "F" and m.why == "under_12_months_compared"
    t13 = fund("t", "EQ-LARGE", "large-cap", seed=5, months=14)
    t13.mnavs = series(14, 0, 0, 0, rets=pattern[:13])
    assert metric(run(t13, others), "t", "HIT_RATE").state == "A"


A36 = (36 / 35) ** 0.5 * 12 ** 0.5       # VOL_M of 36 alternating +-1 returns


def test_vol_ratio_is_vol_over_the_peer_median_volatility():
    others = monthly_peers(alt(60, 1.0))
    t = fund("t", "EQ-LARGE", "large-cap", seed=5)
    t.mnavs = series(61, 0, 0, 0, rets=alt(60, 0.9))
    m = metric(run(t, others), "t", "VOL_RATIO")
    assert m.value == pytest.approx(0.9, rel=1e-6) and m.points == pytest.approx(75.0, abs=1e-4)   # (0.9-1.35)/(0.75-1.35)


def test_z2_case_2_liquid_fund_vol_015_floored_denominator():
    others = monthly_peers(alt(60, 0.005), group="DB-CASH", sub="liquid")
    t = fund("t", "DB-CASH", "liquid", seed=5)
    t.mnavs = series(61, 0, 0, 0, rets=alt(60, 0.15 / A36))
    m = metric(run(t, others), "t", "VOL_RATIO")
    assert m.peer < 0.2 and m.value == pytest.approx(0.75, rel=1e-6) and m.points == pytest.approx(85.0, abs=1e-4)


def test_dd_ratio_and_z2_cases_5_and_6():
    others = peers(9, mdd=-20.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), mdd=-15.0)
    m = metric(run(t, others), "t", "DD_RATIO")
    assert m.value == pytest.approx(0.75) and m.points == pytest.approx(92.857, abs=0.001)
    sc = run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), mdd=0.0), others)       # case 5: equity zero fall -> F
    m = metric(sc, "t", "DD_RATIO")
    assert m.state == "F" and m.rule == "kindC_fall_zero" and sc[0].counters["fall_zero"] >= 1
    cash = peers(9, "DB-CASH", "overnight", mdd=-0.2)                                  # case 6: overnight zero fall scores best
    sc = run(put(fund("t", "DB-CASH", "overnight", seed=5), mdd=0.0), cash)
    assert metric(sc, "t", "MDD_ABS").state == "A" and metric(sc, "t", "MDD_ABS").points == 100.0
    arb = peers(9, "HY-ARB", "arbitrage", mdd=-0.3)
    d = metric(run(put(fund("t", "HY-ARB", "arbitrage", seed=5), mdd=0.0), arb), "t", "DD_RATIO")
    assert d.state == "A" and d.value == 0.0 and d.points == 100.0


def test_down_capture_and_its_floor_and_n():
    pattern = alt(60, 3.0, 1.0)
    others = monthly_peers(pattern)
    rets = [(-1.05 if (i >= 24 and pattern[i] < 0) else pattern[i]) for i in range(60)]
    t = fund("t", "EQ-LARGE", "large-cap", seed=5)
    t.mnavs = series(61, 0, 0, 0, rets=rets)
    m = metric(run(t, others), "t", "DOWN_CAPTURE")
    assert m.value == pytest.approx(105.0) and m.points == pytest.approx(33.333, abs=0.001)
    pat2 = alt(60, 0.5, 0.01)
    others = monthly_peers(pat2)
    t.mnavs = series(61, 0, 0, 0, rets=[(-0.02 if (i >= 24 and pat2[i] < 0) else pat2[i]) for i in range(60)])
    sc = run(t, others)
    assert metric(sc, "t", "DOWN_CAPTURE").value == pytest.approx(40.0)              # denominator floored at -0.05
    assert sc[0].counters["kindB_down_capture_floor"] == 1
    few = [1.0] * 60
    for i in (30, 40, 50):
        few[i] = -1.0
    t.mnavs = series(61, 0, 0, 0, rets=few)
    assert metric(run(t, monthly_peers(few)), "t", "DOWN_CAPTURE").state == "N"


def test_sharpe_rel_and_young_fund():
    others = monthly_peers(alt(60, 1.0), r3y=12.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r3y=12.5)
    t.mnavs = series(61, 0, 0, 0, rets=alt(60, 1.0))
    m = metric(run(t, others), "t", "SHARPE_REL")
    want = 0.5 / A36
    assert m.value == pytest.approx(want) and m.points == pytest.approx((want + 0.5) * 100, abs=1e-4)
    young = put(fund("t", "EQ-LARGE", "large-cap", seed=5, months=30), r3y=None)
    assert metric(run(young, others), "t", "SHARPE_REL").state == "F"


def test_worst12_rel():
    base = [0.5] * 60
    base[40] = -10.0
    others = monthly_peers(base)
    rets = list(base)
    rets[40] = -12.0
    t = fund("t", "EQ-LARGE", "large-cap", seed=5)
    t.mnavs = series(61, 0, 0, 0, rets=rets)
    m = metric(run(t, others), "t", "WORST12_REL")
    fw = (1.005 ** 11 * 0.88 - 1) * 100
    pw = (1.005 ** 11 * 0.90 - 1) * 100
    assert m.own == pytest.approx(fw, abs=1e-6) and m.peer == pytest.approx(pw, abs=1e-6) and m.points == pytest.approx(scale(fw - pw, -6, 6))


def test_calmar():
    others = peers(9, "SOL", "retirement")
    m = metric(run(put(fund("t", "SOL", "retirement", seed=5), r3y=12.0, mdd=-8.0), others), "t", "CALMAR")
    assert m.value == pytest.approx(1.5) and m.points == 100.0
    assert metric(run(put(fund("t", "SOL", "retirement", seed=5), r3y=6.0, mdd=-0.2), others), "t", "CALMAR").value == pytest.approx(6.0)
    assert metric(run(put(fund("t", "SOL", "retirement", seed=5), r3y=-1.0, mdd=-8.0), others), "t", "CALMAR").state == "Z"


def test_ter_metrics_and_z2_case_3_and_4():
    others = peers(8, ter=1.0) + [put(fund(f"z{i}", "EQ-LARGE", "large-cap", seed=900 + i), ter=0.0) for i in range(4)]
    m = metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=1.2), others), "t", "TER_VS_PEER")
    assert m.peer_n == 8 and m.peer == 1.0 and m.points == pytest.approx(33.333, abs=0.001)
    m = metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=0.20), peers(8, ter=0.02)), "t", "TER_VS_PEER")
    assert m.value == pytest.approx(4.0) and m.points == 0.0
    sc = run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=0.0), peers(9, ter=1.0))
    for mid in ("TER_VS_PEER", "TER_ABS"):
        m = metric(sc, "t", mid)
        assert m.state == "F" and m.why == "ter_zero" and m.points == m.gv
    assert sc[0].counters["ter_zero"] == 1
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=0.01), []), "t", "TER_ABS").state == "A"
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=0.9, ter_date=date(2026, 9, 14)), []), "t", "TER_ABS").state == "A"
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), ter=0.9, ter_date=date(2026, 9, 13)), []), "t", "TER_ABS").why == "ter_stale"
    d = put(fund("d", "EQ-LARGE", "large-cap", plan="Direct", seed=5), ter=0.85)
    r = put(fund("r", "EQ-LARGE", "large-cap", plan="Regular", seed=6), ter=1.6)
    assert metric(run(d, []), "d", "TER_ABS").points == pytest.approx(50.0) and metric(run(r, []), "r", "TER_ABS").points == pytest.approx(50.0)


def test_fee_share_and_exit_load():
    others = peers(9, "DB-ACCRUAL", "short-duration")
    m = metric(run(put(fund("t", "DB-ACCRUAL", "short-duration", seed=5), ter=1.0, r3y=7.0), others), "t", "FEE_SHARE")
    assert m.value == pytest.approx(12.5) and m.points == pytest.approx((12.5 - 25) / (2 - 25) * 100)
    for r3 in (-1.0, 0.0):
        assert metric(run(put(fund("t", "DB-ACCRUAL", "short-duration", seed=5), ter=1.0, r3y=r3), others), "t", "FEE_SHARE").state == "Z"
    for text, want in (("Nil", 100.0), ("0.25% for 7 days", 90.0), ("1% if redeemed within 1 year", 60.0), ("2% if redeemed within 1 year", 30.0), ("1% for 2 years", 10.0)):
        assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), exit_text=text), []), "t", "EXIT_LOAD").points == want
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), exit_text="As per SID"), []), "t", "EXIT_LOAD").state == "F"
    assert metric(run(put(fund("t", "SOL", "retirement", seed=5), exit_text="1% for 2 years"), []), "t", "EXIT_LOAD").state == "N"


def test_age_size_and_portfolio_metrics():
    years = (date(2026, 10, 29) - date(2018, 1, 1)).days / 365.25
    m = metric(run(fund("t", "EQ-LARGE", "large-cap", seed=5), []), "t", "AGE")
    assert m.points == pytest.approx((years - 3) / 7 * 100)
    m = metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), launch=None), []), "t", "AGE")
    assert m.state == "S" and m.value == pytest.approx(61 / 12)
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), launch=date(2027, 1, 1)), []), "t", "AGE").why == "launch_date_impossible"
    m = metric(run(put(fund("t", "EQ-MID", "mid-cap", seed=5), aum_lakh=5_000_000.0), []), "t", "SIZE_FIT")
    assert m.points == pytest.approx((50000 - 60000) / (30000 - 60000) * 100)
    assert metric(run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), aum_lakh=5_000_000.0), []), "t", "SIZE_FIT").points == 100.0
    assert metric(run(put(fund("t", "DB-CASH", "liquid", seed=5), aum_lakh=275_000.0), []), "t", "SIZE_FIT").points == pytest.approx(50.0)
    sc = run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), aum_lakh=0.0), peers(9))     # case 11
    assert metric(sc, "t", "SIZE_FIT").state == "F" and sc[0].counters["aum_zero"] == 1
    others = peers(9, top10=40.0, sector_top=25.0)
    sc = run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), equity_pct=92.0, top10=30.0, sector_top=20.0), others)
    assert metric(sc, "t", "EQUITY_INVESTED").points == pytest.approx(12 / 17 * 100)
    assert metric(sc, "t", "TOP10_CONC_REL").value == pytest.approx(-10.0)
    assert metric(sc, "t", "SECTOR_CONC_REL").points == pytest.approx(17 / 18 * 100)
    assert metric(run(put(fund("t", "EQ-THEME", "sectoral-thematic", seed=5), sector_top=60.0), []), "t", "SECTOR_CONC_REL").state == "N"
    sc = run(put(fund("t", "EQ-LARGE", "large-cap", seed=5), top10=0.0, equity_pct=0.0, sector_top=0.0), others)
    assert [metric(sc, "t", i).state for i in ("TOP10_CONC_REL", "EQUITY_INVESTED", "SECTOR_CONC_REL")] == ["F"] * 3


def test_z2_case_12_and_alloc_fit_and_risk_o_meter():
    t = put(fund("t", "DB-ACCRUAL", "short-duration", seed=5), equity_pct=0.0, other_pct=0.0, split_sum=100.0)
    m = metric(run(t, []), "t", "ASSET_FIT_DEBT")
    assert m.state == "A" and m.points == 100.0
    assert metric(run(put(t, split_sum=49.9), []), "t", "ASSET_FIT_DEBT").why == "split_unparsed"
    assert metric(run(put(t, split_sum=50.0), []), "t", "ASSET_FIT_DEBT").state == "A"
    others = peers(9, "HY-AGGR", "aggressive-hybrid", equity_pct=65.0)
    m = metric(run(put(fund("t", "HY-AGGR", "aggressive-hybrid", seed=5), equity_pct=70.0), others), "t", "ALLOC_FIT")
    assert m.points == pytest.approx(66.667, abs=0.001)
    assert metric(run(put(fund("t", "HY-AGGR", "aggressive-hybrid", seed=5), equity_pct=65.0), others), "t", "ALLOC_FIT").points == 100.0
    assert metric(run(put(fund("t", "HY-AGGR", "aggressive-hybrid", seed=5), equity_pct=0.0), others), "t", "ALLOC_FIT").state == "F"
    assert metric(run(fund("t", "HY-ARB", "arbitrage", seed=5), []), "t", "ALLOC_FIT").state == "N"
    rk = [put(fund(f"p{i}", "HY-CONS", "conservative-hybrid", seed=100 + i), risk_text="Moderately High") for i in range(9)]
    m = metric(run(put(fund("t", "HY-CONS", "conservative-hybrid", seed=5), risk_text="Low"), rk), "t", "RISKOMETER_REL")   # case 7
    assert m.state == "A" and m.own == 0.0 and m.value == -3.0 and m.points == 100.0
    assert metric(run(put(fund("t", "HY-CONS", "conservative-hybrid", seed=5), risk_text=None), rk), "t", "RISKOMETER_REL").state == "F"


def test_etf_metrics_and_z2_case_8():
    def etf(**kw):
        return put(fund("e", "OT-PASSIVE", "etf", plan="ETF", kind="etf", seed=5, family_key="nifty50"), **kw)
    for cr, pts in ((30, 100), (25, 100), (24.99, 80), (5, 80), (1, 60), (0.99, 30), (0.25, 30), (0.24, 0), (0.0, 0)):
        assert metric(run(etf(turnover_cr=float(cr)), []), "e", "ETF_LIQUIDITY").points == pts
    assert metric(run(etf(turnover_cr=None), []), "e", "ETF_LIQUIDITY").state == "F"
    assert metric(run(etf(premium=0.5, traded_on_nav_date=True), []), "e", "ETF_PREMIUM").points == pytest.approx(52.6, abs=0.05)
    assert metric(run(etf(premium=0.0, traded_on_nav_date=True), []), "e", "ETF_PREMIUM").points == 100.0
    assert metric(run(etf(premium=0.0, traded_on_nav_date=False), []), "e", "ETF_PREMIUM").state == "F"
    idx = put(fund("i", "OT-PASSIVE", "index-funds", seed=5, family_key="nifty50"))
    assert metric(run(idx, []), "i", "ETF_LIQUIDITY").state == "N"


def test_z2_case_9_all_n_pillar(monkeypatch):
    sheet = dict(SHEETS["EQ-LARGE"])
    sheet["cost"] = [Metric("TER_VS_PEER", 50, None), Metric("TER_ABS", 30, None), Metric("EXIT_LOAD", 20, None)]
    monkeypatch.setitem(SHEETS, "EQ-LARGE", sheet)
    s = run(fund("t", "EQ-LARGE", "large-cap", seed=5), peers(9))[0]
    assert s.pillars["cost"] == 50.0 and s.pillar_flags["cost"] and "PILLAR_ALL_N" in s.flags and s.confidence < 1.0


def test_z2_case_13_frozen_nav():
    others = monthly_peers(alt(60, 1.0), r3y=12.0, mdd=-10.0)
    t = put(fund("t", "EQ-LARGE", "large-cap", seed=5), r3y=12.0, mdd=-1.0)
    t.mnavs = series(61, 0, 0, 0, rets=alt(60, 0.0011))
    sc = run(t, others)
    for mid in ("VOL_RATIO", "SHARPE_REL", "DD_RATIO", "DOWN_CAPTURE", "HIT_RATE", "WORST12_REL"):
        assert metric(sc, "t", mid).state == "F" and metric(sc, "t", mid).why == "frozen_nav"
    assert {"NAV_BREAK", "FROZEN_NAV"} <= set(sc[0].flags)
    assert metric(sc, "p0", "VOL_RATIO").peer_n == 8
