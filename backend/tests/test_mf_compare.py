"""Fund Compare, head to head (finlit/mf_compare.py): rolling-window maths, calendar months and years, consistency counts, the category average
index, the whole answer from fixture series, and the API (categories, fund lists, the compare itself, 10 years from the mirror, the category
average built once per NAV date, the 'pending' answer, refusals).

The series here are made up for the test (smooth growth at a known rate, with a slow wave on top where noted), so the expected figures follow
from the rate: a NAV of 100 x 1.12 ^ (days / 365) grows exactly 12% a year between any two days."""

import asyncio
import math
import os
from datetime import date, timedelta

import httpx
import pytest
from fastapi import FastAPI

from finlit import mf, mf_compare as mc
from finlit.config import Settings
from finlit.store import Store

END = date(2026, 10, 19)   # a Monday: the newest NAV date in the fixtures


def weekdays(first: date, last: date):
    return [o for o in range(first.toordinal(), last.toordinal() + 1) if date.fromordinal(o).weekday() < 5]


def grow(days, rate, wave=0.0, phase=0.0, base=100.0):
    """NAV = base x (1 + rate) ^ (t / 365), times (1 + wave x sin(...)) when a wave is asked for; rounded to 4 decimals like AMFI's NAVs."""
    d0 = days[0]
    return [round(base * (1 + rate) ** ((d - d0) / 365) * (1 + wave * math.sin(2 * math.pi * (d - d0) / 290 + phase)), 4) for d in days]


# ---------------------------------------------------------------------------------------------- maths

def test_rolling_one_month_windows_worked_by_hand():
    days = weekdays(date(2024, 1, 1), date(2024, 3, 29))
    navs = [100.0 + k for k in range(len(days))]          # 23 weekdays in January 2024, 21 in February, 21 to 29 March
    d, v = mc.rolling(days, navs, 1, False)
    got = dict(zip(d, v))
    assert d[0] == date(2024, 2, 1).toordinal() and got[d[0]] == pytest.approx(23.0)          # 1 Feb: NAV 123 against 100 on 1 Jan
    assert got[date(2024, 3, 1).toordinal()] == pytest.approx((144 / 123 - 1) * 100)          # 1 Mar against 1 Feb
    assert got[date(2024, 2, 29).toordinal()] == pytest.approx((143 / 120 - 1) * 100)         # 29 Feb against 29 Jan
    assert got[date(2024, 3, 29).toordinal()] == pytest.approx((164 / 143 - 1) * 100)         # 29 Mar against 29 Feb
    assert len(d) == 42                                                                       # every weekday from 1 Feb to 29 Mar


def test_rolling_three_year_windows_of_a_steady_fund_are_its_rate():
    days = weekdays(date(2016, 1, 1), END)
    navs = [100 * 1.12 ** ((x - days[0]) / 365) for x in days]
    d, v = mc.rolling(days, navs, 36, True)
    assert d[0] >= mf.shift_months(date(2016, 1, 1), -36).toordinal() - 7
    assert all(x == pytest.approx(12.0, abs=1e-9) for x in v)
    s = mc.roll_stats(d, v)
    assert s["min"] == s["median"] == s["max"] == 12.0 and s["positive"] == 100.0 and s["count"] == len(v)
    assert mc.roll_stats([], [])["why"]


def test_window_and_point_return():
    days = weekdays(date(2021, 1, 4), END)
    navs = [100 * 1.10 ** ((x - days[0]) / 365) for x in days]
    (d, v), why = mc.window(days, navs, END.toordinal(), 36)
    assert why is None and d[-1] == END.toordinal() and d[0] == date(2023, 10, 19).toordinal()
    assert mc.point_return(d, v, True) == pytest.approx(10.0, abs=1e-9)
    assert mc.point_return(d, v, False) == pytest.approx((1.10 ** ((d[-1] - d[0]) / 365) - 1) * 100)
    none, why = mc.window(days, navs, END.toordinal(), 120)
    assert none is None and why == "NAV history on file starts on 4 Jan 2021, less than 10 years before 19 Oct 2026."
    holey = [x for x in days if not date(2023, 10, 5).toordinal() <= x <= date(2023, 10, 19).toordinal()]
    none, why = mc.window(holey, [1.0] * len(holey), END.toordinal(), 36)
    assert none is None and "before the start date" in why
    assert mc.window([], [], END.toordinal(), 12) == (None, "No NAV history is loaded for this fund.")


