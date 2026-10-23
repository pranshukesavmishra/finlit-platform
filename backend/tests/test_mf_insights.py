"""Mutual fund industry insights (finlit/mf_insights.py): parsing AMFI's monthly category report, the daily job, and what the page receives.

Fixtures in tests/fixtures/mf_industry are real AMFI files downloaded on 2026-10-23, stored gzip-compressed (the bytes are AMFI's, unchanged):
  amapr2019repo.xls.gz   April 2019, the first category-wise report: .xlsx under an .xls name, 9 columns
  amapr2024repo.xls.gz   April 2024: .xlsx, 11 columns (segregated portfolios added)
  amaug2026repo.xls.gz   August 2026: a real .xls (BIFF8), the new group headings (Debt / Equity / ... / Index Funds / ETFs / Overseas FoF)
  amsep2026repo.xls.gz   September 2026: as August, and a part C row with no heading
  listing_sample.html    amfiindia.com/research-information/amfi-monthly, cut to one link tag and eight of its embedded report records
"""

import gzip
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finlit import mf, mf_insights as mi
from finlit.config import Settings
from finlit.store import Store

FX = Path(__file__).parent / "fixtures" / "mf_industry"
FILES = {name: gzip.decompress((FX / f"{name}.gz").read_bytes()) for name in ("amapr2019repo.xls", "amapr2024repo.xls", "amaug2026repo.xls", "amsep2026repo.xls")}
LISTING = (FX / "listing_sample.html").read_text(encoding="utf-8")
APR19, APR24, AUG26, SEP26 = date(2019, 4, 1), date(2024, 4, 1), date(2026, 8, 1), date(2026, 9, 1)
TODAY = date(2026, 10, 23)


def groups(rep):
    out = {}
    for r in rep.rows:
        out[r.grp] = out.get(r.grp, 0.0) + r.values["aum"]
    return out


# ------------------------------------------------------------------------------------------------------------- parsing

def test_september_2026_new_layout_biff():
    rep = mi.parse_report(FILES["amsep2026repo.xls"], SEP26)
    t = rep.total
    assert round(t["aum"], 2) == 8264116.63 and t["folios"] == 286231680 and t["schemes"] == 1995
    assert round(t["net_flow"], 2) == -133375.57 and round(t["mobilized"], 2) == 1525156.49 and round(t["aaum"], 2) == 8709182.16
    g = groups(rep)
    assert round(g["equity"] / 1e5, 2) == 37.58                       # open-ended equity + close-ended ELSS: the "Equity AUM" card
    assert round(sum(v for k, v in g.items() if k != "fof_domestic"), 2) == round(t["aum"], 2)
    by = {r.category: r for r in rep.rows}
    assert by["Mid Cap Fund"].grp == "equity" and by["Mid Cap Fund"].values["folios"] == 26768077
    assert by["Life Cycle Fund with Maturity of 5 Years"].grp == "solution"
    assert by["Gold ETF"].grp == "other" and by["Arbitrage Fund"].grp == "hybrid" and by["Liquid Fund"].grp == "debt"
    interval = [r for r in rep.rows if r.section == "interval"]
    assert [(r.category, r.heading, r.grp) for r in interval] == [("Income/Debt Oriented Schemes", "Income/Debt Oriented Schemes", "debt")]
    fof = next(r for r in rep.rows if r.grp == "fof_domestic")
    assert fof.values["schemes"] == 158 and fof.section == "fof_domestic"     # AMFI writes "# 158"; it is left out of the totals
    assert len({r.key for r in rep.rows}) == len(rep.rows)                    # "Sectoral Fund" is both a debt and an equity category: keys differ
    assert all(not r.heading.endswith("*") for r in rep.rows)                 # "Solution Oriented Schemes **" loses its footnote marks


