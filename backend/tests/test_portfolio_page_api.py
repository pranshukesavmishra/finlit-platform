"""POST /api/portfolio/page end to end: names only (422), plan gating, the page object for a stored list, one score with the Diversification card, the cache."""
from datetime import datetime

import pytest

from finlit.diversification import api as div_api
from finlit.indices import IST
from finlit.portfolio_page import api as pf_api
from test_auth import app, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401
from test_diversification_calc import SAMPLE
from test_diversification_api import seed, _clock  # noqa: F401  (seed data + fixed clock)

pytestmark = pytest.mark.integration
URL = "/api/portfolio/page"


async def test_only_share_names_are_accepted(app):  # noqa: F811
    silver = await signed_in(app, "s422@example.com", plan="silver")
    base = {"symbols": ["TCS", "INFY", "HCLTECH"]}
    for extra in ({"quantity": [10, 5, 1]}, {"amount": 5000}, {"price": 3500.5}, {"date": "2026-01-01"}, {"qty": 1}, {"weights": [1, 1, 1]}):
        assert (await silver.post(URL, json={**base, **extra})).status_code == 422, extra
    assert (await silver.post(URL, json={"symbols": [{"symbol": "TCS", "qty": 3}]})).status_code == 422
    assert (await silver.post(URL, json={"symbols": []})).status_code == 422
    assert (await silver.post(URL, json={"symbols": ["bad symbol!"]})).status_code == 422
    assert (await silver.post(URL, json={"symbols": [f"S{i}" for i in range(501)]})).status_code == 422


async def test_plan_gating(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as anon:
        assert (await anon.post(URL, json={"symbols": SAMPLE})).status_code in (401, 403)
    basic = await signed_in(app, "b@example.com", plan="basic")
    r = await basic.post(URL, json={"symbols": SAMPLE})
    assert r.status_code == 403 and "plan_required" in r.text
    silver = await signed_in(app, "s@example.com", plan="silver")
    j = (await silver.post(URL, json={"symbols": SAMPLE})).json()
    assert j["page"]["score"]["score"] == 68 and j["styleTilt"]["locked"] == "gold" and "parts" not in j["styleTilt"]
    gold = await signed_in(app, "g@example.com", plan="gold")
    t = (await gold.post(URL, json={"symbols": SAMPLE})).json()["styleTilt"]
    assert len(t["parts"]) == 6 and t["sentence"].startswith("This list leans towards")


async def test_page_for_a_stored_list_and_the_card_agree(app):  # noqa: F811
    await seed(app)
    silver = await signed_in(app, "s2@example.com", plan="silver")
    r = await silver.post(URL, json={"symbols": [s.lower() for s in SAMPLE] + ["ZZUNKNOWN", "NEWCO"]})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "private, no-store"
    j = r.json()
    page = j["page"]
    assert j["unknown"] == ["ZZUNKNOWN"] and j["symbols"][-1] == "NEWCO" and "NEWCO" in page["short_history"] and "NEWCO" not in page["order"]
    assert page["to"] == "2026-10-30" and page["weeks"] == 104 and page["layout"] == "long" and page["together_open_by_default"] is False   # 16 shares
    assert set(j["meta"]["TCS"]) == {"name", "sector", "size", "mcap_cr"} and j["meta"]["TCS"]["size"] == "L"
    assert len(page["summary"]["eq"]) <= 5 and all(x["text"] for x in page["summary"]["eq"])
    card = (await silver.post("/api/diversification", json={"symbols": SAMPLE + ["NEWCO"]})).json()
    clean = (await silver.post(URL, json={"symbols": SAMPLE + ["NEWCO"]})).json()["page"]["score"]
    assert card["score"]["value"] == clean["score"] and card["score"]["band"] == clean["band"]
    assert card["score"]["coMovement"] == clean["comovement"] and card["score"]["sectorSpread"] == clean["sector_spread"]
    assert card["headline"]["effectiveStocks"] == clean["effective_stocks"]


async def test_too_few_shares_and_all_unknown(app):  # noqa: F811
    await seed(app)
    silver = await signed_in(app, "s3@example.com", plan="silver")
    two = (await silver.post(URL, json={"symbols": ["TCS", "INFY"]})).json()
    assert [x["rule"] for x in two["page"]["readings"]] == ["D3"] and two["page"]["order"] == ["INFY", "TCS"] or len(two["page"]["order"]) == 2
    none = (await silver.post(URL, json={"symbols": ["ZZUNKNOWN"]})).json()
    assert none["page"] is None and none["unknown"] == ["ZZUNKNOWN"] and "styleTilt" not in none


async def test_cache_by_list_and_week(app, monkeypatch):  # noqa: F811
    await seed(app)
    calls = []
    real = pf_api._compute
    monkeypatch.setattr(pf_api, "_compute", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    silver = await signed_in(app, "s4@example.com", plan="silver")
    first = (await silver.post(URL, json={"symbols": SAMPLE})).json()
    again = await silver.post(URL, json={"symbols": list(reversed(SAMPLE))})        # same names in another order: the same entry
    assert again.status_code == 200 and again.json()["page"]["score"] == first["page"]["score"] and len(calls) == 1
    await silver.post(URL, json={"symbols": SAMPLE[:-1]})                           # a changed list is computed afresh
    assert len(calls) == 2
    monkeypatch.setattr(div_api, "now_ist", lambda: datetime(2026, 11, 10, 12, 0, tzinfo=IST))   # the next ISO week: a new entry
    await silver.post(URL, json={"symbols": SAMPLE})
    assert len(calls) == 3
