"""How a share trades, from Dhan's instrument file and live quote: surveillance warning, F&O and lot size, margin-trading leverage,
the day's price band, the F&O screener filter and the circuit alert. Mocked rows only; no Dhan account was used."""

import math
from datetime import datetime, timezone

import orjson
import pytest

from finlit import alertengine as eng
from finlit import dhan
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures and helpers)
from test_dhan import HEADER, RAW, FakeDhan, row
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)

COLS = "exch, security_id, symbol, series, asm_gsm, asm_gsm_cat, mtf_leverage, fno, lot_size"


async def put(store, *rows):
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.executemany(f"INSERT INTO dhan_instruments ({COLS}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)", rows)  # nosec B608


def fut(sid, under, lot, expiry):
    return f"NSE,D,{sid},NA,FUTSTK,,{under},{under}-FUT,{under} FUT,FUTSTK,NA,{lot},{expiry},,,0.05,M,N,N,N,NA,A,0,0,0,0,0,0,0,0,0,0"


# ------------------------------------------------------------------ the instrument file and what is said about it

def test_lot_size_is_the_nearest_contracts_even_when_a_revision_lists_later_months_first():
    lines = [HEADER, fut("1", "ACME", "500.0", "2026-12-29"), fut("2", "ACME", "625.0", "2026-10-27"), fut("3", "ACME", "500.0", "2026-11-24"),
             row("NSE", "E", "9", "INE9", "EQUITY", "ACME", "ACME LTD", "EQ", "1.0")]
    (acme,) = dhan.parse_instruments(lines)
    assert acme["fno"] and acme["lot_size"] == 625


def test_facts_say_only_what_is_positively_there():
    at = datetime(2026, 10, 23, 2, 20, tzinfo=timezone.utc)                       # 07:50 in India
    base = {"exch": "NSE", "asm_gsm": "N", "asm_gsm_cat": None, "mtf_leverage": None, "fno": False, "lot_size": None, "loaded_at": at}
    f = dhan.trading_facts(base)
    assert f == {"matched": True, "exchange": "NSE", "asOf": "2026-10-23", "surveillance": None, "fno": None, "mtf": None}   # N is never "not under surveillance"
    assert dhan.trading_facts({**base, "asm_gsm": "Y"})["surveillance"] == {"stage": None}                    # NSE's Y rows carry no category
    assert dhan.trading_facts({**base, "exch": "BSE", "asm_gsm": "Y", "asm_gsm_cat": "II"})["surveillance"] == {"stage": "II"}
    assert dhan.trading_facts({**base, "asm_gsm": "R"})["surveillance"] is None                               # "removed from block": nothing said
    assert dhan.trading_facts({**base, "asm_gsm": "P"})["surveillance"] is None                               # undocumented BSE flag
    assert dhan.trading_facts({**base, "fno": True, "lot_size": 250})["fno"] == {"lotSize": 250}
    assert dhan.trading_facts({**base, "exch": "BSE", "fno": True, "lot_size": 250})["fno"] is None
    # real values from the file: never rounded up ("up to" must not overstate), and 1x (nothing lent) is not shown as leverage
    lev = {x: (dhan.trading_facts({**base, "mtf_leverage": x})["mtf"] or {}).get("leverage") for x in (4.545455, 3.773585, 3.333333, 1.666667, 2.0, 5.0, 2.998501, 1.0)}
    assert lev == {4.545455: 4.5, 3.773585: 3.7, 3.333333: 3.3, 1.666667: 1.6, 2.0: 2.0, 5.0: 5.0, 2.998501: 2.9, 1.0: None}
    assert dhan.trading_facts(None) == {"matched": False}


def test_circuit_state_needs_the_price_and_a_whole_sensible_band():
    q = {"price": 1540.0, "upperCircuit": 1540.0, "lowerCircuit": 1260.0}
    assert eng.circuit_state(q)[0] == 1.0                                          # at the band is "hit"
    assert eng.circuit_state({**q, "price": 1539.95})[0] == 0.0
    assert eng.circuit_state({**q, "price": 1260.0})[0] == -1.0
    assert eng.circuit_state({**q, "price": 1250.0})[0] == -1.0
    for bad in ({**q, "upperCircuit": None}, {"price": 10.0, "lowerCircuit": 9.0}, {**q, "lowerCircuit": 1540.0}, {**q, "price": None}, {}, None, "x"):
        assert eng.circuit_state(bad) == (None, None), bad


# ------------------------------------------------------------------ the stock page's endpoint