def test_calendar_months_and_years_leave_out_partial_ones():
    days = weekdays(date(2023, 11, 15), date(2024, 3, 20))
    navs = [100.0 + k for k in range(len(days))]
    at = dict(zip(days, navs))
    nav = lambda y, m, dd: at[date(y, m, dd).toordinal()]   # noqa: E731
    months = mc.calendar_returns(days, navs, "m")
    # November is the first month (no month-end before it) and March is unfinished (last NAV 20 March): both are left out
    assert list(months) == [(2023, 12), (2024, 1), (2024, 2)]
    assert months[(2023, 12)] == pytest.approx((nav(2023, 12, 29) / nav(2023, 11, 30) - 1) * 100)
    assert months[(2024, 2)] == pytest.approx((nav(2024, 2, 29) / nav(2024, 1, 31) - 1) * 100)
    assert mc.calendar_returns(days, navs, "y") == {}
    yd = weekdays(date(2020, 6, 1), END)
    yv = grow(yd, 0.08)
    years = mc.calendar_returns(yd, yv, "y")
    assert list(years) == [(2021, 0), (2022, 0), (2023, 0), (2024, 0), (2025, 0)]
    assert all(x == pytest.approx(8.0, abs=0.1) for x in years.values())
    assert mc.month_label((2020, 3)) == "Mar 2020"


def test_tally_counts_wins_losses_and_ties_on_shared_keys_only():
    t = mc.tally([1, 2, 3, 4, 9], [5.0, 1.0, 2.0, 7.0, 1.0], [1, 2, 3, 4, 8], [4.0, 3.0, 2.0, 1.0, 0.0])
    assert t == {"a": 2, "b": 1, "ties": 1, "n": 4}


def test_drawdown_with_its_dates_and_recovery():
    days = weekdays(date(2026, 1, 5), date(2026, 3, 13))
    navs = [100.0] * 5 + [110.0] + [100.0, 95.0, 92.0, 90.0, 88.0] + [95.0] * 9 + [110.0] + [120.0] * (len(days) - 21)
    dd = mc.drawdown(days, navs)
    assert dd["value"] == -20.0 and dd["peak"] == date.fromordinal(days[5]).isoformat() and dd["trough"] == date.fromordinal(days[10]).isoformat()
    assert dd["recovered"] == date.fromordinal(days[20]).isoformat()
    assert mc.drawdown(days, navs[:21] + [100.0] * (len(days) - 21))["recovered"] == date.fromordinal(days[20]).isoformat()
    assert mc.drawdown(days, navs[:15] + [90.0] * (len(days) - 15))["recovered"] is None
    assert mc.drawdown(days[:10], navs[:10])["value"] is None


