"""Results throughput: every run is bounded by a time budget and continues where it stopped, nobody starves, a slow or throttled provider cannot hold a run,
the daily chase really runs, and a simulated results-season day clears 1,300 declarations. Plus the canary's last-close comparison (same session only)."""

import asyncio
import random
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from finlit import results as R
from finlit import results_light as L
from finlit import results_run, worker
from finlit.finedge import FinEdgeClient, FinEdgeError
from finlit.jobs import canary
from test_integration import make_settings, store  # noqa: F401  (fixtures + helpers)
from test_results_light import ALL, QK, upto

IST = ZoneInfo("Asia/Kolkata")
READY, BEHIND = upto(20260630), upto(20260331)


class FakeClock:
    """A clock the test moves: asyncio.sleep and the fake provider advance it, so a whole day runs in seconds."""
    def __init__(self, start: datetime):
        self.start, self.t = start, 0.0

    def __call__(self) -> float:
        return self.t

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.t)

    async def sleep(self, s: float) -> None:
        self.t += s
        await _real_sleep(0)


_real_sleep = asyncio.sleep


# ------------------------------------------------------------------------------------------------ the canary: same session or not at all
def test_a_close_from_another_session_is_reported_as_not_comparable_never_watching():
    """HDFCBANK: ours 690.0 (a bar of 30 Oct) against the provider's 699.5 (02 Nov 15:59) was a 1.36% 'mismatch' of two different sessions."""
    skipped: list = []
    stored = {"price": 700.0, "marketCap": 1.0, "close": 690.0, "closeDay": date(2026, 10, 30), "closeAt": datetime(2026, 10, 30, 11, 0, tzinfo=timezone.utc), "marketOpen": False}
    fresh = {"price": 699.5, "asOf": "2026-11-02T15:59:00+05:30"}
    found = canary.compare_company("HDFCBANK", stored, fresh, canary.TOL_CLOSED, skipped)
    assert [m["field"] for m in found if m["field"] == "lastClose"] == []
    assert skipped == ["HDFCBANK last close not comparable: ours is from 30 Oct, the provider's from 02 Nov"]
    confirmed, watching = canary.confirm([m for m in found if m["field"] == "lastClose"], None, datetime(2026, 11, 2, 14, 12, tzinfo=timezone.utc))
    assert confirmed == [] and watching == []


def test_a_close_is_compared_only_for_the_same_finished_session():
    day = date(2026, 11, 2)
    after = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)                       # 16:30 IST
    base = {"price": 1.0, "marketCap": 1.0, "close": 690.0, "closeDay": day, "closeAt": after, "marketOpen": False}
    def lastclose(stored, asof):
        return [m for m in canary.compare_company("HDFCBANK", stored, {"price": 699.5, "asOf": asof}, canary.TOL_CLOSED, []) if m["field"] == "lastClose"]
    assert len(lastclose(base, "2026-11-02T15:59:00+05:30")) == 1                   # same session, both after the close: a real difference
    assert lastclose({**base, "close": 699.5}, "2026-11-02T15:59:00+05:30") == []   # and agreement stays silent
    assert lastclose(base, "2026-11-02T13:10:00+05:30") == []                       # the provider's quote is from mid-session: not the close
    assert lastclose({**base, "closeAt": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)}, "2026-11-02T15:59:00+05:30") == []   # ours was stored at 13:30 IST, before the close
    assert lastclose({**base, "closeDay": None}, "2026-11-02T15:59:00+05:30") == [] and lastclose(base, None) == []   # an unknown date is never compared
    why = canary.close_not_comparable({**base, "closeAt": datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)}, "2026-11-02T15:59:00+05:30")
    assert "ours was stored 02 Nov 13:30 IST, before the 02 Nov close" in why


