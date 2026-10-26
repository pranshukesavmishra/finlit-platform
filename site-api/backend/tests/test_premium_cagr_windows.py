from math import isfinite
import pytest
from backend.premium_engine import score_company
from backend.premium_presentation import build_report_review
from backend.premium_trace import build_calculation_trace


def scored(sales, profit=None):
    data={'sales_y':sales,'net_profit_y':sales if profit is None else profit}
    rating=score_company(data,'MFG')
    return data,rating,{r['metric']:r for r in rating['metrics']}


@pytest.mark.parametrize('values,years,previous',[
    ([100,110,121,133.1,146.41,161.051],5,100),
    ([1,100,120,144,172.8],3,100),  # four years exist; requested 3-year preference wins
    ([100,120,144,172.8],3,100),
    ([100,120,144],2,100),
    ([100,120],1,100),
    ([None,1,100,120,144,172.8],3,100),
    ([10,20,None,100,120,144],2,100),  # do not bridge the missing annual slot
    ([10,20,30,None,100,120],1,100),
])
def test_cagr_prefers_five_then_three_then_latest_consecutive_available(values,years,previous):
    _,_,rows=scored(values)
    for name in ('SALES_CAGR','PROFIT_CAGR'):
        row=rows[name]
        assert row['status']=='A' and row['details']['years']==years
        assert row['details']['previous']==previous and row['details']['current']==values[-1]
        assert row['value']==pytest.approx(((values[-1]/previous)**(1/years)-1)*100)


@pytest.mark.parametrize('values',[[],[100],[100,None],[100,None,120],[100,float('nan'),120]])
def test_cagr_needs_two_latest_consecutive_observations(values):
    data,rating,rows=scored(values)
    for name in ('SALES_CAGR','PROFIT_CAGR'):
        assert rows[name]['status']=='F' and rows[name]['details']['years']==0
        trace=next(r for r in build_calculation_trace(data,rating,{})['metrics'] if r['metric']==name)
        assert '1/0' not in trace['valueCalculation']
        assert 'two consecutive annual observations' in trace['valueCalculation']


def test_sales_and_profit_choose_their_own_available_windows():
    _,_,rows=scored([None,None,None,None,100,121],[100,110,121,133.1,146.41,161.051])
    assert rows['SALES_CAGR']['details']['years']==1 and rows['SALES_CAGR']['value']==pytest.approx(21)
    assert rows['PROFIT_CAGR']['details']['years']==5 and rows['PROFIT_CAGR']['value']==pytest.approx(10)


@pytest.mark.parametrize('values,points',[([0,100],70),([-100,100],70),([100,0],0),([100,-10],0)])
def test_short_cagr_preserves_turnaround_and_latest_loss_rules(values,points):
    _,_,rows=scored([100,110],values)
    profit=rows['PROFIT_CAGR']
    assert profit['points']==points and profit['details']['years']==1
    if values[-1]<=0:assert profit['status']=='Z'
    assert profit['value'] is None or isfinite(profit['value'])


def test_report_and_trace_disclose_selected_period_without_claiming_short_history_is_long_term():
    data,rating,_=scored([None,None,100,120,144,172.8],[None,None,None,None,100,110])
    meta={'chronology':{'annual':['2021','2022','2023','2024','2025','2026']}}
    report={'rating':rating,'inputs':data,'inputMeta':meta}
    review=build_report_review(report)
    factors={r['metric']:r for bucket in ('pros','cons','mixed') for r in review['parts'][0][bucket]}
    assert factors['SALES_CAGR']['label']=='Sales CAGR (3-year)'
    assert factors['SALES_CAGR']['comparisonText']=='Period used: 2023 to 2026.'
    assert factors['PROFIT_CAGR']['label']=='Profit CAGR (1-year)'
    assert factors['PROFIT_CAGR']['comparisonText']=='Period used: 2025 to 2026.'
    assert 'longer term' not in factors['PROFIT_CAGR']['summary'].lower()
    trace=build_calculation_trace(data,rating,meta)
    formula=next(r for r in trace['metrics'] if r['metric']=='SALES_CAGR')['valueCalculation']
    assert '(1/3)' in formula and 'latest 4 consecutive year-ends' in formula
