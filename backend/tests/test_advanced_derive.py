"""Advanced-chart figures (advanced/derive.py) checked against the RAW FinEdge fixture JSON with an independent extraction written here
(raw rupees -> crore, own formulas), plus synthetic sections for every guard (lenders, negative equity, base <= 0, gap, share change,
price jump, partial dividend year, exceptional-items reconciliation)."""

import copy
import json
import math
from datetime import date
from pathlib import Path

import pytest

from finlit.advanced import derive
from finlit.screener.compute import compute

RAW = Path(__file__).parent / "fixtures" / "finedge"
REL = 1e-6


def raw_rows(name):
    d = json.loads((RAW / name).read_text())
    rows = d["financials"] if isinstance(d, dict) else d
    return {int(str(r["period_end"])[:4]): r for r in rows}


PL = raw_rows("financials_reliance_period_annual_statement_code_pl.json")
BS = raw_rows("financials_reliance_period_annual_statement_code_bs.json")
CF = raw_rows("financials_reliance_period_annual_statement_code_cf.json")
CLOSES = sorted((r["quote_date"], r["close_price"]) for r in json.loads((RAW / "daily_quotes_reliance.json").read_text())["price"])
RATIOS_PR = {r["header"]: r for r in json.loads((RAW / "ratios_reliance_ratio_type_pr.json").read_text())["ratios"]}
CR = 1e7


def cr(v):
    return (v or 0) / CR


def close_on_or_before(day):
    c = [x for x in CLOSES if x[0] <= day]
    return c[-1]


def g(a, b):
    return (a / b - 1) * 100


def approx(v):
    return pytest.approx(v, rel=REL, abs=1e-6)


@pytest.fixture(scope="module")
def ax(reliance_sections):
    return derive.latest(reliance_sections, compute(reliance_sections))


