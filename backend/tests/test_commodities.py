"""Commodity prices (finlit/commodity_calc.py, commodity_feeds.py, commodities.py).

The formula expectations are worked out independently with exact rational arithmetic (not by calling the code under test) and agree with the
spec's section 5 vectors. Vendor answers are mocks in the documented shapes (MetalpriceAPI: success/timestamp/rates with USDXAU keys; metals.dev:
status/metals/currencies/timestamps); Dhan answers follow its v2 quote shape. The instrument rows are real rows of Dhan's 23 Oct 2026 file
(tests/fixtures/dhan/instruments_mcx.csv). No account, key or live call was used.
"""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from finlit import commodities as cm, commodity_calc as calc, commodity_feeds as feeds, dhan
from test_indices import FakeRedis
from test_integration import make_settings, store  # noqa: F401  (fixture)

IST = cm.IST
CSV = Path(__file__).parent / "fixtures" / "dhan" / "instruments_mcx.csv"
NOW = datetime(2026, 10, 23, 21, 42, 10, tzinfo=IST)      # a Friday evening, MCX open, global market open
TS = NOW.timestamp()


# ================================================================================================================ arithmetic
def test_constants_are_exact():
    assert calc.TROY_OZ_G == D("31.1034768") and calc.TOLA_G == D("11.6638038")


@pytest.mark.parametrize("usd,duty,base,paid,gst,per10,perkg", [
    ("4032.30", "0.15", "12315.94", "14163.33", "14588.23", "141633", "14163329"),      # gold, 15% = BCD 10 + AIDC 5
    ("54.27", "0.15", "165.76", "190.62", "196.34", "1906", "190622"),                  # silver
    ("1573.30", "0.154", "4805.36", "5545.39", "5711.75", "55454", "5545389"),          # platinum, assumed 15.4%
])
def test_import_parity_at_95(usd, duty, base, paid, gst, per10, perkg):
    bcd = D("0.10")
    p = calc.parity(D(usd), D("95.00"), bcd, D(duty) - bcd, D("0.03"))
    assert (calc.q(p.base, 2), calc.q(p.duty_paid, 2), calc.q(p.with_gst, 2)) == (base, paid, gst)
    assert (calc.q(p.duty_paid * 10, 0), calc.q(p.duty_paid * 1000, 0)) == (per10, perkg)   # from the unrounded base, not from 14,163.33


def test_purity_and_screenshot_arithmetic():
    mcx = D(14250)
    assert calc.q(calc.k22(mcx), 2) == "13062.50" and calc.q(calc.k18(mcx), 2) == "10687.50"
    assert calc.q(calc.k22(mcx, "916"), 2) == "13053.00"           # the BIS convention is Rs 9.50 lower
    assert calc.q(mcx * 10, 0) == "142500" and calc.q(D(196150) / 1000, 2) == "196.15"


def test_premium_like_for_like():
    paid = calc.parity(D("4032.30"), D("95.00"), D("0.10"), D("0.05"), D("0.03")).duty_paid
    assert calc.q(calc.premium_pct(D(14250), paid), 2) == "0.61"                       # no purity adjustment
    assert calc.q(calc.premium_pct(calc.mcx_to_fine(D(14250)), paid), 2) == "1.02"     # MCX 995 scaled to 999 (the default)
    silver = calc.parity(D("54.27"), D("95.00"), D("0.10"), D("0.05"), D("0.03")).duty_paid
    assert calc.q(calc.premium_pct(D("196.15"), silver), 2) == "2.90"
    assert calc.premium_pct(D(1), D(0)) is None


def test_ratio_units_and_rounding():
    assert calc.q(D("4032.30") / D("54.27"), 1) == "74.3"
    assert calc.usd_per_tonne_to_inr_per_kg(D(10000), D(95)) == D(950)
    assert calc.q(D("2.675"), 2) == "2.68" and calc.q(D("-2.675"), 2) == "-2.68"      # half up, not half even and not binary float
    assert calc.q(D("-0.001"), 2) == "0.00"                                            # no "-0.00"
    assert calc.dec("x") is None and calc.dec(None) is None and calc.dec("NaN") is None and calc.dec(True) is None


def test_day_change():
    pct, ab = calc.day_change(D(142500), D(141620))[1], calc.day_change(D(142500), D(141620))[0]
    assert calc.q(pct, 2) == "0.62" and calc.q(ab / 10, 2) == "88.00"
    assert calc.day_change(D(5), D(0)) is None and calc.day_change(D(5), D(-3)) is None and calc.day_change(D(5), None) is None
    assert calc.day_change(D(5), D(5)) == (0, 0)


# ================================================================================================================ vendor adapters
METALS_DEV = {"status": "success", "currency": "USD", "unit": "toz",
              "metals": {"gold": 4032.30, "silver": 54.27, "platinum": 1573.30, "palladium": 1400.5, "copper": 10000.5, "aluminum": 2800.25, "mcx_gold": 4100},
              "currencies": {"INR": 0.0105263158, "EUR": 0.92},
              "timestamps": {"metal": "2026-10-23T16:12:00.000Z", "currency": "2026-10-23T16:11:00.000Z"}}
METALPRICE = {"success": True, "base": "USD", "timestamp": 1792772400,
              "rates": {"INR": 0.0105263158, "USDINR": 95.0, "XAU": 0.000248, "USDXAU": 4032.30, "USDXAG": 54.27, "USDXPT": 1573.30,
                        "USDWTI": 71.55, "USDBRENT": 75.1, "NATURALGAS": 0.3333333333, "USDNATURALGAS": 3.0}}


