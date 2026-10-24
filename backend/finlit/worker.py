"""Ingest worker: FinEdge -> snapshot sections -> Postgres + Redis.

    python -m finlit.worker migrate
    python -m finlit.worker refresh-universe            # stock list for search
    python -m finlit.worker ingest RELIANCE TCS ...     # build snapshots now
    python -m finlit.worker probe RELIANCE              # is the key + network + plan good for every endpoint?
    python -m finlit.worker ingest-all --limit 500      # load the whole universe (resumable; run without --limit for everything)
    python -m finlit.worker refresh-stale --hours 24    # nightly fundamentals refresh
    python -m finlit.worker refresh-quotes              # live price patch, every minute in market hours
    python -m finlit.worker drain-queue --loop          # stocks users opened before they were ingested

Run by cron on the VPS (see deploy/crontab). The API process never calls FinEdge.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import orjson

from . import snapshot
from .config import Settings, get_settings
from .finedge import FinEdgeClient, FinEdgeError, _has_rows, bundle_requests
from .normalize import market
from .store import Store

log = logging.getLogger("finlit.worker")


class DataRejected(Exception):
    def __init__(self, issues):
        super().__init__(f"{len(issues)} critical data issue(s)")
        self.issues = issues


# Without these a report is not worth showing; if any of them failed to load, the load is retried later instead of saved.
CORE_PARTS = ("profile", "quote", "pl_annual", "bs_annual", "daily_quotes", "ratios_pr")



async def _mf_dashboard_empty(store) -> bool:
    """True while no scheme has a fund size, SIP return or checklist yet (a deploy that added those columns after the last refresh ran): the boot
    refresh then runs even though the last run is recent, so the mutual fund dashboard does not stay empty until the next nightly run."""
    async with store.pool.acquire() as conn:
        n = await conn.fetchval("SELECT count(*) FROM mf_schemes WHERE aum_lakh IS NOT NULL OR sip3y IS NOT NULL OR chk_mask IS NOT NULL")
    return not n

async def ingest_one(client: FinEdgeClient, store: Store, symbol: str, statement: str = "consolidated", slim: bool = False) -> dict:
    """Load one company. `slim` keeps only its score and screener figures (about 5 KB) and not its report or prices (about 100 KB): how the bulk
    scoring covers every listed company inside a small database. The report is built in full when somebody opens the company."""
    started, calls_before = time.perf_counter(), client.calls
    symbol = symbol.strip().upper()
    company = await store.company(symbol)
    try:
        bundle = await client.fetch_bundle(symbol, statement)
        if bundle.get("errors", {}).get("pl_annual") in (None, "404"):   # secondary source fills only what the main provider left empty
            try:
                from . import upstox
                up = upstox.UpstoxClient(settings=client.settings, redis=store.redis)
                try:
                    await upstox.supplement(bundle, up, dict(company) if company else None)
                finally:
                    await up.aclose()
            except Exception:
                log.exception("secondary source skipped for %s", symbol)
        if company:
            bundle["symbol_row"] = {"symbol": company["symbol"], "name": company["name"], "nse_code": company["nse_code"],
                                    "bse_code": company["bse_code"], "consolidated_ind": company["has_consolidated"]}
        if bundle.get("statement") == "consolidated" and bundle.get("pl_annual"):   # for the consolidated-vs-standalone revenue guard; best effort
            try:
                path, params, _t = bundle_requests(symbol, "standalone")["pl_annual"]
                bundle["pl_annual_standalone"] = await client.get(path, params, timeout=12, retries=1)
            except Exception:
                pass
        if not bundle.get("pl_annual") and not bundle.get("daily_quotes"):
            raise FinEdgeError("bundle", 404, "no statements or prices for symbol")
        failed_core = sorted(k for k, why in (bundle.get("errors") or {}).items() if k in CORE_PARTS and why != "404")
        if failed_core:   # never store a half-loaded report (price 0, empty sections): keep the last good one and try again later
            raise FinEdgeError("bundle", None, "provider did not answer for " + ", ".join(failed_core))
        sections = snapshot.build(bundle)
        checks = sections["summary"]["dataQuality"]["checks"]
        if checks["status"] == "rejected":
            # Keep serving the last good snapshot; a human reviews the logged issues.
            raise DataRejected([i for i in checks["issues"] if i["severity"] == "critical"])
        if not slim:
            sections["peers"]["items"] = await store.peer_rows(sections["peers"]["symbols"])
        if sections["summary"].get("quote", {}).get("price"):
            sections["summary"]["quote"]["refPrice"] = sections["summary"]["quote"]["price"]
        row = snapshot.score_row(sections)
        if slim:
            await store.save_score_only(symbol, statement, row)
        else:
            # Saved once, under the basis that was asked for (a company with only standalone accounts is not stored twice).
            await store.save_snapshot(symbol, statement, sections, row, sections["price"]["daily"])
        try:
            cov = sections["summary"]["dataQuality"]["coverage"]
            if not slim:
                await store.save_coverage(symbol, statement, cov)
            if cov["mismatches"]:   # the provider sent it and the report lacks it: a bug in this code, never a data gap
                log.error("COVERAGE MISMATCH %s: %s", symbol, "; ".join(cov["mismatches"]))
        except Exception:
            log.exception("coverage not recorded for %s", symbol)
        prof = sections["summary"]["profile"]
        await store.set_company_meta(symbol, prof.get("sector"), prof.get("industry"), prof.get("website"))
        status = "ok" if checks["status"] == "ok" else "warnings"
        errors = {**(bundle.get("errors") or {}), **({"quality": checks["issues"]} if checks["issues"] else {})}
    except DataRejected as exc:
        log.warning("ingest %s rejected by quality gate: %s", symbol, exc.issues)
        status, errors = "rejected", {"quality": exc.issues}
    except Exception as exc:  # one bad stock must never stop a batch
        log.exception("ingest %s failed", symbol)
        status, errors = "failed", {"error": str(exc)[:500]}
    try:
        await store.redis.delete(f"pending:{symbol}:{statement}")   # whoever was waiting on this report asks again now
    except Exception:
        pass
    duration = int((time.perf_counter() - started) * 1000)
    await store.log_run(symbol, statement, status, client.calls - calls_before, duration, errors)
    log.info("ingest %s %s %s in %d ms (%d calls)", symbol, statement, status, duration, client.calls - calls_before)
    return {"symbol": symbol, "status": status, "ms": duration, "errors": errors}


async def _step_aside(store: Store, patience: float = 240.0) -> None:
    """The bulk loader waits while a visitor is waiting on a report: on a small free server, the two would share one slow CPU and the one
    request somebody is staring at would crawl. A hard cap keeps the bulk load moving even if the flag is never cleared."""
    waited = 0.0
    while waited < patience:
        try:
            if not await store.redis.exists(store.READER_FLAG):
                return
        except Exception:
            return
        await asyncio.sleep(2.0)
        waited += 2.0


async def ingest_many(client: FinEdgeClient, store: Store, items: Iterable[Tuple[str, str]], parallel: int = 2, yield_to_readers: bool = False,
                      slim: bool = False) -> List[dict]:
    # Each stock already fans out ~21 requests; a couple of stocks at a time keeps us inside rate limits.
    sem = asyncio.Semaphore(parallel)

    async def run(symbol, statement):
        async with sem:
            if yield_to_readers:
                await _step_aside(store)
            return await ingest_one(client, store, symbol, statement, slim=slim)

    return await asyncio.gather(*(run(s, st) for s, st in items))


async def refresh_universe(client: FinEdgeClient, store: Store) -> int:
    rows = await client.stock_symbols()
    count = await store.upsert_companies(rows)
    log.info("universe: %d companies", count)
    return count


async def refresh_quotes(client: FinEdgeClient, store: Store, symbols: Optional[List[Tuple[str, str]]] = None, dhan_client=None) -> int:
    """Patch the live quote into each summary without re-fetching fundamentals.

    With Dhan set up, every matched company's quote comes from a few batch calls (1,000 companies each); a company Dhan does not match,
    does not answer for, or answers implausibly for (previous close more than 25% from the price held) is asked of FinEdge as before."""
    items = symbols or await store.quote_symbols()
    updated = 0
    touched: List[Tuple[str, str]] = []
    batch: Dict[str, dict] = {}
    if dhan_client is not None and dhan_client.configured and items:
        from . import dhan
        try:
            ids = await dhan.security_map(store, sorted({s for s, _ in items}))
            raw = await dhan_client.quotes(sorted(set(ids.values())))
            batch = {sym: q for sym, key in ids.items() if (q := dhan.to_quote(raw.get(key) or {}))}
        except dhan.DhanError as e:
            log.warning("Dhan quotes unavailable, using FinEdge for all: %s", e)
        except Exception:
            log.exception("Dhan quotes failed, using FinEdge for all")

    async def one(symbol: str, statement: str):
        nonlocal updated
        cached = await store.get_section(symbol, statement, "summary")
        if not cached:
            return
        summary = orjson.loads(cached[0])
        old = summary.get("quote") or {}
        live = batch.get(symbol)
        if live is not None:
            from .dhan import plausible
            if not plausible(live, old):
                log.warning("Dhan quote for %s is far from the price held (%s vs %s); using FinEdge", symbol, live.get("previousClose"), old.get("price"))
                live = None
            else:
                live = dict(live)
                if old.get("marketCapCr") and old.get("price"):       # shares do not change intraday: market cap moves with the price
                    live["marketCapCr"] = round(old["marketCapCr"] * live["price"] / old["price"], 2)
                if old.get("high52") and live.get("high") and live["high"] > old["high52"]:
                    live["high52"] = live["high"]
                if old.get("low52") and live.get("low") and live["low"] < old["low52"]:
                    live["low52"] = live["low"]
        if live is None:
            try:
                live = market.quote(await client.get("/quote", {"symbol": symbol}, timeout=5), symbol)
            except FinEdgeError:
                return
        if not live.get("price"):
            return
        if old.get("price") == live["price"]:   # unchanged price: nothing to rewrite (the trade time alone is not worth a write)
            return
        summary["quote"] = {**old, **{k: v for k, v in live.items() if v is not None}}
        for k in ("upperCircuit", "lowerCircuit"):   # a price band belongs to the quote it came with: never an older day's band beside a newer price
            if live.get(k) is None:
                summary["quote"].pop(k, None)
        await store.save_snapshot(symbol, statement, {"summary": summary})
        updated += 1
        touched.append((symbol, statement))

    await asyncio.gather(*(one(s, st) for s, st in items))
    if touched:  # keep the screener's price-based numbers (P/E, market cap, returns, 52-week position) as fresh as the quote
        try:
            from .screener.jobs import refresh_metrics_for
            await refresh_metrics_for(store, touched)
        except Exception:
            log.exception("screener metrics were not refreshed after the quote update")
    return updated


async def _retry_dropped(store: Store, results: List[dict], attempts: int = 2) -> None:
    """A report somebody asked for that failed only because the provider did not answer is put back in the queue (twice at most), so the
    visitor's wait ends in a report instead of an error. Rejections and companies the provider does not have are not retried."""
    again = []
    for r in results:
        if r.get("status") != "failed" or "did not answer" not in str((r.get("errors") or {}).get("error", "")):
            continue
        key = f"ingest:retry:{r['symbol']}"
        try:
            n = int(await store.redis.incr(key)); await store.redis.expire(key, 900)
        except Exception:
            n = attempts + 1
        if n <= attempts:
            again.append(r["symbol"])
    if again:
        await asyncio.sleep(3.0)
        for sym in again:
            await store.enqueue(sym, "consolidated")