def test_statement_figures_against_raw_json(ax):
    p, p0, b, b0, c, c0 = PL[2026], PL[2025], BS[2026], BS[2025], CF[2026], CF[2025]
    rev, rev0 = cr(p["revenueFromOperations"]), cr(p0["revenueFromOperations"])
    op = rev - (cr(p["expenses"]) - cr(p["financeCosts"]) - cr(p["depreciationAndAmortisation"]))
    op0 = rev0 - (cr(p0["expenses"]) - cr(p0["financeCosts"]) - cr(p0["depreciationAndAmortisation"]))
    np_, np0 = cr(p["profitLossForPeriod"]), cr(p0["profitLossForPeriod"])
    debt = cr(b["borrowingsCurrent"]) + cr(b["borrowingsNoncurrent"])
    debt0 = cr(b0["borrowingsCurrent"]) + cr(b0["borrowingsNoncurrent"])
    cash, cl, ca, ta, tl, eq = (cr(b[k]) for k in ("cashAndCashEquivalents", "currentLiabilities", "currentAssets", "assets", "liabilities", "equityAttributableToOwnersOfParent"))
    cfo, cfo0 = cr(c["cashFlowsFromOperatingActivities"]), cr(c0["cashFlowsFromOperatingActivities"])
    capex, capex0 = abs(cr(c["purchaseOfPPEClassifiedAsInvesting"])), abs(cr(c0["purchaseOfPPEClassifiedAsInvesting"]))
    shares = round(cr(p["dilutedOutstandingShares"]), 2)   # stored statements keep crore figures to 2 decimals (0.01 Cr = 100,000 shares)
    assert ax["ax_fy"] == "FY26"
    assert ax["ax_revenue"] == approx(rev) and ax["ax_np"] == approx(np_) and ax["ax_ebitda"] == approx(op)
    assert ax["ax_g_rev"] == approx(g(rev, rev0)) and ax["ax_g_np"] == approx(g(np_, np0)) and ax["ax_g_ebitda"] == approx(g(op, op0))
    assert ax["ax_g_eps"] == approx(g(p["eps"], p0["eps"]))
    assert ax["ax_opm"] == approx(op / rev * 100) and ax["ax_npm"] == approx(np_ / rev * 100)
    assert ax["ax_ebit_margin"] == approx((cr(p["profitBeforeTax"]) + cr(p["financeCosts"])) / rev * 100)
    ebit0 = cr(p0["profitBeforeTax"]) + cr(p0["financeCosts"])
    assert ax["ax_g_ebit"] == approx(g(cr(p["profitBeforeTax"]) + cr(p["financeCosts"]), ebit0))
    assert ax["ax_g_pbt"] == approx(g(cr(p["profitBeforeTax"]), cr(p0["profitBeforeTax"])))
    assert ax["ax_g_tax"] == approx(g(cr(p["taxExpense"]), cr(p0["taxExpense"])))
    assert ax["ax_g_int"] == approx(g(cr(p["financeCosts"]), cr(p0["financeCosts"])))
    assert ax["ax_g_dep"] == approx(g(cr(p["depreciationAndAmortisation"]), cr(p0["depreciationAndAmortisation"])))
    assert ax["ax_nd_ebitda"] == approx((debt - cash) / op) and ax["ax_g_debt"] == approx(g(debt, debt0))
    assert ax["ax_cash_ratio"] == approx(cash / cl) and ax["ax_cl_tl"] == approx(cl / tl * 100)
    assert ax["ax_wc_rev"] == approx((ca - cl) / rev * 100) and ax["ax_ca_ta"] == approx(ca / ta * 100)
    assert ax["ax_cfo"] == approx(cfo) and ax["ax_cfo_pat"] == approx(cfo / np_ * 100) and ax["ax_cfo_debt"] == approx(cfo / debt)
    assert ax["ax_g_cfo"] == approx(g(cfo, cfo0)) and ax["ax_g_capex"] == approx(g(capex, capex0))
    assert ax["ax_fcf"] == approx(cfo - capex) and ax["ax_g_fcf"] == approx(g(cfo - capex, cfo0 - capex0))
    assert ax["ax_accruals"] == approx((np_ - cfo) / ((ta + cr(b0["assets"])) / 2) * 100)
    assert ax["ax_oi_np"] == approx(cr(p["otherIncome"]) / np_ * 100)
    assert ax["ax_exc_np"] == 0.0   # no exceptional line, and op + OI - fin - dep reconciles to PBT
    assert abs(op + cr(p["otherIncome"]) - cr(p["financeCosts"]) - cr(p["depreciationAndAmortisation"]) - cr(p["profitBeforeTax"])) < 0.02
    assert ax["ax_cfo_ps"] == approx(cfo / shares) and ax["ax_bvps"] == approx(eq / shares)
    assert ax["ax_g_bv"] == approx(g(eq, cr(b0["equityAttributableToOwnersOfParent"])))
    assert ax["ax_g_assets"] == approx(g(ta, cr(b0["assets"])))
    assert ax["ax_g_recv"] == approx(g(cr(b["tradeReceivablesCurrent"]), cr(b0["tradeReceivablesCurrent"])))
    assert ax["ax_g_inv"] == approx(g(cr(b["inventories"]), cr(b0["inventories"])))
    assert ax["ax_g_wc"] == approx(g(ca - cl, cr(b0["currentAssets"]) - cr(b0["currentLiabilities"])))
    assert ax["ax_ev_cfo"] > 0 and ax["ax_fcf_yield"] > 0


def test_provider_ratios_at_the_same_fy(ax):
    roe = RATIOS_PR["Mar 2026"]["returnOnEquity"] * 100
    assert ax["ax_roe"] == pytest.approx(round(roe, 2), abs=1e-9)      # FY26, not the TTM headline
    assert ax["ax_inv_turnover"] == approx(365 / ax["ax_inv_days"])