def test_metals_dev_parse_exact_and_direction_of_the_rate():
    s = feeds.parse_metals_dev(json.loads(json.dumps(METALS_DEV), parse_float=D))
    assert s.quotes["gold"].usd == D("4032.30") and s.quotes["aluminium"].usd == D("2800.25") and "palladium" not in s.quotes
    assert abs(s.usdinr.usd - D("95")) < D("0.0001")                                    # dollars-per-rupee turned into rupees per dollar
    assert s.quotes["gold"].ts == datetime(2026, 10, 23, 16, 12, tzinfo=timezone.utc).timestamp()
    inr = json.loads(json.dumps({**METALS_DEV, "currencies": {"INR": 95.0}}), parse_float=D)
    assert feeds.parse_metals_dev(inr).usdinr.usd == D("95.0")                          # already rupees per dollar
    bad = json.loads(json.dumps({**METALS_DEV, "currencies": {"INR": 3.0}}), parse_float=D)
    assert feeds.parse_metals_dev(bad).usdinr is None                                   # an implausible rate is dropped, never shown


def test_metals_dev_errors_and_junk():
    with pytest.raises(feeds.FeedError, match="1102"):
        feeds.parse_metals_dev({"status": "failure", "error_code": 1102})
    with pytest.raises(feeds.FeedError):
        feeds.parse_metals_dev([])
    s = feeds.parse_metals_dev({"status": "success", "metals": {"gold": "n/a", "silver": 0, "copper": -4}, "timestamps": {"metal": "2026-10-23T16:12:00Z"}})
    assert s.quotes == {} and s.usdinr is None                                           # junk, zero and negative prices are dropped, not guessed


def test_metalprice_parse_uses_the_usd_keys():
    s = feeds.parse_metalprice(json.loads(json.dumps(METALPRICE), parse_float=D))
    assert s.quotes["gold"].usd == D("4032.30") and s.quotes["wti"].usd == D("71.55") and s.quotes["natgas"].usd == D("3.0")
    assert s.usdinr.usd == D("95.0") and s.vendor == "MetalpriceAPI"
    assert "gold" not in feeds.parse_metalprice(json.loads(json.dumps(METALPRICE), parse_float=D), metals=False).quotes
    inv = feeds.parse_metalprice({"success": True, "timestamp": 1, "rates": {"XAU": D("0.5"), "INR": D("0.01")}})
    assert inv.quotes["gold"].usd == D("2") and inv.usdinr.usd == D("100")               # inverse keys only when the USD key is absent
    with pytest.raises(feeds.FeedError, match="104"):
        feeds.parse_metalprice({"success": False, "error": {"code": 104, "message": "quota"}})


async def test_fetch_sends_the_key_and_never_leaks_it():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, text=json.dumps(METALS_DEV) if "metals.dev" in str(req.url) else json.dumps(METALPRICE))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        a = await feeds.fetch_metals_dev(http, "SECRET1")
        b = await feeds.fetch_metalprice(http, "SECRET2", metals=False)
    assert a.quotes["copper"].usd == D("10000.5") and "wti" in b.quotes and "gold" not in b.quotes
    assert seen[1].headers["x-api-key"] == "SECRET2" and "SECRET2" not in str(seen[1].url)
    assert "WTI" in str(seen[1].url) and "XAU" not in str(seen[1].url)

    async def down(req):
        raise httpx.ConnectError("boom SECRET3", request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as http:
        with pytest.raises(feeds.FeedError) as e:
            await feeds.fetch_metals_dev(http, "SECRET3")
    assert "SECRET3" not in str(e.value) and "api_key" not in str(e.value)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429))) as http:
        with pytest.raises(feeds.FeedError, match="HTTP 429"):
            await feeds.fetch_metalprice(http, "k")


# ================================================================================================================ instruments and contracts
def contract_rows():
    out = []
    dhan.parse_instruments(CSV.read_text(encoding="utf-8").splitlines(), commodities=out)
    for r in out:
        r["upper"], r["lower"] = (str(r["upper"]), str(r["lower"]))
    return [{"security_id": r["security_id"], "symbol": r["symbol"], "display_name": r["display_name"], "expiry": r["expiry"], "upper": r["upper"], "lower": r["lower"]} for r in out]


def test_parse_reads_only_mcx_futures_from_the_real_file():
    out = []
    eq = dhan.parse_instruments(CSV.read_text(encoding="utf-8").splitlines(), commodities=out)
    assert eq == [] and len(out) == 50
    gold = next(r for r in out if r["display_name"] == "GOLD DEC FUT")
    assert gold == {"security_id": "495213", "symbol": "GOLD", "display_name": "GOLD DEC FUT", "expiry": "2026-12-04", "tick_paise": 100.0, "upper": 147608.0, "lower": 139010.0}
    assert dhan.parse_instruments(CSV.read_text(encoding="utf-8").splitlines()) == []     # without the list, nothing changes for callers


def test_roll_rule_on_23_oct_2026():
    rows, today = contract_rows(), date(2026, 10, 23)
    names = lambda sym: [c["display_name"] for c in cm.candidates(rows, sym, today)]       # noqa: E731
    assert names("GOLD") == ["GOLD DEC FUT", "GOLD FEB FUT"] and names("SILVER") == ["SILVER DEC FUT", "SILVER MAR FUT"]
    assert names("CRUDEOIL")[0] == "CRUDEOIL NOV FUT" and names("COPPER") == ["COPPER OCT FUT", "COPPER NOV FUT"]
    assert names("NATURALGAS") == ["NATURALGAS OCT FUT", "NATURALGAS NOV FUT"]            # expires in 4 days: both are asked
    assert [c["display_name"] for c in cm.candidates(rows, "NATURALGAS", date(2026, 10, 27))][0] == "NATURALGAS NOV FUT"   # expiry day is left out
    ng = cm.candidates(rows, "NATURALGAS", today)
    assert cm.choose(ng, {}, None)["display_name"] == "NATURALGAS OCT FUT"                 # no volume: the nearest
    vol = {ng[0]["security_id"]: {"volume": 100}, ng[1]["security_id"]: {"volume": 900}}
    assert cm.choose(ng, vol, None)["display_name"] == "NATURALGAS NOV FUT"                # the next trades more
    assert cm.choose(ng, {ng[0]["security_id"]: {"volume": 5000}, ng[1]["security_id"]: {"volume": 1}}, ng[1]["security_id"])["display_name"] == "NATURALGAS NOV FUT"   # kept: no flipping back
    assert cm.choose(ng, {ng[0]["security_id"]: {"volume": 5000}, ng[1]["security_id"]: {"volume": 1}}, ng[0]["security_id"])["display_name"] == "NATURALGAS OCT FUT"
    assert cm.choose([], {}, None) is None and cm.candidates(rows, "GOLD", date(2030, 1, 1)) == []


