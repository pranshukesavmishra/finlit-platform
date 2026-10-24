"""Which statements read the most rows from Postgres: the next hog, found from real data (GET /api/admin/db-usage, administrators only).

Neon's free plan allows 5 GB of data sent from the database a month (docs/NEON-EGRESS.md). Postgres does not count bytes per statement, but rows returned
is the closest thing it keeps, and the statements that return the most rows are the ones to look at first. Needs the pg_stat_statements extension
(migration 056 tries to create it); without it the answer says so instead of failing."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response

from .auth.routes import NO_STORE, Ctx, admin_ctx

log = logging.getLogger("finlit.dbusage")
admin = APIRouter(prefix="/api/admin")
QUERY_CHARS = 200
TOP = 15
LIMIT_GB = 5
NOT_ENABLED = ("pg_stat_statements is not enabled on this database, so there are no per-statement figures. Run "
               "`CREATE EXTENSION pg_stat_statements;` as the database owner (Neon: SQL editor), then wait a day and look again. "
               "Neon's own Usage page (Billing > Usage > Public network transfer) is the authority on the monthly total.")


async def report(pool, top: int = TOP) -> Dict[str, Any]:
    """The `top` statements by total rows returned since the statistics were last reset. Never raises: a missing or unloaded extension is an answer."""
    try:
        async with pool.acquire() as conn:
            if not await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"):
                return {"enabled": False, "message": NOT_ENABLED, "top": []}
            rows = await conn.fetch(
                "SELECT left(query, 600) AS query, calls, rows, total_exec_time FROM pg_stat_statements "
                "WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) ORDER BY rows DESC LIMIT $1", top)
    except Exception as exc:   # installed but not in shared_preload_libraries, or no right to read it
        log.warning("pg_stat_statements not readable: %s", type(exc).__name__)
        return {"enabled": False, "message": NOT_ENABLED + " (It is installed but cannot be read: the host must load it at start.)", "top": []}
    out = []
    for r in rows:
        q = re.sub(r"\s+", " ", r["query"]).strip()
        out.append({"query": q if len(q) <= QUERY_CHARS else q[:QUERY_CHARS] + "…", "calls": int(r["calls"]), "rows": int(r["rows"]),
                    "rowsPerCall": round(int(r["rows"]) / max(1, int(r["calls"]))), "totalMs": round(float(r["total_exec_time"]))})
    total = sum(x["rows"] for x in out)
    return {"enabled": True, "top": out, "topRows": total,
            "budget": {"limitGB": LIMIT_GB, "note": "Rows, not bytes: a row of the screener table is about 7 KB, most others under 200 bytes. "
                       "Check Neon > Billing > Usage > Public network transfer weekly; at 60% of the month's 5 GB before the 20th, act."}}


@admin.get("/db-usage")
async def db_usage(request: Request, ctx: Ctx = Depends(admin_ctx)):
    return Response(content=json.dumps(await report(request.app.state.store.pool)), media_type="application/json", headers=NO_STORE)
