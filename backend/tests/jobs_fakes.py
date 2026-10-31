"""Fakes for the job supervisor tests: a clock that never sleeps, a process runner whose jobs finish when the test says so, fixed resources, in-memory Redis signals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from finlit.jobs.due import PauseInfo
from finlit.jobs.registry import Job, JobsConfig
from finlit.jobs.resources import Snapshot
from finlit.jobs.schedule import IST


def ist(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=IST).astimezone(timezone.utc)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.t = now

    def now(self) -> datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)

    async def sleep(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


class FakeHandle:
    _pid = 1000

    def __init__(self, job: Job, clock: FakeClock) -> None:
        FakeHandle._pid += 1
        self.pid, self.job, self.clock = FakeHandle._pid, job, clock
        self.rc: Optional[int] = None
        self.activity = clock.now().timestamp()
        self.terminated = False
        self.killed = False
        self.rss = 120
        self.out = ""

    def poll(self) -> Optional[int]:
        return self.rc

    def terminate(self) -> None:
        self.terminated = True
        self.rc = -15

    def kill(self) -> None:
        self.killed = True
        self.rc = -9

    def last_activity(self) -> float:
        return self.activity

    def rss_mb(self) -> Optional[int]:
        return self.rss

    def tail(self) -> str:
        return self.out

    def finish(self, rc: int = 0, out: str = "") -> None:
        self.rc, self.out = rc, out

    def touch(self) -> None:
        self.activity = self.clock.now().timestamp()


class FakeRunner:
    def __init__(self, clock: FakeClock) -> None:
        self.clock, self.handles, self.started = clock, [], []
        self.orphans: List[Any] = []

    def start(self, job: Job, extra_env=None) -> FakeHandle:
        h = FakeHandle(job, self.clock)
        self.handles.append(h)
        self.started.append(job.name)
        return h

    def reap_orphan(self, pid) -> bool:
        self.orphans.append(pid)
        return True

    def of(self, name: str) -> FakeHandle:
        return [h for h in self.handles if h.job.name == name][-1]


class FakeResources:
    def __init__(self, free_mb: int = 900, load: float = 0.2) -> None:
        self.free_mb, self.load = free_mb, load

    def snapshot(self) -> Snapshot:
        return Snapshot(self.free_mb, self.load, "fake")


class FakeSignals:
    def __init__(self) -> None:
        self.visitor, self.alerts, self.web = False, True, True
        self.locked = False
        self.beats: List[Dict[str, Any]] = []
        self.notes: List[tuple] = []
        self.started: List[str] = []
        self.json: Dict[str, Any] = {}
        self.cred: Dict[str, str] = {}

    async def acquire_lock(self) -> bool:
        if self.locked:
            return False
        self.locked = True
        return True

    async def refresh_lock(self) -> bool:
        return True

    async def release_lock(self) -> None:
        self.locked = False

    async def heartbeat(self, now, info) -> None:
        self.beats.append({**info, "at": now.timestamp()})

    async def visitor_active(self) -> bool:
        return self.visitor

    async def alerts_active(self) -> bool:
        return self.alerts

    async def web_up(self) -> bool:
        return self.web

    async def note(self, name, why) -> None:
        self.notes.append((name, why))

    async def job_started(self, name, now) -> None:
        self.started.append(name)

    async def set_json(self, key, value, ttl=0) -> None:
        self.json[key] = value

    async def get_json(self, key):
        return self.json.get(key)

    async def credential_refused(self) -> Dict[str, str]:
        return dict(self.cred)


class FakePause:
    def __init__(self) -> None:
        self.info: Optional[PauseInfo] = None
        self.fail = False

    async def current(self, now: datetime) -> Optional[PauseInfo]:
        if self.fail:
            raise RuntimeError("database down")
        if self.info and self.info.until <= now:
            self.info = None          # expired: resumes by itself
        return self.info


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: List[tuple] = []
        self.seen: Dict[str, datetime] = {}

    async def alert(self, key, subject, body, now=None) -> bool:
        if key in self.seen and now and (now - self.seen[key]).total_seconds() < 6 * 3600:
            return False
        self.seen[key] = now
        self.sent.append((key, subject, body))
        return True


def config(**kw) -> JobsConfig:
    base = dict(boot_delay_s=0.0)
    base.update(kw)
    return JobsConfig(**base)
