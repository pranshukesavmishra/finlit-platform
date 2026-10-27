"""The MCP server: the protocol, its safeguards, and that every tool returns the numbers the website's own routes return (same app, anonymous visitor)."""

import json
from datetime import date, timedelta

import pytest

from finlit.mcp import protocol
from finlit.mcp.schema import ArgError, clean_symbol, validate
from finlit.mcp.server import DISCLAIMER, shrink, tools_listing
from finlit.mcp.tools import BY_NAME, TOOLS
from test_auth import app, new_client  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, make_settings, store  # noqa: F401
from test_results import seeded  # noqa: F401  (a results quarter with declarations)
from test_etf import NOW as ETF_NOW, Provider as EtfProvider
from test_flows import fake_sites as flows_sites, nifty as flows_nifty
from test_macro import fake_sites as macro_sites
from test_mf import amfi_client

TOOL_NAMES = ["search_stocks", "get_stock_quote", "get_batch_quotes", "get_company_profile", "get_financials", "get_ratios", "get_shareholding",
              "get_price_history", "get_finlit_score", "get_quarter_results", "get_results_calendar", "screen_stocks", "get_market_overview",
              "get_fii_dii_flows", "get_ipo_calendar", "search_funds", "get_fund_details", "list_etfs", "get_etf", "get_data_freshness"]


@pytest.fixture
async def markets(app, monkeypatch):  # noqa: F811
    """Recorded flows, economy figures, index prices, mutual funds and ETFs loaded the way their own tests load them."""
    import httpx
    from datetime import date as D
    from finlit import etf, flows, indices, macro, mf
    from finlit.config import Settings
    store = app.state.store
    for mod, name, val in ((flows, "PAUSE", 0), (flows, "OI_PAUSE", 0), (flows, "FIRST", D(2025, 8, 1)), (flows, "DII_START", D(2026, 10, 14)), (macro, "PAUSE", 0), (etf, "MIN_INSTRUMENTS", 10)):
        monkeypatch.setattr(mod, name, val)
    await indices.warm(app)
    assert (await macro.refresh(store, transport=macro_sites(), today=D(2026, 10, 23), full=True))["status"] in ("ok", "partial")
    assert (await flows.refresh(store, transport=flows_sites()[0], today=D(2026, 10, 23), nifty=flows_nifty))["status"] == "ok"
    async with amfi_client() as c:
        assert (await mf.refresh(store, None, client=c))["status"] == "ok"
    s = Settings(upstox_access_token="placeholder", database_url=make_settings().database_url, redis_url=make_settings().redis_url)
    assert (await etf.refresh(store, s, transport=httpx.MockTransport(EtfProvider()), now=ETF_NOW))["status"] == "ok"
    async for k in store.redis.scan_iter("*"):
        if not k.startswith(b"rl:"):
            await store.redis.delete(k)
    return store


def rpc(method, params=None, id_=1):
    m = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        m["id"] = id_
    if params is not None:
        m["params"] = params
    return m


async def call(c, name, args=None, **kw):
    r = await c.post("/mcp", json=rpc("tools/call", {"name": name, "arguments": args or {}}), **kw)
    assert r.status_code == 200, r.text
    return r.json()["result"]


async def ok(c, name, args=None):
    res = await call(c, name, args)
    assert res["isError"] is False, res
    return res["structuredContent"]


async def err(c, name, args=None):
    res = await call(c, name, args)
    assert res["isError"] is True and "structuredContent" not in res and res["content"][0]["type"] == "text"
    return res["content"][0]["text"]


# ------------------------------------------------------------------------------------------------ protocol (no database)
async def one(msg):
    async def boom(name, args):
        raise AssertionError("no tool should run")
    return await protocol.handle_one(msg, lambda: [], boom)


