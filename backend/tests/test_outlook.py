"""Profit and revenue outlook (finlit/outlook): the weighted-growth model per the team's methodology (worked example, weights, redistribution, CAGR edge
cases, sector median, cap rule, iterative forecast, horizons), the sector peers, the back-test, Gold gating, Reliance regression."""

import json
import re

import pytest

from finlit.outlook import backtest as BT
from finlit.outlook import model as M
from finlit.outlook.inputs import Inputs, build_inputs
from finlit.outlook.router import build_response
from finlit.outlook.sector import peer_values
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)


def hist(rev, prof, fy0=20):
    return M.Hist([f"FY{fy0 + k}" for k in range(len(rev))], list(rev), list(prof))


def test_weight_columns_total_100_and_match_the_spec():
    for kind in ("revenue", "profit"):
        keys = [p[0] for p in M.PARAMS[kind]]
        for hz in M.HORIZONS:
            w = M.WEIGHTS[kind][hz]
            assert set(w) == set(keys) and sum(w.values()) == 100
    assert M.WEIGHTS["revenue"]["short"] == {"co_1y": 50, "co_3y": 10, "co_5y": 5, "sec_1y": 25, "sec_3y": 5, "sec_5y": 5}
    assert M.WEIGHTS["profit"]["long"]["margin"] == 10 and M.WEIGHTS["profit"]["mid"]["co_3y"] == 25 and M.WEIGHTS["revenue"]["long"]["co_5y"] == 40


def test_horizon_sets_the_number_of_forecast_years():
    h = hist([100, 110, 121, 133, 146, 161], [10, 11, 12, 13, 14, 15])
    for hz, n in (("short", 1), ("mid", 3), ("long", 5)):
        f = M.forecast("revenue", h, hz, M.default_weights("revenue", hz), {})["forecast"]
        assert len(f["years"]) == n and f["years"][0]["period"] == "FY26" and f["years"][-1]["period"] == f"FY{25 + n}" and f["base"] == {"period": "FY25", "valueCr": 161.0}


def test_worked_example_is_iterative_at_a_constant_rate():
    assert [round(v, 2) for v in M.project(1000, 12, 3)] == [1120.00, 1254.40, 1404.93]
    assert [round(v, 2) for v in M.project(100, 15, 2)] == [115.0, 132.25]
    # not exponential from a different rate: the page's table is exactly the iteration
    h = hist([1000.0] * 6, [100.0] * 6)
    inputs = {k: M.Input(k, k, "company", value=12.0, raw=12.0) for k, *_ in M.PARAMS["revenue"]}
    wr = M.weighted_rate("revenue", inputs, M.default_weights("revenue", "mid"))
    assert wr["ratePct"] == 12.0


def test_growth_arithmetic_and_cagr_edge_cases():
    assert M.yoy(100, 112) == pytest.approx(12.0) and M.yoy(0, 5) is None and M.yoy(-5, 5) is None and M.yoy(None, 5) is None
    assert M.cagr(100, 200, 3) == pytest.approx(25.992, abs=1e-3)
    assert M.cagr(-1, 100, 3) is None and M.cagr(100, -1, 3) is None and M.cagr(0, 100, 3) is None and M.cagr(100, 200, 0) is None
    short = hist([100, 110, 121], [10, 11, 12])
    ins = M.company_inputs("revenue", short)
    assert ins["co_1y"].value == pytest.approx(10.0) and ins["co_3y"].value is None and "4 years" in ins["co_3y"].reason and ins["co_5y"].value is None
    mid_gap = M.company_inputs("revenue", hist([100, None, 121, 133, 146, 161], [1] * 6))       # a middle year does not matter to a CAGR (only its two ends do)
    assert mid_gap["co_5y"].value == pytest.approx(M.cagr(100, 161, 5)) and mid_gap["co_1y"].value is not None
    end_gap = M.company_inputs("revenue", hist([100, 110, 121, 133, 146, None], [1] * 6))
    assert end_gap["co_1y"].value is None and "missing" in end_gap["co_1y"].reason and end_gap["co_5y"].value is None


def test_loss_and_near_zero_profit_use_the_stated_alternative():
    turn = hist([1000] * 5, [-50, -20, 10, 40, 80])            # turnaround: CAGR undefined
    p3 = M.company_inputs("profit", turn)["co_3y"]
    assert p3.value is not None and "average size" in p3.method and "loss" in p3.method
    base = (abs(-20) + 10 + 40 + 80) / 4
    assert p3.raw == pytest.approx((80 - -20) / base / 3 * 100)
    near = hist([1000, 1000], [2.0, 30.0])                    # 0.2% margin start: ratio would say +1400%
    p1 = M.company_inputs("profit", near)["co_1y"]
    assert "near zero" in p1.method and p1.raw == pytest.approx((30 - 2) / 16 * 100) and p1.capped and p1.value == 50.0
    normal = M.company_inputs("profit", hist([1000, 1000], [100.0, 110.0]))["co_1y"]
    assert normal.raw == pytest.approx(10.0) and "average size" not in normal.method
    assert M.company_inputs("profit", hist([1000, 1000], [0.0, 0.0]))["co_1y"].value is None


