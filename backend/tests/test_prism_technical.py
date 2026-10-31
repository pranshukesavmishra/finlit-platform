"""The daily technical refresh (finlit/prism_technical.py): the root cause of 'the technical score is late', and its fix.

ROOT CAUSE (test_precompute_never_refreshes_a_young_report_so_its_technical_view_ages): the technical view lives inside the stored Prism report, and
the nightly job selects only companies with no report or a report older than `days` (7), so a report calculated days ago keeps showing the technical
scores of that day. The refresh below recalculates only that view, against a fake site backend and fake Dhan candles."""

import copy
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finlit import prism, prism_technical as pt
from finlit.prism_candles import expected_session
from test_integration import make_settings, store  # noqa: F401  (fixtures)
from test_prism import SECRET, SNAPSHOT, FakeSite, claims

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
IST = prism.IST
FRIDAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 18, 30, tzinfo=IST)          # 18:30 IST on Friday 23 Oct 2026


class TechnicalSite(FakeSite):
    """The site backend's technical route: answers the fixture's real technical assessment with the as-of date of the newest candle sent."""

    def __init__(self):
        super().__init__()
        self.technical, self.status, self.ready = [], 200, True

    async def __call__(self, request):
        if request.url.path != "/api/premium-reports/technical":
            return await super().__call__(request)
        body = json.loads(request.content)
        self.technical.append({"sub": claims(request.headers["authorization"].removeprefix("Bearer "))["sub"], "body": body})
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "x"})
        tech = copy.deepcopy(SNAPSHOT["technicalAssessment"])
        tech["asOf"] = body["suppliedCandles"]["stock"]["candles"][-1][0]
        tech["sharesCr"] = body.get("sharesCr")
        if not self.ready:
            tech["status"], tech["shortTerm"]["score"] = "incomplete", None
            tech["dailyBars"] = tech["usableDailyBars"] + 5
        return httpx.Response(200, json={"technicalAssessment": tech, "calculatedAt": datetime.now(timezone.utc).isoformat()})


def candles_to(day: date):
    return {"stock": {"provider": "Dhan", "candles": [[(day - timedelta(days=1)).isoformat(), 1, 2, 1, 1.5, 9], [day.isoformat(), 1, 2, 1, 1.5, 9]]}, "indices": {}}


@pytest.fixture
async def world(store, monkeypatch):  # noqa: F811
    seen = {"candles": [], "reference": FRIDAY, "available": FRIDAY, "has": {}}

    async def fake_candles(state, symbol, now=None, quote_price=None):
        seen["candles"].append((symbol, quote_price))
        day = seen["has"].get(symbol, seen["available"])
        return candles_to(day) if day else None

    async def fake_reference(state, now=None):
        return seen["reference"]

    monkeypatch.setattr(pt, "supplied_candles", fake_candles)
    monkeypatch.setattr(pt, "reference_session", fake_reference)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol LIKE 'TQ%'")
    for pattern in ("prism:tech:*", "prism:member:active"):
        for key in [k async for k in store.redis.scan_iter(match=pattern)]:
            await store.redis.delete(key)
    settings = make_settings(site_api_url="http://site", cms_jwt_secret=SECRET)
    site = TechnicalSite()
    http = httpx.AsyncClient(transport=httpx.MockTransport(site), base_url="http://site")
    yield store, settings, site, http, seen
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol LIKE 'TQ%'")


async def seed(store, symbol, bar="2026-10-16", age_days=2, statement="consolidated", cap=1000.0, with_quote=True):
    """A stored report, calculated `age_days` ago, whose technical view is as of `bar`."""
    snap = copy.deepcopy(SNAPSHOT)
    snap["technicalAssessment"]["asOf"] = bar
    view = prism.reader_view(snap)
    await prism._save(store, symbol, statement, view, None)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE prism_reports SET generated_at = now() - make_interval(days => $3) WHERE symbol = $1 AND statement = $2", symbol, statement, age_days)
        if with_quote:
            await conn.execute("INSERT INTO listing_quotes (symbol, price, market_cap) VALUES ($1, 500, $2) ON CONFLICT (symbol) DO UPDATE SET price = 500, market_cap = $2", symbol, cap)


async def row(store, symbol, statement="consolidated"):
    r = await store.pool.fetchrow("SELECT * FROM prism_reports WHERE symbol = $1 AND statement = $2", symbol, statement)
    return r, json.loads(r["report"]), json.loads(r["card"])


