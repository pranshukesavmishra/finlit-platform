"""The nightly job (collect transcripts, extract text, ask the fixed questions, validate, store) and the reads the API needs (docs/EARNINGS-CALLS.md).

Everything the site shows was produced here, offline, and checked before it was stored. The API only reads these tables.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import config as C
from . import transcripts as T
from .provider import LlmProvider, NotConfigured, Pacer, ProviderError, RateLimited
from .questions import BY_ID, PROMPT_VERSION, QUESTIONS, Question, build_prompt
from .validate import Checked, Transcript, check_answer, enough, parse_json

log = logging.getLogger("finlit.earnings")
IST = timezone(timedelta(hours=5, minutes=30))
SEARCH_BACK_DAYS = 230          # how far back the stored feed is searched: more than the latest two quarters


class QuotaStop(Exception):
    """The model's quota (ours or the provider's) is spent for now: the run ends cleanly and tomorrow's run continues."""


def india_now() -> datetime:
    return datetime.now(IST)


# ================================================================================================ collection
async def universe(conn, n: int) -> List[str]:
    rows = await conn.fetch("SELECT c.symbol FROM companies c JOIN listing_quotes q ON q.symbol = c.symbol WHERE q.market_cap IS NOT NULL "
                            "ORDER BY q.market_cap DESC, c.symbol LIMIT $1", n)
    return [r["symbol"] for r in rows]


async def save_candidates(conn, best: Mapping[Tuple[str, int, int], T.Candidate]) -> int:
    """New calls are inserted as 'found'. A call that has no text yet takes a newer filing's link; one that has text keeps it."""
    n = 0
    for (sym, fy, q), c in best.items():
        r = await conn.execute(
            "INSERT INTO earnings_calls (symbol, fiscal_year, quarter, call_date, filed_at, transcript_url, source) VALUES ($1,$2,$3,$4,$5,$6,$7) "
            "ON CONFLICT (symbol, fiscal_year, quarter) DO UPDATE SET transcript_url = EXCLUDED.transcript_url, filed_at = EXCLUDED.filed_at, "
            "call_date = COALESCE(EXCLUDED.call_date, earnings_calls.call_date), source = EXCLUDED.source "
            "WHERE earnings_calls.status IN ('found', 'failed') AND EXCLUDED.filed_at > COALESCE(earnings_calls.filed_at, '-infinity') AND EXCLUDED.transcript_url <> earnings_calls.transcript_url",
            sym, fy, q, c.call_date, c.filed, c.url, c.source)
        n += 1 if r.endswith(" 1") else 0
    return n


async def collect(store, fetcher: T.Fetcher, report: dict, env: Optional[Mapping[str, str]] = None, today: Optional[date] = None) -> None:
    env = os.environ if env is None else env
    today = today or india_now().date()
    wanted = T.recent_quarters(today, C.latest_quarters(env))
    async with store.pool.acquire() as conn:
        symbols = await universe(conn, C.top_companies(env))
        since = today - timedelta(days=SEARCH_BACK_DAYS)
        rows = [dict(r) for r in await conn.fetch(
            "SELECT symbol, title, summary, category, link, item_date FROM feed_items WHERE symbol = ANY($1::text[]) AND item_date >= $2 "
            "AND (title ILIKE '%transcript%' OR summary ILIKE '%transcript%' OR link ILIKE '%transcript%')", symbols, since)]
        best = T.best_per_period(T.from_feed_rows(rows), wanted)
        report["from_feed"] = await save_candidates(conn, best)
        have = {(r["symbol"], r["fiscal_year"], r["quarter"]) for r in await conn.fetch(
            "SELECT symbol, fiscal_year, quarter FROM earnings_calls WHERE symbol = ANY($1::text[])", symbols)}
    # companies with a wanted quarter still missing: ask the exchange (a few per run, each company at most once in 3 days)
    missing = [s for s in symbols if any((s, fy, q) not in have for fy, q in wanted)]
    looked = 0
    for sym in missing:
        if looked >= C.NSE_LOOKUPS_PER_RUN or "www.nseindia.com" in fetcher.blocked:
            break
        key = f"earnings:nse:{sym}"
        try:
            if not await store.redis.set(key, "1", nx=True, ex=3 * 86400):
                continue
        except Exception:
            pass
        looked += 1
        try:
            items = await fetcher.nse_announcements(sym, since, today)
        except T.BudgetSpent:
            report["budget_spent"] = True
            break
        except T.Blocked as exc:
            report["nse_blocked"] = str(exc)
            break
        except T.FetchFailed as exc:
            report.setdefault("nse_errors", []).append(f"{sym}: {exc}")
            continue
        cands = [c for c in T.from_nse_json(items) if c.symbol == sym]
        async with store.pool.acquire() as conn:
            report["from_nse"] = report.get("from_nse", 0) + await save_candidates(conn, T.best_per_period(cands, wanted))
    report["nse_lookups"] = looked


