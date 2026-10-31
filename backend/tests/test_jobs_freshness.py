"""Data-freshness invariants and the value self-checks (canary), with synthetic data and a fake clock."""
from datetime import date, datetime, timedelta, timezone

import pytest

from finlit.jobs import canary, freshness as fr
from finlit.jobs.signals import RedisSignals, clear_credential, mark_credential_refused, report_refused
from jobs_fakes import ist
from test_integration import ingested, make_settings, store  # noqa: F401

FRI = date(2026, 10, 30)
MON = date(2026, 11, 2)


def test_expected_session_follows_the_weekday_rule_and_a_found_holiday_lowers_it():
    assert fr.effective_expected(ist(2026, 10, 30, 17, 0), None) == FRI
    assert fr.effective_expected(ist(2026, 10, 30, 12, 0), None) == date(2026, 10, 29)          # before 16:00 the session is not complete
    assert fr.effective_expected(ist(2026, 10, 31, 10, 0), None) == FRI                          # Saturday: Friday's
    assert fr.effective_expected(ist(2026, 11, 2, 17, 0), date(2026, 10, 30)) == FRI             # Monday was a holiday: the technicals job found Friday as the newest
    assert fr.effective_expected(ist(2026, 11, 2, 17, 0), date(2026, 11, 5)) == MON              # a target can never raise the expectation


def test_a_session_dataset_is_fresh_late_then_stale_and_never_blames_the_job_before_the_data_is_due():
    j = lambda actual, now, **k: fr.judge_session("x", "X", ["job"], actual, FRI, now, 1.0, 10.0).status   # noqa: E731
    assert j(FRI, ist(2026, 10, 30, 20, 0)) == "fresh"
    assert j(date(2026, 10, 29), ist(2026, 10, 30, 17, 0)) == "fresh"                              # today's bar is not due until 19:30: yesterday's is what must be there
    assert j(date(2026, 10, 29), ist(2026, 10, 30, 19, 29)) == "fresh"
    assert j(date(2026, 10, 29), ist(2026, 10, 30, 19, 31)) == "late"
    assert j(date(2026, 10, 29), ist(2026, 10, 31, 5, 29)) == "late"
    assert j(date(2026, 10, 29), ist(2026, 10, 31, 5, 31)) == "stale"
    assert j(None, ist(2026, 10, 31, 8, 0)) == "unknown"
    ds = fr.judge_session("x", "X", ["job"], date(2026, 10, 12), FRI, ist(2026, 10, 31, 8, 0), 1.0, 10.0)
    assert ds.status == "stale" and ds.lag == 18 and ds.lagUnit == "days" and ds.expected == "2026-10-30" and ds.actual == "2026-10-12" and ds.jobs == ["job"]
    # a previous-session check on Monday morning looks back over the weekend to Friday
    assert fr.judge_session("x", "X", ["j"], FRI, MON, ist(2026, 11, 2, 9, 0), 1.0, 10.0).status == "fresh"


def test_quotes_during_market_hours_are_judged_in_minutes_and_after_it_by_the_close():
    t = lambda *a: ist(2026, 10, 30, *a)    # noqa: E731
    assert fr.judge_quotes(t(11, 40), t(12, 0), None, FRI).status == "fresh"
    q = fr.judge_quotes(t(10, 0), t(12, 0), None, date(2026, 10, 29))
    assert q.status == "late" and q.lag == 120 and q.lagUnit == "minutes"
    assert fr.judge_quotes(t(8, 0), t(12, 0), None, date(2026, 10, 29)).status == "stale"
    assert fr.judge_quotes(t(15, 45), t(17, 0), None, FRI).status == "fresh"                       # after the close, a post-close quote
    assert fr.judge_quotes(t(14, 0), t(19, 0), None, FRI).status == "late"                          # taken before the close; the close should have come by now
    assert fr.judge_quotes(t(14, 0), ist(2026, 10, 31, 9, 0), None, FRI).status == "stale"
    assert fr.judge_quotes(t(16, 0), ist(2026, 10, 31, 9, 0), None, FRI).status == "fresh"          # Saturday morning: Friday's close is the newest there is
    assert fr.judge_quotes(None, t(12, 0), None, FRI).status == "unknown"


def test_technical_views_are_judged_by_the_share_of_reports_behind_the_expected_session():
    now = ist(2026, 10, 30, 21, 0)
    assert fr.judge_technicals(500, 5, "2026-10-30", FRI, now).status == "fresh"                    # 1%: a few companies Dhan has no candles for
    assert fr.judge_technicals(510, 506, "2026-10-12", FRI, now).status == "late"                    # the incident: 99% behind, but only 2.5 h after the data was due
    assert fr.judge_technicals(510, 506, "2026-10-12", FRI, ist(2026, 10, 31, 6, 0)).status == "stale"
    ds = fr.judge_technicals(510, 506, "2026-10-12", FRI, ist(2026, 10, 31, 6, 0))
    assert "506 of 510" in ds.detail and ds.jobs == ["technicals"]
    assert fr.judge_technicals(500, 400, "2026-10-29", FRI, ist(2026, 10, 30, 17, 0)).status == "fresh"       # the session's data is not final yet
    assert fr.judge_technicals(0, 0, None, FRI, now).status == "unknown"


