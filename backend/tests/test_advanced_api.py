"""Advanced charts: the cross-section engine on a fake screener Table (exclusion accounting, lenders, trim, same-FY, log, highlights),
index reference points (ratio of sums vs median by hand, coverage threshold, never in the statistics, whitelist), the CSV guard, and the
HTTP routes with real sessions (gating per plan, company limits, export, history and technical charts on the ingested RELIANCE fixture)."""

import json
import math

import pytest
from pydantic import ValidationError

from finlit.advanced import index as I
from finlit.advanced import table as T
from finlit.advanced.api import CrossIn, benchmark_years, safe_cell
from finlit.advanced.catalog import METRICS
from finlit.screener.data import Table
from test_auth import app, new_client, signed_in  # noqa: F401
from test_integration import ingested, make_settings, store  # noqa: F401


def _row(sym, sector, full=True, industry=None, **m):
    return {"symbol": sym, "name": sym.title(), "sector": sector, "industry": industry, "band": None, "full": full, "metrics": json.dumps(m)}


def fake_table():
    rows = []
    for i in range(40):
        m = dict(market_cap=1000.0 + 100 * i, pb=1 + 0.1 * i, pe=10 + i * 0.7 + (i % 4), dividend_yield=1.0 + (i % 5) * 0.2, current_ratio=1 + (i % 7) * 0.1,
                 debt_to_equity=0.2 + 0.01 * i, enterprise_value=1200.0 + 100 * i, is_bank=1.0 if i in (3, 4) else 0.0, m_ver=3.0, ax_fy="FY26" if i % 10 else "FY25",
                 ax_miss={}, ax_roe=5 + 0.4 * i + (i % 3), ax_de=0.3 + 0.02 * i, ax_np=50.0 + i if i != 7 else -40.0, ax_revenue=500.0 + 10 * i,
                 ax_ebitda=80.0 + i, ax_c_equity=400.0 + 5 * i, ax_current_ratio=1 + (i % 7) * 0.1, ax_gc_g_rev=500.0 + 10 * i, ax_gp_g_rev=450.0 + 10 * i,
                 ax_g_rev=((500.0 + 10 * i) / (450.0 + 10 * i) - 1) * 100)
        if i == 9:
            m["ax_miss"] = {"roe": "no_fy"}
            del m["ax_roe"]
        rows.append(_row(f"C{i:02d}", "IT" if i % 2 else "Energy", **m))
    rows.append(_row("OLD", "IT", market_cap=900.0, pb=2.0, m_ver=2.0))                       # report stored, figures not rebuilt yet
    rows.append(_row("LIGHT", "IT", full=False, market_cap=800.0))                            # listing row only
    members = {"NIFTY50": [f"C{i:02d}" for i in range(10)], "NIFTYIT": [f"C{i:02d}" for i in range(1, 40, 2)], "NIFTYBANK": ["C03", "C04", "LIGHT"]}
    return Table(rows, members, {})


def run(t, **body):
    core = T.compute(t, body)
    return core, T.public(core, T.highlights(t, core, body.get("highlight", [])))


def test_exclusion_invariant_and_order():
    T.reset()
    t = fake_table()
    for body in ({"pair": "1.9"}, {"pair": "4.1"}, {"pair": "1.9", "trim": True}, {"pair": "1.9", "universe": {"sameFy": True}},
                 {"x": "pb", "y": "roe", "scale": {"x": "log", "y": "lin"}}, {"pair": "1.9", "universe": {"sector": ["IT"]}},
                 {"pair": "1.9", "universe": {"index": ["NIFTY50"], "mcapMin": 1100}}):
        _, out = run(t, **body)
        assert out["universeTotal"] == out["n"] + sum(e["count"] for e in out["excluded"]), body
        stages = [e["stage"] for e in out["excluded"]]
        assert stages == sorted(stages, key=T.STAGES.index)
        assert out["stats"] is None or out["stats"]["n"] == out["n"]
    _, out = run(t, pair="1.9")
    codes = {(e["stage"], e["code"]): e["count"] for e in out["excluded"]}
    assert codes[("no_report", "no_report")] == 1 and codes[("preparing", "preparing")] == 1 and codes[("y", "no_fy")] == 1
    assert out["lenders"]["mode"] == "included" and out["n"] == 39


