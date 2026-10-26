import json
from pathlib import Path
from copy import deepcopy
import pytest
from backend.premium_engine import score_company
from backend.premium_model_config import GROUPS
from backend.premium_presentation import build_report_review
from backend.premium_trace import build_calculation_trace


def inputs():
    d = json.loads(Path(__file__).with_name('premium_example.json').read_text())
    d.update(loans_now=120,loans_1y_ago=100,gross_npa_pct=2,net_npa_pct=.5,capital_adequacy_pct=15,total_assets=10000,industry_median_pb=2,own_5y_median_pb=2)
    return d


def rows(d, group='BANK'):
    return {r['metric']:r for r in score_company(d,group)['metrics']}


def test_bank_uses_industry_pe_when_available_and_keeps_original_slot_weight():
    d=inputs(); r=rows(d)
    assert 'PE_VS_INDUSTRY' in r and 'PE_VS_HISTORY' not in r
    assert r['PE_VS_INDUSTRY']['weight']==30
    d['industry_median_pe']=None
    r=rows(d)
    assert 'PE_VS_INDUSTRY' not in r
    assert r['PE_VS_HISTORY']['status']=='A'
    assert r['PE_VS_HISTORY']['fallbackFor']=='PE_VS_INDUSTRY'
    assert r['PE_VS_HISTORY']['weight']==30
    result=score_company(d,'BANK')
    review=build_report_review({'rating':result,'inputMeta':{},'statementType':'consolidated'})
    factor=next(item for part in review['parts'] for bucket in ('pros','cons','mixed') for item in part[bucket] if item['metric']=='PE_VS_HISTORY')
    assert 'Company history is used' in factor['summary']
    trace=build_calculation_trace(d,result,{})
    assert 'Replaces unavailable PE_VS_INDUSTRY' in next(r for r in trace['metrics'] if r['metric']=='PE_VS_HISTORY')['valueCalculation']


@pytest.mark.parametrize('missing',[None,0,-1])
def test_bank_keeps_missing_industry_slot_if_history_also_unavailable(missing):
    d=inputs();d.update(industry_median_pe=missing,own_5y_median_pe=None)
    r=rows(d)
    assert r['PE_VS_INDUSTRY']['status']=='F'
    assert 'PE_VS_HISTORY' not in r


def test_bank_does_not_treat_a_zero_loss_score_as_missing_or_mutate_shared_config():
    before=deepcopy(GROUPS)
    d=inputs();d.update(eps_q=[-1]*14,industry_median_pe=None)
    r=rows(d)
    assert r['PE_VS_INDUSTRY']['status']=='Z' and r['PE_VS_INDUSTRY']['points']==0
    assert 'PE_VS_HISTORY' not in r
    score_company(inputs(),'BANK')
    assert GROUPS==before


def test_nbfc_does_not_use_bank_fallback():
    d=inputs();d['industry_median_pe']=None
    r=rows(d,'NBFC')
    assert r['PE_VS_INDUSTRY']['status']=='F'
    assert 'PE_VS_HISTORY' not in r


@pytest.mark.parametrize('group,weight', [('BANK',25),('NBFC',25)])
@pytest.mark.parametrize('original', [None,0,18])
def test_financial_quality_always_replaces_original_factor(group,weight,original):
    d=inputs();d.update(capital_adequacy_pct=original,solvency_ratio=original,profit_before_tax=400,interest_cost=100,total_debt=0)
    result=score_company(d,group);r={r['metric']:r for r in result['metrics']}
    assert 'CAPITAL_ADEQUACY' not in r and 'SOLVENCY' not in r
    cover=r['INTEREST_COVER']
    assert cover['value']==5 and cover['points']==50
    assert cover['weight']==weight and cover['share']==weight/100
    assert not cover['fallbackFor'] and cover['status']=='A'
    assert cover['unit']=='x' and (cover['worst'],cover['best'])==(2,8)
    review=build_report_review({'rating':result,'inputMeta':{},'statementType':'consolidated'})
    item=next(i for b in ['pros','cons','mixed'] for i in review['parts'][2][b] if i['metric']=='INTEREST_COVER')
    assert 'unavailable' not in item['label'].lower()
    trace=build_calculation_trace(d,result,{})
    assert 'Annual PBT + interest cost' in next(i for i in trace['metrics'] if i['metric']=='INTEREST_COVER')['valueCalculation']
    assert sum(i['pointsEarned'] for i in result['metrics'])-result['capPointsLost']==pytest.approx(result['final'])


