from datetime import date
import asyncio
import json
import time
from urllib.parse import urlsplit

import pytest
import requests
import jwt
from fastapi import HTTPException

from backend import server
from backend.market_data import market_params, normalize_market_payload, safe_document_url


def test_market_date_windows_and_symbols():
    params = market_params("transcripts", date(2026, 10, 11), date(2026, 10, 18), " itc ")
    assert params == {"from_date": "2026-10-11", "to_date": "2026-10-18", "symbol": "ITC"}
    with pytest.raises(ValueError):
        market_params("transcripts", date(2026, 10, 1), date(2026, 10, 18))
    with pytest.raises(ValueError):
        market_params("announcements", date(2026, 10, 18), date(2026, 10, 1))
    with pytest.raises(ValueError):
        market_params("announcements", symbol="ITC?token=bad")
    with pytest.raises(ValueError):
        market_params("valuations", index_symbol="")
    assert market_params("indices") == {}
    assert market_params("valuations", date(2026, 10, 1), date(2026, 10, 18), index_symbol="NIF50")["index_symbol"] == "NIF50"


def test_company_feeds_have_explicit_schemas_and_no_duplicates():
    ipo = {"data": [{"symbol": "TEST", "company_name": "Test Ltd", "exchange": ["NSE", "BSE"], "subscription": "0", "token": "private"}]}
    normalized = normalize_market_payload("ipo", ipo)
    assert normalized[0]["exchange"] == "NSE, BSE"
    assert normalized[0]["subscription"] == "0"
    assert "token" not in normalized[0]
    result = {"symbol": "TEST", "company_name": "Test Ltd", "expected_result_date": "2026-10-18"}
    assert normalize_market_payload("results", [result, result]) == [result]


def test_disclosures_use_actual_announcement_date_and_safe_document_fallback():
    row = {"stock_symbol": "TEST", "announcement_date": "2026-10-17 19:30:28", "category": "Earnings call", "description": "Transcript",
           "pdf_file_link": "javascript:alert(1)", "pdf_file_link_hist": "https://example.com/report.pdf"}
    for section in ("transcripts", "announcements"):
        result = normalize_market_payload(section, [row, row])
        assert len(result) == 1
        assert result[0]["date"] == "2026-10-17 19:30:28"
        assert result[0]["document_url"] == "https://example.com/report.pdf"
    for value in ("javascript:alert(1)", "data:text/html,bad", "https://user:secret@example.com/file", None):
        assert safe_document_url(value) is None


def test_index_values_preserve_zero_and_missing_and_sort_history():
    payload = {"index_symbol": "NIF50", "rows": [
        {"quote_date": "2026-10-15", "pe": 0, "pb": None, "div_yield": "1.49"},
        {"quote_date": "2026-10-16", "pe": "19.77", "pb": "NaN"},
    ]}
    rows = normalize_market_payload("valuations", payload)
    assert rows[0]["quote_date"] == "2026-10-16"
    assert rows[0]["index_symbol"] == "NIF50"
    assert rows[0]["pb"] is None
    assert rows[1]["pe"] == 0
    assert rows[1]["div_yield"] == 1.49
    index = normalize_market_payload("indices", [{"index_symbol": "NIF50", "index_name": "Nifty 50", "close_price": 23000, "change_pct": -0.5, "quote_date": "2026-10-16"}])[0]
    assert index["close_price"] == 23000
    assert index["change_pct"] == -0.5


def test_empty_data_and_malformed_provider_responses_are_distinct():
    assert normalize_market_payload("ipo", {"data": []}) == []
    assert normalize_market_payload("announcements", []) == []
    with pytest.raises(ValueError):
        normalize_market_payload("indices", {"error": "subscription required"})


def test_public_feed_caches_empty_results_and_separates_filters(monkeypatch):
    monkeypatch.setattr(server, "_public_market_cache", {})
    calls = []
    monkeypatch.setattr(server, "_finedge_get", lambda path, params: calls.append((path, params)) or [])
    params = {"from_date": "2026-10-11", "to_date": "2026-10-18"}
    first = server._public_market_feed("results", params)
    second = server._public_market_feed("results", params)
    assert first["items"] == [] and not first["cached"]
    assert second["cached"] and len(calls) == 1
    server._public_market_feed("results", {**params, "to_date": "2026-10-19"})
    assert len(calls) == 2