def test_stats_carry_the_scale_they_were_computed_on():
    """The page words the slope differently on a log scale; it reads `stats.space`, so the server must always send it (a verifier found it missing)."""
    T.reset()
    t = fake_table()
    _, lin = run(t, pair="1.9")
    assert lin["stats"]["space"] == {"x": "lin", "y": "lin"}
    _, lg = run(t, x="pb", y="roe", scale={"x": "log", "y": "lin"})
    assert lg["stats"]["space"] == {"x": "log", "y": "lin"}


def test_price_charts_say_how_splits_are_handled():
    T.reset()
    t = fake_table()
    _, out = run(t, pair="1.9")
    assert not any("stored daily closes" in n for n in out["notes"])
    _, px = run(t, x="roe", y="ret_fy")
    note = " ".join(px["notes"])
    assert "stored daily closes" in note and "+80%" in note and "-44.4%" in note


def test_lenders_never_in_lender_sensitive_charts():
    t = fake_table()
    _, out = run(t, pair="4.1", universe={"lenders": "include"})
    assert out["lenders"] == {"mode": "excluded", "forced": True, "count": 2}
    assert not {"C03", "C04"} & {p["s"] for p in out["points"]}
    _, only = run(t, x="pb", y="roe", universe={"lenders": "only"})
    assert {p["s"] for p in only["points"]} == {"C03", "C04"}


def test_same_fy_and_trim():
    t = fake_table()
    _, out = run(t, pair="1.9", universe={"sameFy": True})
    assert all(p["fy"] == "FY26" for p in out["points"]) and out["fyBreakdown"] == [{"fy": "FY26", "n": out["n"]}]
    _, tr = run(t, pair="1.9", trim=True)
    assert any(e["code"] == "trimmed" for e in tr["excluded"]) and tr["n"] < 39


def test_highlights():
    t = fake_table()
    _, out = run(t, pair="1.9", universe={"sector": ["Energy"]}, highlight=["C01", "C02", "C09", "LIGHT", "NOPE"])
    st = {h["s"]: h["status"] for h in out["highlights"]}
    assert st == {"C01": "outside", "C02": "included", "C09": "outside", "LIGHT": "no_report", "NOPE": "unknown"}
    _, out = run(t, pair="1.9", highlight=["C09"])
    assert out["highlights"][0]["status"] == "excluded" and out["highlights"][0]["reason"] == "no_fy"


def test_points_reproduce_the_statistics():
    from finlit.advanced import stats as S
    t = fake_table()
    _, out = run(t, pair="1.9")
    st = S.analyse([(p["x"], p["y"], p["s"]) for p in out["points"]])
    assert out["stats"]["pearson"]["r"] == pytest.approx(st["pearson"]["r"], rel=1e-5)
    assert out["stats"]["ols"]["slope"] == pytest.approx(st["ols"]["slope"], rel=1e-5)


# ------------------------------------------------------------ index points
def ipoint(t, code, x, y, mode="include", scale=None):
    return I.point(t, code, code, METRICS[x], METRICS[y], mode, scale or {"x": "lin", "y": "lin"}, T.value_of, T.fy_of)


def test_index_ratio_of_sums_and_median_by_hand():
    t = fake_table()
    p = ipoint(t, "NIFTY50", "pe", "current_ratio")
    mem = range(10)
    mcap = sum(1000.0 + 100 * i for i in mem)
    np_ = sum(50.0 + i if i != 7 else -40.0 for i in mem)        # loss-maker C07 included, as NSE does
    assert p["method"] == {"x": "ratio_of_sums", "y": "median"}
    assert p["x"] == pytest.approx(mcap / np_, rel=1e-9) and p["lossMembers"] == 1
    cr = sorted(1 + (i % 7) * 0.1 for i in mem)
    assert p["y"] == pytest.approx((cr[4] + cr[5]) / 2, rel=1e-9)
    assert p["membersUsed"] == 10 and p["mcapCoveragePct"] == 100.0 and p["inStats"] is False
    g = ipoint(t, "NIFTY50", "g_rev", "pb")
    assert g["x"] == pytest.approx((sum(500.0 + 10 * i for i in mem) / sum(450.0 + 10 * i for i in mem) - 1) * 100, rel=1e-9)
    assert g["y"] == pytest.approx(sum(1000.0 + 100 * i for i in mem) / sum(400.0 + 5 * i for i in mem), rel=1e-9)   # P/B = sum mcap / sum equity
    r = ipoint(t, "NIFTY50", "pb", "roe")
    used = [i for i in mem if i != 9 or True]
    assert r["y"] == pytest.approx(sum(50.0 + i if i != 7 else -40.0 for i in used) / sum(400.0 + 5 * i for i in used) * 100, rel=1e-9)


