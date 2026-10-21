"""The quarter-results page: which quarter a declaration belongs to, never showing last quarter's figures as this quarter's, plan gate."""

from datetime import date, timedelta

import pytest

from finlit import results as R
from finlit.screener.compute import compute, quarter_block
from test_auth import app, new_client, signed_in  # noqa: F401  (fixtures + helpers)
from test_integration import ingested, make_settings, store  # noqa: F401

D = date


# ---------------------------------------------------------------- quarters
def test_quarter_of_a_date_and_labels():
    assert R.quarter_end_before(D(2026, 10, 1)) == D(2026, 9, 30) and R.quarter_end_before(D(2026, 9, 30)) == D(2026, 6, 30)
    assert R.quarter_end_before(D(2027, 1, 3)) == D(2026, 12, 31) and R.quarter_end_before(D(2026, 5, 20)) == D(2026, 3, 31)
    assert R.next_quarter_end(D(2026, 12, 31)) == D(2027, 3, 31) and R.next_quarter_end(D(2026, 9, 30)) == D(2026, 12, 31)
    assert R.parse_quarter("2026-09") == D(2026, 9, 30) and R.parse_quarter("2026-10") is None and R.parse_quarter("x") is None
    q = R.quarter_info(D(2026, 9, 30))
    assert q["key"] == "2026-09" and q["fiscal"] == "Q2 FY27" and q["label"] == "Jul to Sep 2026" and q["from"] == "2026-10-01" and q["to"] == "2026-12-31"
    assert R.quarter_info(D(2027, 3, 31))["fiscal"] == "Q4 FY27" and R.quarter_info(D(2026, 6, 30))["fiscal"] == "Q1 FY27" and R.quarter_info(D(2026, 12, 31))["fiscal"] == "Q3 FY27"


def test_period_named_in_a_filing_title():
    p = R.period_in_title
    assert p("X Limited has submitted to the Exchange, the financial results for the period ended Jun 30, 2026.") == D(2026, 6, 30)
    assert p("results for the quarter and half year ended September 30, 2026") == D(2026, 9, 30)
    assert p("Audited Results for the quarter and year ended 31st March, 2026") == D(2026, 3, 31)
    assert p("unaudited results for the quarter ended 30/06/2026") == D(2026, 6, 30)
    assert p("Outcome of Board Meeting held on 9th October 2026 for approval of results") is None
    assert p("results for the period ended October 9, 2026") is None      # not a quarter-end: ignored, not guessed


def _feed(sym, when, source, category="", title="", company=None):
    return {"symbol": sym, "item_date": when, "source": source, "category": category, "title": title, "company": company}


def test_declarations_join_schedule_and_filings():
    filing = lambda sym, when, title="the financial results for the period ended Sep 30, 2026.": _feed(sym, when, R.FILING_SOURCE, "Outcome of Board Meeting", f"{sym} has submitted to the Exchange, {title}")
    rows = [
        _feed("AAA", D(2026, 10, 25), R.SOURCE_RESULTS), filing("AAA", D(2026, 10, 14)),                                                    # filed earlier than the schedule: the filing is the truth
        _feed("BBB", D(2026, 10, 30), R.SOURCE_RESULTS), _feed("BBB", D(2026, 10, 12), R.FILING_SOURCE, "Board Meeting", "Intimation of board meeting for results"),   # a notice is not a declaration
        _feed("CCC", D(2026, 10, 5), R.FILING_SOURCE, "Reply to Clarification- Financial results", "reply on financial results"),         # nor is a reply to a query
        filing("DDD", D(2026, 10, 3), "the financial results for the period ended Jun 30, 2026."),                                         # a laggard's June results, filed in October: June quarter
        _feed("EEE", D(2026, 12, 20), R.SOURCE_RESULTS), _feed("", D(2026, 10, 1), R.SOURCE_RESULTS),
    ]
    out = R.assign(rows)
    assert out["2026-09"]["AAA"].date == D(2026, 10, 14) and out["2026-09"]["AAA"].confirmed
    assert out["2026-09"]["BBB"].date == D(2026, 10, 30) and not out["2026-09"]["BBB"].confirmed
    assert "CCC" not in out["2026-09"] and out["2026-06"]["DDD"].date == D(2026, 10, 3) and "DDD" not in out["2026-09"]
    assert out["2026-09"]["EEE"].date == D(2026, 12, 20) and set(out) == {"2026-09", "2026-06"}
    qs = R.list_quarters(out, D(2026, 10, 20))
    assert [q["key"] for q in qs] == ["2026-09", "2026-06"] and (qs[0]["declared"], qs[0]["due"]) == (1, 2)
    assert R.default_quarter(qs, D(2026, 10, 20)) == "2026-09"
    assert R.default_quarter(R.list_quarters({"2026-12": {"X": R.Decl(D(2027, 1, 5), False)}, "2026-09": {"Y": R.Decl(D(2026, 10, 5), True)}}, D(2026, 10, 20)), D(2026, 10, 20)) == "2026-09"   # not a quarter with nothing out yet