def raw_quote(price, net, at="23/10/2026 21:41:58", vol=1000, close=None):
    return {"last_price": price, "net_change": net, "volume": vol, "last_trade_time": at, "ohlc": {"open": price, "high": price, "low": price, "close": close if close is not None else price - net}}


def test_read_quote_guards():
    gold = {"upper": "147608", "lower": "139010"}
    ok, why = cm.read_quote(raw_quote(142500, 880), gold)
    assert why is None and ok["price"] == "142500" and ok["prev"] == "141620" and ok["lastTrade"] == "2026-10-23T21:41:58+05:30" and not ok["noTrade"]
    assert cm.read_quote(raw_quote(150000, 880), gold)[1] == "outside the exchange price band"
    assert cm.read_quote(raw_quote(138000, 880), gold)[1] == "outside the exchange price band"
    assert cm.read_quote(raw_quote(142500, 880), {"upper": "147608", "lower": "0.0"})[0] is not None     # a zero bound is unknown
    assert cm.read_quote(raw_quote(142500, 20000), {})[1] == "day move above 12%"
    nt, _ = cm.read_quote(raw_quote(0, 0, at="01/01/1980 00:00:00", close=141620), gold)               # no trade yet: the previous close, flagged
    assert nt["price"] == "141620" and nt["noTrade"] and nt["prev"] is None and nt["lastTrade"] is None
    assert cm.read_quote(raw_quote(0, 0, at="01/01/1980 00:00:00", close=0), gold)[1] == "no price"
    assert cm.read_quote({}, gold)[1] == "no price"


def test_mcx_update_picks_contracts_keeps_old_reading_and_hides_change_after_a_roll():
    rows, today = contract_rows(), date(2026, 10, 23)
    ids = {c["display_name"]: c["security_id"] for c in rows}
    raw = {("MCX_COMM", ids["GOLD DEC FUT"]): raw_quote(142500, 880), ("MCX_COMM", ids["SILVER DEC FUT"]): raw_quote(196150, 1000),
           ("MCX_COMM", ids["GOLD FEB FUT"]): raw_quote(145000, 800, vol=1)}
    first = cm.mcx_update(rows, raw, {}, today, 1000.0)
    assert first["GOLD"]["name"] == "GOLD DEC FUT" and first["GOLD"]["next"] == "GOLD FEB FUT" and first["GOLD"]["rolledOn"] is None
    assert set(first) == {"GOLD", "SILVER"}                                                  # the others had no answer and there is nothing to keep
    # Dhan answers for GOLD with an implausible price: the earlier reading stays (with the reason) and is judged by its age
    bad = {**raw, ("MCX_COMM", ids["GOLD DEC FUT"]): raw_quote(190000, 880)}
    second = cm.mcx_update(rows, bad, first, today, 2000.0)
    assert second["GOLD"]["price"] == "142500" and second["GOLD"]["fetched"] == 1000.0 and second["GOLD"]["why"] == "outside the exchange price band"
    # the contract changes (the nearer one expired): flagged as rolled today
    later = cm.mcx_update(rows, {("MCX_COMM", ids["GOLD FEB FUT"]): raw_quote(145000, 800)}, first, date(2026, 12, 5), 3000.0)
    assert later["GOLD"]["name"] == "GOLD FEB FUT" and later["GOLD"]["rolledOn"] == "2026-12-05"


# ================================================================================================================ hours and states
HOURS = [{"from": "2026-03-09", "to": "2026-10-30", "open": "09:00", "close": "23:30", "confirmed": True},
         {"from": "2026-11-02", "to": "2027-03-12", "open": "09:00", "close": "23:55", "confirmed": False}]


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


def test_hours_across_the_30_oct_2_nov_boundary():
    s = lambda *a, hol=(): cm.mcx_session(at(*a), HOURS, list(hol))     # noqa: E731
    assert s(2026, 10, 30, 23, 29)["open"] and not s(2026, 10, 30, 23, 30)["open"]          # Friday: the summer close, 23:30
    assert not s(2026, 10, 31, 12, 0)["open"] and s(2026, 10, 31, 12, 0)["why"] == "weekend"
    assert not s(2026, 11, 1, 12, 0)["open"]
    mon = s(2026, 11, 2, 23, 40)
    assert mon["open"] and mon["closes"] == "23:55" and mon["confirmed"] is False           # Monday: the winter close, flagged unconfirmed
    assert not s(2026, 11, 2, 23, 55)["open"] and not s(2026, 11, 2, 8, 59)["open"] and s(2026, 11, 2, 9, 0)["open"]
    assert s(2026, 10, 23, 12, 0)["confirmed"] is True
    far = cm.mcx_session(at(2028, 1, 5, 12, 0), HOURS, [])                                    # no row: the default, and it says so
    assert far["open"] and far["closes"] == "23:30" and far["confirmed"] is False


