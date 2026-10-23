"""DCF calculator, server side (finlit/dcf.py): a company's inputs from its stored report, Gold-only access, and saved scenarios."""

import pytest

from finlit import dcf
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
INPUTS = {"fcf0": 100, "r": 12, "g1": 10, "g2": 10, "gT": 5, "marketCap": 2000, "price": 100, "netDebt": 1000, "mos": 4}


def test_company_inputs_from_the_stored_report(reliance_sections):
    c = dcf.company_inputs(reliance_sections["summary"], reliance_sections["financials"])
    cf, bs = reliance_sections["financials"]["yearly"]["cf"], reliance_sections["financials"]["yearly"]["bs"]
    fcf = cf["rows"]["free_cash_flow"]
    assert c["fcf"]["latest"] == {"period": cf["periods"][-1], "fcf": fcf[-1], "operating": cf["rows"]["operating"][-1], "capex": cf["rows"]["capex"][-1]}
    assert c["fcf"]["latest"]["fcf"] == pytest.approx(c["fcf"]["latest"]["operating"] + c["fcf"]["latest"]["capex"], abs=0.01)   # FCF = CFO − capex
    assert c["fcf"]["avg3"] == pytest.approx(sum(fcf[-3:]) / 3)
    assert c["fcf"]["cagr3"] == pytest.approx(((fcf[-1] / fcf[-4]) ** (1 / 3) - 1) * 100)
    assert c["netDebt"]["value"] == pytest.approx(bs["rows"]["borrowings"][-1] - bs["rows"]["cash"][-1])
    assert c["netDebt"]["investments"] == bs["rows"]["investments"][-1] and c["netDebt"]["period"] == bs["periods"][-1]
    q = reliance_sections["summary"]["quote"]
    assert c["price"] == q["price"] and c["marketCap"] == q["marketCapCr"]
    assert c["shares"]["implied"] == pytest.approx(q["marketCapCr"] / q["price"])
    assert c["shares"]["diluted"] == reliance_sections["financials"]["yearly"]["pl"]["rows"]["diluted_shares_cr"][-1]
    assert c["isBank"] is False and c["unit"] == "₹ crore"


def test_growth_is_only_measured_between_positive_years_and_lenders_are_flagged():
    assert dcf.cagr(100, 200, 3) == pytest.approx((2 ** (1 / 3) - 1) * 100)
    assert dcf.cagr(-10, 200, 3) is None and dcf.cagr(100, -5, 3) is None and dcf.cagr(None, 1, 3) is None
    summary = {"quote": {"price": 50, "marketCapCr": 500}, "profile": {"name": "A Bank"}, "dataQuality": {"isBank": True}, "meta": {"symbol": "ABANK"}}
    fin = {"yearly": {"cf": {"periods": ["FY25", "FY26"], "rows": {"free_cash_flow": [10, -40]}}, "bs": {}, "pl": {}}}
    c = dcf.company_inputs(summary, fin)
    assert c["isBank"] and any("lender" in n for n in c["notes"]) and any("negative" in n for n in c["notes"])
    assert c["netDebt"]["value"] is None and c["shares"]["diluted"] is None and c["shares"]["implied"] == 10


async def test_the_calculator_data_is_gold_only(app, anon):  # noqa: F811
    assert (await anon.get("/api/dcf/company/RELIANCE")).status_code == 401
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = await silver.get("/api/dcf/company/RELIANCE")
    assert r.status_code == 403 and r.json()["detail"]["plan"] == "gold"
    assert (await silver.put("/api/dcf/scenarios/x", json={"inputs": INPUTS})).status_code == 403
    gold = await signed_in(app, "g@example.com", plan="gold")
    body = (await gold.get("/api/dcf/company/reliance")).json()
    assert body["symbol"] == "RELIANCE" and body["fcf"]["latest"]["fcf"] and body["price"] > 0 and body["statement"] in ("consolidated", "standalone")
    assert (await gold.get("/api/dcf/company/NOTSTORED")).status_code == 404
    assert (await gold.get("/api/dcf/company/bad%20sym")).status_code == 400
    for c in (silver, gold):
        await c.aclose()


async def test_saved_scenarios_round_trip_are_private_and_limited(app):  # noqa: F811
    gold = await signed_in(app, "g@example.com", plan="gold")
    other = await signed_in(app, "h@example.com", plan="gold")
    assert (await gold.put("/api/dcf/scenarios/Reliance base", json={"inputs": INPUTS, "symbol": "reliance", "note": "first look"})).status_code == 200
    assert (await gold.put("/api/dcf/scenarios/Reliance base", json={"inputs": {**INPUTS, "r": 11}})).status_code == 200   # replaced, not duplicated
    got = (await gold.get("/api/dcf/scenarios")).json()["scenarios"]
    assert len(got) == 1 and got[0]["inputs"]["r"] == 11 and got[0]["name"] == "Reliance base"
    assert (await other.get("/api/dcf/scenarios")).json()["scenarios"] == []                                   # private to the owner
    bad = {**INPUTS, "r": "NaN"}
    assert (await gold.put("/api/dcf/scenarios/x", json={"inputs": bad})).status_code == 422
    assert (await gold.put("/api/dcf/scenarios/" + "n" * 81, json={"inputs": INPUTS})).status_code == 422
    no_csrf = new_client(app, cookies=gold.cookies)
    assert (await no_csrf.put("/api/dcf/scenarios/y", json={"inputs": INPUTS}, headers=ORIGIN)).status_code == 403   # writes need the CSRF token
    for k in range(1, dcf.MAX_SCENARIOS):
        assert (await gold.put(f"/api/dcf/scenarios/s{k}", json={"inputs": INPUTS})).status_code == 200
    r = await gold.put("/api/dcf/scenarios/one too many", json={"inputs": INPUTS})
    assert r.status_code == 403 and r.json()["detail"]["status"] == "limit"
    assert (await gold.delete("/api/dcf/scenarios/Reliance base")).status_code == 200
    assert len((await gold.get("/api/dcf/scenarios")).json()["scenarios"]) == dcf.MAX_SCENARIOS - 1
    for c in (gold, other, no_csrf):
        await c.aclose()