async def drain_queue(client: FinEdgeClient, store: Store, loop: bool = False, idle_seconds: float = 2.0, recheck_seconds: float = 6 * 3600.0) -> int:
    """With loop=True the idle wait watches a Redis flag set by enqueue, and looks at Postgres only when the flag is up (or every
    `recheck_seconds` as a safety net). Polling Postgres every couple of seconds would keep a serverless database awake all day."""
    total, last_db = 0, float("-inf")
    while True:
        if loop and time.monotonic() - last_db < recheck_seconds:
            try:
                flagged = await store.redis.exists(store.QUEUE_FLAG)
            except Exception:
                flagged = True  # Redis trouble: fall back to asking Postgres
            if not flagged:
                await asyncio.sleep(idle_seconds)
                continue
        last_db = time.monotonic()
        if loop:
            try:
                await store.redis.delete(store.QUEUE_FLAG)  # before claiming: an enqueue that arrives meanwhile raises it again
            except Exception:
                pass
        items = await store.claim(3)   # small batches, all at once: a report someone is waiting for never queues behind ten others
        if items:
            try:
                await store.redis.set(store.READER_FLAG, 1, ex=120)   # tells the bulk loader to wait while these are prepared
            except Exception:
                pass
            results = await ingest_many(client, store, items, parallel=3)
            await _retry_dropped(store, results)
            await store.invalidate_search()
            total += len(items)
            continue
        if not loop:
            return total
        await asyncio.sleep(idle_seconds)


