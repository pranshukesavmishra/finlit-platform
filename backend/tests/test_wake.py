"""The database wake budget: Neon (free plan) must be able to sleep. Visitors gate the timers, jobs are grouped into windows, a refusing database gets a clear 503."""

import asyncio
import re
import time
from pathlib import Path

import asyncpg
import httpx
import pytest
import yaml

from finlit import wake, worker
from finlit.api import create_app
from test_auth import ORIGIN, PW, anon, app, make_admin, signed_in  # noqa: F401  (fixtures and helpers)
from test_integration import TEST_REDIS, ingested, make_settings, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
QUOTA = "Your account or project has exceeded the quota. Upgrade your plan to increase limits."


@pytest.fixture(autouse=True)
async def clean_wake_keys(store):  # noqa: F811
    async def wipe():
        keys = [k async for k in store.redis.scan_iter("wake:*")]
        if keys:
            await store.redis.delete(*keys)
    await wipe()
    wake._last_write = wake._last_account = 0.0
    yield
    await wipe()


@pytest.fixture
def swap_pool(store):  # noqa: F811
    """swap_pool(fake): the store uses `fake` until the end of the test, then the real pool again (so the fixture can close it)."""
    real = store.pool

    def swap(fake):
        store.pool = fake
    yield swap
    store.pool = real


class DownPool:
    """Stands in for a pool whose database refuses every connection (Neon: the monthly allowance is used up)."""
    calls = 0

    def acquire(self, *a, **k):
        return self

    async def __aenter__(self):
        DownPool.calls += 1
        raise asyncpg.exceptions.InsufficientResourcesError(QUOTA)

    async def __aexit__(self, *exc):
        return False


# ------------------------------------------------------------------------------------------------------------ pool

async def test_pool_holds_no_connection_while_idle(store):  # noqa: F811
    assert store.pool.get_min_size() == 0   # min_size>=1 keeps one connection open for ever: Neon could never suspend
    s = await worker.Store.connect(make_settings(), idle_seconds=0.3)
    try:
        assert s.pool.get_size() == 0       # nothing connects at start-up
        async with s.pool.acquire() as conn:
            assert await conn.fetchval("SELECT 1") == 1
        assert s.pool.get_size() == 1
        await asyncio.sleep(1.0)
        assert s.pool.get_size() == 0       # closed after the idle time
    finally:
        await s.close()
    from finlit.store import IDLE_CONNECTION_SECONDS
    assert IDLE_CONNECTION_SECONDS <= 30


# ------------------------------------------------------------------------------------------------------------ visitors and the flag

async def test_visit_flag_and_throttle(store):  # noqa: F811
    r = store.redis
    assert not await wake.visitor_active(r)
    await wake.touch_visit(r, now=time.time() - 20 * 60)
    assert not await wake.visitor_active(r)           # twenty minutes ago is not "on the site"
    wake._last_write = 0.0
    await wake.touch_visit(r)
    assert await wake.visitor_active(r)
    first = await r.get(wake.K_VISIT)
    await wake.touch_visit(r, now=time.time() + 5)    # within 20 s: no second write
    assert await r.get(wake.K_VISIT) == first


async def test_visitor_check_fails_closed_when_redis_is_down():
    class Broken:
        async def get(self, k):
            raise ConnectionError("down")
    assert await wake.visitor_active(Broken()) is False
    assert await wake.alerts_active(Broken()) is True   # an alert is checked rather than missed


async def test_alerts_flag(store):  # noqa: F811
    r = store.redis
    assert await wake.alerts_active(r) is True          # unknown: yes
    await wake.set_alerts_flag(r, False)
    assert await wake.alerts_active(r) is False
    await wake.set_alerts_flag(r, True)
    assert await wake.alerts_active(r) is True


async def test_web_app_marks_visits_but_health_and_ping_do_not(store):  # noqa: F811
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/api/ping")).status_code == 200
            assert (await c.get("/api/health")).status_code == 200
            assert not await wake.visitor_active(store.redis)
            await c.get("/api/stocks/RELIANCE")
            assert await wake.visitor_active(store.redis)


# ------------------------------------------------------------------------------------------------------------ the budget

T0 = 1_760_000_000.0


async def stats_of(r, now):
    return await wake.stats(r, now=now)


async def test_budget_counts_wakes_and_minutes_once(store):  # noqa: F811
    r = store.redis
    await wake.mark_start(r, "a", now=T0)
    await wake.mark_end(r, "a", now=T0 + 600)               # 10 min of work + 5 min tail
    s = await stats_of(r, T0 + 700)
    assert (s["wakesToday"], s["awakeMinutesToday"]) == (1, 15)
    await wake.mark_start(r, "b", now=T0 + 720)             # inside the tail: the same wake
    await wake.mark_end(r, "b", now=T0 + 780)
    s = await stats_of(r, T0 + 800)
    assert (s["wakesToday"], s["awakeMinutesToday"]) == (1, 18)
    await wake.mark_start(r, "c", now=T0 + 7200)            # two hours later: a new wake
    await wake.mark_end(r, "c", now=T0 + 7260)
    s = await stats_of(r, T0 + 7300)
    assert (s["wakesToday"], s["awakeMinutesToday"]) == (2, 24)
    assert s["monthAwakeHours"] == 0.4 and s["monthCuHours"] == 0.1 and s["warning"] is None