def test_results_waiting_for_figures_are_flagged_late_the_next_day_and_stale_after_that():
    today = FRI
    assert fr.judge_results([], today, 12).status == "fresh"
    assert fr.judge_results([today, today], today, 12).status == "fresh"
    assert fr.judge_results([today - timedelta(days=1)], today, 12).status == "late"
    r = fr.judge_results([today - timedelta(days=3), today], today, 12)
    assert r.status == "stale" and "1 waiting since 2+ days" in r.detail and r.lag == 3 and set(r.jobs) == {"results", "results-light"}


def test_calendar_nav_and_weekly_judges():
    now = ist(2026, 10, 30, 12, 0)
    assert fr.judge_calendar(14, now - timedelta(hours=1), now).status == "fresh"
    assert fr.judge_calendar(0, now - timedelta(hours=1), now).status == "late"
    assert fr.judge_calendar(14, now - timedelta(hours=20), now).status == "stale"
    # NAV: expected is the last business day that has passed 23:30
    assert fr.judge_nav(date(2026, 10, 29), ist(2026, 10, 30, 22, 0)).status == "fresh"            # tonight's file is not out yet
    assert fr.judge_nav(date(2026, 10, 29), ist(2026, 10, 30, 23, 45)).status == "late"            # Friday's is due, one business day behind (could be a holiday)
    assert fr.judge_nav(date(2026, 10, 27), ist(2026, 10, 30, 23, 45)).status == "stale"
    assert fr.judge_nav(FRI, ist(2026, 11, 1, 10, 0)).status == "fresh"                             # Sunday: Friday's NAV is the latest
    assert fr.judge_weekly("leadership", "L", ["leadership"], date(2026, 10, 23), FRI, 9, 14).status == "fresh"
    assert fr.judge_weekly("leadership", "L", ["leadership"], date(2026, 10, 10), FRI, 9, 14).status == "stale"
    ix = fr.judge_index(ist(2026, 10, 30, 11, 55).timestamp(), ist(2026, 10, 30, 12, 0), True)
    assert ix.status == "fresh"
    assert fr.judge_index(ist(2026, 10, 30, 10, 0).timestamp(), ist(2026, 10, 30, 12, 0), True).status == "stale"
    assert fr.judge_index(ist(2026, 10, 30, 10, 0).timestamp(), ist(2026, 10, 30, 12, 0), False).status == "fresh"        # nobody is looking: fetched on demand


def facts(**kw):
    now = ist(2026, 10, 30, 21, 0)
    f = dict(listing_newest=ist(2026, 10, 30, 15, 45), price_ref=FRI, scores_newest=now - timedelta(hours=5), prism_newest=now - timedelta(hours=5), calendars_ran=now - timedelta(hours=1),
             results_upcoming=20, ipo_updated=now - timedelta(hours=3), flows_newest=FRI, mf_nav=date(2026, 10, 29), mf_score_run=FRI, etf_price=FRI, news_newest=FRI, leadership=date(2026, 10, 30),
             db_mb=500.0, tech_total=500, tech_behind=2, tech_newest_bar="2026-10-30", found_target=None, index_t=None, visitors=False, results_declared=10, results_waiting=[])
    f.update(kw)
    return f, now


def test_the_overall_verdict_lists_stale_datasets_with_their_owner_jobs():
    f, now = facts()
    rep = fr.evaluate_facts(f, now, [], disk=40.0)
    assert rep["dataFresh"] is True and rep["stale"] == [] and len(rep["datasets"]) >= 15
    assert {d["key"] for d in rep["datasets"]} >= {"quotes", "daily_prices", "index_levels", "technicals", "prism", "scores", "results", "results_calendar", "ipo_calendar", "flows", "mf_nav",
                                                    "fund_scores", "etf_prices", "news", "leadership", "ticker"}
    f, now = facts(tech_behind=506, tech_newest_bar="2026-10-12")
    rep = fr.evaluate_facts(f, ist(2026, 10, 31, 8, 0), [], disk=40.0)
    assert rep["dataFresh"] is False and "technicals" in rep["stale"]
    owner = [d for d in rep["datasets"] if d["key"] == "technicals"][0]
    assert owner["jobs"] == ["technicals"] and owner["status"] == "stale"
    f, now = facts(results_waiting=[FRI - timedelta(days=4)])
    assert "results" in fr.evaluate_facts(f, now, [], disk=40.0)["stale"]
    rep = fr.evaluate_facts(facts()[0], now, [{"provider": "dhan", "detail": "HTTP 401"}], disk=88.0)
    assert rep["system"]["diskOk"] is False and rep["system"]["diskPercent"] == 88.0 and rep["credentials"][0]["provider"] == "dhan"


def test_every_dataset_has_an_owner_job_that_exists_in_the_registry():
    from finlit.jobs.registry import by_name
    names = set(by_name({"FUND_LOADS_ENABLED": "1"}))
    f, now = facts()
    for d in fr.evaluate_facts(f, now, [], disk=1.0)["datasets"]:
        assert set(d["jobs"]) <= names, d