async def ingest_all(client: FinEdgeClient, store: Store, statement: str = "consolidated", hours: int = 24, limit: Optional[int] = None,
                     parallel: int = 3, chunk: int = 30) -> dict:
    """Fill (or refresh) every company in the universe, in chunks, so a long run can be stopped and restarted safely:
    each restart picks up whatever has no snapshot yet. Never-loaded companies go first."""
    pending = await store.pending_symbols(statement, hours, limit)
    log.info("ingest-all: %d companies to load (%s)", len(pending), statement)
    done = {"ok": 0, "warnings": 0, "rejected": 0, "failed": 0}
    for i in range(0, len(pending), chunk):
        batch = pending[i:i + chunk]
        for r in await ingest_many(client, store, [(s, statement) for s in batch], parallel=parallel, yield_to_readers=True):
            done[r["status"]] = done.get(r["status"], 0) + 1
        log.info("ingest-all: %d / %d  %s  (%d upstream calls)", min(i + chunk, len(pending)), len(pending), done, client.calls)
    await store.invalidate_search()   # once at the end: each drop makes the next visitor read the whole name list from Postgres again
    return done


async def score_all(client: FinEdgeClient, store: Store, limit: int = 1500, days: int = 7, parallel: int = 2, chunk: int = 30, max_minutes: float = 90.0) -> dict:
    """Give every listed company a score: those with none first, biggest first, then the oldest. Only the small score row is kept (see ingest_one slim),
    so all ~5,800 companies fit in the free database. A run is capped (`limit` companies, `max_minutes`) and resumable: the next run takes whatever is
    still missing, so the whole market is covered within a few nights and refreshed about weekly after that."""
    pending = await store.slim_pending(days, limit)
    log.info("score-all: %d companies to score", len(pending))
    done = {"ok": 0, "warnings": 0, "rejected": 0, "failed": 0}
    deadline = time.monotonic() + max_minutes * 60
    tried = 0
    for i in range(0, len(pending), chunk):
        if time.monotonic() > deadline:
            log.info("score-all: time budget used, the rest waits for the next run")
            break
        batch = pending[i:i + chunk]
        for r in await ingest_many(client, store, [(s, "consolidated") for s in batch], parallel=parallel, yield_to_readers=True, slim=True):
            done[r["status"]] = done.get(r["status"], 0) + 1
        tried += len(batch)
        log.info("score-all: %d / %d  %s  (%d upstream calls)", tried, len(pending), done, client.calls)
    try:
        await store.invalidate_search()
    except Exception:
        pass
    return {**done, "tried": tried, "waiting": len(pending) - tried}