async def test_overlapping_jobs_are_one_wake(store):  # noqa: F811
    r = store.redis
    await wake.mark_start(r, "a", now=T0)
    await wake.mark_start(r, "b", now=T0 + 60)
    await wake.mark_end(r, "a", now=T0 + 120)
    assert (await stats_of(r, T0 + 130))["awakeMinutesToday"] == 0      # b still holds the database: nothing is counted until the last job ends
    await wake.mark_end(r, "b", now=T0 + 3600)
    s = await stats_of(r, T0 + 3700)
    assert s["wakesToday"] == 1 and s["awakeMinutesToday"] == 65


async def test_budget_warns_at_80_percent(store):  # noqa: F811
    r = store.redis
    month_key = f"wake:month:{wake._month(T0)}"
    await r.hset(month_key, "minutes", 0.79 * 400 * 60)
    assert (await stats_of(r, T0))["warning"] is None
    await r.hset(month_key, "minutes", 0.81 * 400 * 60)
    s = await stats_of(r, T0)
    assert s["pct"] == 81 and "81%" in s["warning"] and "100" in s["warning"]
    assert "400" in s["assumption"] and s["budgetAwakeHours"] == 400


async def test_visits_count_toward_the_budget(store):  # noqa: F811
    r = store.redis
    await wake.touch_visit(r, now=T0)
    s = await stats_of(r, T0 + 1)
    assert s["wakesToday"] == 1 and s["awakeMinutesToday"] == 5


async def test_wake_cli_flags_and_gates(store, monkeypatch):  # noqa: F811
    monkeypatch.setenv("REDIS_URL", TEST_REDIS)
    assert await wake._cli(["flag-get", "bootload"]) == 1
    assert await wake._cli(["flag-set", "bootload", "60"]) == 0
    assert await wake._cli(["flag-get", "bootload"]) == 0
    assert await wake._cli(["visit-active", "15"]) == 1
    await wake.touch_visit(store.redis)
    assert await wake._cli(["visit-active", "15"]) == 0
    await wake.set_alerts_flag(store.redis, False)
    assert await wake._cli(["alerts-active"]) == 1
    assert await wake._cli(["start", "x"]) == 0 and await wake._cli(["end", "x"]) == 0
    assert await wake._cli(["nonsense"]) == 2


async def test_worker_jobs_report_to_the_budget(store, monkeypatch):  # noqa: F811
    s = make_settings()
    assert await worker.main(["migrate"], settings=s) == 0
    stats = await wake.stats(store.redis)
    assert stats["wakesToday"] >= 1 and stats["awakeMinutesToday"] >= 5


# ------------------------------------------------------------------------------------------------------------ failing gracefully

async def test_sign_in_says_so_when_the_database_refuses(store, swap_pool):  # noqa: F811
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        swap_pool(DownPool())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/auth/login", json={"email": "a@example.com", "password": PW}, headers=ORIGIN)
            assert r.status_code == 503
            assert r.json()["detail"] == "The member database is temporarily unavailable. Please try again later."
            assert r.json()["status"] == "db_unavailable" and r.headers["retry-after"]
            assert "Something went wrong" not in r.text
            other = await c.get("/api/auth/me")                       # any member route: the same clear answer, never a bare 500
            assert other.status_code in (200, 401, 503) and "Something went wrong" not in other.text


async def test_sign_in_timeout_is_also_a_clear_503(store, swap_pool):  # noqa: F811
    class Slow(DownPool):
        async def __aenter__(self):
            raise asyncio.TimeoutError()
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        swap_pool(Slow())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/auth/login", json={"email": "a@example.com", "password": PW}, headers=ORIGIN)
            assert r.status_code == 503 and r.json()["detail"]["detail"] == wake.DB_DOWN_MESSAGE   # fail() wraps the detail the way the other sign-in refusals are


async def test_every_quota_style_error_maps_to_503(store, monkeypatch):  # noqa: F811
    ex = asyncpg.exceptions
    app = create_app(make_settings(), store=store)

    @app.get("/api/_boom/{kind}")
    async def boom(kind: str):
        raise {"quota": ex.InsufficientResourcesError(QUOTA), "toomany": ex.TooManyConnectionsError("x"), "starting": ex.CannotConnectNowError("x"),
               "reset": ConnectionResetError("x"), "iface": ex.InterfaceError("x")}[kind]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            for kind in ("quota", "toomany", "starting", "reset", "iface"):
                r = await c.get(f"/api/_boom/{kind}")
                assert r.status_code == 503 and r.json()["detail"] == wake.DB_DOWN_MESSAGE, kind


