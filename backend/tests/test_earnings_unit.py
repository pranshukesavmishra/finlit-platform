"""Earnings-call summaries, parts that need no database: quote validation, advice words, quarters, announcement parsing, the PDF, the model client, the polite fetcher."""
import json
from datetime import date, datetime

import httpx
import pytest

from earnings_fakes import FIX, PAGES, Q1, Q3, Q5, TEXT, fixture_pdf, good, make_pdf
from finlit.earnings import config as C
from finlit.earnings import transcripts as T
from finlit.earnings.provider import GeminiProvider, NotConfigured, Pacer, ProviderError, RateLimited
from finlit.earnings.questions import BY_ID, PROMPT_VERSION, QUESTIONS, build_prompt, public_questions
from finlit.earnings.validate import Transcript, advice_words, check_answer, enough, normalise, parse_json

DOC = Transcript.from_text("Q2 FY27", TEXT)


# ------------------------------------------------------------------------------------------------ the questions
def test_ten_fixed_questions_with_unique_ids_and_one_that_needs_the_previous_call():
    assert [q.id for q in QUESTIONS] == ["strategy-moat", "guidance-outlook", "margins-costs", "demand-orders", "capex-debt", "risks-raised", "management-changes",
                                         "what-changed", "capital-allocation", "analyst-concerns"]
    assert [q.id for q in QUESTIONS if q.needs_previous] == ["what-changed"]
    assert all(q.label and q.title and q.ask for q in QUESTIONS) and PROMPT_VERSION
    assert len(public_questions(with_previous=False)) == 9


def test_the_prompt_carries_only_the_transcript_and_the_hard_rules():
    p = build_prompt("Acme", "Q2 FY27", [BY_ID["strategy-moat"]], "THE TEXT")
    assert "THE TEXT" in p["user"] and 'id "strategy-moat"' in p["user"] and "PREVIOUS CALL" not in p["user"]
    for rule in ("word for word", "Never give advice", "covered to false", "Use ONLY"):
        assert rule in p["system"]
    q = build_prompt("Acme", "Q2 FY27", [BY_ID["what-changed"]], "NOW", previous="BEFORE", previous_label="Q1 FY27")
    assert "BEFORE" in q["user"] and "PREVIOUS CALL (Q1 FY27)" in q["user"]


# ------------------------------------------------------------------------------------------------ quote validation
def test_a_real_quote_is_found_with_its_page_and_survives_line_breaks_case_and_curly_quotes():
    assert DOC.find(Q1) == 1 and DOC.find(Q3) == 2 and DOC.find(Q5) == 3
    assert DOC.find(Q1.upper().replace(" ", "  ")) == 1                      # white space and case do not matter
    assert normalise("Don’t “quote” me – invest-\nment") == normalise("Don't \"quote\" me - investment")


def test_a_hallucinated_quote_is_rejected():
    raw = {"covered": True, "sentences": [good("Management is building a plant in Brazil.", "We are building a new plant in Brazil to serve South American customers"),
                                          good("Margins rose.", Q3)]}
    c = check_answer(raw, DOC)
    assert [s["text"] for s in c.sentences] == ["Margins rose."] and c.dropped[0][0] == "quote_not_found"
    assert not enough(c, final=False) and enough(c, final=True)               # one good sentence of two: asked again, accepted on the last attempt


def test_a_quote_that_is_too_short_or_too_long_is_not_accepted():
    raw = {"covered": True, "sentences": [good("Short.", "cost advantage"), good("Long.", "x" * 500)]}
    c = check_answer(raw, DOC)
    assert c.sentences == [] and [d[0] for d in c.dropped] == ["quote_size", "quote_size"] and c.claimed and not enough(c, final=True)


