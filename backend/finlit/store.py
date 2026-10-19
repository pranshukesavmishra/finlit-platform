"""Postgres (source of truth) + Redis (hot path) for precomputed snapshots.

Read path, per request: one Redis HMGET (body + etag) -> bytes on the wire. If Redis is cold,
one Postgres primary-key lookup, then Redis is re-filled. Nothing is computed per request.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import asyncpg
import orjson
import redis.asyncio as aioredis

from .config import Settings, get_settings

log = logging.getLogger("finlit.store")
MIGRATIONS = Path(__file__).parent / "migrations"
SEARCH_KEY = "search-index"
# What the website lists for every company. The 170 screener numbers (scores.metrics) are left out on purpose: they are ~2 KB a company and only /api/screener/query needs them.
LIST_COLUMNS = ("symbol, statement, model, overall, band, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, pillar_technical, price, market_cap, "
                "pe, pb, roe, roce, dividend_yield, debt_to_equity, sales_cagr, profit_cagr, operating_margin, change_pct, return_1m, return_1y, sector, name, updated_at")

SCORE_COLUMNS = ("symbol", "statement", "model", "overall", "band", "pillar_quality", "pillar_growth",
                 "pillar_profitability", "pillar_balance", "pillar_technical", "price", "market_cap", "pe", "roe",
                 "dividend_yield", "sector", "name", "pb", "roce", "debt_to_equity", "sales_cagr", "profit_cagr",
                 "operating_margin", "change_pct", "return_1m", "return_1y", "industry", "macro_sector", "metrics")
SCORE_UPSERT = """
INSERT INTO scores (symbol, statement, model, overall, band, pillar_quality, pillar_growth, pillar_profitability,
                    pillar_balance, pillar_technical, price, market_cap, pe, roe, dividend_yield, sector, name, pb, roce,
                    debt_to_equity, sales_cagr, profit_cagr, operating_margin, change_pct, return_1m, return_1y, industry, macro_sector, metrics, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29::jsonb, now())
ON CONFLICT (symbol, statement, model) DO UPDATE SET
    overall = EXCLUDED.overall, band = EXCLUDED.band, pillar_quality = EXCLUDED.pillar_quality,
    pillar_growth = EXCLUDED.pillar_growth, pillar_profitability = EXCLUDED.pillar_profitability,
    pillar_balance = EXCLUDED.pillar_balance, pillar_technical = EXCLUDED.pillar_technical,
    price = EXCLUDED.price, market_cap = EXCLUDED.market_cap, pe = EXCLUDED.pe, roe = EXCLUDED.roe,
    dividend_yield = EXCLUDED.dividend_yield, sector = EXCLUDED.sector, name = EXCLUDED.name, pb = EXCLUDED.pb,
    roce = EXCLUDED.roce, debt_to_equity = EXCLUDED.debt_to_equity, sales_cagr = EXCLUDED.sales_cagr,
    profit_cagr = EXCLUDED.profit_cagr, operating_margin = EXCLUDED.operating_margin,
    change_pct = EXCLUDED.change_pct, return_1m = EXCLUDED.return_1m, return_1y = EXCLUDED.return_1y, industry = EXCLUDED.industry, macro_sector = EXCLUDED.macro_sector,
    metrics = EXCLUDED.metrics, updated_at = now()
"""


def dumps(value: Any) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY)


def etag_for(body: bytes) -> str:
    return '"' + hashlib.blake2b(body, digest_size=10).hexdigest() + '"'


def stock_key(symbol: str, statement: str) -> str:
    return f"stock:{symbol.upper()}:{statement}"


def prepare_dsn(url: str) -> tuple:
    """Managed Postgres hosts (Neon, Supabase...) hand out URLs asyncpg cannot use as they are.
    Drops options asyncpg does not know (channel_binding), and turns off the prepared-statement cache for pooled endpoints
    (PgBouncer in transaction mode, host contains "-pooler"). Returns (dsn, extra create_pool keyword arguments)."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "channel_binding"]
    extra = {"statement_cache_size": 0} if "-pooler" in (parts.hostname or "") else {}
    return urlunsplit(parts._replace(query=urlencode(query))), extra


