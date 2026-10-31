"""Cheap questions the supervisor asks before it starts an expensive job: is there anything to do? (True/False; an error means unknown, so the job follows its clock)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

BEHIND_SHARE = 0.02      # more than 2% of the reports behind the newest session = work to do (a few companies Dhan has no candles for are normal)


def build(store: Any) -> Dict[str, Callable[[], Awaitable[Optional[bool]]]]:
    async def technicals() -> Optional[bool]:
        from ..prism_technical import current_target
        target = await current_target(store.redis, datetime.now(timezone.utc))
        async with store.pool.acquire() as conn:
            total = await conn.fetchval("SELECT count(DISTINCT symbol) FROM prism_reports")
            behind = await conn.fetchval("SELECT count(*) FROM (SELECT symbol, min(COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}')) AS bar "
                                         "FROM prism_reports GROUP BY symbol) t WHERE bar IS NULL OR bar < $1", target.isoformat())
        return bool(total) and behind / total > BEHIND_SHARE

    async def prism() -> Optional[bool]:
        from .. import prism as prism_mod
        return bool(await prism_mod._pending(store, "consolidated", 7, 1, []))

    return {"technicals": technicals, "prism": prism}
