"""Mutual Fund Screener (finlit/mfscreen, docs/MF-FILTERS.md): the pure figures, the query-string parser, the nightly job and the API, end to end on ~350 seeded funds.

Expected answers are worked out here, in plain Python, from the same seeded arrays (tests/mfscreen_synth.py): the API is never compared with itself except for the
"counts beside an option equal what that option gives" property, which is checked against the list endpoint of the same server."""

import json
import math
import statistics
from datetime import date

import httpx
import pytest
from fastapi import FastAPI

from finlit import mf
from finlit.jobs.registry import by_name
from finlit.mfscreen import calc, job, spec
from mfscreen_synth import CATS, NAV_DATE, build, seed
from test_mf import needs_db, store  # noqa: F401  (fixture)


# ---------------------------------------------------------------------------------------------- pure figures, worked by hand

def test_volatility_worst_month_and_shares_by_hand():
    navs = [100.0, 110.0, 99.0, 108.9, 98.01]          # returns +10%, -10%, +10%, -10%
    r = calc.returns(navs)
    assert [round(x, 6) for x in r] == [0.1, -0.1, 0.1, -0.1]
    assert calc.volatility(r) == pytest.approx(statistics.stdev(r) * math.sqrt(12) * 100)
    assert calc.volatility(r) == pytest.approx(0.11547005 * math.sqrt(12) * 100, rel=1e-6)   # sample stdev of +-0.1 over four months is 0.1155
    assert calc.worst_loss(r) == pytest.approx(10.0)
    assert calc.neg_share(r) == 50.0
    assert calc.below_high(navs) == pytest.approx(3 / 4 * 100)      # 110 is a new high; 99, 108.9 and 98.01 all close below the 110 high
    assert calc.worst_loss([0.01, 0.02]) == 0.0                     # a fund whose every month rose has no loss, not a negative one
    assert calc.neg_share([0.01, 0.02]) == 0.0
    assert calc.volatility([0.01, 0.02]) is None                     # fewer than three returns: no figure


def test_below_high_counts_closes_under_an_earlier_high():
    assert calc.below_high([10, 12, 11, 13, 12.9, 14]) == pytest.approx(2 / 5 * 100)    # 11 and 12.9
    assert calc.below_high([10, 11, 12, 13]) == 0.0


def test_worst_rolling_year():
    navs = [100.0] + [100.0 + i for i in range(1, 12)] + [80.0] + [90.0] * 4         # 17 points: windows 12..16
    assert calc.worst_rolling(navs, 12) == pytest.approx(20.0)     # 80 / 100 - 1 = -20%
    assert calc.worst_rolling([100.0] * 5, 12) is None


def test_down_capture_and_consistency():
    peer = {1: -0.04, 2: 0.03, 3: -0.02, 4: -0.06, 5: 0.05}
    own = {1: -0.02, 2: 0.04, 3: -0.01, 4: -0.03, 5: 0.02}
    # bad peer months 1, 3, 4: fund average -0.02, peers -0.04
    assert calc.down_capture(own, peer) == pytest.approx(50.0)
    assert calc.down_capture(own, {1: -0.01, 2: 0.02}) is None       # fewer than three bad months
    assert calc.consistency(own, peer, need=5) == pytest.approx(4 / 5 * 100)    # beats the peer median in months 1, 2, 3, 4; loses month 5
    assert calc.consistency(own, peer, need=6) is None


def test_peer_median_needs_three_peers_and_sharpe_uses_six_percent():
    assert calc.peer_median_months([{1: 0.1}, {1: 0.2}]) == {}
    assert calc.peer_median_months([{1: 0.1}, {1: 0.2}, {1: 0.4}]) == {1: 0.2}
    assert calc.sharpe(18.0, 12.0) == pytest.approx(1.0)
    assert calc.sharpe(None, 12.0) is None and calc.sharpe(18.0, 0.0) is None
    assert calc.fee_share(1.0, 9.0) == pytest.approx(10.0)
    assert calc.fee_share(1.0, -3.0) is None


