"""Kept model inputs (premium_cache) must never make the technical view older than a fresh fetch would have it.

Statements, ratios and ownership filings are reused for up to a day; the daily candles are not: supplied (Dhan) candles are always applied
again, and candles that were kept are reused only when they end on today's last completed session and come from the same source."""
from datetime import timedelta

from backend import server
from backend.tests.test_premium_supplied_candles import NOW, dashboard, payload  # noqa: F401  (dashboard is a fixture)


def kept_from(symbol, supplied=None, now=NOW):
    raw, sources, effective, sourcing = server._premium_dashboard_inputs(symbol, "consolidated", now, supplied)
    return {"symbol": symbol, "requested": "consolidated", "fetchedAt": now.isoformat(), "raw": raw, "sources": sources,
            "effective": effective, "sourcing": sourcing}


def test_kept_candles_of_the_same_session_and_source_are_reused_without_a_request(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    kept = kept_from(symbol)
    finedge_paths.clear(); upstox_calls.clear()
    current = server._premium_kept_with_current_technical(kept, NOW, None)
    assert current is not None and current["technicalPriceInput"] == kept["raw"]["technicalPriceInput"]
    assert current["technicalBenchmarks"] == kept["raw"]["technicalBenchmarks"]
    assert finedge_paths == [] and upstox_calls == []
    assert current is not kept["raw"]                       # the kept copy itself is never changed


def test_kept_candles_of_an_earlier_session_are_not_reused(dashboard):
    symbol, *_ = dashboard
    kept = kept_from(symbol)
    assert server._premium_kept_with_current_technical(kept, NOW + timedelta(days=1), None) is None


def test_supplied_candles_replace_the_kept_ones_exactly_as_in_a_fresh_fetch(dashboard):
    symbol, *_ = dashboard
    kept = kept_from(symbol)
    assert kept["raw"]["technicalPriceInput"]["provider"] != "Dhan"
    current = server._premium_kept_with_current_technical(kept, NOW, payload())
    fresh = server._premium_dashboard_inputs(symbol, "consolidated", NOW, payload())[0]
    assert current["technicalPriceInput"] == fresh["technicalPriceInput"] and current["technicalPriceInput"]["provider"] == "Dhan"
    assert current["technicalBenchmarks"] == fresh["technicalBenchmarks"]
    assert kept["raw"]["technicalPriceInput"]["provider"] != "Dhan"
    for key in ("profile", "annual", "quarterly", "balance", "quote"):                  # everything else is the kept data
        assert current[key] == kept["raw"][key]


def test_kept_dhan_candles_are_not_reused_when_no_candles_are_supplied_now(dashboard):
    symbol, *_ = dashboard
    kept = kept_from(symbol, payload())
    assert kept["raw"]["technicalPriceInput"]["provider"] == "Dhan"
    assert server._premium_kept_with_current_technical(kept, NOW, None) is None
    assert server._premium_kept_with_current_technical(kept, NOW, payload()) is not None


def test_kept_inputs_without_technical_data_are_not_used_for_the_technical_view(dashboard):
    symbol, *_ = dashboard
    kept = kept_from(symbol)
    for key in ("technicalPriceInput", "technicalBenchmarks"):
        broken = {**kept, "raw": {k: v for k, v in kept["raw"].items() if k != key}}
        assert server._premium_kept_with_current_technical(broken, NOW, None) is None


def test_the_loader_fetches_everything_when_the_kept_candles_cannot_be_made_current(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    kept = kept_from(symbol)
    finedge_paths.clear()
    fresh = {}
    server._premium_inputs_loader(kept, fresh, None)(symbol, "consolidated", NOW + timedelta(days=1))
    assert fresh and fresh["fetchedAt"] == (NOW + timedelta(days=1)).isoformat() and finedge_paths      # a full fetch, kept again
    finedge_paths.clear(); fresh2 = {}
    server._premium_inputs_loader(kept, fresh2, None)(symbol, "consolidated", NOW)
    assert fresh2 == {} and not any(p.startswith("/financials/") for p in finedge_paths)               # reused