@pytest.mark.integration
async def test_the_stored_view_carries_the_day_and_time_of_our_close(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM price_daily WHERE symbol = 'ZZCAN'")
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'ZZCAN'")
        await conn.execute("INSERT INTO price_daily (symbol, day, open, high, low, close, volume) VALUES ('ZZCAN', '2026-10-30', 1, 1, 1, 690, 1)")
        await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ('ZZCAN', 'consolidated', 'summary', '{}', 'e', '2026-10-30T11:00:00Z')")
        view = await canary.stored_view(conn, "ZZCAN", datetime(2026, 11, 2, 14, 12, tzinfo=timezone.utc))
        await conn.execute("DELETE FROM price_daily WHERE symbol = 'ZZCAN'")
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'ZZCAN'")
    assert view["closeDay"] == date(2026, 10, 30) and view["closeAt"] == datetime(2026, 10, 30, 11, 0, tzinfo=timezone.utc) and view["close"] == 690.0


# ------------------------------------------------------------------------------------------------ one call never holds the run
async def test_a_retry_after_longer_than_the_wait_cap_is_not_waited_for(monkeypatch):
    slept: list = []

    async def fake(s):
        slept.append(s)
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", fake)
    async with FinEdgeClient(make_settings(), transport=httpx.MockTransport(lambda r: httpx.Response(503, headers={"Retry-After": "90"}))) as client:
        client.pace_max = 2.0
        with pytest.raises(FinEdgeError) as e:
            await client.get("/x", retries=3, max_wait=3.0)
        assert e.value.throttled and slept == [] and client.calls == 1                         # skipped at once, not 90 s x 3
        assert client.pace <= 2.0 and client._next_at - client._clock() <= 2.1                 # and the shared pace did not hold every other call for 90 s either


class _Book:
    """A provider fake at the client level: each symbol answers with `kind`: ok / behind / 503 / slow (never answers within the call timeout)."""
    def __init__(self, clock: FakeClock, kinds=None, latency=0.8):
        self.clock, self.kinds, self.latency, self.calls = clock, kinds or {}, latency, []

    def kind(self, sym: str) -> str:
        return self.kinds.get(sym, "ok")

    async def get(self, path, params=None, timeout=10, retries=3, low=False, max_wait=None):
        sym = path.rsplit("/", 1)[-1]
        kind = self.kind(sym)
        self.calls.append((sym, params.get("statement_type")))
        if kind == "slow":
            self.clock.t += results_run.CALL_TIMEOUT_S
            raise asyncio.TimeoutError()
        self.clock.t += self.latency
        if kind == "503":
            raise FinEdgeError(path, 503, "busy")
        return READY if kind == "ok" else BEHIND


@pytest.fixture
async def small(store, monkeypatch):  # noqa: F811
    """Six declared companies of known size; the day is 21 Jul 2026 (declared 20 Jul)."""
    syms = {"AAA": 9000.0, "BBB": 7000.0, "CCC": 5000.0, "DDD": 3000.0, "EEE": 1000.0, "FFF": 100.0}
    decls = {QK: {s: R.Decl(date(2026, 7, 20), True, s) for s in syms}}

    async def fake(store_, force=False):
        return decls
    monkeypatch.setattr(R, "get_declarations", fake)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol = ANY($1::text[])", list(syms))
        for s, mc in syms.items():
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2)", s, mc)
    R.reset()
    yield syms
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol = ANY($1::text[])", list(syms))
    R.reset()


TODAY = date(2026, 7, 21)


@pytest.mark.integration
async def test_a_call_that_never_answers_is_cut_at_the_call_timeout_and_the_run_goes_on(store, small, monkeypatch):  # noqa: F811
    class Hangs:
        calls = 0

        async def get(self, path, params=None, timeout=10, retries=3, low=False, max_wait=None):
            Hangs.calls += 1
            if path.endswith("/AAA"):
                await asyncio.sleep(60)
            return READY
    monkeypatch.setattr(L, "CALL_TIMEOUT_S", 0.05)
    out = await L.refresh_light(Hangs(), store, today=TODAY, pause=0)
    assert out["timedOut"] == 1 and out["failed"] == 1 and out["filled"] == 5 and out["errors"] == {"no answer within 0.05 s": 1}
    again = await L.refresh_light(Hangs(), store, today=TODAY, pause=0)
    assert again["tried"] == 1                                                                    # AAA, still unsaved, is the first (and only) one asked again


