"""India macro data: parsers against recorded real answers (tests/fixtures/macro), derived series, checks and the nightly job end to end."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from finlit import macro, macro_sources as S

FX = Path(__file__).parent / "fixtures" / "macro"
load = lambda n: json.loads((FX / n).read_text())          # noqa: E731
text = lambda n: (FX / n).read_text(errors="replace")      # noqa: E731
D = date


def test_cpi_uses_mospis_published_rates_and_divisions():
    p = S.parse_cpi(load("cpi_current_2026_09.json"))
    assert p.series["cpi"][D(2026, 9, 30)] == 5.54 and p.series["cpi_rural"][D(2026, 9, 30)] == 6.08 and p.series["cpi_urban"][D(2026, 9, 30)] == 4.88
    assert p.series["cpi_idx"][D(2026, 9, 30)] == 109.49
    assert p.series["cpi_div_01"][D(2026, 9, 30)] == 7.36 and p.labels["cpi_div_01"] == "Food and beverages"
    assert len([k for k in p.series if k.startswith("cpi_div_")]) == 12
    assert all(len(v) == 1 for v in p.series.values())              # one month in the answer, nothing from other rows


def test_cpi_2025_has_no_published_rate_and_back_series_does():
    assert "cpi" not in S.parse_cpi(load("cpi_current_2025_09.json")).series               # the new series' first year carries no rate
    back = S.parse_cpi(load("cpi_back_2024.json"))
    assert len(back.series["cpi"]) == 12 and all(-5 < v < 15 for v in back.series["cpi"].values())


def test_derived_2025_inflation_matches_how_mospi_computes_2026():
    """The same derivation (index against the same month a year earlier, one base) reproduces MoSPI's own published September 2026 rates."""
    a, b = S.parse_cpi(load("cpi_current_2026_09.json")), S.parse_cpi(load("cpi_current_2025_09.json"))
    for k in ("cpi", "cpi_rural", "cpi_urban"):
        derived = round((a.series[k + "_idx"][D(2026, 9, 30)] / b.series[k + "_idx"][D(2025, 9, 30)] - 1) * 100, 2)
        assert abs(derived - a.series[k][D(2026, 9, 30)]) <= 0.011       # indices are published to two decimals


def test_wpi_is_derived_within_one_base():
    now = S.parse_wpi_index(load("wpi22_2026.json"), "1000000000")
    before = S.parse_wpi_index(load("wpi22_2025.json"), "1000000000")
    assert now[D(2026, 9, 30)] == 112.5 and before[D(2025, 9, 30)] == 101.0
    assert S.yoy({**before, **now})[D(2026, 9, 30)] == 11.39
    assert S.yoy(now) == {}                                                                      # no earlier year in hand: no figure, never a guess
    fuel = S.parse_wpi_index(load("wpi22_2026_fuel.json"), "1200000000")                          # the answer also holds hundreds of item rows under fuel
    assert fuel[D(2026, 9, 30)] == 110.5 and len(fuel) <= 9 and all(100 < v < 140 for v in fuel.values())


def test_gdp_levels_and_growth():
    const, cur = S.parse_gdp(load("nas22_q.json"))
    assert const[D(2026, 6, 30)] == 8136153 and cur[D(2026, 6, 30)] == 8826871
    assert S.yoy(const)[D(2026, 6, 30)] == 7.82 and S.yoy(cur)[D(2026, 6, 30)] == 10.33
    assert S.fy_quarter_end("2025-26", "Q4") == D(2026, 3, 31) and S.fy_quarter_end("2025-26", "Q1") == D(2025, 6, 30) and S.fy_quarter_end("x", "Q1") is None
    old, _ = S.parse_gdp(load("nas11_q.json"))
    assert min(old) <= D(2013, 6, 30) and len(old) >= 50


