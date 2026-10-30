"""The technical-only path (backend/technical_refresh.py, POST /api/premium-reports/technical), the Indian-date rule for the last completed session,
the weekly 'preceding week' rule, and the tolerance for a candle whose close is a rounding step outside its high.

Root cause covered: the technical view used to be refreshed only with the whole report; the daily refresh runs just these functions, so they must
give the report's own numbers (equality below), on the right session (IST, not UTC or the container's zone)."""
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from backend import server
from backend import premium_supplied_candles as supplied_mod
from backend.premium_technical import build_technical_assessment, last_completed_session, normalise_bars
from backend.technical_refresh import NoUsableCandles, technical_only
from backend.technical_series import fit_range, weekly_closes
from backend.tests.test_premium_reports import asgi_request, auth

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)       # 17:30 IST on Friday 23 Oct 2026: its session is complete
NAMES = {"NIF50": "Nifty 50", "NIFMID100": "Nifty Midcap 100", "NIFSMA100": "Nifty Smallcap 100", "NIF500": "Nifty 500"}


def sessions(count, last=date(2026, 10, 23)):
    days, cur = [], last
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(days))


def walk(count, seed, drift=0.0004, vol=0.015, start=500.0, last=date(2026, 10, 23)):
    """A seeded random walk of realistic candles (not a ramp, so every signal moves)."""
    rng, price, out = random.Random(seed), start, []
    for day in sessions(count, last):
        o = price * (1 + rng.gauss(0, vol / 3))
        c = o * (1 + rng.gauss(drift, vol))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
        l = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        out.append([day.isoformat(), round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(1e6 * (1 + abs(rng.gauss(0, 0.5))))])
        price = c
    return out


def supplied(count=700, seed=11):
    return {"stock": {"provider": "Dhan", "candles": walk(count, seed)},
            "indices": {code: {"provider": "Dhan", "candles": walk(count + 40, seed + k + 1, 0.0003, 0.009, 20000.0)} for k, code in enumerate(NAMES)}}


def full_path(sup, now, shares, quote=None):
    """What generate_report does with the same supplied candles: server's own input resolver, then build_technical_assessment."""
    as_of = server._technical_candle_date(now)
    price = supplied_mod.supplied_price_input(sup, as_of, quote)
    required = [r["date"] for r in price["bars"][-505:]]
    bench = supplied_mod.benchmarks_with_supplied(sup, as_of, required, lambda: pytest.fail("no fallback expected"))
    return build_technical_assessment(price, last_completed_session(now), bench, shares)


@pytest.mark.parametrize("shares", [None, 2.0, 100.0, 600.0])      # Nifty 500 / small cap / mid cap / large cap benchmark at these prices
def test_technical_only_equals_the_full_report_path_bar_for_bar(shares):
    sup = supplied()
    alone = technical_only(sup, NOW, shares)
    assert alone == full_path(sup, NOW, shares)
    assert alone["status"] == "ready" and alone["shortTerm"]["score"] is not None and alone["longTerm"]["score"] is not None
    assert alone["asOf"] == "2026-10-23" and alone["sharesCr"] == shares


def test_the_new_session_replaces_the_old_one_the_evening_after_the_close():
    """Off-by-one guard: at 15:59 IST the day's bar is excluded (unfinished); at 16:00 IST it is used."""
    sup = supplied()
    before = technical_only(sup, datetime(2026, 10, 23, 15, 59, tzinfo=server.ZoneInfo("Asia/Kolkata")), None)
    after = technical_only(sup, datetime(2026, 10, 23, 16, 0, tzinfo=server.ZoneInfo("Asia/Kolkata")), None)
    assert before["asOf"] == "2026-10-22" and after["asOf"] == "2026-10-23"
    assert before["inputHash"] != after["inputHash"]


