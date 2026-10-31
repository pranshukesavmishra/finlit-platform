"""The supervisor under a fake clock and a fake process runner: ordering, concurrency, memory gate, watchdog, retries, pause, crash recovery, alerts."""
from datetime import timedelta

import pytest

from finlit.jobs.due import JobState, PauseInfo
from finlit.jobs.registry import Gate, Job, JobsConfig, Sla, WindowRun, build_jobs
from finlit.jobs.state import MemoryState
from finlit.jobs.supervisor import FORCE_MAX_ATTEMPTS, LockHeld, Supervisor
from jobs_fakes import FakeClock, FakeNotifier, FakePause, FakeResources, FakeRunner, FakeSignals, config, ist

pytestmark = pytest.mark.asyncio
NOON = ist(2026, 10, 30, 12, 0)          # Friday


def make(jobs, now=NOON, free=900, cfg=None, env=None, **kw):
    clock = FakeClock(now)
    sup = Supervisor(jobs=jobs, state=MemoryState(), runner=FakeRunner(clock), resources=FakeResources(free), signals=FakeSignals(), pause=FakePause(), clock=clock,
                     config=cfg or config(), env=env or {}, notifier=kw.pop("notifier", None), **kw)
    return sup, clock


def bulk(name, prio, **kw):
    kw.setdefault("max_runtime_min", 60)
    kw.setdefault("weight_mb", 300)
    return Job(name, (name,), cls="bulk", priority=prio, **kw)


def light(name, prio=10, **kw):
    kw.setdefault("weight_mb", 60)
    return Job(name, (name,), cls="light", priority=prio, **kw)


async def settle(sup, clock, seconds=0):
    """one step of the loop at the current time (decide runs because enough time has passed)."""
    clock.advance(seconds=seconds)
    await sup.step()


async def test_bulk_jobs_run_strictly_one_at_a_time_in_priority_order():
    sup, clock = make([bulk("a", 20), bulk("b", 10), bulk("c", 30)])
    await sup.step()
    assert sup.runner.started == ["b"]                                   # priority 10 first; the others wait, with a reason
    st = await sup.state.load_all()
    assert st["a"].state == "waiting" and "bulk jobs run one at a time" in st["a"].state_reason
    sup.runner.of("b").finish(0)
    await settle(sup, clock, 5)                                          # a job ended: the next one starts at once, not at the next minute
    assert sup.runner.started == ["b", "a"]
    sup.runner.of("a").finish(0)
    await settle(sup, clock, 5)
    assert sup.runner.started == ["b", "a", "c"]
    assert max(len([r for r in sup.running.values() if r.job.cls == "bulk"]) for _ in [0]) <= 1


async def test_equal_priority_is_first_come_first_served():
    sup, clock = make([bulk("zeta", 10, interval_min=60, catchup=False), bulk("alpha", 10)])
    st = JobState(job="zeta", first_seen_at=NOON - timedelta(days=1), last_success_at=NOON - timedelta(hours=2))
    await sup.state.save(st)                                             # zeta becomes due now
    await sup.step()
    # both due at the same moment: ties broken by name; a later-due job never jumps the queue
    assert sup.runner.started == ["alpha"]
    sup.runner.of("alpha").finish(0)
    await settle(sup, clock, 5)
    assert sup.runner.started == ["alpha", "zeta"]


async def test_bulk_concurrency_is_a_config_value():
    sup, _ = make([bulk("a", 10), bulk("b", 20), bulk("c", 30)], cfg=config(bulk_concurrency=2))
    await sup.step()
    assert sup.runner.started == ["a", "b"]


async def test_light_jobs_run_beside_the_bulk_job_capped_at_two():
    sup, _ = make([bulk("big", 10), light("l1", 1), light("l2", 2), light("l3", 3)])
    await sup.step()
    assert sup.runner.started == ["l1", "l2", "big"] or set(sup.runner.started) == {"big", "l1", "l2"}
    assert "l3" not in sup.runner.started
    assert "free light slot" in (await sup.state.load_all())["l3"].state_reason


