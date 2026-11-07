"""GET /api/jobs/status: public, read-only, no secrets. Is every background job and every dataset current, and if not, why."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .due import JobState, sla_status
from .pause import KEY as PAUSE_KEY, interpret
from .registry import JOBS_RULE, Job, build_jobs, disabled_reason
from .schedule import fmt_ist, ist
from .signals import BEAT_KEY, CANARY_KEY, FRESH_KEY
from .alerts import HEARTBEAT_STALE_S

router = APIRouter(prefix="/api/jobs")
_cache: Dict[str, Any] = {"t": 0.0, "body": None}


def _iso(t: Optional[datetime]) -> Optional[str]:
    return t.isoformat(timespec="seconds") if t else None


def short(reason: Optional[str]) -> Optional[str]:
    """A public-safe reason: our own sentence, not a log line."""
    if not reason:
        return None
    return reason.split(": ", 1)[0][:140] if reason.startswith(("failed", "exit code")) else reason[:200]


def job_row(job: Job, st: JobState, now: datetime, env: Mapping[str, str], paused: bool) -> Dict[str, Any]:
    off = disabled_reason(job, env)
    sla = sla_status(job, st, now)
    state, reason = (("disabled", off) if off else (st.state or "idle", st.state_reason))
    if job.external:
        state, reason = "idle", "always-on process kept alive by deploy/scheduler.sh"
    return {
        "name": job.name, "class": job.cls, "description": job.what, "priority": job.priority,
        "state": state, "reason": short(reason),
        "lastSuccessAt": _iso(st.last_success_at), "ageHours": round(sla.age_hours, 2) if sla.age_hours is not None else None,
        "slaHours": job.sla.hours or None, "slaKind": job.sla.kind, "slaDeadline": _iso(sla.deadline), "late": sla.breached and not off, "overdue": sla.overdue and not off and not job.external,
        "nextDueAt": _iso(st.next_due_at), "lastAttemptAt": _iso(st.last_attempt_at), "lastStatus": st.last_status,
        "consecutiveFailures": st.consecutive_failures, "retryAt": _iso(st.retry_at), "held": bool(st.held_until),
        "disabledByConfig": bool(off), "disabledReason": off, "honoursPause": job.honours_pause,
    }


NEAR_LIMIT_SHARE = 0.70      # a run that used this share of the time limit is "close"
NEAR_LIMIT_RUNS = 6          # the last runs looked at


def near_limit(job: Job, runs: list) -> Optional[Dict[str, Any]]:
    """Early warning for a job that is not resumable: `runs` are the newest (status, duration_s) of its finished runs, newest first. It is close to its
    limit when it hit the limit in one of the last three runs, or at least two of the recent runs used 70% or more of it. Shown to the admin as a note
    BEFORE the job starts failing; never an alert by itself. Resumable jobs and the always-on lanes are not judged (running long is their design)."""
    if job.resumable or job.cls == "ondemand" or not job.max_runtime_min:
        return None
    limit_s = job.max_runtime_min * 60.0
    recent = [(st, float(d)) for st, d in runs[:NEAR_LIMIT_RUNS] if d is not None]
    timed_out = bool(recent) and recent[0][0] == "timeout"   # the NEWEST run hit the limit; a good run since then means whatever caused it is over
    heavy = [d for _, d in recent if d / limit_s >= NEAR_LIMIT_SHARE]
    newest_heavy = bool(recent) and recent[0][1] / limit_s >= NEAR_LIMIT_SHARE
    if not timed_out and not (newest_heavy and len(heavy) >= 2):   # two heavy runs count only while the newest one is still heavy
        return None
    use = max((d for _, d in recent), default=0.0) / limit_s
    return {"name": job.name, "usePct": int(round(min(use, 1.0) * 100)), "limitMin": job.max_runtime_min, "timedOut": timed_out}


async def build(store: Any, redis: Any, now: Optional[datetime] = None, env: Optional[Mapping[str, str]] = None, admin: bool = False) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    env = os.environ if env is None else env
    jobs = build_jobs(env)
    out: Dict[str, Any] = {"asOf": _iso(now), "asOfIST": fmt_ist(now), "rule": JOBS_RULE}
    states: Dict[str, JobState] = {}
    db_ok, pause = True, None
    try:
        from .state import PgState
        states = await PgState(store.pool).load_all()
        async with store.pool.acquire() as conn:
            raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", PAUSE_KEY)
        pause, _ = interpret(raw, now)
    except Exception:
        db_ok = False
    recent_runs: Dict[str, list] = {}
    try:   # the newest finished runs of every job, for the early warning (a failed read just means no warning)
        async with store.pool.acquire() as conn:
            for r in await conn.fetch(
                    "SELECT job, status, duration_s FROM (SELECT job, status, duration_s, row_number() OVER (PARTITION BY job ORDER BY started_at DESC) AS rn "
                    "FROM job_runs WHERE status IN ('ok', 'timeout') AND started_at > now() - interval '14 days') t WHERE rn <= $1", NEAR_LIMIT_RUNS):
                recent_runs.setdefault(r["job"], []).append((r["status"], r["duration_s"]))
    except Exception:   # nosec B110
        pass
    beat: Dict[str, Any] = {}
    try:
        raw = await redis.get(BEAT_KEY)
        beat = json.loads(raw) if raw else {}
    except Exception:   # nosec B110
        pass
    age = (now.timestamp() - float(beat["at"])) if beat.get("at") else None
    alive = age is not None and age <= HEARTBEAT_STALE_S
    out["supervisor"] = {"alive": alive, "heartbeatAgeSeconds": int(age) if age is not None else None, "heartbeatAt": _iso(datetime.fromtimestamp(beat["at"], timezone.utc)) if beat.get("at") else None,
                         "running": beat.get("running", []), "dbOk": beat.get("dbOk"), "startedAt": _iso(datetime.fromtimestamp(beat["startedAt"], timezone.utc)) if beat.get("startedAt") else None}
    rows = [job_row(j, states.get(j.name) or JobState(job=j.name), now, env, bool(pause)) for j in jobs]
    out["jobs"] = rows
    overdue = [r["name"] for r in rows if r["overdue"]]
    failing = [r["name"] for r in rows if r["consecutiveFailures"] >= 3]
    out["overdue"] = overdue
    out["failing"] = failing
    out["degraded"] = [{"name": r["name"], "reason": r["reason"]} for r in rows if r["state"] == "degraded"]   # finished with the essential step done; an optional step did not work (not a failure)
    out["nearLimit"] = [w for w in (near_limit(j, recent_runs.get(j.name, [])) for j in jobs if not disabled_reason(j, env)) if w]
    out["disabledByConfig"] = [{"name": r["name"], "reason": r["disabledReason"]} for r in rows if r["disabledByConfig"] and not next(j for j in jobs if j.name == r["name"]).external]
    out["pause"] = {"paused": bool(pause), "until": _iso(pause.until) if pause else None, "untilIST": fmt_ist(pause.until) if pause else None,
                    "resumesAutomatically": True, "setBy": "admin" if pause else None, "legacy": bool(pause and pause.legacy),
                    "note": "Only the heavy bulk loads pause. Results, calendars, quotes, alerts and on-demand builds ignore the switch."}
    fresh: Optional[Dict[str, Any]] = None
    canary: Optional[Dict[str, Any]] = None
    try:
        raw = await redis.get(FRESH_KEY)
        fresh = json.loads(raw) if raw else None
        raw = await redis.get(CANARY_KEY)
        canary = json.loads(raw) if raw else None
    except Exception:   # nosec B110
        pass
    out["data"] = fresh or {"checkedAt": None, "dataFresh": None, "datasets": [], "note": "the freshness check has not run yet"}
    out["dataFresh"] = out["data"].get("dataFresh")
    out["canary"] = canary or {"checkedAt": None, "ok": None, "mismatches": [], "note": "the canary has not run yet"}
    out["system"] = (fresh or {}).get("system", {})
    cred = [c for c in (fresh or {}).get("credentials", [])]
    out["credentials"] = cred
    resultsLate = [r["name"] for r in rows if r["name"] in ("results", "results-light", "calendars") and (r["late"] or r["overdue"]) and not r["disabledByConfig"]]
    out["resultsDelayed"] = bool(resultsLate)
    out["healthy"] = bool(alive and db_ok and not overdue and not cred and out["canary"].get("ok") is not False and out["data"].get("dataFresh") is not False)
    out["healthNote"] = ("healthy" if out["healthy"] else "; ".join(x for x in (
        None if alive else "supervisor not reporting", None if db_ok else "database unreadable", f"overdue: {', '.join(overdue)}" if overdue else None,
        "credentials refused" if cred else None, "canary mismatch" if out["canary"].get("ok") is False else None,
        "stale data" if out["data"].get("dataFresh") is False else None) if x))
    if not admin:
        pass
    return out


@router.get("/status")
async def jobs_status(request: Request) -> Response:
    if time.time() - _cache["t"] > 10 or _cache["body"] is None:
        store = request.app.state.store
        body = await build(store, store.redis)
        _cache.update(t=time.time(), body=json.dumps(body, default=str))
    return Response(content=_cache["body"], media_type="application/json", headers={"Cache-Control": "no-store"})