def test_loss_making_latest_year_gets_no_forecast_but_shows_the_inputs():
    h = hist([1000] * 6, [50, 40, 30, 20, -10, -40])
    r = M.forecast("profit", h, "short", M.default_weights("profit", "short"), {})
    assert not r["forecast"]["available"] and "not positive" in r["forecast"]["reason"] and r["rate"]["rows"][0]["status"] == "ok"


def test_margin_trend_is_relative_change_not_points():
    h = hist([1000, 1000], [100.0, 120.0])           # margin 10% -> 12%
    m = M.margin_trend(h)[0]
    assert m == pytest.approx(20.0)                  # relative +20%, not +2 points
    assert M.margin_trend(hist([1000, 1000], [-5.0, 120.0]))[0] is None and "not meaningful" in M.margin_trend(hist([1000, 1000], [-5.0, 120.0]))[2]
    assert "margin" not in M.company_inputs("revenue", h)


def test_cap_rule_marks_when_it_applied():
    assert M.cap(80) == (50.0, True) and M.cap(-90) == (-50.0, True) and M.cap(12.5) == (12.5, False)
    ins = M.company_inputs("revenue", hist([100, 400], [1, 1]))
    assert ins["co_1y"].raw == pytest.approx(300.0) and ins["co_1y"].value == 50.0 and ins["co_1y"].capped


def test_sector_uses_the_median_and_needs_enough_peers():
    assert M.sector_median([1, 2, 100, 3, 4]) == (3.0, 5)             # the median, not the 22 average
    assert M.sector_median([1, 2, 3, 4]) == (None, 4)
    assert M.sector_median([1, None, float("nan"), 2, 3, 4, 5]) == (3.0, 5)
    s = M.sector_inputs("revenue", {"sec_1y": [10, 12, 14, 400, 16], "sec_3y": [1, 2]}, {"sec_1y": "Metals (industry)", "sec_3y": "Metals (industry)"})
    assert s["sec_1y"].raw == 14 and s["sec_1y"].method == "Median of 5 peers in Metals (industry)" and s["sec_3y"].value is None and "at least 5" in s["sec_3y"].reason
    assert s["sec_5y"].value is None
    n = M.sector_inputs("revenue", None, None, "No sector stored")
    assert all(i.value is None and i.reason == "No sector stored" for i in n.values())


def test_peer_values_prefer_industry_then_sector_and_leave_the_company_out():
    n = 14
    symbols = [f"S{k}" for k in range(n)]
    sector = ["Energy"] * n
    industry = ["Oil"] * 6 + ["Gas"] * 8
    col = [float(k) for k in range(n)]
    cols = {"sales_growth": col, "sales_cagr_3y": col, "sales_cagr_5y": [float("nan")] * n}
    v, g, why = peer_values("revenue", "S0", symbols, sector, industry, cols)
    assert why is None and v["sec_1y"] == [1.0, 2.0, 3.0, 4.0, 5.0] and g["sec_1y"] == "Oil (industry)" and v["sec_5y"] == []
    v2, g2, _ = peer_values("revenue", "S7", symbols, sector, industry, cols)        # Gas: 7 peers
    assert len(v2["sec_1y"]) == 7 and g2["sec_1y"] == "Gas (industry)"
    industry3 = ["Oil"] * 3 + ["Gas"] * 11
    v3, g3, _ = peer_values("revenue", "S0", symbols, sector, industry3, cols)       # too few in the industry: the sector
    assert g3["sec_1y"] == "Energy (sector)" and len(v3["sec_1y"]) == 13
    assert peer_values("revenue", "NOPE", symbols, sector, industry, cols)[0] is None