@pytest.mark.parametrize("asked", ["2025-06-18", "2025-03-26", "2024-11-05"])
async def test_initialize_answers_each_supported_version_with_itself(asked):
    r = await one(rpc("initialize", {"protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}))
    assert r["id"] == 1 and r["result"]["protocolVersion"] == asked
    assert r["result"]["capabilities"]["tools"] == {"listChanged": False} and r["result"]["serverInfo"]["name"] == "finlit"
    assert "not a recommendation" in r["result"]["instructions"]


async def test_initialize_with_an_unknown_version_gets_the_newest_one():
    assert (await one(rpc("initialize", {"protocolVersion": "1999-01-01"})))["result"]["protocolVersion"] == "2025-06-18"
    assert (await one(rpc("initialize", {})))["result"]["protocolVersion"] == "2025-06-18"


async def test_ping_lists_and_notifications():
    assert (await one(rpc("ping")))["result"] == {}
    assert (await one(rpc("resources/list")))["result"] == {"resources": []}
    assert (await one(rpc("prompts/list")))["result"] == {"prompts": []}
    assert await one(rpc("notifications/initialized", id_=None)) is None
    assert await one(rpc("some/unknown/notification", id_=None)) is None     # a notification is never answered, not even with an error
    assert await one({"jsonrpc": "2.0", "id": 5, "result": {}}) is None       # a reply from the client: ignored


@pytest.mark.parametrize("msg, code", [
    (rpc("no/such/method"), -32601),
    ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600),
    ({"id": 1, "method": "ping"}, -32600),
    ({"jsonrpc": "2.0", "id": 1}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": 5}, -32600),
    ({"jsonrpc": "2.0", "id": [1], "method": "ping"}, -32600),
    ("just text", -32600), (42, -32600), (None, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]}, -32602),
    (rpc("tools/call", {}), -32602),
    (rpc("tools/call", {"name": 5}), -32602),
    (rpc("tools/call", {"name": "x", "arguments": [1]}), -32602),
])
async def test_json_rpc_error_codes(msg, code):
    r = await one(msg)
    assert r["jsonrpc"] == "2.0" and r["error"]["code"] == code and isinstance(r["error"]["message"], str)


async def test_the_id_is_echoed_exactly():
    for i in (7, "abc", 0, 1.5):
        assert (await one(rpc("ping", id_=i)))["id"] == i


# ------------------------------------------------------------------------------------------------ tool list and schemas
def test_the_tools_are_exactly_the_documented_set_and_read_only():
    listing = tools_listing()
    assert [t["name"] for t in listing] == TOOL_NAMES
    for t in listing:
        assert t["annotations"]["readOnlyHint"] is True and t["annotations"]["destructiveHint"] is False
        assert t["inputSchema"]["type"] == "object" and t["inputSchema"]["additionalProperties"] is False and len(t["description"]) > 30
        for bad in ("add", "delete", "remove", "create", "update", "save", "write", "watchlist", "portfolio", "login", "set_"):
            assert bad not in t["name"], t["name"]
    assert len(TOOLS) == len(BY_NAME) == 20


def test_every_tool_has_a_schema_that_json_serialises():
    json.dumps(tools_listing())


def test_symbol_rule():
    assert clean_symbol(" reliance ") == "RELIANCE" and clean_symbol("m&m") == "M&M" and clean_symbol("bajaj-auto") == "BAJAJ-AUTO"
    for bad in ("", "A" * 21, "RELI ANCE", "../etc", "A;B", "A_B", "AB%", 5, None, "TC\nS"):
        with pytest.raises(ArgError):
            clean_symbol(bad)


def test_validation_clamps_numbers_and_rejects_the_rest():
    schema = BY_NAME["get_price_history"].listing()["inputSchema"]
    clean, notes = validate({"symbol": "tcs", "days": 99999}, schema)
    assert clean["days"] == 1825 and clean["interval"] == "daily" and notes
    assert validate({"symbol": "tcs", "days": 1}, schema)[0]["days"] == 5
    for args in ({"symbol": "TCS", "days": "9"}, {"symbol": "TCS", "interval": "hourly"}, {"symbol": "TCS", "extra": 1}, {}, {"symbol": "TCS", "days": True}, {"symbol": "TCS", "days": 2.5}):
        with pytest.raises(ArgError):
            validate(args, schema)
    batch = BY_NAME["get_batch_quotes"].listing()["inputSchema"]
    with pytest.raises(ArgError):
        validate({"symbols": ["A"] * 21}, batch)
    with pytest.raises(ArgError):
        validate({"symbols": []}, batch)


def test_shrink_cuts_the_biggest_list_and_says_so():
    env = {"data": {"prices": [{"d": i, "pad": "x" * 50} for i in range(400)], "small": [1, 2, 3]}, "notes": []}
    out = shrink(env, 5000)
    assert out["truncated"] is True and len(json.dumps(out)) <= 5200 and out["data"]["prices"][-1]["d"] == 399   # newest kept for a series
    assert out["data"]["small"] == [1, 2, 3] and "too large" in out["notes"][0]
    assert "truncated" not in shrink({"data": {"a": [1]}, "notes": []}, 10000)


# ------------------------------------------------------------------------------------------------ HTTP: transport, safeguards
async def test_http_initialize_list_and_envelope(app):  # noqa: F811
    async with new_client(app) as c:
        r = await c.post("/mcp", json=rpc("initialize", {"protocolVersion": "2025-06-18"}))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json") and r.headers["cache-control"] == "no-store"
        assert r.json()["result"]["protocolVersion"] == "2025-06-18"
        r = await c.post("/mcp", json=rpc("tools/list"))
        assert [t["name"] for t in r.json()["result"]["tools"]] == TOOL_NAMES
        r = await c.post("/mcp", json=rpc("notifications/initialized", id_=None))
        assert r.status_code == 202 and r.content == b""
        sc = await ok(c, "get_stock_quote", {"symbol": "reliance"})
        for key in ("source", "asOf", "disclaimer", "data", "routes", "notes"):
            assert key in sc
        assert sc["disclaimer"] == DISCLAIMER and "not a recommendation" in sc["disclaimer"] and "not registered with SEBI or AMFI" in sc["disclaimer"]
        res = await call(c, "get_stock_quote", {"symbol": "RELIANCE"})
        assert json.loads(res["content"][0]["text"]) == res["structuredContent"] and " " not in res["content"][0]["text"][:30]    # compact JSON


async def test_batch_requests(app):  # noqa: F811
    async with new_client(app) as c:
        r = await c.post("/mcp", json=[rpc("ping", id_=1), rpc("notifications/initialized", id_=None), rpc("tools/list", id_="b"), rpc("nope", id_=3)])
        got = {x["id"]: x for x in r.json()}
        assert r.status_code == 200 and set(got) == {1, "b", 3} and got[3]["error"]["code"] == -32601 and len(got["b"]["result"]["tools"]) == 20
        r = await c.post("/mcp", json=[rpc("notifications/initialized", id_=None)])
        assert r.status_code == 202
        r = await c.post("/mcp", json=[])
        assert r.status_code == 400 and r.json()["error"]["code"] == -32600
        r = await c.post("/mcp", json=[rpc("ping", id_=i) for i in range(25)])
        assert r.status_code == 400
        r = await c.post("/mcp", json=[1, "x"])
        assert r.status_code == 200 and [x["error"]["code"] for x in r.json()] == [-32600, -32600]


async def test_bad_bodies_and_headers(app):  # noqa: F811
    async with new_client(app) as c:
        r = await c.post("/mcp", content=b"{not json", headers={"content-type": "application/json"})
        assert r.status_code == 400 and r.json()["error"]["code"] == -32700 and r.json()["id"] is None
        r = await c.post("/mcp", content=b"\xff\xfe", headers={"content-type": "application/json"})
        assert r.status_code == 400
        assert (await c.post("/mcp", content=b"{}", headers={"content-type": "text/plain"})).status_code == 415
        assert (await c.post("/mcp", json=rpc("ping"), headers={"accept": "text/event-stream"})).status_code == 406
        assert (await c.post("/mcp", json=rpc("ping"), headers={"accept": "application/json, text/event-stream"})).status_code == 200
        assert (await c.post("/mcp", json=rpc("ping"), headers={"mcp-protocol-version": "2025-06-18"})).status_code == 200
        r = await c.post("/mcp", json=rpc("ping"), headers={"mcp-protocol-version": "2020-01-01"})
        assert r.status_code == 400 and "Unsupported" in r.json()["error"]["message"]


async def test_get_and_other_methods_are_405_with_allow_post(app):  # noqa: F811
    async with new_client(app) as c:
        for method in ("GET", "DELETE", "PUT"):
            r = await c.request(method, "/mcp", headers={"accept": "text/event-stream"})
            assert r.status_code == 405 and r.headers["allow"] == "POST", method


async def test_origin_check(app, monkeypatch):  # noqa: F811
    import dataclasses
    async with new_client(app) as c:
        assert (await c.post("/mcp", json=rpc("ping"))).status_code == 200                                    # no Origin: a command-line or server client
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "https://evil.example"})).status_code == 200   # allowed_hosts is * in this test setup
        monkeypatch.setattr(app.state, "settings", dataclasses.replace(app.state.settings, allowed_hosts=["finlitventures.com", "localhost"], cors_origins=["https://app.example.com"]))
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "https://evil.example", "host": "localhost"})).status_code == 403
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "null", "host": "localhost"})).status_code == 403
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "http://localhost:3000", "host": "localhost"})).status_code == 200
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "https://finlitventures.com", "host": "localhost"})).status_code == 200
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "https://app.example.com", "host": "localhost"})).status_code == 200
        assert (await c.post("/mcp", json=rpc("ping"), headers={"host": "localhost"})).status_code == 200
        assert (await c.post("/mcp", json=rpc("ping"), headers={"origin": "https://finlitventures.com.evil.example", "host": "localhost"})).status_code == 403