def test_advice_words_are_rejected_in_a_sentence_but_not_in_a_quote():
    assert advice_words("Analysts should buy the stock") == ["buy"]
    assert advice_words("We recommend this; the price target is high.") == ["price target", "recommend", "target", "we recommend"]
    assert advice_words("Management will hold a call and has a target of 15 percent") == ["hold", "target"]
    assert advice_words("The buyback was not planned and stakeholders were told") == []             # whole words only
    raw = {"covered": True, "sentences": [good("Investors may want to buy now.", Q1), good("Management has a stated target for margins.", Q3), good("Margins rose.", Q3), good("Costs fell.", Q1)]}
    c = check_answer(raw, DOC)
    assert [s["text"] for s in c.sentences] == ["Margins rose.", "Costs fell."] and {d[0].split(":")[0] for d in c.dropped} == {"advice"}
    quote_with_target = "Our integrated plants at Dahej give us a cost position"
    assert check_answer({"covered": True, "sentences": [good("Plants matter.", quote_with_target), good("Again.", Q1)]}, DOC).sentences       # quotes are not scanned


def test_not_covered_stands_only_when_the_model_said_so():
    said = check_answer({"covered": False, "sentences": []}, DOC)
    assert said.covered is False and enough(said, final=False)
    lazy = check_answer({"covered": True, "sentences": []}, DOC)                     # "covered" with nothing behind it is not an answer
    assert lazy.covered is False and not enough(lazy, final=True)
    gone = check_answer(None, DOC)                                                   # no answer at all must never be read as "not covered"
    assert gone.malformed and not enough(gone, final=True)
    assert check_answer({"covered": False, "sentences": [good("Margins rose.", Q3)]}, DOC).sentences == []


def test_at_most_six_sentences_and_a_previous_quote_is_checked_against_the_previous_call():
    many = {"covered": True, "sentences": [good(f"Point {i}.", Q1) for i in range(9)]}
    assert len(check_answer(many, DOC).sentences) == 6
    prev = Transcript.from_text("Q1 FY27", "Margins in the first quarter were under pressure from higher input costs and a weak product mix this time.")
    raw = {"covered": True, "sentences": [good("Last quarter margins were under pressure.", "Margins in the first quarter were under pressure from higher input costs", "previous"), good("Margins rose.", Q3)]}
    c = check_answer(raw, DOC, prev, allow_previous=True)
    assert [s["quote_ref"] for s in c.sentences] == ["Q1 FY27, page 1", "Q2 FY27, page 2"]
    assert check_answer(raw, DOC, None, allow_previous=False).sentences[0]["quote_ref"] == "page 2" and len(check_answer(raw, DOC).sentences) == 1     # a "previous" quote is nothing without that call


def test_the_models_json_is_read_with_or_without_a_code_fence_and_junk_is_empty():
    body = {"answers": {"a": {"covered": False, "sentences": []}}}
    assert parse_json(json.dumps(body)) == body["answers"]
    assert parse_json("```json\n" + json.dumps(body) + "\n```") == body["answers"]
    assert parse_json("Here you go: " + json.dumps(body)) == body["answers"]
    assert parse_json("not json") == {} and parse_json("") == {} and parse_json('{"answers": 3}') == {}


# ------------------------------------------------------------------------------------------------ quarters and announcements
def test_indian_fiscal_quarters():
    assert T.fiscal(date(2026, 10, 23)) == (2027, 3) and T.fiscal(date(2026, 4, 1)) == (2027, 1) and T.fiscal(date(2027, 3, 31)) == (2027, 4) and T.fiscal(date(2027, 1, 5)) == (2027, 4)
    assert T.quarter_end(2027, 2) == date(2026, 9, 30) and T.quarter_end(2027, 4) == date(2027, 3, 31)
    assert T.quarter_label(2027, 2) == "Q2 FY27" and T.previous_quarter(2027, 1) == (2026, 4)
    assert T.recent_quarters(date(2026, 11, 1), 2) == [(2027, 2), (2027, 1)]
    assert T.recent_quarters(date(2026, 10, 2), 2) == [(2027, 1), (2026, 4)]             # Q2 ended 2 days ago: its call cannot have been held yet
    assert T.quarter_for_call(date(2026, 10, 20)) == (2027, 2) and T.quarter_for_call(date(2026, 5, 14)) == (2026, 4)


@pytest.mark.parametrize("text,want", [
    ("Transcript of the Q2 FY27 earnings call", (2027, 2)), ("Q3FY2026-27 conference call transcript", (2027, 3)), ("transcript, FY27 Q1", (2027, 1)),
    ("Transcript for the quarter ended September 30, 2026", (2027, 2)), ("Transcript - quarter ended 31st March 2026", (2026, 4)), ("transcript of the call", None)])