async def test_trading_endpoint_matches_like_the_quotes_and_is_cached(app):  # noqa: F811
    st = app.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name, nse_code, bse_code) VALUES ('BSEONLY', 'Bse Only Ltd', '', '539979') ON CONFLICT (symbol) DO NOTHING")
    await put(st, ("NSE", "25510", "RELIANCE", "D1", "Y", "Stage 9", None, False, None),          # a debenture on the same symbol: never the one read
              ("NSE", "2885", "RELIANCE", "EQ", "N", None, 4.545455, True, 500),
              ("BSE", "500325", "RELIANCE", "A", "Y", "II", None, False, None),
              ("BSE", "539979", "DIGJAMLMTD", "T", "Y", "II", 1.0, False, None))
    rows = await dhan.instrument_rows(st, ["RELIANCE", "BSEONLY", "NOPE"])
    assert {s: (("NSE_EQ" if r["exch"] == "NSE" else "BSE_EQ"), r["security_id"]) for s, r in rows.items()} == await dhan.security_map(st, ["RELIANCE", "BSEONLY", "NOPE"])
    async with new_client(app) as c:
        r = await c.get("/api/stocks/reliance/trading")
        assert r.status_code == 200 and r.headers["cache-control"].startswith("public")
        body = r.json()
        assert body["symbol"] == "RELIANCE" and body["exchange"] == "NSE" and body["surveillance"] is None
        assert body["fno"] == {"lotSize": 500} and body["mtf"] == {"leverage": 4.5} and len(body["asOf"]) == 10
        assert (await c.get("/api/stocks/RELIANCE/trading", headers={"If-None-Match": r.headers["etag"]})).status_code == 304
        b = (await c.get("/api/stocks/BSEONLY/trading")).json()
        assert b["exchange"] == "BSE" and b["surveillance"] == {"stage": "II"} and b["fno"] is None and b["mtf"] is None
        assert (await c.get("/api/stocks/NOPE/trading")).json() == {"symbol": "NOPE", "matched": False}
        assert (await c.get("/api/stocks/bad%20sym/trading")).status_code == 400
        async with st.pool.acquire() as conn:          # kept 30 minutes: a page view does not read the table again
            await conn.execute("UPDATE dhan_instruments SET asm_gsm = 'Y' WHERE security_id = '2885'")
        assert (await c.get("/api/stocks/RELIANCE/trading")).json()["surveillance"] is None
        await st.redis.delete("trading:RELIANCE")
        assert (await c.get("/api/stocks/RELIANCE/trading")).json()["surveillance"] == {"stage": None}
        assert (await c.get("/api/stocks/RELIANCE/ratios")).status_code == 200      # the section route still answers the rest


# ------------------------------------------------------------------ the screener filter

async def test_fno_screener_filter_reads_the_file_at_load_and_leaves_unmatched_unknown(app):  # noqa: F811
    from finlit.screener import data
    st = app.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("INSERT INTO companies (symbol, name, nse_code, bse_code) VALUES ('BSEONLY', 'Bse Only Ltd', '', '539979') ON CONFLICT (symbol) DO NOTHING")
        tcs = await conn.fetchval("SELECT nse_code FROM companies WHERE symbol = 'TCS'")
    assert tcs == "TCS"
    await put(st, ("NSE", "2885", "RELIANCE", "EQ", "N", None, None, True, 500), ("NSE", "11536", "TCS", "EQ", "N", None, None, False, None),
              ("BSE", "539979", "DIGJAMLMTD", "T", "N", None, None, False, None))
    data.reset()
    t = await data.get_table(st, force=True)
    col = t.cols["fno"]
    assert col[t.pos["RELIANCE"]] == 1.0 and col[t.pos["TCS"]] == 0.0
    assert math.isnan(col[t.pos["BSEONLY"]])                                      # matched by BSE code alone: unknown, not "no"
    assert sum(1 for x in col if x == x) == 2                                     # every company the file does not match stays unknown
    async with new_client(app) as c:
        r = await c.post("/api/screener/query", json={"filters": {"fno": {"min": 1}}, "columns": ["fno"]})
        assert r.status_code == 200, r.text
        assert [x["symbol"] for x in r.json()["rows"]] == ["RELIANCE"] and r.json()["rows"][0]["v"]["fno"] == 1
        no = [x["symbol"] for x in (await c.post("/api/screener/query", json={"filters": {"fno": {"max": 0}}})).json()["rows"]]
        assert "TCS" in no and "RELIANCE" not in no
        cat = (await c.get("/api/screener/catalog")).json()
        assert "Has futures & options (F&O)" in str(cat)
    data.reset()


