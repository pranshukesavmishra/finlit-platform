"""Mutual funds (finlit/mf.py): AMFI parsing, packed series, returns maths, search, the refusal rules, the nightly job and the API.

Fixtures in tests/fixtures/mf are real AMFI / mfapi.in answers recorded on 2026-10-21:
  navall_sample.txt         NAVAll.txt trimmed to 13 schemes (headers, a zero-NAV row, a blank-plan ETF, closed-ended and interval funds)
  history_axis_slice.txt    AMFI's own NAV history for four Axis schemes, the five yearly downloads plus the lead-in days, in AMFI's layout
  mfapi_120465.json         api.mfapi.in's answer for one of them (cross-check)
The expected return figures were worked out separately (plain datetime and statistics, straight from the history lines) and are written in as numbers.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finlit import mf
from finlit.config import Settings
from finlit.store import Store

FIX = Path(__file__).parent / "fixtures" / "mf"
NAVALL = (FIX / "navall_sample.txt").read_text(encoding="utf-8")
HISTORY = (FIX / "history_axis_slice.txt").read_text(encoding="utf-8")
LARGE, LIQUID, BUSINESS, CONSUMPTION = 120465, 120389, 151368, 152805


def history_series(code, text=HISTORY):
    days, navs = {}, {}
    for line in text.split("\n"):
        f = line.strip().split(";")
        if len(f) >= 8 and f[0] == str(code):
            days[mf.parse_date(f[7]).toordinal()] = float(f[6])
    ds = sorted(days)
    return ds, [days[d] for d in ds]


# ---------------------------------------------------------------------------------------------- parsing

def test_parse_real_sample_headers_and_fields():
    p = mf.parse_navall(NAVALL)
    assert p.header_ok and len(p.schemes) == 13 and p.newest == date(2026, 10, 20)
    by = {s.code: s for s in p.schemes}
    kids = by[135762]
    assert (kids.amc, kids.category, kids.scheme_type) == ("Axis Mutual Fund", "Children’s Fund - Childrens' Fund", "Open Ended")
    assert (kids.plan, kids.option_class, kids.option_label) == ("Direct", "Growth", "Growth Option")
    assert (kids.isin, kids.isin_reinvest, kids.nav, kids.nav_date) == ("INF846K01WO1", None, 29.1407, date(2026, 10, 19))
    assert by[135765].option_class == "IDCW" and by[135759].plan == "Regular"
    # all four plans of "Axis Children's Fund" are one family; the other funds are not in it
    fam = {by[c].family for c in (135762, 135765, 135759, 135760)}
    assert len(fam) == 1 and by[LARGE].family not in fam
    assert by[LARGE].category == "Equity Schemes - Large Cap Fund" and by[LARGE].nav == 66.74


def test_closed_interval_blank_plan_zero_nav_and_old_rows_are_listed_honestly():
    p = mf.parse_navall(NAVALL)
    by = {s.code: s for s in p.schemes}
    elss, interval = by[141950], by[146839]
    assert (elss.scheme_type, elss.category) == ("Close Ended", "ELSS") and elss.plan == "Direct" and elss.option_class == "Growth"
    assert (interval.scheme_type, interval.category) == ("Interval Fund", "Income") and interval.plan == "Unspecified" and interval.option_class == "Other"
    assert interval.nav == 10.0087785 and interval.isin is None and interval.isin_reinvest == "INF174KA1DD0"
    etf = by[151533]
    assert etf.plan == "Unspecified" and etf.option_class == "Other" and etf.option_label == "Not stated"
    zero = by[148304]   # a real segregated-portfolio row with NAV 0.0000: listed, but with no NAV and no NAV date
    assert zero.nav is None and zero.nav_date is None
    assert p.skipped == {"no usable NAV (N.A., dash, blank or zero)": 1}
    assert by[120607].nav_date == date(2018, 5, 25)   # a stopped scheme keeps its old date


def test_parser_never_raises_and_counts_what_it_leaves_out():
    text = "\n".join([
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date", " ",
        "Open Ended Schemes(Equity Scheme - Mid Cap Fund)", " ", "Test Mutual Fund", " ",
        "1001;INF000A01AA1;-;Test Mid Cap Fund;Direct Plan;Growth;N.A.;19-Oct-2026",
        "1002;-;-;Test Mid Cap Fund;Regular Plan;Growth;-;19-Oct-2026",
        "1003;-;-;Test Mid Cap Fund;Regular Plan;IDCW;12.5;32-Oct-2026",          # impossible date
        "1004;-;-;Test Mid Cap Fund;Regular Plan;IDCW;12.5",                       # short line
        "abc;-;-;Test Mid Cap Fund;Regular Plan;IDCW;12.5;19-Oct-2026",            # not a scheme code
        "1005;-;-;Test Mid Cap Fund;Regular Plan;IDCW;1,234.5;19-Oct-2026",        # thousands comma is not a number AMFI sends
        "1006;-;-;Test Mid Cap Fund;Direct Plan;Growth;45.1234;19-Oct-2026",
        "1006;-;-;Test Mid Cap Fund;Direct Plan;Growth;45.2000;20-Oct-2026",       # repeated code: the later line wins, and it is counted
        "﻿1007;-;-;Dividend Yield Fund;;;10;19-Oct-2026",
    ])
    p = mf.parse_navall(text)
    by = {s.code: s for s in p.schemes}
    assert sorted(by) == [1001, 1002, 1003, 1005, 1006, 1007]
    assert by[1001].nav is None and by[1002].nav is None and by[1003].nav is None and by[1005].nav is None
    assert by[1006].nav == 45.2 and by[1006].nav_date == date(2026, 10, 20)
    assert p.skipped["malformed line"] == 2 and p.skipped["repeated scheme code (last line kept)"] == 1
    assert p.skipped["no usable NAV (N.A., dash, blank or zero)"] == 3 and p.skipped["NAV with an unreadable date"] == 1
    # an option is read from AMFI's column; the name is read only when the column is blank, and only its last part
    assert by[1007].option_class == "Other" and by[1007].plan == "Unspecified"


@pytest.mark.parametrize("raw,name,want", [
    ("Growth Option", "X Fund", ("Growth", "Growth Option")),
    ("GROWTH", "X Fund", ("Growth", "GROWTH")),
    ("Monthly IDCW", "X Fund", ("IDCW", "Monthly IDCW")),
    ("Income Distribution cum capital withdrawal", "X Fund", ("IDCW", "Income Distribution cum capital withdrawal")),
    ("Payout of IDCW", "X Fund", ("IDCW", "Payout of IDCW")),
    ("Bonus", "X Fund", ("Other", "Bonus")),
    ("", "ICICI Prudential Dividend Yield Equity Fund", ("Other", "Not stated")),   # a fund called "Dividend Yield" is not an IDCW option
    ("", "X Fund - Direct Plan - Growth", ("Growth", "Growth")),
    ("", "X Fund - Regular Plan - IDCW", ("IDCW", "IDCW")),
])
def test_option_classes(raw, name, want):
    assert mf.clean_option(raw, name) == want


@pytest.mark.parametrize("name,stem", [
    ("Axis Children's Fund - Direct Plan - Growth Option", "axis children s fund"),
    ("Axis Children's Fund - Regular Plan - Monthly IDCW", "axis children s fund"),
    ("HDFC Mid-Cap Opportunities Fund - Direct Plan - IDCW Payout", "hdfc mid cap opportunities fund"),
    ("X Interval Fund - Monthly Interval Plan I", "x interval fund monthly interval plan i"),     # a frequency alone is part of the name
    ("X Interval Fund - Quarterly Interval Plan I", "x interval fund quarterly interval plan i"),
    ("Aditya Birla Sun Life Liquid Fund - Regular - Payout of Income Distribution cum Capital Withdrawal", "aditya birla sun life liquid fund"),
])
def test_family_stem(name, stem):
    assert mf.family_stem(name) == stem


def test_amc_ids_page_and_name_keys():
    page = 'x{\\"mfId\\":\\"53\\",\\"mfName\\":\\"Axis Mutual Fund\\"},{\\"mfId\\":\\"56\\",\\"mfName\\":\\"L\\u0026T Mutual Fund\\"}'
    assert mf.parse_amc_ids(page) == {"Axis Mutual Fund": 53, "L&T Mutual Fund": 56}
    assert mf.amc_key("ASK MUTUAL FUND") == "ask" and mf.amc_key("quant Mutual Fund") == "quant" and mf.AMC_BY_KEY[mf.amc_key("Axis Mutual Fund")] == 53
    assert len(mf.AMC_IDS) == 76 and len(set(mf.AMC_IDS.values())) == 76


# ---------------------------------------------------------------------------------------------- the file checks

def test_verdict_accepts_the_real_sample_and_refuses_odd_files():
    p = mf.parse_navall(NAVALL)
    assert mf.verdict(p, 13, date(2026, 10, 20), 10) is None
    assert mf.verdict(mf.parse_navall("<html><body>Maintenance</body></html>"), 13, None, 0).startswith("the file does not start with AMFI")
    header_only = mf.parse_navall(NAVALL.split("\n")[0] + "\n")
    assert mf.verdict(header_only, 13, None, 0) == "no scheme rows could be read"
    short = mf.parse_navall("\n".join(NAVALL.split("\n")[:12]))
    assert len(short.schemes) < 13 * mf.MIN_KEEP_RATIO and "less than 80%" in mf.verdict(short, 13, None, 0)
    assert "older than the one stored" in mf.verdict(p, 13, date(2026, 10, 25), 10)
    assert "less than 80%" in mf.verdict(p, 13, None, 50)    # almost no current NAVs although many schemes had one


# ---------------------------------------------------------------------------------------------- packed series

def test_pack_roundtrip_exact_for_awkward_navs():
    days = [738000, 738001, 738004, 738005]
    navs = [10.0087785, 2540201.9508, 0.00000001, 66.74]
    blob = mf.pack_series(days, navs)
    assert mf.unpack_series(blob, days[0]) == (days, navs)


def test_pack_real_series_roundtrips_and_is_small():
    days, navs = history_series(LARGE)
    blob = mf.pack_series(days, navs)
    d2, n2 = mf.unpack_series(blob, days[0])
    assert d2 == days and n2 == navs
    assert len(blob) / len(days) < 6   # bytes a point; the plain row (date, double) is 16


# ---------------------------------------------------------------------------------------------- returns maths

def test_shift_months_clamps_to_month_end():
    assert mf.shift_months(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert mf.shift_months(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert mf.shift_months(date(2026, 10, 19), 60) == date(2021, 10, 19)
    assert mf.shift_months(date(2026, 1, 15), 6) == date(2025, 7, 15)


def test_axis_large_cap_matches_hand_worked_figures():
    # Start NAVs read off the history by hand: 18 Sep 2026 68.50, 17 Apr 2026 67.71, 17 Oct 2025 71.73, 19 Oct 2023 53.02, 19 Oct 2021 53.99; last NAV 19 Oct 2026 66.74.
    days, navs = history_series(LARGE)
    m = mf.metrics_for(days, navs, True)
    r = m["returns"]
    assert r["1m"]["value"] == pytest.approx((66.74 / 68.50 - 1) * 100, rel=1e-12) and r["1m"]["value"] == pytest.approx(-2.5693430656934413)
    assert r["6m"]["value"] == pytest.approx(-1.4325801211047096) and r["1y"]["value"] == pytest.approx((66.74 / 71.73 - 1) * 100)
    assert r["1y"]["kind"] == "absolute" and r["3y"]["kind"] == "cagr"
    assert r["3y"]["value"] == pytest.approx(((66.74 / 53.02) ** (365 / 1096) - 1) * 100) and r["3y"]["value"] == pytest.approx(7.9655236821865705)
    assert r["5y"]["value"] == pytest.approx(((66.74 / 53.99) ** (365 / 1826) - 1) * 100) and r["5y"]["value"] == pytest.approx(4.32886683179845)
    assert r["5y"]["from"] == date(2021, 10, 19) and r["1m"]["from"] == date(2026, 9, 18)
    assert m["vol1y"]["value"] == pytest.approx(13.718777910816979) and m["vol3y"]["value"] == pytest.approx(12.911873796687976)
    dd = m["mdd"]
    assert dd["value"] == pytest.approx(-21.623113728376886) and dd["peak"] == date(2021, 10, 14) and dd["trough"] == date(2022, 6, 17)


def test_liquid_fund_that_publishes_on_weekends():
    days, navs = history_series(LIQUID)
    assert len(days) == 1850   # every calendar day
    m = mf.metrics_for(days, navs, True)
    assert m["returns"]["1y"]["value"] == pytest.approx(6.565380397795262) and m["returns"]["5y"]["value"] == pytest.approx(6.447350235461369)
    # weekend NAVs are left out of volatility: 261 weekday-to-weekday changes in the year (not 365)
    assert m["vol1y"]["value"] == pytest.approx(0.2713778599866945) and m["vol3y"]["value"] == pytest.approx(0.26478667184583354)
    assert m["mdd"]["value"] == pytest.approx(-0.030561092209346885)


def test_young_funds_say_why_a_figure_is_missing():
    days, navs = history_series(BUSINESS)   # about 3.6 years old
    m = mf.metrics_for(days, navs, True)
    assert m["returns"]["3y"]["value"] == pytest.approx(12.076018299093283)
    assert m["returns"]["5y"]["value"] is None and m["returns"]["5y"]["why"].startswith("Younger than 5 years: the first NAV on file is dated")
    days, navs = history_series(CONSUMPTION)   # about 1.1 years old
    m = mf.metrics_for(days, navs, True)
    assert m["returns"]["1y"]["value"] == pytest.approx(-11.944718657453112) and m["returns"]["3y"]["value"] is None
    assert m["vol1y"]["value"] == pytest.approx(14.55292544732523) and m["vol3y"]["value"] is None and "Younger than 3 years" in m["vol3y"]["why"]
    # the same series with history not fully loaded must NOT claim the fund is young
    m = mf.metrics_for(days, navs, False)
    assert "not loaded yet" in m["returns"]["3y"]["why"] and "Younger" not in m["returns"]["3y"]["why"]


def test_a_hole_at_the_start_date_gives_no_figure():
    end = date(2026, 10, 19).toordinal()
    r = mf.trailing_returns([end - 400, end], [10.0, 12.0], True)   # the only earlier NAV is 400 days back, nowhere near the one-year date
    assert r["1y"]["value"] is None and "No NAV within 7 days" in r["1y"]["why"]
    assert r["1m"]["value"] is None and mf.trailing_returns([], [], True)["1y"]["why"] == "No NAV history is loaded for this scheme."


def test_thin_keeps_first_and_last():
    d = list(range(1000))
    n = [float(i) for i in d]
    td, tn = mf.thin(d, n, 100)
    assert td[0] == 0 and td[-1] == 999 and len(td) <= 101 and tn == [float(x) for x in td]
    assert mf.thin(d[:50], n[:50], 100) == (d[:50], n[:50])


# ---------------------------------------------------------------------------------------------- mirror cross-check

def test_mirror_parse_matches_amfi_on_every_common_date():
    payload = json.loads((FIX / "mfapi_120465.json").read_text())
    got = mf.parse_mirror(payload, LARGE)
    assert got is not None and mf.parse_mirror(payload, 999) is None   # an answer for another scheme is refused
    amfi = dict(zip(*history_series(LARGE)))
    mirror = dict(zip(*got))
    common = set(amfi) & set(mirror)
    assert len(common) > 1200
    assert [d for d in common if amfi[d] != mirror[d]] == []   # exact match on common dates


# ---------------------------------------------------------------------------------------------- search

NAMES = [(1, "HDFC Mid-Cap Opportunities Fund - Direct Plan - Growth", "HDFC Mutual Fund"), (2, "Axis Large Cap Fund - Direct Plan - Growth", "Axis Mutual Fund"),
         (3, "ICICI Prudential Bluechip Fund - Direct Plan - Growth", "ICICI Prudential Mutual Fund"), (4, "Nippon India Small Cap Fund - Direct Plan", "Nippon India Mutual Fund"),
         (5, "Kotak Midcap Fund - Regular Plan", "Kotak Mahindra Mutual Fund"), (6, "UTI Nifty 50 Index Fund - Direct Plan", "UTI Mutual Fund")]


@pytest.mark.parametrize("q,first", [
    ("hdfc mid cap", 1), ("hdfcmidcap", 1), ("HDFC  MID-CAP", 1),            # spaces, hyphens, case
    ("axis lage cap", 2), ("icici prudentail blue chip", 3), ("nipon small cap", 4),          # typos
    ("kotak mahindra", 5), ("nifty50", 6), ("nifty 50 index", 6),
])
def test_search_tolerates_spaces_and_typos(q, first):
    got = mf.SearchIndex(NAMES).search(q)
    assert got and got[0] == first


def test_search_midcap_finds_both_spellings():
    got = mf.SearchIndex(NAMES).search("midcap")
    assert set(got) == {1, 5} and got[0] == 5   # "Midcap" as one word ranks above "Mid-Cap"; both are found


def test_search_returns_nothing_for_nonsense_and_none_for_empty():
    idx = mf.SearchIndex(NAMES)
    assert idx.search("zzzzqqq") == [] and idx.search("  ") is None and idx.search("!!") is None
    assert set(idx.search("direct plan")) == {1, 2, 3, 4, 6}


# ---------------------------------------------------------------------------------------------- database + API

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test_mf")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/14")
needs_db = pytest.mark.integration


def amfi_transport(navall=NAVALL, history=HISTORY, calls=None):
    """Stands in for portal.amfiindia.com: NAVAll.txt and the history download (the same slice for every yearly window)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path.endswith("NAVAll.txt"):
            return httpx.Response(200, content=navall.encode("utf-8"))
        if request.url.path.endswith("DownloadNAVHistoryReport_Po.aspx"):
            if request.url.params.get("mf") != "53":
                return httpx.Response(200, text="<html>the web form, no records</html>")
            return httpx.Response(200, content=history.encode("utf-8"))
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def amfi_client(**kw):
    return httpx.AsyncClient(transport=amfi_transport(**kw), follow_redirects=True)