def test_the_quarter_an_announcement_names(text, want):
    assert T.period_from_text(text) == want


def test_nse_announcements_become_candidates_and_only_real_transcripts_with_an_https_link_count():
    items = json.loads((FIX / "nse_announcements.json").read_text())
    cands = T.from_nse_json(items)
    assert [(c.symbol, c.period, c.call_date, c.url.rsplit("/", 1)[1]) for c in cands] == [
        ("ACME", (2027, 2), date(2026, 10, 20), "ACME_23102026182210_Transcript.pdf"), ("ACME", (2027, 1), None, "ACME_28072026174000_Transcript.pdf")]
    assert cands[0].filed.date() == date(2026, 10, 23) and cands[0].source == "nse"
    best = T.best_per_period(cands, [(2027, 2)])
    assert list(best) == [("ACME", 2027, 2)]


def test_the_stored_feed_and_the_providers_shape_parse_the_same_way():
    rows = [{"symbol": "ACME", "title": "Transcript of Q2 FY27 earnings call", "summary": None, "category": "Analyst Call", "link": "https://nsearchives.nseindia.com/c/a.pdf", "item_date": date(2026, 10, 23)},
            {"symbol": "ACME", "title": "Credit rating", "summary": None, "category": "Credit Rating", "link": "https://nsearchives.nseindia.com/c/b.pdf", "item_date": date(2026, 10, 23)}]
    c = T.from_feed_rows(rows)
    assert len(c) == 1 and c[0].period == (2027, 2) and c[0].source == "feed"
    prov = T.from_provider_json(json.loads((FIX.parent / "finedge" / "corp_announcements.json").read_text()))
    assert prov == []                                                      # the recorded Reliance feed holds no transcript
    one = T.from_provider_json([{"nse_code": "ACME", "category": "Updates", "description": "Transcript of earnings call for the quarter ended September 30, 2026",
                                 "announcement_date": "2026-10-23 18:00:00", "pdf_file_link": "https://nsearchives.nseindia.com/c/t.pdf"}])
    assert one[0].period == (2027, 2) and one[0].symbol == "ACME"


# ------------------------------------------------------------------------------------------------ the PDF
def test_the_fixture_pdf_gives_its_pages_and_the_quotes_are_found_in_them():
    pages = T.extract_pages(fixture_pdf())
    assert len(pages) == 3 and "Acme Industries" in pages[0] and "Net debt to EBITDA" in pages[1]
    doc = Transcript.from_pages("Q2 FY27", pages)
    assert doc.find(Q1) == 1 and doc.find(Q3) == 2 and doc.find(Q5) == 3
    assert T.sha256(fixture_pdf()) == T.sha256(make_pdf(PAGES))            # the checked-in file is what the builder makes


def test_a_file_that_is_not_a_pdf_or_has_no_text_gives_no_pages():
    assert T.extract_pages(b"<html>not a pdf</html>") == []
    assert "".join(T.extract_pages(make_pdf([[""]]))).strip() == ""


# ------------------------------------------------------------------------------------------------ the model client
async def test_gemini_reads_the_text_of_the_reply_and_never_puts_the_key_in_the_url():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"answers": '}, {"text": "{}}"}]}}]})
    p = GeminiProvider("sekret", "gemini-test", transport=httpx.MockTransport(handler))
    assert p.configured and await p.generate("sys", "usr") == '{"answers": {}}'
    assert "sekret" not in seen["url"] and seen["key"] == "sekret" and seen["url"].endswith("models/gemini-test:generateContent")
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json" and seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"
    await p.aclose()


async def test_gemini_without_a_key_says_so_and_a_429_carries_the_wait_and_the_daily_flag():
    p = GeminiProvider("", "m", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert not p.configured
    with pytest.raises(NotConfigured):
        await p.generate("s", "u")
    for body, daily in (('{"error": {"details": [{"retryDelay": "34s"}]}}', False), ('{"error": {"message": "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel"}}', True)):
        q = GeminiProvider("k", "m", transport=httpx.MockTransport(lambda r, b=body: httpx.Response(429, text=b)))
        with pytest.raises(RateLimited) as e:
            await q.generate("s", "u")
        assert e.value.daily is daily and (e.value.retry_after == 34 or daily)
    bad = GeminiProvider("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": []})))
    with pytest.raises(ProviderError):
        await bad.generate("s", "u")


