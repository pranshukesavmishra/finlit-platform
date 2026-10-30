"""The light path of the quarter results page: companies not held in full get their quarter from ONE provider call (the quarterly P&L)."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finlit import results as R
from finlit import results_light as L
from finlit.finedge import FinEdgeClient
from finlit.screener.compute import compute, quarter_block
from test_integration import make_settings, store  # noqa: F401  (fixtures + helpers)

FIX = Path(__file__).parent / "fixtures" / "finedge" / "financials_reliance_period_quarterly_statement_code_pl.json"
ALL = json.loads(FIX.read_text())["financials"]          # recorded: newest first, the newest quarter ends 2026-06-30
E = date(2026, 6, 30)
QK = "2026-06"
DECL = date(2026, 7, 20)
TODAY = date(2026, 7, 21)


def upto(end: int, rows=ALL):
    """The provider's quarterly payload as it stood when its newest quarter ended on `end` (yyyymmdd)."""
    return {"symbol": "X", "financials": [r for r in rows if r["period_end"] <= end]}


# ---------------------------------------------------------------- the same numbers on both paths
def test_light_and_full_paths_give_identical_numbers(reliance_bundle, reliance_sections):
    full = compute(reliance_sections)                                    # what the full report stores as scores.metrics
    table = reliance_sections["financials"]["quarterly"]["pl"]
    got = L.quarter_figures(reliance_bundle["pl_quarterly"], E)
    assert got is not None
    for k in ("q_revenue", "q_net_profit", "q_operating_profit", "q_eps", "q_sales_yoy", "q_profit_yoy", "q_sales_qoq", "q_profit_qoq", "q_opm", "q_npm", "q_period_end"):
        assert got["m"][k] == full[k], k                                  # exactly equal, not approximately
    assert got["m"] == {k: v for k, v in ((k, full.get(k)) for k in quarter_block(table, E))}
    ends, ops = table["periodEnds"], table["rows"]["operating_profit"]
    assert got["opg"] == R.op_growth(ends, ops, E, full["q_operating_profit"])
    # an older quarter in the same table is found the same way
    older = L.quarter_figures(reliance_bundle["pl_quarterly"], date(2026, 3, 31))
    assert older["m"]["q_revenue"] == round(quarter_block(table, date(2026, 3, 31))["q_revenue"], 4) and older["opg"] == R.op_growth(ends, ops, date(2026, 3, 31), older["m"]["q_operating_profit"])


def test_a_row_built_from_either_source_is_identical(reliance_bundle, reliance_sections):
    full = compute(reliance_sections)
    table = reliance_sections["financials"]["quarterly"]["pl"]
    got = L.quarter_figures(reliance_bundle["pl_quarterly"], E)
    decl = R.Decl(DECL, True, "Reliance")
    a = R.build_row("RELIANCE", decl, {"name": "Reliance"}, {k: full[k] for k in R.METRIC_KEYS}, E, TODAY, None, [], R.op_growth(table["periodEnds"], table["rows"]["operating_profit"], E, full["q_operating_profit"]))
    b = R.build_row("RELIANCE", decl, {"name": "Reliance"}, got["m"], E, TODAY, None, [], got["opg"], {"used": True, "basis": "consolidated"})
    assert (a.pop("source"), b.pop("source"), b.pop("basis")) == ("full", "light", "consolidated") and a.pop("basis") is None
    assert a == b and a["status"] == "declared" and a["revenue"] is not None


def test_quarter_not_in_the_payload_gives_no_figures():
    assert L.quarter_figures(upto(20260331), E) is None and L.quarter_figures(None, E) is None and L.quarter_figures({"financials": []}, E) is None


# ---------------------------------------------------------------- fake provider + database
def provider(books: dict, calls: list):
    """books: {symbol: {"c": payload | status code, "s": payload | status code}}"""
    def handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.path.rsplit("/", 1)[-1]
        kind = request.url.params.get("statement_type")
        calls.append((sym, kind))
        assert request.url.params.get("statement_code") == "pl" and request.url.params.get("period") == "quarterly"
        got = books.get(sym, {}).get(kind, 404)
        return httpx.Response(got, json={"message": "x"}) if isinstance(got, int) else httpx.Response(200, json=got)
    return FinEdgeClient(make_settings(), transport=httpx.MockTransport(handler))


