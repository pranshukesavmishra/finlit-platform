"""Admin buttons for the ETF and mutual fund loads (the scheduled ones are paused by FUND_LOADS_ENABLED).

POST /api/admin/funds/run starts `python -m finlit.fundjobs <job>` detached. That runner takes the same lock file the scheduler uses
(/tmp/finlit-funds.lock), runs the worker command and records one line in mf_meta ("admin-fund:<job>"). The job name comes from a fixed list.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import subprocess  # nosec B404 - fixed argument list, no shell
import sys
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .auth.routes import NO_STORE, Ctx, admin_ctx, fail, ip_of
from .auth.service import audit

router = APIRouter(prefix="/api/admin/funds")
FUNDS_LOCK = os.environ.get("FUNDS_LOCK", "/tmp/finlit-funds.lock")  # nosec B108 - same fixed path as deploy/scheduler.sh
JOBS = {"refresh-etf": ["refresh-etf"], "refresh-mf": ["refresh-mf"], "backfill-mf": ["backfill-mf"]}
Job = Literal["refresh-etf", "refresh-mf", "backfill-mf"]


class RunIn(BaseModel):
    job: Job


def lock_busy() -> bool:
    """True when some fund job (scheduled or started here) holds the lock."""
    try:
        fd = os.open(FUNDS_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


async def _meta(pool, key: str):
    try:
        async with pool.acquire() as conn:
            raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", key)
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None


async def _set(pool, job: str, value: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                           "admin-fund:" + job, json.dumps(value, default=str))


@router.get("/status")
async def status(request: Request, ctx: Ctx = Depends(admin_ctx)):
    pool = request.app.state.store.pool
    jobs = {j: await _meta(pool, "admin-fund:" + j) for j in JOBS}
    body = {"running": lock_busy(), "scheduledPaused": os.environ.get("FUND_LOADS_ENABLED", "0") != "1", "jobs": jobs}
    return Response(content=json.dumps(body), media_type="application/json", headers=NO_STORE)


@router.post("/run")
async def run(request: Request, body: RunIn, ctx: Ctx = Depends(admin_ctx)):
    pool = request.app.state.store.pool
    if lock_busy():
        raise fail(409, "busy", "A fund data load is already running. Wait for it to finish.")
    await audit(pool, ctx.user_id, "admin_fund_load_started", body.job, ip_of(request))
    await _set(pool, body.job, {"state": "starting", "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    env = {**os.environ, "MALLOC_ARENA_MAX": "2"}
    subprocess.Popen([sys.executable, "-m", "finlit.fundjobs", body.job], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,  # nosec B603
                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    return Response(content=json.dumps({"ok": True, "job": body.job}), media_type="application/json", headers=NO_STORE)


async def _runner(job: str) -> int:
    from .config import Settings
    from .store import Store
    fd = os.open(FUNDS_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return 3
    store = await Store.connect(Settings())
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        await _set(store.pool, job, {"state": "running", "startedAt": started})
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "finlit.worker", *JOBS[job], stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, env={**os.environ, "MALLOC_ARENA_MAX": "2"})
        out, _ = await proc.communicate()
        last = (out.decode("utf-8", "replace").strip().splitlines() or [""])[-1][:300]
        await _set(store.pool, job, {"state": "done" if proc.returncode == 0 else "failed", "rc": proc.returncode, "startedAt": started,
                                     "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": last})
        return proc.returncode or 0
    finally:
        await store.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        sys.exit(2)
    sys.exit(asyncio.run(_runner(sys.argv[1])))
