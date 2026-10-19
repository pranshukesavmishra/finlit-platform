"""The numbers the product stands on. Each case is a real defect an independent audit found (RELIANCE, HDFCBANK, BAJFINANCE, IDEA, PAYTM, TCS)
and the value the correct calculation gives. Provider rows are in rupees; the tables are in crore."""
from datetime import date

from finlit.analytics import derived, returns, scoring
from finlit.normalize import statements as st


def test_net_profit_and_equity_belong_to_the_shareholders_not_the_minorities():
    pl = st.profit_and_loss([{"year": 2026, "revenueFromOperations": 1e12, "profitLossForPeriod": 957.54e9, "profitOrLossAttributableToOwners": 807.75e9, "eps": 59.7}])
    assert pl["rows"]["net_profit"] == [80775.0]                       # RELIANCE FY26: not the 95,754 that includes the minority share
    bs = st.balance_sheet([{"year": 2026, "totalEquity": 10858.66e9, "equityAttributableToOwnersOfParent": 9040.3e9, "nonControllingInterest": 1818.36e9}])
    assert bs["rows"]["total_equity"] == [904030.0]
    only_total = st.balance_sheet([{"year": 2026, "totalEquity": 1000e7, "nonControllingInterest": 100e7}])
    assert only_total["rows"]["total_equity"] == [900.0]


def test_a_bank_has_equity_liabilities_and_no_deposit_debt():
    bs = st.balance_sheet([{"year": 2026, "capital": 15.39e9, "reserves": 5799.75e9, "assets": 49080.4e9, "borrowings": 5884.8e9, "deposits": 30996.4e9, "advances": 30507.8e9}])
    r = bs["rows"]
    assert abs(r["total_equity"][0] - 581514.0) < 1                   # capital + reserves, in crore
    assert abs(r["total_liabilities"][0] - (4908040.0 - 581514.0)) < 5
    assert abs(r["borrowings"][0] - 588480.0) < 5                      # deposits are the bank's raw material, not its debt


def test_an_nbfc_counts_bonds_deposits_and_subordinated_debt_as_borrowings():
    bs = st.balance_sheet([{"year": 2026, "borrowingsNoncurrent": 1706.4e9, "debtSecurities": 1931.3e9, "deposits": 685.3e9, "subordinatedLiabilities": 28.05e9, "totalEquity": 1170e9}])
    assert abs(bs["rows"]["borrowings"][0] - 435107.0) < 20            # about 4.35 lakh crore, not the 1.7 lakh crore of term loans alone


def test_lenders_are_told_apart_from_companies():
    bank = [{"year": 2026, "interestEarned": 3.5e12, "income": 4.9e12}]
    nbfc = [{"year": 2026, "revenueFromOperations": 4.1e12, "interestEarned": 3.6e12, "income": 4.1e12}]
    factory = [{"year": 2026, "revenueFromOperations": 9e12, "interestEarned": 0, "income": 9.5e12}]
    assert st.is_bank(bank) and st.is_bank(nbfc) and not st.is_bank(factory)


def test_lender_margins_are_over_total_income_and_cash_conversion_needs_a_profit():
    pl = {"periods": ["FY25", "FY26"], "rows": {"revenue": [3.0e5, 3.5e5], "total_income": [4.0e5, 4.95e5], "operating_profit": [1.0e5, 1.288e5], "net_profit": [7.3e4, 7.6e4]}}
    d = derived.compute(pl, {"rows": {}}, {"periods": ["FY25", "FY26"], "rows": {"operating": [10.0, 50.0]}}, {}, None, None, None, lender=True)
    assert d["opm"] == 26.02 and d["npm"] == 15.35 and "cfo_to_pat" not in d
    loss = {"periods": ["FY26"], "rows": {"revenue": [100.0], "net_profit": [-50.0]}}
    assert "cfo_to_pat" not in derived.compute(loss, {"rows": {}}, {"periods": ["FY26"], "rows": {"operating": [-100.0]}}, {}, None, None, None)   # -100 / -50 must not read as +200%


def test_growth_counts_years_by_position_and_does_not_skip_a_gap():
    assert derived._cagr([100, None, 200, 300, 400, 500], 5)["years"] == 5 or derived._cagr([100, None, 200, 300, 400, 500], 5) is not None
    assert derived._growth([100, None, 150]) is None                   # the year before the latest is missing: no growth is claimed
    assert derived._growth([100, 110]) == 10.0
    four = derived._cagr([1000, 1100, 1200, 1300, 1400], 5)            # only four years of change exist: it is a 4-year rate and says so
    assert four["years"] == 4


def test_trailing_returns_use_calendar_months_not_day_counts():
    assert returns._months_back(date(2026, 10, 19), 36) == date(2023, 10, 19)   # 1095 days would have said 20 Oct 2023
    assert returns._months_back(date(2026, 5, 31), 3) == date(2026, 2, 28)     # no 31 February
    assert returns._months_back(date(2024, 2, 29), 12) == date(2023, 2, 28)
    dates = [f"2023-10-{d:02d}" for d in range(16, 31)] + ["2026-10-19"]
    out = returns.trailing_returns({"t": dates, "c": [100.0] * 15 + [150.0]}, [])
    three = next(r for r in out if r["period"] == "3Y")
    assert three["price"] == 50.0


def test_the_score_rounds_half_up_like_the_website():
    assert scoring._mean([44, 69]) == 57 and scoring._mean([56, 57]) == 57   # Python's round() gave 56 for 56.5
    assert scoring.band(78)["key"] == "strong" and scoring.band(77.9)["key"] == "healthy" and scoring.band(44)["key"] == "watch"


def test_negative_and_zero_multiples_are_no_number():
    from finlit.normalize import ratios
    out = ratios.price_ratio_latest({"price_ratios": [{"quote_date": "2026-10-16", "pe": -5.5, "pb": -3.74, "ps": 0, "pfcf": -30.6}]})
    assert out["pe"] is None and out["pb"] is None and out["ps"] is None and out["pfcf"] is None