async def results_candidates(store: Store, today: Optional[date] = None, max_age_days: int = 4) -> List[str]:
    """Companies that have declared quarterly results (a filing, or a board-meeting date that has passed) within the last `max_age_days`
    and whose stored report is still on an older quarter: biggest first. Only companies the site keeps in full (the top INGEST_LIMIT
    set, or any with a stored report) are returned."""
    from . import results
    today = today or results.today_ist()
    decls = await results.get_declarations(store, force=True)
    recent: Dict[str, date] = {}
    for qk, by_sym in decls.items():
        for sym, d in by_sym.items():
            if d.date <= today and (today - d.date).days <= max_age_days:
                recent[sym] = max(d.date, recent.get(sym, d.date))
    if not recent:
        return []
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            f"WITH ranked AS ({store.RANKED}) "  # nosec B608 - fixed SQL
            "SELECT x.symbol, r.rn, (SELECT s.metrics->>'q_period_end' FROM scores s WHERE s.symbol = x.symbol AND s.model = 'v1' ORDER BY (s.statement = 'consolidated') DESC, s.updated_at DESC LIMIT 1) AS qpe, "
            "EXISTS (SELECT 1 FROM snapshots n WHERE n.symbol = x.symbol) AS held "
            "FROM unnest($1::text[]) AS x(symbol) LEFT JOIN ranked r ON r.symbol = x.symbol", sorted(recent))
    out = []
    for r in rows:
        d = recent[r["symbol"]]
        e = results.quarter_end_before(d)
        try:
            have = results.ymd_to_date(float(r["qpe"])) if r["qpe"] else None
        except ValueError:
            have = None
        if have is not None and have >= e - timedelta(days=10):
            continue                                  # the stored report already holds this quarter
        rn = int(r["rn"]) if r["rn"] is not None else 10 ** 9
        if r["held"] or rn <= (int(os.getenv("INGEST_LIMIT") or 0) or 100000):
            out.append((rn, r["symbol"]))
    return [sym for _, sym in sorted(out)]


async def refresh_results(client: FinEdgeClient, store: Store, limit: int = 120, retry_minutes: int = 50) -> dict:
    """Run every hour: a company that has just reported is rebuilt from the provider, so its new quarter shows on the site within hours
    (the provider usually has it within a few hours of the filing). A company the provider has not updated yet is tried again an hour
    later, and for up to four days after its declaration."""
    todo = []
    for sym in await results_candidates(store):
        try:
            if await store.redis.set(f"results:try:{sym}", 1, ex=retry_minutes * 60, nx=True):
                todo.append(sym)
        except Exception:
            todo.append(sym)
        if len(todo) >= limit:
            break
    done = {"candidates": len(todo), "ok": 0, "failed": 0}
    for i in range(0, len(todo), 30):
        for r in await ingest_many(client, store, [(s, "consolidated") for s in todo[i:i + 30]], parallel=3):
            done["ok" if r["status"] in ("ok", "warnings") else "failed"] += 1
    if todo:
        await store.invalidate_search()
    log.info("refresh-results: %s", done)
    return done


async def audit_coverage(client: FinEdgeClient, symbols: List[str]) -> dict:
    """Rebuild each company from the provider (nothing is stored) and compare what the provider sent with what the report shows.
    Any mismatch is a bug in this code. Companies the provider sent nothing for are listed, never hidden."""
    sem = asyncio.Semaphore(3)
    out = {"checked": 0, "byState": {}, "mismatches": [], "providerEmpty": [], "errors": [], "all": {}}

    async def one(sym: str):
        async with sem:
            try:
                bundle = await client.fetch_bundle(sym, "consolidated")
                failed = [k for k, why in (bundle.get("errors") or {}).items() if k in CORE_PARTS and why != "404"]
                if failed:
                    out["errors"].append((sym, "provider did not answer: " + ", ".join(failed))); return
                cov = snapshot.build(bundle)["summary"]["dataQuality"]["coverage"]
            except Exception as exc:
                out["errors"].append((sym, str(exc)[:80])); return
            out["checked"] += 1
            out["all"][sym] = cov
            out["byState"][cov["state"]] = out["byState"].get(cov["state"], 0) + 1
            if cov["mismatches"]:
                out["mismatches"].append((sym, cov["mismatches"]))
            if cov["state"] == "empty":
                out["providerEmpty"].append(sym)

    await asyncio.gather(*(one(s) for s in symbols))
    return out


async def probe(client: FinEdgeClient, symbol: str = "RELIANCE", statement: str = "consolidated") -> List[Tuple[str, str, float]]:
    """One request per FinEdge endpoint the site uses: proves the key, the network path and the plan cover everything.
    Prints only endpoint names and HTTP statuses, never the key."""
    out = []
    for key, (path, params, timeout) in bundle_requests(symbol, statement).items():
        t0 = time.perf_counter()
        try:
            payload = await client.get(path, params, timeout=timeout, retries=0)
            state = "ok" if _has_rows(payload) else "empty"
        except FinEdgeError as exc:
            state = f"HTTP {exc.status}" if exc.status else "unreachable"
        out.append((key, state, (time.perf_counter() - t0) * 1000))
    return out


