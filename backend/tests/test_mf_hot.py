"""Mutual funds, part 2: unlisted fund houses, hot and cold storage, the nightly 1 and 5 year figures, and the facts / portfolio routes (finlit/mf.py).

The fund-house names below are every `amc` stored in the full local load of AMFI's NAVAll.txt (2026-10-21), so the matching rule is proven against real names.
"""

import sys
import time
import types
from datetime import date

import httpx
import pytest

from finlit import mf
from finlit.config import MF_EXCLUDED_AMCS
from test_mf import HISTORY, LARGE, LIQUID, NAVALL, amfi_client, api, loaded, store  # noqa: F401  (fixtures)

REAL_HOUSES = """360 ONE Mutual Fund|ASK MUTUAL FUND|Abakkus Mutual Fund|Aditya Birla Sun Life Mutual Fund|AlphaGrep Mutual Fund|Angel One Mutual Fund|Axis Mutual Fund|
Bajaj Finserv Mutual Fund|Bandhan Mutual Fund|Bank of India Mutual Fund|Baroda BNP Paribas Mutual Fund|Canara Robeco Mutual Fund|Capitalmind Mutual Fund|Carnelian Mutual Fund|
Choice Mutual Fund|DSP Mutual Fund|Edelweiss Mutual Fund|Franklin Templeton Mutual Fund|Groww Mutual Fund|HDFC Mutual Fund|HSBC Mutual Fund|Helios Mutual Fund|
ICICI Prudential Mutual Fund|IL&FS Mutual Fund (IDF)|ITI Mutual Fund|Invesco Mutual Fund|JM Financial Mutual Fund|Jio BlackRock Mutual Fund|Kotak Mahindra Mutual Fund|
LIC Mutual Fund|Lakshya Mutual Fund|Mahindra Manulife Mutual Fund|Mirae Asset Mutual Fund|Monarch Mutual Fund|Motilal Oswal Mutual Fund|NJ Mutual Fund|Navi Mutual Fund|
Nippon India Mutual Fund|Old Bridge Mutual Fund|PGIM India Mutual Fund|PPFAS Mutual Fund|Quantum Mutual Fund|SBI Mutual Fund|Samco Mutual Fund|Shriram Mutual Fund|
Sundaram Mutual Fund|Tata Mutual Fund|Taurus Mutual Fund|The Wealth Company Mutual Fund|Trust Mutual Fund|UTI Mutual Fund|Unifi Mutual Fund|Union Mutual Fund|
WhiteOak Capital Mutual Fund|Zerodha Mutual Fund|quant Mutual Fund""".replace("\n", "").split("|")


def test_exclusion_matches_exactly_the_eleven_named_houses():
    hit = sorted(h for h in REAL_HOUSES if mf.is_excluded_amc(h))
    print("excluded:", hit)
    assert len(REAL_HOUSES) == len(set(REAL_HOUSES)) == 56
    assert hit == sorted(["ASK MUTUAL FUND", "Abakkus Mutual Fund", "ITI Mutual Fund", "Lakshya Mutual Fund", "NJ Mutual Fund", "PGIM India Mutual Fund", "Samco Mutual Fund",
                          "Taurus Mutual Fund", "Trust Mutual Fund", "Unifi Mutual Fund", "Zerodha Mutual Fund"])
    assert len(MF_EXCLUDED_AMCS) == 11 and {mf.house_stem(n) for n in MF_EXCLUDED_AMCS} == mf.EXCLUDED_STEMS
    # every entry of the list matches at least one real house
    assert all(any(mf.house_stem(h) == mf.house_stem(n) for h in REAL_HOUSES) for n in MF_EXCLUDED_AMCS)


@pytest.mark.parametrize("name,want", [
    ("Trust Mutual Fund", True), ("TRUST MUTUAL FUND", True), ("Trust  Mutual   Fund", True), ("Trust Asset Management Company Limited", True), ("PGIM India Mutual Fund", True),
    ("Trustline Mutual Fund", False), ("Union Mutual Fund", False), ("Unity Mutual Fund", False), ("Bank of India Mutual Fund", False), ("Franklin Templeton Mutual Fund", False),
    ("ITI Mutual Fund", True), ("Digital ITI Mutual Fund", False), ("NJ Mutual Fund", True), ("NJ India Mutual Fund", False), ("Ask Wealth Advisors Mutual Fund", False), ("Samco Mutual Fund", True),
])
def test_exclusion_edge_cases(name, want):
    assert mf.is_excluded_amc(name) is want


