"""Prebuilt screens over HTTP: plan gating, 404 / 422, caching with an empty cache, the nightly job, usage counts, CSV export, seed top-up."""
import json

import pytest

from finlit.presets import engine, service
from finlit.screener import data
from finlit.screener.data import Table
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


def row(sym, **m):
    return {"symbol": sym, "name": sym.title(), "sector": "Software Products", "industry": "Pharmaceuticals", "band": "mixed", "metrics": json.dumps(m)}


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
    assert r.status_code == 200 and len(cards) == 20 and (await anon.get("/api/screener/presets?tab=basic")).json()["groups"] and all(c["locked"] and c["count"] is None for c in cards) and cards[0]["name"]
    assert [g["name"] for g in body["groups"]][0] == "Top rated" and body["groups"][-1]["name"] == "Prism basics"
    assert (await anon.get("/api/screener/presets/emerging-tech")).status_code == 403
    silver = await signed_in(app, "s@example.com", plan="silver")
    d = await silver.get("/api/screener/presets/emerging-tech")
    assert d.status_code == 403 and d.json()["detail"]["status"] == "plan_required"
    assert (await silver.get("/api/screener/presets/emerging-tech/export")).status_code == 403
    await silver.aclose()


async def test_gold_detail_cache_chips_usage_and_export(app, store):  # noqa: F811
    await wipe(store)
    gold = await signed_in(app, "g@example.com", plan="gold")
    assert (await gold.get("/api/screener/presets/nope")).status_code == 404
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=bogus")).status_code == 422
    assert (await gold.get("/api/screener/presets/psu-stocks")).status_code == 409
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM preset_results") == 0
    r = await gold.get("/api/screener/presets/emerging-tech?chip=none")      # empty cache: computed on demand, not a 404
    b = r.json()
    assert r.status_code == 200 and b["count"] == 30 and b["shown"] == 25 and b["disclaimer"] == "A screen narrows a list. It is not a recommendation." and "exportRows" not in b
    assert b["chips"] == [] and {"key", "label", "format", "align"} <= set(b["columns"][0]) and b["rows"][0]["symbol"] and b["asOf"]
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM preset_results WHERE preset_id = 'emerging-tech' AND chips = 'none'") == 1
    data.reset()                                                                    # the second answer is the cached one, not a recomputation
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=none")).json()["count"] == 30
    assert (await gold.get("/api/screener/presets/emerging-tech")).json()["chips"] == []   # defaults when no chip is given
    e = await gold.get("/api/screener/presets/emerging-tech/export?chip=none")
    assert e.status_code == 200 and e.text.lstrip("﻿").startswith("Symbol,") and "not a recommendation" in e.text
    async with store.pool.acquire() as conn:
        use = {(r["event"]): r["n"] for r in await conn.fetch("SELECT event, sum(n)::int AS n FROM preset_usage WHERE preset_id = 'emerging-tech' GROUP BY event")}
        cols = [r["column_name"] for r in await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'preset_usage'")]
    assert use["open"] >= 2 and use["export"] == 1 and not {"user_id", "ip"} & set(cols)
    listing = (await gold.get("/api/screener/presets")).json()
    card = [c for g in listing["groups"] for c in g["presets"] if c["id"] == "emerging-tech"][0]
    assert card["locked"] is False and card["status"] == "live" and card["chips"][0]["id"] == "show-all-theme"
    await gold.aclose()


async def test_nightly_job_fills_tables_and_cache(store):  # noqa: F811
    await wipe(store)
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name) VALUES ('DIXON', 'Dixon') ON CONFLICT DO NOTHING")
    res = await service.refresh_presets(store)
    assert res["failed"] == [] and res["results"] >= 18
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM industry_breadth_daily") >= 1 and await conn.fetchval("SELECT count(*) FROM industry_clean") == 30
        assert await conn.fetchval("SELECT count(*) FROM preset_scores") >= 0
    again = await service.refresh_presets(store)                                   # the same session twice is one session, not two
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(DISTINCT as_of) FROM industry_breadth_daily") == 1
        assert (await service.read_cached(store, "emerging-tech", engine.chip_key([]))) is not None


def test_job_is_registered_after_prism():
    from finlit.jobs.registry import by_name
    j = by_name({})["presets"]
    assert j.args == ("refresh-presets",) and j.cls == "bulk" and "prism" in j.prerequisites and j.sla.hours == 30


