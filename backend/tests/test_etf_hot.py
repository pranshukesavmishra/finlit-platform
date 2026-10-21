"""ETF returns block (1 day / 1 year / 5 years), hot and cold storage, and holdings / facts. Same recorded Upstox and AMFI answers as test_etf.py.

The returns are recomputed here from the raw recorded candles with code that shares nothing with finlit/etf.py, and compared with what the API serves.
"""

import calendar
import json
import sys
import types
from datetime import date, datetime, timedelta

import httpx
import pytest

from finlit import etf
from finlit.config import Settings
from finlit.api import create_app
from test_etf import BY_KEY, CANDLES, NOW, S, Provider, api, store, FX                       # noqa: F401  (fixtures)
from test_integration import TEST_DB, TEST_REDIS, make_settings


def etf_quotes():
    return json.loads((FX / "quotes.json").read_text())


def raw_closes(symbol):
    """(dates, closes, volumes) oldest first, straight from the recorded Upstox candle rows (one close per date, last one wins)."""
    key = next(k for k, v in BY_KEY.items() if v == symbol)
    byday = {}
    for row in CANDLES[symbol]:
        byday[row[0][:10]] = (float(row[4]), float(row[5] or 0))
    q = next((v for v in etf_quotes().values() if v["symbol"] == symbol), None)               # tonight's close comes from the recorded quote (history lags a day)
    if q:
        qd = datetime.fromtimestamp(int(q["last_trade_time"]) / 1000, etf.IST).date().isoformat()
        if qd > max(byday):
            byday[qd] = (float(q["last_price"]), float(q["volume"] or 0))
    ds = sorted(byday)
    return [date.fromisoformat(d) for d in ds], [byday[d][0] for d in ds], [byday[d][1] for d in ds]


def back(d, months):
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def indep_return(ds, cs, months):
    """Close on the last day, against the close on (or the last trading day before) the same calendar day `months` earlier; None when there is none."""
    target = back(ds[-1], months)
    base = [c for d, c in zip(ds, cs) if d <= target]
    if not base or (target - max(d for d in ds if d <= target)).days > 10:
        return None
    return (cs[-1] / base[-1] - 1) * 100


CLEAN = ["NIFTYBEES", "GOLDBEES", "SILVERBEES", "LIQUIDBEES", "BANKBEES"]


async def test_one_year_five_year_and_one_day_match_the_raw_candles(api):
    checked = 0
    for sym in CLEAN:
        if sym not in CANDLES:
            continue
        ds, cs, _ = raw_closes(sym)
        b = (await api.get(f"/api/etf/{sym}")).json()
        head = {h["key"]: h for h in b["headline"]}
        assert [h["key"] for h in b["headline"]] == ["1d", "1y", "5y"]
        assert head["1d"]["value"] == round((cs[-1] / cs[-2] - 1) * 100, 2), sym
        assert b["changePct"] == head["1d"]["value"] and b["previousClose"] == round(cs[-2], 4) and b["price"] == round(cs[-1], 4)
        assert head["1d"]["from"]["date"] == ds[-2].isoformat() and head["1d"]["to"]["date"] == ds[-1].isoformat()
        for key, months in (("1y", 12), ("5y", 60)):
            want = indep_return(ds, cs, months)
            if want is None:
                assert head[key]["value"] is None and head[key]["why"], (sym, key)
            else:
                assert head[key]["value"] == round(want, 2), (sym, key, head[key]["value"], want)
                assert head[key]["from"]["date"] <= back(ds[-1], months).isoformat() and head[key]["to"]["close"] == round(cs[-1], 4)
                assert round((head[key]["to"]["close"] / head[key]["from"]["close"] - 1) * 100, 2) == head[key]["value"]
        checked += 1
    assert checked >= 5


async def test_every_etf_matches_the_independent_calculation_or_says_why(api):
    items = (await api.get("/api/etf?limit=100")).json()["items"]
    assert len(items) == 17
    for it in items:
        sym = it["symbol"]
        ds, cs, _ = raw_closes(sym)
        if it["breakDate"] is None:
            for key, months in (("ret1y", 12), ("ret5y", 60)):
                want = indep_return(ds, cs, months)
                assert (it[key] is None) == (want is None), (sym, key)
                if want is not None:
                    assert it[key] == round(want, 2), (sym, key)
            assert it["changePct"] == round((cs[-1] / cs[-2] - 1) * 100, 2), sym
        else:
            assert it["breakDate"] <= it["priceDate"], sym             # a split in the series: only prices after it are used (checked by test_etf.py)


