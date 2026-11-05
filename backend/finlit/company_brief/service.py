"""The nightly company-brief job (docs/COMPANY-BRIEF.md).

For each company, largest and most followed first: collect the filings FinLit already stores (announcements, results, presentations, transcripts) and the annual
report (address set by an administrator), decide with refresh_plan() which parts need writing (nothing new = nothing spent), read the PDFs, pick the pages, ask the
language model behind Ask FinLit AI, then validate() and check() the answer. The result is stored as a DRAFT; only a person publishes it.

Bounded: BRIEF_MAX_WRITES_PER_NIGHT model calls a run, a per-minute and per-day pace shared through Redis, a request budget for the exchanges, a time limit.
Resumable: every decision is made from what is stored, so the next run continues where this one stopped. With no key configured the run records "not configured"
and writes nothing: there is no invented text.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import socket
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import httpx

from ..earnings import transcripts as T
from ..earnings.provider import GeminiProvider, NotConfigured, Pacer, ProviderError, RateLimited
from . import config as C
from . import core as B

log = logging.getLogger("finlit.company_brief")

REASONS = {
    "no_annual_report": "No annual report is on file for this company yet, so the brief has not been written. An administrator can add the address in the Console.",
    "no_filings": "FinLit holds no results, presentation or press release for this company yet.",
    "unreadable": "The annual report could not be read (a scan, a password or an address that no longer works).",
    "failed": "The writer's answer did not pass the checks; it is tried again.",
}


class BriefFetcher(T.Fetcher):
    """The exchange-archive fetcher, widened to the https addresses an administrator set for annual reports (the company's own site). Same rules: robots.txt, an
    identifying agent, a pause, a budget, a byte cap. A host that resolves to a private address is refused."""

    def __init__(self, extra_hosts=(), resolve: Optional[Callable[[str], List[str]]] = None, **kw):
        super().__init__(**kw)
        self.extra_hosts = {h.lower() for h in extra_hosts}
        self._resolve = resolve or _resolve

    def host_ok(self, url: str) -> bool:      # type: ignore[override]
        p = urlsplit(url)
        if p.scheme != "https" or not p.hostname or p.port not in (None, 443):
            return False
        h = p.hostname.lower()
        if T.HOST_OK.match(h):
            return True
        if h not in self.extra_hosts or _is_ip(h):
            return False
        try:
            return all(ipaddress.ip_address(a).is_global for a in self._resolve(h))
        except Exception:
            return False

    async def pdf(self, url: str) -> bytes:   # type: ignore[override]
        r = await self._get(url, T.USER_AGENT, {"Accept": "application/pdf, */*"}, C.MAX_PDF_BYTES)
        if r.status_code != 200:
            raise T.FetchFailed(f"HTTP {r.status_code}")
        if not r.content.startswith(b"%PDF"):
            raise T.FetchFailed("not a PDF")
        return r.content


def _is_ip(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _resolve(host: str) -> List[str]:
    return [i[4][0] for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)]


def valid_report_url(url: str) -> Optional[str]:
    """None when the address can be used as an annual-report address, else the reason."""
    p = urlsplit(url or "")
    if p.scheme != "https" or not p.hostname:
        return "The address must start with https://"
    if p.port not in (None, 443) or _is_ip(p.hostname) or p.hostname.lower() in ("localhost",) or "." not in p.hostname:
        return "The address must be a public website name."
    if len(url) > 600 or re.search(r"\s", url):
        return "The address is not valid."
    return None


class BriefPacer(Pacer):
    def _key(self) -> str:
        return "brief:llm:" + time.strftime("%Y-%m-%d", time.gmtime())


def parse_json(text: str) -> Optional[dict]:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            return None
        try:
            v = json.loads(t[a:b + 1])
        except ValueError:
            return None
    return v if isinstance(v, dict) else None


# ------------------------------------------------------------------------------------------------ deciding what to do
def docs_map(docs: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {d["key"]: {"title": d["title"], "date": d.get("date"), "kind": B.KIND_LABEL.get(d["kind"], d["kind"]), "url": d["url"]} for d in docs}


def new_docs_for(brief: Optional[Dict[str, Any]], docs: Sequence[Dict[str, Any]], today: str) -> List[Dict[str, Any]]:
    """The documents the stored brief has not been written from. An annual report has no date: it is new when its address is not one the brief cites."""
    cited = {(d or {}).get("url") for d in ((brief or {}).get("docs") or {}).values()}
    out = []
    for d in docs:
        if d["kind"] == "annual_report":
            if d["url"] not in cited:
                out.append({**d, "date": today})
        elif d["url"] not in cited and (d.get("date") or "") > ((brief or {}).get("as_of") or ""):
            out.append(d)
    return out


def plan_parts(row: Optional[dict], docs: Sequence[Dict[str, Any]], today: str) -> Tuple[List[str], str, List[Dict[str, Any]]]:
    """(parts to write, why, the new documents). Empty parts = nothing to do."""
    has_ar = any(d["kind"] == "annual_report" for d in docs)
    if row is None:
        if not has_ar:
            return [], "no_annual_report", []
        return list(B.PARTS), "first brief", list(docs)
    brief = row["brief"]
    fresh = new_docs_for(brief, docs, today)
    if row.get("rewrite_asked"):
        return list(B.PARTS), "rewrite asked", fresh or list(docs)
    plan = B.refresh_plan(brief, fresh, today)
    parts = [p for p in B.PARTS if p in plan["rewrite"]]
    return (parts + ["gaps"] if parts else []), ("new filings" if parts else "nothing new"), fresh


def choose_docs(docs: Sequence[Dict[str, Any]], parts: Sequence[str], fresh: Sequence[Dict[str, Any]], first: bool, today: str) -> List[Dict[str, Any]]:
    """The PDFs to read: the annual report when the part needs it, then the newest relevant filings (a few of each kind), at most MAX_DOCS."""
    kinds = {k for k, ps in B.REFRESH.items() if set(ps) & set(parts)}
    out: List[Dict[str, Any]] = []
    ar = next((d for d in docs if d["kind"] == "annual_report"), None)
    if ar and (first or {"about", "group"} & set(parts)):
        out.append(ar)
    limit = {"results": 2, "press_release": 1, "presentation": 1, "transcript": 1, "event": 6, "annual_report": 0}
    cut = (date.fromisoformat(today) - timedelta(days=C.SOURCE_WINDOW_DAYS)).isoformat()
    pool = [d for d in (docs if first else fresh) if d["kind"] in kinds and d["kind"] != "annual_report" and (d.get("date") or "") >= cut]
    taken: Dict[str, int] = {}
    for d in sorted(pool, key=lambda d: d.get("date") or "", reverse=True):
        if taken.get(d["kind"], 0) < limit.get(d["kind"], 1) and len(out) < C.MAX_DOCS_PER_BRIEF:
            out.append(d)
            taken[d["kind"]] = taken.get(d["kind"], 0) + 1
    return out


def merge_parts(old: Optional[dict], new: dict, parts: Sequence[str], name: str, symbol: str, docs: Dict[str, Any], as_of: str, points_only: bool) -> dict:
    """The stored brief after a (partial) rewrite: parts not rewritten are kept as they were."""
    out = dict(old or {})
    out.update({"symbol": symbol, "name": name, "as_of": as_of, "template": B.TEMPLATE_VERSION})
    for p in parts:
        if p not in new:
            continue
        if p == "segments" and points_only and old:
            by = {s.get("name"): s for s in new["segments"] if isinstance(s, dict)}
            out["segments"] = [{**s, "points": (by[s["name"]].get("points") or s.get("points")) if s.get("name") in by else s.get("points")} for s in old.get("segments") or []]
        elif p == "gaps" and old and set(parts) != set(B.PARTS):
            seen, merged = set(), []
            for g in [*(new["gaps"] if isinstance(new["gaps"], list) else []), *(old.get("gaps") or [])]:
                if isinstance(g, str) and g not in seen:
                    seen.add(g)
                    merged.append(g)
            out["gaps"] = merged[:8]
        else:
            out[p] = new[p]
    out["docs"] = {**((old or {}).get("docs") or {}), **docs}
    out["disclaimer"] = B.DISCLAIMER
    return out


# ------------------------------------------------------------------------------------------------ database
async def feed_for(conn, symbol: str, since: date) -> Dict[str, Any]:
    rows = await conn.fetch("SELECT item_date, category, title, link FROM feed_items WHERE symbol = $1 AND kind IN ('document', 'result') AND link IS NOT NULL AND item_date >= $2 "
                            "ORDER BY item_date DESC LIMIT 400", symbol, since)
    return {"announcements": [{"date": r["item_date"].isoformat(), "category": r["category"] or "", "description": r["title"], "link": r["link"]} for r in rows]}


async def candidates(conn, top: int, symbols: Optional[List[str]] = None) -> List[dict]:
    """Companies in the order they are served: a rewrite someone asked for, then companies members follow (opened in the last 90 days, or with an active alert), then by market cap."""
    rows = await conn.fetch(
        "SELECT c.symbol, c.name, COALESCE(q.market_cap, 0) AS mcap, COALESCE(b.rewrite_asked, false) AS asked, "
        "(EXISTS (SELECT 1 FROM user_companies u WHERE u.symbol = c.symbol AND u.last_opened > now() - interval '90 days') "
        " OR EXISTS (SELECT 1 FROM alerts a WHERE a.symbol = c.symbol AND a.status = 'active')) AS followed "
        "FROM companies c LEFT JOIN listing_quotes q ON q.symbol = c.symbol LEFT JOIN company_briefs b ON b.symbol = c.symbol "
        "WHERE ($2::text[] IS NULL OR c.symbol = ANY($2)) AND (q.market_cap IS NOT NULL OR b.symbol IS NOT NULL) "
        "ORDER BY asked DESC, followed DESC, mcap DESC, c.symbol LIMIT $1", top, symbols or None)
    return [dict(r) for r in rows]


async def note_source(conn, symbol: str, state: str, reason: str, docs_sig: str = "", bump: bool = False) -> None:
    await conn.execute(
        "INSERT INTO company_brief_sources (symbol, last_state, last_reason, last_tried_at, attempts, last_docs) VALUES ($1, $2, $3, now(), $5, $4) "
        "ON CONFLICT (symbol) DO UPDATE SET last_state = $2, last_reason = $3, last_tried_at = now(), "
        "attempts = CASE WHEN NOT $6 THEN 0 WHEN company_brief_sources.last_docs IS DISTINCT FROM $4 THEN 1 ELSE company_brief_sources.attempts + 1 END, last_docs = $4",
        symbol, state, reason, docs_sig, 1 if bump else 0, bump)


def signature(docs: Sequence[Dict[str, Any]]) -> str:
    return hashlib.sha1("|".join(sorted(d["url"] for d in docs)).encode()).hexdigest()[:16]  # nosec B324 - a change marker


def blocked_by_attempts(src: Optional[dict], sig: str, now: datetime) -> Optional[str]:
    """A company whose last tries failed on these same filings waits RETRY_AFTER_HOURS, and after MAX_ATTEMPTS is left alone until a new filing arrives."""
    if not src or not str(src.get("last_state") or "").startswith("failed") or src.get("last_docs") != sig:
        return None
    if (src.get("attempts") or 0) >= C.MAX_ATTEMPTS:
        return "gave_up"
    t = src.get("last_tried_at")
    if t and now - t < timedelta(hours=C.RETRY_AFTER_HOURS):
        return "waiting"
    return None


# ------------------------------------------------------------------------------------------------ one company
async def ask_model(provider, pacer: Pacer, prompt: str, report: dict, sleep) -> Tuple[Optional[str], Optional[str]]:
    """(text, stop). `stop` names why the whole run must stop: budget | not_configured | quota; None when only this company failed (text None) or all is well."""
    if not await pacer.take():
        return None, "budget"
    for wait_n in (0, 1):
        try:
            return await provider.generate("You write a factual company brief as JSON. Output JSON only.", prompt), None
        except NotConfigured:
            return None, "not_configured"
        except RateLimited as e:
            if e.daily:
                await pacer.exhaust()
                return None, "quota"
            if wait_n:
                return None, "quota"
            await sleep(min(90.0, max(e.retry_after, 20.0)))
        except ProviderError as e:
            report["provider_errors"] = report.get("provider_errors", 0) + 1
            log.info("brief writer failed: %s", e)
            return None, None
    return None, None


async def write_one(store, provider, pacer, fetcher, c: dict, report: dict, today: date, sleep) -> Optional[str]:
    """Returns a reason to stop the whole run, or None."""
    symbol, name, td = c["symbol"], c["name"], today.isoformat()
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM company_briefs WHERE symbol = $1", symbol)
        row = None if row is None else {**dict(row), "brief": json.loads(row["brief"]) if isinstance(row["brief"], str) else row["brief"]}
        src = await conn.fetchrow("SELECT * FROM company_brief_sources WHERE symbol = $1", symbol)
        src = dict(src) if src else None
        feed = await feed_for(conn, symbol, today - timedelta(days=500))
    docs = B.collect_sources(feed, None, (src or {}).get("annual_report_url"))
    parts, why, fresh = plan_parts(row, docs, td)
    if not parts:
        key = "nothing_new" if why == "nothing new" else why
        report[key] = report.get(key, 0) + 1
        if why == "no_annual_report":
            async with store.pool.acquire() as conn:
                await note_source(conn, symbol, "no_annual_report", REASONS["no_annual_report"])
        return None
    first = row is None
    chosen = choose_docs(docs, parts, fresh, first or "about" in parts and "group" in parts, td)
    if not chosen:
        report["no_filings"] = report.get("no_filings", 0) + 1
        return None
    sig = signature(chosen)
    why_not = blocked_by_attempts(src, sig, datetime.now(timezone.utc))
    if why_not:
        report[why_not] = report.get(why_not, 0) + 1
        return None
    # --- read
    pages: Dict[str, List[str]] = {}
    for d in chosen:
        try:
            data = await fetcher.pdf(d["url"])
            pg = await asyncio.to_thread(B.pdf_pages, data, C.MAX_PAGES)
        except T.BudgetSpent:
            return "request_budget"
        except (T.FetchFailed, T.Blocked) as e:
            report["pdf_failed"] = report.get("pdf_failed", 0) + 1
            log.info("brief %s: %s not read: %s", symbol, d["key"], e)
            continue
        if any(x.strip() for x in pg):
            pages[d["key"]] = pg
    read = [d for d in chosen if d["key"] in pages]
    ar_key = next((d["key"] for d in read if d["kind"] == "annual_report"), None)
    if first and not ar_key:
        report["unreadable"] = report.get("unreadable", 0) + 1
        async with store.pool.acquire() as conn:
            await note_source(conn, symbol, "failed_unreadable", REASONS["unreadable"], sig, True)
        return None
    if not read:
        report["unreadable"] = report.get("unreadable", 0) + 1
        async with store.pool.acquire() as conn:
            await note_source(conn, symbol, "failed_unreadable", REASONS["unreadable"], sig, True)
        return None
    # --- write
    points_only = "segments" in parts and not ar_key and not first
    extra = ""
    if points_only:
        names = [s.get("name") for s in row["brief"].get("segments") or []]
        extra = f"10. Segments: keep exactly these names {json.dumps(names)}; for each give only \"name\" and \"points\" (what changed in the latest filings).\n"
    prompt = B.build_prompt(name, symbol, read, pages, td, parts=parts, extra=extra)
    text, stop = await ask_model(provider, pacer, prompt, report, sleep)
    if stop:
        return stop
    report["llm_calls"] = report.get("llm_calls", 0) + 1
    result = parse_json(text or "")
    outcome = evaluate(row, result, parts, read, pages, name, symbol, td, points_only)
    if result is not None and outcome["checks"]["failed"]:
        # one repair pass: tell the writer exactly which citations were wrong
        bad = "; ".join(f"{f['path']}: {f['doc']} page {f['page']} lacks {f['missing']}" + (f" (found on page {f['found_on']})" if f["found_on"] else "") for f in outcome["checks"]["failed"][:12])
        text2, stop = await ask_model(provider, pacer, prompt + f"\nYour previous answer had citations that were not on their pages: {bad}. Return the corrected JSON.\n", report, sleep)
        if stop:
            return stop
        report["llm_calls"] = report.get("llm_calls", 0) + 1
        result2 = parse_json(text2 or "")
        if result2 is not None:
            out2 = evaluate(row, result2, parts, read, pages, name, symbol, td, points_only)
            if len(out2["checks"]["failed"]) < len(outcome["checks"]["failed"]):
                outcome = out2
                outcome["checks"]["fixed"] = [f"{len(bad.split('; '))} citation(s) were corrected on a second pass."]
    if result is None or outcome["merged"] is None:
        report["failed"] = report.get("failed", 0) + 1
        async with store.pool.acquire() as conn:
            await note_source(conn, symbol, "failed_output", REASONS["failed"], sig, True)
        return None
    if row is not None and outcome["problems"]:
        # never replace a draft or a brief that is waiting with one that is worse; the reviewer keeps what they have
        report["failed"] = report.get("failed", 0) + 1
        async with store.pool.acquire() as conn:
            await note_source(conn, symbol, "failed_output", "The new text did not pass: " + "; ".join(outcome["problems"][:3]), sig, True)
        return None
    async with store.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO company_briefs (symbol, status, brief, as_of, checks, problems, flags, parts_written, written_at, written_by, prompt_version, rewrite_asked) "
            "VALUES ($1, 'draft', $2::jsonb, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7, now(), $8, $9, false) "
            "ON CONFLICT (symbol) DO UPDATE SET status = 'draft', brief = $2::jsonb, as_of = $3, checks = $4::jsonb, problems = $5::jsonb, flags = $6::jsonb, parts_written = $7, "
            "written_at = now(), written_by = $8, prompt_version = $9, rewrite_asked = false, reviewed_by = NULL, reviewed_at = NULL, review_note = NULL",
            symbol, json.dumps(outcome["merged"]), date.fromisoformat(outcome["merged"]["as_of"]), json.dumps(outcome["checks"]), json.dumps(outcome["problems"]),
            json.dumps(outcome["flags"]), list(parts), provider.model, C.PROMPT_VERSION)
        await note_source(conn, symbol, "written", "", sig, False)
    report["written"] = report.get("written", 0) + 1
    report.setdefault("written_symbols", []).append(symbol)
    return None


def evaluate(row, result, parts, read, pages, name, symbol, today, points_only) -> dict:
    """Merge the model's answer into the stored brief, run validate() and check(), keep the per-part check records of the parts that were not rewritten."""
    empty = {"merged": None, "problems": [], "flags": [], "checks": {"failed": [], "citations": 0}}
    if result is None:
        return empty
    got = [p for p in parts if p in result]
    if not got or not (set(got) - {"gaps"}):
        return {**empty, "problems": ["the answer held none of the requested parts"]}
    dates = [d.get("date") for d in read if d.get("date")]
    old = row["brief"] if row else None
    as_of = max([*dates, (old or {}).get("as_of") or ""]) or today
    merged = merge_parts(old, result, got, name, symbol, docs_map(read), as_of, points_only)
    problems = B.validate(merged)
    by_part = B.check_by_part(merged, pages, got)
    prior = (row or {}).get("checks") or {}
    prior = json.loads(prior) if isinstance(prior, str) else prior
    for p, rep in (prior.get("by_part") or {}).items():
        if p not in by_part and p in merged:
            by_part[p] = rep
    checks = B.sum_checks(by_part, today)
    merged.pop("checks", None)
    return {"merged": merged, "problems": problems, "flags": B.flags(merged), "checks": checks}


# ------------------------------------------------------------------------------------------------ the run
async def run(store, settings, provider=None, fetcher=None, env: Optional[Mapping[str, str]] = None, today: Optional[date] = None, symbols: Optional[List[str]] = None,
              max_writes: Optional[int] = None, max_minutes: float = 40.0, sleep=asyncio.sleep) -> dict:
    import os
    env = os.environ if env is None else env
    today = today or datetime.now(timezone.utc).date()
    started = time.monotonic()
    model = (env.get("BRIEF_LLM_MODEL") or "").strip() or settings.gemini_model
    provider = provider or GeminiProvider(settings.gemini_api_key, model, max_output_tokens=C.MAX_TOKENS_OUT, user_agent="FinLit-brief/1.0 (+https://finlitventures.com)")
    report: dict = {"status": "ok", "model": provider.model, "prompt_version": C.PROMPT_VERSION}
    if not provider.configured:
        await provider.aclose()
        report = {"status": "not_configured", "detail": "GEMINI_API_KEY is empty: no brief is written. Nothing was changed."}
        await record(store, report)
        return report
    cap = C.max_writes(env) if max_writes is None else max_writes
    pacer = BriefPacer(C.llm_per_minute(env), C.llm_per_day(env), store.redis, sleep=sleep)
    own = fetcher is None
    async with store.pool.acquire() as conn:
        hosts = [urlsplit(r["annual_report_url"]).hostname for r in await conn.fetch("SELECT annual_report_url FROM company_brief_sources WHERE annual_report_url IS NOT NULL")]
        cands = await candidates(conn, int(env.get("BRIEF_TOP_COMPANIES", 500) or 500), symbols)
    fetcher = fetcher or BriefFetcher(extra_hosts=[h for h in hosts if h], budget=C.REQUEST_BUDGET_PER_RUN)
    report["companies"] = len(cands)
    try:
        for c in cands:
            if report.get("written", 0) >= cap:
                report["stopped"] = "write cap"
                break
            if time.monotonic() - started > max_minutes * 60:
                report["stopped"] = "time"
                break
            try:
                stop = await write_one(store, provider, pacer, fetcher, c, report, today, sleep)
            except Exception as exc:   # one company never stops the night
                log.warning("brief for %s failed: %s: %s", c["symbol"], type(exc).__name__, exc)
                report["errors"] = report.get("errors", 0) + 1
                continue
            if stop:
                report["stopped"] = stop
                if stop == "not_configured":
                    report["status"] = "not_configured"
                break
    finally:
        report["exchange_requests"] = getattr(fetcher, "requests", 0)
        report["llm_left_today"] = await pacer.left_today()
        if own:
            await fetcher.aclose()
        await provider.aclose()
    await record(store, report)
    return report


async def record(store, report: dict) -> None:
    try:
        async with store.pool.acquire() as conn:
            await conn.execute("INSERT INTO company_brief_runs (finished_at, status, detail) VALUES (now(), $1, $2::jsonb)", report.get("status", "ok"), json.dumps(report, default=str)[:8000])
            await conn.execute("DELETE FROM company_brief_runs WHERE id < (SELECT max(id) - 60 FROM company_brief_runs)")
    except Exception:   # nosec B110 - the run record is a convenience
        log.warning("could not record the brief run")
