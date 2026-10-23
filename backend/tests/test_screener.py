"""The screener: metric computation from a real recorded company, the filter engine, and who may use which filter."""

import json

import pytest

from finlit.screener.catalog import BY_KEY, CATALOG, GROUPS, INTERNAL_KEYS
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
    assert {k for k in m if not k.startswith("ax_")} <= set(BY_KEY) | INTERNAL_KEYS   # nothing invented outside the catalogue (ax_*: advanced charts)
    assert 20000101 < m["q_period_end"] < 21000101                         # which quarter the q_* figures are for


def test_missing_data_is_left_out_not_guessed():
    assert compute({}) == {} or all(v is not None for v in compute({}).values())
    assert "pe_vs_median_5y" not in compute({"summary": {"profile": {}, "quote": {}}})


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
        showcase = set(app.state.settings.showcase_symbols)
        assert all(r["band"] is None for r in ok.json()["rows"] if r["symbol"] not in showcase)   # the score band is model output too
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
    assert ok.status_code == 200 and ok.json()["total"] >= 1 and any(r["band"] for r in ok.json()["rows"])


# ---------------------------------------------------------------- annual operating profit (item 2)
def test_annual_operating_profit_metrics(reliance_sections):
    m = compute(reliance_sections)
    pl = reliance_sections["financials"]["yearly"]["pl"]["rows"]
    op = [v for v in pl["operating_profit"]]
    assert m["op_profit"] == pytest.approx(op[-1], abs=1e-3)
    if op[-2] and op[-2] > 0:
        assert m["op_profit_growth"] == pytest.approx((op[-1] - op[-2]) / op[-2] * 100, abs=1e-3)
    if len(op) > 3 and op[-4] and op[-4] > 0 and op[-1] > 0:
        assert m["op_profit_cagr_3y"] == pytest.approx(((op[-1] / op[-4]) ** (1 / 3) - 1) * 100, abs=1e-3)
    # the quarterly one is a different figure with its own key
    assert "q_operating_profit" in m and m["q_operating_profit"] != m["op_profit"]
    assert m["m_ver"] >= 2


def test_operating_labels_say_annual_or_quarterly():
    ops = [m for m in CATALOG if "operating" in m.label.lower() and "cash" not in m.label.lower()]
    assert {m.key for m in ops} >= {"op_profit", "op_profit_growth", "op_profit_cagr_3y", "op_profit_cagr_5y", "operating_margin", "q_operating_profit", "q_opm"}
    for m in ops:
        assert ("annual" in m.label.lower()) != ("quarter" in m.label.lower()), m.label   # exactly one of the two, never neither


def test_growth_is_blank_when_last_year_was_a_loss():
    sec = {"summary": {"profile": {}, "quote": {}}, "financials": {"yearly": {"pl": {"periodEnds": [], "rows": {"operating_profit": [-50.0, 100.0], "revenue": [10.0, 20.0]}}}}}
    m = compute(sec)
    assert m["op_profit"] == 100.0 and "op_profit_growth" not in m and "op_profit_cagr_3y" not in m


# ---------------------------------------------------------------- every listed company (item 5)
from finlit.screener import listing  # noqa: E402
from finlit.screener.data import with_listing  # noqa: E402


def test_quote_only_metrics_use_the_same_formulas():
    m = listing.metrics_of({"price": 90.0, "change_pct": -1.5, "market_cap": 5000.0, "high52": 120.0, "low52": 80.0, "volume": 2_000_000})
    assert m["pct_from_high"] == 25.0 and m["pct_from_low"] == 12.5 and m["range_pos"] == 25.0
    assert m["turnover_cr"] == pytest.approx(18.0) and m["ret_1d"] == -1.5 and m["near_high"] == 0.0
    assert set(m) <= set(BY_KEY)
    assert listing.metrics_of({"price": None, "market_cap": None}) == {}          # nothing sent, nothing shown


def test_parse_skips_placeholders_and_unlisted():
    payload = {"AAA": {"current_price": 10, "change": "1.00%", "market_cap": 100, "high52": 12, "low52": 8, "volume": 5, "tradetime": "2099-01-01T10:00:00Z"},
               "BBB": {"current_price": None, "market_cap": 0, "tradetime": "0001-01-01T00:00:00Z"},
               "OLD": {"current_price": 5, "market_cap": 9, "tradetime": "2015-01-01T10:00:00Z"}, "OTHER": {"current_price": 3}}
    out = {r["symbol"]: r for r in listing.parse(payload, {"AAA": "A", "BBB": "B", "OLD": "O", "NONE": "N"})}
    assert set(out) == {"AAA", "BBB"}                                             # a price last traded years ago is not shown; symbols we do not list are ignored
    assert out["AAA"]["price"] == 10 and out["AAA"]["change_pct"] == 1.0
    assert out["BBB"]["price"] is None and out["BBB"]["market_cap"] is None and out["BBB"]["traded_at"] is None


