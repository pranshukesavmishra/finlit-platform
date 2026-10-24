"""Query builder endpoints and baskets: validate / run / export / ratios, plan locks, and basket CRUD, ownership and limits."""

import json

import pytest

from finlit.screener import data
from finlit.screener.data import Table
from test_auth import ORIGIN, anon, app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


def row(sym, **m):
    return {"symbol": sym, "name": sym.title(), "sector": "IT", "industry": None, "band": "mixed", "metrics": json.dumps(m)}


@pytest.fixture(autouse=True)
def fake_table():
    rows = [row(f"S{i:02d}", market_cap=100 * (i + 1), pe=5 + i, roe=i, debt_to_equity=(i % 5) / 2, **({"pb": 1 + i / 10} if i % 2 else {})) for i in range(40)]
    rows.append(row("NOPE", market_cap=50))
    data._table = Table(rows, {}, {})
    yield data._table
    data.reset()


async def post(c, path, **body):
    return await c.post(f"/api/screener/{path}", json=body)


async def test_validate_reports_every_problem_with_positions(app, anon):  # noqa: F811
    r = await post(anon, "ql/validate", query="Market cap > 500 AND Piotroski score > 5 AND ROE >")
    body = r.json()
    assert r.status_code == 200 and body["ok"] is False
    codes = [e["code"] for e in body["errors"]]
    assert codes == ["unknown_metric", "missing_value"]
    e = body["errors"][0]
    assert e["text"] == "Piotroski score" and e["line"] == 1 and e["col"] == 22 and e["seeAll"] and e["suggestions"] and e["fixes"]
    assert [m["key"] for m in body["metrics"]] == ["market_cap", "roe"]
    ok = (await post(anon, "ql/validate", query="Market cap > 500 Cr\nPE < 15")).json()
    assert ok["ok"] and ok["conditions"] == 2 and ok["canonical"] == "Market cap > 500 Cr\nP/E Ratio < 15" and ok["reading"]["type"] == "and"
    assert (await post(anon, "ql/validate", query="x" * 2001)).json()["errors"][0]["code"] == "too_long"
    assert (await post(anon, "ql/validate", query="Market cap > 500000")).json()["warnings"][0]["code"] == "crore_units"


async def test_plan_locks_in_validate_and_run(app, anon):  # noqa: F811
    q = "ROE > 3 AND P/B < 2"
    v = (await post(anon, "ql/validate", query=q)).json()
    assert not v["ok"] and v["errors"][0]["code"] == "plan_locked" and v["errors"][0]["plan"] == "silver" and "Silver" in v["errors"][0]["message"]
    r = (await post(anon, "ql/run", query=q)).json()
    assert r["ok"] is False and r["errors"][0]["code"] == "plan_locked"
    assert (await post(anon, "ql/run", query="ROE > 3", columns=["pb"])).json()["errors"][0]["code"] == "plan_locked"      # nor through a column
    assert (await post(anon, "ql/run", query="ROE > 3", sort={"key": "pb", "dir": "asc"})).json()["errors"][0]["code"] == "plan_locked"
    silver = await signed_in(app, "s@example.com", plan="silver")
    assert (await post(silver, "ql/run", query=q)).json()["ok"] is True
    assert (await post(silver, "ql/run", query="FinLit score > 3")).json()["errors"][0]["plan"] == "gold"
    await silver.aclose()


async def test_run_results_columns_counts_and_paging(app, anon):  # noqa: F811
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = (await post(silver, "ql/run", query="ROE >= 10 AND P/E < 30 AND P/B < 3", limit=5, sort={"key": "roe", "dir": "asc"})).json()
    assert r["ok"] and r["columns"] == ["market_cap", "price", "roe", "pe", "pb"]
    # roe >= 10 -> i >= 10, pe < 30 -> i < 25, pb known only for odd i, pb = 1 + i/10 < 3 -> i < 20: odd i in 11..19
    assert r["total"] == 5 and [x["symbol"] for x in r["rows"]] == ["S11", "S13", "S15", "S17", "S19"]
    assert r["rows"][0]["v"]["roe"] == 11 and r["universe"] == 41 and r["withReport"] == 41
    pm = {m["key"]: m for m in r["leftOut"]["metrics"]}
    # unknown overall: even i in 10..24 (P/B unknown, the other two true) = 8, plus NOPE (everything unknown)
    assert pm["pb"]["missing"] == 21 and pm["pb"]["leftOut"] == 9 and pm["pe"]["leftOut"] == 1 and r["leftOut"]["total"] == 9
    page = (await post(silver, "ql/run", query="ROE >= 10", limit=10, offset=10, sort={"key": "market_cap", "dir": "desc"})).json()
    assert page["total"] == 30 and page["rows"][0]["symbol"] == "S29" and len(page["rows"]) == 10
    bad = (await post(silver, "ql/run", query="ROE >")).json()
    assert bad["ok"] is False and bad["errors"][0]["code"] == "missing_value" and "rows" not in bad
    await silver.aclose()
    free = (await post(anon, "ql/run", query="Market cap > 100", limit=100)).json()
    assert free["total"] == 39 and free["capped"] and len(free["rows"]) == 25