def test_holidays_full_and_morning_only():
    hol = [{"day": "2026-11-09", "kind": "full"}, {"day": "2026-11-10", "kind": "morning"}]
    assert not cm.mcx_session(at(2026, 11, 9, 20, 0), HOURS, hol)["open"] and cm.mcx_session(at(2026, 11, 9, 20, 0), HOURS, hol)["why"] == "holiday"
    assert not cm.mcx_session(at(2026, 11, 10, 12, 0), HOURS, hol)["open"] and cm.mcx_session(at(2026, 11, 10, 17, 0), HOURS, hol)["open"]


def test_global_market_hours():
    u = lambda d, h, m=0: cm.global_open(datetime(2026, 10, d, h, m, tzinfo=timezone.utc))      # noqa: E731
    assert u(23, 21, 59) and not u(23, 22) and not u(24, 12) and not u(25, 22, 59) and u(25, 23) and u(26, 3)   # Fri 23 .. Sun 25 .. Mon 26


def reading(price="142500", prev="141620", traded="2026-10-23T21:41:58+05:30", fetched=None, **kw):
    return {"sid": "495213", "name": "GOLD DEC FUT", "expiry": "2026-12-04", "next": None, "price": price, "prev": prev, "volume": 10, "lastTrade": traded,
            "noTrade": traded is None, "fetched": TS - 5 if fetched is None else fetched, "rolledOn": None, "why": None, **kw}


def test_mcx_state_matrix():
    sess = cm.mcx_session(NOW, HOURS, [])
    st = lambda r, hb=3.0, now=NOW, ss=sess: cm.mcx_state(now, ss, r, hb)       # noqa: E731
    assert st(reading()) == "live"                                                # 12 s since the last trade
    assert st(reading(traded="2026-10-23T21:40:10+05:30")) == "live"              # exactly 2 minutes
    assert st(reading(traded="2026-10-23T21:39:00+05:30")) == "recent"            # 3 minutes
    assert st(reading(traded="2026-10-23T21:27:10+05:30")) == "recent"            # exactly 15 minutes
    assert st(reading(traded="2026-10-23T21:12:00+05:30")) == "delayed"
    assert st(reading(), hb=61.0) == "delayed" and st(reading(), hb=None) == "delayed"      # the worker is silent
    assert st(reading(fetched=TS - 120)) == "delayed"                              # Dhan has not answered for two minutes
    assert st(None) == "none"
    closed = cm.mcx_session(at(2026, 10, 24, 12, 0), HOURS, [])
    assert st(reading(), ss=closed, now=at(2026, 10, 24, 12, 0)) == "closed"
    # open, but the last trade is from a past day: waiting in the first 10 minutes, then treated as a holiday
    old = reading(traded="2026-10-22T23:29:00+05:30")
    assert st(old, now=at(2026, 10, 23, 9, 5), ss=cm.mcx_session(at(2026, 10, 23, 9, 5), HOURS, [])) == "waiting"
    assert st(old, now=at(2026, 10, 23, 9, 11), ss=cm.mcx_session(at(2026, 10, 23, 9, 11), HOURS, [])) == "closed"
    assert st(reading(traded=None), now=at(2026, 10, 23, 12, 0), ss=cm.mcx_session(at(2026, 10, 23, 12, 0), HOURS, [])) == "closed"


def test_international_state_matrix():
    v = lambda age, poll=60: {"ts": TS - age, "poll": poll}      # noqa: E731
    f = lambda age, poll=60, open_=True: cm.intl_state(TS, open_, v(age, poll))      # noqa: E731
    assert f(30) == "fresh" and f(300) == "fresh" and f(301) == "stale" and f(1800) == "stale" and f(1801) == "unavailable"
    assert f(900, 600) == "fresh" and f(1800, 600) == "fresh" and f(2000, 600) == "stale"      # a 10-minute plan is judged by its own poll
    assert f(2 * 86400, open_=False) == "closed" and f(5 * 86400, open_=False) == "unavailable"
    assert cm.intl_state(TS, True, None) == "none"


def test_reference_roll_keeps_fridays_change_over_the_weekend():
    fri_close = datetime(2026, 10, 23, 16, 59, tzinfo=cm.NY).timestamp()      # 16:59 New York on Friday
    mon_open = datetime(2026, 10, 25, 17, 5, tzinfo=cm.NY).timestamp()        # Sunday 17:05 New York: already Monday's trading day
    thu = datetime(2026, 10, 22, 16, 30, tzinfo=cm.NY).timestamp()
    assert cm.trading_day(fri_close) == "2026-10-23" and cm.trading_day(mon_open) == "2026-10-26" and cm.trading_day(thu) == "2026-10-22"
    r, done = cm.roll_ref(None, cm.trading_day(thu), "4000")
    assert r == {"day": "2026-10-22", "last": "4000", "prev": None} and done is None          # first sight: no day change yet, not guessed
    r, done = cm.roll_ref(r, cm.trading_day(fri_close), "4032.30")
    assert r["prev"] == "4000" and done == {"day": "2026-10-22", "value": "4000"}
    for _ in range(3):                                                                    # the frozen weekend price carries Friday's time
        r, done = cm.roll_ref(r, cm.trading_day(fri_close), "4032.30")
        assert r["prev"] == "4000" and done is None
    r, done = cm.roll_ref(r, cm.trading_day(mon_open), "4040")
    assert r == {"day": "2026-10-26", "last": "4040", "prev": "4032.30"} and done == {"day": "2026-10-23", "value": "4032.30"}
    assert cm.roll_ref(r, "2026-10-01", "1")[0] == r                                      # older data than held is ignored


