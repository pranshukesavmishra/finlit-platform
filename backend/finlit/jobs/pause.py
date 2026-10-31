"""The admin switch "Heavy data loads" as a TIME-BOXED pause (mf_meta 'switch:loads').

An admin pauses for 30 minutes (default), 2 hours or 12 hours; at the expiry the supervisor resumes the loads by itself, nobody has to remember. A pause
longer than 12 hours is refused without an explicit confirmation. The light jobs (results, calendars, quotes, alerts) and the on-demand lane ignore the pause.
A row from before this change ("off" with no expiry) is read as a pause until 30 minutes after it was first seen, and that is logged: an old forgotten "off"
can never again hold the loads for days.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .due import PauseInfo

log = logging.getLogger("finlit.jobs.pause")
KEY = "switch:loads"
DEFAULT_MINUTES = 30
CHOICES = (30, 120, 720)
MAX_MINUTES = 720


def _val(raw: Any) -> Optional[Dict[str, Any]]:
    v = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    return v if isinstance(v, dict) else None


def _t(s: Any) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def interpret(raw: Any, now: datetime) -> Tuple[Optional[PauseInfo], Optional[Dict[str, Any]]]:
    """(the pause in force or None, the row to write back or None). Pure."""
    v = _val(raw)
    if v is None or v.get("enabled", True):
        return None, None
    until = _t(v.get("pausedUntil"))
    since = _t(v.get("at"))
    if until is None:   # a row written before pauses had an expiry
        until = now + timedelta(minutes=DEFAULT_MINUTES)
        return PauseInfo(until, v.get("by"), since, legacy=True), {**v, "pausedUntil": until.isoformat(timespec="seconds"), "legacy": True}
    if until <= now:
        return None, {**v, "enabled": True, "resumedAuto": True, "resumedAt": now.isoformat(timespec="seconds")}
    return PauseInfo(until, v.get("by"), since), None


async def read_pause(conn: Any, now: datetime) -> Optional[PauseInfo]:
    """Reads the switch and applies the two automatic changes (expiry, legacy migration). Raises on an unreadable database."""
    raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", KEY)
    info, write = interpret(raw, now)
    if write is not None:
        try:
            await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()", KEY, json.dumps(write))
            if info is None:
                log.info("heavy data loads resumed automatically: the pause expired")
            else:
                log.warning("heavy data loads: an old 'off' switch with no expiry was found; treated as paused until %s and it resumes by itself", info.until.isoformat(timespec="minutes"))
        except Exception:   # a read-only database role: the answer is still right (computed from the stored row); only the tidy-up write is skipped
            log.warning("could not write back the pause state")
    return info


async def set_pause(conn: Any, now: datetime, enabled: bool, minutes: Optional[int], by: Optional[str]) -> Dict[str, Any]:
    val: Dict[str, Any] = {"enabled": enabled, "by": by, "at": now.isoformat(timespec="seconds")}
    if not enabled:
        val["minutes"] = minutes or DEFAULT_MINUTES
        val["pausedUntil"] = (now + timedelta(minutes=val["minutes"])).isoformat(timespec="seconds")
    await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()", KEY, json.dumps(val))
    return val


class PgPause:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def current(self, now: datetime) -> Optional[PauseInfo]:
        async with self.pool.acquire() as conn:
            return await read_pause(conn, now)