async def test_recent_results_option(app, anon):  # noqa: F811
    r = (await post(anon, "ql/run", query="ROE > 1", recent=True)).json()
    assert r["ok"] is False and r["errors"][0]["code"] == "recent_unavailable"      # the test table has no quarter dates
    assert (await anon.get("/api/screener/ql/ratios")).json()["recentResults"]["available"] is False
    rows = [row(f"R{i}", market_cap=10 + i, roe=i, q_period_end=20260930) for i in range(30)] + [row("OLD", market_cap=99, roe=50, q_period_end=20260630)]
    data._table = Table(rows, {}, {})
    got = (await post(anon, "ql/run", query="ROE > 1", recent=True)).json()
    assert got["total"] == 28 and got["recent"]["quarterEnd"] == 20260930 and got["recent"]["dropped"] == 1


async def test_export_is_a_silver_csv(app, anon):  # noqa: F811
    assert (await post(anon, "ql/export", query="ROE > 3")).status_code == 403
    silver = await signed_in(app, "s@example.com", plan="silver")
    r = await post(silver, "ql/export", query="ROE >= 38")
    assert r.status_code == 200 and r.text.startswith("﻿Symbol,Company,Sector,Size,Market cap (Cr)") and "S38" in r.text and "S39" in r.text and "S37" not in r.text
    bad = await post(silver, "ql/export", query="ROE >")
    assert bad.status_code == 422 and bad.json()["detail"]["errors"][0]["code"] == "missing_value"
    await silver.aclose()


async def test_ratios_lists_every_metric_with_names_and_examples(app, anon):  # noqa: F811
    from finlit.screener.catalog import CATALOG
    from finlit.screener.ql import analyze
    body = (await anon.get("/api/screener/ql/ratios")).json()
    assert len(body["ratios"]) == len(CATALOG) and body["aliases"] > 1000 and body["plan"] == "basic"
    by = {r["key"]: r for r in body["ratios"]}
    assert by["pe"]["names"][0] == "P/E Ratio" and "P/E" in by["pe"]["names"] and by["pe"]["unitLabel"] == "times" and by["pe"]["definition"].startswith("The share price")
    assert by["pb"]["locked"] and by["pb"]["tier"] == "silver" and not by["pe"]["locked"]
    for r in body["ratios"]:       # every example written for a ratio is itself a valid query
        assert analyze(r["example"], "gold").ok, (r["key"], r["example"])
    assert {e["id"]: e["locked"] for e in body["examples"]}["value"] is True and {e["id"]: e["locked"] for e in body["examples"]}["quality"] is False
    assert body["limits"]["chars"] == 2000 and body["limits"]["conditions"] == 30 and body["limits"]["rows"] == 25


# ------------------------------------------------------------------------------------------------------------------ baskets
def b(name="Value", query="ROE > 10", **kw):
    return {"name": name, "query": query, **kw}


async def test_baskets_need_sign_in_and_csrf(app, anon):  # noqa: F811
    assert (await anon.get("/api/screener/baskets")).status_code == 401
    c = await signed_in(app, "a@example.com", plan="silver")
    del c.headers["X-CSRF-Token"]
    assert (await c.post("/api/screener/baskets", json=b())).status_code == 403
    c.headers["X-CSRF-Token"] = "wrong"
    assert (await c.post("/api/screener/baskets", json=b())).status_code == 403
    await c.aclose()


async def test_basket_crud_counts_duplicate_rename(app):  # noqa: F811
    c = await signed_in(app, "a@example.com", plan="silver")
    r = await c.post("/api/screener/baskets", json=b("Value", "P/E < 15 AND ROE > 3", note="mine", columns=["pb", "pb"], sort={"key": "roe", "dir": "desc"}))
    assert r.status_code == 201
    made = r.json()["basket"]
    assert made["name"] == "Value" and made["count"] == 6 and made["status"] == "ok" and made["columns"] == ["pb"] and made["sort"]["key"] == "roe"      # pe < 15 -> i < 10 and roe > 3 -> i in 4..9
    listed = (await c.get("/api/screener/baskets")).json()
    assert listed["max"] == 20 and [x["name"] for x in listed["baskets"]] == ["Value"]
    # the count comes from today's table, and is saved for the stale case
    one = (await c.get(f"/api/screener/baskets/{made['id']}")).json()["basket"]
    assert one["count"] == made["count"]
    assert (await c.put(f"/api/screener/baskets/{made['id']}", json={"name": "  Cheap   and good "})).json()["basket"]["name"] == "Cheap and good"
    upd = (await c.put(f"/api/screener/baskets/{made['id']}", json={"query": "ROE >= 38"})).json()["basket"]
    assert upd["count"] == 2 and upd["name"] == "Cheap and good" and upd["columns"] == ["pb"]
    dup = await c.post(f"/api/screener/baskets/{made['id']}/duplicate", json={})
    assert dup.status_code == 201 and dup.json()["basket"]["name"] == "Copy of Cheap and good" and dup.json()["basket"]["query"] == "ROE >= 38"
    dup2 = await c.post(f"/api/screener/baskets/{made['id']}/duplicate", json={})
    assert dup2.json()["basket"]["name"] == "Copy of Cheap and good (2)"
    assert (await c.post(f"/api/screener/baskets/{made['id']}/duplicate", json={"name": "cheap AND good"})).status_code == 409     # names are unique ignoring case
    assert (await c.put(f"/api/screener/baskets/{dup.json()['basket']['id']}", json={"name": "CHEAP and good"})).status_code == 409
    assert (await c.delete(f"/api/screener/baskets/{made['id']}")).status_code == 200
    assert (await c.delete(f"/api/screener/baskets/{made['id']}")).status_code == 404
    assert len((await c.get("/api/screener/baskets")).json()["baskets"]) == 2
    await c.aclose()


