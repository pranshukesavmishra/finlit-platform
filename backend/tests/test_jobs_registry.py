"""The registry is data: check it is coherent, that every command the old bash scheduler ran is still scheduled at an equal or better time, and that the env switches mean what they did."""
from datetime import timedelta
from pathlib import Path

from finlit.jobs.due import Ctx, JobState, evaluate
from finlit.jobs.registry import JobsConfig, build_jobs, by_name, disabled_reason
from jobs_fakes import ist

ENV = {"FUND_LOADS_ENABLED": "1", "DHAN_CLIENT_ID": "x"}
JOBS = by_name(ENV)
OLD = [l.strip() for l in (Path(__file__).parent / "fixtures/old_scheduler_commands.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]


def test_names_are_unique_priorities_sane_and_prerequisites_exist():
    jobs = build_jobs(ENV)
    names = [j.name for j in jobs]
    assert len(names) == len(set(names))
    for j in jobs:
        assert j.cls in ("bulk", "light", "ondemand") and j.max_runtime_min > 0 and j.weight_mb > 0
        for p in j.prerequisites:
            assert p in names, (j.name, p)
        if j.sla.kind != "none":
            assert j.sla.hours > 0
        for w in j.windows:
            assert w.window in ("MORNING", "AFTER_CLOSE", "NIGHT")
        if not j.external and j.cls != "ondemand":
            assert j.windows or j.interval_min or j.daily_at or j.probe or j.sla.kind != "none", f"{j.name} has no schedule"
    # no prerequisite cycles
    for j in jobs:
        seen, todo = set(), list(j.prerequisites)
        while todo:
            p = todo.pop()
            assert p != j.name
            if p not in seen:
                seen.add(p)
                todo += list(JOBS[p].prerequisites)


def test_every_command_the_old_scheduler_ran_is_registered():
    registered = [" ".join(j.args) for j in JOBS.values()]
    for cmd in OLD:
        assert any(r == cmd or r.startswith(cmd + " ") or cmd.startswith(r + " ") or (cmd.split()[0] == r.split()[0] and all(t in r.split() for t in cmd.split()[1:])) for r in registered), cmd


def test_the_always_on_processes_are_visible_but_not_scheduled():
    assert JOBS["drain-queue"].external and JOBS["commodities"].external and JOBS["drain-queue"].cls == "ondemand"
    assert JOBS["drain-queue"].honours_pause is False


def test_bulk_and_light_classes_match_the_incident_analysis():
    for n in ("technicals", "ingest", "score", "prism", "score-mf", "portfolios", "backfill-history", "leadership"):
        assert JOBS[n].cls == "bulk", n          # the three that ran at once on 2 GB are now strictly sequential
    for n in ("results", "results-light", "calendars", "quotes", "listing"):
        assert JOBS[n].cls == "light" and JOBS[n].honours_pause is False, n
    assert JOBS["score-mf"].prerequisites == ("portfolios",) and "ingest" in JOBS["prism"].prerequisites
    assert JOBS["results"].sla.hours == 1.5 and JOBS["calendars"].sla.hours == 1.0 and JOBS["listing"].sla.hours == 6
    for n in ("ingest", "score", "prism", "mf", "portfolios"):
        assert JOBS[n].sla.hours == 26, n


def test_env_switches_keep_their_meaning():
    off = by_name({})
    for n in ("mf", "etf", "facts", "industry", "instruments", "portfolios", "score-mf", "backfill-mf"):
        assert disabled_reason(off[n], {}) and "FUND_LOADS_ENABLED=1" in disabled_reason(off[n], {}), n      # FUND_LOADS_ENABLED=0 (the default): disabled, not overdue
        assert disabled_reason(JOBS[n], ENV) is None
    assert disabled_reason(JOBS["prism"], {"PRISM_PRECOMPUTE_ENABLED": "0"})
    assert disabled_reason(JOBS["prism"], {}) is None
    assert disabled_reason(JOBS["dhan-check"], {}) and disabled_reason(JOBS["dhan-check"], ENV) is None
    cfg = JobsConfig.from_env({"BOOT_LOAD_ENABLED": "0", "BULK_CONCURRENCY": "2", "QUOTES_EVERY_MINUTES": "3", "BOOT_LOAD_DELAY_S": "10"})
    assert not cfg.boot_load_enabled and cfg.bulk_concurrency == 2 and cfg.quotes_every_min == 3 and cfg.boot_delay_s == 10
    assert JobsConfig.from_env({}).bulk_concurrency == 1 and JobsConfig.from_env({"BULK_CONCURRENCY": "junk"}).bulk_concurrency == 1
    assert by_name({"INGEST_LIMIT": "500"})["ingest"].args[-4:-2] == ("--limit", "500") or "500" in by_name({"INGEST_LIMIT": "500"})["ingest"].args
    assert "--limit" not in by_name({"INGEST_LIMIT": "0"})["ingest"].args


# ------------------------------------------------------------------------------------------------ schedule parity with the old slots
FRI, SAT, SUN = (2026, 10, 30), (2026, 10, 31), (2026, 11, 1)


def runs_near(name, day, hm, age_h, probe=None, back=150, fwd=10):
    """True when the job is due (for a schedule reason, not because the SLA is blown) at some moment from `back` minutes before the old slot to `fwd` after."""
    slot = ist(*day, *hm)
    j = JOBS[name]
    for off in range(-back, fwd + 1, 5):
        t = slot + timedelta(minutes=off)
        st = JobState(job=name, first_seen_at=t - timedelta(days=60), last_success_at=t - timedelta(hours=age_h), last_attempt_at=t - timedelta(hours=age_h))
        probes = {j.probe: probe} if j.probe else {}
        v = evaluate(j, st, Ctx(now=t, env=ENV, probes=probes))
        if v.due and "SLA" not in v.reason and "never" not in v.reason:
            return True
    return False


def test_every_old_time_slot_is_covered_by_the_same_job_at_or_before_that_time():
    old_slots = [
        # (job, day, IST time, how old the last success is at that moment)
        ("results", FRI, (10, 20), 0.5), ("results", FRI, (10, 50), 0.5), ("results", FRI, (23, 30), 2), ("results", SAT, (6, 45), 8), ("results", FRI, (15, 50), 1),
        ("results-light", FRI, (10, 35), 1.0), ("results-light", FRI, (21, 10), 1.0),
        ("calendars", FRI, (10, 5), 1.0), ("calendars", SAT, (6, 45), 12), ("calendars", FRI, (23, 30), 2),
        ("listing", FRI, (15, 50), 5), ("listing", FRI, (19, 10), 3), ("listing", SAT, (19, 10), 3),
        ("technicals", FRI, (18, 30), 24, True), ("technicals", FRI, (21, 10), 3, True), ("technicals", SAT, (6, 45), 12, True),
        ("flows-nse", FRI, (19, 10), 24), ("flows", FRI, (19, 10), 24), ("flows", FRI, (21, 10), 2), ("macro", FRI, (19, 10), 24), ("industry", FRI, (19, 10), 24),
        ("mf", FRI, (21, 10), 24), ("mf", FRI, (23, 30), 2.5), ("facts", FRI, (21, 10), 24), ("etf", FRI, (21, 10), 24), ("etf", FRI, (23, 30), 2.5),
        ("instruments", SAT, (6, 45), 24), ("screens", FRI, (6, 45), 24),
        ("alerts-daily", FRI, (19, 10), 24), ("digest", SUN, (19, 10), 24 * 7),
        ("prune", SAT, (1, 0), 24), ("ingest", SAT, (1, 0), 24), ("score", SAT, (1, 0), 24), ("indices", SAT, (1, 0), 24), ("coverage", SAT, (1, 0), 24),
        ("integrity", SAT, (1, 0), 24), ("backfill-mf", SAT, (1, 0), 24), ("backfill-history", SAT, (1, 0), 24), ("prism", SAT, (1, 0), 24, False),
        ("portfolios", SAT, (1, 0), 24), ("score-mf", SAT, (1, 0), 24), ("logos", SAT, (1, 0), 24),
        ("leadership", SAT, (1, 0), 24 * 7), ("universe", SUN, (1, 0), 24 * 7), ("backtest-leadership", (2027, 1, 3), (1, 0), 24 * 100),
        ("rebuild-metrics", SAT, (1, 0), 24 * 7), ("short-history", SAT, (1, 0), 24 * 7), ("history-probe", SAT, (1, 0), 24 * 7), ("dhan-check", SAT, (1, 0), 24 * 7),
    ]
    missing = [s[:3] for s in old_slots if not runs_near(s[0], s[1], s[2], s[3], probe=(s[4] if len(s) > 4 else None))]
    assert not missing, missing


def test_the_new_morning_window_runs_the_whole_catch_up_chain_when_the_night_failed():
    day = (2026, 10, 31)
    need = ["ingest", "score", "prism", "technicals", "mf", "portfolios", "score-mf", "results", "calendars", "listing", "macro", "flows", "indices", "instruments"]
    t = ist(*day, 5, 30)
    for n in need:
        j = JOBS[n]
        st = JobState(job=n, first_seen_at=t - timedelta(days=30), last_success_at=t - timedelta(hours=24 if n == "instruments" else 16), last_attempt_at=t - timedelta(hours=16))
        v = evaluate(j, st, Ctx(now=t, env=ENV, probes={"technicals": True, "prism": True}))
        assert v.due, (n, v.reason)
