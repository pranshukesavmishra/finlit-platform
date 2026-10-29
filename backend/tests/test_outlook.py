"""Profit and revenue outlook (finlit/outlook): scorers with known numbers, renormalisation, the range, weights, Gold gating, Reliance regression."""

import json

import pytest

from finlit.outlook import compose as C
from finlit.outlook import scorers as S
from finlit.outlook.inputs import Inputs, build_inputs
from finlit.outlook.rangecalc import growth_range
from finlit.outlook.registry import GROUPS, default_weights
from finlit.outlook.router import build_response
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)


def mk(pl=None, bs=None, cf=None, ratios=None, q=None, lender=False, segments=None, n=6, nq=12):
    fy = [f"FY{20 + k}" for k in range(n)]
    qp = [f"Q{k}" for k in range(nq)]
    qends = [f"{2023 + (k // 4)}-{[3, 6, 9, 12][k % 4]:02d}-{[31, 30, 30, 31][k % 4]:02d}" for k in range(nq)]
    tab = lambda d, ps: {k: dict(zip(ps, v)) for k, v in (d or {}).items()}  # noqa: E731
    return Inputs(lender=lender, fy=fy, pl=tab(pl, fy), bs=tab(bs, fy), cf=tab(cf, fy), ratios=tab(ratios, fy), qp=qp, qends=qends, q=tab(q, qp), segments=segments or [])


def test_lin_and_piecewise_and_cagr():
    assert S.lin(10, 0, 20) == 50 and S.lin(-5, 0, 20) == 0 and S.lin(99, 0, 20) == 100
    assert S.lin(1, 2, 0) == 50                       # lower is better
    assert S.piecewise(2, [(0, 20), (4, 80)]) == 50 and S.piecewise(99, [(0, 20), (4, 80)]) == 80
    assert S.cagr(200, 100, 3) == pytest.approx(25.992, abs=1e-3) and S.cagr(-1, 100, 3) is None and S.cagr(5, 0, 3) is None


def test_margin_scorers_known_numbers_and_lender_exclusion():
    i = mk(pl={"revenue": [0, 0, 0, 0, 0, 1000], "operating_profit": [0, 0, 0, 0, 0, 125], "depreciation": [0, 0, 0, 0, 0, 25], "net_profit": [0, 0, 0, 0, 0, 75]},
           ratios={"gross_margin": [0, 0, 0, 0, 0, 30]})
    assert S.ebitda_margin(i) == pytest.approx(50)    # 12.5% on 0..25
    assert S.ebit_margin(i) == pytest.approx(50)      # 10% on 0..20
    assert S.net_margin(i) == pytest.approx(50)       # 7.5% on 0..15
    assert S.gross_margin(i) == pytest.approx(50)     # 30 on 10..50
    li = mk(pl=i.pl and {k: list(v.values()) for k, v in i.pl.items()}, lender=True, ratios={"gross_margin": [0] * 6})
    assert isinstance(S.ebitda_margin(li), S.Miss) and S.ebitda_margin(li).reason == "lender"
    assert S.net_margin(li) == pytest.approx(50)      # net margin stays for lenders


def test_growth_scorers():
    i = mk(pl={"net_profit": [100, 100, 100, 100, 100, 200], "revenue": [100, 100, 100, 100, 100, 200]})
    assert S.pat_cagr_3y(i) == pytest.approx(S.lin(S.cagr(200, 100, 3), -10, 20))
    loss = mk(pl={"net_profit": [100, 100, 100, 100, 100, -5]})
    assert S.pat_cagr_3y(loss) == 0.0
    turn = mk(pl={"net_profit": [-5, -5, -5, -5, -5, 10]})
    assert S.pat_cagr_3y(turn).reason == "not_meaningful"
    assert S.pat_cagr_3y(mk(pl={"net_profit": [1, 2]}, n=2)).reason == "no_data"
    steady = mk(pl={"net_profit": [100, 110, 121, 133.1, 146.41, 161.051]})
    assert S.profit_consistency(steady) == pytest.approx(100)     # equal growth: no variation


