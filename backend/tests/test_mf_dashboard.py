"""Mutual funds, part 3: the category dashboard of /funds (finlit/mf.py): SIP returns (XIRR) from month-end NAVs, AMFI category names sorted into
tabs and sub-categories, the multi-category list filter, fund size / expense ratio per scheme and the checklist.

The XIRR cases are worked by hand or are the spreadsheet documentation's own example; the SIP figure of Axis Large Cap Fund is worked out again in this
file from the recorded AMFI history lines with separate, plain code (month-end NAVs, units bought, bisection)."""

import calendar
from datetime import date, timedelta

import httpx
import pytest

from finlit import mf
from test_mf import HISTORY, LARGE, LIQUID, amfi_client, api, history_series, loaded, store  # noqa: F401  (fixtures)

D = lambda y, m, d: date(y, m, d).toordinal()   # noqa: E731


# ---------------------------------------------------------------------------------------------- XIRR and SIP maths

def test_xirr_matches_the_spreadsheet_example_and_simple_cases():
    # the example in the spreadsheet documentation of XIRR: 0.373362535
    flows = [(D(2008, 1, 1), -10000), (D(2008, 3, 1), 2750), (D(2008, 10, 30), 4250), (D(2009, 2, 15), 3250), (D(2009, 4, 1), 2750)]
    assert mf.xirr(flows) == pytest.approx(0.373362535, abs=1e-8)
    assert mf.xirr([(D(2020, 1, 1), -100), (D(2021, 1, 1), 110)]) == pytest.approx((110 / 100) ** (365 / 366) - 1)   # 2020 has 366 days
    assert mf.xirr([(D(2021, 1, 1), -100), (D(2022, 1, 1), 50)]) == pytest.approx(-0.5)
    assert mf.xirr([(D(2021, 1, 1), -100), (D(2022, 1, 1), 100)]) == pytest.approx(0.0, abs=1e-12)
    assert mf.xirr([(D(2021, 1, 1), -100), (D(2022, 1, 1), -100)]) is None and mf.xirr([]) is None   # no receipt: no rate


def _daily(start: date, end: date, nav_at):
    days = [d for d in range(start.toordinal(), end.toordinal() + 1) if date.fromordinal(d).weekday() < 5]
    return days, [nav_at(d) for d in days]


def test_sip_of_a_fund_growing_steadily_returns_exactly_that_rate():
    t0 = date(2019, 1, 1).toordinal()
    days, navs = _daily(date(2019, 1, 1), date(2026, 10, 19), lambda d: 10 * 1.12 ** ((d - t0) / 365))
    md, mv = mf.month_ends(days, navs)
    for months in (36, 60):
        assert mf.sip_return(md, mv, days[-1], navs[-1], months) == pytest.approx(12.0, abs=1e-7)
    flat_d, flat_v = _daily(date(2019, 1, 1), date(2026, 10, 19), lambda d: 25.0)
    fd, fv = mf.month_ends(flat_d, flat_v)
    assert mf.sip_return(fd, fv, flat_d[-1], 25.0, 36) == pytest.approx(0.0, abs=1e-9)
    assert mf.fall_monthly(fd, fv, flat_d[-1], 25.0) == 0.0


def test_sip_hand_worked_three_instalments():
    # NAV 10, 20, 40 at three month-ends; value at the latest NAV 40: units 0.1 + 0.05 + 0.025 = 0.175 -> 7.00 for 3.00 paid in
    md = [D(2026, 7, 31), D(2026, 8, 31), D(2026, 9, 30)]
    mv = [10.0, 20.0, 40.0]
    got = mf.sip_return(md, mv, D(2026, 10, 19), 40.0, 3)
    want = mf.xirr([(md[0], -1), (md[1], -1), (md[2], -1), (D(2026, 10, 19), 0.175 * 40)])
    assert got == pytest.approx(want * 100)
    # the rate makes the three payments grow into the value: check it straight from the definition
    r = got / 100
    assert sum((1 + r) ** ((D(2026, 10, 19) - d) / 365) for d in md) == pytest.approx(7.0, rel=1e-9)


