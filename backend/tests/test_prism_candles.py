"""Dhan daily candles for the Prism technical assessment (finlit/prism_candles.py) and their hand-off to the site backend (finlit/prism.py).

Dhan is faked with httpx.MockTransport in the shapes tests/test_dhan.py and tests/test_etf_dhan.py already use for POST /v2/charts/historical
(parallel arrays open/high/low/close/volume/timestamp). No live account was used.
"""
import json
from datetime import date, datetime, timedelta

import httpx
import pytest

from finlit import dhan, prism, prism_candles as pc
from finlit.config import Settings
from test_integration import make_settings, store  # noqa: F401  (fixture)
from test_prism import FakeSite, SECRET, make_app, member  # noqa: F401

IST = dhan.IST
NOW = datetime(2026, 10, 23, 17, 30, tzinfo=IST)           # Friday after 16:00: its own session counts as complete
LAST = date(2026, 10, 22)                                  # ... but Dhan only has T-1
IDS = {"NIF50": "13", "NIFMID100": "37", "NIFSMA100": "5", "NIF500": "19"}
DHAN_SYMBOLS = {"NIF50": "NIFTY", "NIFMID100": "NIFTY MID100 FREE", "NIFSMA100": "NIFTY SMALLCAP 100", "NIF500": "NIFTY 500"}


def sessions(last, n):
    out, d = [], last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def body(last=LAST, n=1560, mutate=None):
    days = sessions(last, n)
    cols = {"open": [100 + i * .1 for i in range(n)], "high": [102 + i * .1 for i in range(n)], "low": [98 + i * .1 for i in range(n)],
            "close": [101 + i * .1 for i in range(n)], "volume": [1000 + i for i in range(n)]}
    if mutate:
        mutate(cols, days)
    return {**cols, "timestamp": [int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp()) for d in days]}


class FakeDhan:
    def __init__(self, series=None):
        self.series = series or {}          # security id -> response body (default: a complete one)
        self.calls = []                     # (security id, segment, instrument, fromDate, toDate)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.host == "auth.dhan.co":
            return httpx.Response(200, json={"accessToken": "T", "expiryTime": "2099-01-01T00:00:00.000"})
        assert req.url.host == "api.dhan.co" and req.url.path == "/v2/charts/historical" and req.headers["access-token"] == "T"
        sent = json.loads(req.content)
        self.calls.append((sent["securityId"], sent["exchangeSegment"], sent["instrument"], sent["fromDate"], sent["toDate"]))
        got = self.series.get(sent["securityId"], body())
        return httpx.Response(got) if isinstance(got, int) else httpx.Response(200, json=got)


