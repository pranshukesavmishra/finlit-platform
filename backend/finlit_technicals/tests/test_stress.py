"""Stress Lab checks: the arithmetic, the decomposition, the TTM base from FinLit data, today's scenario, calibration."""
import json
import re
from dataclasses import replace
from pathlib import Path

from finlit_technicals import stress as S

FIX = Path(__file__).parent / "fixtures"


def pack():
    return json.loads((FIX / "ASIANPAINT.json").read_text(encoding="utf-8"))


def macro():
    return json.loads((FIX / "macro_2026-11-04.json").read_text(encoding="utf-8"))


def toy(**kw):
    e = S.Exposure(crude_rm=0.5, crude_beta=0.4, import_rm=0.2, energy_opex=0.2, energy_beta=0.5, var_opex=0.5,
                   export_rev=0.1, demand_beta=1.0, pass_through=0.5, floating_debt=0.7)
    base = dict(symbol="TOY", name="Toy Ltd", revenue=1000.0, rm=550.0, emp=80.0, opex=170.0, other_income=20.0,
                dep=40.0, interest=30.0, tax_rate=0.25, shares=10.0, debt=400.0, cash=100.0, exposure=e)
    base.update(kw)
    return S.Company(**base)


def close(a, b, tol=1e-6):
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


def test_zero_shock_reproduces_base():
    co = toy()
    r = S.run(co, S.Scenario())
    close(r["stressed"]["ebitda"], co.ebitda, 1e-3)
    close(r["stressed"]["eps"], co.eps, 1e-3)
    assert r["change_pct"]["eps"] == 0 and r["value"]["move_pct"] == 0
    assert r["label"] == "Holds up well" and r["score"] == 100


def test_drivers_add_up_to_the_pbt_change():
    co = toy()
    for sc in list(S.PRESETS.values()) + [S.Scenario(crude=33, usdinr=-4, cpi=1.5, wpi=3, rate_bp=80, demand=-7,
                                                     metals=12, agri=5)]:
        x = S._engine(co, sc)
        close(sum(x["drivers_rs"].values()), x["PBT1"] - co.pbt, 1e-9)


def test_hand_calculation_crude_only():
    co = toy()
    x = S._engine(co, S.Scenario(crude=20))
    # raw materials: 550 x 0.5 x 0.4 x 20% = 22; other expenses: 170 x 0.2 x 0.5 x 20% = 3.4
    close(x["dC_total"], 25.4)
    close(x["price_gain"], 0.5 * 0.9 * 25.4)          # pass-through on the 90% of revenue sold at home
    close(x["E1"], co.ebitda - 25.4 + 0.5 * 0.9 * 25.4)


def test_full_pass_through_at_home_keeps_ebitda():
    co = toy(exposure=S.Exposure(crude_rm=0.5, import_rm=0.2, export_rev=0.0, pass_through=1.0))
    x = S._engine(co, S.Scenario(crude=40, cpi=2))
    close(x["E1"], co.ebitda, 1e-9)


def test_exporter_gains_from_a_weaker_rupee():
    co = toy(exposure=S.Exposure(crude_rm=0.0, import_rm=0.0, export_rev=0.8, pass_through=0.3))
    r = S.run(co, S.Scenario(usdinr=10))
    assert r["change_pct"]["eps"] > 0
    assert r["drivers"][-1]["key"] == "rupee"


def test_rates_hit_interest_and_value_and_cover_label():
    co = toy(debt=4000.0, interest=150.0, exposure=S.Exposure(floating_debt=1.0))
    r = S.run(co, S.Scenario(rate_bp=300))
    close(r["stressed"]["interest"], 150 + 4000 * 0.03 * 1.0, 1e-3)
    assert r["value"]["move_pct"] < 0
    assert r["stressed"]["interest_cover"] < 1.5 and r["label"] == "Debt cover at risk" and r["score"] <= 30