# ----------------------------------------------------------------------------------------------- H1: the root cause
async def test_precompute_never_refreshes_a_young_report_so_its_technical_view_ages(world):
    store, settings, site, http, seen = world
    await seed(store, "TQAGE", bar="2026-10-16", age_days=2)
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ('TQAGE', 'consolidated', 'summary', '{}', 'x', now()) ON CONFLICT DO NOTHING")
    try:
        assert await prism._pending(store, "consolidated", 7, 100, []) == []                      # the nightly job leaves it alone for 7 days...
        assert await prism._pending(store, "consolidated", 7, 100, []) == await prism._pending(store, "consolidated", 30, 100, [])
        assert await prism.widen_candidates(store, "consolidated", 100, []) is not None
        assert "TQAGE" in await pt.pending(store, FRIDAY, 100, [])                                  # ...while the technical refresh sees that it is a week behind
    finally:
        async with store.pool.acquire() as conn:
            await conn.execute("DELETE FROM snapshots WHERE symbol = 'TQAGE'")


async def test_selection_is_by_bar_date_not_by_report_age(world):
    store, settings, site, http, seen = world
    await seed(store, "TQNEW", bar="2026-10-23", age_days=40)       # an old report whose technical view is current
    await seed(store, "TQOLD", bar="2026-10-22", age_days=0)        # a brand new report with a one-day-old view
    await seed(store, "TQSAME", bar="2026-10-23", age_days=0)
    await seed(store, "TQBIG", bar="2026-10-16", age_days=1, cap=500000)
    await seed(store, "TQLITTLE", bar="2026-10-16", age_days=1, cap=10)
    got = await pt.pending(store, FRIDAY, 100, [])
    assert [s for s in got if s.startswith("TQ")] == ["TQBIG", "TQOLD", "TQLITTLE"]     # biggest first; the current ones are not listed
    assert (await pt.pending(store, FRIDAY, 1, []))[0] == "TQBIG"
    assert "TQNEW" in await pt.pending(store, FRIDAY, 100, [], force=True)
    assert await pt.pending(store, FRIDAY, 100, [], symbols=["TQOLD"]) == ["TQOLD"]
    assert "TQBIG" not in await pt.pending(store, FRIDAY, 100, ["TQBIG"])


# ----------------------------------------------------------------------------------------------- the refresh itself
async def test_the_refresh_replaces_only_the_technical_view_and_its_dates(world):
    store, settings, site, http, seen = world
    await seed(store, "TQA", bar="2026-10-16", age_days=3)
    before, rep0, card0 = await row(store, "TQA")
    out = await pt.refresh(store, settings, client=http, now=NOW, symbols=["TQA"])
    assert out["status"] == "ok" and out["updated"] == 1 and out["targetSession"] == "2026-10-23" and out["failed"] == 0
    after, rep1, card1 = await row(store, "TQA")
    assert rep1["technicalAssessment"]["asOf"] == "2026-10-23" and card1["technicalBarDate"] == "2026-10-23" and card1["technicalAt"]
    assert rep1["technicalCalculatedAt"] == card1["technicalAt"]
    assert {k: v for k, v in rep1.items() if k not in ("technicalAssessment", "technicalCalculatedAt")} == {k: v for k, v in rep0.items() if k != "technicalAssessment"}
    assert (after["id"], after["generated_at"], after["final"], after["label"], after["status"]) == (before["id"], before["generated_at"], before["final"], before["label"], before["status"])
    assert card1["parts"] == card0["parts"] and card1["confidence"] == card0["confidence"]
    assert card1["st"]["score"] == rep1["technicalAssessment"]["shortTerm"]["score"] and "inputHash" not in json.dumps(rep1["technicalAssessment"])
    assert site.technical[0]["sub"] == "prism:technical" and site.technical[0]["body"]["priority"] == "background"
    assert site.technical[0]["body"]["sharesCr"] == pytest.approx(1000.0 / 500)             # listing market value / price, in crore
    assert seen["candles"] == [("TQA", 500.0)]                                               # the last close is checked against the listing price
    again = await pt.refresh(store, settings, client=http, now=NOW)
    assert again["updated"] == 0 and again["queued"] == 0 and len(site.technical) == 1       # at the newest session: nothing is fetched again