async def test_rate_limit_per_minute_and_daily_cap(app, monkeypatch):  # noqa: F811
    await app.state.store.redis.flushdb()
    monkeypatch.setenv("MCP_RATE_PER_MINUTE", "4")
    async with new_client(app) as c:
        codes = [(await c.post("/mcp", json=rpc("ping"))).status_code for _ in range(6)]
        assert codes == [200, 200, 200, 200, 429, 429]
        r = await c.post("/mcp", json=rpc("ping"))
        assert int(r.headers["retry-after"]) >= 1 and r.json()["error"]["message"].startswith("Rate limit")
    await app.state.store.redis.flushdb()
    monkeypatch.setenv("MCP_RATE_PER_MINUTE", "100")
    monkeypatch.setenv("MCP_DAILY_CAP", "2")
    async with new_client(app) as c:
        assert (await c.post("/mcp", json=rpc("ping"))).status_code == 200                              # only tool calls count against the daily cap
        assert (await c.post("/mcp", json=rpc("tools/call", {"name": "get_data_freshness", "arguments": {}}))).status_code == 200
        assert (await c.post("/mcp", json=rpc("tools/call", {"name": "get_data_freshness", "arguments": {}}))).status_code == 200
        r = await c.post("/mcp", json=rpc("tools/call", {"name": "get_data_freshness", "arguments": {}}))
        assert r.status_code == 429 and "daily" in r.json()["error"]["message"]
    await app.state.store.redis.flushdb()