async def test_basket_rejects_bad_queries_names_and_locked_ratios(app):  # noqa: F811
    c = await signed_in(app, "a@example.com", plan="silver")
    r = await c.post("/api/screener/baskets", json=b("Bad", "Foo > 1 AND ROE >"))
    assert r.status_code == 422 and r.json()["detail"]["status"] == "invalid_query" and [e["code"] for e in r.json()["detail"]["errors"]] == ["unknown_metric", "missing_value"]
    assert (await c.post("/api/screener/baskets", json=b("   ", "ROE > 1"))).status_code == 422
    assert (await c.post("/api/screener/baskets", json=b("x" * 81, "ROE > 1"))).status_code == 422
    assert (await c.post("/api/screener/baskets", json=b("L", "FinLit score > 50"))).json()["detail"]["plan"] == "gold"
    assert (await c.post("/api/screener/baskets", json=b("C", "ROE > 1", columns=["nonsense"]))).status_code == 422
    assert (await c.post("/api/screener/baskets", json=b("C", "ROE > 1", columns=["overall"]))).status_code == 403
    assert (await c.get("/api/screener/baskets/not-a-uuid")).status_code == 404
    assert (await c.get("/api/screener/baskets")).json()["baskets"] == []
    await c.aclose()


async def test_baskets_are_private_and_limited_by_plan(app):  # noqa: F811
    mine = await signed_in(app, "a@example.com", plan="basic")
    other = await signed_in(app, "o@example.com", plan="gold")
    ids = []
    for i in range(3):
        r = await mine.post("/api/screener/baskets", json=b(f"B{i}", f"ROE > {i}"))
        assert r.status_code == 201, r.text
        ids.append(r.json()["basket"]["id"])
    over = await mine.post("/api/screener/baskets", json=b("B3"))
    assert over.status_code == 403 and over.json()["detail"]["status"] == "limit" and over.json()["detail"]["max"] == 3
    assert (await mine.post(f"/api/screener/baskets/{ids[0]}/duplicate", json={})).status_code == 403          # a copy counts too
    assert (await mine.get("/api/screener/baskets")).json()["max"] == 3
    # someone else's baskets are invisible and untouchable
    assert (await other.get("/api/screener/baskets")).json()["baskets"] == []
    assert (await other.get(f"/api/screener/baskets/{ids[0]}")).status_code == 404
    assert (await other.put(f"/api/screener/baskets/{ids[0]}", json={"name": "stolen"})).status_code == 404
    assert (await other.delete(f"/api/screener/baskets/{ids[0]}")).status_code == 404
    assert (await other.post(f"/api/screener/baskets/{ids[0]}/duplicate", json={})).status_code == 404
    assert len((await mine.get("/api/screener/baskets")).json()["baskets"]) == 3
    await mine.delete(f"/api/screener/baskets/{ids[0]}")
    assert (await mine.post("/api/screener/baskets", json=b("B0"))).status_code == 201                      # room again
    await mine.aclose(); await other.aclose()


async def test_a_basket_that_uses_a_locked_ratio_after_a_downgrade_is_marked_not_counted(app):  # noqa: F811
    c = await signed_in(app, "a@example.com", plan="silver")
    made = (await c.post("/api/screener/baskets", json=b("Book", "P/B < 3"))).json()["basket"]
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = 'basic' WHERE lower(email) = 'a@example.com'")
    c2 = new_client(app)
    r = await c2.post("/api/auth/login", json={"email": "a@example.com", "password": "a-long-unusual-phrase-42"}, headers=ORIGIN)
    c2.headers.update({**ORIGIN, "X-CSRF-Token": r.json()["csrf"]})
    item = (await c2.get("/api/screener/baskets")).json()["baskets"][0]
    assert item["id"] == made["id"] and item["status"] == "locked" and item["count"] is None
    await c.aclose(); await c2.aclose()
