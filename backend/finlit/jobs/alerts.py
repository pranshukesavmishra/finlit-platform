"""Telling the founder without SSH: an in-app notification for every admin and an email, at most once per 6 hours per problem."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .signals import BEAT_KEY, ALERT_PREFIX

log = logging.getLogger("finlit.jobs.alerts")
RATE_S = 6 * 3600
HEARTBEAT_STALE_S = 300


class Notifier:
    """alert(key, subject, body) -> True when it was sent (False when this problem was already reported in the last 6 hours)."""

    def __init__(self, pool: Any, mailer: Any, redis: Any, site_url: str = "") -> None:
        self.pool, self.mailer, self.redis, self.site_url = pool, mailer, redis, site_url.rstrip("/")
        self._local: Dict[str, float] = {}

    async def _first(self, key: str) -> bool:
        try:
            return bool(await self.redis.set(ALERT_PREFIX + key, "1", nx=True, ex=RATE_S))
        except Exception:   # Redis down: rate limit in this process instead of staying silent
            t = time.time()
            if t - self._local.get(key, 0) < RATE_S:
                return False
            self._local[key] = t
            return True

    async def admins(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch("SELECT id, email FROM users WHERE role = 'admin' AND status = 'active'")]

    async def alert(self, key: str, subject: str, body: str, now: Optional[datetime] = None) -> bool:
        if not await self._first(key):
            return False
        log.warning("ALERT %s: %s", key, subject)
        try:
            admins = await self.admins()
        except Exception:
            log.exception("could not read the admin list for the alert %s", key)
            return True
        link = f"{self.site_url}/console" if self.site_url else "/console"
        for a in admins:
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute("INSERT INTO notifications (user_id, kind, title, body, link, push) VALUES ($1, 'system', $2, $3, '/console', false)", a["id"], subject[:200], body[:1000])
            except Exception:
                log.exception("in-app notification failed")
            try:
                await self.mailer.send(a["email"], f"[FinLit] {subject}", f"{body}\n\nOpen the admin console: {link}\n(Data health tab). This alert repeats at most every 6 hours while the problem lasts.")
            except Exception:
                log.exception("alert email failed")
        return True


async def supervisor_problem(redis: Any, now: float, started_grace_s: float = 0.0) -> Optional[str]:
    """None when the supervisor's heartbeat is fresh; otherwise a sentence saying what is wrong."""
    import json
    try:
        raw = await redis.get(BEAT_KEY)
    except Exception:
        return None     # cannot read Redis: the web process has bigger problems than this alert
    if not raw:
        return "The job supervisor has never reported in (no heartbeat). Background data jobs are not running." if started_grace_s <= 0 else None
    age = now - float(json.loads(raw).get("at", 0))
    if age > HEARTBEAT_STALE_S:
        return f"The job supervisor's last heartbeat is {int(age // 60)} minutes old. Background data jobs have stopped; the container's start script should restart it. If this stays, run: docker compose restart app"
    return None


async def watch_supervisor(app: Any, interval_s: float = 120.0, grace_s: float = 600.0) -> None:
    """A tiny task in the web process: if the supervisor's heartbeat goes stale it alerts (the supervisor cannot report its own death)."""
    t0 = time.time()
    while True:
        try:
            await asyncio.sleep(interval_s)
            store = app.state.store
            problem = await supervisor_problem(store.redis, time.time(), started_grace_s=max(0.0, grace_s - (time.time() - t0)))
            if problem:
                n = Notifier(store.pool, app.state.mailer, store.redis, getattr(app.state.settings, "public_site_url", ""))
                await n.alert("supervisor", "FinLit background jobs are not running", problem)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("supervisor watch failed")
