"""Live index levels from Dhan (finlit/indices.py), FinEdge as the fallback. The instrument rows are Dhan's real public file (its 190 index
rows and a few equity and derivative rows, tests/fixtures/dhan/instruments_indices.csv); quote answers follow Dhan's published v2 shape.
No live account was used."""
import asyncio
import csv
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from finlit import background, dhan, indices
from finlit.config import Settings
from test_indices import FIX, make
from test_integration import make_settings, store  # noqa: F401  (fixture)

CSV = Path(__file__).parent / "fixtures" / "dhan" / "instruments_indices.csv"
IST = indices.IST
FEED = {x["code"]: x for x in indices.shape_feed(json.loads((FIX / "index_daily_feed.json").read_text()))["items"]}


def csv_lines():
    return CSV.read_text(encoding="utf-8").splitlines()


def index_rows():
    out = []
    dhan.parse_instruments(csv_lines(), out)
    return out


def ltt(t: datetime) -> str:
    return t.astimezone(IST).strftime("%d/%m/%Y %H:%M:%S")


def raw(level, change, at, high=None, low=None):
    """One IDX_I entry as /marketfeed/quote sends it."""
    return {"last_price": level, "net_change": change, "volume": 0, "last_trade_time": ltt(at) if at else "01/01/1980 00:00:00",
            "ohlc": {"open": round(level - change, 2), "close": round(level - change, 2), "high": high or level, "low": low or round(level - change, 2)}}


class FakeDhan:
    configured = True

    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.asked = answer, fail, []

    async def quotes(self, ids):
        self.asked.append(list(ids))
        if self.fail:
            raise dhan.DhanError("/marketfeed/quote: HTTP 503")
        return self.answer(ids) if callable(self.answer) else (self.answer or {})

    async def aclose(self):
        pass


def everything_up_1pct(now):
    """Every asked index 1% above FinEdge's close, updated a minute ago; RELIANCE traded a minute ago."""
    def answer(ids):
        by_id = {sid: code for code, (sid, _, _) in indices.DHAN_INDEX.items()}
        out = {}
        for seg, sid in ids:
            if seg == "NSE_EQ":
                out[(seg, sid)] = {"last_price": 1420.5, "net_change": 20.5, "last_trade_time": ltt(now - timedelta(minutes=1))}
            else:
                base = FEED[by_id[sid]]["close"]
                out[(seg, sid)] = raw(round(base * 1.01, 2), round(base * 0.01, 2), now - timedelta(minutes=1))
        return out
    return answer


class Clock:
    """Pins indices.datetime.now() (and so session_open and the reading times) to one moment."""
    def __init__(self, monkeypatch, at):
        self.at = at
        clock = self

        class Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.at.astimezone(tz) if tz else clock.at.replace(tzinfo=None)
        monkeypatch.setattr(indices, "datetime", Fixed)


def live_app(fake, probe="2885"):
    app, c = make(plan=None)
    app.state.index_dhan = fake
    ids, off = indices.confirm(index_rows())
    assert not off
    app.state.store.redis.d[indices.DHAN_IDS_KEY] = json.dumps({"ids": ids, "probe": probe})
    return app, c


async def settle():
    while background._running:
        await asyncio.gather(*list(background._running), return_exceptions=True)


# ------------------------------------------------------------------ instrument file and mapping

def test_index_rows_are_kept_apart_from_equities():
    idx: list = []
    eq = dhan.parse_instruments(csv_lines(), idx)
    assert {(r["exch"], r["security_id"]) for r in eq} == {("NSE", "2885"), ("NSE", "1333"), ("BSE", "500325"), ("BSE", "500180")}   # no index row
    assert all(r["inst_type"] == "ES" for r in eq) and next(r for r in eq if r["security_id"] == "2885")["fno"]
    assert len(idx) == 190 and sum(r["exch"] == "NSE" for r in idx) == 119 and sum(r["exch"] == "BSE" for r in idx) == 71
    assert dhan.parse_instruments(csv_lines()) == eq                                                     # unchanged for callers that ask for equities only
    nifty = [r for r in idx if r["symbol"] == "NIFTY"]
    assert nifty == [{"exch": "NSE", "security_id": "13", "symbol": "NIFTY", "name": "Nifty 50"}]
    # NIFTY futures name 26000 as their underlying: that is not the id the quote API knows the index by under IDX_I
    futs = [r for r in csv.DictReader(csv_lines()) if r["INSTRUMENT"] == "FUTIDX" and r["UNDERLYING_SYMBOL"] == "NIFTY"]
    assert futs and futs[0]["UNDERLYING_SECURITY_ID"] == "26000" and not any(r["security_id"] == "26000" for r in idx)