async def test_a_job_that_does_not_fit_in_memory_waits_with_a_reason_and_starts_when_memory_frees_up():
    sup, clock = make([bulk("big", 10, weight_mb=450)], free=300)
    await sup.step()
    assert sup.runner.started == []
    st = (await sup.state.load_all())["big"]
    assert st.state == "waiting" and "waiting for memory: 300 MB free, needs about 550 MB" in st.state_reason     # weight 450 + 100 MB left for the site
    skips = [r for r in sup.state.runs if r["status"] == "skipped"]
    assert skips and skips[0]["job"] == "big" and "memory" in skips[0]["reason"]                                    # every non-start is recorded
    clock.advance(seconds=61)
    await sup.step()
    assert len([r for r in sup.state.runs if r["status"] == "skipped"]) == 1                                         # the same reason is not recorded again every minute
    sup.resources.free_mb = 900
    clock.advance(seconds=61)
    await sup.step()
    assert sup.runner.started == ["big"]


async def test_memory_reserved_for_a_job_started_in_the_same_tick_counts_against_the_next_one():
    sup, _ = make([bulk("a", 10, weight_mb=300), light("l1", 1, weight_mb=300), light("l2", 2, weight_mb=300)], free=700)
    await sup.step()
    assert set(sup.runner.started) == {"l1", "a"} or set(sup.runner.started) == {"l1", "l2"} or len(sup.runner.started) == 2
    assert len(sup.runner.started) == 2                                  # 700 MB cannot hold three 300 MB jobs (+100 reserve for the bulk one)


async def test_light_results_style_jobs_are_not_blocked_by_the_reserve_a_bulk_job_needs():
    sup, _ = make([light("results", 1, weight_mb=60, honours_pause=False)], free=70)
    await sup.step()
    assert sup.runner.started == ["results"]


async def test_cpu_load_holds_back_a_second_job_but_not_the_first():
    sup, _ = make([bulk("a", 10, weight_mb=100), bulk("b", 20, weight_mb=100)], cfg=config(bulk_concurrency=2))
    sup.resources.load = 5.0
    await sup.step()
    assert sup.runner.started == ["a"]
    assert "CPU" in (await sup.state.load_all())["b"].state_reason


async def test_jobs_of_one_group_take_turns():
    sup, _ = make([light("f1", 1, group="funds"), light("f2", 2, group="funds"), light("x", 3)])
    await sup.step()
    assert set(sup.runner.started) == {"f1", "x"}
    assert "one funds job at a time" in (await sup.state.load_all())["f2"].state_reason


async def test_a_prerequisite_that_is_due_or_running_goes_first():
    sup, clock = make([bulk("portfolios", 50), bulk("score-mf", 40, prerequisites=("portfolios",))], cfg=config(bulk_concurrency=2))
    await sup.step()
    assert sup.runner.started == ["portfolios"]                          # score-mf has the better priority but waits for its input
    assert "waiting for portfolios" in (await sup.state.load_all())["score-mf"].state_reason
    sup.runner.of("portfolios").finish(0)
    await settle(sup, clock, 5)
    assert sup.runner.started == ["portfolios", "score-mf"]


async def test_a_prerequisite_in_backoff_does_not_block_its_dependents_for_ever():
    sup, clock = make([bulk("ingest", 20), bulk("score", 30, prerequisites=("ingest",), interval_min=60, catchup=False)], cfg=config(bulk_concurrency=2))
    await sup.state.save(JobState(job="ingest", first_seen_at=NOON - timedelta(days=2), last_status="failed", consecutive_failures=2, retry_at=NOON + timedelta(minutes=50)))
    await sup.state.save(JobState(job="score", first_seen_at=NOON - timedelta(days=2), last_success_at=NOON - timedelta(hours=2)))
    await sup.step()
    assert sup.runner.started == ["score"]


async def test_disabled_jobs_never_start_and_say_why():
    jobs = [light("funds-job", gate=Gate("FUND_LOADS_ENABLED", "funds are off", default="0"))]
    sup, _ = make(jobs, env={})
    await sup.step()
    st = (await sup.state.load_all())["funds-job"]
    assert sup.runner.started == [] and st.state == "disabled" and st.state_reason == "funds are off"


async def test_bulk_jobs_wait_for_the_web_server_to_settle_after_a_start():
    sup, clock = make([bulk("a", 10), light("l", 1)], cfg=config(boot_delay_s=240))
    await sup.step()
    assert sup.runner.started == ["l"]                                   # light jobs (results) do not wait
    assert "settle" in (await sup.state.load_all())["a"].state_reason
    clock.advance(seconds=241)
    await sup.step()
    assert "a" in sup.runner.started


# ------------------------------------------------------------------------------------------------ outcomes and retries
async def run_to_failure(sup, clock, name, rc=1, out=""):
    sup.runner.of(name).finish(rc, out)
    await sup.poll()


