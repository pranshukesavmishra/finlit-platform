"""Option chain (finlit/options.py): the figures worked out from Dhan's chain, checked against examples worked by hand; market-hours caching;
the shared pacer; Gold-only access; and the API end to end against mocked Dhan answers in the shapes of Dhan's published v2 docs
(POST /optionchain and /optionchain/expirylist). No live Dhan account was used."""

import asyncio
import json
import time
from datetime import date, datetime

import httpx
import pytest

from finlit import options as oc
from finlit.config import Settings
from finlit.dhan import IST, DhanClient, parse_instruments

# The 25650 strike exactly as Dhan's documentation prints it.
DOC_CE = {"average_price": 146.99, "greeks": {"delta": 0.53871, "theta": -15.1539, "gamma": 0.00132, "vega": 12.18593}, "implied_volatility": 9.789193798280868,
          "last_price": 134, "oi": 3786445, "previous_close_price": 244.85, "previous_oi": 402220, "previous_volume": 31931705, "security_id": 42528,
          "top_ask_price": 134, "top_ask_quantity": 1365, "top_bid_price": 133.55, "top_bid_quantity": 1625, "volume": 117567970}
DOC_PE = {"average_price": 134.62, "greeks": {"delta": -0.46732, "theta": -10.61131, "gamma": 0.00109, "vega": 12.2025}, "implied_volatility": 11.939337251984934,
          "last_price": 132.8, "oi": 3096145, "previous_close_price": 101.45, "previous_oi": 2327260, "previous_volume": 81224780, "security_id": 42529,
          "top_ask_price": 132.75, "top_ask_quantity": 390, "top_bid_price": 132.45, "top_bid_quantity": 65, "volume": 157009970}


def leg(oi, prev_oi=None, ltp=None, prev=None, vol=0, iv=None):
    d = {"oi": oi, "volume": vol}
    if prev_oi is not None:
        d["previous_oi"] = prev_oi
    if ltp is not None:
        d["last_price"] = ltp
    if prev is not None:
        d["previous_close_price"] = prev
    if iv is not None:
        d["implied_volatility"] = iv
    return d


# ------------------------------------------------------------------------------------------------------------------ pure figures

def test_one_side_from_the_documented_example():
    ce, pe = oc.side(DOC_CE), oc.side(DOC_PE)
    # OI change = oi − previous_oi; % of previous_oi
    assert ce["oiChange"] == 3786445 - 402220 == 3384225 and ce["oiChangePct"] == 841.39        # 3,384,225 / 402,220 = 8.413866…
    assert pe["oiChange"] == 3096145 - 2327260 == 768885 and pe["oiChangePct"] == 33.04         # 768,885 / 2,327,260 = 0.330384…
    # price change against previous_close_price
    assert ce["change"] == -110.85 and ce["changePct"] == -45.27                               # 110.85 / 244.85 = 0.452726…
    assert pe["change"] == 31.35 and pe["changePct"] == 30.9                                   # 31.35 / 101.45 = 0.309019…
    assert ce["buildup"] == "short_buildup" and pe["buildup"] == "long_buildup"                # call: price down, OI up; put: price up, OI up
    assert ce["iv"] == DOC_CE["implied_volatility"] and ce["delta"] == 0.53871 and ce["securityId"] == 42528
    assert ce["bid"] == 133.55 and ce["ask"] == 134 and ce["bidQty"] == 1625 and ce["volume"] == 117567970 and ce["avgPrice"] == 146.99


def test_build_up_needs_both_changes_known_and_non_zero():
    assert oc.buildup(1.5, 100) == "long_buildup"
    assert oc.buildup(-1.5, 100) == "short_buildup"
    assert oc.buildup(1.5, -100) == "short_covering"
    assert oc.buildup(-1.5, -100) == "long_unwinding"
    for p, o in ((0, 100), (1.5, 0), (None, 100), (1.5, None), (0, 0), (None, None)):
        assert oc.buildup(p, o) is None


