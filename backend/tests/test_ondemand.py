"""A company opened before it is stored: key numbers first, a dedicated priority lane, a page that is answered in the same request, a clear failure.

The recorded FinEdge payloads are RELIANCE's; a transport rewrites another symbol (TCS) to RELIANCE and adds a realistic delay per call, so the timings
below are those of the real call pattern (23 provider calls for a full load, 9 for the key numbers) with 100 ms per call."""
import asyncio
import time

import httpx
import orjson
import pytest

from finlit import wake, worker
from finlit.api import create_app
from finlit.config import Settings
from finlit.finedge import ESSENTIAL_KEYS, FinEdgeClient, fixture_transport
from finlit.worker import CORE_PARTS
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)


class SlowTransport(httpx.AsyncBaseTransport):
    """Fixture answers after `latency` seconds; counts the calls in flight (the peak is the concurrency the provider saw)."""
    def __init__(self, latency=0.1, alias="TCS", fail=()):
        self.inner, self.latency, self.alias, self.fail = fixture_transport(), latency, alias, tuple(fail)
        self.inflight = self.peak = self.total = 0
        self.paths = []

    async def handle_async_request(self, request):
        self.inflight += 1; self.total += 1
        self.peak = max(self.peak, self.inflight)
        self.paths.append(request.url.path)
        try:
            await asyncio.sleep(self.latency)
            if any(f in request.url.path for f in self.fail):
                return httpx.Response(500, json={"message": "down"})
            real = httpx.Request(request.method, str(request.url).replace(self.alias, "RELIANCE"))
            return await self.inner.handle_async_request(real)
        finally:
            self.inflight -= 1


def client_with(transport, **kw):
    return FinEdgeClient(Settings(finedge_api_key="x", finedge_mode="fixtures", finedge_concurrency=kw.pop("conc", 8), **kw), transport=transport)


# ------------------------------------------------------------------------------------------------------- the call pattern and its timing
async def test_first_paint_asks_for_the_key_parts_only_and_is_much_faster():
    t_full, t_ess = SlowTransport(), SlowTransport()
    c1, c2 = client_with(t_full), client_with(t_ess)
    s = time.perf_counter(); full = await c1.fetch_bundle("TCS", "consolidated"); full_s = time.perf_counter() - s
    s = time.perf_counter(); ess = await c2.fetch_bundle("TCS", "consolidated", only=ESSENTIAL_KEYS); ess_s = time.perf_counter() - s
    assert c1.calls == 23 and c2.calls == 18                        # 16 key parts + the two small calls that choose consolidated or standalone; 5 parts wait
    assert set(ess) - {"symbol", "statement", "requestedStatement", "errors", "pl_annual_standalone"} == set(ESSENTIAL_KEYS)
    assert set(CORE_PARTS) <= set(ESSENTIAL_KEYS)                   # everything a report must have is in the first load
    assert len(full) > len(ess)
    assert ess_s <= full_s + 0.02 and ess_s < 0.5                  # 18 calls at 100 ms, 8 at a time: three rounds


async def test_sequential_versus_bounded_concurrency_on_the_same_calls():
    """The critical path of a 23-call load at 100 ms per call: one at a time is 2.3 s, 8 at a time about 0.4 s; the peak never exceeds the cap."""
    timings = {}
    for conc in (1, 4, 8):
        tr = SlowTransport(0.1); c = client_with(tr, conc=conc)
        s = time.perf_counter(); await c.fetch_bundle("TCS", "consolidated"); timings[conc] = time.perf_counter() - s
        assert tr.peak <= conc
    assert timings[1] > 2.0 and timings[8] < 0.8 and timings[8] < timings[4] < timings[1]


async def test_background_parts_never_take_more_than_half_of_the_slots():
    tr = SlowTransport(0.05); c = client_with(tr, conc=8)
    bundle = await c.fetch_bundle("TCS", "consolidated", only=ESSENTIAL_KEYS)
    tr.peak = 0
    await c.fetch_rest(bundle)
    assert tr.peak <= 4                                             # visitors' key-number calls always find free slots
    assert "peers" in bundle and "shareholding" in bundle and "announcements" in bundle


async def test_a_failed_background_part_is_recorded_and_never_raises():
    tr = SlowTransport(0.01, fail=("/shareholdings/", "/peers/")); c = client_with(tr)
    bundle = await c.fetch_bundle("TCS", "consolidated", only=ESSENTIAL_KEYS)
    await c.fetch_rest(bundle)
    assert "shareholding" not in bundle and "peers" not in bundle
    assert bundle["errors"]["shareholding"] == "500" and bundle["errors"]["peers"] == "500"
    assert "announcements" in bundle and "segments" in bundle      # the rest still came


