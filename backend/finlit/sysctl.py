"""Admin-only site controls: pause or resume the heavy background loads, restart the site, and a plain status (memory, uptime).

The loads switch lives in mf_meta ('switch:loads'), so it survives restarts and redeploys. deploy/scheduler.sh reads it with
`python -m finlit.worker switch-get loads` before the boot-load and before every nightly job.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from datetime import datetime, timezone

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
    """True when the heavy loads may run (no row yet = on). Unreadable database: the caller's decision, see worker switch-get."""
    async with pool.acquire() as conn:
        raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", LOADS_KEY)
    val = json.loads(raw) if isinstance(raw, str) else raw
    return bool(val.get("enabled", True)) if isinstance(val, dict) else True


async def switch_get(dsn_settings, name: str) -> int:
    """Prints-ready 1/0 for the scheduler. Safe default when the database cannot be read: the web-facing flags stay ON (a database blip must not
    switch the site's features off), but the heavy loads read as PAUSED (a failing database is no moment to start 512 MB of loading)."""
    import asyncpg
    from .store import prepare_dsn
    default = 0 if name == "loads" else 1
    try:
        dsn, extra = prepare_dsn(dsn_settings.database_url)
        conn = await asyncpg.connect(dsn, timeout=10, command_timeout=10, **extra)
        try:
            raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", "switch:" + name)
        finally:
            await conn.close()
    except Exception:
        return default
    val = json.loads(raw) if isinstance(raw, str) else raw
    return 1 if not isinstance(val, dict) or val.get("enabled", True) else 0


async def _body(pool) -> dict:
    on = True
    try:
        on = await loads_enabled(pool)
    except Exception:
        on = False
    return {"loadsEnabled": on, "bootEnvOff": os.environ.get("BOOT_LOAD_ENABLED", "1") != "1", "fundEnvOff": os.environ.get("FUND_LOADS_ENABLED", "0") != "1", "memory": memory(), "uptimeSeconds": int(time.monotonic() - _T0),
            "startedAt": STARTED_AT.isoformat(timespec="seconds")}


def _json(body: dict, status: int = 200) -> Response:
    return Response(content=json.dumps(body), status_code=status, media_type="application/json", headers=NO_STORE)


@router.get("/status")
async def status(request: Request, ctx: Ctx = Depends(admin_ctx)):
    return _json(await _body(request.app.state.store.pool))


@router.post("/loads")
async def set_loads(request: Request, body: LoadsIn, ctx: Ctx = Depends(admin_ctx)):
    pool = request.app.state.store.pool
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                           LOADS_KEY, json.dumps({"enabled": body.enabled, "by": ctx.user_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    await audit(pool, ctx.user_id, "admin_loads_resumed" if body.enabled else "admin_loads_paused", "loads", ip_of(request))
    return _json(await _body(pool))


@router.post("/restart")
async def restart(request: Request, ctx: Ctx = Depends(admin_ctx)):
    await audit(request.app.state.store.pool, ctx.user_id, "admin_restart", "site", ip_of(request))
    asyncio.get_running_loop().call_later(1.0, lambda: _exit_process())   # answer 202 first; the exit is looked up at call time
    return _json({"ok": True, "restartingInSeconds": 1}, 202)
