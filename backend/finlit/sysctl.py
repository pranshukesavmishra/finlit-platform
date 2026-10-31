"""Admin-only site controls: pause or resume the heavy background loads, restart the site, and a plain status (memory, uptime).

The loads switch lives in mf_meta ('switch:loads'), so it survives restarts and redeploys. It is a TIME-BOXED PAUSE (finlit/jobs/pause.py): 30 minutes by
default, 2 h or 12 h on request, and the loads resume by themselves at the expiry. The job supervisor (finlit/jobs) reads it every tick;
`python -m finlit.worker switch-get loads` still prints 1 (running) or 0 (paused) for manual use.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .auth.routes import NO_STORE, Ctx, admin_ctx, fail, ip_of
from .auth.service import audit

router = APIRouter(prefix="/api/admin/system")
LOADS_KEY = "switch:loads"
STARTED_AT = datetime.now(timezone.utc)
_T0 = time.monotonic()


class LoadsIn(BaseModel):
    enabled: bool
    minutes: Optional[int] = None          # pause length; 30 when omitted
    confirmLong: bool = False              # required for a pause longer than 12 hours


def _exit_process() -> None:
    """Ends the whole container's process group with SIGTERM (uvicorn drains in-flight requests first); Render then starts a fresh instance.
    Fixed signal, no shell, no input. Tests replace this function."""
    os.killpg(os.getpgrp(), signal.SIGTERM)


def _mib(kb: int) -> int:
    return int(kb // 1024)


def memory() -> dict:
    """Used / available memory of this container in MB: the cgroup limit when there is one, else the machine's /proc/meminfo."""
    try:
        for cur_p, max_p, stat_p, key in (("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.stat", "inactive_file"),
                                          ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "/sys/fs/cgroup/memory/memory.limit_in_bytes",
                                           "/sys/fs/cgroup/memory/memory.stat", "total_inactive_file")):
            if os.path.exists(cur_p) and os.path.exists(max_p):
                mx, cur = open(max_p).read().strip(), int(open(cur_p).read())
                if mx.isdigit() and len(mx) < 16:
                    inactive = 0
                    for line in open(stat_p):
                        k, _, v = line.partition(" ")
                        if k == key:
                            inactive = int(v)
                    used = max(cur - inactive, 0)
                    return {"totalMb": int(mx) // 1048576, "usedMb": used // 1048576, "availableMb": max(int(mx) - used, 0) // 1048576}
        info = {}
        for line in open("/proc/meminfo"):
            k, _, v = line.partition(":")
            info[k] = int(v.split()[0])
        return {"totalMb": _mib(info["MemTotal"]), "usedMb": _mib(info["MemTotal"] - info["MemAvailable"]), "availableMb": _mib(info["MemAvailable"])}
    except Exception:
        return {"totalMb": None, "usedMb": None, "availableMb": None}


async def loads_enabled(pool) -> bool:
    """True when the heavy loads may run (no row yet = on; an expired pause = on). Unreadable database: the caller's decision, see worker switch-get."""
    from .jobs.pause import read_pause
    async with pool.acquire() as conn:
        return await read_pause(conn, datetime.now(timezone.utc)) is None


async def switch_get(dsn_settings, name: str) -> int:
    """Prints-ready 1/0 for the scheduler. Safe default when the database cannot be read: the web-facing flags stay ON (a database blip must not
    switch the site's features off), but the heavy loads read as PAUSED (a failing database is no moment to start 512 MB of loading)."""
    import asyncpg
    from .store import prepare_dsn
    explicit = name == "loads-explicit"   # the light results jobs: only an admin's "off" pauses them, not a database that was slow to answer
    if explicit:
        name = "loads"
    default = 0 if name == "loads" and not explicit else 1
    try:
        dsn, extra = prepare_dsn(dsn_settings.database_url)
        conn = await asyncpg.connect(dsn, timeout=10, command_timeout=10, **extra)
        try:
            raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", "switch:" + name)
        finally:
            await conn.close()
    except Exception:
        return default
    from .jobs.pause import interpret
    info, _ = interpret(raw, datetime.now(timezone.utc))
    return 0 if info is not None else 1


async def _body(pool) -> dict:
    on, until, by, legacy = True, None, None, False
    try:
        from .jobs.pause import read_pause
        async with pool.acquire() as conn:
            info = await read_pause(conn, datetime.now(timezone.utc))
        on = info is None
        if info:
            until, by, legacy = info.until, info.by, info.legacy
    except Exception:
        on = False
    from .jobs.schedule import fmt_ist
    return {"loadsEnabled": on, "pausedUntil": until.isoformat(timespec="seconds") if until else None, "pausedUntilIST": fmt_ist(until) if until else None,
            "pausedBy": by, "pauseWasLegacy": legacy, "resumesAutomatically": True, "pauseChoicesMinutes": [30, 120, 720], "bootEnvOff": os.environ.get("BOOT_LOAD_ENABLED", "1") != "1", "fundEnvOff": os.environ.get("FUND_LOADS_ENABLED", "0") != "1", "memory": memory(), "uptimeSeconds": int(time.monotonic() - _T0),
            "startedAt": STARTED_AT.isoformat(timespec="seconds")}


def _json(body: dict, status: int = 200) -> Response:
    return Response(content=json.dumps(body), status_code=status, media_type="application/json", headers=NO_STORE)


@router.get("/status")
async def status(request: Request, ctx: Ctx = Depends(admin_ctx)):
    return _json(await _body(request.app.state.store.pool))


@router.post("/loads")
async def set_loads(request: Request, body: LoadsIn, ctx: Ctx = Depends(admin_ctx)):
    from .jobs import pause as pausemod
    pool = request.app.state.store.pool
    minutes = body.minutes if body.minutes is not None else pausemod.DEFAULT_MINUTES
    if not body.enabled:
        if minutes < 1 or minutes > 7 * 24 * 60:
            raise fail(422, "bad_minutes", "Choose a pause between 1 minute and 7 days.")
        if minutes > pausemod.MAX_MINUTES and not body.confirmLong:
            raise fail(422, "confirm_long_pause", "A pause longer than 12 hours needs to be confirmed. Loads normally resume by themselves; a long pause leaves the data to go stale.")
    async with pool.acquire() as conn:
        email = await conn.fetchval("SELECT email FROM users WHERE id = $1", ctx.user_id)
        await pausemod.set_pause(conn, datetime.now(timezone.utc), body.enabled, minutes, email or str(ctx.user_id))
    await audit(pool, ctx.user_id, "admin_loads_resumed" if body.enabled else "admin_loads_paused", "loads" if body.enabled else f"loads:{minutes}min", ip_of(request))
    return _json(await _body(pool))


@router.post("/restart")
async def restart(request: Request, ctx: Ctx = Depends(admin_ctx)):
    await audit(request.app.state.store.pool, ctx.user_id, "admin_restart", "site", ip_of(request))
    asyncio.get_running_loop().call_later(1.0, lambda: _exit_process())   # answer 202 first; the exit is looked up at call time
    return _json({"ok": True, "restartingInSeconds": 1}, 202)
