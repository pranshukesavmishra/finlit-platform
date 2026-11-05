"""Fill the 1, 3 and 5 year returns of every fund that has none, so the lists and the MF portfolio never show a blank that only means "not downloaded yet".

Why they were blank: AMFI's history can only be asked for a whole fund house, and a house is downloaded only when `backfill-mf` reaches it (and AMFI's site often
times out from the AWS server). A fund of a house not yet reached has no stored history, so its returns stay empty for days.

Here each such fund is filled one at a time from the public mirror of AMFI's own data (api.mfapi.in/mf/<code>, no key, free): the same source and the same safety
check as the fund page's cold path (mf.mirror_fetch): the mirror's NAV for the day of AMFI's latest NAV must agree with AMFI's, else nothing is stored.
Only the worked-out figures and the month-end NAVs are kept (no daily series), so the free database stays small and AMFI's own history, when it arrives,
replaces these figures with its own.

Order: funds somebody holds or follows first, then the biggest. A fund that is too young for any period is not asked again for a few days."""
from __future__ import annotations

import asyncio
import logging
import time
from bisect import bisect_right
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

import httpx

from . import mf

log = logging.getLogger("finlit.mf_fill")

TRIED_TTL = 3 * 86400          # a fund that gave no return (too young, no data) is not asked again for 3 days
MISSING_SQL = """
SELECT s.code, s.nav, s.nav_date
FROM mf_schemes s
WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.nav_date IS NOT NULL
  AND s.r1y IS NULL AND s.r3y IS NULL AND s.r5y IS NULL
  AND ($1::int[] IS NULL OR s.code = ANY($1::int[]))
ORDER BY EXISTS (SELECT 1 FROM mf_holdings h WHERE h.code = s.code) DESC, s.aum_lakh DESC NULLS LAST, s.code
LIMIT $2"""

BACKGROUND = True              # tests switch the instant fill off so no test reaches the network
_background: set = set()       # strong references to the fire-and-forget tasks


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=6.0), follow_redirects=True, headers={"User-Agent": mf.USER_AGENT})


async def fetch_checked(client: httpx.AsyncClient, code: int, nav: float, nav_date: date) -> Optional[tuple]:
    """(days, NAVs) from the mirror, or None when it has nothing usable or disagrees with AMFI's own latest NAV."""
    try:
        r = await client.get(f"{mf.MIRROR_URL}/{code}")
        if r.status_code != 200:
            return None
        series = mf.parse_mirror(r.json(), code)
    except (httpx.HTTPError, ValueError):
        return None
    if not series:
        return None
    days, navs = series
    i = bisect_right(days, nav_date.toordinal()) - 1
    if i < 0 or days[i] != nav_date.toordinal() or abs(navs[i] - float(nav)) > 1e-6 * max(1.0, float(nav)):
        return None            # the mirror lags or disagrees with AMFI: store nothing rather than a number that cannot be confirmed
    return days[: i + 1], navs[: i + 1]


async def _store(conn, code: int, days: List[int], navs: List[float]) -> bool:
    """Write the worked-out figures and the month-end NAVs; True when at least one return was worked out."""
    days, navs = mf.trim(days, navs)
    m = mf.metrics_for(days, navs, False)
    cols = mf.metric_columns(m)
    if cols[2] is None and cols[3] is None and cols[4] is None:
        return False
    prev = (navs[-2], date.fromordinal(days[-2])) if len(days) > 1 else (None, None)
    async with conn.transaction():
        await conn.execute(mf.METRICS_UPDATE, code, *cols, date.fromordinal(days[-1]), *prev, *m["dash"])
        md, mv = mf.month_ends(days, navs)
        old = await conn.fetchrow("SELECT days, navs FROM mf_monthly WHERE code = $1", code)
        d, v = mf.merge_months(([x.toordinal() for x in old["days"]], list(old["navs"])) if old else ([], []), (md, mv))
        await conn.execute(mf.MONTHLY_UPSERT, code, [date.fromordinal(x) for x in d], v)
    return True


async def fill(store, client: httpx.AsyncClient, codes: Optional[Iterable[int]] = None, *, limit: int = 400, max_seconds: float = 600.0, pause: float = 0.25) -> Dict[str, Any]:
    """Fill funds that have no returns (the given codes only, or every such fund). Returns counts; never raises for one bad fund."""
    started = time.monotonic()
    want = sorted(set(codes)) if codes is not None else None
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(MISSING_SQL, want, limit)
    done = skipped = failed = young = 0
    for r in rows:
        if time.monotonic() - started > max_seconds:
            break
        key = f"mf:fill:tried:{r['code']}"
        try:
            if await store.redis.get(key):
                skipped += 1
                continue
        except Exception:   # nosec B110 - Redis trouble only means a repeated ask
            pass
        got = await fetch_checked(client, r["code"], r["nav"], r["nav_date"])
        ok = False
        if got:
            try:
                async with store.pool.acquire() as conn:
                    ok = await _store(conn, r["code"], got[0], got[1])
            except Exception:
                log.exception("fund %s: returns not stored", r["code"])
                failed += 1
                continue
        if ok:
            done += 1
        else:
            young += 1
            try:
                await store.redis.set(key, "1", ex=TRIED_TTL)
            except Exception:   # nosec B110
                pass
        await asyncio.sleep(pause)
    if done:
        await mf._bump(store, None)      # the list caches are keyed on the data version
    out = {"asked": len(rows), "filled": done, "noReturnYet": young, "skipped": skipped, "failed": failed, "seconds": round(time.monotonic() - started, 1)}
    log.info("mf returns fill %s", out)
    return out


def fill_in_background(store, codes: Iterable[int]) -> None:
    """Fire and forget: fill these funds right now (a fund was just added), without holding the request."""
    codes = list(codes)
    if not codes or not BACKGROUND:
        return

    async def run() -> None:
        client = make_client()
        try:
            await fill(store, client, codes, limit=len(codes), max_seconds=60.0, pause=0.1)
        except Exception:
            log.exception("returns fill for %s failed", codes)
        finally:
            await client.aclose()
    task = asyncio.get_running_loop().create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)
