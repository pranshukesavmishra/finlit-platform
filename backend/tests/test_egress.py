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


async def test_a_report_without_price_takes_it_from_the_listing_and_unscored_companies_carry_listing_figures(seeded):
    async with seeded.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET metrics = '{\"pe\": 12}'::jsonb, changed_at = now() WHERE symbol = 'BBB'")
        await conn.execute("INSERT INTO listing_quotes (symbol, price, change_pct, market_cap, high52, low52, volume) VALUES "
                           "('BBB', 55.5, 1.5, 777, 80, 40, 1000), ('CCC', 9.5, -2, 300, 12, 8, 500)")
    t = await data.get_table(seeded)
    b, c = t.pos["BBB"], t.pos["CCC"]
    assert t.cols["price"][b] == 55.5 and t.cols["market_cap"][b] == 777 and t.cols["pe"][b] == 12 and t.full[b]      # patched from the listing row
    assert t.cols["price"][c] == 9.5 and t.cols["ret_1d"][c] == -2 and not t.full[c] and t.cols["pe"][c] != t.cols["pe"][c]
    assert t.cols["price"][t.pos["AAA"]] == 10                                                                      # a report that holds its price keeps it
    fresh = await data._load(seeded)
    assert fresh.cols["price"] == t.cols["price"] and fresh.symbols == t.symbols


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


# ------------------------------------------------------------------ the quote job's reads


async def test_metrics_after_a_quote_patch_are_the_same_from_redis_the_database_or_the_full_sections(ingested, monkeypatch):  # noqa: F811
    import orjson
    from finlit.screener.compute import compute
    from finlit.screener.jobs import SECTIONS, refresh_metrics_for
    st = ingested
    async with st.pool.acquire() as conn:
        rows = await conn.fetch("SELECT section, body FROM snapshots WHERE symbol = 'RELIANCE' AND statement = 'consolidated' AND section = ANY($1::text[])", list(SECTIONS))
    want = compute({r["section"]: json.loads(r["body"]) for r in rows})
    assert len(want) > 100

    async def stored():
        async with st.pool.acquire() as conn:
            return json.loads(await conn.fetchval("SELECT metrics FROM scores WHERE symbol = 'RELIANCE' AND statement = 'consolidated' AND model = 'v1'"))

    from finlit.store import INPUT_SECTIONS, cut_input
    await st.redis.delete("mi:RELIANCE:consolidated")
    from_pg = (await st.metric_inputs([("RELIANCE", "consolidated")]))[("RELIANCE", "consolidated")]
    full = {r["section"]: json.loads(r["body"]) for r in rows}
    assert set(from_pg) == set(INPUT_SECTIONS) and "glossary" not in from_pg["ratios"]
    assert from_pg == {k: json.loads(json.dumps(cut_input(k, full[k]))) for k in INPUT_SECTIONS}      # the cut made in SQL is the cut made in Python
    await st.redis.delete("mi:RELIANCE:consolidated")
    assert await refresh_metrics_for(st, [("RELIANCE", "consolidated")]) == 1                     # inputs from Postgres (price history cut inside the database)
    assert await stored() == orjson.loads(orjson.dumps(want))
    assert await st.redis.exists("mi:RELIANCE:consolidated")

    calls, real = [], type(st.pool).acquire
    monkeypatch.setattr(type(st.pool), "acquire", lambda self, **k: (calls.append(1), real(self, **k))[1])
    got = await st.metric_inputs([("RELIANCE", "consolidated")])                                  # inputs from Redis: no connection taken at all
    monkeypatch.undo()
    assert not calls and set(got[("RELIANCE", "consolidated")]) == {"financials", "ratios", "ownership", "events", "stats", "price"}
    assert await refresh_metrics_for(st, [("RELIANCE", "consolidated")]) == 1
    assert await stored() == orjson.loads(orjson.dumps(want))


