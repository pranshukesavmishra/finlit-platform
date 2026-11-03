"""The nightly job end to end with a FAKE language model and a recorded PDF: collection from the stored feed and from the exchange's list, text extraction, answers,
quote validation, advice words, "not covered", idempotency, prompt versions, rate limits and bounds. Needs Postgres and Redis."""
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from earnings_fakes import FIX, Q1, Q3, FakeProvider, fixture_pdf, good, honest_answers
from finlit.earnings import config as C
from finlit.earnings import service as S
from finlit.earnings import transcripts as T
from finlit.earnings.provider import RateLimited
from finlit.earnings.questions import QUESTIONS
from finlit.config import Settings
from test_integration import make_settings, store  # noqa: F401  (fixture)

pytestmark = pytest.mark.integration

TODAY = date(2026, 11, 1)
URL = "https://nsearchives.nseindia.com/corporate/ACME_23102026182210_Transcript.pdf"
URL_Q1 = "https://nsearchives.nseindia.com/corporate/ACME_28072026174000_Transcript.pdf"
ENV = {"EARNINGS_TOP_COMPANIES": "5", "EARNINGS_QUARTERS": "2"}


@pytest.fixture(autouse=True)
def small_texts(monkeypatch):
    monkeypatch.setattr(C, "MIN_TEXT_CHARS", 500)          # the synthetic transcript is 3 pages, not 80


async def nosleep(_):
    return None


def exchange(pdf=None, nse=None, refuse=()):
    """A fetcher whose 'internet' is this function: robots.txt is absent, PDFs are the fixture, NSE answers with the recorded list."""
    seen = []

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        if req.url.host in refuse:
            return httpx.Response(403)
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf if pdf is not None else fixture_pdf())
        if req.url.path == "/api/corporate-announcements":
            return httpx.Response(200, json=nse if nse is not None else [])
        return httpx.Response(200, text="home")
    f = T.Fetcher(budget=60, transport=httpx.MockTransport(handler), sleep=nosleep, pause=0)
    f.seen = seen
    return f


async def seed(st, feed=True, symbols=("ACME",)):
    async with st.pool.acquire() as conn:
        await conn.execute("TRUNCATE earnings_calls, feed_items RESTART IDENTITY CASCADE")
        await conn.execute("DELETE FROM listing_quotes")
        await conn.execute("DELETE FROM companies WHERE symbol = ANY($1::text[])", list(symbols))
        for i, s in enumerate(symbols):
            await conn.execute("INSERT INTO companies (symbol, name) VALUES ($1, $2)", s, f"{s.title()} Industries Limited")
            await conn.execute("INSERT INTO listing_quotes (symbol, market_cap) VALUES ($1, $2)", s, 100000 - i)
        if feed:
            for title, link, d in (("Transcript of the Q2 FY27 earnings call", URL, date(2026, 10, 23)), ("Transcript of the Q1 FY27 earnings call", URL_Q1, date(2026, 7, 28)),
                                   ("Intimation of earnings call", "https://nsearchives.nseindia.com/corporate/ACME_x.pdf", date(2026, 10, 14))):
                await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, link, item_date, category, auto, dedupe) VALUES ('document',$1,'ACME','Acme',$2,$3,'Analyst Call',true,$4)",
                                   title, link, d, title + link)


async def run(st, provider, fetcher=None, **kw):
    kw.setdefault("env", ENV)
    kw.setdefault("today", TODAY)
    return await S.run(st, make_settings(), provider=provider, fetcher=fetcher or exchange(), sleep=nosleep, **kw)


async def answers(st, symbol="ACME", fy=2027, q=2):
    async with st.pool.acquire() as conn:
        rows = await conn.fetch("SELECT a.* FROM earnings_call_answers a JOIN earnings_calls c ON c.id = a.call_id WHERE c.symbol=$1 AND c.fiscal_year=$2 AND c.quarter=$3 ORDER BY a.question_id", symbol, fy, q)
    return {r["question_id"]: dict(r) | {"answer": json.loads(r["answer"])} for r in rows}


