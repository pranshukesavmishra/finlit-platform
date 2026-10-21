"""Built-in alerts for the eight P&L divergence cases: wording, recency, plan, preference and once-per-company-case-period delivery."""

import json
from datetime import date, timedelta

import pytest

from finlit import plalerts as pa
from test_auth import app, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)


def body(ends, rev, np_, yearly=None):
    q = {"period": "quarterly", "periods": [f"Q{i}" for i in range(len(ends))], "periodEnds": ends, "rows": {"revenue": rev, "net_profit": np_}}
    return {"quarterly": {"pl": q}, "yearly": {"pl": yearly or {"periods": [], "periodEnds": [], "rows": {}}}}


def test_message_is_plain_and_not_advice():
    f = {"case": 3, "title": "Revenue rose while profit fell", "period": "Mar 2026", "text": "Revenue grew 10.0% while net profit fell 10.0%. Compared with Mar 2025.", "why": "Costs may be rising.", "scope": "quarterly"}
    title, text = pa.message("ABC", f)
    assert title == "ABC – Revenue rose while profit fell (Mar 2026)"
    assert "worth a closer look" in text and "not investment advice" in text
    assert pa.kind_of(f) == "pl_flag_3" and pa.link_for("ABC", f) == "/stocks/ABC#quarter"
    assert pa.link_for("ABC", {**f, "scope": "annual"}) == "/stocks/ABC#financials"


def test_only_recently_reported_periods_make_alerts():
    today = date(2026, 7, 1)
    ends = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
    b = body(ends, [100, 100, 100, 100, 110], [10, 10, 10, 10, 8])
    assert [f["case"] for f in pa.fresh_flags(b, today)] == [3]
    assert pa.fresh_flags(b, date(2026, 12, 1)) == []              # more than 120 days old: not news
    assert pa.fresh_flags(b, date(2026, 3, 1)) == []              # a period end in the future is never fresh
    assert pa.fresh_flags({}, today) == []
    assert pa.fresh_flags({"quarterly": {"pl": {"periods": ["a"], "periodEnds": ["x"], "rows": {}}}}, today) == []


async def test_alert_goes_to_silver_watchlists_once_per_company_case_and_period(app):
    c = await signed_in(app, "plf@example.com", plan="silver")
    basic = await signed_in(app, "plfbasic@example.com", plan="basic")
    off = await signed_in(app, "plfoff@example.com", plan="silver")
    await off.put("/api/me/prefs", json={"palette": "gold", "profitGap": False})
    lists = {"lists": [{"id": "main", "name": "Main", "symbols": ["RELIANCE"]}], "meta": {}}
    for m in (c, basic, off):
        assert (await m.put("/api/me/watchlist", json=lists)).status_code == 200
    today = date.today()
    last = today - timedelta(days=20)
    # five quarters: the first is the same quarter a year before the last (365 days earlier), the rest fill in between
    ends = [(last - timedelta(days=365)).isoformat(), (last - timedelta(days=274)).isoformat(), (last - timedelta(days=182)).isoformat(), (last - timedelta(days=91)).isoformat(), last.isoformat()]
    async with app.state.store.pool.acquire() as conn:
        for r in await conn.fetch("SELECT statement, body FROM snapshots WHERE symbol = 'RELIANCE' AND section = 'financials'"):
            d = json.loads(r["body"])
            d["quarterly"]["pl"].update({"period": "quarterly", "periods": ["Q1", "Q2", "Q3", "Q4", "Q5"], "periodEnds": ends,
                                         "rows": {**d["quarterly"]["pl"]["rows"], "revenue": [1000, 1000, 1000, 1000, 1100], "net_profit": [100, 100, 100, 100, 80]}})
            d["yearly"]["pl"].update({"period": "yearly", "periods": ["FY24", "FY25"], "periodEnds": ["2024-03-31", "2025-03-31"], "rows": {"revenue": [1, 1], "net_profit": [1, 1]}})
            await conn.execute("UPDATE snapshots SET body = $2 WHERE symbol = 'RELIANCE' AND section = 'financials' AND statement = $1", r["statement"], json.dumps(d))
    pool = app.state.store.pool
    assert await pa.auto_pl_flags(pool, app.state.mailer, "http://test") == 1
    n = (await c.get("/api/notifications")).json()["notifications"]
    assert len(n) == 1 and "Revenue rose while profit fell" in n[0]["title"] and n[0]["link"] == "/stocks/RELIANCE#quarter"
    assert "not investment advice" in n[0]["body"]
    assert (await basic.get("/api/notifications")).json()["notifications"] == []     # Basic gets none
    assert (await off.get("/api/notifications")).json()["notifications"] == []       # switched off in preferences
    assert await pa.auto_pl_flags(pool, app.state.mailer, "http://test") == 0         # once per company, case and period
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM auto_alert_sent WHERE kind = 'pl_flag_3'") == 1
    await c.aclose(); await basic.aclose(); await off.aclose()
