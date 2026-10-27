"""FinLit AI with the FinLit data tools: the tool loop against a fake Gemini and a fake MCP endpoint (no network, no key)."""
import asyncio
import json
import sys
import types
from types import SimpleNamespace

import pytest
import requests

from backend import mcp_tools, server

TOOLS = [
    {"name": "get_stock_quote", "description": "Latest price of one company.", "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"], "additionalProperties": False}},
    {"name": "get_market_overview", "description": "Indices.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "screen_stocks", "description": "Screener.", "inputSchema": {"type": "object", "properties": {"filters": {"type": "object", "propertyNames": {"enum": ["pe", "roe"]}, "additionalProperties": {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}}}}}}},
]
QUOTE = {"tool": "get_stock_quote", "data": {"symbol": "RELIANCE", "quote": {"price": 1184.0, "changePct": -1.21}}, "source": "FinLit", "asOf": "2026-09-29T15:59:02+05:30", "disclaimer": "d"}


class FakeMcp:
    """Stands in for requests.post to the MCP endpoint."""

    def __init__(self, tools=TOOLS, results=None, down=False, status=200):
        self.tools, self.results, self.down, self.status = tools, results or {}, down, status
        self.calls = []

    def __call__(self, url, data=None, headers=None, timeout=None, allow_redirects=None):
        body = json.loads(data)
        self.calls.append({"url": url, "method": body["method"], "params": body.get("params"), "headers": headers, "timeout": timeout})
        if self.down:
            raise requests.ConnectionError("refused")
        if self.status != 200:
            return SimpleNamespace(status_code=self.status, json=lambda: {})
        if body["method"] == "tools/list":
            result = {"tools": self.tools}
        else:
            name = body["params"]["name"]
            r = self.results.get(name)
            result = r(body["params"]["arguments"]) if callable(r) else r
            if result is None:
                result = {"content": [{"type": "text", "text": "nothing"}], "isError": True}
        return SimpleNamespace(status_code=200, json=lambda: {"jsonrpc": "2.0", "id": 1, "result": result})

    @property
    def listed(self):
        return sum(1 for c in self.calls if c["method"] == "tools/list")


def ok_result(envelope):
    return {"content": [{"type": "text", "text": json.dumps(envelope)}], "structuredContent": envelope, "isError": False}


class FakeGemini:
    def __init__(self, script):
        self.script, self.calls = script, []

    def generate_content(self, **kwargs):
        self.calls.append({"contents": list(kwargs["contents"]), "config": kwargs["config"], "model": kwargs["model"]})
        step = self.script(len(self.calls), kwargs)
        return step

    def install(self, monkeypatch):
        fake_types = SimpleNamespace(
            GenerateContentConfig=lambda **kw: kw, Tool=lambda **kw: {"tool": kw}, FunctionDeclaration=lambda **kw: kw,
            AutomaticFunctionCallingConfig=lambda **kw: kw)
        fake_genai = SimpleNamespace(Client=lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=self.generate_content)), types=fake_types)
        google_module = types.ModuleType("google")
        google_module.genai = fake_genai
        monkeypatch.setitem(sys.modules, "google", google_module)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


def asks(*calls, text=""):
    return SimpleNamespace(text=text, function_calls=[SimpleNamespace(name=n, args=a) for n, a in calls],
                           candidates=[SimpleNamespace(finish_reason="STOP", content={"role": "model", "parts": [{"function_call": {"name": n, "args": a}} for n, a in calls]})])


def says(text):
    return SimpleNamespace(text=text, function_calls=None, candidates=[SimpleNamespace(finish_reason="STOP")])


def request(ip="203.0.113.7"):
    return SimpleNamespace(client=SimpleNamespace(host="test-chat-client"), headers={"x-forwarded-for": ip})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    mcp_tools.reset_cache()
    yield
    mcp_tools.reset_cache()


def use_mcp(monkeypatch, mcp):
    monkeypatch.setenv("MCP_INTERNAL_URL", "http://mcp.test/mcp")
    monkeypatch.setattr(mcp_tools.requests, "post", mcp)
    return mcp


def chat(message="What is Reliance's share price?", ip="203.0.113.7"):
    return asyncio.run(server.chat(server.ChatRequest(message=message), request(ip)))