async def test_progress_is_reported_part_by_part():
    seen = []
    async def on_part(key): seen.append(key)
    c = client_with(SlowTransport(0.01))
    await c.fetch_bundle("TCS", "consolidated", only=ESSENTIAL_KEYS, on_part=on_part)
    assert set(ESSENTIAL_KEYS) <= set(seen)


# ------------------------------------------------------------------------------------------------------- stored in two steps
async def test_key_numbers_are_stored_first_then_the_complete_report(store):
    c = client_with(SlowTransport(0.01))
    await worker.refresh_universe(FinEdgeClient(make_settings()), store)
    await store.redis.set("pending:TCS:consolidated", 1, ex=300)
    res, bundle = await worker.ingest_essential(c, store, "TCS", "consolidated")
    assert res["status"] in ("ok", "warnings") and bundle is not None
    first = orjson.loads((await store.get_section("TCS", "consolidated", "summary"))[0])
    assert first["meta"]["partial"] is True and "peers" in first["meta"]["pendingParts"] and first["quote"]["price"]
    assert first["profile"]["name"] and not await store.redis.exists("pending:TCS:consolidated")   # the waiting page is released
    assert first["score"]["overall"] is not None and first["keyMetrics"] and first["returns"]       # everything the score needs was in the first load: no half-score
    assert "shareholding" not in first["dataQuality"]["missing"]                                     # not asked for yet is not "missing"
    for later in worker.LATER_SECTIONS:                                                              # these blocks have no row yet: the API says "still loading"
        assert await store.get_section("TCS", "consolidated", later) is None
    assert await store.get_section("TCS", "consolidated", "financials") and await store.get_section("TCS", "consolidated", "ratios")
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM scores WHERE symbol = 'TCS'") == 0        # the scores table is written once, by the complete load
    done = await worker.ingest_rest(c, store, "TCS", "consolidated", bundle)
    assert done["status"] in ("ok", "warnings")
    full = orjson.loads((await store.get_section("TCS", "consolidated", "summary"))[0])
    assert not full["meta"].get("partial") and full["score"]["overall"] is not None
    peers = orjson.loads((await store.get_section("TCS", "consolidated", "peers"))[0])
    assert peers["symbols"] and await store.get_section("TCS", "consolidated", "ownership")
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM scores WHERE symbol = 'TCS'") >= 1


async def test_a_failed_first_paint_leaves_a_note_and_stores_nothing(store, monkeypatch):
    c = client_with(SlowTransport(0.0))
    real, real_sleep = c.get, asyncio.sleep
    async def quick(path, params=None, timeout=10, retries=3, low=False):
        if "/ratios/" in path:                                   # a core part the provider does not answer
            raise worker.FinEdgeError(path, 500, "down")
        return await real(path, params, timeout, retries=0)
    async def fast_sleep(_s): await real_sleep(0)
    c.get = quick
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", fast_sleep)
    await worker.refresh_universe(FinEdgeClient(make_settings()), store)
    await store.redis.set("pending:TCS:consolidated", 1, ex=300)
    res, bundle = await worker.ingest_essential(c, store, "TCS", "consolidated")
    assert res["status"] == "failed" and bundle is None and res["retry"] is True            # a provider that did not answer: tried again, the page keeps waiting
    assert await store.redis.exists("pending:TCS:consolidated") and not await store.redis.exists("ingest:fail:TCS:consolidated")
    for _ in range(2):
        res, _ = await worker.ingest_essential(c, store, "TCS", "consolidated")
    assert res["retry"] is False                                                           # third failure: stop, tell the page
    assert await store.redis.get("ingest:fail:TCS:consolidated") and not await store.redis.exists("pending:TCS:consolidated")
    assert await store.get_section("TCS", "consolidated", "summary") is None


async def test_peers_of_a_new_report_are_queued_at_low_priority_and_not_twice(store):
    await worker.refresh_universe(FinEdgeClient(make_settings()), store)
    sections = {"summary": {"meta": {"symbol": "TCS"}}, "peers": {"symbols": ["TCS", "INFY", "WIPRO", "HCLTECH", "NOTACOMPANY"]}}
    assert await worker.warm_peers_of(store, sections, 5) == 3                              # not itself, not unknown symbols
    assert await worker.warm_peers_of(store, sections, 5) == 0                              # already queued
    assert sorted(s for s, _ in await store.claim_low(10)) == ["HCLTECH", "INFY", "WIPRO"]
    assert await store.queue_length() == 0                                                  # the visitors' queue is untouched


