"""Fund facts from AMFI (finlit/disclosure.py): parsing, the nightly job's checks, and what the fund and ETF pages receive.

Fixtures in tests/fixtures/disclosure are real AMFI answers recorded on 2026-10-22, cut to the 13 schemes of tests/fixtures/mf/navall_sample.txt:
  master_sample.csv   portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0 (the scheme master)
  ter_months.json     amfiindia.com/api/populate-ter-month?year=2026-2027
  ter_sample.xlsx     amfiindia.com/api/populate-te-rdata-revised?...&excel=true (the TER workbook), 20-22 October rows of those schemes
  aum_sample.json     amfiindia.com/api/average-aum-schemewise?strType=Typewise&fyId=1&periodId=1 (July - September 2026)
"""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from finlit import disclosure as d
from finlit import mf
from test_mf import amfi_client, needs_db, store  # noqa: F401  (fixtures)

FX = Path(__file__).parent / "fixtures" / "disclosure"
MASTER = (FX / "master_sample.csv").read_text(encoding="utf-8")
MONTHS = (FX / "ter_months.json").read_bytes()
TER = (FX / "ter_sample.xlsx").read_bytes()
AUM = json.loads((FX / "aum_sample.json").read_text(encoding="utf-8"))
SMALL = {"min_rows": 10, "min_schemes": 5, "min_codes": 5}       # the fixtures are a 13-scheme slice of the industry files
TODAY = date(2026, 10, 22)
LARGE_CAP, CHILDREN_DG, CHILDREN_RG, CHILDREN_DI, CHILDREN_RI = 120465, 135762, 135759, 135765, 135760
ETF_ISIN, GILT, INTERVAL = "INF209KB18T9", 120607, 146839


# ------------------------------------------------------------------------------------------------------------- parsing

def test_scheme_master():
    rows = d.parse_master(MASTER)
    assert len(rows) == 13
    lc = rows[LARGE_CAP]
    assert lc.base_name == "Axis Large Cap Fund" and lc.launch == date(2009, 11, 11)
    assert lc.minimum == "Rs. 5000 in multiples of Rs. 1 thereafter"                           # wording kept as AMFI wrote it
    assert rows[GILT].minimum is None                                                          # AMFI says "5": not a real minimum, not shown
    assert rows[INTERVAL].minimum == "₹20,00,00,000"                                           # a plain amount, Indian grouping
    assert {rows[c].base_name for c in (CHILDREN_DG, CHILDREN_RG, CHILDREN_DI, CHILDREN_RI)} == {"Axis Children's Fund"}
    assert d.parse_master("Code,Name\n1,x\n") == {}                                            # a changed header is refused, not misread


def test_ter_workbook_keeps_each_schemes_latest_day_and_reads_zero_as_no_plan(tmp_path):
    p = tmp_path / "ter.xlsx"
    p.write_bytes(TER)
    rows = d.parse_ter_xlsx(str(p))
    lc = rows[d.name_key("Axis Large Cap Fund")]
    assert (lc.regular, lc.direct, lc.day) == (1.76, 0.92, date(2026, 10, 21))
    assert rows[d.name_key("BANK OF INDIA MID CAP TAX FUND SERIES 1")].day == date(2026, 10, 22)
    etf = rows[d.name_key("Aditya Birla Sun Life CRISIL Liquid Overnight ETF")]
    assert etf.regular is None and etf.direct == 0.44                                          # AMFI writes 0 for the plan the ETF does not have
    assert d.name_key("AXIS CHILDRENS FUND") == d.name_key("Axis Children's Fund")


def test_average_aum_and_its_period():
    label, end, codes = d.parse_aum(AUM)
    assert label == "July - September 2026" and end == date(2026, 9, 30)
    assert codes[LARGE_CAP] == 1200075.27 and len(codes) == 10
    assert d.parse_aum({"data": "nonsense"}) == (None, None, {})
    assert d.period_end("October - December 2025") == date(2025, 12, 31) and d.period_end("January - March 2024") == date(2024, 3, 31)


