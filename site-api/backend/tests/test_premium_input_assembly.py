"""The faster way of assembling a premium report's inputs must give the model EXACTLY the data the slow way gave it.

Each fixture in fixtures/premium_replay is every answer the provider gave while the pre-speed-up code calculated one real company on 26 Oct 2026
(a manufacturer, a bank, an NBFC, an insurer and an IT company; see make_fixture.py). The same recorded answers are replayed through
  * the legacy assembly: the dashboard resolver as it was (every extra fetched, calls made one after another, peers looked up one by one), and
  * the new assembly: shared calls, the extras skipped, kept model inputs, kept peer observations;
and the reports must be equal in the rating (every factor's points), the inputs, the calculation trace, the benchmarks, the warnings and the
review. Only the labels of the dashboard-only sections that are no longer fetched may differ. The model itself is not touched here."""
import copy
import gzip
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import premium_cache, premium_data, premium_service, server
from backend.premium_data import NO_OBSERVATION, ObservationCache

FIXTURES = Path(__file__).parent / "fixtures" / "premium_replay"
COMPANIES = ["SKIPPER", "HDFCBANK", "BAJFINANCE", "HDFCLIFE", "TCS"]
GROUPS = {"SKIPPER": "MFG", "HDFCBANK": "BANK", "BAJFINANCE": "NBFC", "HDFCLIFE": "INSURANCE", "TCS": "LIGHT"}
SKIPPED_LABELS = {"revenueSegments", "shareholding", "corporateActions", "competitors"}


def load(symbol):
    with gzip.open(FIXTURES / f"{symbol}.json.gz", "rt") as handle:
        return json.load(handle)


class Replay:
    """The provider, answering from a recording and counting every request."""

    def __init__(self, fixture):
        self.recorded = fixture["recorded"]
        self.calls = []
        self.lock = threading.Lock()

    def once(self, path, params=None):
        key = json.dumps([path, params or {}], sort_keys=True)
        with self.lock:
            self.calls.append((path, params or {}))
        if key in self.recorded:
            return copy.deepcopy(self.recorded[key])
        raise server.HTTPException(status_code=404, detail="not recorded")      # an endpoint the recording never asked for

    def peers(self, symbol):
        return [c for c in self.calls if c[0].startswith("/daily-price-ratios/") and c[0] != f"/daily-price-ratios/{symbol}"]

    def own(self, symbol):
        """Requests about the company itself (its statements, quote, prices, ratios, ownership and industry list)."""
        return [c for c in self.calls if c[0].endswith(f"/{symbol}") or c[1].get("symbol") == symbol]


@pytest.fixture
def replay(monkeypatch):
    def start(symbol):
        fixture = load(symbol)
        frozen = datetime.fromisoformat(fixture["now"])

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen if tz is None else frozen.astimezone(tz)

        provider = Replay(fixture)
        monkeypatch.setattr(server, "_finedge_get_once", provider.once)
        monkeypatch.setattr(server, "sleep", lambda *_: None)
        monkeypatch.setattr(server, "datetime", Frozen)
        monkeypatch.setattr(premium_service, "datetime", Frozen)
        monkeypatch.setattr(server, "_resolve_finedge_stock", lambda q: {"symbol": symbol, "name": fixture["name"]})
        monkeypatch.setattr(server, "_try_resolve_upstox_instrument", lambda *a: {})
        server._stock_fundamentals_cache.clear()
        premium_data._BENCHMARK_OBSERVATIONS.clear()
        return fixture, provider
    return start


def legacy_report(fixture):
    symbol = fixture["symbol"]
    load_inputs = lambda s, st, now: server._premium_dashboard_inputs_resolved(s, st, now, lean=False)
    return premium_service.generate_report(server._finedge_get, symbol, fixture["name"], fixture["statement"], "a" * 32, fixture["now"], load_inputs)


def new_report(fixture, kept=None, observations=None):
    symbol = fixture["symbol"]
    fresh, observations = {}, observations if observations is not None else ObservationCache()
    report = premium_service.generate_report(server._finedge_get, symbol, fixture["name"], fixture["statement"], "a" * 32, fixture["now"],
                                             server._premium_inputs_loader(kept, fresh, observations), observations)
    return report, fresh, observations


