import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from finlit import indices, premium
from finlit.finedge import FinEdgeClient, fixture_transport

FIX = Path(__file__).parent / "fixtures" / "finedge"


class FakeRedis:
    def __init__(self): self.d = {}
    async def get(self, k): return self.d.get(k)
    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.d: return None
        self.d[k] = v; return True
    async def delete(self, k): self.d.pop(k, None)


def make(plan="gold"):
    app = FastAPI()
    app.include_router(indices.router)
    app.state.store = SimpleNamespace(redis=FakeRedis())
    app.state.settings = SimpleNamespace()
    client = FinEdgeClient(SimpleNamespace(finedge_mode="live", finedge_api_key="k", finedge_base_url="https://data.example/api/v1", finedge_concurrency=4),
                           transport=fixture_transport())
    app.state.index_client = client
    def gate():   # the real plan rule, without a database session
        return _check(plan)
    app.dependency_overrides[premium.premium_ctx] = gate
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _check(plan):
    from finlit.auth.entitlements import has
    from finlit.auth.routes import fail
    if not has(plan or "free", "gold"):
        raise fail(403, "plan_required", "Gold only.", plan="gold")
    return SimpleNamespace(role="investor", plan=plan)


def test_feed_shape_names_groups_and_key_order():
    out = indices.shape_feed(json.loads((FIX / "index_daily_feed.json").read_text()))
    items = {x["code"]: x for x in out["items"]}
    assert len(out["items"]) == 229 and out["key"][:3] == ["NIF50", "SNSXSENSEX", "NIFBAN"]
    assert [x["code"] for x in out["items"][:3]] == ["NIF50", "SNSXSENSEX", "NIFBAN"]
    assert items["NIF50"]["group"] == "Broad market" and items["NIFBAN"]["group"] == "Sector" and items["INDVIX"]["group"] == "Volatility"
    assert items["NIFIT"]["group"] == "Sector" and items["NIFMID100"]["group"] == "Broad market" and items["SNSXSENSEX"]["exchange"] == "BSE"
    assert items["INDVIX"]["pe"] is None   # the provider sends 0 for 'no P/E'; that must not read as a P/E of zero
    assert items["NIF50"]["close"] > 1000 and items["NIF50"]["pe"] and out["asOf"]


def test_history_is_ascending_trimmed_and_scored():
    raw = json.loads((FIX / "index_valuation_nif50.json").read_text())
    five, one = indices.shape_history(raw, 5), indices.shape_history(raw, 1)
    d = [r["d"] for r in five["rows"]]
    assert d == sorted(d) and len(five["rows"]) > 1000 and 200 < len(one["rows"]) < 280
    s = five["stats"]["pe"]
    assert s["min"] <= s["median"] <= s["max"] and 0 <= s["pctile"] <= 100 and s["now"] == five["rows"][-1]["pe"]


def test_market_hours_are_india_time():
    ist = indices.IST
    assert indices.market_open(datetime(2026, 10, 19, 10, 0, tzinfo=ist)) and not indices.market_open(datetime(2026, 10, 19, 16, 0, tzinfo=ist))
    assert not indices.market_open(datetime(2026, 10, 18, 11, 0, tzinfo=ist))   # Sunday


async def test_prices_are_public_and_second_call_uses_the_saved_copy():
    app, c = make(plan=None)
    a = await c.get("/api/indices")
    assert a.status_code == 200 and a.json()["items"][0]["code"] == "NIF50"
    app.state.index_client = None   # a second call must not need the provider
    b = await c.get("/api/indices")
    assert b.status_code == 200 and b.json()["items"] == a.json()["items"]


async def test_valuation_history_is_gold_only_and_returns_stats():
    _, c = make(plan=None)
    assert (await c.get("/api/indices/NIF50/valuation")).status_code in (401, 403)
    _, c = make()
    r = await c.get("/api/indices/NIF50/valuation?years=3")
    body = r.json()
    assert r.status_code == 200 and body["name"] == "Nifty 50" and body["years"] == 3 and body["stats"]["pe"]["median"] > 0
    assert (await c.get("/api/indices/bad code!/valuation")).status_code in (400, 404)
    assert (await c.get("/api/indices/NIFIT/valuation")).status_code in (404, 502)   # no recorded history for it


async def test_level_history_is_public_ascending_and_cached():
    app, c = make(plan=None)
    r = await c.get("/api/indices/NIF50/history?years=1")
    b = r.json()
    d = [x["d"] for x in b["rows"]]
    assert r.status_code == 200 and b["unit"] == "points" and b["name"] == "Nifty 50" and d == sorted(d) and 200 < len(d) < 280 and b["rows"][-1]["c"] > 1000
    client, app.state.index_client = app.state.index_client, None   # served from the saved copy
    assert (await c.get("/api/indices/NIF50/history?years=5")).json()["rows"][0]["d"] < d[0]
    app.state.index_client = client
    assert (await c.get("/api/indices/bad code!/history")).status_code in (400, 404)
    assert (await c.get("/api/indices/NIFIT/history")).status_code in (404, 502)