def test_cash_and_leverage_scorers():
    i = mk(pl={"net_profit": [0] * 5 + [100], "operating_profit": [0] * 5 + [200], "depreciation": [0] * 5 + [50], "finance_costs": [0] * 5 + [25],
               "revenue": [0] * 5 + [1000]},
           cf={"operating": [0] * 5 + [80], "free_cash_flow": [0] * 5 + [50]}, bs={"borrowings": [0] * 5 + [600], "cash": [0] * 5 + [100], "total_equity": [0] * 5 + [500],
                                                                              "total_assets": [1000] * 6})
    assert S.cfo_to_pat(i) == pytest.approx(S.lin(0.8, 0.4, 1.2))     # 50
    assert S.fcf_to_pat(i) == pytest.approx(50)
    assert S.net_debt_ebitda(i) == pytest.approx(S.lin(2.5, 5, 0))    # (600-100)/200
    assert S.interest_coverage(i) == pytest.approx(S.lin(6, 1, 8))    # EBIT 150 / 25
    assert S.debt_to_equity(i) == pytest.approx(S.lin(1.2, 2, 0))
    assert S.finance_cost_ratio(i) == pytest.approx(S.lin(2.5, 8, 0))
    assert S.accrual_ratio(i) == pytest.approx(S.lin(0.02, 0.08, -0.02))
    netcash = mk(pl={"operating_profit": [0] * 5 + [-5]}, bs={"borrowings": [0] * 5 + [10], "cash": [0] * 5 + [50]})
    assert S.net_debt_ebitda(netcash) == 100
    for fn in (S.cfo_to_pat, S.net_debt_ebitda, S.interest_coverage, S.debt_to_equity):
        assert fn(mk(lender=True)).reason == "lender"


def test_quarterly_scorers_and_gap_guard():
    rev = [100, 100, 100, 100, 110, 110, 110, 110, 121, 121, 121, 121]
    i = mk(q={"revenue": rev, "net_profit": rev})
    assert S.quarterly_revenue_growth(i) == pytest.approx(S.lin(10, -10, 25))
    assert S.quarterly_revenue_volatility(i) == pytest.approx(100)    # constant 10% growth: no variation
    gap = mk(q={"revenue": rev})
    gap.qends[5] = "2030-01-31"
    assert S.quarterly_revenue_growth(gap).reason == "no_data"        # a gap in the quarters: not worked out
    assert S.seasonality(mk(q={"revenue": [100] * 12})) == pytest.approx(100)
    assert S.seasonality(mk(q={"revenue": [10, 10, 10, 70] * 3})) == 0


def test_segment_scorers():
    two = mk(segments=[{"sharePct": 50, "growthPct": 10}, {"sharePct": 50, "growthPct": 20}])
    assert S.segment_growth(two) == pytest.approx(S.lin(15, -5, 20))
    assert S.segment_concentration(two) == pytest.approx(S.lin(0.5, 0.95, 0.35))
    assert S.segment_growth(mk(segments=[{"sharePct": 100, "growthPct": 5}])).reason == "no_data"


def test_registry_adds_up():
    for kind, gs in GROUPS.items():
        assert sum(g.weight for g in gs) == 100
        assert all(sum(p.weight for p in g.params) == g.weight for g in gs)
    assert [g.weight for g in GROUPS["profit"]] == [25, 15, 15, 10, 10, 10, 5, 5, 5]
    assert [g.weight for g in GROUPS["revenue"]] == [25, 15, 15, 10, 10, 10, 10, 5]


def test_weights_validation():
    d = default_weights("profit")
    assert C.validate_weights("profit", None) == d
    custom = {**d, "A": 35, "B": 5}
    assert C.validate_weights("profit", custom)["A"] == 35
    for bad in ({**d, "A": 30}, {**d, "Z": 1}, {k: v for k, v in d.items() if k != "A"}, {**d, "A": -5, "B": 35}, {**d, "A": float("nan")}, {**d, "A": 101}):
        with pytest.raises(C.WeightError):
            C.validate_weights("profit", bad)
    assert C.validate_weights("profit", {**d, "A": 25.004})["A"] == 25.004   # within 0.01


