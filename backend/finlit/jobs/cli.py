"""`python -m finlit.worker supervise [--once] [--dry-run]`, `jobs-status`, `canary`: the command-line door to the supervisor."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import timezone
from typing import Any

from . import canary as canary_mod, freshness, probes
from .alerts import Notifier
from .pause import PgPause
from .registry import JobsConfig, build_jobs
from .resources import SystemResources, disk_percent
from .runner import ProcessRunner
from .signals import CANARY_KEY, RedisSignals, SystemClock, clear_credential
from .state import PgState
from .supervisor import LockHeld, Supervisor

log = logging.getLogger("finlit.jobs")


def make_mailer(settings: Any, pool: Any) -> Any:
    from ..auth.mailer import ConsoleMailer, ResendMailer
    if settings.mail_mode == "resend" and settings.resend_api_key:
        return ResendMailer(settings.resend_api_key, settings.mail_from)
    return ConsoleMailer(pool)


async def build_supervisor(settings: Any, store: Any, dry_run: bool = False) -> Supervisor:
    env = os.environ
    cfg = JobsConfig.from_env(env)
    signals = RedisSignals(store.redis, cfg.web_port)
    clock = SystemClock()
    notifier = None if dry_run else Notifier(store.pool, make_mailer(settings, store.pool), store.redis, settings.public_site_url)

    async def fresh(now):
        return await freshness.check(store, signals, now)

    async def extra(now):
        out = []
        disk = disk_percent()
        if disk is not None and disk >= freshness.DISK_ALERT_PCT:
            out.append(("disk", "FinLit server disk is almost full", f"The server disk is {disk:.0f}% full (alert at {freshness.DISK_ALERT_PCT:.0f}%). Free space: docker system prune -f; check "
                        "the backups volume and /var/log. The prune job also runs every night."))
        for p, detail in (await signals.credential_refused()).items():
            name = {"dhan": "Dhan", "finedge": "FinEdge"}.get(p, p)
            out.append((f"cred:{p}", f"The {name} key is not accepted", f"The {name} key is not accepted ({detail}). Update it in /opt/finlit/.env.aws and run: docker compose up -d app (see docs/JOBS.md, failure table)."))
        c = await signals.get_json(CANARY_KEY)
        if c and c.get("ok") is False:
            ms = "; ".join(f"{m['symbol']} {m['field']}: ours {m['ours']} vs provider {m['provider']} ({m['diffPercent']}%)" for m in c.get("mismatches", [])[:6])
            out.append(("canary", "FinLit canary found data that differs from the provider", ms))
        return out

    async def legacy():
        from datetime import datetime as dt
        out = {}
        async with store.pool.acquire() as conn:
            for r in await conn.fetch("SELECT key, value FROM mf_meta WHERE key LIKE 'run:%'"):
                v = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]
                try:
                    out[r["key"][4:]] = (dt.fromisoformat(v["at"]), v.get("status"))
                except Exception:   # nosec B112 - an unreadable old record is simply not used
                    continue
        return out

    sup = Supervisor(jobs=build_jobs(env), state=PgState(store.pool), runner=ProcessRunner(nice=cfg.nice, oom_adj=cfg.oom_score_adj), resources=SystemResources(),
                     signals=signals, pause=PgPause(store.pool), clock=clock, config=cfg, env=env, probes=probes.build(store), notifier=notifier, freshness=fresh, extra_alerts=extra, legacy=legacy)
    return sup


def print_plan(plan: Any) -> None:
    print(f"{'job':<20}{'state':<10}reason")
    for name, v in sorted(plan.verdicts.items(), key=lambda kv: (kv[1].state != "due", kv[0])):
        state = "waiting" if name in plan.blocked else v.state
        reason = plan.blocked.get(name) or v.reason
        mark = "  <- would start" if any(j.name == name for j in plan.start) else ""
        print(f"{name:<20}{state:<10}{reason}{mark}")


async def supervise(settings: Any, once: bool = False, dry_run: bool = False, wait: bool = True) -> int:
    from ..store import Store
    store = await Store.connect(settings, migrate=False)
    try:
        sup = await build_supervisor(settings, store, dry_run)
        if dry_run:
            print_plan(await sup.plan())
            return 0
        if not await sup.signals.acquire_lock():
            print("another supervisor is already running (Redis lock held); nothing started", file=sys.stderr)
            return 3
        try:
            await sup.reconcile()
            if once:
                print_plan(await sup.run_once(wait=wait))
                return 0
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for s in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(s, stop.set)
            logging.getLogger("finlit.jobs").info("supervisor started (pid %s)", os.getpid())
            while not stop.is_set():
                await sup.step()
                try:
                    await asyncio.wait_for(stop.wait(), sup.cfg.poll_s)
                except asyncio.TimeoutError:
                    pass
            return 0
        except LockHeld as exc:
            print(f"supervisor stopped: {exc}", file=sys.stderr)
            return 3
        finally:
            await sup.shutdown()
    finally:
        await store.close()


async def run_canary(settings: Any, store: Any) -> int:
    from datetime import datetime
    from ..finedge import FinEdgeClient
    now = datetime.now(timezone.utc)
    async with FinEdgeClient(settings) as client:
        result = await canary_mod.run(store, client, now)
    await store.redis.set(CANARY_KEY, json.dumps(result, default=str), ex=7 * 86400)
    from ..mf import record_run
    await record_run(store, "canary", {"status": "ok" if result["ok"] else "mismatch" if result["ok"] is False else "failed", "checked": len(result["checked"]), "mismatches": len(result["mismatches"])})
    print(json.dumps(result, default=str))
    if result["checked"]:
        await clear_credential(store.redis, "finedge")      # a call went through: the key is accepted
    return 0 if result["ok"] is not None else 1
