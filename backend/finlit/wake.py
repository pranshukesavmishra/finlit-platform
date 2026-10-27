"""Keeps the metered database (Neon free plan) asleep whenever nobody needs it.

Neon's compute stops about 5 minutes after the last query, and the free plan allows a fixed number of compute hours a month. Anything that
touches Postgres on a timer keeps it awake, so all timer-driven database work is grouped into a few "DB windows" a day (deploy/scheduler.sh) and
the few jobs that run outside a window first ask this module, using Redis only (Redis is not metered):

  * `last-visit`      set by the web app when a visitor (not a health check) is on the site; "visitor active" = within the last 15 minutes.
  * `alerts-active`   whether any member alert or watchlist target exists; refreshed inside every window and raised when a member creates one.
  * the wake budget   an estimate of how often Postgres was woken today and how many compute hours this month used, from the start and end
                      of every database job and of visitor activity. It is an ESTIMATE of Neon's own meter (Neon's Usage page is the authority).

Command line (all but `refresh-alerts` need Redis only): `python -m finlit.wake visit-active|alerts-active|flag-get|flag-set|start|end|stats|refresh-alerts`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
K_VISIT = "wake:last-visit"
K_ALERTS = "wake:alerts-active"
K_RUNNING = "wake:running"        # how many database jobs are running now (expires by itself if a job dies without ending)
K_ACC = "wake:acc"                # the time up to which awake minutes are already counted
TAIL_MIN = 5.0                    # Neon suspends the compute after about 5 minutes without a query
VISIT_MINUTES = 15                # a visitor counts as "on the site" for this long after the last page request
VISIT_WRITE_EVERY = 20.0          # seconds between Redis writes from the web app
ACCOUNT_EVERY = 60.0              # seconds between wake-budget updates for visits
# Neon free plan, as understood when this was written (verify on the Neon Usage page): 100 CU-hours a month per project; the compute runs at
# 0.25 CU when idle, so 100 CU-hours = about 400 awake hours. Autoscaling up to 2 CU under load uses the hours faster.
CU = 0.25
BUDGET_CU_HOURS = 100.0
WARN_AT = 0.8

DB_DOWN_MESSAGE = "The member database is temporarily unavailable. Please try again later."

_last_write = 0.0
_last_account = 0.0


def db_down_errors() -> tuple:
    """Exceptions that mean 'the database refused or lost the connection' (quota exceeded, too many connections, starting up, network)."""
    import socket

    import asyncpg
    ex = asyncpg.exceptions
    names = ("InsufficientResourcesError", "TooManyConnectionsError", "CannotConnectNowError", "PostgresConnectionError", "ConnectionDoesNotExistError",
             "InterfaceError", "AdminShutdownError", "CrashShutdownError", "DiskFullError", "OutOfMemoryError")
    return tuple(getattr(ex, n) for n in names if hasattr(ex, n)) + (ConnectionError, socket.gaierror)


def _day(now: float) -> str:
    return datetime.fromtimestamp(now, IST).strftime("%Y-%m-%d")


def _month(now: float) -> str:
    return datetime.fromtimestamp(now, IST).strftime("%Y-%m")


# ------------------------------------------------------------------------------------------------------------------ visitors

async def touch_visit(redis, now: Optional[float] = None) -> None:
    """Called by the web app for a real page or data request. Cheap: one Redis write at most every 20 s per process; never raises."""
    global _last_write
    t = time.time() if now is None else now
    if t - _last_write < VISIT_WRITE_EVERY:
        return
    _last_write = t
    try:
        await redis.set(K_VISIT, repr(t), ex=86400)
        await account_visit(redis, t)
    except Exception:
        pass


async def visitor_active(redis, minutes: float = VISIT_MINUTES, now: Optional[float] = None) -> bool:
    """True when a visitor was on the site within `minutes`. Redis trouble reads as False: timers then skip instead of waking the database."""
    try:
        raw = await redis.get(K_VISIT)
        return bool(raw) and (time.time() if now is None else now) - float(raw) <= minutes * 60
    except Exception:
        return False


# ------------------------------------------------------------------------------------------------------------------ alerts flag

async def set_alerts_flag(redis, active: bool, ttl: int = 3 * 86400) -> None:
    try:
        await redis.set(K_ALERTS, "1" if active else "0", ex=ttl)
    except Exception:
        pass


async def alerts_active(redis) -> bool:
    """False only when the flag says there are no alerts. Unknown (no flag yet, Redis down) reads as True: an alert must never be missed."""
    try:
        raw = await redis.get(K_ALERTS)
    except Exception:
        return True
    if raw is None:
        return True
    return (raw.decode() if isinstance(raw, bytes) else str(raw)) == "1"


async def refresh_alerts_flag(settings, redis) -> bool:
    """Inside a DB window (the database is awake anyway): look once for active alerts or watchlist targets and store the answer."""
    import asyncpg

    from .store import prepare_dsn
    dsn, extra = prepare_dsn(settings.database_url)
    conn = await asyncpg.connect(dsn, timeout=15, command_timeout=15, **extra)
    try:
        active = bool(await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM alerts WHERE status = 'active') "
            "OR EXISTS(SELECT 1 FROM user_state WHERE watchlist::text LIKE '%\"target\"%')"))
    finally:
        await conn.close()
    await set_alerts_flag(redis, active)
    return active


# ------------------------------------------------------------------------------------------------------------------ the wake budget

async def _account(redis, t: float, event: str) -> None:
    """event: 'start' or 'end' of a database job. A job that starts while another runs is not a new wake. Minutes are counted from the first
    start of a wake until 5 minutes after its last end (the time Neon stays up), each minute once."""
    day, month = f"wake:day:{_day(t)}", f"wake:month:{_month(t)}"
    acc = float(await redis.get(K_ACC) or 0.0)
    if event == "start":
        running = await redis.incr(K_RUNNING)
        await redis.expire(K_RUNNING, 6 * 3600)
        if running == 1 and t >= acc:
            await redis.hincrby(day, "wakes", 1)
            acc = t                                  # a new wake: nothing before now is counted (inside the previous wake's 5-minute tail it is the same wake)
        await redis.set(K_ACC, repr(acc), ex=7 * 86400)
        return
    running = max(0, await redis.decr(K_RUNNING))
    if running > 0:
        return                                       # another job still holds the database: count when the last one ends
    if running == 0:
        await redis.set(K_RUNNING, 0, ex=6 * 3600)
    end = t + TAIL_MIN * 60
    start = acc if acc else t
    if end > start:
        mins = (end - start) / 60.0
        await redis.hincrbyfloat(day, "minutes", mins)
        await redis.hincrbyfloat(month, "minutes", mins)
        await redis.expire(day, 40 * 86400)
        await redis.expire(month, 400 * 86400)
        await redis.set(K_ACC, repr(end), ex=7 * 86400)


async def mark_start(redis, name: str = "", now: Optional[float] = None) -> None:
    try:
        await _account(redis, time.time() if now is None else now, "start")
    except Exception:
        pass


async def mark_end(redis, name: str = "", now: Optional[float] = None) -> None:
    try:
        await _account(redis, time.time() if now is None else now, "end")
    except Exception:
        pass


async def account_visit(redis, t: float) -> None:
    """A visit counts as a short database use (it may not have needed one: this errs on the high side)."""
    global _last_account
    if t - _last_account < ACCOUNT_EVERY:
        return
    _last_account = t
    await _account(redis, t, "start")
    await _account(redis, t, "end")


async def stats(redis, now: Optional[float] = None) -> Dict[str, Any]:
    """The 'Database wake budget' line of the admin Data health tab."""
    t = time.time() if now is None else now
    out: Dict[str, Any] = {"wakesToday": None, "awakeMinutesToday": None, "monthAwakeHours": None, "monthCuHours": None,
                           "budgetCuHours": BUDGET_CU_HOURS, "budgetAwakeHours": BUDGET_CU_HOURS / CU, "pct": None, "warning": None, "available": False,
                           "assumption": "Neon free plan: 100 CU-hours a month; the idle compute is 0.25 CU, so about 400 awake hours. This is an estimate: Neon's Usage page is the authority."}
    try:
        d = await redis.hgetall(f"wake:day:{_day(t)}")
        m = await redis.hgetall(f"wake:month:{_month(t)}")
    except Exception:
        return out
    get = lambda h, k: float((h.get(k) if k in h else h.get(k.encode())) or 0)   # noqa: E731 - bytes or str keys, depending on the client
    wakes, dmin, mmin = int(get(d, "wakes")), get(d, "minutes"), get(m, "minutes")
    hours = mmin / 60.0
    cu_hours = hours * CU
    pct = cu_hours / BUDGET_CU_HOURS
    out.update(available=True, wakesToday=wakes, awakeMinutesToday=round(dmin), monthAwakeHours=round(hours, 1), monthCuHours=round(cu_hours, 1), pct=round(pct * 100))
    if pct >= WARN_AT:
        out["warning"] = (f"This month's estimate is {round(pct * 100)}% of the free database's compute allowance ({round(cu_hours, 1)} of {BUDGET_CU_HOURS:.0f} CU-hours). "
                          "When it runs out the database refuses connections and sign-in stops until the month turns over or the plan is upgraded. "
                          "Check Neon > Billing > Usage, and pause the heavy loads (System tab) if the real figure is close.")
    return out


# ------------------------------------------------------------------------------------------------------------------ command line

async def _cli(argv: list) -> int:
    import redis.asyncio as aioredis

    from .config import get_settings
    cmd = argv[0] if argv else ""
    settings = get_settings()
    redis = aioredis.Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
    try:
        if cmd == "visit-active":
            return 0 if await visitor_active(redis, float(argv[1]) if len(argv) > 1 else VISIT_MINUTES) else 1
        if cmd == "alerts-active":
            return 0 if await alerts_active(redis) else 1
        if cmd == "flag-get":      # flag-get NAME: exit 0 when the flag is set
            return 0 if await redis.exists("wake:flag:" + argv[1]) else 1
        if cmd == "flag-set":      # flag-set NAME SECONDS
            await redis.set("wake:flag:" + argv[1], "1", ex=int(argv[2]))
            return 0
        if cmd == "start":
            await mark_start(redis, argv[1] if len(argv) > 1 else "")
            return 0
        if cmd == "end":
            await mark_end(redis, argv[1] if len(argv) > 1 else "")
            return 0
        if cmd == "stats":
            print(json.dumps(await stats(redis)))
            return 0
        if cmd == "refresh-alerts":
            await mark_start(redis, "refresh-alerts")
            try:
                print("alerts active:", await refresh_alerts_flag(settings, redis))
            finally:
                await mark_end(redis, "refresh-alerts")
            return 0
        print("usage: python -m finlit.wake visit-active [minutes] | alerts-active | flag-get NAME | flag-set NAME SECONDS | start NAME | end NAME | stats | refresh-alerts", file=sys.stderr)
        return 2
    except Exception as exc:   # a gate that cannot read Redis must not crash the scheduler: callers read the exit status
        print(f"wake {cmd}: {type(exc).__name__}", file=sys.stderr)
        return 0 if cmd == "alerts-active" else 3 if cmd == "refresh-alerts" else 1   # Redis unreadable: an alert is checked rather than missed
    finally:
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli(sys.argv[1:])))
