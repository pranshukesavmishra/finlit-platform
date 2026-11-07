"""The time-limit contract: no job may be written so that the supervisor kills it at its limit with nothing saved, every scheduled command must be a
command the worker really has, and a job that is getting close to its limit is reported before it starts failing."""
import re

import pytest

from finlit import worker
from finlit.jobs.registry import LIMIT_POLICY, Job, build_jobs, limit_policy
from finlit.jobs.status import NEAR_LIMIT_SHARE, near_limit

ENV = {"FUND_LOADS_ENABLED": "1", "DHAN_CLIENT_ID": "x", "SECTORS_ENABLED": "1", "SECTORS_JOB": "on"}   # the sector job is off by default since 7 Nov 2026; these tests judge it as if on
JOBS = [j for j in build_jobs(ENV)]
TIMED = [j for j in JOBS if j.cls != "ondemand"]


@pytest.mark.parametrize("job", TIMED, ids=lambda j: j.name)
def test_every_job_declares_what_happens_at_its_time_limit(job):
    policy = limit_policy(job)
    assert policy, f"{job.name}: say how it behaves at its limit (resumable=True, or an entry in LIMIT_POLICY with the reason)"
    if policy == "resume":
        assert job.resumable
        return
    kind, _, why = policy.partition(": ")
    assert kind in ("deadline", "fixed", "database", "measured"), policy
    assert len(why) >= 12, f"{job.name}: the reason is too short to mean anything"


@pytest.mark.parametrize("job", [j for j in TIMED if (limit_policy(j) or "").startswith("deadline")], ids=lambda j: j.name)
def test_a_deadline_job_really_stops_itself_before_its_limit(job):
    assert "--max-minutes" in job.args, f"{job.name} says it stops itself, but its command has no --max-minutes"
    minutes = float(job.args[job.args.index("--max-minutes") + 1])
    assert 0 < minutes < job.max_runtime_min, f"{job.name}: its own deadline ({minutes} min) must be below its limit ({job.max_runtime_min:g} min)"
    assert job.max_runtime_min - minutes >= 3, f"{job.name}: leave a few minutes between the deadline and the limit for the company in hand and the recording"


@pytest.mark.parametrize("job", [j for j in TIMED if (limit_policy(j) or "").startswith("measured") and "-minute limit" in (limit_policy(j) or "")], ids=lambda j: j.name)
def test_a_measured_note_names_the_current_limit(job):
    m = re.search(r"against an? (\d+)-minute limit", limit_policy(job))
    assert m and int(m.group(1)) == int(job.max_runtime_min), f"{job.name}: the note says {m and m.group(1)} minutes, the limit is {job.max_runtime_min:g}"


def test_no_policy_is_left_for_a_job_that_no_longer_exists():
    names = {j.name for j in JOBS}
    assert set(LIMIT_POLICY) <= names, sorted(set(LIMIT_POLICY) - names)
    assert not [n for n in LIMIT_POLICY if next(j for j in JOBS if j.name == n).resumable], "a resumable job needs no entry"


@pytest.mark.parametrize("job", [j for j in JOBS if j.module == "finlit.worker"], ids=lambda j: j.name)
def test_every_scheduled_command_is_a_valid_worker_command(job):
    """A typo in a flag (or a flag that was renamed) would fail at 3 a.m. on every retry; the real parser rejects it here instead."""
    parser = worker.build_parser()
    try:
        parser.parse_args(list(job.args))
    except SystemExit as exc:   # argparse exits on an error
        pytest.fail(f"{job.name}: `{' '.join(job.args)}` is not accepted by the worker (exit {exc.code})")


def _job(**kw) -> Job:
    return Job("j", ("x",), max_runtime_min=kw.pop("limit", 20), **kw)


def test_a_job_close_to_its_limit_is_reported_before_it_fails():
    job = _job(limit=20)                                                   # 1200 s
    assert near_limit(job, [("ok", 100), ("ok", 90), ("ok", 80)]) is None  # comfortable
    assert near_limit(job, [("ok", 900), ("ok", 100), ("ok", 80)]) is None  # one long run is noise
    w = near_limit(job, [("ok", 900), ("ok", 1000), ("ok", 80)])           # two runs at 70% or more
    assert w and w["name"] == "j" and w["usePct"] == 83 and w["limitMin"] == 20 and not w["timedOut"]
    t = near_limit(job, [("timeout", 1200), ("ok", 100)])                  # it hit the limit in a recent run
    assert t and t["timedOut"] and t["usePct"] == 100
    assert near_limit(job, [("ok", 100), ("ok", 100), ("ok", 100), ("timeout", 1200)]) is None   # an old timeout, three good runs since
    assert near_limit(job, [("ok", 100), ("timeout", 1200), ("timeout", 1200)]) is None          # a good run since the timeouts: the cause is over
    assert NEAR_LIMIT_SHARE == 0.70


def test_resumable_jobs_and_always_on_lanes_are_never_judged():
    assert near_limit(_job(resumable=True), [("timeout", 1200), ("timeout", 1200)]) is None
    assert near_limit(Job("d", ("x",), cls="ondemand"), [("timeout", 1200)]) is None


# ---------------------------------------------------------------- jobs that can never fit the server
from finlit.jobs.registry import disabled_reason, unfit_reason   # noqa: E402


def test_a_job_too_big_for_the_container_is_disabled_with_a_reason_not_reported_late():
    """The 4 Nov 2026 alert "job overdue: sectors": the job then needed about 1.5 GB, the app container has 1.2 GB, so it could never start. That is a fact about the
    server, not a late job: it is shown as disabled, with the reason, and never raises the overdue alarm. (The sector job was since split into stages that each
    fit, so this uses a job of that old size.)"""
    from dataclasses import replace
    jobs = {j.name: j for j in build_jobs(ENV)}
    sectors = replace(jobs["sectors"], weight_mb=1500)
    why = disabled_reason(sectors, {**ENV, "JOBS_CAPACITY_MB": "1200"})
    assert why and "1500 MB" in why and "1200 MB" in why and "never start" in why
    assert disabled_reason(sectors, {**ENV, "JOBS_CAPACITY_MB": "4096"}) is None      # a bigger server runs it
    assert disabled_reason(sectors, ENV) is None                                         # capacity unknown (a test, a laptop): no judgement
    assert unfit_reason(sectors, None) is None and unfit_reason(sectors, 0) is None


def test_the_sector_job_fits_the_1200_mb_container_with_room_for_the_website():
    """The staged sector job (docs/SECTORS.md, section 8) peaks at 364 MB at the real size, so it is not disabled on this server and it can wait for free memory
    like any other bulk job. If its weight is ever raised above what a 1,200 MB container can give, this fails: decide on purpose."""
    sectors = {j.name: j for j in build_jobs(ENV)}["sectors"]
    assert disabled_reason(sectors, {**ENV, "JOBS_CAPACITY_MB": "1200"}) is None
    assert sectors.weight_mb >= 364 and sectors.weight_mb + 100 <= 700       # the measured peak, and what is realistically free beside the site


def test_on_this_server_no_job_is_too_big():
    """If a new job is added that does not fit the 1,200 MB app container, this test names it: decide on purpose (smaller weight, or build elsewhere)."""
    too_big = sorted(j.name for j in JOBS if unfit_reason(j, 1200))
    assert too_big == [], too_big


def test_the_always_on_lanes_are_never_judged_by_memory():
    assert unfit_reason(Job("d", ("x",), cls="ondemand", weight_mb=99999), 1200) is None