def test_iip_and_unemployment():
    p = S.parse_iip(load("iip22_2026.json"))
    assert p.series["iip"][D(2026, 8, 31)] == 8.0 and p.series["iip_mfg"][D(2026, 8, 31)] == 9.0 and p.series["iip_capital"][D(2026, 8, 31)] == 16.9
    u = S.parse_plfs(load("plfs_2026_p1.json")).merge(S.parse_plfs(load("plfs_2026_p2.json")))
    assert u.series["unemployment"][D(2026, 9, 30)] == 5.0 and u.series["unemployment_youth"][D(2026, 9, 30)] == 15.2 and u.series["unemployment_urban"][D(2026, 9, 30)] == 6.9
    assert u.series["unemployment"][D(2026, 7, 31)] == 5.1


def test_rbi_tables_via_mospi():
    r = S.parse_rbi_reserves_monthly(load("rbi47_p1.json"))
    assert r == {} or all(v > 0 for v in r.values())                                          # only the Total row in US$ is read; other rows are skipped
    sample = {"data": [{"year": "2025", "month": "March", "foreign_exchange_reserve_type": "Total", "foreign_exchange_reserve_currency": "US $ Millions", "value": "668,000.5"},
                       {"year": "2025", "month": "March", "foreign_exchange_reserve_type": "Gold", "foreign_exchange_reserve_currency": "US $ Millions", "value": "70000"},
                       {"year": "2025", "month": "April", "foreign_exchange_reserve_type": "Total", "foreign_exchange_reserve_currency": "₹ Crores", "value": "5000000"},
                       {"year": "2002", "month": "April", "foreign_exchange_reserve_type": "Total", "foreign_exchange_reserve_currency": "US $ Millions", "value": "-"}]}
    assert S.parse_rbi_reserves_monthly(sample) == {D(2025, 3, 31): 668.0}
    fx = S.parse_rbi_usdinr_monthly(load("rbi33_p1.json"))
    assert all(30 < v < 150 for v in fx.values())
    assert S.parse_rbi_usdinr_monthly({"data": [{"year": "2025", "month": "August", "currency": "US Dollar", "reference_rate": "Average", "value": "87.5"},
                                                {"year": "2025", "month": "August", "currency": "US Dollar", "reference_rate": "End-month", "value": "88"},
                                                {"year": "2025", "month": "August", "currency": "SDR", "reference_rate": "Average", "value": "119"}]}) == {D(2025, 8, 31): 87.5}


def test_rbi_current_rates_panel():
    got = S.parse_rbi_home(text("rbi_home.html"))
    assert got["rates"] == {"repo": 5.5, "sdf": 5.25, "msf": 5.75, "bank_rate": 5.75, "reverse_repo": 3.35, "crr": 3.0, "slr": 18.0}
    assert got["fx"]["usdinr"] == 94.9432 and got["fxAsOf"] == "2026-10-23"
    assert S.parse_rbi_home("<html>redesigned</html>") is None                 # a redesign gives nothing, never a wrong number
    assert S.parse_rbi_home("<p>Current Rates Bank Rate : 5.75%</p>") is None   # no repo rate: not trusted


def test_wss_extract():
    link = S.latest_wss_link(text("rbi_press_rss.xml"))
    assert link and link[0].endswith("prid=63855")
    assert S.latest_wss_link("<rss><item><title>Auction</title><link>https://rbi.org.in/x</link></item></rss>") is None
    assert S.latest_wss_link("<rss><item><title>Weekly Statistical Supplement - Extract</title><link>https://evil.example/x</link></item></rss>") is None
    w = S.parse_wss_extract(text("rbi_wss_extract.html"))
    t = w["reserves"]["total"]
    assert w["reservesAsOf"] == "2026-10-16" and t["usd"] == 721016 and t["weekUsd"] == -5011 and t["yearUsd"] == 18736
    assert w["reserves"]["gold"]["usd"] == 105800
    assert w["credit_yoy"] == 18.2 and w["deposits_yoy"] == 16.7 and w["m3_yoy"] == 16.0 and w["banksAsOf"] == "2026-10-15"
    pts = S.wss_reserve_points(w)
    assert pts[D(2026, 10, 16)] == 721.016 and pts[D(2025, 10, 17)] == 702.28 and pts[D(2026, 3, 27)] == 691.107
    assert S.parse_wss_extract("<html>nothing</html>") is None