def test_mapping_is_exact_against_dhans_file_and_the_names_the_site_shows():
    rows = {r["SECURITY_ID"]: r for r in csv.DictReader(csv_lines()) if r["SEGMENT"] == "I"}
    sids = [sid for sid, _, _ in indices.DHAN_INDEX.values()]
    assert len(sids) == len(set(sids)) == 170                                                           # no Dhan index used twice
    for code, (sid, sym, name) in indices.DHAN_INDEX.items():
        r = rows[sid]
        assert (r["EXCH_ID"], r["SYMBOL_NAME"], r["INSTRUMENT"]) == (indices.exchange_of(code), sym, "INDEX"), code
        assert FEED[code]["name"] == name, code                                                           # the site's own name, exactly
    assert set(indices.KEY) <= set(indices.DHAN_INDEX)                                                    # the whole strip
    want = {"NIF50": ("13", "Nifty 50"), "NIFBAN": ("25", "Nifty Bank"), "SNSXSENSEX": ("51", "BSE SENSEX"), "NIFNEX50": ("38", "Nifty Next 50"),
            "NIFMID100": ("37", "NIFTY MIDCAP 100"), "NIFSMA100": ("5", "NIFTY Smallcap 100"), "NIFIT": ("29", "Nifty IT"), "INDVIX": ("21", "INDIA VIX"),
            "NIFFINSER": ("27", "Nifty Financial Services"), "NIFMIDSEL2": ("442", "NIFTY MIDCAP SELECT"), "SNSXBANKEX": ("69", "BSE BANKEX"),
            "NIF500": ("19", "Nifty 500"), "NIFMID150": ("1", "Nifty Midcap 150")}
    assert {k: (indices.DHAN_INDEX[k][0], indices.DHAN_INDEX[k][2]) for k in want} == want
    # names that only look alike are not matched: FinEdge's stale second SENSEX, and BSE rows Dhan names differently
    for code in ("SNSXBSE30", "SNSXCOMDTY", "SNSXFINSER", "SNSXCONDIS", "SNSXSMLCAP", "SNSXMIDCAP", "NIFHEA2", "NIFLOWVOL50", "NIF50ARB"):
        assert code in FEED and code not in indices.DHAN_INDEX, code


def test_mapping_is_used_only_while_the_stored_file_confirms_it():
    rows = index_rows()
    ok, off = indices.confirm(rows)
    assert len(ok) == 170 and off == [] and ok["NIF50"] == "13"
    moved = [dict(r, symbol="NIFTY NEW") if r["security_id"] == "13" else r for r in rows]             # Dhan gave id 13 to something else
    ok, off = indices.confirm(moved)
    assert "NIF50" not in ok and off == ["NIF50"]
    twice = rows + [{"exch": "BSE", "security_id": "25", "symbol": "X", "name": None}]                   # an id no longer unique under IDX_I
    assert "NIFBAN" not in indices.confirm(twice)[0]
    assert indices.confirm([]) == ({}, list(indices.DHAN_INDEX))


def test_session_is_0915_to_1530_on_weekdays():
    d = lambda h, m, day=23: datetime(2026, 10, day, h, m, tzinfo=IST)   # noqa: E731   23 Oct 2026 is a Friday
    assert not indices.session_open(d(9, 14)) and indices.session_open(d(9, 15)) and indices.session_open(d(15, 30))
    assert not indices.session_open(d(15, 31)) and not indices.session_open(d(11, 0, 24))                # Saturday
    assert indices.session_open(datetime(2026, 10, 23, 5, 0, tzinfo=indices.ZoneInfo("UTC")))            # 10:30 in India


# ------------------------------------------------------------------ the checks on each reading

