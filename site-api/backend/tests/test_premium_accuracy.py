"""Regression cases discovered by the October 2026 eight-sector data audit."""
from datetime import date
import json
from pathlib import Path

import pytest
from backend.premium_data import adapt_inputs
from backend.premium_provider import provider_get
from backend.premium_engine import score_company

AS_OF = date(2026, 10, 18)


def adapt(raw):
    return adapt_inputs(raw, 'TEST', AS_OF, 'consolidated')


def test_nbfc_net_interest_and_split_loan_fields():
    raw = {'profile': {'industry': 'Finance', 'sector': 'Non Banking Financial Company (NBFC)'},
           'quarterly': {'financials': [{'period_end': 20260630, 'interestEarned': 205127300000, 'financeCosts': 79420900000}]},
           'balance': {'financials': [{'period_end': 20260331, 'loansCurrent': 0, 'loansNoncurrent': 4989435400000},
                                      {'period_end': 20250331, 'loansCurrent': 0, 'loansNoncurrent': 4078441400000}]}}
    d, group, *_ = adapt(raw)
    assert group == 'NBFC'
    assert d['sales_q'] == [pytest.approx(12570.64)]
    assert d['loans_now'] == pytest.approx(498943.54)
    assert d['loans_1y_ago'] == pytest.approx(407844.14)


def test_insurer_maps_policyholder_premium_and_shareholder_profit_separately():
    raw = {'profile': {'industry': 'Insurance'}, 'quarterly': {'financials': [
        {'period_end': 20260930, 'netPremiumIncome': 218557900000, 'profitLossAfterTaxAndExtraordinaryItems': 5216000000,
         'surplusDeficit': 12669700000, 'solvencyRatio': 1.8}]}}
    d, group, *_ = adapt(raw)
    assert group == 'INSURANCE'
    assert d['sales_q'] == [21855.79]
    assert d['net_profit_q'] == [521.6]
    assert d['solvency_ratio'] == 1.8


def test_bank_book_equity_must_reconcile_to_balance_sheet():
    row = {'period_end': 20260331, 'capital': 15393400000, 'reserves': 5799750200000,
           'assets': 49080408400000, 'deposits': 30996382900000, 'borrowings': 5884845500000,
           'otherLiabilitiesAndProvisions': 6384036400000}
    raw = {'profile': {'industry': 'Banks'}, 'balance': {'financials': [row]}}
    d, _, _, meta, *_ = adapt(raw)
    assert d['net_worth'] == pytest.approx(581514.36)
    assert 'reconciled' in meta['provenance']['net_worth'][0]
    row['assets'] += 1_000_000_000_000
    assert adapt(raw)[0]['net_worth'] is None


def test_yoy_balance_comparison_requires_same_month_and_day():
    rows = [{'period_end': 20260930, 'loans': 400000000, 'totalEquity': 200000000},
            {'period_end': 20250930, 'loans': 200000000, 'totalEquity': 100000000},
            {'period_end': 20250331, 'loans': 50000000, 'totalEquity': 25000000}]
    raw = {'profile': {'industry': 'NBFC'}, 'balance_recent': {'financials': rows}}
    d, *_ = adapt(raw)
    assert d['loans_1y_ago'] == 20 and d['net_worth_1y_ago'] == 10
    rows.pop(1)
    assert adapt(raw)[0]['loans_1y_ago'] is None


def test_profitability_preserves_owner_model_latest_equity_and_assets():
    raw = {'profile': {'industry': 'Automobiles'},
           'annual': {'financials': [{'period_end': 20260331, 'profitLossForPeriod': 20000000}]},
           'balance': {'financials': [{'period_end': 20260331, 'totalEquity': 100000000, 'assets': 200000000}]},
           'balance_recent': {'financials': [{'period_end': 20260930, 'totalEquity': 200000000, 'assets': 400000000}]}}
    d, *_ = adapt(raw)
    rows = {r['metric']: r for r in score_company(d, 'MFG')['metrics']}
    assert d['net_worth'] == 20 and d['annual_net_worth'] == 10
    assert rows['ROE']['value'] == 10
    rows = {r['metric']: r for r in score_company(d, 'BANK')['metrics']}
    assert rows['ROA']['value'] == 5
    raw['balance'] = {}
    rows = {r['metric']: r for r in score_company(adapt(raw)[0], 'MFG')['metrics']}
    assert rows['ROE']['value'] == 10