# ================================================================================================================ the answer
DUTY = [{"metal": "gold", "from": "2026-05-13", "bcd": "10", "aidc": "5", "gst": "3", "checked": "2026-10-23", "confirmed": True, "source": "x"},
        {"metal": "silver", "from": "2026-05-13", "bcd": "10", "aidc": "5", "gst": "3", "checked": "2026-10-23", "confirmed": True, "source": "x"},
        {"metal": "gold", "from": "2024-07-24", "bcd": "5", "aidc": "1", "gst": "3", "checked": "2024-07-24", "confirmed": True, "source": "old"},
        {"metal": "platinum", "from": "2026-05-13", "bcd": "10", "aidc": "5.4", "gst": "3", "checked": "2026-10-23", "confirmed": False, "source": "assumed"}]
CFG = {"duty": DUTY, "hours": HOURS, "holidays": []}


def settings(**kw):
    return SimpleNamespace(**{"dhan_client_id": "c", "metals_dev_api_key": "k", "metalprice_api_key": "k2", "commodity_mcx_display_cleared": False, **kw})


def mcx_blob(**over):
    return {"t": TS - 3, "err": None, "items": {
        "GOLD": reading(), "SILVER": reading(price="196150", prev="195150", name="SILVER DEC FUT", sid="495214"),
        "CRUDEOIL": reading(price="9400", prev="9300", name="CRUDEOIL NOV FUT", sid="573422"), "NATURALGAS": reading(price="262.3", prev="260.1", name="NATURALGAS OCT FUT", sid="1"),
        "COPPER": reading(price="1350.55", prev="1340.05", name="COPPER OCT FUT", sid="2"), "ALUMINIUM": reading(price="320.1", prev="319.1", name="ALUMINIUM OCT FUT", sid="3"), **over}}


def q_(usd, prev=None, age=20, vendor="metals.dev", poll=60):
    return {"usd": usd, "ts": TS - age, "vendor": vendor, "fetched": TS - 5, "poll": poll, "prev": prev}


def fx_(age=20):
    return {"usdinr": "95.00", "ts": TS - age, "vendor": "metals.dev", "fetched": TS - 5, "poll": 60}


def intl_blob(**over):
    return {"quotes": {"gold": q_("4032.30", "4000.00"), "silver": q_("54.27", "54.00"), "platinum": q_("1573.30", "1580"), "copper": q_("10000.5", "9900"),
                       "aluminium": q_("2800.25"), "wti": q_("71.55", "70", vendor="MetalpriceAPI", poll=600), "brent": q_("75.1", None, vendor="MetalpriceAPI", poll=600),
                       "natgas": q_("3.0", "3.1", vendor="MetalpriceAPI", poll=600)},
            "fx": fx_(), "err": {}, **over}


def item(body, code):
    return next(i for i in body["items"] if i["code"] == code)


def test_full_answer_matches_the_worked_vectors():
    b = cm.build(settings(), NOW, mcx_blob(), intl_blob(), CFG, TS - 2)
    g = item(b, "gold")
    assert g["mcx"]["state"] == "live" and g["mcx"]["label"] == "Updating"                    # never "Live" until the permission is cleared
    assert g["mcx"]["contract"] == "GOLD DEC FUT" and g["mcx"]["expiry"] == "2026-12-04"
    assert g["mcx"]["price"] == {"value": "14250.00", "unit": "₹ per gram"}
    assert [(e["label"], e["value"]) for e in g["mcx"]["extra"]] == [("Exchange quote, per 10 g", "142500"), ("22K, per gram", "13062.50"), ("18K, per gram", "10687.50")]
    assert g["mcx"]["change"] == {"pct": "0.62", "abs": "88.00", "absUnit": "₹ per gram"}
    assert g["intl"][0]["usd"] == "4032.30" and g["intl"][0]["changePct"] == "0.81" and g["intl"][0]["state"] == "fresh"
    p = g["parity"]
    assert p["state"] == "ok" and (p["perGram"], p["withGst"], p["per10g"], p["perKg"]) == ("14163.33", "14588.23", "141633", "14163329")
    assert p["duty"]["bcd"] == "10" and p["duty"]["aidc"] == "5" and p["duty"]["total"] == "15" and p["duty"]["gst"] == "3" and p["duty"]["effectiveFrom"] == "2026-05-13"
    assert p["premiumPct"] == "1.02" and "995" in p["premiumBasis"] and p["usdinr"] == "95.0000"
    s = item(b, "silver")
    assert s["mcx"]["price"]["value"] == "196.15" and s["mcx"]["extra"] == [{"label": "Exchange quote, per kg", "value": "196150", "unit": "₹"}]
    assert (s["parity"]["perGram"], s["parity"]["premiumPct"]) == ("190.62", "2.90")
    assert b["ratio"]["goldSilver"] == "74.3" and b["fx"]["usdinr"] == "95.0000" and b["assumptions"]["k22"] == "22/24"
    assert b["market"]["mcx"]["open"] and b["market"]["global"]["open"] and b["status"] == "ok"
    c = item(b, "crude")
    assert c["mcx"]["price"] == {"value": "9400", "unit": "₹ per barrel"} and [x["key"] for x in c["intl"]] == ["wti", "brent"] and c["parity"] is None
    assert item(b, "natgas")["mcx"]["price"]["value"] == "262.3" and item(b, "natgas")["intl"][0]["usd"] == "3.000"
    assert item(b, "copper")["mcx"]["price"] == {"value": "1350.55", "unit": "₹ per kg"} and item(b, "copper")["parity"] is None      # no parity for base metals
    assert [i["code"] for i in b["items"]] == ["gold", "silver", "platinum", "crude", "natgas", "copper", "aluminium"]