def test_august_2026_and_the_first_category_report():
    aug = mi.parse_report(FILES["amaug2026repo.xls"], AUG26)
    assert aug.total["folios"] == 283519085 and len(aug.rows) == 62
    apr = mi.parse_report(FILES["amapr2019repo.xls"], APR19)                  # 9 columns, numbered rows, AUM header "AUM as on 30-Apr-2019"
    assert apr.total["folios"] == 82736339 and round(apr.total["aum"], 2) == 2478756.93 and apr.released == date(2019, 5, 9)
    assert {r.grp for r in apr.rows} == {"debt", "equity", "hybrid", "solution", "other", "fof_domestic"}
    other_close = [r for r in apr.rows if r.section == "close" and r.category == "Other Schemes"]
    assert other_close and other_close[0].grp == "other"                      # a heading that carries figures itself is a category too


def test_april_2024_eleven_columns():
    rep = mi.parse_report(FILES["amapr2024repo.xls"], APR24)
    assert round(rep.total["aum"], 2) == 5725897.98 and rep.total["folios"] == 181468286 and rep.released == date(2024, 5, 9)
    assert len([r for r in rep.rows if r.section != "fof_domestic"]) == 49


def test_wrong_month_and_not_a_workbook_are_refused():
    with pytest.raises(mi.ReportRejected, match="names Sep 2026, not Aug 2026"):
        mi.parse_report(FILES["amsep2026repo.xls"], AUG26)
    with pytest.raises(mi.ReportRejected, match="not an Excel workbook"):
        mi.parse_report(b"<html><body>Page not found</body></html>", SEP26)
    with pytest.raises(mi.ReportRejected, match="not a readable workbook"):
        mi.parse_report(b"PK\x03\x04 broken", SEP26)


READ_ROWS = mi.read_rows


def _tampered(monkeypatch, name, change):
    rows = READ_ROWS(FILES[name])
    change(rows)
    monkeypatch.setattr(mi, "read_rows", lambda data: rows)


def _row(rows, label):
    return next(r for r in rows if any(isinstance(c, str) and c.strip() == label for c in r))


def test_a_report_whose_categories_do_not_add_up_is_refused(monkeypatch):
    def bump_mid_cap(rows):
        r = _row(rows, "Mid Cap Fund")
        r[7] = r[7] + 1000.0                                                  # net assets of one category, 1,000 crore more than AMFI printed
    _tampered(monkeypatch, "amsep2026repo.xls", bump_mid_cap)
    with pytest.raises(mi.ReportRejected, match="add up to"):
        mi.parse_report(FILES["amsep2026repo.xls"], SEP26)


def test_a_report_with_a_missing_column_or_an_unknown_heading_is_refused(monkeypatch):
    def drop_average(rows):
        h = next(r for r in rows if mi._has_header(r))
        h[8] = "Something else"
    _tampered(monkeypatch, "amapr2024repo.xls", drop_average)
    with pytest.raises(mi.ReportRejected, match=r"lacks the column\(s\) aaum"):
        mi.parse_report(FILES["amapr2024repo.xls"], APR24)

    def rename_heading(rows):
        r = _row(rows, "Hybrid Schemes")
        r[1] = "Balanced Schemes"
    _tampered(monkeypatch, "amapr2024repo.xls", rename_heading)
    with pytest.raises(mi.ReportRejected, match="unknown group heading 'Balanced Schemes'"):
        mi.parse_report(FILES["amapr2024repo.xls"], APR24)


def test_a_wrong_subtotal_is_refused_too(monkeypatch):
    def break_subtotal(rows):
        r = next(r for r in rows if isinstance(r[1], str) and r[1].startswith("Sub Total - II"))
        r[3] = r[3] + 1                                                       # one folio more than its categories
    _tampered(monkeypatch, "amapr2024repo.xls", break_subtotal)
    with pytest.raises(mi.ReportRejected, match="Sub Total - II"):
        mi.parse_report(FILES["amapr2024repo.xls"], APR24)


def test_listing_links_prefer_the_revised_file():
    links = mi.listing_links(LISTING)
    assert links[date(2021, 12, 1)] == "https://portal.amfiindia.com/spages/amdec2021reporevised.xls"
    assert links[date(2022, 1, 1)] == "https://portal.amfiindia.com/spages/amjan2022reporevised.xls"
    assert links[SEP26] == "https://portal.amfiindia.com/spages/amsep2026repo.xls" == mi.file_url(SEP26)
    assert date(2008, 4, 1) not in links                                      # 2008 reports are web pages, not workbooks