def test_tool_round_trip_answers_from_the_tool_data_and_names_the_source(monkeypatch):
    mcp = use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    gem = FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "RELIANCE"})) if n == 1 else says("Reliance last traded at Rs 1184.00, down 1.21%, as of 29 Sep 2026."))
    gem.install(monkeypatch)
    out = chat().response
    assert out.startswith("Reliance last traded at Rs 1184.00") and out.endswith("Data from FinLit tools: get_stock_quote")
    first, second = gem.calls
    assert [d["name"] for d in first["config"]["tools"][0]["tool"]["function_declarations"]] == ["get_stock_quote", "get_market_overview", "screen_stocks"]
    assert first["config"]["automatic_function_calling"] == {"disable": True}
    sysmsg = first["config"]["system_instruction"]
    assert "Use a tool for EVERY number" in sysmsg and "Never invent" in sysmsg and "as-of date" in sysmsg and "Never say or imply that anyone should buy" in sysmsg
    assert "Do not invent live market data" in sysmsg                                  # every earlier guard is still there
    turn_model, turn_tool = second["contents"][-2], second["contents"][-1]
    assert turn_model["role"] == "model" and turn_tool["role"] == "user"
    reply = turn_tool["parts"][0]["function_response"]
    assert reply["name"] == "get_stock_quote" and reply["response"] == QUOTE            # exactly what the tool returned
    calls = [c for c in mcp.calls if c["method"] == "tools/call"]
    assert calls[0]["params"] == {"name": "get_stock_quote", "arguments": {"symbol": "RELIANCE"}}
    assert all(c["headers"]["x-forwarded-for"] == "203.0.113.7" for c in mcp.calls)    # the visitor's own address, so limits are theirs
    assert all(c["timeout"][1] <= 20 for c in mcp.calls)


def test_tool_list_is_fetched_once_and_cached_for_ten_minutes(monkeypatch):
    mcp = use_mcp(monkeypatch, FakeMcp())
    FakeGemini(lambda n, kw: says("General education answer.")).install(monkeypatch)
    chat(), chat()
    assert mcp.listed == 1
    t = mcp_tools.monotonic()
    monkeypatch.setattr(mcp_tools, "monotonic", lambda: t + mcp_tools.CACHE_SECONDS + 1)
    chat()
    assert mcp.listed == 2


def test_a_tool_error_is_passed_to_the_model_and_no_source_is_claimed(monkeypatch):
    use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": {"content": [{"type": "text", "text": "The company NOSUCH was not found in FinLit's data."}], "isError": True}}))
    gem = FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "NOSUCH"})) if n == 1 else says("I could not find that company in FinLit's data."))
    gem.install(monkeypatch)
    out = chat("price of NOSUCH").response
    assert gem.calls[1]["contents"][-1]["parts"][0]["function_response"]["response"] == {"error": "The company NOSUCH was not found in FinLit's data."}
    assert out == "I could not find that company in FinLit's data." and "Data from FinLit tools" not in out


def test_unknown_tool_and_unreachable_endpoint_are_errors_for_the_model_not_crashes(monkeypatch):
    mcp = use_mcp(monkeypatch, FakeMcp())
    gem = FakeGemini(lambda n, kw: asks(("delete_everything", {})) if n == 1 else says("That is not something I can look up."))
    gem.install(monkeypatch)
    chat()
    assert gem.calls[1]["contents"][-1]["parts"][0]["function_response"]["response"] == {"error": "That tool does not exist."}
    assert not [c for c in mcp.calls if c["method"] == "tools/call"]
    # the endpoint dies between listing and calling
    mcp_tools.reset_cache()
    mcp2 = FakeMcp(results={"get_stock_quote": ok_result(QUOTE)})
    use_mcp(monkeypatch, mcp2)
    real = mcp2.__call__

    def flaky(url, data=None, **kw):
        if json.loads(data)["method"] == "tools/call":
            raise requests.Timeout("slow")
        return real(url, data=data, **kw)
    monkeypatch.setattr(mcp_tools.requests, "post", flaky)
    gem2 = FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "TCS"})) if n == 1 else says("The data service did not answer."))
    gem2.install(monkeypatch)
    out = chat().response
    assert gem2.calls[1]["contents"][-1]["parts"][0]["function_response"]["response"] == {"error": "The data service could not be reached right now."}
    assert "Data from FinLit tools" not in out


def test_at_most_four_tool_rounds_then_the_model_must_answer_without_tools(monkeypatch):
    mcp = use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    gem = FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "TCS"})) if "tools" in kw["config"] else says("With what I found: the price is above."))
    gem.install(monkeypatch)
    out = chat().response
    tool_runs = [c for c in mcp.calls if c["method"] == "tools/call"]
    assert len(tool_runs) == mcp_tools.MAX_TOOL_ROUNDS == 4
    assert len(gem.calls) == 6 and ["tools" in c["config"] for c in gem.calls] == [True] * 5 + [False]
    assert out.startswith("With what I found") and out.endswith("Data from FinLit tools: get_stock_quote")


def test_round_limit_with_no_final_text_gives_a_plain_fallback(monkeypatch):
    use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "TCS"}))).install(monkeypatch)
    assert chat().response.startswith(server.CHAT_TOOL_FALLBACK)


def test_many_calls_in_one_round_are_capped_and_each_gets_an_answer(monkeypatch):
    mcp = use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    gem = FakeGemini(lambda n, kw: asks(*[("get_stock_quote", {"symbol": f"S{i}"}) for i in range(7)]) if n == 1 else says("Done."))
    gem.install(monkeypatch)
    chat()
    replies = gem.calls[1]["contents"][-1]["parts"]
    assert len(replies) == 7 and len([c for c in mcp.calls if c["method"] == "tools/call"]) == mcp_tools.MAX_CALLS_PER_ROUND
    assert replies[-1]["function_response"]["response"] == {"error": "Too many tool calls at once; ask for fewer."}


