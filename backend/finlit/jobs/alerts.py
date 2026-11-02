"""Telling the founder without SSH: an in-app notification for every admin and an email, at most once per 6 hours per problem."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .signals import BEAT_KEY

log = logging.getLogger("finlit.jobs.alerts")
HEARTBEAT_STALE_S = 300


REMIND_S = 24 * 3600     # an unchanged problem is mentioned again once, after this long
WORSE_JUMP = 1.5        # a number in the text (companies, failures, hours) that grew by this factor, and by at least 10, is a material worsening


def _shape(text: str) -> str:
    """The text without its changing numbers: the same reason with different counts is one reason."""
    return " ".join("".join("#" if c.isdigit() else c for c in text).split())


def _numbers(text: str) -> List[int]:
    import re
    return [int(x) for x in re.findall(r"\d+", text)][:12]


def materially_changed(old_body: str, new_body: str) -> Optional[str]:
    """None when the new text is the same problem; else why it is worth another notification ('a new reason' or 'it got worse')."""
    if _shape(old_body) != _shape(new_body):
        return "the reason changed"
    for a, b in zip(_numbers(old_body), _numbers(new_body)):
        if b >= a * WORSE_JUMP and b - a >= 10:
            return "it got worse"
    return None


class Notifier:
    """One open alert per problem key. alert(key, subject, body) -> True when a notification went out: the first time, when the reason changed or the
    problem got materially worse, and as a single reminder after 24 hours of no change. resolve(key) closes it and sends a short 'resolved' notice."""

    def __init__(self, pool: Any, mailer: Any, redis: Any, site_url: str = "") -> None:
        self.pool, self.mailer, self.redis, self.site_url = pool, mailer, redis, site_url.rstrip("/")
        self._deduped = False

    async def admins(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            return [dict(r) for r in await conn.fetch("SELECT id, email FROM users WHERE role = 'admin' AND status = 'active'")]

    async def dedupe(self) -> int:
        """Idempotent: of the unread system notifications with the same title for one person, only the newest stays (older repeats are removed)."""
        async with self.pool.acquire() as conn:
            res = await conn.execute("DELETE FROM notifications n USING notifications m WHERE n.kind = 'system' AND m.kind = 'system' AND n.user_id = m.user_id AND n.title = m.title "
                                     "AND n.read_at IS NULL AND m.read_at IS NULL AND n.id < m.id")
        return int(res.split()[-1])

    async def open_keys(self) -> List[str]:
        async with self.pool.acquire() as conn:
            return [r["key"] for r in await conn.fetch("SELECT key FROM admin_alerts WHERE resolved_at IS NULL")]

    async def _send(self, subject: str, body: str) -> None:
        try:
            admins = await self.admins()
        except Exception:
            log.exception("could not read the admin list for the alert %s", subject)
            return
        link = f"{self.site_url}/console" if self.site_url else "/console"
        for a in admins:
            try:
                async with self.pool.acquire() as conn:
                    # the bell keeps one unread notification per title: a repeat replaces the older one instead of piling up
                    await conn.execute("DELETE FROM notifications WHERE user_id = $1 AND kind = 'system' AND title = $2 AND read_at IS NULL", a["id"], subject[:200])
                    await conn.execute("INSERT INTO notifications (user_id, kind, title, body, link, push) VALUES ($1, 'system', $2, $3, '/console', false)", a["id"], subject[:200], body[:1000])
            except Exception:
                log.exception("in-app notification failed")
            try:
                await self.mailer.send(a["email"], f"[FinLit] {subject}", f"{body}\n\nOpen the admin console: {link}\n(Data health tab). You get one message per problem, another only if it changes or after 24 hours, and one when it is resolved.")
            except Exception:
                log.exception("alert email failed")

    async def alert(self, key: str, subject: str, body: str, now: Optional[datetime] = None) -> bool:
        if not self._deduped:
            self._deduped = True
            try:
                await self.dedupe()
            except Exception:
                log.exception("could not collapse duplicate notifications")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT subject, body, last_sent_at FROM admin_alerts WHERE key = $1 AND resolved_at IS NULL", key)
            if row is None:
                await conn.execute("INSERT INTO admin_alerts (key, subject, body) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET subject = EXCLUDED.subject, body = EXCLUDED.body, "
                                   "opened_at = now(), last_sent_at = now(), sent_count = 1, resolved_at = NULL", key, subject, body)
                prefix = ""
            else:
                why = materially_changed(row["body"], body)
                age = (datetime.now(row["last_sent_at"].tzinfo) - row["last_sent_at"]).total_seconds()
                if why is None and age < REMIND_S:
                    return False                                   # the same problem, already reported: nothing new to say
                prefix = f"Update ({why}): " if why else "Reminder, still open after 24 hours: "
                await conn.execute("UPDATE admin_alerts SET body = $2, last_sent_at = now(), sent_count = sent_count + 1 WHERE key = $1", key, body)
        log.warning("ALERT %s: %s", key, subject)
        await self._send(subject, prefix + body)
        return True

    async def resolve(self, key: str) -> bool:
        """The problem is over: close it and send a short 'resolved' notice (once). False when it was not open."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("UPDATE admin_alerts SET resolved_at = now() WHERE key = $1 AND resolved_at IS NULL RETURNING subject", key)
        if row is None:
            return False
        await self._send(f"Resolved: {row['subject']}", f"{row['subject']} is resolved. The data jobs report no problem for this any more.")
        return True

    async def clear(self, key: str) -> None:
        await self.resolve(key)


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
            else:
                n = Notifier(store.pool, app.state.mailer, store.redis, getattr(app.state.settings, "public_site_url", ""))
                await n.resolve("supervisor")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("supervisor watch failed")