def test_category_index_equal_weight_joins_holidays_and_bad_data():
    grid = mc.weekday_grid(date(2026, 10, 5).toordinal(), date(2026, 10, 16).toordinal())   # two weeks, Monday to Friday
    g = lambda k: grid[k]   # noqa: E731
    idx = mc.CategoryIndex(grid)
    holiday = 4   # nobody publishes a NAV on the fifth weekday
    x = [(g(k), v) for k, v in enumerate([100, 110, 110, 110, 110, 110, 110, 110, 110, 110]) if k != holiday]
    y = [(g(k), 100.0) for k in range(10) if k != holiday]
    z = [(g(k), v) for k, v in ((3, 50.0), (5, 55.0), (6, 55.0), (7, 55.0), (8, 55.0), (9, 55.0))]   # joins on day 3
    bad = [(g(k), v) for k, v in ((0, 100.0), (1, 300.0), (2, 300.0))]
    for code, s in ((1, x), (2, y), (3, z), (4, bad)):
        idx.add(code, [a for a, _ in s], [b for _, b in s])
    assert idx.codes == [1, 2, 3] and idx.skipped == [4] and idx.starts == [g(0), g(0), g(3)]
    days, vals = idx.index()
    assert g(holiday) not in days and days[0] == g(0) and len(days) == 9
    lv = dict(zip(days, vals))
    assert lv[g(0)] == 100.0 and lv[g(1)] == pytest.approx(105.0) and lv[g(3)] == pytest.approx(105.0)
    assert lv[g(5)] == pytest.approx(105.0 * (1 + 0.10 / 3)) and lv[g(9)] == pytest.approx(lv[g(5)])


def test_assemble_whole_answer_from_fixture_series():
    days = weekdays(date(2016, 6, 1), END)
    a = grow(days, 0.12, 0.03, 0.0)
    b = grow(days, 0.10, 0.03, 1.0)
    c = grow(days, 0.08, 0.03, 2.0)
    idx = mc.CategoryIndex(mc.weekday_grid(END.toordinal() - mc.CAT_SPAN, END.toordinal()))
    for code, s in ((1, a), (2, b), (3, c)):
        idx.add(code, days, s)
    cd, cv = idx.index()
    cat = {"days": cd, "vals": cv, "why": None, "note": "Equal-weighted.", "eligible": 3, "members": 3, "starts": idx.starts}
    row = lambda code, name: {"code": code, "name": name, "amc": "Test Mutual Fund", "category": "Equity Scheme - Flexi Cap Fund", "plan": "Direct",   # noqa: E731
                              "option_label": "Growth", "nav": None, "nav_date": END}
    facts = {"ter": {"value": "0.60% a year"}, "terPct": 0.6}
    out = mc.assemble("5Y", row(1, "A"), row(2, "B"), (days, a, "amfi", None), (days, b, "amfi", None), cat, facts, facts, "Direct")
    assert out["from"] == "2021-10-19" and out["to"] == "2026-10-19" and out["months"] == 60 and not out["pending"]
    r = out["returns"]
    (wd, wv), _ = mc.window(days, a, END.toordinal(), 60)
    assert r["kind"] == "cagr" and r["funds"]["a"]["value"] == round(mc.point_return(wd, wv, True), 2)
    assert r["funds"]["a"]["growth"] == round(10000 * wv[-1] / wv[0])
    assert r["rolling"]["months"] == 12 and r["rolling"]["kind"] == "absolute" and r["rolling"]["funds"]["a"]["count"] > 900
    assert set(r["growth"]) == {"a", "b", "cat"} and r["growth"]["a"]["v"][0] == 10000.0 and len(r["growth"]["a"]["t"]) <= mc.CHART_CAP
    assert len(r["rolling"]["chart"]["b"]["t"]) <= mc.ROLL_CAP
    # A grows 2 points a year faster than B with the same wave shifted: A is ahead in most one-year windows, and above the category average
    con = out["consistency"]
    assert con["rolling"]["n"] == r["rolling"]["funds"]["a"]["count"] and con["rolling"]["a"] > con["rolling"]["b"]
    assert con["months"]["n"] == 60 - 1 and con["years"]["n"] == 4 and [y["year"] for y in con["years"]["rows"]] == [2022, 2023, 2024, 2025]
    assert con["vsCategory"]["a"]["pct"] > 50 and con["vsCategory"]["a"]["n"] == con["rolling"]["n"]
    alpha = out["costs"]["alpha"]
    assert alpha["a"]["value"] > 1 and alpha["b"]["value"] < alpha["a"]["value"] and out["costs"]["alphaBasis"] == "category average"
    risk = out["risk"]["funds"]
    assert risk["a"]["volatility"]["value"] > 0 and risk["a"]["maxDrawdown"]["value"] < 0 and risk["a"]["worstMonth"]["month"]
    assert risk["a"]["sharpe"]["value"] == round((mc.point_return(wd, wv, True) - mc.RISK_FREE) / mc.measure(days, a, END.toordinal(), "5Y")["vol"], 2)
    assert out["category"]["membersAtStart"] == 3 and out["category"]["why"] is None

    # B younger than the period: its figures are empty with the reason, A's stay; nothing about the pair is guessed
    young = [x for x in days if x >= date(2024, 3, 1).toordinal()]
    out = mc.assemble("5Y", row(1, "A"), row(2, "B"), (days, a, "amfi", None), (young, b[-len(young):], "mirror", "note"), cat, facts, facts, "Direct")
    assert out["returns"]["funds"]["b"]["value"] is None and out["why"]["b"].startswith("NAV history on file starts on 1 Mar 2024")
    assert out["returns"]["funds"]["a"]["value"] is not None and out["consistency"]["rolling"]["n"] == 0 and out["consistency"]["rolling"]["why"] == out["why"]["b"]
    assert out["costs"]["alpha"]["b"]["value"] is None and out["funds"]["b"]["history"]["source"] == "mirror"

    # 1 year: total change, three-month windows, no whole calendar year
    out = mc.assemble("1Y", row(1, "A"), row(2, "B"), (days, a, "amfi", None), (days, b, "amfi", None), {"pending": True, "why": "being worked out"}, facts, facts, "Direct")
    assert out["returns"]["kind"] == "absolute" and out["returns"]["rolling"]["months"] == 3 and out["consistency"]["years"]["n"] == 0
    assert out["pending"] and out["category"]["pending"] and out["costs"]["alpha"]["a"] == {"value": None, "why": "being worked out"}


