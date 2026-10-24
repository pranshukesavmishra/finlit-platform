"""FII / DII flows: parsers against recorded real answers (tests/fixtures/flows), streaks, moods, periods, correlation, publish-time checks,
the nightly job end to end against a fake of NSDL and the NSE archive serving the recordings, manual entry and the admin route."""
import json
import time
from datetime import date
from pathlib import Path

import httpx
import pytest

from finlit import flows, flows_sources as S
from test_auth import app  # noqa: F401  (fixture)
from test_integration import ingested, store  # noqa: F401  (fixtures)

FX = Path(__file__).parent / "fixtures" / "flows"
text = lambda n: (FX / n).read_text(errors="replace")      # noqa: E731
D = date


# ---- NSDL: FPI (FII)
def test_latest_page_reads_the_equity_stock_exchange_route_and_the_all_asset_view():
    page = text("nsdl_fpi_latest_2026-10-23.html")
    assert S.fpi_header_date(page) == D(2026, 10, 23)
    (day,) = S.parse_fpi(page)                              # the derivative-trades table below it is not read as a day
    assert day.d == D(2026, 10, 23) and day.problems == []
    assert (day.equity.buy, day.equity.sell, day.equity.net, day.equity.usd) == (14875.82, 17137.99, -2262.17, -238.88)
    assert day.equity_primary.net == 2417.14 and day.equity_total.net == 154.97          # both routes together: not the same as the exchange route
    assert day.debt_net == -3020.73 and day.hybrid_net == -21.46 and day.mf_net == 40.96 and day.aif_net == 0.0
    assert day.total.net == -2846.26 and day.total.usd == -300.55 and day.rate == 94.6986


def test_monthly_page_has_every_day_of_the_month_so_far():
    days = S.parse_fpi(text("nsdl_fpi_monthly_2026-10.html"))
    assert len(days) == 15 and days[0].d == D(2026, 10, 1) and days[-1].d == D(2026, 10, 23)
    assert days[0].equity.net == -9569.57 and days[0].equity_total.net == -9231.88 and days[0].total.net == -9507.95 and days[0].rate == 95.9832
    assert days[0].debt_net == -199.02                     # general limit + VRR + FAR sub-totals: -669.12 + 776.09 - 305.99
    assert all(x.equity and not x.problems for x in days) and [x.d for x in days] == sorted(x.d for x in days)


def test_archive_pages_in_every_layout_NSDL_has_used():
    sep = S.parse_fpi(text("nsdl_fpi_archive_2025-09.html"))
    assert len(sep) == 20 and S.fpi_header_date(text("nsdl_fpi_archive_2025-09.html")) == D(2025, 9, 30)
    assert sep[0].d == D(2025, 9, 1) and sep[0].equity.net == -9024.69 and sep[0].debt_net == 1245.74 and sep[0].mf_net == 65.73
    old = S.parse_fpi(text("nsdl_fpi_archive_2012-01.html"))              # one decimal in the older years: net may differ from purchases - sales by a step
    assert len(old) == 21 and all(x.equity and not x.problems for x in old)
    assert (old[0].d, old[0].equity.buy, old[0].equity.sell, old[0].equity.net) == (D(2012, 1, 2), 965.1, 1062.7, -97.5) and old[0].rate == 53.266
    assert old[0].debt_net == -812.7 and old[0].hybrid_net is None
    flat = S.parse_fpi(text("nsdl_fpi_archive_2008-12_no_route.html"))    # 2008 has no route column: only the combined figure exists, so no exchange-route flow is invented
    assert len(flat) == 21 and all(x.equity is None and x.equity_total is not None for x in flat)


def test_a_row_that_does_not_add_up_is_not_read():
    page = text("nsdl_fpi_latest_2026-10-23.html").replace("(2262.17)", "(2999.17)")
    (day,) = S.parse_fpi(page)
    assert day.equity is None and "does not add up" in day.problems[0]
    assert S.parse_fpi("<html>nothing here</html>") == []


def test_numbers_as_NSDL_prints_them():
    assert S.num("(9569.57)") == -9569.57 and S.num(" (20.13)") == -20.13 and S.num("1,234.50") == 1234.5 and S.num("Rs.95.9832") == 95.9832
    assert S.num("") is None and S.num("-") is None and S.num("abc") is None and S.parse_date("23-Oct-2026") == D(2026, 10, 23) and S.parse_date("2026-10-23") is None


