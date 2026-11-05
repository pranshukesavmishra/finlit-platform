"""disclosure.relay_for: with AMFI_RELAY_URL set, the www.amfiindia.com requests (TER months, TER workbook, average AUM) go through the relay with the shared key;
the scheme master on portal.amfiindia.com and every other address are untouched; with no relay nothing changes."""
import httpx
import pytest

from finlit import disclosure as d


def test_no_relay_leaves_every_address_alone(monkeypatch):
    monkeypatch.delenv("AMFI_RELAY_URL", raising=False)
    assert d.relay_for(d.URL_AUM) == (d.URL_AUM, {})


def test_relay_rewrites_only_www_amfi_addresses_and_sends_the_key(monkeypatch):
    monkeypatch.setenv("AMFI_RELAY_URL", "https://amfi-relay.example.workers.dev/")
    monkeypatch.setenv("AMFI_RELAY_KEY", "k-test")
    assert d.relay_for(d.URL_AUM) == ("https://amfi-relay.example.workers.dev/api/average-aum-schemewise", {"X-Relay-Key": "k-test"})
    assert d.relay_for(d.URL_TER)[0] == "https://amfi-relay.example.workers.dev/api/populate-te-rdata-revised"
    assert d.relay_for(d.URL_TER_MONTHS)[0].endswith("/api/populate-ter-month")
    assert d.relay_for(d.URL_MASTER) == (d.URL_MASTER, {})                      # portal.amfiindia.com answers directly
    assert d.relay_for("https://example.org/x") == ("https://example.org/x", {})


@pytest.mark.asyncio
async def test_a_fetch_goes_to_the_relay_with_its_params_and_header(monkeypatch):
    monkeypatch.setenv("AMFI_RELAY_URL", "https://relay.test")
    monkeypatch.setenv("AMFI_RELAY_KEY", "k")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("x-relay-key")))
        return httpx.Response(200, json=[{"MonthNumber": "2026-10"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        r = await d._get(c, d.URL_TER_MONTHS, params={"year": "2026-2027"})
    assert r.json() == [{"MonthNumber": "2026-10"}]
    assert seen == [("https://relay.test/api/populate-ter-month?year=2026-2027", "k")]