def test_platinum_parity_is_hidden_until_the_duty_is_confirmed():
    b = cm.build(settings(), NOW, mcx_blob(), intl_blob(), CFG, TS - 2)
    pl = item(b, "platinum")
    assert pl["mcx"] is None and pl["intl"][0]["usd"] == "1573.30"
    assert pl["parity"]["state"] == "hidden" and "confirmed" in pl["parity"]["reason"]
    confirmed = {**CFG, "duty": [{**d, "confirmed": True} if d["metal"] == "platinum" else d for d in DUTY]}
    p = item(cm.build(settings(), NOW, mcx_blob(), intl_blob(), confirmed, TS - 2), "platinum")["parity"]
    assert (p["state"], p["perGram"], p["withGst"], p["duty"]["total"], p["premiumPct"]) == ("ok", "5545.39", "5711.75", "15.4", None)


def test_the_duty_in_force_is_chosen_by_date_and_a_stale_check_hides_parity():
    assert cm.duty_for(CFG, "gold", date(2026, 5, 12))["bcd"] == "5" and cm.duty_for(CFG, "gold", date(2026, 5, 13))["bcd"] == "10"
    assert cm.duty_for(CFG, "gold", date(2024, 1, 1)) is None and cm.duty_for(CFG, "crude", date(2026, 10, 23)) is None
    old = {**CFG, "duty": [{**d, "checked": "2026-05-01"} for d in DUTY]}
    p = item(cm.build(settings(), NOW, mcx_blob(), intl_blob(), old, TS - 2), "gold")["parity"]
    assert p["state"] == "hidden" and "check" in p["reason"]
    edge = {**CFG, "duty": [{**d, "checked": (NOW.date() - timedelta(days=120)).isoformat()} for d in DUTY]}
    assert item(cm.build(settings(), NOW, mcx_blob(), intl_blob(), edge, TS - 2), "gold")["parity"]["state"] == "ok"
    assert item(cm.build(settings(), NOW, mcx_blob(), intl_blob(), {"hours": HOURS}, TS - 2), "gold")["parity"]["reason"] == "The customs duty rate is not set."


def test_no_keys_shows_mcx_alone_and_says_the_rest_is_not_connected():
    b = cm.build(settings(metals_dev_api_key="", metalprice_api_key=""), NOW, mcx_blob(), None, CFG, TS - 2)
    g = item(b, "gold")
    assert g["mcx"]["price"]["value"] == "14250.00" and g["mcx"]["state"] == "live"
    assert g["intl"][0]["state"] == "off" and g["intl"][0]["usd"] is None and "not connected" in g["intl"][0]["note"]
    assert g["parity"]["state"] == "hidden" and "not connected" in g["parity"]["reason"] and "perGram" not in g["parity"]
    assert "International price not connected." in g["notes"]
    assert b["fx"]["state"] == "off" and b["fx"]["usdinr"] is None and b["ratio"]["goldSilver"] is None
    assert b["sources"]["intl"]["connected"] is False and b["sources"]["mcx"]["label"] == "MCX futures price (via Dhan)"
    # no zeros anywhere: every price field is absent or a real number
    dumped = json.dumps(b)
    assert '"0.00"' not in dumped and '"usd": "0' not in dumped


def test_nothing_connected_and_nothing_yet_is_waiting_not_zero():
    b = cm.build(settings(dhan_client_id="", metals_dev_api_key="", metalprice_api_key=""), NOW, None, None, None, None)
    g = item(b, "gold")
    assert b["status"] == "waiting" and g["mcx"]["state"] == "off" and g["mcx"]["price"] is None and g["mcx"]["label"] == "Not connected"
    w = cm.build(settings(), NOW, None, None, CFG, None)
    assert item(w, "gold")["mcx"]["state"] == "none" and item(w, "gold")["mcx"]["note"] == "Waiting for the first MCX price." and item(w, "gold")["intl"][0]["state"] == "none"
    assert item(w, "gold")["parity"]["state"] == "hidden"


def test_only_metalprice_key_covers_precious_metals_and_energy_but_not_base_metals():
    b = cm.build(settings(metals_dev_api_key=""), NOW, mcx_blob(), intl_blob(), CFG, TS - 2)
    assert item(b, "gold")["intl"][0]["state"] == "fresh" and item(b, "crude")["intl"][0]["state"] == "fresh" and item(b, "copper")["intl"][0]["state"] == "fresh"   # held
    b2 = cm.build(settings(metals_dev_api_key=""), NOW, mcx_blob(), {"quotes": {"wti": q_("71.55", vendor="MetalpriceAPI", poll=600)}, "fx": None, "err": {}}, CFG, TS - 2)
    assert item(b2, "copper")["intl"][0]["state"] == "off" and item(b2, "crude")["intl"][0]["state"] == "fresh" and item(b2, "gold")["intl"][0]["state"] == "none"
    assert b2["sources"]["intl"]["metals"] == "MetalpriceAPI"


def test_live_badge_only_when_cleared_and_fresh():
    assert item(cm.build(settings(commodity_mcx_display_cleared=True), NOW, mcx_blob(), intl_blob(), CFG, TS - 2), "gold")["mcx"]["label"] == "Live"
    stale = mcx_blob(GOLD=reading(traded="2026-10-23T21:20:00+05:30"))
    m = item(cm.build(settings(commodity_mcx_display_cleared=True), NOW, stale, intl_blob(), CFG, TS - 2), "gold")["mcx"]
    assert m["state"] == "delayed" and m["label"] == "Delayed" and m["change"] is None and "hidden" in m["note"]


