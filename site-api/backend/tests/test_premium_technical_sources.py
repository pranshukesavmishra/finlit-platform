"""Provider source order, session-date coverage, fallback and caching."""
from datetime import date

from backend import premium_technical_sources as sources
from backend.tests.test_premium_technical import candles

ASOF = date(2026,10,23)


def test_finedge_complete_history_is_kept_without_secondary_request(monkeypatch):
    monkeypatch.setattr(sources,"_CACHE",{})
    bars = candles()
    calls = []
    def get(path,params):
        calls.append((path,params))
        return {"rows":bars}
    def secondary(key):
        raise AssertionError("Complete FinEdge data must take precedence")
    result = sources.load_benchmark_history(get,ASOF,secondary,[b['date'] for b in bars[-505:]])
    assert all(row['provider']=='FinEdge' for row in result.values())
    assert len(calls)==4
    assert {params['index_symbol'] for _,params in calls}=={'NIF500','NIF50','NIFMID100','NIFSMA100'}
    assert all(path=='/index/market-price/historical' for path,_ in calls)
    sources.load_benchmark_history(get,ASOF,secondary,[b['date'] for b in bars[-505:]])
    assert len(calls)==4


def test_long_fresh_history_with_a_missing_session_uses_one_secondary_series(monkeypatch):
    monkeypatch.setattr(sources,"_CACHE",{})
    bars = candles()
    primary = bars[:550]+bars[551:]
    seen = []
    def secondary(key):
        seen.append(key)
        return [{**b,"close":b['close']+1000} for b in bars]
    result = sources.load_benchmark_history(lambda *args:{'rows':primary},ASOF,secondary,[b['date'] for b in bars[-505:]])
    assert len(seen)==4
    assert all(row['provider']=='Upstox' for row in result.values())
    assert all(row['bars'][0]['close']==1100 for row in result.values())
    assert all('matching stock-session' in row['notes'][0] for row in result.values())


def test_bad_index_observation_is_a_gap_not_a_zero_or_compressed_return():
    bars = candles()
    bars[-10]['close']=-1
    result = sources.index_bars({'rows':bars},ASOF)
    assert len(result)==9
    assert all(row['close']>0 for row in result)
