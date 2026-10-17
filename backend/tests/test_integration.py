"""End-to-end: fixtures -> worker -> Postgres/Redis -> API. Needs DATABASE_URL and REDIS_URL;
skipped when they are not reachable (CI provides both as service containers)."""

import os
import statistics
import time

import httpx
import orjson
import pytest

from finlit import worker
from finlit.api import create_app
from finlit.config import Settings
from finlit.finedge import FinEdgeClient
from finlit.store import Store

pytestmark = pytest.mark.integration

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


def make_settings(**overrides):
    return Settings(**{"finedge_api_key": "test", "finedge_mode": "fixtures", "database_url": TEST_DB,
                       "redis_url": TEST_REDIS, "rate_limit_per_minute": 100_000, **overrides})


@pytest.fixture
async def store():
    settings = make_settings()
    try:
        s = await Store.connect(settings)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    try:
        await s.redis.ping()
    except Exception as exc:  # pragma: no cover
        await s.close()
        pytest.skip(f"redis not available: {exc}")
    async with s.pool.acquire() as conn:
        # Timescale refuses to drop a hypertable in the same statement as other tables.
        await conn.execute("DROP TABLE IF EXISTS price_daily CASCADE")
        await conn.execute("DROP TABLE IF EXISTS snapshots, scores, companies, ingest_runs, "
                           "ingest_queue, schema_migrations, users, sessions, email_tokens, audit_events, user_state, "
                           "plan_requests, outbox, score_history, alert_state, ipos, feed_items CASCADE")
    await s.redis.flushdb()
    await s.migrate()
    yield s
    await s.close()


@pytest.fixture
async def ingested(store):
    async with FinEdgeClient(make_settings()) as client:
        assert await worker.refresh_universe(client, store) > 5000
        result = await worker.ingest_one(client, store, "RELIANCE")
    assert result["status"] in ("ok", "warnings"), result  # fixtures age, so freshness may warn
    return store