def test_endpoint_down_the_chat_works_exactly_as_before(monkeypatch, caplog):
    mcp = use_mcp(monkeypatch, FakeMcp(down=True))
    gem = FakeGemini(lambda n, kw: says("This is general financial education."))
    gem.install(monkeypatch)
    out = chat().response
    assert out == "This is general financial education." and len(gem.calls) == 1
    assert "tools" not in gem.calls[0]["config"] and "automatic_function_calling" not in gem.calls[0]["config"]
    assert "FinLit data tools" not in gem.calls[0]["config"]["system_instruction"] and "Do not invent live market data" in gem.calls[0]["config"]["system_instruction"]
    assert "event=mcp_list_failed" in caplog.text and "refused" not in caplog.text
    chat()
    assert mcp.listed == 1                                       # one quick attempt, then a minute of not trying: a down endpoint costs nothing


@pytest.mark.parametrize("value", ["off", "", "0"])
def test_tools_can_be_switched_off(monkeypatch, value):
    mcp = use_mcp(monkeypatch, FakeMcp())
    monkeypatch.setenv("MCP_INTERNAL_URL", value)
    gem = FakeGemini(lambda n, kw: says("Plain answer."))
    gem.install(monkeypatch)
    assert chat().response == "Plain answer." and not mcp.calls and "tools" not in gem.calls[0]["config"]


def test_sdk_trouble_building_the_tools_also_falls_back(monkeypatch):
    use_mcp(monkeypatch, FakeMcp())
    gem = FakeGemini(lambda n, kw: says("Plain answer."))
    gem.install(monkeypatch)
    monkeypatch.setattr(sys.modules["google.genai"].types, "Tool", lambda **kw: (_ for _ in ()).throw(ValueError("schema")))
    assert chat().response == "Plain answer." and "tools" not in gem.calls[0]["config"]


def test_guards_still_apply_with_tools(monkeypatch):
    use_mcp(monkeypatch, FakeMcp())
    FakeGemini(lambda n, kw: says("ok")).install(monkeypatch)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.chat(server.ChatRequest(message="   "), request()))
    assert e.value.status_code == 400
    for i in range(server.CHAT_MAX_REQUESTS_PER_MINUTE):
        chat(ip="198.51.100.9")
    with pytest.raises(HTTPException) as e:
        chat(ip="198.51.100.9")
    assert e.value.status_code == 429
    with pytest.raises(ValueError):
        server.ChatRequest(message="x" * 2001)
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(HTTPException) as e:
        chat(ip="198.51.100.10")
    assert e.value.status_code == 503


def test_advice_sentences_are_dropped_from_tool_based_answers(monkeypatch):
    use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    text = "Reliance traded at Rs 1184 as of 29 Sep. You should buy it now. Its 52-week low is Rs 1182.05. Our price target is 1500."
    FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "RELIANCE"})) if n == 1 else says(text)).install(monkeypatch)
    out = chat().response
    assert out.startswith("Reliance traded at Rs 1184 as of 29 Sep. Its 52-week low is Rs 1182.05.") and "buy" not in out.split("Data from")[0] and "target" not in out


def test_strip_recommendations_keeps_neutral_text():
    keep = "Promoters hold 50.48% as of Jun 2026. The stock has fallen 13.75% in a year. A buyback is not planned."
    assert server.strip_recommendations(keep) == keep
    assert server.strip_recommendations("It is a good buy. We recommend holding this.") == ""


def test_long_tool_results_are_shortened_for_the_model(monkeypatch):
    big = {"tool": "x", "data": {"rows": ["y" * 100] * 1000}, "asOf": "2026-01-01"}
    use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(big)}))
    gem = FakeGemini(lambda n, kw: asks(("get_stock_quote", {"symbol": "TCS"})) if n == 1 else says("ok"))
    gem.install(monkeypatch)
    chat()
    resp = gem.calls[1]["contents"][-1]["parts"][0]["function_response"]["response"]
    assert len(resp["partialJson"]) == mcp_tools.MAX_RESULT_CHARS and "shortened" in resp["note"]


def test_gemini_schema_keeps_only_what_gemini_accepts():
    decls = mcp_tools.declarations(TOOLS)
    assert decls[1] == {"name": "get_market_overview", "description": "Indices."}                    # no parameters at all for a tool without arguments
    props = decls[2]["parameters"]["properties"]["filters"]["properties"]
    assert set(props) == {"pe", "roe"} and props["pe"]["properties"] == {"min": {"type": "number"}, "max": {"type": "number"}}
    assert "additionalProperties" not in json.dumps(decls) and "propertyNames" not in json.dumps(decls)
    assert decls[0]["parameters"]["required"] == ["symbol"]