def test_months():
    assert mi.add_months(date(2026, 1, 1), -1) == date(2025, 12, 1) and mi.add_months(date(2025, 12, 1), 1) == date(2026, 1, 1)
    assert mi.month_end(date(2024, 2, 1)) == date(2024, 2, 29) and mi.parse_month("2019-04") == APR19
    with pytest.raises(ValueError):
        mi.parse_month("April")
    assert mi.months_named(["Monthly Report for the month of September 2026", "AUM as on 30-Apr-2019", "as on April 30, 2024"]) == {SEP26, APR19, APR24}
    assert mi.file_url(date(2021, 12, 1), revised=True).endswith("/amdec2021reporevised.xls")


def test_plan_asks_only_for_what_is_new_or_may_have_changed():
    now = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
    ok = lambda m, url=None: {"status": "ok", "source_url": url or mi.file_url(m), "etag": f"e{m.month}", "fetched_at": now}   # noqa: E731
    known = {date(2026, 6, 1): ok(date(2026, 6, 1)), date(2026, 7, 1): ok(date(2026, 7, 1)), AUG26: ok(AUG26),
             date(2026, 5, 1): {"status": "missing", "source_url": None, "etag": None, "fetched_at": now - timedelta(days=2)},
             date(2026, 4, 1): {"status": "refused", "source_url": None, "etag": None, "fetched_at": now - timedelta(days=9)}}
    links = {date(2026, 7, 1): "https://portal.amfiindia.com/spages/amjul2026reporevised.xls"}
    got = mi.plan(known, links, date(2026, 3, 1), SEP26, now)
    assert got == [(date(2026, 3, 1), None, None),                             # never tried
                   (date(2026, 4, 1), None, None),                             # refused 9 days ago: asked again
                   (date(2026, 7, 1), links[date(2026, 7, 1)], None),          # AMFI now links a revised file
                   (AUG26, mi.file_url(AUG26), "e8"),                          # the newest stored month, with its ETag
                   (SEP26, None, None)]                                        # May (missing 2 days ago, not recent) and June are left alone


# ------------------------------------------------------------------------------------------------------------- the daily job (Postgres + Redis)

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test_mf")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/14")
needs_db = pytest.mark.integration


@pytest.fixture
async def store():
    settings = Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)
    try:
        s = await Store.connect(settings, migrate=True)
        await s.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    async with s.pool.acquire() as conn:
        await conn.execute("TRUNCATE mf_industry, mf_industry_months")
    async for k in s.redis.scan_iter("mfi:*"):
        await s.redis.delete(k)
    yield s
    await s.close()


class Amfi:
    """Stands in for AMFI: the listing page and the report files, with ETags; records every request."""

    def __init__(self, files=None, listing=LISTING, down=()):
        self.files = dict(files or {"amaug2026repo.xls": FILES["amaug2026repo.xls"], "amsep2026repo.xls": FILES["amsep2026repo.xls"]})
        self.listing, self.down, self.calls = listing, set(down), []

    def etag(self, name):
        return '"' + str(abs(hash(self.files[name])) % 10 ** 12) + ':0"'

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, request.headers.get("if-none-match")))
        if request.url.path == "/research-information/amfi-monthly":
            return httpx.Response(200, text=self.listing) if self.listing is not None else httpx.Response(503)
        name = request.url.path.rsplit("/", 1)[-1]
        if name in self.down:
            raise httpx.ConnectError("connection reset")
        if name not in self.files:
            return httpx.Response(404, text="<html>The resource cannot be found.</html>")
        if request.headers.get("if-none-match") == self.etag(name):
            return httpx.Response(304)
        return httpx.Response(200, content=self.files[name], headers={"etag": self.etag(name)})

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def asked(self, name):
        return [h for p, h in self.calls if p.endswith("/" + name)]


