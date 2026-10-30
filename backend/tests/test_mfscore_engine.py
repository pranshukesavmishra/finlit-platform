"""FinLit Mutual Fund Health Score, part 3: the engine (every group sheet, history rows, caps, labels, ranks, reasons, compliance wording) and the
database side (job, API, plan gating)."""

import json
import re
from datetime import date

import httpx
import pytest
from fastapi import FastAPI

from finlit.mfscore import api as score_api, engine
from finlit.mfscore.engine import cap_label, label_of, score_universe, weak_cap
from finlit.mfscore.reasons import indian, texts
from finlit.mfscore.sheets import SHEETS, WEIGHTS, metric_ids

from mfscore_synth import END, fund, month_ends, series, universe

RUN = date(2026, 10, 29)
BANNED = re.compile(r"\b(buy|sell|hold|recommend\w*|best|should|advis\w+|invest in)\b", re.I)


def test_weights_and_sheets_match_the_spec():
    assert WEIGHTS["DB-CASH"] == (20, 30, 35, 15) and WEIGHTS["HY-ARB"] == (20, 20, 45, 15) and WEIGHTS["OT-PASSIVE"] == (20, 15, 40, 25) and WEIGHTS["SOL"] == (30, 35, 15, 20)
    assert all(sum(w) == 100 for w in WEIGHTS.values()) and set(WEIGHTS) == set(SHEETS) and len(SHEETS) == 16
    assert metric_ids("EQ-LARGE")[:3] == ["RET_5Y_REL", "RET_3Y_REL", "RET_1Y_REL"]
    for g, sh in SHEETS.items():
        for p, ms in sh.items():
            assert sum(m.wt for m in ms) in (100, 125), (g, p)


def test_labels_edges_and_caps():
    assert [label_of(x) for x in (100, 80, 79.9, 65, 64.9, 50, 49.9, 35, 34.9, 0)] == ["Strong", "Strong", "Healthy", "Healthy", "Average", "Average", "Weak", "Weak", "Poor", "Poor"]
    assert label_of(None) is None and cap_label("Strong") == "Healthy" and cap_label("Average") == "Average"
    assert weak_cap(30, 80)[0] == 64 and weak_cap(80, 49)[0] == 79 and weak_cap(50, 50) == (None, None)
    assert weak_cap(34.9, 90)[0] == 64


@pytest.mark.parametrize("group", sorted(WEIGHTS))
def test_every_group_sheet_scores_a_synthetic_universe(group):
    funds = universe(10, [group])
    sc = score_universe(funds, RUN)
    assert len(sc) == 20
    for s in sc:
        assert s.status == "RATED" and 0 <= s.final <= 100 and s.label in ("Strong", "Healthy", "Average", "Weak", "Poor")
        assert all(0 <= v <= 100 for v in s.pillars.values()) and 0 < s.confidence <= 1
        assert [r.id for r in s.metrics] == metric_ids(group)
        w = sum(r.weight for r in s.metrics)
        assert w == pytest.approx(100.0, abs=1e-6) or group.startswith("OT-")
        assert s.rank is not None and s.rank_of == 10          # Direct ranked against Direct only
    assert {s.plan for s in sc} == {"Direct", "Regular"}


def test_final_is_the_weighted_sum_of_pillars():
    sc = score_universe(universe(10, ["EQ-MID"]), RUN)
    s = sc[0]
    wp = WEIGHTS["EQ-MID"]
    raw = sum(w * s.pillars[p] for w, p in zip(wp, ("performance", "risk", "cost", "quality"))) / 100
    assert s.raw_final == pytest.approx(raw)