def test_sip_needs_every_instalment_month_and_a_fresh_month_end():
    days, navs = _daily(date(2022, 1, 1), date(2026, 10, 19), lambda d: 10 + (d % 7))
    md, mv = mf.month_ends(days, navs)
    assert mf.sip_return(md, mv, days[-1], navs[-1], 36) is not None
    assert mf.sip_return(md, mv, days[-1], navs[-1], 60) is None            # history starts Jan 2022: younger than five years of instalments
    hole = [(d, v) for d, v in zip(md, mv) if not (date.fromordinal(d).year == 2025 and date.fromordinal(d).month == 3)]
    assert mf.sip_return([h[0] for h in hole], [h[1] for h in hole], days[-1], navs[-1], 36) is None   # March 2025 missing
    stale = [(D(2025, 3, 20) if date.fromordinal(d).year == 2025 and date.fromordinal(d).month == 3 else d, v) for d, v in zip(md, mv)]
    assert mf.sip_return([s[0] for s in stale], [s[1] for s in stale], days[-1], navs[-1], 36) is None  # its last NAV is 11 days before the month's end
    assert mf.sip_return(md, mv, days[-1], None, 36) is None and mf.sip_return([], [], days[-1], 10.0, 36) is None


def test_month_ends_merge_and_the_month_end_fall():
    days = [D(2026, 1, 5), D(2026, 1, 30), D(2026, 2, 2), D(2026, 2, 27), D(2026, 3, 3)]
    md, mv = mf.month_ends(days, [1, 2, 3, 4, 5])
    assert md == [D(2026, 1, 30), D(2026, 2, 27), D(2026, 3, 3)] and mv == [2, 4, 5]
    d, v = mf.merge_months((md, mv), ([D(2026, 2, 28)], [4.5]), ([D(2026, 3, 1)], [9]))   # a later day of a month wins; an earlier one does not
    assert d == [D(2026, 1, 30), D(2026, 2, 28), D(2026, 3, 3)] and v == [2, 4.5, 5]
    assert len(mf.merge_months((list(range(D(2010, 1, 1), D(2026, 1, 1), 30)), [1.0] * 195))[0]) == mf.MONTHLY_KEEP
    # 36 month-ends: up from 100 to 150, down to 90, back to 120; the largest fall is 150 -> 90
    ends = [mf.month_last_day(mf.month_key(D(2023, 10, 1)) + i) for i in range(36)]
    vals = [100 + 50 * i / 11 for i in range(12)] + [150 - 60 * i / 11 for i in range(12)] + [90 + 30 * i / 11 for i in range(12)]
    assert mf.fall_monthly(ends, vals, D(2026, 10, 19), 120.0) == pytest.approx((90 / 150 - 1) * 100)
    assert mf.fall_monthly(ends[5:], vals[5:], D(2026, 10, 19), 120.0) is None   # does not reach back three years


# ---------------------------------------------------------------------------------------------- categories

