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
    assert title == "ABC – Revenue rose while profit fell in the latest quarter (Mar 2026)"
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
    for m in (c, off):
        assert (await m.put("/api/me/watchlist", json=lists)).status_code == 200
    today = date.today()
    last = today - timedelta(days=20)
    # five quarters: the first is the same quarter a year before the last (365 days earlier), the rest fill in between
    ends = [(last - timedelta(days=365)).isoformat(), (last - timedelta(days=274)).isoformat(), (last - timedelta(days=182)).isoformat(), (last - timedelta(days=91)).isoformat(), last.isoformat()]
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM auto_alert_sent WHERE kind LIKE 'pl_flag_%'")
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


def _q(rev, np_, ends=("2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"), **extra):
    return {"period": "quarterly", "periods": ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"], "periodEnds": list(ends), "rows": {"revenue": rev, "net_profit": np_, **extra}}


def _y(rev, np_, **extra):
    return {"period": "yearly", "periods": ["FY25", "FY26"], "periodEnds": ["2025-03-31", "2026-03-31"], "rows": {"revenue": rev, "net_profit": np_, **extra}}


def test_quarter_and_year_are_tested_separately_and_named():
    from finlit.plflags import period_views
    today = date(2026, 10, 26)
    b = {"quarterly": {"pl": _q([100, 100, 100, 100, 110], [10, 10, 10, 10, 8])}, "yearly": {"pl": _y([100, 106.3], [10, 8.72])}}
    # the year ended Mar 2026 is more than 200 days old on 26 Oct 2026: only the fresh quarter alerts
    fl = pa.fresh_flags(b, today)
    assert [(f["case"], f["scope"], f["period"]) for f in fl] == [(3, "quarterly", "Sep 2026")]
    v = period_views(b["yearly"]["pl"], b["quarterly"]["pl"])
    assert v["annual"]["growth"] == {"revenue": 6.3, "profit": -12.8, "operating": None} and v["annual"]["against"] == "FY25"
    title, text = pa.message("KOTAKBANK", fl[0], v)
    assert title == "KOTAKBANK – Revenue rose while profit fell in the latest quarter (Sep 2026)"
    assert "Latest quarter, Sep 2026 against Sep 2025: revenue +10.0%, net profit −20.0%." in text
    assert "Latest year, FY26 against FY25: revenue +6.3%, net profit −12.8%." in text and "not investment advice" in text
    ann = {**fl[0], "scope": "annual", "period": "FY26"}
    assert pa.message("X", ann)[0].endswith("in the latest year (FY26)")


def test_a_quarter_missing_never_shifts_the_comparison():
    q = {"period": "quarterly", "periods": ["Sep 2025", "Mar 2026", "Sep 2026"], "periodEnds": ["2025-09-30", "2026-03-31", "2026-09-30"], "rows": {"revenue": [100, 100, 110], "net_profit": [10, 10, 8]}}
    fl = pa.fresh_flags({"quarterly": {"pl": q}}, date(2026, 10, 26))
    assert [(f["case"], f["against"]) for f in fl] == [(3, "Sep 2025")]


def test_lenders_use_total_income_and_have_no_operating_profit():
    today = date(2026, 10, 26)
    q = _q([100, 100, 100, 100, 110], [20, 20, 20, 20, 22], total_income=[200, 200, 200, 200, 200], operating_profit=[50, 50, 50, 50, 40])
    assert [f["case"] for f in pa.fresh_flags({"quarterly": {"pl": q}}, today)] == [7]            # a company: operating profit fell, net rose
    assert pa.fresh_flags({"quarterly": {"pl": q}}, today, lender=True) == []                      # a lender: total income flat, no operating profit
    from finlit.plflags import period_views
    v = period_views(None, q, lender=True)["quarterly"]
    assert v["growth"] == {"revenue": 0.0, "profit": 10.0, "operating": None}
    _, text = pa.message("KOTAK", {"case": 5, "title": "t", "period": "Sep 2026", "scope": "quarterly", "text": "x.", "why": "w."}, {"quarterly": v}, True)
    assert "total income" in text and "operating" not in text