# ---------------------------------------------------------------- figures
QPL = {"periodEnds": ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"],
       "rows": {"revenue": [100.0, 110.0, 120.0, 130.0, 150.0, 165.0], "net_profit": [10.0, 11.0, 12.0, 13.0, 15.0, 22.0], "operating_profit": [20.0, 22.0, 24.0, 26.0, 30.0, 33.0], "eps": [1.0, 1.1, 1.2, 1.3, 1.5, 2.2]}}


def test_quarter_block_says_which_quarter_it_is():
    now = quarter_block(QPL)
    assert now["q_period_end"] == 20260930 and now["q_revenue"] == 165 and now["q_sales_yoy"] == pytest.approx(50.0) and now["q_profit_yoy"] == pytest.approx(100.0)
    assert now["q_sales_qoq"] == pytest.approx(10.0) and now["q_opm"] == pytest.approx(20.0) and now["q_npm"] == pytest.approx(13.3333, rel=1e-3)
    prev = quarter_block(QPL, D(2026, 6, 30))
    assert prev["q_period_end"] == 20260630 and prev["q_revenue"] == 150 and prev["q_sales_yoy"] == pytest.approx(50.0) and prev["q_profit_qoq"] == pytest.approx(15.3846, rel=1e-3)
    assert quarter_block(QPL, D(2026, 8, 15)) == {} and quarter_block(QPL, D(2030, 3, 31)) == {} and quarter_block({}, D(2026, 9, 30)) == {}
    assert quarter_block({})["q_revenue"] is None and quarter_block({})["q_period_end"] is None


def test_compute_keeps_the_quarter_figures_and_adds_the_date(reliance_sections):
    m = compute(reliance_sections)
    q = reliance_sections["financials"]["quarterly"]["pl"]
    assert {k: m.get(k) for k in ("q_revenue", "q_net_profit", "q_sales_yoy")} == pytest.approx({k: round(v, 4) for k, v in quarter_block(q).items() if k in ("q_revenue", "q_net_profit", "q_sales_yoy")}, rel=1e-3)
    assert str(int(m["q_period_end"])) == q["periodEnds"][-1].replace("-", "")


E = D(2026, 9, 30)
TODAY = D(2026, 10, 20)


def _row(sym="AAA", when=D(2026, 10, 14), m=None, base=None, today=TODAY, mcap=1000.0):
    b = {"name": sym.title(), "sector": "IT", "market_cap": mcap, **(base or {})}
    return R.build_row(sym, R.Decl(when, True), b, m or {}, E, today, "Large", ["NIFTY50"])


FIG = {"q_revenue": 165.0, "q_net_profit": 22.0, "q_operating_profit": 33.0, "q_eps": 2.2, "q_sales_yoy": 50.0, "q_profit_yoy": 100.0, "q_sales_qoq": 10.0, "q_profit_qoq": 46.7, "q_opm": 20.0, "q_npm": 13.33}