REAL = {   # AMFI category names as stored from NAVAll.txt (both generations of names), and where the page files them
    "Equity Scheme - Large Cap Fund": ("equity", "large-cap"), "Equity Schemes - Large Cap Fund": ("equity", "large-cap"),
    "Equity Scheme - Large & Mid Cap Fund": ("equity", "large-mid-cap"), "Equity Schemes - Large & Mid Cap Fund": ("equity", "large-mid-cap"),
    "Equity Scheme - ELSS": ("equity", "elss"), "Equity Schemes - ELSS- Tax Saver Fund": ("equity", "elss"), "ELSS": ("equity", "elss"),
    "Equity Scheme - Sectoral/ Thematic": ("equity", "sectoral-thematic"), "Equity Schemes - Sectoral Fund": ("equity", "sectoral-thematic"),
    "Equity Schemes - Thematic Fund": ("equity", "sectoral-thematic"), "Equity Scheme - Flexi Cap Fund": ("equity", "flexi-cap"),
    "Equity Scheme - Small Cap Fund": ("equity", "small-cap"), "Equity Scheme - Mid Cap Fund": ("equity", "mid-cap"), "Equity Scheme - Multi Cap Fund": ("equity", "multi-cap"),
    "Equity Scheme - Contra Fund": ("equity", "contra"), "Equity Scheme - Dividend Yield Fund": ("equity", "dividend-yield"), "Equity Scheme - Value Fund": ("equity", "value"),
    "Equity Scheme - Focused Fund": ("equity", "focused"), "Growth": ("equity", "equity-other"),
    "Debt Scheme - Money Market Fund": ("debt", "money-market"), "Income/Debt Oriented Schemes - Money Market Fund": ("debt", "money-market"),
    "Debt Scheme - Corporate Bond Fund": ("debt", "corporate-bond"), "Income/Debt Oriented Schemes - Corporate Bond Fund": ("debt", "corporate-bond"),
    "Debt Scheme - Low Duration Fund": ("debt", "low-duration"), "Income/Debt Oriented Schemes - Ultra Short to Short Term Fund": ("debt", "low-duration"),
    "Debt Scheme - Ultra Short Duration Fund": ("debt", "ultra-short"), "Income/Debt Oriented Schemes - Ultra Short Term Fund": ("debt", "ultra-short"),
    "Debt Scheme - Medium to Long Duration Fund": ("debt", "medium-long-duration"), "Income/Debt Oriented Schemes - Medium Term Fund": ("debt", "medium-duration"),
    "Income/Debt Oriented Schemes - Long Term Fund": ("debt", "long-duration"), "Debt Scheme - Short Duration Fund": ("debt", "short-duration"),
    "Income/Debt Oriented Schemes - 10-year Constant Maturity Gilt Fund": ("debt", "gilt-10y"), "Debt Scheme - Gilt Fund": ("debt", "gilt"),
    "Income/Debt Oriented Schemes - Dynamic Term Fund": ("debt", "dynamic-bond"), "Income/Debt Oriented Schemes - Floating Interest Rates Fund": ("debt", "floater"),
    "Income/Debt Oriented Schemes - Banking and PSU Debt Fund": ("debt", "banking-psu"), "Debt Scheme - Banking and PSU Fund": ("debt", "banking-psu"),
    "Income/Debt Oriented Schemes - Fixed Term Plan": ("debt", "fixed-term"), "Income": ("debt", "fixed-term"), "Debt Scheme - Overnight Fund": ("debt", "overnight"),
    "Income/Debt Oriented Schemes - Liquid Fund": ("debt", "liquid"), "Income/Debt Oriented Schemes - Other Debt Scheme": ("debt", "debt-other"),
    "Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage": ("hybrid", "balanced-advantage"),
    "Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation": ("hybrid", "balanced-advantage"), "Hybrid Schemes - Balanced Hybrid Fund": ("hybrid", "balanced-hybrid"),
    "Hybrid Scheme - Aggressive Hybrid Fund": ("hybrid", "aggressive-hybrid"), "Hybrid Schemes - Equity Savings Fund": ("hybrid", "equity-savings"),
    "Hybrid Scheme - Arbitrage Fund": ("hybrid", "arbitrage"), "Hybrid Schemes - Multi Asset Allocation Fund": ("hybrid", "multi-asset"),
    "Hybrid Scheme - Conservative Hybrid Fund": ("hybrid", "conservative-hybrid"),
    "Solution Oriented Scheme - Retirement Fund": ("solution", "retirement"), "Solution Oriented Schemes ** - Retirement Fund": ("solution", "retirement"),
    "Solution Oriented Scheme - Children’s Fund": ("solution", "childrens"), "Children’s Fund - Childrens' Fund": ("solution", "childrens"),
    "Life Cycle Funds - Life Cycle Fund with Maturity of 10 Years": ("solution", "life-cycle"),
    "Other Scheme - Index Funds": ("other", "index-funds"), "Index Funds - Equity Funds": ("other", "index-funds"), "Index Funds - Debt Funds": ("other", "index-debt"),
    "Other Scheme - Gold ETF": ("other", "gold-etf"), "Exchange Traded Funds (ETFs) - Gold ETF": ("other", "gold-etf"), "Exchange Traded Funds (ETFs) - Silver ETF": ("other", "silver-etf"),
    "Exchange Traded Funds (ETFs) - Debt ETF": ("other", "etf-debt"), "Other Scheme - Other ETFs": ("other", "etf"), "Exchange Traded Funds (ETFs) - Equity ETF": ("other", "etf"),
    "Other Scheme - FoF Overseas": ("other", "fof-overseas"), "Overseas Fund of Funds - Fund of Funds investing overseas": ("other", "fof-overseas"),
    "Other Scheme - FoF Domestic": ("other", "fof-domestic"), "Fund of Funds Scheme (Domestic) - Fund of Funds Scheme (Domestic)": ("other", "fof-domestic"),
    "Something New - Never Seen": ("other", "other"),
}