def test_history_rows_status():
    peers_ = [fund(f"p{i}", "EQ-LARGE", "large-cap", seed=i + 10) for i in range(10)]
    young = fund("y", "EQ-LARGE", "large-cap", months=24, seed=3)
    mid = fund("m", "EQ-LARGE", "large-cap", months=48, seed=4)
    tiny = fund("t", "EQ-LARGE", "large-cap", months=8, seed=5)
    sc = {s.key: s for s in score_universe(peers_ + [young, mid, tiny], RUN)}
    assert sc["p0"].status == "RATED"
    assert sc["m"].status == "RATED" and next(r for r in sc["m"].metrics if r.id == "RET_5Y_REL").state == "F"
    assert next(r for r in sc["m"].metrics if r.id == "RET_ABS").state == "S"        # 3-year stands in for the missing 5-year
    assert sc["y"].status in ("PROVISIONAL", "NOT RATED") and sc["y"].months == 24
    if sc["y"].status == "PROVISIONAL":
        assert sc["y"].label in ("Healthy", "Average", "Weak", "Poor")                  # never above Healthy
    assert sc["t"].status == "NOT RATED" and sc["t"].final is None and "under 12 months" in sc["t"].reason and sc["t"].label is None


def test_provisional_label_is_capped_at_healthy():
    peers_ = [fund(f"p{i}", "EQ-LARGE", "large-cap", seed=i + 10, drift=0.5) for i in range(10)]
    star = fund("s", "EQ-LARGE", "large-cap", months=30, seed=99, drift=2.5, vol=1.0)
    s = next(x for x in score_universe(peers_ + [star], RUN) if x.key == "s")
    if s.status == "PROVISIONAL":
        assert s.label in ("Healthy", "Average", "Weak", "Poor")


def test_weak_fund_cap_stops_a_high_return_hiding_weak_risk():
    peers_ = [fund(f"p{i}", "EQ-LARGE", "large-cap", seed=i + 10, drift=0.8, vol=3.0) for i in range(10)]
    wild = fund("w", "EQ-LARGE", "large-cap", seed=77, drift=2.0, vol=12.0, mdd=-60.0)
    s = next(x for x in score_universe(peers_ + [wild], RUN) if x.key == "w")
    if s.pillars["risk"] < 50 or s.pillars["quality"] < 50:
        assert s.final <= 79 and (s.cap is not None or s.raw_final <= 79)


def test_ranks_and_percentiles_are_within_category_and_plan():
    sc = score_universe(universe(10, ["EQ-LARGE"]), RUN)
    direct = sorted((s for s in sc if s.plan == "Direct"), key=lambda s: -s.final)
    assert direct[0].rank == 1 and direct[0].percentile == 100 and direct[-1].percentile == 0 and direct[-1].rank == 10 or direct[-1].rank <= 10
    assert all(s.rank_scope == "sub" and s.rank_of == 10 for s in sc)


def test_passive_funds_rank_inside_their_tracking_family_and_etfs_apart_from_funds():
    funds = []
    for i in range(5):
        funds.append(fund(f"mf:i{i}", "OT-PASSIVE", "index-funds", seed=20 + i, family_key="nifty50", ter=0.2 + i * 0.05))
    for i in range(4):
        funds.append(fund(f"etf:e{i}", "OT-PASSIVE", "etf", plan="ETF", kind="etf", seed=40 + i, family_key="nifty50", turnover_cr=10.0, premium=0.1, traded_on_nav_date=True))
    sc = {s.key: s for s in score_universe(funds, RUN)}
    assert sc["mf:i0"].rank_scope == "fam" and sc["mf:i0"].rank_of == 5 and sc["etf:e0"].rank_of == 4
    r = {x.id: x for x in sc["mf:i0"].metrics}["RET_3Y_REL"]
    assert r.scope == "fam" and r.peer_n == 4
    lone = fund("mf:lone", "OT-PASSIVE", "index-funds", seed=1, family_key="rareindex")
    s = score_universe(funds + [lone], RUN)[-1]
    assert next(x for x in s.metrics if x.id == "RET_3Y_REL").state == "F"           # a family of one: never widened


def test_group_value_is_min_of_median_and_50_and_filled_gaps_take_it():
    funds = universe(10, ["EQ-LARGE"])
    for f in funds[:10]:
        f.ter = 0.0                                                                    # all Direct funds: TER reported as 0
    sc = score_universe(funds, RUN)
    s = sc[0]
    m = next(r for r in s.metrics if r.id == "TER_ABS")
    assert m.state == "F" and m.gv is not None and m.points == m.gv <= 50
    assert s.confidence < 1


