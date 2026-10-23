"""Dhan client (finlit/dhan.py). The response shapes follow Dhan's published v2 documentation; no live account was used."""
import json
from datetime import date

import httpx
import pytest

from finlit import dhan
from finlit.config import Settings
from test_integration import ingested, store  # noqa: F401  (fixtures)

HEADER = "EXCH_ID,SEGMENT,SECURITY_ID,ISIN,INSTRUMENT,UNDERLYING_SECURITY_ID,UNDERLYING_SYMBOL,SYMBOL_NAME,DISPLAY_NAME,INSTRUMENT_TYPE,SERIES,LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,TICK_SIZE,EXPIRY_FLAG,BRACKET_FLAG,COVER_FLAG,ASM_GSM_FLAG,ASM_GSM_CATEGORY,BUY_SELL_INDICATOR,BUY_CO_MIN_MARGIN_PER,BUY_CO_SL_RANGE_MAX_PERC,BUY_CO_SL_RANGE_MIN_PERC,BUY_BO_MIN_MARGIN_PER,BUY_BO_PROFIT_RANGE_MAX_PERC,BUY_BO_PROFIT_RANGE_MIN_PERC,MTF_LEVERAGE,SM_UPPER_LIMIT,SM_LOWER_LIMIT,SM_FREEZE_QTY"


def row(exch, seg, sid, isin, inst, under, name, series, lot, asm="N", cat="NA", mtf="0"):
    return f"{exch},{seg},{sid},{isin},{inst},,{under},{name},{name.title()},ES,{series},{lot},,,,0.05,NA,N,N,{asm},{cat},A,0,0,0,0,0,0,{mtf},0,0,0"


FILE = "\n".join([
    HEADER,
    row("NSE", "E", "2885", "INE002A01018", "EQUITY", "RELIANCE", "RELIANCE INDUSTRIES LTD", "EQ", "1.0", mtf="4.5"),
    row("NSE", "E", "777", "INE000X01010", "EQUITY", "SMALLCO", "SMALL CO LTD", "SM", "1.0", asm="Y", cat="ASM LT Stage 2"),
    row("BSE", "E", "500325", "INE002A01018", "EQUITY", "RELIANCE", "RELIANCE INDUSTRIES LTD", "A", "1.0"),
    row("BSE", "E", "540084", "NA", "EQUITY", "SPICY", "SPICY ENTERTAINMENT", "X", "1.0"),
    row("NSE", "D", "49081", "NA", "FUTSTK", "RELIANCE", "RELIANCE FUT", "NA", "250.0"),
    row("NSE", "D", "49082", "NA", "OPTSTK", "RELIANCE", "RELIANCE OPT", "NA", "250.0"),
    row("NSE", "E", "", "INE0", "EQUITY", "NOID", "NO ID", "EQ", "1.0"),
])


def test_totp_matches_the_rfc_6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"             # ASCII "12345678901234567890"
    assert dhan.totp(secret, at=59, digits=8) == "94287082"
    assert dhan.totp(secret, at=59) == "287082"
    assert dhan.totp(secret.lower().replace("GEZD", "GEZD "), at=1111111109, digits=8) == "07081804"   # spaces and case do not matter


def test_instrument_file_keeps_equities_marks_futures_and_surveillance():
    rows = {(r["exch"], r["security_id"]): r for r in dhan.parse_instruments(FILE.splitlines())}
    assert set(rows) == {("NSE", "2885"), ("NSE", "777"), ("BSE", "500325"), ("BSE", "540084")}   # derivatives and id-less rows are not equities
    ril = rows[("NSE", "2885")]
    assert ril["isin"] == "INE002A01018" and ril["fno"] and ril["lot_size"] == 250 and ril["mtf_leverage"] == 4.5 and ril["asm_gsm"] == "N" and ril["asm_gsm_cat"] is None
    assert rows[("NSE", "777")]["asm_gsm"] == "Y" and rows[("NSE", "777")]["asm_gsm_cat"] == "ASM LT Stage 2" and not rows[("NSE", "777")]["fno"]
    assert rows[("BSE", "500325")]["fno"] is False                 # futures are NSE's: the BSE listing of the same company is not marked
    assert rows[("BSE", "540084")]["isin"] is None and rows[("BSE", "540084")]["mtf_leverage"] is None