@pytest.mark.parametrize("name,want", list(REAL.items()))
def test_every_amfi_category_lands_in_one_tab_and_sub_category(name, want):
    tab, key, label = mf.classify(name)
    assert (tab, key) == want and label


def test_card_categories_have_the_owner_labels():
    assert mf.classify("Equity Scheme - ELSS")[2] == "ELSS (Tax Savings)" and mf.classify("Equity Scheme - Large & Mid Cap Fund")[2] == "Large & Mid Cap"
    assert [k for k, _ in mf.TABS] == ["equity", "hybrid", "debt", "solution", "other"]


# ---------------------------------------------------------------------------------------------- database: SIP figures for every scheme

def _hand_sip(code, months, end_day, end_nav):
    """The SIP return straight from the recorded history lines: last NAV of each calendar month, one unit of money each month, bisection on the rate."""
    last = {}
    for line in HISTORY.split("\n"):
        f = line.strip().split(";")
        if len(f) >= 8 and f[0] == str(code):
            d = mf.parse_date(f[7])
            if (d.year, d.month) not in last or d > last[(d.year, d.month)][0]:
                last[(d.year, d.month)] = (d, float(f[6]))
    y, m = end_day.year, end_day.month
    paid = []
    for _ in range(months):
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        d, nav = last[(y, m)]
        assert d.day >= calendar.monthrange(y, m)[1] - 7
        paid.append((d, nav))
    value = sum(1 / nav for _, nav in paid) * end_nav
    lo, hi = -0.99, 5.0
    for _ in range(200):
        r = (lo + hi) / 2
        grown = sum((1 + r) ** ((end_day - d).days / 365) for d, _ in paid)
        lo, hi = (r, hi) if grown < value else (lo, r)
    return r * 100


@pytest.mark.integration
async def test_sip_figures_from_the_daily_series_match_the_hand_worked_ones(loaded):
    async with loaded.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT sip3y, sip5y, mdd3y_m, nav, nav_date FROM mf_schemes WHERE code = $1", LARGE)
        m = await conn.fetchrow("SELECT days, navs FROM mf_monthly WHERE code = $1", LARGE)
    assert r["sip3y"] == pytest.approx(_hand_sip(LARGE, 36, r["nav_date"], r["nav"]), abs=1e-6)
    assert r["sip5y"] == pytest.approx(_hand_sip(LARGE, 60, r["nav_date"], r["nav"]), abs=1e-6)
    assert r["mdd3y_m"] is not None and r["mdd3y_m"] <= 0
    assert m and m["days"][-1] == date(2026, 10, 19) and 58 <= len(m["days"]) <= mf.MONTHLY_KEEP   # month-ends of the backfilled series are kept for later