async def download_pending(store, fetcher: T.Fetcher, report: dict, limit: int = C.MAX_DOWNLOADS_PER_RUN, min_chars: Optional[int] = None, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    min_chars = C.MIN_TEXT_CHARS if min_chars is None else min_chars
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, symbol, transcript_url, attempts FROM earnings_calls WHERE transcript_url IS NOT NULL AND "
            "(status = 'found' OR (status = 'failed' AND attempts < $1 AND (fetched_at IS NULL OR fetched_at < $2))) "
            "ORDER BY COALESCE(call_date, filed_at::date) DESC NULLS LAST, id LIMIT $3", C.MAX_DOWNLOAD_ATTEMPTS, now - timedelta(days=C.RETRY_FAILED_AFTER_DAYS), limit)
    done = failed = unreadable = 0
    for r in rows:
        try:
            pdf = await fetcher.pdf(r["transcript_url"])
        except T.BudgetSpent:
            report["budget_spent"] = True
            break
        except T.Blocked as exc:
            report["download_blocked"] = str(exc)
            break
        except T.FetchFailed as exc:
            failed += 1
            async with store.pool.acquire() as conn:
                await conn.execute("UPDATE earnings_calls SET status='failed', attempts=attempts+1, note=$2, fetched_at=now() WHERE id=$1", r["id"], str(exc)[:200])
            continue
        pages = T.extract_pages(pdf)
        text = T.join_pages(pages)
        digest = T.sha256(pdf)
        async with store.pool.acquire() as conn:
            if len(text.replace("\f", "").strip()) < min_chars:
                unreadable += 1
                await conn.execute("UPDATE earnings_calls SET status='unreadable', transcript_sha256=$2, text_chars=$3, pages=$4, note=$5, fetched_at=now() WHERE id=$1",
                                   r["id"], digest, len(text), len(pages), "no readable text: a scan or a short note")
                continue
            async with conn.transaction():
                await conn.execute("INSERT INTO earnings_call_text (call_id, body) VALUES ($1,$2) ON CONFLICT (call_id) DO UPDATE SET body = EXCLUDED.body", r["id"], text)
                await conn.execute("UPDATE earnings_calls SET status='text_ok', transcript_sha256=$2, text_chars=$3, pages=$4, note=NULL, fetched_at=now() WHERE id=$1",
                                   r["id"], digest, len(text), len(pages))
        done += 1
    report.update(downloaded=done, download_failed=failed, unreadable=unreadable)


# ================================================================================================ answers
def _cut(body: str, cap: int) -> List[str]:
    """The pages of the transcript as the model sees them: cut at `cap` characters (inside a page only when the first page alone is longer).
    Quotes are checked against these same pages."""
    keep, total = [], 0
    for p in body.split("\f"):
        if total + len(p) > cap:
            if not keep:
                keep.append(p[:cap])
            break
        keep.append(p)
        total += len(p) + 1
    return keep


def _prompt_text(pages: Sequence[str]) -> str:
    return "\n\n".join(f"[page {i + 1}]\n{p}" for i, p in enumerate(pages))