def test_month_windows_need_every_month():
    days = [date(2026, m, 28) for m in (1, 2, 3, 5)]               # April missing; and a NAV too far from month end is dropped
    by = calc.by_month(days + [date(2026, 6, 10)], [10.0, 11.0, 12.0, 13.0, 14.0])
    assert sorted(by) == [calc.month_key(date(2026, m, 1)) for m in (1, 2, 3, 5)]   # 28 Jan is 3 days before the 31st: fine; 10 June is not a month-end NAV
    assert calc.window(by, calc.month_key(date(2026, 6, 1)), 2) is None
    assert calc.window(by, calc.month_key(date(2026, 4, 1)), 2) == [10.0, 11.0, 12.0]


# ---------------------------------------------------------------------------------------------- the parser

class QP:
    """A tiny stand-in for Starlette's QueryParams."""
    def __init__(self, pairs):
        self.pairs = list(pairs)

    def get(self, k, d=None):
        return next((v for kk, v in self.pairs if kk == k), d)

    def getlist(self, k):
        return [v for kk, v in self.pairs if kk == k]


CTX = spec.Ctx(by_key={"mid-cap": ["Equity Scheme - Mid Cap Fund"], "large-cap": ["Equity Scheme - Large Cap Fund"], "index-funds": ["Other Scheme - Index Funds"]},
               by_tab={"equity": ["Equity Scheme - Mid Cap Fund", "Equity Scheme - Large Cap Fund"]})


def parse(*pairs):
    return spec.parse(QP(pairs), CTX)


def test_defaults_are_the_pages_defaults():
    sql, args = spec.where(parse().preds)
    assert sql == " WHERE active AND option_class = ANY($1::text[])" and args == [["Growth"]]


@pytest.mark.parametrize("pairs, why", [
    ([("rng", "bogus:1:2")], "Unknown field"), ([("rng", "ter:5:1")], "above its max"), ([("rng", "ter:a:1")], "not a number"), ([("rng", "ter:1")], "field:min:max"),
    ([("rng", "ter:1:2"), ("rng", "ter:3:4")], "twice"), ([("rng", "ter:1e12:2e12")], "out of range"), ([("rng", "ter:nan:1")], "out of range"),
    ([("subs", "no-such")], "Unknown value"), ([("cap", "huge")], "Unknown value"), ([("tick", "has_riskometer")], "data source"), ([("tick", "x; DROP")], "Unknown tick"),
    ([("status", "maybe")], "status"), ([("plan", "Gold")], "Unknown plan"), ([("rk", "3y:top1")], "Unknown rank"), ([("chk", "9")], "1 to 5"), ([("exit", "forever")], "Unknown value"),
    ([("launch_from", "yesterday")], "YYYY-MM-DD"), ([("launch_from", "2026-01-02"), ("launch_to", "2025-01-01")], "after"), ([("tags", "a b")], "Unknown tag"),
    ([("holds", "not a symbol!")], "NSE symbol"), ([("sector", "x;y")], "Unknown sector"), ([("sector", "Banks"), ("sector_min", "150")], "0 to 100"),
    ([("rng", f"ter:1:{i}") for i in range(2, 50)], "At most"), ([("amcs", "a" * 200)], "too long"), ([("nd", "nonsense")], "Unknown value"),
])
def test_refused_inputs(pairs, why):
    with pytest.raises(spec.ScreenError) as e:
        parse(*pairs)
    assert why in str(e.value)


def test_values_are_always_bound_never_pasted_into_sql():
    hostile = "x'); DROP TABLE mf_schemes; --"
    scr = parse(("amcs", hostile), ("rng", "ter:0.1:0.9"), ("sector", "Banks"), ("holds", "reliance"), ("subs", "mid-cap"))
    sql, args = spec.where(scr.preds)
    assert hostile not in sql and "DROP" not in sql and "Banks" not in sql and "RELIANCE" not in sql
    assert hostile in sum([a if isinstance(a, list) else [a] for a in args], [])
    assert all(f"${i}" in sql for i in range(1, len(args) + 1))


