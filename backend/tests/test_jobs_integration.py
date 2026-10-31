"""The job supervisor against the real Postgres and Redis: migration 077, state storage, the time-boxed pause, the status endpoint, alert delivery, the lock."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from finlit.jobs import pause as pausemod, status as jobs_status
from finlit.jobs.alerts import Notifier, supervisor_problem
from finlit.jobs.due import JobState
from finlit.jobs.registry import Job, Sla, build_jobs
from finlit.jobs.signals import BEAT_KEY, RedisSignals
from finlit.jobs.state import PgState
from finlit.jobs.supervisor import Supervisor
from jobs_fakes import FakeClock, FakeResources, FakeRunner, FakeSignals, config
from test_auth import app, make_admin  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)


async def clean(store):
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM job_runs; DELETE FROM job_state; DELETE FROM mf_meta WHERE key = 'switch:loads'")


async def test_migration_077_creates_the_job_tables(store):
    async with store.pool.acquire() as conn:
        cols = {r["column_name"] for r in await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'job_state'")}
        runs = {r["column_name"] for r in await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'job_runs'")}
        assert await conn.fetchval("SELECT count(*) FROM schema_migrations WHERE version = '077_jobs'") == 1
    assert {"last_success_at", "last_attempt_at", "next_due_at", "consecutive_failures", "held_until", "held_reason", "retry_at", "forced_at"} <= cols
    assert {"started_at", "finished_at", "status", "reason", "attempt", "exit_code", "duration_s", "peak_rss_mb", "counts"} <= runs


async def test_state_round_trip_and_the_run_history(store):
    await clean(store)
    st = PgState(store.pool)
    await st.ensure(["a", "b"], NOW)
    await st.ensure(["a"], NOW + timedelta(days=1))                      # does not overwrite first_seen_at
    s = (await st.load_all())["a"]
    assert s.first_seen_at == NOW and s.state == "idle"
    s.last_success_at, s.consecutive_failures, s.retry_at, s.state, s.state_reason = NOW, 2, NOW + timedelta(minutes=30), "waiting", "retry"
    await st.save(s)
    s2 = (await st.load_all())["a"]
    assert (s2.last_success_at, s2.consecutive_failures, s2.retry_at, s2.state_reason) == (NOW, 2, NOW + timedelta(minutes=30), "retry")
    rid = await st.start_run("a", NOW, 3, 4321)
    assert [r["job"] for r in await st.running_runs()] == ["a"]
    await st.finish_run(rid, NOW + timedelta(minutes=5), "failed", "exit code 1", 1, 300.0, 210, {"tail": "boom"})
    await st.record_skip("b", NOW, "waiting for memory: 10 MB free")
    rows = await st.recent_runs(10)
    assert [r["status"] for r in rows] == ["skipped", "failed"] and rows[1]["counts"] == {"tail": "boom"} and rows[1]["peak_rss_mb"] == 210
    assert await st.running_runs() == []
    assert len(await st.recent_runs(10, job="a")) == 1


async def test_the_real_state_drives_the_supervisor_end_to_end(store):
    await clean(store)
    clock = FakeClock(NOW)
    j = Job("probe-job", ("probe",), cls="bulk", priority=1, weight_mb=100, sla=Sla("hours", 26))
    sup = Supervisor(jobs=[j], state=PgState(store.pool), runner=FakeRunner(clock), resources=FakeResources(), signals=FakeSignals(), pause=pausemod.PgPause(store.pool), clock=clock,
                     config=config(), env={})
    await sup.step()
    assert sup.runner.started == ["probe-job"]
    sup.runner.of("probe-job").finish(0)
    await sup.poll()
    s = (await PgState(store.pool).load_all())["probe-job"]
    assert s.last_success_at == clock.now() and s.last_status == "ok"
    clock.advance(minutes=5)
    sup2 = Supervisor(jobs=[j], state=PgState(store.pool), runner=FakeRunner(clock), resources=FakeResources(), signals=FakeSignals(), pause=pausemod.PgPause(store.pool), clock=clock,
                      config=config(), env={})
    await sup2.step()
    assert sup2.runner.started == []                                     # a new supervisor sees the stored success: nothing to do


# ------------------------------------------------------------------------------------------------ the time-boxed pause
def test_pause_interpretation_is_pure_and_covers_every_case():
    now = NOW
    assert pausemod.interpret(None, now) == (None, None)
    assert pausemod.interpret({"enabled": True}, now) == (None, None)
    info, write = pausemod.interpret({"enabled": False, "by": "a@b.c", "at": now.isoformat(), "pausedUntil": (now + timedelta(minutes=20)).isoformat()}, now)
    assert info.until == now + timedelta(minutes=20) and not info.legacy and write is None
    info, write = pausemod.interpret({"enabled": False, "pausedUntil": (now - timedelta(minutes=1)).isoformat()}, now)
    assert info is None and write["enabled"] is True and write["resumedAuto"] is True          # expired: resumes by itself
    info, write = pausemod.interpret(json.dumps({"enabled": False, "by": "x"}), now)             # the old row: "off" without an expiry
    assert info.legacy and info.until == now + timedelta(minutes=30) and write["pausedUntil"] and write["legacy"] is True


async def test_a_legacy_off_switch_resumes_30_minutes_after_it_is_first_read_and_an_expired_pause_clears_itself(store):
    await clean(store)
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_meta (key, value) VALUES ('switch:loads', '{\"enabled\": false, \"by\": \"old\"}')")
        info = await pausemod.read_pause(conn, NOW)
        assert info.legacy and info.until == NOW + timedelta(minutes=30)
        info2 = await pausemod.read_pause(conn, NOW + timedelta(minutes=10))                       # the expiry was stored on the first read: it does not slide
        assert info2.until == NOW + timedelta(minutes=30)
        assert await pausemod.read_pause(conn, NOW + timedelta(minutes=31)) is None
        raw = json.loads(await conn.fetchval("SELECT value FROM mf_meta WHERE key = 'switch:loads'"))
        assert raw["enabled"] is True and raw["resumedAuto"] is True


async def test_set_pause_stores_the_expiry_and_who_set_it(store):
    await clean(store)
    async with store.pool.acquire() as conn:
        v = await pausemod.set_pause(conn, NOW, False, 120, "boss@example.com")
        assert v["pausedUntil"] == (NOW + timedelta(hours=2)).isoformat(timespec="seconds")
        info = await pausemod.read_pause(conn, NOW + timedelta(minutes=1))
        assert info.by == "boss@example.com" and info.until == NOW + timedelta(hours=2)
        await pausemod.set_pause(conn, NOW, True, None, "boss@example.com")
        assert await pausemod.read_pause(conn, NOW) is None


async def test_the_admin_api_pauses_with_an_expiry_and_refuses_a_long_pause_without_confirmation(app):  # noqa: F811
    import time as _t
    from finlit.auth import crypto
    boss = await make_admin(app, "pause-boss@example.com")
    secret = (await boss.post("/api/me/mfa/setup")).json()["secret"]
    await boss.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(_t.time()) // 30)})
    await clean(app.state.store)
    r = (await boss.post("/api/admin/system/loads", json={"enabled": False})).json()
    assert r["loadsEnabled"] is False and r["resumesAutomatically"] is True and r["pausedBy"] == "pause-boss@example.com"
    until = datetime.fromisoformat(r["pausedUntil"])
    assert timedelta(minutes=29) < until - datetime.now(timezone.utc) <= timedelta(minutes=30, seconds=5)        # default 30 minutes
    assert r["pausedUntilIST"].endswith("IST") and r["pauseChoicesMinutes"] == [30, 120, 720]
    r = (await boss.post("/api/admin/system/loads", json={"enabled": False, "minutes": 720})).json()
    assert timedelta(hours=11, minutes=59) < datetime.fromisoformat(r["pausedUntil"]) - datetime.now(timezone.utc) <= timedelta(hours=12, seconds=5)
    long = await boss.post("/api/admin/system/loads", json={"enabled": False, "minutes": 1440})
    assert long.status_code == 422 and long.json()["detail"]["status"] == "confirm_long_pause"
    ok = await boss.post("/api/admin/system/loads", json={"enabled": False, "minutes": 1440, "confirmLong": True})
    assert ok.status_code == 200 and ok.json()["loadsEnabled"] is False
    assert (await boss.post("/api/admin/system/loads", json={"enabled": False, "minutes": 0})).status_code == 422
    back = (await boss.post("/api/admin/system/loads", json={"enabled": True})).json()
    assert back["loadsEnabled"] is True and back["pausedUntil"] is None
    # an expired pause reads as running without anyone touching the switch
    async with app.state.store.pool.acquire() as conn:
        await pausemod.set_pause(conn, datetime.now(timezone.utc) - timedelta(hours=1), False, 30, "x")
    assert (await boss.get("/api/admin/system/status")).json()["loadsEnabled"] is True
    await boss.aclose()


# ------------------------------------------------------------------------------------------------ the status endpoint
async def seed(store, rows):
    st = PgState(store.pool)
    await st.ensure([j.name for j in build_jobs({})], NOW - timedelta(days=30))
    for name, kw in rows.items():
        s = (await st.load_all())[name]
        for k, v in kw.items():
            setattr(s, k, v)
        await st.save(s)


async def test_status_shape_healthy_and_overdue_logic(store):
    await clean(store)
    env = {"FUND_LOADS_ENABLED": "0"}
    ok_recent = {j.name: dict(last_success_at=NOW - timedelta(minutes=10), last_status="ok", state="idle") for j in build_jobs(env) if not j.external}
    await seed(store, ok_recent)
    await store.redis.set(BEAT_KEY, json.dumps({"at": NOW.timestamp() - 30, "running": ["technicals"], "dbOk": True}))
    body = await jobs_status.build(store, store.redis, NOW, env)
    assert body["healthy"] is True and body["overdue"] == [] and body["supervisor"]["alive"] and body["supervisor"]["running"] == ["technicals"]
    job = {j["name"]: j for j in body["jobs"]}
    assert set(job["results"]) >= {"name", "state", "reason", "lastSuccessAt", "ageHours", "slaHours", "nextDueAt", "consecutiveFailures", "late", "overdue", "disabledByConfig"}
    assert job["results"]["slaHours"] == 1.5 and job["results"]["ageHours"] == pytest.approx(0.17, abs=0.01)
    assert job["mf"]["state"] == "disabled" and job["mf"]["disabledByConfig"] and "FUND_LOADS_ENABLED=1" in job["mf"]["disabledReason"]
    assert body["disabledByConfig"] and any(d["name"] == "mf" for d in body["disabledByConfig"]) and "mf" not in body["overdue"]       # disabled is flagged, never "overdue"
    assert body["pause"]["paused"] is False and body["pause"]["resumesAutomatically"] is True
    # a job 3 times past its promise is overdue and makes the whole thing unhealthy
    await seed(store, {"ingest": dict(last_success_at=NOW - timedelta(hours=60))})
    body = await jobs_status.build(store, store.redis, NOW, env)
    assert body["overdue"] == ["ingest"] and body["healthy"] is False and "overdue: ingest" in body["healthNote"]
    # 1.2 x the SLA is late but not yet overdue
    await seed(store, {"ingest": dict(last_success_at=NOW - timedelta(hours=31))})
    body = await jobs_status.build(store, store.redis, NOW, env)
    assert body["overdue"] == [] and {j["name"]: j for j in body["jobs"]}["ingest"]["late"] is True and body["healthy"] is True
    # no heartbeat for 6 minutes: the supervisor is considered dead
    await store.redis.set(BEAT_KEY, json.dumps({"at": NOW.timestamp() - 360}))
    body = await jobs_status.build(store, store.redis, NOW, env)
    assert body["supervisor"]["alive"] is False and body["healthy"] is False and "supervisor not reporting" in body["healthNote"]
    assert body["resultsDelayed"] is False


async def test_results_delayed_flag_and_the_pause_block(store):
    await clean(store)
    env = {"FUND_LOADS_ENABLED": "1"}
    await seed(store, {"results": dict(last_success_at=NOW - timedelta(hours=1, minutes=45))})
    async with store.pool.acquire() as conn:
        await pausemod.set_pause(conn, NOW, False, 30, "boss@example.com")
    body = await jobs_status.build(store, store.redis, NOW + timedelta(minutes=10), env)
    assert body["pause"]["paused"] is True and body["pause"]["setBy"] == "admin" and "boss@example.com" not in json.dumps(body)       # no addresses in a public page
    body = await jobs_status.build(store, store.redis, NOW + timedelta(hours=5), env)
    assert body["pause"]["paused"] is False


async def test_the_endpoint_is_public_read_only_and_never_cached(ingested):
    import httpx
    from finlit.api import create_app
    app = create_app(make_settings(), store=ingested)
    jobs_status._cache["t"] = 0
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/jobs/status")
            assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
            body = r.json()
            assert {"healthy", "overdue", "pause", "supervisor", "jobs", "data", "canary", "disabledByConfig", "dataFresh", "resultsDelayed"} <= set(body)
            assert (await c.post("/api/jobs/status")).status_code in (404, 405)
            text = r.text
            assert "password" not in text.lower() and "secret" not in text.lower() and "token" not in text.lower()


# ------------------------------------------------------------------------------------------------ alerts and the lock
async def test_alerts_reach_every_admin_in_app_and_by_email_once_per_six_hours(app):  # noqa: F811
    store = app.state.store
    await (await make_admin(app, "alert-boss@example.com")).aclose()
    await store.redis.flushdb()
    n = Notifier(store.pool, app.state.mailer, store.redis, "https://finlit.example")
    assert await n.alert("overdue:results", "FinLit job overdue: results", "results has not succeeded for 5 hours")
    assert not await n.alert("overdue:results", "FinLit job overdue: results", "again")          # rate limited
    assert await n.alert("overdue:calendars", "FinLit job overdue: calendars", "x")              # another problem is its own alert
    async with store.pool.acquire() as conn:
        notes = await conn.fetch("SELECT n.title, n.kind, n.link FROM notifications n JOIN users u ON u.id = n.user_id WHERE u.email = 'alert-boss@example.com' AND n.kind = 'system'")
        mails = await conn.fetch("SELECT subject, body FROM outbox WHERE to_email = 'alert-boss@example.com' AND subject LIKE '[FinLit]%'")
    assert len(notes) == 2 and notes[0]["link"] == "/console"
    assert len(mails) == 2 and "Open the admin console: https://finlit.example/console" in mails[0]["body"]


async def test_the_web_process_notices_a_dead_supervisor(store):
    await store.redis.flushdb()
    now = time.time()
    assert "never reported" in await supervisor_problem(store.redis, now)
    assert await supervisor_problem(store.redis, now, started_grace_s=100) is None                # right after the web server starts there is a grace period
    await store.redis.set(BEAT_KEY, json.dumps({"at": now - 60}))
    assert await supervisor_problem(store.redis, now) is None
    await store.redis.set(BEAT_KEY, json.dumps({"at": now - 400}))
    assert "6 minutes old" in await supervisor_problem(store.redis, now)


async def test_only_one_real_supervisor_holds_the_redis_lock(store):
    await store.redis.flushdb()
    a, b = RedisSignals(store.redis), RedisSignals(store.redis)
    assert await a.acquire_lock() is True
    assert await b.acquire_lock() is False
    assert await b.refresh_lock() is False                                # b cannot extend a's lock
    assert await a.refresh_lock() is True
    await b.release_lock()                                                # releasing someone else's lock does nothing
    assert await b.acquire_lock() is False
    await a.release_lock()
    assert await b.acquire_lock() is True
    await b.heartbeat(NOW, {"running": []})
    assert json.loads(await store.redis.get(BEAT_KEY))["at"] == NOW.timestamp()
    assert await store.redis.get("scheduler:alive")                       # the key /api/results/status has always shown


async def test_pruning_deletes_old_finished_runs_only(store):
    await clean(store)
    st = PgState(store.pool)
    old = await st.start_run("a", NOW - timedelta(days=90), 1, 1)
    await st.finish_run(old, NOW - timedelta(days=90), "ok", None, 0, 1.0, None, {})
    running = await st.start_run("a", NOW - timedelta(days=90), 1, 2)
    fresh = await st.start_run("a", NOW, 1, 3)
    await st.prune_runs(NOW, 60)
    assert sorted(r["id"] for r in await st.recent_runs(10)) == sorted([running, fresh])