@pytest.fixture
async def store():
    settings = Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        s = await Store.connect(settings, migrate=True)
        await s.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with s.pool.acquire() as conn:
        await conn.execute("TRUNCATE mf_history, mf_backfill, mf_meta, mf_schemes CASCADE")
    async for k in s.redis.scan_iter("mf:*"):
        await s.redis.delete(k)
    yield s
    await s.close()


@pytest.fixture
async def loaded(store):
    """The sample file applied and Axis's history backfilled from the recorded AMFI download."""
    async with amfi_client() as c:
        assert (await mf.refresh(store, None, client=c))["status"] == "ok"
        res = await mf.backfill(store, None, amc="Axis", client=c, log_fn=lambda *_: None, settle=False)
    assert res["status"] == "ok" and not res["failed"]
    return store


@pytest.fixture
async def api(loaded):
    app = FastAPI()
    app.include_router(mf.router)
    app.state.store = loaded
    app.state.settings = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.app = app
        yield c


@needs_db
async def test_refresh_applies_the_sample_and_is_idempotent(store):
    async with amfi_client() as c:
        first = await mf.refresh(store, None, client=c)
        second = await mf.refresh(store, None, client=c)
    assert first["status"] == "ok" and first["schemesInFile"] == 13 and first["newSchemes"] == 13 and first["navDate"] == "2026-10-20"
    assert first["active"] == 10 and first["withHistory"] == 0   # 148304 has no NAV; 120607 (2018) and 146839 (2019) stopped
    assert second["newSchemes"] == 0 and second["active"] == 10
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_schemes") == 13
        assert await conn.fetchval("SELECT active FROM mf_schemes WHERE code = 120607") is False
        assert await conn.fetchval("SELECT nav FROM mf_schemes WHERE code = 148304") is None


