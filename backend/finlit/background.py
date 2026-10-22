"""Small helpers shared by the API modules: fire-and-forget tasks that cannot be lost, and If-None-Match matching."""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Optional, Set

log = logging.getLogger("finlit.background")
_running: Set[asyncio.Task] = set()


def spawn(coro: Coroutine) -> asyncio.Task:
    """Run `coro` in the background. The event loop keeps only a weak reference to a task, so one nobody holds can be garbage collected
    before it finishes; this keeps it until it is done, and logs a failure instead of leaving "Task exception was never retrieved"."""
    task = asyncio.create_task(coro)
    _running.add(task)

    def done(t: asyncio.Task) -> None:
        _running.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.warning("background task failed: %r", t.exception())

    task.add_done_callback(done)
    return task


def etag_matches(if_none_match: Optional[str], etag: str) -> bool:
    """RFC 9110 If-None-Match for GET: `*`, or any listed tag equal to ours by weak comparison (a W/ prefix on either side is ignored)."""
    if not if_none_match:
        return False
    ours = etag[2:] if etag.startswith("W/") else etag
    for tag in if_none_match.split(","):
        tag = tag.strip()
        if tag == "*":
            return True
        if (tag[2:] if tag.startswith("W/") else tag) == ours:
            return True
    return False
