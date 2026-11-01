"""A stored report from older scoring rules must not suppress a current calculation."""
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finlit import prism
from test_prism import env, generate, member  # noqa: F401
from test_integration import store  # noqa: F401


def test_gateway_and_scoring_engine_versions_match():
    source = Path(__file__).resolve().parents[2] / 'site-api/backend/premium_model_config.py'
    tree = ast.parse(source.read_text())
    actual = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'MODEL_VERSION' for t in n.targets))
    assert prism.REQUIRED_MODEL_VERSION == actual


@pytest.mark.parametrize('raw', [None, {}, {'rating': None}, {'rating': {'modelVersion': '3.6.10'}},
                               {'rating': {'modelVersion': 'unknown'}}, 'not-json'])
def test_old_or_unversioned_reports_are_stale(raw):
    assert prism.stale_model(raw)


def test_current_calculations_remain_reusable_including_a_zero_peg_score():
    report = {'rating': {'modelVersion': prism.REQUIRED_MODEL_VERSION,
                         'metrics': [{'metric': 'PEG', 'status': 'Z', 'points': 0}]}}
    for encoded in (report, json.dumps(report)):
        assert not prism.stale_model(encoded)
        assert prism._fresh({'report': encoded, 'generated_at': datetime.now(timezone.utc)})


@pytest.mark.integration
async def test_old_saved_reliance_is_hidden_and_recalculated_even_when_recent(env):  # noqa: F811
    app, fake = env
    gold = await member(app, 'gold')
    await generate(gold, 'RELIANCE')
    row = await prism._stored(app.state.store, 'RELIANCE', 'consolidated')
    old = json.loads(row['report'])
    old['rating']['modelVersion'] = '3.6.10'
    peg = next(m for m in old['rating']['metrics'] if m['metric'] == 'PEG')
    peg.update(status='N', points=None, value=None, share=0)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE prism_reports SET report=$1::jsonb, model_version='3.6.10' WHERE symbol='RELIANCE'",
                           json.dumps(old))
    for view in ('full', 'summary'):
        response = await gold.get('/api/prism/reports/latest', params={'symbol': 'RELIANCE', 'view': view})
        assert response.status_code == 404 and response.json()['status'] == 'none'
    assert not prism._fresh(await prism._stored(app.state.store, 'RELIANCE', 'consolidated'))
    response = await generate(gold, 'RELIANCE')
    assert response.status_code == 200 and response.json()['cached'] is False
    assert response.json()['rating']['modelVersion'] == prism.REQUIRED_MODEL_VERSION
    assert len(fake.reports) == 2
    assert (await gold.get('/api/prism/reports/latest?symbol=RELIANCE')).status_code == 200
    assert (await generate(gold, 'RELIANCE')).json()['cached'] is True


@pytest.mark.integration
async def test_nightly_queue_selects_old_model_without_waiting_for_age_cutoff(env):  # noqa: F811
    app, _ = env
    gold = await member(app, 'gold')
    await generate(gold, 'RELIANCE')
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO snapshots (symbol,statement,section,body,etag,generated_at) "
                           "VALUES ('RELIANCE','consolidated','summary','{}','v',now()) ON CONFLICT DO NOTHING")
        await conn.execute("UPDATE prism_reports SET model_version='3.6.10' WHERE symbol='RELIANCE'")
    assert 'RELIANCE' in await prism._pending(app.state.store, 'consolidated', 7, 20, [])
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE prism_reports SET model_version=$1 WHERE symbol='RELIANCE'", prism.REQUIRED_MODEL_VERSION)
    assert 'RELIANCE' not in await prism._pending(app.state.store, 'consolidated', 7, 20, [])