def test_missing_inputs_redistribute_weights_proportionally():
    ins = {k: M.Input(k, k, "company", value=v, raw=v) for k, v in (("co_1y", 10.0), ("co_3y", 20.0))}
    for k in ("co_5y", "sec_1y", "sec_3y", "sec_5y"):
        ins[k] = M.Input(k, k, "company", reason="blank")
    w = M.default_weights("revenue", "short")          # 50, 10, then 5+25+5+5 missing
    wr = M.weighted_rate("revenue", ins, w)
    assert wr["ratePct"] == pytest.approx((50 * 10 + 10 * 20) / 60, abs=0.01) and wr["weightLeftPct"] == 60
    eff = {r["key"]: r["effectiveWeightPct"] for r in wr["rows"]}
    assert eff["co_1y"] == pytest.approx(83.33, abs=0.01) and eff["co_3y"] == pytest.approx(16.67, abs=0.01) and eff["sec_1y"] == 0
    assert sum(eff.values()) == pytest.approx(100, abs=0.02) and len(wr["unavailable"]) == 4
    assert sum(r["contributionPts"] or 0 for r in wr["rows"]) == pytest.approx(wr["ratePct"], abs=0.02)
    assert M.weighted_rate("revenue", {k: M.Input(k, k, "company") for k in ins}, w)["ratePct"] is None


def test_custom_weights_validate_normalise_and_replace_the_column():
    d = M.default_weights("revenue", "mid")
    assert M.validate_weights("revenue", None, "mid") == d
    assert M.validate_weights("revenue", {**d, "co_1y": 20, "co_3y": 30}, "mid")["co_1y"] == 20
    for bad in ({**d, "co_1y": 50}, {**d, "zzz": 0}, {k: v for k, v in d.items() if k != "co_1y"}, {**d, "co_1y": -1}, {**d, "co_1y": 101}, {**d, "co_1y": True}):
        with pytest.raises(M.WeightError):
            M.validate_weights("revenue", bad, "mid")
    n = M.validate_weights("revenue", {k: v * 2 for k, v in d.items()}, "mid", normalise=True)
    assert sum(n.values()) == pytest.approx(100, abs=0.01) and n["co_3y"] == pytest.approx(40, abs=0.01)
    with pytest.raises(M.WeightError):
        M.validate_weights("revenue", {k: 0 for k in d}, "mid", normalise=True)
    pd = M.default_weights("profit", "short")
    assert "margin" in pd and "margin" not in d


def test_normalised_profit_removes_one_offs_and_says_so():
    assert M.adjust_profit(100, None, None, None, None) == (100, False)
    assert M.adjust_profit(150, 100, None, None, None) == (100, True)                       # discontinued profit already taken out
    assert M.adjust_profit(100, None, 40, 20, 100) == (100 - 40 * 0.8, True)                # a material one-off gain, taxed at 20%
    assert M.adjust_profit(100, None, 5, 25, 100) == (100, False)                           # immaterial: left in
    assert M.adjust_profit(None, None, 5, None, None) == (None, False)
    inp = Inputs(fy=["FY24", "FY25"], pl={"revenue": {"FY24": 1000, "FY25": 1100}, "net_profit": {"FY24": 100, "FY25": 200}, "exceptional_items": {"FY24": 0, "FY25": 100},
                                          "tax": {"FY24": 30, "FY25": 40}, "profit_before_tax": {"FY24": 130, "FY25": 240}})
    h = M.hist_from_inputs(inp)
    assert h.adjusted == ["FY25"] and h.profit[0] == 100 and h.profit[1] < 200


def test_forecast_hands_back_rate_rows_and_the_year_table():
    h = hist([1000, 1100, 1210, 1331, 1464.1, 1610.51], [100, 110, 121, 133.1, 146.41, 161.051])
    sec = M.sector_inputs("revenue", {k: [10.0] * 5 for k in ("sec_1y", "sec_3y", "sec_5y")}, {k: "X (sector)" for k in ("sec_1y", "sec_3y", "sec_5y")})
    r = M.forecast("revenue", h, "mid", M.default_weights("revenue", "mid"), sec)
    assert r["rate"]["ratePct"] == pytest.approx(10.0, abs=0.01) and r["rate"]["unavailable"] == []
    ys = r["forecast"]["years"]
    assert [y["valueCr"] for y in ys] == [1771.56, 1948.72, 2143.59] and ys[0]["period"] == "FY26" and r["inputCapPct"] == 50.0


# ------------------------------------------------------------------------------------------------------------ back-test
def test_backtest_uses_only_data_before_the_origin_and_summarises():
    def co(sym, g, sector="A"):
        rev = [100 * (1 + g) ** k for k in range(9)]
        return BT.Company(sym, hist(rev, [r / 10 for r in rev]), sector, "ind", "Large")
    uni = [co(f"C{k}", 0.1 + k / 100) for k in range(8)]
    rows = BT.run(uni, kinds=("revenue",), horizons=("short", "mid"))
    assert rows and {r["horizon"] for r in rows} == {"short", "mid"}
    r0 = next(r for r in rows if r["symbol"] == "C0" and r["horizon"] == "short" and r["origin"] == "FY22")
    assert r0["target"] == "FY23" and r0["actual"] == pytest.approx(100 * 1.1 ** 3) and abs(r0["estimate"] - r0["actual"]) / r0["actual"] < 0.1
    s = BT.summarise(rows, "horizon")
    assert {x["group"] for x in s} == {"short", "mid"} and all(x["n"] > 0 and x["mapePct"] is not None for x in s)
    assert BT.summarise(rows, "size")[0]["group"][1] == "Large"
    # future data never leaks: a company whose growth jumps after the origin is forecast from the earlier pace
    jump = BT.Company("J", hist([100, 110, 121, 133.1, 1000, 1000], [10, 11, 12, 13, 100, 100]), "A", "ind", "Mid")
    jr = [r for r in BT.run([jump], kinds=("revenue",), horizons=("short",)) if r["origin"] == "FY23"][0]
    assert jr["estimate"] == pytest.approx(133.1 * 1.1, rel=0.01)
    assert BT.sample_ok(30) and not BT.sample_ok(5)