def test_faceted_where_leaves_out_one_group():
    scr = parse(("rng", "ter:0:1"), ("rng", "r3y:10:"), ("plans", "Direct"))
    full, _ = spec.where(scr.preds)
    no_ter, _ = spec.where(scr.preds, ["rng:ter"])
    assert "ter" in full and "(ter)" not in no_ter and "(r3y)" in no_ter


def test_legacy_parameters_still_mean_what_they_did():
    scr = parse(("stopped", "true"), ("min1y", "5"), ("max5y", "30"), ("group", "equity"), ("amc", "Alpha Mutual Fund"), ("option", "All"), ("plan", "Direct"))
    sql, args = spec.where(scr.preds)
    assert "active" not in sql.replace("NOT active", "")      # stopped=true: stopped funds stay in
    assert "(r1y) >= " in sql and "(r5y) <= " in sql and "option_class" not in sql    # option=All: no option filter
    assert [5.0, 30.0] == [a for a in args if isinstance(a, float)]


def test_every_numeric_field_has_sorted_edges_and_a_sql_expression():
    for n in spec.NUMS:
        assert list(n.edges) == sorted(set(n.edges)) and len(n.edges) >= 4, n.key
        assert n.expr and ";" not in n.expr and "--" not in n.expr, n.key
    assert len({n.key for n in spec.NUMS}) == len(spec.NUMS)


# ---------------------------------------------------------------------------------------------- registered job and worker command

def test_the_nightly_job_is_registered_after_its_inputs():
    j = by_name()["mf-screen"]
    assert j.args == ("refresh-mf-screen",) and j.group == "funds" and set(j.prerequisites) == {"facts", "industry", "portfolios"}
    assert j.sla.hours <= 30 and j.cls == "bulk"
    from pathlib import Path
    assert 'add_parser("refresh-mf-screen"' in (Path(__file__).resolve().parents[1] / "finlit/worker.py").read_text()


# ---------------------------------------------------------------------------------------------- tags and exit-load text

def test_tag_rules_use_whole_words_and_the_tab():
    tags = [{"tag": "i_nifty50", "keywords": ["nifty 50"], "sectors": [], "sector_min": 40, "tabs": ["other", "equity"]},
            {"tag": "i_nifty500", "keywords": ["nifty 500"], "sectors": [], "sector_min": 40, "tabs": ["other", "equity"]},
            {"tag": "banking", "keywords": ["bank"], "sectors": ["banks"], "sector_min": 40, "tabs": ["equity"]}]
    assert job.tags_for("Alpha Nifty 50 Index Fund", "other", tags, None) == ["i_nifty50"]
    assert job.tags_for("Alpha Nifty 500 Index Fund", "other", tags, None) == ["i_nifty500"]      # 'nifty 50' is not inside 'nifty 500'
    assert job.tags_for("Alpha Banking and PSU Fund", "debt", tags, None) == []                    # debt funds never get theme tags
    assert job.tags_for("Alpha Flexi Cap Fund", "equity", tags, {"Banks": 30.0, "Other": 5.0}) == []           # rule 2 needs 40% in the tag's sectors
    assert job.tags_for("Alpha Flexi Cap Fund", "equity", tags, {"Banks": 44.0}) == ["banking"]


def test_exit_load_states():
    assert job.exit_figures(None) == (None, None, None) and job.exit_figures("  ") == (None, None, None)
    assert job.exit_figures("Nil") == ("nil", 0.0, None)
    st, pct, days = job.exit_figures("1% if redeemed within 1 year")
    assert (st, pct, days) == ("read", 1.0, 365)
    assert job.exit_figures("see the scheme document")[0] == "unread"


# ---------------------------------------------------------------------------------------------- end to end on the seeded funds

@pytest.fixture
async def world(store):
    funds = build()
    await seed(store, funds)
    res = await job.run(store)
    assert res["status"] == "ok", res
    app = FastAPI()
    from finlit.mfscreen import api as screen_api
    app.include_router(screen_api.router)      # before mf.router, as finlit/api.py does: /api/mf/{code} would claim /api/mf/screen
    app.include_router(mf.router)
    app.state.store = store
    app.state.settings = None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.funds, c.job = funds, res
        yield c


