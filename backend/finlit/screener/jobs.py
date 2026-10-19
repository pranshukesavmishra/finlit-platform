"""Worker jobs for the screener: recompute every company's metrics from stored snapshots, and refresh index membership."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Dict, List

import httpx
import orjson

from .catalog import INDEX_LISTS
from .compute import compute

log = logging.getLogger("finlit.screener")
SECTIONS = ("summary", "financials", "ratios", "ownership", "events", "price", "stats")


async def rebuild_metrics(store, only_missing: bool = False) -> int:
    """Recompute metrics for every company that has a stored snapshot. Database work only: no data-provider calls."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, statement FROM scores WHERE model = 'v1'" + (" AND metrics IS NULL" if only_missing else ""))
        done = 0
        for r in rows:
            snaps = await conn.fetch("SELECT section, body FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = ANY($3::text[])", r["symbol"], r["statement"], list(SECTIONS))
            sections: Dict[str, dict] = {s["section"]: json.loads(s["body"]) for s in snaps}
            if "summary" not in sections:
                continue
            metrics = compute(sections)
            prof = sections["summary"].get("profile") or {}
            await conn.execute("UPDATE scores SET metrics = $3::jsonb, industry = COALESCE($4, industry), macro_sector = COALESCE($5, macro_sector) WHERE symbol = $1 AND statement = $2",
                               r["symbol"], r["statement"], orjson.dumps(metrics).decode(), prof.get("industry"), prof.get("macroSector"))
            done += 1
    log.info("screener metrics rebuilt for %d companies", done)
    return done


async def refresh_metrics_for(store, pairs) -> int:
    """Recompute the screener metrics of the given (symbol, statement) pairs after a live-price patch, in two queries for the whole batch."""
    pairs = list(pairs)
    if not pairs:
        return 0
    symbols = sorted({s for s, _ in pairs})
    wanted = set(pairs)
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, statement, section, body FROM snapshots WHERE symbol = ANY($1::text[]) AND section = ANY($2::text[])", symbols, list(SECTIONS))
        grouped: Dict[tuple, dict] = {}
        for r in rows:
            if (r["symbol"], r["statement"]) in wanted:
                grouped.setdefault((r["symbol"], r["statement"]), {})[r["section"]] = json.loads(r["body"])
        updates = [(sym, st, orjson.dumps(compute(sec)).decode()) for (sym, st), sec in grouped.items() if "summary" in sec]
        if updates:
            await conn.executemany("UPDATE scores SET metrics = $3::jsonb WHERE symbol = $1 AND statement = $2", updates)
    return len(updates)


async def refresh_indices(store) -> Dict[str, int]:
    """Download the public index constituent lists (NSE Indices) and store which companies belong to which index."""
    counts: Dict[str, int] = {}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0 (FinLit research)", "Accept": "text/csv,*/*"}) as http:
        for code, (label, fname) in INDEX_LISTS.items():
            try:
                r = await http.get(f"https://www.niftyindices.com/IndexConstituent/{fname}.csv")
                r.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("index list %s unavailable: %s", code, type(exc).__name__)
                continue
            symbols: List[str] = [(row.get("Symbol") or "").strip().upper() for row in csv.DictReader(io.StringIO(r.text))]
            symbols = [s for s in symbols if s]
            if len(symbols) < 10:
                continue
            async with store.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM index_members WHERE index_code = $1", code)
                    await conn.executemany("INSERT INTO index_members (index_code, symbol) VALUES ($1, $2) ON CONFLICT DO NOTHING", [(code, s) for s in symbols])
            counts[code] = len(symbols)
    log.info("index membership refreshed: %s", counts)
    return counts
