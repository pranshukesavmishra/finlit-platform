"""Why the latest results could be stale, one test each: the calendar refresh, the retry back-off, the run records and the status page."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finlit import results as R
from finlit import results_light as L
from finlit.calendars import SOURCE_RESULTS, refresh_calendars, today_ist, why
from finlit.finedge import FinEdgeError
from test_integration import store  # noqa: F401
from test_results_light import ALL, E, QK, provider, upto

pytestmark = pytest.mark.integration
DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


class Fake:
    def __init__(self, results, ipos=None, fail=None): self.results, self.ipos, self.fail = results, ipos or [], fail
    async def get(self, path, params=None, timeout=10, retries=3):
        if self.fail and path == "/results-calendar": raise self.fail
        return self.results if path == "/results-calendar" else self.ipos


def test_today_is_the_indian_day_and_failures_say_why():
    assert today_ist() == datetime.now(R.IST).date()
    assert why(FinEdgeError("/results-calendar", 502, "Bad Gateway")).startswith("FinEdgeError HTTP 502")
    assert why(RuntimeError("x")) == "RuntimeError: x"


async def test_calendar_that_sends_only_upcoming_dates_keeps_the_past_ones(store):  # noqa: F811
    t = today_ist()
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE source = $1", SOURCE_RESULTS)
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, source, item_date, auto, dedupe) VALUES ('result', 'old', 'OLD', 'Old', $1, $2, true, 'rc-test-old')", SOURCE_RESULTS, t - timedelta(days=5))
    rep: dict = {}
    f = Fake({"data": [{"symbol": "NEW", "company_name": "New", "expected_result_date": (t + timedelta(days=3)).isoformat()}]})
    await refresh_calendars(f, store, report=rep)
    async with store.pool.acquire() as conn:
        syms = {r["symbol"] for r in await conn.fetch("SELECT symbol FROM feed_items WHERE source = $1", SOURCE_RESULTS)}
        await conn.execute("DELETE FROM feed_items WHERE source = $1", SOURCE_RESULTS)
    assert syms == {"OLD", "NEW"} and rep["newestSent"] == (t + timedelta(days=3)).isoformat() and rep["errors"] == {}


async def test_calendar_failures_and_empty_answers_are_reported_with_their_reason(store):  # noqa: F811
    rep: dict = {}
    assert await refresh_calendars(Fake({}, fail=FinEdgeError("/results-calendar", 502, "Bad Gateway")), store, report=rep) == {"results": 0, "ipos": 0}
    assert "HTTP 502" in rep["errors"]["results"]
    rep = {}
    await refresh_calendars(Fake({"data": []}), store, report=rep)
    assert rep["errors"]["results"] == "the provider sent no rows"
    rep = {}
    await refresh_calendars(Fake({"data": [{"symbol": "AAA", "when": "2026-10-30"}]}), store, report=rep)       # rows sent but the date field has another name
    assert "none with a symbol and a readable date" in rep["errors"]["results"] and "when" in rep["errors"]["results"]


def test_retry_back_off():
    d = date(2026, 10, 29)
    assert [R.retry_minutes(50, d, d + timedelta(days=n)) for n in range(5)] == [50, 50, 150, 300, 300]


@pytest.fixture
async def one(store, monkeypatch):  # noqa: F811
    decls = {QK: {"AAA": R.Decl(date(2026, 7, 18), True, "Aaa")}}

    async def fake(store_, force=False):
        return decls
    monkeypatch.setattr(R, "get_declarations", fake)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
    yield
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")


async def test_a_late_company_is_asked_less_often_and_a_fresh_one_every_run(store, one):  # noqa: F811
    today = date(2026, 7, 21)                        # declared 3 days ago
    async with store.pool.acquire() as conn:
        await L.save(conn, "AAA", QK, {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)})
        await conn.execute("UPDATE quarter_light SET checked_at = now() - interval '2 hours'")
    assert await L.candidates(store, today) == []                                   # back-off: not again after 2 hours
    assert await L.candidates(store, date(2026, 7, 19)) == [("AAA", QK)]            # declared yesterday: asked again after 50 minutes
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE quarter_light SET checked_at = now() - interval '6 hours'")
    assert await L.candidates(store, today) == [("AAA", QK)]


async def test_row_says_when_it_last_asked_and_what_the_provider_holds(store, one):  # noqa: F811
    async with store.pool.acquire() as conn:
        await L.save(conn, "AAA", QK, {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)})
    d = R.Decl(date(2026, 7, 20), True, "Aaa")
    late = {r["symbol"]: r for r in (await R._build(store, E, {"AAA": d}, date(2026, 7, 21))).rows}["AAA"]
    assert late["status"] == "awaiting" and late["awaitingWhy"] == "provider" and late["awaitingStage"] == "late" and late["providerLatest"] == "2026-03-31"
    assert datetime.fromisoformat(late["lastCheckedAt"]).tzinfo is not None
    same_day = {r["symbol"]: r for r in (await R._build(store, E, {"AAA": d}, date(2026, 7, 20))).rows}["AAA"]
    assert same_day["awaitingStage"] == "recent"


async def test_a_refusing_provider_is_not_asked_for_every_company(store, monkeypatch):  # noqa: F811
    syms = [f"S{i:02d}" for i in range(30)]

    async def fake(store_, force=False):
        return {QK: {s: R.Decl(date(2026, 7, 20), True, s) for s in syms}}
    monkeypatch.setattr(R, "get_declarations", fake)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
    calls: list = []
    async with provider({s: {"c": 429} for s in syms}, calls) as client:
        out = await L.refresh_light(client, store, today=date(2026, 7, 21), pause=0)
    assert out["failed"] == L.MAX_IN_A_ROW and out["stoppedEarly"] is True and len(calls) <= L.MAX_IN_A_ROW * 4
    assert any("HTTP 429" in k for k in out["errors"])


async def test_status_shows_the_last_runs_and_the_newest_result(store):  # noqa: F811
    from finlit.mf import record_run
    t = today_ist()
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE source = $1", SOURCE_RESULTS)
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, source, item_date, auto, dedupe) VALUES ('result', 'x', 'ZZZ', 'Zzz', $1, $2, true, 'rc-test-s1'), ('result', 'y', 'YYY', 'Yyy', $1, $3, true, 'rc-test-s2')",
                           SOURCE_RESULTS, t - timedelta(days=1), t + timedelta(days=2))
    from finlit.worker import _record_results_run
    await _record_results_run(store, "refresh-calendars", "ok", {"results": 2, "ipos": 0}, {})
    await store.redis.set("wake:note:results", json.dumps({"at": "2026-10-30T10:00:00+05:30", "why": "skipped: heavy data loads are paused by the admin switch"}))
    st = await R.pipeline_status(store)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE source = $1", SOURCE_RESULTS)
    await store.redis.delete("wake:note:results")
    assert st["todayIST"] == t.isoformat() and st["newestResultInDb"] >= (t - timedelta(days=1)).isoformat() and st["upcomingCount"] >= 1
    cal = st["lastRun"]["calendars"]
    assert cal["status"] == "ok" and cal["counts"] == {"results": 2, "ipos": 0} and cal["newestResultDate"] == st["newestResultInDb"] and cal["at"]
    assert st["lastRun"]["results"] is None or "status" in st["lastRun"]["results"]
    assert "paused" in st["lastSkipped"]["results"]["why"]


def test_the_supervisor_runs_the_results_jobs_without_a_visitor_every_evening_hour_and_in_the_morning():
    from finlit.jobs.due import Ctx, JobState, evaluate
    from finlit.jobs.registry import by_name
    from jobs_fakes import ist
    jobs = by_name({})
    for name in ("results", "results-light", "calendars"):
        j = jobs[name]
        assert j.honours_pause is False and j.visitor_gate == "env:RESULTS_NEED_VISITOR" and j.cls == "light"
        for hm in ((8, 20), (15, 50), (19, 10), (21, 10), (23, 30)):          # every old evening slot: due without a visitor
            now = ist(2026, 10, 30, *hm)
            st = JobState(job=name, first_seen_at=now - timedelta(days=9), last_success_at=now - timedelta(hours=1.5), last_attempt_at=now - timedelta(hours=1.5))
            assert evaluate(j, st, Ctx(now=now, visitor_active=False)).due, (name, hm)
        morning = ist(2026, 10, 31, 5, 30)
        st = JobState(job=name, first_seen_at=morning - timedelta(days=9), last_success_at=morning - timedelta(hours=6))
        assert evaluate(j, st, Ctx(now=morning)).due, name                                  # the early window: before the 08:00 active hours
        now = ist(2026, 10, 31, 10, 0)
        st = JobState(job=name, first_seen_at=now - timedelta(days=9), last_success_at=now - timedelta(hours=0.9))
        assert not evaluate(j, st, Ctx(now=now, visitor_active=False, env={"RESULTS_NEED_VISITOR": "1"})).due   # the old metered-database rule is still available

