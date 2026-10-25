from copy import deepcopy
from datetime import date
import pytest
from backend.fundamental_resolution import derive_finedge, recover_inputs


def inputs():
    return {'annual':{'financials':[{'period_start':'2024-04-01','period_end':'2025-03-31','result_date':'2025-05-08',
        'revenueFromOperations':1000,'profitOrLossAttributableToOwners':100,'ebitda':200,'eps':10}]},
        'quarterly':{'financials':[
            {'period_start':'2024-04-01','period_end':'2024-06-30','revenueFromOperations':100,'profitOrLossAttributableToOwners':10,'ebitda':20},
            {'period_start':'2024-07-01','period_end':'2024-09-30','revenueFromOperations':200,'profitOrLossAttributableToOwners':20,'ebitda':40},
            {'period_start':'2024-10-01','period_end':'2024-12-31','revenueFromOperations':300,'profitOrLossAttributableToOwners':30,'ebitda':60},
            {'period_start':'2024-10-01','period_end':'2025-03-31','revenueFromOperations':9999,'profitOrLossAttributableToOwners':9999,'eps':9999},
        ]}}


def test_malformed_q4_is_calculated_from_annual_and_three_quarters_not_relabelled():
    raw=inputs();original=deepcopy(raw)
    resolved,notes=derive_finedge(raw)
    row=next(r for r in resolved['quarterly']['financials'] if r['period_end']=='2025-03-31')
    assert row['period_start']=='2025-01-01'
    assert row['revenueFromOperations']==400 and row['profitOrLossAttributableToOwners']==40 and row['ebitda']==80
    assert row['result_date']=='2025-05-08' and 'eps' not in row
    assert any('full-year amounts minus the three matching quarters' in note for note in notes)
    assert raw==original


def test_valid_reported_zero_and_quarterly_eps_keep_precedence():
    raw=inputs();row=raw['quarterly']['financials'][-1]
    row.update(period_start='2025-01-01',revenueFromOperations=0,eps=2)
    resolved,_=derive_finedge(raw)
    row=next(r for r in resolved['quarterly']['financials'] if r['period_end']=='2025-03-31')
    assert row['revenueFromOperations']==0 and row['eps']==2


@pytest.mark.parametrize('problem',['missing_quarter','partial_year','missing_annual_start'])
def test_incomplete_annual_or_first_three_quarters_cannot_recover_q4(problem):
    raw=inputs()
    if problem=='missing_quarter':raw['quarterly']['financials'].pop(0)
    elif problem=='partial_year':raw['annual']['financials'][0]['period_start']='2024-07-01'
    else:raw['annual']['financials'][0].pop('period_start')
    resolved,notes=derive_finedge(raw)
    assert not any('full-year amounts minus' in note for note in notes)
    assert next(r for r in resolved['quarterly']['financials'] if r['period_end']=='2025-03-31')['revenueFromOperations']==9999


def test_future_annual_publication_does_not_make_derived_quarter_available_early():
    resolved,_=recover_inputs(inputs(),'consolidated',date(2025,4,30),lambda _:None,period='quarterly',recover_prices=False)
    assert not any(r['period_end']=='2025-03-31' for r in resolved['quarterly']['financials'])


def test_quarterly_dashboard_optional_annual_source_and_non_march_financial_year():
    raw={'annual_for_quarter_recovery':{'financials':[{'period_start':'2024-01-01','period_end':'2024-12-31','revenueFromOperations':1000}]},
         'quarterly':{'financials':[{'period_start':s,'period_end':e,'revenueFromOperations':v} for s,e,v in [
             ('2024-01-01','2024-03-31',100),('2024-04-01','2024-06-30',200),('2024-07-01','2024-09-30',300)]]}}
    resolved,_=derive_finedge(raw)
    row=next(r for r in resolved['quarterly']['financials'] if r['period_end']=='2024-12-31')
    assert row['period_start']=='2024-10-01' and row['revenueFromOperations']==400