@needs_db
async def test_short_or_odd_files_are_refused_and_change_nothing(store):
    async with amfi_client() as c:
        await mf.refresh(store, None, client=c)
    async with store.pool.acquire() as conn:
        before = await conn.fetch("SELECT code, nav, nav_date, active FROM mf_schemes ORDER BY code")
    bad = {
        "html": "<html><body>Service unavailable</body></html>",
        "empty": "",
        "header only": NAVALL.split("\n")[0] + "\n",
        "short": "\n".join(NAVALL.split("\n")[:14]),
        "stale": NAVALL.replace("20-Oct-2026", "10-Oct-2026").replace("19-Oct-2026", "09-Oct-2026"),
    }
    for label, text in bad.items():
        async with amfi_client(navall=text) as c:
            res = await mf.refresh(store, None, client=c)
        assert res["status"] == "refused", label
    async with store.pool.acquire() as conn:
        assert await conn.fetch("SELECT code, nav, nav_date, active FROM mf_schemes ORDER BY code") == before


@needs_db
async def test_download_errors_leave_data_alone_and_raise(store):
    async with amfi_client() as c:
        await mf.refresh(store, None, client=c)
    boom = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(httpx.HTTPStatusError):
        await mf.refresh(store, None, client=boom)
    await boom.aclose()
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_schemes") == 13