async def test_a_failed_job_is_retried_after_30_then_60_then_120_minutes_and_a_success_resets():
    sup, clock = make([bulk("a", 10, interval_min=600, catchup=True)])
    expect = [30, 60, 120, 120]
    for i, mins in enumerate(expect, 1):
        await sup.step()
        assert sup.runner.started.count("a") == i
        await run_to_failure(sup, clock, "a", 1, "Traceback: boom")
        st = (await sup.state.load_all())["a"]
        assert st.consecutive_failures == i and st.retry_at == clock.now() + timedelta(minutes=mins), (i, st.retry_at)
        clock.advance(minutes=mins - 1)
        await sup.step()
        assert sup.runner.started.count("a") == i                          # not before the retry time
        clock.advance(minutes=1, seconds=5)
    await sup.step()
    sup.runner.of("a").finish(0)
    await sup.poll()
    st = (await sup.state.load_all())["a"]
    assert st.consecutive_failures == 0 and st.retry_at is None and st.last_success_at == clock.now() and st.last_status == "ok"


async def test_a_killed_job_restarts_within_30_minutes():
    sup, clock = make([bulk("a", 10)])
    await sup.step()
    sup.runner.of("a").finish(-9)                                        # the kernel's out-of-memory killer
    await sup.poll()
    run = sup.state.runs[0]
    assert run["status"] == "killed" and "SIGKILL" in run["reason"] and "out of memory" in run["reason"]
    clock.advance(minutes=30, seconds=61)
    await sup.step()
    assert sup.runner.started.count("a") == 2                            # requirement (c): back within 30 minutes


async def test_five_failures_in_a_row_hold_the_job_alert_and_it_is_still_retried_every_two_hours():
    notifier = FakeNotifier()
    sup, clock = make([bulk("a", 10, max_attempts=5)], notifier=notifier)
    for i in range(5):
        await sup.step()
        await run_to_failure(sup, clock, "a", 1)
        clock.advance(hours=2, seconds=5)
    st = (await sup.state.load_all())["a"]
    assert st.consecutive_failures == 5 and st.held_reason and "failed 5 times" in st.held_reason
    assert st.retry_at - st.last_attempt_at == timedelta(minutes=120)
    plan = await sup.plan()
    await sup.check_alerts(plan, clock.now())
    assert any(k == "failing:a" for k, _, _ in notifier.sent)
    await sup.step()                                                     # held, yet retried
    assert sup.runner.started.count("a") == 6


async def test_exit_codes_listed_as_ok_count_as_success():
    sup, clock = make([bulk("audit", 10, ok_exit=(0, 1))])
    await sup.step()
    await run_to_failure(sup, clock, "audit", 1)
    assert (await sup.state.load_all())["audit"].last_status == "ok"


async def test_the_failure_reason_carries_the_last_log_line():
    sup, clock = make([bulk("a", 10)])
    await sup.step()
    await run_to_failure(sup, clock, "a", 2, "RuntimeError: provider said no")
    assert "exit code 2: RuntimeError: provider said no" in sup.state.runs[0]["reason"]


async def test_the_watchdog_stops_a_job_past_its_runtime_and_a_non_resumable_one_counts_a_failure():
    sup, clock = make([bulk("a", 10, max_runtime_min=10, stall_min=None)])
    await sup.step()
    h = sup.runner.of("a")
    clock.advance(minutes=9)
    await sup.poll()
    assert not h.terminated
    clock.advance(minutes=2)
    await sup.poll()                                                     # the watchdog sends the stop signal ...
    assert h.terminated
    await sup.poll()                                                     # ... and the next look collects the exit
    assert "a" not in sup.running
    run = sup.state.runs[0]
    assert run["status"] == "timeout" and "10-minute limit" in run["reason"]
    st = (await sup.state.load_all())["a"]
    assert st.consecutive_failures == 1 and st.retry_at == clock.now() + timedelta(minutes=30)


async def test_a_resumable_job_that_reaches_its_cap_yields_and_continues_in_two_minutes_without_a_failure():
    sup, clock = make([bulk("ingest", 10, max_runtime_min=10, resumable=True, stall_min=None), bulk("other", 20)])
    await sup.step()
    h = sup.runner.of("ingest")
    clock.advance(minutes=11)
    await sup.poll()
    await sup.poll()
    st = (await sup.state.load_all())["ingest"]
    assert sup.state.runs[0]["status"] == "timeout" and st.consecutive_failures == 0 and st.retry_at == clock.now() + timedelta(minutes=2)
    await sup.step()                                                     # the slot is free: the other bulk job gets its turn at once
    assert sup.runner.started == ["ingest", "other"]