async def _no_wait_retry(fn, tries: int = 3, base: float = 3.0):
    return await fn()


async def run(store, amfi, since=date(2026, 7, 1), today=TODAY):
    async with amfi.client() as c:
        return await mi.refresh(store, since=since, client=c, today=today, pause=0)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(mf, "_retry", _no_wait_retry)


@needs_db
async def test_backfill_stores_months_and_a_second_run_only_checks_the_newest(store):
    amfi = Amfi()
    res = await run(store, amfi)
    assert res["status"] == "ok", res
    assert res["stored"] == ["2026-08", "2026-09"] and res["missing"] == ["2026-07"] and res["latest"] == "2026-09" and res["months"] == 2
    assert amfi.asked("amjul2026repo.xls") and amfi.asked("amjul2026reporevised.xls")      # not linked: the usual name, then the revised one
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_industry WHERE month = $1", SEP26) == 62
        row = await conn.fetchrow("SELECT status, folios, etag, source_url FROM mf_industry_months WHERE month = $1", SEP26)
        assert row["status"] == "ok" and row["folios"] == 286231680 and row["etag"] == amfi.etag("amsep2026repo.xls")
        assert (await conn.fetchrow("SELECT status FROM mf_industry_months WHERE month = '2026-07-01'"))["status"] == "missing"

    amfi.calls.clear()
    again = await run(store, amfi)
    assert again["stored"] == [] and again["unchanged"] == ["2026-09"] and again["status"] == "ok"
    assert amfi.asked("amsep2026repo.xls") == [amfi.etag("amsep2026repo.xls")]           # one conditional request, answered 304
    assert not amfi.asked("amaug2026repo.xls") and not amfi.asked("amjul2026repo.xls")      # August is done; July was tried today and is older


@needs_db
async def test_a_failed_month_is_picked_up_by_the_next_run(store):
    amfi = Amfi(down={"amsep2026repo.xls"})
    first = await run(store, amfi, since=AUG26)
    assert first["status"] == "partial" and first["stored"] == ["2026-08"] and "2026-09" in first["failed"]
    amfi.down.clear(); amfi.calls.clear()
    second = await run(store, amfi, since=AUG26)
    assert second["stored"] == ["2026-09"] and second["months"] == 2
    assert amfi.asked("amaug2026repo.xls") == [amfi.etag("amaug2026repo.xls")]           # August was the newest stored: a 304 check, no reload


@needs_db
async def test_a_republished_newest_month_replaces_it_and_a_bad_one_is_refused_keeping_the_figures(store):
    amfi = Amfi()
    await run(store, amfi, since=AUG26)
    amfi.files["amsep2026repo.xls"] = FILES["amsep2026repo.xls"] + b""                    # same bytes, new ETag: nothing is rewritten
    amfi.etag = lambda name, _old=amfi.etag: _old(name) if name != "amsep2026repo.xls" else '"republished:0"'
    same = await run(store, amfi, since=AUG26)
    assert same["unchanged"] == ["2026-09"] and same["stored"] == []

    amfi.files["amsep2026repo.xls"] = FILES["amaug2026repo.xls"]                          # a wrong file under September's name
    amfi.etag = lambda name, _old=amfi.etag: '"wrong:0"' if name == "amsep2026repo.xls" else _old(name)
    bad = await run(store, amfi, since=AUG26)
    assert bad["status"] == "failed" and "names Aug 2026, not Sep 2026" in bad["refused"]["2026-09"] and "kept" in bad["refused"]["2026-09"]
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, folios FROM mf_industry_months WHERE month = $1", SEP26)
    assert row["status"] == "ok" and row["folios"] == 286231680                          # September's figures are untouched


@needs_db
async def test_without_the_listing_page_the_usual_file_names_are_used(store):
    amfi = Amfi(listing=None)
    res = await run(store, amfi, since=SEP26)
    assert res["stored"] == ["2026-09"] and res["listing"].startswith("unavailable")


# ------------------------------------------------------------------------------------------------------------- the API

