"""Database egress: the screener table is cached and kept current by a probe and small deltas; the Dhan instrument map is cached by a version stamp;
the quote job reads what it can from Redis; the admin query-statistics endpoint. Neon bills every byte the database sends (docs/NEON-EGRESS.md)."""

import json
import time

import pytest

from finlit import dhan
from finlit.screener import data
from test_auth import app, make_admin, new_client  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, store  # noqa: F401


async def score(conn, sym, st, pe, sector="Test", name=None):
    await conn.execute(
        "INSERT INTO scores (symbol, statement, model, sector, name, metrics) VALUES ($1, $2, 'v1', $3, $4, $5::jsonb) "
        "ON CONFLICT (symbol, statement, model) DO UPDATE SET metrics = EXCLUDED.metrics, changed_at = now()",
        sym, st, sector, name or sym, json.dumps({"market_cap": 1000, "price": 10, "pe": pe}))


@pytest.fixture
async def seeded(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        for t in ("listing_quotes", "index_members", "dhan_instruments"):
            await conn.execute(f"DELETE FROM {t}")  # nosec B608 - fixed names
        await conn.execute("DELETE FROM companies")
        for s in ("AAA", "BBB", "CCC"):
            await conn.execute("INSERT INTO companies (symbol, name, nse_code) VALUES ($1, $1, $1)", s)
        await score(conn, "AAA", "consolidated", 10)
        await score(conn, "AAA", "standalone", 99)
        await score(conn, "BBB", "consolidated", 20)
        await conn.execute("UPDATE scores SET changed_at = now() - interval '1 hour' WHERE symbol <> 'BBB'")   # older than the overlap a delta re-reads
        await conn.execute("UPDATE scores SET changed_at = now() - interval '3 hours' WHERE symbol = 'BBB'")
    data.reset()
    yield store
    data.reset()


def spy(monkeypatch, *names):
    calls = {n: 0 for n in names}
    for n in names:
        orig = getattr(data, n)

        def wrap(*a, _o=orig, _n=n, **k):
            calls[_n] += 1
            return _o(*a, **k)
        monkeypatch.setattr(data, n, wrap)
    return calls


def pe(t, sym):
    return t.cols["pe"][t.pos[sym]]


async def test_probe_that_sees_no_change_reads_no_rows(seeded, monkeypatch):
    t1 = await data.get_table(seeded)
    assert t1.n == 3 and t1.n_full == 2 and pe(t1, "AAA") == 10
    calls = spy(monkeypatch, "_score_rows", "_listing", "_extras", "_full")
    t1.loaded -= 99999
    await data._sync(seeded)
    assert data._table is t1 and calls == {"_score_rows": 0, "_listing": 0, "_extras": 0, "_full": 0}    # one probe, nothing fetched
    assert time.time() - t1.loaded < 5                                                                    # and the table counts as fresh again


async def test_delta_fetches_only_changed_symbols_and_prefers_the_consolidated_row(seeded, monkeypatch):
    await data.get_table(seeded)
    seen = []
    orig = data._score_rows

    async def watch(store, symbols=None, since=None):
        out = await orig(store, symbols, since)
        seen.append(sorted(out))
        return out
    monkeypatch.setattr(data, "_score_rows", watch)
    async with seeded.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET metrics = jsonb_set(metrics, '{pe}', '77'), changed_at = now() WHERE symbol = 'AAA' AND statement = 'standalone'")
    await data._sync(seeded)
    assert seen == [["AAA"]]                                                  # BBB did not move: not read
    assert pe(data._table, "AAA") == 10                                       # the standalone row changed, the consolidated one still wins
    async with seeded.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET metrics = jsonb_set(metrics, '{pe}', '11'), changed_at = now() WHERE symbol = 'AAA' AND statement = 'consolidated'")
        await score(conn, "CCC", "standalone", 5)                             # a company that has just been scored joins the full rows
        await conn.execute("UPDATE scores SET changed_at = now() WHERE symbol = 'CCC'")
    await data._sync(seeded)
    assert pe(data._table, "AAA") == 11 and pe(data._table, "CCC") == 5 and data._table.n == 3 and data._table.n_full == 3
    assert [s for s in seen[1:] for s in s] == ["AAA", "CCC"]


async def test_delta_table_equals_a_fresh_full_load(seeded):
    await data.get_table(seeded)
    async with seeded.pool.acquire() as conn:
        await score(conn, "BBB", "consolidated", 33)
        await conn.execute("UPDATE scores SET changed_at = now() WHERE symbol = 'BBB'")
    await data._sync(seeded)
    fresh = await data._load(seeded)
    t = data._table
    assert t.symbols == fresh.symbols and t.cols["pe"] == fresh.cols["pe"] and t.cols["market_cap"] == fresh.cols["market_cap"] and t.name == fresh.name


async def test_full_reload_only_when_the_saved_rows_are_old_and_a_reconcile_drops_pruned_companies(seeded, monkeypatch):
    await data.get_table(seeded)
    calls = spy(monkeypatch, "_full", "_reconcile")
    async with seeded.pool.acquire() as conn:
        await conn.execute("DELETE FROM scores WHERE symbol = 'BBB'")          # pruned
    await data._sync(seeded)                                                    # the count moved and no row was written: reconciled at once
    assert calls == {"_full": 0, "_reconcile": 1} and data._table.n_full == 1  # BBB is now a listing-only row
    state = data._unpack(data._blob)
    state["recon_at"] -= data.RECONCILE_EVERY + 1
    data._blob = data._pack(state)
    await data._sync(seeded)
    assert calls == {"_full": 0, "_reconcile": 2}                               # every 6 hours
    state = data._unpack(data._blob)
    state["full_at"] -= data.FULL_EVERY + 1
    data._blob = data._pack(state)
    await data._sync(seeded)
    assert calls["_full"] == 1


async def test_a_restart_reads_redis_not_postgres_and_a_redis_miss_falls_back_to_postgres(seeded, monkeypatch):
    await data.get_table(seeded)
    assert await seeded.redis.exists(f"{data.CACHE_KEY}:{seeded.db_tag}")
    data.reset()                                                                # a restart: memory is gone, Redis is not
    calls = spy(monkeypatch, "_score_rows", "_full")
    t = await data.get_table(seeded)
    assert t.n == 3 and calls == {"_score_rows": 0, "_full": 0}
    data.reset()
    await seeded.redis.flushdb()                                                # evicted
    t = await data.get_table(seeded)
    assert t.n == 3 and calls["_full"] == 1
    data.reset()

    async def down(*a, **k):
        raise ConnectionError("redis is down")
    monkeypatch.setattr(seeded.redis, "get", down)
    monkeypatch.setattr(seeded.redis, "set", down)
    t = await data.get_table(seeded)                                            # no Redis at all: still a table
    assert t.n == 3 and calls["_full"] == 2


async def test_another_database_never_reuses_the_saved_rows(seeded):
    await data.get_table(seeded)
    async with seeded.pool.acquire() as conn:
        await conn.execute("DELETE FROM scores")
    data.reset()
    t = await data.get_table(seeded)                                            # the probe sees an empty database where rows were saved: start again
    assert t.n_full == 0


async def test_market_hours_gap(monkeypatch):
    from datetime import datetime
    ist = lambda *a: datetime(*a, tzinfo=data.IST).timestamp()  # noqa: E731
    assert data.in_market_hours(ist(2026, 10, 26, 10, 30)) and not data.in_market_hours(ist(2026, 10, 26, 17, 0))
    assert not data.in_market_hours(ist(2026, 10, 25, 10, 30))                  # a Sunday
    assert data.MARKET_GAP > data.OFF_GAP


async def test_security_map_is_cached_until_the_instrument_version_moves(seeded):
    async with seeded.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '1', 'AAA', 'EQ')")
    assert await dhan.security_map(seeded, ["AAA", "BBB"]) == {"AAA": ("NSE_EQ", "1")}
    async with seeded.pool.acquire() as conn:
        await conn.execute("UPDATE dhan_instruments SET security_id = '2'")
    assert await dhan.security_map(seeded, ["AAA", "BBB"]) == {"AAA": ("NSE_EQ", "1")}   # no query: the cached map
    await dhan.bump_version(seeded)                                                       # what refresh-instruments and the company reload do
    assert await dhan.security_map(seeded, ["AAA", "BBB"]) == {"AAA": ("NSE_EQ", "2")}
    async with seeded.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '3', 'CCC', 'EQ')")
    got = await dhan.security_map(seeded, ["AAA", "CCC"])                                 # a symbol the cache has not seen is asked of the database
    assert got == {"AAA": ("NSE_EQ", "2"), "CCC": ("NSE_EQ", "3")}