@pytest.mark.integration
async def test_the_run_stops_at_its_time_budget_records_where_and_the_next_run_continues(store, small, monkeypatch):  # noqa: F811
    clock = FakeClock(datetime(2026, 7, 21, 9, 0, tzinfo=IST))
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", clock.sleep)
    book = _Book(clock, latency=60.0)                                                              # a slow provider: a minute per company
    out = await L.refresh_light(book, store, today=TODAY, pause=0, max_minutes=3, clock=clock, now_fn=clock.now)
    assert out["tried"] == 3 and out["stoppedBy"] == "budget" and out["stoppedEarly"] and "time budget of 3 minutes" in out["stopReason"] and out["left"] == 3
    assert out["durationSeconds"] <= 3 * 60 + 60                                                    # never more than one call past the budget
    note = await results_run.read_progress(store.redis, "refresh-results-light")
    assert note["state"] == "partial" and note["done"] == 3
    clock2 = FakeClock(datetime(2026, 7, 21, 9, 30, tzinfo=IST))
    nxt = await L.refresh_light(_Book(clock2, latency=1.0), store, today=TODAY, pause=0, clock=clock2, now_fn=clock2.now)
    assert nxt["filled"] == 3 and nxt["left"] == 0 and [c[0] for c in book.calls] == ["AAA", "BBB", "CCC"]   # nobody was asked twice, nobody skipped


@pytest.mark.integration
async def test_the_run_ends_politely_when_the_supervisor_asks_it_to_stop(store, small, monkeypatch):  # noqa: F811
    class StopsAfterTwo(_Book):
        async def get(self, *a, **kw):
            got = await super().get(*a, **kw)
            if len(self.calls) == 2:
                results_run.Stop.requested, results_run.Stop.signal_name = True, "SIGTERM"
            return got
    results_run.Stop.reset()
    try:
        clock = FakeClock(datetime(2026, 7, 21, 9, 0, tzinfo=IST))
        out = await L.refresh_light(StopsAfterTwo(clock), store, today=TODAY, pause=0, clock=clock, now_fn=clock.now)
    finally:
        results_run.Stop.reset()
    assert out["tried"] == 2 and out["stoppedBy"] == "signal" and "told to stop (SIGTERM)" in out["stopReason"] and out["left"] == 4


@pytest.mark.integration
async def test_a_throttled_company_is_skipped_not_waited_for_and_the_pause_stays_under_its_cap(store, small, monkeypatch):  # noqa: F811
    clock = FakeClock(datetime(2026, 7, 21, 9, 0, tzinfo=IST))
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", clock.sleep)
    book = _Book(clock, {s: "503" for s in small})
    monkeypatch.setattr(L, "MAX_THROTTLED_IN_A_ROW", 99)
    out = await L.refresh_light(book, store, today=TODAY, pause=0.4, clock=clock, now_fn=clock.now)
    assert out["throttled"] == 6 and out["failed"] == 0 and out["pauseSeconds"] == L.PAUSE_MAX and out["durationSeconds"] <= 6 * (L.PAUSE_MAX + 1)


# ------------------------------------------------------------------------------------------------ fair order, reserved daily chase
@pytest.mark.integration
async def test_nobody_starves_never_asked_first_then_the_longest_unasked_then_the_bigger(store, small):  # noqa: F811
    pending = {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)}
    now = datetime.now().astimezone()
    async with store.pool.acquire() as conn:
        await L.save(conn, "AAA", QK, pending, at=now - timedelta(hours=1))      # the biggest, asked an hour ago
        await L.save(conn, "BBB", QK, pending, at=now - timedelta(hours=10))
        await L.save(conn, "CCC", QK, pending, at=now - timedelta(hours=9))      # same 3 h band as BBB: the bigger one (BBB) first
        await L.save(conn, "DDD", QK, pending, at=now - timedelta(hours=4))
    order = [c[0] for c in await L.candidates(store, TODAY, recheck_minutes=10)]
    assert order == ["EEE", "FFF", "BBB", "CCC", "DDD", "AAA"]                   # never asked (bigger first), then the oldest band, ... AAA (big but recently asked) last


