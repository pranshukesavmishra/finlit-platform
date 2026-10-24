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
            company = await store.company(sym)
            row["upstox"] = "token set" if up.enabled else "no token"
            if up.enabled and company:
                try:
                    inst = await up.resolve(sym, [n for n in (company["name"], company["nse_code"]) if n], dict(company).get("isin"))
                    row["upstox instrument"] = bool(inst)
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
