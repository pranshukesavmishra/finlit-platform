"""The read-only data audit (finlit/dataaudit.py): seeded problems are reported with the right severity, an empty database finishes and says what is empty,
a missing table is a finding and not a crash, and the command writes nothing."""
import asyncio
import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from finlit import dataaudit, worker
from finlit.config import Settings
from finlit.store import Store

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://finlit:finlit@localhost:5432/finlit_test")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
ROOT = Path(__file__).resolve().parents[2]
WIPE = sorted({t.table for t in dataaudit.TABLES} | {"job_state", "index_members", "snapshots"})


def settings():
    return Settings(finedge_api_key="test", finedge_mode="fixtures", database_url=TEST_DB, redis_url=TEST_REDIS)


@pytest.fixture
async def store():
    try:
        s = await Store.connect(settings())
        await s.redis.ping()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres/redis not available: {exc}")
    await s.migrate()
    async with s.pool.acquire() as conn:
        await conn.execute("TRUNCATE " + ", ".join(WIPE) + " CASCADE")  # nosec B608 - table names come from the module's own fixed list
    await s.redis.flushdb()
    yield s
    await s.close()


def find(result, feature, needle=""):
    return [f for f in result["findings"] if f["feature"] == feature and needle in f["what"]]


async def test_empty_database_finishes_and_says_what_is_empty(store, tmp_path):
    res = await dataaudit.run_audit(settings())
    assert res["meta"]["seconds"] < 60
    names = {f["feature"] for f in res["findings"] if f["severity"] == "MISSING" and "EMPTY" in f["what"]}
    assert {"Stock universe", "Stock scores (summary page)", "Mutual fund schemes (NAV, returns, SIP, AUM)", "Live quotes (price, market cap, 52-week)"} <= names
    assert not [f for f in res["findings"] if f["severity"] == "WRONG"]
    text = dataaudit.render(res)
    assert "EMPTY" in text and "stocks" not in text.split("\n")[0]
    out = tmp_path / "a.json"
    assert await worker.main(["audit-data", "--json", str(out)], settings()) == 0
    assert json.loads(out.read_text())["findings"]


async def test_every_query_is_valid_sql(store):
    """validate=True runs every rule even on empty tables: no 'could not check' may come from a typo in a column or a clause."""
    res = await dataaudit.run_audit(settings(), validate=True)
    broken = [f for f in res["findings"] if f["severity"] == "UNCHECKED"]
    assert not broken, broken[:5]