def test_row_status_never_passes_old_numbers_off_as_new():
    ok = _row(m=FIG)
    assert ok["status"] == "declared" and ok["revenue"] == 165 and ok["gap"] == 50 and ok["flagged"] and not ok["awaiting"] and ok["hasNumbers"]
    assert ok["npmChange"] == pytest.approx(13.33 - 13.33 * 1.5 / 2.0, abs=0.06)         # last year's margin = 22/2 over 165/1.5 = 10%
    old = _row(m={}, base={"q_period_end": 20260630.0})                                      # date passed, but our figures are June's
    assert old["status"] == "awaiting" and old["awaiting"] and old["revenue"] is None and old["netProfit"] is None and not old["flagged"] and old["loadedPeriodEnd"] == "2026-06-30"
    assert _row(m={}, when=D(2026, 11, 5))["status"] == "due" and not _row(m={}, when=D(2026, 11, 5))["awaiting"]
    assert _row(m={}, base={"q_period_end": 20261231.0})["status"] == "missing"             # data has moved on and this quarter was not kept
    assert _row(m={})["status"] == "awaiting"                                                # a row with no stored quarter at all: awaiting, not guessed
    assert _row(m={**FIG, "q_profit_yoy": None})["gap"] is None and not _row(m={**FIG, "q_profit_yoy": None})["flagged"]
    assert _row(m={**FIG, "q_profit_yoy": 40.0})["flagged"] is False and _row(m={**FIG, "q_profit_yoy": 35.0})["flagged"] is True   # 15 points apart is the line
    assert _row(m={**FIG, "q_net_profit": -5.0})["loss"]


def test_sorting_filtering_and_summary():
    rows = [_row("A", D(2026, 10, 14), FIG, mcap=100), _row("B", D(2026, 10, 14), {**FIG, "q_profit_yoy": -10.0}, mcap=500), _row("C", D(2026, 10, 17), {}, mcap=50),
            _row("D", D(2026, 10, 10), {**FIG, "q_sales_yoy": 5.0}, mcap=None), _row("E", D(2026, 11, 3), {}, mcap=900)]
    sym = lambda rs: [r["symbol"] for r in rs]   # noqa: E731
    assert sym(R.select(rows, today="2026-10-20")) == ["C", "B", "A", "D", "E"]               # declared: newest date first, biggest company first within a day; dates to come last
    assert sym(R.select(rows, desc=False, today="2026-10-20")) == ["D", "B", "A", "C", "E"]
    assert sym(R.select(rows)) == ["E", "C", "B", "A", "D"]                                  # (without a "today" every date counts as declared)
    assert sym(R.select(rows, sort="profitYoY"))[:3] == ["A", "D", "B"] and sym(R.select(rows, sort="profitYoY", desc=False))[:3] == ["B", "D", "A"]
    assert sym(R.select(rows, sort="profitYoY"))[3:] == ["E", "C"]                           # no figures: always last
    assert sym(R.select(rows, flagged=True)) == ["B", "A", "D"] and sym(R.select(rows, q="c")) == ["C"] and sym(R.select(rows, index="NIFTY100")) == [] and sym(R.select(rows, symbols={"A", "E"})) == ["E", "A"]
    s = R.summarize(rows, TODAY)
    assert (s["companies"], s["declared"], s["due"], s["awaiting"], s["withNumbers"]) == (5, 4, 1, 1, 3)
    assert s["medianRevenueYoY"] == 50.0 and s["medianProfitYoY"] == 100.0 and s["profitUpShare"] == pytest.approx(66.7) and s["flagged"] == 3
    assert R.summarize([], TODAY)["medianProfitYoY"] is None
    locked = R.strip_figures(rows[0])
    assert locked["revenue"] is None and locked["netProfit"] is None and locked["gap"] is None and not locked["flagged"] and locked["locked"] and locked["date"] == "2026-10-14" and locked["name"]


# ---------------------------------------------------------------- the endpoint, against Postgres

