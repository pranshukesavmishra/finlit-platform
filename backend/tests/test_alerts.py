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
