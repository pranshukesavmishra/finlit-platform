"""Regression tests for faults the founder reported (ledger: docs/KNOWN-ISSUES.md). Recorded data only, no live calls.

Items (a) and (c) live in test_coverage.py and test_pl_crosscheck.py; (d) and (f) are frontend tests (Atlas.test.tsx, chartAxis.regression.test.ts);
(g) is in site-api/backend/tests/test_regression_risk_inputs.py. This file holds (b) and (e).
"""
from datetime import date

import pytest

from finlit import finedge, integrity, results


def _rows(*ends):
    return {"financials": [{"period_end": e.replace("-", ""), "year": int(e[:4])} for e in ends]}


@pytest.mark.xfail(strict=False, reason="stale-basis fix in progress by another agent (finedge._prefer_current_basis / worker); drop the marker once it lands")
def test_b_stale_consolidated_is_replaced_by_the_fresher_standalone_basis():
    """SBFC: consolidated quarters stop Mar 2025, standalone run to Sep 2026. The fresher basis must be chosen, with the reason recorded."""
    bundle = {"pl_quarterly": _rows("2024-12-31", "2025-03-31"), "pl_annual": _rows("2024-03-31", "2025-03-31")}
    why = finedge.stale_reason(bundle, _rows("2025-03-31", "2026-03-31"), _rows("2026-06-30", "2026-09-30"))
    assert why is not None
    assert why["consolidatedLatestQuarter"] == "2025-03-31" and why["standaloneLatestQuarter"] == "2026-09-30"
    assert finedge.stale_reason(bundle, _rows("2025-03-31"), _rows("2025-03-31")) is None           # equally fresh: stay consolidated


def test_e_results_declared_long_ago_are_flagged_when_the_report_is_still_old():
    """A declared result must turn into figures; 'being updated' for more than 3 days is a fault the nightly audit counts."""
    today, q = date(2026, 10, 26), date(2026, 9, 30)
    assert integrity.check_declared(date(2026, 10, 15), q, "2026-06-30", today)
    assert integrity.check_declared(date(2026, 10, 15), q, "2026-09-30", today) is None
    # the results page itself words the state honestly
    assert results.status_of(date(2026, 10, 15), today, False, date(2026, 6, 30), q) == "awaiting"
    assert results.status_of(date(2026, 10, 15), today, True, date(2026, 9, 30), q) == "declared"