async def test_recently_opened_companies_join_the_nightly_refresh_set(store):
    await worker.refresh_universe(FinEdgeClient(make_settings()), store)
    await store.note_view("QUESS")
    assert "QUESS" in await store.viewed_symbols()
    assert "QUESS" in await store.pending_symbols(limit=3)                                  # outside the top 3, but somebody opened it lately


# ------------------------------------------------------------------------------------------------------- the lane
class LaneStore:
    """Just enough of Store for drain_queue: a visitors' queue, a low queue and Redis flags."""
    QUEUE_FLAG, READER_FLAG, LOW_FLAG = "q", "reader", "low"
    def __init__(self, items, low=()):
        self.items, self.lows, self.flags = list(items), list(low), {"q": 1, "reader": 1}
        self.redis = self
    async def exists(self, k): return 1 if self.flags.get(k) else 0
    async def delete(self, k): self.flags.pop(k, None)
    async def set(self, k, v, ex=None): self.flags[k] = v
    async def claim(self, n):
        out, self.items = self.items[:n], self.items[n:]
        return out
    async def claim_low(self, n):
        out, self.lows = self.lows[:n], self.lows[n:]
        return out
    async def invalidate_search(self): pass


async def test_two_lanes_a_slow_company_does_not_hold_up_the_next_one(monkeypatch):
    done = {}
    async def fake_serve(client, store, sym, st, extras, background):
        await asyncio.sleep(0.6 if sym == "SLOW" else 0.05)
        done[sym] = time.perf_counter()
        return {"symbol": sym, "status": "ok"}
    monkeypatch.setattr(worker, "serve_one", fake_serve)
    store = LaneStore([("SLOW", "consolidated"), ("A", "consolidated"), ("B", "consolidated"), ("C", "consolidated")])
    t0 = time.perf_counter()
    assert await worker.drain_queue(None, store, loop=False, idle_seconds=0.01) == 4
    # the old batch of three waited for the slowest before taking the fourth; now the free lane takes B and C while SLOW still runs
    assert done["C"] - t0 < 0.5 < done["SLOW"] - t0
    assert "reader" not in store.flags                                                      # nobody waits any more: the bulk jobs go on at once


async def test_the_lane_never_runs_more_than_its_cap(monkeypatch):
    live = peak = 0
    async def fake_serve(client, store, sym, st, extras, background):
        nonlocal live, peak
        live += 1; peak = max(peak, live)
        await asyncio.sleep(0.05); live -= 1
        return {"symbol": sym, "status": "ok"}
    monkeypatch.setattr(worker, "serve_one", fake_serve)
    store = LaneStore([(f"S{i}", "consolidated") for i in range(8)])
    await worker.drain_queue(None, store, loop=False, idle_seconds=0.01, lanes=2)
    assert peak == 2


async def test_pre_warm_waits_for_visitors_and_skips_what_is_stored(monkeypatch):
    order = []
    async def fake_serve(client, store, sym, st, extras, background):
        order.append(("visitor", sym)); await asyncio.sleep(0.05)
        return {"symbol": sym, "status": "ok"}
    async def fake_usable(store, sym, st): return sym == "STORED"
    async def fake_one(client, store, sym, st, slim=False, low=False):
        order.append(("warm", sym, low)); return {"symbol": sym, "status": "ok"}
    monkeypatch.setattr(worker, "serve_one", fake_serve); monkeypatch.setattr(worker, "_usable_report", fake_usable); monkeypatch.setattr(worker, "ingest_one", fake_one)
    store = LaneStore([("V1", "consolidated")], low=[("PEER", "consolidated"), ("STORED", "consolidated")])
    await worker.drain_queue(None, store, loop=False, idle_seconds=0.01)
    assert order[0] == ("visitor", "V1") and ("warm", "PEER", True) in order and not any(o[1] == "STORED" for o in order if o[0] == "warm")


async def test_bulk_jobs_step_aside_while_a_visitor_waits_and_the_flag_clears(store):
    from finlit import prism
    assert not await prism._members_busy(store.redis)
    await store.redis.set(store.READER_FLAG, 1, ex=120)
    assert await prism._members_busy(store.redis)                                           # technicals and the Prism pre-compute pause
    fake = LaneStore([])
    fake.redis = store.redis; fake.QUEUE_FLAG = store.QUEUE_FLAG; fake.READER_FLAG = store.READER_FLAG
    fake.claim = store.claim
    await worker.drain_queue(None, fake, loop=False, idle_seconds=0.01)
    assert not await prism._members_busy(store.redis)                                       # drained: released at once, not after two minutes


