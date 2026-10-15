import httpx
import pytest

from finlit.config import Settings
from finlit.finedge import FinEdgeClient, FinEdgeError, fixture_transport
from finlit.snapshot import build


def settings(**kw):
    return Settings(finedge_api_key="test", finedge_mode="fixtures", **kw)


async def test_fixture_bundle_has_every_section():
    async with FinEdgeClient(settings()) as client:
        bundle = await client.fetch_bundle("reliance", "standalone")
    assert bundle["symbol"] == "RELIANCE"
    assert bundle["errors"] == {}
    sections = build(bundle)
    assert sections["summary"]["dataQuality"]["missing"] == []


async def test_consolidated_falls_back_to_standalone():
    base = fixture_transport()

    def handler(request):
        if request.url.params.get("statement_type") == "c":
            return httpx.Response(200, json={"financials": [], "symbol": "RELIANCE"})
        return base.handle_request(request)

    async with FinEdgeClient(settings(), transport=httpx.MockTransport(handler)) as client:
        bundle = await client.fetch_bundle("RELIANCE", "consolidated")
    assert bundle["statement"] == "standalone"
    assert bundle["pl_annual"]["financials"]


async def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", _no_sleep)
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(429) if hits["n"] < 3 else httpx.Response(200, json={"ok": True})

    async with FinEdgeClient(settings(), transport=httpx.MockTransport(handler)) as client:
        assert await client.get("/x") == {"ok": True}
    assert hits["n"] == 3


async def test_4xx_is_not_retried(monkeypatch):
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", _no_sleep)
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(403, text="plan not entitled")

    async with FinEdgeClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FinEdgeError):
            await client.get("/x")
    assert hits["n"] == 1


async def test_token_sent_as_query_param():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={})

    async with FinEdgeClient(Settings(finedge_api_key="secret-key"), transport=httpx.MockTransport(handler)) as client:
        await client.get("/quote", {"symbol": "TCS"})
    assert seen == {"symbol": "TCS", "token": "secret-key"}


async def _no_sleep(_):
    return None
