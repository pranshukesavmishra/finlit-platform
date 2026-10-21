"""P&L cross-checks: operating profit, profit before tax, profit after tax and EPS are recomputed from the company's own components on
recorded FinEdge rows, so a sign or definition slip shows up here and not on a user's screen. Fixture: tests/fixtures/finedge/pl_cross_check.json."""

import json
import logging
from pathlib import Path

import pytest

from finlit.normalize import statements as st

DATA = json.loads((Path(__file__).parent / "fixtures" / "finedge" / "pl_cross_check.json").read_text())
CONSOLIDATED = DATA["consolidated"]
OPERATING = {k: v for k, v in CONSOLIDATED.items() if k not in ("MAHABANK", "PNBHOUSING")}   # lenders report interest earned instead
CR = 1e7


@pytest.mark.parametrize("symbol", sorted(CONSOLIDATED))
def test_every_year_ties_out(symbol):
    assert st.reconcile(CONSOLIDATED[symbol]) == []


@pytest.mark.parametrize("symbol", sorted(OPERATING))
def test_operating_profit_pbt_pat_recomputed(symbol):
    table = st.profit_and_loss(CONSOLIDATED[symbol])
    rows, n = table["rows"], len(table["periods"])
    for i in range(n):
        revenue, expenses, oi = rows["revenue"][i], rows["expenses"][i], rows.get("other_income", [0] * n)[i] or 0
        fin, dep = rows.get("finance_costs", [0] * n)[i] or 0, rows.get("depreciation", [0] * n)[i] or 0
        exc = rows.get("exceptional_items", [0] * n)[i] or 0
        op = rows["operating_profit"][i]
        # operating profit: revenue less costs before interest and depreciation, other income excluded
        assert op == pytest.approx(revenue - (expenses - fin - dep), abs=0.02)
        # and it bridges to profit before tax through the stated identity
        pbt = rows["profit_before_tax"][i]
        assert pbt == pytest.approx(op + oi - fin - dep + exc, abs=max(0.05, 0.02 * abs(pbt)))


@pytest.mark.parametrize("symbol", sorted(CONSOLIDATED))
def test_eps_sign_follows_profit_and_matches_shares(symbol):
    table = st.profit_and_loss(CONSOLIDATED[symbol])
    for eps, profit, shares in zip(table["rows"]["eps"], table["rows"]["net_profit"], table["rows"]["diluted_shares_cr"]):
        if not eps or not profit:
            continue
        assert (eps > 0) == (profit > 0), (symbol, eps, profit)
        assert abs(eps) == pytest.approx(abs(profit) / shares, rel=0.25)


def test_cineline_the_company_in_the_founders_screenshots():
    rows = CONSOLIDATED["CINELINE"]
    table = st.profit_and_loss(rows)
    by = lambda key: dict(zip(table["periods"], table["rows"][key]))
    # the stock page showed EPS 5.14 for FY25 and 11.78 for FY22: both are losses, the provider's EPS is negative
    assert by("eps")["FY25"] == -5.14 and by("eps")["FY22"] == -11.78 and by("eps")["FY24"] == -1.32
    assert by("net_profit")["FY25"] < 0 and by("profit_before_tax")["FY25"] == -36.84
    # operating profit is before interest and depreciation: 210.62 - (223.83 - 28.70 - 24.46) = 39.95 (the Gold dashboard's -39.12 is PBT - other income)
    assert by("operating_profit")["FY25"] == pytest.approx(39.94, abs=0.02)
    assert by("profit_before_tax")["FY25"] - by("other_income")["FY25"] == pytest.approx(-39.12, abs=0.01)
    assert by("revenue")["FY24"] == 247.82   # consolidated; 189.61 is the STANDALONE figure for the same year


def test_eps_sign_is_taken_from_profit_when_the_provider_contradicts_it():
    row = {"period_end": "20250331", "year": 2025, "revenueFromOperations": 2e9, "expenses": 2.4e9, "income": 2.1e9, "profitBeforeTax": -3e8,
           "taxExpense": 0, "profitLossForPeriod": -1.76e8, "profitOrLossAttributableToOwners": -1.76e8, "eps": 5.14, "dilutedOutstandingShares": 3.43e7}
    table = st.profit_and_loss([row])
    assert table["rows"]["eps"] == [-5.14] and table["epsSignRepaired"] == ["FY25"]


def test_eps_is_left_alone_when_the_magnitude_cannot_be_verified():
    base = {"period_end": "20250331", "year": 2025, "revenueFromOperations": 2e9, "expenses": 2.4e9, "profitLossForPeriod": -1.76e8, "eps": 9.9}
    assert st.profit_and_loss([{**base, "dilutedOutstandingShares": 3.43e7}])["rows"]["eps"] == [9.9]   # 9.9 is not -176m / 34.3m
    assert st.profit_and_loss([base])["rows"]["eps"] == [9.9]   # no share count: no guess


def test_provider_eps_is_never_changed_when_consistent():
    for symbol, rows in CONSOLIDATED.items():
        assert "epsSignRepaired" not in st.profit_and_loss(rows), symbol


def test_basis_gap_flags_years_where_consolidated_and_standalone_revenue_differ_by_more_than_1pct(caplog):
    gaps = st.basis_gaps(CONSOLIDATED["CINELINE"], DATA["standalone"]["CINELINE"])
    by = {g["period"]: g for g in gaps}
    assert by["FY24"]["consolidated"] == 247.82 and by["FY24"]["standalone"] == 189.61 and by["FY24"]["gapPct"] == pytest.approx(23.5, abs=0.1)
    assert "FY25" not in by   # 210.62 on both bases
    assert [g["period"] for g in gaps] == sorted(by)
    assert st.basis_gaps(CONSOLIDATED["CINELINE"], CONSOLIDATED["CINELINE"]) == []


def test_the_snapshot_reports_reconcile_and_basis_gaps():
    from finlit import snapshot
    sections = snapshot.build({"symbol": "CINELINE", "statement": "consolidated", "pl_annual": {"financials": CONSOLIDATED["CINELINE"]},
                               "pl_annual_standalone": {"financials": DATA["standalone"]["CINELINE"]}})
    quality = sections["summary"]["dataQuality"]
    assert quality["plReconcile"] == [] and quality["epsSignRepaired"] == []
    assert any(g["period"] == "FY24" for g in quality["basisGaps"])