# ------------------------------------------------------------------------------------------------------- the request
async def _app(store, **overrides):
    app = create_app(make_settings(**overrides), store=store)
    return app, httpx.ASGITransport(app=app)


async def test_the_first_request_waits_for_the_key_numbers_and_returns_the_page(ingested):
    """No 'preparing' page at all when the key numbers arrive inside the wait: the same request answers with the report."""
    app, tr = await _app(ingested, ondemand_wait_seconds=8.0)
    c = client_with(SlowTransport(0.05))
    async def the_worker():                                  # the always-on drain loop, started by the enqueue's flag
        for _ in range(100):
            if await ingested.queue_length():
                return await worker.drain_queue(c, ingested)
            await asyncio.sleep(0.05)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        t0 = time.perf_counter()
        task = asyncio.create_task(the_worker())
        r = await http.get("/api/stocks/TCS")
        took = time.perf_counter() - t0
        await task
    assert r.status_code == 200 and r.json()["meta"]["symbol"] == "TCS" and r.json()["quote"]["price"]
    assert took < 4.0


async def test_a_block_still_loading_says_so_instead_of_queueing_the_company_again(ingested):
    app, tr = await _app(ingested, ondemand_wait_seconds=0.0)
    async with ingested.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'RELIANCE' AND section = 'peers'")
    await ingested.redis.hdel("stock:RELIANCE:consolidated", "peers", "peers:etag")
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        r = await http.get("/api/stocks/RELIANCE/peers")
    assert r.status_code == 202 and r.json()["status"] == "queued" and await ingested.queue_length() == 0


async def test_past_the_wait_the_page_gets_progress_and_the_company_name(ingested):
    app, tr = await _app(ingested, ondemand_wait_seconds=0.3)
    await ingested.redis.set("ingest:progress:TCS:consolidated", 3, ex=60)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        r = await http.get("/api/stocks/TCS")
        again = await http.get("/api/stocks/TCS")             # the page asking again does not queue it twice or use up the allowance
    body = r.json()
    assert r.status_code == 202 and r.headers["retry-after"] == "1"
    assert body["status"] == "queued" and body["total"] == len(ESSENTIAL_KEYS) and body["done"] == 3 and body["company"]["name"]
    assert again.status_code == 202 and await ingested.queue_length() == 1


async def test_a_provider_that_is_down_ends_in_a_clear_failure_not_endless_waiting(ingested):
    app, tr = await _app(ingested, ondemand_wait_seconds=6.0)
    async def quick(path, params=None, timeout=10, retries=3, low=False):
        raise worker.FinEdgeError(path, 500, "down")
    c = client_with(SlowTransport(0.0)); c.get = quick
    async def the_worker():
        for _ in range(3):
            for _ in range(100):
                if await ingested.queue_length():
                    break
                await asyncio.sleep(0.05)
            await worker.drain_queue(c, ingested)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        task = asyncio.create_task(the_worker())
        r = await http.get("/api/stocks/TCS")
        await task
    assert r.status_code == 503 and r.json()["status"] == "build_failed"


async def test_limits_per_visitor_and_in_total_still_hold(ingested):
    app, tr = await _app(ingested, queue_limit_per_hour=1, ondemand_wait_seconds=0.0)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        assert (await http.get("/api/stocks/TCS")).status_code == 202
        r = await http.get("/api/stocks/INFY")
        assert r.status_code == 429 and r.json()["status"] == "busy"
    app, tr = await _app(ingested, queue_max_pending=1, queue_limit_per_hour=50, ondemand_wait_seconds=0.0)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        assert (await http.get("/api/stocks/WIPRO")).status_code == 429                    # TCS is already waiting: the total cap of 1 is reached


async def test_a_partial_report_that_was_never_completed_is_queued_again(ingested):
    app, tr = await _app(ingested, ondemand_wait_seconds=0.0)
    cached = await ingested.get_section("RELIANCE", "consolidated", "summary")
    summary = orjson.loads(cached[0]); summary["meta"]["partial"] = True
    summary["meta"]["generatedAt"] = "2026-01-01T00:00:00+00:00"
    await ingested.save_snapshot("RELIANCE", "consolidated", {"summary": summary})
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        r = await http.get("/api/stocks/RELIANCE")
        assert r.status_code == 200 and r.json()["meta"]["partial"] is True                   # shown as it is (the key numbers are good) ...
    assert ("RELIANCE", "consolidated") in await ingested.claim(5)                          # ... and completed in the background


