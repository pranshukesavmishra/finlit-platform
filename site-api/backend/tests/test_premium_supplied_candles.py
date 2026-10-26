"""FinLit addition: Dhan candles supplied by the research API (premium_supplied_candles.py) and their use by the premium report.

Covers: supplied wins when valid, invalid or incomplete data falls back exactly as before, the provider label is true, a series is
never mixed between providers, and the technical input hash covers the supplied candles.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from backend import premium_service, server
from backend import premium_supplied_candles as supplied_mod
from backend.premium_technical import build_technical_assessment
from backend.tests.test_premium_technical import ASOF, candles

NAMES = {"NIF50": "Nifty 50", "NIFMID100": "Nifty Midcap 100", "NIFSMA100": "Nifty Smallcap 100", "NIF500": "Nifty 500"}


def rows(bars, bump=0.0, scale=1.0):
    return [[b["date"], (b["open"] + bump) * scale, (b["high"] + bump) * scale, (b["low"] + bump) * scale, (b["close"] + bump) * scale, b["volume"]] for b in bars]


def payload(count=600, bump=0.0, price=None):
    """Synthetic Dhan candles. `price`: scale the STOCK so its last close is that price (the quote price check compares the two)."""
    bars = candles(count)
    scale = price / (bars[-1]["close"] + bump) if price else 1.0
    return {"stock": {"provider": "Dhan", "candles": rows(bars, bump, scale)},
            "indices": {code: {"provider": "Dhan", "candles": rows(bars, 1.0)} for code in NAMES}}


FIXTURE_PRICE = 1210            # the quote price of the audit fixture's RELIANCE (premium_stock_audit_2026_10_18.json)


# ----------------------------------------------------------------------------------------------------------- the module
def test_valid_series_are_taken_whole_and_labelled_dhan():
    sup = payload()
    price = supplied_mod.supplied_price_input(sup, ASOF)
    assert price["provider"] == "Dhan" and len(price["bars"]) == 600 and "Dhan" in price["notes"][0]
    required = [b["date"] for b in price["bars"][-505:]]
    bench = supplied_mod.supplied_benchmarks(sup, ASOF, required)
    assert set(bench) == set(NAMES.values()) and all(v["provider"] == "Dhan" for v in bench.values())
    assert bench["Nifty 50"]["bars"][-1] == {"date": ASOF.isoformat(), "open": 100 + 599 + 1.0 - 1, "high": 102 + 599 + 1.0, "low": 98 + 599 + 1.0,
                                             "close": 100 + 599 + 1.0, "volume": 1000 + 599}


@pytest.mark.parametrize("mutate", [
    lambda s: s["stock"].update(provider="Upstox"),                                    # a label that is not true
    lambda s: s["stock"].update(provider="dhan"),
    lambda s: s["stock"].update(candles=s["stock"]["candles"][:200]),                 # too short
    lambda s: s["stock"]["candles"].insert(5, list(s["stock"]["candles"][5])),         # duplicate date
    lambda s: s["stock"]["candles"].reverse(),                                         # not sorted
    lambda s: s["stock"]["candles"][10].__setitem__(4, None),                          # missing close
    lambda s: s["stock"]["candles"][10].__setitem__(4, float("nan")),
    lambda s: s["stock"]["candles"][10].__setitem__(3, 0),                             # zero low
    lambda s: s["stock"]["candles"][10].__setitem__(5, -1),                            # negative volume
    lambda s: s["stock"]["candles"][10].__setitem__(2, 1.0),                           # high below open/close
    lambda s: s["stock"]["candles"][10].__setitem__(0, "2026-13-40"),                  # not a date
    lambda s: s["stock"]["candles"][10].__setitem__(1, True),                          # a bool is not a price
    lambda s: s["stock"]["candles"][10].pop(),                                         # five fields
    lambda s: s["stock"]["candles"].__setitem__(slice(None), s["stock"]["candles"][:-30]),   # stale: ends more than 10 days before as_of
    lambda s: s.__setitem__("stock", "not an object"),
])
def test_invalid_stock_series_is_refused(mutate):
    sup = payload()
    mutate(sup)
    assert supplied_mod.supplied_price_input(sup, ASOF) is None


def test_non_dict_and_oversized_payloads_are_refused_without_raising():
    for junk in (None, [], "x", 5, {"stock": None}, {"stock": {"provider": "Dhan", "candles": "x"}}):
        assert supplied_mod.supplied_price_input(junk, ASOF) is None
        assert supplied_mod.supplied_benchmarks(junk, ASOF, []) == {}
    big = payload(600)
    big["stock"]["candles"] = big["stock"]["candles"] * 4          # 2,400 rows
    assert supplied_mod.supplied_price_input(big, ASOF) is None


def test_rows_after_the_last_completed_session_are_dropped_not_kept():
    sup = payload()
    last = date.fromisoformat(sup["stock"]["candles"][-1][0])
    sup["stock"]["candles"].append([(last + timedelta(days=1)).isoformat(), 5, 6, 4, 5, 1])
    price = supplied_mod.supplied_price_input(sup, ASOF)
    assert price["bars"][-1]["date"] == ASOF.isoformat() and len(price["bars"]) == 600


def test_an_index_series_with_a_missing_stock_session_or_too_short_is_left_out():
    sup = payload()
    price = supplied_mod.supplied_price_input(sup, ASOF)
    required = [b["date"] for b in price["bars"][-505:]]
    del sup["indices"]["NIF50"]["candles"][550]                                         # a session the stock has
    sup["indices"]["NIF500"]["candles"] = sup["indices"]["NIF500"]["candles"][-400:]   # fewer than 505
    sup["indices"]["NIFMID100"]["provider"] = "FinEdge"
    got = supplied_mod.supplied_benchmarks(sup, ASOF, required)
    assert set(got) == {"Nifty Smallcap 100"}


def test_fallback_is_used_only_for_the_series_that_are_not_supplied_and_never_mixed_in_a_series():
    sup = payload()
    price = supplied_mod.supplied_price_input(sup, ASOF)
    required = [b["date"] for b in price["bars"][-505:]]
    sup["indices"]["NIF500"]["candles"][3][2] = 0.5                                      # invalid row: the whole series goes
    finedge = {name: {"bars": [{"date": d, "close": 7.0} for d in required], "provider": "FinEdge", "notes": []} for name in NAMES.values()}
    calls = []
    got = supplied_mod.benchmarks_with_supplied(sup, ASOF, required, lambda: calls.append(1) or deepcopy(finedge))
    assert calls == [1]
    assert got["Nifty 500"]["provider"] == "FinEdge" and got["Nifty 500"]["bars"] == finedge["Nifty 500"]["bars"]
    assert all(got[n]["provider"] == "Dhan" for n in ("Nifty 50", "Nifty Midcap 100", "Nifty Smallcap 100"))
    assert all(len(got[n]["bars"]) == 600 for n in ("Nifty 50",))
    # all four valid: the fallback (FinEdge/Upstox network calls) is never made
    good = payload()
    assert len(supplied_mod.benchmarks_with_supplied(good, ASOF, required, lambda: pytest.fail("fallback must not run"))) == 4


def test_prices_fallback_runs_only_when_the_supplied_stock_is_unusable():
    sentinel = {"bars": [], "provider": "Upstox"}
    assert supplied_mod.prices_with_supplied(None, ASOF, lambda: sentinel) is sentinel
    bad = payload()
    bad["stock"]["provider"] = "X"
    assert supplied_mod.prices_with_supplied(bad, ASOF, lambda: sentinel) is sentinel
    assert supplied_mod.prices_with_supplied(payload(), ASOF, lambda: pytest.fail("fallback must not run"))["provider"] == "Dhan"


# ------------------------------------------------------------------------------------------------- the assessment itself
def assess(sup):
    price = supplied_mod.supplied_price_input(sup, ASOF)
    bench = supplied_mod.supplied_benchmarks(sup, ASOF, [b["date"] for b in price["bars"][-505:]])
    return build_technical_assessment(price, ASOF, bench, 100)


def test_assessment_names_dhan_and_the_input_hash_covers_every_supplied_candle():
    a = assess(payload())
    assert a["provider"] == "Dhan" and a["status"] == "ready"
    assert {v["provider"] for v in a["benchmarkSources"].values()} == {"Dhan"}
    assert any("Dhan" in n for n in a["notes"]) and not any("Upstox" in n for n in a["notes"])
    assert assess(payload())["inputHash"] == a["inputHash"]                              # deterministic
    stock_changed = payload()
    stock_changed["stock"]["candles"][100][5] += 1                                       # one volume figure of the stock
    assert assess(stock_changed)["inputHash"] != a["inputHash"]
    index_changed = payload()
    index_changed["indices"]["NIF500"]["candles"][100][1] += 0.5                         # an index OPEN, which the model does not read
    assert assess(index_changed)["inputHash"] != a["inputHash"]


# ------------------------------------------------------------------------ through server._premium_dashboard_inputs
@pytest.fixture
def dashboard(monkeypatch):
    data = json.loads((Path(__file__).parent / "fixtures" / "premium_stock_audit_2026_10_18.json").read_text())["stocks"][0]
    raw, symbol = data["raw"], data["symbol"]
    instrument = {"symbol": symbol, "name": symbol, "isin": "INE000A01010", "instrumentKey": symbol}
    monkeypatch.setattr(server, "_resolve_finedge_stock", lambda q: instrument)
    monkeypatch.setattr(server, "_try_resolve_upstox_instrument", lambda *q: {**instrument, "instrumentKey": "NSE_EQ|INE000A01010", "exchange": "NSE"})
    monkeypatch.setattr(server, "_stock_fundamentals_cache", {})
    monkeypatch.setattr(server, "_safe_upstox_get", lambda path, *a, **k: {})
    upstox_calls = []
    old = [{"date": (date(2026, 10, 18) - timedelta(days=300 - i)).isoformat(), "close": 100 + i, "volume": 1000} for i in range(300)]
    monkeypatch.setattr(server, "_fetch_upstox_price_history", lambda key: upstox_calls.append(key) or deepcopy(old))
    monkeypatch.setattr(server, "_finedge_statement", lambda s, b, c, p: deepcopy(raw.get({"pl": "annual" if p == "yearly" else "quarterly", "bs": "balance" if p == "yearly" else "balance_recent", "cf": "cashflow"}[c], {}).get("financials", [])))
    finedge_paths = []

    def get(path, params=None):
        finedge_paths.append(path)
        if path.startswith("/company-profile/"):
            return deepcopy(raw["profile"])
        if path.startswith("/daily-quotes/"):
            return deepcopy(raw["prices"])
        if path == "/quote":
            return deepcopy(raw["quote"])
        if path.startswith("/shareholdings/"):
            return deepcopy(raw.get({"summary": "summary", "distribution": "distribution", "declaration": "declaration"}.get(path.split("/")[2], ""), {}))
        return {}
    monkeypatch.setattr(server, "_finedge_get", get)
    monkeypatch.setattr("backend.premium_benchmarks.peer_benchmark", lambda *a: ({}, {}))
    monkeypatch.setattr("backend.premium_technical_sources._CACHE", {})
    return symbol, upstox_calls, finedge_paths


NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)      # 17:30 IST on ASOF: its session is complete


def test_supplied_candles_win_through_the_report_and_the_usual_providers_are_not_asked_for_candles(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    report = premium_service.generate_report(server._finedge_get, symbol, symbol, "consolidated", "r" * 32, "2026-10-23",
                                             lambda s, t, n: server._premium_dashboard_inputs(s, t, n, payload(price=FIXTURE_PRICE)))
    tech = report["technicalAssessment"]
    assert tech["provider"] == "Dhan" and tech["status"] == "ready"
    assert {v["provider"] for v in tech["benchmarkSources"].values()} == {"Dhan"}
    assert not any(p.startswith("/index/") for p in finedge_paths)   # (the dashboard's own Upstox price-history reads are not the technical ones)


def test_without_supplied_candles_the_original_path_runs_unchanged(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    raw, *_ = server._premium_dashboard_inputs(symbol, "consolidated", NOW)
    assert raw["technicalPriceInput"]["provider"] != "Dhan"
    assert any(p.startswith("/index/") for p in finedge_paths)


def test_unusable_supplied_candles_fall_back_exactly_as_before(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    bad = payload()
    bad["stock"]["candles"][5][4] = None
    bad["indices"] = {"NIF50": {"provider": "Upstox", "candles": []}}
    raw, *_ = server._premium_dashboard_inputs(symbol, "consolidated", NOW, bad)
    assert raw["technicalPriceInput"]["provider"] != "Dhan"
    assert all(v["provider"] != "Dhan" for v in raw["technicalBenchmarks"].values())
    assert any(p.startswith("/index/") for p in finedge_paths)


def test_request_model_accepts_the_optional_field_and_old_bodies_still_work():
    assert server.PremiumReportRequest(query="TCS").suppliedCandles is None
    body = server.PremiumReportRequest(query="TCS", delivery="inline", suppliedCandles=payload(300))
    assert body.suppliedCandles["stock"]["provider"] == "Dhan"
    assert len(json.dumps(payload(1550))) < 2_000_000          # six years x five series stays well inside any proxy body limit


# ------------------------------------------------------------------------------------------ plausibility of a supplied series
def split_series(unadjusted, factor=5, at=400):
    """Stock candles through a 1:`factor` split at row `at`. Dhan's adjusted series is smooth; an unadjusted one drops by 1/factor overnight."""
    sup = payload()
    for index, row in enumerate(sup["stock"]["candles"]):
        divisor = factor if (index >= at or not unadjusted) else 1     # adjusted: every older price is divided too, so the series stays smooth
        row[1:5] = [value / divisor for value in row[1:5]]
    return sup