def test_index_coverage_threshold_and_lenders():
    t = fake_table()
    p = ipoint(t, "NIFTYBANK", "pb", "roe", mode="include")
    # members C03, C04 (lenders with reports) and LIGHT (listing row only): coverage by market cap below 80%? 1300+1400 of 3500 = 77%
    assert p["x"] is None and p["reason"] == "low_coverage" and "77%" in p["reasonText"] and p["mcapCoveragePct"] == pytest.approx(77.1, abs=0.05)
    q = ipoint(t, "NIFTY50", "pe", "roe", mode="exclude")
    assert q["membersEligible"] == 8 and q["lenders"] == "excluded" and q["x"] is not None


def test_index_never_in_statistics_and_whitelist():
    t = fake_table()
    core, out = run(t, pair="1.9")
    n0 = out["n"]
    pts = [ipoint(t, c, "pb", "roe") for c in ("NIFTY50", "NIFTYIT")]
    assert out["n"] == n0 and all(p["inStats"] is False for p in pts)
    assert CrossIn(pair="1.9", indices=["nifty50", "NIFTY50", "NIFTYIT"]).indices == ["NIFTY50", "NIFTYIT"]
    with pytest.raises(ValidationError):
        CrossIn(pair="1.9", indices=["NIF50X"])
    with pytest.raises(ValidationError):
        CrossIn(pair="1.9", indices=["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500"])


def test_benchmark_years():
    from datetime import date
    lv = [(date(2025, 3, 28), 100.0), (date(2026, 3, 31), 110.0)]
    out = benchmark_years(lv, ["FY25", "FY26"], ["2025-03-31", "2026-03-31"])
    assert out[0]["value"] is None and out[1]["value"] == pytest.approx(10.0)


def test_csv_guard():
    assert safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and safe_cell("+1") == "'+1" and safe_cell("@x") == "'@x" and safe_cell("ABB") == "ABB"
    assert safe_cell(-5.0) == -5.0


# ------------------------------------------------------------ HTTP (needs Postgres + Redis)
@pytest.mark.integration
async def test_routes_gating_and_limits(app, monkeypatch):  # noqa: F811
    import finlit.advanced.api as A
    t = fake_table()

    async def fake_get_table(_store, force=False):
        return t
    monkeypatch.setattr(A, "get_table", fake_get_table)
    T.reset()
    async with new_client(app) as anon:
        r = await anon.get("/api/advanced/catalog")
        assert r.status_code == 200 and r.headers["cache-control"].startswith("public") and r.json()["counts"]["pairs"] == 162
        r = await anon.post("/api/advanced/cross", json={"pair": "1.9"})
        assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_required" and r.json()["detail"]["plan"] == "silver"
        assert (await anon.get("/api/advanced/history", params={"symbols": "RELIANCE", "pair": "3.2"})).status_code == 403
        assert (await anon.get("/api/advanced/tech", params={"symbol": "RELIANCE", "kind": "rsi"})).status_code == 403
        assert (await anon.post("/api/advanced/export", json={"pair": "1.9"})).status_code == 403
    silver = await signed_in(app, "adv-s@example.com", plan="silver")
    r = await silver.post("/api/advanced/cross", json={"pair": "1.9", "highlight": ["C01", "C02"], "indices": ["NIFTY50"]})
    body = r.json()
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"] and body["n"] == 39 and body["indices"][0]["code"] == "NIFTY50"
    assert body["universeTotal"] == body["n"] + sum(e["count"] for e in body["excluded"])
    r = await silver.post("/api/advanced/cross", json={"pair": "1.9", "highlight": ["C01", "C02", "C03", "C05"]})
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_limit" and r.json()["detail"]["limit"] == 3
    assert (await silver.post("/api/advanced/cross", json={"pair": "8.1", "variant": "forward"})).status_code == 403   # forward = Gold
    assert (await silver.post("/api/advanced/cross", json={"pair": "9.13"})).status_code == 400                        # unavailable pair
    assert (await silver.post("/api/advanced/cross", json={"x": "nonsense", "y": "roe"})).status_code == 400
    assert (await silver.post("/api/advanced/cross", json={"pair": "1.9", "indices": ["XYZ"]})).status_code == 422
    r = await silver.get("/api/advanced/history", params={"symbols": "RELIANCE", "pair": "3.2"})
    assert r.status_code == 200 and r.json()["companies"][0]["n"] >= 6
    assert (await silver.get("/api/advanced/history", params={"symbols": "RELIANCE", "pair": "4.1"})).status_code == 403  # D/E history = Gold
    assert (await silver.get("/api/advanced/tech", params={"symbol": "RELIANCE", "kind": "rsi", "h": 20})).status_code == 403
    r = await silver.post("/api/advanced/export", json={"mode": "cross", "pair": "1.9"})
    assert r.status_code == 200 and r.text.startswith("﻿# chart,") and "symbol,name,sector,fy,x,y,included,reason,highlighted" in r.text
    gold = await signed_in(app, "adv-g@example.com", plan="gold")
    r = await gold.post("/api/advanced/cross", json={"pair": "8.1", "variant": "forward", "highlight": ["C01", "C02", "C03", "C05", "C06", "C08"]})
    assert r.status_code == 200
    r = await gold.get("/api/advanced/history", params={"symbols": "RELIANCE", "pair": "4.1"})
    assert r.status_code == 200 and r.json()["companies"][0]["status"] == "ok"
    r = await gold.get("/api/advanced/history", params={"symbols": "RELIANCE", "pair": "3.8", "index": "NIF50"})
    assert r.status_code == 200 and r.json()["benchmarks"][0]["code"] == "NIF50"
    r = await gold.get("/api/advanced/tech", params={"symbol": "RELIANCE", "kind": "rsi", "h": 20})
    tb = r.json()
    assert r.status_code == 200 and tb["n"] >= 15 and tb["pair"] == "8.5"
    r = await gold.get("/api/advanced/tech", params={"symbol": "RELIANCE", "kind": "beta"})
    assert r.status_code == 200 and r.json()["market"]["code"] == "NIF50"
    assert (await gold.get("/api/advanced/tech", params={"symbol": "RELIANCE", "kind": "beta", "market": "FAKE"})).status_code == 400
    r = await gold.post("/api/advanced/export", json={"mode": "tech", "symbol": "RELIANCE", "kind": "rsi", "h": 20})
    assert r.status_code == 200 and "date,x,y,included,reason" in r.text


