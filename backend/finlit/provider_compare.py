"""compare-provider: for a few companies, put FinEdge's raw figure next to the figure our stored report shows, and say which rule produced ours.

    python -m finlit.worker compare-provider --symbols LUMAXTECH
    python -m finlit.worker compare-provider --sample 5

Why: the company's older site and this one must agree wherever both read FinEdge. The founder cannot check every company by hand, so this tool
checks the whole data path for any company in one command: the raw FinEdge answer (endpoint and field named), the figure in our stored report
(section named), the percent difference, a verdict and the rule that produced our figure.

Verdicts:  match (within 0.5%)  |  explained (a named, legitimate reason: a labelled fallback, a different date, the one-market-cap rule ...)  |  MISMATCH
Exit code 1 when any figure is a MISMATCH. The result is stored in mf_meta ('provider-compare:last') like the integrity audit's.

Provider calls: at most 9 per company (company profile, quote, daily price ratios, ratios pr and le, basic financials, yearly and quarterly P&L, yearly
balance sheet), 11 with --discover (adds financial-metrics cu and av to look for fields our code does not read yet). Sequential, with a pause between calls.
The pure functions take plain dicts, so the tests need neither the network nor a database.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .normalize import statements
from .normalize.common import crore, fiscal_year_label, parse_date, to_number
from .normalize.ratios import _fy

log = logging.getLogger("finlit.provider_compare")

META_LAST = "provider-compare:last"
TOLERANCE_PCT = 0.5          # a figure within this percent of FinEdge's is a match
PAUSE_SECONDS = 0.4          # between provider calls
CALLS = ("profile", "quote", "daily_price_ratios", "ratios_pr", "ratios_le", "basic", "pl_annual", "pl_quarterly", "bs_annual")
DISCOVER_CALLS = {"metrics_cu": ("/financial-metrics/{s}", {"statement_type": "{t}", "ratio_type": "cu"}, 10),
                  "metrics_av": ("/financial-metrics/{s}", {"statement_type": "{t}", "ratio_type": "av"}, 10)}
WATCH = re.compile(r"yield|ev.?to.?ebitda|ev.?ebitda|enterprise|evebit", re.IGNORECASE)   # field names that would be a FinEdge EV/EBITDA or dividend yield

# key -> (label, unit)
FIGURES: List[Tuple[str, str, str]] = [
    ("mcap_profile", "Market cap, company profile", "Cr"),
    ("mcap_quote", "Market cap, live quote", "Cr"),
    ("mcap_screener", "Market cap, screener metrics", "Cr"),
    ("price", "Price", "Rs"),
    ("pe", "P/E", "x"),
    ("pb", "P/B", "x"),
    ("ev_ebitda", "EV/EBITDA", "x"),
    ("dividend_yield", "Dividend yield", "%"),
    ("roe", "ROE", "%"),
    ("roce", "ROCE", "%"),
    ("debt_to_equity", "Debt / equity", "x"),
    ("sales_year", "Net sales, latest year", "Cr"),
    ("profit_year", "Net profit, latest year", "Cr"),
    ("sales_ttm", "Net sales, TTM (last 4 quarters)", "Cr"),
    ("profit_ttm", "Net profit, TTM (last 4 quarters)", "Cr"),
    ("eps", "EPS, latest year", "Rs"),
    ("book_value_ps", "Book value per share", "Rs"),
    ("shares", "Shares outstanding", "count"),
]
LABEL = {k: (label, unit) for k, label, unit in FIGURES}
RULE_TEXT = {
    "finedge": "FinEdge's own figure (rule: FinEdge wins)",
    "fallback": "FinLit fallback (FinEdge sent none)",
    "override": "FinLit override (different measure or basis, see note)",
    None: "not labelled (report stored before the rule labels: rebuild it)",
}


# ---------------------------------------------------------------- helpers

def _num(v: Any) -> Optional[float]:
    return to_number(v)


def _rows(payload: Any, key: str) -> List[dict]:
    value = payload.get(key) if isinstance(payload, dict) else payload
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def _statement_rows(payload: Any) -> List[dict]:
    return statements._ordered(_rows(payload, "financials"))


def _first_key(row: dict, keys: Tuple[str, ...]) -> Optional[str]:
    return next((k for k in keys if row.get(k) not in (None, "")), None)


def _raw(value: Optional[float], endpoint: str, field: str, note: str = "", **extra: Any) -> dict:
    return {"value": value, "endpoint": endpoint, "field": field, "note": note, **extra}


def _ratio_row(payload: Any, period: Optional[str], fy_month: int = 3) -> Tuple[Optional[dict], Optional[str]]:
    """The FinEdge ratio row for one of OUR period labels ('TTM' or 'FY26'); the newest annual row when we have no period."""
    rows = _rows(payload, "ratios")
    if period:
        for r in rows:
            if _fy(r, fy_month) == period:
                return r, str(r.get("header"))
    ttm = next((r for r in rows if str(r.get("header")).upper() == "TTM"), None)
    return (ttm, "TTM") if ttm else (None, None)


# ---------------------------------------------------------------- what FinEdge sent (raw)

def raw_figures(symbol: str, payloads: Dict[str, Any], periods: Optional[Dict[str, str]] = None) -> Dict[str, dict]:
    """key -> {value, endpoint, field, note}. `periods` are the period labels OUR report shows ({'roe': 'TTM', 'roce': 'FY26'}), so a ratio is looked up
    in the FinEdge row for the same period."""
    periods = periods or {}
    sym = symbol.upper()
    out: Dict[str, dict] = {}
    prof = payloads.get("profile") if isinstance(payloads.get("profile"), dict) else {}
    out["mcap_profile"] = _raw(_num(prof.get("market_cap")), "/company-profile/{symbol}", "market_cap", "Rs crore")
    q = (payloads.get("quote") or {}).get(sym) if isinstance(payloads.get("quote"), dict) else None
    q = q if isinstance(q, dict) else {}
    tradetime = q.get("tradetime")
    out["mcap_quote"] = _raw(_num(q.get("market_cap")), "/quote?symbol={symbol}", f"{sym}.market_cap", "Rs crore", asOf=tradetime)
    out["mcap_screener"] = {**out["mcap_quote"], "note": "the screener reads the quote's market cap, else the profile's"}
    out["price"] = _raw(_num(q.get("current_price")), "/quote?symbol={symbol}", f"{sym}.current_price", "Rs", asOf=tradetime)

    pr = sorted((r for r in _rows(payloads.get("daily_price_ratios"), "price_ratios") if parse_date(r.get("quote_date"))), key=lambda r: parse_date(r["quote_date"]))
    last = pr[-1] if pr else {}
    for key in ("pe", "pb"):
        out[key] = _raw(_num(last.get(key)), "/daily-price-ratios/{symbol}", f"price_ratios[{last.get('quote_date')}].{key}", "FinEdge sends 0 when a ratio is undefined",
                        asOf=last.get("quote_date"))

    watch = payloads.get("_watch") or []
    for key, words in (("ev_ebitda", "EV/EBITDA"), ("dividend_yield", "dividend yield")):
        hits = [w for w in watch if (re.search(r"yield", w["field"], re.I) is not None) == (key == "dividend_yield")]
        if hits:
            h = hits[0]
            out[key] = _raw(_num(h["value"]), h["endpoint"], h["field"], f"FinEdge field found: {h['field']}", found=True)
        else:
            out[key] = _raw(None, "(none)", "(none)", f"FinEdge has no {words} field in any endpoint read")

    for key, fam, field in (("roe", "ratios_pr", "returnOnEquity"), ("roce", "ratios_pr", "returnOnCapital"), ("debt_to_equity", "ratios_le", "totalDebtToEquity")):
        row, header = _ratio_row(payloads.get(fam), periods.get(key))
        v = _num((row or {}).get(field))
        if v is not None and key != "debt_to_equity":
            v = round(v * 100, 2)   # FinEdge sends profitability as fractions
        out[key] = _raw(v, "/ratios/{symbol}?ratio_type=" + ("pr" if fam == "ratios_pr" else "le"), f"ratios[{header}].{field}", "fraction x 100" if key != "debt_to_equity" else "")

    pl = _statement_rows(payloads.get("pl_annual"))
    if pl:
        r = pl[-1]
        label = fiscal_year_label(r.get("period_end"), r.get("year"))
        sk = _first_key(r, ("revenueFromOperations", "interestEarned", "operatingIncome", "income")) or "revenueFromOperations"
        out["sales_year"] = _raw(statements._revenue(r), "/financials/{symbol}?statement_code=pl&period=annual", f"financials[{label}].{sk}", "rupees / 1e7 = Rs crore", period=label)
        pk = _first_key(r, ("profitOrLossAttributableToOwners", "profitLossForPeriod", "profitLossForThePeriod", "profitLossAfterTax")) or "profitLossForPeriod"
        out["profit_year"] = _raw(crore(statements._net_profit(r)), "/financials/{symbol}?statement_code=pl&period=annual", f"financials[{label}].{pk}", "rupees / 1e7 = Rs crore (owners' share)", period=label)
        out["eps"] = _raw(statements.eps_checked(r)[0], "/financials/{symbol}?statement_code=pl&period=annual", f"financials[{label}].eps", "Rs per share", period=label)
    else:
        for k in ("sales_year", "profit_year", "eps"):
            out[k] = _raw(None, "/financials/{symbol}?statement_code=pl&period=annual", "(no rows)")
    qs = _statement_rows(payloads.get("pl_quarterly"))[-4:]
    if len(qs) == 4:
        qlabel = f"{parse_date(qs[0].get('period_end'))}..{parse_date(qs[-1].get('period_end'))}"
        sk = _first_key(qs[-1], ("revenueFromOperations", "interestEarned", "operatingIncome", "income")) or "revenueFromOperations"
        pk = _first_key(qs[-1], ("profitOrLossAttributableToOwners", "profitLossForPeriod", "profitLossForThePeriod", "profitLossAfterTax")) or "profitLossForPeriod"
        sv, pv = [statements._revenue(r) for r in qs], [crore(statements._net_profit(r)) for r in qs]
        out["sales_ttm"] = _raw(round(sum(sv), 2) if None not in sv else None, "/financials/{symbol}?statement_code=pl&period=quarterly", f"sum of financials[{qlabel}].{sk}", "last four quarters added up")
        out["profit_ttm"] = _raw(round(sum(pv), 2) if None not in pv else None, "/financials/{symbol}?statement_code=pl&period=quarterly", f"sum of financials[{qlabel}].{pk}", "last four quarters added up")
    else:
        for k in ("sales_ttm", "profit_ttm"):
            out[k] = _raw(None, "/financials/{symbol}?statement_code=pl&period=quarterly", "(fewer than 4 quarters)")

    bs = _statement_rows(payloads.get("bs_annual"))
    basic = next((r for r in _rows(payloads.get("basic"), "ratios") if str(r.get("header")).upper() == "TTM"), {})
    shares = _num(basic.get("sharesOutstanding"))
    out["shares"] = _raw(shares, "/basic-financials/{symbol}?statement_code=pl", "ratios[TTM].sharesOutstanding", "number of shares")
    if bs and pl and _num(pl[-1].get("dilutedOutstandingShares")):
        equity = statements._equity(bs[-1])   # already Rs crore
        out["book_value_ps"] = _raw(round(equity * 1e7 / _num(pl[-1]["dilutedOutstandingShares"]), 2) if equity is not None else None,
                                    "/financials/{symbol}?statement_code=bs&period=annual", "totalEquity / pl dilutedOutstandingShares", "Rs per share; FinEdge sends no book value per share")
    else:
        out["book_value_ps"] = _raw(None, "/financials/{symbol}?statement_code=bs&period=annual", "(no rows)")
    return out


def discover(payloads: Dict[str, Any]) -> List[dict]:
    """Every field anywhere in the payloads whose name looks like EV/EBITDA or a yield: [{endpoint, field, value}] (the first row of a list only)."""
    found: List[dict] = []

    def walk(node: Any, endpoint: str, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    walk(v, endpoint, f"{path}.{k}" if path else str(k))
                elif WATCH.search(str(k)):
                    found.append({"endpoint": endpoint, "field": f"{path}.{k}" if path else str(k), "value": v})
        elif isinstance(node, list) and node:
            walk(node[0], endpoint, path + "[0]")
    for name, payload in payloads.items():
        if not name.startswith("_"):
            walk(payload, name, "")
    return found


# ---------------------------------------------------------------- what our stored report shows

def stored_figures(sections: Dict[str, dict]) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """-> (key -> {value, where, rule, note, period, asOf}, our period labels for roe/roce/debt_to_equity)."""
    from .screener import compute as screener_compute
    summary, rat, fin = sections.get("summary") or {}, sections.get("ratios") or {}, sections.get("financials") or {}
    latest, blanks = rat.get("latest") or {}, rat.get("blanks") or {}
    prof, quote = summary.get("profile") or {}, summary.get("quote") or {}
    yearly = (fin.get("yearly") or {})
    pl, bs = yearly.get("pl") or {}, yearly.get("bs") or {}
    qpl = (fin.get("quarterly") or {}).get("pl") or {}
    out: Dict[str, dict] = {}

    def ours(value, where, rule=None, note=None, period=None, asof=None, blank=None):
        return {"value": value, "where": where, "rule": rule, "note": note, "period": period, "asOf": asof, "blank": blank}

    out["mcap_profile"] = ours(prof.get("marketCapCr"), "summary.profile.marketCapCr", prof.get("marketCapSource") or None,
                               "one market cap on the whole page: the live quote's, else the profile's", asof=quote.get("asOf"))
    out["mcap_quote"] = ours(quote.get("marketCapCr"), "summary.quote.marketCapCr", prof.get("marketCapSource") or None, asof=quote.get("asOf"))
    try:
        metrics = screener_compute.compute(sections)
    except Exception as exc:   # an old or partial report must not stop the audit
        log.info("screener metrics not computed (%s)", type(exc).__name__)
        metrics = {}
    out["mcap_screener"] = ours(metrics.get("market_cap"), "scores.metrics.market_cap (screener_compute.compute)", prof.get("marketCapSource") or None, asof=quote.get("asOf"))
    out["price"] = ours(quote.get("price"), "summary.quote.price", "quote-price", asof=quote.get("asOf"))
    for key in ("pe", "pb", "ev_ebitda", "dividend_yield", "roe", "roce", "debt_to_equity"):
        e = latest.get(key) or {}
        out[key] = ours(e.get("value"), f"ratios.latest.{key}", e.get("rule"), e.get("note"), e.get("period"), blank=blanks.get(key))
    ps = lambda t, k: [v for v in (t.get("rows") or {}).get(k) or []]   # noqa: E731
    for key, table, row, where in (("sales_year", pl, "revenue", "financials.yearly.pl.rows.revenue"), ("profit_year", pl, "net_profit", "financials.yearly.pl.rows.net_profit"),
                                   ("eps", pl, "eps", "financials.yearly.pl.rows.eps")):
        vals = ps(table, row)
        period = (table.get("periods") or [None])[-1]
        out[key] = ours(vals[-1] if vals else None, f"{where}[{period}]", "statement", "FinEdge statement line converted to Rs crore", period)
    for key, row in (("sales_ttm", "revenue"), ("profit_ttm", "net_profit")):
        vals = ps(qpl, row)[-4:]
        out[key] = ours(round(sum(vals), 2) if len(vals) == 4 and None not in vals else None, f"financials.quarterly.pl.rows.{row} (last 4 added)", "statement",
                        "FinEdge statement lines converted to Rs crore", (qpl.get("periods") or [None])[-1])
    out["book_value_ps"] = ours(metrics.get("book_value_ps"), "scores.metrics.book_value_ps (equity / diluted shares)", "statement")
    sh = ps(pl, "diluted_shares_cr")
    out["shares"] = ours(round(sh[-1] * 1e7) if sh and sh[-1] else None, "financials.yearly.pl.rows.diluted_shares_cr x 1e7", "statement")
    periods = {k: (out[k].get("period")) for k in ("roe", "roce", "debt_to_equity") if out[k].get("period")}
    return out, periods


# ---------------------------------------------------------------- verdict

def _diff_pct(ours: float, raw: float) -> Optional[float]:
    return None if not raw else round((ours - raw) / abs(raw) * 100, 3)


def _same_instant(a: Any, b: Any) -> bool:
    return bool(a) and bool(b) and str(a)[:16].replace("Z", "") == str(b)[:16].replace("Z", "").split("+")[0]


def judge(key: str, raw: dict, ours: dict) -> Tuple[Optional[float], str, str]:
    """-> (percent difference or None, verdict, reason). Verdict is 'match', 'explained' or 'MISMATCH'."""
    rv, ov = raw.get("value"), ours.get("value")
    if rv is None and ov is None:
        if ours.get("blank"):
            return None, "match", "both blank; our reason: " + ours["blank"]
        if key in ("ev_ebitda", "dividend_yield", "pe", "pb"):
            return None, "MISMATCH", "blank with no reason shown (report stored before the blank reasons: rebuild it)"
        return None, "match", "both blank"
    if rv is None:
        if raw.get("found"):
            return None, "MISMATCH", f"FinEdge sends {raw['field']} but our rule did not use it"
        if ours.get("rule") == "fallback" and ours.get("note"):
            return None, "explained", "FinEdge sent none; our figure is the labelled fallback"
        if ours.get("rule") == "statement":
            return None, "explained", "FinEdge's raw answer has no such field to compare; ours is built from its statements"
        return None, "MISMATCH", "FinEdge sent none, yet we show a figure with no fallback label"
    if ov is None:
        if key in ("pe", "pb") and (rv or 0) <= 0:
            return None, "explained", "FinEdge sent 0 = undefined; we show no number" + (": " + ours["blank"] if ours.get("blank") else "")
        return None, "MISMATCH", "FinEdge has the figure, ours is blank" + (f" ({ours['blank']})" if ours.get("blank") else " with no reason")
    candidates = [ov, ov / 100] if key == "dividend_yield" and raw.get("found") else [ov]
    diff = min((_diff_pct(c, rv) for c in candidates), key=lambda d: abs(d) if d is not None else 1e9)
    if diff is not None and abs(diff) <= TOLERANCE_PCT:
        return diff, "match", ""
    # --- explained differences, each with a named reason
    if key == "mcap_profile" and ours.get("rule") == "quote":
        return diff, "explained", "rule: one market cap on the page = the live quote's; FinEdge's profile figure is an older daily file"
    if key in ("mcap_quote", "mcap_screener", "price") and not _same_instant(ours.get("asOf"), raw.get("asOf")):
        return diff, "explained", f"our stored quote is from {ours.get('asOf')}, FinEdge's now is from {raw.get('asOf')}"
    if key in ("pe", "pb") and ours.get("rule") == "finedge" and raw.get("asOf") and str(ours.get("period") or "").lower() != f"as of {_pretty(raw.get('asOf'))}".lower():
        return diff, "explained", f"our stored figure is FinEdge's of {ours.get('period')}; FinEdge's file has since moved to {raw.get('asOf')}"
    if ours.get("rule") == "override" and ours.get("note"):
        return diff, "explained", "override: " + ours["note"]
    if key in ("sales_year", "profit_year", "eps") and raw.get("period") and ours.get("period") != raw.get("period"):
        return diff, "explained", f"our report's latest year is {ours.get('period')}, FinEdge now has {raw.get('period')}: refresh the report"
    return diff, "MISMATCH", "no rule or date difference explains this"


def _pretty(iso: Any) -> str:
    d = parse_date(iso)
    return f"{d:%d %b %Y}" if d else str(iso)


# ---------------------------------------------------------------- one company

def compare_symbol(symbol: str, statement: str, payloads: Dict[str, Any], sections: Dict[str, dict]) -> dict:
    ours, periods = stored_figures(sections)
    if "_watch" not in payloads:
        payloads = {**payloads, "_watch": discover(payloads)}
    raw = raw_figures(symbol, payloads, periods)
    rows = []
    for key, label, unit in FIGURES:
        r, o = raw[key], ours[key]
        diff, verdict, why = judge(key, r, o)
        rows.append({
            "key": key, "label": label, "unit": unit,
            "finedge": {"value": r["value"], "endpoint": r["endpoint"], "field": r["field"], "note": r.get("note", "")},
            "ours": {"value": o["value"], "where": o["where"], "period": o.get("period")},
            "diffPct": diff, "verdict": verdict, "why": why,
            "rule": RULE_TEXT.get(o.get("rule"), str(o.get("rule"))) if o.get("rule") not in ("quote", "profile", "statement", "quote-price") else {
                "quote-price": "FinEdge live quote price (else last daily close)", "quote": "one market cap: FinEdge's live quote", "profile": "one market cap: FinEdge's profile (the quote sent none)", "statement": "FinEdge statement line, converted"}[o["rule"]],
            "note": o.get("note") or "",
        })
    seen = [w for w in payloads.get("_watch") or []]
    quote = (payloads.get("quote") or {}).get(symbol.upper()) if isinstance(payloads.get("quote"), dict) else {}
    info = []
    shares_q, mcap_q, price_q = _num((quote or {}).get("shares")), _num((quote or {}).get("market_cap")), _num((quote or {}).get("current_price"))
    if shares_q and mcap_q and price_q and abs(shares_q * price_q / 1e7 / mcap_q - 1) > 0.05:
        info.append(f"FinEdge /quote.shares ({shares_q:,.0f}) disagrees with its own market_cap / current_price ({mcap_q * 1e7 / price_q:,.0f}): the quote's share count is not used.")
    meta = (sections.get("summary") or {}).get("meta") or {}
    return {"symbol": symbol.upper(), "statement": statement, "generatedAt": meta.get("generatedAt"), "version": meta.get("version"), "rows": rows,
            "counts": {v: sum(1 for r in rows if r["verdict"] == v) for v in ("match", "explained", "MISMATCH")}, "providerFieldsSeen": seen, "info": info}


def render(result: dict) -> str:
    lines: List[str] = []
    for c in result["companies"]:
        if c.get("error"):
            lines += [f"=== {c['symbol']}: {c['error']}", ""]
            continue
        lines.append(f"=== {c['symbol']} ({c['statement']} report, built {c.get('generatedAt')}, version {c.get('version')})  match {c['counts']['match']}  explained {c['counts']['explained']}  MISMATCH {c['counts']['MISMATCH']}")
        for r in c["rows"]:
            fe, us = r["finedge"], r["ours"]
            diff = "" if r["diffPct"] is None else f"{r['diffPct']:+.2f}%"
            lines.append(f"{r['label']} [{r['unit']}]  -> {r['verdict']}{'  ' + diff if diff else ''}")
            lines.append(f"    FinEdge  {_fmt(fe['value']):>16}   {fe['endpoint']}  field {fe['field']}" + (f"   ({fe['note']})" if fe["note"] else ""))
            lines.append(f"    ours     {_fmt(us['value']):>16}   {us['where']}" + (f"  period {us['period']}" if us.get("period") else ""))
            lines.append(f"    rule     {r['rule']}" + (f"   note: {r['note']}" if r["note"] else ""))
            if r["why"]:
                lines.append(f"    why      {r['why']}")
        for w in c["providerFieldsSeen"]:
            lines.append(f"  FinEdge field seen: {w['endpoint']} {w['field']} = {w['value']}")
        lines += [f"  note: {i}" for i in c["info"]]
        lines.append("")
    lines.append(f"{result['companies'].__len__()} companies, {result['calls']} provider calls: match {result['match']}  explained {result['explained']}  MISMATCH {result['mismatches']}")
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if v is None:
        return "none"
    return f"{v:,.2f}" if isinstance(v, float) and abs(v) < 1e7 else f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


# ---------------------------------------------------------------- the run (provider + database)

async def fetch_payloads(client, symbol: str, statement: str, discover_fields: bool = False, pause: float = PAUSE_SECONDS) -> Tuple[Dict[str, Any], int, Dict[str, str]]:
    """The raw FinEdge answers, one after another with a pause. -> (payloads, calls made, {call: error})."""
    from .finedge import FinEdgeError, bundle_requests
    reqs = bundle_requests(symbol, statement)
    wanted = {k: reqs[k] for k in CALLS}
    if discover_fields:
        s, t = symbol.upper(), ("c" if statement == "consolidated" else "s")
        for k, (path, params, timeout) in DISCOVER_CALLS.items():
            wanted[k] = (path.format(s=s), {pk: pv.format(t=t) for pk, pv in params.items()}, timeout)
    payloads: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for n, (key, (path, params, timeout)) in enumerate(wanted.items()):
        if n:
            await asyncio.sleep(pause)
        try:
            payloads[key] = await client.get(path, params, timeout)
        except FinEdgeError as exc:
            errors[key] = f"HTTP {exc.status}" if exc.status else "unreachable"
    return payloads, len(wanted), errors


async def _pick(store, symbols: List[str], sample: int, seed: Optional[int]) -> List[Tuple[str, str]]:
    sql = ("SELECT DISTINCT ON (symbol) symbol, statement FROM snapshots WHERE section = 'summary' {where} "
           "ORDER BY symbol, (statement = 'consolidated') DESC")
    async with store.pool.acquire() as conn:
        if symbols:
            rows = await conn.fetch(sql.format(where="AND symbol = ANY($1::text[])"), [s.upper() for s in symbols])   # nosec B608
        else:
            rows = await conn.fetch(sql.format(where=""))   # nosec B608
    picks = [(r["symbol"], r["statement"]) for r in rows]
    if symbols:
        order = {s.upper(): i for i, s in enumerate(symbols)}
        return sorted(picks, key=lambda p: order[p[0]])
    return random.Random(seed).sample(picks, min(sample, len(picks)))


async def _sections(store, symbol: str, statement: str) -> Dict[str, dict]:
    import orjson
    out = {}
    for name in ("summary", "ratios", "financials"):
        got = await store.get_section(symbol, statement, name)
        if got:
            out[name] = orjson.loads(got[0])
    return out


async def last_result(pool) -> Optional[dict]:
    from .integrity import _meta_get
    try:
        async with pool.acquire() as conn:
            return await _meta_get(conn, META_LAST)
    except Exception:
        return None


async def run(store, client, symbols: List[str], sample: int = 3, seed: Optional[int] = None, discover_fields: bool = False, pause: float = PAUSE_SECONDS) -> dict:
    from .integrity import _meta_set
    picks = await _pick(store, symbols, sample, seed)
    companies: List[dict] = []
    calls = 0
    for sym in symbols and [s.upper() for s in symbols] or [p[0] for p in picks]:
        found = dict(picks).get(sym)
        if not found:
            companies.append({"symbol": sym, "error": "no stored report for this symbol (ingest it first)"})
            continue
        sections = await _sections(store, sym, found)
        if not sections.get("summary"):
            companies.append({"symbol": sym, "error": "stored report has no summary section"})
            continue
        payloads, n, errors = await fetch_payloads(client, sym, found, discover_fields, pause)
        calls += n
        if "quote" in errors or "profile" in errors:
            companies.append({"symbol": sym, "error": "FinEdge did not answer: " + ", ".join(f"{k} {v}" for k, v in errors.items())})
            continue
        company = compare_symbol(sym, found, payloads, sections)
        if errors:
            company["info"].append("FinEdge did not answer for: " + ", ".join(f"{k} ({v})" for k, v in errors.items()) + "; those figures read as blank on the FinEdge side")
        companies.append(company)
        await asyncio.sleep(pause)
    counts = {v: sum(c.get("counts", {}).get(v, 0) for c in companies) for v in ("match", "explained", "MISMATCH")}
    errored = [c for c in companies if c.get("error")]
    result = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "calls": calls, "companies": companies,
              "match": counts["match"], "explained": counts["explained"], "mismatches": counts["MISMATCH"] + len(errored),
              "level": "red" if counts["MISMATCH"] or errored else "green"}
    async with store.pool.acquire() as conn:
        await _meta_set(conn, META_LAST, result)
    return result
