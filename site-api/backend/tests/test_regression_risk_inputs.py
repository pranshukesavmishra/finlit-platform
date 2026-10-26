"""Regression (docs/KNOWN-ISSUES.md g): the Input completeness card must never call a risk figure unavailable when the Risk card shows it."""
import pytest
from backend.premium_completeness import build_input_completeness
from backend.premium_engine import score_company

RISK = ('VOLATILITY', 'BIGGEST_FALL', 'TRADING_VALUE')


@pytest.mark.xfail(strict=False, reason="risk-inputs completeness fix in progress by another agent (premium_*.py); drop the marker once it lands")
@pytest.mark.parametrize('inputs', [
    {'volatility_pct': 31.0, 'biggest_fall_pct': -42.0, 'trading_value_cr': 12.5},
    {'volatility_pct': 31.0, 'biggest_fall_pct': -42.0, 'trading_value_cr': 12.5, 'risk_calculation': {'sessions': 260}},
    {'biggest_fall_pct': -42.0, 'risk_calculation': {'sessions': 260, 'invalidCloseLast250': 0}},
])
def test_a_risk_figure_the_risk_card_shows_is_never_listed_as_unavailable(inputs):
    rating = score_company(inputs, 'INSURANCE')
    shown = {r['metric'] for r in rating['metrics'] if r['metric'] in RISK and r['status'] not in ('F', 'L') and r.get('points') is not None}
    listed = {i['metric'] for i in build_input_completeness({'inputs': inputs, 'rating': rating, 'inputMeta': {}})['items'] if i['kind'] == 'missing'}
    assert not (shown & listed), shown & listed
