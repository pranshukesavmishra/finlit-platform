"""Member alerts end to end: creating, plan limits, crossing detection, notifications, email and the in-app centre."""

import re
from pathlib import Path

import pytest

from finlit import alertengine as eng
from test_auth import app, last_mail, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


def body(**kw):
    return {"symbol": "RELIANCE", "metric": "price", "op": "above", "value": 1200, "channels": ["app", "email"], **kw}


async def set_price(app, price):
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET price = $1 WHERE symbol = 'RELIANCE'", price)


async def run(app, kind="all"):
    return await eng.evaluate(app.state.store.pool, app.state.mailer, "http://test", kind)


def test_catalogue_matches_the_front_end():
    ts = (Path(__file__).parents[2] / "frontend/src/lib/alertCatalog.ts").read_text()
    keys = set(re.findall(r'^\s{2}"?([a-z0-9_]+)"?: \{ label:', ts, re.M))
    assert keys == set(eng.METRICS), keys ^ set(eng.METRICS)


async def test_price_alert_fires_once_on_a_crossing_and_lands_in_the_notification_centre(app):
    c = await signed_in(app, "a@example.com")
    await set_price(app, 1100)
    r = await c.post("/api/alerts", json=body())
    assert r.status_code == 201 and r.json()["alreadyMet"] is False and r.json()["current"] == 1100
    assert await run(app) == 0                       # still below
    await set_price(app, 1250)
    assert await run(app) == 1                       # crossed
    n = (await c.get("/api/notifications")).json()
    assert n["unread"] == 1 and "RELIANCE – Price is now ₹1,250" in n["notifications"][0]["title"] and n["notifications"][0]["link"] == "/stocks/RELIANCE"
    assert "FinLit alert" in (await last_mail(app, "a@example.com"))["subject"]
    assert await run(app) == 0                       # a one-time alert is finished
    assert (await c.get("/api/alerts")).json()["alerts"][0]["status"] == "done"
    await c.post("/api/notifications/read", json={})
    assert (await c.get("/api/notifications?unread=true")).json()["unread"] == 0
    await c.aclose()


async def test_repeating_alert_needs_a_new_crossing_and_respects_pause_and_email_preference(app):
    c = await signed_in(app, "b@example.com")
    await c.put("/api/me/prefs", json={"palette": "gold", "alerts": False})
    await set_price(app, 1100)
    aid = (await c.post("/api/alerts", json=body(repeat="every"))).json()["id"]
    await set_price(app, 1300)
    assert await run(app) == 1
    assert (await last_mail(app, "b@example.com"))["subject"] != "FinLit alert"   # emails switched off in preferences: none about the alert
    assert await run(app) == 0                       # stays above, no repeat
    assert (await c.patch(f"/api/alerts/{aid}", json={"status": "paused"})).json()["status"] == "paused"
    await set_price(app, 1000)
    assert await run(app) == 0                       # paused: nothing evaluated
    assert (await c.patch(f"/api/alerts/{aid}", json={"status": "active"})).json()["met"] is False
    await set_price(app, 1400)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE alerts SET last_fired_at = now() - interval '2 hours'")
    assert await run(app) == 1
    assert (await c.get("/api/notifications")).json()["unread"] == 2
    await c.aclose()


async def test_validation_limits_and_ownership(app):
    basic = await signed_in(app, "c@example.com")
    assert (await basic.post("/api/alerts", json=body(metric="overall", value=70))).json()["detail"]["status"] == "plan_required"
    assert (await basic.post("/api/alerts", json=body(op="below", metric="volume_x", value=3))).json()["detail"]["status"] == "bad_metric"
    assert (await basic.post("/api/alerts", json=body(channels=["app", "sms"]))).json()["detail"]["status"] == "bad_channel"
    assert (await basic.post("/api/alerts", json=body(symbol="NOPE123"))).json()["detail"]["status"] == "unknown_stock"
    assert (await basic.post("/api/alerts", json=body(metric="news_keyword", op="event"))).json()["detail"]["status"] == "keyword_required"
    assert (await basic.post("/api/alerts", json={**body(), "value": None})).json()["detail"]["status"] == "value_required"
    for v in (1500, 1600, 1700):
        assert (await basic.post("/api/alerts", json=body(value=v))).status_code == 201
    assert (await basic.post("/api/alerts", json=body(value=1500))).status_code == 409
    assert (await basic.post("/api/alerts", json=body(value=1800))).json()["detail"]["status"] == "plan_limit"
    other = await signed_in(app, "d@example.com", plan="silver")
    ours = (await basic.get("/api/alerts")).json()["alerts"][0]["id"]
    assert (await other.delete(f"/api/alerts/{ours}")).status_code == 404
    assert (await other.post("/api/alerts", json=body(metric="overall", value=40))).status_code == 201
    assert (await basic.delete(f"/api/alerts/{ours}")).status_code == 200
    anon_status = (await (await signed_in(app, "e@example.com")).get("/api/alerts")).status_code
    assert anon_status == 200
    for c in (basic, other):
        await c.aclose()


