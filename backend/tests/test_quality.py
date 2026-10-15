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