# ---- NSDL: DII
def test_dii_report_total_is_the_sum_of_the_investor_types():
    d = S.parse_dii(text("nsdl_dii_latest_2026-10-23.html"))
    assert d.d == D(2026, 10, 23) and d.problems == [] and d.rate == 94.6986
    assert (d.equity.buy, d.equity.sell, d.equity.net) == (16121.71, 13397.42, 2724.29)
    assert set(d.by_type) == {"Bank", "Insurance", "MFs", "AIFs", "Others"} and d.by_type["MFs"].net == 1760.37
    assert round(sum(v.net for v in d.by_type.values()), 2) == 2724.29
    assert S.parse_dii(text("nsdl_dii_archive_2026-10-15.html")).equity.net == 2791.83


def test_dii_no_data_and_foreign_pages_are_none():
    assert S.parse_dii(text("nsdl_dii_archive_no_data.html")) is None and S.parse_dii(text("nsdl_fpi_latest_2026-10-23.html")) is None
    assert S.parse_dii(text("nsdl_dii_latest_2026-10-23.html").replace("13397.42", "13000.00")) is None      # total no longer adds up: refused


# ---- NSE archive: participant-wise open interest
def test_participant_oi_files_old_and_new():
    d = S.parse_participant_oi(text("nse_participant_oi_2026-10-22.csv"))
    assert d.d == D(2026, 10, 22)
    assert d.rows[("FII", "Index Futures")] == (34703, 315003) and d.rows[("DII", "Stock Futures")] == (384160, 4719038)
    assert d.rows[("FII", "Index Options")] == (808596 + 1171687, 1098945 + 669527) and d.rows[("Pro", "Stock Options")] == (1169678 + 1192000, 1700021 + 1136195)
    assert len(d.rows) == 16 and {p for p, _ in d.rows} == {"FII", "DII", "Pro", "Client"}          # the TOTAL line is not a participant
    old = S.parse_participant_oi(text("nse_participant_oi_2012-01-03.csv"))                           # header spelled CLIENT_TYPE, date spelled out in full
    assert old.d == D(2012, 1, 3) and old.rows[("Client", "Index Futures")] == (239132, 250336)
    assert S.parse_participant_oi("<html>Access Denied</html>") is None and S.parse_participant_oi("") is None


# ---- the maths
def test_nse_report_is_read_and_checked():
    days = S.parse_nse(text("nse_fiidii_2026-10-23.json"))
    assert len(days) == 1 and days[0].d == D(2026, 10, 23) and not days[0].problems
    assert (days[0].fii.buy, days[0].fii.sell, days[0].fii.net) == (14445.54, 13557.89, 887.65) and days[0].dii.net == 3235.36
    bad = text("nse_fiidii_2026-10-23.json").replace('"netValue":"887.65"', '"netValue":"-887.65"')
    assert S.parse_nse(bad)[0].problems and S.parse_nse("<html>blocked</html>") == []


def test_mood_thresholds_are_exact():
    m = flows.mood_of
    assert [m(v) for v in (-5000, -4999.99, -500.01, -500, 0, 500, 500.01, 4999.99, 5000)] == [
        "Heavy outflow", "Mild outflow", "Mild outflow", "Balanced", "Balanced", "Balanced", "Mild inflow", "Mild inflow", "Heavy inflow"] and m(None) is None


def test_streak_is_the_run_of_the_latest_sign():
    s = lambda *v: [(D(2026, 10, 1 + i), x) for i, x in enumerate(v)]          # noqa: E731
    assert flows.streak(s(5, -3, -2, -10)) == {"side": "selling", "days": 3, "since": "2026-10-02", "sum": -15.0, "velocity": -5.0}
    assert flows.streak(s(-1, 4, 2))["side"] == "buying" and flows.streak(s(-1, 4, 2))["velocity"] == 3.0
    assert flows.streak(s(1, 0, 0)) == {"side": "flat", "days": 2, "since": "2026-10-02", "sum": 0.0, "velocity": 0.0}
    assert flows.streak(s(7))["days"] == 1 and flows.streak([]) is None


def row(d, fn=None, dn=None, fb=None, fs=None, db=None, ds=None, fsrc="nsdl", dsrc="nsdl"):
    return flows.Row(d, fb, fs, fn, fsrc if fn is not None else None, db, ds, dn, dsrc if dn is not None else None)