STALE_C = upto(20250331, [r for r in ALL if r["period_end"] <= 20250331])      # consolidated stopped at Mar 2025 (the SBFC pattern)


@pytest.fixture
async def seeded(store, monkeypatch):  # noqa: F811
    syms = {"AAA": 9000.0, "BBB": 7000.0, "CCC": 5000.0, "DDD": 3000.0, "EEE": 100.0, "FULL": 99999.0}
    decls = {QK: {s: R.Decl(DECL, True, s.title()) for s in syms}}

    async def fake(store_, force=False):
        return decls
    monkeypatch.setattr(R, "get_declarations", fake)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol = ANY($1::text[])", list(syms))
        await conn.execute("DELETE FROM scores WHERE symbol = ANY($1::text[])", list(syms))
        for s, mc in syms.items():
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2)", s, mc)
        # FULL: the stored full report already holds the quarter (so the light path must not touch it)
        await conn.execute("INSERT INTO scores (symbol, statement, model, name, market_cap, metrics) VALUES ('FULL', 'consolidated', 'v1', 'Full', 99999, $1::jsonb)",
                           json.dumps({"q_revenue": 1.0, "q_net_profit": 1.0, "q_period_end": 20260630.0}))
    R.reset()
    yield syms
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM quarter_light")
        await conn.execute("DELETE FROM listing_quotes WHERE symbol = ANY($1::text[])", list(syms))
        await conn.execute("DELETE FROM scores WHERE symbol = ANY($1::text[])", list(syms))
    R.reset()


async def rows_of(store, decls=None):
    decls = decls or (await R.get_declarations(store))[QK]
    return {r["symbol"]: r for r in (await R._build(store, E, decls, TODAY)).rows}


@pytest.mark.integration
async def test_new_quarter_is_declared_with_figures_and_provider_gap_stays_awaiting_with_its_reason(store, seeded):  # noqa: F811
    calls: list = []
    behind = upto(20260331)        # the provider's newest quarter is March: June is not published yet
    books = {"AAA": {"c": upto(20260630)}, "BBB": {"c": behind}, "CCC": {"c": STALE_C, "s": upto(20260630)}, "DDD": {"c": 400}, "EEE": {"c": upto(20260630)}}
    async with provider(books, calls) as client:
        out = await L.refresh_light(client, store, today=TODAY, pause=0)
    assert out == {"candidates": 5, "tried": 5, "filled": 3, "providerPending": 1, "failed": 1, "errors": out["errors"]}
    assert next(iter(out["errors"])).startswith("FinEdgeError HTTP 400")             # the log and the status page say which HTTP status the provider sent
    assert ("FULL", "c") not in calls                                         # held in full: not asked
    assert [c[0] for c in calls if c[1] == "c"] == ["AAA", "BBB", "CCC", "DDD", "EEE"]   # biggest market cap first, one consolidated call each
    rows = await rows_of(store)
    a = rows["AAA"]
    assert a["status"] == "declared" and a["source"] == "light" and a["basis"] == "consolidated" and a["awaitingWhy"] is None
    want = L.quarter_figures(upto(20260630), E)
    assert a["revenue"] == pytest.approx(round(want["m"]["q_revenue"], 2)) and a["netProfit"] == pytest.approx(round(want["m"]["q_net_profit"], 2))
    assert a["revenueYoY"] == pytest.approx(round(want["m"]["q_sales_yoy"], 1)) and a["profitQoQ"] == pytest.approx(round(want["m"]["q_profit_qoq"], 1))
    assert a["operatingProfit"] is not None and a["eps"] is not None and a["loadedPeriodEnd"] == "2026-06-30"
    assert a["opYoY"] == pytest.approx(round(want["opg"]["opYoY"], 1))
    b = rows["BBB"]
    assert b["status"] == "awaiting" and b["awaitingWhy"] == "provider" and b["revenue"] is None and b["source"] is None
    c = rows["CCC"]
    assert c["status"] == "declared" and c["basis"] == "standalone" and ("CCC", "s") in calls            # stale consolidated -> standalone, never mixed
    assert ("BBB", "s") not in calls and ("AAA", "s") not in calls                                                                     # one call when consolidated holds the quarter
    d = rows["DDD"]
    assert d["status"] == "awaiting" and d["awaitingWhy"] == "ours" and rows["EEE"]["status"] == "declared"    # a failure writes nothing: not blamed on the provider
    assert rows["FULL"]["source"] == "full" and rows["FULL"]["revenue"] == 1.0
    s = R.summarize(list(rows.values()), TODAY)
    assert (s["awaiting"], s["awaitingProvider"], s["awaitingOurs"], s["withNumbers"]) == (2, 1, 1, 4)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM snapshots WHERE symbol = ANY($1::text[])", list(seeded)) == 0   # no full snapshot, no score
        assert await conn.fetchval("SELECT count(*) FROM scores WHERE symbol = ANY($1::text[]) AND symbol <> 'FULL'", list(seeded)) == 0