# ------------------------------------------------------------------------------------------------ migration and "not configured"
async def test_migration_080_applies_to_a_database_that_lacks_it(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS earnings_call_usage, earnings_call_answers, earnings_call_text, earnings_calls CASCADE")
        await conn.execute("DELETE FROM schema_migrations WHERE version = '080_earnings_calls'")
    await store.migrate()
    async with store.pool.acquire() as conn:
        tables = {r["table_name"] for r in await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'earnings_call%'")}
        assert tables == {"earnings_calls", "earnings_call_text", "earnings_call_answers", "earnings_call_usage"}
        cols = {r["column_name"] for r in await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'earnings_calls'")}
        assert {"symbol", "fiscal_year", "quarter", "call_date", "filed_at", "transcript_url", "transcript_sha256", "source", "text_chars", "status", "fetched_at"} <= cols
        assert await conn.fetchval("SELECT count(*) FROM schema_migrations WHERE version = '080_earnings_calls'") == 1
    await store.migrate()                                    # a second run changes nothing


async def test_without_a_key_the_job_says_not_configured_and_touches_nothing(store):  # noqa: F811
    await seed(store)
    p = FakeProvider(honest_answers, configured=False)
    f = exchange()
    res = await run(store, p, f)
    assert res["status"] == "not_configured" and "GEMINI_API_KEY" in res["detail"] and f.seen == [] and p.requests == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM earnings_calls") == 0


# ------------------------------------------------------------------------------------------------ the happy path and idempotency
async def test_find_download_read_ask_validate_store_then_a_second_run_does_nothing(store):  # noqa: F811
    await seed(store)
    p = FakeProvider(honest_answers)
    res = await run(store, p)
    assert res["status"] == "ok" and res["from_feed"] == 2 and res["downloaded"] == 2 and res["calls_summarised"] == 2
    async with store.pool.acquire() as conn:
        calls = {(r["fiscal_year"], r["quarter"]): dict(r) for r in await conn.fetch("SELECT * FROM earnings_calls ORDER BY quarter DESC")}
    q2 = calls[(2027, 2)]
    assert q2["transcript_url"] == URL and q2["filed_at"].astimezone(S.IST).date() == date(2026, 10, 23) and q2["pages"] == 3 and q2["text_chars"] > 1000 and len(q2["transcript_sha256"]) == 64
    assert q2["status"] == "answered" and q2["source"] == "feed" and q2["fetched_at"]
    a = await answers(store)
    assert len(a) == 10 and all(x["validated"] and x["prompt_version"] == "v1" and x["model"] == "fake-1" for x in a.values())
    first = a["strategy-moat"]["answer"]
    assert first["covered"] is True and [s["quote_ref"] for s in first["sentences"]] == ["page 1", "page 1"]
    assert a["risks-raised"]["answer"] == {"covered": False, "sentences": []} and a["risks-raised"]["validated"] is True
    assert a["margins-costs"]["answer"]["sentences"][0]["quote"] == Q3
    # Q1 has no previous call stored (Q4 FY26 is not collected), Q2 does have Q1: its "what changed" is asked
    assert a["what-changed"]["validated"] and a["what-changed"]["answer"]["covered"] is False      # the fake model has nothing to say about it
    assert len(await answers(store, fy=2027, q=1)) == 9                                              # the older call has no previous call: nine questions
    before = p.requests
    again = await run(store, p)
    assert p.requests == before and again["calls_summarised"] == 0 and again["answers_stored"] == 0
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM earnings_call_answers") == 19
    assert (await answers(store))["strategy-moat"]["generated_at"] == a["strategy-moat"]["generated_at"]


async def test_one_request_asks_every_question_of_a_call_and_the_prompt_holds_only_that_calls_text(store):  # noqa: F811
    await seed(store)
    p = FakeProvider(honest_answers)
    await run(store, p, max_calls=1)
    assert p.requests == 1
    system, user = p.prompts[0]
    assert user.count('- id "') == 10 and "TRANSCRIPT OF THE PREVIOUS CALL (Q1 FY27)" in user and "Acme Industries" in user and "Use ONLY" in system
    async with store.pool.acquire() as conn:
        # the first call in the order is the newest (Q2): it has a previous call, so ten questions; the older call is still waiting for the next run
        assert await conn.fetchval("SELECT status FROM earnings_calls WHERE quarter = 1") == "text_ok"


# ------------------------------------------------------------------------------------------------ validation in the job
async def test_a_hallucinated_quote_is_never_stored_as_valid_and_the_question_is_asked_again(store):  # noqa: F811
    await seed(store, feed=True)
    bad = {"covered": True, "sentences": [good("Management is expanding into Brazil.", "We are opening a new plant in Brazil to serve customers in South America"),
                                          good("It also plans a plant in Chile.", "The Chile plant will double our capacity by next year according to the board")]}

    def answer(ids, user):
        out = honest_answers(ids, user)
        out["strategy-moat"] = bad
        return out
    p = FakeProvider(answer)
    res = await run(store, p, max_calls=1)
    assert p.requests == 2                                    # the second request carries only the failed question
    assert 'id "strategy-moat"' in p.prompts[1][1] and p.prompts[1][1].count('- id "') == 1 and "quotes could not be found" in p.prompts[1][1]
    a = await answers(store)
    sm = a["strategy-moat"]
    assert sm["validated"] is False and sm["answer"] == {"covered": False, "sentences": []} and sm["reject_reason"].startswith("too_few_valid_sentences:quote_not_found")
    assert a["margins-costs"]["validated"] is True and res["answers_rejected"] == 1 and res["dropped_sentences"]["quote_not_found"] == 4
    # tomorrow it is asked again (up to MAX_ANSWER_ATTEMPTS times), then left alone
    for _ in range(C.MAX_ANSWER_ATTEMPTS - 1):
        await run(store, p, max_calls=1)
    assert (await answers(store))["strategy-moat"]["attempts"] == C.MAX_ANSWER_ATTEMPTS
    def asked():
        return sum("This call: Q2 FY27" in u and 'id "strategy-moat"' in u for _, u in p.prompts)
    before = asked()
    await run(store, p, max_calls=1)
    assert asked() == before and (await answers(store))["strategy-moat"]["attempts"] == C.MAX_ANSWER_ATTEMPTS      # given up for this prompt version


async def test_a_bad_first_try_is_repaired_by_the_second_request(store):  # noqa: F811
    await seed(store)
    state = {"n": 0}

    def answer(ids, user):
        state["n"] += 1
        out = honest_answers(ids, user)
        if state["n"] == 1:
            out["margins-costs"] = {"covered": True, "sentences": [good("Margins rose.", Q3), good("Costs fell.", "raw material costs fell by thirty percent in the quarter overall")]}
        return out
    p = FakeProvider(answer)
    await run(store, p, max_calls=1)
    a = (await answers(store))["margins-costs"]
    assert p.requests == 2 and a["validated"] and len(a["answer"]["sentences"]) == 2 and a["attempts"] == 1


async def test_advice_words_are_rejected_and_never_reach_the_database_as_valid(store):  # noqa: F811
    await seed(store)

    def answer(ids, user):
        out = honest_answers(ids, user)
        out["capex-debt"] = {"covered": True, "sentences": [good("Investors should buy ahead of the expansion.", Q1), good("The price target looks conservative.", Q3)]}
        return out
    p = FakeProvider(answer)
    res = await run(store, p, max_calls=1)
    a = (await answers(store))["capex-debt"]
    assert a["validated"] is False and a["answer"]["sentences"] == [] and "advice" in a["reject_reason"]
    assert res["dropped_sentences"]["advice"] == 4
    async with store.pool.acquire() as conn:
        stored = " ".join(r["answer"] for r in await conn.fetch("SELECT answer::text FROM earnings_call_answers WHERE validated"))
    for w in ("should buy", "price target"):
        assert w not in stored


async def test_not_covered_is_stored_as_a_valid_answer_and_a_missing_answer_is_not(store):  # noqa: F811
    await seed(store)

    def answer(ids, user):
        out = honest_answers(ids, user)
        del out["risks-raised"]                              # the model forgot a question: that is NOT "not covered"
        return out
    await run(store, FakeProvider(answer), max_calls=1)
    a = await answers(store)
    assert a["management-changes"]["validated"] and a["management-changes"]["answer"]["covered"] is False
    assert a["risks-raised"]["validated"] is False and a["risks-raised"]["reject_reason"] == "no_usable_answer"


# ------------------------------------------------------------------------------------------------ prompt versions
async def test_a_validated_answer_is_replaced_only_by_a_validated_one_under_a_new_prompt_version(store, monkeypatch):  # noqa: F811
    await seed(store)
    await run(store, FakeProvider(honest_answers), max_calls=1)
    old = (await answers(store))["margins-costs"]
    monkeypatch.setattr(S, "PROMPT_VERSION", "v2")
    broken = {"covered": True, "sentences": [good("Invented.", "this sentence was never said by anyone on the call at all")]}

    def worse(ids, user):
        out = honest_answers(ids, user)
        out["margins-costs"] = broken
        return out
    await run(store, FakeProvider(worse), max_calls=1)
    kept = (await answers(store))["margins-costs"]
    assert kept["validated"] and kept["prompt_version"] == "v1" and kept["answer"] == old["answer"] and kept["last_version"] == "v2" and kept["attempts"] == 1   # still the old, checked text
    other = (await answers(store))["strategy-moat"]
    assert other["prompt_version"] == "v2" and other["validated"]                        # the others were answered again
    await run(store, FakeProvider(honest_answers), max_calls=1)
    new = (await answers(store))["margins-costs"]
    assert new["validated"] and new["prompt_version"] == "v2" and new["generated_at"] > old["generated_at"]


# ------------------------------------------------------------------------------------------------ limits and rate limits
async def test_a_429_waits_and_retries_and_a_daily_quota_stops_the_run_cleanly(store):  # noqa: F811
    await seed(store)
    waited = []

    async def sleep(s):
        waited.append(s)
    p = FakeProvider(honest_answers)
    p.raises = [RateLimited(retry_after=45)]
    res = await S.run(store, make_settings(), provider=p, fetcher=exchange(), env=ENV, today=TODAY, max_calls=1, sleep=sleep)
    assert res["rate_limited"] == 1 and 45 in waited and p.requests == 2 and res["calls_summarised"] == 1
    await seed(store)
    q = FakeProvider(honest_answers)
    q.raises = [RateLimited(daily=True)]
    res = await S.run(store, make_settings(), provider=q, fetcher=exchange(), env=ENV, today=TODAY, sleep=nosleep)
    assert res["stopped"] == "the provider's daily quota is spent" and res["calls_summarised"] == 0 and res["status"] == "ok"
    again = await S.run(store, make_settings(), provider=FakeProvider(honest_answers), fetcher=exchange(), env=ENV, today=TODAY, sleep=nosleep)
    assert again["calls_summarised"] == 0 and again["stopped"] == "the daily request budget is used"      # the day's budget is shared between runs (Redis)


async def test_the_daily_request_budget_and_the_per_run_call_limit_bound_the_cost(store):  # noqa: F811
    await seed(store)
    p = FakeProvider(honest_answers)
    res = await run(store, p, env={**ENV, "EARNINGS_LLM_PER_DAY": "0"})
    assert p.requests == 0 and res["stopped"] and res["calls_summarised"] == 0
    await store.redis.flushdb()
    p2 = FakeProvider(honest_answers)
    res = await run(store, p2, max_calls=1)
    assert p2.requests == 1 and res["calls_summarised"] == 1 and res["stopped"] == "per-run limit"


# ------------------------------------------------------------------------------------------------ collection
async def test_the_largest_companies_only_and_only_the_latest_quarters(store):  # noqa: F811
    await seed(store, symbols=("ACME", "BIGCO", "TINYCO"))
    async with store.pool.acquire() as conn:
        await conn.execute("UPDATE listing_quotes SET market_cap = CASE symbol WHEN 'BIGCO' THEN 900000 WHEN 'ACME' THEN 500 ELSE 1 END WHERE symbol IN ('ACME','BIGCO','TINYCO')")
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, link, item_date, category, auto, dedupe) VALUES ('document','Transcript of Q4 FY26 earnings call','ACME',$1,'2026-05-10','Analyst Call',true,'old')", URL_Q1.replace("28072026", "10052026"))
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, link, item_date, category, auto, dedupe) VALUES ('document','Transcript of Q2 FY27 earnings call','TINYCO',$1,'2026-10-23','Analyst Call',true,'tiny')", URL)
    report = {}
    await S.collect(store, exchange(), report, {"EARNINGS_TOP_COMPANIES": "2", "EARNINGS_QUARTERS": "2"}, TODAY)
    async with store.pool.acquire() as conn:
        got = {(r["symbol"], r["fiscal_year"], r["quarter"]) for r in await conn.fetch("SELECT * FROM earnings_calls")}
    assert got == {("ACME", 2027, 2), ("ACME", 2027, 1)}      # TINYCO is outside the top 2 by market cap; Q4 FY26 is older than the latest two quarters
    widened = {}
    await S.collect(store, exchange(), widened, {"EARNINGS_TOP_COMPANIES": "3", "EARNINGS_QUARTERS": "3"}, TODAY)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM earnings_calls") == 4                    # widening is only a number


async def test_the_exchange_list_is_used_for_companies_the_stored_feed_does_not_cover(store):  # noqa: F811
    await seed(store, feed=False)
    nse = json.loads((FIX / "nse_announcements.json").read_text())
    f = exchange(nse=nse)
    report = {}
    await S.collect(store, f, report, ENV, TODAY)
    assert report["nse_lookups"] == 1 and report["from_nse"] == 2
    assert any("nseindia.com/api/corporate-announcements?index=equities&symbol=ACME" in u for u in f.seen)
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT fiscal_year, quarter, source, call_date, transcript_url FROM earnings_calls ORDER BY quarter DESC")
    assert [(r["fiscal_year"], r["quarter"], r["source"]) for r in rows] == [(2027, 2, "nse"), (2027, 1, "nse")] and rows[0]["call_date"] == date(2026, 10, 20)
    again = {}
    await S.collect(store, exchange(nse=nse), again, ENV, TODAY)
    assert again["nse_lookups"] == 0                         # each company is asked about at most once in three days


async def test_a_refusing_exchange_is_left_alone_and_a_scan_is_marked_unreadable(store):  # noqa: F811
    await seed(store, feed=False)
    f = exchange(refuse=("www.nseindia.com",))
    report = {}
    await S.collect(store, f, report, ENV, TODAY)
    assert "refused" in report["nse_blocked"] and "www.nseindia.com" in f.blocked
    await seed(store)
    scan = exchange(pdf=T_make_blank())
    rep = {}
    await S.collect(store, scan, rep, ENV, TODAY)
    await S.download_pending(store, scan, rep)
    async with store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM earnings_calls WHERE status = 'unreadable'") == 2
        assert await conn.fetchval("SELECT count(*) FROM earnings_call_text") == 0
    assert rep["unreadable"] == 2


def T_make_blank():
    from earnings_fakes import make_pdf
    return make_pdf([[""], [""]])


async def test_a_failed_download_is_retried_later_and_not_before(store):  # noqa: F811
    await seed(store)
    boom = T.Fetcher(budget=20, transport=httpx.MockTransport(lambda r: httpx.Response(404)), sleep=nosleep, pause=0)
    rep = {}
    await S.collect(store, boom, rep, ENV, TODAY)
    await S.download_pending(store, boom, rep)
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT status, attempts, note FROM earnings_calls")
    assert {r["status"] for r in rows} == {"failed"} and {r["attempts"] for r in rows} == {1} and "HTTP 404" in rows[0]["note"]
    rep2 = {}
    await S.download_pending(store, exchange(), rep2)
    assert rep2["downloaded"] == 0                            # two days must pass first
    await S.download_pending(store, exchange(), rep2, now=datetime.now(timezone.utc) + timedelta(days=3))   # the first try is stamped with the clock, so the retry date is read from the clock too
    assert rep2["downloaded"] == 2