def test_unknown_values_are_null_never_zero_and_real_zeros_are_kept():
    s = oc.side({"oi": 0, "previous_oi": 0, "volume": 0, "last_price": 0, "previous_close_price": 0, "implied_volatility": 0,
                 "top_bid_price": 0, "top_ask_price": 0, "top_bid_quantity": 0, "greeks": {"delta": 0, "theta": 0, "gamma": 0, "vega": 0}})
    assert s["oi"] == 0 and s["volume"] == 0 and s["oiChange"] == 0          # nothing open, nothing traded: real zeros
    assert s["oiChangePct"] is None                                           # no percentage of a zero base
    for k in ("ltp", "prevClose", "change", "changePct", "iv", "bid", "ask", "bidQty", "delta", "gamma", "theta", "vega", "buildup", "avgPrice"):
        assert s[k] is None, k
    s = oc.side({"oi": 500, "previous_oi": 0, "last_price": 12.5})            # a strike that opened today
    assert s["oiChange"] == 500 and s["oiChangePct"] is None and s["change"] is None and s["buildup"] is None
    s = oc.side({"last_price": 10})                                           # no OI fields at all
    assert s["oi"] is None and s["prevOi"] is None and s["oiChange"] is None and s["volume"] is None
    assert oc.side(None) is None and oc.side({}) is None and oc.side("x") is None
    assert oc.side({"oi": "NaN", "last_price": float("inf"), "greeks": {"delta": 0.5}})["oi"] is None
    assert oc.side({"oi": 1, "greeks": {"delta": 0.5, "gamma": 0, "theta": 0, "vega": 0}})["gamma"] == 0   # one real greek: the others are kept as sent


def test_rows_are_sorted_by_strike_and_empty_strikes_dropped():
    rows = oc.parse_rows({"120.000000": {"ce": leg(1)}, "100.000000": {"pe": leg(2)}, "110.500000": {"ce": leg(3), "pe": leg(4)},
                          "130.000000": {}, "junk": {"ce": leg(1)}, "-5": {"ce": leg(1)}})
    assert [r["strike"] for r in rows] == [100, 110.5, 120]
    assert rows[0]["ce"] is None and rows[0]["pe"]["oi"] == 2 and rows[2]["pe"] is None
    assert oc.parse_rows(None) == [] and oc.parse_rows([]) == []


def test_atm_is_the_nearest_strike_and_a_tie_goes_up():
    ks = [100.0, 105.0, 110.0]
    assert oc.atm_strike(ks, 102.49) == 100
    assert oc.atm_strike(ks, 102.5) == 105      # exactly midway: the higher strike
    assert oc.atm_strike(ks, 102.51) == 105
    assert oc.atm_strike(ks, 107.5) == 110      # midway again
    assert oc.atm_strike(ks, 250) == 110 and oc.atm_strike(ks, 1) == 100
    assert oc.atm_strike([25600.0, 25650.0, 25700.0], 25642.8) == 25650
    assert oc.atm_strike(ks, None) is None and oc.atm_strike([], 100) is None


def test_max_pain_worked_by_hand():
    # strike:      100   110   120
    # call OI:      10    20     5
    # put OI:        5    20    10
    # S = 100: calls 0;                     puts (110−100)×20 + (120−100)×10 = 200 + 200 = 400
    # S = 110: calls (110−100)×10 = 100;    puts (120−110)×10 = 100                   → 200
    # S = 120: calls 20×10 + 10×20 = 400;   puts 0                                    → 400
    rows = oc.parse_rows({"100": {"ce": leg(10), "pe": leg(5)}, "110": {"ce": leg(20), "pe": leg(20)}, "120": {"ce": leg(5), "pe": leg(10)}})
    mp = oc.max_pain(rows)
    assert mp["strike"] == 110 and mp["payout"] == 200
    assert [c["payout"] for c in mp["curve"]] == [400, 200, 400]