def test_labels_and_score():
    assert S._label(-35, 5, True)[0] == "Hit hard"
    assert S._label(-15, 5, True)[0] == "Takes a clear hit"
    assert S._label(-5, 5, True)[0] == "Holds up well"
    assert S._label(12, 5, True)[0] == "Gains under this shock"
    assert S._label(-5, 1.2, True)[0] == "Debt cover at risk"
    assert S._label(-5, 1.2, False)[0] == "Holds up well"


def test_value_one_year_shock_vs_permanent():
    co = toy()
    one = S.run(co, S.Scenario(crude=40))["value"]["move_pct"]
    perm = S.run(co, replace(S.Scenario(crude=40), persistence="permanent"))["value"]["move_pct"]
    eps = S.run(co, S.Scenario(crude=40))["change_pct"]["eps"]
    assert eps < perm <= 0 or abs(perm - eps) < 0.05     # permanent: value moves with EPS
    assert perm < one < 0                                 # one year: a fraction of it


def test_breaking_points_halve_eps():
    co = toy()
    bp = S.breaking_points(co)
    x = S._engine(co, S.Scenario(crude=bp["crude_pct"]))
    close(x["eps1"], co.eps / 2, 1e-2)      # breaking points are rounded to 0.1
    y = S._engine(co, S.Scenario(demand=bp["demand_pct"]))
    close(y["eps1"], co.eps / 2, 1e-2)


def test_ttm_base_from_finlit_pack():
    co = S.company_from_pack(pack(), calibrate_history=False)
    close(co.revenue, 9976.51 + 10541.94 + 9246.7 + 8867.02, 1e-9)
    close(co.ebitda, 1557.07 + 2168.76 + 1786.61 + 1780.96, 1e-6)
    close(co.rm, 6013.29 + 5946.49 + 5103.52 + 4928.87, 1e-9)
    assert co.base_label == "TTM Dec 2025 to Sep 2026" and co.base_end == "2026-09-30"
    assert "basic industry: Paints" in co.exposure.source and co.exposure.crude_rm == 0.45
    assert 0.24 < co.tax_rate < 0.27 and co.shares == 95.92


def test_fy_and_quarter_bases():
    fy = S.company_from_pack(pack(), base="fy", calibrate_history=False)
    close(fy.revenue, 35583.54)
    close(fy.rm, 20001.78)
    q = S.company_from_pack(pack(), base="q:Sep 2025", calibrate_history=False)
    close(q.revenue, 8531.27)


def test_cost_split_falls_back_to_latest_year():
    p = pack()
    for k in ("cost_of_goods_sold", "employee_benefit_expense", "otherExpenses", "costOfMaterialsConsumed",
              "purchasesOfStockInTrade", "changesInInventories"):
        p["quarterly"]["rows"].pop(k)
    co = S.company_from_pack(p, calibrate_history=False)
    close(co.rm + co.emp + co.opex, co.revenue - 7293.40, 1e-6)
    close(co.rm / (co.rm + co.emp + co.opex), 20001.78 / (20001.78 + 2799.59 + 6086.25), 1e-6)
    assert any("latest full year" in n for n in co.notes)


def test_banks_are_excluded():
    p = pack()
    p["dataQuality"]["isBank"] = True
    try:
        S.company_from_pack(p)
        raise AssertionError("bank accepted")
    except ValueError as e:
        assert "not covered" in str(e)


def test_today_scenario_against_the_ttm_window():
    m = macro()
    try:
        S.today_scenario(m, brent=m["brent_quarterly"], base_end="2026-09-30")
        raise AssertionError("gap in FinLit's USD/INR series not caught")
    except ValueError as e:
        assert "0 of 12 months" in str(e)
    sc = S.today_scenario(m, brent=m["brent_quarterly"], brent_now=m["brent_now"], usdinr=m["usdinr_monthly"],
                          base_end="2026-09-30")
    close(sc.crude, (105.55 / ((63.63 + 81.11 + 102.93 + 95.95) / 4) - 1) * 100, 1e-3)
    close(sc.usdinr, 2.36, 1e-2)
    close(sc.cpi, 5.54 - 37.66 / 12, 1e-2)
    close(sc.rate_bp, (5.5 - 63.5 / 12) * 100, 1e-2)
    assert sc.inputs["base_window"] == ["2025-09-30", "2026-09-30"]