def test_number_and_date_helpers():
    assert S.num("1,234.5") == 1234.5 and S.num("-") is None and S.num("") is None and S.num(None) is None and S.num("abc") is None
    assert S.month_of("September") == 9 and S.month_of("Sept") == 9 and S.month_of(3) == 3 and S.month_of("x") is None and S.month_of(13) is None
    assert S.month_end(2024, 2) == D(2024, 2, 29) and S.month_end(2026, 12) == D(2026, 12, 31)


def test_repo_series_is_a_step_line():
    ds = [S.Decision(D(2025, 2, 7), 6.25, -25, "x"), S.Decision(D(2025, 4, 9), 6.0, -25, "x"), S.Decision(D(2025, 6, 6), 5.5, -50, "x")]
    s = S.repo_series(ds, D(2025, 8, 15))
    assert s[D(2025, 2, 28)] == 6.25 and s[D(2025, 4, 30)] == 6.0 and s[D(2025, 5, 31)] == 6.0 and s[D(2025, 6, 30)] == 5.5 and s[D(2025, 8, 15)] == 5.5
    assert D(2025, 1, 31) not in s and S.repo_series([], D(2025, 1, 1)) == {}


def test_repo_decision_history_is_consistent():
    ds = macro.load_decisions()
    prev = 6.75                                                                    # the rate before the first listed change (April 2016)
    for d in ds:
        assert round(prev + d.change_bp / 100, 2) == d.rate, d
        prev = d.rate
    assert ds[-1].rate == 5.5 and ds[-1].date == D(2026, 10, 7) and len({d.date for d in ds}) == len(ds)