def test_max_pain_tie_goes_to_the_lower_strike_and_needs_some_oi():
    # call OI 1 at 100, put OI 1 at 110: S = 100 pays the put 10; S = 110 pays the call 10 → tie → 100
    rows = oc.parse_rows({"100": {"ce": leg(1), "pe": leg(0)}, "110": {"ce": leg(0), "pe": leg(1)}})
    assert oc.max_pain(rows)["strike"] == 100
    assert oc.max_pain(oc.parse_rows({"100": {"ce": leg(0)}, "110": {"pe": leg(0)}})) is None
    assert oc.max_pain([]) is None
    # paise strikes stay exact: 0.1 + 0.2 style float error never decides the minimum
    rows = oc.parse_rows({"10.10": {"ce": leg(3)}, "10.20": {"pe": leg(3)}, "10.30": {"pe": leg(1)}})
    assert oc.max_pain(rows) == {"strike": 10.2, "payout": 0.4, "curve": [{"strike": 10.1, "payout": 0.5}, {"strike": 10.2, "payout": 0.4},
                                                                          {"strike": 10.3, "payout": 0.6}]}


def test_summary_pcr_totals_itm_and_missing_sides():
    data = {"last_price": 108, "oc": {
        "100.000000": {"ce": leg(10, 4, 9.5, 8, vol=30, iv=12.5), "pe": leg(5, 5, 1.2, 1.5, vol=10)},
        "110.000000": {"ce": leg(20, 25, 2.5, 3, vol=50), "pe": leg(20, 10, 3.1, 2.9, vol=40)},
        "120.000000": {"ce": leg(5, 0, 0.5, 0.5, vol=20)},              # no put at this strike
    }}
    s = oc.summarize(data)
    t = s["summary"]["totals"]
    assert t["ce"]["oi"] == 35 and t["pe"]["oi"] == 25 and t["ce"]["volume"] == 100 and t["pe"]["volume"] == 50
    assert t["ce"]["oiChange"] == (10 - 4) + (20 - 25) + (5 - 0) == 6 and t["pe"]["oiChange"] == 0 + 10 == 10
    assert t["ce"]["strikes"] == 3 and t["pe"]["strikes"] == 2
    assert s["summary"]["pcrOi"] == round(25 / 35, 4) == 0.7143 and s["summary"]["pcrVolume"] == 0.5
    assert s["atm"] == 110 and [r["atm"] for r in s["rows"]] == [False, True, False]
    assert [r["ceItm"] for r in s["rows"]] == [True, False, False]       # calls below spot 108
    assert [r["peItm"] for r in s["rows"]] == [False, True, True]        # puts above it
    assert s["rows"][2]["pe"] is None and s["rows"][0]["ce"]["iv"] == 12.5 and s["rows"][1]["ce"]["iv"] is None
    assert s["rows"][0]["ce"]["buildup"] == "long_buildup" and s["rows"][1]["ce"]["buildup"] == "long_unwinding"   # price and OI both down
    assert s["rows"][0]["pe"]["buildup"] is None                          # OI unchanged
    assert s["rows"][1]["pe"]["buildup"] == "long_buildup" and s["rows"][2]["ce"]["buildup"] is None   # price unchanged
    # max pain by hand: S=100: puts 10×20 = 200; S=110: calls 10×10 = 100; S=120: calls 10×20 + 20×10 = 400 → 110
    assert s["summary"]["maxPain"] == {"strike": 110, "payout": 100}
    assert s["notes"] == []


def test_summary_without_spot_or_calls_says_so_and_never_divides_by_zero():
    s = oc.summarize({"oc": {"100": {"pe": leg(5)}}})
    assert s["spot"] is None and s["atm"] is None and not s["rows"][0]["peItm"] and s["summary"]["pcrOi"] is None
    assert any("last price" in n for n in s["notes"])
    s = oc.summarize({"last_price": 100, "oc": {"100": {"ce": {"last_price": 3}, "pe": leg(5)}}})
    assert s["summary"]["totals"]["ce"]["oi"] is None and s["summary"]["pcrOi"] is None and s["summary"]["missing"]["ce.oi"] == 1
    assert any("without open interest" in n for n in s["notes"])
    assert oc.summarize(None)["rows"] == [] and oc.summarize({"oc": "x"})["summary"]["maxPain"] is None


def test_expiries_are_cleaned_and_past_dates_dropped():
    assert oc.clean_expiries(["2026-10-27", "2026-10-20", "bad", "2026-02-30", "2026-11-03", "2026-10-27"], date(2026, 10, 23)) == ["2026-10-27", "2026-11-03"]
    assert oc.clean_expiries(None, date(2026, 10, 23)) == []