@needs_db
async def test_a_blank_nav_never_overwrites_a_good_one_and_an_older_date_never_wins(store):
    async with amfi_client() as c:
        await mf.refresh(store, None, client=c)
    worse = NAVALL.replace("66.74;19-Oct-2026", "N.A.;19-Oct-2026").replace("17.11;19-Oct-2026", "99.99;01-Oct-2026")
    async with amfi_client(navall=worse) as c:
        assert (await mf.refresh(store, None, client=c))["status"] == "ok"
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT nav FROM mf_schemes WHERE code = $1", LARGE) == 66.74
        assert await conn.fetchval("SELECT nav FROM mf_schemes WHERE code = $1", BUSINESS) == 17.11


@needs_db
async def test_backfill_stores_history_and_precomputes_the_figures(loaded):
    async with loaded.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM mf_schemes WHERE code = $1", LARGE)
        h = await conn.fetchrow("SELECT n, d0, d1, complete, length(blob) AS size FROM mf_history WHERE code = $1", LARGE)
        done = await conn.fetch("SELECT amc, schemes, points, note FROM mf_backfill")
        hist_codes = {x["code"] for x in await conn.fetch("SELECT code FROM mf_history")}
    assert hist_codes == {LARGE, LIQUID, BUSINESS, CONSUMPTION}   # active Growth options of Axis found in the file; IDCW and children's funds have no rows
    assert h["n"] == 1256 and h["d1"] == date(2026, 10, 19) and h["complete"] and h["size"] < 8000
    assert r["has_hist"] and r["r1y"] == pytest.approx(-6.956642966680615) and r["r3y"] == pytest.approx(7.9655236821865705) and r["mdd"] == pytest.approx(-21.623113728376886)
    assert len(done) == 1 and done[0]["amc"] == "Axis Mutual Fund" and "0 newest-NAV mismatches" in done[0]["note"]