def test_periods_sum_only_what_every_session_has():
    rows = [row(D(2026, 9, 28), -100.0), row(D(2026, 9, 30), 50.0), row(D(2026, 10, 1), -10.0, 20.0), row(D(2026, 10, 5), 30.0, 5.0), row(D(2026, 10, 6), 1.0, None)]
    p = {x["key"]: x for x in flows.periods(rows, D(2026, 10, 7))}
    assert p["week"]["days"] == 2 and p["week"]["from"] == "2026-10-05" and p["week"]["fii"] == 31.0 and p["week"]["diiNet"] is None        # DII missing on 6 Oct
    assert p["month"]["days"] == 3 and p["month"]["fii"] == 21.0
    assert p["fy"]["days"] == 5 and p["fy"]["fii"] == -29.0 and p["fy"]["diiNet"] is None and p["cy"]["fii"] == -29.0
    assert p["r30"]["fii"] is None and p["r30"]["days"] == 5 and p["r365"]["fii"] is None            # fewer sessions than the window: counted, not summed
    assert flows.periods([], D(2026, 10, 7))[0]["days"] == 0
    m = flows.grouped(rows, "%Y-%m", "m")
    assert m[0] == {"m": "2026-09", "fii": -50.0, "dii": None, "days": 2} and m[1]["days"] == 3
    only_dii = [row(D(2026, 10, 1), -10.0, 20.0), row(D(2026, 10, 5), 30.0, 5.0)]
    assert flows.grouped(only_dii, "%Y", "y") == [{"y": "2026", "fii": 20.0, "dii": 25.0, "days": 2}]


def test_pearson_and_the_30_session_floor():
    xs = list(range(40))
    assert flows.pearson(xs, [2 * x + 1 for x in xs]) == 1.0 and flows.pearson(xs, [-x for x in xs]) == -1.0
    assert flows.pearson(xs[:29], xs[:29]) is None and flows.pearson(xs, [3] * 40) is None


def test_correlation_pairs_each_day_with_the_index_move_of_that_day():
    start = D(2026, 1, 1)
    days = [start.fromordinal(start.toordinal() + i) for i in range(45)]
    closes = {}
    level = 100.0
    rows = []
    for i, d in enumerate(days):
        flow = float((i * 37) % 11 - 5)
        level *= 1 + flow / 1000                       # the index moves exactly with the flow of its own day
        closes[d] = level
        rows.append(row(d, flow))
    c = flows.correlation(rows, closes)
    assert c["index"] == "NIF50" and c["days"] == 44 and c["fiiVsIndex"] > 0.99 and c["diiVsIndex"] is None
    assert flows.correlation(rows[:20], closes) is None


def test_publish_checks_leave_out_what_cannot_be_right():
    ok, bad = row(D(2026, 10, 1), -10.0, fb=100.0, fs=110.0), row(D(2026, 10, 2), 500.0, fb=100.0, fs=110.0)
    rows, issues = flows.checked([ok, bad, row(D(2026, 12, 1), 5.0), row(D(2026, 10, 3), 999999.0)], D(2026, 10, 7))
    assert rows == [ok] and len(issues) == 3 and "not purchases minus sales" in issues[0] and "future" in issues[1] and "out of range" in issues[2]