# ------------------------------------------------------------------------------------------------ value checks (canary)
def test_the_canary_compares_values_with_stated_tolerances():
    assert canary.compare("TCS", "price", 4000, 4010, 0.005) is None
    m = canary.compare("TCS", "price", 4000, 4100, 0.005)
    assert m == {"symbol": "TCS", "field": "price", "ours": 4000.0, "provider": 4100.0, "diffPercent": 2.44, "tolerancePercent": 0.5}
    assert canary.compare("TCS", "price", None, 4100, 0.005) is None and canary.compare("TCS", "price", 4000, None, 0.005) is None     # absence is a freshness matter
    closed, open_ = ist(2026, 10, 30, 17, 0), ist(2026, 10, 30, 11, 0)
    assert canary.tolerances(closed)["price"] == 0.005 and canary.tolerances(open_)["price"] == 0.03


def test_compare_company_checks_price_market_cap_close_and_quarter_figures():
    tol = canary.TOL_CLOSED
    stored = {"price": 1000.0, "marketCap": 100000.0, "close": 1000.0, "closeIsLatest": True, "quarter": {"revenue": 500.0, "netProfit": 50.0}}
    fresh = {"price": 1002.0, "marketCapCr": 101000.0, "quarter": {"revenue": 500.0, "netProfit": 50.1}}
    assert canary.compare_company("X", stored, fresh, tol) == []
    bad = {"price": 1100.0, "marketCapCr": 130000.0, "quarter": {"revenue": 450.0, "netProfit": 50.0}}
    fields = {m["field"] for m in canary.compare_company("X", stored, bad, tol)}
    assert fields == {"price", "marketCap", "lastClose", "quarterRevenue"}
    stored["closeIsLatest"] = False                                      # our newest bar is older than the latest session: that is freshness, not a wrong value
    assert "lastClose" not in {m["field"] for m in canary.compare_company("X", stored, bad, tol)}


def test_the_canary_summary_is_ok_false_only_with_mismatches_and_none_when_nothing_could_be_checked():
    now = ist(2026, 10, 30, 17, 0)
    assert canary.summarise(["RELIANCE"], [], [], now)["ok"] is True
    assert canary.summarise(["RELIANCE"], [{"symbol": "X"}], [], now)["ok"] is False
    assert canary.summarise([], [], ["RELIANCE: ConnectError"], now)["ok"] is None
    assert canary.summarise(["A"], [], ["B: ConnectError"], now)["ok"] is True
    assert canary.summarise(["A"], [], [], now)["tolerancesPercent"]["price"] == 0.5


class FakeProvider:
    def __init__(self, prices):
        self.prices = prices

    async def get(self, path, params=None, timeout=10, retries=3, low=False):
        sym = params["symbol"]
        if sym not in self.prices:
            raise RuntimeError("down")
        return {sym: {"current_price": self.prices[sym], "change": 1.0, "market_cap": 1000.0, "tradetime": "2026-10-30 15:30:00"}}


async def test_the_canary_run_flags_a_wrong_stored_price_and_an_unreachable_provider(store):
    now = ist(2026, 10, 30, 17, 0)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM listing_quotes")
        for s, p in (("RELIANCE", 1000), ("TCS", 4000), ("HDFCBANK", 1500), ("INFY", 1400)):
            await conn.execute("INSERT INTO listing_quotes (symbol, price, market_cap) VALUES ($1, $2, 1000)", s, p)
    got = await canary.run(store, FakeProvider({"RELIANCE": 1001, "TCS": 4400, "HDFCBANK": 1500, "INFY": 1400}), now)
    assert got["ok"] is False and [m["symbol"] for m in got["mismatches"]] == ["TCS"] and got["mismatches"][0]["field"] == "price"
    assert sorted(got["checked"]) == ["HDFCBANK", "INFY", "RELIANCE", "TCS"]
    down = await canary.run(store, FakeProvider({}), now)
    assert down["ok"] is None and len(down["errors"]) == 4


async def test_the_freshness_facts_read_a_real_database_without_error(ingested):
    now = datetime.now(timezone.utc)
    f = await fr.gather(ingested, now)
    rep = fr.evaluate_facts(f, now, [], disk=None)
    assert rep["datasets"] and {"checkedAt", "dataFresh", "stale", "late", "system"} <= set(rep)
    assert f["tech_total"] >= 0 and "expected" in f


async def test_a_refused_provider_key_is_remembered_for_the_alert_and_cleared_when_a_call_works(store):
    await store.redis.flushdb()
    sig = RedisSignals(store.redis)
    await mark_credential_refused(store.redis, "dhan", "HTTP 401")
    assert await sig.credential_refused() == {"dhan": "HTTP 401"}
    await clear_credential(store.redis, "dhan")
    assert await sig.credential_refused() == {}

    class S:
        redis_url = make_settings().redis_url
    from finlit.jobs import signals
    signals._reported.clear()
    await report_refused(S(), "finedge", 403)
    assert "finedge" in await sig.credential_refused()
    await report_refused(S(), "finedge", 403)                           # throttled in-process: one write per 10 minutes