@needs_db
async def test_backfill_is_resumable_and_skips_houses_already_done(loaded):
    calls = []
    async with amfi_client(calls=calls) as c:
        res = await mf.backfill(loaded, None, amc="all", client=c, log_fn=lambda *_: None)
        again = await mf.backfill(loaded, None, amc="all", client=c, log_fn=lambda *_: None)
    # Axis was done by the fixture; Bank of India (the sample's other active Growth scheme) is asked for, AMFI answers with its web form, and that is recorded
    assert [d["amc"] for d in res["done"]] == ["Bank of India Mutual Fund"] and res["done"][0]["schemes"] == 0 and res["skipped"] == ["Axis Mutual Fund"]
    assert calls and all("mf=46" in u for u in calls if "History" in u)
    assert again["done"] == [] and sorted(again["skipped"]) == ["Axis Mutual Fund", "Bank of India Mutual Fund"]
    async with loaded.pool.acquire() as conn:
        assert "no history rows" in await conn.fetchval("SELECT note FROM mf_backfill WHERE amc_key = 'bankofindia'")


@needs_db
async def test_nightly_file_appends_the_new_day_and_recomputes(loaded):
    nxt = NAVALL.replace("66.74;19-Oct-2026", "67.50;20-Oct-2026").replace("3180.5188;20-Oct-2026", "3182.0000;21-Oct-2026")
    async with amfi_client(navall=nxt) as c:
        res = await mf.refresh(store=loaded, settings=None, client=c)
    assert res["status"] == "ok" and res["historyAppended"] == 2 and res["navDate"] == "2026-10-21" and res["gapDays"] == 0
    async with loaded.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT nav, prev_nav, prev_date, nav_date, r1m FROM mf_schemes WHERE code = $1", LARGE)
        h = await conn.fetchrow("SELECT blob, d0, n, d1 FROM mf_history WHERE code = $1", LARGE)
    assert (r["nav"], r["prev_nav"], r["prev_date"], r["nav_date"]) == (67.5, 66.74, date(2026, 10, 19), date(2026, 10, 20))
    days, navs = mf.unpack_series(bytes(h["blob"]), h["d0"].toordinal())
    assert h["n"] == 1257 and days[-1] == date(2026, 10, 20).toordinal() and navs[-1] == 67.5
    # one month before 20 Oct 2026 is 20 Sep 2026 (a Sunday): the start NAV is Friday's, 18 Sep, 68.50
    assert r["r1m"] == pytest.approx((67.5 / 68.5 - 1) * 100)


