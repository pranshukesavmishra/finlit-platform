"""The 'provider sent it, the report shows it' rule (finlit/coverage.py), on a company the provider sent nothing for and on faults it must catch."""
from finlit import coverage

EMPTY = {"symbol": "540084", "quote": {"540084": {}}, "pl_annual": {"financials": [], "symbol": "540084"}, "bs_annual": {"financials": []}, "cf_annual": {"financials": []},
         "pl_quarterly": {"financials": []}, "ratios_pr": {"ratios": []}, "ratios_le": {"ratios": []}, "ratios_li": {"ratios": []}, "ratios_ef": {"ratios": []},
         "daily_quotes": {"price": [{"quote_date": "2023-02-27", "close_price": 0}]}, "shareholding": {"rows": None}, "peers": {"peers": ["PNC"]}}
NO_REPORT = {"summary": {"quote": {"price": None}}, "financials": {"yearly": {}, "quarterly": {}}, "price": {"daily": {"t": []}}, "ratios": {"history": {"periods": []}, "latest": {}}, "ownership": {}}


def test_a_company_the_provider_sent_nothing_for_is_empty_and_explained_not_a_fault():
    cov = coverage.assess(EMPTY, NO_REPORT)
    assert cov["state"] == "empty" and cov["mismatches"] == []
    assert any("no live price" in r for r in cov["reasons"]) and any("annual financial statements" in r for r in cov["reasons"])


def test_data_the_provider_sent_but_the_report_lacks_is_caught():
    sent = {**EMPTY, "quote": {"540084": {"current_price": 58.4}}, "pl_annual": {"financials": [{"year": 2026}, {"year": 2025}]},
            "ratios_pr": {"ratios": [{"header": "TTM"}]}}
    cov = coverage.assess(sent, NO_REPORT)
    assert cov["state"] != "empty"
    joined = " | ".join(cov["mismatches"])
    assert "live price" in joined and "2 rows of annual profit and loss" in joined and "current ratios" in joined


def test_ttm_only_ratios_are_not_a_missing_history_and_a_complete_report_is_clean():
    sent = {**EMPTY, "quote": {"X": {"current_price": 10}}, "symbol": "X", "pl_annual": {"financials": [{"y": 1}]}, "ratios_pr": {"ratios": [{"header": "TTM"}, {"header": "TTM"}]}}
    report = {"summary": {"quote": {"price": 10}}, "financials": {"yearly": {"pl": {"periods": ["FY26"]}}, "quarterly": {}}, "price": {"daily": {"t": ["2026-10-19"]}},
              "ratios": {"history": {"periods": []}, "latest": {"roe": {"value": 1}}}, "ownership": {}}
    cov = coverage.assess(sent, report)
    assert cov["mismatches"] == [] and cov["state"] == "complete"
    assert any("ratio history" in r for r in cov["reasons"])           # honest: only the latest ratios exist


def test_a_real_report_built_from_recorded_provider_data_has_no_mismatch():
    import json, gzip
    from pathlib import Path
    from finlit import snapshot
    from finlit.finedge import FinEdgeClient  # noqa: F401  (recorded fixtures go through the same bundle path as live data)
    import asyncio
    from finlit.config import Settings, get_settings
    st = get_settings()
    import dataclasses
    st = dataclasses.replace(st, finedge_mode="fixtures") if dataclasses.is_dataclass(st) else st

    async def run():
        async with FinEdgeClient(st) as c:
            return await c.fetch_bundle("RELIANCE", "consolidated")
    bundle = asyncio.run(run())
    cov = snapshot.build(bundle)["summary"]["dataQuality"]["coverage"]
    assert cov["mismatches"] == [] and cov["state"] == "complete"


import pytest  # noqa: E402
from test_integration import ingested, store  # noqa: E402,F401  (fixtures)


@pytest.mark.integration
async def test_every_rebuild_records_coverage_and_the_admin_health_shows_it(ingested):  # noqa: F811
    h = await ingested.health()
    assert h["coverage"]["byState"].get("complete", 0) >= 1 and h["coverage"]["mismatches"] == []