async def test_request_size_cap_and_switch(app, monkeypatch):  # noqa: F811
    async with new_client(app) as c:
        monkeypatch.setenv("MCP_MAX_BODY_BYTES", "300")
        big = rpc("tools/call", {"name": "search_stocks", "arguments": {"query": "x" * 400}})
        r = await c.post("/mcp", json=big)
        assert r.status_code == 413
        assert (await c.post("/mcp", json=rpc("ping"))).status_code == 200
        monkeypatch.delenv("MCP_MAX_BODY_BYTES")
        r = await c.post("/mcp", content=b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"a" * 70_000 + b'"}}', headers={"content-type": "application/json"})
        assert r.status_code == 413                                                                    # also over the site-wide 64 KB body cap
        monkeypatch.setenv("MCP_ENABLED", "0")
        assert (await c.post("/mcp", json=rpc("ping"))).status_code == 404
        assert (await c.get("/mcp")).status_code == 404 and (await c.get("/.well-known/mcp.json")).status_code == 404


async def test_well_known_file(app):  # noqa: F811
    async with new_client(app) as c:
        r = await c.get("/.well-known/mcp.json")
        j = r.json()
        assert r.status_code == 200 and j["endpoint"] == "http://test/mcp" and j["transport"] == "streamable-http" and j["tools"] == 20
        assert j["toolNames"] == TOOL_NAMES and j["authentication"] == "none" and j["readOnly"] is True


async def test_unknown_tool_and_argument_errors(app):  # noqa: F811
    async with new_client(app) as c:
        r = await c.post("/mcp", json=rpc("tools/call", {"name": "delete_everything", "arguments": {}}))
        assert r.json()["error"]["code"] == -32602 and "Unknown tool" in r.json()["error"]["message"]
        for bad in ("RELI ANCE", "x" * 50, "../../etc/passwd", "RELIANCE;DROP"):
            assert "Invalid arguments" in await err(c, "get_stock_quote", {"symbol": bad})
        assert "Missing required" in await err(c, "get_stock_quote", {})
        assert "Unknown argument" in await err(c, "get_stock_quote", {"symbol": "TCS", "cookie": "x"})
        assert "at most 20" in await err(c, "get_batch_quotes", {"symbols": ["TCS"] * 21})
        assert "not a filter" in await err(c, "screen_stocks", {"filters": {"revenue": {"min": 1}}})
        assert "was not found" in await err(c, "get_stock_quote", {"symbol": "NOSUCHCO"})


async def test_calls_are_counted_per_tool_per_day(app):  # noqa: F811
    from datetime import datetime
    from finlit.mcp.server import IST
    await app.state.store.redis.flushdb()
    async with new_client(app) as c:
        await ok(c, "get_data_freshness")
        await ok(c, "get_data_freshness")
        await err(c, "get_stock_quote", {"symbol": "bad sym"})
    raw = await app.state.store.redis.hgetall(f"mcp:calls:{datetime.now(IST).date().isoformat()}")
    assert {k.decode(): int(v) for k, v in raw.items()} == {"get_data_freshness": 2, "get_stock_quote:error": 1}