async def test_five_year_is_stated_as_a_total_not_per_year(api):
    b = (await api.get("/api/etf/NIFTYBEES")).json()
    h5 = next(h for h in b["headline"] if h["key"] == "5y")
    assert "total" in h5["basis"] and "not per year" in h5["basis"]
    if h5["value"] is not None:
        assert h5["annualised"] == b["cagr5y"] and h5["annualised"] != h5["value"]


def test_headline_withholds_a_change_that_is_itself_the_break():
    v = {"changePct": None, "ret1y": None, "ret5y": None, "cagr5y": None}
    ds = [date(2026, 10, 1) + timedelta(days=i) for i in range(5)]
    out = etf.headline(v, {"change": "jumped", "ret_1y": "break", "ret_5y": "break"}, ds, [10, 10, 10, 10, 20], ds[-1])
    assert [h["value"] for h in out] == [None, None, None] and out[0]["why"] == "jumped" and out[0]["from"] is None


async def test_a_jump_on_the_last_day_gives_no_one_day_figure(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    ds = [date(2026, 9, 1) + timedelta(days=i) for i in range(30)]
    cs = [100.0 + i * 0.1 for i in range(29)] + [180.0]
    m = etf.build_metrics(ds, cs, [], [], None, ds[-1])
    async with store.pool.acquire() as conn:
        await etf._write_row(conn, "NIFTYBEES", ds, cs, [0.0] * 30, m, None, None, None)
        r = dict(await conn.fetchrow("SELECT change_pct, prev_close, price, reasons FROM etf_funds WHERE symbol='NIFTYBEES'"))
    assert r["change_pct"] is None and r["price"] == 180.0 and r["prev_close"] == pytest.approx(102.8)
    assert "withheld" in json.loads(r["reasons"])["change"] and "30 Sep 2026" in json.loads(r["reasons"])["change"]


# ------------------------------------------------------------------------------------------------------------ hot / cold
async def test_traded_value_ranking_matches_raw_price_times_volume(api, store):
    want = {}
    for sym in BY_KEY.values():
        ds, cs, vs = raw_closes(sym)
        pairs = [(c, v) for c, v in zip(cs, vs) if v > 0][-20:]
        want[sym] = sum(c * v for c, v in pairs) / len(pairs) if len(pairs) >= 10 else None
    async with store.pool.acquire() as conn:
        rows = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, avg_turnover, turnover_rank, hot FROM etf_funds")}
    for sym, w in want.items():
        got = rows[sym]["avg_turnover"]
        assert (got is None) == (w is None), sym
        if w is not None:
            assert got == pytest.approx(w, rel=1e-9), sym
    order = [s for s, w in sorted(((s, w) for s, w in want.items() if w is not None), key=lambda kv: (-kv[1], kv[0]))]
    assert [s for s, r in sorted(rows.items(), key=lambda kv: kv[1]["turnover_rank"] or 10**6) if r["turnover_rank"]] == order
    assert {s for s, r in rows.items() if r["hot"]} == set(order)                    # fewer than 100 ETFs with a figure: all of those are hot
    assert [s for s, r in rows.items() if not r["turnover_rank"]] and not any(rows[s]["hot"] for s, r in rows.items() if not r["turnover_rank"])


async def test_only_hot_etfs_keep_packed_history_but_every_etf_keeps_its_returns(store, monkeypatch):
    monkeypatch.setattr(etf, "HOT_N", 5)
    r = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    assert r["status"] == "ok" and r["hot"] == 5
    async with store.pool.acquire() as conn:
        hist = {x["symbol"] for x in await conn.fetch("SELECT symbol FROM etf_history")}
        hot = [x["symbol"] for x in await conn.fetch("SELECT symbol FROM etf_funds WHERE hot ORDER BY turnover_rank")]
        in_table = [x["symbol"] for x in await conn.fetch("SELECT symbol FROM etf_hot ORDER BY rank")]
        narrow = await conn.fetch("SELECT symbol, change_pct, ret_1y, ret_5y, price FROM etf_funds WHERE avg_turnover IS NOT NULL")
    assert hist == set(hot) == set(in_table) and in_table == hot and len(narrow) == 16
    cold = [n for n in narrow if n["symbol"] not in hot]
    assert len(cold) == 11 and all(n["price"] and n["change_pct"] is not None for n in cold) and any(n["ret_1y"] is not None for n in cold)
    # next night: the ETF that is no longer hot loses its packed history, one that became hot gets it
    monkeypatch.setattr(etf, "HOT_N", 3)
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW + timedelta(hours=1))
    async with store.pool.acquire() as conn:
        assert {x["symbol"] for x in await conn.fetch("SELECT symbol FROM etf_history")} == set(hot[:3])