@needs_db
async def test_list_shape_count_filters_sort_and_paging(api):
    r = await api.get("/api/mf")
    assert r.status_code == 200 and "max-age=300" in r.headers["cache-control"]
    body = r.json()
    assert body["total"] == 7 and all(i["optionClass"] == "Growth" for i in body["items"]) and body["page"] == 1 and body["pages"] == 1   # Growth only by default; stopped schemes are left out
    full = (await api.get("/api/mf?option=All&sort=name")).json()
    assert full["total"] == 10
    assert body["source"].startswith("AMFI") and body["disclaimer"].startswith("Information only. Not investment advice.") and body["dataDate"] == "2026-10-20"
    assert [i["name"] for i in full["items"]] == sorted(i["name"] for i in full["items"])
    allr = (await api.get("/api/mf?stopped=true&option=All")).json()
    assert allr["total"] == 13
    item = next(i for i in body["items"] if i["code"] == LARGE)
    # the category table's columns: 1, 3 and 5 years, SIP 3 and 5 years, fund size, expense ratio, checklist; 1 month and volatility / drawdown stay on the scheme's page
    assert item["r1y"] == -6.96 and item["r3y"] == 7.97 and "r1m" not in item and "mdd" not in item and item["r5y"] == 4.33 and item["retDate"] == "2026-10-19" and item["plan"] == "Direct" and item["optionClass"] == "Growth" and item["noReturns"] is None
    assert {"sip3y", "sip5y", "aum", "ter", "checklist"} <= set(item) and item["sip3y"] is not None and item["sip5y"] is not None
    idcw = next(i for i in full["items"] if i["code"] == 135765)
    assert idcw["r1y"] is None and idcw["noReturns"] == "idcw"
    assert (await api.get("/api/mf?category=Equity Schemes - Thematic Fund")).json()["total"] == 2
    assert (await api.get("/api/mf?amc=Axis Mutual Fund&option=Growth&plan=Direct")).json()["total"] == 5   # 135762, 120465, 120389, 151368, 152805
    pg = (await api.get("/api/mf?size=3&page=2&sort=r1y&dir=desc&option=All")).json()
    assert pg["pages"] == 4 and pg["total"] == 10 and len(pg["items"]) == 3
    ranked = (await api.get("/api/mf?sort=r1y&dir=desc&option=Growth&plan=Direct&amc=Axis Mutual Fund")).json()["items"]
    vals = [i["r1y"] for i in ranked]
    assert vals[0] == 6.57 and vals[-1] is None and vals[:4] == sorted([v for v in vals if v is not None], reverse=True)   # the columns the user sorts by; nulls last
    rng = (await api.get("/api/mf?min1y=0&max1y=10")).json()
    assert [i["code"] for i in rng["items"]] == [LIQUID]


@needs_db
async def test_list_search_is_fuzzy_and_validates_input(api):
    got = (await api.get("/api/mf?q=axis lage cap")).json()
    assert got["total"] >= 1 and got["items"][0]["code"] == LARGE
    assert (await api.get("/api/mf?q=axisliquid")).json()["items"][0]["code"] == LIQUID
    assert (await api.get("/api/mf?q=zzzzqqqq")).json()["total"] == 0
    assert (await api.get("/api/mf?size=101")).status_code == 422 and (await api.get("/api/mf?page=0")).status_code == 422
    assert (await api.get("/api/mf?sort=drop table")).status_code == 400 and (await api.get("/api/mf?plan=Gold")).status_code == 400
    assert (await api.get("/api/mf?q=" + "x" * 81)).status_code == 422


@needs_db
async def test_filters_endpoint_counts(api):
    f = (await api.get("/api/mf/filters")).json()
    assert f["totals"] == {"schemes": 13, "active": 10, "withHistory": 4}
    cats = {c["name"]: c for c in f["categories"]}
    assert cats["Equity Schemes - Thematic Fund"]["active"] == 2 and cats["Equity Schemes - Thematic Fund"]["group"] == "Equity Schemes"
    assert cats["ELSS"]["type"] == "Close Ended" and cats["Income"]["type"] == "Interval Fund" and cats["Income"]["active"] == 0 and cats["Income"]["total"] == 1
    amcs = {a["name"]: a for a in f["amcs"]}
    assert amcs["Axis Mutual Fund"] == {"name": "Axis Mutual Fund", "active": 8, "total": 8}
    assert {o["name"] for o in f["options"]} == {"Growth", "IDCW", "Other"} and f["dataDate"] == "2026-10-20"


