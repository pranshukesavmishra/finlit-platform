"""The job supervisor: decides what is due, runs it within the machine's limits, watches it, retries it, and says so when something is wrong.

Every step is a method that takes its inputs from injected objects (state store, process runner, resources, Redis signals, clock, pause source, notifier),
so the whole thing runs under a fake clock and a fake process runner in the tests. docs/JOBS.md explains the rules in plain words.
"""
from __future__ import annotations

import asyncio
import logging
import signal as sigmod
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from .due import HELD_RETRY_MIN, YIELD_RETRY_MIN, Ctx, JobState, Verdict, evaluate, retry_delay_min, sla_status
from .registry import Job, JobsConfig, disabled_reason
from .schedule import fmt_ist

log = logging.getLogger("finlit.jobs")
TERM_GRACE_S = 20.0
PROBE_EVERY_S = 300.0
FRESHNESS_EVERY_S = 600.0
FORCE_MAX_ATTEMPTS = 2
NOTE_JOBS = {"calendars": "calendars", "results": "results", "results-light": "results-light", "technicals": "technicals"}   # the names /api/results/status reads


def kind(reason: Optional[str]) -> str:
    """The reason without its changing numbers and lists: 'waiting for memory: 312 MB free ...' is one reason, not a new one every minute."""
    import re
    return re.sub(r"\d+", "#", (reason or "").split(" (")[0].split(":")[0])


class LockHeld(RuntimeError):
    pass


@dataclass
class Running:
    job: Job
    run_id: int
    handle: Any
    started: datetime
    attempt: int
    peak_mb: int = 0
    kill_reason: Optional[str] = None
    kill_status: Optional[str] = None
    term_at: Optional[float] = None


@dataclass
class Plan:
    ctx: Ctx
    states: Dict[str, JobState]
    verdicts: Dict[str, Verdict]
    start: List[Job] = field(default_factory=list)
    blocked: Dict[str, str] = field(default_factory=dict)