async def pending_for(conn, call_id: int, have_previous: bool) -> List[Question]:
    """The questions still to ask of this call: never asked, answered under an older prompt version, or failed validation fewer than MAX_ANSWER_ATTEMPTS times
    under the current one. A validated answer of the current version is never asked again."""
    rows = {r["question_id"]: r for r in await conn.fetch("SELECT question_id, validated, prompt_version, last_version, attempts FROM earnings_call_answers WHERE call_id = $1", call_id)}
    out = []
    for q in QUESTIONS:
        if q.needs_previous and not have_previous:
            continue
        r = rows.get(q.id)
        if r is not None and r["validated"] and r["prompt_version"] == PROMPT_VERSION:
            continue
        if r is not None and r["last_version"] == PROMPT_VERSION and r["attempts"] >= C.MAX_ANSWER_ATTEMPTS:
            continue
        out.append(q)
    return out


# A validated answer is never overwritten, except by a validated one under a new prompt version. Every attempt is counted (per prompt version) either way.
_REPLACE = "(NOT a.validated OR (EXCLUDED.validated AND a.prompt_version <> EXCLUDED.prompt_version))"
UPSERT_ANSWER = (
    "INSERT INTO earnings_call_answers AS a (call_id, question_id, answer, model, prompt_version, last_version, validated, attempts, reject_reason) "
    "VALUES ($1,$2,$3::jsonb,$4,$5,$5,$6,1,$7) ON CONFLICT (call_id, question_id) DO UPDATE SET "
    f"answer = CASE WHEN {_REPLACE} THEN EXCLUDED.answer ELSE a.answer END, "
    f"model = CASE WHEN {_REPLACE} THEN EXCLUDED.model ELSE a.model END, "
    f"generated_at = CASE WHEN {_REPLACE} THEN now() ELSE a.generated_at END, "
    f"validated = CASE WHEN {_REPLACE} THEN EXCLUDED.validated ELSE a.validated END, "
    f"prompt_version = CASE WHEN {_REPLACE} THEN EXCLUDED.prompt_version ELSE a.prompt_version END, "
    "attempts = CASE WHEN a.last_version = EXCLUDED.last_version THEN a.attempts + 1 ELSE 1 END, "
    "last_version = EXCLUDED.last_version, reject_reason = EXCLUDED.reject_reason")


async def ask(provider: LlmProvider, pacer: Pacer, prompt: Dict[str, str], report: dict, sleep=asyncio.sleep) -> Optional[str]:
    """One request, paced, with back-off on 429. Raises QuotaStop when the day's budget is gone."""
    for wait in (0.0, *C.LLM_BACKOFF_SECONDS):
        if not await pacer.take():
            raise QuotaStop("the daily request budget is used")
        try:
            report["llm_requests"] = report.get("llm_requests", 0) + 1
            return await provider.generate(prompt["system"], prompt["user"])
        except RateLimited as exc:
            report["rate_limited"] = report.get("rate_limited", 0) + 1
            if exc.daily:
                await pacer.exhaust()
                raise QuotaStop("the provider's daily quota is spent") from None
            await sleep(max(exc.retry_after, wait))
        except ProviderError as exc:
            report.setdefault("provider_errors", []).append(str(exc)[:80])
            return None
    raise QuotaStop("still rate limited after the back-off")