@pytest.fixture
async def api(store):
    app = FastAPI()
    app.include_router(mi.router)            # the order api.py uses: before mf's /api/mf/{code}
    app.include_router(mf.router)
    app.state.store = store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def test_the_site_registers_insights_before_the_scheme_page():
    from finlit.api import create_app
    app = create_app(Settings(finedge_api_key="test", finedge_mode="fixtures"))

    def flat(routes):                        # this FastAPI keeps each included router whole, behind a wrapper with `original_router`
        for r in routes:
            inner = getattr(r, "original_router", None)
            yield from flat(inner.routes) if inner is not None else [getattr(r, "path", "")]
    paths = list(flat(app.routes))
    assert paths.index("/api/mf/insights") < paths.index("/api/mf/{code}")


@needs_db
async def test_the_page_says_plainly_when_nothing_is_loaded(api):
    r = await api.get("/api/mf/insights")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "empty" and "not been loaded" in d["reason"] and d["source"] == "AMFI Monthly Category Report"
    assert "kpis" not in d                                                                # no figure is made up


@needs_db
async def test_insights_shape_kpis_and_cache(api, store):
    await run(store, Amfi(), since=AUG26)
    r = await api.get("/api/mf/insights")
    assert r.status_code == 200 and r.headers["etag"]
    d = r.json()
    assert d["status"] == "ok" and d["month"] == "2026-09" and d["asOf"] == "2026-09-30" and d["prevMonth"] == "2026-08"
    assert d["source"] == "AMFI Monthly Category Report" and d["sourceUrl"].endswith("/amsep2026repo.xls") and "never advice" in d["disclaimer"]
    k = d["kpis"]
    assert k["aum"]["value"] == 8264116.63 and k["aum"]["prev"] == 8707887.74 and k["aum"]["change"] == -443771.11 and k["aum"]["changePct"] == -5.1
    assert k["folios"]["value"] == 286231680 and k["folios"]["change"] == 2712595 and k["folios"]["changePct"] == 0.96
    assert k["netFlow"]["value"] == -133375.57 and k["netFlow"]["changePct"] is None and k["netFlow"]["mobilized"] == 1525156.49
    assert round(k["equityAum"]["value"] / 1e5, 2) == 37.58 and k["equityAum"]["prev"] is not None
    s = d["series"]
    assert s["t"] == ["2026-08-31", "2026-09-30"] and s["folios"] == [283519085, 286231680] and len(s["aum"]) == len(s["netFlow"]) == len(s["equityAum"]) == 2
    assert [g["key"] for g in d["groups"]] == ["equity", "debt", "hybrid", "solution", "other"]
    assert round(sum(g["share"] for g in d["groups"]), 1) == 100.0
    eq = d["groups"][0]
    assert eq["label"] == "Equity" and any(i["name"] == "Mid Cap Fund" for i in eq["items"]) and any(i["section"] == "close" for i in eq["items"])
    assert set(eq["items"][0]) >= {"name", "heading", "sectionLabel", "schemes", "folios", "netFlow", "aum", "aaum", "mobilized", "redemption"}
    assert d["fofDomestic"]["schemes"] == 158 and "out of its totals" in d["fofDomestic"]["note"] and d["gaps"] == []

    assert (await api.get("/api/mf/insights", headers={"If-None-Match": r.headers["etag"]})).status_code == 304


@needs_db
async def test_a_new_month_invalidates_the_cached_answer(api, store):
    amfi = Amfi(files={"amaug2026repo.xls": FILES["amaug2026repo.xls"]})
    await run(store, amfi, since=AUG26, today=date(2026, 9, 20))
    first = (await api.get("/api/mf/insights")).json()
    assert first["month"] == "2026-08" and first["prevMonth"] is None and first["kpis"]["aum"]["change"] is None
    amfi.files["amsep2026repo.xls"] = FILES["amsep2026repo.xls"]
    await run(store, amfi, since=AUG26)
    assert (await api.get("/api/mf/insights")).json()["month"] == "2026-09"