async def test_security_map_works_without_redis(seeded, monkeypatch):
    async with seeded.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '1', 'AAA', 'EQ')")

    async def down(*a, **k):
        raise ConnectionError("redis is down")
    for m in ("get", "set", "incr"):
        monkeypatch.setattr(seeded.redis, m, down)
    assert await dhan.security_map(seeded, ["AAA"]) == {"AAA": ("NSE_EQ", "1")}


# ------------------------------------------------------------------ pg_stat_statements


class NoExt:
    async def fetchval(self, *a):
        return None


class Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class Ctx:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False
        return Ctx()


async def test_usage_report_says_plainly_when_the_extension_is_missing():
    from finlit import dbusage
    out = await dbusage.report(Pool(NoExt()))
    assert out["enabled"] is False and "pg_stat_statements" in out["message"] and out["top"] == []


async def test_usage_report_survives_an_extension_that_is_installed_but_not_loaded():
    from finlit import dbusage

    class NotLoaded:
        async def fetchval(self, *a):
            return 1

        async def fetch(self, *a):
            raise RuntimeError('pg_stat_statements must be loaded via "shared_preload_libraries"')
    out = await dbusage.report(Pool(NotLoaded()))
    assert out["enabled"] is False and out["top"] == []


async def test_usage_report_ranks_by_rows_and_trims_the_query():
    from finlit import dbusage

    class Rows:
        async def fetchval(self, *a):
            return 1

        async def fetch(self, *a):
            return [{"query": "SELECT " + "x, " * 200 + "y FROM scores", "calls": 4, "rows": 40000, "total_exec_time": 12.5, "bytes_est": 1}]
    out = await dbusage.report(Pool(Rows()))
    t = out["top"][0]
    assert out["enabled"] and t["calls"] == 4 and t["rowsPerCall"] == 10000 and len(t["query"]) <= dbusage.QUERY_CHARS + 1 and t["query"].startswith("SELECT x, x")


async def test_db_usage_endpoint_is_admin_only(app):  # noqa: F811
    from test_auth import signed_in
    import time as _t
    from finlit.auth import crypto
    anon = new_client(app)
    assert (await anon.get("/api/admin/db-usage")).status_code in (401, 403)
    silver = await signed_in(app, "dbu@example.com", plan="silver")
    assert (await silver.get("/api/admin/db-usage")).status_code == 403
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(_t.time()) // 30)})
    r = await admin.get("/api/admin/db-usage")
    assert r.status_code == 200 and "enabled" in r.json() and isinstance(r.json()["top"], list)
    for c in (anon, silver, admin):
        await c.aclose()