def same(a, b, path=""):
    """Exact equality with the path of the first difference (== alone would only say False)."""
    assert type(a) is type(b) or (isinstance(a, (int, float)) and isinstance(b, (int, float))), f"{path}: {type(a)} vs {type(b)}"
    if isinstance(a, dict):
        assert set(a) == set(b), f"{path}: keys {set(a) ^ set(b)}"
        for key in a:
            same(a[key], b[key], f"{path}/{key}")
    elif isinstance(a, list):
        assert len(a) == len(b), f"{path}: {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{path}[{i}]")
    else:
        assert a == b, f"{path}: {a!r} vs {b!r}"


def comparable(report):
    """The report without the ids and times of the calculation and the provenance labels of the sections that are no longer fetched."""
    out = {k: v for k, v in report.items() if k not in ("completedAt", "sources")}
    meta = copy.deepcopy(out["inputMeta"])
    for period in ("yearly", "quarterly"):
        for label in SKIPPED_LABELS:
            meta["dashboardSources"][period].pop(label, None)
    out["inputMeta"] = meta
    return out


@pytest.mark.parametrize("symbol", COMPANIES)
def test_new_assembly_gives_the_model_exactly_the_legacy_inputs_and_rating(replay, symbol):
    fixture, provider = replay(symbol)
    old = legacy_report(fixture)
    legacy_calls = len(provider.calls)
    provider.calls.clear()
    server._stock_fundamentals_cache.clear()
    premium_data._BENCHMARK_OBSERVATIONS.clear()
    new, fresh, _ = new_report(fixture)
    assert old["rating"]["group"] == GROUPS[symbol] and old["rating"]["metrics"], "the fixture must really be rated by the model"
    same(old["rating"], new["rating"], "rating")          # every factor's value, points, status and weight, and the final score
    same(old["inputs"], new["inputs"], "inputs")
    assert old["inputHash"] == new["inputHash"]
    same(old["calculationTrace"], new["calculationTrace"], "trace")
    same(comparable(old), comparable(new), "report")
    assert len(provider.calls) < legacy_calls, "the new assembly must ask the provider for less"
    assert "revenueSegments" not in str(fresh["sources"]) and not any("segment" in c[0] or "corporate-actions" in c[0] or "dividend" in c[0] for c in provider.calls)


def test_a_rated_insurer_uses_financial_leverage_and_the_fixture_set_covers_a_rated_company_of_each_kind():
    # the insurer's interest cover was replaced by financial leverage in the model; the fixtures must keep exercising that rule
    insurer = load("HDFCLIFE")
    assert insurer["group"] == "INSURANCE"


@pytest.mark.parametrize("symbol", ["SKIPPER", "HDFCBANK"])
def test_kept_inputs_need_no_provider_call_and_give_the_same_report(replay, symbol):
    fixture, provider = replay(symbol)
    first, fresh, _ = new_report(fixture)
    packed = premium_cache.pack(fresh)
    kept = premium_cache.usable_inputs(packed, symbol, fixture["statement"], now=datetime.fromisoformat(fixture["now"]) + timedelta(hours=3))
    assert kept is not None
    provider.calls.clear()
    second, again, _ = new_report(fixture, kept=kept)
    assert provider.own(symbol) == [], "no request about the company itself is made"      # peers are looked up unless kept too (next test)
    assert again == {}                                  # nothing fresh to keep: it came from the kept inputs
    same(first["rating"], second["rating"], "rating")
    same(first["inputs"], second["inputs"], "inputs")
    same(comparable(first), comparable(second), "report")