def test_depository_receipts_are_included_only_with_reconciled_total_shares():
    raw = {'profile': {'industry': 'Oil & Gas'},
           'summary': {'summary': [{'header': 'Jun 2026', 'paidUpEquityShares': 13303071854,
                                    'outstandingDepositoryRcpts': 229466868, 'totalShares': 13532538722}]},
           'quote': {'TEST': {'current_price': 1210, 'shares': 6338512384, 'market_cap': 1637437.19, 'tradetime': '2026-10-16'}}}
    d, _, _, meta, *_ = adapt(raw)
    assert d['shares'] == pytest.approx(1353.2538722)
    assert d['price'] * d['shares'] == pytest.approx(1637437.19, abs=.1)
    assert not d['rating_cautions'][-1:] == ['Share-count discrepancies require corporate-action reconciliation.']
    assert 'depository receipts' in meta['provenance']['shares'][0]
    raw['summary']['summary'][0]['totalShares'] *= 2
    d, *_ = adapt(raw)
    assert 'Share-count discrepancies require corporate-action reconciliation.' in d['rating_cautions']


def test_future_filing_is_never_used_before_its_publication_date():
    raw = {'profile': {'industry': 'IT - Software'}, 'quarterly': {'financials': [
        {'period_end': 20260930, 'result_date': 20261020, 'revenueFromOperations': 200000000},
        {'period_end': 20260630, 'result_date': 20260715, 'revenueFromOperations': 100000000}]}}
    d, _, _, meta, *_ = adapt(raw)
    assert d['sales_q'] == [10] and meta['quarterlyAsOf'] == '2026-06-30'


def test_unknown_group_and_stale_price_cannot_receive_unrestricted_rating():
    example = json.loads(Path(__file__).with_name('premium_example.json').read_text())
    assert score_company(example, 'MFG')['status'] == 'RATED'
    example['rating_cautions'] = ['Stale price']
    assert score_company(example, 'MFG')['status'] == 'RATED'
    assert score_company(example, 'MFG')['dataIntegrityStatus'] == 'REVIEW REQUIRED'
    example['rating_blockers'] = ['Unknown group']
    result = score_company(example, 'MFG')
    assert result['status'] == 'NOT RATED' and result['final'] is None
    raw = {'profile': {'industry': 'Unclassified'}, 'quote': {'TEST': {'current_price': 100, 'tradetime': '2026-09-01'}}}
    d, *_ = adapt(raw)
    assert d['rating_blockers'] and any('freshness' in text for text in d['rating_cautions'])


def test_valuation_discrepancy_is_flagged_without_changing_documented_math():
    raw = {'profile': {'industry': 'Automobiles'},
           'quarterly': {'financials': [{'period_end': day, 'eps': 1} for day in (20250930,20251231,20260331,20260630)]},
           'quote': {'TEST': {'current_price': 100, 'tradetime': '2026-10-16'}},
           'ratios': {'price_ratios': [{'quote_date': '2026-10-16', 'pe': 10}]}}
    d, _, _, meta, *_ = adapt(raw)
    assert meta['valuationChecks']['pe']['computed'] == 25
    assert d['valuation_unverified'] == ['pe']
    d['industry_median_pe'] = 20
    rows = {r['metric']: r for r in score_company(d, 'MFG')['metrics']}
    assert rows['PE_VS_INDUSTRY']['status'] == 'A'
    assert rows['PE_VS_INDUSTRY']['value'] == 1.25
    # A different market date is not a valid independent comparison.
    raw['ratios']['price_ratios'][0]['quote_date'] = '2026-10-15'
    assert adapt(raw)[0]['valuation_unverified'] == []