# ------------------------------------------------------------------ the day's price band in the quote, and the circuit alert

async def summary(st):
    return orjson.loads((await st.get_section("RELIANCE", "consolidated", "summary"))[0])


async def set_quote(st, **q):
    body = await summary(st)
    body["quote"] = {k: v for k, v in {**body["quote"], **q}.items() if v is not None}
    for k, v in q.items():
        if v is None:
            body["quote"].pop(k, None)
    await st.save_snapshot("RELIANCE", "consolidated", {"summary": body})


async def test_a_band_never_outlives_the_quote_it_came_with(ingested):  # noqa: F811
    from finlit import worker
    from finlit.finedge import FinEdgeClient
    await put(ingested, ("NSE", "2885", "RELIANCE", "EQ", "N", None, None, False, None))
    await set_quote(ingested, price=1400.0, previousClose=1400.0)
    async with FinEdgeClient(make_settings()) as fe:
        assert await worker.refresh_quotes(fe, ingested, dhan_client=FakeDhan({("NSE_EQ", "2885"): RAW})) == 1
        q = (await summary(ingested))["quote"]
        assert (q["price"], q["upperCircuit"], q["lowerCircuit"]) == (1420.5, 1540, 1260)
        assert await worker.refresh_quotes(fe, ingested, dhan_client=FakeDhan(fail=True)) == 1     # FinEdge's quote has no band
        q = (await summary(ingested))["quote"]
        assert q["price"] == 1184.0 and "upperCircuit" not in q and "lowerCircuit" not in q


async def run_live(app):
    return await eng.evaluate(app.state.store.pool, app.state.mailer, "http://test", "live")


async def test_circuit_alert_fires_at_the_band_and_never_without_one(app):  # noqa: F811
    st = app.state.store
    c = await signed_in(app, "circuit@example.com")
    await set_quote(st, price=1500.0, upperCircuit=1540.0, lowerCircuit=1260.0)
    assert (await c.get("/api/alerts/value?symbol=RELIANCE&metric=circuit")).json()["value"] == 0
    r = await c.post("/api/alerts", json={"symbol": "RELIANCE", "metric": "circuit", "op": "above", "value": 999, "channels": ["app"], "repeat": "every"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["value"] == 1 and a["alreadyMet"] is False and a["current"] == 0        # the target is the server's, whatever was sent
    low = (await c.post("/api/alerts", json={"symbol": "RELIANCE", "metric": "circuit", "op": "below", "channels": ["app"]})).json()
    assert low["value"] == -1
    assert (await c.patch(f"/api/alerts/{a['id']}", json={"value": 5})).json()["detail"]["status"] == "bad_value"
    assert await run_live(app) == 0                                                 # inside the band
    await set_quote(st, price=1540.0)
    assert await run_live(app) == 1                                                 # at the upper band: the upper alert only
    n = (await c.get("/api/notifications")).json()["notifications"][0]
    assert n["title"] == "RELIANCE – at its upper circuit (₹1,540)"
    assert n["body"] == "The price, ₹1,540, has reached the highest price the exchange allows for RELIANCE today, ₹1,540."
    for word in ("buy", "sell", "signal", "opportunity"):
        assert word not in (n["title"] + n["body"]).lower()
    assert await run_live(app) == 0                                                 # stays there: no repeat without a new crossing
    async with st.pool.acquire() as conn:
        await conn.execute("UPDATE alerts SET last_fired_at = now() - interval '2 hours'")
    await set_quote(st, price=1500.0, upperCircuit=None, lowerCircuit=None)         # the band goes missing
    assert await run_live(app) == 0
    await set_quote(st, price=1600.0)                                               # far above where the band was, but no band: nothing fires
    assert await run_live(app) == 0
    await set_quote(st, price=1260.0, upperCircuit=1540.0, lowerCircuit=1260.0)
    assert await run_live(app) == 1                                                 # the lower one
    assert "lower circuit (₹1,260)" in (await c.get("/api/notifications")).json()["notifications"][0]["title"]
    await c.aclose()


def test_circuit_is_live_and_open_to_every_member():
    m = eng.METRICS["circuit"]
    assert m["live"] and m["tier"] == "basic" and m["ops"] == ("above", "below") and eng.FIXED_TARGET["circuit"] == {"above": 1.0, "below": -1.0}
