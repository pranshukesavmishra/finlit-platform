"""Fund houses' own TER pages (finlit/disclosure_parsers/ter.py) and how the figures reach the fund page (portfolios.step_ter, disclosure.get_facts).

Fixtures in tests/fixtures/ter are real answers recorded on 2026-10-28, cut to a few schemes (and, for the workbooks, a few days):
  sbi_ter_sample.xlsx      sbimf.com/docs/default-source/ter_allschemes/current-year-ter.xlsx
  nippon_ter_sample.xlsx   mf.nipponindiaim.com/TotalExpenseRatio/TotalExpenseRatio2026-2027.xlsx (two sheets, percent signs in text cells)
  tata_ter_sample.xlsx     Tata's 'TotalExpenseRatioApril2026 to Mar2027' workbook (the original is .xls)
  sundaram_daily_ter.json  sundarammutual.com AjaxPro call Views_TER_V2.DailyTER (first 8 schemes)
  canara_ter_records.json  canararobeco.com/wp-json/ter/v1/records?from_date=2026-10-20&to_date=2026-10-27 (5 schemes)
  tata_page_snippet.html   the two download links of Tata's TER page
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from finlit import disclosure, portfolios
from finlit.disclosure_parsers import ter
from test_portfolios import FAM, store  # noqa: F401  (fixture)

FX = Path(__file__).parent / "fixtures" / "ter"
TODAY = date(2026, 10, 28)


def book(name: str) -> dict:
    st: dict = {}
    out = ter._read_book((FX / name).read_bytes(), ".xlsx", st)
    assert st.get("refused", 0) == 0
    return {r.name: r for r in out.values()}


def test_sbi_workbook_keeps_the_newest_row_per_scheme():
    b = book("sbi_ter_sample.xlsx")
    lm = b["SBI LARGE & MIDCAP FUND"]
    assert (lm.as_of, lm.regular, lm.direct) == (date(2026, 10, 27), 1.66, 0.87)          # not the 1 April row of 1.54 / 0.69
    assert b["SBI Nifty200 Value 30 ETF FOF"].direct == 0.08


def test_nippon_text_percents_across_two_sheets():
    b = book("nippon_ter_sample.xlsx")
    a = b["Nippon India Arbitrage Fund"]
    assert (a.as_of, a.regular, a.direct) == (date(2026, 10, 27), 2.04, 1.35)


def test_tata_workbook():
    t = book("tata_ter_sample.xlsx")["TATA BALANCED ADVANTAGE FUND"]
    assert (t.as_of, t.regular, t.direct) == (date(2026, 10, 12), 1.86, 0.68)


def test_sundaram_ajax_text_and_canara_json():
    items = ter.parse_sundaram("'" + (FX / "sundaram_daily_ter.json").read_text() + "'")
    assert items[0]["Group_Name"] == "Sundaram Aggressive Hybrid Fund" and ter.num(items[0]["RP_TOT_TER"]) == 2.15
    st: dict = {}
    recs = {r.name: r for r in ter.parse_canara(json.loads((FX / "canara_ter_records.json").read_text()), st)}
    c = recs["Canara Robeco Consumption Fund"]
    assert (c.as_of, c.regular, c.direct) == (date(2026, 10, 27), 2.17, 0.95) and len(recs) == 5


def test_tata_page_link_for_the_financial_year():
    page = (FX / "tata_page_snippet.html").read_text()
    assert ter.tata_file_url(page, TODAY).endswith("TotalExpenseRatioApril2026%20to%20Mar2027_14.xls")
    assert ter.tata_file_url(page, date(2027, 2, 1)).endswith("_14.xls")
    assert ter.tata_file_url(page, date(2024, 10, 1)) is None


@pytest.mark.parametrize("reg, direct, ok", [
    (1.5, 0.8, True), (1.5, None, True), (None, 0.4, True), (0.0, 0.0, True), (3.5, 1.0, True),
    (3.6, 1.0, False), (-0.1, None, False), (1.0, 1.2, False), (None, None, False), (1.0, 9.0, False)])
def test_junk_is_refused(reg, direct, ok):
    assert (ter.plans_ok(reg, direct) is None) is ok


def test_etf_with_zero_regular_keeps_its_direct_figure_and_real_junk_is_dropped():
    d = date(2026, 10, 27)
    st: dict = {}
    out = ter.settle({"a": ter.TerRec("A ETF", "a", d, 0.0, 0.07), "b": ter.TerRec("B Fund", "b", d, 1.0, 1.4), "c": ter.TerRec("C Fund", "c", d, 6.78, 1.0)}, st)
    assert set(out) == {"a"} and out["a"].regular is None and out["a"].direct == 0.07 and st["refused"] == 2


def test_dates_and_numbers():
    assert ter.to_date(46322.0) == date(2026, 10, 27) and ter.to_date("27/10/2026") == date(2026, 10, 27) and ter.to_date("28-10-2026") == date(2026, 10, 28)
    assert ter.num("1.29%") == 1.29 and ter.num("-") is None and ter.num("abc") is None and ter.num(None) is None


def test_a_sheet_without_the_sebi_header_is_not_read(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(["Scheme", "Something else"])
    wb.active.append(["X", 1])
    p = tmp_path / "x.xlsx"
    wb.save(p)
    with pytest.raises(Exception):
        ter.parse_workbook(str(p), {})


# ------------------------------------------------------------------------------------------------------------- database

def transport(sbi_fail: bool = False):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if str(req.url) == ter.URL_SBI:
            return httpx.Response(500) if sbi_fail else httpx.Response(200, content=(FX / "sbi_ter_sample.xlsx").read_bytes())
        return httpx.Response(404)
    return httpx.MockTransport(handler), calls


async def test_house_ter_reaches_the_fund_page_and_amfis_wins_when_present(store, monkeypatch):
    monkeypatch.setattr(ter, "SOURCES", {"sbi": ter.SOURCES["sbi"]})
    monkeypatch.setattr(ter, "PAUSE", 0)
    idx = portfolios.Index()
    idx.add(152655, "SBI MNC Fund - Direct Plan - Growth", "SBI Mutual Fund", FAM)
    idx.add(152657, "SBI MNC Fund - Regular Plan - Growth", "SBI Mutual Fund", FAM)
    tr, calls = transport()
    async with httpx.AsyncClient(transport=tr) as client:
        res = await portfolios.step_ter(store.pool, client, idx, TODAY)
        assert res["status"] == "ok" and res["stored"] == 1 and res["matched"] == {"sbi": 1}
        again = await portfolios.step_ter(store.pool, client, idx, TODAY)          # resumable: a house stored today is not asked again
        assert again["alreadyDone"] == ["sbi"] and again["stored"] == 0 and len(calls) == 1
        forced = await portfolios.step_ter(store.pool, client, idx, TODAY, force=True)
        assert forced["stored"] == 1 and len(calls) == 2
    x = await portfolios.extra_facts(store.pool, 152657)
    assert x["ter"]["value"] == {"regular": 2.01, "direct": 1.38} and x["ter"]["asOf"] == "2026-10-27" and "SBI" in x["ter"]["source"]
    f = await disclosure.get_facts(store.pool, 152655)
    assert f["terDirect"]["value"] == "1.38% a year" and f["terRegular"]["value"] == "2.01% a year" and f["terDirect"]["asOf"] == "2026-10-27"
    assert "sbimf" in f["terDirect"]["source"].lower() or "SBI" in f["terDirect"]["source"]
    async with store.pool.acquire() as conn:      # AMFI's own file, when it has the scheme, is preferred
        await conn.execute("INSERT INTO mf_facts (code, base_name, name_key) VALUES (152655, 'SBI MNC Fund', $1)", disclosure.name_key("SBI MNC Fund"))
        await conn.execute("INSERT INTO mf_ter (name_key, name, category, ter_regular, ter_direct, ter_date) VALUES ($1,$2,'x',2.5,1.5,$3)",
                           disclosure.name_key("SBI MNC Fund"), "SBI MNC Fund", date(2026, 10, 20))
    f = await disclosure.get_facts(store.pool, 152655)
    assert f["terDirect"]["source"] == disclosure.SRC_TER and f["terDirect"]["value"] == "1.50% a year"


async def test_a_house_that_fails_is_retried_and_does_not_stop_the_step(store, monkeypatch):
    monkeypatch.setattr(ter, "SOURCES", {"sbi": ter.SOURCES["sbi"]})
    monkeypatch.setattr(ter, "PAUSE", 0)
    idx = portfolios.Index()
    tr, _ = transport(sbi_fail=True)
    async with httpx.AsyncClient(transport=tr) as client:
        res = await portfolios.step_ter(store.pool, client, idx, TODAY)
    assert res["status"] == "partial" and res["failedSources"] == ["sbi"]
    assert not await portfolios._run_done(store.pool, "ter:sbi", TODAY.isoformat())


def test_the_nightly_job_runs_the_ter_step():
    assert "ter" in portfolios.STEP_NAMES