@pytest.fixture
async def api(ingested):
    app = create_app(make_settings(), store=ingested)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_summary_served_with_etag_and_304(api):
    r = await api.get("/api/stocks/reliance")
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("private") and "Cookie" in r.headers["vary"]  # plan-dependent section
    body = r.json()
    assert body["meta"]["symbol"] == "RELIANCE" and body["score"]["overall"] is not None
    again = await api.get("/api/stocks/RELIANCE", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


async def test_screener_universe(api):
    r = await api.get("/api/screener/universe")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("private") and "Cookie" in r.headers["vary"]
    rows = {x["symbol"]: x for x in r.json()["rows"]}
    rel = rows["RELIANCE"]
    assert rel["name"] == "Reliance Industries Ltd" and rel["sector"]
    # every field the screener and comparison pages read is present and numeric (or null)
    for k in ("overall", "pe", "pb", "roe", "roce", "debt_to_equity", "sales_cagr", "profit_cagr", "operating_margin",
              "change_pct", "return_1m", "return_1y", "market_cap", "price", "dividend_yield", "pillar_quality", "pillar_balance"):
        assert k in rel and (rel[k] is None or isinstance(rel[k], (int, float))), k
    assert rel["overall"] is not None and rel["band"] in {"strong", "healthy", "mixed", "watch"}
    assert "statement" not in rel and "updated_at" not in rel


async def test_every_section_and_range(api):
    for name in ("financials", "ratios", "ownership", "events", "segments", "peers"):
        r = await api.get(f"/api/stocks/RELIANCE/{name}")
        assert r.status_code == 200, name
    for rng in ("1M", "6M", "1Y", "3Y", "5Y", "MAX"):
        r = await api.get(f"/api/stocks/RELIANCE/price?range={rng}")
        assert r.status_code == 200 and r.json()["series"]["t"], rng
    assert (await api.get("/api/stocks/RELIANCE/price?range=7Y")).status_code == 404
    peers = (await api.get("/api/stocks/RELIANCE/peers")).json()
    assert peers["items"] and peers["items"][0]["name"]  # names come from the stock universe
    assert (await api.get("/api/stocks/RELIANCE/secrets")).status_code == 404
    assert (await api.get("/api/stocks/DROP%20TABLE")).status_code == 400


async def test_unknown_and_queued(api, ingested):
    assert (await api.get("/api/stocks/NOTASTOCK")).status_code == 404
    r = await api.get("/api/stocks/TCS")  # in the universe, not yet ingested
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert ("TCS", "consolidated") in await ingested.claim()


async def test_search_index(api):
    r = await api.get("/api/stocks/search-index")
    data = r.json()
    assert data["fields"][0] == "symbol" and len(data["rows"]) > 5000
    ready = [row for row in data["rows"] if row[3]]
    assert r.headers.get("content-encoding") == "gzip"
    assert (await api.get("/api/stocks/search-index", headers={"If-None-Match": r.headers["etag"]})).status_code == 304
    assert [row[0] for row in ready] == ["RELIANCE"]


async def test_cold_redis_falls_back_to_postgres(api, ingested):
    await ingested.redis.flushdb()
    r = await api.get("/api/stocks/RELIANCE/ratios")
    assert r.status_code == 200
    assert await ingested.redis.hexists("stock:RELIANCE:consolidated", "ratios")  # refilled


async def test_prices_and_scores_persisted(ingested):
    async with ingested.pool.acquire() as conn:
        days = await conn.fetchval("SELECT count(*) FROM price_daily WHERE symbol = 'RELIANCE'")
        score = await conn.fetchrow("SELECT * FROM scores WHERE symbol = 'RELIANCE'")
        run = await conn.fetchrow("SELECT * FROM ingest_runs ORDER BY id DESC LIMIT 1")
    assert days > 400 and score["overall"] is not None and run["status"] in ("ok", "warnings") and run["calls"] >= 21


async def test_refresh_quotes_patches_summary(ingested):
    async with FinEdgeClient(make_settings()) as client:
        cached = await ingested.get_section("RELIANCE", "consolidated", "summary")
        summary = orjson.loads(cached[0])
        summary["quote"]["price"] = 1.0
        await ingested.save_snapshot("RELIANCE", "consolidated", {"summary": summary})
        assert await worker.refresh_quotes(client, ingested) == 1
    body, _ = await ingested.get_section("RELIANCE", "consolidated", "summary")
    assert orjson.loads(body)["quote"]["price"] == 1184.0


async def test_latency_budget(api):
    """Server-side time for a warm summary must stay far below the 1 s target."""
    await api.get("/api/stocks/RELIANCE")
    samples = []
    for _ in range(200):
        t = time.perf_counter()
        r = await api.get("/api/stocks/RELIANCE")
        samples.append((time.perf_counter() - t) * 1000)
        assert r.status_code == 200
    p95 = statistics.quantiles(samples, n=20)[18]
    print(f"summary p50={statistics.median(samples):.2f} ms p95={p95:.2f} ms")
    assert p95 < 50


async def _client(store, **overrides):
    app = create_app(make_settings(**overrides), store=store)
    return app, httpx.ASGITransport(app=app)


async def test_security_headers(api):
    r = await api.get("/api/stocks/RELIANCE")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert r.headers["x-frame-options"] == "DENY"
    assert "server" not in r.headers
    assert (await api.post("/api/stocks/RELIANCE")).status_code == 405  # read-only API


async def test_rate_limit_returns_429(ingested):
    app, transport = await _client(ingested, rate_limit_per_minute=5)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        codes = [(await c.get("/api/stocks/RELIANCE")).status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
        assert (await c.get("/api/health")).status_code == 200  # health is never limited


async def test_queue_limit_per_client(ingested):
    app, transport = await _client(ingested, queue_limit_per_hour=1)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/api/stocks/TCS")).status_code == 202
        r = await c.get("/api/stocks/INFY")
        assert r.status_code == 429 and r.json()["status"] == "busy"


async def test_untrusted_host_rejected(ingested):
    app, transport = await _client(ingested, allowed_hosts=["api.finlitventures.com"])
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as c:
            r = await c.get("/api/stocks/RELIANCE")
            assert r.status_code == 400 and r.headers["x-content-type-options"] == "nosniff"
        async with httpx.AsyncClient(transport=transport, base_url="http://api.finlitventures.com") as c:
            assert (await c.get("/api/stocks/RELIANCE")).status_code == 200


async def test_rejected_data_is_never_published(ingested, monkeypatch):
    from finlit import snapshot as snap
    real_build = snap.build

    def broken_build(bundle, now=None):
        sections = real_build(bundle, now)
        sections["summary"]["dataQuality"]["checks"] = {"status": "rejected", "passed": 0, "total": 1,
                                                        "issues": [{"key": "x", "severity": "critical", "message": "bad"}]}
        sections["summary"]["quote"]["price"] = -1
        return sections

    before, _ = await ingested.get_section("RELIANCE", "consolidated", "summary")
    monkeypatch.setattr(snap, "build", broken_build)
    async with FinEdgeClient(make_settings()) as client:
        result = await worker.ingest_one(client, ingested, "RELIANCE")
    assert result["status"] == "rejected"
    after, _ = await ingested.get_section("RELIANCE", "consolidated", "summary")
    assert after == before  # last good snapshot still served


async def test_ingest_all_works_through_the_universe_in_chunks_and_skips_fresh(store):
    # The recorded fixtures only cover RELIANCE, so the other companies fail upstream; the run must carry on past them.
    async with FinEdgeClient(make_settings()) as client:
        await worker.refresh_universe(client, store)
        await worker.ingest_one(client, store, "RELIANCE")
        assert "RELIANCE" not in await store.pending_symbols(limit=50)  # fresh snapshots are skipped
        result = await worker.ingest_all(client, store, limit=5, chunk=2)
        assert sum(result.values()) == 5 and result["failed"] == 5  # all five attempted, none aborted the batch
        assert len(await store.pending_symbols()) > 5000


async def test_probe_reports_every_endpoint(store):
    async with FinEdgeClient(make_settings()) as client:
        results = await worker.probe(client, "RELIANCE")
    assert len(results) >= 20 and all(state in ("ok", "empty") for _, state, _ in results)


async def test_score_history_and_health(api, ingested):
    h = await api.get("/api/stocks/RELIANCE/score-history")  # showcase symbol: open
    pts = h.json()["points"]
    assert h.status_code == 200 and len(pts) == 1 and pts[0]["overall"] is not None
    await worker.ingest_one(FinEdgeClient(make_settings()), ingested, "RELIANCE")  # same day: still one point
    assert len((await api.get("/api/stocks/RELIANCE/score-history")).json()["points"]) == 1
    health = await ingested.health()
    assert health["universe"] > 5000 and health["loaded"] == 1 and health["scored"] >= 1 and "runs24h" in health


async def test_exchange_announcements_become_feed_items(api, ingested):
    r = await api.get("/api/feed?kind=news&symbol=RELIANCE")
    items = r.json()["items"]
    assert r.status_code == 200 and items and all(i["symbol"] == "RELIANCE" and i["auto"] for i in items)
    await worker.ingest_one(FinEdgeClient(make_settings()), ingested, "RELIANCE")  # loading again must not duplicate anything
    again = (await api.get("/api/feed?kind=news&symbol=RELIANCE")).json()["items"]
    assert len(again) == len(items)
    kinds = {i["kind"] for k in ("news", "result", "document") for i in (await api.get(f"/api/feed?kind={k}&symbol=RELIANCE")).json()["items"]}
    assert kinds <= {"news", "result", "document"}
    assert (await api.get("/api/feed?symbol=DROP%20TABLE")).status_code == 400
    assert (await api.get("/api/feed?kind=other")).status_code == 422