def test_a_legitimate_split_adjusted_series_is_accepted():
    bars = supplied_mod.supplied_price_input(split_series(unadjusted=False), ASOF)["bars"]
    assert len(bars) == 600 and all(abs(b["close"] / a["close"] - 1) < .4 for a, b in zip(bars, bars[1:]))


def test_a_genuine_unadjusted_split_is_refused_and_the_reason_is_logged(caplog):
    with caplog.at_level("WARNING"):
        assert supplied_mod.supplied_price_input(split_series(unadjusted=True), ASOF) is None
    assert "more than 40% in a day" in caplog.text and "stock" in caplog.text
    # a 2:1 bonus issue (price halves) and a 1:10 split too
    assert supplied_mod.supplied_price_input(split_series(True, 2), ASOF) is None
    assert supplied_mod.supplied_price_input(split_series(True, 10), ASOF) is None


@pytest.mark.parametrize("factor,usable", [(1.39, True), (1.41, False), (0.61, True), (0.59, False)])
def test_the_daily_move_limit_is_forty_percent_either_way(factor, usable):
    sup = payload()
    for row in sup["stock"]["candles"][300:]:
        row[1:5] = [value * factor for value in row[1:5]]
    # (the first row after the jump is the only large move; 100+299 -> x factor)
    assert (supplied_mod.supplied_price_input(sup, ASOF) is not None) is usable