class Store:
    def __init__(self, pool: asyncpg.Pool, redis: aioredis.Redis, timescale: bool = False):
        self.pool, self.redis, self.timescale = pool, redis, timescale

    # ------------------------------------------------------------ lifecycle

    @classmethod
    async def connect(cls, settings: Optional[Settings] = None, migrate: bool = False) -> "Store":
        settings = settings or get_settings()
        dsn, extra = prepare_dsn(settings.database_url)
        # Idle connections are closed after 60 s: serverless Postgres (Neon) suspends after 5 idle minutes and would otherwise leave dead pooled connections.
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10, command_timeout=10, max_inactive_connection_lifetime=60, **extra)
        redis = aioredis.from_url(settings.redis_url, decode_responses=False, health_check_interval=30)
        store = cls(pool, redis)
        if migrate:
            await store.migrate()
        return store

    async def close(self):
        await self.pool.close()
        await self.redis.aclose()

    async def migrate(self):
        async with self.pool.acquire() as conn:
            await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                               "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.stem not in applied:
                    async with conn.transaction():
                        await conn.execute(path.read_text())
                        await conn.execute("INSERT INTO schema_migrations(version) VALUES($1)", path.stem)
            self.timescale = await self._enable_timescale(conn)

    async def _enable_timescale(self, conn) -> bool:
        available = await conn.fetchval("SELECT count(*) FROM pg_available_extensions WHERE name = 'timescaledb'")
        if not available:
            log.info("timescaledb not installed; price_daily stays a plain table")
            return False
        await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        await conn.execute("SELECT create_hypertable('price_daily', 'day', if_not_exists => TRUE, migrate_data => TRUE)")
        return True

    # ------------------------------------------------------------ writes (worker)

    async def save_snapshot(self, symbol: str, statement: str, sections: Dict[str, dict],
                            score_row: Optional[dict] = None, daily: Optional[dict] = None) -> Dict[str, str]:
        symbol = symbol.upper()
        generated = datetime.fromisoformat(sections["summary"]["meta"]["generatedAt"])
        encoded = {name: dumps(body) for name, body in sections.items()}
        etags = {name: etag_for(body) for name, body in encoded.items()}

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(
                """INSERT INTO snapshots(symbol, statement, section, body, etag, generated_at)
                   VALUES($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (symbol, statement, section)
                   DO UPDATE SET body = EXCLUDED.body, etag = EXCLUDED.etag, generated_at = EXCLUDED.generated_at""",
                [(symbol, statement, name, body.decode(), etags[name], generated) for name, body in encoded.items()],
            )
            if score_row:
                await self._upsert_score(conn, {**score_row, "statement": statement})
            if daily and daily.get("t"):
                await self._upsert_prices(conn, symbol, daily)
            if sections.get("events"):
                from .feed import save_announcements
                await save_announcements(conn, symbol, sections["summary"]["profile"].get("name") or symbol, sections["events"].get("announcements") or [])

        await self._cache(symbol, statement, encoded, etags)
        return etags

    async def _cache(self, symbol: str, statement: str, encoded: Dict[str, bytes], etags: Dict[str, str]):
        mapping: Dict[str, bytes] = {}
        for name, body in encoded.items():
            mapping[name] = body
            mapping[f"{name}:etag"] = etags[name].encode()
        key = stock_key(symbol, statement)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=mapping)
            await pipe.execute()

    async def _upsert_score(self, conn, row: dict):
        vals = [row.get(c) for c in SCORE_COLUMNS]
        vals[-1] = orjson.dumps(vals[-1]).decode() if vals[-1] else None
        await conn.execute(SCORE_UPSERT, *vals)
        if row.get("overall") is not None:
            await conn.execute(
                "INSERT INTO score_history (symbol, statement, model, day, overall, pillar_quality, pillar_growth, pillar_profitability, "
                "pillar_balance, pillar_technical) VALUES ($1, $2, $3, CURRENT_DATE, $4, $5, $6, $7, $8, $9) "
                "ON CONFLICT (symbol, statement, model, day) DO UPDATE SET overall = EXCLUDED.overall, pillar_quality = EXCLUDED.pillar_quality, "
                "pillar_growth = EXCLUDED.pillar_growth, pillar_profitability = EXCLUDED.pillar_profitability, "
                "pillar_balance = EXCLUDED.pillar_balance, pillar_technical = EXCLUDED.pillar_technical",
                row["symbol"], row["statement"], row.get("model") or "v1", row["overall"], row.get("pillar_quality"), row.get("pillar_growth"),
                row.get("pillar_profitability"), row.get("pillar_balance"), row.get("pillar_technical"))

    async def score_history(self, symbol: str, statement: str = "consolidated", model: str = "v1", limit: int = 400) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT day, overall, pillar_quality, pillar_growth, pillar_profitability, pillar_balance, pillar_technical FROM score_history "
                "WHERE symbol = $1 AND statement = $2 AND model = $3 ORDER BY day DESC LIMIT $4", symbol.upper(), statement, model, limit)
        return [{**dict(r), "day": r["day"].isoformat()} for r in reversed(rows)]

    async def health(self) -> dict:
        """Counts for the admin data-health panel: how much of the universe is loaded and what recently failed."""
        async with self.pool.acquire() as conn:
            universe = await conn.fetchval("SELECT count(*) FROM companies")
            loaded = await conn.fetchval("SELECT count(DISTINCT symbol) FROM snapshots WHERE section = 'summary'")
            scored = await conn.fetchval("SELECT count(*) FROM scores WHERE overall IS NOT NULL")
            queued = await conn.fetchval("SELECT count(*) FROM ingest_queue")
            last = await conn.fetchval("SELECT max(generated_at) FROM snapshots WHERE section = 'summary'")
            runs = await conn.fetch("SELECT status, count(*) AS n FROM ingest_runs WHERE started_at > now() - interval '24 hours' GROUP BY status")
            cal_res = await conn.fetchval("SELECT max(created_at) FROM feed_items WHERE source = 'FinEdge results calendar'")
            cal_res_to = await conn.fetchval("SELECT max(item_date) FROM feed_items WHERE source = 'FinEdge results calendar'")
            cal_ipo = await conn.fetchval("SELECT max(updated_at) FROM ipos WHERE ext_key IS NOT NULL")
            failed = await conn.fetch("SELECT symbol, status, started_at AS at, errors FROM ingest_runs WHERE status IN ('failed', 'rejected') ORDER BY id DESC LIMIT 15")
        return {"universe": universe, "loaded": loaded, "scored": scored, "queued": queued, "lastLoad": last.isoformat() if last else None,
                "calendars": {"resultsAt": cal_res.isoformat() if cal_res else None, "resultsThrough": cal_res_to.isoformat() if cal_res_to else None, "ipoAt": cal_ipo.isoformat() if cal_ipo else None},
                "runs24h": {r["status"]: r["n"] for r in runs},
                "recentProblems": [{"symbol": r["symbol"], "status": r["status"], "at": r["at"].isoformat(), "detail": str(r["errors"])[:200]} for r in failed]}

    async def _upsert_prices(self, conn, symbol: str, daily: dict):
        rows = [(symbol, date.fromisoformat(t), daily["o"][i], daily["h"][i], daily["l"][i], daily["c"][i], daily["v"][i])
                for i, t in enumerate(daily["t"])]
        await conn.execute("CREATE TEMP TABLE IF NOT EXISTS _prices (LIKE price_daily) ON COMMIT DROP")
        await conn.copy_records_to_table("_prices", records=rows)
        await conn.execute(
            """INSERT INTO price_daily SELECT * FROM _prices
               ON CONFLICT (symbol, day) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high,
               low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume""")
        # Dates FinEdge no longer reports (bad ticks we dropped) must not linger.
        await conn.execute("DELETE FROM price_daily WHERE symbol = $1 AND day >= $2 AND NOT (day = ANY($3::date[]))",
                           symbol, rows[0][1], [r[1] for r in rows])

    async def upsert_companies(self, rows: Iterable[dict]) -> int:
        records = [(str(r["symbol"]).upper(), r.get("name") or r["symbol"], r.get("nse_code"), r.get("bse_code"),
                    bool(r.get("consolidated_ind", True))) for r in rows if r.get("symbol")]
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """INSERT INTO companies(symbol, name, nse_code, bse_code, has_consolidated) VALUES($1, $2, $3, $4, $5)
                   ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name, nse_code = EXCLUDED.nse_code,
                   bse_code = EXCLUDED.bse_code, has_consolidated = EXCLUDED.has_consolidated, updated_at = now()""",
                records)
        await self.redis.delete(SEARCH_KEY)
        return len(records)

    async def set_company_meta(self, symbol: str, sector: Optional[str], industry: Optional[str]):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE companies SET sector = $2, industry = $3, updated_at = now() WHERE symbol = $1",
                               symbol.upper(), sector, industry)

    async def company(self, symbol: str) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM companies WHERE symbol = $1", symbol.upper())
        return dict(row) if row else None

    async def log_run(self, symbol: str, statement: str, status: str, calls: int, duration_ms: int, errors: dict):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO ingest_runs(symbol, statement, status, calls, duration_ms, errors, finished_at)
                   VALUES($1, $2, $3, $4, $5, $6::jsonb, now())""",
                symbol.upper(), statement, status, calls, duration_ms, json.dumps(errors))

    # ------------------------------------------------------------ queue

    QUEUE_FLAG = "ingest:queue:pending"

    async def enqueue(self, symbol: str, statement: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ingest_queue(symbol, statement) VALUES($1, $2) ON CONFLICT DO NOTHING",
                symbol.upper(), statement)
        try:  # lets the worker watch Redis instead of polling Postgres, so a serverless database (Neon) can sleep when idle
            await self.redis.set(self.QUEUE_FLAG, 1, ex=3600)
        except Exception:
            pass

    async def queue_length(self) -> int:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT count(*) FROM ingest_queue")

    async def claim(self, limit: int = 10) -> List[Tuple[str, str]]:
        async with self.pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                """DELETE FROM ingest_queue WHERE (symbol, statement) IN (
                       SELECT symbol, statement FROM ingest_queue ORDER BY requested_at
                       LIMIT $1 FOR UPDATE SKIP LOCKED)
                   RETURNING symbol, statement""", limit)
        return [(r["symbol"], r["statement"]) for r in rows]

    async def snapshot_symbols(self, older_than_hours: Optional[int] = None) -> List[Tuple[str, str]]:
        query = "SELECT symbol, statement FROM snapshots WHERE section = 'summary'"
        args: list = []
        if older_than_hours is not None:
            query += " AND generated_at < now() - make_interval(hours => $1)"
            args.append(older_than_hours)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query + " ORDER BY symbol", *args)
        return [(r["symbol"], r["statement"]) for r in rows]

    async def pending_symbols(self, statement: str = "consolidated", older_than_hours: int = 24, limit: Optional[int] = None) -> List[str]:
        """Universe companies with no snapshot yet (first) or an old one (after). NSE tickers come before numeric BSE-only codes (many of those are suspended), then in the order the universe was stored."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT c.symbol FROM companies c LEFT JOIN snapshots s ON s.symbol = c.symbol AND s.statement = $1 AND s.section = 'summary' "
                "WHERE s.symbol IS NULL OR s.generated_at < now() - make_interval(hours => $2) "
                "ORDER BY (s.symbol IS NOT NULL), (c.symbol ~ '^[0-9]+$'), c.updated_at, c.symbol LIMIT $3", statement, older_than_hours, limit or 100000)
        return [r["symbol"] for r in rows]

    # ------------------------------------------------------------ reads (API)

    async def get_section(self, symbol: str, statement: str, section: str) -> Optional[Tuple[bytes, str]]:
        key = stock_key(symbol, statement)
        body, etag = await self.redis.hmget(key, [section, f"{section}:etag"])
        if body is not None and etag is not None:
            return body, etag.decode()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT body, etag FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = $3",
                symbol.upper(), statement, section)
        if not row:
            return None
        body = row["body"].encode()
        await self.redis.hset(key, mapping={section: body, f"{section}:etag": row["etag"].encode()})
        return body, row["etag"]

    async def get_etag(self, symbol: str, statement: str, section: str) -> Optional[str]:
        etag = await self.redis.hget(stock_key(symbol, statement), f"{section}:etag")
        return etag.decode() if etag else None

    async def search_index(self) -> Tuple[bytes, bytes, str]:
        """Compact list for client-side search, pre-gzipped once (it is ~600 KB raw for ~5,700 stocks).
        Rows are [symbol, name, bse, ready], biggest company first; the NSE code is sent only when it differs from the symbol."""
        cached = await self.redis.hmget(SEARCH_KEY, ["body", "gzip", "etag"])
        if cached[0] is not None and cached[1] is not None:
            return cached[0], cached[1], cached[2].decode()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.symbol, c.name, c.nse_code, c.bse_code,
                          EXISTS(SELECT 1 FROM snapshots s WHERE s.symbol = c.symbol AND s.section = 'summary') AS ready
                   FROM companies c
                   LEFT JOIN LATERAL (SELECT market_cap FROM scores WHERE symbol = c.symbol AND market_cap IS NOT NULL ORDER BY updated_at DESC LIMIT 1) m ON true
                   ORDER BY m.market_cap DESC NULLS LAST, c.symbol""")  # biggest companies first: the order of the list is the ranking the search shows
        out = []
        for r in rows:
            row = [r["symbol"], r["name"], r["bse_code"], int(r["ready"])]
            if r["nse_code"] and r["nse_code"] != r["symbol"]:
                row.append(r["nse_code"])
            out.append(row)
        body = dumps({"fields": ["symbol", "name", "bse", "ready", "nse"], "rows": out})
        packed = gzip.compress(body, compresslevel=9, mtime=0)
        etag = etag_for(body)
        await self.redis.hset(SEARCH_KEY, mapping={"body": body, "gzip": packed, "etag": etag.encode()})
        await self.redis.expire(SEARCH_KEY, 3600)
        return body, packed, etag

    async def invalidate_search(self):
        await self.redis.delete(SEARCH_KEY)

    async def peer_rows(self, symbols: List[str], model: str = "v1") -> List[dict]:
        """Name, sector and (if already scored) score and price for each peer, in the given order."""
        if not symbols:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.symbol, c.name, c.sector, s.overall, s.band, s.price, s.market_cap, s.pe, s.roe
                   FROM companies c
                   LEFT JOIN LATERAL (SELECT * FROM scores WHERE symbol = c.symbol AND model = $2
                                      ORDER BY updated_at DESC LIMIT 1) s ON true
                   WHERE c.symbol = ANY($1::text[])""", symbols, model)
        found = {r["symbol"]: {k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in dict(r).items()} for r in rows}
        return [found.get(s, {"symbol": s, "name": None}) for s in symbols]

    async def top_scores(self, model: str = "v1", limit: int = 50) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {LIST_COLUMNS} FROM scores WHERE model = $1 ORDER BY overall DESC NULLS LAST LIMIT $2", model, limit)  # nosec B608 - fixed column list
        return [dict(r) for r in rows]

    async def screener_rows(self, model: str = "v1", statement: str = "consolidated", limit: int = 6000) -> List[dict]:
        """One row per company for the screener and comparison tool (client-side filtering, so no per-click queries)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT ON (symbol) {LIST_COLUMNS} FROM scores WHERE model = $1 "  # nosec B608 - fixed column list
                "ORDER BY symbol, (statement = $2) DESC, updated_at DESC LIMIT $3", model, statement, limit)
        return [dict(r) for r in rows]

    async def ping(self) -> Dict[str, bool]:
        status = {"postgres": False, "redis": False}
        try:
            async with self.pool.acquire() as conn:
                status["postgres"] = await conn.fetchval("SELECT 1") == 1
        except Exception:  # pragma: no cover - surfaced through /api/health
            log.exception("postgres ping failed")
        try:
            status["redis"] = bool(await self.redis.ping())
        except Exception:  # pragma: no cover
            log.exception("redis ping failed")
        return status