def with_house(text: str, house: str, code: int, name: str) -> str:
    return text.rstrip("\n") + f"\n\nOpen Ended Schemes ( Equity Schemes - Flexi Cap Fund )\n\n{house}\n\n{code};INF000X01AA1;-;{name};Direct Plan;Growth Option;12.5000;20-Oct-2026\n"


@pytest.mark.integration
async def test_unlisted_houses_are_not_loaded_not_listed_not_searchable_and_old_rows_are_pruned(store):  # noqa: F811
    text = with_house(NAVALL, "Trust Mutual Fund", 999001, "Trust Flexi Cap Fund - Direct Plan - Growth")
    async with amfi_client(navall=text) as c:
        res = await mf.refresh(store, None, client=c)
    assert res["status"] == "ok" and res["excludedSchemesSkipped"] == 1 and res["excludedRowsPruned"] == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_schemes WHERE code = 999001") == 0
        # a row from before the rule existed (and its backfill record) is deleted by the next refresh, and only that house's
        await conn.execute("INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, family) VALUES (999002, 'Zerodha Nifty Fund', 'Zerodha Mutual Fund', 'Open Ended', 'x', 'Direct', 'Growth', 'f')")
        await conn.execute("INSERT INTO mf_backfill (amc_key, amc) VALUES ('zerodha', 'Zerodha Mutual Fund')")
        before = await conn.fetchval("SELECT count(*) FROM mf_schemes")
    async with amfi_client(navall=text) as c:
        res = await mf.refresh(store, None, client=c)
        again = await mf.refresh(store, None, client=c)
    assert res["excludedRowsPruned"] == 1 and again["excludedRowsPruned"] == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_schemes") == before - 1
        assert await conn.fetchval("SELECT count(*) FROM mf_backfill WHERE amc_key = 'zerodha'") == 0
        assert await conn.fetchval("SELECT count(*) FROM mf_schemes WHERE amc = 'Axis Mutual Fund'") > 0   # other houses untouched
    assert await mf.prune_excluded(store) == 0


@pytest.mark.integration
async def test_api_never_returns_an_unlisted_house(api):  # noqa: F811
    async with api.app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, family, nav, nav_date, active) VALUES "
                           "(999003, 'Taurus Banking Fund', 'Taurus Mutual Fund', 'Open Ended', 'Equity', 'Direct', 'Growth', 'f', 10, '2026-10-19', true)")
        await mf.prune_excluded(api.app.state.store)
    await api.app.state.store.redis.set("mf:ver", "after-prune")
    assert (await api.get("/api/mf?q=taurus banking")).json()["total"] == 0
    f = (await api.get("/api/mf/filters")).json()
    assert all("Taurus" not in a["name"] for a in f["amcs"]) and f["excludedAmcs"] == list(MF_EXCLUDED_AMCS)
    assert (await api.get("/api/mf/999003")).status_code == 404


# ---------------------------------------------------------------------------------------------- hot and cold

@pytest.mark.integration
async def test_hot_set_keeps_series_only_for_hot_schemes_and_cold_ones_keep_their_1y_5y(loaded, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mf, "HOT_SIZE", 2)
    async with loaded.pool.acquire() as conn:
        n_before = await conn.fetchval("SELECT count(*) FROM mf_history")
    async with amfi_client() as c:
        out = await mf.refresh_hot(loaded, c)
    assert n_before == 4 and out["hot"] == 2 and out["basis"] == "fallback" and out["historyDropped"] == 2
    async with loaded.pool.acquire() as conn:
        hot = [r["code"] for r in await conn.fetch("SELECT code FROM mf_hot ORDER BY rank")]
        kept = {r["code"] for r in await conn.fetch("SELECT code FROM mf_history")}
        cold = await conn.fetchrow("SELECT r1y, r5y, r3y, vol1y, mdd, has_hist, sip3y FROM mf_schemes WHERE code = ANY($1::int[]) AND code <> ALL($2::int[]) AND option_class = 'Growth' AND r1y IS NOT NULL LIMIT 1",
                                   [LARGE, LIQUID, 151368, 152805], hot)
    assert len(hot) == 2 and kept == set(hot)
    # a cold row keeps 1Y, 3Y and 5Y (kept current nightly by refresh_anchors), the SIP figures (refresh_monthly) and the previous NAV; volatility and drawdown go
    assert cold["r1y"] is not None and cold["vol1y"] is None and cold["mdd"] is None
    body = await loaded.redis.get("mf:hot:list")
    assert body and b"NOT a ranking by size" in body