def test_formats():
    assert d.inr(147064) == "1,47,064" and d.inr(999) == "999" and d.inr(10000000) == "1,00,00,000"
    assert d.aum_text(14706447.0) == "₹1,47,064 crore" and d.aum_text(4530) == "₹45.30 crore" and d.aum_text(82.5) == "₹82.50 lakh"
    assert d.min_text("Rs. 5000/-") == "₹5,000" and d.min_text("1000") == "₹1,000" and d.min_text("NA") is None and d.min_text("10") is None
    assert d.fiscal_year(date(2026, 3, 31)) == "2025-2026" and d.fiscal_year(date(2026, 4, 1)) == "2026-2027"


# ------------------------------------------------------------------------------------------------------------- the nightly job

def amfi_facts_transport(*, master=MASTER, ter=TER, aum=AUM, ter_status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if calls is not None:
            calls.append(url)
        if "DownloadSchemeData_Po" in url:
            return httpx.Response(200, content=master.encode("utf-8"))
        if "populate-ter-month" in url:
            return httpx.Response(200, content=MONTHS if request.url.params.get("year") == "2026-2027" else b"[]")
        if "populate-te-rdata-revised" in url:
            assert request.url.params["Month"] == "10-2026" and request.url.params["excel"] == "true"
            return httpx.Response(ter_status, content=ter)
        if "average-aum-schemewise" in url:
            fy, per = request.url.params["fyId"], request.url.params["periodId"]
            return httpx.Response(200, json=aum if (fy, per) == ("1", "1") else {"selectedPeriod": "April - June 2026", "data": []})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
async def funds(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(d, "RETRY_PAUSE", 0)
    monkeypatch.setattr(mf, "_retry", _no_wait_retry)
    async with store.pool.acquire() as conn:
        await conn.execute("TRUNCATE mf_facts, mf_ter")
    async with amfi_client() as c:
        assert (await mf.refresh(store, None, client=c))["status"] == "ok"
    return store


async def _no_wait_retry(fn, tries: int = 3, base: float = 3.0):
    return await fn()                                                                          # one attempt: the recorded answers do not change


async def run(store, **kw):  # noqa: F811
    async with httpx.AsyncClient(transport=amfi_facts_transport(**kw)) as c:
        return await d.refresh(store, client=c, today=TODAY, **SMALL)


@needs_db
async def test_the_job_loads_every_fact_and_the_pages_read_them(funds):
    res = await run(funds)
    assert res["status"] == "ok", res
    assert res["ter"]["month"] == "10-2026" and res["aum"]["period"] == "July - September 2026"

    f = await d.get_facts(funds.pool, LARGE_CAP)
    assert f["terRegular"] == {"value": "1.76% a year", "asOf": "2026-10-21", "source": d.SRC_TER}
    assert f["terDirect"]["value"] == "0.92% a year"
    assert f["aum"]["value"] == "₹12,001 crore" and f["aum"]["asOf"] == "2026-09-30" and "July - September 2026" in f["aum"]["note"]
    assert f["launchDate"]["value"] == "2009-11-11"
    assert "out of date" in f["minInvestment"]["unavailable"]                                   # AMFI's minimum is stale for some schemes: not shown
    for k in ("exitLoad", "benchmark", "riskometer", "managers"):
        assert f[k]["unavailable"], k                                                          # no verified source: a reason, never a guess


@needs_db
async def test_fund_size_adds_every_plan_and_option_of_the_scheme(funds):
    await run(funds)
    _, _, codes = d.parse_aum(AUM)
    total = sum(codes[c] for c in (CHILDREN_DG, CHILDREN_RG, CHILDREN_DI, CHILDREN_RI))
    for c in (CHILDREN_DG, CHILDREN_RG, CHILDREN_DI, CHILDREN_RI):                              # the same figure on each plan's page
        assert (await d.get_facts(funds.pool, c))["aum"]["value"] == d.aum_text(total) == "₹764 crore"


@needs_db
async def test_missing_figures_say_why(funds):
    await run(funds)
    interval = await d.get_facts(funds.pool, INTERVAL)                                         # stopped interval plan: in no current AMFI file
    assert "quarterly AUM" in interval["aum"]["unavailable"] and "TER" in interval["terRegular"]["unavailable"]
    async with funds.pool.acquire() as conn:                                                   # stored for later checking, never shown
        assert await conn.fetchval("SELECT min_text FROM mf_facts WHERE code = $1", LARGE_CAP) == "Rs. 5000 in multiples of Rs. 1 thereafter"
        assert await conn.fetchval("SELECT min_text FROM mf_facts WHERE code = $1", GILT) is None
    assert await d.get_facts(funds.pool, 999999) is None


@needs_db
async def test_an_etf_is_read_by_isin_with_its_one_plan(funds):
    await run(funds)
    f = await d.get_facts(funds.pool, ETF_ISIN)
    assert f["ter"]["value"] == "0.44% a year"                                                 # filed under Direct by AMFI: still found
    assert f["aum"]["value"] == "₹40.56 crore" and f["minInvestment"]["value"].startswith("1 unit") and f["exitLoad"]["value"].startswith("None")
    assert "terRegular" not in f and f["trackingError"]["unavailable"]
    assert await d.get_facts(funds.pool, "INF000000000") is None


@needs_db
async def test_a_short_answer_is_refused_and_stored_figures_stay(funds):
    await run(funds)
    before = await d.get_facts(funds.pool, LARGE_CAP)
    res = await run(funds, master="AMC,Code\n", aum={"selectedPeriod": "July - September 2026", "data": []}, ter_status=500)
    assert res["status"] == "failed" and res["master"]["status"] == "refused" and res["aum"]["status"] == "refused" and res["ter"]["status"] == "failed"
    assert await d.get_facts(funds.pool, LARGE_CAP) == before
    status = await mf.last_run_age_hours(funds, "refresh-facts")
    assert status[1] == "failed"                                                               # readable at /api/mf/status


@needs_db
async def test_one_failing_step_leaves_the_others_working(funds):
    res = await run(funds, ter_status=503)
    assert res["status"] == "partial" and res["master"]["status"] == "ok" and res["aum"]["status"] == "ok" and res["ter"]["status"] == "failed"
    f = await d.get_facts(funds.pool, LARGE_CAP)
    assert f["aum"]["value"] and "TER" in f["terRegular"]["unavailable"]


@needs_db
async def test_a_new_quarter_replaces_the_old_one_whole(funds):
    await run(funds)
    later = json.loads(json.dumps(AUM))
    later["selectedPeriod"] = "October - December 2026"
    for house in later["data"]:
        house["schemes"] = [s for s in house["schemes"] if s["AMFI_Code"] != LARGE_CAP]          # the scheme is missing from the new quarter
    await run(funds, aum=later)
    lc = await d.get_facts(funds.pool, LARGE_CAP)
    assert "unavailable" in lc["aum"]                                                          # no figure, rather than last quarter's
    assert (await d.get_facts(funds.pool, CHILDREN_DG))["aum"]["asOf"] == "2026-12-31"


@needs_db
async def test_top_by_aum_gives_one_growth_option_per_scheme_largest_first(funds):
    await run(funds)
    async with funds.pool.acquire() as conn:
        await conn.execute("UPDATE mf_schemes SET r5y = 10 WHERE option_class = 'Growth' AND active")   # the slice has no 5-year figures yet
    top = await d.top_by_aum(funds.pool, 10)
    assert top[0] == 120389                                                                    # Axis Liquid Fund, ₹48,669 crore
    assert top[1] == LARGE_CAP
    assert CHILDREN_DG in top and CHILDREN_RG not in top                                       # one entry for the scheme: its Direct Growth option
    assert len(top) == len(set(top))


@needs_db
async def test_the_fund_page_route_serves_the_facts(funds):
    await run(funds)
    app = FastAPI()
    app.include_router(mf.router)
    app.state.store, app.state.settings = funds, None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        body = (await c.get(f"/api/mf/{LARGE_CAP}/facts")).json()
    assert body["facts"]["terDirect"]["value"] == "0.92% a year" and body["facts"]["aum"]["note"]
    assert body["facts"]["category"]["value"] == "Equity Schemes - Large Cap Fund"