@pytest.mark.integration
async def test_month_ends_read_from_amfi_give_the_same_sip_figures_and_are_read_once(loaded):
    """A scheme without a stored daily series: its month-ends come from AMFI's industry-wide history (one window a month), and the SIP figures equal
    those worked out from the full daily series."""
    async with loaded.pool.acquire() as conn:
        want = {r["code"]: (r["sip3y"], r["sip5y"], r["mdd3y_m"]) for r in await conn.fetch("SELECT code, sip3y, sip5y, mdd3y_m FROM mf_schemes WHERE code = ANY($1::int[])", [LARGE, LIQUID])}
        await conn.execute("DELETE FROM mf_history")
        await conn.execute("DELETE FROM mf_monthly")
        await conn.execute("DELETE FROM mf_meta WHERE key = 'monthly'")
        await conn.execute("UPDATE mf_schemes SET sip3y = NULL, sip5y = NULL, mdd3y_m = NULL")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, content=HISTORY.encode())   # every window answers with the recorded history; only the window's days are used
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        out = await mf.refresh_monthly(loaded, c, date(2026, 10, 20))
        again = await mf.refresh_monthly(loaded, c, date(2026, 10, 20))
    assert out["monthsRead"] == 60 and out["monthsMissing"] == 0 and len(seen) == 60 and "mf" not in seen[0]   # every fund house at once
    assert seen[0] == {"frmdt": "23-Sep-2026", "todt": "30-Sep-2026"} and seen[-1]["todt"] == "31-Oct-2021"   # newest month first, its last 8 days
    assert again["monthsRead"] == 0 and len(seen) == 60   # read once, remembered in mf_meta
    async with loaded.pool.acquire() as conn:
        got = {r["code"]: (r["sip3y"], r["sip5y"], r["mdd3y_m"]) for r in await conn.fetch("SELECT code, sip3y, sip5y, mdd3y_m FROM mf_schemes WHERE code = ANY($1::int[])", [LARGE, LIQUID])}
    for code in want:
        assert got[code] == pytest.approx(want[code]), code


@pytest.mark.integration
async def test_month_end_downloads_stop_after_three_failures_and_keep_the_rest(loaded):
    calls = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(200, text="<html>form</html>"))) as c:
        out = await mf.refresh_monthly(loaded, c, date(2026, 10, 20))
    assert len(calls) == mf.MONTH_FILL_FAILS and out["monthsFailed"] == 3 and out["monthsMissing"] == 60
    async with loaded.pool.acquire() as conn:   # the figures from the stored daily series are untouched
        assert await conn.fetchval("SELECT sip3y FROM mf_schemes WHERE code = $1", LARGE) is not None


# ---------------------------------------------------------------------------------------------- database: list filters

@pytest.mark.integration
async def test_list_filters_by_several_categories_and_by_tab(api):
    one = (await api.get("/api/mf?category=Equity Schemes - Large Cap Fund&option=All")).json()["total"]
    two = (await api.get("/api/mf", params=[("categories", "Equity Schemes - Large Cap Fund"), ("categories", "Equity Schemes - Thematic Fund"), ("option", "All")])).json()
    assert one == 1 and two["total"] == 3 and {i["category"] for i in two["items"]} == {"Equity Schemes - Large Cap Fund", "Equity Schemes - Thematic Fund"}
    eq = (await api.get("/api/mf?group=equity&option=All")).json()
    assert eq["total"] == 4 and all(mf.classify(i["category"])[0] == "equity" for i in eq["items"])   # large cap, two thematic and a closed-ended ELSS
    debt = (await api.get("/api/mf?group=debt&option=All&stopped=true")).json()
    assert {i["category"] for i in debt["items"]} >= {"Debt Scheme - Gilt Fund", "Income/Debt Oriented Schemes - Liquid Fund", "Income"}
    both = (await api.get("/api/mf", params=[("group", "debt"), ("categories", "Equity Schemes - Large Cap Fund")])).json()
    assert both["total"] == 0   # every filter given must hold
    assert (await api.get("/api/mf?group=bonds")).status_code == 400
    assert (await api.get("/api/mf", params=[("categories", f"x{i}") for i in range(81)])).status_code == 400
    assert (await api.get("/api/mf?categories=Nope")).json()["total"] == 0