class Supervisor:
    def __init__(self, *, jobs: List[Job], state: Any, runner: Any, resources: Any, signals: Any, pause: Any, clock: Any, config: JobsConfig,
                 env: Mapping[str, str], probes: Optional[Dict[str, Callable[[], Awaitable[Optional[bool]]]]] = None, notifier: Any = None,
                 freshness: Optional[Callable[[datetime], Awaitable[Dict[str, Any]]]] = None, extra_alerts: Optional[Callable[[datetime], Awaitable[List[tuple]]]] = None,
                 legacy: Optional[Callable[[], Awaitable[Dict[str, tuple]]]] = None) -> None:
        self.jobs = {j.name: j for j in jobs}
        self.order = sorted(jobs, key=lambda j: (j.priority, j.name))
        self.state, self.runner, self.resources, self.signals, self.pause, self.clock = state, runner, resources, signals, pause, clock
        self.cfg, self.env, self.probes, self.notifier, self.freshness_fn, self.extra_alerts = config, env, probes or {}, notifier, freshness, extra_alerts
        self.legacy = legacy
        self.running: Dict[str, Running] = {}
        self.started_at = clock.now()
        self.ticks = 0
        self._last_decide = 0.0
        self._last_fresh = -1e9
        self._probe_cache: Dict[str, tuple] = {}
        self._last_reason: Dict[str, str] = {}
        self._due_since: Dict[str, float] = {}
        self.last_fresh_report: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.db_ok = True

    # ------------------------------------------------------------------------------------------------ start-up
    async def reconcile(self) -> int:
        """Runs still marked 'running' from a supervisor that died: stop any leftover process, mark them 'killed', schedule the retry (no failure counted)."""
        now = self.clock.now()
        await self.state.ensure(self.jobs, now)
        states = await self.state.load_all()
        n = 0
        for row in await self.state.running_runs():
            self.runner.reap_orphan(row.get("pid"))
            started = row["started_at"]
            await self.state.finish_run(row["id"], now, "killed", "the supervisor restarted while this run was in progress", None, (now - started).total_seconds(), None, {})
            st = states.get(row["job"])
            if st:
                st.last_status, st.state, st.state_reason = "killed", "waiting", "restarting after the supervisor restarted"
                st.retry_at = now + timedelta(minutes=1)
                await self.state.save(st)
            n += 1
            log.warning("reconciled a stale running row: %s (run %s) -> killed, retry in 1 minute", row["job"], row["id"])
        await self._seed_from_legacy(states, now)
        return n

    async def _seed_from_legacy(self, states: Dict[str, JobState], now: datetime) -> int:
        """First start after the upgrade: a job the old scheduler ran recently left `run:<command>` in mf_meta (record_run). Take that as its last success, so
        the supervisor does not re-run the whole night's work just because its own history is empty."""
        if not self.legacy:
            return 0
        try:
            runs = await self.legacy()
        except Exception:
            log.warning("legacy run records not read")
            return 0
        n = 0
        for name, job in self.jobs.items():
            st = states.get(name)
            if st is None or st.last_success_at is not None or st.last_attempt_at is not None or not job.args:
                continue
            rec = runs.get(job.args[0])
            if rec and rec[1] in ("ok", "partial") and rec[0] <= now:
                st.last_success_at = rec[0]
                await self.state.save(st)
                n += 1
        return n

    # ------------------------------------------------------------------------------------------------ the decision
    async def _probe(self, name: str, now: datetime) -> Optional[bool]:
        fn = self.probes.get(name)
        if fn is None:
            return None
        t, val = self._probe_cache.get(name, (-1e9, None))
        mono = now.timestamp()
        if mono - t < PROBE_EVERY_S:
            return val
        try:
            val = await asyncio.wait_for(fn(), 30)
        except Exception as exc:   # an unanswerable probe means "unknown": the job then follows its clock
            log.warning("probe %s failed: %s", name, type(exc).__name__)
            val = None
        self._probe_cache[name] = (mono, val)
        return val

    async def make_ctx(self, now: datetime) -> Ctx:
        pause = await self.pause.current(now)
        probes = {n: await self._probe(n, now) for n in {j.probe for j in self.jobs.values() if j.probe}}
        return Ctx(now=now, pause=pause, visitor_active=await self.signals.visitor_active(), alerts_active=await self.signals.alerts_active(),
                   probes=probes, env=self.env, config=self.cfg)

    def _blocker(self, job: Job, plan: Plan, free_mb: float, load: float, reserved: Dict[str, float], now: datetime) -> Optional[str]:
        for p in job.prerequisites:
            pj = self.jobs.get(p)
            if pj and (p in self.running or plan.verdicts[p].due):
                return f"waiting for {p} to finish first"
        if job.cls == "bulk" or job.group == "funds":
            since = (now - self.started_at).total_seconds()
            if since < self.cfg.boot_delay_s:
                return f"waiting for the web server to settle after the start ({int(self.cfg.boot_delay_s - since)} s)"
        running_bulk = [r.job.name for r in self.running.values() if r.job.cls == "bulk"] + [j.name for j in plan.start if j.cls == "bulk"]
        running_light = [r.job.name for r in self.running.values() if r.job.cls == "light"] + [j.name for j in plan.start if j.cls == "light"]
        if job.cls == "bulk" and len(running_bulk) >= self.cfg.bulk_concurrency:
            return f"waiting for {running_bulk[0]} (bulk jobs run one at a time)"
        if job.cls == "light" and len(running_light) >= self.cfg.light_cap:
            return f"waiting for a free light slot ({', '.join(running_light)} running)"
        if job.group:
            for name in [r.job.name for r in self.running.values()] + [j.name for j in plan.start]:
                if name != job.name and self.jobs[name].group == job.group:
                    return f"waiting for {name} (one {job.group} job at a time)"
        need = job.weight_mb + (self.cfg.reserve_mb if job.cls == "bulk" else 0)
        avail = free_mb - reserved["mb"]
        if avail < need:
            return f"waiting for memory: {int(avail)} MB free, needs about {need} MB"
        if job.cls == "bulk" and (self.running or plan.start) and load > self.cfg.max_load_per_cpu:
            return f"waiting for the CPU: load {load:.1f} per core is above {self.cfg.max_load_per_cpu:g}"
        return None

    async def plan(self) -> Plan:
        now = self.clock.now()
        await self.state.ensure(self.jobs, now)
        states = await self.state.load_all()
        for n, s in states.items():
            s.running = n in self.running
        ctx = await self.make_ctx(now)
        verdicts = {n: evaluate(j, states.get(n) or JobState(job=n, first_seen_at=now), ctx) for n, j in self.jobs.items()}
        plan = Plan(ctx=ctx, states=states, verdicts=verdicts)
        snap = self.resources.snapshot()
        reserved = {"mb": 0.0}
        for n, v in verdicts.items():
            if v.due:
                self._due_since.setdefault(n, now.timestamp())
            else:
                self._due_since.pop(n, None)
        # priority first, then first come first served among equals
        for job in sorted(self.order, key=lambda j: (j.priority, self._due_since.get(j.name, 0.0), j.name)):
            if not verdicts[job.name].due:
                continue
            why = self._blocker(job, plan, snap.free_mb, snap.load_per_cpu, reserved, now)
            if why:
                plan.blocked[job.name] = why
            else:
                plan.start.append(job)
                reserved["mb"] += job.weight_mb
        return plan

    async def decide(self) -> Plan:
        plan = await self.plan()
        now = self.clock.now()
        for job in plan.start:
            await self._start(job, plan.states.get(job.name) or JobState(job=job.name, first_seen_at=now), plan.verdicts[job.name], now)
        await self._persist(plan, now)
        return plan

    async def _start(self, job: Job, st: JobState, verdict: Verdict, now: datetime) -> None:
        attempt = st.consecutive_failures + 1
        forced = bool(st.forced_at and (st.last_attempt_at is None or st.last_attempt_at < st.forced_at))
        try:
            handle = self.runner.start(job)
        except Exception as exc:   # the process could not even be created: a recorded failure with a retry, not a silent skip
            run_id = await self.state.start_run(job.name, now, attempt, None)
            await self._complete_raw(job, st, run_id, now, "failed", f"could not start: {type(exc).__name__}: {exc}"[:300], None, 0.0, None, {})
            await self.state.save(st)
            return
        run_id = await self.state.start_run(job.name, now, attempt, handle.pid)
        self.running[job.name] = Running(job, run_id, handle, now, attempt)
        st.last_attempt_at, st.last_status, st.retry_at, st.state, st.state_reason, st.running = now, "running", None, "running", verdict.reason, True
        if forced:
            st.forced_attempts += 1
        await self.state.save(st)
        try:
            await self.signals.job_started(job.name, now)
        except Exception:   # nosec B110 - a Redis hiccup must not stop the job
            pass
        log.info("start %s (%s)", job.name, verdict.reason)

    async def _persist(self, plan: Plan, now: datetime) -> None:
        for name, job in self.jobs.items():
            st = plan.states.get(name) or JobState(job=name, first_seen_at=now)
            v = plan.verdicts[name]
            if name in self.running:
                state, reason = "running", st.state_reason or "running"
            elif name in plan.blocked:
                state, reason = "waiting", plan.blocked[name]
            elif v.due:
                continue   # was just started (state saved by _start)
            else:
                state, reason = v.state, v.reason
            changed = (st.state, kind(st.state_reason), st.next_due_at) != (state, kind(reason), v.next_due_at)
            if not changed:
                continue
            st.state, st.state_reason, st.next_due_at = state, reason, v.next_due_at
            await self.state.save(st)
            if state == "waiting" and name in plan.blocked and self._last_reason.get(name) != kind(reason):
                await self.state.record_skip(name, now, reason)   # every non-start has a recorded reason
                log.info("%s not started: %s", name, reason)
                if name in NOTE_JOBS:
                    try:
                        await self.signals.note(NOTE_JOBS[name], f"waiting: {reason}")
                    except Exception:   # nosec B110
                        pass
            self._last_reason[name] = kind(reason)

    # ------------------------------------------------------------------------------------------------ watching the running jobs
    async def poll(self) -> bool:
        """Checks every running job; returns True when one finished (the caller then looks for the next job at once)."""
        any_done = False
        now = self.clock.now()
        for name in list(self.running):
            r = self.running[name]
            rc = r.handle.poll()
            rss = r.handle.rss_mb()
            if rss:
                r.peak_mb = max(r.peak_mb, rss)
            if rc is None:
                self._watchdog(r, now)
                continue
            await self._finished(r, rc, now)
            any_done = True
        return any_done

    def _watchdog(self, r: Running, now: datetime) -> None:
        if r.term_at is not None:
            if time.monotonic() - r.term_at > TERM_GRACE_S:
                r.handle.kill()
            return
        runtime_min = (now - r.started).total_seconds() / 60
        if runtime_min > r.job.max_runtime_min:
            self._terminate(r, "timeout", f"ran longer than its {r.job.max_runtime_min:g}-minute limit")
        elif r.job.stall_min and now.timestamp() - r.handle.last_activity() > r.job.stall_min * 60:
            self._terminate(r, "timeout", f"no output or heartbeat for {r.job.stall_min:g} minutes (hung)")

    def _terminate(self, r: Running, status: str, reason: str) -> None:
        log.warning("stopping %s: %s", r.job.name, reason)
        r.kill_status, r.kill_reason, r.term_at = status, reason, time.monotonic()
        r.handle.terminate()

    async def _finished(self, r: Running, rc: int, now: datetime) -> None:
        del self.running[r.job.name]
        tail = r.handle.tail()
        duration = (now - r.started).total_seconds()
        if r.kill_status:
            status, reason = r.kill_status, r.kill_reason
        elif rc in r.job.ok_exit:
            status, reason = "ok", None
        elif rc < 0:
            name = sigmod.Signals(-rc).name if -rc in {s.value for s in sigmod.Signals} else str(-rc)
            status, reason = "killed", f"killed by {name}" + (" (most likely out of memory)" if name == "SIGKILL" else "")
        else:
            status, reason = "failed", f"exit code {rc}" + (f": {tail}" if tail else "")
        st = (await self.state.load_all()).get(r.job.name) or JobState(job=r.job.name, first_seen_at=now)
        await self._complete_raw(r.job, st, r.run_id, now, status, reason, rc, duration, r.peak_mb or None, {"tail": tail} if tail else {})
        await self.state.save(st)
        log.info("done %s: %s%s", r.job.name, status, f" ({reason})" if reason else "")

    async def _complete_raw(self, job: Job, st: JobState, run_id: int, now: datetime, status: str, reason: Optional[str], rc: Optional[int],
                            duration: float, peak: Optional[int], counts: Dict[str, Any]) -> None:
        await self.state.finish_run(run_id, now, status, reason, rc, duration, peak, counts)
        st.running, st.last_attempt_at, st.last_status = False, st.last_attempt_at or now, status
        if status == "ok":
            st.last_success_at, st.consecutive_failures, st.retry_at, st.held_until, st.held_reason, st.forced_at = now, 0, None, None, None, None   # forced_attempts is cleared only when the data turns fresh
            st.state, st.state_reason = "idle", "finished"
            return
        if status == "timeout" and job.resumable and reason and reason.startswith("ran longer"):
            st.retry_at = now + timedelta(minutes=YIELD_RETRY_MIN)    # a resumable job yields at its time cap and continues: not a failure
            st.state, st.state_reason = "waiting", f"reached its time limit; continues at {fmt_ist(st.retry_at)} (resumable)"
            return
        st.consecutive_failures += 1
        held = st.consecutive_failures >= job.max_attempts
        delay = HELD_RETRY_MIN if held else retry_delay_min(st.consecutive_failures)
        st.retry_at = now + timedelta(minutes=delay)
        if held:
            st.held_until, st.held_reason = st.retry_at, f"failed {st.consecutive_failures} times in a row; last: {reason or status}"[:300]
        st.state, st.state_reason = ("held" if held else "waiting"), f"{status}: {reason or ''}; retry at {fmt_ist(st.retry_at)}"[:300]

    # ------------------------------------------------------------------------------------------------ freshness, alerts
    async def check_freshness(self, now: datetime) -> None:
        if not self.freshness_fn:
            return
        report = await self.freshness_fn(now)
        self.last_fresh_report = report
        try:
            await self.signals.set_json("jobs:freshness", report)
        except Exception:   # nosec B110
            pass
        states = await self.state.load_all()
        stale_owners: Dict[str, List[str]] = {}
        for d in report.get("datasets", []):
            if d["status"] == "stale":
                for owner in d.get("jobs", []):
                    stale_owners.setdefault(owner, []).append(d["key"])
        for name, job in self.jobs.items():
            st = states.get(name)
            if st is None or job.external or disabled_reason(job, self.env):
                continue
            if name in stale_owners and name not in self.running:
                if st.retry_at and st.retry_at > now:
                    continue    # in backoff: the retry rule already owns it
                if st.forced_attempts < FORCE_MAX_ATTEMPTS and (st.last_attempt_at is None or (now - st.last_attempt_at).total_seconds() >= 600) and not st.forced_at:
                    st.forced_at = now
                    await self.state.save(st)
                    log.warning("data stale (%s): %s forced due now", ",".join(stale_owners[name]), name)
            elif name not in stale_owners and st.forced_attempts and name not in self.running:
                st.forced_attempts, st.forced_at = 0, None
                await self.state.save(st)

    async def check_alerts(self, plan: Plan, now: datetime) -> List[str]:
        sent: List[str] = []
        if not self.notifier:
            return sent
        problems: List[tuple] = []
        for name, job in self.jobs.items():
            st, v = plan.states.get(name), plan.verdicts[name]
            if st is None or v.state == "disabled" or job.external:
                continue
            sla = sla_status(job, st, now)
            if sla.overdue and not (job.honours_pause and plan.ctx.pause):
                problems.append((f"overdue:{name}", f"FinLit job overdue: {name}",
                                 f"{name} ({job.what}) has not succeeded for {sla.age_hours:.1f} hours; its promise is {job.sla.hours:g} hours ({job.sla.kind}). "
                                 f"State: {v.state}: {v.reason}. Last result: {st.last_status}. Open /api/jobs/status for the full picture."
                                 if sla.age_hours is not None else f"{name} ({job.what}) has never succeeded and is {sla.lateness_hours:.1f} hours past its promise. State: {v.state}: {v.reason}."))
            if st.consecutive_failures >= 3:
                problems.append((f"failing:{name}", f"FinLit job failing: {name}",
                                 f"{name} has failed {st.consecutive_failures} times in a row ({st.last_status}). {st.state_reason or ''} It is retried automatically "
                                 f"{'every 2 hours' if st.consecutive_failures >= job.max_attempts else 'with a growing delay'}. Look at /tmp/job-{name}.log in the app container."))
        if self.last_fresh_report:
            states = plan.states
            for d in self.last_fresh_report.get("datasets", []):
                if d["status"] != "stale":
                    continue
                owners = [states.get(o) for o in d.get("jobs", []) if o in states]
                if owners and all(o.forced_attempts >= FORCE_MAX_ATTEMPTS for o in owners if o) and not any(o.running for o in owners if o):
                    problems.append((f"stale:{d['key']}", f"FinLit data is stale: {d['label']}",
                                     f"{d['label']} is stale (expected {d.get('expected')}, found {d.get('actual')}) even after the job was run again twice. {d.get('detail') or ''}"))
        if self.extra_alerts:
            try:
                problems += await self.extra_alerts(now)
            except Exception:
                log.exception("extra alert checks failed")
        for key, subject, body in problems:
            if await self.notifier.alert(key, subject, body, now):
                sent.append(key)
        return sent

    # ------------------------------------------------------------------------------------------------ the loop
    async def step(self) -> None:
        now = self.clock.now()
        self.ticks += 1
        if not await self.signals.refresh_lock():
            raise LockHeld("another supervisor took over")
        try:
            await self.signals.heartbeat(now, {"pid": __import__("os").getpid(), "ticks": self.ticks, "running": sorted(self.running), "startedAt": self.started_at.timestamp(),
                                               "dbOk": self.db_ok, "lastError": self.last_error})
        except Exception:   # nosec B110 - the heartbeat is best effort; the loop goes on
            pass
        finished = False
        try:
            finished = await self.poll()
        except Exception as exc:
            self.last_error = f"poll: {type(exc).__name__}"
            log.exception("poll failed")
        mono = now.timestamp()
        if finished or mono - self._last_decide >= self.cfg.tick_s:
            self._last_decide = mono
            try:
                plan = await self.decide()
                self.db_ok, self.last_error = True, None
                if mono - self._last_fresh >= FRESHNESS_EVERY_S:
                    self._last_fresh = mono
                    await self.state.prune_runs(now, 60)
                    await self.check_freshness(now)
                await self.check_alerts(plan, now)
            except LockHeld:
                raise
            except Exception as exc:   # database down, Redis down: keep watching the running jobs, try again next tick
                self.db_ok, self.last_error = False, f"{type(exc).__name__}: {exc}"[:200]
                log.exception("tick failed")

    async def run_forever(self, stop: Optional[asyncio.Event] = None) -> None:
        stop = stop or asyncio.Event()
        if not await self.signals.acquire_lock():
            raise LockHeld("another supervisor is running")
        try:
            try:
                await self.reconcile()
            except Exception:
                log.exception("reconcile failed (will retry on the next start)")
            while not stop.is_set():
                await self.step()
                await self.clock.sleep(self.cfg.poll_s)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Stops the jobs it started and marks them 'killed', so the next supervisor retries them at once instead of finding stale rows."""
        now = self.clock.now()
        for name in list(self.running):
            r = self.running.pop(name)
            r.handle.terminate()
            try:
                await self.state.finish_run(r.run_id, now, "killed", "the supervisor was stopped", None, (now - r.started).total_seconds(), r.peak_mb or None, {})
                st = (await self.state.load_all()).get(name)
                if st:
                    st.running, st.last_status, st.retry_at, st.state = False, "killed", now + timedelta(minutes=1), "waiting"
                    await self.state.save(st)
            except Exception:
                log.exception("could not record the stop of %s", name)
        try:
            await self.signals.release_lock()
        except Exception:   # nosec B110
            pass

    async def run_once(self, wait: bool = True, timeout_s: float = 6 * 3600) -> Plan:
        """One pass: start what is due now (no new jobs afterwards), optionally wait for those to finish. Used by `supervise --once` and tests."""
        plan = await self.decide()
        if wait:
            t0 = self.clock.now()
            while self.running and (self.clock.now() - t0).total_seconds() < timeout_s:
                await self.clock.sleep(self.cfg.poll_s)
                await self.poll()
        return plan
