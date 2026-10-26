from copy import deepcopy
import pytest
from backend.premium_presentation import build_report_review
from backend.tests.test_premium_trace import DATA, report_for


@pytest.mark.parametrize('stock', DATA['stocks'], ids=lambda s:s['symbol'])
def test_review_accounts_for_every_factor_without_changing_rating(stock):
    report = report_for(stock)
    before = deepcopy(report)
    review = build_report_review(report)
    for part in review['parts']:
        source = {r['metric']: r for r in report['rating']['metrics'] if r['part'] == part['key']}
        seen = []
        for bucket in ('pros','cons','mixed','unavailable','notApplicable'):
            for item in part[bucket]:
                row = source[item['metric']]
                seen.append(item['metric'])
                if bucket == 'pros': assert row['status'] in ('A','S','Z') and row['points'] >= 70
                if bucket == 'cons': assert row['status'] in ('A','S','Z') and row['points'] < 40
                if bucket == 'mixed': assert 40 <= row['points'] < 70
                if bucket == 'unavailable': assert row['status'] in ('F','L')
        assert sorted(seen) == sorted(source)
    assert report == before


def test_missing_zero_and_substituted_data_are_not_misrepresented():
    report = report_for(DATA['stocks'][0])
    base = report['rating']['metrics'][0]
    def row(metric, points, status, value, **extra):
        return dict(base, part='risk', metric=metric, label=metric, points=points, status=status, value=value, unit='%', **extra)
    report['rating']['metrics'] = [row('PLEDGE',100,'A',0), row('CAPITAL_ADEQUACY',50,'F',None),
        row('TRADING_VALUE',None,'L',None), row('ROA',39.99,'A',.48), row('ROE',40,'A',8),
        row('VOLATILITY',69.99,'A',30), row('PB_VS_HISTORY',70,'S',.9)]
    part = build_report_review(report)['parts'][-1]
    assert {r['metric'] for r in part['pros']} == {'PLEDGE','PB_VS_HISTORY'}
    assert part['pros'][0]['valueText'] == '0.00%'
    assert 'No promoter shares' in part['pros'][0]['summary']
    assert 'industry' in part['pros'][1]['label']
    assert 'company history is unavailable' in part['pros'][1]['summary']
    assert {r['metric'] for r in part['cons']} == {'ROA'}
    assert {r['metric'] for r in part['mixed']} == {'ROE','VOLATILITY'}
    assert {r['metric'] for r in part['unavailable']} == {'CAPITAL_ADEQUACY','TRADING_VALUE'}
    assert 'estimate' in part['unavailable'][0]['summary']


def test_zero_interest_expense_is_not_described_as_a_loss():
    report = report_for(DATA['stocks'][0])
    base = report['rating']['metrics'][0]
    report['rating']['metrics'] = [dict(base, part='quality', metric='INTEREST_COVER', label='Interest cover', value=None, points=100, status='A', details={})]
    part = build_report_review(report)['parts'][2]
    assert part['pros'][0]['summary'] == 'No interest expense is reported for the year.'