async def test_health_answers_fast_when_the_database_refuses(store, swap_pool):  # noqa: F811
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        swap_pool(DownPool())
        DownPool.calls = 0
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/api/ping")).status_code == 200
            started = time.perf_counter()
            r = await c.get("/api/health")
            assert r.status_code == 200 and DownPool.calls == 0     # no visitor: the database is not asked at all
            await wake.touch_visit(store.redis)                      # a visitor is here: now the check is real
            r = await c.get("/api/health")
            assert r.status_code == 503 and r.json()["ok"] is False and DownPool.calls == 1
            r = await c.get("/api/health")                           # a failure is rechecked at most once a minute
            assert r.status_code == 503 and DownPool.calls == 1
            assert time.perf_counter() - started < 3


# ------------------------------------------------------------------------------------------------------------ admin line and flags

async def test_data_health_has_the_wake_budget_line(app):  # noqa: F811
    import time as _t

    from finlit.auth import crypto
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(_t.time()) // 30)})
    await wake.mark_start(app.state.store.redis, "t")
    await wake.mark_end(app.state.store.redis, "t")
    h = (await admin.get("/api/admin/data-health")).json()
    assert h["dbWake"]["available"] is True and h["dbWake"]["wakesToday"] >= 1
    assert h["dbWake"]["budgetCuHours"] == 100 and "assumption" in h["dbWake"]
    await admin.aclose()


async def test_saving_a_price_target_raises_the_alerts_flag(app):  # noqa: F811
    r = app.state.store.redis
    await wake.set_alerts_flag(r, False)
    c = await signed_in(app, "tgt@example.com", plan="silver")
    wl = {"lists": [{"id": "main", "name": "x", "symbols": ["RELIANCE"]}], "meta": {"RELIANCE": {"target": 1200, "added": 1}}}
    assert (await c.put("/api/me/watchlist", json=wl)).status_code == 200
    assert await wake.alerts_active(r) is True
    await c.aclose()


async def test_refresh_alerts_flag_reads_the_database(store):  # noqa: F811
    s = make_settings()
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM alerts")
        await conn.execute("UPDATE user_state SET watchlist = '{}'::jsonb")
    assert await wake.refresh_alerts_flag(s, store.redis) is False
    assert await wake.alerts_active(store.redis) is False


# ------------------------------------------------------------------------------------------------------------ deploy files

SCHEDULER = (ROOT / "deploy" / "scheduler.sh").read_text()


def test_render_health_check_is_database_free():
    cfg = yaml.safe_load((ROOT / "render.yaml").read_text())
    assert cfg["services"][0]["healthCheckPath"] == "/api/ping"


def test_the_supervisor_gates_quotes_and_alerts_on_visitors_and_alerts_and_results_on_nothing():
    """The old bash main loop is gone (docs/JOBS.md): the same gating now lives in the registry. Quotes follow visitors (or, slower, member alerts), the live alert job
    needs an alert to exist, and the results jobs need no visitor unless RESULTS_NEED_VISITOR=1."""
    from finlit.jobs.registry import by_name
    jobs = by_name({})
    assert jobs["quotes"].visitor_gate == "visitor_or_alerts" and jobs["quotes"].interval_idle_min == 15 and jobs["quotes"].interval_market
    assert jobs["alerts-live"].visitor_gate == "alerts" and jobs["alerts-live"].interval_min == 15 and jobs["alerts-live"].interval_market
    for n in ("results", "results-light", "calendars"):
        assert jobs[n].visitor_gate == "env:RESULTS_NEED_VISITOR"
    assert "scheduler.sh" in " ".join(jobs["drain-queue"].what.split()) or jobs["drain-queue"].external
    assert "run light" not in SCHEDULER and "due(" not in SCHEDULER


def test_the_scheduler_keeps_the_loops_quiet_and_the_windows_live_in_the_registry():
    from finlit.jobs.schedule import WINDOWS
    assert set(WINDOWS) == {"MORNING", "AFTER_CLOSE", "NIGHT"}
    assert "sleep 120; done" in SCHEDULER and "sleep 30; done" not in SCHEDULER      # a loop that exits waits two minutes, not 30 s
    assert "/api/health" not in SCHEDULER                                               # nothing here queries the database while idle
    from finlit.jobs.registry import by_name
    jobs = by_name({"FUND_LOADS_ENABLED": "1"})
    for job in ("quotes", "alerts-live", "results", "results-light", "calendars"):
        assert job in jobs


def test_deploy_scripts_parse(tmp_path):
    import subprocess
    for f in ("scheduler.sh", "render-start.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / "deploy" / f)]).returncode == 0