async def test_score_event_and_technical_metrics_evaluate_from_stored_data(app):
    c = await signed_in(app, "f@example.com", plan="silver")
    async with app.state.store.pool.acquire() as conn:
        rs = await eng.load_values(conn, ["RELIANCE"], {"rsi14", "from_high52", "ema200_gap", "q_net_profit", "overall", "volume_x"})
    v = rs["RELIANCE"]
    assert v["overall"] is not None and v["rsi14"] is not None and 0 <= v["rsi14"] <= 100 and v["from_high52"] >= 0
    assert (await c.get("/api/alerts/value?symbol=RELIANCE&metric=rsi14")).json()["value"] == v["rsi14"]
    r = await c.post("/api/alerts", json=body(metric="news_keyword", op="event", value=None, keyword="  Dividend "))
    assert r.status_code == 201 and r.json()["keyword"] == "dividend"
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, item_date, auto, dedupe) VALUES ('news', 'Board declares interim dividend', 'RELIANCE', current_date, false, 'alerts-test-1')")
    assert await run(app, "daily") == 1
    n = (await c.get("/api/notifications")).json()["notifications"][0]
    assert "Board declares interim dividend" in n["title"]
    assert await run(app, "daily") == 0
    await c.aclose()


def test_revenue_profit_gap_metric_and_message():
    from finlit import alertengine as ae
    g = ae.quarter_gap({"revenue": [772, 800, 900, 929, 1057.8], "net_profit": [115.5, 100, 90, 115.3, 73.9]})   # Waaree-style: sales +37%, profit -36%
    assert g and round(g["rev"]) == 37 and round(g["profit"]) == -36 and g["gap"] > 70
    assert ae.quarter_gap({"revenue": [100, 110, 120, 130, 140], "net_profit": [10, 11, 12, 13, 14.5]})["gap"] == 5.0
    assert ae.quarter_gap({"revenue": [100, 1, 1, 1, 140], "net_profit": [-5, 1, 1, 1, 9]}) is None          # growth on a loss is not meaningful
    assert ae.quarter_gap({"revenue": [100, 110], "net_profit": [10, 11]}) is None                           # fewer than five quarters
    title, body = ae.headline({"symbol": "WAAREERTL", "metric": "rev_profit_gap", "op": "above", "value": 15}, g["gap"], g)
    assert "The anticipated difference between revenue and profit is >= 15 percent thus please check the report thoroughly." in body
    assert "37%" in body and "-36%" in body and "WAAREERTL" in title
    assert ae.allowed("basic", "rev_profit_gap") is False and ae.allowed("silver", "rev_profit_gap") and ae.allowed("gold", "rev_profit_gap")


async def test_builtin_profit_gap_alert_goes_to_silver_watchlists_once_per_quarter(app):
    import json
    from datetime import date, timedelta
    c = await signed_in(app, "gap@example.com", plan="silver")
    basic = await signed_in(app, "gapbasic@example.com", plan="basic")
    lists = {"lists": [{"id": "main", "name": "Main", "symbols": ["RELIANCE"]}], "meta": {}}
    assert (await c.put("/api/me/watchlist", json=lists)).status_code == 200
    end = (date.today() - timedelta(days=20)).isoformat()
    async with app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT statement, body FROM snapshots WHERE symbol = 'RELIANCE' AND section = 'financials'")
        for r in rows:
            d = json.loads(r["body"])
            d["quarterly"]["pl"].update({"periods": ["Q1", "Q2", "Q3", "Q4", "Q5"], "periodEnds": ["a", "b", "c", "d", end],
                                         "rows": {**d["quarterly"]["pl"]["rows"], "revenue": [772, 800, 900, 929, 1057.8], "net_profit": [115.5, 100, 90, 115.3, 73.9]}})
            await conn.execute("UPDATE snapshots SET body = $2 WHERE symbol = 'RELIANCE' AND section = 'financials' AND statement = $1", r["statement"], json.dumps(d))
    assert await eng.auto_profit_gap(app.state.store.pool, app.state.mailer, "http://test") == 1
    n = (await c.get("/api/notifications")).json()["notifications"][0]
    assert "revenue and profit growth are" in n["title"] and "check the report thoroughly" in n["body"]
    assert (await basic.get("/api/notifications")).json()["notifications"] == []          # Basic gets none
    assert await eng.auto_profit_gap(app.state.store.pool, app.state.mailer, "http://test") == 0   # once per company and quarter
    await c.aclose(); await basic.aclose()


async def test_members_own_companies_are_remembered_kept_and_refreshed(app):
    """A company a member opens or follows stays stored and refreshed outside the always-loaded top set, and is listed for that member only."""
    import asyncio
    c = await signed_in(app, "mine@example.com", plan="silver")
    other = await signed_in(app, "other@example.com", plan="silver")
    store = app.state.store
    assert (await c.get("/api/stocks/RELIANCE")).status_code == 200
    await asyncio.sleep(0.5)                                               # the remembering runs in the background
    mine = (await c.get("/api/me/companies")).json()["companies"]
    assert [x["symbol"] for x in mine] == ["RELIANCE"] and mine[0]["ready"] is True and mine[0]["lastOpened"]
    assert (await other.get("/api/me/companies")).json()["companies"] == []          # personal: another member sees nothing of it
    assert (await app_anon(app).get("/api/me/companies")).status_code == 401
    lists = {"lists": [{"id": "main", "name": "Main", "symbols": ["TCS"]}], "meta": {}}
    assert (await c.put("/api/me/watchlist", json=lists)).status_code == 200
    pinned = await store.pinned_symbols()
    assert "TCS" in pinned and "RELIANCE" in pinned                         # followed first, then opened
    todo = await store.pending_symbols("consolidated", 24, 1)               # the always-loaded set is just one company here
    assert "TCS" in todo                                                    # the followed company is refreshed although it is outside that set
    assert await store.pinned_symbols(0) == []
    await c.aclose(); await other.aclose()


def app_anon(app):
    from test_auth import new_client
    return new_client(app)