def test_delayed_closed_notrade_and_roll_states_of_the_mcx_block():
    d = item(cm.build(settings(), NOW, mcx_blob(), intl_blob(), CFG, TS - 300), "gold")                       # the worker has been silent for 5 minutes
    assert d["mcx"]["state"] == "delayed" and d["mcx"]["change"] is None and d["mcx"]["price"]["value"] == "14250.00"   # the figure stays, greyed by the page
    sat = at(2026, 10, 24, 12, 0)
    c = item(cm.build(settings(), sat, mcx_blob(), intl_blob(), CFG, sat.timestamp() - 2), "gold")["mcx"]
    assert c["state"] == "closed" and c["label"] == "Closed" and "last traded price" in c["note"] and c["change"] is not None
    nt = item(cm.build(settings(), NOW, mcx_blob(GOLD=reading(traded=None, prev=None)), intl_blob(), CFG, TS - 2), "gold")["mcx"]
    assert nt["state"] == "closed"                                                                            # 12:00-style rule: no trade today is a holiday
    rolled = item(cm.build(settings(), NOW, mcx_blob(GOLD=reading(rolledOn="2026-10-23")), intl_blob(), CFG, TS - 2), "gold")["mcx"]
    assert rolled["change"] is None and "contract changed" in rolled["note"]


def test_stale_and_unavailable_international_prices_and_the_fx_rule():
    old = intl_blob(quotes={**intl_blob()["quotes"], "gold": q_("4032.30", "4000", age=700)})
    g = item(cm.build(settings(), NOW, mcx_blob(), old, CFG, TS - 2), "gold")
    assert g["intl"][0]["state"] == "stale" and "11 min" in g["intl"][0]["note"] and g["parity"]["state"] == "ok"      # dimmed with its age, parity still shown
    dead = intl_blob(quotes={**intl_blob()["quotes"], "gold": q_("4032.30", "4000", age=4000)})
    g = item(cm.build(settings(), NOW, mcx_blob(), dead, CFG, TS - 2), "gold")
    assert g["intl"][0]["state"] == "unavailable" and g["intl"][0]["usd"] is None and g["parity"]["state"] == "hidden"
    bad_fx = intl_blob(fx=fx_(700))
    p = item(cm.build(settings(), NOW, mcx_blob(), bad_fx, CFG, TS - 2), "gold")["parity"]
    assert p["state"] == "hidden" and "USD/INR" in p["reason"]
    assert item(cm.build(settings(), NOW, mcx_blob(), bad_fx, CFG, TS - 2), "gold")["intl"][0]["usd"] == "4032.30"       # the rest of the card stays


def test_weekend_shows_fridays_global_prices_as_closed():
    sat = at(2026, 10, 24, 12, 0)
    fri = intl_blob(quotes={k: {**v, "ts": TS - 3600} for k, v in intl_blob()["quotes"].items()}, fx=fx_(3600))
    b = cm.build(settings(), sat, mcx_blob(), {**fri, "quotes": {k: {**v, "ts": TS - 3600} for k, v in fri["quotes"].items()}}, CFG, sat.timestamp() - 2)
    g = item(b, "gold")
    assert not b["market"]["global"]["open"] and g["intl"][0]["state"] == "closed" and "closed" in g["intl"][0]["note"].lower()
    assert g["parity"]["state"] == "ok" and g["intl"][0]["changePct"] == "0.81"


def test_negative_or_zero_previous_prices_give_no_percentage():
    b = cm.build(settings(), NOW, mcx_blob(), intl_blob(quotes={**intl_blob()["quotes"], "wti": q_("-5.5", "-37.6", vendor="MetalpriceAPI", poll=600)}), CFG, TS - 2)
    w = item(b, "crude")["intl"][0]
    assert w["usd"] == "-5.50" and w["changePct"] is None


# ================================================================================================================ the endpoint
async def test_endpoint_serves_redis_only_and_sets_cache_headers():
    app = FastAPI()
    app.include_router(cm.router)
    app.state.store = SimpleNamespace(redis=FakeRedis())
    app.state.settings = settings(metals_dev_api_key="", metalprice_api_key="")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/commodity-prices")                                    # nothing saved yet
        assert r.status_code == 200 and r.json()["status"] == "waiting" and r.headers["cache-control"].startswith("public, max-age=")
        await app.state.store.redis.set(cm.K_MCX, json.dumps(mcx_blob()))
        await app.state.store.redis.set(cm.K_CFG, json.dumps(CFG))
        await app.state.store.redis.set(cm.K_HB, str(datetime.now().timestamp()))
        j = (await c.get("/api/commodity-prices")).json()
    assert j["status"] == "ok" and j["sources"]["intl"]["connected"] is False
    assert all(isinstance(i["intl"], list) for i in j["items"])


# ================================================================================================================ the worker (database and Redis)
class FakeDhan:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.asked = answer or {}, fail, []

    async def quotes(self, ids):
        self.asked.append(list(ids))
        if self.fail:
            raise dhan.DhanError("/marketfeed/quote: HTTP 503")
        return {k: v for k, v in self.answer.items() if k in ids}


async def load_fixture_contracts(store):
    await dhan.save_commodity_contracts(store, [{"security_id": r["security_id"], "symbol": r["symbol"], "display_name": r["display_name"], "expiry": r["expiry"],
                                                  "tick_paise": 100, "upper": float(r["upper"]), "lower": float(r["lower"])} for r in contract_rows()], minimum=10)


async def test_save_contracts_refuses_a_short_list_and_keeps_the_stored_ones(store):
    await load_fixture_contracts(store)
    with pytest.raises(dhan.DhanError, match="incomplete"):
        await dhan.save_commodity_contracts(store, contract_rows()[:5])
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM dhan_commodity_contracts") == 50
        assert await conn.fetchval("SELECT expiry FROM dhan_commodity_contracts WHERE security_id = '495213'") == date(2026, 12, 4)