def test_mirror_history_is_used_only_when_it_agrees_with_amfi():
    days = weekdays(date(2014, 1, 1), END)
    navs = grow(days, 0.1)
    payload = {"meta": {"scheme_code": 7}, "status": "SUCCESS",
               "data": [{"date": date.fromordinal(d).strftime("%d-%m-%Y"), "nav": f"{v:.4f}"} for d, v in reversed(list(zip(days, navs)))]}
    row = {"code": 7, "nav": navs[-1], "nav_date": END, "prev_nav": navs[-2], "prev_date": date.fromordinal(days[-2])}
    d, v = mc.parse_full(payload, row)
    assert d[-1] == END.toordinal() and END.toordinal() - d[0] <= mc.CAT_SPAN and v[-1] == navs[-1]
    assert mc.parse_full(payload, {**row, "code": 8}) is None
    assert mc.parse_full(payload, {**row, "nav": navs[-1] + 1, "prev_nav": navs[-2] + 1}) is None
    lagging = {**payload, "data": payload["data"][1:]}       # the mirror is a day behind AMFI: accepted when it has AMFI's previous NAV
    assert mc.parse_full(lagging, row)[0][-1] == days[-2]
    assert mc.parse_full({**row}, row) is None


# ---------------------------------------------------------------------------------------------- database + API

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test_c")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/14")
needs_db = pytest.mark.integration
FLEXI, LARGE = "Equity Scheme - Flexi Cap Fund", "Equity Scheme - Large Cap Fund"
A, B, C, D, A_REG, A_IDCW, OTHER, STOPPED = 900001, 900002, 900003, 900004, 900011, 900021, 900005, 900006
ALL_DAYS = weekdays(date(2015, 6, 1), END)
SERIES = {A: (ALL_DAYS, grow(ALL_DAYS, 0.13, 0.04, 0.0)), B: (ALL_DAYS, grow(ALL_DAYS, 0.11, 0.04, 1.5)), C: (ALL_DAYS, grow(ALL_DAYS, 0.09, 0.02, 3.0))}
_young = [d for d in ALL_DAYS if d >= date(2024, 3, 1).toordinal()]
SERIES[D] = (_young, grow(_young, 0.15, 0.02))
_reg = SERIES[A][1]
SERIES[A_REG] = (ALL_DAYS, [round(x * 0.9, 4) for x in _reg])
SERIES[OTHER] = (ALL_DAYS, grow(ALL_DAYS, 0.1))