def test_calibration_recovers_a_known_pass_through():
    e = S.Exposure(crude_rm=0.5, crude_beta=0.4, import_rm=0.2, pass_through=0.6)
    mf = S.load_macro_fy()
    years = mf["years"]
    true_pass, s, rev = 0.8, 0.55, 1000.0
    revs, cogs = [rev], [rev * s]
    for a, b in zip(years, years[1:]):
        i, j = years.index(a), years.index(b)
        crude_inr = (mf["brent_usd"][j] * mf["usdinr"][j]) / (mf["brent_usd"][i] * mf["usdinr"][i]) - 1
        pi, _ = S.input_inflation(e, crude_inr=crude_inr, fx=mf["usdinr"][j] / mf["usdinr"][i] - 1,
                                  wpi=mf["wpi_mfg"][j] / 100, cpi=mf["cpi"][j] / 100, agri=mf["wpi_primary"][j] / 100)
        p = true_pass * pi * s                            # price rise that recovers 80% of the cost rise
        rev, s = rev * (1 + p), s * (1 + pi) / (1 + p)
        revs.append(rev)
        cogs.append(rev * s)
    per = [str(2000 + int(y[2:])) for y in years][::-1]
    fake = {"yearly": {"periods": per, "rows": {"revenue": revs[::-1], "cost_of_goods_sold": cogs[::-1],
                                                "otherExpenses": [100.0] * len(per)}}}
    cal = S.calibrate(fake, e, macro_fy=mf)
    assert abs(cal["pass_through"]["estimate"] - true_pass) < 0.02, cal["pass_through"]


def test_asian_paints_today_end_to_end():
    m = macro()
    co = S.company_from_pack(pack())
    sc = S.load_today(m, co.base_end)
    r = S.run(co, sc)
    assert -20 < r["change_pct"]["eps"] < -5 and r["drivers"][0]["key"] == "crude"
    page = S.stress_page(co, {"today": sc, **S.PRESETS})
    txt = json.dumps(page)
    assert set(page["scenarios"]) == {"today", *S.PRESETS}
    # descriptive wording only
    assert not re.search(r"\b(buy|sell|hold|accumulate|target price|recommend)\b", txt, re.I)


def test_backtest_runs_on_history():
    rows = S.backtest_years(pack())
    assert len(rows) == 8 and {r["to"] for r in rows} >= {"FY22", "FY23"}
    fy22 = next(r for r in rows if r["to"] == "FY22")
    assert fy22["change_predicted_pts"] < -2 and fy22["change_reported_pts"] < -5
    summ = S.backtest_summary(rows)
    assert summ["all_years"]["direction_right"] >= 6


def test_exposure_table_lookup_and_checks():
    t = S.exposures()
    e = t.lookup(symbol="X", basic="Airline", industry="Transport Services", sector="Services")
    assert e.energy_opex == 0.55 and e.source[-1] == "basic industry: Airline"
    assert t.lookup(sector="Financial Services").excluded
    assert t.unmatched(["Paints", "Something New"]) == ["Something New"]
    try:
        S.Exposure(crude_rm=0.7, import_rm=0.5).check()
        raise AssertionError("shares over 1 accepted")
    except ValueError:
        pass


def test_cli_runs(tmp_path):
    from finlit_technicals.__main__ import main
    assert main(["stress", str(FIX / "ASIANPAINT.json"), "--preset", "2022"]) == 0
    assert main(["stress", str(FIX / "ASIANPAINT.json"), "--set", "crude=30", "--set", "rate_bp=100", "--json"]) == 0
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "ASIANPAINT.json").write_text((FIX / "ASIANPAINT.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["stress-batch", "--packs", str(packs), "--today", str(FIX / "macro_2026-11-04.json"),
                 "--out", str(tmp_path / "out")]) == 0
    page = json.loads((tmp_path / "out" / "ASIANPAINT.json").read_text(encoding="utf-8"))
    assert "today" in page["scenarios"] and page["breaking_points"]["crude_pct"] > 50