def test_provider_retries_transient_errors_but_not_entitlement_failures(monkeypatch):
    waits, calls = [], []
    monkeypatch.setattr('backend.premium_provider.time.sleep', waits.append)
    class ProviderError(Exception):
        def __init__(self, status): self.status_code = status
    def flaky(path, params):
        calls.append(path)
        if len(calls) < 3: raise ProviderError(429)
        return {'ok': True}
    assert provider_get(flaky, '/test', {}) == {'ok': True}
    assert len(calls) == 3 and waits == [.5, 1.]
    calls.clear()
    def forbidden(path, params):
        calls.append(path)
        raise ProviderError(403)
    with pytest.raises(ProviderError): provider_get(forbidden, '/test', {})
    assert len(calls) == 1


def test_cagr_does_not_bridge_missing_years():
    d = {'sales_y': [None,100,110,121,133.1,146.41], 'net_profit_y': [1,2,None,4,5,6]}
    rows = {r['metric']: r for r in score_company(d, 'MFG')['metrics']}
    assert rows['SALES_CAGR']['status'] == 'A'
    assert rows['SALES_CAGR']['details']['years'] == 3
    assert rows['SALES_CAGR']['details']['previous'] == 110
    assert rows['PROFIT_CAGR']['status'] == 'A'
    assert rows['PROFIT_CAGR']['details']['years'] == 2
    assert rows['PROFIT_CAGR']['details']['previous'] == 4


AUDIT = json.loads((Path(__file__).parent / 'fixtures' / 'premium_stock_audit_2026_10_18.json').read_text())


@pytest.mark.parametrize('stock', AUDIT['stocks'], ids=lambda stock: stock['symbol'])
def test_eight_sector_live_fixtures_reconcile_valuation_and_scores(stock):
    d, group, _, meta, _, _ = adapt_inputs(stock['raw'], stock['symbol'], date.fromisoformat(AUDIT['asOf']), AUDIT['basis'])
    assert group == stock['group'] and not meta['groupDefaulted']
    checks = meta['valuationChecks']
    assert checks['pe']['computed'] == pytest.approx(stock['expectedRatios']['pe'], rel=.001)
    # The model explicitly uses total equity. Provider P/B may instead use parent equity.
    assert checks['pb']['computed'] == pytest.approx(d['price'] * d['shares'] / d['net_worth'])
    assert 'pe' not in d['valuation_unverified']
    balance_rows = stock['raw']['balance']['financials'] + stock['raw']['balance_recent']['financials']
    latest = max(balance_rows, key=lambda row: row['period_end'])
    if latest.get('totalEquity') is not None:
        assert d['net_worth'] == pytest.approx(latest['totalEquity'] / 10_000_000)
    result = score_company(d, group)
    if result['status'] == 'NOT RATED':
        assert result['final'] is None and result['confidence'] < .5
    else:
        assert result['final'] is not None and 0 <= result['final'] <= 100
    assert 0 <= result['confidence'] <= 1
    if result['final'] is not None:
        assert sum(r['pointsEarned'] for r in result['metrics']) - result['capPointsLost'] == pytest.approx(result['final'])
    assert all(0 <= r['points'] <= 100 for r in result['metrics'] if r['points'] is not None)


def test_invalid_close_does_not_create_a_return_across_missing_session():
    from datetime import timedelta
    rows = [{'quote_date': (AS_OF-timedelta(days=70-i)).isoformat(), 'close_price': 100, 'volume': 1000} for i in range(70)]
    rows[35]['close_price'] = 0
    for row in rows[36:]: row['close_price'] = 200
    raw = {'profile': {'industry': 'IT - Software'}, 'prices': {'price': rows}}
    d, *_ = adapt(raw)
    # The apparent doubling across an unknown observation is not a one-session return.
    assert d['volatility_pct'] == 0
    assert d['trading_value_cr'] is None
    assert any('Invalid closing prices' in text for text in d['rating_cautions'])


def test_invalid_quote_and_pledge_are_not_accepted_as_actual_values():
    raw = {'profile': {'industry': 'Automobiles'}, 'quote': {'TEST': {'current_price': 0}},
           'prices': {'price': [{'quote_date': '2026-10-16', 'close_price': 200, 'volume': 100}]},
           'distribution': {'distributions': [{'date_header': 'Jun 2026', 'distributions': [
               {'group': 'promoterAndPromoterGroup', 'data': {'pledgedShares': 200, 'totalShares': 100}}]}]}}
    d, _, _, _, warnings, _ = adapt(raw)
    assert d['price'] == 200
    assert d['promoter_pledged_pct'] is None
    assert any('outside 0–100%' in text for text in warnings)