@pytest.mark.parametrize("stamp,expected", [
    (datetime(2026, 10, 26, 15, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))), date(2026, 10, 25)),   # Monday before 16:00: Sunday (no bar; Friday's is the newest)
    (datetime(2026, 10, 26, 16, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))), date(2026, 10, 26)),
    (datetime(2026, 10, 25, 20, 30, tzinfo=timezone.utc), date(2026, 10, 25)),           # 02:00 IST Monday is still Sunday for the session rule
    (datetime(2026, 10, 26, 10, 29, tzinfo=timezone.utc), date(2026, 10, 25)),           # 15:59 IST Monday
    (datetime(2026, 10, 26, 10, 30, tzinfo=timezone.utc), date(2026, 10, 26)),           # 16:00 IST Monday
    (datetime(2026, 10, 23, 18, 29, tzinfo=timezone.utc), date(2026, 10, 23)),           # 23:59 IST Friday
    (datetime(2026, 10, 23, 18, 30, tzinfo=timezone.utc), date(2026, 10, 23)),           # 00:00 IST Saturday: before 16:00, previous day = Friday
])
def test_last_completed_session_uses_the_indian_clock_whatever_the_zone_of_the_server(stamp, expected):
    assert last_completed_session(stamp) == expected == server._technical_candle_date(stamp)


def test_a_holiday_leaves_the_previous_session_as_the_last_bar():
    """No bar for the holiday: the series simply ends on the last real session and the view is as of that date."""
    sup = supplied()
    sup["stock"]["candles"] = [r for r in sup["stock"]["candles"] if r[0] != "2026-10-23"]
    assert technical_only(sup, NOW, None)["asOf"] == "2026-10-22"


def test_unusable_stock_candles_raise_and_nothing_is_taken_from_elsewhere():
    sup = supplied()
    sup["stock"]["provider"] = "Upstox"
    with pytest.raises(NoUsableCandles):
        technical_only(sup, NOW, None)
    with pytest.raises(NoUsableCandles):
        technical_only({}, NOW, None)


def test_the_benchmark_fallback_is_used_only_for_an_index_that_is_missing():
    sup = supplied()
    stock_dates = [r[0] for r in sup["stock"]["candles"]]
    loaded = {n: {"bars": [{"date": d, "close": 100.0 + i} for i, d in enumerate(stock_dates)], "provider": "FinEdge", "notes": []} for n in NAMES.values()}
    del sup["indices"]["NIF500"]
    asked = []
    got = technical_only(sup, NOW, None, None, lambda day, dates: asked.append(day) or loaded)
    assert asked == [date(2026, 10, 23)]
    assert got["benchmarkSources"]["Nifty 500"]["provider"] == "FinEdge" and got["benchmarkSources"]["Nifty 50"]["provider"] == "Dhan"


# ------------------------------------------------------------------------------------------------ the endpoint
def test_the_endpoint_returns_only_the_technical_view_and_refuses_the_rest(monkeypatch):
    sup = supplied()
    status, body = asgi_request(server.app, "POST", "/api/premium-reports/technical", {"suppliedCandles": sup, "sharesCr": 2.0}, headers=auth())
    assert status == 200 and set(body) == {"technicalAssessment", "calculatedAt"}
    expected = full_path(sup, datetime.fromisoformat(body["calculatedAt"]), 2.0)
    assert body["technicalAssessment"] == expected
    assert body["technicalAssessment"]["modelVersion"] == "st-lt-14.3"
    assert asgi_request(server.app, "POST", "/api/premium-reports/technical", {"suppliedCandles": sup})[0] in (401, 403)
    bad = {**sup, "stock": {**sup["stock"], "provider": "FinEdge"}}
    status, body = asgi_request(server.app, "POST", "/api/premium-reports/technical", {"suppliedCandles": bad}, headers=auth())
    assert status == 422 and "supplied" in body["detail"].lower()
    monkeypatch.setattr(server, "_premium_interactive", 1)
    assert asgi_request(server.app, "POST", "/api/premium-reports/technical", {"suppliedCandles": sup}, headers=auth())[0] == 429
    assert asgi_request(server.app, "POST", "/api/premium-reports/technical", {"suppliedCandles": sup, "priority": "interactive"}, headers=auth())[0] == 200


