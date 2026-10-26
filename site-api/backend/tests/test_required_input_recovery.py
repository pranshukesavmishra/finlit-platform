from copy import deepcopy
from datetime import date
from backend.fundamental_resolution import derive_finedge, recover_inputs, statement_rows

ASOF=date(2026,10,25)


def test_explicit_ebit_identity_recovers_expense_but_not_generic_operating_profit():
    raw={'annual':{'financials':[{'period_end':20260331,'ebit':80,'profitBeforeTax':60},
                                {'period_end':20250331,'operatingProfit':80,'profitBeforeTax':60},
                                {'period_end':20240331,'ebit':80,'profitBeforeTax':90}]}}
    result,_=derive_finedge(raw)
    rows=result['annual']['financials']
    assert rows[0]['financeCosts']==20
    assert all('financeCosts' not in r for r in rows[1:])
    raw['annual']['financials'][0]['interestExpense']=0
    result,_=derive_finedge(raw)
    assert 'financeCosts' not in result['annual']['financials'][0]


def test_lender_interest_expense_from_matching_earned_interest_and_nii():
    raw={'profile':{'industry':'Banks'},'annual':{'financials':[{'period_end':20260331,'interestEarned':100,'netInterestIncome':40}]}}
    result,_=derive_finedge(raw)
    assert result['annual']['financials'][0]['interestExpended']==60
    raw['profile']['industry']='Insurance'
    result,_=derive_finedge(raw)
    assert 'interestExpended' not in result['annual']['financials'][0]


def test_complete_income_history_still_attempts_required_pbt_and_expense_recovery():
    raw={'annual':{'financials':[{'period_end':f'{y}-03-31','revenueFromOperations':10,'profitLossForPeriod':1,'basicEPS':1} for y in range(2021,2027)]}}
    calls=[]
    def load(section):
        calls.append(section)
        return {'type':'consolidated','time_period':'yearly','units_in':'crore','full_statement':[
            {'particular':'Profit Before Tax','history':[{'period':'Mar 2026','value':2}]},
            {'particular':'Interest Expense','history':[{'period':'Mar 2026','value':0}]}]} if section=='annual' else None
    out,_=recover_inputs(raw,'consolidated',ASOF,load,recover_prices=False)
    assert calls.count('annual')==1
    assert out['annual']['financials'][-1]['profitBeforeTax']==20_000_000
    assert out['annual']['financials'][-1]['financeCosts']==0


def test_operating_cashflow_category_recovers_when_detailed_statement_is_absent():
    payload={'type':'consolidated','time_period':'yearly','units_in':'crore','cash_flow':[
        {'category':'operating','history':[{'period':'Mar 2026','value':0}]},
        {'category':'financing','history':[{'period':'Mar 2026','value':500}]}]}
    rows=statement_rows(payload,'consolidated',cashflow=True)
    assert rows[0]['cashFlowsFromOperatingActivities']==0
    assert 'financeCosts' not in rows[0]
    assert statement_rows({**payload,'type':'standalone'},'consolidated',cashflow=True)==[]


def test_partial_balance_recovery_only_fills_matching_periods_preserving_zero():
    raw={'annual':{'financials':[{'period_end':20260331}]},'balance':{'financials':[
        {'period_end':20260331,'totalAssets':100_000_000,'borrowings':0},
        {'period_end':20260630,'totalAssets':120_000_000}]}}
    original=deepcopy(raw)
    payload={'type':'consolidated','units_in':'crore','time_period':'yearly',
             'history':[{'period':'Mar 2026','total_asset':999,'total_liability':4},
                        {'period':'Mar 2025','total_asset':8,'total_liability':3}],
             'full_statement':[{'particular':'Total Equity','history':[{'period':'Mar 2026','value':995},{'period':'Mar 2025','value':5}]}]}
    out,notes=recover_inputs(raw,'consolidated',ASOF,lambda k:payload if k=='balance' else None,recover_prices=False)
    rows=out['balance']['financials']
    assert rows[0]['totalAssets']==100_000_000 and rows[0]['borrowings']==0
    # Reject an equity value that reconciles to Upstox's assets but conflicts
    # with the FinEdge assets kept for the same date.
    assert 'totalEquity' not in rows[0]
    assert len(rows)==2 and 'totalEquity' not in rows[1]
    assert raw==original


def test_matching_partial_balance_is_recovered_without_overwriting_finedge():
    raw={'annual':{'financials':[{'period_end':20260331}]},'balance':{'financials':[{'period_end':20260331,'totalAssets':100_000_000,'borrowings':0}]}}
    payload={'type':'consolidated','units_in':'crore','time_period':'yearly',
             'history':[{'period':'Mar 2026','total_asset':10,'total_liability':4}],
             'full_statement':[{'particular':'Total Equity','history':[{'period':'Mar 2026','value':6}]}]}
    out,notes=recover_inputs(raw,'consolidated',ASOF,lambda k:payload if k=='balance' else None,recover_prices=False)
    row=out['balance']['financials'][0]
    assert row['totalEquity']==60_000_000 and row['borrowings']==0
    assert any(n.startswith('Upstox balance ') and 'recovered periods' in n for n in notes)


def test_annual_insurance_premium_and_interest_alias_are_recoverable_from_four_quarters():
    raw={'annual':{'financials':[{'period_end':20260331}]},'quarterly':{'financials':[
        {'period_end':end,'netPremiumIncome':100,'interestExpense':2} for end in (20250630,20250930,20251231,20260331)]}}
    out,_=derive_finedge(raw)
    assert out['annual']['financials'][0]['netPremiumIncome']==400
    assert out['annual']['financials'][0]['financeCosts']==8
