import gzip
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "finedge"

# fixture file -> bundle key used by finlit.snapshot.build
BUNDLE_FILES = {
    "profile": "company_profile_reliance.json",
    "peers": "peers_reliance_group_sector.json",
    "quote": "quote.json",
    "pl_annual": "financials_reliance_period_annual_statement_code_pl.json",
    "bs_annual": "financials_reliance_period_annual_statement_code_bs.json",
    "cf_annual": "financials_reliance_period_annual_statement_code_cf.json",
    "pl_quarterly": "financials_reliance_period_quarterly_statement_code_pl.json",
    "segments": "segment_revenue_reliance_period_annual_statement_code_pl.json",
    "ratios_pr": "ratios_reliance_ratio_type_pr.json",
    "ratios_le": "ratios_reliance_ratio_type_le.json",
    "ratios_li": "ratios_reliance_ratio_type_li.json",
    "ratios_ef": "ratios_reliance_ratio_type_ef.json",
    "growth": "financial_metrics_reliance_ratio_type_gr.json",
    "basic": "basic_financials_reliance_statement_code_pl.json",
    "daily_quotes": "daily_quotes_reliance.json",
    "daily_price_ratios": "daily_price_ratios_reliance.json",
    "annual_price_ratios": "annual_price_ratios_reliance.json",
    "shareholding": "shareholdings_pattern_reliance_period_quarterly.json",
    "dividends": "dividend_reliance.json",
    "corporate_actions": "corporate_actions_all.json",
    "announcements": "corp_announcements.json",
}


def load(name):
    path = FIXTURES / name
    if name.endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def reliance_bundle():
    bundle = {key: load(name) for key, name in BUNDLE_FILES.items()}
    bundle.update(symbol="RELIANCE", statement="standalone")
    return bundle


@pytest.fixture(scope="session")
def reliance_sections(reliance_bundle):
    from finlit.snapshot import build
    return build(reliance_bundle)


@pytest.fixture(autouse=True)
def _mf_clock(monkeypatch):
    """The recorded AMFI files are dated late October 2026; the future-date guard in finlit.mf compares with the real clock. Tests see a fixed
    'today' after every recorded date, so they do not depend on the day they run (the guard itself is tested with an explicit date)."""
    from datetime import date
    try:
        from finlit import mf
    except Exception:
        return
    monkeypatch.setattr(mf, "india_today", lambda: date(2099, 1, 1))