def test_bands_follow_the_site_rule():
    assert C.band(70)["color"] == "green" and C.band(69.9)["color"] == "orange" and C.band(50)["color"] == "orange" and C.band(49.9)["color"] == "red"
    assert C.band(None)["key"] == "na"


def test_renormalisation_and_the_fifty_percent_rule(reliance_sections):
    inp = build_inputs(reliance_sections["summary"], reliance_sections["financials"], reliance_sections["ratios"], reliance_sections["segments"])
    w = default_weights("revenue")
    res = C.compose("revenue", inp, w)
    live = [g for g in res["groups"] if g["score"] is not None]
    assert sum(g["effectiveWeightPct"] for g in live) == pytest.approx(100, abs=0.05)       # weights of groups without data are redistributed
    unavailable = [g for g in res["groups"] if g["status"] == "unavailable"]
    assert {g["letter"] for g in unavailable} == {"C", "E", "G"} and all(g["reason"] and g["weightPct"] and g["effectiveWeightPct"] == 0 for g in unavailable)
    expected = sum(g["weightPct"] * g["score"] for g in live) / sum(g["weightPct"] for g in live)
    assert res["score"]["value"] == pytest.approx(expected, abs=0.1)
    # all weight on groups with no data: no score, with a reason
    only_c = {k: (100.0 if k == "C" else 0.0) for k in w}
    r2 = C.compose("revenue", inp, only_c)
    assert r2["score"]["value"] is None and "Only 0%" in r2["score"]["reason"] and r2["_raw_score"] is None
    # a company with no segments: revenue measurable weight drops under 50%
    bare = build_inputs(reliance_sections["summary"], reliance_sections["financials"], reliance_sections["ratios"], None)
    r3 = C.compose("revenue", bare, w)
    assert r3["score"]["value"] is None and r3["coverage"]["weightPct"] < 50


def test_lender_profit_tab_says_so():
    summary = {"dataQuality": {"isBank": True}}
    n = 6
    fin = {"yearly": {"pl": {"periods": [f"FY{k}" for k in range(n)], "rows": {"revenue": [100.0 * (1.1 ** k) for k in range(n)], "net_profit": [10.0 * (1.12 ** k) for k in range(n)],
                                                                         "profit_before_tax": [13.0] * n, "tax": [3.0] * n, "exceptional_items": [0.0] * n}},
                       "bs": {"periods": [f"FY{k}" for k in range(n)], "rows": {"total_assets": [1000.0] * n}}, "cf": {}}, "quarterly": {}}
    inp = build_inputs(summary, fin, {}, None)
    res = C.compose("profit", inp, default_weights("profit"))
    by = {g["letter"]: g for g in res["groups"]}
    assert inp.lender and by["E"]["status"] == "unavailable" and "banks and lenders" in by["E"]["reason"]
    assert by["D"]["status"] == "unavailable" and by["A"]["coverage"]["measured"] == 1     # only net margin stays in A
    assert res["score"]["value"] is None and "Banks and lenders" in res["score"]["reason"]  # too little of the model applies: no invented number


