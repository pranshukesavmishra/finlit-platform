"""Job history (job_runs) and current state (job_state) in Postgres, plus an in-memory twin with the same methods for tests and dry runs."""
from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .due import JobState

PERSISTED = ("first_seen_at", "last_success_at", "last_attempt_at", "last_status", "next_due_at", "consecutive_failures", "retry_at", "held_until",
             "held_reason", "forced_at", "forced_attempts", "state", "state_reason")


class MemoryState:
    def __init__(self) -> None:
        self.states: Dict[str, JobState] = {}
        self.runs: List[Dict[str, Any]] = []

    async def ensure(self, names: Iterable[str], now: datetime) -> None:
        for n in names:
            self.states.setdefault(n, JobState(job=n, first_seen_at=now))

    async def load_all(self) -> Dict[str, JobState]:
        return {k: JobState(**{f.name: getattr(v, f.name) for f in fields(JobState)}) for k, v in self.states.items()}

    async def save(self, st: JobState) -> None:
        self.states[st.job] = JobState(**{f.name: getattr(st, f.name) for f in fields(JobState)})

    async def start_run(self, job: str, now: datetime, attempt: int, pid: Optional[int]) -> int:
        self.runs.append({"id": len(self.runs) + 1, "job": job, "started_at": now, "finished_at": None, "status": "running", "reason": None,
                          "attempt": attempt, "exit_code": None, "duration_s": None, "peak_rss_mb": None, "pid": pid, "counts": {}})
        return len(self.runs)

    async def finish_run(self, run_id: int, now: datetime, status: str, reason: Optional[str], exit_code: Optional[int], duration_s: float,
                         peak_rss_mb: Optional[int], counts: Dict[str, Any]) -> None:
        r = self.runs[run_id - 1]
        r.update(finished_at=now, status=status, reason=reason, exit_code=exit_code, duration_s=duration_s, peak_rss_mb=peak_rss_mb, counts=counts)

    async def record_skip(self, job: str, now: datetime, reason: str) -> None:
        self.runs.append({"id": len(self.runs) + 1, "job": job, "started_at": now, "finished_at": now, "status": "skipped", "reason": reason,
                          "attempt": 0, "exit_code": None, "duration_s": 0, "peak_rss_mb": None, "pid": None, "counts": {}})

    async def prune_runs(self, now: datetime, days: int) -> None:
        self.runs = [r for r in self.runs if r["status"] == "running" or r["started_at"] > now - timedelta(days=days)]

    async def running_runs(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.runs if r["status"] == "running"]

    async def recent_runs(self, limit: int = 40, job: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [dict(r) for r in reversed(self.runs) if job is None or r["job"] == job]
        return rows[:limit]


class PgState:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def ensure(self, names: Iterable[str], now: datetime) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany("INSERT INTO job_state (job, first_seen_at) VALUES ($1, $2) ON CONFLICT (job) DO NOTHING", [(n, now) for n in names])

    async def load_all(self) -> Dict[str, JobState]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT job, {', '.join(PERSISTED)} FROM job_state")  # nosec B608 - fixed column names
        return {r["job"]: JobState(job=r["job"], **{k: r[k] for k in PERSISTED}) for r in rows}

    async def save(self, st: JobState) -> None:
        cols = ", ".join(PERSISTED)
        marks = ", ".join(f"${i + 2}" for i in range(len(PERSISTED)))
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in PERSISTED if c != "first_seen_at")
        async with self.pool.acquire() as conn:
            await conn.execute(f"INSERT INTO job_state (job, {cols}) VALUES ($1, {marks}) ON CONFLICT (job) DO UPDATE SET {sets}, updated_at = now()",  # nosec B608 - fixed column names
                               st.job, *[getattr(st, c) for c in PERSISTED])

    async def start_run(self, job: str, now: datetime, attempt: int, pid: Optional[int]) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("INSERT INTO job_runs (job, started_at, status, attempt, pid) VALUES ($1, $2, 'running', $3, $4) RETURNING id", job, now, attempt, pid)

    async def finish_run(self, run_id: int, now: datetime, status: str, reason: Optional[str], exit_code: Optional[int], duration_s: float,
                         peak_rss_mb: Optional[int], counts: Dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE job_runs SET finished_at = $2, status = $3, reason = $4, exit_code = $5, duration_s = $6, peak_rss_mb = $7, counts = $8::jsonb WHERE id = $1",
                               run_id, now, status, reason, exit_code, duration_s, peak_rss_mb, json.dumps(counts))

    async def record_skip(self, job: str, now: datetime, reason: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO job_runs (job, started_at, finished_at, status, reason, attempt, duration_s) VALUES ($1, $2, $2, 'skipped', $3, 0, 0)", job, now, reason)

    async def prune_runs(self, now: datetime, days: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM job_runs WHERE status <> 'running' AND started_at < $1", now - timedelta(days=days))

    async def running_runs(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch("SELECT id, job, pid, started_at, attempt FROM job_runs WHERE status = 'running'")]

    async def recent_runs(self, limit: int = 40, job: Optional[str] = None) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, job, started_at, finished_at, status, reason, attempt, exit_code, duration_s, peak_rss_mb, counts FROM job_runs "
                                    "WHERE ($2::text IS NULL OR job = $2) ORDER BY id DESC LIMIT $1", limit, job)
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("counts"), str):
                d["counts"] = json.loads(d["counts"])
            out.append(d)
        return out