def test_an_index_series_with_an_implausible_move_is_left_out():
    sup = payload()
    price = supplied_mod.supplied_price_input(sup, ASOF)
    for row in sup["indices"]["NIF50"]["candles"][500:]:
        row[1:5] = [value / 3 for value in row[1:5]]
    got = supplied_mod.supplied_benchmarks(sup, ASOF, [b["date"] for b in price["bars"][-505:]])
    assert set(got) == {"Nifty Midcap 100", "Nifty Smallcap 100", "Nifty 500"}


def test_the_last_close_must_be_within_fifteen_percent_of_the_quote_price(caplog):
    sup = payload()
    last = sup["stock"]["candles"][-1][4]
    for quote, usable in ((last, True), (last * 1.17, True), (last * 1.1765, False), (last / 1.14, True), (last / 0.84, False),
                          (last * 0.5, False), (last * 3, False), (None, True), (0, True), (-5, True), (float("nan"), True)):
        assert (supplied_mod.supplied_price_input(sup, ASOF, quote) is not None) is usable, quote
    with caplog.at_level("WARNING"):
        supplied_mod.supplied_price_input(sup, ASOF, last * 3)
    assert "from the quote price" in caplog.text
    assert supplied_mod.prices_with_supplied(sup, ASOF, lambda: "fallback", last * 3) == "fallback"
    assert supplied_mod.prices_with_supplied(sup, ASOF, lambda: "fallback", last)["provider"] == "Dhan"