async def test_a_hung_job_without_output_or_heartbeat_is_killed_and_retried():
    sup, clock = make([bulk("a", 10, max_runtime_min=600, stall_min=20)])
    await sup.step()
    h = sup.runner.of("a")
    for _ in range(10):
        clock.advance(minutes=1)
        h.touch()                                                        # output keeps coming
        await sup.poll()
    assert not h.terminated
    clock.advance(minutes=21)                                            # silence
    await sup.poll()
    assert h.terminated
    await sup.poll()
    run = sup.state.runs[0]
    assert run["status"] == "timeout" and "no output or heartbeat for 20 minutes" in run["reason"]
    assert (await sup.state.load_all())["a"].consecutive_failures == 1


async def test_a_job_that_ignores_sigterm_is_killed_after_the_grace_period():
    class Stubborn:
        pass
    sup, clock = make([bulk("a", 10, max_runtime_min=1, stall_min=None)])
    await sup.step()
    h = sup.runner.of("a")
    h.terminate = lambda: setattr(h, "terminated", True)                 # does not die
    clock.advance(minutes=2)
    await sup.poll()
    assert h.terminated and not h.killed
    import finlit.jobs.supervisor as s
    r = sup.running["a"]
    r.term_at -= s.TERM_GRACE_S + 1
    await sup.poll()
    assert h.killed


async def test_peak_memory_and_pid_are_recorded_and_the_start_is_published_for_the_results_page():
    sup, clock = make([bulk("a", 10)])
    await sup.step()
    sup.runner.of("a").rss = 321
    await sup.poll()
    sup.runner.of("a").finish(0)
    await sup.poll()
    run = sup.state.runs[0]
    assert run["peak_rss_mb"] == 321 and run["pid"] and run["duration_s"] >= 0 and run["exit_code"] == 0
    assert sup.signals.started == ["a"]


async def test_a_job_that_cannot_be_started_is_a_recorded_failure_with_a_retry():
    sup, clock = make([bulk("a", 10)])
    sup.runner.start = lambda job, env=None: (_ for _ in ()).throw(OSError("no such file"))
    await sup.step()
    run = sup.state.runs[0]
    st = (await sup.state.load_all())["a"]
    assert run["status"] == "failed" and "could not start" in run["reason"] and st.retry_at and st.consecutive_failures == 1


# ------------------------------------------------------------------------------------------------ the admin pause
async def test_the_pause_holds_bulk_jobs_and_ends_by_itself_at_the_expiry_while_light_jobs_run_throughout():
    sup, clock = make([bulk("ingest", 10), light("results", 1, honours_pause=False)])
    sup.pause.info = PauseInfo(until=NOON + timedelta(minutes=30), by="boss")
    await sup.step()
    assert sup.runner.started == ["results"]
    st = (await sup.state.load_all())["ingest"]
    assert st.state == "waiting" and "paused by the admin until" in st.state_reason
    clock.advance(minutes=29)
    await sup.step()
    assert "ingest" not in sup.runner.started
    clock.advance(minutes=2)                                             # 31 minutes: the pause is over
    await sup.step()
    assert "ingest" in sup.runner.started                                # requirement (a): back on without anyone doing anything


# ------------------------------------------------------------------------------------------------ crash recovery and the lock
async def test_a_restarted_supervisor_marks_stale_running_rows_killed_and_schedules_the_retry():
    sup, clock = make([bulk("a", 10), bulk("b", 20)])
    await sup.state.ensure(["a", "b"], NOON)
    rid = await sup.state.start_run("a", NOON - timedelta(minutes=40), 1, 4242)
    n = await sup.reconcile()
    assert n == 1 and sup.runner.orphans == [4242]                       # a leftover process is stopped, too
    run = sup.state.runs[rid - 1]
    assert run["status"] == "killed" and "supervisor restarted" in run["reason"]
    st = (await sup.state.load_all())["a"]
    assert st.retry_at == NOON + timedelta(minutes=1) and st.consecutive_failures == 0
    clock.advance(minutes=2)
    await sup.step()
    assert "a" in sup.runner.started


async def test_only_one_supervisor_runs():
    first, _ = make([bulk("a", 10)])
    second, _ = make([bulk("a", 10)])
    second.signals = first.signals
    assert await first.signals.acquire_lock()
    with pytest.raises(LockHeld):
        await second.run_forever()