def scheme(code, name, category=FLEXI, plan="Direct", option="Growth", active=True):
    days, navs = SERIES.get(code, SERIES[A])
    stem = name.split(" - ")[0].lower()
    return (code, name, "Test Mutual Fund", "Open Ended", category, plan, option, option, f"test|{category}|{stem}", navs[-1], date.fromordinal(days[-1]),
            navs[-2], date.fromordinal(days[-2]), active)


SCHEMES = [scheme(A, "Alpha Flexi Cap Fund - Direct Plan - Growth"), scheme(B, "Beta Flexi Cap Fund - Direct Plan - Growth"),
           scheme(C, "Gamma Flexi Cap Fund - Direct Plan - Growth"), scheme(D, "Delta Flexi Cap Fund - Direct Plan - Growth"),
           scheme(A_REG, "Alpha Flexi Cap Fund - Regular Plan - Growth", plan="Regular"), scheme(A_IDCW, "Alpha Flexi Cap Fund - Direct Plan - IDCW", option="IDCW"),
           scheme(OTHER, "Omega Large Cap Fund - Direct Plan - Growth", category=LARGE), scheme(STOPPED, "Zeta Flexi Cap Fund - Direct Plan - Growth", active=False)]


class Mirror:
    """api.mfapi.in stand-in: the full fixture history of each code, newest first, as the mirror answers; counts calls per code."""

    def __init__(self, delay=0.0, shift=None, fail=()):
        self.fail = set(fail)
        self.calls = {}
        self.delay = delay
        self.shift = shift or {}

    def client(self):
        async def handler(request):
            code = int(request.url.path.rsplit("/", 1)[1])
            self.calls[code] = self.calls.get(code, 0) + 1
            if self.delay:
                await asyncio.sleep(self.delay)
            if code not in SERIES or code in self.fail:
                return httpx.Response(503)
            days, navs = SERIES[code]
            return httpx.Response(200, json={"meta": {"scheme_code": code}, "status": "SUCCESS",
                                             "data": [{"date": date.fromordinal(d).strftime("%d-%m-%Y"), "nav": f"{v + self.shift.get(code, 0):.4f}"}
                                                      for d, v in reversed(list(zip(days, navs)))]})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    @property
    def total(self):
        return sum(self.calls.values())


@pytest.fixture
async def store():
    settings = Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        s = await Store.connect(settings, migrate=True)
        await s.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with s.pool.acquire() as conn:
        await conn.execute("TRUNCATE mf_cat_avg, mf_history, mf_backfill, mf_meta, mf_facts, mf_schemes CASCADE")
        await conn.executemany("""INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, option_label, family, nav, nav_date,
                                                          prev_nav, prev_date, active) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""", SCHEMES)
        # AMFI's own five years are stored for A and B (the hot path); C and D are cold (the mirror serves them)
        rows = []
        for code in (A, B):
            days, navs = mf.trim(*SERIES[code])
            rows.append((code, len(days), date.fromordinal(days[0]), date.fromordinal(days[-1]), mf.pack_series(days, navs), True, "amfi"))
        await conn.executemany(mf.HIST_UPSERT, rows)
        await conn.execute("UPDATE mf_schemes SET has_hist = true WHERE code = ANY($1::int[])", [A, B])
    async for k in s.redis.scan_iter("mf:*"):
        await s.redis.delete(k)
    yield s
    await s.close()


