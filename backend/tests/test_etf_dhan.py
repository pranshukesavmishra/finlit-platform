"""ETF refresh through Dhan (finlit/etf.py _DhanSource): the same recorded prices as test_etf.py, served in Dhan's shapes, must give exactly
the figures the Upstox run gives. Dhan's shapes follow its published v2 documentation."""
import json
from datetime import date, datetime, timedelta

import httpx

from finlit import etf
from finlit.config import Settings
from test_etf import BY_SYMBOL, CANDLES, ETFS, FX, MIGRATIONS, NOW, QUOTES, S, Provider, store  # noqa: F401  (fixture)
from test_integration import TEST_DB, TEST_REDIS

SID = {r["trading_symbol"]: str(1000 + i) for i, r in enumerate(ETFS)}      # made-up Dhan security ids
BY_SID = {v: k for k, v in SID.items()}
SAME = ("symbol", "isin", "price", "price_date", "prev_close", "change_pct", "volume", "avg_turnover", "ret_1m", "ret_6m", "ret_1y", "ret_3y", "ret_5y",
        "cagr_3y", "cagr_5y", "vol_1y", "mdd_1y", "high_52", "low_52", "first_date", "points", "break_date", "nav", "nav_date", "premium", "hot", "turnover_rank")


def dhan_settings():
    return Settings(dhan_client_id="1000000001", dhan_pin="123456", dhan_totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", database_url=TEST_DB, redis_url=TEST_REDIS)


def ist_text(ms):
    return datetime.fromtimestamp(int(ms) / 1000, etf.IST).strftime("%d/%m/%Y %H:%M:%S")


class DhanProvider:
    def __init__(self):
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req.url.path)
        if req.url.host == "portal.amfiindia.com":
            return httpx.Response(200, content=(FX / "amfi.txt").read_bytes())
        if req.url.host == "auth.dhan.co":
            return httpx.Response(200, json={"accessToken": "T", "expiryTime": "2099-01-01T00:00:00.000"})
        assert req.url.host == "api.dhan.co" and req.headers["access-token"] == "T"
        body = json.loads(req.content)
        if req.url.path == "/v2/marketfeed/quote":
            out = {}
            for sid in body.get("NSE_EQ", []):
                q = next((v for v in QUOTES.values() if v["symbol"] == BY_SID[str(sid)]), None)
                if q:
                    out[str(sid)] = {"last_price": q["last_price"], "volume": q["volume"], "net_change": q["net_change"], "ohlc": q["ohlc"],
                                     "last_trade_time": ist_text(q["last_trade_time"])}
            return httpx.Response(200, json={"data": {"NSE_EQ": out}, "status": "success"})
        if req.url.path == "/v2/charts/historical":
            sym = BY_SID[body["securityId"]]
            rows = sorted((c for c in CANDLES.get(sym, []) if body["fromDate"] <= c[0][:10] < body["toDate"]), key=lambda c: c[0][:10])   # same-day rows keep the recorded order
            ts = [int(datetime.fromisoformat(c[0][:10]).replace(tzinfo=etf.IST).timestamp()) for c in rows]
            return httpx.Response(200, json={"open": [c[1] for c in rows], "high": [c[2] for c in rows], "low": [c[3] for c in rows],
                                             "close": [c[4] for c in rows], "volume": [c[5] or 0 for c in rows], "timestamp": ts})
        return httpx.Response(404)


async def load_instruments(st):
    await st.redis.delete("dhan:token")                                    # a token another test left in Redis
    async with st.pool.acquire() as conn:
        for f in ("044_dhan_instruments.sql", "045_dhan_instrument_type.sql"):
            await conn.execute((MIGRATIONS / f).read_text())
        await conn.execute("DELETE FROM dhan_instruments")
        rows = [("NSE", SID[r["trading_symbol"]], r["trading_symbol"], r["isin"], r.get("name"), "EQ", "ETF", r.get("name")) for r in ETFS]
        rows.append(("NSE", "999999", "SFMP6DD", "INF200K01ZZ9", "SBIAMC - SFMP6DD", "MF", "MF", "SBIAMC - SFMP6DD"))   # a listed fund unit: not an ETF
        await conn.executemany("INSERT INTO dhan_instruments (exch, security_id, symbol, isin, name, series, inst_type, exch_name) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)", rows)


