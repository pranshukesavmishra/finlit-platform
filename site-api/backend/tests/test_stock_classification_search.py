import pytest
from fastapi import HTTPException

from backend import server


@pytest.fixture
def classification_directory(monkeypatch):
    monkeypatch.setattr(server, "_stock_search_cache", {})
    items = [
        {"symbol": "RELIANCE", "name": "Reliance Industries Ltd", "instrumentKey": "RELIANCE", "bseCode": "500325"},
        {"symbol": "IOC", "name": "Indian Oil Corporation Ltd", "instrumentKey": "IOC", "bseCode": "530965"},
    ]
    monkeypatch.setattr(server, "_finedge_all_symbols", lambda: items)
    return items


def test_classification_search_uses_exact_parameters_resolves_bse_and_deduplicates(monkeypatch, classification_directory):
    calls = []

    def provider(path, params):
        calls.append((path, params))
        return {"symbols": [" RELIANCE ", "500325", "IOC", "544999", "", None]}

    monkeypatch.setattr(server, "_finedge_get", provider)
    result = server._search_finedge_classification("industry", " Petroleum Products ")
    assert calls == [("/stock-search", {"group": "industry", "value": "Petroleum Products"})]
    assert len(result) == 3
    assert sum(item["symbol"] == "RELIANCE" for item in result) == 1
    assert next(item for item in result if item["symbol"] == "IOC")["name"] == "Indian Oil Corporation Ltd"
    assert next(item for item in result if item["symbol"] == "544999")["instrumentKey"] == "544999"
    assert server._search_finedge_classification("industry", "Petroleum Products") == result
    assert len(calls) == 1
    server._search_finedge_classification("sector", "Petroleum Products")
    assert len(calls) == 2


def test_empty_classification_results_do_not_become_name_search(monkeypatch, classification_directory):
    monkeypatch.setattr(server, "_finedge_get", lambda *_args: {"symbols": []})
    assert server._search_finedge_classification("sector", "No Such Sector") == []


def test_classification_errors_are_not_cached_as_empty_results(monkeypatch, classification_directory):
    def provider(*_args):
        raise HTTPException(status_code=403, detail="Provider unavailable")

    monkeypatch.setattr(server, "_finedge_get", provider)
    with pytest.raises(HTTPException):
        server._search_finedge_classification("industry", "Banks")
    assert server._stock_search_cache == {}
    with pytest.raises(HTTPException):
        server._search_finedge_classification("industry", "   ")


def test_name_search_uses_directory_without_calling_classification_api(monkeypatch, classification_directory):
    def provider(*_args):
        pytest.fail("Name search must not call the classification endpoint")

    monkeypatch.setattr(server, "_finedge_get", provider)
    assert server._search_finedge_stocks("reliance") == [classification_directory[0]]
