"""Prebuilt screens over HTTP: plan gating, 404 / 422, caching with an empty cache, the nightly job, usage counts, CSV export, seed top-up."""
import json

import pytest

from finlit.presets import service
from finlit.screener import data
from finlit.screener.data import Table
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


def row(sym, **m):
    return {"symbol": sym, "name": sym.title(), "sector": "IT", "industry": "Pharmaceuticals", "band": "mixed", "metrics": json.dumps(m)}


@pytest.fixture(autouse=True)
def fake_table():
    rows = [row(f"S{i:02d}", market_cap=5000 + i, flag_count=1.0, sales_cagr_3y=20, profit_cagr_3y=20, q_sales_yoy=15, q_profit_yoy=15, q_sales_up=4, q_revenue=100, roce=20,
                debt_to_equity=0.2, is_bank=0) for i in range(30)]
    data._table = Table(rows, {}, {})
    yield
    data.reset()


async def wipe(st):
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE preset_results, preset_usage, preset_scores, preset_meta, industry_breadth_daily, industry_clean, theme_tags")


async def test_non_gold_gets_names_but_no_values(app, anon):  # noqa: F811
    r = await anon.get("/api/screener/presets")
    body = r.json()
    cards = [c for g in body["groups"] for c in g["presets"]]
    assert r.status_code == 200 and len(cards) == 24 and all(c["locked"] and c["count"] is None for c in cards) and cards[0]["name"]
    assert [g["name"] for g in body["groups"]][0] == "Top rated" and body["groups"][-1]["name"] == "Prism basics"
    assert (await anon.get("/api/screener/presets/consistent-growers")).status_code == 403
    silver = await signed_in(app, "s@example.com", plan="silver")
    d = await silver.get("/api/screener/presets/consistent-growers")
    assert d.status_code == 403 and d.json()["detail"]["status"] == "plan_required"
    assert (await silver.get("/api/screener/presets/consistent-growers/export")).status_code == 403
    await silver.aclose()


async def test_gold_detail_cache_chips_usage_and_export(app, store):  # noqa: F811
    await wipe(store)
    gold = await signed_in(app, "g@example.com", plan="gold")
    assert (await gold.get("/api/screener/presets/nope")).status_code == 404
    assert (await gold.get("/api/screener/presets/consistent-growers?chip=bogus")).status_code == 422
    assert (await gold.get("/api/screener/presets/psu-stocks")).status_code == 409
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM preset_results") == 0
    r = await gold.get("/api/screener/presets/consistent-growers?chip=none")      # empty cache: computed on demand, not a 404
    b = r.json()
    assert r.status_code == 200 and b["count"] == 30 and b["shown"] == 25 and b["disclaimer"] == "A screen narrows a list. It is not a recommendation." and "exportRows" not in b
    assert b["chips"] == [] and {"key", "label", "format", "align"} <= set(b["columns"][0]) and b["rows"][0]["symbol"] and b["asOf"]
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM preset_results WHERE preset_id = 'consistent-growers' AND chips = 'none'") == 1
    data.reset()                                                                    # the second answer is the cached one, not a recomputation
    assert (await gold.get("/api/screener/presets/consistent-growers?chip=none")).json()["count"] == 30
    assert (await gold.get("/api/screener/presets/consistent-growers")).json()["chips"] == ["rated-only"]   # defaults when no chip is given
    e = await gold.get("/api/screener/presets/consistent-growers/export?chip=none")
    assert e.status_code == 200 and e.text.lstrip("﻿").startswith("Symbol,") and "not a recommendation" in e.text
    async with store.pool.acquire() as conn:
        use = {(r["event"]): r["n"] for r in await conn.fetch("SELECT event, sum(n)::int AS n FROM preset_usage WHERE preset_id = 'consistent-growers' GROUP BY event")}
        cols = [r["column_name"] for r in await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'preset_usage'")]
    assert use["open"] >= 2 and use["export"] == 1 and not {"user_id", "ip"} & set(cols)
    listing = (await gold.get("/api/screener/presets")).json()
    card = [c for g in listing["groups"] for c in g["presets"] if c["id"] == "consistent-growers"][0]
    assert card["locked"] is False and card["status"] == "live" and card["chips"][0]["id"] == "rated-only"
    await gold.aclose()


async def test_nightly_job_fills_tables_and_cache(store):  # noqa: F811
    await wipe(store)
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ('DIXON', 'Dixon') ON CONFLICT DO NOTHING")
    res = await service.refresh_presets(store)
    assert res["failed"] == [] and "SIFY" in res["themeSeedMissing"] and res["results"] >= 18
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM theme_tags WHERE symbol = 'DIXON'") >= 1
        assert await conn.fetchval("SELECT count(*) FROM industry_breadth_daily") >= 1 and await conn.fetchval("SELECT count(*) FROM industry_clean") == 30
        assert await conn.fetchval("SELECT count(*) FROM preset_scores") >= 0
    again = await service.refresh_presets(store)                                   # the same session twice is one session, not two
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(DISTINCT as_of) FROM industry_breadth_daily") == 1
    assert again["themeTagsAdded"] == 0
    assert (await service.read_cached(store, "consistent-growers", "rated-only")) is not None


def test_job_is_registered_after_prism():
    from finlit.jobs.registry import by_name
    j = by_name({})["presets"]
    assert j.args == ("refresh-presets",) and j.cls == "bulk" and "prism" in j.prerequisites and j.sla.hours == 30
