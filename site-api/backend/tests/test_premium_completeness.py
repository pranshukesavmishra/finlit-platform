from copy import deepcopy
import pytest
from backend.premium_completeness import build_input_completeness
from backend.premium_engine import score_company
from backend.premium_model_config import GROUPS
from backend.premium_presentation import build_report_review
from backend.tests.test_premium_trace import DATA, report_for


def report(inputs, group='INSURANCE'):
    return {'inputs':inputs,'rating':score_company(inputs,group),'inputMeta':{}}


def test_insurer_missing_expense_and_two_short_histories_are_separate():
    data={'sales_q':[100,110,120,130,140,150], 'net_profit_q':list(range(1,9)),
          'sales_y':[100,110], 'net_profit_y':[10,12,14,16], 'profit_before_tax':20}
    before=deepcopy(data)
    result=build_input_completeness(report(data))
    rows={i['metric']:i for i in result['items']}
    assert 'INTEREST_COVER' not in rows
    assert rows['FINANCIAL_LEVERAGE']['missingInputs']==['Total assets', 'Book equity']
    assert rows['SALES_STREAK']['kind']=='limitedHistory'
    assert rows['SALES_STREAK']['treatment'].startswith('2 of 10')
    assert rows['PROFIT_STREAK']['treatment'].startswith('4 of 10')
    assert 'SALES_CAGR' not in rows and 'PROFIT_CAGR' not in rows
    assert data==before


@pytest.mark.parametrize('group',GROUPS)
def test_every_unavailable_scored_factor_is_disclosed_for_every_group(group):
    sample=report({},group)
    before=deepcopy(sample)
    audit=build_input_completeness(sample)
    seen={i['metric'] for i in audit['items']}
    missing={r['metric'] for r in sample['rating']['metrics'] if r['status'] in ('F','L')}
    assert missing <= seen
    assert audit['missingFactorCount']==len(missing)
    assert all(i['reason'] and i['treatment'] and i['missingInputs'] for i in audit['items'])
    assert sample==before


def test_unknown_pledge_is_disclosed_even_though_excluded_from_scoring():
    audit=build_input_completeness(report({}))
    pledge=next(i for i in audit['items'] if i['metric']=='PLEDGE')
    assert pledge['missingInputs']==['Promoter pledged-share disclosure']
    assert pledge['treatment'].startswith('Excluded from scoring')
    assert not audit['complete']


def test_valid_zero_and_loss_rules_and_not_applicable_are_not_missing():
    sample=report({})
    base=sample['rating']['metrics'][0]
    sample['rating']['metrics']=[dict(base,metric=metric,status=status,points=points,value=value,details={})
                                for metric,status,points,value in [('PLEDGE','A',100,0),('PEG','Z',0,None),('INTEREST_COVER','N',None,None)]]
    assert build_input_completeness(sample)['complete']


def test_missing_values_include_the_actual_financial_periods():
    sample=report({'net_profit_y':[10,20,30],'operating_cash_flow_y':[None,0,None]},'MFG')
    sample['inputMeta']={'chronology':{'annual':['2024','2025','2026']}}
    item=next(i for i in build_input_completeness(sample)['items'] if i['metric']=='CASH_CONVERSION')
    assert '2024, 2026' in item['reason']
    assert '1 of 3' in item['reason']  # observed zero is available


def test_required_streak_periods_include_history_older_than_provider_response():
    sample=report({'sales_q':[100,110,120,130,140,150], 'net_profit_q':list(range(1,9))})
    # Arrays from the adapter normally share a calendar; leading holes retain
    # missing insurer premium observations while older profit is recovered.
    sample['inputs']['sales_q']=[None,None]+sample['inputs']['sales_q']
    sample['inputMeta']={'chronology':{'quarterly':['2024-09','2024-12','2025-03','2025-06','2025-09','2025-12','2026-03','2026-06']}}
    item=next(i for i in build_input_completeness(sample)['items'] if i['metric']=='SALES_STREAK')
    assert '6 of 14' in item['reason']
    assert 'missing periods: 2023-03, 2023-06' in item['reason']
    assert '2024-09, 2024-12' in item['reason']


def test_available_benchmark_does_not_hide_missing_company_eps():
    sample=report({'price':20,'industry_median_pe':15})
    item=next(i for i in build_input_completeness(sample)['items'] if i['metric']=='PE_VS_INDUSTRY')
    assert 'Trailing EPS' in item['reason']
    assert 'valuation benchmark' not in item['reason']


@pytest.mark.parametrize('stock',DATA['stocks'],ids=lambda s:s['symbol'])
def test_review_contains_complete_gap_audit_without_rescoring(stock):
    sample=report_for(stock)
    before=deepcopy(sample)
    review=build_report_review(sample)
    assert review['completeness']==build_input_completeness(sample)
    assert sample==before
