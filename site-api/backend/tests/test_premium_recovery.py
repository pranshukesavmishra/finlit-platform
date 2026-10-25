from copy import deepcopy
from datetime import date, timedelta
import pytest
from backend.fundamental_resolution import recover_inputs, statement_rows
from backend.premium_data import adapt_inputs

ASOF = date(2026, 10, 18)


def payload(kind='income', basis='consolidated'):
    return {'type': basis, 'time_period': 'yearly', 'units_in': 'crore', 'full_statement': [
        {'particular': 'Cash flow from Operations' if kind == 'cashflow' else 'Revenue',
         'history': [{'period':'Mar 2025','value':400.47}, {'period':'Mar 2023','value':832.03}]}]}


def test_recovery_fixes_misdated_annual_cf_without_treating_quarter_as_year():
    raw = {'annual': {'financials':[{'period_end':20250331,'revenueFromOperations':100}]},
           'cashflow': {'financials':[{'period_start':20250101,'period_end':20250331,'cashFlowsFromOperatingActivities':1}]}}
    out, events = recover_inputs(raw, 'consolidated', ASOF, lambda k: payload('cashflow') if k=='cashflow' else None)
    d,*_ = adapt_inputs(out,'TEST',ASOF,'consolidated')
    assert d['operating_cash_flow_y']==[400.47]
    assert raw['cashflow']['financials'][0]['period_start']==20250101
    assert any('2025-03-31' in e and 'publication dates' in e for e in events)


def test_recovery_extends_history_but_preserves_actual_zero_and_aliases():
    raw = {'annual': {'financials':[{'period_start':20240401,'period_end':20250331,'revenueFromOperations':0}]}}
    out, events = recover_inputs(raw,'consolidated',ASOF,lambda k:payload() if k=='annual' else None)
    d,*_ = adapt_inputs(out,'TEST',ASOF,'consolidated')
    assert d['sales_y']==[832.03,None,0]
    assert len(raw['annual']['financials'])==1


@pytest.mark.parametrize('change',[{'type':'standalone'},{'units_in':'million'},{'time_period':'quarterly'}])
def test_incompatible_financial_basis_units_or_duration_cannot_fill(change):
    p=payload(); p.update(change)
    assert statement_rows(p,'consolidated')==[]


def test_whole_exchange_risk_series_replaces_gaps_without_splicing():
    candles=[{'date':(ASOF-timedelta(days=300-i)).isoformat(),'close':100+i,'volume':1000} for i in range(300)]
    raw={'prices':{'price':[{'date':c['date'],'close':0,'volume':1} for c in candles]}}
    out, events=recover_inputs(raw,'consolidated',ASOF,lambda k:{'prices':candles,'exchange':'NSE','instrumentKey':'NSE_EQ|TEST'} if k=='prices' else None)
    d,*_=adapt_inputs(out,'TEST',ASOF,'consolidated')
    assert d['biggest_fall_pct']==0
    assert d['volatility_pct'] is not None and d['trading_value_cr']>0
    assert out['prices']['price']==candles
    assert any('NSE' in e for e in events)
    bad=deepcopy(candles);bad[-3]['close']=0
    unchanged,_=recover_inputs(raw,'consolidated',ASOF,lambda k:{'prices':bad} if k=='prices' else None)
    assert unchanged==raw


def test_bank_revenue_is_not_replaced_by_upstox_gross_revenue():
    raw={'profile':{'industry':'Banks','sector':'Financial Services'}}
    out,_=recover_inputs(raw,'consolidated',ASOF,lambda k:payload())
    assert 'annual' not in out


def test_provider_failure_keeps_original_data_and_reports_unavailability():
    def fail(k): raise TimeoutError()
    raw={'annual':[]}
    out,events=recover_inputs(raw,'consolidated',ASOF,fail)
    assert out==raw
    assert any('unavailable' in e for e in events)