@pytest.fixture
async def seeded(app):  # noqa: F811
    """RELIANCE (full report), one scored company whose stored figures are a quarter behind, one scored company from before q_period_end existed, one unscored."""
    R.reset()
    store = app.state.store
    async with store.pool.acquire() as conn:
        srow = await conn.fetchrow("SELECT statement, metrics FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1'")
        import json
        m = json.loads(srow["metrics"]) if isinstance(srow["metrics"], str) else dict(srow["metrics"])
        qend = R.ymd_to_date(m["q_period_end"])
        assert qend is not None
        # a second company that is "a quarter behind": same figures, but stamped with the quarter before
        behind = dict(m, q_period_end=float((qend - timedelta(days=95)).year * 10000 + (qend - timedelta(days=95)).month * 100 + 30))
        legacy = {k: v for k, v in m.items() if k != "q_period_end"}
        await conn.execute("DELETE FROM scores WHERE symbol IN ('LATEX', 'OLDX')")
        for sym, mm in (("LATEX", behind), ("OLDX", legacy)):
            await conn.execute("INSERT INTO scores (symbol, statement, model, name, market_cap, metrics) VALUES ($1, $2, 'v1', $3, $4, $5::jsonb)", sym, srow["statement"], sym.title(), 5000.0, json.dumps(mm))
            await conn.execute("DELETE FROM snapshots WHERE symbol = $1", sym)
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) SELECT $1, statement, section, body, etag, generated_at FROM snapshots "
                               "WHERE symbol = 'RELIANCE' AND statement = $2 AND section = 'financials'", sym, srow["statement"])
        await conn.execute("DELETE FROM feed_items WHERE source = 'results-test'")
        when = qend + timedelta(days=20)
        for i, (sym, d) in enumerate((("RELIANCE", when), ("LATEX", when), ("OLDX", when - timedelta(days=3)), ("NOSCORE", when - timedelta(days=5)), ("LATER", date.today() + timedelta(days=400)))):
            await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, source, item_date, auto, dedupe) VALUES ('result', $1, $2, $3, 'results-test', $4, true, $5)",
                               f"{sym}: board meeting for results", sym, sym.title(), d, f"results-test-{sym}")
    yield {"quarter": R.quarter_key(qend), "qend": qend, "when": when, "meta": m}
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE source = 'results-test'")
        await conn.execute("DELETE FROM scores WHERE symbol IN ('LATEX', 'OLDX')")
        await conn.execute("DELETE FROM snapshots WHERE symbol IN ('LATEX', 'OLDX')")
    R.reset()