async def test_both_statements_of_a_company_get_the_same_view_in_one_call(world):
    store, settings, site, http, seen = world
    await seed(store, "TQB", statement="consolidated")
    await seed(store, "TQB", statement="standalone")
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["updated"] == 1 and len(site.technical) == 1
    assert (await row(store, "TQB", "standalone"))[2]["technicalBarDate"] == (await row(store, "TQB", "consolidated"))[2]["technicalBarDate"] == "2026-10-23"


async def test_the_shares_the_report_used_are_reused_so_the_benchmark_cannot_change(world):
    store, settings, site, http, seen = world
    await seed(store, "TQS", cap=99999)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE prism_reports SET report = jsonb_set(report, '{technicalAssessment,sharesCr}', '3.5') WHERE symbol = 'TQS'")
    await pt.refresh(store, settings, client=http, now=NOW)
    assert site.technical[0]["body"]["sharesCr"] == 3.5


async def test_a_holiday_or_a_late_dhan_makes_the_newest_session_the_earlier_one_and_nothing_is_fetched_twice(world):
    store, settings, site, http, seen = world
    seen["reference"] = date(2026, 10, 22)                  # Dhan's Nifty 50 ends on Thursday although Friday is expected
    seen["available"] = date(2026, 10, 22)
    await seed(store, "TQH", bar="2026-10-21")
    await seed(store, "TQH2", bar="2026-10-22")
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["expectedSession"] == "2026-10-23" and out["targetSession"] == "2026-10-22" and out["updated"] == 1 and out["queued"] == 1
    assert (await row(store, "TQH"))[2]["technicalBarDate"] == "2026-10-22"
    assert (await pt.status_report(store, NOW))["newestSessionFound"] == "2026-10-22"
    # the late retry: Dhan now has Friday
    seen["reference"] = seen["available"] = FRIDAY
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["updated"] == 2 and out["targetSession"] == "2026-10-23"


async def test_a_company_dhan_holds_nothing_newer_for_is_not_asked_again_that_day(world):
    store, settings, site, http, seen = world
    await seed(store, "TQSUSP", bar="2026-10-20")
    seen["has"]["TQSUSP"] = date(2026, 10, 20)               # suspended: its newest candle is the stored one
    first = await pt.refresh(store, settings, client=http, now=NOW)
    assert first["skipped"] == 1 and first["reasons"] == {"no_new_bar": 1} and site.technical == []
    n = len(seen["candles"])
    second = await pt.refresh(store, settings, client=http, now=NOW)
    assert second["queued"] == 0 and len(seen["candles"]) == n


async def test_no_candles_leaves_the_stored_view_and_says_why_and_five_failures_stop_the_run(world):
    store, settings, site, http, seen = world
    for i in range(8):
        await seed(store, f"TQF{i}", cap=100 - i)
    seen["available"] = None                                  # Dhan answers nothing
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["status"] == "partial" and out["failed"] == 5 and out["reasons"] == {"no_candles": 5} and "five failures" in out["stopped"]
    assert (await row(store, "TQF0"))[2]["technicalBarDate"] == "2026-10-16"      # unchanged, still labelled with its own date
    seen["available"] = FRIDAY
    site.status = 422
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["reasons"].get("unusable_candles", 0) >= 1 and out["updated"] == 0


async def test_an_incomplete_view_never_replaces_a_complete_one(world):
    store, settings, site, http, seen = world
    await seed(store, "TQW")
    site.ready = False
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["withheld"] == 1 and out["reasons"] == {"gap_in_candles": 1} and out["updated"] == 0
    _, rep, card = await row(store, "TQW")
    assert rep["technicalAssessment"]["status"] == "ready" and rep["technicalAssessment"]["asOf"] == "2026-10-16" and card["technicalBarDate"] == "2026-10-16"
    async with store.pool.acquire() as conn:      # but where the stored view was itself incomplete, the newer incomplete one is stored: it carries the reason
        await conn.execute("UPDATE prism_reports SET report = jsonb_set(report, '{technicalAssessment,status}', '\"incomplete\"') WHERE symbol = 'TQW'")
    await pt.refresh(store, settings, client=http, now=NOW, force=True)
    assert (await row(store, "TQW"))[1]["technicalAssessment"]["asOf"] == "2026-10-23"