# ------------------------------------------------------------------------------------------------------------------ market hours

def ist(*a):
    return datetime(*a, tzinfo=IST)


def test_market_hours_and_freshness():
    fri = ist(2026, 10, 23, 11, 0)                                   # a Friday
    assert oc.market_open(fri) and oc.live_window(fri)
    assert not oc.market_open(ist(2026, 10, 23, 9, 14)) and oc.market_open(ist(2026, 10, 23, 9, 15))
    assert not oc.market_open(ist(2026, 10, 23, 15, 30)) and oc.live_window(ist(2026, 10, 23, 15, 34))   # closing figures still arriving
    assert not oc.live_window(ist(2026, 10, 23, 15, 35)) and not oc.live_window(ist(2026, 10, 24, 11, 0))  # Saturday
    # during the session: FRESH_SECONDS
    assert oc.chain_fresh(fri.timestamp() - 30, fri) and not oc.chain_fresh(fri.timestamp() - oc.FRESH_SECONDS, fri)
    # after the close: an answer taken after 15:35 is kept until Monday's open; one taken during the session is asked again once
    sat = ist(2026, 10, 24, 20, 0)
    assert oc.chain_fresh(ist(2026, 10, 23, 15, 40).timestamp(), sat) and not oc.chain_fresh(ist(2026, 10, 23, 15, 20).timestamp(), sat)
    mon_pre = ist(2026, 10, 26, 9, 10)
    assert oc.chain_fresh(ist(2026, 10, 23, 16, 0).timestamp(), mon_pre)
    assert not oc.chain_fresh(ist(2026, 10, 23, 16, 0).timestamp(), ist(2026, 10, 26, 9, 15))          # Monday's session has begun
    assert oc.next_open(sat) == ist(2026, 10, 26, 9, 15) and oc.next_open(ist(2026, 10, 23, 8, 0)) == ist(2026, 10, 23, 9, 15)
    assert oc.last_settle(mon_pre) == ist(2026, 10, 23, 15, 35)
    # the expiry list is asked again after each open and each close
    assert oc.expiries_fresh(ist(2026, 10, 23, 9, 20).timestamp(), fri) and not oc.expiries_fresh(ist(2026, 10, 23, 9, 0).timestamp(), fri)
    assert oc.last_mark(sat) == ist(2026, 10, 23, 15, 35)


# ------------------------------------------------------------------------------------------------------------------ lot sizes

CSV = """EXCH_ID,SEGMENT,SECURITY_ID,ISIN,INSTRUMENT,UNDERLYING_SECURITY_ID,UNDERLYING_SYMBOL,SYMBOL_NAME,DISPLAY_NAME,INSTRUMENT_TYPE,SERIES,LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE
NSE,I,13,NA,INDEX,13,NIFTY,NIFTY,Nifty 50,INDEX,NA,1.0,0001-01-01,-0.01000,XX
NSE,D,35008,NA,OPTIDX,26000,NIFTY,NIFTY-Nov2026-17350-CE,NIFTY 09 NOV 17350 CALL,OP,NA,65.0,2026-11-09,17350.00000,CE
NSE,D,35009,NA,OPTIDX,26000,NIFTY,NIFTY-Nov2026-17350-PE,NIFTY 09 NOV 17350 PUT,OP,NA,65.0,2026-11-09,17350.00000,PE
BSE,D,1,NA,OPTIDX,1,SENSEX,SENSEX-Oct2026-80000-CE,SENSEX 29 OCT 80000 CALL,OP,NA,20.0,2026-10-29,80000.00000,CE
NSE,D,106474,NA,OPTSTK,2885,RELIANCE,RELIANCE-Oct2026-720-CE,RELIANCE 27 OCT 720 CALL,OP,NA,500.0,2026-10-27,720.00000,CE
NSE,D,106475,NA,OPTSTK,2885,RELIANCE,RELIANCE-Oct2026-740-CE,RELIANCE 27 OCT 740 CALL,OP,NA,500.0,2026-10-27,740.00000,CE
NSE,D,106476,NA,OPTSTK,2885,RELIANCE,RELIANCE-Oct2026-760-CE,RELIANCE 27 OCT 760 CALL,OP,NA,505.0,2026-10-27,760.00000,CE
NSE,D,5001,NA,FUTSTK,2885,RELIANCE,RELIANCE-Oct2026-FUT,RELIANCE OCT FUT,FUT,NA,500.0,2026-10-27,-0.01000,XX
NSE,E,2885,INE002A01018,EQUITY,2885,RELIANCE,RELIANCE INDUSTRIES LTD,Reliance Industries,ES,EQ,1.0,0001-01-01,-0.01000,XX
"""