async def test_a_company_page_can_ask_which_top_rated_and_theme_screens_it_is_in(app, store):  # noqa: F811
    await wipe(store)
    gold = await signed_in(app, "badges@example.com", plan="gold")
    silver = await signed_in(app, "badges-s@example.com", plan="silver")
    from finlit.presets.registry import BY_ID
    for pid, syms in (("emerging-tech", ["AAA", "BBB"]), ("highest-rated-large", ["AAA"]), ("consistent-growers", ["AAA", "CCC"])):
        p = BY_ID[pid]
        chips = [c.id for c in p.chips if c.default]
        rows = [{"symbol": x} for x in syms]
        await service.store_result(store, p, {"chips": chips, "asOf": "2026-10-31", "rows": rows[:1], "exportRows": rows, "count": len(rows)})   # the shown list is shorter than the full match
    r = await gold.get("/api/screener/presets/for/bbb")
    d = r.json()
    assert r.status_code == 200 and d["symbol"] == "BBB" and d["ready"] is True and d["asOf"] == "2026-10-31"
    assert [s["id"] for s in d["screens"]] == ["emerging-tech"]                                      # in the full match, though not in the shown rows; the large-cap list does not hold it
    both = (await gold.get("/api/screener/presets/for/AAA")).json()
    assert sorted(s["id"] for s in both["screens"]) == ["emerging-tech", "highest-rated-large"]    # a growth screen is never named on a company page
    assert (await gold.get("/api/screener/presets/for/ZZZ")).json()["screens"] == []                # in none: nothing to say
    assert (await gold.get("/api/screener/presets/for/bad%20one")).status_code == 422
    assert (await silver.get("/api/screener/presets/for/AAA")).status_code == 403                    # the server enforces the plan
    assert (await new_client(app).get("/api/screener/presets/for/AAA")).status_code in (401, 403)
    await wipe(store)
    await store.redis.flushdb()                                                                       # the results are also kept in Redis; this is the test database 15
    assert (await gold.get("/api/screener/presets/for/AAA")).json() == {"symbol": "AAA", "screens": [], "ready": False, "asOf": None}   # before the first nightly run: says it is not ready


async def test_basic_tab_screens_are_silver_and_advanced_stay_gold(app, store):  # noqa: F811
    await wipe(store)
    silver = await signed_in(app, "bs@example.com", plan="silver")
    free = await signed_in(app, "bf@example.com", plan="basic")
    lst = (await silver.get("/api/screener/presets?tab=basic")).json()
    cards = [c for g in lst["groups"] for c in g["presets"]]
    assert lst["tab"] == "basic" and len(cards) == 16 and all(c["tab"] == "basic" and c["locked"] is False for c in cards)
    assert all(c["locked"] for g in (await free.get("/api/screener/presets?tab=basic")).json()["groups"] for c in g["presets"])
    d = await silver.get("/api/screener/presets/basic-emerging-tech")
    assert d.status_code == 200 and d.json()["id"] == "basic-emerging-tech"
    assert (await free.get("/api/screener/presets/basic-top-large")).status_code == 403
    assert (await silver.get("/api/screener/presets/highest-rated-large")).status_code == 403          # the Prism screens are Gold
    adv = (await silver.get("/api/screener/presets")).json()
    assert adv["tab"] == "advanced" and all(c["locked"] for g in adv["groups"] for c in g["presets"])
    await silver.aclose(); await free.aclose()


async def test_the_screener_rows_carry_the_52_week_and_return_figures_for_the_optional_columns(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM scores WHERE symbol = 'EXTRA1'")
        await conn.execute("INSERT INTO scores (symbol, statement, model, overall, metrics) VALUES ('EXTRA1', 'consolidated', 'v1', 70, $1::jsonb)",
                           json.dumps({"pct_from_high": 12.5, "ret_3m": 4.0, "ret_6m": -2.5}))
        await conn.execute("INSERT INTO scores (symbol, statement, model, overall, metrics) VALUES ('EXTRA2', 'consolidated', 'v1', 60, '{}'::jsonb) ON CONFLICT DO NOTHING")
    rows = {r["symbol"]: r for r in await store.screener_rows()}
    assert rows["EXTRA1"]["pct_from_high"] == 12.5 and rows["EXTRA1"]["ret_3m"] == 4.0 and rows["EXTRA1"]["ret_6m"] == -2.5
    assert rows["EXTRA2"]["pct_from_high"] is None and rows["EXTRA2"]["ret_6m"] is None            # missing is blank, never zero
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM scores WHERE symbol IN ('EXTRA1', 'EXTRA2')")


async def test_results_page_by_25_with_offset_and_limit_and_export_keeps_every_row(app, store):  # noqa: F811
    await wipe(store)
    gold = await signed_in(app, "pg@example.com", plan="gold")
    first = (await gold.get("/api/screener/presets/emerging-tech?chip=none")).json()
    assert first["count"] == 30 and first["shown"] == 25 and first["offset"] == 0 and first["hasMore"] is True and first["pageSize"] == 25 and "listText" not in first
    second = (await gold.get("/api/screener/presets/emerging-tech?chip=none&offset=25")).json()
    assert second["shown"] == 5 and second["offset"] == 25 and second["hasMore"] is False and [r["position"] for r in second["rows"]] == [26, 27, 28, 29, 30]
    assert {r["symbol"] for r in first["rows"]}.isdisjoint(r["symbol"] for r in second["rows"]) and "exportRows" not in second
    allrows = (await gold.get("/api/screener/presets/emerging-tech?chip=none&limit=2000")).json()
    assert allrows["shown"] == 30 and allrows["hasMore"] is False
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=none&offset=x")).status_code == 422
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=none&offset=-1")).status_code == 422
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=none&limit=0")).status_code == 422
    assert (await gold.get("/api/screener/presets/emerging-tech?chip=none&offset=900")).json()["rows"] == []
    top = (await gold.get("/api/screener/presets/highest-rated-large?chip=none&offset=25")).json()
    assert "offset" not in top and top["shown"] == len(top["rows"]) <= 10                      # the Top 10 lists are ten by rule
    e = await gold.get("/api/screener/presets/emerging-tech/export?chip=none")
    assert e.text.count("\n") >= 30 + 2
    card = [c for g in (await gold.get("/api/screener/presets")).json()["groups"] for c in g["presets"] if c["id"] == "emerging-tech"][0]
    assert card["listText"] is None
    await gold.aclose()