async def test_oversized_results_are_cut_and_still_valid(app, markets, monkeypatch):  # noqa: F811
    monkeypatch.setenv("MCP_MAX_RESULT_BYTES", "2500")
    async with new_client(app) as c:
        sc = await ok(c, "list_etfs", {"limit": 50})
        assert sc["truncated"] is True and "too large" in " ".join(sc["notes"]) and len(json.dumps(sc)) < 3000 and sc["data"]["etfs"]
        res = await call(c, "get_market_overview")
        assert json.loads(res["content"][0]["text"])["truncated"] is True


# ------------------------------------------------------------------------------------------------ every tool equals the website's route
async def site(c, path, **kw):
    r = await (c.post(path, **kw) if "json" in kw else c.get(path))
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    return r.json()


async def test_quote_profile_batch_equal_the_summary_route(app):  # noqa: F811
    async with new_client(app) as c:
        s = await site(c, "/api/stocks/RELIANCE")
        q = await ok(c, "get_stock_quote", {"symbol": "reliance"})
        assert q["data"]["quote"] == s["quote"] and q["data"]["quote"]["price"] == 1184.0 and q["asOf"] == s["quote"]["asOf"] and q["data"]["name"] == s["profile"]["name"]
        assert q["data"]["range52"] == s["range52"] and q["routes"] == ["/api/stocks/RELIANCE"]
        p = await ok(c, "get_company_profile", {"symbol": "RELIANCE"})
        assert p["data"]["profile"] == s["profile"] and p["asOf"] == s["meta"]["generatedAt"]
        b = await ok(c, "get_batch_quotes", {"symbols": ["reliance", "RELIANCE", "NOSUCHCO"]})
        rows = {r["symbol"]: r for r in b["data"]["quotes"]}
        assert list(rows) == ["RELIANCE", "NOSUCHCO"] and rows["RELIANCE"]["quote"] == s["quote"]
        assert rows["NOSUCHCO"]["quote"] is None and "not found" in rows["NOSUCHCO"]["error"]           # missing is missing, not zero


async def test_financials_equal_the_financials_route(app):  # noqa: F811
    async with new_client(app) as c:
        f = await site(c, "/api/stocks/RELIANCE/financials")
        a = (await ok(c, "get_financials", {"symbol": "RELIANCE", "period": "annual", "limit": 3}))["data"]
        pl = f["yearly"]["pl"]
        assert a["profitAndLoss"]["periods"] == pl["periods"][-3:] and a["unit"] == f["unit"] == "Cr"
        for k, v in pl["rows"].items():
            assert a["profitAndLoss"]["rows"][k] == v[-3:], k
        assert a["balanceSheet"]["rows"] == {k: v[-3:] for k, v in f["yearly"]["bs"]["rows"].items()} and "cashFlow" in a
        qd = (await ok(c, "get_financials", {"symbol": "RELIANCE", "period": "quarterly", "limit": 4}))
        assert qd["data"]["profitAndLoss"]["rows"]["revenue"] == f["quarterly"]["pl"]["rows"]["revenue"][-4:]
        assert "balanceSheet" not in qd["data"] and any("balance sheet" in n for n in qd["notes"])        # stated as not available
        assert qd["asOf"] == f["quarterly"]["pl"]["periodEnds"][-1]
        default = (await ok(c, "get_financials", {"symbol": "RELIANCE"}))["data"]
        assert default["period"] == "annual" and len(default["profitAndLoss"]["periods"]) == 8


async def test_ratios_and_shareholding_equal_their_routes(app):  # noqa: F811
    async with new_client(app) as c:
        r = await site(c, "/api/stocks/RELIANCE/ratios")
        got = (await ok(c, "get_ratios", {"symbol": "RELIANCE"}))["data"]
        assert {k: v["value"] for k, v in got["latest"].items()} == {k: v["value"] for k, v in r["latest"].items()} and got["latest"]["roce"]["value"] == 7.29
        assert got["latest"]["roce"]["period"] == "FY26"
        for k, v in r["history"]["rows"].items():
            assert got["history"]["rows"][k] == v[-8:]
        o = await site(c, "/api/stocks/RELIANCE/ownership")
        sh = await ok(c, "get_shareholding", {"symbol": "RELIANCE"})
        assert sh["data"]["series"] == o["series"] and sh["data"]["latest"] == o["latest"] and sh["asOf"] == o["asOf"] == "Jun 2026"