async def test_seeded_problems_are_reported_with_the_right_severity(store):
    today = date.today()
    async with store.pool.acquire() as c:
        await c.execute("INSERT INTO companies (symbol, name, sector) VALUES ('TCS','Tata','IT'),('tcs ','Tata dup','IT'),('GOODCO','Good','IT'),('NOSECTOR','No Sector',NULL),('S0','s','IT'),('S1','s','IT'),('S2','s','IT'),('S3','s','IT'),('S4','s','IT'),('S5','s','IT')")
        for i in range(6):   # NULL P/E and ROE on most rows, one negative price, one score out of range, one orphan
            await c.execute("INSERT INTO scores (symbol, statement, model, overall, price, market_cap, pe, roe) VALUES ($1,'consolidated','v1',$2,$3,1000,NULL,NULL)",
                            f"S{i}", 150 if i == 0 else 60, -5 if i == 1 else 100)
        await c.execute("INSERT INTO scores (symbol, statement, model, overall, price, market_cap, pe, roe) VALUES ('ORPHANX','consolidated','v1',50,10,100,20,10)")
        await c.execute("INSERT INTO listing_quotes (symbol, price, market_cap, updated_at) VALUES ('GOODCO', 100, 1000, now() - interval '30 days')")
        await c.execute("INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, family, nav, nav_date, active) VALUES "
                        "(1,'Stale Fund','A','Open Ended','Equity','Direct','Growth','f1',10.5,$1,true),(2,'Zero Nav','A','Open Ended','Equity','Direct','Growth','f2',0,$2,true),"
                        "(3,'Fresh','A','Open Ended','Equity','Direct','Growth','f3',20,$2,true)", today - timedelta(days=40), today)
        await c.execute("INSERT INTO flows_daily (d, fii_net, dii_net) VALUES ($1, 10, 5)", today + timedelta(days=10))
    res = await dataaudit.run_audit(settings())
    sev = lambda feature, needle: {f["severity"] for f in find(res, feature, needle)}
    scores, funds = "Stock scores (summary page)", "Mutual fund schemes (NAV, returns, SIP, AUM)"
    assert "WRONG" in sev("Stock universe", "not upper case")
    dup = find(res, "Stock universe", "same symbol twice")
    assert dup and dup[0]["severity"] == "WRONG" and dup[0]["count"] == 1 and dup[0]["examples"] == ["TCS"]
    assert "MISSING" in sev(scores, "scores.pe empty") and "MISSING" in sev(scores, "scores.roe empty")
    assert "WRONG" in sev(scores, "outside 0-100")
    neg = find(res, scores, "price zero or negative")
    assert neg and neg[0]["severity"] == "WRONG" and neg[0]["examples"] == ["S1"]
    orphan = find(res, scores, "orphan")
    assert orphan and orphan[0]["severity"] == "WRONG" and "ORPHANX" in orphan[0]["examples"]
    assert "STALE" in sev("Live quotes (price, market cap, 52-week)", "days old")
    zero = find(res, funds, "NAV zero or negative")
    assert zero and zero[0]["severity"] == "WRONG" and zero[0]["examples"] == ["2"]
    assert "STALE" in sev(funds, "NAV older than 7 days")
    assert "WRONG" in sev("FII / DII daily flows", "future")
    order = [dataaudit.RANK[f["severity"]] for f in res["findings"]]
    assert order == sorted(order)
    blob = json.dumps(res)
    assert "finlit:finlit" not in blob and "postgresql://" not in blob


async def test_missing_table_is_a_finding_not_a_crash(store):
    async with store.pool.acquire() as c:
        await c.execute("ALTER TABLE preset_meta RENAME TO preset_meta_gone")
    try:
        res = await dataaudit.run_audit(settings())
    finally:
        async with store.pool.acquire() as c:
            await c.execute("ALTER TABLE preset_meta_gone RENAME TO preset_meta")
    hit = [f for f in res["findings"] if f["feature"] == "Preset run facts"]
    assert hit and hit[0]["severity"] == "UNCHECKED" and hit[0]["what"].startswith("could not check: table preset_meta does not exist")
    assert res["meta"]["counts"]["UNCHECKED"] >= 1


async def test_only_option_limits_the_run_and_unknown_is_reported(store):
    res = await dataaudit.run_audit(settings(), only=["funds"])
    assert res["findings"] and {f["group"] for f in res["findings"]} <= {"funds"}
    res = await dataaudit.run_audit(settings(), only=["nonsense"])
    assert res["meta"]["unknownFeatures"] == ["nonsense"] and not res["findings"]


async def test_the_audit_writes_nothing(store):
    async def total():
        async with store.pool.acquire() as c:
            return await c.fetchval("SELECT coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_user_tables")
    await asyncio.sleep(0.7)
    before = await total()
    await dataaudit.run_audit(settings(), quick=True)
    await asyncio.sleep(0.7)
    assert before == await total()


async def test_unreachable_database_still_exits_zero(capsys, tmp_path):
    bad = Settings(finedge_api_key="t", finedge_mode="fixtures", database_url="postgresql://nobody:pw@127.0.0.1:1/none", redis_url=TEST_REDIS)
    assert await dataaudit.run_cli(bad, None, True, str(tmp_path / "x.json")) == 0
    out = capsys.readouterr().out
    assert "could not check" in out and "pw@" not in out


def test_the_command_is_documented():
    assert "audit-data" in (ROOT / "backend/finlit/worker.py").read_text()
    doc = (ROOT / "docs/DATA-AUDIT.md").read_text()
    assert "bash /opt/finlit/src/finlit-platform/deploy/aws/deploy.sh compose exec app python -m finlit.worker audit-data" in doc