@pytest.mark.integration
async def test_endpoint_awaiting_and_plan_gate(app, seeded):  # noqa: F811
    q = seeded["quarter"]
    async with new_client(app) as anon:
        r = await anon.get(f"/api/results/quarter?quarter={q}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["locked"] and body["plan"] == "basic" and body["quarter"]["key"] == q and q in [x["key"] for x in body["quarters"]]
        rows = {x["symbol"]: x for x in body["rows"]}
        assert {"RELIANCE", "LATEX", "OLDX", "NOSCORE"} <= set(rows) and rows["RELIANCE"]["name"]
        for x in body["rows"]:   # Basic: dates and names only, every figure withheld
            assert all(x[k] is None for k in R.FIGURES) and x["flagged"] is False
        assert rows["RELIANCE"]["locked"] and not rows["NOSCORE"]["locked"] and body["summary"]["medianProfitYoY"] is None and body["summary"]["companies"] >= 4
        assert (await anon.get(f"/api/results/quarter?quarter={q}&sort=profitYoY")).status_code == 403     # no reading figures through the sort order
        assert (await anon.get(f"/api/results/quarter?quarter={q}&flagged=true")).status_code == 403
        assert (await anon.get(f"/api/results/quarter/export?quarter={q}")).status_code == 403
        assert (await anon.get(f"/api/results/quarter?quarter={q}&scope=watchlist")).status_code == 401
        assert (await anon.get("/api/results/quarter?quarter=2026-07")).status_code == 400 and (await anon.get("/api/results/quarter?quarter=2026-09&sort=bogus")).status_code == 400
        assert [x["date"] for x in body["rows"]] == sorted((x["date"] for x in body["rows"]), reverse=True)
    silver = await signed_in(app, "res-silver@example.com", plan="silver")
    body = (await silver.get(f"/api/results/quarter?quarter={q}")).json()
    rows = {x["symbol"]: x for x in body["rows"]}
    m = seeded["meta"]
    assert not body["locked"] and rows["RELIANCE"]["status"] == "declared" and rows["RELIANCE"]["revenue"] == pytest.approx(m["q_revenue"], rel=1e-3)
    assert rows["RELIANCE"]["periodEnd"] == seeded["qend"].isoformat()
    # a quarter behind: date has passed, but its stored figures are for the earlier quarter -> awaiting, and NO numbers at all
    assert rows["LATEX"]["status"] == "awaiting" and rows["LATEX"]["awaiting"] and rows["LATEX"]["revenue"] is None and rows["LATEX"]["netProfit"] is None and rows["LATEX"]["loadedPeriodEnd"] < seeded["qend"].isoformat()
    # a row stored before q_period_end existed is read from its statements, not guessed: the same quarter is found there
    assert rows["OLDX"]["status"] == "declared" and rows["OLDX"]["revenue"] == pytest.approx(m["q_revenue"], rel=1e-3) and rows["OLDX"]["loadedPeriodEnd"] == seeded["qend"].isoformat()
    assert rows["NOSCORE"]["status"] == "awaiting" and rows["NOSCORE"]["revenue"] is None
    assert body["summary"]["awaiting"] >= 2 and body["totals"]["withNumbers"] >= 2
    one = (await silver.get(f"/api/results/quarter?quarter={q}&q=reliance&limit=1")).json()
    assert one["total"] == 1 and one["rows"][0]["symbol"] == "RELIANCE"
    exp = await silver.get(f"/api/results/quarter/export?quarter={q}&sort=profitYoY")
    assert exp.status_code == 200 and {x["symbol"] for x in exp.json()["rows"]} >= {"RELIANCE", "LATEX"}
    # watchlist scope reads the member's own list on the server
    put = await silver.put("/api/me/watchlist", json={"lists": [{"id": "a1", "name": "Mine", "symbols": ["NOSCORE"]}], "meta": {}})
    assert put.status_code == 200, put.text
    mine = (await silver.get(f"/api/results/quarter?quarter={q}&scope=watchlist")).json()
    assert [x["symbol"] for x in mine["rows"]] == ["NOSCORE"]


@pytest.mark.integration
async def test_rebuild_metrics_only_missing_adds_the_quarter_date(app):  # noqa: F811
    from finlit.screener.jobs import rebuild_metrics
    store = app.state.store
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE scores SET metrics = metrics - 'q_period_end' WHERE symbol = 'RELIANCE'")
        assert await conn.fetchval("SELECT metrics ? 'q_period_end' FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1' LIMIT 1") is False
    assert await rebuild_metrics(store, only_missing=True) >= 1
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT metrics ? 'q_period_end' FROM scores WHERE symbol = 'RELIANCE' AND model = 'v1' LIMIT 1") is True
    assert await rebuild_metrics(store, only_missing=True) == 0      # nothing left to do: the nightly run stays cheap


@pytest.mark.integration
async def test_days_are_counted_for_the_page_headings(app, seeded):  # noqa: F811
    async with new_client(app) as anon:
        body = (await anon.get(f"/api/results/quarter?quarter={seeded['quarter']}")).json()
    assert sum(d["n"] for d in body["days"]) == body["total"] and [d["date"] for d in body["days"]] == sorted((d["date"] for d in body["days"]), reverse=True)


@pytest.mark.integration
async def test_results_refresh_picks_companies_that_reported_but_are_a_quarter_behind(app, seeded):  # noqa: F811
    from finlit import worker
    store = app.state.store
    today = seeded["when"] + timedelta(days=1)
    found = await worker.results_candidates(store, today=today)
    assert "LATEX" in found and "OLDX" in found           # reported, stored report still on an older (or unknown) quarter
    assert "RELIANCE" not in found                         # its stored report already holds the quarter
    assert "NOSCORE" not in found and "LATER" not in found   # no report held / date still to come
    assert await worker.results_candidates(store, today=today + timedelta(days=30)) == []   # an old declaration is not chased forever


# ---------------------------------------------------------------- operating profit growth, the date filter
OPQ = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]


def test_operating_profit_growth_uses_the_statement_rows_and_says_why_it_is_missing():
    g = R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 30.0, 33.0], E, 33.0)
    assert g["opYoY"] == pytest.approx(50.0) and g["opQoQ"] == pytest.approx(10.0) and g["opYoYWhy"] is None and g["opQoQWhy"] is None
    assert R.op_growth(OPQ, [20.0, -22.0, 24.0, 26.0, 30.0, 33.0], E, 33.0)["opYoYWhy"] == "loss_base"                 # a year ago was a loss: no percentage
    assert R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 0.0, 33.0], E, 33.0)["opQoQWhy"] == "loss_base"                   # a zero base is not growth either
    neg = R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 30.0, -5.0], E, -5.0)
    assert neg["opYoY"] == pytest.approx(-122.7273, rel=1e-4) and neg["opQoQ"] == pytest.approx(-116.6667, rel=1e-4)   # a loss now against a profit before is real, negative growth
    gap = ["2025-06-30", "2025-09-30", "2026-03-31", "2026-06-30", "2026-09-30"]                                          # a quarter missing: five rows back is NOT a year ago
    assert R.op_growth(gap, [20.0, 22.0, 26.0, 30.0, 33.0], E, 33.0)["opYoYWhy"] == "no_prior"
    assert R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 30.0, 33.0], E, 40.0)["opYoYWhy"] == "mismatch"                    # disagrees with the screener's stored figure: withheld
    assert R.op_growth(OPQ, [20.0, None, 24.0, 26.0, 30.0, 33.0], E, 33.0)["opYoYWhy"] == "no_prior"
    assert R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 30.0, 33.0], D(2026, 8, 15))["opYoYWhy"] == "no_data"              # the quarter asked for is not in the table
    assert R.op_growth([], [], E)["opYoY"] is None