def test_lot_sizes_per_series_from_the_same_pass_over_the_instrument_file():
    lots = oc.LotCollector()
    eq = parse_instruments(CSV.splitlines(), on_row=lots.add)
    assert [r["symbol"] for r in eq] == ["RELIANCE"] and eq[0]["fno"] and eq[0]["lot_size"] == 500      # the equity parse is unchanged
    got = {(r["underlying"], r["expiry"].isoformat()): r for r in lots.rows()}
    assert set(got) == {("NIFTY", "2026-11-09"), ("SENSEX", "2026-10-29"), ("RELIANCE", "2026-10-27")}
    assert got[("NIFTY", "2026-11-09")]["lot_size"] == 65 and got[("NIFTY", "2026-11-09")]["exch"] == "NSE" and not got[("NIFTY", "2026-11-09")]["mixed"]
    assert got[("SENSEX", "2026-10-29")]["lot_size"] == 20 and got[("SENSEX", "2026-10-29")]["exch"] == "BSE"
    r = got[("RELIANCE", "2026-10-27")]
    assert r["lot_size"] == 500 and r["mixed"] and r["instrument"] == "OPTSTK" and r["underlying_id"] == "2885"   # 2 of 3 contracts at 500


def test_index_ids_are_the_ones_in_dhans_instrument_file():
    assert {i["key"]: (i["segment"], i["securityId"]) for i in oc.INDICES} == {
        "NIFTY": ("IDX_I", 13), "BANKNIFTY": ("IDX_I", 25), "FINNIFTY": ("IDX_I", 27), "MIDCPNIFTY": ("IDX_I", 442), "SENSEX": ("IDX_I", 51)}


# ------------------------------------------------------------------------------------------------------------------ pacer (Redis)

@pytest.fixture
async def redis():
    import redis.asyncio as aioredis
    from test_integration import TEST_REDIS
    r = aioredis.from_url(TEST_REDIS)
    try:
        await r.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"redis not available: {exc}")
    await r.delete(oc.PACE_KEY)
    yield r
    await r.delete(oc.PACE_KEY)
    await r.aclose()


async def test_the_pacer_hands_out_one_turn_per_gap_across_callers(redis):
    waits = await asyncio.gather(*(oc.take_turn(redis, gap=3.0, limit=10.0) for _ in range(4)))
    assert sorted(round(w, 1) for w in waits) == [0.0, 3.0, 6.0, 9.0]       # one turn every 3 s, whoever asks
    with pytest.raises(oc.Busy) as e:
        await oc.take_turn(redis, gap=3.0, limit=10.0)                       # the next would wait 12 s: refused, not queued
    assert 11.5 < e.value.retry_after <= 12.0
    ttl = await redis.pttl(oc.PACE_KEY)
    assert 0 < ttl <= 13_000                                                 # the reservation expires on its own


# ------------------------------------------------------------------------------------------------------------------ API (mocked Dhan)

from test_auth import app, anon, signed_in  # noqa: E402,F401  (fixtures and helpers)
from test_integration import ingested, store  # noqa: E402,F401

EXPIRIES = {"data": ["2020-01-02", "2026-10-27", "2026-11-03", "2099-12-31"], "status": "success"}