async def test_the_refresh_gives_way_to_a_member_and_stops_on_its_time_limit(world, monkeypatch):
    store, settings, site, http, seen = world
    monkeypatch.setattr(prism, "RETRY_AFTER_BACKGROUND", 0.01)
    await seed(store, "TQM")
    await store.redis.set(prism.MEMBER_ACTIVE_KEY, "1", ex=60)
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["updated"] == 1 and out["paused_for_members"] >= 1
    await seed(store, "TQM2")
    timed = await pt.refresh(store, settings, client=http, now=NOW, max_minutes=0.0)
    assert timed["status"] == "partial" and timed["updated"] == 0


async def test_without_dhan_or_the_secret_nothing_runs(world, monkeypatch):
    store, settings, site, http, seen = world
    seen["reference"] = None
    out = await pt.refresh(store, settings, client=http, now=NOW)
    assert out["status"] == "skipped" and out["reason"] == "dhan_unavailable"
    assert (await pt.refresh(store, make_settings(), client=http, now=NOW))["reason"] == "site_api_url_not_set"


async def test_the_full_report_path_marks_the_card_with_its_bar_date(world):
    store, settings, site, http, seen = world
    await seed(store, "TQC", bar="2026-10-20")
    _, rep, card = await row(store, "TQC")
    assert card["technicalBarDate"] == "2026-10-20" and card["technicalAt"]
    assert prism.card_of(prism.reader_view(copy.deepcopy(SNAPSHOT)))["technicalBarDate"] == "2026-10-16"
    assert prism.card_of({"rating": {}})["technicalBarDate"] is None


# ----------------------------------------------------------------------------------------------- opening a page, the status page
class _App:
    def __init__(self, store, settings):
        from types import SimpleNamespace
        self.state = SimpleNamespace(store=store, settings=settings)


async def test_opening_a_stale_report_starts_one_background_refresh_per_company_and_half_hour(world, monkeypatch):
    store, settings, site, http, seen = world
    calls = []

    async def fake_refresh(app, symbol, now, target=None):
        calls.append(symbol)
        return pt.Outcome.UPDATED, "ok"
    monkeypatch.setattr(pt, "refresh_symbol", fake_refresh)
    app = _App(store, settings)
    stale = {"stale": True, "asOf": "2026-10-16"}
    assert await pt.refresh_on_open(app, "TQX", stale) is True
    assert await pt.refresh_on_open(app, "TQX", stale) is True                       # still refreshing (the page asks again), but never started twice
    await store.redis.set(pt.TRY_PREFIX + "TQX", str(__import__("time").time() - 400), ex=60)
    assert await pt.refresh_on_open(app, "TQX", stale) is False                      # started more than 150 s ago and rate limited for half an hour
    assert await pt.refresh_on_open(app, "TQY", {"stale": False}) is False           # current: nothing to do
    await pt.asyncio.sleep(0.05)
    assert calls == ["TQX"]
    await store.redis.set(pt.NONEW_PREFIX + "TQZ", "2026-10-16", ex=60)
    assert await pt.refresh_on_open(app, "TQZ", stale) is False                      # Dhan holds nothing newer for it
    await store.redis.set("prism:candles:down", "1", ex=60)
    assert await pt.refresh_on_open(app, "TQW2", stale) is False                     # Dhan was found down a moment ago
    await store.redis.delete("prism:candles:down")


async def test_the_latest_report_answer_carries_the_technical_date_and_refreshing_flag(world, monkeypatch):
    store, settings, site, http, seen = world
    from test_prism import make_app, client, member
    await seed(store, "TCS", bar="2026-10-16")
    started = []

    async def fake_open(app, symbol, state):
        started.append((symbol, state["asOf"], state["stale"]))
        return True
    monkeypatch.setattr(pt, "refresh_on_open", fake_open)
    monkeypatch.setattr(pt, "expected_session", lambda now: FRIDAY)
    app, fake = await make_app(store)
    async with app.router.lifespan_context(app):
        c = await member(app, plan="gold")
        full = (await c.get("/api/prism/reports/latest", params={"symbol": "TCS"})).json()
        summary = (await c.get("/api/prism/reports/latest", params={"symbol": "TCS", "view": "summary"})).json()["summary"]
    assert full["technical"] == {"asOf": "2026-10-16", "calculatedAt": full["technical"]["calculatedAt"], "stale": True, "refreshing": True}
    assert summary["technical"]["asOf"] == "2026-10-16" and summary["technical"]["refreshing"] is True
    assert started and started[0] == ("TCS", "2026-10-16", True)
    scores = (await c.get("/api/prism/scores", params={"symbols": "TCS"})).json()["scores"]["TCS"]
    assert scores["technicalAsOf"] == "2026-10-16" and scores["technicalAt"]


