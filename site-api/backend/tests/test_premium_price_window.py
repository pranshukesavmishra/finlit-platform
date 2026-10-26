from datetime import date, timedelta
from backend.premium_completeness import build_input_completeness
from backend.premium_data import adapt_inputs
from backend.premium_engine import score_company


def _sessions(n, placeholders=(), bad_close=()):
    rows, day, i = [], date(2026, 10, 26), 0
    while len(rows) < n:
        if day.weekday() < 5:
            if i in placeholders:   # the provider's all-zero padding row for a day it has no record of
                rows.append({'quote_date': day.isoformat(), 'open_price': 0, 'close_price': 0, 'high_price': 0, 'low_price': 0, 'volume': 0})
            else:
                c = 0 if i in bad_close else 100 + (i % 7)
                rows.append({'quote_date': day.isoformat(), 'open_price': 100, 'close_price': c, 'high_price': 110, 'low_price': 90, 'volume': 1_000_000})
            i += 1
        day -= timedelta(days=1)
    return rows


def _inputs(rows):
    return adapt_inputs({'prices': {'symbol': 'X', 'price': rows}}, 'X', date(2026, 10, 26), 'consolidated')[0]


def test_all_zero_padding_rows_do_not_break_the_250_and_60_session_windows():
    d = _inputs(_sessions(300, placeholders={5, 40}))
    assert d['biggest_fall_pct'] is not None and d['trading_value_cr'] is not None
    assert d['risk_calculation']['sessions'] == 298 and d['risk_calculation']['invalidCloseLast250'] == 0


def test_a_zero_close_beside_real_volume_stays_a_bad_tick_and_the_reason_is_given():
    d = _inputs(_sessions(300, bad_close={10}))
    assert d['biggest_fall_pct'] is None and d['risk_calculation']['invalidCloseLast250'] == 1
    rep = {'inputs': d, 'rating': score_company(d, 'MFG'), 'inputMeta': {}}
    rows = {i['metric']: i for i in build_input_completeness(rep)['items']}
    assert '300 trading sessions' in rows['BIGGEST_FALL']['missingInputs'][0] and '1 of the latest 250' in rows['BIGGEST_FALL']['missingInputs'][0]


def test_short_history_reason():
    d = _inputs(_sessions(120))
    rep = {'inputs': d, 'rating': score_company(d, 'MFG'), 'inputMeta': {}}
    rows = {i['metric']: i for i in build_input_completeness(rep)['items']}
    assert '120 trading sessions, 250 are needed' in rows['BIGGEST_FALL']['missingInputs'][0]