def test_row_carries_operating_profit_growth_and_basic_never_sees_it():
    r = _row(m=FIG, opg=None) if False else R.build_row("AAA", R.Decl(D(2026, 10, 14), True), {"name": "Aaa", "sector": "IT", "market_cap": 1.0}, FIG, E, TODAY, "Large", [],
                                                         R.op_growth(OPQ, [20.0, 22.0, 24.0, 26.0, 30.0, 33.0], E, 33.0))
    assert r["opYoY"] == 50.0 and r["opQoQ"] == 10.0 and r["opYoYWhy"] is None and r["operatingProfit"] == 33 and r["opm"] == 20
    lost = R.build_row("AAA", R.Decl(D(2026, 10, 14), True), {}, FIG, E, TODAY, None, [], R.op_growth(OPQ, [20.0, -1.0, 24.0, 26.0, 30.0, 33.0], E, 33.0))
    assert lost["opYoY"] is None and "loss" in lost["opYoYWhy"] and lost["opQoQ"] == 10.0 and lost["opQoQWhy"] is None
    none = _row(m={**FIG, "q_operating_profit": None, "q_opm": None})
    assert none["operatingProfit"] is None and none["opYoY"] is None and "not reported" in none["opYoYWhy"]
    assert _row(m=FIG)["opYoY"] is None and _row(m=FIG)["opYoYWhy"]                       # no statement history at all: a dash with a reason, not a guess
    assert _row(m={})["opYoYWhy"] is None and _row(m={})["opYoY"] is None
    locked = R.strip_figures(r)
    assert locked["opYoY"] is None and locked["opQoQ"] is None and locked["opYoYWhy"] is None and locked["operatingProfit"] is None


def test_date_range_is_validated_in_india_time():
    t = D(2026, 10, 21)
    assert R.parse_range("", "", "", t) is None
    assert R.parse_range("2026-10-21", "", "", t) == (t, t) and R.parse_range("", "2026-10-14", "2026-10-21", t) == (D(2026, 10, 14), t)
    assert R.parse_range("", "2026-10-14", "", t) == (D(2026, 10, 14), t)                 # an open end means "up to today"
    for args, code in ((("2026-10-22", "", ""), "future_date"), (("", "2026-10-01", "2026-12-31"), "future_date"), (("", "2026-10-20", "2026-10-01"), "bad_request"), (("2026-13-01", "", ""), "bad_request"),
                       (("2026-02-30", "", ""), "bad_request"), (("21/10/2026", "", ""), "bad_request"), (("2026-10-01", "2026-10-01", ""), "bad_request"), (("", "", "2026-10-01"), "bad_request")):
        with pytest.raises(Exception) as ex:
            R.parse_range(*args, t)
        assert ex.value.detail["status"] == code, args
    assert "India time" in _raises(lambda: R.parse_range("2026-10-22", "", "", t)).detail["detail"]


def _raises(fn):
    with pytest.raises(Exception) as ex:
        fn()
    return ex.value


def test_select_filters_by_announcement_date_inclusive():
    rows = [_row("A", D(2026, 10, 14), FIG), _row("B", D(2026, 10, 15), FIG), _row("C", D(2026, 10, 17), {}), _row("D", D(2026, 10, 18), FIG)]
    sym = lambda rs: [r["symbol"] for r in rs]   # noqa: E731
    assert sym(R.select(rows, date_from="2026-10-15", date_to="2026-10-17", today="2026-10-20")) == ["C", "B"]
    assert sym(R.select(rows, date_from="2026-10-14", date_to="2026-10-14", today="2026-10-20")) == ["A"]
    assert R.select(rows, date_from="2026-10-19", date_to="2026-10-19") == []
    assert sym(R.select(rows, date_from="2026-10-15", date_to="2026-10-18", flagged=True, today="2026-10-20")) == ["D", "B"]