async def test_hot_list_fast_path_equals_the_full_path(api, store):
    fast = (await api.get("/api/etf?limit=10")).json()
    assert fast["hotCount"] == 16 and fast["total"] == 17 and fast["universe"] == 17
    assert await store.redis.exists(etf.HOT_KEY) and await store.redis.exists(etf.ALL_KEY)
    # same page without Redis, without the etf_hot table: the full path must give exactly the same items and counts
    await store.redis.delete(etf.HOT_KEY, etf.ALL_KEY)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM etf_hot")
    api._transport.app.state.etf_cache = None
    api._transport.app.state.etf_hot = None
    slow = (await api.get("/api/etf?limit=10")).json()
    for k in ("items", "total", "universe", "categories", "groups", "asOf"):
        assert slow[k] == fast[k], k
    assert [i["rank"] for i in fast["items"]] == list(range(1, 11)) and all(i["hot"] for i in fast["items"])


async def test_redis_rows_round_trip_exactly(store):
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    async with store.pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch("SELECT * FROM etf_funds WHERE active ORDER BY avg_turnover DESC NULLS LAST, symbol")]
    back_ = etf._unpack_rows(etf._pack_rows(rows))
    assert [etf.row_view(r) for r in back_] == [etf.row_view(r) for r in rows]


async def test_cold_etf_is_fetched_when_opened_then_served_from_redis(store, monkeypatch):
    monkeypatch.setattr(etf, "HOT_N", 3)
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    async with store.pool.acquire() as conn:
        cold = (await conn.fetchrow("SELECT symbol FROM etf_funds WHERE NOT hot AND avg_turnover IS NOT NULL ORDER BY turnover_rank LIMIT 1"))["symbol"]
        assert await conn.fetchval("SELECT count(*) FROM etf_history WHERE symbol=$1", cold) == 0
    prov = Provider()
    real = etf.UpstoxClient
    monkeypatch.setattr(etf, "UpstoxClient", lambda s, r, transport=None: real(s, r, transport=httpx.MockTransport(prov) if transport is None else transport))
    app = create_app(make_settings(upstox_access_token="placeholder"), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            b = (await c.get(f"/api/etf/{cold}")).json()
            assert b["series"]["available"] and b["hot"] is False
            ds, cs, _ = raw_closes(cold)
            assert b["series"]["points"][-1][0] == b["priceDate"] and b["headline"][0]["from"]["date"] == ds[-2].isoformat()
            n = len([u for u in prov.calls if "historical-candle" in u])
            assert n == 1
            ttl = await store.redis.ttl(f"etf:hist:{cold}")
            assert 13 * 86400 < ttl <= etf.HIST_TTL
            await c.get(f"/api/etf/{cold}?range=5Y")
            assert len([u for u in prov.calls if "historical-candle" in u]) == n                  # second open: Redis, no new call
            # tonight's refresh brings the cached history up to date without touching its 14 days
            await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW + timedelta(hours=1))
            assert 13 * 86400 < await store.redis.ttl(f"etf:hist:{cold}") <= etf.HIST_TTL
    async with store.pool.acquire() as conn:
        assert "placeholder" not in json.dumps([dict(r) for r in await conn.fetch("SELECT detail FROM etf_runs")], default=str)


