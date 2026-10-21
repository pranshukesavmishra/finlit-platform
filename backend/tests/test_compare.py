"""Custom comparison: every selected measure comes back for every company, plan limits are enforced on the server, saved sets."""

import json

import pytest

from finlit.screener import data as screener_data
from finlit.screener.catalog import CATALOG
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration


async def seed(app):
    metrics = {
        "AAA": {"market_cap": 5000, "price": 100.5, "pe": 12.5, "pb": 2.1, "roe": 18.25, "debt_to_equity": 0.4, "overall": 71, "net_debt": -300},
        "BBB": {"market_cap": 900, "price": 40, "pe": 30, "roe": 6, "debt_to_equity": 1.9},   # no P/B, no model score, no net debt
        "CCC": {"market_cap": 100, "price": 5, "roe": 9},
    }
    async with app.state.store.pool.acquire() as conn:
        for s, m in metrics.items():
            await conn.execute("INSERT INTO scores (symbol, statement, model, sector, metrics) VALUES ($1, 'consolidated', 'v1', 'Test', $2::jsonb) "
                               "ON CONFLICT (symbol, statement, model) DO UPDATE SET metrics = EXCLUDED.metrics", s, json.dumps(m))
    screener_data.reset()


async def test_every_metric_for_every_company(app):  # noqa: F811
    await seed(app)
    gold = await signed_in(app, "gcmp@example.com", plan="gold")
    keys = [m.key for m in CATALOG]
    r = await gold.post("/api/compare/metrics", json={"symbols": ["aaa", "BBB", "CCC", "ZZZ"], "keys": keys})
    assert r.status_code == 200, r.text
    j = r.json()
    assert [c["symbol"] for c in j["companies"]] == ["AAA", "BBB", "CCC", "ZZZ"]
    assert [m["key"] for m in j["metrics"]] == keys
    for k in keys:                                                   # a cell for every company, a number or a reason, never both
        assert set(j["values"][k]) == {"AAA", "BBB", "CCC", "ZZZ"}
        for cell in j["values"][k].values():
            assert (cell["v"] is None) != (cell["why"] is None)
    assert j["values"]["pe"]["AAA"]["v"] == 12.5 and j["values"]["roe"]["AAA"]["v"] == 18.25 and j["values"]["net_debt"]["AAA"]["v"] == -300
    assert j["values"]["pb"]["BBB"]["v"] is None and "not meaningful" in j["values"]["pb"]["BBB"]["why"].lower()
    assert j["values"]["overall"]["BBB"]["v"] is None and j["values"]["pe"]["ZZZ"]["why"] == "This company is not in the FinLit list yet"
    assert next(c for c in j["companies"] if c["symbol"] == "ZZZ")["known"] is False
    meta = {m["key"]: m for m in j["metrics"]}
    assert meta["pe"]["better"] == "lower" and meta["roe"]["better"] == "higher" and meta["pe"]["unit"] == "x" and meta["pe"]["groupLabel"] == "Valuation"


async def test_plan_gate_and_limits(app):  # noqa: F811
    await seed(app)
    async with new_client(app) as anon:
        ok = await anon.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB"], "keys": ["pe", "roe"]})
        assert ok.status_code == 200 and ok.json()["plan"] == "basic"
        no = await anon.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB"], "keys": ["pe", "pb"]})        # P/B is Silver
        assert no.status_code == 403 and no.json()["detail"]["plan"] == "silver" and no.json()["detail"]["keys"] == ["pb"]
        assert (await anon.post("/api/compare/metrics", json={"symbols": ["AAA"], "keys": ["overall"]})).status_code == 403
        assert (await anon.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB", "CCC"], "keys": ["pe"]})).status_code == 403   # Basic compares 2
        assert (await anon.post("/api/compare/metrics", json={"symbols": ["AAA"], "keys": ["nonsense"]})).status_code == 422
        assert (await anon.post("/api/compare/metrics", json={"symbols": ["AAA"], "keys": []})).status_code == 422
        assert (await anon.post("/api/compare/metrics", json={"symbols": ["bad symbol!"], "keys": ["pe"]})).status_code == 422
    silver = await signed_in(app, "scmp@example.com", plan="silver")
    assert (await silver.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB"], "keys": ["pe", "pb", "net_debt"]})).status_code == 200
    assert (await silver.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB"], "keys": ["overall"]})).status_code == 403   # FinLit model is Gold
    assert (await silver.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB", "CCC"], "keys": ["pe"]})).status_code == 403
    gold = await signed_in(app, "gcmp2@example.com", plan="gold")
    assert (await gold.post("/api/compare/metrics", json={"symbols": ["AAA", "BBB", "CCC"], "keys": ["overall"]})).status_code == 200


async def test_saved_sets(app):  # noqa: F811
    async with new_client(app) as anon:
        assert (await anon.get("/api/compare/sets")).status_code == 401
    basic = await signed_in(app, "bcmp@example.com")
    assert (await basic.put("/api/compare/sets", json={"sets": []})).status_code == 403          # saving to the account is Silver and up
    silver = await signed_in(app, "scmp2@example.com", plan="silver")
    body = {"sets": [{"name": "Value", "keys": ["pe", "pb", "ev_cfo"]}]}
    assert (await silver.put("/api/compare/sets", json=body)).status_code == 200
    got = (await silver.get("/api/compare/sets")).json()
    assert got["sets"] == body["sets"] and got["limit"] == 10
    assert (await silver.put("/api/compare/sets", json={"sets": [{"name": "X", "keys": ["nope"]}]})).status_code == 422
    assert (await silver.put("/api/compare/sets", json={"sets": [{"name": "A", "keys": ["pe"]}, {"name": "a", "keys": ["pb"]}]})).status_code == 422
    assert (await silver.put("/api/compare/sets", json={"sets": [{"name": f"S{i}", "keys": ["pe"]} for i in range(11)]})).status_code == 403
    assert (await silver.put("/api/compare/sets", json={"sets": []})).status_code == 200