def test_public_feed_masks_provider_credentials_on_errors(monkeypatch):
    monkeypatch.setattr(server, "_public_market_cache", {})

    def failing(*_args):
        raise requests.ConnectionError("https://provider.test?token=private-secret")

    monkeypatch.setattr(server, "_finedge_get", failing)
    with pytest.raises(HTTPException) as error:
        server._public_market_feed("indices", {})
    assert error.value.status_code == 502
    assert "private-secret" not in error.value.detail
    assert not server._public_market_cache


def test_market_feed_requires_admin_and_preserves_validation(isolated_app, monkeypatch):
    app, _ = isolated_app
    monkeypatch.setattr(server, "_public_market_feed", lambda section, params: {"items": [], "section": section, "filters": params})
    monkeypatch.setattr(server, "_commodity_feed", lambda **kwargs: {"items": [], **kwargs})
    async def check():
        async def get(path, authenticated=True):
            finished = asyncio.Event()
            sent = False
            messages = []

            async def receive():
                nonlocal sent
                if sent:
                    await finished.wait()
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    finished.set()

            url = urlsplit(path)
            headers = [(b"host", b"localhost")]
            if authenticated:
                token = jwt.encode({"sub": "admin@example.test", "role": "admin", "iat": int(time.time()), "exp": int(time.time()) + 60}, "test-only-jwt-secret-with-more-than-32-bytes", algorithm="HS256")
                headers.append((b"authorization", f"Bearer {token}".encode()))
            await app({"type": "http", "http_version": "1.1", "method": "GET", "scheme": "http", "path": url.path,
                       "raw_path": url.path.encode(), "query_string": url.query.encode(), "root_path": "",
                       "headers": headers, "server": ("localhost", 80), "client": ("127.0.0.1", 123)}, receive, send)
            status = next(message["status"] for message in messages if message["type"] == "http.response.start")
            body = json.loads(b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body"))
            return status, body

        for section in ("ipo", "results", "announcements", "transcripts", "indices", "valuations"):
            status, _ = await get(f"/api/market-data/{section}", authenticated=False)
            assert status == 401
        for path in ("/api/commodities", "/api/commodities/123"):
            status, _ = await get(path, authenticated=False)
            assert status == 401
            status, _ = await get(path)
            assert status == 200
        status, _ = await get("/api/commodities?category=invalid")
        assert status == 422
        status, _ = await get("/api/commodities/bad-code")
        assert status == 400
        status, body = await get("/api/market-data/indices")
        assert status == 200 and body["section"] == "indices"
        status, _ = await get("/api/market-data/not-a-feed")
        assert status == 422
        status, _ = await get("/api/market-data/transcripts?from_date=2026-10-01&to_date=2026-10-18")
        assert status == 400
    asyncio.run(check())


def test_commodities_preserve_units_zero_missing_and_actual_month_order():
    from market_data import normalize_commodity_list, normalize_commodity_history, normalize_commodity_changes
    assert normalize_commodity_list([{"code": 123, "name": "Gold", "weight": 0}, {"code": "../bad", "name": "Bad"}]) == [{"code": "123", "name": "Gold", "weight": 0}]
    history = normalize_commodity_history([
        {"date_header": "Dec-2025", "timestamp": 202501231, "value": 0},
        {"date_header": "Mar-2026", "timestamp": 202600331, "value": None},
        {"date_header": "invalid", "value": 3}])
    assert [row["period"] for row in history] == ["2026-03", "2025-12"]
    assert history[0]["value"] is None and history[1]["value"] == 0
    assert normalize_commodity_changes({"pct_change": [{"index": "1 month", "change_pct": "-0.50%"}]}) == [{"period": "1 month", "value": -0.5}]
    with pytest.raises(ValueError):
        normalize_commodity_history({"error": "no access"})


def test_commodity_cache_and_partial_change_failure(monkeypatch):
    monkeypatch.setattr(server, "_public_market_cache", {})
    calls = []
    def provider(path, params=None):
        calls.append(path)
        if "pct-change" in path:
            raise requests.ConnectionError("token=secret")
        return [{"date_header": "Mar-2026", "value": 20}]
    monkeypatch.setattr(server, "_finedge_get", provider)
    result = server._commodity_feed(code="123")
    assert result["history"][0]["value"] == 20
    assert result["changesUnavailable"] and result["changes"] == []
    assert server._commodity_feed(code="123")["cached"]
    assert len(calls) == 2