@pytest.mark.integration
async def test_second_run_skips_filled_and_fresh_and_asks_the_provider_again_later(store, seeded):  # noqa: F811
    calls: list = []
    books = {"AAA": {"c": upto(20260630)}, "BBB": {"c": upto(20260331)}, "CCC": {"c": upto(20260630)}, "DDD": {"c": upto(20260630)}, "EEE": {"c": upto(20260630)}}
    async with provider(books, calls) as client:
        await L.refresh_light(client, store, today=TODAY, pause=0)
        calls.clear()
        again = await L.refresh_light(client, store, today=TODAY, pause=0)
        assert again["candidates"] == 0 and calls == []                       # filled ones are done, BBB was asked minutes ago
        async with store.pool.acquire() as conn:
            await conn.execute("UPDATE quarter_light SET checked_at = now() - interval '2 hours' WHERE symbol = 'BBB'")
        books["BBB"]["c"] = upto(20260630)                                    # the provider publishes it at last
        later = await L.refresh_light(client, store, today=TODAY, pause=0)
    assert later == {"candidates": 1, "tried": 1, "filled": 1, "providerPending": 0, "failed": 0} and calls == [("BBB", "c")]
    assert (await rows_of(store))["BBB"]["status"] == "declared"


@pytest.mark.integration
async def test_caps_and_order(store, seeded):  # noqa: F811
    calls: list = []
    books = {s: {"c": upto(20260630)} for s in seeded}
    async with provider(books, calls) as client:
        out = await L.refresh_light(client, store, limit=2, today=TODAY, pause=0)
        assert out["candidates"] == 5 and out["tried"] == 2 and [c[0] for c in calls] == ["AAA", "BBB"]
        out = await L.refresh_light(client, store, limit=2, today=TODAY, pause=0)
        assert [c[0] for c in calls] == ["AAA", "BBB", "CCC", "DDD"] and out["candidates"] == 3
    assert await L.candidates(store, TODAY + timedelta(days=10)) == []          # a declaration is chased for 4 days only


@pytest.mark.integration
async def test_keeps_only_the_latest_three_quarters_and_never_overwrites_figures_with_a_miss(store, seeded):  # noqa: F811
    calls: list = []
    async with provider({"AAA": {"c": upto(20260630)}}, calls) as client:
        got = await L.fetch_quarter(client, "AAA", E)
    async with store.pool.acquire() as conn:
        for qk in ("2025-09", "2025-12", "2026-03", "2026-06"):
            await L.save(conn, "AAA", qk, got)
        assert [r["quarter"] for r in await conn.fetch("SELECT quarter FROM quarter_light WHERE symbol = 'AAA' ORDER BY quarter")] == ["2025-12", "2026-03", "2026-06"]
        await L.save(conn, "AAA", "2026-06", {"basis": "consolidated", "figures": None, "providerLatest": date(2026, 3, 31)})
        assert await conn.fetchval("SELECT filled FROM quarter_light WHERE symbol = 'AAA' AND quarter = '2026-06'") is True


@pytest.mark.integration
async def test_data_health_counts(store, seeded):  # noqa: F811
    calls: list = []
    books = {"AAA": {"c": upto(20260630)}, "BBB": {"c": upto(20260331)}, "CCC": {"c": upto(20260630)}}
    async with provider(books, calls) as client:
        async with store.pool.acquire() as conn:
            for sym in ("AAA", "BBB", "CCC"):
                await L.save(conn, sym, QK, await L.fetch_quarter(client, sym, E))
    c = await L.coverage(store, TODAY)
    assert c == {"days": 3, "declared": 6, "filled": 3, "fromFullReport": 1, "fromLightRow": 2, "awaitingProvider": 1, "awaitingOurs": 2}