async def test_price_history_equals_the_price_routes(app):  # noqa: F811
    async with new_client(app) as c:
        p = await site(c, "/api/stocks/RELIANCE/price-1M")
        got = await ok(c, "get_price_history", {"symbol": "RELIANCE", "days": 30})
        rows = got["data"]["prices"]
        s = p["series"]
        assert [r["close"] for r in rows] == s["c"][-len(rows):] and [r["date"] for r in rows] == s["t"][-len(rows):] and [r["volume"] for r in rows] == s["v"][-len(rows):]
        assert rows[-1]["close"] == 1184.0 and got["asOf"] == s["t"][-1] == got["data"]["to"] and got["data"]["interval"] == "daily"
        assert (date.fromisoformat(s["t"][-1]) - date.fromisoformat(rows[0]["date"])).days <= 30
        wk = (await ok(c, "get_price_history", {"symbol": "RELIANCE", "days": 30, "interval": "weekly"}))["data"]["prices"]
        assert len(wk) < len(rows) and wk[-1]["close"] == rows[-1]["close"] and sum(r["volume"] for r in wk) == sum(r["volume"] for r in rows)
        assert max(r["high"] for r in wk) == max(r["high"] for r in rows) and min(r["low"] for r in wk) == min(r["low"] for r in rows)
        long = await ok(c, "get_price_history", {"symbol": "RELIANCE", "days": 1825, "interval": "daily"})
        five = await site(c, "/api/stocks/RELIANCE/price-5Y")
        assert long["data"]["interval"] == "weekly" and [r["close"] for r in long["data"]["prices"]] == five["series"]["c"][-long["data"]["count"]:]
        assert all(r["open"] is None for r in long["data"]["prices"]) and any("weekly" in n for n in long["notes"])


async def test_score_only_where_the_website_shows_it(app):  # noqa: F811
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'LOCKEDCO'")
        await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) SELECT 'LOCKEDCO', statement, section, body, etag, generated_at FROM snapshots WHERE symbol = 'RELIANCE'")
    try:
        async with new_client(app) as c:
            s = await site(c, "/api/stocks/RELIANCE")
            sc = (await ok(c, "get_finlit_score", {"symbol": "RELIANCE"}))["data"]
            assert sc["locked"] is False and sc["score"]["overall"] == s["score"]["overall"] == 51 and sc["score"]["band"] == s["score"]["band"]
            assert [(p["key"], p["score"]) for p in sc["score"]["pillars"]] == [(p["key"], p["score"]) for p in s["score"]["pillars"]]
            locked = await ok(c, "get_finlit_score", {"symbol": "LOCKEDCO"})
            site_view = await site(c, "/api/stocks/LOCKEDCO")
            assert site_view["score"]["overall"] is None and locked["data"]["locked"] is True and locked["data"]["score"] is None
            assert "Silver" in locked["data"]["message"]
            text = json.dumps(locked)
            assert str(s["score"]["overall"]) + "," not in text and "thesis" not in text and "pillars" not in text      # nothing leaks
    finally:
        async with app.state.store.pool.acquire() as conn:
            await conn.execute("DELETE FROM snapshots WHERE symbol = 'LOCKEDCO'")


async def test_search_stocks(app):  # noqa: F811
    async with new_client(app) as c:
        got = (await ok(c, "search_stocks", {"query": "reli"}))["data"]
        assert got["companies"][0]["symbol"] == "RELIANCE" and got["companies"][0]["reportReady"] is True and got["companies"][0]["bseCode"] == "500325"
        assert (await ok(c, "search_stocks", {"query": "500325"}))["data"]["companies"][0]["symbol"] == "RELIANCE"
        none = await ok(c, "search_stocks", {"query": "zzzzqqqq"})
        assert none["data"]["companies"] == [] and any("No company matched" in n for n in none["notes"])
        assert len((await ok(c, "search_stocks", {"query": "a", "limit": 3}))["data"]["companies"]) == 3
        assert "empty" in await err(c, "search_stocks", {"query": "  "})


async def test_screener_equals_the_screener_route_and_stays_in_the_free_tier(app):  # noqa: F811
    async with new_client(app) as c:
        body = {"filters": {"pe": {"max": 60}}, "cats": {}, "q": "", "sort": {"key": "market_cap", "dir": "desc"}, "columns": ["market_cap", "price", "pe"], "limit": 5}
        route = await site(c, "/api/screener/query", json=body)
        got = (await ok(c, "screen_stocks", {"filters": {"pe": {"max": 60}}, "limit": 5}))["data"]
        assert got["matched"] == route["total"] and [r["symbol"] for r in got["rows"]] == [r["symbol"] for r in route["rows"]]
        assert [r["values"] for r in got["rows"]] == [r["v"] for r in route["rows"]] and got["rows"][0]["values"]["pe"] == 40.86
        # a Silver filter is refused by the route and by the tool (the key is not even offered)
        assert (await c.post("/api/screener/query", json={"filters": {"revenue": {"min": 1}}})).status_code == 403
        assert "not a filter" in await err(c, "screen_stocks", {"filters": {"revenue": {"min": 1}}})
        assert "not a filter" in await err(c, "screen_stocks", {"filters": {"overall": {"min": 50}}})
        sch = BY_NAME["screen_stocks"].listing()["inputSchema"]["properties"]["filters"]["propertyNames"]["enum"]
        assert "revenue" not in sch and "pe" in sch
        cap = (await ok(c, "screen_stocks", {"limit": 500}))
        assert cap["data"]["returned"] <= 25 and any("maximum 25" in n for n in cap["notes"])