async def test_shutdown_stops_the_jobs_marks_them_killed_and_releases_the_lock():
    sup, clock = make([bulk("a", 10)])
    await sup.signals.acquire_lock()
    await sup.step()
    h = sup.runner.of("a")
    await sup.shutdown()
    assert h.terminated and sup.state.runs[0]["status"] == "killed" and not sup.signals.locked
    assert (await sup.state.load_all())["a"].retry_at is not None


async def test_every_step_leaves_a_heartbeat_and_a_database_outage_does_not_stop_the_loop():
    sup, clock = make([bulk("a", 10)])
    await sup.step()
    sup.pause.fail = True                                                # the pause read fails like the database would
    clock.advance(minutes=2)
    await sup.step()
    assert len(sup.signals.beats) == 2 and sup.db_ok is False
    clock.advance(minutes=2)
    await sup.step()
    assert sup.signals.beats[-1]["dbOk"] is False and "RuntimeError" in sup.signals.beats[-1]["lastError"]
    sup.pause.fail = False
    clock.advance(minutes=2)
    await sup.step()
    assert sup.db_ok is True


# ------------------------------------------------------------------------------------------------ alerts and freshness
async def test_overdue_failing_and_stale_data_alerts_are_sent_once_per_six_hours():
    notifier = FakeNotifier()
    j = bulk("score", 10, sla=Sla("hours", 26), windows=(WindowRun("NIGHT", 18),))
    sup, clock = make([j], notifier=notifier, now=ist(2026, 10, 30, 12, 0))
    await sup.state.ensure(["score"], clock.now())
    st = (await sup.state.load_all())["score"]
    st.last_success_at, st.first_seen_at = clock.now() - timedelta(hours=60), clock.now() - timedelta(days=10)
    st.retry_at = clock.now() + timedelta(days=1)                         # held back so it cannot start: the point is the alert
    await sup.state.save(st)
    plan = await sup.plan()
    assert "overdue:score" in await sup.check_alerts(plan, clock.now())
    assert await sup.check_alerts(plan, clock.now()) == []                # the same problem is not repeated
    clock.advance(hours=7)
    plan = await sup.plan()
    assert "overdue:score" in await sup.check_alerts(plan, clock.now())   # but it is not forgotten either
    assert notifier.sent[0][1] == "FinLit job overdue: score"


async def test_a_stale_dataset_forces_its_owner_job_now_and_alerts_if_it_stays_stale_after_two_attempts():
    notifier = FakeNotifier()
    report = {"datasets": [{"key": "technicals", "label": "Technical views", "status": "stale", "jobs": ["tech"], "expected": "2026-10-30", "actual": "2026-10-12", "detail": "506 of 510"}]}

    async def fresh(now):
        return report
    j = bulk("tech", 10, windows=(WindowRun("AFTER_CLOSE", 0),), sla=Sla("hours", 100000), catchup=False)
    sup, clock = make([j], notifier=notifier, freshness=fresh)
    await sup.state.save(JobState(job="tech", first_seen_at=NOON - timedelta(days=30), last_success_at=NOON - timedelta(hours=3)))   # a "successful" job and still stale data
    await sup.step()                                                     # decide + freshness check: forced
    await sup.step()
    clock.advance(seconds=61)
    await sup.step()
    assert sup.runner.started == ["tech"] and (await sup.state.load_all())["tech"].forced_attempts == 1
    sup.runner.of("tech").finish(0)                                      # succeeds again, data still stale
    await sup.poll()
    clock.advance(minutes=11)
    await sup.step()
    clock.advance(seconds=61)
    await sup.step()
    assert sup.runner.started == ["tech", "tech"] and (await sup.state.load_all())["tech"].forced_attempts == FORCE_MAX_ATTEMPTS
    sup.runner.of("tech").finish(0)
    await sup.poll()
    clock.advance(minutes=11)
    await sup.step()                                                     # no third forced run: the alert says so
    assert sup.runner.started == ["tech", "tech"]
    sent = [k for k, _, _ in notifier.sent]                              # the step itself raised it
    assert "stale:technicals" in sent
    assert "even after the job was run again twice" in [b for k, s, b in notifier.sent if k == "stale:technicals"][0]