def settings(**kw):
    return make_settings(dhan_client_id="1000000001", dhan_pin="123456", dhan_totp_secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", **kw)


async def prepare(st, fake, **kw):
    """A state like the app's: the store, settings, and a Dhan client served by `fake`; Dhan ids for RELIANCE and the four indices."""
    from types import SimpleNamespace
    redis = st.redis
    for key in ("dhan:token", "dhan:secmap", pc.DOWN_KEY, *[pc.CACHE_KEY + c for c in IDS]):
        await redis.delete(key)
    async with st.pool.acquire() as conn:
        await conn.execute("DELETE FROM dhan_instruments")
        await conn.execute("DELETE FROM dhan_indices")
        await conn.execute("INSERT INTO companies (symbol, name, nse_code) VALUES ('RELIANCE', 'Reliance Industries', 'RELIANCE') ON CONFLICT (symbol) DO UPDATE SET nse_code = 'RELIANCE'")
        await conn.execute("INSERT INTO dhan_instruments (exch, security_id, symbol, series) VALUES ('NSE', '2885', 'RELIANCE', 'EQ')")
        await conn.executemany("INSERT INTO dhan_indices (exch, security_id, symbol, name) VALUES ('NSE', $1, $2, $3)",
                               [(IDS[c], DHAN_SYMBOLS[c], c) for c in IDS])
    s = settings(**kw)
    state = SimpleNamespace(store=st, settings=s)
    state.prism_dhan = dhan.DhanClient(s, redis, http=httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return state


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(pc, "_down_until", 0.0)
    monkeypatch.setattr(pc, "CALL_GAP", 0.0)


# ------------------------------------------------------------------------------------------------------------ clean()
def rows(n=600, **over):
    out = [{"day": d, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 5} for d in sessions(LAST, n)]
    return out


@pytest.mark.parametrize("name,mutate", [
    ("missing close", lambda r: r[7].update(close=None)),
    ("zero low", lambda r: r[7].update(low=0)),
    ("nan", lambda r: r[7].update(open=float("nan"))),
    ("negative volume", lambda r: r[7].update(volume=-1)),
    ("high below close", lambda r: r[7].update(high=10.5)),
    ("same day twice with different prices", lambda r: r.insert(8, {**r[8], "close": 10.5})),
    ("unsorted", lambda r: r.reverse()),
    ("bool", lambda r: r[7].update(open=True)),
])
def test_one_bad_row_rejects_the_whole_series(name, mutate):
    r = rows()
    mutate(r)
    assert pc.clean(r, LAST, 252) is None, name


def test_a_day_sent_twice_is_one_session_when_the_prices_agree():
    """Dhan now and then repeats a day (seen on live data: an exact copy, and a copy with a much smaller volume). One session, not two:
    the larger volume is kept. Two records of one day with different prices are still refused."""
    r = rows()
    r.insert(8, dict(r[7]))                                    # an exact copy
    r.insert(11, {**r[10], "volume": 2})                       # a partial copy after the complete record
    r.insert(14, {**r[13], "volume": 1}); r[14], r[13] = {**r[13]}, {**r[13], "volume": 1}   # partial record first, complete one after
    got = pc.clean(r, LAST, 252)
    assert got is not None and len(got) == 600
    assert [row[0] for row in got] == sorted({row[0] for row in got})              # strictly increasing
    assert {row[5] for row in got} == {5}                                         # the complete record (volume 5) always wins
    clash = rows(); clash.insert(8, {**clash[8], "close": 10.5})
    assert pc.clean(clash, LAST, 252) is None


def test_clean_series_rules():
    good = pc.clean(rows(), LAST, 252)
    assert good[0][0] < good[-1][0] and good[-1] == [LAST.isoformat(), 10.0, 12.0, 9.0, 11.0, 5]
    assert pc.clean(rows(200), LAST, 252) is None                           # too few sessions
    assert pc.clean(rows(), LAST + timedelta(days=11), 252) is None          # last session more than 10 days old
    assert pc.clean([], LAST, 252) is None and pc.clean(rows(2100), LAST, 252) is None
    assert pc.clean([{**r, "volume": 0} for r in rows()], LAST, 252) is not None    # volume zero is valid
    extra = rows() + [{"day": LAST + timedelta(days=1), "open": 1.0, "high": 2.0, "low": 1.0, "close": 2.0, "volume": 1}]
    assert pc.clean(extra, LAST, 252)[-1][0] == LAST.isoformat()             # the unfinished day is dropped, not an error


def test_the_last_completed_session_is_today_only_after_16_00_ist_on_a_weekday():
    assert pc.expected_session(datetime(2026, 10, 23, 15, 59, tzinfo=IST)) == date(2026, 10, 22)
    assert pc.expected_session(datetime(2026, 10, 23, 16, 0, tzinfo=IST)) == date(2026, 10, 23)
    assert pc.expected_session(datetime(2026, 10, 24, 12, 0, tzinfo=IST)) == date(2026, 10, 23)      # Saturday
    assert pc.expected_session(datetime(2026, 10, 26, 9, 0, tzinfo=IST)) == date(2026, 10, 23)       # Monday morning


# ------------------------------------------------------------------------------------------------------ the fetching
async def test_stock_and_four_indices_are_fetched_complete_and_the_indices_are_cached(store):  # noqa: F811
    fake = FakeDhan()
    state = await prepare(store, fake)
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert set(got) == {"stock", "indices"} and set(got["indices"]) == set(IDS)
    assert got["stock"]["provider"] == "Dhan" and all(v["provider"] == "Dhan" for v in got["indices"].values())
    assert len(got["stock"]["candles"]) == 1560 and got["stock"]["candles"][-1][0] == LAST.isoformat()
    assert got["stock"]["candles"][0][:2] == [sessions(LAST, 1560)[0].isoformat(), 100.0]
    assert [c[1:] for c in got["stock"]["candles"][-1:]] == [[100 + 1559 * .1, 102 + 1559 * .1, 98 + 1559 * .1, 101 + 1559 * .1, 1000 + 1559]]
    by_id = {c[0]: c for c in fake.calls}
    assert by_id["2885"][1:3] == ("NSE_EQ", "EQUITY") and all(by_id[i][1:3] == ("IDX_I", "INDEX") for i in IDS.values())
    assert len(fake.calls) == 5 and by_id["2885"][4] == "2026-10-24"                     # Dhan's end date is not included
    assert date.fromisoformat(by_id["2885"][4]) - date.fromisoformat(by_id["2885"][3]) >= timedelta(days=365 * 6)
    json.dumps(got)                                                                      # the body is plain JSON
    assert len(json.dumps(got)) < 1_500_000

    again = await pc.supplied_candles(state, "RELIANCE", NOW)                            # the next company: one call, the stock's
    assert again["indices"] == got["indices"] and len(fake.calls) == 6 and fake.calls[-1][0] == "2885"


async def test_indices_are_asked_again_only_after_a_newer_session_has_completed(store):  # noqa: F811
    fake = FakeDhan()
    state = await prepare(store, fake)
    await pc.supplied_candles(state, "RELIANCE", NOW)
    n = len(fake.calls)
    await pc.supplied_candles(state, "RELIANCE", NOW.replace(hour=20))                   # same session: cache
    assert len(fake.calls) == n + 1
    monday = datetime(2026, 10, 26, 17, 0, tzinfo=IST)
    fake.series = {"2885": body(date(2026, 10, 26)), **{i: body(date(2026, 10, 26)) for i in IDS.values()}}
    got = await pc.supplied_candles(state, "RELIANCE", monday)
    assert len(fake.calls) == n + 1 + 5 and got["indices"]["NIF50"]["candles"][-1][0] == "2026-10-26"


async def test_a_cached_index_lacking_the_stocks_newest_session_is_refreshed_not_assumed(store, monkeypatch):  # noqa: F811
    older = FakeDhan({i: body(date(2026, 10, 21)) for i in IDS.values()})               # the indices are a day behind the stock
    state = await prepare(store, older)
    await pc.supplied_candles(state, "RELIANCE", NOW)
    n = len(older.calls)
    await pc.supplied_candles(state, "RELIANCE", NOW)                                    # asked again at once? no: Dhan may simply not have it yet
    assert len(older.calls) == n + 1
    monkeypatch.setattr(pc, "RECHECK_SECONDS", -1)
    older.series = {}                                                                    # Dhan now has the session
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert len(older.calls) == n + 1 + 5 and got["indices"]["NIF500"]["candles"][-1][0] == LAST.isoformat()


async def test_todays_partial_candle_is_not_sent_before_16_00(store):  # noqa: F811
    today = date(2026, 10, 23)
    fake = FakeDhan({"2885": body(today)})                                               # Dhan already shows a candle for today
    state = await prepare(store, fake)
    got = await pc.supplied_candles(state, "RELIANCE", datetime(2026, 10, 23, 11, 0, tzinfo=IST))
    assert got["stock"]["candles"][-1][0] == "2026-10-22"
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert got["stock"]["candles"][-1][0] == "2026-10-23"


async def test_incomplete_series_are_left_out_and_nothing_is_filled(store):  # noqa: F811
    def hole(cols, days):
        cols["low"][700] = None                                                          # one missing low
    short = body(n=300)                                                                  # fewer than the 505 sessions an index needs
    unequal = body()
    unequal["close"] = unequal["close"][:-1]                                             # arrays of different lengths: dhan.daily returns []
    fake = FakeDhan({"2885": body(mutate=hole), IDS["NIF50"]: short, IDS["NIFMID100"]: unequal, IDS["NIFSMA100"]: 400})
    state = await prepare(store, fake)
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert "stock" not in got and set(got["indices"]) == {"NIF500"}
    assert await store.redis.get(pc.CACHE_KEY + "NIF50") is None                          # a bad answer is not cached


async def test_nothing_at_all_when_every_series_fails(store):  # noqa: F811
    fake = FakeDhan({i: 400 for i in ("2885", *IDS.values())})
    assert await pc.supplied_candles(await prepare(store, fake), "RELIANCE", NOW) is None


async def test_unmatched_company_still_gets_the_indices_and_unconfirmed_indices_are_not_asked(store):  # noqa: F811
    fake = FakeDhan()
    state = await prepare(store, fake)
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE dhan_indices SET symbol = 'SOMETHING ELSE' WHERE security_id = '19'")   # Dhan re-used the id for another index
    got = await pc.supplied_candles(state, "NOPE", NOW)
    assert "stock" not in got and set(got["indices"]) == {"NIF50", "NIFMID100", "NIFSMA100"}
    assert "19" not in {c[0] for c in fake.calls} and "2885" not in {c[0] for c in fake.calls}


async def test_dhan_not_set_up_means_nothing_is_fetched_or_sent(store):  # noqa: F811
    from types import SimpleNamespace
    state = SimpleNamespace(store=store, settings=make_settings())
    assert await pc.supplied_candles(state, "RELIANCE", NOW) is None and getattr(state, "prism_dhan", None) is None


async def test_the_client_is_made_from_settings_once_and_logs_no_secrets(store, caplog):  # noqa: F811
    from types import SimpleNamespace
    state = SimpleNamespace(store=store, settings=settings())
    a = pc.dhan_client(state, state.settings, store.redis)
    assert a is pc.dhan_client(state, state.settings, store.redis) and a.configured
    await a.aclose()
    fake = FakeDhan({i: 400 for i in ("2885", *IDS.values())})
    st = await prepare(store, fake)
    with caplog.at_level("DEBUG"):
        await pc.supplied_candles(st, "RELIANCE", NOW)
    text = caplog.text
    assert "123456" not in text and "GEZDGNBVGY3TQOJQ" not in text and "access-token" not in text.lower()


# ------------------------------------------------------------------------------------- the hand-off to the site backend
async def test_candles_ride_in_the_request_body_and_the_default_body_is_unchanged(store, monkeypatch):  # noqa: F811
    app, fake = await make_app(store)
    plain = await prism._report_body(app, "TCS", "consolidated")
    assert plain == {"query": "TCS", "statement_type": "consolidated", "delivery": "inline"}      # Dhan not set up: exactly as before
    sent = {"stock": {"provider": "Dhan", "candles": [["2026-10-22", 1.0, 2.0, 0.5, 1.5, 3]]}}

    async def fake_candles(state, symbol):
        return sent
    monkeypatch.setattr(prism, "supplied_candles", fake_candles)
    assert (await prism._report_body(app, "TCS", "consolidated"))["suppliedCandles"] == sent

    async def broken(state, symbol):
        raise RuntimeError("secret detail")
    monkeypatch.setattr(prism, "supplied_candles", broken)
    assert await prism._report_body(app, "TCS", "consolidated") == plain                          # never stops the calculation

    async def slow(state, symbol):
        await prism.asyncio.sleep(5)
    monkeypatch.setattr(prism, "supplied_candles", slow)
    monkeypatch.setattr(prism, "CANDLE_SECONDS", 0.05)
    assert await prism._report_body(app, "TCS", "consolidated") == plain


async def test_a_member_calculation_and_the_nightly_run_both_send_the_candles(store, monkeypatch):  # noqa: F811
    sent = {"stock": {"provider": "Dhan", "candles": [["2026-10-22", 1.0, 2.0, 0.5, 1.5, 3]]}}
    asked = []

    async def fake_candles(state, symbol):
        asked.append((symbol, state.store is store))
        return sent
    monkeypatch.setattr(prism, "supplied_candles", fake_candles)
    app, site = await make_app(store)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'PZC'")
        await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ('PZC', 'consolidated', 'summary', '{}', 'x', now())")
    async with app.router.lifespan_context(app):
        gold = await member(app, "gold")
        r = await gold.post("/api/prism/reports", json={"symbol": "TCS", "statement": "consolidated"})
        assert r.status_code == 200 and site.reports[-1]["body"]["suppliedCandles"] == sent
    settings_ = make_settings(site_api_url="http://site", cms_jwt_secret=SECRET)
    http = httpx.AsyncClient(transport=httpx.MockTransport(site), base_url="http://site")
    out = await prism.precompute(store, settings_, limit=5, client=http)
    assert out["calculated"] >= 1 and ("PZC", True) in asked
    assert site.reports[-1]["sub"] == "prism:nightly" and site.reports[-1]["body"]["suppliedCandles"] == sent
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM snapshots WHERE symbol = 'PZC'")


# ------------------------------------------------------------------------------------------------------ review fixes
def test_lock_outlives_candles_slot_wait_and_calculation():
    assert prism.LOCK_SECONDS == int(prism.CANDLE_SECONDS + prism.SLOT_WAIT + prism.GENERATE_SECONDS + prism.LOCK_MARGIN) >= 320
    assert prism.JOB_WORKING_SECONDS == prism.LOCK_SECONDS


def scaled(n=600, split_at=None, factor=5, adjusted=False):
    out = []
    for i, d in enumerate(sessions(LAST, n)):
        div = factor if adjusted or (split_at is not None and i >= split_at) else 1
        out.append({"day": d, "open": (100 + i) / div, "high": (102 + i) / div, "low": (98 + i) / div, "close": (101 + i) / div, "volume": 5})
    return out


def test_implausible_daily_moves_are_refused_and_a_split_adjusted_series_is_not():
    assert pc.clean(scaled(), LAST, 252) is not None
    assert pc.clean(scaled(adjusted=True), LAST, 252) is not None                  # Dhan's adjusted series is smooth
    got, why = pc.clean_reason(scaled(split_at=400), LAST, 252)                       # genuine unadjusted 1:5 split
    assert got is None and "more than 40% in a day" in why
    assert pc.clean(scaled(split_at=400, factor=2), LAST, 252) is None               # bonus 1:1
    base = scaled()
    for r in base[300:]:
        for k in ("open", "high", "low", "close"):
            r[k] *= 1.39
    assert pc.clean(base, LAST, 252) is not None
    for r in base[300:]:
        for k in ("open", "high", "low", "close"):
            r[k] *= 1.05
    assert pc.clean(base, LAST, 252) is None                                          # now about 46% overnight


def test_last_close_must_be_within_fifteen_percent_of_the_quote():
    last = pc.clean(scaled(), LAST, 252)[-1][4]
    assert pc.clean(scaled(), LAST, 252, last * 1.14) is not None and pc.clean(scaled(), LAST, 252, last / 1.14) is not None
    assert pc.clean(scaled(), LAST, 252, last * 1.2) is None and pc.clean(scaled(), LAST, 252, last * 0.5) is None
    for none in (None, 0, -1, float("nan")):
        assert pc.clean(scaled(), LAST, 252, none) is not None


def test_a_datetime_is_not_a_calendar_date():
    r = rows()
    r[7]["day"] = datetime(r[7]["day"].year, r[7]["day"].month, r[7]["day"].day)
    assert pc.clean(r, LAST, 252) is None


async def test_unexpected_answers_do_not_raise(store):  # noqa: F811
    fake = FakeDhan({"2885": {**body(), "timestamp": [10 ** 20] * 1560}, **{i: body() for i in IDS.values()}})
    got = await pc.supplied_candles(await prepare(store, fake), "RELIANCE", NOW)
    assert "stock" not in got and set(got["indices"]) == set(IDS)


async def test_a_crashing_stock_fetch_does_not_cancel_the_indices(store, monkeypatch):  # noqa: F811
    state = await prepare(store, FakeDhan())

    async def boom(*a, **k):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(pc, "security_map", boom)
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert "stock" not in got and set(got["indices"]) == set(IDS)


async def test_stock_failure_alone_does_not_pause_dhan_but_a_total_failure_does(store):  # noqa: F811
    fake = FakeDhan({"2885": 500})
    state = await prepare(store, fake)
    got = await pc.supplied_candles(state, "RELIANCE", NOW)
    assert "stock" not in got and len(got["indices"]) == 4 and await store.redis.get(pc.DOWN_KEY) is None
    down = FakeDhan({i: 400 for i in ("2885", *IDS.values())})
    state = await prepare(store, down)
    assert await pc.supplied_candles(state, "RELIANCE", NOW) is None
    assert await store.redis.get(pc.DOWN_KEY) is not None and 0 < await store.redis.ttl(pc.DOWN_KEY) <= 300
    calls = len(down.calls)
    assert await pc.supplied_candles(state, "RELIANCE", NOW) is None and len(down.calls) == calls     # no new Dhan call during the pause
    await store.redis.delete(pc.DOWN_KEY)
    down.series = {}
    assert (await pc.supplied_candles(state, "RELIANCE", NOW)) is not None


async def test_a_candle_timeout_in_a_report_pauses_dhan_too(store, monkeypatch):  # noqa: F811
    app, fake = await make_app(store)
    await store.redis.delete(pc.DOWN_KEY)

    async def slow(state, symbol):
        await prism.asyncio.sleep(5)
    monkeypatch.setattr(prism, "supplied_candles", slow)
    monkeypatch.setattr(prism, "CANDLE_SECONDS", 0.05)
    async with app.router.lifespan_context(app):
        await prism._report_body(app, "TCS", "consolidated")
        assert await store.redis.get(pc.DOWN_KEY) is not None
        await store.redis.delete(pc.DOWN_KEY)


async def test_a_corrupt_cache_entry_is_a_miss(store):  # noqa: F811
    fake = FakeDhan()
    state = await prepare(store, fake)
    await pc.supplied_candles(state, "RELIANCE", NOW)
    n = len(fake.calls)
    for bad in (b"not json", b'{"expected": "2026-10-22", "fetched": 1, "candles": [[1]]}', b'{"expected": 5, "candles": []}',
                b'{"expected": "2026-10-22", "fetched": "x", "candles": [["2026-10-22", 1, 2, 3, 4, 5]]}', b'[1]'):
        await store.redis.set(pc.CACHE_KEY + "NIF50", bad)
        got = await pc.supplied_candles(state, "RELIANCE", NOW)
        assert len(got["indices"]["NIF50"]["candles"]) == 1560


def test_the_pacing_lock_works_in_every_event_loop():
    import asyncio

    async def use():
        async with pc._pace_lock():
            pass
        return pc._pace_lock()
    a, b = asyncio.run(use()), asyncio.run(use())
    assert a is not b


async def test_candles_are_fetched_before_a_calculation_slot_is_taken(store, monkeypatch):  # noqa: F811
    app, site = await make_app(store)
    seen = []

    async def fake_candles(state, symbol):
        seen.append(prism._slots(app)._value)
        return None
    monkeypatch.setattr(prism, "supplied_candles", fake_candles)
    async with app.router.lifespan_context(app):
        status, _, _ = await prism._execute(app, "prism:visitor", "TCS", "consolidated", None, False)
    assert seen == [prism.SLOTS] and status in (200, 404, 422, 502, 503)