ORACLE = json.loads((Path(__file__).parent / 'fixtures' / 'premium_owner_parity.json').read_text())


@pytest.mark.parametrize('case', ORACLE['cases'], ids=lambda c: c['group'])
def test_documented_scoring_matches_supplied_owner_code(case,monkeypatch):
    # This oracle predates the owner's 24 October unconditional Quality changes.
    # Retain it as a baseline algorithm check with its original financial slots;
    # current slots/ranges are independently tested in test_premium_bank_fallbacks.
    if case['group'] in ('BANK','NBFC','INSURANCE'):
        from copy import deepcopy
        from backend import premium_engine
        legacy=deepcopy(premium_engine.GROUPS)
        weights=legacy[case['group']]['weights']['quality']
        previous='SOLVENCY' if case['group']=='INSURANCE' else 'CAPITAL_ADEQUACY'
        legacy[case['group']]['weights']['quality']={previous if k in ('INTEREST_COVER','FINANCIAL_LEVERAGE') else k:v for k,v in weights.items()}
        monkeypatch.setattr(premium_engine,'GROUPS',legacy)
    if case['group']=='BANK':
        from backend import premium_engine
        # The oracle also predates the owner's October 2026 request that PEG is a core factor for banks.
        monkeypatch.setattr(premium_engine,'PEG_CORE_GROUPS',('LIGHT','MFG'))
    actual=score_company(case['input'],case['group'])
    expected=case['expected']
    assert actual['final']==pytest.approx(expected['final'],abs=1e-6)
    assert actual['parts']==pytest.approx(expected['parts'],abs=1e-6)
    assert actual['confidence']==pytest.approx(expected['confidence'])
    assert actual['label']==expected['label']


def test_document_net_worth_is_total_equity_not_parent_equity():
    raw={'profile':{'industry':'Oil & Gas'},'balance':{'financials':[{'period_end':20260331,
        'equityAttributableToOwnersOfParent':9040300000000,'nonControllingInterest':1818360000000,'totalEquity':10858660000000}]}}
    d,_,_,meta,*_=adapt(raw)
    assert d['net_worth']==1085866
    assert meta['provenance']['net_worth']==['totalEquity']
    del raw['balance']['financials'][0]['totalEquity']
    assert adapt(raw)[0]['net_worth']==1085866
    del raw['balance']['financials'][0]['nonControllingInterest']
    assert adapt(raw)[0]['net_worth'] is None


RECONCILIATION=json.loads((Path(__file__).parent/'fixtures'/'premium_reconciliation_2026_10_18.json').read_text())


@pytest.mark.parametrize('case',RECONCILIATION['cases'],ids=lambda c:c['symbol'])
def test_all_seven_historical_reference_symbols_reproduce_the_original_cagr_policy(case,monkeypatch):
    # This recorded reconciliation predates the owner-requested 1/2-year
    # fallback. Preserve that historical check; current windows have dedicated
    # arithmetic and disclosure tests in test_premium_cagr_windows.py.
    monkeypatch.setattr('backend.premium_engine.CAGR_MIN_YEARS',3)
    result=score_company(case['inputs'],case['group'])
    assert result['final']==pytest.approx(case['expectedScore'],abs=1e-8)
    assert result['parts']==pytest.approx(case['expectedParts'],abs=1e-8)


def test_full_user_reliance_screenshot_reproduces_score_and_all_categories():
    case=json.loads((Path(__file__).parent/'fixtures'/'premium_reliance_screenshot.json').read_text())
    result=score_company(case['inputs'],'HEAVY')
    assert result['final']==pytest.approx(case['expectedScore'],abs=.05)
    assert result['parts']==pytest.approx(case['expectedParts'],abs=.05)
    assert result['confidence']==pytest.approx(.98)
