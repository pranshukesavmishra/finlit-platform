"""Owner-confirmed assets/equity scale and shared reported/calculated inputs."""
from copy import deepcopy
from datetime import date
import pytest

from backend.premium_data import adapt_inputs
from backend.premium_engine import insurance_leverage_score,score_company
from backend.premium_presentation import build_report_review
from backend.premium_trace import build_calculation_trace
from backend.tests.test_premium_bank_fallbacks import inputs


@pytest.mark.parametrize('leverage,expected',[(0,100),(4,100),(5,100),(8,80),(12,53.33),(12.5,50),(19,6.67),(20,0),(33.41,0)])
def test_owner_linear_function_including_boundaries_and_rounding(leverage,expected):
    assert insurance_leverage_score(leverage*100,100)==expected


@pytest.mark.parametrize('assets,equity',[(100,0),(100,-10),(None,10),(100,None),(-1,10),(float('nan'),10)])
def test_invalid_or_missing_inputs_do_not_become_a_positive_leverage_score(assets,equity):
    assert insurance_leverage_score(assets,equity) is None


def test_insurance_replaces_interest_cover_preserves_slot_and_exposes_formula():
    d=inputs();d.update(total_assets=12000,net_worth=1000,interest_cost=None)
    before=deepcopy(d)
    rating=score_company(d,'INSURANCE')
    rows={row['metric']:row for row in rating['metrics']}
    leverage=rows['FINANCIAL_LEVERAGE']
    assert leverage['value']==12 and leverage['points']==53.33
    assert leverage['weight']==50 and leverage['share']==.5 and leverage['unit']=='x'
    assert (leverage['worst'],leverage['best'])==(20,5)
    assert 'INTEREST_COVER' not in rows and 'SOLVENCY' not in rows
    assert rating['coverage']['quality']==1
    trace=build_calculation_trace(d,rating,{})
    record=next(row for row in trace['metrics'] if row['metric']=='FINANCIAL_LEVERAGE')
    assert 'Total assets / book equity' in record['valueCalculation']
    assert sum(row['pointsEarned'] for row in rating['metrics'])-rating['capPointsLost']==pytest.approx(rating['final'])
    assert d==before


@pytest.mark.parametrize('equity',[0,-1000])
def test_nonpositive_equity_is_flagged_not_filled_even_if_reported_leverage_exists(equity):
    d=inputs();d.update(total_assets=10000,net_worth=equity,financial_leverage=5)
    rating=score_company(d,'INSURANCE')
    row=next(row for row in rating['metrics'] if row['metric']=='FINANCIAL_LEVERAGE')
    assert row['points'] is None and row['status']=='L'
    assert row['statusLabel']=='Invalid input' and row['details']['invalid']
    assert rating['dataIntegrityStatus']=='REVIEW REQUIRED'
    assert any('financial distress' in alert for alert in rating['alerts'])
    review=build_report_review({'inputs':d,'rating':rating,'inputMeta':{}})
    item=next(item for part in review['parts'] for item in part['unavailable'] if item['metric']=='FINANCIAL_LEVERAGE')
    assert item['valueText']=='Invalid'
    gap=next(item for item in review['completeness']['items'] if item['metric']=='FINANCIAL_LEVERAGE')
    assert 'no estimate' in gap['treatment']


def test_finedge_reported_then_calculation_then_upstox_without_mixing_balance_dates():
    raw={'profile':{'industry':'Insurance'},'balance':{'financials':[{'period_end':20260331,'totalAssets':1_200_000_000,'totalEquity':100_000_000}]},
         'leverage':{'ratios':[{'header':'TTM','year':2026,'financialLeverage':8}]},'secondaryLeverage':18}
    def adapt():return adapt_inputs(raw,'TEST',date(2026,10,26),'consolidated')[0]
    assert adapt()['financial_leverage']==8
    raw['leverage']={}
    assert adapt()['financial_leverage']==12
    raw['balance']={}
    assert adapt()['financial_leverage']==18
    raw['secondaryLeverage']=None
    assert adapt()['financial_leverage'] is None


def test_npa_placeholders_do_not_erase_reported_capital_adequacy():
    raw={'profile':{'industry':'Banks'},'quarterly':{'financials':[{'period_end':20260930,'capitalAdequacyRatio':.18,
         'percentageOfGrossNpa':0,'percentageOfNpa':0,'cET1Ratio':0}]}}
    d,*_=adapt_inputs(raw,'BANK',date(2026,10,26),'consolidated')
    assert d['capital_adequacy_pct']==18
    assert d['gross_npa_pct'] is None