async def summarise_call(store, provider: LlmProvider, pacer: Pacer, call: Mapping[str, Any], report: dict, name: str, sleep=asyncio.sleep) -> Tuple[int, int]:
    """Ask every pending question of one call in one request (a second request only for questions whose quotes did not check out).
    Returns (questions stored as validated, questions rejected)."""
    async with store.pool.acquire() as conn:
        body = await conn.fetchval("SELECT body FROM earnings_call_text WHERE call_id = $1", call["id"])
        prev_fy, prev_q = T.previous_quarter(call["fiscal_year"], call["quarter"])
        prev = await conn.fetchrow("SELECT t.body FROM earnings_calls c JOIN earnings_call_text t ON t.call_id = c.id WHERE c.symbol = $1 AND c.fiscal_year = $2 AND c.quarter = $3",
                                   call["symbol"], prev_fy, prev_q)
        todo = await pending_for(conn, call["id"], prev is not None)
    if not body or not todo:
        return 0, 0
    label, prev_label = T.quarter_label(call["fiscal_year"], call["quarter"]), T.quarter_label(prev_fy, prev_q)
    cur_pages = _cut(body, C.MAX_TRANSCRIPT_CHARS)
    cur = Transcript.from_pages(label, cur_pages)
    prv_pages = _cut(prev["body"], C.MAX_PREVIOUS_CHARS) if prev is not None else None
    prv = Transcript.from_pages(prev_label, prv_pages) if prv_pages is not None else None
    results: Dict[str, Checked] = {}
    asked = list(todo)
    for attempt in (1, 2):
        wants_prev = prv is not None and any(q.needs_previous for q in asked)
        prompt = build_prompt(name, label, asked, _prompt_text(cur_pages), previous=_prompt_text(prv_pages) if wants_prev else None, previous_label=prev_label)
        if attempt == 2:
            prompt["user"] += "\n\nYour earlier answer to these questions had sentences whose quotes could not be found in the transcript. Copy each quote exactly, character for character."
        answers = parse_json(await ask(provider, pacer, prompt, report, sleep) or "")
        retry = []
        for q in asked:
            c = results[q.id] = check_answer(answers.get(q.id), cur, prv, allow_previous=q.needs_previous)
            report.setdefault("dropped", []).extend(r for r, _ in c.dropped)
            if not enough(c, final=attempt == 2):
                retry.append(q)
        asked = retry
        if not asked:
            break
    ok = bad = 0
    async with store.pool.acquire() as conn:
        for q in todo:
            c = results[q.id]
            valid = enough(c, final=True)
            why = None if valid else ("no_usable_answer" if c.malformed else "too_few_valid_sentences:" + ",".join(sorted({r.split(":")[0] for r, _ in c.dropped}))[:150])
            await conn.execute(UPSERT_ANSWER, call["id"], q.id, json.dumps(c.as_answer()), provider.model, PROMPT_VERSION, valid, why)
            ok, bad = (ok + 1, bad) if valid else (ok, bad + 1)
        if not await pending_for(conn, call["id"], prev is not None):
            await conn.execute("UPDATE earnings_calls SET status = 'answered' WHERE id = $1 AND status = 'text_ok'", call["id"])
    return ok, bad


async def generate(store, provider: LlmProvider, pacer: Pacer, report: dict, max_calls: int = C.MAX_CALLS_PER_RUN, sleep=asyncio.sleep) -> None:
    async with store.pool.acquire() as conn:
        calls = [dict(r) for r in await conn.fetch(
            "SELECT c.id, c.symbol, c.fiscal_year, c.quarter, COALESCE(co.name, c.symbol) AS name FROM earnings_calls c LEFT JOIN companies co ON co.symbol = c.symbol "
            "WHERE c.status IN ('text_ok', 'answered') ORDER BY COALESCE(c.call_date, c.filed_at::date) DESC NULLS LAST, c.id")]
    done = ok = bad = 0
    for call in calls:
        if done >= max_calls:
            report["stopped"] = "per-run limit"
            break
        async with store.pool.acquire() as conn:
            if not await pending_for(conn, call["id"], True):
                continue
        try:
            o, b = await summarise_call(store, provider, pacer, call, report, call["name"], sleep)
        except QuotaStop as exc:
            report["stopped"] = str(exc)
            break
        except NotConfigured as exc:
            report["stopped"] = f"not configured: {exc}"
            report["status"] = "not_configured"
            break
        if o or b:
            done += 1
        ok, bad = ok + o, bad + b
    report.update(calls_summarised=done, answers_stored=ok, answers_rejected=bad)