@pytest.mark.integration
async def test_the_daily_chase_has_reserved_places_even_when_the_declared_lately_group_fills_the_run(store, small, monkeypatch):  # noqa: F811
    decls = {QK: {**{f"N{i:03d}": R.Decl(date(2026, 7, 20), True, "n") for i in range(40)}, **{f"L{i:02d}": R.Decl(date(2026, 7, 10), True, "l") for i in range(10)}}}

    async def fake(store_, force=False):
        return decls
    monkeypatch.setattr(R, "get_declarations", fake)
    got, due = await L.plan(store, TODAY, limit=20, late_per_run=5)
    names = [s for s, _ in got]
    assert len(got) == 20 and sum(n.startswith("L") for n in names) == 5 and due == 50       # 15 declared lately + 5 of the daily chase, not 20 + 0
    got, _ = await L.plan(store, TODAY, limit=100, late_per_run=5)
    assert len(got) == 50                                                                      # the unused places are not wasted


# ------------------------------------------------------------------------------------------------ the full rebuild job: same rules
@pytest.mark.integration
async def test_refresh_results_stops_at_its_budget_and_does_not_lock_out_companies_it_never_reached(store, monkeypatch):  # noqa: F811
    r = store.redis
    syms = [f"R{i}" for i in range(9)]
    await r.delete("results:fail", "results:asked", *[f"results:try:{s}" for s in syms])
    clock = FakeClock(datetime(2026, 7, 21, 9, 0, tzinfo=IST))
    seen: list = []

    async def cands(store_, with_dates=False):
        return [(s, date(2026, 7, 20)) for s in syms]

    async def many(client, store_, items, **kw):
        seen.append([s for s, _ in items])
        clock.t += 300                                                                       # five minutes per batch of three
        return [{"symbol": s, "status": "ok", "errors": {}} for s, _ in items]
    monkeypatch.setattr(worker, "results_candidates", cands)
    monkeypatch.setattr(worker, "ingest_many", many)
    done = await worker.refresh_results(None, store, max_minutes=10, clock=clock)
    assert done["tried"] == 6 and done["stoppedBy"] == "budget" and done["left"] == 3 and seen == [syms[:3], syms[3:6]]
    assert [await r.exists(f"results:try:{s}") for s in syms] == [1] * 6 + [0] * 3         # the three it never reached are NOT locked out
    done = await worker.refresh_results(None, store, max_minutes=10, clock=clock)
    assert seen[2] == syms[6:9] and done["left"] == 0                                        # the next run starts with exactly those (never asked first)
    note = await results_run.read_progress(r, "refresh-results")
    assert note["state"] == "done"


@pytest.mark.integration
async def test_a_batch_that_never_answers_is_cut_and_recorded_per_symbol(store, monkeypatch):  # noqa: F811
    r = store.redis
    await r.delete("results:fail", "results:asked", "results:try:T1", "results:try:T2")

    async def cands(store_, with_dates=False):
        return [("T1", date(2026, 7, 20)), ("T2", date(2026, 7, 20))]

    async def hangs(client, store_, items, **kw):
        await asyncio.sleep(60)
    monkeypatch.setattr(worker, "results_candidates", cands)
    monkeypatch.setattr(worker, "ingest_many", hangs)
    monkeypatch.setattr(results_run, "COMPANY_TIMEOUT_S", 0.05)
    done = await worker.refresh_results(None, store)
    assert done["timedOut"] == 2 and done["failed"] == 2 and "did not answer within" in done["failedSymbols"]["T1"]
    assert await r.exists("results:try:T1") == 0                                              # asked again on the next run
    await r.delete("results:fail", "results:asked")


@pytest.mark.integration
async def test_a_killed_run_shows_its_last_symbol_and_step_at_the_status_page(store):  # noqa: F811
    p = results_run.Progress(store.redis, "refresh-results", 960, planned=40)
    await p.step("MODIS", "rebuilding MODIS, X, Y from the provider", done=12)
    note = await results_run.read_progress(store.redis, "refresh-results", now=p.note["updatedAt"] + 30)
    assert note["state"] == "running" and "interrupted" not in note                           # still alive
    note = await results_run.read_progress(store.redis, "refresh-results", now=p.note["updatedAt"] + 600)
    assert note["state"] == "killed" and "last step was 'rebuilding MODIS, X, Y from the provider' on MODIS, 12 of 40 companies done" in note["interrupted"]
    p.clock = lambda: __import__("time").time() - 600                                           # a note last written ten minutes ago
    await p.step("MODIS", "rebuilding MODIS, X, Y from the provider", done=12)
    status = await R.pipeline_status(store, TODAY)
    assert status["progress"]["results"]["state"] == "killed" and "MODIS" in status["progress"]["results"]["interrupted"]
    assert status["throughput"]["resultsLight"]["companiesPerRun"] == L.PER_RUN and status["throughput"]["results"]["companiesPerRun"] == worker.RESULTS_PER_RUN
    await store.redis.delete("results:progress:refresh-results")