@pytest.mark.integration
async def test_filters_name_the_tab_sub_category_and_growth_counts(api):
    f = (await api.get("/api/mf/filters")).json()
    cats = {c["name"]: c for c in f["categories"]}
    lc = cats["Equity Schemes - Large Cap Fund"]
    assert (lc["tab"], lc["key"], lc["label"]) == ("equity", "large-cap", "Large Cap") and lc["growth"] == 1 and lc["direct"] == 1 and lc["regular"] == 0
    assert cats["Children’s Fund - Childrens' Fund"]["tab"] == "solution" and cats["Children’s Fund - Childrens' Fund"]["direct"] == 1
    assert [t["key"] for t in f["tabs"]] == ["equity", "hybrid", "debt", "solution", "other"]


# ---------------------------------------------------------------------------------------------- database: fund size, expense ratio, checklist

CAT_NEW, CAT_OLD = "Equity Scheme - Small Cap Fund", "Equity Schemes - Small Cap Fund"   # the two spellings: one peer group


async def _seed(conn):
    """Six Direct Growth small-cap schemes (A..F, one filed under the older spelling) and a Regular plan of A; facts and TER for some."""
    rows = [  # code, name, category, plan, r3y, r5y, mdd3y_m
        (900001, "A Small Cap Fund", CAT_NEW, "Direct", 20.0, 25.0, -10.0),
        (900002, "B Small Cap Fund", CAT_NEW, "Direct", 18.0, 22.0, -15.0),
        (900003, "C Small Cap Fund", CAT_NEW, "Direct", 16.0, 18.0, -20.0),
        (900004, "D Small Cap Fund", CAT_OLD, "Direct", 14.0, 15.0, -25.0),
        (900005, "E Small Cap Fund", CAT_NEW, "Direct", 30.0, None, -30.0),   # younger than 5 years: its return check uses 3 years
        (900006, "F Small Cap Fund", CAT_NEW, "Direct", None, None, None),   # new: nothing to compare yet
        (900007, "A Small Cap Fund", CAT_NEW, "Regular", 19.0, 24.0, -10.0),
    ]
    await conn.executemany("""INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, option_label, family, nav, nav_date, active, r3y, r5y, mdd3y_m)
                              VALUES ($1, $2, 'Test Mutual Fund', 'Open Ended', $3, $4, 'Growth', 'Growth', $5, 10, '2026-10-19', true, $6, $7, $8)""",
                           [(c, n, cat, p, f"test|{cat}|{n.lower()}", r3, r5, dd) for c, n, cat, p, r3, r5, dd in rows])
    # fund size: AMFI's quarterly average for A (both plans add up), month-end net assets for B, nothing for the others; launch dates
    await conn.executemany("INSERT INTO mf_facts (code, base_name, name_key, launch_date, aum_lakh, aum_end, aum_label) VALUES ($1, $2, $3, $4, $5, $6, 'July - September 2026')",
                           [(900001, "A Small Cap Fund", "asmallcapfund", date(2015, 1, 1), 60_000.0, date(2026, 9, 30)),
                            (900007, "A Small Cap Fund", "asmallcapfund", date(2015, 1, 1), 15_000.0, date(2026, 9, 30)),
                            (900002, "B Small Cap Fund", "bsmallcapfund", date(2016, 1, 1), None, None),
                            (900003, "C Small Cap Fund", "csmallcapfund", date(2017, 1, 1), 1_000.0, date(2026, 9, 30)),
                            (900005, "E Small Cap Fund", "esmallcapfund", date(2023, 6, 1), None, None),
                            (900006, "F Small Cap Fund", "fsmallcapfund", None, None, None)])
    await conn.execute("""INSERT INTO disclosure_portfolios (fkey, as_of, amc, scheme_name, source, source_url, net_assets_lakh, pct_total, n, holdings)
                          VALUES ($1, '2026-09-30', 'Test', 'B', 'test', 'https://example.invalid', 52000, 100, 0, '[]'::jsonb)""", f"test|{CAT_NEW}|b small cap fund")
    await conn.executemany("INSERT INTO mf_ter (name_key, name, ter_regular, ter_direct, ter_date) VALUES ($1, $1, $2, $3, '2026-10-01')",
                           [("asmallcapfund", 1.80, 0.40), ("bsmallcapfund", 1.90, 0.60), ("csmallcapfund", 2.00, 0.80), ("esmallcapfund", 2.10, 1.00)])