@needs_db
async def test_detail_shape_numbers_series_and_family(api):
    r = await api.get(f"/api/mf/{LARGE}")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "Axis Large Cap Fund" and d["amc"] == "Axis Mutual Fund" and d["isin"] == "INF846K01DP8" and d["plan"] == "Direct" and d["option"] == "Growth Option"
    assert d["nav"] == 66.74 and d["navDate"] == "2026-10-19" and d["active"]
    assert d["change"] == {"abs": -0.82, "pct": -1.21, "since": "2026-10-16"}   # against the NAV before it in the stored history (16 Oct, 67.56)
    assert d["returns"]["1y"] == {"value": -6.96, "kind": "absolute", "from": "2025-10-17", "why": None}
    assert d["returns"]["3y"]["kind"] == "cagr" and d["returns"]["3y"]["value"] == 7.97 and d["returns"]["5y"]["value"] == 4.33
    assert d["risk"]["vol1y"]["value"] == 13.72 and d["risk"]["maxDrawdown"]["peak"] == "2021-10-14" and d["risk"]["maxDrawdown"]["trough"] == "2022-06-17"
    assert set(d["series"]) == {"1M", "6M", "1Y", "3Y", "5Y"} and d["series"]["5Y"]["v"][-1] == 66.74 and d["series"]["1M"]["t"][-1] == "2026-10-19"
    assert len(d["series"]["5Y"]["t"]) <= 450 and d["series"]["5Y"]["t"][0] == "2021-10-19"
    assert d["history"]["source"] == "amfi" and d["history"]["complete"] and d["history"]["points"] == 1256 and d["history"]["note"] is None
    assert d["family"] == [] and "AUM" in " ".join(d["notAvailable"]["items"]) and d["disclaimer"].startswith("Information only")
    young = (await api.get(f"/api/mf/{CONSUMPTION}")).json()
    assert young["returns"]["3y"]["value"] is None and "Younger than 3 years" in young["returns"]["3y"]["why"] and set(young["series"]) == {"1M", "6M", "1Y", "MAX"}


@needs_db
async def test_detail_of_an_idcw_option_has_no_returns_and_links_its_family(api):
    d = (await api.get("/api/mf/135765")).json()
    assert d["optionClass"] == "IDCW" and all(v["value"] is None for v in d["returns"].values()) and "IDCW" in d["returnsNote"] and d["series"] == {}
    assert sorted(k["code"] for k in d["family"]) == [135759, 135760, 135762]
    stopped = (await api.get("/api/mf/120607")).json()
    assert stopped["active"] is False and "stopped" in stopped["returnsNote"]
    no_nav = (await api.get("/api/mf/148304")).json()
    assert no_nav["nav"] is None and no_nav["navDate"] is None


@needs_db
async def test_unknown_and_bad_codes(api):
    assert (await api.get("/api/mf/999999")).status_code == 404
    assert (await api.get("/api/mf/abc")).status_code == 422
    assert (await api.get("/api/mf/99999999")).status_code == 404


