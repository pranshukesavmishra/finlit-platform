"""Diagnostic: fetch one stock's Dhan daily candles exactly as Prism does and say which rows break the strictly-increasing-dates rule.
Run on the server:  docker compose ... exec -T app python - < scripts/dhan_series_check.py   (prints no secret)"""
import asyncio
import datetime as dt
import sys

import redis.asyncio as aioredis

from finlit.config import get_settings
from finlit.dhan import IST, DhanClient

SID = sys.argv[1] if len(sys.argv) > 1 else "625"


async def main():
    s = get_settings()
    r = aioredis.from_url(s.redis_url)
    async with DhanClient(s, r) as c:
        today = dt.datetime.now(IST).date()
        rows = await c.daily(SID, "NSE_EQ", today - dt.timedelta(days=2190), today + dt.timedelta(days=1))
    days = [x["day"] for x in rows]
    bad = [(i, str(days[i - 1]), str(days[i])) for i in range(1, len(days)) if days[i] <= days[i - 1]]
    print("rows", len(rows), "first", days[0] if days else None, "last", days[-1] if days else None, "today(IST)", today)
    print("non-increasing pairs:", len(bad), bad[:6])
    for i, _, _ in bad[:3]:
        print("  around", i, [(str(x["day"]), x["close"], x["volume"]) for x in rows[max(0, i - 1):i + 2]])
    print("last 3 rows:", [(str(x["day"]), x["close"], x["volume"]) for x in rows[-3:]])


asyncio.run(main())
