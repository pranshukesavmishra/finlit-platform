"""The start script runs `create-admin` with ADMIN_PASSWORD at every start: it must create the account once, then leave a password changed
under Account alone, and apply a NEW value only when the owner chose one (the way back in without a shell)."""

import httpx
import pytest

from finlit.api import create_app
from finlit.auth import cli, crypto
from test_integration import TEST_DB, TEST_REDIS, ingested, make_settings, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
EMAIL = "owner@finlit-test.com"
FIRST, CHANGED, NEW = "first-start-phrase-91", "changed-under-account-73", "a-new-start-value-58"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS)


async def password_hash(store, email=EMAIL):  # noqa: F811
    async with store.pool.acquire() as conn:
        return await conn.fetchrow("SELECT password_hash, role, plan, status, email_verified_at FROM users WHERE lower(email) = $1", email)


async def test_create_admin_once_then_keep_later_changes(store, env):  # noqa: F811
    assert await cli.create_admin(EMAIL, FIRST) == "created"
    row = await password_hash(store)
    assert await crypto.verify_password(row["password_hash"], FIRST) and row["role"] == "admin" and row["plan"] == "gold" and row["email_verified_at"]

    async with store.pool.acquire() as conn:   # the owner changes the password under Account; ADMIN_PASSWORD is left as it was
        await conn.execute("UPDATE users SET password_hash = $2 WHERE lower(email) = $1", EMAIL, await crypto.hash_password(CHANGED))
    assert await cli.create_admin(EMAIL, FIRST) == "unchanged"
    assert await crypto.verify_password((await password_hash(store))["password_hash"], CHANGED)   # a restart no longer undoes it


async def test_a_new_value_replaces_the_password_and_ends_sessions(store, env):  # noqa: F811
    await cli.create_admin(EMAIL, FIRST)
    async with store.pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE lower(email) = $1", EMAIL)
        await conn.execute("UPDATE users SET locked_until = now() + interval '1 hour', failed_logins = 5 WHERE id = $1", uid)
        await conn.execute("INSERT INTO sessions (user_id, token_hash, csrf, expires_at) VALUES ($1, 'h-old', 'c', now() + interval '1 day')", uid)
    await store.redis.sadd(f"usess:{uid}", "h-old")
    await store.redis.set("sess:h-old", "{}")
    assert await cli.create_admin(EMAIL, NEW) == "password_set"
    assert await crypto.verify_password((await password_hash(store))["password_hash"], NEW)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM sessions WHERE user_id = $1", uid) == 0
        assert await conn.fetchval("SELECT locked_until IS NULL AND failed_logins = 0 FROM users WHERE id = $1", uid)
    assert not await store.redis.exists("sess:h-old") and not await store.redis.exists(f"usess:{uid}")
    assert await cli.create_admin(EMAIL, NEW) == "unchanged"   # and the next start leaves it alone


async def test_an_existing_account_is_adopted_without_changing_its_password(store, env):  # noqa: F811
    async with store.pool.acquire() as conn:   # an administrator made before the fingerprint existed, password since changed
        await conn.execute("INSERT INTO users (email, password_hash, role, plan, email_verified_at) VALUES ($1, $2, 'admin', 'gold', now())",
                           EMAIL, await crypto.hash_password(CHANGED))
    assert await cli.create_admin(EMAIL, FIRST) == "adopted"
    assert await crypto.verify_password((await password_hash(store))["password_hash"], CHANGED)
    assert await cli.create_admin(EMAIL, FIRST) == "unchanged"
    assert await cli.create_admin(EMAIL, NEW) == "password_set"


async def test_role_and_status_are_put_back(store, env):  # noqa: F811
    await cli.create_admin(EMAIL, FIRST)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET role = 'investor', plan = 'basic', status = 'disabled' WHERE lower(email) = $1", EMAIL)
    assert await cli.create_admin(EMAIL, FIRST) == "unchanged"
    row = await password_hash(store)
    assert (row["role"], row["plan"], row["status"]) == ("admin", "gold", "active")


async def test_the_kept_password_signs_in(ingested, env):  # noqa: F811
    await cli.create_admin(EMAIL, FIRST)
    async with ingested.pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash = $2 WHERE lower(email) = $1", EMAIL, await crypto.hash_password(CHANGED))
    await cli.create_admin(EMAIL, FIRST)
    app = create_app(make_settings(admin_require_mfa=False), store=ingested)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            ok = await c.post("/api/auth/login", json={"email": EMAIL, "password": CHANGED}, headers={"Origin": "http://test"})
            old = await c.post("/api/auth/login", json={"email": EMAIL, "password": FIRST}, headers={"Origin": "http://test"})
    assert ok.status_code == 200, ok.text
    assert old.status_code == 401