def test_readings_take_the_move_from_previous_close_and_refuse_stale_or_far_levels(caplog):
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    feed = {"items": [FEED["NIF50"], FEED["NIFBAN"], FEED["INDVIX"], FEED["SNSXSENSEX"], FEED["NIFIT"]]}
    ids = {k: indices.DHAN_INDEX[k][0] for k in ("NIF50", "NIFBAN", "INDVIX", "SNSXSENSEX", "NIFIT", "NIFMID100")}
    probe_today = {"last_price": 1420.5, "net_change": 1, "last_trade_time": ltt(now)}
    got = {("IDX_I", "13"): raw(23117.85, 228.9, now - timedelta(seconds=5), high=23150.1, low=22901.4),
           ("IDX_I", "25"): raw(55488.1 * 1.25, 100, now),                                                # 25% from what FinEdge holds
           ("IDX_I", "21"): raw(15.12, 0.35, None),                                                       # no update time: RELIANCE says today
           ("IDX_I", "51"): raw(74100.0, 247.1, now - timedelta(days=1)),                                 # yesterday's: a stuck feed
           ("IDX_I", "29"): {"last_price": 0, "net_change": 0},                                           # no level
           ("NSE_EQ", "2885"): probe_today}
    with caplog.at_level(logging.INFO, logger="finlit.indices"):
        out = indices.readings(got, ids, "2885", feed, None, now)
    assert set(out) == {"NIF50", "INDVIX"}
    n = out["NIF50"]
    assert n["close"] == 23117.85 and n["points"] == 228.9 and n["changePct"] == round(228.9 / round(23117.85 - 228.9, 2) * 100, 2)
    assert (n["high"], n["low"], n["date"], n["time"]) == (23150.1, 22901.4, "2026-10-23", "2026-10-23T10:59:55+05:30")
    assert out["INDVIX"]["time"] == "2026-10-23T11:00:00+05:30"                                         # as of when Dhan was asked
    assert "more than 10% from the 55488.1 held" in caplog.text and "NIFBAN" in caplog.text
    assert "not today 1 (SNSXSENSEX)" in caplog.text and "no level 1 (NIFIT)" in caplog.text and "name 1 (NIFMID100)" in caplog.text

    probe_old = {**probe_today, "last_trade_time": ltt(now - timedelta(days=3))}                       # a weekday holiday: no trade today
    assert "INDVIX" not in indices.readings({**got, ("NSE_EQ", "2885"): probe_old}, ids, "2885", feed, None, now)
    assert "INDVIX" not in indices.readings(got, ids, None, feed, None, now)                              # no way to tell: refused

    # the last level held is today's earlier Dhan reading when there is one: a VIX jump against yesterday's FinEdge close is not refused
    jump = {("IDX_I", "21"): raw(17.4, 2.63, now)}
    assert "INDVIX" not in indices.readings(jump, {"INDVIX": "21"}, None, feed, None, now)
    prev = {"t": "2026-10-23T10:59:00+05:30", "q": {"INDVIX": {"close": 17.1}}}
    assert indices.readings(jump, {"INDVIX": "21"}, None, feed, prev, now)["INDVIX"]["close"] == 17.4
    old = {"t": "2026-10-22T15:29:00+05:30", "q": {"INDVIX": {"close": 17.1}}}                            # yesterday's reading is not today's
    assert "INDVIX" not in indices.readings(jump, {"INDVIX": "21"}, None, feed, old, now)

    renamed = {"items": [dict(FEED["NIF50"], name="Nifty 50 Equal Weight")]}                            # FinEdge reused the code: not followed
    assert indices.readings(got, {"NIF50": "13"}, "2885", renamed, None, now) == {}


# ------------------------------------------------------------------ the endpoint

async def test_one_batched_call_serves_every_visitor_and_dhan_levels_replace_finedges(monkeypatch):
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    Clock(monkeypatch, now)
    fake = FakeDhan(everything_up_1pct(now))
    app, c = live_app(fake)
    first = (await c.get("/api/indices")).json()                                    # nothing saved yet: FinEdge at once, Dhan asked behind it
    assert {x["source"] for x in first["items"]} == {"finedge"} and first["live"] is False and first["marketOpen"] is True
    await settle()
    assert len(fake.asked) == 1
    asked = fake.asked[0]
    assert len(asked) == 171 and {s for s, _ in asked} == {"IDX_I", "NSE_EQ"} and ("NSE_EQ", "2885") in asked and ("IDX_I", "13") in asked
    assert len({sid for s, sid in asked if s == "IDX_I"}) == 170

    bodies = [r.json() for r in await asyncio.gather(*(c.get("/api/indices") for _ in range(25)))]       # many visitors, one minute
    await settle()
    assert len(fake.asked) == 1 and all(b == bodies[0] for b in bodies)
    b = bodies[0]
    items = {x["code"]: x for x in b["items"]}
    nifty = items["NIF50"]
    want = round(FEED["NIF50"]["close"] * 1.01, 2)
    assert nifty["source"] == "dhan" and nifty["close"] == want and nifty["points"] == round(FEED["NIF50"]["close"] * 0.01, 2)
    assert nifty["date"] == "2026-10-23" and nifty["time"] == "2026-10-23T10:59:00+05:30"
    assert nifty["valDate"] == FEED["NIF50"]["date"] and nifty["pe"] == FEED["NIF50"]["pe"] and nifty["name"] == "Nifty 50"   # P/E stays FinEdge's, dated
    assert items["NIF50ARB"]["source"] == "finedge" and items["NIF50ARB"]["close"] == FEED["NIF50ARB"]["close"]                # not mapped: FinEdge
    assert sum(x["source"] == "dhan" for x in b["items"]) == 170 and b["live"] is True and b["asOf"] == "2026-10-23"
    assert b["key"] == indices.KEY and [x["code"] for x in b["items"][:7]] == indices.KEY

    Clock(monkeypatch, now + timedelta(seconds=90))                                 # past the refresh interval: one more call, behind the scenes
    app.state.store.redis.d[indices.DHAN_KEY] = json.dumps({**json.loads(app.state.store.redis.d[indices.DHAN_KEY]), "t": time.time() - 61})
    await c.get("/api/indices")
    await settle()
    assert len(fake.asked) == 2