def test_the_budget_is_eighty_percent_of_the_jobs_limit_and_the_caps_fit_it():
    assert results_run.budget_minutes("results", 0) == 16.0 and results_run.budget_minutes("results-light", 0) == 24.0
    assert L.BUDGET_FALLBACK_MIN == 24.0 and worker.RESULTS_BUDGET_FALLBACK_MIN == 16.0
    from finlit.jobs.registry import by_name
    jobs = by_name()
    assert jobs["results"].resumable and jobs["results-light"].resumable                      # a hard kill would be a yield, not three failures in a row
    worst_light = L.PER_RUN * (L.PAUSE_MAX + 1.0)                                              # every call throttled-paced at the cap, one second each
    assert worst_light / 60 <= jobs["results-light"].max_runtime_min * 1.0 + 1               # even then the budget (not the kill) ends the run
    assert L.PER_RUN * 16 >= 1300 * 3                                                          # a day's runs cover a 1,300-declaration day several times over


# ------------------------------------------------------------------------------------------------ a results-season day, simulated
class _SimProvider:
    """Publishes each company's quarter at its own time; answers 503 at random and during a storm; some calls hang (slow); a slow patch makes every call 20 s."""
    def __init__(self, clock: FakeClock, publish: dict, rng: random.Random):
        self.clock, self.publish, self.rng = clock, publish, rng
        self.storms: list = []      # (from, to) sim datetimes where every call is a 503
        self.slow: list = []        # (from, to) sim datetimes where every call takes 20 s
        self.calls = self.n503 = self.nslow = 0

    async def get(self, path, params=None, timeout=10, retries=3, low=False, max_wait=None):
        sym, now = path.rsplit("/", 1)[-1], self.clock.now()
        self.calls += 1
        if any(a <= now < b for a, b in self.storms) or self.rng.random() < 0.08:
            self.clock.t += 0.5
            self.n503 += 1
            raise FinEdgeError(path, 503, "busy")
        if self.rng.random() < 0.02:
            self.clock.t += results_run.CALL_TIMEOUT_S
            self.nslow += 1
            raise asyncio.TimeoutError()
        self.clock.t += 20.0 if any(a <= now < b for a, b in self.slow) else 0.8
        return READY if self.publish.get(sym) is not None and self.publish[sym] <= self.clock.now() else BEHIND