async def test_a_full_load_stores_the_cached_inputs_and_a_prune_drops_them(ingested):  # noqa: F811
    st = ingested
    assert await st.redis.exists("mi:RELIANCE:consolidated")                                      # ingest_one stored them
    got = await st.metric_inputs([("RELIANCE", "consolidated")])
    assert got[("RELIANCE", "consolidated")]["price"]["daily"].keys() == {"t", "c", "v"}          # only what the figures read
    await st.prune(keep_top=0, keep_viewed_days=0)
    assert not await st.redis.exists("mi:RELIANCE:consolidated")


# ------------------------------------------------------------------ the other readers


async def test_alert_statement_figures_are_the_same_when_cut_inside_the_database(ingested):  # noqa: F811
    from finlit import alertengine as ae
    async with ingested.pool.acquire() as conn:
        got = (await ae.load_values(conn, ["RELIANCE"], set(ae.SNAP)))["RELIANCE"]
        fin = json.loads(await conn.fetchval("SELECT body FROM snapshots WHERE symbol = 'RELIANCE' AND statement = 'consolidated' AND section = 'financials'"))
        own = json.loads(await conn.fetchval("SELECT body FROM snapshots WHERE symbol = 'RELIANCE' AND statement = 'consolidated' AND section = 'ownership'"))
    rows = fin["quarterly"]["pl"]["rows"]
    last = lambda xs: float([x for x in xs if x is not None][-1])  # noqa: E731
    assert got["q_net_profit"] == last(rows["net_profit"]) and got["q_revenue"] == last(rows["revenue"])
    g = ae.quarter_gap(rows)
    assert got["rev_profit_gap"] == (g["gap"] if g else None) and (g is None or got["_gap_detail"]["gap"] == g["gap"])
    for key, col in (("promoters", "promoter_chg"), ("fii", "fii_chg")):
        v = [x for x in own["series"][key] if x is not None]
        assert got[col] == round(float(v[-1]) - float(v[-2]), 2)


async def test_saved_screens_read_only_the_figures_they_filter_on(ingested):  # noqa: F811
    from finlit.screens import matches
    async with ingested.pool.acquire() as conn:
        full = dict(await conn.fetchrow("SELECT * FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1' ORDER BY updated_at DESC"))
        cut = dict(await conn.fetchrow(
            "SELECT symbol, name, sector, macro_sector, industry, band, (SELECT jsonb_object_agg(e.key, e.value) FROM jsonb_each(metrics) e WHERE e.key = ANY($1::text[])) AS metrics "
            "FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1' ORDER BY updated_at DESC", ["pe", "roe"]))
    assert set(json.loads(cut["metrics"]) if isinstance(cut["metrics"], str) else cut["metrics"]) == {"pe", "roe"}
    for state in ({"ranges": {"pe": {"max": 1000}}}, {"ranges": {"pe": {"max": 1}}}, {"ranges": {"roe": {"min": 0}, "pe": {"min": 0}}, "bands": [full["band"]]}):
        assert matches(full, state) == matches(cut, state)


async def test_results_declarations_come_from_redis_while_the_feed_is_unchanged_and_a_quarter_is_rebuilt_only_when_something_moved(ingested, monkeypatch):  # noqa: F811
    from finlit import results as R
    st = ingested
    R.reset()
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, source, item_date, dedupe) VALUES ('result', 'Results', 'RELIANCE', 'Reliance', $1, current_date, 'egress-1')",
                           R.SOURCE_RESULTS)
    reads = []
    real = R.assign
    monkeypatch.setattr(R, "assign", lambda rows: (reads.append(len(rows)), real(rows))[1])
    first = await R._declarations(st)
    second = await R._declarations(st)
    assert len(reads) == 1 and first == second and first                                          # the second came from Redis
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, source, item_date, dedupe) VALUES ('result', 'Results', 'TCS', 'TCS', $1, current_date, 'egress-2')", R.SOURCE_RESULTS)
    await R._declarations(st)
    assert len(reads) == 2                                                                         # the feed moved: read again
    qkey = R.quarter_key(R.quarter_end_before(R.today_ist()))
    e = await R.get_entry(st, qkey, force=True)
    builds = []
    real_build = R._build
    monkeypatch.setattr(R, "_build", lambda *a, **k: (builds.append(1), real_build(*a, **k))[1])
    e.loaded -= 99999
    await R._refresh_entry(st, qkey)
    assert not builds and time.time() - e.loaded < 5                                               # nothing moved: the rows are as current as a rebuild
    async with st.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET changed_at = now() WHERE symbol = 'RELIANCE'")
    await R._refresh_entry(st, qkey)
    assert builds == [1]
    R.reset()