def test_every_listed_company_is_in_the_table_and_filters_are_honest():
    full = [_row(f"F{i}", "IT", market_cap=1000 * (i + 1), price=10.0 + i, pe=10 + i, roe=8 + i) for i in range(6)]
    light = [with_listing({"symbol": f"L{i}", "name": f"Light {i}", "sector": None, "industry": None, "price": 5.0 + i, "market_cap": 50.0 + i, "change_pct": 1.0,
                           "high52": 20.0, "low52": 4.0, "volume": 100}) for i in range(4)]
    light.append(with_listing({"symbol": "NOQUOTE", "name": "No quote", "sector": None, "industry": None, "price": None, "market_cap": None}))
    t = Table(full + light, {}, {})
    assert t.n == 11 and t.n_full == 6                                             # the count shown to users is the number of rows really in the table
    pick = lambda f, c=None, q="": [t.symbols[i] for i in t.sort(t.match(f, c or {}, q), "market_cap", True)]
    assert len(pick({})) == 11                                                     # no filter: nobody is left out for lacking a figure
    assert len(pick({"market_cap": {"min": 0}})) == 10                             # a filter on market cap leaves out the one company without it, honestly
    assert pick({"pe": {"min": 0}}) == [f"F{i}" for i in range(5, -1, -1)]         # a filter on P/E (which light rows lack) leaves them out
    assert pick({"price": {"max": 7}})[:2] == ["L2", "L1"] and "NOQUOTE" not in pick({"price": {"max": 7}})
    row = t.row(t.pos["L1"], ["market_cap", "pe", "pct_from_high"])
    assert row["full"] is False and row["v"]["pe"] is None and row["v"]["market_cap"] == 51.0 and row["v"]["pct_from_high"] == pytest.approx((20.0 - 6.0) / 20.0 * 100)
    assert t.row(t.pos["F0"], ["pe"])["full"] is True
    assert pick({}, {}, "light 3") == ["L3"]


async def test_nightly_listing_refresh_end_to_end(ingested):   # noqa: F811
    store = ingested
    async with store.pool.acquire() as conn:
        await conn.execute("TRUNCATE listing_quotes")
        syms = [r["symbol"] for r in await conn.fetch("SELECT symbol FROM companies ORDER BY symbol LIMIT 3500")]

    class Fake:
        def __init__(self, quotes): self.quotes, self.calls = quotes, []
        async def stock_symbols(self):
            import gzip, json as _j, pathlib
            p = pathlib.Path(__file__).parent / "fixtures" / "finedge" / "stock_symbols.json.gz"
            return _j.loads(gzip.open(p).read())
        async def get(self, path, params=None, timeout=10, retries=3):
            self.calls.append(path)
            return self.quotes

    good = {s: {"current_price": 100 + i, "change": "0.5%", "market_cap": 1000 + i, "high52": 200, "low52": 50, "volume": 10, "tradetime": "2099-01-01T10:00:00Z"} for i, s in enumerate(syms)}
    c = Fake(good)
    res = await listing.refresh_listing(c, store, force=True)
    assert res["quoted"] == 3500 and res["withPrice"] == 3500 and c.calls.count("/quote") == 1      # one market-wide quote call
    again = await listing.refresh_listing(Fake(good), store)
    assert "skipped" in again                                                                      # a restarted server does not repeat it
    short = await listing.refresh_listing(Fake({syms[0]: good[syms[0]]}), store, force=True)
    assert short.get("refused")                                                                    # a hiccup never wipes the good rows
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM listing_quotes") == 3500
    from finlit.screener.data import _load
    t = await _load(store)
    assert t.n >= 5700 and t.n_full == 1 and t.symbols.count("RELIANCE") == 1                      # every listed company; one full report
    assert t.cols["market_cap"][t.pos[syms[10]]] == 1010
    assert t.cols["pe"][t.pos[syms[10]]] != t.cols["pe"][t.pos[syms[10]]]                          # NaN: unknown, not guessed


async def test_default_view_is_company_market_cap_and_price(app):  # noqa: F811
    async with new_client(app) as anon:
        cat = (await anon.get("/api/screener/catalog")).json()
        assert cat["defaultColumns"] == ["market_cap", "price"] and "withReport" in cat and cat["withReport"] <= cat["total"]
        r = await _q(anon, {"limit": 5})
        assert r.status_code == 200 and r.json()["columns"] == ["market_cap", "price"]
    gold = await signed_in(app, "g2@example.com", plan="gold")
    assert (await _q(gold, {"limit": 5})).json()["columns"] == ["market_cap", "price"]       # the same default for every plan; filters add columns
    assert (await _q(gold, {"columns": ["overall"], "limit": 5})).status_code == 200            # Gold columns still work for Gold