def chain_answer(spot=25642.8):
    return {"data": {"last_price": spot, "oc": {
        "25600.000000": {"ce": leg(1000, 800, 160.5, 150, vol=5000, iv=10.2), "pe": leg(3000, 2000, 95.0, 110.0, vol=9000, iv=11.0)},
        "25650.000000": {"ce": DOC_CE, "pe": DOC_PE},
        "25700.000000": {"ce": leg(4000, 4500, 60.0, 80.0, vol=7000, iv=9.5), "pe": {"oi": 0, "previous_oi": 0, "volume": 0, "last_price": 0}},
    }}, "status": "success"}


class FakeDhan:
    """Answers like Dhan's documented endpoints and records every call."""

    def __init__(self):
        self.calls, self.fail, self.refuse_seg, self.delay = [], False, None, 0.0
        self.spot = 25642.8

    async def handler(self, req: httpx.Request):
        body = json.loads(req.content)
        assert req.headers["access-token"] == "T" and req.headers["client-id"] == "1000000001"
        self.calls.append((req.url.path, body))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            return httpx.Response(500, json={"errorType": "Internal", "errorCode": "DH-908"})
        if self.refuse_seg and body.get("UnderlyingSeg") == self.refuse_seg:
            return httpx.Response(400, json={"errorType": "Input_Exception", "errorCode": "DH-905", "errorMessage": "Invalid segment"})
        if req.url.path.endswith("/optionchain/expirylist"):
            return httpx.Response(200, json=EXPIRIES)
        assert req.url.path.endswith("/optionchain") and set(body) == {"UnderlyingScrip", "UnderlyingSeg", "Expiry"}
        return httpx.Response(200, json=chain_answer(self.spot))

    def paths(self, suffix):
        return [c for c in self.calls if c[0].endswith(suffix)]


