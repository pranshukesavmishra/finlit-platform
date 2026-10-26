from datetime import date
import pytest
import requests
from fastapi import HTTPException
from backend import server
from backend.fundamental_resolution import statement_rows, recover_inputs
from backend.premium_data import provider_get, adapt_inputs
from backend.premium_engine import score_company
from backend.premium_presentation import build_report_review

ASOF=date(2026,10,24)


def test_unscored_insurer_solvency_keeps_raw_value_without_affecting_quality():
    raw={'profile':{'industry':'Insurance'},'quarterly':{'financials':[{'period_end':20260630,'solvencyRatio':.0242}]}}
    inputs,group,*_=adapt_inputs(raw,'LICI',ASOF,'consolidated')
    assert inputs['solvency_ratio']==.0242
    assert not any('solvency' in c.lower() for c in inputs['rating_cautions'])
    rating=score_company(inputs,group)
    assert 'SOLVENCY' not in {r['metric'] for r in rating['metrics']}
    assert next(r for r in rating['metrics'] if r['metric']=='INTEREST_COVER')['status']=='F'


def test_metric_specific_short_history_ignores_only_leading_unreported_slots():
    data={'sales_q':[None]*7+[100,110,120,130,150,160,180], 'net_profit_q':list(range(1,15)),
          'sales_y':[100,200], 'net_profit_y':[10,20]}
    result=score_company(data,'INSURANCE')
    growth=next(r for r in result['metrics'] if r['metric']=='SALES_GROWTH')
    assert growth['status']=='A' and growth['value']==50
    assert 'Latest quarter vs same quarter' in growth['details']['basis']
    data['sales_q']=[100,110,120,130,None,150,160,180,190]
    growth=next(r for r in score_company(data,'INSURANCE')['metrics'] if r['metric']=='SALES_GROWTH')
    assert growth['status']=='F'  # genuine interior missing comparison remains missing


def test_quarterly_recovery_uses_grouped_series_and_never_annual_full_statement():
    payload={'type':'consolidated','time_period':'quarterly','units_in':'crore',
             'income_statement':[{'category':'revenue','history':[{'period':'Jun 2026','value':100}]},
                                 {'category':'net_profit','history':[{'period':'Jun 2026','value':10}]},
                                 {'category':'operating_profit','history':[{'period':'Jun 2026','value':25}]}],
             'full_statement':[{'particular':'Revenue','history':[{'period':'Mar 2026','value':9999}]},
                               {'particular':'EPS - Basic','history':[{'period':'Mar 2026','value':999}]}]}
    rows=statement_rows(payload,'consolidated',quarterly=True)
    assert len(rows)==1 and rows[0]['period_end']=='2026-06-30'
    assert rows[0]['revenueFromOperations']==1_000_000_000
    assert rows[0]['profitLossForPeriod']==100_000_000
    assert 'basicEPS' not in rows[0] and 'ebitda' not in rows[0]
    assert statement_rows({**payload,'income_statement':[]},'consolidated',quarterly=True)==[]


def test_missing_values_inside_six_annual_rows_trigger_recovery_and_keep_zero():
    rows=[{'period_end':f'{y}-03-31','revenueFromOperations':0,'profitLossForPeriod':10,'basicEPS':1} for y in range(2021,2027)]
    rows[-1].pop('revenueFromOperations')
    calls=[]
    def load(section):
        calls.append(section)
        return {'type':'consolidated','time_period':'yearly','units_in':'crore','full_statement':[
            {'particular':'Revenue','history':[{'period':'Mar 2026','value':20},{'period':'Mar 2025','value':999}]}]}
    out,_=recover_inputs({'annual':{'financials':rows}},'consolidated',ASOF,load,recover_prices=False)
    assert 'annual' in calls
    assert out['annual']['financials'][-1]['revenueFromOperations']==200_000_000
    assert out['annual']['financials'][-2]['revenueFromOperations']==0


def test_interior_history_gap_triggers_recovery_even_with_fourteen_raw_rows():
    dates=['2023-03-31','2023-06-30','2023-09-30','2023-12-31','2024-03-31','2024-06-30','2024-09-30','2024-12-31',
           '2025-03-31','2025-06-30','2025-09-30','2025-12-31','2026-03-31','2026-06-30']
    rows=[{'period_end':d,'revenueFromOperations':10,'profitLossForPeriod':1} for d in dates]
    rows[9]['period_end']='2019-03-31'
    calls=[]
    def load(section):
        calls.append(section)
        return {'type':'consolidated','time_period':'quarterly','units_in':'crore','income_statement':[
            {'category':'revenue','history':[{'period':'Jun 2025','value':20}]}, {'category':'net_profit','history':[{'period':'Jun 2025','value':2}]}]}
    out,_=recover_inputs({'quarterly':{'financials':rows}},'consolidated',ASOF,load,period='quarterly',recover_prices=False)
    assert 'quarterly' in calls
    assert any(r['period_end']=='2025-06-30' for r in out['quarterly']['financials'])


def test_sentinel_quote_date_is_rejected_for_dated_price_fallback():
    bad={'SOLARINDS':{'current_price':19780.3,'tradetime':'0001-01-01T00:00:00Z'}}
    assert server._quote_from_finedge_quote(bad,'SOLARINDS')=={}
    assert server._parse_market_date('0001-01-01') is None
    assert server._derive_dividend_yield([],19780.3,'0001-01-01') is None
    good={'SOLARINDS':{'current_price':19780.3,'tradetime':'2026-10-23T15:30:00Z'}}
    assert server._quote_from_finedge_quote(good,'SOLARINDS')['price']==19780.3


def test_shared_finedge_retries_transient_errors_once_per_provider_budget(monkeypatch):
    calls=[]
    def once(*args):
        calls.append(args)
        if len(calls)<3:raise HTTPException(502,'temporary')
        return {'available':True}
    monkeypatch.setattr(server,'_finedge_get_once',once)
    monkeypatch.setattr(server,'sleep',lambda *_:None)
    assert provider_get(server._finedge_get,'/test',{})=={'available':True}
    assert len(calls)==3


@pytest.mark.parametrize('status',[400,401,403,404])
def test_provider_auth_and_request_errors_are_not_retried(monkeypatch,status):
    calls=[]
    def once(*a):
        calls.append(a);raise HTTPException(status,'unavailable')
    monkeypatch.setattr(server,'_finedge_get_once',once)
    with pytest.raises(HTTPException) as caught:server._finedge_get('/test')
    assert caught.value.status_code==status and len(calls)==1


def test_exhausted_transport_errors_are_sanitized_and_not_retried_again(monkeypatch):
    calls=[]
    def once(*args):
        calls.append(args);raise requests.exceptions.Timeout('provider URL contains secret')
    monkeypatch.setattr(server,'_finedge_get_once',once)
    monkeypatch.setattr(server,'sleep',lambda *_:None)
    with pytest.raises(HTTPException) as caught:provider_get(server._finedge_get,'/test',{})
    assert len(calls)==3 and caught.value.status_code==502
    assert 'secret' not in caught.value.detail