# ---- the nightly job end to end, against a fake of NSDL and the NSE archive serving the recordings
def fake_sites(down=False):
    state = {"posts": [], "gets": []}

    def handler(req: httpx.Request) -> httpx.Response:
        if down:
            return httpx.Response(503)
        state["gets" if req.method == "GET" else "posts"].append(str(req.url))
        u = req.url
        if u.host == "www.nseindia.com":
            return httpx.Response(200, text=text("nse_fiidii_2026-10-23.json")) if u.path == "/api/fiidiiTradeReact" else httpx.Response(403)
        assert req.headers["user-agent"].startswith("FinLit-data/1.0 (+https://finlitventures.com)")
        if u.host == "archives.nseindia.com":
            return httpx.Response(200, text=text("nse_participant_oi_2026-10-22.csv")) if u.path.endswith("22102026.csv") else httpx.Response(404, text="<html>Not found</html>")
        if u.host != "www.fpi.nsdl.co.in":
            return httpx.Response(404)
        if u.path.endswith("/Reports/Latest.aspx"):
            return httpx.Response(200, text=text("nsdl_fpi_latest_2026-10-23.html"))
        if u.path.endswith("/Reports/Monthly.aspx"):
            return httpx.Response(200, text=text("nsdl_fpi_monthly_2026-10.html"))
        if u.path.endswith("/Users/DIIGenerateReport.aspx"):
            if u.params.get("Rep") == "L":
                return httpx.Response(200, text=text("nsdl_dii_latest_2026-10-23.html"))
            if req.method == "GET":
                return httpx.Response(200, text=text("nsdl_dii_archive_no_data.html"))
            return httpx.Response(200, text=text("nsdl_dii_archive_2026-10-15.html") if "15-Oct-2026" in req.content.decode() else text("nsdl_dii_archive_no_data.html"))
        if u.path.endswith("/Reports/Archive.aspx"):
            if req.method == "GET":
                return httpx.Response(200, text=text("nsdl_fpi_archive_form.html"))
            body = req.content.decode()
            assert "__EVENTTARGET=btnSubmit1" in body and "__VIEWSTATE" in body
            return httpx.Response(200, text=text("nsdl_fpi_archive_2025-09.html") if "30-Sep-2025" in body else "<table><tr><th>Daily Trends in FPI Investments up to 31-Aug-2025</th></tr></table>")
        return httpx.Response(404)
    return httpx.MockTransport(handler), state


async def nifty():
    return json.loads((Path(__file__).parent / "fixtures" / "finedge" / "index_price_nif50.json").read_text())