@pytest.fixture
async def seeded(api):
    store_ = api.app.state.store
    async with store_.pool.acquire() as conn:
        await conn.execute("DELETE FROM disclosure_portfolios WHERE fkey LIKE 'test|%'")
        await conn.execute("DELETE FROM mf_facts WHERE code >= 900000")
        await conn.execute("DELETE FROM mf_ter WHERE name_key LIKE '_smallcapfund'")
        await _seed(conn)
    yield api
    async with store_.pool.acquire() as conn:
        await conn.execute("DELETE FROM disclosure_portfolios WHERE fkey LIKE 'test|%'")
        await conn.execute("DELETE FROM mf_facts WHERE code >= 900000")
        await conn.execute("DELETE FROM mf_ter WHERE name_key LIKE '_smallcapfund'")


@pytest.mark.integration
async def test_fund_size_and_expense_ratio_per_scheme(seeded):
    store_ = seeded.app.state.store
    res = await mf.derive_dashboard(store_)
    assert res["status"] == "ok"
    async with store_.pool.acquire() as conn:
        got = {r["code"]: dict(r) for r in await conn.fetch("SELECT code, aum_lakh, aum_kind, aum_asof, ter FROM mf_schemes WHERE code >= 900000")}
    assert got[900001]["aum_lakh"] == 75_000 and got[900001]["aum_kind"] == "q" and got[900001]["aum_asof"] == date(2026, 9, 30)   # both plans of A together
    assert got[900007]["aum_lakh"] == 75_000
    assert got[900002]["aum_lakh"] == 52_000 and got[900002]["aum_kind"] == "m"    # no quarterly figure: the month-end net assets
    assert got[900004]["aum_lakh"] is None and got[900004]["ter"] is None           # nothing loaded for D
    assert got[900001]["ter"] == 0.40 and got[900007]["ter"] == 1.80               # each plan its own TER
    assert got[900003]["ter"] == 0.80 and got[900003]["aum_lakh"] == 1_000