async def test_the_pacer_spaces_requests_and_stops_at_the_daily_budget():
    waits, now = [], [0.0]

    async def sleep(s):
        waits.append(round(s, 1))
        now[0] += s
    pc = Pacer(per_minute=6, per_day=3, redis=None, clock=lambda: now[0], sleep=sleep)
    assert [await pc.take() for _ in range(4)] == [True, True, True, False]
    assert waits == [10.0, 10.0] and await pc.left_today() == 0


# ------------------------------------------------------------------------------------------------ the polite fetcher
def exchange(handler):
    async def nosleep(_):
        return None
    return T.Fetcher(budget=10, transport=httpx.MockTransport(handler), sleep=nosleep, pause=0)


async def test_only_https_exchange_hosts_are_fetched_and_robots_txt_is_obeyed():
    calls = []

    def handler(req: httpx.Request):
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        return httpx.Response(200, content=fixture_pdf())
    f = exchange(handler)
    assert (await f.pdf("https://nsearchives.nseindia.com/corporate/a.pdf")).startswith(b"%PDF")
    with pytest.raises(T.Blocked):
        await f.pdf("https://nsearchives.nseindia.com/private/a.pdf")
    with pytest.raises(T.FetchFailed):
        await f.pdf("https://evil.example.com/a.pdf")
    with pytest.raises(T.FetchFailed):
        await f.pdf("http://nsearchives.nseindia.com/a.pdf")
    with pytest.raises(T.FetchFailed):
        await f.pdf("https://nseindia.com.evil.example/a.pdf")
    assert calls == ["https://nsearchives.nseindia.com/robots.txt", "https://nsearchives.nseindia.com/corporate/a.pdf"]
    await f.aclose()


async def test_a_refusal_stops_the_host_and_the_request_budget_ends_the_run():
    def refuse(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(403)
    f = exchange(refuse)
    with pytest.raises(T.Blocked):
        await f.pdf("https://nsearchives.nseindia.com/a.pdf")
    with pytest.raises(T.Blocked):                                           # asked once, then left alone for the rest of the run
        await f.pdf("https://nsearchives.nseindia.com/b.pdf")
    assert f.requests == 2
    tiny = T.Fetcher(budget=1, transport=httpx.MockTransport(lambda r: httpx.Response(404)), sleep=lambda s: _noop(), pause=0)
    with pytest.raises(T.BudgetSpent):
        await tiny.pdf("https://nsearchives.nseindia.com/a.pdf")


async def _noop():
    return None


async def test_a_429_is_retried_after_a_wait_and_a_non_pdf_is_refused():
    state = {"n": 0}
    waited = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        state["n"] += 1
        return httpx.Response(429, headers={"retry-after": "7"}) if state["n"] == 1 else httpx.Response(200, content=b"<html>login</html>")

    async def sleep(s):
        waited.append(s)
    f = T.Fetcher(budget=10, transport=httpx.MockTransport(handler), sleep=sleep, pause=0)
    with pytest.raises(T.FetchFailed, match="not a PDF"):
        await f.pdf("https://www.bseindia.com/x.pdf")
    assert 7 in waited


def test_the_free_tier_numbers_stay_inside_the_published_limits():
    assert C.LLM_REQUESTS_PER_MINUTE <= 10 and C.LLM_REQUESTS_PER_DAY <= 200 and C.MAX_CALLS_PER_RUN <= C.LLM_REQUESTS_PER_DAY
    assert C.TOP_COMPANIES == 300 and C.LATEST_QUARTERS == 2 and C.CALLS_PER_MONTH_GOLD == 5
    assert C.top_companies({"EARNINGS_TOP_COMPANIES": "50"}) == 50 and C.top_companies({"EARNINGS_TOP_COMPANIES": "x"}) == 300 and C.latest_quarters({"EARNINGS_QUARTERS": "0"}) == 1