async def test_search_quotes_rows_are_kept_in_redis_and_only_changed_companies_are_read(ingested):  # noqa: F811
    from finlit import search
    import orjson
    import zlib
    st = ingested
    await st.redis.delete(search.RAW_KEY)
    first = await search._raw_rows(st)
    state = orjson.loads(zlib.decompress(await st.redis.get(search.RAW_KEY)))
    assert len(first) > 5000
    async with st.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET price = 123.45, changed_at = now() WHERE symbol = 'RELIANCE'")
    second = await search._raw_rows(st)
    after = orjson.loads(zlib.decompress(await st.redis.get(search.RAW_KEY)))
    assert after["full_at"] == state["full_at"]                                                    # a delta, not a rebuild of everything
    assert {r["symbol"]: r for r in second}["RELIANCE"]["sp"] == 123.45 and [r["symbol"] for r in second] == [r["symbol"] for r in first]
    await st.redis.delete(search.RAW_KEY)
    fresh = await search._raw_rows(st)
    assert {r["symbol"]: r for r in fresh} == {r["symbol"]: r for r in second}                     # same as reading everything


async def test_the_quote_job_remembers_who_it_quotes(ingested):  # noqa: F811
    st = ingested
    await st.redis.delete("quotes:symbols")
    assert await st.quote_symbols() == [("RELIANCE", "consolidated")]
    async with st.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots")
    assert await st.quote_symbols() == [("RELIANCE", "consolidated")]                             # from Redis: no query
    await st.redis.delete("quotes:symbols")
    assert await st.quote_symbols() == []


# ---- the listing takes the exchange's close from Dhan, and a Saturday report write does not beat Friday's quote
async def test_dhan_overlay_replaces_price_and_move_and_keeps_provider_for_the_rest(monkeypatch):
    from finlit import dhan
    from finlit.screener import listing

    async def fake_map(store, symbols):
        return {"RELIANCE": ("NSE_EQ", "2885")}

    class DC:
        configured = True

        async def quotes(self, ids):
            return {("NSE_EQ", "2885"): {"last_price": 1190.0, "net_change": 5.45, "volume": 1000, "last_trade_time": "23/10/2026 15:29:58"}}
    monkeypatch.setattr(dhan, "security_map", fake_map)
    recs = [{"symbol": "RELIANCE", "price": 1190.0, "change_pct": 1.19, "market_cap": 1000.0, "high52": None, "low52": None, "volume": 5, "traded_at": None},
            {"symbol": "TCS", "price": 2528.0, "change_pct": 1.0, "market_cap": 500.0, "high52": None, "low52": None, "volume": 5, "traded_at": None}]
    assert await listing.dhan_overlay(recs, None, DC()) == 1
    assert recs[0]["change_pct"] == 0.46 and recs[0]["volume"] == 1000 and recs[0]["traded_at"].day == 23
    assert recs[1]["change_pct"] == 1.0


def test_report_beats_the_listing_row_only_from_a_later_session():
    from datetime import datetime, timezone
    from finlit import search
    ist = search.IST
    fri_close = datetime(2026, 10, 23, 15, 29, tzinfo=ist)
    sat_write = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
    base = {"symbol": "X", "overall": 70, "band": "good", "sp": 100.0, "sc": 1.19, "qp": 101.0, "qc": 0.46, "qt": fri_close, "su": sat_write, "sha8": None}
    assert search.quote_rows([base], "gold", set())[0][2] == 0.46
    newer = {**base, "su": datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)}
    assert search.quote_rows([newer], "gold", set())[0][2] == 1.19
