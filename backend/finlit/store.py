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

SCORE_COLUMNS = ("symbol", "statement", "model", "overall", "band", "pillar_quality", "pillar_growth",
                 "pillar_profitability", "pillar_balance", "pillar_technical", "price", "market_cap", "pe", "roe",
                 "dividend_yield", "sector", "name", "pb", "roce", "debt_to_equity", "sales_cagr", "profit_cagr",
                 "operating_margin", "change_pct", "return_1m", "return_1y")
SCORE_UPSERT = """
INSERT INTO scores (symbol, statement, model, overall, band, pillar_quality, pillar_growth, pillar_profitability,
                    pillar_balance, pillar_technical, price, market_cap, pe, roe, dividend_yield, sector, name, pb, roce,
                    debt_to_equity, sales_cagr, profit_cagr, operating_margin, change_pct, return_1m, return_1y, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, now())
ON CONFLICT (symbol, statement, model) DO UPDATE SET
    overall = EXCLUDED.overall, band = EXCLUDED.band, pillar_quality = EXCLUDED.pillar_quality,
    pillar_growth = EXCLUDED.pillar_growth, pillar_profitability = EXCLUDED.pillar_profitability,
    pillar_balance = EXCLUDED.pillar_balance, pillar_technical = EXCLUDED.pillar_technical,
    price = EXCLUDED.price, market_cap = EXCLUDED.market_cap, pe = EXCLUDED.pe, roe = EXCLUDED.roe,
    dividend_yield = EXCLUDED.dividend_yield, sector = EXCLUDED.sector, name = EXCLUDED.name, pb = EXCLUDED.pb,
    roce = EXCLUDED.roce, debt_to_equity = EXCLUDED.debt_to_equity, sales_cagr = EXCLUDED.sales_cagr,
    profit_cagr = EXCLUDED.profit_cagr, operating_margin = EXCLUDED.operating_margin,
    change_pct = EXCLUDED.change_pct, return_1m = EXCLUDED.return_1m, return_1y = EXCLUDED.return_1y, updated_at = now()
"""


def dumps(value: Any) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY)


def etag_for(body: bytes) -> str:
    return '"' + hashlib.blake2b(body, digest_size=10).hexdigest() + '"'


def stock_key(symbol: str, statement: str) -> str:
    return f"stock:{symbol.upper()}:{statement}"


class Store:
    def __init__(self, pool: asyncpg.Pool, redis: aioredis.Redis, timescale: bool = False):
        self.pool, self.redis, self.timescale = pool, redis, timescale

    # ------------------------------------------------------------ lifecycle

    @classmethod
    async def connect(cls, settings: Optional[Settings] = None, migrate: bool = False) -> "Store":
        settings = settings or get_settings()
        pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10, command_timeout=5)
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
        await conn.execute(SCORE_UPSERT, *[row.get(c) for c in SCORE_COLUMNS])

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

    async def enqueue(self, symbol: str, statement: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ingest_queue(symbol, statement) VALUES($1, $2) ON CONFLICT DO NOTHING",
                symbol.upper(), statement)

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
        Rows are [symbol, name, bse, ready]; the NSE code is sent only when it differs from the symbol."""
        cached = await self.redis.hmget(SEARCH_KEY, ["body", "gzip", "etag"])
        if cached[0] is not None and cached[1] is not None:
            return cached[0], cached[1], cached[2].decode()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.symbol, c.name, c.nse_code, c.bse_code,
                          EXISTS(SELECT 1 FROM snapshots s WHERE s.symbol = c.symbol AND s.section = 'summary') AS ready
                   FROM companies c ORDER BY c.symbol""")
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
                "SELECT * FROM scores WHERE model = $1 ORDER BY overall DESC NULLS LAST LIMIT $2", model, limit)
        return [dict(r) for r in rows]

    async def screener_rows(self, model: str = "v1", statement: str = "consolidated", limit: int = 6000) -> List[dict]:
        """One row per company for the screener and comparison tool (client-side filtering, so no per-click queries)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ON (symbol) * FROM scores WHERE model = $1 "
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