def test_group_value_is_50_with_fewer_than_8_actual_values():
    funds = [fund(f"p{i}", "EQ-LARGE", "large-cap", seed=i) for i in range(5)]
    funds[0].ter = None
    s = score_universe(funds, RUN)[0]
    assert next(r for r in s.metrics if r.id == "TER_ABS").gv == 50.0


def test_reasons_cover_strengths_watchouts_gaps_and_use_no_advice_words():
    funds = universe(12, ["EQ-LARGE", "DB-CASH", "HY-ARB", "OT-PASSIVE", "SOL"])
    funds[0].ter = None
    sc = score_universe(funds, RUN)
    seen = 0
    for s in sc:
        r = s.reasons
        assert len(r["strengths"]) <= 3 and len(r["watchouts"]) <= 3
        for line in r["strengths"] + r["watchouts"] + r["gaps"] + r["notApplicable"]:
            assert not BANNED.search(line["text"]), line["text"]
            assert "{" not in line["text"]
            seen += 1
    assert seen > 50 and sc[0].reasons["gaps"] and any(g["why"] == "ter_missing" for g in sc[0].reasons["gaps"])
    assert any(s.near_identical and "NEAR_IDENTICAL" in s.flags for s in sc)


def test_reasons_data_file_has_a_template_for_every_metric_and_no_banned_words():
    t = texts()
    every = {m for g in SHEETS for m in metric_ids(g)}
    assert every <= set(t["metrics"])
    blob = json.dumps(t)
    assert not BANNED.search(re.sub(r"_about[^}]*", "", blob.split('"metrics"')[1]))
    assert indian(12345678) == "1,23,45,678" and indian(5000) == "5,000" and indian(999) == "999"


def test_frozen_nav_and_break_flags_travel_with_the_score():
    peers_ = [fund(f"p{i}", "EQ-LARGE", "large-cap", seed=i + 10) for i in range(10)]
    frozen = fund("f", "EQ-LARGE", "large-cap", seed=1)
    frozen.mnavs = series(61, 0, 0, 0, rets=[0.0011 if i % 2 else -0.0011 for i in range(60)])
    s = next(x for x in score_universe(peers_ + [frozen], RUN) if x.key == "f")
    assert "FROZEN_NAV" in s.flags and "NAV_BREAK" in s.flags


def test_scores_are_deterministic():
    a = score_universe(universe(9, ["EQ-SMALL"]), RUN)
    b = score_universe(universe(9, ["EQ-SMALL"]), RUN)
    assert [s.final for s in a] == [s.final for s in b]


# ------------------------------------------------------------------------------------------------------------ database and API
from test_integration import TEST_DB, TEST_REDIS  # noqa: E402
from finlit.config import Settings  # noqa: E402
from finlit.store import Store  # noqa: E402
from finlit.mfscore import job  # noqa: E402
from finlit.mfscore.loader import portfolio_summary  # noqa: E402


@pytest.fixture
async def store():
    s = Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        st = await Store.connect(s, migrate=True)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres not available: {exc}")
    async with st.pool.acquire() as c:
        await c.execute("TRUNCATE mf_scores")
    yield st
    await st.close()


def test_portfolio_summary_reads_split_top10_and_largest_sector():
    h = [["A", None, "Banks", "e", 20.0, 1, 1], ["B", None, "Banks", "e", 10.0, 1, 1], ["C", None, "IT", "e", 25.0, 1, 1], ["D", None, "Not classified", "e", 5.0, 1, 1],
         ["E", None, None, "d", 30.0, 1, 1], ["F", None, None, "c", 8.0, 1, 1], ["G", None, None, "o", 2.0, 1, 1]]
    s = portfolio_summary(h)
    assert s["equity_pct"] == 60.0 and s["other_pct"] == 2.0 and s["split_sum"] == 100.0 and s["top10"] == 92.0 and s["sector_top"] == 30.0
    assert portfolio_summary([])["split_sum"] == 0.0


