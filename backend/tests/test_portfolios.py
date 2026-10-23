"""Fund portfolios (finlit/portfolios.py): parsing real fund-house sheets, the checks that decide what is stored, AMFI's load text, and the read side the fund pages use."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from finlit import disclosure, portfolios
from finlit.config import Settings
from finlit.disclosure_parsers.amcs import file_month
from finlit.disclosure_parsers.model import Holding, Portfolio, validate
from finlit.disclosure_parsers.sebi import parse_rows, split_title
from finlit.store import Store
from test_integration import TEST_DB, TEST_REDIS

FX = Path(__file__).parent / "fixtures" / "disclosure"
TODAY = date(2026, 10, 22)


def sheet(name: str) -> list:
    return json.loads((FX / name).read_text())


# ------------------------------------------------------------------------------------------------------------ parsing real sheets
def test_sbi_sheet_with_back_to_index_link_and_benchmark_under_the_table():
    p = parse_rows(iter(sheet("sbi_automotive_2026_09.json")), "SBI Mutual Fund, monthly portfolio disclosure", "https://www.sbimf.com/x.xlsx")
    assert p.scheme_name == "SBI Automotive Opportunities Fund"          # not the 'Back to Index' link above it
    assert p.as_of == date(2026, 9, 30) and p.benchmark == "NIFTY AUTO TRI"
    v = validate(p, TODAY)
    assert v.ok, v.problems
    top = max(p.holdings, key=lambda h: h.pct_nav)
    assert top.name.startswith("Mahindra & Mahindra") and top.sector == "Automobiles" and top.asset_class == "equity"
    assert len(p.holdings) >= 30 and p.net_assets_lakh and p.net_assets_lakh > 100_000


def test_arbitrage_fund_with_short_futures_in_another_unit_reconciles():
    """Groww prints holdings as fractions and the short futures as percents: the futures are left out of the list, and the total still checks out."""
    p = parse_rows(iter(sheet("groww_arbitrage_2026_09.json")), "Groww Mutual Fund", "https://example/x.xlsx")
    assert p.scheme_name == "Groww Arbitrage Fund"                        # 'IB67-' sheet code dropped
    assert all(h.pct_nav >= 0 for h in p.holdings)
    assert p.hedge_pct == pytest.approx(-73.499, abs=0.01)
    assert validate(p, TODAY).ok


def test_titles():
    assert split_title("IB01-Groww Large Cap Fund")[0] == "Groww Large Cap Fund"
    main, al = split_title("SBI Aggressive Hybrid Fund (Erstwhile known as SBI Equity Hybrid Fund)")
    assert main == "SBI Aggressive Hybrid Fund" and al == ["SBI Equity Hybrid Fund"]


@pytest.mark.parametrize("name, end", [
    ("PPFAS_Monthly_Portfolio_Report_September_30_2026.xls?07102026", date(2026, 9, 30)),
    ("BOBBNPMF_Monthly_Portfolio_30-09-2026_20376.xls", date(2026, 9, 30)),
    ("helios-small-cap-fund-monthly-portfolio-as-on-30st-september-2026.xls", date(2026, 9, 30)),
    ("Monthly%20Portfolio-%20Sep%2030,%202026.xlsx", date(2026, 9, 30)),
    ("Monthly-Portfolio-february_2024.xlsx", date(2024, 2, 29)),
    ("portfolio.xlsx", None),
])
def test_file_month(name, end):
    assert file_month("https://x/" + name) == end


# ------------------------------------------------------------------------------------------------------------ what may be stored
def P(*hs, total=100.0, hedge=0.0):
    return Portfolio("k", date(2026, 9, 30), "src", "url", list(hs), "X Fund", published_total_pct=total, hedge_pct=hedge)


def test_validation_rules():
    eq = Holding("A Ltd", "INE002A01018", "Oil", "equity", 60.0, 1, 1)
    cash = Holding("TREPS", None, None, "cash", 40.0, None, 1)
    assert validate(P(eq, cash), TODAY).ok
    assert not validate(P(Holding("A Ltd", "INE002A01018", "Oil", "equity", -1.0, 1, 1), cash), TODAY).ok          # a negative share holding is wrong
    assert validate(P(eq, Holding("A Ltd October 2026 Future", None, None, "debt", -0.01, None, 1), cash, Holding("adj", None, None, "cash", 0.01, None, 1)), TODAY).ok
    fof = Holding("X ETF", "INF204KB14I2", None, "other", 102.8, 1, 1)
    v = validate(P(fof, Holding("Net payables", None, None, "cash", -2.8, None, 1)), TODAY)
    assert v.ok and v.warnings                                                                                     # a fund of funds slightly over 100 %
    assert not validate(P(Holding("X ETF", "INF204KB14I2", None, "other", 150.0, 1, 1)), TODAY).ok
    assert validate(P(eq, cash, total=100.0, hedge=-20.0), TODAY).ok                                               # the file's total leaves the hedge out
    assert validate(P(Holding("A Ltd", "INE002A01018", "Oil", "equity", 80.0, 1, 1), Holding("C", None, None, "cash", 40.0, None, 1), hedge=-20.0), TODAY).ok  # or counts it


@pytest.mark.parametrize("raw, want", [
    ("Entry Load : Not Applicable  Exit Load : Nil", "Nil"),
    ("NIl", "Nil"),
    ("Entry Load: N.A. Exit Load: \u2013 NIL", "Nil"),
    ("NA", None),
    ("", None),
    ("Entry Load: Nil Exit Load: 0.15% upto 30 days Nil after 30 days", "0.15% upto 30 days Nil after 30 days"),
    ("For Exits within 90 days from date of allotment of units : 0.50%.", "For Exits within 90 days from date of allotment of units : 0.50%."),
])
def test_exit_load_text(raw, want):
    assert portfolios.exit_load_text(raw) == want


# ------------------------------------------------------------------------------------------------------------ database: write and read
@pytest.fixture
async def store():
    try:
        s = await Store.connect(Settings(database_url=TEST_DB, redis_url=TEST_REDIS), migrate=True)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres not available: {exc}")
    async with s.pool.acquire() as conn:
        await conn.execute("TRUNCATE disclosure_portfolios, disclosure_facts, disclosure_isin, disclosure_runs")
        await conn.execute("TRUNCATE mf_schemes, mf_facts, mf_ter CASCADE")
        fam = "sbi|Equity Scheme - Sectoral/ Thematic|sbi automotive opportunities fund"
        for code, plan, isin in ((152655, "Direct", "INF200KA1Z00"), (152657, "Regular", "INF200KA1Z18")):
            await conn.execute("""INSERT INTO mf_schemes (code, name, isin, amc, scheme_type, category, plan, option_class, family, active)
                                  VALUES ($1, 'SBI Automotive Opportunities Fund', $2, 'SBI Mutual Fund', 'Open Ended', 'Equity Scheme - Sectoral/ Thematic', $3, 'Growth', $4, true)""",
                               code, isin, plan, fam)
    yield s
    await s.close()


FAM = "sbi|Equity Scheme - Sectoral/ Thematic|sbi automotive opportunities fund"


async def test_portfolio_facts_merge_into_the_fund_page_facts(store):
    p = parse_rows(iter(sheet("sbi_automotive_2026_09.json")), "SBI Mutual Fund, monthly portfolio disclosure", "https://www.sbimf.com/x.xlsx")
    assert await portfolios.store_portfolio(store.pool, FAM, "SBI Mutual Fund", p) == "stored"
    await portfolios.put_facts(store.pool, [
        (FAM, "launch_details", TODAY, {"date": "2024-05-17"}, portfolios.SRC_DETAILS, None),
        (FAM, "exitload", TODAY, {"text": "1% if redeemed within 1 year"}, portfolios.SRC_DETAILS, None)])
    x = await portfolios.extra_facts(store.pool, 152657)                  # the Regular plan reads the family's facts
    assert x["benchmark"]["value"] == "NIFTY AUTO TRI" and x["exitLoad"]["value"].startswith("1%") and x["riskometer"] is None
    assert x["monthEndAum"]["lakh"] == pytest.approx(p.net_assets_lakh)
    f = await disclosure.get_facts(store.pool, 152657)                    # what the fund page gets: AMFI's facts (not loaded here) plus these
    assert f["benchmark"]["value"] == "NIFTY AUTO TRI" and f["exitLoad"]["value"].startswith("1%")
    assert f["launchDate"]["value"] == "2024-05-17"                       # the second source fills in while the scheme master is not loaded
    assert f["aum"]["value"] == disclosure.aum_text(p.net_assets_lakh) and "month" in f["aum"]["note"]
    assert "unavailable" in f["riskometer"] and "unavailable" in f["managers"] and "unavailable" in f["minInvestment"]
    port = await disclosure.get_portfolio(store.pool, "INF200KA1Z00")     # ETF pages look schemes up by ISIN
    assert port["asOf"] == "2026-09-30" and len(port["holdings"]) == len(p.holdings)
    assert port["summary"]["sectors"][0]["sector"] == "Auto Components" and port["summary"]["top10Pct"] == pytest.approx(49.3, abs=0.1)
    assert await portfolios.extra_facts(store.pool, 999999) is None and await disclosure.get_facts(store.pool, 999999) is None


async def test_a_shorter_reread_never_replaces_a_good_portfolio(store):
    p = parse_rows(iter(sheet("sbi_automotive_2026_09.json")), "SBI", "u")
    await portfolios.store_portfolio(store.pool, FAM, "SBI Mutual Fund", p)
    p.holdings = p.holdings[:5]
    assert await portfolios.store_portfolio(store.pool, FAM, "SBI Mutual Fund", p) == "kept_existing"


async def test_exit_loads_from_amfi_scheme_details(store):
    calls = []

    def amfi(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/api/populate-mf":
            return httpx.Response(200, json=[{"mfId": "22", "mfName": "SBI Mutual Fund"}, {"mfId": "99", "mfName": "Zerodha Mutual Fund"}])
        if req.url.path == "/api/populate-scheme":
            return httpx.Response(200, json=[{"scheme_id": "13929", "scheme_name": "SBI Automotive Opportunities Fund"}, {"scheme_id": "1", "scheme_name": "Some Closed Fund"}])
        if req.url.path == "/api/scheme-details":
            return httpx.Response(200, json={"data": [{"Scheme_load": "Entry Load: Nil Exit Load: 1% if redeemed within 1 year", "Launch_Date": "2024-05-17T00:00:00+05:30"}]})
        return httpx.Response(404)
    idx = await portfolios.load_index(store.pool)
    async with httpx.AsyncClient(transport=httpx.MockTransport(amfi)) as c:
        r = await portfolios.step_loads(store.pool, c, idx, TODAY)
        assert r["families"] == 1 and r["blank"] == 0
        assert calls.count("/api/populate-scheme") == 1                    # the excluded fund house is never asked
        f = await portfolios.extra_facts(store.pool, 152655)
        assert f["exitLoad"]["value"] == "1% if redeemed within 1 year" and f["launchDate"]["value"] == "2024-05-17"
        calls.clear()
        assert (await portfolios.step_loads(store.pool, c, idx, TODAY))["families"] == 0   # fresh: not asked again this month
        assert "/api/scheme-details" not in calls


def test_every_adapter_has_a_unique_key():
    keys = [a.key for a in portfolios.ADAPTERS]
    assert len(keys) == len(set(keys)) and not set(keys) & set(portfolios.STEP_NAMES)


# ------------------------------------------------------------------------------------------------------------ risk-o-meter, managers, benchmark
@pytest.mark.parametrize("raw, level", [("Very High", "Very High"), ("very high risk", "Very High"), ("Moderately-High", "Moderately High"),
                                        ("Low to Moderate", "Low to Moderate"), ("HIGH", "High"), ("risky", None), ("", None)])
def test_only_sebi_risk_levels_are_accepted(raw, level):
    from finlit.disclosure_parsers.managers_risk import norm_level
    assert norm_level(raw) == level


def test_manager_names_lose_titles_and_tenure():
    from finlit.disclosure_parsers.managers_risk import clean_person
    assert clean_person("Mr. Sailesh Raj Bhan (since Jan 2020)") == "Sailesh Raj Bhan" and clean_person("") is None


def test_a_fund_houses_own_benchmark_beats_amfis_wording():
    from finlit.disclosure_parsers import managers_risk as m
    rows = [("f", "benchmark", None, {"name": "NIFTY 50 TRI"}, m.SRC_AMFI_TE, None), ("f", "benchmark", None, {"name": "Nifty 50 Total Return Index"}, "house", None)]
    assert m.merge_rows(rows) == [rows[1]]


async def test_risk_and_managers_reach_the_fund_page(store):
    await portfolios.put_facts(store.pool, [
        (FAM, "risk", TODAY, {"scheme": "Very High", "benchmark": "Very High"}, "SBI Mutual Fund website", None),
        (FAM, "managers", TODAY, {"names": ["Tanmaya Desai", "Pradeep Kesavan"]}, "SBI Mutual Fund website", None)])
    f = await disclosure.get_facts(store.pool, 152655)
    assert f["riskometer"]["value"] == "Very High" and f["riskometer"]["benchmarkRisk"] == "Very High"
    assert f["managers"]["value"] == "Tanmaya Desai, Pradeep Kesavan"


def test_a_name_written_without_its_space_still_matches_one_scheme():
    idx = portfolios.Index()
    idx.add(1, "Mahindra Manulife Banking & Financial Services Fund", "Mahindra Manulife Mutual Fund", "mm|eq|bfsi")
    idx.add(2, "Mahindra Manulife Flexi Cap Fund", "Mahindra Manulife Mutual Fund", "mm|eq|flexi")
    assert idx.resolve(["MahindraManulife Banking & Financial Services Fund"])[0] == "mm|eq|bfsi"
    assert idx.resolve(["Something Else Fund"])[0] is None
