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
from .compute import METRICS_VERSION, compute

log = logging.getLogger("finlit.screener")
SECTIONS = ("summary", "financials", "ratios", "ownership", "events", "price", "stats")


async def rebuild_metrics(store, only_missing: bool = False) -> int:
    """Recompute metrics for every company that has a stored snapshot. Database work only: no data-provider calls.
    `only_missing` picks up companies with no metrics yet AND companies whose metrics were worked out by an older version of compute.py (`m_ver`),
    so a new filter (or a fixed formula) reaches every stored company once, without waiting for each company's next full load."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, statement FROM scores WHERE model = 'v1'"  # nosec B608 - fixed text, no user input
                                + (" AND (metrics IS NULL OR NOT metrics ? 'm_ver' OR COALESCE((metrics->>'m_ver')::float, 0) < $1"
                                   " OR (metrics ? 'q_revenue' AND NOT metrics ? 'q_period_end'))" if only_missing else ""),
                                *([METRICS_VERSION] if only_missing else []))
        done = 0
        for r in rows:
            snaps = await conn.fetch("SELECT section, body FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = ANY($3::text[])", r["symbol"], r["statement"], list(SECTIONS))
            sections: Dict[str, dict] = {s["section"]: json.loads(s["body"]) for s in snaps}
            if "summary" not in sections:
                continue
            metrics = compute(sections)
            prof = sections["summary"].get("profile") or {}
            await conn.execute("UPDATE scores SET metrics = $3::jsonb, industry = COALESCE($4, industry), macro_sector = COALESCE($5, macro_sector), changed_at = now() WHERE symbol = $1 AND statement = $2",
                               r["symbol"], r["statement"], orjson.dumps(metrics).decode(), prof.get("industry"), prof.get("macroSector"))
            done += 1
    log.info("screener metrics rebuilt for %d companies", done)
    return done


async def refresh_metrics_for(store, pairs) -> int:
    """Recompute the screener metrics of the given (symbol, statement) pairs after a live-price patch. The live summary is read from Redis (where the quote
    patch has just put it) and the rest of the inputs from the Redis copy store.metric_inputs keeps: Postgres is asked only for what Redis does not hold.
    This runs every minute for every company with a report, so reading ~100 KB a company from Postgres here would be tens of megabytes a minute."""
    pairs = list(pairs)
    done = 0
    for i in range(0, len(pairs), 25):   # 25 companies at a time keeps memory small on the free server
        chunk = pairs[i:i + 25]
        inputs = await store.metric_inputs(chunk)
        updates = []
        for sym, st in chunk:
            got = await store.get_section(sym, st, "summary")
            if not got:
                continue
            m = compute({**inputs.get((sym, st), {}), "summary": json.loads(got[0])})
            updates.append((sym, st, orjson.dumps(m).decode(), m.get("price"), m.get("market_cap"), m.get("ret_1d"), m.get("pe"), m.get("pb"), m.get("dividend_yield")))
        if updates:   # the flat columns the company list shows move with the quote too
            async with store.pool.acquire() as conn:
                await conn.executemany("UPDATE scores SET metrics = $3::jsonb, price = COALESCE($4, price), market_cap = COALESCE($5, market_cap), "
                                       "change_pct = COALESCE($6, change_pct), pe = $7, pb = $8, dividend_yield = $9, changed_at = now() WHERE symbol = $1 AND statement = $2", updates)
        done += len(updates)
    return done


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
            symbols = [s for s in symbols if s and not s.startswith("DUMMY")]   # the exchange's placeholder rows are not companies
            if len(symbols) < 10:
                continue
            async with store.pool.acquire() as conn:
                stored = await conn.fetchval("SELECT count(*) FROM index_members WHERE index_code = $1", code)
                if stored and len(symbols) < 0.8 * stored:   # a cut-off answer must not replace a full list
                    log.warning("index list %s refused: %d members against %d stored", code, len(symbols), stored)
                    continue
                async with conn.transaction():
                    await conn.execute("DELETE FROM index_members WHERE index_code = $1", code)
                    await conn.executemany("INSERT INTO index_members (index_code, symbol) VALUES ($1, $2) ON CONFLICT DO NOTHING", [(code, s) for s in symbols])
            counts[code] = len(symbols)
    log.info("index membership refreshed: %s", counts)
    try:
        await store.redis.delete("markets:members")   # the dashboard heat-maps read the new lists at once
    except Exception:
        pass
    return counts