async def test_migration_seeds_the_duty_hours_and_unconfirmed_platinum(store):
    cfg = await cm.load_cfg(store)
    byk = {(d["metal"], d["from"]): d for d in cfg["duty"]}
    g = byk[("gold", "2026-05-13")]
    assert (g["bcd"], g["aidc"], g["gst"], g["confirmed"]) == ("10", "5", "3", True) and byk[("silver", "2026-05-13")]["aidc"] == "5"
    assert byk[("platinum", "2026-05-13")]["confirmed"] is False
    assert [(h["from"], h["close"], h["confirmed"]) for h in cfg["hours"]] == [("2026-03-09", "23:30", True), ("2026-11-02", "23:55", False)]


async def test_worker_pass_writes_redis_and_the_page_builds_from_it(store):
    await load_fixture_contracts(store)
    rows = contract_rows()
    ids = {c["display_name"]: c["security_id"] for c in rows}
    fake = FakeDhan({("MCX_COMM", ids["GOLD DEC FUT"]): raw_quote(142500, 880), ("MCX_COMM", ids["SILVER DEC FUT"]): raw_quote(196150, 1000),
                     ("MCX_COMM", ids["CRUDEOIL NOV FUT"]): raw_quote(9400, 100)})

    def handler(req: httpx.Request):
        return httpx.Response(200, text=json.dumps(dict(METALS_DEV, timestamps={"metal": "2026-10-23T16:12:00Z", "currency": "2026-10-23T16:11:00Z"}) if "metals.dev" in str(req.url) else METALPRICE))

    s = make_settings(metals_dev_api_key="k1", metalprice_api_key="k2", metals_dev_poll_seconds=60, metalprice_poll_seconds=600, dhan_client_id="c")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        w = cm.Worker(s, store, fake, http)
        rep = await w.tick(NOW)
        assert rep["mcx"] == 3 and rep["metals"] == 5 and rep["energy"] == 3 and rep["cfg"] is True
        assert (await w.tick(NOW + timedelta(seconds=5))) == {}                                  # nothing is due again after 5 seconds
        assert len((await w.tick(NOW + timedelta(seconds=11))).keys() & {"mcx"}) == 1             # MCX again after 10 seconds, vendors not yet
    asked = fake.asked[0]
    assert ("MCX_COMM", ids["GOLD DEC FUT"]) in asked and ("MCX_COMM", ids["GOLD FEB FUT"]) in asked and len(asked) == len(set(asked)) == 12   # six symbols, two contracts each
    assert all(seg == "MCX_COMM" for seg, _ in asked)
    raw = {k: json.loads(await store.redis.get(k)) for k in (cm.K_MCX, cm.K_INTL, cm.K_CFG)}
    assert raw[cm.K_MCX]["items"]["GOLD"]["name"] == "GOLD DEC FUT" and D(raw[cm.K_INTL]["quotes"]["gold"]["usd"]) == D("4032.30")
    assert raw[cm.K_INTL]["quotes"]["wti"]["vendor"] == "MetalpriceAPI" and raw[cm.K_INTL]["fx"]["vendor"] == "metals.dev"      # metals.dev owns metals and FX when both keys are set
    assert "gold" not in {k for k, v in raw[cm.K_INTL]["quotes"].items() if v["vendor"] == "MetalpriceAPI"}
    assert await store.redis.get(cm.K_HB)
    # the vendor time is Friday 16:12 UTC = 12:12 New York; build one minute later from what the worker saved
    when = datetime(2026, 10, 23, 21, 43, tzinfo=IST)
    body = cm.build(s, when, raw[cm.K_MCX], raw[cm.K_INTL], raw[cm.K_CFG], float(await store.redis.get(cm.K_HB)))
    g = item(body, "gold")
    assert g["mcx"]["price"]["value"] == "14250.00" and g["intl"][0]["usd"] == "4032.30" and g["intl"][0]["changePct"] is None    # first day seen: no change base yet, none invented
    assert g["parity"]["state"] == "ok" and abs(D(g["parity"]["usdinr"]) - 95) < D("0.0001") and g["parity"]["perGram"] in ("14163.33", "14163.34", "14163.32")


async def test_worker_survives_provider_failures_and_keeps_the_last_good_values(store):
    await load_fixture_contracts(store)
    rows = contract_rows()
    gold = next(c["security_id"] for c in rows if c["display_name"] == "GOLD DEC FUT")
    calls = {"n": 0}

    def handler(req: httpx.Request):
        calls["n"] += 1
        return httpx.Response(200, text=json.dumps(METALS_DEV)) if calls["n"] == 1 else httpx.Response(429)

    fake = FakeDhan({("MCX_COMM", gold): raw_quote(142500, 880)})
    s = make_settings(metals_dev_api_key="k1", metals_dev_poll_seconds=60, dhan_client_id="c")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        w = cm.Worker(s, store, fake, http)
        await w.tick(NOW)
        fake.fail = True
        rep = await w.tick(NOW + timedelta(seconds=70))
    assert "mcx" not in rep and "metals" not in rep
    j = json.loads(await store.redis.get(cm.K_INTL))
    assert D(j["quotes"]["gold"]["usd"]) == D("4032.30") and "429" in j["err"]["metals.dev"]                  # the last good price stays; the failure is recorded
    m = json.loads(await store.redis.get(cm.K_MCX))
    assert m["items"]["GOLD"]["price"] == "142500" and "503" in m["err"]
    assert "k1" not in json.dumps(j)


async def test_run_without_any_source_does_nothing_and_says_so(store):
    out = await cm.run(make_settings(dhan_client_id="", metals_dev_api_key="", metalprice_api_key=""), store)
    assert out["status"] == "ok" and out["dhan"] is False and out["metals.dev"] is False and out["metalprice"] is False
