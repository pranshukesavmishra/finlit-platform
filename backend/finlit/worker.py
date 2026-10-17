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
import logging
import time
from typing import Iterable, List, Optional, Tuple

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


async def ingest_one(client: FinEdgeClient, store: Store, symbol: str, statement: str = "consolidated") -> dict:
    started, calls_before = time.perf_counter(), client.calls
    symbol = symbol.strip().upper()
    company = await store.company(symbol)
    try:
        bundle = await client.fetch_bundle(symbol, statement)
        if company:
            bundle["symbol_row"] = {"symbol": company["symbol"], "name": company["name"], "nse_code": company["nse_code"],
                                    "bse_code": company["bse_code"], "consolidated_ind": company["has_consolidated"]}
        if not bundle.get("pl_annual") and not bundle.get("daily_quotes"):
            raise FinEdgeError("bundle", 404, "no statements or prices for symbol")
        sections = snapshot.build(bundle)
        checks = sections["summary"]["dataQuality"]["checks"]
        if checks["status"] == "rejected":
            # Keep serving the last good snapshot; a human reviews the logged issues.
            raise DataRejected([i for i in checks["issues"] if i["severity"] == "critical"])
        sections["peers"]["items"] = await store.peer_rows(sections["peers"]["symbols"])
        effective = bundle["statement"]
        row = snapshot.score_row(sections)
        await store.save_snapshot(symbol, statement, sections, row, sections["price"]["daily"])
        if effective != statement:  # also serve it under the basis it really is
            await store.save_snapshot(symbol, effective, sections, row)
        prof = sections["summary"]["profile"]
        await store.set_company_meta(symbol, prof.get("sector"), prof.get("industry"))
        status = "ok" if checks["status"] == "ok" else "warnings"
        errors = {**(bundle.get("errors") or {}), **({"quality": checks["issues"]} if checks["issues"] else {})}
    except DataRejected as exc:
        log.warning("ingest %s rejected by quality gate: %s", symbol, exc.issues)
        status, errors = "rejected", {"quality": exc.issues}
    except Exception as exc:  # one bad stock must never stop a batch
        log.exception("ingest %s failed", symbol)
        status, errors = "failed", {"error": str(exc)[:500]}
    duration = int((time.perf_counter() - started) * 1000)
    await store.log_run(symbol, statement, status, client.calls - calls_before, duration, errors)
    log.info("ingest %s %s %s in %d ms (%d calls)", symbol, statement, status, duration, client.calls - calls_before)
    return {"symbol": symbol, "status": status, "ms": duration, "errors": errors}


async def ingest_many(client: FinEdgeClient, store: Store, items: Iterable[Tuple[str, str]], parallel: int = 2) -> List[dict]:
    # Each stock already fans out ~21 requests; a couple of stocks at a time keeps us inside rate limits.
    sem = asyncio.Semaphore(parallel)

    async def run(symbol, statement):
        async with sem:
            return await ingest_one(client, store, symbol, statement)

    return await asyncio.gather(*(run(s, st) for s, st in items))


async def refresh_universe(client: FinEdgeClient, store: Store) -> int:
    rows = await client.stock_symbols()
    count = await store.upsert_companies(rows)
    log.info("universe: %d companies", count)
    return count


async def refresh_quotes(client: FinEdgeClient, store: Store, symbols: Optional[List[Tuple[str, str]]] = None) -> int:
    """Patch the live quote into each summary without re-fetching fundamentals."""
    items = symbols or await store.snapshot_symbols()
    updated = 0

    async def one(symbol: str, statement: str):
        nonlocal updated
        cached = await store.get_section(symbol, statement, "summary")
        if not cached:
            return
        try:
            live = market.quote(await client.get("/quote", {"symbol": symbol}, timeout=5), symbol)
        except FinEdgeError:
            return
        if not live.get("price"):
            return
        summary = orjson.loads(cached[0])
        if summary["quote"].get("price") == live["price"] and summary["quote"].get("asOf") == live.get("asOf"):
            return
        summary["quote"] = {**summary["quote"], **{k: v for k, v in live.items() if v is not None}}
        await store.save_snapshot(symbol, statement, {"summary": summary})
        updated += 1

    await asyncio.gather(*(one(s, st) for s, st in items))
    return updated


async def drain_queue(client: FinEdgeClient, store: Store, loop: bool = False, idle_seconds: float = 2.0) -> int:
    total = 0
    while True:
        items = await store.claim(10)
        if items:
            await ingest_many(client, store, items)
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
        for r in await ingest_many(client, store, [(s, statement) for s in batch], parallel=parallel):
            done[r["status"]] = done.get(r["status"], 0) + 1
        await store.invalidate_search()
        log.info("ingest-all: %d / %d  %s  (%d upstream calls)", min(i + chunk, len(pending)), len(pending), done, client.calls)
    return done


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
    sub.add_parser("check-alerts", help="email members whose watchlist stocks crossed their target price")
    sub.add_parser("check-screens", help="email members when a company newly matches one of their saved screens")
    sub.add_parser("send-digest", help="send the weekly week-ahead email to members who switched it on")
    sub.add_parser("refresh-quotes")
    p_drain = sub.add_parser("drain-queue")
    p_drain.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)

    settings = settings or get_settings()
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
            print(await check_alerts(store.pool, mailer, settings.public_site_url), "alerts sent")
            return 0
        async with FinEdgeClient(settings) as client:
            if args.cmd == "refresh-universe":
                print(await refresh_universe(client, store), "companies")
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
            elif args.cmd == "refresh-quotes":
                print(await refresh_quotes(client, store), "quotes updated")
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
