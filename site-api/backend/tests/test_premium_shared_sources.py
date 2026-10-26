"""Contract tests: reports must consume the dashboard's resolved observations."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import calendar
import json
from pathlib import Path
import pytest
from backend import server, premium_service
from backend.premium_benchmarks import peer_benchmark, derive_peer_ev_ebitda
from backend.fundamental_resolution import derive_finedge, recover_inputs, balance_rows

ASOF = date(2026,10,18)


def test_direct_finedge_then_calculation_then_secondary_provider():
    row={'period_end':20260331,'revenueFromOperations':0,'totalRevenue':500,'otherIncome':20,
         'profitBeforeTax':100,'currentTax':12,'deferredTax':8,
         'shortTermBorrowings':30,'longTermBorrowings':70}
    resolved,notes=derive_finedge({'annual':{'financials':[row]}})
    actual=resolved['annual']['financials'][0]
    assert actual['revenueFromOperations']==0
    assert actual['profitLossForPeriod']==80
    assert actual['borrowings']==100
    assert 'profitLossForPeriod' not in row
    secondary={'type':'consolidated','time_period':'yearly','units_in':'crore',
        'full_statement':[{'particular':'Profit After Tax','history':[{'period':'Mar 2026','value':999}]}]}
    out,_=recover_inputs({'annual':{'financials':[row]}},'consolidated',ASOF,lambda k:secondary)
    assert out['annual']['financials'][0]['profitLossForPeriod']==80
    assert any('Calculated FinEdge' in note for note in notes)


def test_annual_calculation_requires_four_comparable_quarters():
    quarters=[]
    for end,start in [(20250630,20250401),(20250930,20250701),(20251231,20251001),(20260331,20260101)]:
        quarters.append({'period_end':end,'period_start':start,'revenueFromOperations':10})
    raw={'quarterly':{'financials':quarters},'annual':{'financials':[{'period_end':20260331}]}}
    out,_=derive_finedge(raw)
    assert out['annual']['financials'][0]['revenueFromOperations']==40
    raw['quarterly']['financials'][0]['period_start']=20250101
    out,_=derive_finedge(raw)
    assert 'revenueFromOperations' not in out['annual']['financials'][0]


def test_unrecoverable_bad_duration_is_na_in_shared_table():
    raw={'annual':{'financials':[{'period_end':20260331,'period_start':20260101,'revenueFromOperations':12}]}}
    out,notes=recover_inputs(raw,'consolidated',ASOF,lambda k:None)
    assert out['annual']['financials']==[]
    assert any('inconsistent duration' in note for note in notes)


def test_upstox_balance_equity_is_reconciled_and_does_not_invent_debt_or_cash():
    p={'type':'consolidated','units_in':'crore','history':[{'period':'Mar 2026','total_asset':100,'total_liability':40}],
       'full_statement':[{'particular':'Equity Capital','history':[{'period':'Mar 2026','value':60}]}]}
    r=balance_rows(p,'consolidated')[0]
    assert r['totalEquity']==600_000_000
    assert 'borrowings' not in r and 'cash' not in r
    assert balance_rows(p,'standalone')==[]


def test_bank_npa_uses_exact_dashboard_disclosure_with_basis_label():
    from backend.premium_data import adapt_inputs
    raw={'profile':{'industry':'Banks'},'quarterly':{'financials':[{'period_end':20260630,'percentageOfNpa':0,'percentageOfGrossNpa':0,'cET1Ratio':0}]},
         'asset_quality':{'financials':[{'period_end':20260630,'percentageOfNpa':0,'percentageOfGrossNpa':.0111,'cET1Ratio':.18}]},'asset_quality_basis':'standalone'}
    d,_,_,meta,notes,_=adapt_inputs(raw,'BANK',ASOF,'consolidated')
    dashboard=server._normalize_bank_asset_quality_history(raw['asset_quality']['financials'],'quarterly')
    assert d['gross_npa_pct']==dashboard[0]['history'][0]['value']==1.11
    assert d['net_npa_pct']==0
    assert d['capital_adequacy_pct'] is None  # CET1 is not total CRAR.
    assert meta['assetQualityStatementType']=='standalone'
    assert any('standalone' in n for n in notes)


def test_large_industry_fetch_is_complete_cached_and_does_not_hide_missing_peers():
    calls=[]
    def get(path,params):
        calls.append(path)
        return {'price_ratios':[{'quote_date':'2026-10-16','pe':20,'pb':2}]}
    peers={'peers':[f'S{i}' for i in range(101)]}
    result,meta=peer_benchmark(get,peers,'consolidated',ASOF)
    assert result['industry_median_pe']==20 and meta['fetchedCount']==101
    peer_benchmark(get,peers,'consolidated',ASOF)
    assert len(calls)==101
    def missing(path,params):return {} if path.endswith('/S0') else get(path,params)
    result,meta=peer_benchmark(missing,peers,'consolidated',ASOF)
    assert result=={'industry_median_pe':20,'industry_median_pb':2}
    assert meta['metrics']['industry_median_pe']['partial']
    assert meta['metrics']['industry_median_pe']['observedCount']==100
    assert meta['missingSymbols']==['S0']


def test_report_generation_reads_the_dashboard_results_and_cache(monkeypatch):
    data=json.loads((Path(__file__).parent/'fixtures'/'premium_stock_audit_2026_10_18.json').read_text())['stocks'][0]
    raw=data['raw'];symbol=data['symbol']
    instrument={'symbol':symbol,'name':symbol,'isin':'INE000A01010','instrumentKey':symbol}
    monkeypatch.setattr(server,'_resolve_finedge_stock',lambda q:instrument)
    monkeypatch.setattr(server,'_try_resolve_upstox_instrument',lambda *q:{**instrument,'instrumentKey':'NSE_EQ|INE000A01010','exchange':'NSE'})
    monkeypatch.setattr(server,'_stock_fundamentals_cache',{})
    upstox_ratios=[{'name':'P/E','company_value':999,'sector_value':25}, {'name':'P/B','company_value':888,'sector_value':3}]
    monkeypatch.setattr(server,'_safe_upstox_get',lambda path,*a,**k:upstox_ratios if path.endswith('/key-ratios') else {})
    candles=[{'date':(ASOF-timedelta(days=300-i)).isoformat(),'close':100+i,'volume':1000} for i in range(300)]
    monkeypatch.setattr(server,'_fetch_upstox_price_history',lambda key:deepcopy(candles))
    def statement(s,b,c,p):
        section={'pl':'annual' if p=='yearly' else 'quarterly','bs':'balance' if p=='yearly' else 'balance_recent','cf':'cashflow'}[c]
        return deepcopy(raw.get(section,{}).get('financials',[]))
    monkeypatch.setattr(server,'_finedge_statement',statement)
    def get(path,params=None):
        if path.startswith('/company-profile/'):return deepcopy(raw['profile'])
        if path.startswith('/daily-quotes/'):return deepcopy(raw['prices'])
        if path=='/quote':return deepcopy(raw['quote'])
        if path.startswith('/shareholdings/'):
            return deepcopy(raw.get({'summary':'summary','distribution':'distribution','declaration':'declaration'}.get(path.split('/')[2],''),{}))
        return {}
    monkeypatch.setattr(server,'_finedge_get',get)
    monkeypatch.setattr('backend.premium_benchmarks.peer_benchmark',lambda *a:({},{}))
    yearly=server._fetch_stock_fundamentals(symbol,'consolidated','yearly')
    quarterly=server._fetch_stock_fundamentals(symbol,'consolidated','quarterly')
    report=premium_service.generate_report(get,symbol,symbol,'consolidated','r'*32,'2026-10-18',server._premium_dashboard_inputs)
    assert report['inputs']['price']==yearly['quote']['price']
    assert report['inputMeta']['dashboardSources']['yearly']==yearly['sources']
    assert report['inputMeta']['dashboardSources']['quarterly']==quarterly['sources']
    capture=server._stock_fundamentals_cache[f'finedge:{symbol}:consolidated:yearly']['model_inputs']
    assert capture['prices']['price']==yearly['priceHistory']
    assert capture['income']['financials']
    assert report['inputs']['industry_median_pe']==25
    assert report['inputs']['industry_median_pb']==3
    assert report['benchmark']['reportedObservations']==yearly['valuationBenchmarks']==capture['benchmarkObservations']
    assert next(r for r in yearly['ratios'] if r['name']=='P/E')['company_value']!=999
    assert next(r for r in yearly['ratios'] if r['name']=='P/E')['sector_value']==25
    assert all('model_inputs' not in key for key in yearly)


def test_missing_peer_ratio_is_calculated_from_finedge_before_na():
    from backend.premium_benchmarks import derive_peer_price_ratios
    quarters=[{'period_end':end,'basicEPS':2} for end in (20250930,20251231,20260331,20260630)]
    def get(path,params):
        if path=='/quote':return {'PEER':{'current_price':40,'market_cap':200,'tradetime':'2026-10-16'}}
        if params['statement_code']=='pl':return {'financials':quarters}
        return {'financials':[{'period_end':20260630,'totalEquity':1_000_000_000}]}
    row=derive_peer_price_ratios(get,'PEER','consolidated',ASOF)
    assert row['pe']==5 and row['pb']==2
    assert row['source']=='calculated_finedge_quote_and_financials'


def test_peer_enterprise_multiple_needs_complete_same_definition_inputs():
    raw={'quote':{'PEER':{'current_price':40,'market_cap':200,'tradetime':'2026-10-16'}},
         'quarterly':{'financials':[{'period_end':end,'ebitda':50_000_000} for end in (20250930,20251231,20260331,20260630)]},
         'balance_recent':{'financials':[{'period_end':20260630,'borrowings':400_000_000,'cashAndCashEquivalents':200_000_000}]}}
    assert derive_peer_ev_ebitda(raw,'PEER','consolidated',ASOF)==11
    del raw['balance_recent']['financials'][0]['cashAndCashEquivalents']
    assert derive_peer_ev_ebitda(raw,'PEER','consolidated',ASOF) is None


def test_missing_industry_pb_cannot_be_covered_by_pe_observation():
    def get(path,params):
        if path=='/quote':return {}
        return {'price_ratios':[{'quote_date':'2026-10-16','pe':20,'pb':None}]}
    data,meta=peer_benchmark(get,{'peers':['A','B','C','D','E']},'consolidated',ASOF)
    assert data=={'industry_median_pe':20}
    assert meta['fetchedCount']==5


def test_finedge_ratio_actual_precedes_calculated_and_zero_roe_is_preserved():
    ratios=[{'name':'ROE','company_value':0,'sector_value':None}]
    income={'income_statement':[{'category':'net_profit','history':[{'period':'2026','value':100}]}]}
    balance={'balance_sheet':[{'category':'equity','history':[{'period':'2026','value':500}]}]}
    out=server._reconcile_valuation_ratios(ratios,{'marketCap':1000},income,balance)
    assert next(r for r in out if r['name']=='ROE')['company_value']==0