@needs_db
async def test_etag_gives_304(api):
    r = await api.get(f"/api/mf/{LARGE}")
    again = await api.get(f"/api/mf/{LARGE}", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


@needs_db
async def test_compare_two_to_four_with_rebased_chart(api):
    r = await api.get(f"/api/mf/compare?ids={LARGE},{BUSINESS},{CONSUMPTION}&range=1Y")
    assert r.status_code == 200
    d = r.json()
    assert [f["code"] for f in d["funds"]] == [LARGE, BUSINESS, CONSUMPTION]
    assert d["funds"][0]["returns"]["1y"]["value"] == -6.96 and d["funds"][2]["returns"]["3y"]["value"] is None
    ch = d["chart"]
    assert ch["range"] == "1Y" and [s["code"] for s in ch["series"]] == [LARGE, BUSINESS, CONSUMPTION]
    assert all(s["v"][0] == 100.0 for s in ch["series"])
    assert ch["series"][0]["v"][-1] == pytest.approx(66.74 / 71.73 * 100, abs=1e-3) and ch["series"][2]["v"][-1] == pytest.approx(8.92 / 10.13 * 100, abs=1e-3)
    three = (await api.get(f"/api/mf/compare?ids={LARGE},{CONSUMPTION}&range=3Y")).json()
    assert three["chart"] is None and "shorter" in three["chartNote"]   # one fund is younger than 3 years: no chart is drawn that would mislead
    for bad in ("", str(LARGE), f"{LARGE},{LARGE}", "1,2,3,4,5", "a,b"):
        assert (await api.get(f"/api/mf/compare?ids={bad}")).status_code == 400, bad
    assert (await api.get(f"/api/mf/compare?ids={LARGE},999999")).status_code == 404


class FakeMirror:
    """api.mfapi.in stand-in serving the recorded answer, optionally with the newest NAV changed."""

    def __init__(self, nav_shift=0.0):
        self.payload = json.loads((FIX / "mfapi_120465.json").read_text())
        if nav_shift:
            self.payload["data"][0]["nav"] = str(float(self.payload["data"][0]["nav"]) + nav_shift)
        self.calls = 0

    def client(self):
        def handler(request):
            self.calls += 1
            return httpx.Response(200, json=self.payload)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@needs_db
async def test_mirror_fills_history_only_when_amfi_history_is_missing_and_says_so(api):
    async with api.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_history WHERE code = $1", LARGE)
    await api.app.state.store.redis.set("mf:ver", "changed")   # data changed: older cached pages are no longer served
    fake = FakeMirror()
    api.app.state.mf_client = fake.client()
    d = (await api.get(f"/api/mf/{LARGE}")).json()
    assert d["history"]["source"] == "mirror" and d["history"]["note"] == "NAV history: third-party mirror of AMFI data (api.mfapi.in)" and d["history"]["complete"] is False
    assert d["returns"]["1y"]["value"] == -6.96 and fake.calls == 1
    await api.get(f"/api/mf/compare?ids={LARGE},{LIQUID}")
    assert fake.calls == 1   # the mirror's answer is cached for hours


@needs_db
async def test_mirror_that_disagrees_with_amfi_is_not_used(api):
    async with api.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_history WHERE code = $1", LARGE)
    await api.app.state.store.redis.set("mf:ver", "changed")
    api.app.state.mf_client = FakeMirror(nav_shift=0.5).client()
    d = (await api.get(f"/api/mf/{LARGE}")).json()
    # no confirmed history: the risk figures and periods that need it stay empty, but the 1 and 5 year figures worked out nightly from AMFI's own history are kept, dated
    assert d["history"]["source"] is None and d["series"] == {} and d["risk"]["maxDrawdown"]["value"] is None and d["returns"]["6m"]["value"] is None
    assert d["returns"]["1y"]["value"] == -6.96 and d["returns"]["1y"]["from"] is None and d["retDate"] == "2026-10-19"


@needs_db
async def test_missed_nights_are_filled_from_amfis_industry_wide_history(loaded):
    """The job did not run for a week: the next file's NAVs sit a week after the stored ones, so the days between come from AMFI's history download."""
    nxt = NAVALL.replace("66.74;", "70.00;").replace("19-Oct-2026", "27-Oct-2026").replace("20-Oct-2026", "27-Oct-2026")
    rows = "\n".join(f"{LARGE};Axis Large Cap Fund - Direct Plan - Growth;Direct Plan;Growth Option;INF846K01DP8;;{nav};{d}"
                     for d, nav in (("20-Oct-2026", "67.10"), ("21-Oct-2026", "67.20"), ("22-Oct-2026", "67.30"), ("23-Oct-2026", "67.40"), ("26-Oct-2026", "69.00")))
    gap_text = "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date\n\nOpen Ended Schemes ( Equity Schemes - Large Cap Fund )\n\nAxis Mutual Fund\n" + rows + "\n"
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        if request.url.path.endswith("NAVAll.txt"):
            return httpx.Response(200, content=nxt.encode())
        return httpx.Response(200, content=gap_text.encode())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await mf.refresh(loaded, None, client=c)
    assert res["status"] == "ok" and res["gapDays"] == 8 and seen[1] == {"frmdt": "20-Oct-2026", "todt": "27-Oct-2026"}   # no mf=: every fund house at once
    async with loaded.pool.acquire() as conn:
        h = await conn.fetchrow("SELECT blob, d0, n FROM mf_history WHERE code = $1", LARGE)
    days, navs = mf.unpack_series(bytes(h["blob"]), h["d0"].toordinal())
    assert [date.fromordinal(d).day for d in days[-6:]] == [20, 21, 22, 23, 26, 27] and navs[-6:] == [67.1, 67.2, 67.3, 67.4, 69.0, 70.0]
    assert days[0] > date(2026, 10, 27).toordinal() - mf.KEEP_DAYS and h["n"] == len(days)   # and the oldest days beyond the kept window were trimmed


def test_a_future_dated_nav_is_not_stored_and_cannot_block_later_files():
    """A typo date (tomorrow+ or a year like 2062) must not become the newest date: it would make every correct file look older than what is stored."""
    from datetime import date as _d
    lines = NAVALL.split("\n")
    rows = [i for i, l in enumerate(lines) if l.count(";") == 7 and l.split(";")[0].strip().isdigit()]
    good = mf.parse_navall(NAVALL)
    today = good.newest
    f = lines[rows[0]].split(";")
    f[7] = (today.replace(year=2062)).strftime("%d-%b-%Y")
    lines[rows[0]] = ";".join(f)
    p = mf.parse_navall("\n".join(lines), today=today)
    assert p.newest == today and p.skipped.get("NAV dated in the future") == 1
    assert mf.latest_allowed(_d(2026, 10, 23)) == _d(2026, 10, 24)