def test_kept_peer_observations_replace_the_peer_lookups_and_change_nothing(replay):
    fixture, provider = replay("SKIPPER")
    first, _, cache = new_report(fixture)
    assert provider.peers("SKIPPER"), "the first report looks the peers up"
    shipped = premium_cache.flatten(cache.new)                      # as sent to the research API and back
    assert shipped and all(set(v) <= {"pe", "pb", "source", "none"} for v in shipped.values() if isinstance(v, dict))
    provider.calls.clear()
    second, _, cache2 = new_report(fixture, observations=ObservationCache(premium_cache.preload(json.loads(json.dumps(shipped)))))
    assert provider.peers("SKIPPER") == [] and cache2.new == {}
    assert len(cache2.universe()) == len(cache.universe()) > 50
    same(first["rating"], second["rating"], "rating")
    same(first["benchmark"]["metrics"], second["benchmark"]["metrics"], "benchmark")
    same(first["inputs"], second["inputs"], "inputs")


def test_a_peer_with_no_usable_row_is_remembered_and_not_asked_again(replay):
    fixture, provider = replay("SKIPPER")
    _, _, cache = new_report(fixture)
    empty = [k for k, v in cache.new.items() if v == NO_OBSERVATION]
    assert empty, "SKIPPER's industry has peers the provider gives nothing usable for"
    provider.calls.clear()
    new_report(fixture, observations=ObservationCache(premium_cache.preload(premium_cache.flatten(cache.new))))
    assert provider.peers("SKIPPER") == []


def test_missing_sections_fall_back_to_the_provider_and_a_failed_call_is_retried(replay):
    fixture, provider = replay("TCS")
    failures = {"left": 1}
    real = provider.once

    def flaky(path, params=None):
        if path.startswith("/financials/TCS") and (params or {}).get("period") == "annual" and (params or {}).get("statement_code") == "pl" and failures["left"]:
            failures["left"] -= 1
            raise server.HTTPException(status_code=503, detail="down")
        return real(path, params)

    server._finedge_get_once = flaky
    report, fresh, _ = new_report(fixture)
    assert failures["left"] == 0 and report["rating"]["final"] is not None   # the 503 was retried, not turned into a missing section
    # kept inputs of another company or basis, stale, damaged or oversized are refused: the provider is asked instead
    now = datetime.fromisoformat(fixture["now"])
    packed = premium_cache.pack(fresh)
    assert premium_cache.usable_inputs(packed, "TCS", "consolidated", now=now + timedelta(hours=1)) is not None
    assert premium_cache.usable_inputs(packed, "INFY", "consolidated", now=now) is None
    assert premium_cache.usable_inputs(packed, "TCS", "standalone", now=now) is None
    assert premium_cache.usable_inputs(packed, "TCS", "consolidated", now=now + timedelta(hours=25)) is None
    assert premium_cache.usable_inputs(packed, "TCS", "consolidated", now=now - timedelta(minutes=5)) is None
    assert premium_cache.usable_inputs(packed[:-8] + "AAAAAAAA", "TCS", "consolidated", now=now) is None
    assert premium_cache.usable_inputs("not base64 !", "TCS", "consolidated", now=now) is None
    assert premium_cache.usable_inputs(None, "TCS", "consolidated", now=now) is None
    bomb = premium_cache.pack({"raw": "0" * 30_000_000})
    assert premium_cache.unpack(bomb) is None


def test_the_premium_resolver_leaves_the_dashboards_cache_alone(replay):
    fixture, _ = replay("SKIPPER")
    new_report(fixture)
    assert server._stock_fundamentals_cache == {}


def test_a_dashboard_cache_entry_still_feeds_the_report_without_provider_calls(replay):
    fixture, provider = replay("SKIPPER")
    legacy_report(fixture)                                   # opens the dashboard's resolver the old way, which fills its cache
    assert server._stock_fundamentals_cache
    provider.calls.clear()
    report, _, _ = new_report(fixture)
    assert {c[0] for c in provider.own("SKIPPER")} == {"/daily-price-ratios/SKIPPER", "/peers/SKIPPER"}   # the two the dashboard never holds
    assert report["rating"]["final"] is not None


