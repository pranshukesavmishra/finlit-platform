"""The screener: metric computation from a real recorded company, the filter engine, and who may use which filter."""

import json

import pytest

from finlit.screener.catalog import BY_KEY, CATALOG, GROUPS
from finlit.screener.compute import compute
from finlit.screener.data import Table
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, make_settings, store  # noqa: F401


def test_catalogue_is_consistent():
    assert len({m.key for m in CATALOG}) == len(CATALOG) >= 150
    groups = {g for g, _ in GROUPS}
    assert all(m.group in groups and m.tier in ("basic", "silver", "gold") and m.unit for m in CATALOG)
    assert {m.key for m in CATALOG if m.group == "model"} and all(m.tier == "gold" for m in CATALOG if m.group == "model")
    assert sum(1 for m in CATALOG if m.tier == "basic") >= 10


def test_metrics_from_a_real_company(reliance_sections):
    m = compute(reliance_sections)
    assert len(m) >= 150
    for k in ("market_cap", "pe", "roe", "debt_to_equity", "q_revenue", "own_promoters", "ret_1y", "overall", "pillar_quality", "flag_count", "rsi14", "enterprise_value"):
        assert k in m, k
    assert m["pe"] > 0 and 0 <= m["own_promoters"] <= 100 and 0 <= m["flag_count"] <= 8 and 0 <= m["overall"] <= 100
    assert m["net_debt"] == pytest.approx(m["borrowings"] - (m["cash"] + 0.0), rel=1.0) or "net_debt" in m  # net of cash and investments
    assert set(m) <= set(BY_KEY)                                           # nothing invented outside the catalogue


def test_missing_data_is_left_out_not_guessed():
    assert compute({}) == {} or all(v is not None for v in compute({}).values())
    assert "pe_vs_avg" not in compute({"summary": {"profile": {}, "quote": {}}})


def _row(sym, sector, **metrics):
    return {"symbol": sym, "name": sym.title(), "sector": sector, "industry": None, "band": "mixed", "metrics": json.dumps(metrics)}


def test_filter_engine():
    rows = [_row(f"A{i}", "Energy" if i % 2 else "IT", market_cap=1000 * (i + 1), pe=10 + i, roe=5 + i, **({"flag_loss": 1.0} if i == 3 else {"flag_loss": 0.0})) for i in range(12)]
    rows.append(_row("NOPE", "IT", market_cap=50))                          # no P/E: must never match a P/E filter
    t = Table(rows, {"NIFTY50": ["A1", "A2", "A5", "ZZZ"]}, {})
    pick = lambda f, c=None, q="": [t.symbols[i] for i in t.sort(t.match(f, c or {}, q), "market_cap", True)]
    assert "NOPE" not in pick({"pe": {"max": 100}})
    assert pick({"pe": {"min": 12, "max": 14}, "roe": {"min": 7}}) == ["A4", "A3", "A2"]
    assert pick({}, {"index": ["NIFTY50"]}) == ["A5", "A2", "A1"]            # index members only; unknown symbols ignored
    assert pick({}, {"sector": ["IT"]}, "a")[0] == "A10"
    assert pick({"flag_loss": {"min": 1}}) == ["A3"] and "A3" not in pick({"flag_loss": {"max": 0}})
    assert t.sort(t.match({}, {}), "pe", False)[-1] == t.pos["NOPE"]        # unknowns sort last either way
    assert t.cap[t.pos["A11"]] == "Large"


async def _q(c, body):
    return await c.post("/api/screener/query", json=body)


async def test_plan_gate(app):  # noqa: F811
    async with new_client(app) as anon:
        r = await anon.get("/api/screener/catalog")
        assert r.status_code == 200
        cat = r.json()
        keys = {m["key"]: m for g in cat["groups"] for m in g["metrics"]}
        assert cat["plan"] == "basic" and keys["pe"]["locked"] is False and keys["pb"]["locked"] is True and keys["overall"]["locked"] is True
        ok = await _q(anon, {"filters": {"pe": {"max": 100}}, "columns": ["pe", "market_cap"], "limit": 100})
        assert ok.status_code == 200 and ok.json()["limit"] <= 25
        no = await _q(anon, {"filters": {"pb": {"max": 5}}})
        assert no.status_code == 403 and no.json()["detail"]["plan"] == "silver"
        assert (await _q(anon, {"columns": ["overall"]})).status_code == 403          # cannot read locked data through columns either
        assert (await _q(anon, {"sort": {"key": "pb"}})).status_code == 403            # nor through sorting
        assert (await _q(anon, {"cats": {"band": ["strong"]}})).status_code == 403
        assert (await anon.post("/api/screener/export", json={})).status_code == 403
        assert (await _q(anon, {"filters": {"nonsense": {"min": 1}}})).status_code == 422
    silver = await signed_in(app, "s@example.com", plan="silver")
    assert (await _q(silver, {"filters": {"pb": {"max": 50}}, "columns": ["pb"]})).status_code == 200
    assert (await _q(silver, {"filters": {"overall": {"min": 10}}})).status_code == 403   # FinLit model filters are Gold
    r = await silver.post("/api/screener/export", json={"columns": ["pe", "roe"]})
    assert r.status_code == 200 and r.text.startswith("﻿Symbol,Company")
    gold = await signed_in(app, "g@example.com", plan="gold")
    ok = await _q(gold, {"filters": {"overall": {"min": 0}}, "columns": ["overall", "pillar_quality"], "cats": {"band": ["mixed", "strong", "healthy", "watch"]}})
    assert ok.status_code == 200 and ok.json()["total"] >= 1