@pytest.mark.integration
async def test_a_results_season_day_with_1300_declarations_clears_and_nobody_is_left_unasked(store, monkeypatch):  # noqa: F811
    rng = random.Random(7)
    day0 = datetime(2026, 7, 21, 8, 0, tzinfo=IST)
    n = 1300
    syms = [f"S{i:04d}" for i in range(n)]
    # declared over the last 12 days (about 108 a day, the busiest ones the most recent), the provider publishes 1-60 h after the declaration
    declared = {s: (day0 - timedelta(days=min(11, int(rng.expovariate(0.45))))).date() for s in syms}
    publish = {s: datetime.combine(declared[s], dtime(18, 0), IST) + timedelta(hours=rng.uniform(1, 60)) for s in syms}
    decls = {QK: {s: R.Decl(declared[s], True, s) for s in syms}}

    async def fake(store_, force=False):
        return decls
    monkeypatch.setattr(R, "get_declarations", fake)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol LIKE 'S0%' OR symbol LIKE 'S1%'")
        await conn.executemany("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2)", [(s, float(rng.randint(10, 500000))) for s in syms])
    R.reset()

    clock = FakeClock(day0)
    monkeypatch.setattr("finlit.finedge.asyncio.sleep", clock.sleep)
    provider = _SimProvider(clock, publish, rng)
    provider.storms = [(day0 + timedelta(hours=3), day0 + timedelta(hours=4, minutes=30))]                       # 11:00-12:30 on the first day, every call is a 503
    provider.slow = [(day0 + timedelta(days=1, hours=2), day0 + timedelta(days=1, hours=4))]                     # next day 10:00-12:00 every call takes 20 s
    runs, worst_hours = [], {}
    stops = {"budget": 0, "throttled": 0}
    for day in range(3):
        start = day0 + timedelta(days=day)
        t = start
        while t < start + timedelta(hours=15):                                                                    # 08:00 .. 23:00 IST, a run every 55 minutes
            clock.start, clock.t = t, 0.0
            today = t.astimezone(IST).date()
            out = await L.refresh_light(provider, store, today=today, pause=0.4, clock=clock, now_fn=clock.now)
            runs.append(out)
            for k in stops:
                stops[k] += out.get("stoppedBy") == k
            assert out["durationSeconds"] <= 24 * 60 + L.CALL_TIMEOUT_S + 5, out                                  # a run NEVER outlives its budget (and never reaches the 30-minute kill)
            # the targets, checked after every run: nobody in the window is unasked for more than ASKED_WITHIN_HOURS (16 h = the 5 h re-ask + the 9 h quiet night + slack), nobody past it for more than 48 h
            if day >= 1:
                at = clock.now()
                recent = await L.recent_declarations(store, today, L.CHASE_DAYS, force=False)
                st = await L.states(store, recent)
                b = L.summarise_buckets(recent, st, today, at)
                during_trouble = any(a - timedelta(minutes=1) <= at < bb + timedelta(hours=1) for a, bb in provider.storms + provider.slow)
                if not during_trouble:
                    assert b[L.OURS]["count"] == 0, (at.isoformat(), b[L.OURS], b["oursSample"])
                for s, v in st.items():
                    if v["source"] in ("provider", "ours") and v["checkedAt"] is not None:
                        worst_hours[s] = max(worst_hours.get(s, 0.0), (at - v["checkedAt"]).total_seconds() / 3600)
            t += timedelta(minutes=55)
    # end of day 3 (after the last run): every company the provider has published is filled, and every one it has not yet is waiting for the PROVIDER, not for us
    end = clock.now()
    recent = await L.recent_declarations(store, end.astimezone(IST).date(), L.CHASE_DAYS, force=False)
    st = await L.states(store, recent)
    published = [s for s in syms if publish[s] <= end - timedelta(hours=2) and (end.date() - declared[s]).days <= L.CHASE_DAYS]
    unfilled_published = [s for s in published if st[s]["source"] not in ("full", "light")]
    assert len(unfilled_published) <= 5, (len(unfilled_published), unfilled_published[:10])                       # only the hours since the last run can be missing
    buckets = L.summarise_buckets(recent, st, end.astimezone(IST).date(), end)
    assert buckets[L.OURS]["count"] == 0 and buckets[L.FILLED]["count"] >= len(published) - 5
    in_window_worst = max((h for s, h in worst_hours.items() if (end.date() - declared[s]).days <= L.MAX_AGE_DAYS + 2), default=0)
    assert in_window_worst <= L.ASKED_WITHIN_HOURS + 2, in_window_worst                                           # target: asked at least every 16 h (+ a storm / slow hour of slack)
    assert stops["budget"] >= 1 and provider.n503 > 50 and provider.nslow > 5                                      # the bad hours really happened: the budget stopped runs, nothing was killed
    print("SIM", {"runs": len(runs), "asked": sum(r["tried"] for r in runs), "filled": sum(r["filled"] for r in runs), "throttled": sum(r["throttled"] for r in runs), "timedOut": sum(r["timedOut"] for r in runs),
                  "stopped": stops, "longestRunSeconds": max(r["durationSeconds"] for r in runs), "meanAskedPerRun": round(sum(r["tried"] for r in runs) / len(runs)), "worstAskGapHours": round(in_window_worst, 1)})
    assert sum(r["tried"] for r in runs) < 3 * 16 * L.PER_RUN                                                      # and the caps were not what cleared it: the work was
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol LIKE 'S0%' OR symbol LIKE 'S1%'")
    R.reset()