@pytest.mark.parametrize('group', ['BANK','NBFC'])
@pytest.mark.parametrize('interest,pbt,value,points',[(100,100,2,0),(100,400,5,50),(100,700,8,100),(100,-100,0,0),(0,100,None,100)])
def test_financial_interest_cover_formula_and_approved_scale(group,interest,pbt,value,points):
    d=inputs();d.update(profit_before_tax=pbt,interest_cost=interest)
    cover=rows(d,group)['INTEREST_COVER']
    assert cover['value']==value and cover['points']==points and cover['status']=='A'


@pytest.mark.parametrize('group', ['BANK','NBFC'])
@pytest.mark.parametrize('interest,pbt',[(None,100),(100,None),(None,None),(-10,100)])
def test_financial_missing_interest_is_filled_even_when_original_factor_exists(group,interest,pbt):
    d=inputs();d.update(capital_adequacy_pct=18,solvency_ratio=2,interest_cost=interest,profit_before_tax=pbt)
    result=score_company(d,group);r={r['metric']:r for r in result['metrics']}
    assert 'CAPITAL_ADEQUACY' not in r and 'SOLVENCY' not in r
    assert r['INTEREST_COVER']['status']=='F'
    assert result['coverage']['quality']==.75


@pytest.mark.parametrize('roe,points',[(8,0),(13,50),(18,100),(0,0),(-5,0)])
def test_bank_uses_roe_only_for_unavailable_industry_pb_in_same_valuation_slot(roe,points):
    d=inputs();d.update(industry_median_pb=None,net_worth=1000,net_profit_y=[20,30,40,roe*10])
    result=score_company(d,'BANK');r={r['metric']:r for r in result['metrics']}
    assert 'PB_VS_INDUSTRY' not in r
    assert r['ROE']['part']=='valuation' and r['ROE']['weight']==40
    assert r['ROE']['value']==pytest.approx(roe) and r['ROE']['points']==points
    assert r['ROE']['unit']=='%' and r['ROE']['fallbackFor']=='PB_VS_INDUSTRY'
    assert r['ROE']['status']=='A' and (r['ROE']['worst'],r['ROE']['best'])==(8,18)
    assert r['PB_VS_HISTORY']['weight']==30
    assert result['coverage']['valuation']==1
    review=build_report_review({'rating':result,'inputMeta':{},'statementType':'consolidated'})
    part=review['parts'][1]
    item=next(i for b in ['pros','cons','mixed'] for i in part[b] if i['metric']=='ROE')
    assert item['label']=='Return on equity (industry P/B unavailable)'
    assert 'industry P/B comparison' in item['summary']
    trace=build_calculation_trace(d,result,{})
    item=next(i for i in trace['metrics'] if i['metric']=='ROE')
    assert 'Replaces unavailable PB_VS_INDUSTRY' in item['valueCalculation']
    assert 'owner-attributable profit' in item['valueCalculation']


def test_bank_keeps_primary_pb_even_when_roe_would_be_better_and_preserves_loss_rule():
    d=inputs();d.update(net_worth=1000,net_profit_y=[100,150,180,300])
    assert 'ROE' not in rows(d)
    d.update(net_worth=-1000,industry_median_pb=None)
    r=rows(d)
    assert r['PB_VS_INDUSTRY']['status']=='Z' and r['PB_VS_INDUSTRY']['points']==0
    assert 'ROE' not in r


@pytest.mark.parametrize('profit,equity',[([],1000),([100,None],1000),([100],None)])
def test_bank_keeps_pb_missing_if_roe_cannot_be_calculated(profit,equity):
    d=inputs();d.update(industry_median_pb=None,net_profit_y=profit,net_worth=equity)
    r=rows(d)
    assert 'ROE' not in r
    assert r['PB_VS_INDUSTRY']['status']=='F'