@pytest.fixture
async def api(store):
    app = FastAPI()
    app.include_router(mf.router)
    app.include_router(mc.router)
    app.state.store = store
    app.state.settings = None
    app.state.mirror = Mirror()
    app.state.mf_client = app.state.mirror.client()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.app = app
        yield c


@needs_db
async def test_categories_and_fund_lists(api):
    cats = (await api.get("/api/mf-compare/categories")).json()
    assert [c["name"] for c in cats["categories"]] == [FLEXI]          # Large Cap has one fund only: nothing to compare
    assert cats["categories"][0] == {"name": FLEXI, "short": "Flexi Cap Fund", "group": "Equity Scheme", "direct": 4, "regular": 1, "variants": [FLEXI]}
    assert cats["disclaimer"] == mf.DISCLAIMER
    d = (await api.get("/api/mf-compare/funds", params={"category": FLEXI})).json()
    assert [f["code"] for f in d["funds"]] == [A, B, D, C] and d["plan"] == "Direct"   # A to Z; IDCW, Regular and stopped options are not offered
    assert set(d["funds"][0]) == {"code", "name", "amc", "launch", "r1y", "r5y"}
    reg = (await api.get("/api/mf-compare/funds", params={"category": FLEXI, "plan": "Regular"})).json()
    assert [f["code"] for f in reg["funds"]] == [A_REG]
    assert (await api.get("/api/mf-compare/funds", params={"category": FLEXI, "plan": "Both"})).status_code == 422