async def test_the_public_status_page_shows_the_dates_held_and_the_last_run(world):
    store, settings, site, http, seen = world
    from test_prism import make_app
    await seed(store, "TQP1", bar="2026-10-23")
    await seed(store, "TQP2", bar="2026-10-20")
    await seed(store, "TQP3", bar="2026-10-16")
    await pt.refresh(store, settings, client=http, now=NOW, symbols=["TQP3"])
    s = await pt.status_report(store, NOW)
    assert s["newestBarDate"] == "2026-10-23" and s["oldestBarDate"] == "2026-10-20" and s["behindNewestSession"] == 1 and s["upToDate"] == 2
    assert s["lastRun"]["status"] == "ok" and s["lastRun"]["updated"] == 1 and s["medianAgeDays"] == 0 and s["maxAgeDays"] == 3 and s["barDates"] == {"2026-10-23": 2, "2026-10-20": 1}
    assert "symbol" not in json.dumps(s).lower().replace("symbols", "")      # counts and dates only
    app, _ = await make_app(store)
    async with app.router.lifespan_context(app):
        anon = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        r = await anon.get("/api/technicals/status")
    assert r.status_code == 200 and r.json()["newestBarDate"] == "2026-10-23" and "max-age" in r.headers["cache-control"]


# ----------------------------------------------------------------------------------------------- scheduling (static)
def test_the_supervisor_and_cron_run_the_refresh_after_the_close_with_a_late_retry():
    from finlit.jobs.due import Ctx, JobState, evaluate
    from finlit.jobs.registry import by_name
    from jobs_fakes import ist
    job = by_name({})["technicals"]
    assert job.cls == "bulk" and job.args == ("refresh-technicals",) and job.sla.kind == "session" and job.probe == "technicals"
    assert {w.window for w in job.windows} == {"AFTER_CLOSE", "MORNING"}               # 18:30 after the close, and the 05:00 to 06:45 catch-up
    friday_close = ist(2026, 10, 30, 18, 45)
    stale = JobState(job="technicals", first_seen_at=friday_close - timedelta(days=9), last_success_at=friday_close - timedelta(hours=24))
    assert evaluate(job, stale, Ctx(now=friday_close)).due                              # the evening run
    late = JobState(job="technicals", first_seen_at=friday_close - timedelta(days=9), last_success_at=ist(2026, 10, 30, 19, 0), last_attempt_at=ist(2026, 10, 30, 19, 0))
    assert not evaluate(job, late, Ctx(now=ist(2026, 10, 30, 21, 10), probes={"technicals": False})).due
    assert evaluate(job, late, Ctx(now=ist(2026, 10, 30, 21, 10), probes={"technicals": True})).due   # the late retry: companies the first run could not reach
    assert evaluate(job, JobState(job="technicals", first_seen_at=friday_close - timedelta(days=9), last_success_at=ist(2026, 10, 29, 19, 0)), Ctx(now=ist(2026, 10, 31, 5, 30))).due   # the morning catch-up
    cron = (ROOT / "deploy/crontab").read_text()
    assert re.search(r"^30 18 \* \* 1-5\s+root \$W refresh-technicals", cron, re.M) and re.search(r"^15 21 \* \* 1-5\s+root \$W refresh-technicals", cron, re.M)
    worker = (ROOT / "backend/finlit/worker.py").read_text()
    assert '"refresh-technicals"' in worker and "prism_technical.refresh(" in worker


def test_the_refresh_waits_for_the_candles_to_be_final():
    """Both the report path and this job use the 16:00 IST rule; the job is scheduled two and a half hours later."""
    assert expected_session(datetime(2026, 10, 23, 15, 59, tzinfo=IST)) == date(2026, 10, 22)
    assert expected_session(datetime(2026, 10, 23, 18, 30, tzinfo=IST)) == date(2026, 10, 23)
    assert expected_session(datetime(2026, 10, 26, 6, 50, tzinfo=IST)) == date(2026, 10, 23)        # Monday morning: Friday's
    assert expected_session(datetime(2026, 10, 25, 12, 0, tzinfo=IST)) == date(2026, 10, 23)        # Sunday