async def run(store, settings, provider: Optional[LlmProvider] = None, fetcher: Optional[T.Fetcher] = None, env: Optional[Mapping[str, str]] = None,
               max_calls: int = C.MAX_CALLS_PER_RUN, today: Optional[date] = None, sleep=asyncio.sleep) -> dict:
    """The worker command. Idempotent and resumable: every step skips what is already done, and each is bounded."""
    from .provider import GeminiProvider
    env = os.environ if env is None else env
    provider = provider or GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    report: dict = {"status": "ok", "model": provider.model, "prompt_version": PROMPT_VERSION}
    if not provider.configured:
        await provider.aclose()
        return {"status": "not_configured", "detail": "GEMINI_API_KEY is empty: no transcripts are collected and no summaries are made."}
    own_fetcher = fetcher is None
    fetcher = fetcher or T.Fetcher()
    pacer = Pacer(C.llm_per_minute(env), C.llm_per_day(env), store.redis, sleep=sleep)
    try:
        await collect(store, fetcher, report, env, today)
        await download_pending(store, fetcher, report)
        await generate(store, provider, pacer, report, max_calls, sleep)
    finally:
        report["exchange_requests"] = fetcher.requests
        report["llm_left_today"] = await pacer.left_today()
        if own_fetcher:
            await fetcher.aclose()
        await provider.aclose()
    dropped = report.pop("dropped", [])
    if dropped:
        counts: Dict[str, int] = {}
        for d in dropped:
            counts[d.split(":")[0]] = counts.get(d.split(":")[0], 0) + 1
        report["dropped_sentences"] = counts
    return report


# ================================================================================================ reads for the API
def user_hash(secret: str, user_id: str) -> str:
    """Who opened a call, as a keyed hash: the table never holds an id or an email, and the hash cannot be rebuilt without the server's secret."""
    return hmac.new(("earnings-usage|" + secret).encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]


def month_key(now: Optional[datetime] = None) -> str:
    return (now or india_now()).astimezone(IST).strftime("%Y-%m")


async def list_calls(conn, symbol: str) -> List[dict]:
    rows = await conn.fetch(
        "SELECT c.id, c.fiscal_year, c.quarter, c.call_date, c.filed_at, c.transcript_url, c.pages, c.text_chars, "
        "(SELECT count(*) FROM earnings_call_answers a WHERE a.call_id = c.id AND a.validated) AS answers "
        "FROM earnings_calls c WHERE c.symbol = $1 AND c.status IN ('text_ok', 'answered') ORDER BY c.fiscal_year DESC, c.quarter DESC", symbol)
    return [dict(r) for r in rows]


async def usage_count(conn, uhash: str, month: str) -> int:
    return int(await conn.fetchval("SELECT count(*) FROM earnings_call_usage WHERE user_hash = $1 AND month = $2", uhash, month) or 0)


async def open_call(pool, uhash: str, month: str, call_id: int, limit: int) -> Tuple[bool, int]:
    """Count this call as opened by this member this month. Opening one already counted is free. Returns (allowed, calls used this month)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "earnings-usage|" + uhash)
            used = await usage_count(conn, uhash, month)
            if await conn.fetchval("SELECT 1 FROM earnings_call_usage WHERE user_hash = $1 AND month = $2 AND call_id = $3", uhash, month, call_id):
                return True, used
            if used >= limit:
                return False, used
            await conn.execute("INSERT INTO earnings_call_usage (user_hash, month, call_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", uhash, month, call_id)
            return True, used + 1


async def answers_for(conn, call_id: int) -> Dict[str, dict]:
    rows = await conn.fetch("SELECT question_id, answer, generated_at FROM earnings_call_answers WHERE call_id = $1 AND validated", call_id)
    out = {}
    for r in rows:
        a = r["answer"]
        out[r["question_id"]] = {**(json.loads(a) if isinstance(a, str) else a), "generatedAt": r["generated_at"].isoformat(timespec="seconds")}
    return out