@needs_db
async def test_head_to_head_shape_and_numbers(api):
    r = await api.get(f"/api/mf-compare?a={A}&b={B}&period=3Y")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["period"] == "3Y" and d["to"] == END.isoformat() and d["from"] == "2023-10-19" and d["pending"] is False
    assert d["funds"]["a"]["code"] == A and d["funds"]["b"]["history"]["source"] == "amfi" and d["planNote"] is None
    for key in ("returns", "risk", "consistency", "costs", "category"):
        assert key in d
    # the API's figures are the pure functions' on the same NAVs
    (wd, wv), _ = mc.window(*SERIES[A], END.toordinal(), 36)
    assert d["returns"]["funds"]["a"]["value"] == round(mc.point_return(wd, wv, True), 2)
    assert d["returns"]["rolling"]["months"] == 12 and set(d["returns"]["rolling"]["chart"]) == {"a", "b", "cat"}
    cat = d["category"]
    assert cat["members"] == 4 and cat["eligible"] == 4 and cat["membersAtStart"] == 3 and cat["why"] is None and "Equal-weighted" in cat["note"]
    assert d["returns"]["funds"]["cat"]["value"] is not None
    assert abs(d["costs"]["alpha"]["a"]["value"] - (d["returns"]["funds"]["a"]["value"] - d["returns"]["funds"]["cat"]["value"])) <= 0.011   # both sides rounded
    facts = d["costs"]["funds"]["a"]
    assert set(facts) == {"ter", "terPct", "aum", "exitLoad", "benchmark", "managers", "riskometer", "launchDate"} and "unavailable" in facts["exitLoad"]
    assert d["risk"]["riskFree"] == 6.0 and "assumption" in d["risk"]["note"]
    assert d["consistency"]["rolling"]["n"] > 400 and d["consistency"]["years"]["n"] == 2
    assert d["disclaimer"] == mf.DISCLAIMER
    # the category average was built once (four NAV histories from the mirror) and is read from mf_cat_avg afterwards
    mirror = api.app.state.mirror
    assert mirror.calls == {A: 1, B: 1, C: 1, D: 1}
    async with api.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT nav_date, members, n, codes FROM mf_cat_avg WHERE category = $1 AND plan = 'Direct'", "equityschemeflexicap")
    assert row["nav_date"] == END and row["members"] == 4 and row["n"] > 2000 and sorted(row["codes"]) == [A, B, C, D]
    five = (await api.get(f"/api/mf-compare?a={B}&b={A}&period=5Y")).json()
    assert mirror.total == 4 and five["funds"]["a"]["code"] == B and five["consistency"]["years"]["n"] == 4
    again = await api.get(f"/api/mf-compare?a={A}&b={B}&period=3Y", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304


@needs_db
async def test_ten_years_come_from_the_mirror_and_young_funds_say_why(api):
    d = (await api.get(f"/api/mf-compare?a={A}&b={B}&period=10Y")).json()
    assert d["from"] == "2016-10-19" and d["funds"]["a"]["history"]["source"] == "mirror" and "api.mfapi.in" in d["funds"]["a"]["history"]["note"]
    assert d["returns"]["rolling"]["months"] == 36 and d["returns"]["rolling"]["kind"] == "cagr"
    assert d["returns"]["funds"]["a"]["value"] is not None and d["returns"]["funds"]["cat"]["value"] is not None
    assert d["consistency"]["years"]["n"] == 9
    young = (await api.get(f"/api/mf-compare?a={A}&b={D}&period=5Y")).json()
    assert young["returns"]["funds"]["b"]["value"] is None and young["why"]["b"].startswith("NAV history on file starts on")
    assert young["returns"]["funds"]["a"]["value"] is not None


@needs_db
async def test_ten_years_need_a_mirror_that_agrees_with_amfi(api):
    api.app.state.mf_client = Mirror(shift={A: 0.5}).client()
    d = (await api.get(f"/api/mf-compare?a={A}&b={B}&period=10Y")).json()
    # A's mirror history disagrees with AMFI's NAV: only AMFI's five stored years are used, so ten years cannot be shown for it
    assert d["funds"]["a"]["history"]["source"] == "amfi" and d["returns"]["funds"]["a"]["value"] is None and "less than 10 years" in d["why"]["a"]


@needs_db
async def test_category_average_pending_answer_is_not_cached(api, monkeypatch):
    monkeypatch.setattr(mc, "CAT_WAIT", 0.0)
    api.app.state.mf_client = Mirror(delay=0.2).client()
    r = await api.get(f"/api/mf-compare?a={A}&b={C}&period=1Y")
    d = r.json()
    assert d["pending"] is True and d["category"]["pending"] and "being worked out" in d["category"]["why"] and r.headers["cache-control"] == "no-store"
    assert d["returns"]["funds"]["a"]["value"] is not None            # the two funds' own figures do not wait for the average
    for _ in range(100):
        if not mc._tasks:
            break
        await asyncio.sleep(0.05)
    d = (await api.get(f"/api/mf-compare?a={A}&b={C}&period=1Y")).json()
    assert d["pending"] is False and d["returns"]["funds"]["cat"]["value"] is not None


@needs_db
async def test_refusals(api):
    assert (await api.get(f"/api/mf-compare?a={A}&b={A}")).status_code == 400
    assert (await api.get(f"/api/mf-compare?a={A}&b={OTHER}")).json()["detail"]["detail"].startswith("Fund Compare puts two funds of the same category")
    assert (await api.get(f"/api/mf-compare?a={A_IDCW}&b={B}")).status_code == 400
    assert (await api.get(f"/api/mf-compare?a={A}&b={STOPPED}")).status_code == 400
    assert (await api.get(f"/api/mf-compare?a={A}&b=999999")).status_code == 404
    assert (await api.get(f"/api/mf-compare?a={A}&b={B}&period=2Y")).status_code == 422
    assert (await api.get(f"/api/mf-compare?a=x&b={B}")).status_code == 422
    # the old /api/mf routes are untouched by the new prefix
    assert (await api.get(f"/api/mf/compare?ids={A},{B}")).status_code == 200


@needs_db
async def test_regular_plans_use_a_regular_category_average(api):
    async with api.app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET plan = 'Regular' WHERE code = ANY($1::int[])", [B, C])
    d = (await api.get(f"/api/mf-compare?a={A_REG}&b={B}&period=3Y")).json()
    assert d["category"]["plan"] == "Regular" and d["category"]["members"] == 3 and d["planNote"] is None
    mixed = (await api.get(f"/api/mf-compare?a={A}&b={B}&period=3Y")).json()
    assert mixed["planNote"] and mixed["category"]["plan"] == "Direct"
    # only two Direct funds are left (A and D): too few for an average, and the reason is given
    assert mixed["category"]["why"].startswith("Fewer than 3 funds") and mixed["costs"]["alpha"]["a"]["value"] is None


def test_category_keys_join_the_two_wordings_amfi_uses_and_nothing_else():
    k = mc.cat_key
    assert k("Equity Scheme - Flexi Cap Fund") == k("Equity Schemes - Flexi Cap Fund") == "equityschemeflexicap"
    assert k("Hybrid Scheme - Equity Savings") == k("Hybrid Schemes - Equity Savings Fund")
    assert k("Equity Scheme - ELSS") == k("Equity Schemes - ELSS- Tax Saver Fund")
    assert k("Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage") == k("Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation")
    assert k("Solution Oriented Scheme - Retirement Fund") == k("Solution Oriented Schemes ** - Retirement Fund")
    assert k("Equity Scheme - Large Cap Fund") != k("Equity Scheme - Large & Mid Cap Fund")
    assert k("Debt Scheme - Liquid Fund") != k("Income/Debt Oriented Schemes - Liquid Fund")
    assert k("Equity Scheme - Sectoral/ Thematic") != k("Equity Schemes - Sectoral Fund")


@needs_db
async def test_both_wordings_of_a_category_are_one_category(api):
    new_wording = "Equity Schemes - Flexi Cap Fund"
    row = scheme(OTHER, "Epsilon Flexi Cap Fund - Direct Plan - Growth", category=new_wording)
    async with api.app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET category = $2, name = $3, family = $4 WHERE code = $1", OTHER, new_wording, row[1], row[8])
    cats = (await api.get("/api/mf-compare/categories")).json()["categories"]
    assert len(cats) == 1 and cats[0]["name"] == FLEXI and cats[0]["direct"] == 5 and cats[0]["variants"] == [FLEXI, new_wording]
    for name in (FLEXI, new_wording):
        got = (await api.get("/api/mf-compare/funds", params={"category": name})).json()["funds"]
        assert [f["code"] for f in got] == [A, B, D, OTHER, C]
    d = await api.get(f"/api/mf-compare?a={A}&b={OTHER}&period=3Y")
    assert d.status_code == 200 and d.json()["category"]["members"] == 5


@needs_db
async def test_an_answer_missing_a_funds_history_is_not_kept_for_hours(api):
    api.app.state.mf_client = Mirror(fail={C}).client()
    first = await api.get(f"/api/mf-compare?a={A}&b={C}&period=1Y")
    d = first.json()
    assert d["returns"]["funds"]["b"]["value"] is None and d["why"]["b"] and "_nocache" not in d and first.headers["cache-control"] == "no-store"
    api.app.state.mf_client = Mirror().client()
    await api.app.state.store.redis.delete(f"mf:cold:{C}")   # the failed fetch is remembered for ten minutes by mf.py; the mirror is back now
    again = (await api.get(f"/api/mf-compare?a={A}&b={C}&period=1Y")).json()
    assert again["returns"]["funds"]["b"]["value"] is not None


def test_a_mostly_failed_category_average_is_retried_after_fifteen_minutes():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    row = lambda members, eligible, age: {"members": members, "eligible": eligible, "built_at": now - timedelta(minutes=age)}   # noqa: E731
    assert not mc._partial(row(2, 39, 5)) and mc._partial(row(2, 39, 20))       # too few members, but only once it is old enough
    assert not mc._partial(row(39, 39, 600)) and not mc._partial(row(30, 39, 600))
    assert not mc._partial(row(70, 200, 600)) and mc._partial(row(30, 200, 600))   # at most CAT_MAX (60) funds are used, so 70% of 60