def test_dividends_prices_and_windows_against_raw(ax):
    # dividends (adjusted amounts): FY26 final Rs 6 (5 Jun 2026), FY25 final Rs 5.5 (14 Aug 2025)
    assert ax["ax_payout"] == approx(6 / 32.4 * 100) and ax["ax_div_cover"] == approx(32.4 / 6) and ax["ax_g_dps"] == approx(g(6, 5.5))
    d0, c0 = close_on_or_before("2025-03-31")
    d1, c1 = close_on_or_before("2026-03-31")
    assert ax["ax_ret_fy"] == approx(g(c1, c0))
    assert ax["ax_tsr_fy"] == approx(((c1 + 5.5) / c0 - 1) * 100)     # ex-date 14 Aug 2025 inside (31 Mar 2025, 31 Mar 2026]
    assert ax["ax_pe_fy"] == approx(c1 / 32.4)
    # forward signal: FY25 end + 75 days = 14 Jun 2025, 12 months later 14 Jun 2026
    assert ax["ax_sig_fy"] == "FY25" and ax["ax_sig_date"] == "2025-06-14"
    _, cs = close_on_or_before("2025-06-14")
    _, ce = close_on_or_before("2026-06-14")
    assert ax["ax_fwd12"] == approx(g(ce, cs)) and ax["ax_pe_sig"] == approx(cs / 26.06)
    assert ax["ax_miss"]["vol3y"] == "short_history"     # the fixture holds 430 sessions, 700 are needed
    assert ax["ax_inst_chg"] == pytest.approx(-2.01 + 1.39)


def test_latest_is_the_last_point_of_history(reliance_sections, ax):
    h = derive.history(reliance_sections)
    for m, vals in h["values"].items():
        if m in ("pe", "pb"):
            continue   # history P/E and P/B are the provider's yearly figures; cross-section P/E and P/B are today's
        key = f"ax_{m}"
        if vals[-1] is None:
            assert key not in ax and m in ax["ax_miss"], m
        else:
            assert ax[key] == pytest.approx(vals[-1], rel=1e-12), m
    assert h["values"]["pe"][-1] == 44.18 and h["values"]["pb"][-1] == 3.42   # provider valuationHistory FY26


def test_compute_stores_ax_with_full_precision(reliance_sections):
    m = compute(reliance_sections)
    assert m["m_ver"] == 3.0 and m["ax_fy"] == "FY26" and isinstance(m["ax_miss"], dict)
    raw = derive.latest(reliance_sections, None)["ax_g_rev"]
    assert m["ax_g_rev"] == float(f"{raw:.10g}")


# ------------------------------------------------------------ synthetic guards
def sections(pl_rows, bs_rows=None, cf_rows=None, ends=None, bank=False, actions=None, price=None, hist=None, vh=None):
    ends = ends or ["2023-03-31", "2024-03-31", "2025-03-31", "2026-03-31"][-len(next(iter(pl_rows.values()))):]
    fys = ["FY" + e[2:4] for e in ends]
    def t(rows):
        return {"periods": fys, "periodEnds": ends, "rows": rows or {}}
    return {"financials": {"yearly": {"pl": t(pl_rows), "bs": t(bs_rows or {}), "cf": t(cf_rows or {})}},
            "ratios": {"history": hist or {"periods": fys, "rows": {}}, "valuationHistory": vh or {}},
            "summary": {"dataQuality": {"isBank": bank}}, "events": {"actions": actions or []}, "price": price or {}}


