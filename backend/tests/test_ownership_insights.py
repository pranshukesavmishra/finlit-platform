"""Ownership insights (docs/OWNERSHIP.md): the pack built from what the site stores, the stored row, the API route, and the nightly job with a fake premium endpoint."""
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from finlit import ownership_insights as oi
from test_auth import anon, app  # noqa: F401  (fixtures)
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)

FX = json.loads((Path(__file__).resolve().parents[1] / "finlit_technicals" / "tests" / "fixtures" / "ownership.json").read_text(encoding="utf-8"))


def own_body(sym="RELIANCE"):
    p = FX[sym]
    return {"periods": p["periods"], "series": p["series"]}


def premium_of(sym="RELIANCE"):
    """The premium fundamentals shape (ownershipStructure + shareholdingDetails) rebuilt from the team's fixture pack."""
    st, p = FX[sym]["structure"], FX[sym]
    structure = [{"category": k, "history": [{"period": per, "value": v} for per, v in zip(st["periods"], vals)]} for k, vals in st.items() if k != "periods"]
    group = {"dii": "Institutions Domestic", "fii": "Institutions Foreign", "public": "Non-Institutions", "government": "Government"}
    details = {}
    for name, g, now, ago in p["holders"]:
        details.setdefault(group[g], []).append({"label": name, "history": [{"value": now}, {}, {}, {}, {"value": ago}]})
    return {"ownershipStructure": structure, "shareholdingDetails": [{"label": k, "children": v} for k, v in details.items()]}


# ------------------------------------------------------------------------------------------------ the pure part
def test_a_pack_built_from_the_premium_shape_equals_the_teams_fixture_pack():
    extra = oi.extra_from_premium("RELIANCE", own_body(), premium_of())
    assert extra["structure"]["total_shares"] == FX["RELIANCE"]["structure"]["total_shares"]
    assert [h[0] for h in extra["holders"]] == [h[0] for h in FX["RELIANCE"]["holders"]]
    from finlit_technicals import ownership as O
    assert oi.build_view("RELIANCE", own_body(), extra)["facts"] == O.analyse({"symbol": "RELIANCE", **FX["RELIANCE"]})["facts"]


def test_without_the_premium_part_the_view_has_no_facts_and_the_block_says_why():
    view = oi.build_view("RELIANCE", own_body(), None)
    assert view["facts"]["shareholders"] is None and view["facts"]["top_holders"] == [] and len(view["table"]) == 5
    block = oi.finish(view, "missing", oi.REASON_PENDING, None)["premium"]
    assert block == {"state": "missing", "reason": oi.REASON_PENDING, "has": {"structure": False, "holders": False}}


def test_an_empty_premium_answer_gives_no_extra_and_garbage_does_not_raise():
    assert oi.extra_from_premium("X", own_body(), {"ownershipStructure": [], "shareholdingDetails": []}) is None
    assert oi.extra_from_premium("X", own_body(), None) is None
    assert oi.parse_body(b"{}") is None and oi.parse_body("not json") is None and oi.parse_body({"periods": [], "series": {}}) is None


def test_which_companies_are_due_for_the_premium_call():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    ok = {"as_of": "Sep 2026", "premium_state": "ok", "premium_at": now - timedelta(days=3), "premium_tried_at": now - timedelta(days=3)}
    assert oi.due_for_premium(None, "Sep 2026", now) == 0                                                         # never built
    assert oi.due_for_premium(ok, "Sep 2026", now) is None                                                        # current
    assert oi.due_for_premium({**ok, "as_of": "Jun 2026"}, "Sep 2026", now) == 1                                  # a newer filing than the kept figures
    assert oi.due_for_premium({**ok, "premium_at": now - timedelta(days=40)}, "Sep 2026", now) == 2              # older than 25 days
    miss = {"as_of": "Sep 2026", "premium_state": "missing", "premium_at": None, "premium_tried_at": now - timedelta(hours=1)}
    assert oi.due_for_premium(miss, "Sep 2026", now) is None                                                      # failed an hour ago: wait
    assert oi.due_for_premium({**miss, "premium_tried_at": now - timedelta(hours=7)}, "Sep 2026", now) == 0


# ------------------------------------------------------------------------------------------------ the route
pytestmark_int = pytest.mark.integration


@pytest.mark.integration
async def test_a_page_opened_before_the_job_still_gets_insights_and_queues_the_premium_part(app, anon):  # noqa: F811
    st = app.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
    await st.redis.delete(oi.WANTED)
    r = await anon.get("/api/stocks/RELIANCE/ownership-insights")
    b = r.json()
    assert r.status_code == 200 and b["available"] and b["stored"] is False and len(b["table"]) >= 4 and b["premium"]["state"] == "missing" and b["premium"]["reason"]
    assert "ownership" in r.headers["cache-control"] or r.headers["cache-control"].startswith("public")
    async with st.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM ownership_insights WHERE symbol = 'RELIANCE'") == 1
    assert await st.redis.zscore(oi.WANTED, "RELIANCE") is not None
    again = await anon.get("/api/stocks/RELIANCE/ownership-insights")
    assert again.json()["stored"] is True and again.json()["table"] == b["table"]
    assert (await anon.get("/api/stocks/RELIANCE/ownership-insights", headers={"If-None-Match": again.headers["etag"]})).status_code == 304