async def test_dhan_down_or_failing_means_finedge_for_every_index(monkeypatch, caplog):
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    Clock(monkeypatch, now)
    fake = FakeDhan(fail=True)
    app, c = live_app(fake)
    with caplog.at_level(logging.WARNING, logger="finlit.indices"):
        await c.get("/api/indices")
        await settle()
    b = (await c.get("/api/indices")).json()
    assert len(fake.asked) == 1 and {x["source"] for x in b["items"]} == {"finedge"} and b["live"] is False
    assert {x["code"]: x["close"] for x in b["items"]} == {k: v["close"] for k, v in FEED.items()} and "Dhan index levels unavailable" in caplog.text
    assert json.loads(app.state.store.redis.d[indices.DHAN_KEY])["v"]["error"]

    fake.fail, fake.answer = False, everything_up_1pct(now)                         # Dhan back, but its saved reading goes stale: not shown
    app.state.store.redis.d[indices.DHAN_KEY] = json.dumps({"t": time.time() - 61, "v": {"t": now.isoformat(), "q": {}}})
    await c.get("/api/indices")
    await settle()
    assert (await c.get("/api/indices")).json()["live"] is True
    Clock(monkeypatch, now + timedelta(minutes=4))
    app.state.index_dhan = FakeDhan(fail=True)
    b = (await c.get("/api/indices")).json()                                        # the 11:00 reading is four minutes old at 11:04
    assert {x["source"] for x in b["items"]} == {"finedge"}


async def test_an_implausible_index_keeps_finedge_and_the_rest_stay_live(monkeypatch, caplog):
    now = datetime(2026, 10, 23, 11, 0, tzinfo=IST)
    Clock(monkeypatch, now)
    base = everything_up_1pct(now)

    def answer(ids):
        out = base(ids)
        out[("IDX_I", "51")] = raw(FEED["SNSXSENSEX"]["close"] * 0.85, -100, now)           # SENSEX 15% below the level held
        return out
    app, c = live_app(FakeDhan(answer))
    with caplog.at_level(logging.WARNING, logger="finlit.indices"):
        await c.get("/api/indices")
        await settle()
    items = {x["code"]: x for x in (await c.get("/api/indices")).json()["items"]}
    assert items["SNSXSENSEX"]["source"] == "finedge" and items["SNSXSENSEX"]["close"] == FEED["SNSXSENSEX"]["close"]
    assert items["NIF50"]["source"] == "dhan" and "SNSXSENSEX" in caplog.text and "more than 10%" in caplog.text


async def test_outside_market_hours_no_dhan_call_and_finedge_closes(monkeypatch):
    fake = FakeDhan(everything_up_1pct(datetime(2026, 10, 23, 15, 29, tzinfo=IST)))
    for at in (datetime(2026, 10, 23, 16, 0, tzinfo=IST), datetime(2026, 10, 23, 9, 10, tzinfo=IST), datetime(2026, 10, 24, 11, 0, tzinfo=IST)):
        Clock(monkeypatch, at)
        app, c = live_app(fake)
        app.state.store.redis.d[indices.DHAN_KEY] = json.dumps({"t": time.time(), "v": {"t": "2026-10-23T15:29:00+05:30", "q": {
            "NIF50": {"close": 1.0, "points": 0, "changePct": 0, "open": None, "high": None, "low": None, "time": "2026-10-23T15:29:00+05:30", "date": "2026-10-23"}}}})
        b = (await c.get("/api/indices")).json()
        await settle()
        assert fake.asked == [] and b["marketOpen"] is False and b["live"] is False
        assert {x["source"] for x in b["items"]} == {"finedge"} and next(x for x in b["items"] if x["code"] == "NIF50")["close"] == FEED["NIF50"]["close"]