def test_bank_valuation_fallbacks_and_financial_quality_replacement_reconcile():
    before=deepcopy(GROUPS)
    d=inputs();d.update(industry_median_pe=None,industry_median_pb=None,capital_adequacy_pct=None,interest_cost=100,profit_before_tax=400)
    result=score_company(d,'BANK');r={r['metric']:r for r in result['metrics']}
    assert r['PE_VS_HISTORY']['fallbackFor']=='PE_VS_INDUSTRY'
    assert r['ROE']['fallbackFor']=='PB_VS_INDUSTRY'
    assert r['INTEREST_COVER']['fallbackFor'] is None
    assert sum(i['pointsEarned'] for i in result['metrics'])-result['capPointsLost']==pytest.approx(result['final'])
    assert not {'PE_VS_INDUSTRY','PB_VS_INDUSTRY','CAPITAL_ADEQUACY'} & r.keys()
    other=rows(d,'NBFC')
    assert not {'ROE','PE_VS_HISTORY'} & other.keys()
    assert other['INTEREST_COVER']['points']==50
    assert other['PB_VS_INDUSTRY']['status']=='F'
    assert GROUPS==before


# Insurers: the Quality pillar uses financial leverage (total assets / book equity, lower is better) instead of interest cover.
def ins(**kw):
    d=inputs();d.update(solvency_ratio=2,profit_before_tax=400,interest_cost=100,total_assets=1000,net_worth=100,net_profit_y=[10,12,14,13]);d.update(kw)
    return d


def test_insurer_quality_uses_financial_leverage_not_interest_cover():
    d=ins();result=score_company(d,'INSURANCE');r={x['metric']:x for x in result['metrics']}
    assert 'INTEREST_COVER' not in r and 'SOLVENCY' not in r
    lev=r['FINANCIAL_LEVERAGE']
    assert lev['value']==pytest.approx(10) and lev['unit']=='x' and (lev['worst'],lev['best'])==(20,6)
    assert lev['points']==pytest.approx(100*(20-10)/(20-6)) and lev['status']=='A'
    assert lev['weight']==50 and r['ROE']['weight']==50
    review=build_report_review({'rating':result,'inputMeta':{},'statementType':'consolidated'})
    item=next(i for b in ['pros','cons','mixed'] for i in review['parts'][2][b] if i['metric']=='FINANCIAL_LEVERAGE')
    assert item['label']=='Financial leverage' and 'unavailable' not in item['label'].lower()
    assert 'Total assets / book equity' in next(i for i in build_calculation_trace(d,result,{})['metrics'] if i['metric']=='FINANCIAL_LEVERAGE')['valueCalculation']
    assert sum(i['pointsEarned'] for i in result['metrics'])-result['capPointsLost']==pytest.approx(result['final'])


@pytest.mark.parametrize('assets,points',[(2000,0),(3000,0),(600,100),(400,100)])
def test_insurer_financial_leverage_scale_ends(assets,points):
    assert rows(ins(total_assets=assets),'INSURANCE')['FINANCIAL_LEVERAGE']['points']==points


@pytest.mark.parametrize('equity',[0,-50])
def test_insurer_non_positive_equity_gives_zero_leverage_points(equity):
    lev=rows(ins(net_worth=equity),'INSURANCE')['FINANCIAL_LEVERAGE']
    assert lev['points']==0 and lev['value'] is None


@pytest.mark.parametrize('field',['total_assets','net_worth'])
def test_insurer_missing_balance_sheet_input_is_unavailable_and_disclosed(field):
    from backend.premium_completeness import build_input_completeness
    d=ins(**{field:None});result=score_company(d,'INSURANCE')
    assert {x['metric']:x for x in result['metrics']}['FINANCIAL_LEVERAGE']['status']=='F'
    item={i['metric']:i for i in build_input_completeness({'inputs':d,'rating':result,'inputMeta':{}})['items']}['FINANCIAL_LEVERAGE']
    assert 'Total assets' in item['missingInputs'] or 'Book equity' in item['missingInputs']
    assert ('Total assets' if field=='total_assets' else 'Book equity') in item['missingInputs']


def test_insurer_leverage_is_insurer_only_and_other_groups_keep_interest_cover():
    d=ins()
    for g in ('BANK','NBFC','MFG'):
        r=rows(d,g)
        assert 'FINANCIAL_LEVERAGE' not in r and r['INTEREST_COVER']['value']==5 and r['INTEREST_COVER']['points']==50
