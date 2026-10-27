"""Every listed company gets a score without a database that grows by 100 KB a company: the score row (about 5 KB) is kept for all, the report and
prices only for the top set and what people open. Covers the score-only save, who is picked for scoring, prune, and the screener list."""

import pytest

from finlit import worker
from finlit.finedge import FinEdgeClient
from test_integration import api, ingested, make_settings, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


async def counts(store, symbol):
    async with store.pool.acquire() as conn:
        return {t: await conn.fetchval(f"SELECT count(*) FROM {t} WHERE symbol = $1", symbol)  # nosec B608 - fixed table names
                for t in ("scores", "snapshots", "price_daily", "score_history")}


async def test_a_slim_load_keeps_the_score_and_not_the_report(store):
    async with FinEdgeClient(make_settings()) as client:
        await worker.refresh_universe(client, store)
        r = await worker.ingest_one(client, store, "RELIANCE", slim=True)
        assert r["status"] in ("ok", "warnings"), r
    c = await counts(store, "RELIANCE")
    assert c["scores"] == 1 and c["score_history"] == 1 and c["snapshots"] == 0 and c["price_daily"] == 0, c
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT overall, market_cap, sector FROM scores WHERE symbol = 'RELIANCE'")
        assert row["overall"] is not None and row["market_cap"] and row["sector"]
        assert (await conn.fetchval("SELECT sector FROM companies WHERE symbol = 'RELIANCE'"))     # the company gets its sector, so sector filters can list it
    # opening the company later builds the full report on top of the score
    async with FinEdgeClient(make_settings()) as client:
        await worker.ingest_one(client, store, "RELIANCE")
    c = await counts(store, "RELIANCE")
    assert c["scores"] == 1 and c["snapshots"] > 0 and c["price_daily"] > 0, c


async def test_who_is_scored_next(ingested):
    store = ingested
    async with store.pool.acquire() as conn:
        syms = [r["symbol"] for r in await conn.fetch("SELECT symbol FROM companies WHERE symbol <> 'RELIANCE' AND symbol ~ '^[A-Z]+$' ORDER BY symbol LIMIT 6")]
        big, small, fresh, stale, failed, _ = syms
        for s, mc in ((big, 500000), (small, 1000), (fresh, 7000), (stale, 8000), (failed, 9000)):
            await conn.execute("INSERT INTO listing_quotes(symbol, price, market_cap) VALUES ($1, 10, $2) ON CONFLICT (symbol) DO UPDATE SET market_cap = $2", s, mc)
        for s in (fresh, stale):
            await store._upsert_score(conn, {"symbol": s, "statement": "consolidated", "model": "v1", "overall": 60})
        await conn.execute("UPDATE scores SET updated_at = now() - interval '10 days' WHERE symbol = $1", stale)
    await store.log_run(failed, "consolidated", "failed", 1, 5, {})
    got = await store.slim_pending(days=7, limit=100000)
    assert "RELIANCE" not in got                       # its stored report is refreshed by the report job
    assert fresh not in got and failed not in got      # a recent score; a recent failure is not retried every night
    assert got.index(big) < got.index(small)           # the biggest first
    assert got.index(small) < got.index(stale) and got[-1] == stale     # never scored before merely old
    assert len(await store.slim_pending(days=7, limit=3)) == 3


async def test_prune_drops_the_heavy_part_and_keeps_every_score(ingested):
    store = ingested
    async with store.pool.acquire() as conn:
        await store._upsert_score(conn, {"symbol": "GHOSTCO", "statement": "consolidated", "model": "v1", "overall": 40})
    out = await store.prune(0)                         # nothing is in the kept set and nobody opened anything lately
    c = await counts(store, "RELIANCE")
    assert c["snapshots"] == 0 and c["price_daily"] == 0 and c["scores"] == 1, (c, out)
    assert (await counts(store, "GHOSTCO"))["scores"] == 0      # not in the symbol list any more: gone


async def test_the_universe_lists_every_company_scored_or_not(api):
    body = (await api.get("/api/screener/universe")).json()
    rows = body["rows"]
    assert len(body["as_of"]) == 10 and body["as_of"][4] == "-"      # the day the newest score was computed (the score screener states it)
    assert len(rows) > 5000                            # the whole symbol list, not just the stored reports
    by = {r["symbol"]: r for r in rows}
    assert by["RELIANCE"]["scored"] is True and by["RELIANCE"]["overall"] is not None
    other = next(r for r in rows if r["symbol"] != "RELIANCE")
    assert other["scored"] is False and other["overall"] is None and "pe" in other and other["pe"] is None     # every column present
    assert sum(r["scored"] for r in rows) == 1


async def test_score_all_is_capped_and_scores_slim(store, monkeypatch):
    async with FinEdgeClient(make_settings()) as client:
        await worker.refresh_universe(client, store)
        seen = []

        async def fake(_client, _store, items, parallel=2, yield_to_readers=False, slim=False):
            items = list(items)
            seen.append((len(items), slim))
            return [{"symbol": s, "status": "ok", "ms": 1, "errors": {}} for s, _ in items]
        monkeypatch.setattr(worker, "ingest_many", fake)
        out = await worker.score_all(client, store, limit=70, chunk=30)
    assert out["tried"] == 70 and out["ok"] == 70 and seen == [(30, True), (30, True), (10, True)], (out, seen)
    out = await worker.score_all(client, store, limit=70, chunk=30, max_minutes=0)       # a spent time budget starts nothing more
    assert out["tried"] == 0 and out["waiting"] == 70
