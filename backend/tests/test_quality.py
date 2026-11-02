import copy
from datetime import datetime, timezone

import pytest

from finlit import quality
from finlit.snapshot import build

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def clean(reliance_bundle):
    return build(reliance_bundle, now=NOW)


def keys(result, severity=None):
    return {i["key"] for i in result["issues"] if severity is None or i["severity"] == severity}


def test_real_data_passes_every_check(clean):
    result = clean["summary"]["dataQuality"]["checks"]
    assert result["status"] == "ok" and result["passed"] == result["total"] >= 20


def test_unit_slip_in_market_cap_is_rejected(clean):
    broken = copy.deepcopy(clean)
    broken["summary"]["quote"]["marketCapCr"] *= 100  # rupees vs crore style mistake
    result = quality.run(broken, today=NOW.date())
    assert result["status"] == "rejected" and "market_cap_consistent" in keys(result, "critical")


def test_balance_sheet_that_does_not_balance_is_rejected(clean):
    broken = copy.deepcopy(clean)
    broken["financials"]["yearly"]["bs"]["rows"]["total_assets"][-1] *= 1.5
    result = quality.run(broken, today=NOW.date())
    assert "balance_sheet_balances" in keys(result, "critical")


def test_old_site_dividend_bug_is_rejected(clean):
    broken = copy.deepcopy(clean)
    for r in broken["summary"]["returns"]:
        if r["dividend"] is not None:
            r["dividend"] = 89.14
    assert "dividend_return_1Y" in keys(quality.run(broken, today=NOW.date()), "critical")


def since_listing(clean, dividend, listed="1999-03-01"):
    broken = copy.deepcopy(clean)
    broken["summary"]["returns"] = [r for r in broken["summary"]["returns"] if r["period"] != "Since listing"] + [
        {"period": "Since listing", "price": 400.0, "dividend": dividend, "total": 400.0 + dividend, "annualised": 8.0, "from": listed}]
    return quality.run(broken, today=NOW.date())


def test_a_long_listed_dividend_payer_is_not_rejected_for_what_it_paid_since_listing(clean):
    """Kennametal India (listed for decades) was refused its whole report because 17.29% since listing was held to the one-year limit of 15%."""
    r = since_listing(clean, 17.29, listed="1999-03-01")                      # 27 years: the limit is 15% a year, so about 400%
    assert "dividend_return_Since listing" not in keys(r)
    assert since_listing(clean, 380.0, listed="1999-03-01") and "dividend_return_Since listing" not in keys(since_listing(clean, 380.0, listed="1999-03-01"))


def test_the_dividend_check_still_catches_an_impossible_figure_since_listing(clean):
    assert "dividend_return_Since listing" in keys(since_listing(clean, 89.0, listed="2026-01-02"), "critical")        # a company listed 9 months ago did not pay 89%
    assert "dividend_return_Since listing" in keys(since_listing(clean, 900.0, listed="1999-03-01"), "critical")       # nor 900% in 27 years (limit about 400%)


def test_stale_prices_and_odd_ratios_only_warn(clean):
    broken = copy.deepcopy(clean)
    next(m for m in broken["summary"]["keyMetrics"] if m["key"] == "pe")["value"] = 5000
    result = quality.run(broken, today=datetime(2026, 12, 1).date())
    assert result["status"] == "warnings"
    assert {"range_pe", "price_fresh"} <= keys(result, "warning")


def test_zero_price_is_rejected(clean):
    broken = copy.deepcopy(clean)
    broken["summary"]["quote"]["price"] = 0.0
    assert quality.run(broken, today=NOW.date())["status"] == "rejected"