async def test_quarter_results_and_calendar_equal_the_results_route(app, seeded):  # noqa: F811
    q = seeded["quarter"]
    async with new_client(app) as c:
        route = await site(c, f"/api/results/quarter?quarter={q}&limit=100")
        got = await ok(c, "get_quarter_results", {"quarter": q, "limit": 100})
        d = got["data"]
        assert d["quarter"] == q and d["total"] == route["total"] and [r["symbol"] for r in d["rows"]] == [r["symbol"] for r in route["rows"]]
        assert [r["date"] for r in d["rows"]] == [r["date"] for r in route["rows"]] and d["summary"]["declared"] == route["summary"]["declared"]
        assert all(r["revenue"] is None and r["netProfit"] is None for r in d["rows"]) and any("Silver" in n for n in got["notes"])   # withheld, as for a visitor
        assert (await ok(c, "get_quarter_results", {"quarter": q, "limit": 1}))["data"]["returned"] == 1
        one_day = await ok(c, "get_quarter_results", {"date": seeded["when"].isoformat()}) if seeded["when"] <= date.today() else None
        if one_day:
            assert {r["date"] for r in one_day["data"]["rows"]} == {seeded["when"].isoformat()}
        assert "not both" in await err(c, "get_quarter_results", {"quarter": q, "date": "2026-10-14"})
        assert "Invalid arguments" in await err(c, "get_quarter_results", {"quarter": "2026-07"})
        cal = await ok(c, "get_results_calendar", {"days": 60})
        window_end = (date.today() + timedelta(days=60)).isoformat()
        assert all(r["status"] == "due" and date.today().isoformat() <= r["date"] <= window_end for r in cal["data"]["rows"])
        dates = [r["date"] for r in cal["data"]["rows"]]
        assert dates == sorted(dates)


async def test_markets_flows_ipos_equal_their_routes(app, markets):  # noqa: F811
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM ipos WHERE name LIKE 'McpTest%'")
        t = date.today()
        await conn.execute("INSERT INTO ipos (name, symbol, open_date, close_date, price_low, price_high, lot_size, issue_size_cr) VALUES ('McpTest Open', 'MCPO', $1, $2, 100, 105, 140, 250.5)", t - timedelta(days=1), t + timedelta(days=1))
        await conn.execute("INSERT INTO ipos (name, open_date, close_date) VALUES ('McpTest Soon', $1, $2)", t + timedelta(days=10), t + timedelta(days=12))
    try:
        async with new_client(app) as c:
            ipos = {i["name"]: i for i in (await site(c, "/api/ipos"))["ipos"]}
            allr = {i["name"]: i for i in (await ok(c, "get_ipo_calendar", {}))["data"]["ipos"]}
            assert allr["McpTest Open"] == ipos["McpTest Open"] and allr["McpTest Open"]["priceHigh"] == 105.0 and allr["McpTest Soon"]["priceHigh"] is None   # missing stays null
            only = (await ok(c, "get_ipo_calendar", {"status": "upcoming"}))["data"]["ipos"]
            assert {i["name"] for i in only if i["name"].startswith("McpTest")} == {"McpTest Soon"} and all(i["status"] == "upcoming" for i in only)
            fl = await site(c, "/api/flows")
            f = await ok(c, "get_fii_dii_flows", {"days": 5})
            assert f["data"]["days"] == fl["days"][-5:] and f["data"]["latest"] == fl["latest"] and f["data"]["last30"] == fl["last30"]
            ix = await site(c, "/api/indices")
            m = await ok(c, "get_market_overview")
            by = {i["code"]: i for i in ix["items"]}
            assert m["data"]["indices"] and all(i["close"] == by[i["code"]]["close"] and i["changePct"] == by[i["code"]]["changePct"] for i in m["data"]["indices"] + m["data"]["sectorIndices"])
            assert m["data"]["indices"][0]["code"] == "NIF50" and m["data"]["indices"][0]["close"] == 22888.95 and m["asOf"]["indices"] == ix["asOf"]
            macro = await site(c, "/api/macro")
            assert {e["key"]: e["value"] for e in m["data"]["economy"]} == {e["key"]: e["value"] for e in macro["cards"]}
    finally:
        async with app.state.store.pool.acquire() as conn:
            await conn.execute("DELETE FROM ipos WHERE name LIKE 'McpTest%'")