# ------------------------------------------------------------------------------------------------------- scheduler heartbeat
async def test_scheduler_heartbeat_and_job_list(store):
    st = await wake.scheduler_status(store.redis)
    assert st["schedulerAlive"] is False and st["schedulerAliveAt"] is None and st["jobsLastHour"] == []
    now = time.time()
    await wake.heartbeat(store.redis, now - 30)
    await wake.job_started(store.redis, "results", now - 600)
    await wake.job_started(store.redis, "calendars-hourly", now - 5000)                    # older than an hour: not listed
    st = await wake.scheduler_status(store.redis, now)
    assert st["schedulerAlive"] is True and st["schedulerAgeSeconds"] == 30
    assert [j["name"] for j in st["jobsLastHour"]] == ["results"]
    await wake.heartbeat(store.redis, now - 900)
    assert (await wake.scheduler_status(store.redis, now))["schedulerAlive"] is False      # a stopped scheduler shows within three minutes


async def test_results_status_reports_the_scheduler(ingested):
    await wake.heartbeat(ingested.redis)
    await wake.job_started(ingested.redis, "results-light")
    app, tr = await _app(ingested)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=tr, base_url="http://test") as http:
        body = (await http.get("/api/results/status")).json()
    assert body["schedulerAlive"] is True and body["schedulerAliveAt"] and body["jobsLastHour"][0]["name"] == "results-light"
    assert "lastSkipped" in body and "lastRun" in body


# ------------------------------------------------------------------------------------------------------- configuration seen by `docker compose exec`
def test_site_backend_address_defaults_like_render_start_sh(tmp_path):
    from finlit.config import site_api_url_default as d
    site = str(tmp_path)
    live = {"SITE_API_DIR": site, "FINEDGE_API_KEY": "k", "CMS_JWT_SECRET": "x" * 32}
    assert d(live) == "http://127.0.0.1:8001"                                   # a manual shell gets what the scheduler's processes get
    assert d({**live, "SITE_API_URL": "http://other:9/"}) == "http://other:9"   # an explicit value wins
    assert d({**live, "SITE_API_START": "never"}) == ""
    assert d({**live, "CMS_JWT_SECRET": "short"}) == ""                         # needs MONGO_URL or a long secret, exactly as start.sh
    assert d({**live, "CMS_JWT_SECRET": "short", "MONGO_URL": "m"}) == "http://127.0.0.1:8001"
    assert d({**live, "FINEDGE_MODE": "fixtures"}) == ""
    assert d({**live, "SITE_API_DIR": site + "/missing"}) == ""
    assert d({**live, "SITE_API_START": "always", "FINEDGE_API_KEY": ""}) == "http://127.0.0.1:8001"


async def test_prism_commands_name_what_is_missing(store):
    from finlit import prism, prism_technical
    s1 = Settings(finedge_api_key="x", site_api_url="", cms_jwt_secret="x" * 40)
    s2 = Settings(finedge_api_key="x", site_api_url="http://127.0.0.1:8001", cms_jwt_secret="short")
    assert (await prism_technical.refresh(store, s1))["reason"] == "site_api_url_not_set"
    assert (await prism_technical.refresh(store, s2))["reason"] == "cms_jwt_secret_too_short"
    assert (await prism.precompute(store, s1))["reason"] == "site_api_url_not_set"
    assert (await prism.precompute(store, s2))["reason"] == "cms_jwt_secret_too_short"


async def test_the_admin_loads_switch_never_blocks_a_visitor_or_the_results_jobs(store, monkeypatch):
    import inspect
    from finlit import sysctl
    src = inspect.getsource(worker.drain_queue) + inspect.getsource(worker.serve_one) + inspect.getsource(worker.ingest_essential)
    assert "sysctl" not in src and "loads_enabled" not in src
    cmds = inspect.getsource(worker).split('elif args.cmd == "refresh-results-light":')[1].split('elif args.cmd == "drain-queue"')[0]
    assert "loads_enabled" not in cmds                                             # results-light ignores the switch
    sh = open(__import__("pathlib").Path(__file__).resolve().parents[2] / "deploy/scheduler.sh").read()
    drain = [l for l in sh.splitlines() if "drain-queue --loop" in l][0]
    assert "loads_paused" not in drain
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_meta(key, value) VALUES('switch:loads', '{\"enabled\": false}') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
    assert not await sysctl.loads_enabled(store.pool)
    from finlit import results
    assert (await results.pipeline_status(store))["loadsPaused"] is True          # shown on /api/results/status
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_meta WHERE key = 'switch:loads'")
