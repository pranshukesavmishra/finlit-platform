"""When is a job due? Pure functions of (job, its stored state, the clock and a few facts): no I/O, no sleeping, so every rule is tested with a fake clock.

A job is DUE when something needs it now: its SLA is breached, a quiet window is open and the job has not run for long enough, its interval has passed,
its daily time has passed without a success, a probe says there is work, the freshness checker found its data stale, or a retry is owed. It is never
"missed": a late supervisor, a busy box or a restart simply find the job still due at the next look.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Tuple

from .registry import Job, JobsConfig, disabled_reason
from .schedule import (IST, fmt_ist, in_active_hours, ist, is_weekday, latest_ready, market_hours, next_active_start, next_window_start, open_windows,
                       session_ready_at, window_open)

RETRY_STEPS_MIN = (30, 60, 120)        # after the 1st, 2nd, 3rd and later failure in a row; reset by a success
HELD_RETRY_MIN = 120                   # a job held after max_attempts failures is still retried this often
YIELD_RETRY_MIN = 2                    # a resumable job that reached its time cap yields and continues after this long


def retry_delay_min(failures: int) -> int:
    return RETRY_STEPS_MIN[min(max(failures, 1), len(RETRY_STEPS_MIN)) - 1]


@dataclass
class JobState:
    job: str
    first_seen_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    last_status: Optional[str] = None
    next_due_at: Optional[datetime] = None
    consecutive_failures: int = 0
    retry_at: Optional[datetime] = None
    held_until: Optional[datetime] = None
    held_reason: Optional[str] = None
    forced_at: Optional[datetime] = None
    forced_attempts: int = 0
    state: str = "idle"
    state_reason: Optional[str] = None
    running: bool = False


@dataclass
class PauseInfo:
    until: datetime
    by: Optional[str] = None
    since: Optional[datetime] = None
    legacy: bool = False


@dataclass
class Ctx:
    now: datetime
    pause: Optional[PauseInfo] = None
    visitor_active: bool = False
    alerts_active: bool = True
    probes: Dict[str, Optional[bool]] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    config: JobsConfig = field(default_factory=JobsConfig)


@dataclass
class Verdict:
    state: str                       # idle | due | waiting | held | disabled | running
    reason: str
    due: bool = False
    next_due_at: Optional[datetime] = None


@dataclass
class SlaStatus:
    applicable: bool
    deadline: Optional[datetime]
    age_hours: Optional[float]
    lateness_hours: float
    breached: bool
    overdue: bool                   # more than 1.5 x the SLA


def _hours(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 3600.0


def _active_add(anchor: datetime, hours: float, span: Tuple[int, int]) -> datetime:
    """anchor + hours of ACTIVE time (the clock only runs inside the active hours, IST)."""
    t = anchor if in_active_hours(anchor, span) else next_active_start(anchor, span)
    rem = timedelta(hours=hours)
    for _ in range(400):
        i = ist(t)
        seg_end = i.replace(hour=span[1], minute=59, second=59, microsecond=0)
        avail = seg_end - i
        if rem <= avail:
            return t + rem
        rem -= avail
        t = next_active_start(seg_end + timedelta(seconds=1), span)
    return t


def _first_ready_after(t: datetime) -> datetime:
    """The first trading-day data-final moment (18:30 IST) strictly after t."""
    d = ist(t).date()
    for _ in range(12):
        if is_weekday(d) and session_ready_at(d) > t:
            return session_ready_at(d)
        d += timedelta(days=1)
    return session_ready_at(d)


def sla_status(job: Job, st: JobState, now: datetime) -> SlaStatus:
    sla = job.sla
    if sla.kind == "none" or not sla.hours:
        return SlaStatus(False, None, None, 0.0, False, False)
    anchor = st.last_success_at or st.first_seen_at or now
    age = _hours(now, st.last_success_at) if st.last_success_at else None
    if sla.kind == "hours":
        deadline = anchor + timedelta(hours=sla.hours)
    elif sla.kind == "active":
        deadline = _active_add(anchor, sla.hours, job.active_hours or (8, 23))
    else:   # session: a success must exist after each trading day's data is final; overdue sla.hours after the FIRST session that was missed
        deadline = _first_ready_after(anchor) + timedelta(hours=sla.hours)
    late = _hours(now, deadline)
    return SlaStatus(True, deadline, age, max(late, 0.0), late > 0, late > 0.5 * sla.hours)


def _day_ok(job: Job, now: datetime) -> bool:
    return job.day_rule is None or job.day_rule(ist(now).date())


def _age_h(st: JobState, now: datetime) -> float:
    return _hours(now, st.last_success_at) if st.last_success_at else float("inf")


def _visitor_gate(job: Job, ctx: Ctx) -> Tuple[bool, Optional[float]]:
    """(allowed, interval override in minutes)."""
    g = job.visitor_gate
    if not g:
        return True, None
    if g.startswith("env:"):
        return (ctx.env.get(g[4:], "0") != "1" or ctx.visitor_active), None
    if g == "visitor":
        return ctx.visitor_active, None
    if g == "alerts":
        return ctx.alerts_active, None
    if g == "visitor_or_alerts":
        if ctx.visitor_active:
            return True, job.interval_min
        return ctx.alerts_active, job.interval_idle_min or job.interval_min
    return True, None


def _window_hit(job: Job, st: JobState, ctx: Ctx) -> Optional[str]:
    now = ctx.now
    if not _day_ok(job, now):
        return None
    age = _age_h(st, now)
    for wr in job.windows:
        if not window_open(wr.window, now):
            continue
        if wr.not_before and (ist(now).hour, ist(now).minute) < wr.not_before:
            continue
        if job.sla.kind == "session":
            _, ready = latest_ready(now)
            if not st.last_success_at or st.last_success_at < ready:
                return f"{wr.window.lower().replace('_', '-')} window is open and the latest session's data is not processed yet"
            continue
        if age >= wr.min_age_h:
            return f"{wr.window.lower().replace('_', '-')} window is open"
    return None


def need(job: Job, st: JobState, ctx: Ctx) -> Tuple[bool, str, bool]:
    """(needed, why, soft): soft = a SLA breach that waits for a quiet moment instead of starting now."""
    now = ctx.now
    if st.forced_at and (st.last_attempt_at is None or st.last_attempt_at < st.forced_at):
        return True, "its data is stale (freshness check): running now", False
    if st.retry_at and now >= st.retry_at:
        return True, f"retrying after {st.last_status or 'a failed run'} (attempt {st.consecutive_failures + 1})", False
    if st.last_success_at is None and job.catchup and not (job.boot and not ctx.config.boot_load_enabled):
        return True, "has never succeeded: catching up", False
    w = _window_hit(job, st, ctx)
    if w:
        return True, w, False
    age_min = _age_h(st, now) * 60
    allowed, override = _visitor_gate(job, ctx)
    probe = ctx.probes.get(job.probe) if job.probe else None
    if job.probe and probe is True and (st.last_attempt_at is None or _hours(now, st.last_attempt_at) * 60 >= job.min_gap_min) and _day_ok(job, now):
        return True, f"there is work waiting ({job.probe})", False
    interval = override or job.interval_min
    if interval and allowed and _day_ok(job, now) and in_active_hours(now, job.active_hours) and (not job.interval_market or market_hours(now)) \
            and age_min >= interval and not (job.probe and probe is False):
        return True, f"every {interval:g} minutes", False
    if job.daily_at and _day_ok(job, now):
        t = ist(now).replace(hour=job.daily_at[0], minute=job.daily_at[1], second=0, microsecond=0)
        if now >= t and (st.last_success_at is None or st.last_success_at < t):
            return True, f"daily run from {job.daily_at[0]:02d}:{job.daily_at[1]:02d} IST has not succeeded yet", False
    sla = sla_status(job, st, now)
    if sla.breached:
        if job.boot and not ctx.config.boot_load_enabled and sla.lateness_hours <= job.sla.hours:
            return False, "", False
        if open_windows(now) or not ctx.visitor_active or sla.lateness_hours > job.sla.hours:
            return True, f"SLA breached by {sla.lateness_hours:.1f} h", False
        return True, f"SLA breached by {sla.lateness_hours:.1f} h; waiting for a quiet moment (visitors are on the site)", True
    return False, "", False


def evaluate(job: Job, st: JobState, ctx: Ctx) -> Verdict:
    now = ctx.now
    off = disabled_reason(job, ctx.env)
    if off:
        return Verdict("disabled", off)
    if job.external:
        return Verdict("idle", "kept alive by deploy/scheduler.sh")
    if st.running:
        return Verdict("running", "running")
    if st.retry_at and now < st.retry_at:
        held = st.consecutive_failures >= job.max_attempts
        why = f"{'held after ' + str(st.consecutive_failures) + ' failures in a row; ' if held else ''}retry at {fmt_ist(st.retry_at)} after {st.last_status or 'a failed run'}"
        return Verdict("held" if held else "waiting", why, False, st.retry_at)
    needed, why, soft = need(job, st, ctx)
    if not needed:
        return Verdict("idle", "up to date", False, next_due_at(job, st, ctx))
    if job.honours_pause and ctx.pause:
        return Verdict("waiting", f"paused by the admin until {fmt_ist(ctx.pause.until)}; resumes automatically (wanted: {why})", False, ctx.pause.until)
    if soft:
        return Verdict("waiting", why, False, None)
    return Verdict("due", why, True, now)


def next_due_at(job: Job, st: JobState, ctx: Ctx) -> Optional[datetime]:
    """Best estimate of when the job next becomes due (for the status page); None when nothing is scheduled."""
    if job.external or disabled_reason(job, ctx.env):
        return None
    now = ctx.now
    cands: List[datetime] = []
    if st.retry_at and st.retry_at > now:
        cands.append(st.retry_at)
    base = st.last_success_at or now
    if job.interval_min:
        t = base + timedelta(minutes=job.interval_min)
        if job.active_hours and not in_active_hours(t, job.active_hours):
            t = next_active_start(t, job.active_hours)
        cands.append(max(t, now))
    for wr in job.windows:
        s = next_window_start(wr.window, now)
        for _ in range(9):
            t = s
            if wr.not_before:
                t = t.replace(hour=wr.not_before[0], minute=wr.not_before[1])
            if st.last_success_at and job.sla.kind != "session" and not job.probe:
                t = max(t, st.last_success_at + timedelta(hours=wr.min_age_h))
            if job.day_rule is None or job.day_rule(ist(t).date()):
                cands.append(t)
                break
            s += timedelta(days=1)
    if job.daily_at:
        d = ist(now).date()
        for k in range(9):
            t = datetime(d.year, d.month, d.day, job.daily_at[0], job.daily_at[1], tzinfo=IST) + timedelta(days=k)
            if t > now and (job.day_rule is None or job.day_rule(t.date())):
                cands.append(t)
                break
    sla = sla_status(job, st, now)
    if sla.deadline:
        cands.append(max(sla.deadline, now))
    return min(cands) if cands else None