# --------------------------------------------------------------------------------------------------------------- response
def test_reliance_regression_shapes_and_no_banned_words(reliance_sections):
    for kind in ("profit", "revenue"):
        for hz in ("short", "mid", "long"):
            r = build_response(kind, hz, M.default_weights(kind, hz), False, reliance_sections, "RELIANCE", "standalone")
            text = json.dumps(r).lower()
            assert not re.search(r"\b(buy|sell|hold|target price|recommend\w*|guarantee\w*)\b", text)
            assert r["asOf"]["yearly"] == "FY26" and r["mode"] == "model" and r["horizon"]["years"] == M.HORIZONS[hz]["years"]
            f = r["forecast"]
            assert f["available"] and len(f["years"]) == M.HORIZONS[hz]["years"] and f["base"]["period"] == "FY26"
            assert sum(x["weightPct"] for x in r["rate"]["rows"]) == pytest.approx(100, abs=0.01)
            pts = r["history"]["points"]
            assert pts[-1]["period"] == "FY26" and pts[-1]["valueCr"] == f["base"]["valueCr"] and len(pts) <= M.HISTORY_YEARS
            assert any(x["status"] == "unavailable" and x["who"] == "sector" and x["reason"] for x in r["rate"]["rows"])    # no table passed: sector reasons shown
    p = build_response("profit", "short", M.default_weights("profit", "short"), True, reliance_sections, "RELIANCE", "standalone")
    assert p["mode"] == "custom" and p["defaultWeights"] == M.default_weights("profit", "short")


# -------------------------------------------------------------------------------------------------------------- API
@pytest.mark.integration
async def test_outlook_is_gold_only_and_validates(app, anon):  # noqa: F811
    body = {"kind": "profit", "horizon": "mid"}
    assert (await anon.post("/api/outlook/RELIANCE", json=body)).status_code == 401
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = await silver.post("/api/outlook/RELIANCE", json=body)
    assert r.status_code == 403 and r.json()["detail"]["plan"] == "gold" and "forecast" not in r.text
    gold = await signed_in(app, "g@example.com", plan="gold")
    ok = await gold.post("/api/outlook/reliance", json=body)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "private, no-store"
    j = ok.json()
    assert j["symbol"] == "RELIANCE" and j["mode"] == "model" and j["horizon"]["key"] == "mid" and len(j["forecast"]["years"]) == 3 and len(j["rate"]["rows"]) == 7
    d = M.default_weights("profit", "mid")
    custom = await gold.post("/api/outlook/RELIANCE", json={**body, "weights": {**d, "co_1y": 20, "co_3y": 15}})
    assert custom.status_code == 200 and custom.json()["mode"] == "custom" and custom.json()["weights"]["co_1y"] == 20
    scaled = await gold.post("/api/outlook/RELIANCE", json={**body, "weights": {k: v * 2 for k, v in d.items()}, "normalise": True})
    assert scaled.status_code == 200 and sum(scaled.json()["weights"].values()) == pytest.approx(100, abs=0.01)
    assert (await gold.post("/api/outlook/RELIANCE", json={**body, "weights": {**d, "co_1y": 50}})).status_code == 422
    assert (await gold.post("/api/outlook/RELIANCE", json={**body, "weights": {**d, "Q": 0}})).status_code == 422
    assert (await gold.post("/api/outlook/RELIANCE", json={"kind": "other"})).status_code == 422
    assert (await gold.post("/api/outlook/RELIANCE", json={"kind": "profit", "horizon": "decade"})).status_code == 422
    assert (await gold.post("/api/outlook/NOTSTORED", json=body)).status_code == 404
    assert (await gold.post("/api/outlook/bad%20sym", json=body)).status_code == 400
    again = await gold.post("/api/outlook/RELIANCE", json=body)
    assert again.status_code == 200 and again.json() == j      # second call is served from the short cache with the same body
    for c in (silver, gold):
        await c.aclose()