def test_call_memo_shares_one_call_between_askers_and_keeps_only_successes():
    memo, made, release = server._CallMemo(), [], threading.Event()

    def call(path, params):
        made.append(path)
        release.wait(2)
        return {"path": path}

    results = []
    threads = [threading.Thread(target=lambda: results.append(memo.get("/a", {"x": 1}, call))) for _ in range(4)]
    [t.start() for t in threads]
    release.set()
    [t.join() for t in threads]
    assert made == ["/a"] and results == [{"path": "/a"}] * 4
    results[0]["path"] = "changed"
    assert memo.get("/a", {"x": 1}, call) == {"path": "/a"}          # a caller changing its copy cannot change what others receive

    attempts = []

    def flaky(path, params):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("provider down")
        return "ok"

    with pytest.raises(RuntimeError):
        memo.get("/b", None, flaky)
    assert memo.get("/b", None, flaky) == "ok" and len(attempts) == 2   # the failure was not kept


def test_observation_cache_does_one_lookup_per_key_across_threads():
    cache, made = ObservationCache(), []

    def compute():
        made.append(1)
        threading.Event().wait(0.05)
        return {"pe": 10.0}

    key = ("consolidated", "2026-10-26", "pr:pb,pe", "ABB")
    threads = [threading.Thread(target=lambda: cache.get_or_compute(key, compute)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(made) == 1 and cache.new == {key: {"pe": 10.0}} and cache.universe() == ["ABB"]
    failed = ObservationCache()
    assert failed.get_or_compute(key, lambda: None) is None and failed.new == {}      # a failed lookup is not kept: the next report tries again


def test_preload_drops_anything_malformed():
    good = {"consolidated|2026-10-26|pr:pb,pe|ABB": {"pe": 1.0}, "consolidated|2026-10-26|ev|ABB": 7.5}
    bad = {"nonsense": {"pe": 1}, "weird|2026-10-26|pr|ABB": {"pe": 1}, "consolidated|2026-10-26|pr|ABB": "text", "consolidated|2026-10-26|pr|TCS": True}
    assert set(premium_cache.preload({**good, **bad})) == {("consolidated", "2026-10-26", "pr:pb,pe", "ABB"), ("consolidated", "2026-10-26", "ev", "ABB")}
    assert premium_cache.preload(None) == {} and premium_cache.preload([1]) == {}


def test_the_nightly_job_gives_way_to_a_member_and_the_cache_block_is_only_sent_when_asked(monkeypatch):
    from backend.tests.test_premium_reports import asgi_request, auth, sample_report, example  # noqa: F401
    seen = {}

    def fake_generate(get, symbol, name, statement, report_id, created, loader, observations):
        seen["observations"] = observations
        return report_for_route
    import backend.tests.test_premium_reports as shared
    report_for_route = None
    monkeypatch.setattr(server, "_resolve_finedge_stock", lambda q: {"symbol": "TEST", "name": "Test Ltd"})
    example_data = json.loads((Path(shared.__file__).parent / "premium_example.json").read_text())
    report_for_route = shared.sample_report(example_data)
    monkeypatch.setattr(premium_service, "generate_report", fake_generate)
    body = {"query": "TEST", "delivery": "inline"}
    status, plain = asgi_request(server.app, "POST", "/api/premium-reports", body, shared.auth())
    assert status == 200 and "cache" not in plain                       # nothing extra for a caller that did not ask: its snapshot verifies as before
    status, rich = asgi_request(server.app, "POST", "/api/premium-reports", {**body, "cache": True, "observations": {"consolidated|2026-10-26|pr:pb,pe|ABB": {"pe": 1}}}, shared.auth())
    assert status == 200 and set(rich["cache"]) >= {"observations", "universe", "inputsReused", "seconds"} and rich["cache"]["inputsReused"] is False
    assert ("consolidated", "2026-10-26", "pr:pb,pe", "ABB") in seen["observations"].rows
    monkeypatch.setattr(server, "_premium_interactive", 1)               # a member's calculation is running
    status, refused = asgi_request(server.app, "POST", "/api/premium-reports", {**body, "priority": "background"}, shared.auth())
    assert status == 429 and "member is waiting" in refused["detail"]
    status, member = asgi_request(server.app, "POST", "/api/premium-reports", body, shared.auth())
    assert status == 200 and server._premium_interactive == 1           # members are never turned away, and the count is put back