async def _write(store, funds):
    sc = score_universe(funds, RUN)
    by = {f.key: f for f in funds}
    async with store.pool.acquire() as c:
        await c.executemany(job.UPSERT, [job.row(s, by[s.key], RUN) for s in sc])
    return sc


def _app(store, plan="gold", role="visitor"):
    from finlit.auth.service import Ctx
    app = FastAPI()
    app.include_router(score_api.router)
    app.state.store = store
    return app, Ctx(user_id="u", plan=plan, role=role)


async def _client(store, monkeypatch, plan):
    app, ctx = _app(store, plan)

    async def cur(request):
        return ctx
    monkeypatch.setattr(score_api, "current", cur)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_job_rows_and_api_gating(store, monkeypatch):
    funds = universe(10, ["EQ-LARGE"])
    for i, f in enumerate(funds):
        f.code, f.key = 900000 + i, f"mf:{900000 + i}"
        f.category = "Equity Scheme - Large Cap Fund"
    await _write(store, funds)
    async with store.pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM mf_scores") == 20
        await c.executemany(job.UPSERT, [job.row(s, {f.key: f for f in funds}[s.key], RUN) for s in score_universe(funds, RUN)])   # idempotent
        assert await c.fetchval("SELECT count(*) FROM mf_scores") == 20
    code = funds[0].code
    async with await _client(store, monkeypatch, "gold") as c:
        r = await c.get(f"/api/mf/scores?codes={code}")
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
        it = r.json()["items"][0]
        assert it["final"] is not None and set(it["pillars"]) == {"performance", "risk", "cost", "quality"}
        lst = (await c.get("/api/mf/scores?group=EQ-LARGE&plan=Direct&sort=final&limit=5")).json()
        assert len(lst["items"]) == 5 and lst["total"] == 10
        fs = [i["final"] for i in lst["items"]]
        assert fs == sorted(fs, reverse=True)
    async with await _client(store, monkeypatch, "gold") as c:
        # the specific route is not claimed by an integer path
        assert (await c.get("/api/mf/scores?sort=bogus")).status_code == 400
    async with await _client(store, monkeypatch, "basic") as c:
        r = await c.get(f"/api/mf/scores?codes={code}")
        it = r.json()["items"][0]
        assert r.json()["locked"] and it["final"] is None and it["pillars"] is None and it["rank"] is None and it["label"] is None
        assert (await c.get("/api/mf/scores?group=EQ-LARGE")).json()["items"] == []            # a list's order would leak the ranking
        body = (await c.get(f"/api/mf/scores?codes={code}")).text
        sd = (await c.get(f"/api/mf/{code}/score")).json()
        assert sd["locked"] and sd["final"] is None and all(p["score"] is None for p in sd["pillars"]) and "metrics" not in sd and "reasons" not in sd and "rank" not in sd
        assert str(funds[0].code) in body
    async with await _client(store, monkeypatch, "gold") as c:
        r = (await c.get(f"/api/mf/{code}/score")).json()
        assert not r["locked"] and r["final"] is not None and len(r["pillars"]) == 4 and r["metrics"] and r["rank"]["of"] == 10
        assert r["disclaimer"].startswith("Describes the fund's health") and r["method"] == "/methodology/mf-score"
        assert not BANNED.search(json.dumps(r["reasons"]))