@pytest.mark.integration
async def test_checklist_rules(seeded):
    store_ = seeded.app.state.store
    await mf.derive_dashboard(store_)
    async with store_.pool.acquire() as conn:
        c = {r["code"]: dict(r) for r in await conn.fetch("SELECT code, chk_pass, chk_known, chk_bits, chk_mask FROM mf_schemes WHERE code >= 900000")}
        dash = await mf._meta(conn, "dashboard")
    peer = dash["peers"]["small-cap|Direct"]
    # Direct peers A B C D E F, both spellings together: 5 year median of 25, 22, 18, 15 = 20; 3 year of 20, 18, 16, 14, 30 = 18; TER of .4 .6 .8 1.0 = 0.7;
    # month-end fall of -10 -15 -20 -25 -30 = -20
    assert peer["n"] == 6 and peer["r5y"] == 20 and peer["n5"] == 4 and peer["r3y"] == 18 and peer["ter"] == 0.7 and peer["fall"] == -20
    bit = lambda code, i: bool(c[code]["chk_bits"] & (1 << i))   # noqa: E731
    known = lambda code, i: bool(c[code]["chk_mask"] & (1 << i))   # noqa: E731
    # A: 5Y 25 > 20 yes, TER .4 < .7 yes, fall -10 > -20 yes, ₹750 crore >= 500 yes, launched 2015 yes -> 5 of 5, its return check used 5 years
    assert (c[900001]["chk_pass"], c[900001]["chk_known"]) == (5, 5) and c[900001]["chk_bits"] & mf.CHECK_RET5_BIT
    # B: 22 > 20, .6 < .7, -15 > -20, ₹520 crore (month-end), launched 2016 -> 5 of 5
    assert (c[900002]["chk_pass"], c[900002]["chk_known"]) == (5, 5)
    # C: 18 < 20 no, .8 no, -20 is not smaller than the median no, ₹10 crore no, 2017 yes -> 1 of 5
    assert (c[900003]["chk_pass"], c[900003]["chk_known"]) == (1, 5) and bit(900003, 4) and not bit(900003, 3)
    # D (older spelling, same peers): 15 no; no TER, no size, no launch date but a 5 year figure -> age passes; fall -25 no -> 1 of 3 known
    assert (c[900004]["chk_pass"], c[900004]["chk_known"]) == (1, 3) and not known(900004, 1) and not known(900004, 3) and bit(900004, 4)
    # E: no 5 year figure, so 3 years: 30 > 18 yes, and the return bit says 3 years; TER 1.0 no; fall -30 no; no size; launched 2023 -> under 5 years, no
    assert bit(900005, 0) and not c[900005]["chk_bits"] & mf.CHECK_RET5_BIT and not bit(900005, 4) and known(900005, 4) and (c[900005]["chk_pass"], c[900005]["chk_known"]) == (1, 4)
    # F: nothing to compare and no launch date -> nothing known
    assert (c[900006]["chk_pass"], c[900006]["chk_known"]) == (0, 0)
    # the Regular plan has only itself as a peer: too few to compare, but size (₹750 crore, the scheme's plans together) and age are known
    assert (c[900007]["chk_pass"], c[900007]["chk_known"]) == (2, 2)
    # the list shows it with the peer medians it used, and sorts by it
    body = (await seeded.get("/api/mf", params=[("categories", CAT_NEW), ("categories", CAT_OLD), ("plan", "Direct"), ("sort", "checklist"), ("dir", "desc")])).json()
    assert [i["code"] for i in body["items"]][:2] == [900001, 900002] and body["items"][-1]["code"] == 900006
    a = body["items"][0]
    assert a["checklist"] == {"pass": 5, "of": 5, "bits": 63, "mask": 31, "peer": "small-cap|Direct"} and body["peers"]["small-cap|Direct"]["r5y"] == 20
    assert a["aum"] == 750 and a["aumKind"] == "q" and a["ter"] == 0.4 and len(body["checklist"]["checks"]) == 5
    by_size = (await seeded.get("/api/mf", params=[("group", "equity"), ("categories", CAT_NEW), ("categories", CAT_OLD), ("sort", "aum"), ("dir", "desc"), ("plan", "Direct")])).json()["items"]
    assert [i["code"] for i in by_size][:3] == [900001, 900002, 900003] and by_size[-1]["aum"] is None   # schemes without a size last


@pytest.mark.integration
async def test_a_stopped_scheme_loses_its_checklist_and_sip(seeded):
    store_ = seeded.app.state.store
    await mf.derive_dashboard(store_)
    async with store_.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET active = false, sip3y = 1 WHERE code = 900003")
    await mf.derive_dashboard(store_)
    await mf.refresh_monthly(store_, None, date(2026, 10, 20))
    async with store_.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT chk_mask, sip3y FROM mf_schemes WHERE code = 900003")
    assert r["chk_mask"] is None and r["sip3y"] is None


async def test_boot_refresh_is_not_skipped_while_the_dashboard_columns_are_empty(store):
    """A deploy that added fund size / SIP / checklist after the last refresh ran must not wait for the next nightly run."""
    from finlit.worker import _mf_dashboard_empty
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_schemes")
        await conn.execute("INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, family) VALUES (999101, 'Empty Cols Fund', 'X Mutual Fund', 'Open Ended', 'x', 'Direct', 'Growth', 'f')")
    assert await _mf_dashboard_empty(store) is True
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET sip3y = 12.5 WHERE code = 999101")
    assert await _mf_dashboard_empty(store) is False
