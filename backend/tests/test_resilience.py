"""When the cache or the database is busy or down, and when a request carries values the database cannot read: clear answers, not 500s."""

import httpx
import redis.asyncio as aioredis

from test_integration import ingested, make_settings, store  # noqa: F401


class _DownRedis:
    """Stands in for a Redis whose pool is exhausted: every command fails at once."""
    def __getattr__(self, name):
        async def fail(*a, **k):
            raise aioredis.ConnectionError("No connection available.")
        return fail


async def test_stock_pages_and_search_read_postgres_when_redis_fails(ingested):  # noqa: F811
    real = ingested.redis
    ingested.redis = _DownRedis()
    try:
        got = await ingested.get_section("RELIANCE", "consolidated", "summary")
        assert got is not None and got[0]
        body, packed, etag = await ingested.search_index()
        assert b"RELIANCE" in body and packed and etag
        assert await ingested.get_etag("RELIANCE", "consolidated", "summary") is None
    finally:
        ingested.redis = real


async def test_a_busy_store_answers_503_and_unreadable_values_400(store):  # noqa: F811
    from finlit.api import create_app
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        @app.get("/api/__redis")
        async def boom():
            raise aioredis.ConnectionError("No connection available.")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/__redis")
            assert r.status_code == 503 and r.headers["retry-after"] == "5"
            r = await c.get("/api/mf", params={"q": "abc\x00def"})
            assert r.status_code in (200, 400), r.text
            r = await c.post("/api/auth/login", json={"email": "not-an-email", "password": 123456789})
            assert r.status_code == 422 and "123456789" not in r.text and "input" not in r.text
