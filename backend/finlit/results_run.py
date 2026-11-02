"""What every results run shares: a time budget, a polite stop, and a progress note that survives a kill.

Why this exists. The `results` job was killed by its 20-minute limit three runs in a row (TIMEOUT), and its companies starved. Three causes, all fixed here
and in worker.refresh_results / results_light.refresh_light:
  * no time budget: a run took every candidate it was given (up to 120 full rebuilds of ~20 provider calls each), however slow the provider was;
  * the adaptive pace (up to 8 s between calls, shared by the ~20 calls of one rebuild) and the 3 retries with Retry-After (up to 120 s) of a single call
    were unbounded, so one throttled company could hold the run for minutes;
  * the "asked recently" lock was taken for the whole selection up front, so the companies a killed run never reached stayed locked out for the next
    50 minutes to 5 hours, and the order was biggest-first only, so the small ones were always the ones cut off.
Now a run stops at BUDGET_SHARE (80%) of the job's max_runtime, records `partial` and the next run continues; a single call is bounded; the order is fair.
If a run IS killed anyway, the progress note below tells /api/results/status the last symbol and step it was on.
"""

from __future__ import annotations

import logging
import signal
import time
from typing import Any, Dict, Optional

import orjson

log = logging.getLogger("finlit.results_run")

BUDGET_SHARE = 0.8            # a run stops by itself at this share of the job's max_runtime; the rest is the margin for the last call and for recording
CALL_TIMEOUT_S = 30.0         # one company (light: 1-2 provider calls) never holds a run longer than this
COMPANY_TIMEOUT_S = 150.0     # one full rebuild (~20 provider calls, in parallel) never holds a run longer than this
FAIR_BAND_H = 3               # companies asked within the same 3-hour band are ordered by size; an older band always comes first
PROGRESS_KEY = "results:progress:"
PROGRESS_TTL_S = 3 * 86400
STALE_PROGRESS_S = 120        # a progress note still "running" this long after its last step belongs to a run that was killed


def budget_minutes(job: str, fallback: float) -> float:
    """BUDGET_SHARE of the registry's max_runtime for `job` (one source of truth: change the limit there and the budget follows)."""
    try:
        from .jobs.registry import by_name
        return round(by_name()[job].max_runtime_min * BUDGET_SHARE, 2)
    except Exception:   # nosec B110 - the registry is only the source of the number
        return fallback


class Stop:
    """Set when the supervisor asks the job to end (SIGTERM at its time limit): the run finishes the company in hand, records `partial` and exits 0."""
    requested = False
    signal_name: Optional[str] = None

    @classmethod
    def install(cls, loop) -> None:
        def handler(name):
            cls.requested, cls.signal_name = True, name
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, handler, sig.name)
            except (NotImplementedError, RuntimeError, ValueError):   # not the main thread / not unix: the default behaviour stays
                pass

    @classmethod
    def reset(cls) -> None:
        cls.requested, cls.signal_name = False, None


def fair_band(age_hours: Optional[float]) -> int:
    """Smaller = earlier in the run. Never asked is first (-1); then the longest unasked; the FAIR_BAND_H bands keep the order by size inside a band."""
    if age_hours is None:
        return -(10 ** 6)
    return -int(max(0.0, age_hours) // FAIR_BAND_H)


class Progress:
    """One small note in Redis per command: what the run is doing right now. Written after every company; never raises."""

    def __init__(self, redis: Any, cmd: str, budget_s: float, planned: int = 0, clock=time.time):
        self.redis, self.cmd, self.clock = redis, cmd, clock
        self.note: Dict[str, Any] = {"state": "running", "startedAt": clock(), "budgetSeconds": round(budget_s), "planned": planned, "done": 0, "symbol": None, "step": "starting"}

    async def _save(self) -> None:
        self.note["updatedAt"] = self.clock()
        try:
            await self.redis.set(PROGRESS_KEY + self.cmd, orjson.dumps(self.note).decode(), ex=PROGRESS_TTL_S)
        except Exception:   # nosec B110 - the note is for the status page
            pass

    async def step(self, symbol: Optional[str], step: str, **fields: Any) -> None:
        self.note.update(symbol=symbol, step=step, **fields)
        await self._save()

    async def finish(self, state: str, **fields: Any) -> None:
        self.note.update(state=state, finishedAt=self.clock(), **fields)
        await self._save()


async def read_progress(redis: Any, cmd: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """The note for /api/results/status, with `interrupted` filled in when it still says running long after its last step (the run was killed)."""
    try:
        raw = await redis.get(PROGRESS_KEY + cmd)
    except Exception:
        return None
    if not raw:
        return None
    note = orjson.loads(raw)
    now = now if now is not None else time.time()
    if note.get("state") == "running" and now - float(note.get("updatedAt") or 0) > STALE_PROGRESS_S:
        note["state"] = "killed"
        note["interrupted"] = (f"the run was killed (time limit or restart): its last step was '{note.get('step')}'"
                               + (f" on {note['symbol']}" if note.get("symbol") else "") + f", {note.get('done', 0)} of {note.get('planned', 0)} companies done")
    return note


def run_stats(res: Dict[str, Any], started: float, budget_s: float, now: Optional[float] = None) -> Dict[str, Any]:
    """The per-run numbers shown at /api/results/status for either job: asked, filled, throttled, left, duration."""
    took = (now if now is not None else time.monotonic()) - started
    asked = int(res.get("tried", res.get("candidates", 0)) or 0)
    filled = int(res.get("filled", res.get("ok", 0)) or 0)
    return {"asked": asked, "filled": filled, "throttled": int(res.get("throttled", 0) or 0), "failed": int(res.get("failed", 0) or 0),
            "left": int(res.get("left", 0) or 0), "durationSeconds": int(took), "budgetSeconds": int(budget_s),
            "perMinute": round(asked / (took / 60), 1) if took >= 30 and asked else None, "stoppedBy": res.get("stoppedBy")}
