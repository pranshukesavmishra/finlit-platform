"""Graph Studio saved views: plan limits are enforced when a view is saved, and the front-end copy of the limits matches."""

import re
from pathlib import Path

import pytest

from finlit import graphviews as gv
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, store  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def fresh_table(store):  # noqa: F811
    """The shared fixture drops `users ... CASCADE` but not this table, so an older copy would survive without its foreign key."""
    async with store.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS graph_views")
        await conn.execute((Path(gv.__file__).parent / "migrations" / "028_graph_views.sql").read_text())


def cfg(layout="2x2", cells=None, **kw):
    cells = cells if cells is not None else [{"chart": "line", "series": [{"s": "reliance", "m": "revenue"}, {"s": "TCS", "m": "net_profit", "as": "bar"}]}]
    return {"config": {"v": 1, "layout": layout, "basis": "annual", "range": "5Y", "cells": cells, **kw}}


def test_front_end_limits_match_the_server():
    ts = (Path(__file__).parents[2] / "frontend/src/lib/graphLimits.ts").read_text()
    found = {}
    for m in re.finditer(r"^\s{2}(basic|silver|gold): \{ cells: (\d+), companies: (\d+), series: (\d+), views: (\d+), charts: \[([^\]]*)\] \}", ts, re.M):
        found[m[1]] = {"cells": int(m[2]), "companies": int(m[3]), "series": int(m[4]), "views": int(m[5]), "charts": re.findall(r'"([a-z]+)"', m[6])}
    assert found == gv.GRAPH_LIMITS


def test_every_plan_offers_only_known_charts_and_layouts():
    for plan, lim in gv.GRAPH_LIMITS.items():
        assert set(lim["charts"]) <= set(gv.CHARTS)
        assert lim["cells"] in gv.LAYOUTS.values(), plan


async def test_signed_out_cannot_use_saved_views(app):  # noqa: F811
    c = new_client(app)
    assert (await c.get("/api/me/graph-views")).status_code == 401
    await c.aclose()


async def test_save_load_overwrite_delete(app):  # noqa: F811
    c = await signed_in(app, "gv1@example.com")
    r = await c.put("/api/me/graph-views/My%20view", json=cfg())
    assert r.status_code == 200 and r.json()["name"] == "My view"
    body = (await c.get("/api/me/graph-views")).json()
    assert body["plan"] == "basic" and body["limits"]["views"] == 2
    assert [v["name"] for v in body["views"]] == ["My view"]
    saved = body["views"][0]["config"]
    assert saved["cells"][0]["series"][0] == {"s": "RELIANCE", "m": "revenue"}            # symbol cleaned
    assert saved["cells"][0]["series"][1]["as"] == "bar"
    r = await c.put("/api/me/graph-views/My%20view", json=cfg("1x1", cells=[{"chart": "area", "series": []}]))   # same name replaces
    assert r.status_code == 200 and len((await c.get("/api/me/graph-views")).json()["views"]) == 1
    assert (await c.delete("/api/me/graph-views/My%20view")).status_code == 200
    assert (await c.get("/api/me/graph-views")).json()["views"] == []
    await c.aclose()


async def test_views_are_private_to_their_owner(app):  # noqa: F811
    a, b = await signed_in(app, "gv2a@example.com"), await signed_in(app, "gv2b@example.com")
    await a.put("/api/me/graph-views/Mine", json=cfg())
    assert (await b.get("/api/me/graph-views")).json()["views"] == []
    await b.delete("/api/me/graph-views/Mine")
    assert len((await a.get("/api/me/graph-views")).json()["views"]) == 1
    await a.aclose(); await b.aclose()