async def main(argv: Optional[List[str]] = None, settings: Optional[Settings] = None) -> int:
    parser = argparse.ArgumentParser(prog="finlit.worker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("refresh-universe")
    sub.add_parser("refresh-short-history", help="reload stored reports whose yearly statements cover 4 years or fewer, so the second source can add older years (reads a few KB)")
    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("symbols", nargs="+")
    p_ingest.add_argument("--statement", default="consolidated", choices=["consolidated", "standalone"])
    p_stale = sub.add_parser("refresh-stale")
    p_stale.add_argument("--hours", type=int, default=None)
    p_all = sub.add_parser("ingest-all", help="load every company in the universe (resumable)")
    p_all.add_argument("--statement", default="consolidated", choices=["consolidated", "standalone"])
    p_all.add_argument("--hours", type=int, default=24, help="reload snapshots older than this")
    p_all.add_argument("--limit", type=int, default=None)
    p_all.add_argument("--parallel", type=int, default=3)
    p_probe = sub.add_parser("probe", help="check the FinEdge key and every endpoint for one symbol")
    p_probe.add_argument("symbol", nargs="?", default="RELIANCE")
    p_alerts = sub.add_parser("check-alerts", help="evaluate members' alerts and watchlist targets; notify in the app and by email")
    p_alerts.add_argument("--kind", choices=["live", "daily", "all"], default="all", help="live: price metrics (market hours); daily: the rest (evenings)")
    sub.add_parser("check-screens", help="email members when a company newly matches one of their saved screens")
    sub.add_parser("send-digest", help="send the weekly week-ahead email to members who switched it on")
    sub.add_parser("refresh-quotes")
    p_aud = sub.add_parser("audit-coverage", help="compare what the provider sends with what the reports show, for a random sample (exit 1 on any mismatch)")
    p_aud.add_argument("--sample", type=int, default=100)
    p_aud.add_argument("--seed", type=int, default=None)
    p_aud.add_argument("--record", action="store_true", help="also store the results (the admin Data health panel then covers the sample)")
    p_aud.add_argument("symbols", nargs="*")
    sub.add_parser("refresh-results", help="rebuild companies that have just declared quarterly results (hourly)")
    p_sa = sub.add_parser("score-all", help="score every listed company that has no score (or an old one), keeping only the small score row; capped and resumable")
    p_sa.add_argument("--limit", type=int, default=None, help="companies per run (default: SCORE_ALL_PER_RUN, else 1500)")
    p_sa.add_argument("--days", type=int, default=7, help="a score older than this many days is refreshed")
    p_sa.add_argument("--max-minutes", type=float, default=90.0, help="stop starting new batches after this long")
    p_sa.add_argument("--parallel", type=int, default=2)
    p_prune = sub.add_parser("prune", help="keep the database inside its storage limit (reports outside the top INGEST_LIMIT nobody opened lately, old prices and logs)")
    p_prune.add_argument("--keep", type=int, default=None, help="companies always kept (default: INGEST_LIMIT, else 500)")
    sub.add_parser("refresh-calendars", help="IPO and results calendars from the data provider")
    p_rm = sub.add_parser("rebuild-metrics", help="recompute every screener filter value from stored snapshots (no provider calls)")
    p_rm.add_argument("--only-missing", action="store_true")
    sub.add_parser("refresh-indices", help="download NIFTY index constituent lists for the screener")
    p_ls = sub.add_parser("refresh-listing", help="nightly: price, market cap and 52-week range of EVERY listed company from the provider's market-wide quote list (two calls, one short write)")
    p_ls.add_argument("--force", action="store_true", help="run even if it ran in the last few hours")
    for _name, _help in (("refresh-etf", "nightly: ETF prices and history from Upstox (never overwrites good rows with a short answer)"),
                         ("refresh-mf", "nightly: mutual fund NAVs from AMFI (never overwrites good rows with a short answer)")):
        _p = sub.add_parser(_name, help=_help)
        _p.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours (a clean run) or the last 15 minutes (a partial one): redeploys must not repeat a full load")
        if _name == "refresh-etf":
            _p.add_argument("--resume", action="store_true", help="fetch only the ETFs not fetched since the last market close (a retry after a partial run)")
    p_ff = sub.add_parser("refresh-facts", help="nightly: fund facts from AMFI (scheme master, expense ratios, quarterly average AUM) for funds and ETFs; run after refresh-mf")
    p_ff.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours")
    p_mi = sub.add_parser("refresh-industry", help="daily: AMFI's monthly category report (industry AUM, net flows, folios by scheme category) for the Mutual Fund Insights page; resumable, only new or re-published months are read")
    p_mi.add_argument("--since", default=None, help="first month to load, YYYY-MM (default and earliest: 2019-04, the first category-wise report)")
    p_mi.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours")
    p_di = sub.add_parser("refresh-instruments", help="weekly: Dhan's public instrument file (ISIN, surveillance flag, margin eligibility, F&O status of every NSE and BSE equity); needs no account")
    p_di.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours")
    p_cm = sub.add_parser("refresh-commodities", help="commodity prices: MCX futures from Dhan and international prices from metals.dev / MetalpriceAPI into Redis (--loop: keeps running)")
    p_cm.add_argument("--loop", action="store_true")
    p_hp = sub.add_parser("history-probe", help="how many yearly statements each source holds for a few old companies (recorded at /api/mf/status, run:history-probe)")
    p_hp.add_argument("symbols", nargs="*", default=None)
    sub.add_parser("dhan-check", help="prove the Dhan credentials work: token, instrument file, RELIANCE's last price and candles (prints no secret)")
    p_dc = sub.add_parser("refresh-portfolios", help="fund holdings, sector split, benchmark and exit loads from the fund houses' monthly portfolio files and AMFI scheme details (resumable; files already read are skipped)")
    p_dc.add_argument("--only", nargs="*", default=None, help="steps (isin performance loads) or fund-house keys (sbi nippon ...)")
    p_dc.add_argument("--skip", nargs="*", default=None, help="steps or fund-house keys to leave out")
    p_dc.add_argument("--months", type=int, default=None, help="month-ends to read per fund house (default: the latest 3)")
    p_dc.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran in the last N hours")
    p_bf = sub.add_parser("backfill-mf", help="one-off, resumable: 5 years of NAV history from AMFI, one fund house at a time (run once after the first refresh-mf)")
    p_bf.add_argument("--amc", default="all", help="AMFI fund house id or name, or all")
    p_bf.add_argument("--force", action="store_true")
    p_lg = sub.add_parser("refresh-logos", help="nightly: company and fund-house logos from their own websites (robots.txt obeyed; blocked sites are left alone)")
    p_lg.add_argument("--limit", type=int, default=150, help="sites to try in one run")
    p_lg.add_argument("--profiles", type=int, default=100, help="provider company-profile calls for large companies with no website on file")
    p_mc = sub.add_parser("refresh-macro", help="nightly: India macro data from MoSPI (CPI, WPI, GDP, IIP, PLFS) and the RBI (policy rates, weekly reserves and credit)")
    p_mc.add_argument("--full", action="store_true", help="reload the full history (the first run does this by itself)")
    p_mc.add_argument("--only", nargs="*", default=None, help="steps: cpi wpi gdp iip plfs rbi_tables rbi_home rbi_wss")
    p_mc.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours")
    p_fl = sub.add_parser("refresh-flows", help="nightly: FII/DII institutional flows from NSDL (FPI and DII reports) and NSE's participant-wise open-interest files, plus Nifty closes for the correlation")
    p_fl.add_argument("--full", action="store_true", help="reload the full FPI history, month by month (the first run does this by itself)")
    p_fl.add_argument("--only", nargs="*", default=None, help="steps: fii dii nse oi nifty")
    p_fl.add_argument("--max-age-hours", type=float, default=None, help="skip when this ran fine in the last N hours")
    p_drain = sub.add_parser("drain-queue")
    p_drain.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)

    settings = settings or get_settings()
    if args.cmd == "audit-coverage":   # needs the provider only, no database
        import random
        async with FinEdgeClient(settings) as client:
            names = list(args.symbols) or [r["symbol"] for r in await client.stock_symbols()]
            picks = list(args.symbols) or random.Random(args.seed).sample(names, min(args.sample, len(names)))
            res = await audit_coverage(client, picks)
        if args.record:
            store = await Store.connect(settings, migrate=True)
            try:
                for sym, cov in res["all"].items():
                    await store.save_coverage(sym, "consolidated", cov)
            finally:
                await store.close()
        print(f"checked {res['checked']}  provider state {res['byState']}  mismatches {len(res['mismatches'])}  provider-empty {len(res['providerEmpty'])}  errors {len(res['errors'])}")
        for sym, lines in res["mismatches"]:
            print("MISMATCH", sym, "; ".join(lines))
        for sym in res["providerEmpty"][:15]:
            print("provider sent nothing:", sym)
        return 1 if res["mismatches"] else 0
    store = await Store.connect(settings, migrate=True)
    try:
        if args.cmd == "migrate":
            print("migrated; timescale =", store.timescale)
            return 0
        if args.cmd in ("check-screens", "send-digest"):
            from .auth.mailer import ConsoleMailer, ResendMailer
            mailer = ResendMailer(settings.resend_api_key, settings.mail_from) if settings.mail_mode == "resend" and settings.resend_api_key else ConsoleMailer(store.pool)
            if args.cmd == "check-screens":
                from .screens import check_screens
                print(await check_screens(store.pool, mailer, settings.public_site_url), "screen alerts sent")
            else:
                from .digest import send_digests
                print(await send_digests(store.pool, mailer, settings.public_site_url), "digests sent")
            return 0
        if args.cmd == "check-alerts":
            from .alerts import check_alerts
            from .auth.mailer import ConsoleMailer, ResendMailer
            mailer = ResendMailer(settings.resend_api_key, settings.mail_from) if settings.mail_mode == "resend" and settings.resend_api_key else ConsoleMailer(store.pool)
            from .alertengine import evaluate
            sent = await evaluate(store.pool, mailer, settings.public_site_url, args.kind)
            if args.kind != "daily":
                sent += await check_alerts(store.pool, mailer, settings.public_site_url)
            print(sent, "alerts sent")
            return 0
        if args.cmd == "refresh-facts":
            from .disclosure import refresh as refresh_facts
            from .mf import last_run_age_hours, make_client, refresh_hot
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and last == "ok" and age < args.max_age_hours:
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            result = await refresh_facts(store, settings)       # records its own result at /api/mf/status
            if result["aum"].get("status") == "ok":            # the ready-made top 100 is now ranked by fund size; a newly ranked scheme's
                async with make_client() as client:              # NAV series is fetched (with a client), never left missing
                    result["hot"] = await refresh_hot(store, client)
            print(result)
            return 0 if result["status"] == "ok" else 1
        if args.cmd == "refresh-macro":
            from . import macro
            from .mf import last_run_age_hours, record_run
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and last in ("ok", "partial") and age < args.max_age_hours:
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            result = await macro.refresh(store, full=args.full, only=args.only)
            await record_run(store, args.cmd, {"status": result["status"], "calls": result["calls"], "cards": result["cards"],
                                               "failed": [k for k, v in result["steps"].items() if v["status"] == "failed"]})
            print(result)
            return 0 if result["status"] in ("ok", "partial") else 1
        if args.cmd == "refresh-flows":
            from . import flows
            from .mf import last_run_age_hours, record_run
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and last in ("ok", "partial") and age < args.max_age_hours:
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            result = await flows.refresh(store, full=args.full, only=args.only, settings=settings)
            await record_run(store, args.cmd, {"status": result["status"], "calls": result["calls"], "sessions": result["sessions"], "diiSessions": result["diiSessions"],
                                               "failed": [k for k, v in result["steps"].items() if v["status"] == "failed"]})
            print(result)
            return 0 if result["status"] in ("ok", "partial") else 1
        if args.cmd == "refresh-industry":
            from . import mf_insights
            from .mf import last_run_age_hours, record_run
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and last == "ok" and age < args.max_age_hours:
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            try:
                result = await mf_insights.refresh(store, settings, since=mf_insights.parse_month(args.since) if args.since else None)
            except Exception as exc:
                await record_run(store, args.cmd, {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:300]})
                raise
            await record_run(store, args.cmd, {"status": result["status"], "latest": result["latest"], "months": result["months"], "stored": result["stored"][-12:],
                                               "missing": result["missing"], "refused": dict(list(result["refused"].items())[:4]),
                                               "failed": dict(list(result["failed"].items())[:4]), "listing": result["listing"]})
            print(json.dumps(result, default=str)[:4000])
            return 0 if result["status"] in ("ok", "partial") else 1
        if args.cmd == "refresh-instruments":
            from . import dhan
            from .mf import last_run_age_hours, record_run
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and last == "ok" and age < args.max_age_hours:
                    async with store.pool.acquire() as conn:      # a run from before the index and option-lot tables existed left them empty: load again
                        empty = not (await conn.fetchval("SELECT count(*) FROM dhan_indices") and await conn.fetchval("SELECT count(*) FROM dhan_option_lots"))
                    if not empty:
                        print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                        return 0
            from .options import LotCollector, save_option_lots
            lots = LotCollector()
            idx: List[dict] = []
            mcx: List[dict] = []
            try:
                n = await dhan.save_instruments(store, await dhan.fetch_instruments(indices=idx, on_row=lots.add, commodities=mcx))
            except dhan.DhanError as e:
                await record_run(store, args.cmd, {"status": "failed", "error": str(e)})
                print({"status": "failed", "error": str(e)})
                return 1
            try:                                  # the index rows never hold up the equities: a short list keeps the stored ones
                ni: Any = await dhan.save_indices(store, idx)
                from .indices import DHAN_IDS_KEY
                await store.redis.delete(DHAN_IDS_KEY)   # the live index strip re-checks its mapping against the new file
            except dhan.DhanError as e:
                ni = str(e)
            result = {"status": "ok", "equities": n, "indices": ni}
            try:
                result["option_series"] = await save_option_lots(store, lots.rows())   # lot size per underlying and expiry (option chain)
            except dhan.DhanError as e:
                result["option_series_error"] = str(e)
            try:                                  # likewise the MCX futures: the commodity page keeps the stored contracts if the list is short
                result["commodities"] = await dhan.save_commodity_contracts(store, mcx)
                await store.redis.delete("cmd:contracts")
            except dhan.DhanError as e:
                result["commodities"] = str(e)
            await record_run(store, args.cmd, result)
            print(result)
            return 0
        if args.cmd == "refresh-commodities":
            from . import commodities
            print(await commodities.run(settings, store, loop=args.loop))
            return 0
        if args.cmd == "history-probe":
            from .history_probe import probe
            from .mf import record_run
            res = await probe(client, store, settings, args.symbols or None)
            await record_run(store, args.cmd, {"status": "ok", "companies": res})
            print(res)
            return 0
        if args.cmd == "dhan-check":
            from . import dhan
            from .mf import record_run
            try:
                res = await dhan.check(settings, store.redis)
            except dhan.DhanError as e:
                await record_run(store, args.cmd, {"status": "failed", "error": str(e)})
                print({"status": "failed", "error": str(e)})
                return 1
            ok = bool(res.get("configured")) and res.get("ltp") is not None
            await record_run(store, args.cmd, {"status": "ok" if ok else "incomplete", "mode": res.get("mode"), "data_plan": (res.get("account") or {}).get("dataPlan"),
                                               "data_valid_until": (res.get("account") or {}).get("dataValidity"), "instruments": res.get("instruments"),
                                               "ltp_reliance": res.get("ltp"), "commodity_segment": res.get("commodity_segment"), "why": res.get("why")})
            print(res)
            return 0 if ok else 1
        if args.cmd == "refresh-portfolios":
            from . import portfolios as disclosure
            from .mf import record_run, last_run_age_hours
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and age < args.max_age_hours:
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            names = list(args.only) if args.only else [*disclosure.STEP_NAMES, *(a.key for a in disclosure.ADAPTERS)]
            names = [n for n in names if n not in set(args.skip or ())]
            try:
                result = await disclosure.refresh(store, settings, names, args.months or disclosure.KEEP_MONTHS)
            except Exception as exc:
                await record_run(store, args.cmd, {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:300]})
                raise
            parts = {**result.get("steps", {}), **result.get("amc", {})}
            await record_run(store, args.cmd, {"status": result.get("status"), "why": str(result.get("why") or "")[:200],
                                               "parts": {k: v.get("status") for k, v in parts.items()},
                                               "stored": sum(int(v.get("stored") or 0) for v in result.get("amc", {}).values()),
                                               "failed": [f"{k}: {str(v.get('why') or '')[:80]}" for k, v in parts.items() if v.get("status") in ("error", "refused")][:8]})
            print(json.dumps(result, default=str)[:4000])
            return 0 if result.get("status") in ("ok", "partial") else 1
        if args.cmd == "backfill-mf":
            from .mf import backfill, record_run
            try:
                result = await backfill(store, settings, args.amc, force=args.force)
            except Exception as exc:
                await record_run(store, args.cmd, {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:300]})
                raise
            await record_run(store, args.cmd, {"status": result.get("status"), "done": len(result.get("done", [])), "failed": len(result.get("failed", []))})
            print(result)
            return 0 if result.get("status") == "ok" else 1
        if args.cmd in ("refresh-etf", "refresh-mf"):
            if args.cmd == "refresh-etf":
                from .etf import refresh as refresh_funds
            else:
                from .mf import refresh as refresh_funds
            from .mf import record_run, last_run_age_hours
            if args.max_age_hours:
                age, last = await last_run_age_hours(store, args.cmd)
                if age is not None and age < (args.max_age_hours if last == "ok" else min(0.25, args.max_age_hours)) and not (args.cmd == "refresh-mf" and await _mf_dashboard_empty(store)):
                    print({"status": "skipped", "reason": f"ran {age:.1f} hours ago ({last})"})
                    return 0
            try:
                result = await refresh_funds(store, settings, **({"resume": True} if getattr(args, "resume", False) else {}))
            except Exception as exc:
                await record_run(store, args.cmd, {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:300]})
                raise
            await record_run(store, args.cmd, {"status": result.get("status"), "reason": str(result.get("reason") or "")[:200],
                                               **{k: [str(x)[:60] for x in v[:4]] + ([f"+{len(v) - 4} more"] if len(v) > 4 else []) for k, v in result.items() if isinstance(v, list) and v}})
            print(result)
            return 0 if result.get("status") in ("ok", "partial", "skipped") else 1   # partial = some instruments failed but good rows were kept; skipped = nothing to do (no ETF price source set up); a refused or empty answer stops the boot chain
        if args.cmd in ("rebuild-metrics", "refresh-indices"):
            from .screener import jobs
            if args.cmd == "rebuild-metrics":
                print(await jobs.rebuild_metrics(store, args.only_missing), "companies updated")
            else:
                print(await jobs.refresh_indices(store))
            return 0
        async with FinEdgeClient(settings) as client:
            if args.cmd == "refresh-universe":
                print(await refresh_universe(client, store), "companies")
            elif args.cmd == "refresh-short-history":
                async with store.pool.acquire() as conn:
                    short = [r["symbol"] for r in await conn.fetch(
                        "SELECT symbol FROM snapshots WHERE section = 'financials' AND statement = 'consolidated' "
                        "AND jsonb_array_length(body::jsonb #> '{yearly,pl,periods}') BETWEEN 1 AND 4 ORDER BY symbol")]
                print(len(short), "reports with a short history", short[:30])
                results = await ingest_many(client, store, [(s, "consolidated") for s in short], parallel=2) if short else []
                await store.invalidate_search()
                for r in results:
                    print(f"{r['symbol']:<14} {r['status']:<7} {r['ms']:>6} ms  {r['errors'] or ''}")
            elif args.cmd == "ingest":
                results = await ingest_many(client, store, [(s, args.statement) for s in args.symbols])
                await store.invalidate_search()
                for r in results:
                    print(f"{r['symbol']:<14} {r['status']:<7} {r['ms']:>6} ms  {r['errors'] or ''}")
                return 0 if all(r["status"] in ("ok", "warnings") for r in results) else 1
            elif args.cmd == "ingest-all":
                print(await ingest_all(client, store, args.statement, args.hours, args.limit, args.parallel))
            elif args.cmd == "probe":
                results = await probe(client, args.symbol)
                for key, state, ms in results:
                    print(f"{key:<22} {state:<12} {ms:>6.0f} ms")
                return 0 if all(st in ("ok", "empty") for _, st, _ in results) else 1
            elif args.cmd == "refresh-stale":
                items = await store.snapshot_symbols(args.hours or settings.fundamentals_ttl_hours)
                await ingest_many(client, store, items)
                print(len(items), "refreshed")
            elif args.cmd == "prune":
                keep = args.keep or int(os.getenv("INGEST_LIMIT") or 0) or 500
                print(await store.prune(keep))
            elif args.cmd == "score-all":
                limit = args.limit or int(os.getenv("SCORE_ALL_PER_RUN") or 0) or 1500
                print(await score_all(client, store, limit, args.days, args.parallel, max_minutes=args.max_minutes))
            elif args.cmd == "refresh-listing":
                from .screener.listing import refresh_listing
                async with DhanClient(settings, store.redis) as dc:
                    print(await refresh_listing(client, store, force=args.force, dhan_client=dc))
            elif args.cmd == "refresh-logos":
                from .logos import refresh as refresh_logos
                print(await refresh_logos(store, client, limit=args.limit, profile_limit=args.profiles))
            elif args.cmd == "refresh-calendars":
                from .calendars import refresh_calendars
                print(await refresh_calendars(client, store))
            elif args.cmd == "refresh-quotes":
                from .dhan import DhanClient
                async with DhanClient(settings, store.redis) as dc:
                    print(await refresh_quotes(client, store, dhan_client=dc), "quotes updated")
            elif args.cmd == "refresh-results":
                print(await refresh_results(client, store))
            elif args.cmd == "drain-queue":
                print(await drain_queue(client, store, loop=args.loop), "ingested")
    finally:
        await store.close()
    return 0


def cli():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # FinEdge takes the key as a ?token= query parameter, so httpx's request log lines would print it.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    cli()