@pytest.mark.integration
async def test_route_errors_say_why(app, anon):  # noqa: F811
    assert (await anon.get("/api/stocks/bad!sym/ownership-insights")).status_code == 400
    assert (await anon.get("/api/stocks/RELIANCE/ownership-insights?statement=x")).status_code == 400
    r = await anon.get("/api/stocks/NOSUCHCO/ownership-insights")
    assert r.status_code == 404 and r.json()["available"] is False and "not been loaded" in r.json()["reason"]


@pytest.mark.integration
async def test_a_newer_stored_filing_than_the_row_is_built_again_with_the_kept_premium_part(app, anon):  # noqa: F811
    st = app.state.store
    extra = oi.extra_from_premium("RELIANCE", own_body(), premium_of())
    old = oi.build_view("RELIANCE", own_body(), extra)
    old["as_of"] = "Jun 2020"
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
        await oi.save_row(conn, "RELIANCE", "consolidated", old, extra, "ok", None, premium_ok=True, tried=True)
    b = (await anon.get("/api/stocks/RELIANCE/ownership-insights")).json()
    assert b["premium"]["state"] == "ok" and b["facts"]["shareholders"] and b["as_of"] != "Jun 2020"


# ------------------------------------------------------------------------------------------------ the job
def fake_site(calls, slow=False, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        assert request.headers["authorization"].startswith("Bearer ") and request.url.path == "/api/stocks/admin/fundamentals"
        return httpx.Response(status, json=premium_of() if status == 200 else {"detail": "no"})
    return httpx.AsyncClient(base_url="http://site", transport=httpx.MockTransport(handler))


@pytest.mark.integration
async def test_the_job_builds_every_row_then_fetches_the_premium_part_once(ingested):  # noqa: F811
    st = ingested
    settings = replace(make_settings(), site_api_url="http://site", cms_jwt_secret="s" * 40)
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
    calls = []
    res = await oi.refresh(st, settings, client=fake_site(calls))
    assert res["built"] >= 1 and res["premium_ok"] == 1 and calls == [{"query": "RELIANCE", "statement_type": "consolidated", "period": "yearly"}] and res["left"] == 0
    row = await oi.load_row(st, "RELIANCE", "consolidated")
    assert row["premium_state"] == "ok" and row["body"]["facts"]["shareholders"] and row["body"]["premium"]["state"] == "ok" and row["extra"]["holders"]
    calls.clear()
    again = await oi.refresh(st, settings, client=fake_site(calls))
    assert calls == [] and again["premium_ok"] == 0 and again["built"] == 0              # nothing is fetched twice


@pytest.mark.integration
async def test_a_provider_failure_keeps_the_row_and_the_reason_and_waits_six_hours(ingested):  # noqa: F811
    st = ingested
    settings = replace(make_settings(), site_api_url="http://site", cms_jwt_secret="s" * 40)
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
    calls = []
    res = await oi.refresh(st, settings, client=fake_site(calls, status=502))
    assert res["premium_failed"] == 1
    row = await oi.load_row(st, "RELIANCE", "consolidated")
    assert row["premium_state"] == "missing" and "HTTP 502" in row["premium_reason"] and row["body"]["table"]
    calls.clear()
    await oi.refresh(st, settings, client=fake_site(calls))
    assert calls == []                                                                   # tried just now: not again for six hours


@pytest.mark.integration
async def test_not_connected_still_builds_rows_and_says_so(ingested):  # noqa: F811
    st = ingested
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
    res = await oi.refresh(st, replace(make_settings(), site_api_url="", cms_jwt_secret=""))
    assert res["premium"] == "not_connected" and res["built"] >= 1
    row = await oi.load_row(st, "RELIANCE", "consolidated")
    assert row["premium_reason"] == oi.REASON_NOT_CONNECTED


@pytest.mark.integration
async def test_visitors_companies_go_first_and_the_run_is_bounded(ingested):  # noqa: F811
    st = ingested
    settings = replace(make_settings(), site_api_url="http://site", cms_jwt_secret="s" * 40)
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE ownership_insights")
    res = await oi.refresh(st, settings, client=fake_site([]), limit=0)
    assert res["premium_ok"] == 0 and res["left"] >= 1 and res["built"] >= 1             # limit 0: rows are built, no premium call is made
