"""finlit.mf_fill: funds with no 1/3/5 year returns are filled from the mirror of AMFI's data, only when the mirror agrees with AMFI's own latest NAV;
held funds are done first; a fund too young for any period is not asked again for a while."""
from datetime import date, timedelta

import httpx
import pytest

from finlit import mf_fill
from test_integration import make_settings, store  # noqa: F401

pytestmark = pytest.mark.integration
BASE = 920000
TODAY = date.today()
NAV_DATE = TODAY - timedelta(days=1)


def history(years: float, nav_now: float = 200.0):
    """A mirror answer: daily NAVs ending on NAV_DATE, growing about 12% a year (newest first, DD-MM-YYYY, like api.mfapi.in)."""
    n = int(years * 365)
    rows = []
    for k in range(n):
        d = NAV_DATE - timedelta(days=k)
        rows.append({"date": d.strftime("%d-%m-%Y"), "nav": f"{nav_now / (1.12 ** (k / 365)):.4f}"})
    return rows


def client_for(answers):
    def handler(request: httpx.Request) -> httpx.Response:
        code = int(request.url.path.rsplit("/", 1)[1])
        data = answers.get(code)
        if data is None:
            return httpx.Response(404)
        return httpx.Response(200, json={"meta": {"scheme_code": code}, "status": "SUCCESS", "data": data})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
async def schemes(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_schemes WHERE code >= $1", BASE)
        for k, (nav, aum) in enumerate([(200.0, 100.0), (200.0, 900.0), (200.0, 500.0), (50.0, 800.0)]):
            await conn.execute(
                "INSERT INTO mf_schemes (code, name, amc, scheme_type, category, plan, option_class, option_label, family, isin, nav, nav_date, active, aum_lakh, has_hist) "
                "VALUES ($1,$2,'Test Mutual Fund','Open Ended','Equity Scheme - Large Cap Fund','Direct','Growth','Growth',$3,$4,$5,$6,true,$7,false)",
                BASE + k, f"Test Fund {k} - Direct Plan - Growth", f"Test Fund {k}", f"INF92{k:07d}", nav, NAV_DATE, aum)
    for c in range(4):
        await store.redis.delete(f"mf:fill:tried:{BASE + c}")
    yield
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_monthly WHERE code >= $1", BASE)
        await conn.execute("DELETE FROM mf_schemes WHERE code >= $1", BASE)


async def row(store, code):
    async with store.pool.acquire() as conn:
        return await conn.fetchrow("SELECT r1y, r3y, r5y, has_hist, metrics_date FROM mf_schemes WHERE code = $1", code)


async def test_a_fund_without_returns_gets_them_from_the_mirror(store):  # noqa: F811
    async with client_for({BASE: history(6)}) as c:
        out = await mf_fill.fill(store, c, [BASE], pause=0)
    assert out["filled"] == 1 and out["failed"] == 0
    r = await row(store, BASE)
    assert r["has_hist"] and r["metrics_date"] == NAV_DATE
    assert r["r1y"] == pytest.approx(12.0, abs=0.6) and r["r3y"] == pytest.approx(12.0, abs=0.6) and r["r5y"] == pytest.approx(12.0, abs=0.6)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM mf_monthly WHERE code = $1", BASE) == 1      # the month-end NAVs are kept for the SIP figures


async def test_a_mirror_that_disagrees_with_amfi_stores_nothing(store):  # noqa: F811
    async with client_for({BASE + 1: history(6, nav_now=210.0)}) as c:       # AMFI says 200.0 for the same day
        out = await mf_fill.fill(store, c, [BASE + 1], pause=0)
    assert out["filled"] == 0
    r = await row(store, BASE + 1)
    assert r["r1y"] is None and r["r3y"] is None and r["r5y"] is None


async def test_a_young_fund_is_marked_and_not_asked_again(store):  # noqa: F811
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"meta": {"scheme_code": BASE + 2}, "status": "SUCCESS", "data": history(0.2)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        first = await mf_fill.fill(store, c, [BASE + 2], pause=0)
        second = await mf_fill.fill(store, c, [BASE + 2], pause=0)
    assert first["filled"] == 0 and first["noReturnYet"] == 1
    assert second["skipped"] == 1 and len(calls) == 1               # the second run did not ask the mirror again


async def test_held_funds_come_first_then_the_biggest(store):  # noqa: F811
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(int(request.url.path.rsplit("/", 1)[1]))
        return httpx.Response(404)
    async with store.pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users LIMIT 1")
        if uid:
            await conn.execute("INSERT INTO mf_holdings (user_id, code, folio) VALUES ($1, $2, '') ON CONFLICT DO NOTHING", uid, BASE)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await mf_fill.fill(store, c, [BASE, BASE + 1, BASE + 2, BASE + 3], pause=0)
    big_first = [BASE + 1, BASE + 3, BASE + 2, BASE]          # by fund size when nobody holds any
    assert asked == big_first or asked[0] == BASE, asked          # a held fund (when a user exists in this database) leads; else the biggest
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM mf_holdings WHERE code >= $1", BASE)