@pytest.mark.integration
async def test_hot_endpoint_and_hot_detail_are_served_from_redis(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mf, "HOT_SIZE", 3)   # only two Direct Growth schemes in the sample have a 5 year figure
    async with amfi_client() as c:
        await mf.refresh_hot(api.app.state.store, c)
    h = (await api.get("/api/mf/hot")).json()
    assert [i["rank"] for i in h["items"]] == [1, 2] and h["basis"].startswith("No verified fund size") and h["source"].startswith("AMFI")
    assert all(set(i) >= {"code", "name", "r1y", "r5y", "change", "retDate"} for i in h["items"])
    code = h["items"][0]["code"]
    r = await api.get(f"/api/mf/{code}")
    assert r.headers["x-mf-path"] == "hot" and r.json()["code"] == code and r.json()["series"]
    cold = next(c for c in (LARGE, LIQUID, 151368, 152805) if c not in {i["code"] for i in h["items"]})
    assert "x-mf-path" not in (await api.get(f"/api/mf/{cold}")).headers
    # the DB copy answers when Redis lost the key
    await api.app.state.store.redis.delete("mf:hot:list")
    assert len((await api.get("/api/mf/hot")).json()["items"]) == 2
    # opens are counted for the fallback ranking
    assert int(await api.app.state.store.redis.hget(mf.OPENS_KEY, str(code))) >= 1


@pytest.mark.integration
async def test_cold_scheme_is_fetched_once_cached_with_a_stamp_and_expires(api):  # noqa: F811
    from test_mf import FakeMirror
    store_ = api.app.state.store
    async with store_.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_history WHERE code = $1", LARGE)
    await store_.redis.set("mf:ver", "cold-1")
    fake = FakeMirror()
    api.app.state.mf_client = fake.client()
    d = (await api.get(f"/api/mf/{LARGE}")).json()
    assert d["history"]["source"] == "mirror" and fake.calls == 1
    raw = await store_.redis.get(f"mf:cold:{LARGE}")
    ttl = await store_.redis.ttl(f"mf:cold:{LARGE}")
    import json
    stamp = json.loads(raw)["o"]
    assert abs(stamp - time.time()) < 30 and 0 < ttl <= mf.COLD_TTL
    # the number on the page equals the number the list shows from the nightly figures
    lst = next(i for i in (await api.get("/api/mf?q=axis large cap")).json()["items"] if i["code"] == LARGE)
    assert lst["r1y"] == d["returns"]["1y"]["value"] and lst["r5y"] == d["returns"]["5y"]["value"]
    async with store_.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_history WHERE code = $1", LARGE) == 0   # nothing was written to Postgres for a cold scheme


@pytest.mark.integration
async def test_nightly_anchor_figures_equal_the_figures_from_the_full_series(loaded):  # noqa: F811
    async with loaded.pool.acquire() as conn:
        want = {r["code"]: (r["r1y"], r["r5y"], r["r3y"]) for r in await conn.fetch("SELECT code, r1y, r5y, r3y FROM mf_schemes WHERE code = ANY($1::int[])", [LARGE, LIQUID, 151368, 152805])}
        await conn.execute("DELETE FROM mf_history")
        await conn.execute("UPDATE mf_schemes SET r1y = NULL, r5y = NULL, r3y = NULL WHERE code = ANY($1::int[])", list(want))
    c = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=HISTORY.encode())))   # every window answers with the recorded history
    out = await mf.refresh_anchors(loaded, c, date(2026, 10, 19))
    assert out["failed"] == [] and out["updated"] >= 4 and out["previousNavs"] >= 4
    async with loaded.pool.acquire() as conn:
        got = {r["code"]: (r["r1y"], r["r5y"], r["r3y"]) for r in await conn.fetch("SELECT code, r1y, r5y, r3y FROM mf_schemes WHERE code = ANY($1::int[])", list(want))}
    async with loaded.pool.acquire() as conn:
        prev = await conn.fetchrow("SELECT nav_date, prev_nav, prev_date FROM mf_schemes WHERE code = $1", LARGE)
    assert (prev["prev_date"], prev["prev_nav"]) == (date(2026, 10, 16), 67.56)   # the NAV before 19 Oct in AMFI's own history
    for code, (a, b, c) in want.items():
        assert got[code][0] == pytest.approx(a) and (got[code][1] == pytest.approx(b) if b is not None else got[code][1] is None), code
        assert (got[code][2] == pytest.approx(c) if c is not None else got[code][2] is None), code   # the 3 year figure too