def test_target_watch_follows_the_framework_rule():
    q = lambda vals: {S.month_end(2026 - (i // 12), 12 - i % 12): v for i, v in enumerate(vals)}   # noqa: E731
    calm = macro.target_watch({S.month_end(2026, m): 5.0 for m in range(1, 10)})
    assert calm["streak"] == 0 and calm["target"] == 4.0 and calm["band"] == [2.0, 6.0]
    hot = macro.target_watch({S.month_end(2026, m): 6.5 for m in range(1, 10)})
    assert hot["streak"] == 3 and hot["side"] == "above"
    low = macro.target_watch({S.month_end(2026, m): 1.5 for m in range(4, 10)})
    assert low["streak"] == 2 and low["side"] == "below"
    mixed = macro.target_watch({**{S.month_end(2026, m): 6.5 for m in range(1, 7)}, **{S.month_end(2026, m): 1.0 for m in range(7, 10)}})
    assert mixed["streak"] == 1 and mixed["side"] == "below"
    assert q([1, 2])  # helper kept simple


def test_checks_drop_bad_points_without_changing_good_ones():
    s, issues = macro.checked({"cpi": {D(2026, 1, 31): 5.0, D(2026, 2, 28): 400.0, D(2099, 1, 31): 5.0}, "repo": {D(2026, 1, 31): 5.5}}, D(2026, 10, 1))
    assert s["cpi"] == {D(2026, 1, 31): 5.0} and s["repo"] == {D(2026, 1, 31): 5.5} and len(issues) == 2


def test_period_labels_and_card_shape():
    assert macro.period_label(D(2026, 6, 30), "Q") == "Q1 FY27 (Apr-Jun 2026)" and macro.period_label(D(2026, 3, 31), "Q") == "Q4 FY26 (Jan-Mar 2026)"
    assert macro.period_label(D(2026, 9, 30), "M") == "Sep 2026" and macro.period_label(D(2026, 10, 3), "W") == "3 Oct 2026"
    c = macro.card("cpi", {D(2025, 9, 30): 1.41, D(2026, 8, 31): 4.83, D(2026, 9, 30): 5.54})
    assert c["value"] == 5.54 and c["change"] == 0.71 and c["prevPeriod"] == "Aug 2026" and c["yearAgo"] == 1.41 and c["changeUnit"] == "pp"
    assert macro.card("cpi", {}) is None


def test_derive_splices_bases_and_marks_the_breaks():
    raw = {"cpi": {D(2024, 12, 31): 5.2, D(2026, 1, 31): 2.75}, "cpi_idx": {D(2025, 1, 31): 105.0}, "cpi_idx_back": {D(2024, 1, 31): 100.0}}
    out, breaks, notes = macro.derive(raw, macro.load_decisions(), D(2026, 10, 23))
    assert out["cpi"][D(2025, 1, 31)] == 5.0 and out["cpi"][D(2024, 12, 31)] == 5.2 and out["cpi"][D(2026, 1, 31)] == 2.75
    assert breaks["cpi"] and "base 2024" in notes["cpi"]
    assert out["real_rate"][D(2025, 1, 31)] == round(out["repo"][D(2025, 1, 31)] - 5.0, 2)


# ---- the nightly job, end to end, against a fake of both sites serving the recorded answers
def fake_sites():
    cpi = {("Current", 2026, 9): "cpi_current_2026_09.json", ("Current", 2025, 9): "cpi_current_2025_09.json"}

    def handler(req: httpx.Request) -> httpx.Response:
        u, q = req.url, dict(req.url.params)
        if u.host == "api.mospi.gov.in":
            p = u.path
            if p == "/api/cpi/getCPIData":
                f = cpi.get((q.get("series_code"), int(q.get("year", 0)), int(q.get("month_code", 9)))) if q.get("series_code") == "Current" else "cpi_back_2024.json"
                return httpx.Response(200, content=(FX / f).read_bytes() if f else b'{"data": [], "meta_data": {"totalPages": 1}}')
            if p == "/api/wpi/getWpiRecords":
                f = {("2022-23", "2026"): "wpi22_2026.json", ("2022-23", "2025"): "wpi22_2025.json"}.get((q["base_year"], q["year"]))
                if f and q["major_group_code"] == "1000000000":
                    return httpx.Response(200, content=(FX / f).read_bytes())
                return httpx.Response(200, content=b'{"data": [], "meta_data": {"totalPages": 1}}')
            if p == "/api/nas/getNASData":
                return httpx.Response(200, content=(FX / ("nas22_q.json" if q["base_year"] == "2022-23" else "nas11_q.json")).read_bytes())
            if p == "/api/iip/getIipData":
                return httpx.Response(200, content=(FX / "iip22_2026.json").read_bytes() if q["base_year"] == "2022-23" and q["year"] == "2026" else b'{"data": [], "meta_data": {"totalPages": 1}}')
            if p == "/api/plfs/getData":
                return httpx.Response(200, content=(FX / ("plfs_2026_p1.json" if q["year"] == "2026" and q.get("page") == "1" else "plfs_2026_p2.json" if q["year"] == "2026" else "plfs_2026_p1.json")).read_bytes()
                                      if q["year"] == "2026" else b'{"data": [], "meta_data": {"totalPages": 1}}')
            if p == "/api/rbi/getRbiRecords":
                return httpx.Response(200, content=(FX / ("rbi47_p1.json" if q["sub_indicator_code"] == "47" else "rbi33_p1.json")).read_bytes())
            return httpx.Response(404)
        if u.path.endswith("pressreleases_rss.xml"):
            return httpx.Response(200, text=text("rbi_press_rss.xml"))
        if "prid=63855" in str(u):
            return httpx.Response(200, text=text("rbi_wss_extract.html"))
        if u.host.endswith("rbi.org.in"):
            return httpx.Response(200, text=text("rbi_home.html"))
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
async def mstore():
    import os
    from finlit.config import Settings
    from finlit.store import Store
    s = Settings(finedge_api_key="t", finedge_mode="fixtures", database_url=os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test"),
                 redis_url=os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"))
    try:
        st = await Store.connect(s)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with st.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS macro_points, macro_meta, schema_migrations CASCADE")
    await st.redis.flushdb()
    await st.migrate()
    yield st
    await st.close()


@pytest.mark.integration
async def test_refresh_macro_and_serve(mstore, monkeypatch):
    import httpx as hx
    from finlit.api import create_app
    from finlit.config import Settings
    monkeypatch.setattr(macro, "PAUSE", 0)
    res = await macro.refresh(mstore, transport=fake_sites(), today=D(2026, 10, 23), full=True)
    assert res["steps"]["cpi"]["status"] == "ok" and res["steps"]["rbi_home"]["repo"] == 5.5 and res["steps"]["rbi_wss"]["asOf"] == "2026-10-16", res
    assert res["status"] in ("ok", "partial")
    s = Settings(finedge_api_key="t", finedge_mode="fixtures", database_url=mstore.settings.database_url if hasattr(mstore, "settings") else "x", redis_url="redis://localhost:6379/15")
    app = create_app(s, store=mstore)
    async with app.router.lifespan_context(app):
        async with hx.AsyncClient(transport=hx.ASGITransport(app=app), base_url="http://test") as api:
            r = await api.get("/api/macro")
            assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
            body = r.json()
            cards = {c["key"]: c for c in body["cards"]}
            assert cards["cpi"]["value"] == 5.54 and cards["wpi"]["value"] == 11.39 and cards["gdp"]["value"] == 7.82 and cards["repo"]["value"] == 5.5
            assert cards["fx_reserves"]["value"] == 721.016 and cards["fx_reserves"]["change"] == -5.011
            assert body["targetWatch"]["target"] == 4.0 and body["sources"] and "not investment advice" in body["disclaimer"]
            assert (await api.get("/api/macro", headers={"If-None-Match": r.headers["etag"]})).status_code == 304
            assert not [i for i in body["issues"] if "cpi" in i]


@pytest.mark.integration
async def test_a_failing_source_keeps_the_rest_and_the_last_good_data(mstore, monkeypatch):
    monkeypatch.setattr(macro, "PAUSE", 0)
    await macro.refresh(mstore, transport=fake_sites(), today=D(2026, 10, 23), full=True)

    res = await macro.refresh(mstore, transport=httpx.MockTransport(lambda r: httpx.Response(503)), today=D(2026, 10, 24))
    assert res["status"] == "partial" and {k for k, v in res["steps"].items() if v["status"] == "failed"} >= {"cpi", "wpi", "gdp", "iip", "plfs", "rbi_home", "rbi_wss"}
    async with mstore.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'cpi'") > 12            # nothing deleted
        payload = await macro.get_meta(conn, "payload")
    assert {c["key"]: c for c in payload["cards"]}["cpi"]["value"] == 5.54


def test_a_misread_rbi_rates_panel_is_refused_before_it_is_saved():
    """A repo rate out of range, or one far from the last decision, must not become a fake rate decision; other out-of-range rates are dropped."""
    from datetime import date as _d
    from finlit import macro
    from finlit import macro_sources as S
    decisions = [S.Decision(_d(2026, 6, 6), 5.5, -50, "x")]
    with pytest.raises(RuntimeError):
        macro.check_rbi_rates({"rates": {"repo": 55.0, "crr": 3.0}}, decisions)
    with pytest.raises(RuntimeError):
        macro.check_rbi_rates({"rates": {"repo": 9.5}}, decisions)   # 400 bp jump
    ok = macro.check_rbi_rates({"rates": {"repo": 5.25, "crr": 300.0, "slr": 18.0}, "fx": {}}, decisions)
    assert ok["rates"] == {"repo": 5.25, "slr": 18.0}