@pytest.fixture
async def dhan(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(oc, "PACE_SECONDS", 0.05)
    fake = FakeDhan()
    c = DhanClient(Settings(dhan_client_id="1000000001", dhan_access_token="T"), app.state.store.redis,
                   http=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    app.state.options_dhan = c
    st = app.state.store
    async with st.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.execute("DELETE FROM dhan_option_lots")
        await conn.executemany("INSERT INTO dhan_instruments (exch, security_id, symbol, name, series, fno, lot_size) VALUES ($1,$2,$3,$4,'EQ',$5,$6)",
                               [("NSE", "2885", "RELIANCE", "Reliance Industries", True, 500), ("NSE", "1333", "HDFCBANK", "HDFC Bank", True, 550),
                                ("NSE", "99001", "011NSETEST", None, True, 1), ("NSE", "11536", "TCS", "TCS", False, None), ("BSE", "500325", "RELIANCE", None, False, None)])
    for k in await st.redis.keys("oc:*"):
        await st.redis.delete(k)
    yield fake
    await c.aclose()


async def test_the_option_chain_is_gold_only(app, anon, dhan):  # noqa: F811
    assert (await anon.get("/api/options/underlyings")).status_code == 401
    silver = await signed_in(app, "s@example.com", plan="silver")
    for path in ("/api/options/underlyings", "/api/options/expiries?u=NIFTY", "/api/options/chain?u=NIFTY&expiry=2026-10-27"):
        r = await silver.get(path)
        assert r.status_code == 403 and r.json()["detail"]["plan"] == "gold", path
    assert dhan.calls == []                                                   # nothing reached Dhan for them
    gold = await signed_in(app, "g@example.com", plan="gold")
    body = (await gold.get("/api/options/underlyings")).json()
    assert [i["key"] for i in body["indices"]] == ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]
    assert [s["key"] for s in body["stocks"]] == ["HDFCBANK", "RELIANCE"]     # F&O only, no exchange test scrip, no BSE row
    assert body["stocks"][1] == {"key": "RELIANCE", "name": "Reliance Industries", "securityId": 2885, "lotSize": 500} and body["connected"]
    # once option series are loaded, only stocks that have options are listed
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_option_lots VALUES ('NSE','OPTSTK','RELIANCE','2885','2026-10-27',500,false)")
    assert [s["key"] for s in (await gold.get("/api/options/underlyings")).json()["stocks"]] == ["RELIANCE"]
    for c in (silver, gold):
        await c.aclose()


async def test_chain_end_to_end_with_shared_calls_and_cache(app, dhan):  # noqa: F811
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO dhan_option_lots VALUES ('NSE','OPTIDX','NIFTY','26000','2026-10-27',65,false)")
    gold = await signed_in(app, "g@example.com", plan="gold")
    r = await gold.get("/api/options/expiries?u=nifty")
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["expiries"] == ["2026-10-27", "2026-11-03", "2099-12-31"]     # a past date in Dhan's list is dropped
    assert dhan.calls == [("/v2/optionchain/expirylist", {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"})]

    # five visitors at once: one chain call
    rs = await asyncio.gather(*(gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27") for _ in range(5)))
    assert all(x.status_code == 200 for x in rs), [x.text for x in rs]
    assert dhan.paths("/optionchain") == [("/v2/optionchain", {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": "2026-10-27"})]
    assert len(dhan.paths("/expirylist")) == 1
    c = rs[0].json()
    assert c["spot"] == 25642.8 and c["atm"] == 25650 and c["lotSize"] == 65 and c["lotSource"] == "instrument file, this expiry"
    assert c["underlying"] == {"key": "NIFTY", "name": "Nifty 50", "kind": "index", "segment": "IDX_I", "securityId": 13, "exchange": "NSE"}
    assert [row["strike"] for row in c["rows"]] == [25600, 25650, 25700] and c["rows"][1]["atm"]
    t = c["summary"]["totals"]
    assert t["ce"]["oi"] == 1000 + 3786445 + 4000 and t["pe"]["oi"] == 3000 + 3096145 + 0
    assert c["summary"]["pcrOi"] == round((3000 + 3096145) / (1000 + 3786445 + 4000), 4)
    assert c["summary"]["pcrVolume"] == round((9000 + 157009970) / (5000 + 117567970 + 7000), 4)
    assert t["ce"]["oiChange"] == (1000 - 800) + (3786445 - 402220) + (4000 - 4500)
    pe0 = c["rows"][2]["pe"]
    assert pe0["oi"] == 0 and pe0["ltp"] is None and pe0["change"] is None                      # a real zero OI; no trade is not a 0 price
    assert c["rows"][0]["ce"]["buildup"] == "long_buildup" and c["rows"][2]["ce"]["buildup"] == "long_unwinding"
    assert c["rows"][0]["pe"]["buildup"] == "short_buildup"
    assert c["summary"]["maxPain"]["strike"] in (25600, 25650, 25700) and c["state"] == "fresh" and c["asOf"].endswith("+05:30")
    # max pain by hand for these three strikes (call OI 1000 / 3786445 / 4000, put OI 3000 / 3096145 / 0):
    #   S=25600: puts 50×3096145 + 100×0 = 154,807,250
    #   S=25650: calls 50×1000 = 50,000; puts 50×0 = 0 → 50,000
    #   S=25700: calls 100×1000 + 50×3786445 = 189,422,250
    assert c["summary"]["maxPain"] == {"strike": 25650, "payout": 50000}
    # asked again straight away: from the cache, no new call
    again = (await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27")).json()
    assert again["state"] == "fresh" and len(dhan.paths("/optionchain")) == 1 and again["asOf"] == c["asOf"]

    # an unlisted or bad expiry never reaches Dhan
    assert (await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-28")).status_code == 404
    assert (await gold.get("/api/options/chain?u=NIFTY&expiry=27-10-2026")).status_code == 400
    assert (await gold.get("/api/options/chain?u=NOPE&expiry=2026-10-27")).status_code == 404
    assert (await gold.get("/api/options/chain?u=TCS&expiry=2026-10-27")).status_code == 404       # no F&O
    assert len(dhan.calls) == 2
    await gold.aclose()


async def test_a_stale_chain_is_served_with_its_time_when_dhan_fails(app, dhan):  # noqa: F811
    gold = await signed_in(app, "g@example.com", plan="gold")
    first = (await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27")).json()
    key = "oc:chain:NIFTY:2026-10-27"
    redis = app.state.store.redis
    entry = json.loads(await redis.get(key))
    entry["t"] = time.time() - 10 * 24 * 3600                                 # ten days old: stale in or out of market hours
    await redis.set(key, json.dumps(entry))
    dhan.fail = True
    r = await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27")
    assert r.status_code == 200 and r.json()["state"] == "refreshing" and r.json()["ageSeconds"] >= 10 * 24 * 3600 - 5
    for _ in range(40):                                                       # the background refresh fails…
        if not await redis.exists(key + ":lock"):
            break
        await asyncio.sleep(0.05)
    r = await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27")
    assert r.status_code == 200 and r.json()["state"] == "stale" and r.json()["spot"] == first["spot"]   # …the old answer stays, with its time
    n = len(dhan.paths("/optionchain"))
    await gold.get("/api/options/chain?u=NIFTY&expiry=2026-10-27")
    assert len(dhan.paths("/optionchain")) == n                               # and Dhan is left alone for a while after failing
    # with nothing stored, a failure is an error, not an empty chain
    dhan.fail = False
    await redis.delete("oc:exp:NIFTY")
    dhan.fail = True
    r = await gold.get("/api/options/chain?u=NIFTY&expiry=2026-11-03")
    assert r.status_code == 502 and r.json()["detail"]["status"] == "provider_unavailable"
    await gold.aclose()


async def test_stock_chains_use_the_stock_segment_and_fall_back_once(app, dhan):  # noqa: F811
    gold = await signed_in(app, "g@example.com", plan="gold")
    dhan.refuse_seg = "NSE_EQ"                                                # if Dhan wanted the F&O segment instead…
    r = await gold.get("/api/options/expiries?u=RELIANCE")
    assert r.status_code == 200 and r.json()["underlying"]["segment"] == "NSE_FNO"
    assert [c[1] for c in dhan.calls] == [{"UnderlyingScrip": 2885, "UnderlyingSeg": "NSE_EQ"}, {"UnderlyingScrip": 2885, "UnderlyingSeg": "NSE_FNO"}]
    assert await app.state.store.redis.get(oc.STOCK_SEG_KEY) == b"NSE_FNO"   # …it is remembered, and the next stock asks that first
    c = (await gold.get("/api/options/chain?u=RELIANCE&expiry=2026-10-27")).json()
    assert dhan.calls[-1][1] == {"UnderlyingScrip": 2885, "UnderlyingSeg": "NSE_FNO", "Expiry": "2026-10-27"}
    assert c["lotSize"] == 500 and c["lotSource"] == "instrument file, the stock's futures" and c["underlying"]["kind"] == "stock"
    await gold.get("/api/options/expiries?u=HDFCBANK")
    assert dhan.calls[-1][1] == {"UnderlyingScrip": 1333, "UnderlyingSeg": "NSE_FNO"}
    await gold.aclose()


async def test_stock_chain_asks_the_stock_segment_first(app, dhan):  # noqa: F811
    gold = await signed_in(app, "g@example.com", plan="gold")
    r = await gold.get("/api/options/expiries?u=RELIANCE")
    assert r.json()["underlying"]["segment"] == "NSE_EQ" and len(dhan.calls) == 1
    await gold.aclose()


async def test_not_connected_and_busy(app, dhan, monkeypatch):  # noqa: F811
    gold = await signed_in(app, "g@example.com", plan="gold")
    await app.state.options_dhan.aclose()
    app.state.options_dhan = DhanClient(Settings(), app.state.store.redis)
    r = await gold.get("/api/options/expiries?u=NIFTY")
    assert r.status_code == 503 and r.json()["detail"]["status"] == "not_connected"
    assert (await gold.get("/api/options/underlyings")).json()["connected"] is False
    # every turn taken for longer than a visitor should wait: "busy" with Retry-After, and Dhan is not asked
    fake = FakeDhan()
    app.state.options_dhan = DhanClient(Settings(dhan_client_id="1000000001", dhan_access_token="T"), app.state.store.redis,
                                        http=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    await app.state.store.redis.set(oc.PACE_KEY, str(time.time() + 60), ex=60)
    r = await gold.get("/api/options/expiries?u=NIFTY")
    assert r.status_code == 503 and r.json()["status"] == "busy" and int(r.headers["retry-after"]) >= 40 and fake.calls == []
    await app.state.store.redis.delete(oc.PACE_KEY)
    await gold.aclose()