async def lst(c, *pairs, **kw):
    r = await c.get("/api/mf", params=[*pairs, ("size", "100")] + list(kw.items()))
    assert r.status_code == 200, r.text
    return r.json()


async def fac(c, *pairs):
    r = await c.get("/api/mf/filters", params=[("screen", "true"), *pairs])
    assert r.status_code == 200, r.text
    return r.json()["screen"]


def growth_codes(funds, plan=None):
    return [(f, p) for f in funds for p in (["Direct", "Regular"] if plan is None else [plan])]


@needs_db
async def test_job_wrote_a_row_per_scheme_and_values_match_a_plain_python_recount(world):
    c = world
    n = len(c.funds) * 3
    assert c.job["rows"] == n and c.job["status"] == "ok"
    async with c._transport.app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_screen") == n
        wrong = 0
        checked = 0
        for f in c.funds:
            code = f.codes["Direct|Growth"]
            row = await conn.fetchrow("SELECT * FROM mf_screen WHERE x_code = $1", code)
            keys = [(2023 + (8 + i) // 12, (8 + i) % 12 + 1) for i in range(37)]       # Sep 2023 .. Sep 2026: the 37 month-ends behind 36 returns
            if all(k in f.navs for k in keys):
                navs = [f.navs[k] for k in keys]
                r = [navs[i] / navs[i - 1] - 1 for i in range(1, 37)]
                checked += 1
                ok = (row["x_vol3"] == pytest.approx(statistics.stdev(r) * math.sqrt(12) * 100, abs=1e-3)
                      and row["x_worst_loss"] == pytest.approx(max(0, -min(r)) * 100, abs=1e-3)
                      and row["x_neg_share"] == pytest.approx(sum(1 for x in r if x < 0) / 36 * 100, abs=1e-3))
                wrong += not ok
            else:
                assert row["x_vol3"] is None and row["x_neg_share"] is None, f.name        # a young fund has no 3-year risk figures, not zeros
        assert checked > 50 and wrong == 0
        # excess over the peer median, recomputed: every Direct Growth fund of Mid Cap
        mids = [f for f in c.funds if "Mid Cap" in f.cat]
        r3 = {f.name: mf_r3(f) for f in mids if mf_r3(f) is not None}
        med = statistics.median(r3.values())
        for f in mids:
            ex = await conn.fetchval("SELECT x_ex3y FROM mf_screen WHERE x_code = $1", f.codes["Direct|Growth"])
            assert (ex is None) == (f.name not in r3)
            if ex is not None:
                assert ex == pytest.approx(r3[f.name] - med, abs=1e-3)
        # IDCW options are never given return-derived figures
        assert await conn.fetchval("SELECT count(*) FROM mf_screen s JOIN mf_schemes m ON m.code = s.x_code WHERE m.option_class = 'IDCW' AND (s.x_vol3 IS NOT NULL OR s.x_ex3y IS NOT NULL)") == 0
        # houses without a portfolio file have NULL, never 0, in every portfolio column
        bad = await conn.fetchval("SELECT count(*) FROM mf_screen s JOIN mf_schemes m ON m.code = s.x_code WHERE m.amc LIKE 'Eta%' AND (s.x_eq_pct IS NOT NULL OR s.x_n_hold IS NOT NULL)")
        assert bad == 0
        assert await conn.fetchval("SELECT count(*) FROM mf_screen s JOIN mf_schemes m ON m.code = s.x_code WHERE m.amc LIKE 'Alpha%' AND s.x_eq_pct IS NULL") == 0


def mf_r3(f):
    from mfscreen_synth import cagr
    return cagr(f, 3)


@needs_db
async def test_job_is_idempotent_and_leaves_unchanged_rows_alone(world):
    store = world._transport.app.state.store
    async with store.pool.acquire() as conn:
        before = [tuple(r.values()) for r in await conn.fetch("SELECT * FROM mf_screen ORDER BY x_code")]
        xmin = await conn.fetchval("SELECT max(xmin::text::bigint) FROM mf_screen")
    again = await job.run(store)
    assert again["status"] == "ok" and again["rows"] == len(before)
    async with store.pool.acquire() as conn:
        after = [tuple(r.values()) for r in await conn.fetch("SELECT * FROM mf_screen ORDER BY x_code")]
        assert after == before
        assert await conn.fetchval("SELECT max(xmin::text::bigint) FROM mf_screen") == xmin      # no row was rewritten
        assert await conn.fetchval("SELECT count(*) FROM mf_screen_hold") > 100 and await conn.fetchval("SELECT count(*) FROM mf_cat_flow") >= len(CATS)


@needs_db
async def test_default_list_is_growth_plans_of_active_funds_and_old_parameters_work(world):
    c = world
    d = await lst(c)
    assert d["total"] == len(c.funds) * 2
    assert (await lst(c, ("plan", "Direct")))["total"] == len(c.funds)
    assert (await lst(c, ("option", "IDCW")))["total"] == len(c.funds)
    assert (await lst(c, ("option", "All")))["total"] == len(c.funds) * 3
    assert (await lst(c, ("group", "debt")))["total"] == sum(n for cat, _, _, n in CATS if cat.startswith("Debt")) * 2
    assert (await lst(c, ("category", "Equity Scheme - Mid Cap Fund")))["total"] == 24
    assert (await lst(c, ("categories", "Equity Scheme - Mid Cap Fund"), ("categories", "Equity Scheme - Small Cap Fund")))["total"] == 48
    r = await c.get("/api/mf", params={"min1y": "0", "max1y": "5"})
    assert r.status_code == 200
    # old two-parameter return range: same answer as the new rng form
    a = (await lst(c, ("min1y", "5"), ("max1y", "30")))["total"]
    b = (await lst(c, ("rng", "r1y:5:30")))["total"]
    assert a == b > 0


@needs_db
async def test_range_filter_matches_a_hand_count_and_the_no_data_toggle_adds_exactly_the_missing(world):
    c = world
    exp = sum(1 for f in c.funds if f.has_ter for ter in (f.ter_dir, f.ter_reg) if ter <= 1.0)
    assert (await lst(c, ("rng", "ter:0:1")))["total"] == exp > 20
    no_ter = sum(2 for f in c.funds if not f.has_ter)
    with_nd = (await lst(c, ("rng", "ter:0:1"), ("nd", "ter")))["total"]
    assert with_nd == exp + no_ter
    # 5-year return: young funds have none; the toggle brings them back
    have5 = sum(2 for f in c.funds if mf_cagr(f, 5) is not None)
    assert (await lst(c, ("rng", "r5y:-100:1000")))["total"] == have5
    assert (await lst(c, ("rng", "r5y:-100:1000"), ("nd", "r5y")))["total"] == len(c.funds) * 2
    assert have5 < len(c.funds) * 2


def mf_cagr(f, y):
    from mfscreen_synth import cagr
    return cagr(f, y)


@needs_db
async def test_category_chips_house_instrument_and_family_view(world):
    c = world
    assert (await lst(c, ("cap", "mid")))["total"] == 24 and (await lst(c, ("cap", "mid,large")))["total"] == 48
    assert (await lst(c, ("subs", "mid-cap"), ("plans", "Direct")))["total"] == 12
    assert (await lst(c, ("style", "passive")))["total"] == (10 + 6) * 2 and (await lst(c, ("style", "active")))["total"] == (len(c.funds) - 16) * 2
    assert (await lst(c, ("mat", "d91")))["total"] == 20 and (await lst(c, ("mat", "y1_3,d91")))["total"] == 40
    assert (await lst(c, ("inst", "etf")))["total"] == 12 and (await lst(c, ("inst", "fund")))["total"] == (len(c.funds) - 6) * 2
    assert (await lst(c, ("struct", "open")))["total"] == len(c.funds) * 2 and (await lst(c, ("struct", "close")))["total"] == 0
    houses = {}
    for f in c.funds:
        houses[f.house] = houses.get(f.house, 0) + 2
    for h, n in houses.items():
        assert (await lst(c, ("amcs", h)))["total"] == n
    two = sorted(houses)[:2]
    assert (await lst(c, ("amcs", two[0]), ("amcs", two[1])))["total"] == houses[two[0]] + houses[two[1]]
    fam = await lst(c, ("family", "true"))
    assert fam["total"] == len(c.funds)
    assert {i["plan"] for i in fam["items"]} == {"Direct"}                      # the Direct Growth plan stands for its family
    fam_reg = await lst(c, ("family", "true"), ("plans", "Regular"))
    assert fam_reg["total"] == len(c.funds) and {i["plan"] for i in fam_reg["items"]} == {"Regular"}


@needs_db
async def test_tags_checklist_ticks_exit_load_and_hot(world):
    c = world
    funds = c.funds
    import re
    n50 = [f for f in funds if re.search(r"Nifty 50\b", f.name)]
    assert n50 and (await lst(c, ("tags", "i_nifty50")))["total"] == len(n50) * 2
    assert (await lst(c, ("tags", "i_nifty500")))["total"] == len([f for f in funds if "Nifty 500" in f.name]) * 2
    assert (await lst(c, ("tags", "defence")))["total"] >= len([f for f in funds if "Defence Fund" in f.name]) * 2 > 0
    # exit load: bands are exclusive; every fund with a text lands in exactly one
    got = {k: (await lst(c, ("exit", k)))["total"] for k in ("none", "d7", "d30", "y1", "y1p", "unread")}
    with_text = sum(2 for f in funds if f.exit_text is not None)
    assert sum(got.values()) == with_text and got["none"] == 2 * sum(1 for f in funds if f.exit_text == "Nil")
    assert (await lst(c, ("tick", "has_exit")))["total"] == with_text - got["unread"]
    assert (await lst(c, ("tick", "has_ter")))["total"] == sum(2 for f in funds if f.has_ter)
    assert (await lst(c, ("tick", "has_port")))["total"] == sum(2 for f in funds if f.house != "Eta Mutual Fund" and f.house != "Theta Mutual Fund")
    assert (await lst(c, ("tick", "hot")))["total"] == 0                                  # mf_hot is empty in this world
    one = await lst(c, ("chk", "5"))
    assert all(i["checklist"]["pass"] == 5 for i in one["items"])
    assert (await lst(c, ("chk", "3")))["total"] >= one["total"]
    assert (await lst(c, ("tick", "noneg36")))["total"] == (await lst(c, ("rng", "neg_share:0:0")))["total"]


@needs_db
async def test_portfolio_and_stock_filters_show_houses_without_files_honestly(world):
    c = world
    d = await lst(c, ("rng", "eq_pct:50:100"), ("extra", "true"))
    assert d["total"] > 0 and all(i["x"]["portfolio"]["equity"] >= 50 for i in d["items"])
    everyone = await lst(c, ("rng", "eq_pct:0:100"))
    assert everyone["total"] == (await lst(c, ("tick", "has_port")))["total"] < len(c.funds) * 2      # no-file houses are not zero-equity funds
    assert (await lst(c, ("rng", "eq_pct:0:100"), ("nd", "eq_pct")))["total"] == len(c.funds) * 2
    from mfscreen_synth import reliance_fund
    f = reliance_fund(c.funds)
    isin = f"INE{f.fid * 100:09d}"[:12]
    held = await lst(c, ("holds", isin))
    assert held["total"] >= 2 and any(i["name"].startswith(f.name) for i in held["items"])
    by_symbol = await lst(c, ("holds", "RELIANCE"))
    assert by_symbol["total"] >= 2 and (await lst(c, ("holds", "NOSUCHSTOCK")))["total"] == 0
    sec = await lst(c, ("sector", "Banks"), ("sector_min", "10"))
    assert 0 < sec["total"] < len(c.funds) * 2
    r = await c.get("/api/mf/screen/stocks", params={"q": "RELI"})
    assert r.status_code == 200 and r.json()["items"][0]["symbol"] == "RELIANCE" and r.json()["items"][0]["families"] >= 1
    assert (await c.get("/api/mf/screen/stocks", params={"q": "r"})).status_code == 400


@needs_db
async def test_category_market_view_filters(world):
    c = world
    d = await lst(c, ("cflow", "pos"), ("extra", "true"))
    assert d["total"] > 0 and all(i["x"]["category"]["flow"] > 0 for i in d["items"])
    neg = await lst(c, ("cflow", "neg"))
    assert d["total"] + neg["total"] == len(c.funds) * 2
    big = await lst(c, ("csize", "gt5"), ("extra", "true"))
    assert all(i["x"]["category"]["share"] > 5 for i in big["items"])
    assert (await lst(c, ("rng", "cf_aum_yoy:0:1000")))["total"] > 0


@needs_db
async def test_sorting_by_every_new_key(world):
    c = world
    for key in ("fall", "age", "launch", "ex3y", "rank3y", "rank1y", "rank5y", "vol", "sharpe", "gap", "consist", "aumrank", "worst", "negshare", "r1m", "r6m"):
        for d in ("asc", "desc"):
            r = await c.get("/api/mf", params={"sort": key, "dir": d, "size": "10"})
            assert r.status_code == 200, (key, r.text)
    asc = await lst(c, ("sort", "vol"), ("dir", "asc"), ("extra", "true"))
    vols = [i["x"]["risk"]["vol3"] for i in asc["items"] if i["x"]["risk"]["vol3"] is not None]
    assert vols == sorted(vols) and vols[0] < 1.5          # the liquid funds, least volatile, come first
    assert (await c.get("/api/mf", params={"sort": "nonsense"})).status_code == 400


@needs_db
async def test_bad_requests_are_400_not_500_and_hostile_text_does_nothing(world):
    c = world
    for pairs in ([("rng", "bogus:1:2")], [("subs", "x")], [("tick", "has_riskometer")], [("rk", "9y:q1")], [("holds", "a b")]):
        r = await c.get("/api/mf", params=pairs)
        assert r.status_code == 400 and r.json()["detail"], pairs
        r2 = await c.get("/api/mf/filters", params=[("screen", "true"), *pairs])
        assert r2.status_code == 400
    r = await c.get("/api/mf", params={"amcs": "x'); DROP TABLE mf_schemes; --"})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert (await lst(c))["total"] == len(c.funds) * 2      # the table is still there
    assert (await c.get("/api/mf/filters", params={"screen": "true", "fields": "nope"})).status_code == 400


@needs_db
async def test_every_count_beside_an_option_equals_what_ticking_it_gives(world):
    """The faceted counts of /filters?screen=1 against the list endpoint, for a base filter that already narrows the result."""
    c = world
    base = [("rng", "ter:0:2.0"), ("plans", "Direct")]
    s = await fac(c, *base)
    assert s["total"] == (await lst(c, *base))["total"] > 0
    checks = [("subs", "mid-cap", next(x["n"] for x in s["subs"] if x["key"] == "mid-cap")), ("cap", "small", s["cap"]["small"]), ("style", "passive", s["style"]["passive"]),
              ("struct", "open", s["struct"]["open"]), ("inst", "etf", s["inst"]["etf"]), ("amcs", "Alpha Mutual Fund", next(x["n"] for x in s["amcs"] if x["name"] == "Alpha Mutual Fund")),
              ("tags", "i_sensex", next(x["n"] for x in s["tags"] if x["tag"] == "i_sensex")), ("mat", "y1_3", s["mat"]["y1_3"]), ("exit", "d7", s["exit"]["d7"]),
              ("chk", "4", s["chk"]["4"]), ("tick", "noneg36", s["tick"]["noneg36"]), ("cflow", "pos", s["cflow"]["pos"]), ("aumrank", "top10", s["aumrank"]["top10"]),
              ("rk", "3y:q1", None), ("house", "h2", s["house"]["h2"]), ("pfdate", "latest", s["portfolio"]["latest"])]
    for key, val, want in checks:
        got = (await lst(c, *base, (key, val)))["total"]
        if want is not None:
            assert got == want, (key, val, got, want)
    assert sum(s["type"].values()) == s["total"] and s["status"]["active"] == s["total"]
    assert s["plans"].get("Regular", 0) > 0        # the plan group is counted with every OTHER filter on, not its own: Regular shows what ticking it would add
    # the count of "no data" for a group's own field never hides behind the field's own range
    s2 = await fac(c, ("rng", "ter:0:0.3"))
    assert s2["numeric"]["ter"]["m"] == (await lst(c))["total"] and s2["total"] < s2["numeric"]["ter"]["n"]


@needs_db
async def test_histograms_say_how_many_have_the_figure(world):
    c = world
    s = await fac(c, ("rng", "r3y:5:"))
    for key, h in s["numeric"].items():
        assert sum(h["bins"]) == h["n"] <= h["m"], key
        assert len(h["bins"]) == len(h["edges"]) - 1
    r3 = s["numeric"]["r3y"]
    assert r3["m"] == (await lst(c))["total"] and r3["n"] == len([1 for f in c.funds for _ in (0, 1) if mf_cagr(f, 3) is not None])
    assert s["total"] < r3["n"]                                          # the slider's own range does not flatten its histogram, the result is smaller than the picture
    # funds with no portfolio file are in M but not in N for the asset-split sliders
    eq = s["numeric"]["eq_pct"]
    assert eq["m"] > eq["n"] > 0
    only = await c.get("/api/mf/filters", params={"screen": "true", "fields": "ter,r1y"})
    assert set(only.json()["screen"]["numeric"]) == {"ter", "r1y"}


@needs_db
async def test_scatter_flows_and_build_info(world):
    c = world
    s = await fac(c, ("subs", "mid-cap"), ("plans", "Direct"))
    pts = s["scatter"]
    assert pts["shown"] == len(pts["points"]) <= 400 and pts["eligible"] >= pts["shown"] > 0
    assert all(len(p) == 4 and p[3] > 0 for p in pts["points"])
    assert s["flows"] and s["flows"][0]["key"] == "mid-cap" and len(s["flows"][0]["net"]) == len(s["flows"][0]["months"]) <= 6
    assert s["built"]["rows"] == len(c.funds) * 3 and s["built"]["tagged"] > 0 and s["built"]["indexTagged"] > 0 and s["built"]["run"]


@needs_db
async def test_responses_are_cached_with_etags_and_the_version_moves_on_a_new_run(world):
    c = world
    r = await c.get("/api/mf/filters", params={"screen": "true", "subs": "mid-cap"})
    tag = r.headers["etag"]
    r2 = await c.get("/api/mf/filters", params={"screen": "true", "subs": "mid-cap"}, headers={"if-none-match": tag})
    assert r2.status_code == 304
    other = await c.get("/api/mf/filters", params={"screen": "true", "subs": "small-cap"})
    assert other.headers["etag"] != tag
    legacy = await c.get("/api/mf/filters")
    assert "screen" not in legacy.json() and legacy.json()["totals"]["active"] == len(c.funds) * 3      # the old answer is unchanged
    await job.run(c._transport.app.state.store)
    again = await c.get("/api/mf/filters", params={"screen": "true", "subs": "mid-cap"})
    assert again.status_code == 200 and again.json()["screen"]["total"] == r.json()["screen"]["total"]


@needs_db
async def test_a_stopped_scheme_and_a_scheme_missing_from_the_job_do_not_break_the_list(world):
    c = world
    store = c._transport.app.state.store
    async with store.pool.acquire() as conn:
        code = c.funds[0].codes["Direct|Growth"]
        await conn.execute("UPDATE mf_schemes SET active = false WHERE code = $1", code)
        await conn.execute("DELETE FROM mf_screen WHERE x_code = $1", c.funds[1].codes["Direct|Growth"])      # a scheme added after last night's run
        await conn.execute("DELETE FROM mf_meta WHERE key = 'x'")
    await mf._bump(store, NAV_DATE)
    d = await lst(c)
    assert d["total"] == len(c.funds) * 2 - 1
    assert (await lst(c, ("status", "stopped")))["total"] == 1 and (await lst(c, ("status", "both")))["total"] == len(c.funds) * 2
    s = await fac(c)
    assert s["total"] == d["total"]
    r = await lst(c, ("rng", "ter:0:100"), ("extra", "true"))        # the unjoined scheme has no figures and stays out of every range, but is in the plain list
    assert r["total"] < d["total"]