async def test_a_dataset_that_becomes_fresh_clears_the_forcing():
    state = {"status": "stale"}

    async def fresh(now):
        return {"datasets": [{"key": "scores", "label": "Scores", "status": state["status"], "jobs": ["s"]}]}
    sup, clock = make([bulk("s", 10, catchup=False)], freshness=fresh)
    await sup.state.save(JobState(job="s", first_seen_at=NOON - timedelta(days=3), last_success_at=NOON - timedelta(hours=1), forced_attempts=1))
    state["status"] = "fresh"
    await sup.step()
    assert (await sup.state.load_all())["s"].forced_attempts == 0


# ------------------------------------------------------------------------------------------------ a whole day, real registry
async def test_a_simulated_day_with_the_real_registry_never_runs_two_bulk_jobs_and_leaves_nothing_overdue():
    from finlit.jobs.due import sla_status
    env = {"FUND_LOADS_ENABLED": "1", "DHAN_CLIENT_ID": "x"}
    jobs = build_jobs(env)
    start = ist(2026, 10, 30, 6, 0)
    clock = FakeClock(start)
    sup = Supervisor(jobs=jobs, state=MemoryState(), runner=FakeRunner(clock), resources=FakeResources(1100), signals=FakeSignals(), pause=FakePause(), clock=clock,
                     config=config(), env=env)
    run_for = {j.name: (5 if j.cls == "bulk" else 1) for j in jobs}
    ends = {}
    maxbulk = 0
    for _ in range(60 * 30):                                             # 30 hours of one-minute steps
        for h in sup.runner.handles:
            if h.poll() is None and clock.now() >= h.born + timedelta(minutes=run_for[h.job.name]):
                h.finish(0)
        await sup.step()
        for h in sup.runner.handles:
            if not hasattr(h, "born"):
                h.born = clock.now()
        maxbulk = max(maxbulk, sum(1 for r in sup.running.values() if r.job.cls == "bulk"))
        clock.advance(minutes=1)
    assert maxbulk == 1
    names = set(sup.runner.started)
    for must in ("ingest", "score", "technicals", "results", "calendars", "listing", "portfolios", "score-mf", "mf", "etf", "macro", "flows", "leadership"):
        assert must in names, must
    states = await sup.state.load_all()
    overdue = [j.name for j in jobs if not j.external and sla_status(j, states[j.name], clock.now()).overdue]
    assert overdue == []
    # technicals ran after the Friday close, in the after-close window
    runs = [r for r in sup.state.runs if r["job"] == "technicals" and r["status"] == "ok"]
    assert any(ist(2026, 10, 30, 18, 30) <= r["started_at"] <= ist(2026, 10, 30, 21, 30) for r in runs)


async def test_the_first_start_after_the_upgrade_trusts_the_old_schedulers_run_records():
    async def legacy():
        return {"refresh-macro": (NOON - timedelta(hours=3), "ok"), "refresh-flows": (NOON - timedelta(hours=3), "failed"), "refresh-results": (NOON + timedelta(hours=1), "ok")}
    jobs = [light("macro", 1, interval_min=1000), light("flows", 2), light("results", 3)]
    jobs = [Job("macro", ("refresh-macro",), cls="light", interval_min=1000), Job("flows", ("refresh-flows",), cls="light"), Job("results", ("refresh-results",), cls="light")]
    sup, clock = make(jobs, legacy=legacy)
    await sup.reconcile()
    st = await sup.state.load_all()
    assert st["macro"].last_success_at == NOON - timedelta(hours=3)         # a recent run counts: no needless re-run on the first start
    assert st["flows"].last_success_at is None                              # a failed run does not
    assert st["results"].last_success_at is None                            # a record from the future is ignored
    await sup.step()
    assert "macro" not in sup.runner.started and set(sup.runner.started) == {"flows", "results"}


async def test_a_changing_number_in_a_waiting_reason_is_one_recorded_skip_not_one_per_minute():
    sup, clock = make([bulk("big", 10, weight_mb=450)], free=300)
    for free in (300, 290, 310, 280):
        sup.resources.free_mb = free
        await sup.step()
        clock.advance(seconds=61)
    assert len([r for r in sup.state.runs if r["status"] == "skipped"]) == 1


async def test_old_run_history_is_pruned_but_running_rows_are_kept():
    sup, clock = make([bulk("a", 10)])
    old = await sup.state.start_run("a", NOON - timedelta(days=90), 1, 1)
    await sup.state.finish_run(old, NOON - timedelta(days=90), "ok", None, 0, 1.0, None, {})
    live = await sup.state.start_run("a", NOON - timedelta(days=90), 1, 2)
    await sup.state.prune_runs(NOON, 60)
    assert [r["id"] for r in sup.state.runs] == [live]