def test_date_facts_name_the_quarters_and_the_nearest_days():
    decls = {"2026-09": {"A": R.Decl(D(2026, 10, 14), True), "B": R.Decl(D(2026, 10, 14), True), "C": R.Decl(D(2026, 10, 9), True), "D": R.Decl(D(2026, 10, 30), False)},
             "2026-06": {"E": R.Decl(D(2026, 10, 14), True), "F": R.Decl(D(2026, 8, 1), True)}}
    f = R.date_facts(decls, (D(2026, 10, 14), D(2026, 10, 14)), "2026-09")
    assert f["single"] and [(x["key"], x["n"]) for x in f["quarters"]] == [("2026-09", 2), ("2026-06", 1)] and f["inQuarter"]
    e = R.date_facts(decls, (D(2026, 10, 12), D(2026, 10, 13)), "2026-09")
    assert not e["inQuarter"] and e["quarters"] == [] and [(x["date"], x["n"]) for x in e["nearest"]] == [("2026-10-09", 1), ("2026-10-14", 2)]
    assert e["coverage"] == {"earliest": "2026-08-01", "latest": "2026-10-30"}
    assert R.date_facts({}, (D(2026, 10, 12), D(2026, 10, 12)), None)["coverage"]["earliest"] is None


@pytest.mark.integration
async def test_endpoint_date_filter_deep_link_and_errors(app, seeded):  # noqa: F811
    today = R.today_ist()
    when, q = seeded["when"], seeded["quarter"]
    if when > today:
        pytest.skip("fixture quarter ends too recently for a past announcement date")
    silver = await signed_in(app, "res-date@example.com", plan="silver")
    one = (await silver.get(f"/api/results/quarter?date={when.isoformat()}")).json()                   # no quarter given: found from the date
    assert one["quarter"]["key"] == q and {x["symbol"] for x in one["rows"]} >= {"RELIANCE", "LATEX"} and all(x["date"] == when.isoformat() for x in one["rows"])
    assert one["dates"]["single"] and one["dates"]["quarters"][0]["key"] == q and "announced" in one["dateMeaning"]
    rng = (await silver.get(f"/api/results/quarter?quarter={q}&from={(when - timedelta(days=5)).isoformat()}&to={(when - timedelta(days=3)).isoformat()}")).json()
    assert {x["symbol"] for x in rng["rows"]} == {"OLDX", "NOSCORE"} and rng["total"] == 2
    empty = (await silver.get(f"/api/results/quarter?quarter={q}&date={(when - timedelta(days=1)).isoformat()}")).json()
    assert empty["rows"] == [] and empty["total"] == 0 and empty["dates"]["nearest"] and empty["dates"]["coverage"]["earliest"]    # never a blank: says where results are
    assert (await silver.get(f"/api/results/quarter?date={(today + timedelta(days=1)).isoformat()}")).status_code == 400
    assert (await silver.get("/api/results/quarter?date=nonsense")).status_code == 400 and (await silver.get("/api/results/quarter?from=2026-10-02&to=2026-10-01")).status_code == 400
    exp = (await silver.get(f"/api/results/quarter/export?quarter={q}&date={when.isoformat()}")).json()
    assert {x["symbol"] for x in exp["rows"]} >= {"RELIANCE"} and all(x["date"] == when.isoformat() for x in exp["rows"])
    async with new_client(app) as anon:                                                                     # Basic keeps dates and names, no figures, also through a date link
        b = (await anon.get(f"/api/results/quarter?date={when.isoformat()}")).json()
        assert b["rows"] and all(x[k] is None for x in b["rows"] for k in R.FIGURES)
    full = {x["symbol"]: x for x in (await silver.get(f"/api/results/quarter?quarter={q}")).json()["rows"]}
    assert "opYoY" in full["RELIANCE"] and (full["RELIANCE"]["opYoY"] is not None or full["RELIANCE"]["opYoYWhy"])