async def test_basic_plan_limits_are_enforced_on_the_server(app):  # noqa: F811
    c = await signed_in(app, "gv3@example.com")
    r = await c.put("/api/me/graph-views/big", json=cfg("3x3"))
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_limit"
    r = await c.put("/api/me/graph-views/sc", json=cfg(cells=[{"chart": "scatter", "series": []}]))
    assert r.status_code == 403 and "scatter" in r.json()["detail"]["detail"]
    four = [{"s": "A", "m": "revenue"}, {"s": "A", "m": "net_profit"}, {"s": "A", "m": "eps"}, {"s": "A", "m": "pe"}]
    assert (await c.put("/api/me/graph-views/many", json=cfg(cells=[{"chart": "line", "series": four}]))).status_code == 403
    three_co = [{"s": s, "m": "revenue"} for s in ("AAA", "BBB", "CCC")]
    assert (await c.put("/api/me/graph-views/co", json=cfg(cells=[{"chart": "line", "series": three_co[:2]}, {"chart": "line", "series": three_co[2:]}]))).status_code == 403
    assert (await c.put("/api/me/graph-views/v1", json=cfg())).status_code == 200
    assert (await c.put("/api/me/graph-views/v2", json=cfg())).status_code == 200
    r = await c.put("/api/me/graph-views/v3", json=cfg())                    # a third new name is over the Basic limit of two
    assert r.status_code == 403 and "2 saved views" in r.json()["detail"]["detail"]
    assert (await c.put("/api/me/graph-views/v2", json=cfg())).status_code == 200   # replacing an existing one is fine
    await c.aclose()


async def test_gold_gets_every_chart_and_layout(app):  # noqa: F811
    c = await signed_in(app, "gv4@example.com", plan="gold")
    cells = [{"chart": ch, "series": [{"s": "RELIANCE", "m": "price"}]} for ch in gv.CHARTS]
    r = await c.put("/api/me/graph-views/all", json=cfg("3x3", cells=cells))
    assert r.status_code == 200, r.text
    await c.aclose()


async def test_malformed_views_are_refused(app):  # noqa: F811
    c = await signed_in(app, "gv5@example.com", plan="gold")
    for bad in (cfg("5x5"), cfg(cells=[{"chart": "radar", "series": []}]), cfg(cells=[{"chart": "line", "series": [{"s": "../x", "m": "revenue"}]}]),
                cfg(cells=[{"chart": "line", "series": [{"s": "TCS", "m": "Robert'); DROP"}]}]), cfg("1x2", cells=[{"chart": "line"}] * 3)):
        assert (await c.put("/api/me/graph-views/x", json=bad)).status_code in (403, 422), bad
    assert (await c.put("/api/me/graph-views/%20", json=cfg())).status_code == 422                # empty name
    assert (await c.put("/api/me/graph-views/" + "n" * 61, json=cfg())).status_code == 422
    assert (await c.get("/api/me/graph-views")).json()["views"] == []
    await c.aclose()


async def test_deleting_the_account_removes_views(app):  # noqa: F811
    c = await signed_in(app, "gv6@example.com")
    await c.put("/api/me/graph-views/Mine", json=cfg())
    async with app.state.store.pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE lower(email) = 'gv6@example.com'")
        assert await conn.fetchval("SELECT count(*) FROM graph_views WHERE user_id = $1", uid) == 1
        await conn.execute("DELETE FROM users WHERE id = $1", uid)
        assert await conn.fetchval("SELECT count(*) FROM graph_views WHERE user_id = $1", uid) == 0
    await c.aclose()


async def test_index_series_are_saved_and_do_not_count_as_companies(app):  # noqa: F811
    c = await signed_in(app, "gv3@example.com")
    body = cfg(cells=[{"chart": "line", "series": [{"s": "idx:nif50", "m": "price"}, {"s": "TCS", "m": "price"}, {"s": "INFY", "m": "price"}]}])
    assert (await c.put("/api/me/graph-views/Idx", json=body)).status_code == 200      # basic plan: 2 companies + an index
    saved = (await c.get("/api/me/graph-views")).json()["views"][0]["config"]
    assert saved["cells"][0]["series"][0]["s"] == "IDX:NIF50"
    bad = cfg(cells=[{"chart": "line", "series": [{"s": "IDX:", "m": "price"}]}])
    assert (await c.put("/api/me/graph-views/Bad", json=bad)).status_code == 422
    await c.aclose()