def test_range_is_deterministic_bounded_and_honest(reliance_sections):
    inp = build_inputs(reliance_sections["summary"], reliance_sections["financials"], reliance_sections["ratios"], reliance_sections["segments"])
    a, b = growth_range("revenue", inp, 60), growth_range("revenue", inp, 60)
    assert a == b and a["available"] and a["low"] < a["mid"] < a["high"]
    assert growth_range("revenue", inp, 90)["mid"] > growth_range("revenue", inp, 10)["mid"]      # the score tilts the middle
    assert growth_range("revenue", inp, None)["tilted"] is False
    t = sum(inp.qv("revenue", k) for k in range(4))
    t0 = sum(inp.qv("revenue", k + 4) for k in range(4))
    assert a["baselineAmountCr"] == round(t) and a["baselineQuarter"] == inp.qp[-1]
    assert growth_range("revenue", inp, None)["mid"] == pytest.approx(((t / t0 - 1) * 100 + S.cagr(inp.y("revenue"), inp.y("revenue", 3), 3)) / 2, abs=0.1)
    # capped
    wild = mk(q={"net_profit": [10, 10, 10, 10, 100, 100, 100, 100, 1000, 1000, 1000, 1000]}, pl={"net_profit": [1, 2, 4, 8, 16, 32]})
    r = growth_range("profit", wild, 100)
    assert r["available"] and r["high"] == 60.0 and "high" in r["capped"] and "60" in r["cappedNote"]
    # honest empty states
    assert "Not enough history for a range" in growth_range("profit", mk(q={"net_profit": [1] * 6}, nq=6), 50)["reason"]
    assert "not positive" in growth_range("profit", mk(q={"net_profit": [-1] * 12}), 50)["reason"]


def test_reliance_regression_and_no_detail_leak(reliance_sections):
    for kind in ("profit", "revenue"):
        r = build_response(kind, default_weights(kind), False, reliance_sections, "RELIANCE", "standalone")
        text = json.dumps(r).lower()
        for banned in ("threshold", "formula", "ebitda_margin", "pat_cagr", "cfo_pat", "order_book", "params", "lo\":", "hi\":"):
            assert banned not in text
        assert r["score"]["value"] is not None and r["range"]["available"] and r["coverage"]["measured"] < r["coverage"]["total"]
    p = build_response("profit", default_weights("profit"), False, reliance_sections, "RELIANCE", "standalone")
    assert p["coverage"] == {"measured": 27, "total": 30, "weightPct": 89.0} and p["score"]["value"] == pytest.approx(52.6, abs=0.1)
    assert p["asOf"] == {"yearly": "FY26", "quarterly": "Jun 2026"}


# -------------------------------------------------------------------------------------------------------------- API
@pytest.mark.integration
async def test_outlook_is_gold_only_and_validates(app, anon):  # noqa: F811
    body = {"kind": "profit"}
    assert (await anon.post("/api/outlook/RELIANCE", json=body)).status_code == 401
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = await silver.post("/api/outlook/RELIANCE", json=body)
    assert r.status_code == 403 and r.json()["detail"]["plan"] == "gold" and "score" not in r.text
    gold = await signed_in(app, "g@example.com", plan="gold")
    ok = await gold.post("/api/outlook/reliance", json=body)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "private, no-store"
    j = ok.json()
    assert j["symbol"] == "RELIANCE" and j["mode"] == "model" and j["score"]["value"] is not None and len(j["groups"]) == 9
    d = default_weights("profit")
    custom = await gold.post("/api/outlook/RELIANCE", json={"kind": "profit", "weights": {**d, "A": 45, "B": 0, "C": 10}})
    assert custom.status_code == 200 and custom.json()["mode"] == "custom" and custom.json()["score"]["value"] != j["score"]["value"]
    assert (await gold.post("/api/outlook/RELIANCE", json={"kind": "profit", "weights": {**d, "A": 50}})).status_code == 422
    assert (await gold.post("/api/outlook/RELIANCE", json={"kind": "profit", "weights": {**d, "Q": 0}})).status_code == 422
    assert (await gold.post("/api/outlook/RELIANCE", json={"kind": "other"})).status_code == 422
    assert (await gold.post("/api/outlook/NOTSTORED", json=body)).status_code == 404
    assert (await gold.post("/api/outlook/bad%20sym", json=body)).status_code == 400
    again = await gold.post("/api/outlook/RELIANCE", json=body)
    assert again.status_code == 200 and again.json() == j      # second call is served from the short cache with the same body
    for c in (silver, gold):
        await c.aclose()