async def test_not_rated_and_inherited_and_unscored_answers(store, monkeypatch):
    async with store.pool.acquire() as c:
        await c.execute("DELETE FROM mf_schemes WHERE code IN (910001, 910002, 910003)")
        base = dict(amc="X Mutual Fund", scheme_type="Open Ended", category="Equity Scheme - Large Cap Fund", family="x|y|z", nav=10.0, nav_date=date(2026, 10, 28))
        for code, plan, opt, active in ((910001, "Direct", "Growth", True), (910002, "Direct", "IDCW", True), (910003, "Direct", "IDCW", False)):
            await c.execute("INSERT INTO mf_schemes (code, name, plan, option_class, family, amc, scheme_type, category, nav, nav_date, active) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                            code, f"Fund {code}", plan, opt, base["family"] if code != 910003 else "lone|family", base["amc"], base["scheme_type"], base["category"], 10.0, base["nav_date"], active)
    tiny = fund("mf:910001", "EQ-LARGE", "large-cap", months=8, seed=3)
    tiny.code, tiny.category = 910001, "Equity Scheme - Large Cap Fund"
    await _write(store, [tiny])
    async with await _client(store, monkeypatch, "gold") as c:
        n = (await c.get("/api/mf/910001/score")).json()
        assert n["status"] == "NOT RATED" and n["final"] is None and "under 12 months" in n["reason"] and n["pillars"][0]["score"] is None
        i = (await c.get("/api/mf/910002/score")).json()
        assert i["status"] == "NOT RATED" and i["inherited"]["code"] == 910001
        s = (await c.get("/api/mf/910003/score")).json()
        assert s["status"] == "NOT SCORED" and "IDCW" in s["reason"]
        assert (await c.get("/api/mf/99999999/score")).status_code in (404, 422)
        assert (await c.get("/api/mf/555555/score")).status_code == 404
    async with store.pool.acquire() as c:
        await c.execute("DELETE FROM mf_schemes WHERE code IN (910001, 910002, 910003)")


async def test_the_fund_list_sorts_by_score_for_gold_only(store, monkeypatch):
    from finlit import mf
    app = FastAPI()
    app.include_router(score_api.router)
    app.include_router(mf.router)
    app.state.store = store
    from finlit.auth.service import Ctx
    ctx = {"v": Ctx(user_id="u", plan="basic")}

    async def cur(request):
        return ctx["v"]
    monkeypatch.setattr(score_api, "current", cur)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/mf?sort=score&dir=desc")
        assert r.status_code == 403
        ctx["v"] = Ctx(user_id="u", plan="gold")
        r = await c.get("/api/mf?sort=score&dir=desc")
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"


# ---------------------------------------------------------------------------------------- the category dashboard, ETF symbols and the ETF list order
def test_dashboard_summary_median_counts_and_bands():
    from finlit.mfscore.dashboard import band_of, median, summarize
    assert median([]) is None and median([40.0]) == 40.0 and median([10, 90, 50, 30]) == 40.0 and median([3, 1, 2]) == 2
    assert [band_of(v) for v in (70.0, 69.9, 50.0, 49.9, 0.0, 100.0)] == ["green", "orange", "orange", "red", "red", "green"]
    out = summarize([("large-cap", 80.0), ("large-cap", 60.0), ("large-cap", 40.0), ("large-cap", None), ("mid-cap", None), ("small-cap", 55.55)])
    assert out["large-cap"] == {"median": 60.0, "n": 3, "green": 1, "orange": 1, "red": 1}
    assert out["small-cap"]["median"] == 55.5 or out["small-cap"]["median"] == 55.6
    assert "mid-cap" not in out                       # no scored fund: no entry, never a made-up zero


async def test_category_dashboard_is_gold_only_and_direct_plan_only(store, monkeypatch):
    async with store.pool.acquire() as c:
        await c.execute("DELETE FROM mf_scores")
    async with await _client(store, monkeypatch, "gold") as c:
        r = (await c.get("/api/mf/scores/categories")).json()
        assert r["locked"] is False and r["runDate"] is None and r["items"] == {}          # the score job has not run: the page says "Not scored yet"
    funds = universe(10, ["EQ-LARGE"])
    for i, f in enumerate(funds):
        f.code, f.key, f.category = 900000 + i, f"mf:{900000 + i}", "Equity Scheme - Large Cap Fund"
    sc = await _write(store, funds)
    direct = sorted(round(s.final, 1) for s, f in zip(sc, funds) if f.plan == "Direct" and s.final is not None)
    async with await _client(store, monkeypatch, "gold") as c:
        r = await c.get("/api/mf/scores/categories")
        assert r.headers["cache-control"] == "private, no-store"
        it = r.json()["items"]["large-cap"]
        assert it["n"] == len(direct) and it["green"] + it["orange"] + it["red"] == it["n"]            # the Regular plan funds are not counted
        assert abs(it["median"] - (direct[len(direct) // 2] if len(direct) % 2 else (direct[len(direct) // 2 - 1] + direct[len(direct) // 2]) / 2)) <= 0.11
        assert r.json()["plan"] == "Direct" and r.json()["disclaimer"].startswith("Describes the fund's health")
    for plan in ("basic", "silver"):
        async with await _client(store, monkeypatch, plan) as c:
            r = await c.get("/api/mf/scores/categories")
            assert r.json()["locked"] is True and r.json()["items"] == {} and "median" not in r.text and "large-cap" not in r.text


async def test_scores_by_etf_symbol_are_redacted_for_basic(store, monkeypatch):
    etfs = [fund(f"etf:ZZ{i}", "OT-PASSIVE", "etf", plan="ETF", seed=40 + i, kind="etf", symbol=f"ZZ{i}", family_key="nifty50") for i in range(4)]
    await _write(store, etfs)
    async with await _client(store, monkeypatch, "gold") as c:
        r = (await c.get("/api/mf/scores?symbols=zz0,ZZ1,ZZNONE")).json()
        by = {i["symbol"]: i for i in r["items"]}
        assert set(by) == {"ZZ0", "ZZ1"} and by["ZZ0"]["final"] is not None and by["ZZ0"]["plan"] == "ETF" and by["ZZ0"]["code"] is None
        assert (await c.get("/api/mf/scores?symbols=bad%20one")).status_code == 400
    async with await _client(store, monkeypatch, "basic") as c:
        r = await c.get("/api/mf/scores?symbols=ZZ0,ZZ1")
        assert r.json()["locked"] is True and all(i["final"] is None and i["pillars"] is None and i["label"] is None for i in r.json()["items"])
        assert (await c.get("/api/mf/scores?plan=ETF")).json()["items"] == []


async def test_the_etf_list_sorts_by_score_for_gold_only(store, monkeypatch):
    from finlit import etf
    etfs = [fund(f"etf:ZY{i}", "OT-PASSIVE", "etf", plan="ETF", seed=60 + i, drift=0.2 + i * 0.3, kind="etf", symbol=f"ZY{i}", family_key="nifty50") for i in range(4)]
    sc = await _write(store, etfs)
    finals = {s.key.split(":")[1]: s.final for s in sc}
    rows = [{"symbol": f"ZY{i}", "display_name": f"Test ETF {i}", "isin": f"INF00000000{i}", "category": None, "price_date": date(2026, 10, 29), "updated_at": None, "hot": False} for i in range(4)]
    app, _ = _app(store)
    app.include_router(etf.router)
    app.state.etf_cache = {"at": 1e18, "rows": rows, "by": {r["symbol"]: r for r in rows}, "words": {}, "asOf": "2026-10-29", "updatedAt": None}
    ctx = {"v": None}
    from finlit.auth.service import Ctx

    async def cur(request):
        return ctx["v"]
    monkeypatch.setattr(score_api, "current", cur)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        ctx["v"] = Ctx(user_id="u", plan="basic")
        assert (await c.get("/api/etf?sort=score&order=desc")).status_code == 403
        assert (await c.get("/api/etf?sort=turnover")).headers["cache-control"].startswith("public")      # the plain list is unchanged
        ctx["v"] = Ctx(user_id="u", plan="gold")
        r = await c.get("/api/etf?sort=score&order=desc")
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
        got = [i["symbol"] for i in r.json()["items"]]
        assert got == sorted(got, key=lambda s: -finals[s])
        assert "final" not in r.text                                                                       # the list itself carries no score; the page asks /api/mf/scores