@pytest.fixture
async def fstore(monkeypatch):
    import os
    from finlit.config import Settings
    from finlit.store import Store
    s = Settings(finedge_api_key="t", finedge_mode="fixtures", database_url=os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test"),
                 redis_url=os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"))
    try:
        st = await Store.connect(s)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    sql = (Path(flows.__file__).parent / "migrations" / "051_flows.sql").read_text()
    async with st.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS flows_daily, flows_oi, flows_index, flows_meta")
        await conn.execute(sql)
        await conn.execute((Path(flows.__file__).parent / "migrations" / "058_flows_nse_source.sql").read_text())
    await st.redis.flushdb()
    monkeypatch.setattr(flows, "PAUSE", 0)
    monkeypatch.setattr(flows, "OI_PAUSE", 0)
    monkeypatch.setattr(flows, "FIRST", D(2025, 8, 1))
    monkeypatch.setattr(flows, "DII_START", D(2026, 10, 14))
    yield st
    await st.close()


def client(store):
    from finlit.api import create_app
    from finlit.config import Settings
    return create_app(Settings(finedge_api_key="t", finedge_mode="fixtures", database_url=store.settings.database_url if hasattr(store, "settings") else "x", redis_url="redis://localhost:6379/15"), store=store)


@pytest.mark.integration
async def test_nightly_refresh_builds_and_serves_the_page(fstore):
    transport, seen = fake_sites()
    res = await flows.refresh(fstore, transport=transport, today=D(2026, 10, 23), nifty=nifty)
    assert res["status"] == "ok", res
    assert res["steps"]["fii"]["rows"] > 30 and res["steps"]["dii"]["rows"] >= 2 and res["steps"]["oi"]["latest"] == "2026-10-22" and res["steps"]["nifty"]["rows"] > 1000
    assert any("Archive.aspx" in p for p in seen["posts"]) and any("fao_participant_oi_22102026" in g for g in seen["gets"])
    app = client(fstore)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            r = await api.get("/api/flows")
            assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
            body = r.json()
            assert (await api.get("/api/flows", headers={"If-None-Match": r.headers["etag"]})).status_code == 304
    lt = body["latest"]
    assert lt["d"] == "2026-10-23" and lt["fii"] == {"buy": 14445.54, "sell": 13557.89, "net": 887.65} and lt["dii"] == {"buy": 19232.31, "sell": 15996.95, "net": 3235.36}      # the exchange's figures win over NSDL's for the day
    assert lt["combinedNet"] == 4123.01 and lt["fiiShareOfSelling"] == round(13557.89 / (13557.89 + 15996.95), 4) and lt["mood"] == "Mild inflow"
    assert body["days"][-1]["d"] == "2026-10-23" and body["days"][0]["d"] == "2025-09-01" and body["days"][0]["dii"] is None       # no DII before NSDL's first report
    assert body["streaks"]["fii"]["side"] in ("selling", "buying") and body["streaks"]["dii"]["days"] >= 1
    assert body["last30"]["dii"] is None and body["last30"]["fii"] is not None and body["last30"]["days"] == 30
    assert {p["key"] for p in body["periods"]} == {"week", "month", "fy", "cy", "r30", "r90", "r365"}
    month = next(p for p in body["periods"] if p["key"] == "month")
    assert month["days"] == 15 and month["diiNet"] is None        # DII exists only from 14 Oct in this test: a part-sum is not given
    assert [m["m"] for m in body["monthly"]] == ["2025-09", "2026-10"] and body["yearly"][0]["y"] == "2025" and body["yearly"][0]["dii"] is None
    assert body["derivatives"]["asOf"] == "2026-10-22" and {"participant": "FII", "instrument": "Index Futures", "long": 34703, "short": 315003, "net": -280300} in body["derivatives"]["rows"]
    assert body["fpi"] == {"asOf": "2026-10-23", "equityNet": 154.97, "debtNet": -3020.73, "hybridNet": -21.46, "totalNet": -2846.26, "usdMillion": -300.55, "inr": 94.6986}
    assert body["correlation"]["index"] == "NIF50" and body["correlation"]["days"] >= 30 and -1 <= body["correlation"]["fiiVsIndex"] <= 1
    assert body["index"] and body["coverage"]["to"] == "2026-10-23" and body["coverage"]["diiSessions"] >= 2
    src = {s["id"]: s for s in body["sources"]}
    assert src["fii"]["status"] == "ok" and src["fii"]["lastDate"] == "2026-10-23" and src["dii"]["status"] == "ok" and src["participant-oi"]["status"] == "ok"
    assert src["nse-cash"]["status"] == "ok" and "manual" not in src and "not investment advice" in body["disclaimer"]


@pytest.mark.integration
async def test_a_failing_source_keeps_the_last_good_data_and_says_so(fstore):
    await flows.refresh(fstore, transport=fake_sites()[0], today=D(2026, 10, 23), nifty=nifty)

    async def boom():
        raise RuntimeError("provider down")
    import asyncio

    async def instant(*_a, **_k):
        return None
    orig = asyncio.sleep
    asyncio.sleep = instant
    try:
        res = await flows.refresh(fstore, transport=fake_sites(down=True)[0], today=D(2026, 10, 25), nifty=boom)
    finally:
        asyncio.sleep = orig
    assert res["status"] == "failed" and {k for k, v in res["steps"].items() if v["status"] == "failed"} == {"fii", "dii", "nse", "oi", "nifty"}
    async with fstore.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM flows_daily WHERE fii_net IS NOT NULL") > 30
        payload = await flows.get_meta(conn, "payload")
    assert payload["latest"]["fii"]["net"] == 887.65 and payload["today"] == "2026-10-25"
    src = {s["id"]: s for s in payload["sources"]}
    assert "last refresh failed" in src["fii"]["note"] and src["fii"]["lastDate"] == "2026-10-23" and src["fii"]["status"] == "ok"


@pytest.mark.integration
async def test_a_source_that_stops_posting_turns_stale(fstore):
    await flows.refresh(fstore, transport=fake_sites()[0], today=D(2026, 10, 23), nifty=nifty)
    p = await flows.publish(fstore, D(2026, 11, 20))
    assert {s["id"]: s for s in p["sources"]}["fii"]["status"] == "stale"


@pytest.mark.integration
async def test_loading_503_until_the_first_run(fstore):
    app = client(fstore)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            r = await api.get("/api/flows")
            assert r.status_code == 503 and r.json()["status"] == "loading" and r.headers["retry-after"]


@pytest.mark.integration
async def test_manual_entry_wins_is_labelled_and_is_never_overwritten(fstore):
    await flows.refresh(fstore, transport=fake_sites()[0], today=D(2026, 10, 23), nifty=nifty)
    async with fstore.pool.acquire() as conn:
        done = await flows.save_manual(conn, flows.ManualIn(d=D(2026, 10, 22), fii=flows.SideIn(buy=1000, sell=1500), dii=flows.SideIn(net=250.5)), D(2026, 10, 23))
        assert done == ["fii", "dii"]
        with pytest.raises(ValueError):
            await flows.save_manual(conn, flows.ManualIn(d=D(2026, 10, 24), dii=flows.SideIn(net=1)), D(2026, 10, 23))
        with pytest.raises(ValueError):
            await flows.save_manual(conn, flows.ManualIn(d=D(2026, 10, 21), fii=flows.SideIn(buy=1000)), D(2026, 10, 23))
        with pytest.raises(ValueError):
            await flows.save_manual(conn, flows.ManualIn(d=D(2026, 10, 21), fii=flows.SideIn(buy=1000, sell=900, net=5)), D(2026, 10, 23))
    await flows.refresh(fstore, transport=fake_sites()[0], today=D(2026, 10, 23), nifty=nifty, only=["fii", "dii"])      # the nightly run does not undo it
    async with fstore.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM flows_daily WHERE d = '2026-10-22'")
    assert (r["fii_net"], r["fii_source"], r["dii_net"], r["dii_source"]) == (-500.0, "manual", 250.5, "manual")
    p = await flows.publish(fstore, D(2026, 10, 23))
    src = {s["id"]: s for s in p["sources"]}
    assert src["manual"]["lastDate"] == "2026-10-22" and "1 day" in src["manual"]["note"]
    async with fstore.pool.acquire() as conn:
        assert await flows.clear_manual(conn, D(2026, 10, 22), "both") == 2
        assert await conn.fetchval("SELECT fii_source FROM flows_daily WHERE d = '2026-10-22'") is None


@pytest.mark.integration
async def test_without_dii_the_page_still_works_and_says_why(fstore):
    base = fake_sites()[0]
    t = httpx.MockTransport(lambda req: httpx.Response(200, text=text("nsdl_dii_archive_no_data.html")) if "DIIGenerate" in req.url.path else base.handler(req))
    res = await flows.refresh(fstore, transport=t, today=D(2026, 10, 23), nifty=nifty, only=["fii", "dii", "oi", "nifty"])      # the exchange's report, which carries DII, is left out here
    assert res["steps"]["fii"]["status"] == "ok"
    p = await flows.publish(fstore, D(2026, 10, 23))
    assert p["latest"]["dii"] is None and p["latest"]["combinedNet"] is None and p["latest"]["fiiShareOfSelling"] is None and p["coverage"]["diiSessions"] == 0
    assert p["streaks"]["dii"] is None and p["last30"]["dii"] is None and all(d["dii"] is None for d in p["days"])
    dii = {s["id"]: s for s in p["sources"]}["dii"]
    assert dii["status"] == "unavailable" and dii["lastDate"] is None and "estimated" in dii["note"]


# ---- the admin route
@pytest.mark.integration
async def test_admin_route_needs_an_administrator_with_mfa(app, monkeypatch):      # noqa: F811
    from finlit.auth import crypto
    from test_auth import make_admin, new_client, signed_in
    sql = (Path(flows.__file__).parent / "migrations" / "051_flows.sql").read_text()
    async with app.state.store.pool.acquire() as conn:
        await conn.execute(sql)
        await conn.execute("DELETE FROM flows_daily")
    body = {"d": "2026-10-20", "fii": {"buy": 9000, "sell": 12000}, "dii": {"net": 3100.25}}
    async with new_client(app) as anon:
        assert (await anon.post("/api/admin/flows", json=body)).status_code == 401
    user = await signed_in(app, "member@example.com")
    assert (await user.post("/api/admin/flows", json=body)).json()["detail"]["status"] == "forbidden"
    boss = await make_admin(app, "flows-boss@example.com")
    assert (await boss.post("/api/admin/flows", json=body)).json()["detail"]["status"] == "mfa_required"
    secret = (await boss.post("/api/me/mfa/setup")).json()["secret"]
    assert (await boss.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    assert (await boss.post("/api/admin/flows", json={"d": "2026-10-20", "fii": {"buy": 5}})).status_code == 422
    r = await boss.post("/api/admin/flows", json=body)
    assert r.status_code == 200 and r.json()["sides"] == ["fii", "dii"]
    served = (await boss.get("/api/flows")).json()
    assert served["latest"]["d"] == "2026-10-20" and served["latest"]["fii"]["net"] == -3000.0 and served["latest"]["dii"]["net"] == 3100.25
    assert {s["id"]: s for s in served["sources"]}["manual"]["status"] == "ok"
    assert (await boss.delete("/api/admin/flows/2026-10-20")).json()["removed"] == 2
    for c in (user, boss):
        await c.aclose()