@pytest.mark.integration
async def test_failed_anchor_download_keeps_the_old_figures(loaded):  # noqa: F811
    async with loaded.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_history")
        old = await conn.fetchval("SELECT r1y FROM mf_schemes WHERE code = $1", LARGE)
    c = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>form</html>")))
    out = await mf.refresh_anchors(loaded, c, date(2026, 10, 19))
    assert out["failed"] == ["1y", "3y", "5y", "1d"] and out["updated"] == 0
    async with loaded.pool.acquire() as conn:
        assert await conn.fetchval("SELECT r1y FROM mf_schemes WHERE code = $1", LARGE) == old


@pytest.mark.integration
async def test_one_day_change_is_the_last_two_navs_of_the_series(api):  # noqa: F811
    d = (await api.get(f"/api/mf/{LARGE}")).json()
    days = [ln.split(";") for ln in HISTORY.splitlines() if ln.startswith(f"{LARGE};")]
    from datetime import datetime
    pts = sorted((datetime.strptime(x[7], "%d-%b-%Y").date(), float(x[6])) for x in days)
    (d0, v0), (d1, v1) = pts[-2], pts[-1]
    assert d["navDate"] == d1.isoformat() and d["change"]["since"] == d0.isoformat() and d["change"]["pct"] == round((v1 / v0 - 1) * 100, 2)


# ---------------------------------------------------------------------------------------------- facts and portfolio

def stub_disclosure(monkeypatch, **fns):
    import finlit
    mod = types.ModuleType("finlit.disclosure")
    for k, v in fns.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, "finlit.disclosure", mod)
    monkeypatch.setattr(finlit, "disclosure", mod, raising=False)


def no_disclosure(monkeypatch):
    import finlit
    monkeypatch.setitem(sys.modules, "finlit.disclosure", None)
    monkeypatch.delattr(finlit, "disclosure", raising=False)


@pytest.mark.integration
async def test_facts_and_portfolio_say_why_when_the_disclosure_module_is_missing(api, monkeypatch):  # noqa: F811
    no_disclosure(monkeypatch)
    f = (await api.get(f"/api/mf/{LARGE}/facts")).json()
    assert f["facts"]["aum"]["unavailable"] and "not loaded" in f["facts"]["aum"]["unavailable"]
    assert f["facts"]["category"]["value"].startswith("Equity Schemes") and f["facts"]["amc"]["source"].startswith("AMFI") and f["facts"]["amc"]["asOf"] == "2026-10-19"
    assert [k for k in f["order"]][:3] == ["aum", "terRegular", "terDirect"]
    p = (await api.get(f"/api/mf/{LARGE}/portfolio")).json()
    assert p == {"unavailable": mf.NO_PORTFOLIO}
    assert (await api.get("/api/mf/999999/facts")).status_code == 404 and (await api.get("/api/mf/999999/portfolio")).status_code == 404


@pytest.mark.integration
async def test_facts_and_portfolio_pass_the_disclosure_payload_through(api, monkeypatch):  # noqa: F811
    port = {"asOf": "2026-09-30", "previousAsOf": "2026-08-31", "source": "Axis AMC monthly portfolio", "sourceUrl": "https://example.invalid/p", "holdings": [], "exited": [],
            "summary": {"count": 0, "top10Pct": None, "assetSplit": {"equity": None, "debt": None, "cash": None, "other": None}, "sectors": []}}

    async def get_facts(pool, code):
        return {"aum": {"value": 1234.5, "asOf": "2026-09-30", "source": "AMFI"}, "terDirect": {"unavailable": "not published"}}

    async def get_portfolio(pool, code):
        assert code == LARGE
        return port
    stub_disclosure(monkeypatch, get_facts=get_facts, get_portfolio=get_portfolio)
    f = (await api.get(f"/api/mf/{LARGE}/facts")).json()["facts"]
    assert f["aum"] == {"value": 1234.5, "asOf": "2026-09-30", "source": "AMFI"} and f["terDirect"] == {"unavailable": "not published"}
    assert "Not published in the sources" in f["exitLoad"]["unavailable"]
    assert (await api.get(f"/api/mf/{LARGE}/portfolio")).json() == port


@pytest.mark.integration
async def test_a_failing_disclosure_module_never_breaks_the_page(api, monkeypatch):  # noqa: F811
    async def boom(pool, code):
        raise RuntimeError("down")
    stub_disclosure(monkeypatch, get_facts=boom, get_portfolio=boom)
    assert (await api.get(f"/api/mf/{LARGE}/facts")).status_code == 200
    assert "unavailable" in (await api.get(f"/api/mf/{LARGE}/portfolio")).json()