@pytest.mark.integration
async def test_real_table_has_reliance_ax(app):  # noqa: F811
    from finlit.screener.data import get_table, reset
    reset()
    t = await get_table(app.state.store, force=True)
    i = t.pos["RELIANCE"]
    assert t.ax_ready[i] and t.ax_fy[i] == "FY26" and not math.isnan(t.ax["ax_g_rev"][i])


def test_cfo_divergence_rule():
    from finlit.advanced.api import cfo_divergence
    h = {"fys": ["FY25", "FY26"], "values": {"g_rev": [5.0, 3.0], "g_np": [4.0, 2.0], "g_cfo": [1.0, -8.0]}}
    out = cfo_divergence(h)
    assert [f["fy"] for f in out] == ["FY26"] and out[0]["cfoGrowth"] == -8.0


@pytest.mark.integration
async def test_flags_route(app):  # noqa: F811
    async with new_client(app) as anon:
        assert (await anon.get("/api/advanced/flags", params={"symbols": "RELIANCE"})).status_code == 403
    silver = await signed_in(app, "adv-f@example.com", plan="silver")
    r = await silver.get("/api/advanced/flags", params={"symbols": "RELIANCE,NOPE"})
    body = r.json()
    assert r.status_code == 200 and body["companies"][0]["status"] == "ok" and body["companies"][1]["status"] == "no_report"
    assert all(f["case"] == 1 for f in body["companies"][0]["threeX"])


@pytest.mark.integration
async def test_rebuild_only_missing_picks_up_old_versions(ingested):  # noqa: F811
    from finlit.screener.compute import METRICS_VERSION
    from finlit.screener.jobs import rebuild_metrics
    store = ingested
    assert await rebuild_metrics(store, only_missing=True) == 0                  # fresh ingest: already current
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET metrics = jsonb_set(metrics, '{m_ver}', '2.0') WHERE symbol = 'RELIANCE'")
    assert await rebuild_metrics(store, only_missing=True) == 1                  # bumping METRICS_VERSION now reaches old rows
    async with store.pool.acquire() as conn:
        m = json.loads(await conn.fetchval("SELECT metrics FROM scores WHERE symbol = 'RELIANCE'"))
    assert m["m_ver"] == METRICS_VERSION and m["ax_fy"] == "FY26"
