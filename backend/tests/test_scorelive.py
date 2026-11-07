"""Real-time scores: the live-price recompute equals a full build at that price; the Prism queue and its staleness rules."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from finlit import scorelive
from finlit.snapshot import build
from tests.conftest import BUNDLE_FILES, load
from tests.test_integration import store  # noqa: F401  (the database fixture)


def _bundle(price=None, trade="2026-09-30T10:00:00"):
    b = {k: load(n) for k, n in BUNDLE_FILES.items()}
    b.update(symbol="RELIANCE", statement="standalone")
    b["quote"] = copy.deepcopy(b["quote"])
    q = b["quote"]["RELIANCE"]
    if price is not None:
        q["current_price"] = price
    if trade:
        q["tradetime"] = trade
    return b


def _inputs(sections):
    from finlit.store import cut_input
    return {k: cut_input(k, sections[k]) for k in ("ratios", "price", "stats", "events")} | {"financials": sections["financials"], "ownership": sections["ownership"]}


def _compare(price, trade):
    base = build(_bundle(trade="2026-09-29T15:59:02"))                    # the stored report
    summary = copy.deepcopy(base["summary"])
    summary["quote"] = {**summary["quote"], "price": price, "asOf": trade}  # what the quote job does
    got = scorelive.rescore(summary, _inputs(base))
    full = build(_bundle(price=price, trade=trade))["summary"]            # what the nightly batch computes for that price
    assert got is not None
    assert got["score"] == {k: full["score"][k] for k in ("overall", "band", "model", "pillars")}
    assert got["thesis"] == full["thesis"]
    assert got["strengths"] == full["strengths"] and got["watchouts"] == full["watchouts"]
    return got


@pytest.mark.parametrize("price,trade", [(1100.0, "2026-09-30T10:00:00"), (1500.0, "2026-09-30T10:00:00"), (900.0, "2026-09-29T15:59:02"), (1184.0, "2026-10-05T11:00:00")])
def test_live_price_score_equals_full_build(price, trade):
    _compare(price, trade)


def test_price_move_changes_only_the_technical_pillar():
    a, b = _compare(1100.0, "2026-09-30T10:00:00"), _compare(1500.0, "2026-09-30T10:00:00")
    pa = {p["key"]: p["score"] for p in a["score"]["pillars"]}
    pb = {p["key"]: p["score"] for p in b["score"]["pillars"]}
    assert {k for k in pa if pa[k] != pb[k]} <= {"technical"}


def test_a_report_without_exact_inputs_is_left_to_the_batch():
    base = build(_bundle())
    s = copy.deepcopy(base["summary"])
    s.pop("iqInputs")
    assert scorelive.rescore(s, _inputs(base)) is None
    s = copy.deepcopy(base["summary"])
    s["iqInputs"]["metrics"]["roe"] = 1.0 if s["iqInputs"]["metrics"].get("roe") != 1.0 else 50.0  # inputs that do not match the stored score
    s["iqInputs"]["metrics"]["roce"] = 99.0
    s["iqInputs"]["metrics"]["opm"] = 99.0
    assert scorelive.rescore(s, _inputs(base)) is None


def test_score_as_of_is_stored():
    a = build(_bundle())["summary"]["score"]["asOf"]
    assert a["live"] is False and a["computedAt"] and a["priceAsOf"]


def test_stale_reason_rules():
    now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
    fresh = now - timedelta(hours=1)
    assert scorelive.stale_reason(None, None, None, False, now)[0] == "none"
    assert scorelive.stale_reason(fresh, "2026-06-30", 20260630.0, True, now)[0] == "model"
    assert scorelive.stale_reason(fresh, "2026-06-30", "20260930.0", False, now)[0] == "filing"
    assert scorelive.stale_reason(fresh, "2026-06-30", "20260630.0", False, now) is None
    assert scorelive.stale_reason(now - timedelta(days=3), "2026-06-30", "20260630.0", False, now)[0] == "session"


@pytest.mark.asyncio
async def test_queue_is_bounded_and_deduplicated(store):
    await store.redis.delete(scorelive.PRISM_Q)
    assert await scorelive.enqueue_prism(store, "tcs") is True
    assert await scorelive.enqueue_prism(store, "TCS") is False
    assert await scorelive.queue_depth(store.redis) == 1
    assert await scorelive.has_work(store) is True
    await store.redis.delete(scorelive.PRISM_Q)


@pytest.mark.asyncio
async def test_drain_skips_when_prism_not_connected(store):
    from types import SimpleNamespace
    res = await scorelive.drain_prism(store, SimpleNamespace(site_api_url="", cms_jwt_secret=""))
    assert res["status"] == "skipped"


@pytest.mark.asyncio
async def test_quote_tick_updates_summary_and_the_screener_row_together(store):
    """One write path: the stock page's stored summary and the screener's scores row show the same new IQ, and the list carries scored_at."""
    from finlit import snapshot
    from finlit.worker import refresh_quotes

    sections = build(_bundle(trade="2026-09-29T15:59:02"))
    await store.save_snapshot("RELIANCE", "standalone", sections, snapshot.score_row(sections), sections["price"]["daily"])

    class Dhan:
        configured = False

    class Client:
        async def get(self, path, params, timeout=5):
            return {"RELIANCE": {"current_price": 1500.0, "change": 1.0, "tradetime": "2026-09-30T10:00:00"}}

    await refresh_quotes(Client(), store, [("RELIANCE", "standalone")])
    got = await store.get_section("RELIANCE", "standalone", "summary")
    summary = json.loads(got[0])
    full = build(_bundle(price=1500.0, trade="2026-09-30T10:00:00"))["summary"]
    assert summary["score"]["overall"] == full["score"]["overall"] and summary["score"]["asOf"]["live"] is True
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT overall, pillar_technical, live_at FROM scores WHERE symbol = 'RELIANCE'")
    tech = next(p["score"] for p in full["score"]["pillars"] if p["key"] == "technical")
    assert row["overall"] == full["score"]["overall"] and row["pillar_technical"] == tech and row["live_at"] is not None
    rows = await store.top_scores()
    assert rows and rows[0]["scored_at"] is not None


def test_score_lag_dataset_judges_prism_behind_a_filing():
    from finlit.jobs.freshness import judge_score_lag
    now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
    assert judge_score_lag({"prism_behind": 0, "queue": 0}, now, False).status == "fresh"
    assert judge_score_lag({"prism_behind": 3, "prism_behind_since": now - timedelta(hours=8), "queue": 3}, now, False).status == "late"
    assert judge_score_lag({"prism_behind": 3, "prism_behind_since": now - timedelta(hours=40), "queue": 3}, now, False).status == "stale"


async def _rate_behind(store, symbol, prism_quarter, iq_quarter, hours_old=5):
    """A company with a stored Prism rating (built from `prism_quarter`) and a FinLit IQ that holds `iq_quarter` (YYYYMMDD)."""
    import json
    import uuid
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports WHERE symbol = $1", symbol)
        await conn.execute("DELETE FROM scores WHERE symbol = $1", symbol)
        await conn.execute("INSERT INTO scores (symbol, statement, model, sector, metrics, updated_at) VALUES ($1, 'consolidated', 'v1', 'Test', $2::jsonb, now() - make_interval(hours => $3))",
                           symbol, json.dumps({"q_period_end": float(iq_quarter)}), hours_old)
        await conn.execute("INSERT INTO prism_reports (symbol, statement, id, report, final, label, status) VALUES ($1, 'consolidated', $2, $3::jsonb, 60, 'AVERAGE', 'RATED')",
                           symbol, uuid.uuid4().hex, json.dumps({"inputMeta": {"quarterlyAsOf": prism_quarter}}))


async def _clean(store, *symbols):
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports WHERE symbol = ANY($1::text[])", list(symbols))
        await conn.execute("DELETE FROM scores WHERE symbol = ANY($1::text[])", list(symbols))
    await store.redis.delete(scorelive.PRISM_Q, *[f"prism:pre:fail:consolidated:{x}" for x in symbols], *[scorelive.PRISM_TRY + f"{x}|consolidated" for x in symbols])


@pytest.mark.asyncio
async def test_a_rating_behind_a_filed_quarter_is_found_and_queued_even_when_the_results_job_never_queued_it(store):
    await _clean(store, "BHA1", "BHA2", "BHA3")
    try:
        await _rate_behind(store, "BHA1", "2026-06-30", "20260930")            # behind the quarter the IQ holds: found
        await _rate_behind(store, "BHA2", "2026-09-30", "20260930")            # current: left alone
        await _rate_behind(store, "BHA3", "2026-06-30", "20260930", hours_old=0)   # the IQ changed under 2 hours ago: the live job has had no turn yet, same rule as the status page
        assert await scorelive.behind_members(store, 10) == ["BHA1|consolidated"]
        assert await scorelive.has_work(store) is True                          # the probe wakes the job although the queue is empty
        assert await scorelive.queue_depth(store.redis) == 0
        assert await scorelive.enqueue_behind(store) == 1
        assert await scorelive.enqueue_behind(store) == 0                        # not twice
        assert await scorelive.queue_depth(store.redis) == 1
    finally:
        await _clean(store, "BHA1", "BHA2", "BHA3")


@pytest.mark.asyncio
async def test_a_company_the_data_cannot_catch_up_for_is_not_asked_again_and_again(store):
    await _clean(store, "BHB1", "BHB2")
    try:
        await _rate_behind(store, "BHB1", "2026-06-30", "20260930")
        await _rate_behind(store, "BHB2", "2026-06-30", "20260930")
        await store.redis.set("prism:pre:fail:consolidated:BHB1", "quarter-not-available", ex=600)     # the provider is behind: left for the nightly job
        await store.redis.set(scorelive.PRISM_TRY + "BHB2|consolidated", "filing", ex=600)              # tried a moment ago
        assert await scorelive.behind_members(store, 10) == []
        assert await scorelive.has_work(store) is False                          # nothing to do: the job does not start for nothing
    finally:
        await _clean(store, "BHB1", "BHB2")


@pytest.mark.asyncio
async def test_the_status_page_and_the_job_count_the_same_companies(store):
    await _clean(store, "BHC1")
    try:
        await _rate_behind(store, "BHC1", "2026-06-30", "20260930")
        facts = await scorelive.facts(store)
        assert facts["prism_behind"] >= 1
        assert "BHC1|consolidated" in await scorelive.behind_members(store, 500)
    finally:
        await _clean(store, "BHC1")
