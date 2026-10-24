"""A read-only look at how many yearly statements each source holds for a few old companies, so a gap can be told from a bug. Recorded where
/api/mf/status shows it (the host's logs are not reachable from outside). Calls: about 8 per company."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import upstox
from .finedge import bundle_requests

DEFAULT = ["LICI", "SBILIFE", "HDFCLIFE", "ICICIGI", "NESTLEIND", "HYUNDAI", "IRCTC", "JIOFIN", "TCS"]


def _span(rows: Any) -> Optional[str]:
    rows = rows.get("financials") if isinstance(rows, dict) else rows
    ends = sorted(str(r.get("period_end") or r.get("year"))[:7] for r in rows or [] if isinstance(r, dict))
    return f"{len(ends)}: {ends[0]}..{ends[-1]}" if ends else "0"


def _shape(payload: Any) -> str:
    """What an endpoint answered: the longest list in it, how many entries, and the period range or the first keys."""
    if isinstance(payload, list):
        lst, name = payload, "list"
    elif isinstance(payload, dict):
        lists = [(k, v) for k, v in payload.items() if isinstance(v, list)]
        if not lists:
            return "keys " + ",".join(list(payload)[:8])
        name, lst = max(lists, key=lambda kv: len(kv[1]))
    else:
        return str(type(payload).__name__)
    if not lst:
        return f"{name}: 0"
    first = lst[0] if isinstance(lst[0], dict) else {}
    span = _span(lst) if any(k in first for k in ("period_end", "year")) else "-"
    return f"{name}: {len(lst)} ({span}); keys " + ",".join(list(first)[:10])


async def probe(client, store, settings, symbols: Optional[List[str]] = None) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    up = upstox.UpstoxClient(settings=settings, redis=store.redis)
    try:
        for sym in symbols or DEFAULT:
            row: Dict[str, Any] = {}
            for basis in ("consolidated", "standalone"):
                req = bundle_requests(sym, basis)
                for key in ("pl_annual", "bs_annual", "cf_annual"):
                    path, params, timeout = req[key]
                    try:
                        row[f"finedge {basis} {key}"] = _span(await client.get(path, params, timeout=timeout, retries=1))
                    except Exception as exc:
                        row[f"finedge {basis} {key}"] = f"error {str(exc)[:40]}"
            if sym == (symbols or DEFAULT)[0]:       # every other endpoint the old site might have read, for the first company only
                for basis in ("consolidated", "standalone"):
                    for key, (path, params, timeout) in bundle_requests(sym, basis).items():
                        if key in ("pl_annual", "bs_annual", "cf_annual", "profile", "peers", "quote", "daily_quotes", "daily_price_ratios", "corporate_actions", "announcements", "shareholding", "dividends"):
                            continue
                        try:
                            row[f"{basis} {key}"] = _shape(await client.get(path, params, timeout=timeout, retries=1))
                        except Exception as exc:
                            row[f"{basis} {key}"] = f"error {str(exc)[:40]}"
            if sym == (symbols or DEFAULT)[0]:       # what the cash-flow and balance-sheet rows of both sources look like, to line their years up
                try:
                    path, params, timeout = bundle_requests(sym, "standalone")["cf_annual"]
                    rows = (await client.get(path, params, timeout=timeout, retries=1) or {}).get("financials") or []
                    row["finedge cf row keys"] = sorted(rows[-1])[:30] if rows else []
                    row["finedge cf period_end values"] = [str(r.get("period_end")) for r in rows]
                except Exception as exc:
                    row["finedge cf row keys"] = f"error {str(exc)[:40]}"
            company = await store.company(sym)
            row["upstox"] = "token set" if up.enabled else "no token"
            if up.enabled and company:
                try:
                    inst = await up.resolve(sym, [n for n in (company["name"], company["nse_code"]) if n], dict(company).get("isin"))
                    row["upstox instrument"] = bool(inst)
                    if inst and sym == (symbols or DEFAULT)[0]:
                        bs = await up.statement(inst["isin"], "balance-sheet", "standalone", "yearly")
                        hist = (bs.get("history") if isinstance(bs, dict) else None) or []
                        row["upstox balance sheet"] = {"keys": sorted(bs) if isinstance(bs, dict) else str(type(bs)), "history rows": len(hist), "first row keys": sorted(hist[0]) if hist and isinstance(hist[0], dict) else []}
                        cf = await up.statement(inst["isin"], "cash-flow", "standalone", "yearly")
                        row["upstox cash flow"] = {"categories": [r.get("category") for r in (cf.get("cash_flow") or [])][:20] if isinstance(cf, dict) else str(type(cf)),
                                                   "periods": [pt.get("period") for pt in ((cf.get("cash_flow") or [{}])[0].get("history") or [])] if isinstance(cf, dict) else []}
                    if inst:
                        for basis in ("consolidated", "standalone"):
                            rows = upstox.income_rows(await up.statement(inst["isin"], "income-statement", basis, "yearly"))
                            row[f"upstox {basis} income"] = _span(rows)
                            row[f"upstox {basis} net profit (Cr)"] = {r["period_end"][:4]: round(r.get("profitLossForPeriod", 0) / upstox.CRORE) for r in rows[-5:]}
                except Exception as exc:
                    row["upstox error"] = str(exc)[:60]
            out[sym] = row
    finally:
        await up.aclose()
    return out
