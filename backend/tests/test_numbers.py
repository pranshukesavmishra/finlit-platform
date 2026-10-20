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


def test_empty_scores_say_why_and_short_annual_history_falls_back_to_quarters():
    from finlit import snapshot
    score = {"overall": None, "band": {"key": "insufficient", "label": "x"}, "pillars": [{"key": k, "score": None} for k in ("quality", "growth", "profitability", "balance", "technical")]}
    snapshot._explain_gaps(score, lender=False, annual=0, quarterly=0, days=10)
    why = {p["key"]: p["reason"] for p in score["pillars"]}
    assert "listed recently" in why["quality"] and "10 trading days" in why["technical"] and score["band"]["label"] == "Not scored yet"
    bank = {"overall": 66, "band": {}, "pillars": [{"key": "balance", "score": None}]}
    snapshot._explain_gaps(bank, lender=True, annual=8, quarterly=12, days=900)
    assert "banks and lenders" in bank["pillars"][0]["reason"]
    one_year = {"overall": 40, "band": {}, "pillars": [{"key": "growth", "score": None}]}
    snapshot._explain_gaps(one_year, lender=False, annual=1, quarterly=3, days=500)
    assert "two years" in one_year["pillars"][0]["reason"]
    # one annual result but five quarters (a recent listing like JSW Cement): growth is the latest quarter against the same quarter a year ago
    pl = {"periods": ["FY26"], "rows": {"revenue": [6512.46], "net_profit": [900.0]}}
    q = {"rows": {"revenue": [1559.82, 1436.43, 1621.22, 1894.99, 1896.41], "net_profit": [100.0, 90.0, 110.0, 120.0, 130.0]}}
    d = derived.compute(pl, {"rows": {}}, {"periods": [], "rows": {}}, {}, None, None, None, False, q)
    assert d["sales_growth_latest"] == 21.58 and d["profit_growth_latest"] == 30.0 and d["growth_basis"] == "quarter"


def test_equity_survives_provider_zero_for_owners_equity():
    """Small companies send equityAttributableToOwnersOfParent=0 meaning "not reported": total equity must still show."""
    from finlit.normalize import statements
    row = {"period_end": "2025-03-31", "totalEquity": 836379000, "equityAttributableToOwnersOfParent": 0, "nonControllingInterest": 0}
    assert statements.balance_sheet([row])["rows"]["total_equity"] == [83.64]


def test_profitability_ratios_filled_from_statements_when_provider_leaves_them_out():
    """Rows the provider omits are worked out from our statements on the provider's own definitions (margins over total income);
    a provider row is never overwritten, only its blank ROE years are filled."""
    from finlit import snapshot
    view = {"history": {"periods": ["FY24", "FY25"], "rows": {"net_margin": [9.0, 11.0], "roe": [None, 14.0]}}, "notes": []}
    pl = {"periods": ["FY24", "FY25"], "rows": {"revenue": [1000.0, 1200.0], "other_income": [50.0, 100.0], "total_income": [1050.0, 1300.0], "net_profit": [90.0, 132.0],
                                                  "operating_profit": [200.0, 260.0], "depreciation": [40.0, 50.0], "finance_costs": [20.0, 10.0],
                                                  "profit_before_tax": [120.0, 170.0], "tax": [30.0, 38.0]}}
    bs = {"periods": ["FY24", "FY25"], "rows": {"total_equity": [600.0, 700.0], "total_assets": [1500.0, 1700.0], "current_liabilities": [300.0, 350.0]}}
    snapshot._fill_profitability(view, pl, bs, lender=False)
    r = view["history"]["rows"]
    assert r["net_margin"] == [9.0, 11.0]                                  # provider row untouched
    assert r["roe"] == [15.0, 14.0]                                        # blank year filled (90 / 600), provider year kept
    assert r["pretax_margin"] == [round(120 / 1050 * 100, 2), round(170 / 1300 * 100, 2)]       # over total income
    assert r["effective_tax_rate"] == [25.0, 22.35]
    assert r["operating_margin"] == [round((200 - 40 + 50) / 1050 * 100, 2), round((260 - 50 + 100) / 1300 * 100, 2)]
    assert r["ebit_margin"] == [round(140 / 1050 * 100, 2), round(180 / 1300 * 100, 2)]          # (pre-tax + interest) / total income
    assert r["ebitda_margin"] == [round(180 / 1050 * 100, 2), round(230 / 1300 * 100, 2)]
    assert r["roce"] == [round(140 / 1200 * 100, 2), round(180 / 1350 * 100, 2)]                 # (pre-tax + interest) / (assets - current liabilities)
    assert r["roa"] == [6.0, 7.76]
    assert view["notes"] and "worked out by FinLit" in view["notes"][0]
    lender_view = {"history": {"periods": ["FY24"], "rows": {}}, "notes": []}
    snapshot._fill_profitability(lender_view, {"periods": ["FY24"], "rows": {"revenue": [500.0], "total_income": [800.0], "net_profit": [80.0]}}, {"periods": ["FY24"], "rows": {"total_equity": [400.0]}}, lender=True)
    assert lender_view["history"]["rows"]["net_margin"] == [10.0] and "ebitda_margin" not in lender_view["history"]["rows"]   # lenders: no EBITDA