async def test_a_weekday_holiday_stops_the_calls_for_the_day(monkeypatch):
    now = datetime(2026, 10, 21, 9, 45, tzinfo=IST)                                  # a Wednesday the exchange is shut
    Clock(monkeypatch, now)
    yesterday = now - timedelta(days=1, hours=3)
    fake = FakeDhan(lambda ids: {(s, i): ({"last_price": 1400, "net_change": 3, "last_trade_time": ltt(yesterday)} if s == "NSE_EQ"
                                          else raw(FEED["NIF50"]["close"], 0, None)) for s, i in ids})
    app, c = live_app(fake)
    await c.get("/api/indices")
    await settle()
    saved = json.loads(app.state.store.redis.d[indices.DHAN_KEY])
    assert saved["v"]["closed"] == "2026-10-21" and saved["v"]["q"] == {}
    app.state.store.redis.d[indices.DHAN_KEY] = json.dumps({**saved, "t": time.time() - 61})
    b = (await c.get("/api/indices")).json()
    await settle()
    assert len(fake.asked) == 1 and {x["source"] for x in b["items"]} == {"finedge"}


async def test_without_dhan_settings_the_feed_is_finedges_alone():
    app, c = make(plan=None)                                                        # no DHAN_CLIENT_ID: never asked, nothing to close
    b = (await c.get("/api/indices")).json()
    assert {x["source"] for x in b["items"]} == {"finedge"} and b["live"] is False and getattr(app.state, "index_dhan", None) is None


# ------------------------------------------------------------------ storage, the daily load, and the account-wide pace

async def test_index_rows_are_stored_apart_and_confirm_the_mapping(store, monkeypatch):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.execute("DELETE FROM dhan_indices")
    idx = index_rows()

    async def fetch(client=None, indices=None):
        indices.extend(idx)
        return [{"exch": "NSE", "security_id": f"9{i:05d}", "symbol": f"S{i}", "isin": None, "name": None, "series": "EQ", "asm_gsm": "N", "asm_gsm_cat": None,
                 "mtf_leverage": None, "fno": False, "lot_size": None, "inst_type": "ES", "exch_name": None} for i in range(5199)] + [
                {"exch": "NSE", "security_id": "2885", "symbol": "RELIANCE", "isin": "INE002A01018", "name": "Reliance Industries", "series": "EQ", "asm_gsm": "N",
                 "asm_gsm_cat": None, "mtf_leverage": None, "fno": True, "lot_size": 500, "inst_type": "ES", "exch_name": None}]
    monkeypatch.setattr(dhan, "fetch_instruments", fetch)
    await store.redis.set(indices.DHAN_IDS_KEY, "stale")
    from finlit import worker
    assert await worker.main(["refresh-instruments"], settings=make_settings()) == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM dhan_indices") == 190
        assert await conn.fetchval("SELECT count(*) FROM dhan_instruments WHERE security_id = ANY($1::text[])", [r["security_id"] for r in idx if r["exch"] == "BSE"]) == 0
        assert await conn.fetchval("SELECT count(*) FROM dhan_instruments WHERE inst_type = 'INDEX' OR symbol IN ('NIFTY', 'SENSEX')") == 0
    assert await store.redis.get(indices.DHAN_IDS_KEY) is None                      # the strip re-checks its mapping against the new file

    app = type("A", (), {})()
    app.state = type("S", (), {"store": store})()
    m = await indices._dhan_ids(app)
    assert len(m["ids"]) == 170 and m["probe"] == "2885" and json.loads(await store.redis.get(indices.DHAN_IDS_KEY)) == m
    with pytest.raises(dhan.DhanError):
        await dhan.save_indices(store, idx[:10])                                    # a short list keeps what is stored
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM dhan_indices") == 190
    await store.redis.delete(indices.DHAN_IDS_KEY)


async def test_quote_calls_keep_one_a_second_across_processes(store):  # noqa: F811
    seen = []

    def h(req):
        seen.append(time.monotonic())
        return httpx.Response(200, json={"data": {"IDX_I": {"13": {"last_price": 23000.5}}}})
    await store.redis.delete(dhan.PACE_KEY)
    s = Settings(dhan_client_id="1000000001", dhan_access_token="PASTED")
    a = dhan.DhanClient(s, store.redis, http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    b = dhan.DhanClient(s, store.redis, http=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    got = await asyncio.gather(a.quotes([("IDX_I", "13")]), b.quotes([("IDX_I", "13")]), a.ltp({"IDX_I": [13]}))
    assert got[0] == {("IDX_I", "13"): {"last_price": 23000.5}} and len(seen) == 3
    seen.sort()
    assert all(y - x >= 1.0 for x, y in zip(seen, seen[1:]))                        # two clients (two processes), one pace
    await a.aclose(); await b.aclose()