# ------------------------------------------------------------------------------------------------ the weekly rule
def bars_ending(last, count=60):
    return [{"date": d.isoformat(), "close": 100.0 + i} for i, d in enumerate(sessions(count, last))]


def test_weekly_signals_use_the_preceding_week_on_a_friday_evening_and_on_the_next_monday():
    friday, monday = date(2026, 10, 23), date(2026, 10, 26)
    on_friday = weekly_closes(bars_ending(friday), friday)
    on_monday = weekly_closes(bars_ending(monday), monday)
    fri_bars = bars_ending(friday)
    # Friday: the current week (Mon 19 to Fri 23) is NOT in the series; the last weekly close is the previous Friday's
    assert on_friday[-1] == [b["close"] for b in fri_bars if b["date"] == "2026-10-16"][0]
    # Monday: the week that just ended (closing Friday 23) is now the last one
    mon_bars = bars_ending(monday)
    assert on_monday[-1] == [b["close"] for b in mon_bars if b["date"] == "2026-10-23"][0]
    assert len(on_monday) == len(on_friday) + 1


def test_a_holiday_shortened_week_still_closes_on_its_last_session():
    bars = [b for b in bars_ending(date(2026, 10, 30)) if b["date"] != "2026-10-23"]        # Friday 23 Oct a holiday
    week = weekly_closes(bars, date(2026, 10, 30))
    assert week[-1] == [b["close"] for b in bars if b["date"] == "2026-10-22"][0]


# ------------------------------------------------------------------------------------------------ close above high
@pytest.mark.parametrize("o,h,l,c,fitted", [
    (100, 101, 99, 100.5, (101, 99)),                    # consistent: untouched
    (100, 101, 99, 101.03, (101.03, 99)),                # close 0.03% above the high: rounding, taken as the high
    (100, 101, 99, 98.97, (101, 98.97)),                 # close 0.03% below the low
    (3141, 3141, 3092, 3178.2, None),                    # the recorded TCS bar of 1 Feb 2026: 1.2% above the high is a bad candle
    (100, 101, 99, 101.6, None),
])
def test_fit_range_tolerates_rounding_only(o, h, l, c, fitted):
    got = fit_range(o, h, l, c)
    assert (got is None) if fitted is None else got == pytest.approx(fitted)


def test_a_rounding_sized_violation_keeps_the_history_and_a_real_one_still_withholds():
    rows = lambda: [{"quote_date": d, "open_price": o, "high_price": h, "low_price": l, "close_price": c, "volume": v} for d, o, h, l, c, v in walk(300, 3)]
    clean = rows()
    clean[100]["close_price"] = round(clean[100]["high_price"] * 1.0003, 2)      # 0.03% above the high
    got = normalise_bars({"price": clean}, date(2026, 10, 23))
    assert len(got) == 300 and all(b["open"] is not None for b in got) and got[100]["high"] >= got[100]["close"]
    bad = rows()
    bad[100]["close_price"] = round(bad[100]["high_price"] * 1.012, 2)           # 1.2% above: a bad candle, withheld as before
    got = normalise_bars({"price": bad}, date(2026, 10, 23))
    assert got[100]["open"] is None and got[100]["close"] is not None
    sup = supplied()
    sup["stock"]["candles"][100][4] = round(sup["stock"]["candles"][100][2] * 1.0003, 2)
    assert supplied_mod.supplied_price_input(sup, date(2026, 10, 23)) is not None
    sup["stock"]["candles"][100][4] = round(sup["stock"]["candles"][100][2] * 1.012, 2)
    assert supplied_mod.supplied_price_input(sup, date(2026, 10, 23)) is None