def test_base_le0_gap_and_no_prev():
    s = sections({"revenue": [-5.0, 100.0], "net_profit": [10.0, 20.0], "eps": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"])
    h = derive.history(s)
    assert h["values"]["g_rev"] == [None, None] and h["miss"]["g_rev"] == ["no_prev", "base_le0"]
    assert h["values"]["g_np"][1] == pytest.approx(100.0)
    s = sections({"revenue": [50.0, 100.0]}, ends=["2024-03-31", "2026-03-31"])
    assert derive.history(s)["miss"]["g_rev"][1] == "gap"


def test_share_change_guard():
    pl = {"net_profit": [100.0, 120.0], "eps": [10.0, 6.0], "diluted_shares_cr": [10.0, 20.0]}
    h = derive.history(sections(pl, ends=["2025-03-31", "2026-03-31"]))
    assert h["values"]["g_eps"][1] is None and h["miss"]["g_eps"][1] == "share_change"
    pl = {"net_profit": [100.0, 120.0], "eps": [5.0, 6.0], "diluted_shares_cr": [20.0, 20.0]}   # restated for the bonus: comparable
    act = [{"date": "2025-10-28", "type": "bonus"}]
    h = derive.history(sections(pl, ends=["2025-03-31", "2026-03-31"], actions=act))
    assert h["values"]["g_eps"][1] == pytest.approx(20.0)
    pl = {"net_profit": [100.0, 120.0], "eps": [5.0, 5.6], "diluted_shares_cr": [20.0, 21.5]}  # +7.5% shares with a bonus in between
    h = derive.history(sections(pl, ends=["2025-03-31", "2026-03-31"], actions=act))
    assert h["miss"]["g_eps"][1] == "share_change"


def test_lenders_and_negative_equity():
    pl = {"revenue": [100.0, 110.0], "total_income": [120.0, 130.0], "operating_profit": [30.0, 33.0], "net_profit": [10.0, 12.0]}
    cf = {"operating": [5.0, 6.0]}
    lt = derive.latest(sections(pl, cf_rows=cf, ends=["2025-03-31", "2026-03-31"], bank=True), {})
    assert "ax_cfo" not in lt and lt["ax_miss"]["cfo"] == "lender" and lt["ax_miss"]["g_cfo"] == "lender"
    assert lt["ax_opm"] == pytest.approx(33 / 130 * 100)    # a lender's margin is on total income
    assert lt["ax_npm"] == pytest.approx(12 / 130 * 100) and lt["ax_g_rev"] == pytest.approx(10.0)
    bs = {"total_equity": [-5.0, -3.0]}
    lt = derive.latest(sections({"net_profit": [1.0, 2.0]}, bs_rows=bs, ends=["2025-03-31", "2026-03-31"]), {})
    assert lt["ax_miss"]["roe"] == "neg_equity" and lt["ax_miss"]["de"] == "neg_equity"


def test_exceptional_items_reconciliation_rule():
    base = {"revenue": [100.0, 100.0], "operating_profit": [20.0, 20.0], "other_income": [2.0, 2.0], "finance_costs": [1.0, 1.0],
            "depreciation": [3.0, 3.0], "net_profit": [10.0, 12.0]}
    ok = derive.latest(sections({**base, "profit_before_tax": [18.0, 18.0]}, ends=["2025-03-31", "2026-03-31"]), {})
    assert ok["ax_exc_np"] == 0.0
    bad = derive.latest(sections({**base, "profit_before_tax": [18.0, 25.0]}, ends=["2025-03-31", "2026-03-31"]), {})
    assert "ax_exc_np" not in bad and bad["ax_miss"]["exc_np"] == "no_data"   # does not reconcile: an unlisted item exists


def test_partial_dividend_year_and_no_dividend():
    pl = {"net_profit": [10.0, 12.0], "eps": [1.0, 1.2]}
    act = [{"date": "2024-07-01", "type": "final_dividend", "amount": 0.5, "adjustedAmount": 0.5, "forFY": "FY24"},
           {"date": "2025-07-01", "type": "final_dividend", "amount": 0.6, "adjustedAmount": 0.6, "forFY": "FY25"}]
    s = sections(pl, ends=["2025-03-31", "2026-03-31"], actions=act)
    early = derive.latest(s, {}, today=date(2026, 6, 1))       # FY26 final not declared yet: not a zero
    assert early["ax_miss"]["payout"] == "partial" and early["ax_miss"]["g_dps"] == "partial"
    late = derive.latest(s, {}, today=date(2026, 12, 1))       # declaration season over, nothing declared: a real 0
    assert late["ax_payout"] == 0.0 and late["ax_miss"]["div_cover"] == "no_dividend" and late["ax_g_dps"] == pytest.approx(-100.0)


def _price(days, closes):
    return {"daily": {"t": days, "c": closes, "v": [1000] * len(days)}}


def test_price_jump_and_start_gap():
    days = ["2025-03-28", "2025-09-01", "2025-09-02", "2026-03-31"]
    s = sections({"net_profit": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"], price=_price(days, [100.0, 100.0, 49.0, 60.0]))
    assert derive.latest(s, {})["ax_miss"]["ret_fy"] == "jump"           # a 1:1 bonus not adjusted in the closes
    s = sections({"net_profit": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"], price=_price(days, [100.0, 100.0, 101.0, 110.0]))
    assert derive.latest(s, {})["ax_ret_fy"] == pytest.approx(10.0)
    act = [{"date": "2025-06-01", "type": "split"}]
    s = sections({"net_profit": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"], price=_price(days, [100.0, 100.0, 101.0, 110.0]), actions=act)
    assert derive.latest(s, {})["ax_miss"]["ret_fy"] == "jump"           # an action inside the window
    s = sections({"net_profit": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"], price=_price(["2025-03-10", "2026-03-31"], [100.0, 110.0]))
    assert derive.latest(s, {})["ax_miss"]["ret_fy"] == "start_gap"      # no close within 7 days of 31 Mar 2025


def test_tsr_needs_confirmed_basis_when_dividends_were_rebased():
    days = ["2025-03-28", "2025-08-01", "2026-03-31"]
    act = [{"date": "2025-07-01", "type": "final_dividend", "amount": 10.0, "adjustedAmount": 5.0, "forFY": "FY25"}]
    s = sections({"net_profit": [1.0, 2.0]}, ends=["2025-03-31", "2026-03-31"], price=_price(days, [100.0, 100.0, 110.0]), actions=act)
    assert derive.latest(s, {})["ax_miss"]["tsr_fy"] == "basis"          # cannot confirm the closes are on the adjusted basis


def test_volatility_and_drawdown_independent():
    days, closes = [], []
    d = date(2023, 1, 2).toordinal()
    for k in range(720):
        days.append(date.fromordinal(d + k).isoformat())
        closes.append(100 * math.exp(0.01 * math.sin(k / 7.0) + 0.0002 * k))
    lt = derive.latest(sections({"net_profit": [1.0]}, ends=["2026-03-31"], price=_price(days, closes)), {})
    rets = [math.log(closes[k] / closes[k - 1]) for k in range(1, len(closes))]
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    assert lt["ax_vol3y"] == pytest.approx(sd * math.sqrt(252) * 100, rel=1e-12)
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, c / peak - 1)
    assert lt["ax_mdd3y"] == pytest.approx(worst * 100, rel=1e-12)


def test_missing_sections_never_invent():
    lt = derive.latest({}, {})
    assert not [k for k in lt if k.startswith("ax_") and k not in ("ax_miss",)]
    assert all(v for v in lt["ax_miss"].values())
    s = copy.deepcopy(sections({"revenue": [1.0, 2.0]}, ends=["2025-12-31", "2026-12-31"], hist={"periods": ["FY26"], "rows": {"roe": [5.0]}}))
    # a December-year company keeps the provider's yearly ratio row that carries its own year's label (it used to be refused as "non_march")
    got = derive.latest(s, {})
    assert "roe" not in got["ax_miss"] and got["ax_roe"] == 5.0
    s2 = copy.deepcopy(sections({"revenue": [1.0, 2.0]}, ends=["2025-12-31", "2026-12-31"], hist={"periods": ["FY20"], "rows": {"roe": [5.0]}}))
    assert derive.latest(s2, {})["ax_miss"]["roe"] == "no_fy"   # a year the provider did not send is missing, with its reason


def test_provider_yearly_pe_pb_definition(reliance_sections):
    """Plan risk 2: the provider's yearly P/E is the AVERAGE price over the financial year / that year's EPS, and P/B the average price /
    (equity / diluted shares), on all eight stored years; the average price is on the split/bonus-adjusted basis (RELIANCE FY24 Rs 1,275,
    half the pre-bonus level), consistent with the restated EPS and share count."""
    vh = reliance_sections["ratios"]["valuationHistory"]
    pl = reliance_sections["financials"]["yearly"]["pl"]
    bs = reliance_sections["financials"]["yearly"]["bs"]
    eq = dict(zip(bs["periods"], bs["rows"]["total_equity"]))
    eps, sh = dict(zip(pl["periods"], pl["rows"]["eps"])), dict(zip(pl["periods"], pl["rows"]["diluted_shares_cr"]))
    for fy, pe, pb, ap in zip(vh["periods"], vh["rows"]["pe"], vh["rows"]["pb"], vh["rows"]["average_price"]):
        assert round(ap / eps[fy], 2) == pe and round(ap / (eq[fy] / sh[fy]), 2) == pb, fy
    assert all(1352 < s < 1354 for s in pl["rows"]["diluted_shares_cr"])      # ~1,353 crore in every year: restated for the Oct 2024 1:1 bonus (676.6 crore before)
    assert bs["rows"]["equity_capital"][-3:] == [6766.0, 13532.0, 13532.0]    # while the balance sheet share capital doubled in FY25