def test_recent_listing_gets_a_since_listing_return():
    from finlit.analytics import returns
    days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 29, 2)]
    hist = {"t": days, "c": [100.0 + i for i in range(len(days))]}
    out = returns.trailing_returns(hist, [])
    assert out[3]["period"] == "1Y" and out[3]["price"] is None                              # too young for a year
    last = out[-1]
    assert last["period"] == "Since listing" and last["price"] == round((hist["c"][-1] / 100.0 - 1) * 100, 2) and last["from"] == days[0]
    full = returns.trailing_returns({"t": [f"{y}-{m:02d}-15" for y in range(2019, 2027) for m in range(1, 13)], "c": [50.0 + i for i in range(96)]}, [])
    assert all(r["period"] != "Since listing" for r in full)                                  # a long history needs no extra row


def test_discontinued_operations_profit_is_kept_out_of_pe_roe_and_margin():
    """Tata Motors FY26 shape: reported profit 82,390 cr includes 84,022 cr from a demerged business; continuing operations lost money."""
    from finlit import snapshot
    from finlit.normalize import statements
    pl = statements.with_continuing({"periods": ["FY25", "FY26"], "rows": {"revenue": [439695.0, 335582.0], "total_income": [445939.0, 341369.0],
                                                                         "net_profit": [27830.0, 82390.0], "discontinued_profit": [4871.0, 84022.0]}})
    assert pl["rows"]["net_profit_continuing"] == [22959.0, -1632.0] and pl["rows"]["net_profit"] == [27830.0, 82390.0]
    small = statements.with_continuing({"periods": ["FY26"], "rows": {"net_profit": [1000.0], "discontinued_profit": [50.0]}})
    assert "net_profit_continuing" not in small["rows"]                      # 5% is not material
    pl_q = {"periods": ["Q1", "Q2", "Q3", "Q4"], "rows": {"net_profit": [775.0, 76170.0, -3486.0, 5783.0], "discontinued_profit": [0.0, 82616.0, 0.0, 0.0]}}
    view = {"history": {"periods": ["FY25", "FY26"], "rows": {"roe": [30.0, 70.71], "roa": [5.0, 15.0], "net_margin": [6.0, 24.0]}},
            "latest": {"pe": {"value": 1.3}, "roe": {"value": 70.71}, "roa": {"value": 15.0}, "net_margin": {"value": 24.0}}, "notes": []}
    bs = {"periods": ["FY25", "FY26"], "rows": {"total_equity": [100000.0, 110000.0], "total_assets": [300000.0, 320000.0]}}
    snapshot._adjust_for_discontinued(view, pl, pl_q, bs, 102891.0)
    assert view["history"]["rows"]["roe"][1] == round(-1632 / 110000 * 100, 2)
    assert "pe" not in view["latest"]                                        # continuing profit is a loss: no P/E at all
    assert view["latest"]["roe"]["value"] == round(-1632 / 110000 * 100, 2) and any("discontinued" in n for n in view["notes"])
