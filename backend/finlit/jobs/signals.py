"""Everything the supervisor reads from or writes to Redis, and the real clock. The tests use in-memory twins (tests/jobs_fakes.py)."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

LOCK_KEY = "jobs:supervisor:lock"
BEAT_KEY = "jobs:supervisor"
FRESH_KEY = "jobs:freshness"
CANARY_KEY = "jobs:canary"
ALERT_PREFIX = "jobs:alert:"
CRED_PREFIX = "jobs:cred:"
LOCK_TTL = 180


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class RedisSignals:
    def __init__(self, redis: Any, port: int = 8000) -> None:
        self.redis, self.port, self.token = redis, port, uuid.uuid4().hex

    # --- one supervisor at a time
    async def acquire_lock(self) -> bool:
        return bool(await self.redis.set(LOCK_KEY, self.token, nx=True, ex=LOCK_TTL))

    async def refresh_lock(self) -> bool:
        cur = await self.redis.get(LOCK_KEY)
        cur = cur.decode() if isinstance(cur, bytes) else cur
        if cur == self.token:
            await self.redis.expire(LOCK_KEY, LOCK_TTL)
            return True
        return bool(await self.redis.set(LOCK_KEY, self.token, nx=True, ex=LOCK_TTL))   # expired meanwhile and nobody took it: take it again

    async def release_lock(self) -> None:
        cur = await self.redis.get(LOCK_KEY)
        cur = cur.decode() if isinstance(cur, bytes) else cur
        if cur == self.token:
            await self.redis.delete(LOCK_KEY)

    # --- liveness
    async def heartbeat(self, now: datetime, info: Dict[str, Any]) -> None:
        await self.redis.set(BEAT_KEY, json.dumps({**info, "at": now.timestamp()}), ex=7 * 86400)
        await self.redis.set("scheduler:alive", str(now.timestamp()), ex=7 * 86400)   # the key /api/results/status has always shown as schedulerAliveAt

    # --- the facts the due rules ask for
    async def visitor_active(self) -> bool:
        from .. import wake
        return await wake.visitor_active(self.redis)

    async def alerts_active(self) -> bool:
        from .. import wake
        return await wake.alerts_active(self.redis)

    async def web_up(self) -> bool:
        def probe() -> bool:
            import urllib.request
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/ping", timeout=3)  # nosec B310 - fixed local URL
                return True
            except Exception:
                return False
        return await asyncio.get_running_loop().run_in_executor(None, probe)

    # --- compatibility notes and the "jobs started" list shown at /api/results/status
    async def note(self, name: str, why: str) -> None:
        from .. import wake
        await self.redis.set(wake.NOTE_PREFIX + name, json.dumps({"at": datetime.now(wake.IST).isoformat(timespec="seconds"), "why": why[:200]}), ex=3 * 86400)

    async def job_started(self, name: str, now: datetime) -> None:
        from .. import wake
        await wake.job_started(self.redis, name, now.timestamp())

    # --- reports for the public status
    async def set_json(self, key: str, value: Any, ttl: int = 7 * 86400) -> None:
        await self.redis.set(key, json.dumps(value, default=str), ex=ttl)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.redis.get(key)
        return json.loads(raw) if raw else None

    async def once_per(self, key: str, seconds: int) -> bool:
        """True the first time in `seconds` (rate limiting an alert per problem)."""
        return bool(await self.redis.set(ALERT_PREFIX + key, "1", nx=True, ex=seconds))

    async def credential_refused(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        async for k in self.redis.scan_iter(match=CRED_PREFIX + "*"):
            k = k.decode() if isinstance(k, bytes) else k
            v = await self.redis.get(k)
            out[k[len(CRED_PREFIX):]] = (v.decode() if isinstance(v, bytes) else str(v or ""))
        return out


async def mark_credential_refused(redis: Any, which: str, detail: str = "") -> None:
    """Called by the provider clients when a key is refused (HTTP 401/403). Never raises. Cleared by the next successful canary/probe."""
    try:
        await redis.set(CRED_PREFIX + which, (detail or "refused")[:120], ex=6 * 3600)
    except Exception:   # nosec B110 - Redis trouble must not break a data call
        pass


async def clear_credential(redis: Any, which: str) -> None:
    try:
        await redis.delete(CRED_PREFIX + which)
    except Exception:   # nosec B110
        pass


def now_epoch() -> float:
    return time.time()


def pid() -> int:
    return os.getpid()


_reported: Dict[str, float] = {}


async def report_refused(settings: Any, which: str, status: int) -> None:
    """A provider refused our key (HTTP 401/403). Remembered in Redis for the admin alert 'The Dhan / FinEdge key is not accepted'. At most one write per
    10 minutes per process; never raises (a data call must not fail because of the alert)."""
    t = time.time()
    if t - _reported.get(which, 0) < 600:
        return
    _reported[which] = t
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        try:
            await mark_credential_refused(r, which, f"HTTP {status}")
        finally:
            await r.aclose()
    except Exception:   # nosec B110
        pass