def test_quote_price_is_read_from_the_raw_inputs():
    assert supplied_mod.quote_price_from_raw({"quote": {"TCS": {"current_price": 4000.5}}}) == 4000.5
    for raw in (None, {}, {"quote": None}, {"quote": {"TCS": {"current_price": None}}}, {"quote": {"TCS": {"current_price": 0}}},
                {"quote": {"TCS": "x"}}, {"quote": {"TCS": {"current_price": True}}}):
        assert supplied_mod.quote_price_from_raw(raw) is None


@pytest.mark.parametrize("text", ["2026-W43-1", "20261022", "2026-10-2 ", "２０２６-10-22", "2026/10/22", "2026-1-022", "٢٠٢٦-١٠-٢٢", "2026-10-22T"])
def test_only_strict_calendar_dates_are_accepted(text):
    sup = payload()
    sup["stock"]["candles"][10][0] = text
    assert supplied_mod.supplied_price_input(sup, ASOF) is None


def test_a_supplied_candles_value_that_is_not_an_object_does_not_refuse_the_request(caplog):
    for junk in ("x", 5, [1, 2], True):
        with caplog.at_level("WARNING"):
            request = server.PremiumReportRequest(query="TCS", suppliedCandles=junk)
        assert request.suppliedCandles is None
    assert "suppliedCandles ignored" in caplog.text
    assert server.PremiumReportRequest(query="TCS").suppliedCandles is None
    assert server.PremiumReportRequest(query="TCS", suppliedCandles={"stock": 1}).suppliedCandles == {"stock": 1}


def test_a_bad_quote_price_basis_falls_back_through_the_dashboard(dashboard):
    symbol, upstox_calls, finedge_paths = dashboard
    raw, *_ = server._premium_dashboard_inputs(symbol, "consolidated", NOW, payload(price=FIXTURE_PRICE * 1.3))
    assert raw["technicalPriceInput"]["provider"] != "Dhan"
    raw, *_ = server._premium_dashboard_inputs(symbol, "consolidated", NOW, payload(price=FIXTURE_PRICE * 1.1))
    assert raw["technicalPriceInput"]["provider"] == "Dhan"