async def figures(st):
    async with st.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM etf_funds WHERE active ORDER BY symbol")
        hist = {r["symbol"]: (list(r["dates"]), list(r["closes"])) for r in await conn.fetch("SELECT symbol, dates, closes FROM etf_history")}
    return {r["symbol"]: {k: r[k] for k in SAME if k in r} for r in rows}, hist, {r["symbol"]: r["instrument_key"] for r in rows}


async def test_dhan_gives_the_same_figures_as_upstox(store, monkeypatch):  # noqa: F811
    await load_instruments(store)
    up = await etf.refresh(store, S(), transport=httpx.MockTransport(Provider()), now=NOW)          # no Dhan settings: Upstox, as before
    assert up["source"] == "upstox" and up["status"] in ("ok", "partial")
    want, want_hist, _ = await figures(store)

    async with store.pool.acquire() as conn:                                                     # start again from nothing, through Dhan
        await conn.execute("TRUNCATE etf_funds, etf_history, etf_hot, etf_runs")
    prov = DhanProvider()
    got_run = await etf.refresh(store, dhan_settings(), transport=httpx.MockTransport(prov), now=NOW)
    assert got_run["source"] == "dhan" and got_run["status"] == up["status"], got_run
    got, got_hist, keys = await figures(store)
    assert set(got) == set(want) and "SFMP6DD" not in got                                       # fund units are left out
    for sym in want:
        assert got[sym] == want[sym], sym
    assert got_hist == want_hist
    assert all(k == "DHAN|" + SID[s] for s, k in keys.items())
    assert prov.calls.count("/v2/marketfeed/quote") == 1                                         # every ETF's quote in one call


async def test_upstox_is_kept_when_dhan_has_no_instrument_file_or_is_forced_off(store, monkeypatch):  # noqa: F811
    async with store.pool.acquire() as conn:
        for f in ("044_dhan_instruments.sql", "045_dhan_instrument_type.sql"):
            await conn.execute((MIGRATIONS / f).read_text())
        await conn.execute("DELETE FROM dhan_instruments")
    src = await etf.pick_source(store, dhan_settings())
    assert src.name == "upstox"
    await src.aclose()
    await load_instruments(store)
    src = await etf.pick_source(store, dhan_settings())
    assert src.name == "dhan"
    await src.aclose()
    monkeypatch.setenv("ETF_SOURCE", "upstox")
    src = await etf.pick_source(store, dhan_settings())
    assert src.name == "upstox"
    await src.aclose()


async def test_a_cold_etf_priced_through_dhan_is_fetched_from_dhan(store, monkeypatch):  # noqa: F811
    from finlit.api import create_app
    monkeypatch.setattr(etf, "HOT_N", 3)
    await load_instruments(store)
    prov = DhanProvider()
    await etf.refresh(store, dhan_settings(), transport=httpx.MockTransport(prov), now=NOW)
    async with store.pool.acquire() as conn:
        cold = (await conn.fetchrow("SELECT symbol FROM etf_funds WHERE NOT hot AND avg_turnover IS NOT NULL ORDER BY turnover_rank LIMIT 1"))["symbol"]
    real = etf.DhanClient
    later = DhanProvider()
    monkeypatch.setattr(etf, "DhanClient", lambda s, r=None, http=None: real(s, r, http=http or httpx.AsyncClient(transport=httpx.MockTransport(later))))
    app = create_app(Settings(**{**dhan_settings().__dict__, "finedge_mode": "fixtures", "finedge_api_key": "x"}), store=store)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            b = (await c.get(f"/api/etf/{cold}")).json()
    assert b["series"]["available"], b["series"]
    assert later.calls.count("/v2/charts/historical") == 1
