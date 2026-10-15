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


def make_settings():
    return Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)


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
                           "ingest_queue, schema_migrations CASCADE")
    await s.redis.flushdb()
    await s.migrate()
    yield s
    await s.close()


@pytest.fixture
async def ingested(store):
    async with FinEdgeClient(make_settings()) as client:
        assert await worker.refresh_universe(client, store) > 5000
        result = await worker.ingest_one(client, store, "RELIANCE")
    assert result["status"] == "ok", result
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
    assert r.headers["cache-control"].startswith("public")
    body = r.json()
    assert body["meta"]["symbol"] == "RELIANCE" and body["score"]["overall"] is not None
    again = await api.get("/api/stocks/RELIANCE", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


async def test_every_section_and_range(api):
    for name in ("financials", "ratios", "ownership", "events", "segments", "peers"):
        r = await api.get(f"/api/stocks/RELIANCE/{name}")
        assert r.status_code == 200, name
    for rng in ("1M", "6M", "1Y", "3Y", "5Y", "MAX"):
        r = await api.get(f"/api/stocks/RELIANCE/price?range={rng}")
        assert r.status_code == 200 and r.json()["series"]["t"], rng
    assert (await api.get("/api/stocks/RELIANCE/price?range=7Y")).status_code == 404
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
    assert days > 400 and score["overall"] is not None and run["status"] == "ok" and run["calls"] >= 21


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
