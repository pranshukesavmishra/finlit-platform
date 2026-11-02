"""Alert hygiene: the results buckets (waiting for the provider / gave up / ours to fix), provider pacing and backoff, per-symbol failure reasons, the canary's
false-alarm rules, and the supervisor's degraded state and alert messages. Synthetic data and a fake clock throughout."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from finlit import disclosure as d  # noqa: F401  (imported to prove the module loads with the new exit-code import)
from finlit import results as R
from finlit import results_light as L
from finlit import worker
from finlit.finedge import FinEdgeClient, FinEdgeError, backoff_delay, parse_retry_after
from finlit.jobs import canary, freshness as fr
from finlit.jobs.due import DEGRADED_RETRY_MIN, HELD_MAX_WAIT_MIN, JobState, effective_retry_at
from finlit.jobs.reasons import PARTIAL_EXIT, essential_ok, explain, failed_steps
from finlit.jobs.registry import Job, Sla
from finlit.jobs.state import MemoryState
from finlit.jobs.supervisor import Supervisor
from jobs_fakes import FakeClock, FakeNotifier, FakePause, FakeResources, FakeRunner, FakeSignals, config, ist
from test_integration import make_settings, store  # noqa: F401  (fixtures + helpers)
from test_jobs_freshness import facts
from test_results_light import DECL, E, QK, TODAY, provider, seeded, upto  # noqa: F401  (fixtures + helpers)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
D0 = date(2026, 11, 2)


def st(source, asked_h=None, latest=None):
    return {"source": source, "checkedAt": None if asked_h is None else NOW - timedelta(hours=asked_h), "providerLatest": latest, "mcap": 1.0, "quarter": "2026-09"}


# ------------------------------------------------------------------------------------------------ (1a) the results buckets
def test_a_company_the_provider_has_not_published_yet_is_information_not_an_alarm():
    v = L.bucket_of(st("provider", 2), D0 - timedelta(days=3), D0, NOW)
    assert v["bucket"] == L.WAITING and v["severity"] is None and "asked 2 h ago" in v["reason"]


def test_a_company_we_did_not_ask_in_time_is_ours_to_fix_and_a_day_old_one_is_stale_at_two_days():
    late = L.bucket_of(st("provider", 20), D0 - timedelta(days=1), D0, NOW)
    assert late["bucket"] == L.OURS and late["severity"] == "late" and "not asked for 20 h" in late["reason"]
    assert L.bucket_of(st("provider", 20), D0 - timedelta(days=3), D0, NOW)["severity"] == "stale"


def test_the_provider_having_the_quarter_while_we_did_not_fill_it_is_ours_to_fix():
    v = L.bucket_of(st("ours", 1, latest=date(2026, 9, 30)), D0 - timedelta(days=2), D0, NOW)
    assert v["bucket"] == L.OURS and v["severity"] == "stale" and "provider has data up to 2026-09-30" in v["reason"]


def test_declared_today_and_not_asked_yet_is_queued_but_yesterday_never_asked_is_ours():
    assert L.bucket_of(st("ours"), D0, D0, NOW)["bucket"] == L.QUEUED
    assert L.bucket_of(st("ours"), D0 - timedelta(days=1), D0, NOW)["bucket"] == L.OURS


def test_past_the_chase_window_a_company_is_gave_up_not_an_alarm_unless_the_daily_check_stopped():
    old = D0 - timedelta(days=8)
    v = L.bucket_of(st("provider", 5), old, D0, NOW)
    assert v["bucket"] == L.GAVE_UP and v["severity"] is None and "once a day" in v["reason"]
    assert L.bucket_of(st("ours"), old, D0, NOW)["bucket"] == L.GAVE_UP                       # never reached by the daily check yet: still not an alarm
    broken = L.bucket_of(st("provider", 60), old, D0, NOW)
    assert broken["bucket"] == L.OURS and broken["severity"] == "late" and "daily check has not asked for 60 h" in broken["reason"]


def test_filled_companies_are_filled():
    assert L.bucket_of(st("full"), D0, D0, NOW)["bucket"] == L.FILLED and L.bucket_of(st("light"), D0, D0, NOW)["bucket"] == L.FILLED


def summary(rows):
    recent = {s: ("2026-09", dcl) for s, (dcl, _) in rows.items()}
    return L.summarise_buckets(recent, {s: x for s, (_, x) in rows.items()}, D0, NOW)


def test_the_live_picture_323_waiting_105_for_two_days_is_green_when_none_is_ours():
    rows = {f"W{i}": (D0 - timedelta(days=3), st("provider", 2)) for i in range(105)}                  # 105 waiting since 2+ days, asked 2 hours ago
    rows.update({f"T{i}": (D0, st("provider", 1)) for i in range(218)})                              # 218 declared today, asked an hour ago
    rows.update({f"F{i}": (D0 - timedelta(days=1), st("light")) for i in range(623)})
    b = summary(rows)
    ds = fr.judge_results([], D0, 946, b)
    assert ds.status == "fresh" and ds.actual == "323 of 946 declared companies waiting for figures"
    assert b["waiting_for_provider"]["count"] == 323 and b["waiting_for_provider"]["oldest"] == "2026-10-30" and b["ours_to_fix"]["count"] == 0
    assert "Nothing for us to fix" in ds.detail and "waiting for the provider: 323" in ds.detail and "not an alarm" in ds.detail
    assert ds.buckets["waiting_for_provider"]["count"] == 323 and ds.buckets["gave_up"]["count"] == 0


def test_one_company_ours_to_fix_turns_the_dataset_stale_and_the_text_says_why():
    rows = {f"W{i}": (D0 - timedelta(days=3), st("provider", 2)) for i in range(5)}
    rows["BAD"] = (D0 - timedelta(days=3), st("ours", 1, latest=date(2026, 9, 30)))
    rows["LATE"] = (D0 - timedelta(days=1), st("provider", 30))
    ds = fr.judge_results([], D0, 7, summary(rows))
    assert ds.status == "stale" and ds.lag == 3
    assert ds.detail.startswith("FOR US TO FIX: 2 (oldest declaration 2026-10-30)") and "the provider has data up to" in ds.detail and "not asked for" in ds.detail
    assert ds.buckets["ours_to_fix"]["count"] == 2 and ds.buckets["oursSample"][0]["symbol"] == "BAD"


def test_yesterdays_one_is_only_late_and_gave_up_never_alarms():
    rows = {"LATE": (D0 - timedelta(days=1), st("provider", 30)), **{f"G{i}": (D0 - timedelta(days=9), st("provider", 6)) for i in range(40)}}
    ds = fr.judge_results([], D0, 41, summary(rows))
    assert ds.status == "late"
    rows.pop("LATE")
    ds = fr.judge_results([], D0, 40, summary(rows))
    assert ds.status == "fresh" and "gave up chasing every run: 40" in ds.detail and ds.buckets["gave_up"]["oldest"] == "2026-10-24"


def test_the_old_list_input_still_works_and_evaluate_facts_carries_the_buckets():
    assert fr.judge_results([FRI_MINUS(3)], D0, 5).status == "stale"                                      # the pre-bucket call shape
    f, now = facts(results_buckets=summary({"A": (D0, st("provider", 1))}), results_waiting=[])
    rep = fr.evaluate_facts(f, now, [], disk=40.0)
    res = [x for x in rep["datasets"] if x["key"] == "results"][0]
    assert res["status"] == "fresh" and res["buckets"]["waiting_for_provider"]["count"] == 1 and "detail" in res and "expected" in res      # old fields are all still there
    other = [x for x in rep["datasets"] if x["key"] == "quotes"][0]
    assert other["buckets"] is None


def FRI_MINUS(days):
    return D0 - timedelta(days=days)


# ------------------------------------------------------------------------------------------------ (1a) the low-rate chase
@pytest.mark.integration
async def test_past_four_days_a_company_is_asked_once_a_day_at_a_capped_rate(store, seeded):  # noqa: F811
    today = DECL + timedelta(days=6)
    assert len(await L.candidates(store, today)) == 5                                              # never asked: all of them, nothing is dropped
    assert len(await L.candidates(store, today, late_per_run=2)) == 2                              # the cap protects the provider's limits
    pending = {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)}
    async with store.pool.acquire() as conn:
        for sym in seeded:
            await L.save(conn, sym, QK, pending)
        assert await L.candidates(store, today) == []                                              # asked a moment ago
        await conn.execute("UPDATE quarter_light SET checked_at = now() - interval '30 hours' WHERE symbol IN ('AAA', 'BBB')")
    assert [c[0] for c in await L.candidates(store, today)] == ["AAA", "BBB"]                      # a day later: asked again, biggest first
    assert await L.candidates(store, DECL + timedelta(days=15)) == []                              # 14 days after the declaration the chase ends


@pytest.mark.integration
async def test_the_states_feed_the_buckets_from_a_real_database(store, seeded):  # noqa: F811
    async with store.pool.acquire() as conn:
        await L.save(conn, "AAA", QK, {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)})
    recent = await L.recent_declarations(store, TODAY, 14)
    b = L.summarise_buckets(recent, await L.states(store, recent), TODAY, datetime.now(timezone.utc))
    assert b["waiting_for_provider"]["count"] == 1 and b["filled"]["count"] == 1 and b["ours_to_fix"]["count"] == 4       # FULL is filled; BBB..EEE never asked, a day old
    assert (await L.bucket_facts(store, TODAY, datetime.now(timezone.utc)))["declared"] == 6


# ------------------------------------------------------------------------------------------------ (1b) pacing and backoff
async def _record_sleeps(monkeypatch):
    sleeps = []

    async def fake(s):
        sleeps.append(s)
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", fake)    # the same asyncio module everywhere: results_light's pauses are recorded too
    return sleeps


def test_retry_after_is_read_as_seconds_or_a_date_and_capped():
    assert parse_retry_after("5") == 5.0 and parse_retry_after("1000") == 120.0 and parse_retry_after(None) is None and parse_retry_after("soon") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


def test_backoff_is_exponential_with_jitter_and_honours_retry_after():
    for attempt in range(5):
        samples = [backoff_delay(attempt) for _ in range(30)]
        top = min(30.0, 0.5 * 2 ** attempt)
        assert all(top * 0.5 <= x <= top for x in samples) and len(set(samples)) > 1
    assert 7.0 <= backoff_delay(0, 7.0) <= 7.25


async def test_a_503_with_retry_after_waits_that_long_then_the_pace_recovers(monkeypatch):
    sleeps = await _record_sleeps(monkeypatch)
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(503, headers={"Retry-After": "3"}) if hits["n"] <= 2 else httpx.Response(200, json={"ok": True})

    async with FinEdgeClient(make_settings(), transport=httpx.MockTransport(handler)) as client:
        assert await client.get("/x") == {"ok": True}
        assert client.throttled == 2 and any(3.0 <= s <= 3.3 for s in sleeps)                     # the provider's own instruction was honoured
        assert client.pace > 0
        for _ in range(12):
            await client.get("/x")
        assert client.pace == 0.0                                                                  # every success shortens it until it is gone


async def test_after_a_throttle_calls_are_spaced_by_the_pace(monkeypatch):
    sleeps = await _record_sleeps(monkeypatch)
    client = FinEdgeClient(make_settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    client._clock = lambda: 100.0
    client.pace, client._next_at = 2.0, 0.0
    await client._wait_turn()
    await client._wait_turn()
    assert sleeps == [2.0]                                                                        # the first call goes at once (slot = now), the second waits `pace`
    await client.aclose()


async def test_a_503_that_never_clears_raises_a_throttled_error_with_the_retry_after(monkeypatch):
    await _record_sleeps(monkeypatch)
    async with FinEdgeClient(make_settings(), transport=httpx.MockTransport(lambda r: httpx.Response(503, headers={"Retry-After": "9"}, text="too many requests"))) as client:
        with pytest.raises(FinEdgeError) as e:
            await client.get("/x", retries=2)
    assert e.value.throttled and e.value.retry_after == 9.0 and e.value.status == 503


@pytest.mark.integration
async def test_503s_are_not_failures_do_not_stop_the_run_and_the_pause_recovers(store, seeded, monkeypatch):  # noqa: F811
    sleeps = await _record_sleeps(monkeypatch)
    monkeypatch.setattr(L, "MAX_IN_A_ROW", 1)                                                       # one real failure in a row would end the run
    calls: list = []
    books = {"AAA": {"c": 503}, "BBB": {"c": upto(20260630)}, "CCC": {"c": 503}, "DDD": {"c": upto(20260630)}, "EEE": {"c": upto(20260630)}}
    async with provider(books, calls) as client:
        out = await L.refresh_light(client, store, today=TODAY, pause=0.4)
    assert out["failed"] == 0 and out["throttled"] == 2 and out["filled"] == 3 and "stoppedEarly" not in out and out["deferred"] == ["AAA", "CCC"]
    assert 0.4 < out["pauseSeconds"] < 1.0                                                          # grew after the 503s, came back down after the successes
    assert max(sleeps) >= 0.8
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM quarter_light WHERE symbol IN ('AAA', 'CCC')") == 0     # nothing was recorded for them: they are first in line next run
    assert [c[0] for c in await L.candidates(store, TODAY)][:2] == ["AAA", "CCC"]


@pytest.mark.integration
async def test_a_provider_that_keeps_saying_too_many_requests_ends_the_run_politely_and_resumes(store, seeded, monkeypatch):  # noqa: F811
    await _record_sleeps(monkeypatch)
    monkeypatch.setattr(L, "MAX_THROTTLED_IN_A_ROW", 3)
    books = {s: {"c": 503} for s in seeded}
    async with provider(books, []) as client:
        out = await L.refresh_light(client, store, today=TODAY, pause=0)
    assert out["tried"] == 3 and out["throttled"] == 3 and out["failed"] == 0 and out["stoppedEarly"] and "too many requests" in out["stopReason"]
    books.update({s: {"c": upto(20260630)} for s in seeded})
    async with provider(books, []) as client:
        again = await L.refresh_light(client, store, today=TODAY, pause=0)
    assert again["filled"] == 5 and again["candidates"] == 5                                         # the next run starts where this one stopped


@pytest.mark.integration
async def test_real_failures_still_end_the_run_after_the_limit(store, seeded, monkeypatch):  # noqa: F811
    await _record_sleeps(monkeypatch)
    monkeypatch.setattr(L, "MAX_IN_A_ROW", 2)
    async with provider({s: {"c": 400} for s in seeded}, []) as client:
        out = await L.refresh_light(client, store, today=TODAY, pause=0)
    assert out["failed"] == 2 and out["stoppedEarly"] and "2 failures in a row" in out["stopReason"] and out["throttled"] == 0


# ------------------------------------------------------------------------------------------------ (1c) never silently drop a rebuild
def test_the_failure_reasons_read_plainly():
    rej = worker.result_failure_reason({"status": "rejected", "errors": {"quality": [{"key": "rev", "severity": "critical", "message": "revenue is ten times last year"}]}})
    assert rej == "rejected by the quality gate: revenue is ten times last year"
    assert worker.result_failure_reason({"status": "failed", "errors": {"error": "provider did not answer for quote"}}) == "provider did not answer for quote"
    assert worker.result_failure_reason({"status": "failed", "errors": {"error": "boom"}}) == "failed: boom"


@pytest.mark.integration
async def test_a_rejected_or_unanswered_rebuild_is_recorded_per_symbol_and_asked_again_on_the_next_run(store, monkeypatch):  # noqa: F811
    r = store.redis
    await r.delete("results:fail", "results:try:AAA", "results:try:BBB", "results:try:CCC")
    seen: list = []
    outcome = {"AAA": {"symbol": "AAA", "status": "rejected", "errors": {"quality": [{"key": "k", "severity": "critical", "message": "profit is not revenue minus costs"}]}},
               "BBB": {"symbol": "BBB", "status": "failed", "errors": {"error": "provider did not answer for quote"}},
               "CCC": {"symbol": "CCC", "status": "ok", "errors": {}}}

    async def cands(store_, with_dates=False):
        return [("AAA", DECL), ("BBB", DECL), ("CCC", DECL)]

    async def many(client, store_, items, **kw):
        seen.append([s for s, _ in items])
        return [outcome[s] for s, _ in items]
    monkeypatch.setattr(worker, "results_candidates", cands)
    monkeypatch.setattr(worker, "ingest_many", many)
    done = await worker.refresh_results(None, store)
    assert done["ok"] == 1 and done["failed"] == 2
    assert done["failedSymbols"] == {"AAA": "rejected by the quality gate: profit is not revenue minus costs", "BBB": "provider did not answer for quote"}
    assert await r.exists("results:try:AAA") == 0 and await r.exists("results:try:BBB") == 0 and await r.exists("results:try:CCC") == 1   # the failed two are not locked out
    status = await R.pipeline_status(store, TODAY)
    by = {x["symbol"]: x for x in status["failedSymbols"]}
    assert status["failedSymbolCount"] == 2 and by["AAA"]["status"] == "rejected" and "profit is not revenue" in by["AAA"]["reason"] and by["BBB"]["attempts"] == 1
    outcome["AAA"] = outcome["BBB"] = {"symbol": "x", "status": "ok", "errors": {}}
    outcome["AAA"], outcome["BBB"] = {**outcome["CCC"], "symbol": "AAA"}, {**outcome["CCC"], "symbol": "BBB"}
    await worker.refresh_results(None, store)
    assert seen[1] == ["AAA", "BBB"]                                                                # next run: the two failed ones, not CCC
    assert (await R.pipeline_status(store, TODAY))["failedSymbolCount"] == 0                        # filled in: the note is gone


@pytest.mark.integration
async def test_a_quality_gate_rejection_backs_off_to_the_normal_rhythm_after_six_tries(store):  # noqa: F811
    await store.redis.delete("results:fail", "results:try:ZZZ")
    for _ in range(worker.QUALITY_RETRIES):
        await store.redis.set("results:try:ZZZ", 1)
        await worker.note_result_failure(store, "ZZZ", "rejected", "rejected by the quality gate: x")
        assert await store.redis.exists("results:try:ZZZ") == 0
    await store.redis.set("results:try:ZZZ", 1)
    await worker.note_result_failure(store, "ZZZ", "rejected", "rejected by the quality gate: x")
    assert await store.redis.exists("results:try:ZZZ") == 1                                         # the 7th: back to the usual wait
    await worker.clear_result_failure(store, "ZZZ")
    await store.redis.delete("results:try:ZZZ")


# ------------------------------------------------------------------------------------------------ (2) the canary
def test_a_low_priced_stock_gets_a_two_tick_floor_but_a_large_cap_keeps_the_half_percent():
    assert canary.compare("LOW", "price", 10.00, 10.08, 0.005) is None                                # 0.8% apart, but 2 ticks of Re 0.05 is 1% of Rs 10
    assert canary.compare("RELIANCE", "price", 1400.0, 1409.0, 0.005) is not None                      # 0.64% on a large cap is real
    assert canary.tick_floor(24.58) == pytest.approx(0.0041, rel=0.01) and canary.tick_floor(None) == 0.0


def test_the_message_says_which_side_is_probably_right_and_when_each_figure_was_taken():
    m = canary.compare("TCS", "price", 4000.0, 4100.0, 0.005, ours_at="2026-10-30T15:29:00+05:30", provider_at="2026-10-30T14:00:00+05:30")
    assert m["probablyRight"] == "ours" and "ours is newer" in m["message"] and "30 Oct 15:29 IST" in m["message"] and "30 Oct 14:00 IST" in m["message"]
    m = canary.compare("TCS", "price", 4000.0, 4100.0, 0.005, ours_at="2026-10-30T14:00:00+05:30", provider_at="2026-10-30T15:29:00+05:30")
    assert m["probablyRight"] == "provider" and "provider's is newer" in m["message"]
    assert canary.compare("TCS", "price", 4000.0, 4100.0, 0.005)["probablyRight"] == "unknown"


def test_after_the_close_two_prices_from_different_moments_are_not_compared():
    skipped: list = []
    stored = {"price": 24.79, "priceAt": datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc), "marketOpen": False}                 # 15:30 IST
    fresh = {"price": 24.58, "asOf": "2026-10-30T13:10:00+05:30"}                                                                 # the provider's last trade, hours earlier
    assert canary.compare_company("FISCHER", stored, fresh, canary.TOL_CLOSED, skipped) == [] and "not compared" in skipped[0]
    fresh["asOf"] = "2026-10-30T15:25:00+05:30"                                                                                   # the same moment: now it is a real difference
    assert [m["field"] for m in canary.compare_company("FISCHER", stored, fresh, canary.TOL_CLOSED, skipped)] == ["price"]


def test_a_mismatch_needs_two_runs_in_a_row_and_a_stale_or_agreeing_previous_run_does_not_count():
    found = [{"symbol": "TCS", "field": "price", "message": "TCS price: x", "ours": 1, "provider": 2, "diffPercent": 50, "tolerancePercent": 0.5}]
    now = ist(2026, 10, 30, 17, 0)
    confirmed, watching = canary.confirm(found, None, now)
    assert confirmed == [] and watching[0]["runs"] == 1 and watching[0]["firstSeenAt"] == now.isoformat(timespec="seconds")
    first = canary.summarise(["TCS"], confirmed, [], now, watching)
    assert first["ok"] is True and first["watching"][0]["symbol"] == "TCS"
    confirmed, watching = canary.confirm(found, first, now + timedelta(hours=12))
    assert watching == [] and confirmed[0]["runs"] == 2 and "two runs in a row" in confirmed[0]["message"] and confirmed[0]["firstSeenAt"] == now.isoformat(timespec="seconds")
    assert canary.confirm(found, first, now + timedelta(days=3))[0] == []                              # the earlier sighting is too old to count
    assert canary.confirm([], first, now + timedelta(hours=12)) == ([], [])                            # it agrees again: dropped
    again = canary.summarise(["TCS"], confirmed, [], now, [])
    assert again["ok"] is False and canary.alert_text(again).startswith("TCS price: x - the same on two runs")


@pytest.mark.integration
async def test_only_liquid_large_companies_are_checked(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM listing_quotes")
        for sym, cap in (("FISCHER", 900.0), ("NEWIPO", 3000.0), ("BIGCO", 80000.0), ("HUGECO", 250000.0)):
            await conn.execute("INSERT INTO listing_quotes (symbol, price, market_cap) VALUES ($1, 10, $2)", sym, cap)
        picked = await canary.pick_symbols(conn, date(2026, 10, 30))
        assert picked[:4] == list(canary.CORE) and len(picked) == 5 and picked[4] in ("BIGCO", "HUGECO")
        await conn.execute("DELETE FROM listing_quotes WHERE market_cap >= 50000")
        assert await canary.pick_symbols(conn, date(2026, 10, 30)) == list(canary.CORE)                  # a thin stock is never the reference
        await conn.execute("DELETE FROM listing_quotes")


# ------------------------------------------------------------------------------------------------ (3) the supervisor
NOON = ist(2026, 10, 30, 12, 0)


def job(name="facts", **kw):
    kw.setdefault("max_runtime_min", 60)
    return Job(name, (name,), cls="light", priority=10, weight_mb=60, sla=Sla("hours", 30), **kw)


def make(jobs, run_detail=None, notifier=None):
    clock = FakeClock(NOON)
    sup = Supervisor(jobs=jobs, state=MemoryState(), runner=FakeRunner(clock), resources=FakeResources(900), signals=FakeSignals(), pause=FakePause(), clock=clock,
                     config=config(), env={}, notifier=notifier, run_detail=run_detail)
    return sup, clock


def record(clock, status="partial", **steps):
    return {"status": status, "at": clock.now().isoformat(), **steps}


FACTS = {"master": {"status": "ok", "schemes": 8000}, "ter": {"status": "failed", "why": "ConnectTimeout: "}, "aum": {"status": "failed", "why": "ConnectTimeout: "}}


def test_the_reason_of_a_run_is_read_from_its_stored_steps():
    assert failed_steps({"status": "partial", **FACTS}) == {"ter": "ConnectTimeout", "aum": "ConnectTimeout"}
    text = explain({"status": "partial", **FACTS})
    assert "ter step failed: ConnectTimeout" in text and "aum step failed: ConnectTimeout" in text and "master" not in text
    assert explain({"status": "failed", "error": "database unreachable"}) == "database unreachable" and explain({"status": "ok"}) is None and explain(None) is None
    assert essential_ok({"master": {"status": "ok"}}) and not essential_ok({"master": {"status": "failed"}}) and not essential_ok({})


async def test_partial_with_the_essential_step_ok_is_degraded_with_its_own_message_not_a_failure():
    box = {}

    async def detail(cmd):
        return box["rec"]
    notifier = FakeNotifier()
    sup, clock = make([job()], detail, notifier)
    box["rec"] = record(clock, **FACTS)
    await sup.step()
    sup.runner.of("facts").finish(PARTIAL_EXIT)                       # the worker's exit code for 'master ok, TER and AUM failed'
    await sup.poll()
    s = (await sup.state.load_all())["facts"]
    assert s.state == "degraded" and s.last_status == "partial" and s.consecutive_failures == 0 and s.held_until is None and s.last_success_at == clock.now()
    assert "ter step failed: ConnectTimeout" in s.state_reason and "aum step failed: ConnectTimeout" in s.state_reason
    assert sup.state.runs[0]["status"] == "partial" and sup.state.runs[0]["counts"]["steps"] == {"ter": "ConnectTimeout", "aum": "ConnectTimeout"}
    assert s.retry_at == clock.now() + timedelta(minutes=DEGRADED_RETRY_MIN)
    plan = await sup.plan()
    assert plan.verdicts["facts"].state == "degraded" and "degraded:" in plan.verdicts["facts"].reason
    assert await sup.check_alerts(plan, clock.now()) == []             # a degraded job is not a failing one
    clock.advance(minutes=DEGRADED_RETRY_MIN, seconds=5)
    await sup.step()
    assert sup.runner.started.count("facts") == 2                      # and it is tried again, without waiting for the next window


async def test_a_nonzero_exit_whose_stored_result_says_partial_is_also_degraded():
    async def detail(cmd):
        return record(clock, **FACTS)
    sup, clock = make([job()], detail)
    await sup.step()
    sup.runner.of("facts").finish(1)
    await sup.poll()
    s = (await sup.state.load_all())["facts"]
    assert s.state == "degraded" and s.consecutive_failures == 0


async def test_an_old_stored_result_is_not_used_to_explain_this_run():
    async def detail(cmd):
        return {"status": "partial", "at": (clock.now() - timedelta(days=1)).isoformat(), **FACTS}
    sup, clock = make([job()], detail)
    await sup.step()
    sup.runner.of("facts").finish(1, "Traceback: boom")
    await sup.poll()
    s = (await sup.state.load_all())["facts"]
    assert s.state == "waiting" and s.consecutive_failures == 1 and "boom" in s.state_reason


async def test_the_failing_alert_carries_the_reason_from_the_stored_result_and_ends_with_the_next_success():
    notifier = FakeNotifier()

    async def detail(cmd):
        return record(clock, "failed", error="the AMFI scheme master is unreachable (ConnectTimeout)")
    sup, clock = make([job()], detail, notifier)
    for _ in range(3):
        await sup.step()
        sup.runner.of("facts").finish(1)
        await sup.poll()
        clock.advance(hours=2, seconds=5)
    plan = await sup.plan()
    sent = await sup.check_alerts(plan, clock.now())
    body = [b for k, _, b in notifier.sent if k == "failing:facts"][0]
    assert "failing:facts" in sent and "failed 3 times in a row" in body and "Why: exit code 1: the AMFI scheme master is unreachable (ConnectTimeout)" in body
    assert "the alert ends when a run succeeds" in body
    await sup.step()
    sup.runner.of("facts").finish(0)
    await sup.poll()
    s = (await sup.state.load_all())["facts"]
    assert s.consecutive_failures == 0 and "failing:facts" in notifier.cleared and "overdue:facts" in notifier.cleared
    assert "facts" not in [j for j in (await sup.plan()).states if (await sup.plan()).states[j].consecutive_failures >= 3]


async def test_a_held_job_is_retried_at_least_every_three_hours_whatever_retry_time_is_stored():
    sup, clock = make([job()])
    await sup.state.save(JobState(job="facts", first_seen_at=NOON - timedelta(days=9), last_success_at=NOON - timedelta(days=5), last_attempt_at=NOON - timedelta(hours=4),
                                  last_status="failed", consecutive_failures=21, retry_at=NOON + timedelta(days=2), held_until=NOON + timedelta(days=2)))     # an old rule left it waiting for days
    s = (await sup.state.load_all())["facts"]
    assert effective_retry_at(s) == NOON - timedelta(hours=4) + timedelta(minutes=HELD_MAX_WAIT_MIN) and HELD_MAX_WAIT_MIN <= 180
    await sup.step()
    assert sup.runner.started == ["facts"]                             # past the 3-hour cap: it runs now, held or not


async def test_a_true_hold_after_repeated_total_failures_is_kept():
    sup, clock = make([job(max_attempts=3)])
    for _ in range(3):
        await sup.step()
        sup.runner.of("facts").finish(1)
        await sup.poll()
        clock.advance(hours=2, seconds=5)
    s = (await sup.state.load_all())["facts"]
    assert s.consecutive_failures == 3 and s.held_until is not None and s.state == "held" and s.retry_at - s.last_attempt_at <= timedelta(hours=3)


async def test_the_overdue_alert_also_says_why():
    notifier = FakeNotifier()

    async def detail(cmd):
        return record(clock, "failed", error="provider key refused")
    sup, clock = make([job(windows=())], detail, notifier)
    await sup.step()
    sup.runner.of("facts").finish(1)
    await sup.poll()
    s = (await sup.state.load_all())["facts"]
    s.last_success_at, s.retry_at = clock.now() - timedelta(hours=60), clock.now() + timedelta(days=1)
    await sup.state.save(s)
    sent = await sup.check_alerts(await sup.plan(), clock.now())
    assert "overdue:facts" in sent and "Why: exit code 1: provider key refused" in [b for k, _, b in notifier.sent if k == "overdue:facts"][0]


# ------------------------------------------------------------------------------------------------ facts
def test_the_facts_command_exits_with_the_degraded_code_when_only_the_optional_steps_failed():
    import inspect
    src = inspect.getsource(worker.main)
    assert "PARTIAL_EXIT if result[\"status\"] == \"partial\" and essential_ok(result)" in src
    assert PARTIAL_EXIT not in (0, 1, 2)


@pytest.mark.integration
async def test_a_partial_facts_run_names_each_failed_step_and_the_date_of_the_figures_still_served(store, monkeypatch):  # noqa: F811
    async def ok_master(store_, client, **kw):
        return {"status": "ok", "schemes": 1}

    async def bad(store_, client, *a, **kw):
        raise httpx.ConnectTimeout("")
    monkeypatch.setattr(d, "step_master", ok_master)
    monkeypatch.setattr(d, "step_ter", bad)
    monkeypatch.setattr(d, "step_aum", bad)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_ter")
        await conn.execute("INSERT INTO mf_ter (name_key, name, category, ter_regular, ter_direct, ter_date) VALUES ('k', 'n', 'c', 1.0, 0.5, '2026-09-30')")

    class C:
        async def aclose(self):
            return None
    res = await d.refresh(store, client=C(), today=date(2026, 11, 2))
    assert res["status"] == "partial" and res["master"]["status"] == "ok" and res["ter"]["status"] == "failed" and res["aum"]["status"] == "failed"
    assert res["ter"]["why"].startswith("ConnectTimeout") and res["ter"]["serving"] == "the last good figures, dated 2026-09-30" and res["ter"]["servingDate"] == "2026-09-30"
    assert essential_ok(res)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_ter") == 1                                  # the last good figures were not touched
        await conn.execute("DELETE FROM mf_ter")


async def test_the_status_lists_a_degraded_job_apart_from_the_failing_ones():
    from finlit.jobs.status import job_row
    s = JobState(job="facts", state="degraded", state_reason="ter step failed: ConnectTimeout", last_status="partial")
    row = job_row(job(), s, NOON, {}, False)
    assert row["state"] == "degraded" and row["reason"] == "ter step failed: ConnectTimeout" and row["consecutiveFailures"] == 0 and row["held"] is False

