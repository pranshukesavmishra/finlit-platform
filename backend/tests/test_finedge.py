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


def test_has_rows_understands_every_endpoint_shape():
    from finlit.finedge import _has_rows
    assert _has_rows({"symbol": "X", "financials": [{"a": 1}]})
    assert _has_rows({"symbol": "X", "ratios": [{"a": 1}]})
    assert _has_rows({"symbol": "X", "ratio_type": "growth", "financial_metrics": {"cagr": 1}})
    assert _has_rows({"RELIANCE": {"price": 1}})
    assert _has_rows([{"ex_date": "2026-01-01"}])
    assert not _has_rows({"symbol": "X", "financials": []})
    assert not _has_rows({"symbol": "X", "ratio_type": "growth"})
    assert not _has_rows([]) and not _has_rows(None)


def test_announcements_request_carries_the_required_date_range():
    from finlit.finedge import bundle_requests
    _, params, _ = bundle_requests("RELIANCE", "consolidated")["announcements"]
    assert params["symbol"] == "RELIANCE" and params["from_date"] < params["to_date"]


def _stale_consolidated_client(cut_quarter: str, cut_year: str):
    """Consolidated P&L rows stop at the given period ends; standalone is the full recorded set."""
    base = fixture_transport()

    def handler(request):
        p = request.url.params
        response = base.handle_request(request)
        if p.get("statement_type") == "c" and p.get("statement_code") == "pl" and "/financials/" in request.url.path and "basic" not in request.url.path:
            body = response.json()
            cut = cut_quarter if p.get("period") == "quarterly" else cut_year
            body["financials"] = [r for r in body["financials"] if str(r.get("period_end")) <= cut]
            return httpx.Response(200, json=body)
        return response

    return FinEdgeClient(settings(), transport=httpx.MockTransport(handler))


async def test_stale_consolidated_switches_every_statement_to_standalone_and_says_so():
    full = fixture_transport()
    async with FinEdgeClient(settings(), transport=full) as c0:
        latest = (await c0.fetch_bundle("RELIANCE", "standalone"))["pl_quarterly"]["financials"]
    last = max(str(r["period_end"]) for r in latest)
    year = str(int(last[:4]) - 2) + last[4:]
    async with _stale_consolidated_client(year, year) as client:
        bundle = await client.fetch_bundle("RELIANCE", "consolidated")
    assert bundle["statement"] == "standalone" and bundle["requestedStatement"] == "consolidated"
    assert bundle["basisChoice"]["reason"] == "stale_consolidated"
    assert max(str(r["period_end"]) for r in bundle["pl_quarterly"]["financials"]) == last
    sections = build(bundle)
    assert sections["summary"]["meta"]["statement"] == "standalone"
    dq = sections["summary"]["dataQuality"]
    assert dq["basis"]["chosen"] == "standalone"
    assert any("standalone, which are up to date" in n and n.startswith("Consolidated statements stop at") for n in dq["notes"])


async def test_healthy_consolidated_stays_consolidated_and_adds_no_note():
    async with FinEdgeClient(settings()) as client:
        bundle = await client.fetch_bundle("RELIANCE", "consolidated")
    assert bundle["statement"] == "consolidated" and "basisChoice" not in bundle
    assert "pl_annual_standalone" in bundle   # fetched once here, reused by the worker's revenue guard
    assert not any("standalone, which are up to date" in n for n in build(bundle)["summary"]["dataQuality"]["notes"])
