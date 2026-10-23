"""Intraday charts (finlit/intraday.py and DhanClient.intraday). Dhan is mocked from its published v2 documentation; no live account was used."""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from finlit import dhan, intraday
from finlit.config import Settings
from finlit.api import create_app
from test_auth import signed_in
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)

IST = dhan.IST
HOLIDAY = date(2026, 10, 21)            # a weekday with no session in the fake exchange calendar


def at(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=IST)


def mock_client(handler):
    s = Settings(dhan_client_id="1000000001", dhan_access_token="T")
    return dhan.DhanClient(s, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


# ------------------------------------------------------------------ the client method

async def test_intraday_reads_epoch_seconds_as_indian_time_oldest_first():
    seen = []
    # From Dhan's own sample: 1328845020 is the 09:07 pre-open candle of 10 Feb 2012, 1328845500 the 09:15 one. Sent out of order on purpose.
    body = {"open": [3757.85, 3750], "high": [3757.9, 3750], "low": [3746.1, 3750], "close": [3751.25, 3750], "volume": [53629, 166],
            "timestamp": [1328845500, 1328845020], "open_interest": [0, 0]}

    def h(req):
        seen.append(json.loads(req.content))
        assert req.url.path == "/v2/charts/intraday"
        return httpx.Response(200, json=body)
    async with mock_client(h) as c:
        got = await c.intraday("1333", "NSE_EQ", 1, datetime(2012, 2, 10, 9, 0), datetime(2012, 2, 10, 3, 50, tzinfo=timezone.utc))
    assert seen == [{"securityId": "1333", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "interval": 1, "oi": False,
                     "fromDate": "2012-02-10 09:00:00", "toDate": "2012-02-10 09:20:00"}]         # naive = Indian time; UTC converted
    assert [g["at"].isoformat() for g in got] == ["2012-02-10T09:07:00+05:30", "2012-02-10T09:15:00+05:30"]
    assert got[0]["close"] == 3750 and got[0]["volume"] == 166 and got[1]["open"] == 3757.85 and got[1]["volume"] == 53629
    assert got[0]["at"].utcoffset() == timedelta(hours=5, minutes=30)


async def test_intraday_refuses_more_than_90_days_without_calling():
    calls = []

    def h(req):
        calls.append(req)
        return httpx.Response(200, json={"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": []})
    async with mock_client(h) as c:
        with pytest.raises(dhan.DhanError, match="90 days"):
            await c.intraday("2885", "NSE_EQ", 60, datetime(2026, 1, 1), datetime(2026, 4, 1, 0, 0, 1))
        with pytest.raises(dhan.DhanError, match="interval"):
            await c.intraday("2885", "NSE_EQ", 30, datetime(2026, 1, 1), datetime(2026, 1, 2))
        with pytest.raises(dhan.DhanError):
            await c.intraday("2885", "NSE_EQ", 1, datetime(2026, 1, 2), datetime(2026, 1, 1))
        assert calls == []
        assert await c.intraday("2885", "NSE_EQ", 60, datetime(2026, 1, 1), datetime(2026, 4, 1)) == []      # exactly 90 days is allowed
    assert len(calls) == 1


async def test_intraday_unequal_arrays_are_no_data_and_bad_candles_are_dropped():
    body = {"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [1, 2], "volume": [5, 5, 5], "timestamp": [1, 61, 121]}

    def h(req):
        return httpx.Response(200, json=body)
    async with mock_client(h) as c:
        assert await c.intraday("2885", "NSE_EQ", 1, datetime(2026, 1, 1), datetime(2026, 1, 2)) == []
        body.update(close=[1, None, 0], timestamp=[1761191100, 1761191160, 1761191220])
        got = await c.intraday("2885", "NSE_EQ", 1, datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert len(got) == 1 and got[0]["close"] == 1                                                     # a missing or zero price is never drawn


# ------------------------------------------------------------------ clock rules

def test_cache_lifetime_follows_the_market_clock():
    assert intraday.ttl(at(2026, 10, 23, 11, 0)) == 60                                     # session in progress
    assert intraday.ttl(at(2026, 10, 23, 9, 5)) == 60                                      # pre-open auction
    assert intraday.ttl(at(2026, 10, 23, 15, 50)) == 60                                    # closing session
    assert intraday.ttl(at(2026, 10, 23, 16, 0)) == (at(2026, 10, 26, 9, 0) - at(2026, 10, 23, 16, 0)).total_seconds()   # Friday close: Monday
    assert intraday.ttl(at(2026, 10, 24, 11, 0)) == (at(2026, 10, 26, 9, 0) - at(2026, 10, 24, 11, 0)).total_seconds()   # Saturday
    assert intraday.ttl(at(2026, 10, 22, 7, 0)) == 2 * 3600                                # before the open: until 09:00
    assert intraday.ttl(at(2026, 10, 22, 8, 59, 30)) == 60                                 # never less than a minute
    assert intraday.ttl(datetime(2026, 10, 23, 5, 30, tzinfo=timezone.utc)) == 60          # 11:00 IST given in UTC
    assert [intraday.phase(t) for t in (at(2026, 10, 23, 9, 14), at(2026, 10, 23, 9, 15), at(2026, 10, 23, 15, 29), at(2026, 10, 23, 15, 30),
                                        at(2026, 10, 24, 11, 0), at(2026, 10, 23, 8, 0))] == ["pre_open", "open", "open", "closed", "closed", "closed"]


async def test_dhan_calls_are_paced_and_capped_across_processes(store, monkeypatch):  # noqa: F811
    r = store.redis
    assert [await intraday.slot(r, now=1000.0) for _ in range(3)] == [None, None, "busy"]      # two a second for these charts
    assert await intraday.slot(r, now=1001.0) is None
    monkeypatch.setattr(intraday, "DAILY_CAP", 4)
    assert await intraday.slot(r, now=1002.0) is None and await intraday.slot(r, now=1003.0) == "budget"


# ------------------------------------------------------------------ the endpoint

class Exchange:
    """A fake Dhan: complete candles of every weekday session (09:15 to 15:30) inside the asked window, except HOLIDAY."""

    def __init__(self):
        self.calls, self.empty, self.fail, self.delay = [], False, False, 0.0

    async def __call__(self, req):
        if self.delay:
            await asyncio.sleep(self.delay)
        b = json.loads(req.content)
        self.calls.append(b)
        if self.fail:
            return httpx.Response(400, json={"errorCode": "DH-905"})
        frm = datetime.strptime(b["fromDate"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        to = datetime.strptime(b["toDate"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        step = timedelta(minutes=int(b["interval"]))
        ts, cl = [], []
        d = frm.date()
        while d <= to.date() and not self.empty:
            if d.weekday() < 5 and d != HOLIDAY:
                t = datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
                end = t.replace(hour=15, minute=30)
                while t < end and min(t + step, end) <= to:
                    if t >= frm:
                        ts.append(int(t.timestamp()))
                        cl.append(round(1400 + d.day + (t.hour * 60 + t.minute) / 100, 2))
                    t += step
            d += timedelta(days=1)
        return httpx.Response(200, json={"open": cl, "high": [c + 1 for c in cl], "low": [c - 1 for c in cl], "close": cl,
                                         "volume": [1000] * len(cl), "timestamp": ts})


@pytest.fixture
async def site(ingested, monkeypatch):  # noqa: F811
    async with ingested.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '2885', 'RELIANCE', 'EQ')")
        other = await conn.fetchval("SELECT symbol FROM companies WHERE symbol <> 'RELIANCE' ORDER BY symbol LIMIT 1")
    ex = Exchange()
    real = intraday.DhanClient
    monkeypatch.setattr(intraday, "DhanClient", lambda s, r=None: real(s, r, http=httpx.AsyncClient(transport=httpx.MockTransport(ex))))
    clock = {"now": at(2026, 10, 23, 11, 0, 30)}
    monkeypatch.setattr(intraday, "_now", lambda: clock["now"])
    app = create_app(make_settings(dhan_client_id="1000000001", dhan_access_token="T", showcase_symbols=[]), store=ingested)
    async with app.router.lifespan_context(app):
        yield app, ex, clock, other


async def test_a_session_in_progress_is_one_dhan_call_for_many_visitors(site):
    app, ex, clock, _ = site
    c = await signed_in(app, "a@example.com")
    try:
        ex.delay = 0.2                                                              # Dhan takes a moment: the other requests arrive meanwhile
        got = await asyncio.gather(*[c.get("/api/stocks/RELIANCE/intraday?range=1D") for _ in range(25)])
        assert {r.status_code for r in got} == {200}
        assert len(ex.calls) == 1                                                   # the lock: 25 concurrent misses, one call
        assert ex.calls[0]["fromDate"] == "2026-10-13 00:00:00" and ex.calls[0]["toDate"] == "2026-10-23 11:00:30" and ex.calls[0]["interval"] == 1
        b = got[0].json()
        assert b["source"] == "Dhan" and b["asOf"] == "2026-10-23T11:00:30+05:30" and b["session"] == "2026-10-23" == b["today"]
        assert b["phase"] == "open" and b["sessions"] == ["2026-10-23"] and b["exchange"] == "NSE" and b["interval"] == 1
        t = b["series"]["t"]
        assert t[0] == "2026-10-23T09:15:00+05:30" and t[-1] == "2026-10-23T10:59:00+05:30" and len(t) == 105 == len(b["series"]["c"])
        assert b["lastBarAt"] == t[-1]
        for _ in range(5):
            assert (await c.get("/api/stocks/reliance/intraday?range=1d")).status_code == 200
        assert len(ex.calls) == 1                                                   # still the cached copy
        assert 0 < await app.state.store.redis.ttl("intra:RELIANCE:1D") <= 60        # a minute while the market is open
        r = await c.get("/api/stocks/RELIANCE/intraday?range=1D")
        assert (await c.get("/api/stocks/RELIANCE/intraday?range=1D", headers={"If-None-Match": r.headers["etag"]})).status_code == 304
        assert r.headers["cache-control"] == "private, no-cache" and "Cookie" in r.headers["vary"]
    finally:
        await c.aclose()


async def test_after_the_close_and_on_weekends_1d_is_the_last_session_kept_until_the_next(site):
    app, ex, clock, _ = site
    clock["now"] = at(2026, 10, 24, 11, 0)                                            # Saturday
    c = await signed_in(app, "a@example.com")
    try:
        b = (await c.get("/api/stocks/RELIANCE/intraday?range=1D")).json()
        assert b["session"] == "2026-10-23" and b["today"] == "2026-10-24" and b["phase"] == "closed"
        assert b["series"]["t"][0] == "2026-10-23T09:15:00+05:30" and b["series"]["t"][-1] == "2026-10-23T15:29:00+05:30" and len(b["series"]["t"]) == 375
        left = await app.state.store.redis.ttl("intra:RELIANCE:1D")
        assert abs(left - (at(2026, 10, 26, 9, 0) - clock["now"]).total_seconds()) < 5   # kept until Monday's pre-open
        await app.state.store.redis.delete("intra:RELIANCE:1D")
        clock["now"] = at(2026, 10, 21, 10, 0)                                        # a weekday holiday, in market hours
        b = (await c.get("/api/stocks/RELIANCE/intraday?range=1D")).json()
        assert b["session"] == "2026-10-20" and b["today"] == "2026-10-21" and b["phase"] == "open"
        await app.state.store.redis.delete("intra:RELIANCE:1D")
        clock["now"] = at(2026, 10, 26, 8, 30)                                        # Monday before the pre-open
        b = (await c.get("/api/stocks/RELIANCE/intraday?range=1D")).json()
        assert b["session"] == "2026-10-23" and b["phase"] == "closed"
    finally:
        await c.aclose()


async def test_5d_and_1m_cut_whole_sessions_at_their_intervals(site):
    app, ex, clock, _ = site
    clock["now"] = at(2026, 10, 24, 11, 0)
    c = await signed_in(app, "s@example.com", plan="silver")
    try:
        b = (await c.get("/api/stocks/RELIANCE/intraday?range=5D")).json()
        assert b["interval"] == 5 and b["sessions"] == ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-22", "2026-10-23"]   # weekend and holiday skipped
        assert len(b["series"]["t"]) == 5 * 75 and b["series"]["t"][0] == "2026-10-16T09:15:00+05:30"
        b = (await c.get("/api/stocks/RELIANCE/intraday?range=1M")).json()
        assert b["interval"] == 60 and b["sessions"][0] == "2026-09-22" and b["sessions"][-1] == "2026-10-23"        # 31 days back, as the daily 1M
        assert b["series"]["t"][:2] == ["2026-09-22T09:15:00+05:30", "2026-09-22T10:15:00+05:30"]
        assert sum(1 for t in b["series"]["t"] if t.startswith("2026-10-23")) == 7                                       # 09:15 ... 15:15
        assert ex.calls[-1]["fromDate"] == "2026-09-09 00:00:00" and ex.calls[-1]["interval"] == 60
    finally:
        await c.aclose()


async def test_plans_unmatched_and_untraded_companies(site):
    app, ex, clock, other = site
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as anon:
        r = await anon.get("/api/stocks/RELIANCE/intraday?range=1D")
        assert r.status_code == 401 and r.json()["status"] == "auth_required"
        assert (await anon.get("/api/stocks/RELIANCE/intraday?range=2D")).status_code == 400
    basic = await signed_in(app, "b@example.com")
    silver = await signed_in(app, "s@example.com", plan="silver")
    try:
        assert (await basic.get("/api/stocks/RELIANCE/intraday?range=1D")).status_code == 200
        r = await basic.get("/api/stocks/RELIANCE/intraday?range=5D")
        assert r.status_code == 403 and r.json()["plan"] == "silver"
        assert (await basic.get("/api/stocks/RELIANCE/intraday?range=1M")).status_code == 403
        assert (await silver.get("/api/stocks/RELIANCE/intraday?range=5D")).status_code == 200
        n = len(ex.calls)
        r = await basic.get(f"/api/stocks/{other}/intraday?range=1D")
        assert r.status_code == 404 and r.json()["status"] == "not_available" and "Dhan" in r.json()["detail"]
        assert (await basic.get(f"/api/stocks/{other}/intraday?range=1D")).status_code == 404
        assert (await basic.get("/api/stocks/NOSUCHCO/intraday?range=1D")).json()["status"] == "not_found"
        assert len(ex.calls) == n                                                    # Dhan is never asked about a company it does not list
        ex.empty = True                                                              # suspended, or no trade in the window
        b = (await silver.get("/api/stocks/RELIANCE/intraday?range=1M")).json()
        assert b["status"] == "no_data" and b["available"] is False and "suspended" in b["detail"] and b["source"] == "Dhan"
    finally:
        await basic.aclose()
        await silver.aclose()


async def test_showcase_company_is_open_to_visitors(ingested, monkeypatch):  # noqa: F811
    async with ingested.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '2885', 'RELIANCE', 'EQ')")
    ex = Exchange()
    real = intraday.DhanClient
    monkeypatch.setattr(intraday, "DhanClient", lambda s, r=None: real(s, r, http=httpx.AsyncClient(transport=httpx.MockTransport(ex))))
    monkeypatch.setattr(intraday, "_now", lambda: at(2026, 10, 23, 11, 0, 30))
    app = create_app(make_settings(dhan_client_id="1000000001", dhan_access_token="T"), store=ingested)   # RELIANCE is the default showcase
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as anon:
            assert (await anon.get("/api/stocks/RELIANCE/intraday?range=1M")).status_code == 200


async def test_a_waiting_request_takes_the_fresh_copy_and_a_failed_source_shows_the_last_one(site):
    app, ex, clock, _ = site
    redis = app.state.store.redis
    c = await signed_in(app, "a@example.com")
    try:
        await redis.set("intra:lock:RELIANCE:1D", b"1", ex=20)                       # another process is asking Dhan
        r = await c.get("/api/stocks/RELIANCE/intraday?range=1D")
        assert r.status_code == 202 and r.json()["status"] == "preparing" and ex.calls == []
        waiting = asyncio.create_task(c.get("/api/stocks/RELIANCE/intraday?range=1D"))
        await asyncio.sleep(0.3)
        await redis.set("intra:RELIANCE:1D", json.dumps({"status": "ok", "available": True, "session": "2026-10-23", "source": "Dhan",
                                                         "asOf": "2026-10-23T11:00:00+05:30", "series": {"t": [], "c": []}}), ex=60)
        r = await waiting
        assert r.status_code == 200 and r.json()["asOf"] == "2026-10-23T11:00:00+05:30" and ex.calls == []
        await redis.delete("intra:lock:RELIANCE:1D", "intra:RELIANCE:1D")
        assert (await c.get("/api/stocks/RELIANCE/intraday?range=1D")).status_code == 200 and len(ex.calls) == 1
        await redis.delete("intra:RELIANCE:1D")
        ex.fail = True
        clock["now"] = at(2026, 10, 23, 11, 5)
        r = await c.get("/api/stocks/RELIANCE/intraday?range=1D")
        b = r.json()
        assert r.status_code == 200 and b["stale"] is True and b["asOf"] == "2026-10-23T11:00:30+05:30" and "last copy" in b["detail"]
        assert r.headers["cache-control"] == "no-store" and len(ex.calls) == 2
        await c.get("/api/stocks/RELIANCE/intraday?range=1D")
        assert len(ex.calls) == 2                                                    # not asked again for 30 seconds after a failure
        await redis.delete("intra:keep:RELIANCE:1D")
        r = await c.get("/api/stocks/RELIANCE/intraday?range=1D")
        assert r.status_code == 503 and r.json()["status"] == "source_down"
    finally:
        await c.aclose()


async def test_not_connected_without_dhan(ingested):  # noqa: F811
    app = create_app(make_settings(showcase_symbols=[]), store=ingested)
    async with app.router.lifespan_context(app):
        c = await signed_in(app, "a@example.com")
        try:
            r = await c.get("/api/stocks/RELIANCE/intraday?range=1D")
            assert r.status_code == 503 and r.json()["status"] == "not_connected"
        finally:
            await c.aclose()