async def test_funds_and_etfs_equal_their_routes(app, markets):  # noqa: F811
    async with new_client(app) as c:
        route = await site(c, "/api/mf?q=sbi&size=10")
        got = await ok(c, "search_funds", {"query": "sbi"})
        assert got["data"]["total"] == route["total"] and [f["code"] for f in got["data"]["funds"]] == [f["code"] for f in route["items"]] and got["asOf"] == route["dataDate"]
        assert [f["nav"] for f in got["data"]["funds"]] == [f["nav"] for f in route["items"]]
        if route["items"]:
            code = route["items"][0]["code"]
            det = await site(c, f"/api/mf/{code}")
            fd = await ok(c, "get_fund_details", {"code": code})
            assert fd["data"]["name"] == det["name"] if "name" in det else fd["data"].keys() == det.keys()
        assert "Invalid arguments" in await err(c, "get_fund_details", {"code": "abc"})
        assert "not found" in await err(c, "get_fund_details", {"code": 9999999})
        el = await site(c, "/api/etf?limit=5")
        got = await ok(c, "list_etfs", {"limit": 5})
        assert [e["symbol"] for e in got["data"]["etfs"]] == [e["symbol"] for e in el["items"]] and [e["price"] for e in got["data"]["etfs"]] == [e["price"] for e in el["items"]]
        sym = el["items"][0]["symbol"]
        det = await site(c, f"/api/etf/{sym}")
        one_etf = await ok(c, "get_etf", {"symbol": sym})
        assert one_etf["data"]["price"] == det["price"] and one_etf["data"]["nav"] == det["nav"] and one_etf["asOf"] == det["priceDate"]
        assert "not found" in await err(c, "get_etf", {"symbol": "NOSUCHETF"})


async def test_freshness_reports_dates_it_holds(app, markets):  # noqa: F811
    async with new_client(app) as c:
        s = await site(c, "/api/stocks/RELIANCE")
        fr = (await ok(c, "get_data_freshness", {"symbol": "RELIANCE"}))["data"]["datasets"]
        assert fr["company"]["reportBuilt"] == s["meta"]["generatedAt"] and fr["company"]["priceAsOf"] == s["quote"]["asOf"]
        assert fr["indices"]["latestDataDate"] == "2026-10-19" and fr["fiiDiiFlows"]["latestDataDate"] == (await site(c, "/api/flows"))["latest"]["d"] == "2026-10-23"
        assert (await ok(c, "get_data_freshness"))["data"]["datasets"].get("company") is None


async def test_the_tools_never_send_a_session_or_leave_the_free_tier(app):  # noqa: F811
    """A signed-in visitor's cookie on the MCP request is not forwarded: the tools see the site as an anonymous visitor."""
    async with new_client(app) as c:
        c.cookies.set("finlit_session", "whatever")
        r = await c.post("/mcp", json=rpc("tools/call", {"name": "get_ratios", "arguments": {"symbol": "RELIANCE"}}), headers={"authorization": "Bearer x"})
        res = r.json()["result"]
        assert res["isError"] is False
        latest = res["structuredContent"]["data"]["latest"]
        anon = (await site(c, "/api/stocks/RELIANCE/ratios"))["latest"]
        assert set(latest) == set(anon)


async def test_data_that_is_not_loaded_is_said_to_be_missing_never_zero(app):  # noqa: F811
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("TRUNCATE flows_daily, flows_oi, flows_index, flows_meta")
        await conn.execute("DELETE FROM ipos")
    await app.state.store.redis.flushdb()
    async with new_client(app) as c:
        assert "not been loaded" in await err(c, "get_fii_dii_flows")
        fr = (await ok(c, "get_data_freshness"))["data"]["datasets"]
        assert fr["fiiDiiFlows"]["latestDataDate"] is None and "error" in fr["fiiDiiFlows"]
        q = await ok(c, "get_quarter_results")
        assert q["data"]["quarter"] is None and q["data"]["rows"] == [] and any("No quarter" in n for n in q["notes"])
        assert (await ok(c, "get_ipo_calendar"))["data"]["ipos"] == []