def client(handler, **kw):
    s = Settings(dhan_client_id="1000000001", dhan_pin="123456", dhan_totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", **kw)
    return dhan.DhanClient(s, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_token_is_made_once_with_pin_and_code_and_reused():
    calls = []

    def h(req):
        calls.append(req)
        assert req.url.host == "auth.dhan.co" and req.url.path == "/app/generateAccessToken"
        q = dict(req.url.params)
        assert q["dhanClientId"] == "1000000001" and q["pin"] == "123456" and len(q["totp"]) == 6
        return httpx.Response(200, json={"accessToken": "TOK", "expiryTime": "2099-01-01T00:00:00.000"})
    async with client(h) as c:
        assert await c.token() == "TOK" and await c.token() == "TOK"
    assert len(calls) == 1


async def test_a_refused_token_is_renewed_once_then_reported_without_secrets():
    n = {"auth": 0, "api": 0}

    def h(req):
        if req.url.host == "auth.dhan.co":
            n["auth"] += 1
            return httpx.Response(200, json={"accessToken": f"T{n['auth']}", "expiryTime": "2099-01-01T00:00:00.000"})
        n["api"] += 1
        return httpx.Response(401, json={"errorCode": "DH-901"}) if req.headers["access-token"] == "T1" else httpx.Response(200, json={"data": {"NSE_EQ": {"2885": {"last_price": 1420.5}}}})
    async with client(h) as c:
        assert await c.ltp({"NSE_EQ": [2885]}) == {"NSE_EQ": {"2885": 1420.5}}
    assert n == {"auth": 2, "api": 2}

    def bad(req):
        return httpx.Response(200, json={}) if req.url.host == "auth.dhan.co" else httpx.Response(500)
    async with client(bad) as c:
        with pytest.raises(dhan.DhanError) as e:
            await c.token()
    assert "123456" not in str(e.value) and "auth.dhan.co" not in str(e.value)


async def test_pasted_token_mode_and_the_unconfigured_state():
    seen = []

    def h(req):
        seen.append((req.headers["access-token"], req.headers["client-id"]))
        return httpx.Response(200, json={"data": {"NSE_EQ": {"1": {"last_price": 10}, "2": {"last_price": None}}}})
    c = dhan.DhanClient(Settings(dhan_client_id="1000000001", dhan_access_token="PASTED"), http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    assert c.configured and await c.ltp({"NSE_EQ": [1, 2]}) == {"NSE_EQ": {"1": 10.0}}     # a missing price is left out, not zero
    assert seen == [("PASTED", "1000000001")]
    assert not dhan.DhanClient(Settings(dhan_client_id="x")).configured and not dhan.DhanClient(Settings()).configured
    with pytest.raises(dhan.DhanError):
        await c.ltp({"NSE_EQ": list(range(1001))})


async def test_daily_candles_are_read_in_order_and_unequal_arrays_are_refused():
    ts = [1768156800, 1768243200]                                   # 2026-01-12 00:00 IST and the next day
    body = {"open": [1, 2], "high": [2, 3], "low": [0.5, 1.5], "close": [1.5, 2.5], "volume": [100, 200], "timestamp": ts}

    def h(req):
        sent = json.loads(req.content)
        assert sent["securityId"] == "2885" and sent["exchangeSegment"] == "NSE_EQ" and sent["fromDate"] == "2026-01-01" and sent["toDate"] == "2026-01-20"
        return httpx.Response(200, json=body)
    async with client(h, dhan_access_token="") as c:
        c._token = {"token": "T", "exp": 9e12}
        got = await c.daily("2885", "NSE_EQ", date(2026, 1, 1), date(2026, 1, 20))
    assert [g["close"] for g in got] == [1.5, 2.5] and got[0]["day"] < got[1]["day"] and got[1]["volume"] == 200
    body["close"] = [1.5]
    async with client(h) as c:
        c._token = {"token": "T", "exp": 9e12}
        assert await c.daily("2885", "NSE_EQ", date(2026, 1, 1), date(2026, 1, 20)) == []


async def test_instruments_replace_the_table_and_a_short_file_changes_nothing(store):  # noqa: F811
    rows = [{"exch": "NSE", "security_id": str(i), "symbol": f"S{i}", "isin": None, "name": None, "series": "EQ", "asm_gsm": "N", "asm_gsm_cat": None,
             "mtf_leverage": None, "fno": False, "lot_size": None} for i in range(5200)]
    assert await dhan.save_instruments(store, rows) == 5200
    with pytest.raises(dhan.DhanError):
        await dhan.save_instruments(store, rows[:10])
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM dhan_instruments") == 5200


async def test_profile_returns_only_status_fields():
    def h(req):
        assert req.method == "GET" and req.url.path == "/v2/profile"
        return httpx.Response(200, json={"dhanClientId": "1000000001", "tokenValidity": "30/03/2026 15:37", "activeSegment": "Equity", "dataPlan": "Active",
                                          "dataValidity": "2026-12-05 09:37:52.0", "ddpi": "Active"})
    c = dhan.DhanClient(Settings(dhan_client_id="1000000001", dhan_access_token="P"), http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    p = await c.profile()
    assert p["dataPlan"] == "Active" and "dhanClientId" not in p and "ddpi" not in p


# ------------------------------------------------------------------ live quotes

RAW = {"last_price": 1420.5, "net_change": 20.5, "volume": 523000, "ohlc": {"open": 1401, "high": 1425, "low": 1398.2, "close": 1400},
       "upper_circuit_limit": 1540, "lower_circuit_limit": 1260, "last_trade_time": "23/10/2026 15:29:58"}


def test_quote_conversion_reads_change_from_previous_close_and_drops_placeholders():
    q = dhan.to_quote(RAW)
    assert q["price"] == 1420.5 and q["previousClose"] == 1400.0 and q["change"] == 20.5 and q["changePct"] == round(20.5 / 1400 * 100, 2)
    assert (q["open"], q["high"], q["low"], q["volume"]) == (1401, 1425, 1398.2, 523000)
    assert q["upperCircuit"] == 1540 and q["lowerCircuit"] == 1260 and q["asOf"] == "2026-10-23T15:29:58+05:30"
    blank = dhan.to_quote({"last_price": 368.15, "net_change": 0, "volume": 0, "ohlc": {"open": 0, "high": 0, "low": 0, "close": 368.15},
                           "last_trade_time": "01/01/1980 00:00:00"})
    assert blank["price"] == 368.15 and blank["open"] is None and blank["volume"] is None and blank["asOf"] is None   # no trade yet: no zeros
    assert dhan.to_quote({"last_price": 0}) == {} and dhan.to_quote({}) == {}


def test_plausibility_guard():
    assert dhan.plausible({"price": 1420.5, "previousClose": 1400}, {"price": 1395})
    assert not dhan.plausible({"price": 50, "previousClose": 49}, {"price": 1395})        # another company's price: refused
    assert dhan.plausible({"price": 10}, {})                                                 # nothing held yet: nothing to compare


class FakeDhan:
    configured = True

    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.asked = data or {}, fail, []

    async def quotes(self, ids):
        self.asked.append(list(ids))
        if self.fail:
            raise dhan.DhanError("/marketfeed/quote: HTTP 503")
        return self.data


async def test_refresh_quotes_uses_dhan_first_and_finedge_when_dhan_is_wrong_or_down(ingested):  # noqa: F811
    import orjson
    from finlit import worker
    from finlit.finedge import FinEdgeClient
    from test_integration import make_settings
    async with ingested.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.executemany("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ($1, $2, $3, $4)",
                               [("NSE", "25510", "RELIANCE", "D1"), ("NSE", "2885", "RELIANCE", "EQ"), ("BSE", "500325", "RELIANCE", "A")])
    assert await dhan.security_map(ingested, ["RELIANCE", "NOPE"]) == {"RELIANCE": ("NSE_EQ", "2885")}   # the share, not the debenture

    async def hold(price, mcap):
        body = orjson.loads((await ingested.get_section("RELIANCE", "consolidated", "summary"))[0])
        body["quote"].update(price=price, previousClose=price, marketCapCr=mcap, high52=1410.0)
        await ingested.save_snapshot("RELIANCE", "consolidated", {"summary": body})

    async def quote():
        return orjson.loads((await ingested.get_section("RELIANCE", "consolidated", "summary"))[0])["quote"]

    async with FinEdgeClient(make_settings()) as fe:
        await hold(1400.0, 1_900_000.0)
        fake = FakeDhan({("NSE_EQ", "2885"): RAW})
        assert await worker.refresh_quotes(fe, ingested, dhan_client=fake) == 1
        q = await quote()
        assert fake.asked == [[("NSE_EQ", "2885")]] and q["price"] == 1420.5 and q["upperCircuit"] == 1540
        assert q["marketCapCr"] == round(1_900_000.0 * 1420.5 / 1400.0, 2) and q["high52"] == 1425       # cap follows the price; new 52-week high

        await hold(1.0, 1.0)                                                       # held price far from Dhan's: Dhan refused, FinEdge used
        assert await worker.refresh_quotes(fe, ingested, dhan_client=FakeDhan({("NSE_EQ", "2885"): RAW})) == 1
        assert (await quote())["price"] == 1184.0

        await hold(1.0, 1.0)                                                       # Dhan down: FinEdge for everyone
        assert await worker.refresh_quotes(fe, ingested, dhan_client=FakeDhan(fail=True)) == 1
        assert (await quote())["price"] == 1184.0


async def test_processes_share_one_token_through_redis_and_never_renew_together(store):  # noqa: F811
    made = []

    def h(req):
        made.append(1)
        return httpx.Response(200, json={"accessToken": f"T{len(made)}", "expiryTime": "2099-01-01T00:00:00.000"})
    await store.redis.delete(dhan.TOKEN_KEY, dhan.TOKEN_KEY + ":lock")
    s = Settings(dhan_client_id="1000000001", dhan_pin="123456", dhan_totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    a = dhan.DhanClient(s, store.redis, http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    b = dhan.DhanClient(s, store.redis, http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    import asyncio
    ta, tb = await asyncio.gather(a.token(), b.token())
    assert ta == tb == "T1" and len(made) == 1                     # one token for both processes
    assert await a.token(force=True) == "T2" and len(made) == 2     # a refusal renews ...
    assert await b.token(force=True) == "T2" and len(made) == 2     # ... and the other process takes that new one instead of renewing again
    await a.aclose(); await b.aclose()
    await store.redis.delete(dhan.TOKEN_KEY)


async def test_refresh_instruments_reloads_when_the_index_or_option_tables_are_empty(store, monkeypatch):  # noqa: F811
    """A recent run is skipped only when it also left the index and option-lot tables filled (a run from before they existed must reload)."""
    from finlit import worker
    from finlit.mf import record_run
    from test_integration import make_settings
    calls = []

    async def fetch(client=None, indices=None, on_row=None):
        calls.append(1)
        raise dhan.DhanError("stop here")
    monkeypatch.setattr(dhan, "fetch_instruments", fetch)
    await record_run(store, "refresh-instruments", {"status": "ok", "equities": 1})
    assert await worker.main(["refresh-instruments", "--max-age-hours", "20"], settings=make_settings()) == 1 and calls == [1]   # tables empty: it ran
    await record_run(store, "refresh-instruments", {"status": "ok", "equities": 1})      # the failed attempt above recorded itself
    async with store.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_indices (exch, security_id, symbol) VALUES ('NSE', '13', 'NIFTY') ON CONFLICT DO NOTHING")
        await conn.execute("INSERT INTO dhan_option_lots (exch, instrument, underlying, underlying_id, expiry, lot_size) VALUES ('NSE', 'OPTIDX', 'NIFTY', '13', '2026-11-09', 65) ON CONFLICT DO NOTHING")
    assert await worker.main(["refresh-instruments", "--max-age-hours", "20"], settings=make_settings()) == 0 and calls == [1]   # filled: skipped