async def test_cold_etf_without_a_price_source_still_shows_every_figure_and_says_why_the_chart_is_missing(store, monkeypatch):
    monkeypatch.setattr(etf, "HOT_N", 3)
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    app = create_app(make_settings(), store=store)                                                  # no UPSTOX_ACCESS_TOKEN in the API process
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            lst = (await c.get("/api/etf?limit=100")).json()["items"]
            cold = next(i for i in lst if not i["hot"] and i["avgTurnover"])
            b = (await c.get(f"/api/etf/{cold['symbol']}")).json()
            assert b["series"]["available"] is False and "not connected" in b["series"]["why"]
            h = {x["key"]: x for x in b["headline"]}
            assert h["1d"]["value"] == cold["changePct"] and h["1y"]["value"] == cold["ret1y"] and h["1y"]["from"] is None
            cmp_ = await c.get(f"/api/etf/compare?symbols={cold['symbol']},{lst[0]['symbol']}")
            assert cmp_.status_code == 200 and cmp_.json()["notes"]


async def test_search_finds_cold_etfs_with_typos(store, monkeypatch):
    monkeypatch.setattr(etf, "HOT_N", 2)
    await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)
    app = create_app(make_settings(), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            body = (await c.get("/api/etf?q=nifti bees")).json()
            assert body["items"][0]["symbol"] == "NIFTYBEES" and body["items"][0]["hot"] is False and body["universe"] == 17 and body["hotCount"] == 2


# ------------------------------------------------------------------------------------------------------------ holdings and facts
async def test_portfolio_and_facts_are_unavailable_with_a_reason_when_the_module_is_missing(api, monkeypatch):
    monkeypatch.setitem(sys.modules, "finlit.disclosure", None)                                    # makes the import fail like a missing module
    for path in ("portfolio", "facts"):
        r = await api.get(f"/api/etf/niftybees/{path}")
        b = r.json()
        assert r.status_code == 200 and b["unavailable"] and "not connected" in b["unavailable"] and b["isin"] == "INF204KB14I2"
    assert (await api.get("/api/etf/NOSUCHETF/portfolio")).status_code == 404


async def test_portfolio_and_facts_pass_the_disclosure_data_through(api, monkeypatch):
    seen = []
    stub = types.ModuleType("finlit.disclosure")

    async def get_portfolio(pool, isin):
        seen.append(isin)
        return {"asOf": "2026-09-30", "previousAsOf": "2026-08-31", "source": "Nippon India Mutual Fund", "sourceUrl": "https://example.invalid/p.xlsx",
                "holdings": [{"name": "HDFC Bank", "isin": "INE040A01034", "sector": "Financial", "assetClass": "equity", "pct": 12.5, "qty": 10, "valueLakh": 5.0,
                              "stockSymbol": "HDFCBANK", "prevPct": 12.0, "change": 0.5}], "exited": [],
                "summary": {"count": 1, "top10Pct": 12.5, "assetSplit": {"equity": 100.0}, "sectors": [{"sector": "Financial", "pct": 12.5}]}}

    async def get_facts(pool, isin):
        return {"ter": {"value": 0.04, "asOf": "2026-09-30", "source": "AMC"}, "aum": {"unavailable": "Not in the disclosure we read"}}
    stub.get_portfolio, stub.get_facts = get_portfolio, get_facts
    monkeypatch.setitem(sys.modules, "finlit.disclosure", stub)
    b = (await api.get("/api/etf/NIFTYBEES/portfolio")).json()
    assert seen == ["INF204KB14I2"] and "unavailable" not in b and b["holdings"][0]["stockSymbol"] == "HDFCBANK" and b["summary"]["top10Pct"] == 12.5
    f = (await api.get("/api/etf/NIFTYBEES/facts")).json()
    assert f["unavailable"] is None and f["facts"]["ter"]["value"] == 0.04 and f["facts"]["aum"]["unavailable"]


async def test_a_failing_disclosure_module_does_not_break_the_page(api, monkeypatch):
    stub = types.ModuleType("finlit.disclosure")

    async def boom(pool, isin):
        raise RuntimeError("secret internal detail")
    stub.get_portfolio = stub.get_facts = boom
    monkeypatch.setitem(sys.modules, "finlit.disclosure", stub)
    r = await api.get("/api/etf/NIFTYBEES/portfolio")
    assert r.status_code == 200 and "secret" not in r.text and r.json()["unavailable"]
    assert (await api.get("/api/etf/NIFTYBEES")).status_code == 200
