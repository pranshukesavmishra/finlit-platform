"""The FinLit MCP tools. Each one asks the website's own public route(s) in-process, as an anonymous visitor (see gateway.py), and reshapes
nothing but the layout: the numbers are the route's. Read-only: there are no tools that write, and no tool takes a login or a watchlist."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from .gateway import Gateway, ToolError
from .schema import SYMBOL_SCHEMA, clean_symbol

IST = ZoneInfo("Asia/Kolkata")
DISCLAIMER = ("Describes the company's financial health from its filings and prices; not a recommendation. "
              "FinLit Ventures is a technology company and is not registered with SEBI or AMFI.")
SOURCE_STOCKS = "FinLit Ventures research database: company filings and exchange prices, the same figures the FinLit website shows"
MAX_BATCH = 20


@dataclass
class Out:
    data: Any
    as_of: Any = None
    source: str = SOURCE_STOCKS
    routes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


Handler = Callable[[Gateway, Dict[str, Any]], Awaitable[Out]]


@dataclass
class Tool:
    name: str
    title: str
    description: str
    properties: Dict[str, Any]
    handler: Handler
    required: List[str] = field(default_factory=list)

    def listing(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {"type": "object", "properties": self.properties, "additionalProperties": False}
        if self.required:
            schema["required"] = self.required
        return {"name": self.name, "title": self.title, "description": self.description, "inputSchema": schema,
                "annotations": {"title": self.title, "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}


# ------------------------------------------------------------------------------------------------------------- helpers
def _sym_prop(extra: str = "") -> Dict[str, Any]:
    return dict(SYMBOL_SCHEMA, description=SYMBOL_SCHEMA["description"] + extra)


async def _section(gw: Gateway, sym: str, section: str = "") -> Dict[str, Any]:
    path = f"/api/stocks/{sym}" + (f"/{section}" if section else "")
    return await gw.json(path, subject=f"The company {sym}")


def _tail(values: Any, n: int) -> Any:
    return values[-n:] if isinstance(values, list) else values


def _slim_lists(obj: Any, keep: int, hit: List[str], path: str = "") -> Any:
    """Long lists inside a detail answer (price series, NAV history) are cut to the newest `keep` entries; the cut is reported."""
    if isinstance(obj, dict):
        return {k: _slim_lists(v, keep, hit, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > keep:
            hit.append(f"{path.lstrip('.') or 'list'}: newest {keep} of {len(obj)} entries")
            obj = obj[-keep:]
        return [_slim_lists(x, keep, hit, path) for x in obj]
    return obj


def _today_ist() -> date:
    return datetime.now(IST).date()


# ------------------------------------------------------------------------------------------------------------- tools
async def search_stocks(gw: Gateway, a: Dict[str, Any]) -> Out:
    q = a["query"].strip()
    if not q:
        raise ToolError("query is empty: give a company name or symbol.")
    body = await gw.json("/api/stocks/search-index", subject="The company list")
    fields = body.get("fields") or ["symbol", "name", "bse", "ready", "nse"]
    ix = {f: i for i, f in enumerate(fields)}
    needle = q.lower()
    scored = []
    for row in body.get("rows", []):
        sym, name = str(row[ix["symbol"]]), str(row[ix["name"]])
        bse = str(row[ix["bse"]]) if "bse" in ix and len(row) > ix["bse"] else ""
        s, n = sym.lower(), name.lower()
        if s == needle or bse == needle:
            rank = 0
        elif s.startswith(needle) or n.startswith(needle):
            rank = 1
        elif any(w.startswith(needle) for w in n.replace("&", " ").split()):
            rank = 3
        elif needle in n or needle in s:
            rank = 4
        else:
            continue
        ready = bool(row[ix["ready"]]) if "ready" in ix else False
        scored.append((rank, not ready, len(sym), sym, name, bse, ready))
    scored.sort()
    items = [{"symbol": s, "name": n, "bseCode": b or None, "reportReady": r} for _, _, _, s, n, b, r in scored[: a["limit"]]]
    notes = ["reportReady false means the company is listed but FinLit has not prepared its report yet."]
    if not items:
        notes.append("No company matched. Try a shorter part of the name, or the exchange symbol.")
    return Out({"query": q, "matches": len(scored), "returned": len(items), "companies": items}, routes=["/api/stocks/search-index"], notes=notes,
               as_of=_today_ist().isoformat())


async def get_stock_quote(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    s = await _section(gw, sym)
    q = s.get("quote")
    notes = [] if q else ["No price is available for this company yet."]
    return Out({"symbol": sym, "name": (s.get("profile") or {}).get("name"), "currency": "INR", "quote": q, "range52": s.get("range52")},
               as_of=(q or {}).get("asOf") or (s.get("dataQuality") or {}).get("priceAsOf"), routes=[f"/api/stocks/{sym}"], notes=notes)


async def get_batch_quotes(gw: Gateway, a: Dict[str, Any]) -> Out:
    syms: List[str] = []
    for raw in a["symbols"]:
        sym = clean_symbol(raw, "symbols[]")
        if sym not in syms:
            syms.append(sym)
    sem = asyncio.Semaphore(4)

    async def one(sym: str) -> Dict[str, Any]:
        async with sem:
            try:
                s = await _section(gw, sym)
            except ToolError as e:
                return {"symbol": sym, "name": None, "quote": None, "error": str(e)}
            return {"symbol": sym, "name": (s.get("profile") or {}).get("name"), "quote": s.get("quote")}

    rows = await asyncio.gather(*(one(s) for s in syms))
    stamps = [r["quote"]["asOf"] for r in rows if r.get("quote") and r["quote"].get("asOf")]
    return Out({"currency": "INR", "quotes": rows}, as_of=max(stamps) if stamps else None, routes=[f"/api/stocks/{s}" for s in syms],
               notes=[] if stamps else ["No prices were available."])


async def get_company_profile(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    s = await _section(gw, sym)
    meta = s.get("meta") or {}
    return Out({"symbol": sym, "profile": s.get("profile"), "statementBasis": meta.get("statement")}, as_of=meta.get("generatedAt"),
               routes=[f"/api/stocks/{sym}"])


async def get_financials(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    period, n = a["period"], a["limit"]
    f = await _section(gw, sym, "financials")
    block = (f.get("quarterly") if period == "quarterly" else f.get("yearly")) or {}
    out: Dict[str, Any] = {}
    for code, label in (("pl", "profitAndLoss"), ("bs", "balanceSheet"), ("cf", "cashFlow")):
        st = block.get(code)
        if not st:
            continue
        out[label] = {"periods": _tail(st.get("periods"), n), "periodEnds": _tail(st.get("periodEnds"), n),
                      "rows": {k: _tail(v, n) for k, v in (st.get("rows") or {}).items()}}
    notes = ["Amounts are in the unit given (Cr = crore rupees; eps is rupees per share). null means the figure is not available for that period."]
    missing = [name for code, name in (("pl", "profit and loss"), ("bs", "balance sheet"), ("cf", "cash flow")) if not block.get(code)]
    if missing:
        notes.append(f"Not available for the {period} view: {', '.join(missing)}.")
    last = ((out.get("profitAndLoss") or {}).get("periodEnds") or [None])[-1]
    return Out({"symbol": sym, "period": period, "unit": f.get("unit"), "statementBasis": (f.get("meta") or {}).get("statement"), **out},
               as_of=last, routes=[f"/api/stocks/{sym}/financials"], notes=notes)


async def get_ratios(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    r = await _section(gw, sym, "ratios")
    latest = {k: {"label": v.get("label"), "value": v.get("value"), "unit": v.get("unit"), "period": v.get("period")} for k, v in (r.get("latest") or {}).items()}
    hist = r.get("history") or {}
    notes = list(r.get("notes") or [])
    notes.append("Only the ratios the website shows to a visitor without an account are included.")
    periods = [v["period"] for v in latest.values() if v.get("period")]
    return Out({"symbol": sym, "latest": latest, "history": {"periods": _tail(hist.get("periods"), 8), "rows": {k: _tail(v, 8) for k, v in (hist.get("rows") or {}).items()}}},
               as_of=(r.get("meta") or {}).get("generatedAt"), routes=[f"/api/stocks/{sym}/ratios"], notes=notes + ([f"Periods covered include: {sorted(set(periods))[:6]}"] if periods else []))


async def get_shareholding(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    o = await _section(gw, sym, "ownership")
    notes = [] if o.get("latest") else ["No shareholding pattern is available for this company."]
    return Out({"symbol": sym, "unit": "% of shares", "periods": o.get("periods"), "series": o.get("series"), "latest": o.get("latest"),
                "comparedWith": o.get("comparedWith")}, as_of=o.get("asOf"), routes=[f"/api/stocks/{sym}/ownership"], notes=notes)


RANGES = ((31, "1M"), (183, "6M"), (366, "1Y"), (1096, "3Y"), (1827, "5Y"))


def _weekly(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    key = None
    for r in rows:
        y, w, _ = date.fromisoformat(r["date"]).isocalendar()
        if (y, w) != key:
            key = (y, w)
            out.append(dict(r))
            continue
        cur = out[-1]
        cur["date"], cur["close"] = r["date"], r["close"]
        for f, fn in (("high", max), ("low", min)):
            if cur.get(f) is not None and r.get(f) is not None:
                cur[f] = fn(cur[f], r[f])
        if cur.get("volume") is not None and r.get("volume") is not None:
            cur["volume"] += r["volume"]
    return out


async def get_price_history(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym, days, interval = clean_symbol(a["symbol"]), a["days"], a["interval"]
    rng = next((name for limit, name in RANGES if days <= limit), "5Y")
    p = await _section(gw, sym, f"price-{rng}")
    s = p.get("series") or {}
    ts = s.get("t") or []
    if not ts:
        raise ToolError(f"No price history is stored for {sym}.")
    cut = (date.fromisoformat(ts[-1]) - timedelta(days=days)).isoformat()
    rows = []
    for i, t in enumerate(ts):
        if t < cut:
            continue
        rows.append({"date": t, **{name: (s[key][i] if key in s and i < len(s[key]) else None)
                                   for name, key in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}})
    notes = []
    grain = p.get("grain")
    if grain == "weekly" and interval == "daily":
        notes.append("Beyond about one year the website stores weekly closes only, so daily prices are not available for this span; weekly closes are returned.")
        interval = "weekly"
    elif interval == "weekly" and grain == "daily":
        rows = _weekly(rows)
        notes.append("Weekly rows are worked out from the daily prices: first open, highest high, lowest low, last close, summed volume; dated by the last trading day of the week.")
    if grain == "weekly":
        notes.append("open, high and low are null for weekly history: only the closing price and volume are stored.")
    if p.get("provisionalLastBar"):
        notes.append("The last row may be provisional (the day's trading is not final).")
    if p.get("complete") is False:
        notes.append(f"Stored history starts {p.get('startsAt') or 'later'} and does not cover the whole span asked for.")
    return Out({"symbol": sym, "currency": "INR", "interval": interval, "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None,
                "count": len(rows), "prices": rows}, as_of=ts[-1], routes=[f"/api/stocks/{sym}/price-{rng}"], notes=notes)


async def get_finlit_score(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    s = await _section(gw, sym)
    sc = s.get("score") or {}
    asof = (s.get("meta") or {}).get("generatedAt")
    if sc.get("overall") is None:
        return Out({"symbol": sym, "locked": True, "score": None,
                    "message": "The FinLit score for this company is a Silver plan feature on the FinLit website and is not available through this free server."},
                   as_of=asof, routes=[f"/api/stocks/{sym}"])
    return Out({"symbol": sym, "locked": False, "score": {"overall": sc.get("overall"), "scale": "0 to 100", "band": sc.get("band"), "model": sc.get("model"),
                                                           "pillars": [{k: p.get(k) for k in ("key", "label", "score", "band")} for p in sc.get("pillars", [])]}},
               as_of=asof, routes=[f"/api/stocks/{sym}"],
               notes=["The score and its bands describe financial health from filings and prices. They are computed mechanically and are not a recommendation."])


def _results_params(a: Dict[str, Any], limit: int) -> Dict[str, Any]:
    p: Dict[str, Any] = {"limit": limit}
    for k, dst in (("quarter", "quarter"), ("date", "date"), ("sector", "sector"), ("status", "status")):
        if a.get(k):
            p[dst] = a[k]
    return p


def _results_out(b: Dict[str, Any], path: str, extra_notes: Optional[List[str]] = None) -> Out:
    notes = list(extra_notes or [])
    if b.get("locked"):
        notes.append("Growth and margin figures for these results are a Silver feature on the website, so rows here carry dates, names and status only; figures are null because they are withheld, not because they are zero.")
    if not b.get("quarter"):
        notes.append("No quarter with declarations is loaded yet.")
    rows = [{k: r.get(k) for k in ("symbol", "name", "sector", "cap", "date", "status", "periodEnd", "hasNumbers", "revenue", "netProfit", "revenueYoY", "profitYoY") if k in r} for r in b.get("rows", [])]
    return Out({"quarter": (b.get("quarter") or {}).get("key") if isinstance(b.get("quarter"), dict) else b.get("quarter"),
                "quarterLabel": (b.get("quarter") or {}).get("label") if isinstance(b.get("quarter"), dict) else None,
                "total": b.get("total"), "returned": len(rows), "summary": {k: (b.get("summary") or {}).get(k) for k in ("companies", "declared", "due", "awaiting")},
                "dateMeaning": b.get("dateMeaning"), "rows": rows}, as_of=b.get("updatedAt") or b.get("today"), routes=[path], notes=notes)


async def get_quarter_results(gw: Gateway, a: Dict[str, Any]) -> Out:
    if a.get("date") and a.get("quarter"):
        raise ToolError("Give either date or quarter, not both.")
    b = await gw.json("/api/results/quarter", _results_params(a, a["limit"]), subject="Quarter results")
    return _results_out(b, "/api/results/quarter")


async def get_results_calendar(gw: Gateway, a: Dict[str, Any]) -> Out:
    today = _today_ist()
    last = (today + timedelta(days=a["days"])).isoformat()
    b = await gw.json("/api/results/quarter", {"status": "due", "sort": "date", "dir": "asc", "limit": 100}, subject="The results calendar")
    b = dict(b, rows=[r for r in b.get("rows", []) if today.isoformat() <= str(r.get("date")) <= last])
    return _results_out(b, "/api/results/quarter", [f"Companies with a result date from {today.isoformat()} to {last}, soonest first (at most 100). A date taken from the board-meeting calendar can move until the company files."])


async def screen_stocks(gw: Gateway, a: Dict[str, Any]) -> Out:
    filters = {k: {kk: vv for kk, vv in v.items() if kk in ("min", "max") and vv is not None} for k, v in (a.get("filters") or {}).items()}
    filters = {k: v for k, v in filters.items() if v}
    cats: Dict[str, Any] = {}
    for k in ("sector", "cap", "index"):
        if a.get(k):
            cats[k] = [a[k]] if isinstance(a[k], str) else a[k]
    body = {"filters": filters, "cats": cats, "q": a.get("query", ""), "sort": {"key": a["sort_by"], "dir": a["order"]},
            "columns": list(dict.fromkeys(["market_cap", "price", *filters, *([a["sort_by"]] if a["sort_by"] not in ("name", "symbol") else [])])),
            "limit": a["limit"]}
    r = await gw.json("/api/screener/query", method="POST", body=body, subject="The screener")
    notes = ["Only the filters the free FinLit screener offers are available. Values are in the units named in the filter list."]
    if r.get("capped"):
        notes.append(f"The free screener shows at most {r.get('limit')} rows; {r.get('total')} companies matched.")
    rows = [{"symbol": x.get("symbol"), "name": x.get("name"), "sector": x.get("sector"), "size": x.get("cap"), "values": x.get("v")} for x in r.get("rows", [])]
    return Out({"matched": r.get("total"), "returned": len(rows), "columns": r.get("columns"), "rows": rows}, as_of=_today_ist().isoformat(),
               routes=["/api/screener/query"], notes=notes)


async def get_market_overview(gw: Gateway, a: Dict[str, Any]) -> Out:
    notes: List[str] = []
    headline = sectors = macro = None
    ix_asof = None
    pick = ("code", "name", "close", "changePct", "points", "pe", "pb", "divYield")
    try:
        ix = await gw.json("/api/indices", subject="Index levels")
        items = ix.get("items", [])
        keys = ix.get("key") or []
        headline = [{k: i.get(k) for k in pick} for i in items if i.get("code") in keys]
        sectors = [{k: i.get(k) for k in pick} for i in items if i.get("group") == "Sector" and i.get("code") not in keys]
        ix_asof = ix.get("asOf") or max([i["date"] for i in items if i.get("date")], default=None)
        notes.append(f"{len(items)} indices exist; the headline indices and the sector indices are returned. pe, pb and divYield are null where the index provider gives none.")
        if not ix.get("live"):
            notes.append("Index levels are the last close, not live prices.")
    except ToolError as e:
        notes.append(f"Index levels unavailable: {e}")
    try:
        m = await gw.json("/api/macro", subject="Economy figures")
        macro = [{k: c.get(k) for k in ("key", "label", "value", "unit", "period", "date", "prev", "prevPeriod", "change", "changeUnit", "yearAgo", "source")} for c in m.get("cards", [])]
    except ToolError as e:
        notes.append(f"India economy figures unavailable: {e}")
    if headline is None and macro is None:
        raise ToolError("Market data is not available right now.")
    return Out({"indices": headline, "sectorIndices": sectors, "economy": macro},
               as_of={"indices": ix_asof, "economy": max([c["date"] for c in (macro or []) if c.get("date")], default=None)},
               source="FinLit Ventures: index data from the data provider; economy figures from MoSPI, RBI and other official publishers (named on each item)",
               routes=["/api/indices", "/api/macro"], notes=notes)


async def get_fii_dii_flows(gw: Gateway, a: Dict[str, Any]) -> Out:
    f = await gw.json("/api/flows", subject="Institutional flows")
    days = _tail(f.get("days") or [], a["days"])
    notes = ["Rs crore, cash market. NSDL's daily figures are provisional and are revised."]
    if not days:
        notes.append("No daily flow figures are loaded right now.")
    return Out({"unit": "Rs crore", "latest": f.get("latest"), "last30": f.get("last30"), "days": days,
                "sources": [{k: s.get(k) for k in ("label", "status", "lastDate")} for s in f.get("sources", [])]},
               as_of=(f.get("latest") or {}).get("d") or f.get("updatedAt"), source="NSDL FPI Monitor and NSE archives, as shown on the FinLit flows page",
               routes=["/api/flows"], notes=notes)


async def get_ipo_calendar(gw: Gateway, a: Dict[str, Any]) -> Out:
    b = await gw.json("/api/ipos", subject="The IPO list")
    rows = [i for i in b.get("ipos", []) if a["status"] == "all" or i.get("status") == a["status"]]
    rows = rows[: a["limit"]]
    notes = ["Status is worked out from the issue's open, close and listing dates in India time."]
    if not rows:
        notes.append("No issues are listed for that status.")
    return Out({"status": a["status"], "returned": len(rows), "ipos": rows}, as_of=_today_ist().isoformat(), source="FinLit Ventures IPO list (entered by FinLit from issue documents)",
               routes=["/api/ipos"], notes=notes)


async def search_funds(gw: Gateway, a: Dict[str, Any]) -> Out:
    q = a["query"].strip()
    if not q:
        raise ToolError("query is empty: give part of a fund name.")
    b = await gw.json("/api/mf", {"q": q, "size": a["limit"]}, subject="Mutual funds")
    items = [{k: i.get(k) for k in ("code", "name", "amc", "category", "plan", "optionClass", "nav", "navDate", "r1y", "r3y", "r5y", "aum", "ter")} for i in (b.get("items") or [])[: a["limit"]]]
    return Out({"query": q, "total": b.get("total"), "returned": len(items), "funds": items}, as_of=b.get("dataDate"), source=b.get("source") or "AMFI",
               routes=["/api/mf"], notes=["Returns are the fund's own past performance as computed by FinLit from AMFI NAVs; null means not available.", b.get("disclaimer") or ""])


async def get_fund_details(gw: Gateway, a: Dict[str, Any]) -> Out:
    code = a["code"]
    b = await gw.json(f"/api/mf/{code}", subject=f"The fund {code}")
    hit: List[str] = []
    b = _slim_lists(b, 60, hit)
    asof = (b.get("dataDate") or b.get("navDate") or (b.get("fund") or {}).get("navDate")) if isinstance(b, dict) else None
    return Out(b, as_of=asof, source="AMFI (Association of Mutual Funds in India), official NAV files, as shown on FinLit",
               routes=[f"/api/mf/{code}"], notes=[f"Long series are cut: {', '.join(hit)}."] if hit else [])


async def list_etfs(gw: Gateway, a: Dict[str, Any]) -> Out:
    params: Dict[str, Any] = {"limit": a["limit"]}
    if a.get("query"):
        params["q"] = a["query"]
    b = await gw.json("/api/etf", params, subject="ETFs")
    items = [{k: i.get(k) for k in ("symbol", "name", "fundHouse", "categoryLabel", "assetClass", "price", "changePct", "priceDate", "nav", "navDate", "premium", "ret1y", "cagr3y", "high52", "low52")} for i in b.get("items", [])]
    return Out({"total": b.get("total"), "returned": len(items), "etfs": items}, as_of=b.get("asOf"), source="Exchange prices and fund-house data, as shown on the FinLit ETF page",
               routes=["/api/etf"], notes=["null means the figure is not available."])


async def get_etf(gw: Gateway, a: Dict[str, Any]) -> Out:
    sym = clean_symbol(a["symbol"])
    b = await gw.json(f"/api/etf/{sym}", subject=f"The ETF {sym}")
    hit: List[str] = []
    b = _slim_lists(b, 60, hit)
    asof = None
    if isinstance(b, dict):
        asof = b.get("asOf") or b.get("priceDate") or (b.get("etf") or {}).get("priceDate")
    return Out(b, as_of=asof, source="Exchange prices and fund-house data, as shown on the FinLit ETF page", routes=[f"/api/etf/{sym}"],
               notes=[f"Long series are cut: {', '.join(hit)}."] if hit else [])


async def get_data_freshness(gw: Gateway, a: Dict[str, Any]) -> Out:
    parts: Dict[str, Any] = {}
    routes: List[str] = []
    if a.get("symbol"):
        sym = clean_symbol(a["symbol"])
        try:
            s = await _section(gw, sym)
            dq = s.get("dataQuality") or {}
            parts["company"] = {"symbol": sym, "reportBuilt": (s.get("meta") or {}).get("generatedAt"), "priceAsOf": (s.get("quote") or {}).get("asOf") or dq.get("priceAsOf"),
                                "fundamentalsAsOf": dq.get("fundamentalsAsOf")}
        except ToolError as e:
            parts["company"] = {"symbol": sym, "error": str(e)}
        routes.append(f"/api/stocks/{sym}")
    checks = (("indices", "/api/indices", lambda b: max([i["date"] for i in b.get("items", []) if i.get("date")], default=None)),
              ("fiiDiiFlows", "/api/flows", lambda b: (b.get("latest") or {}).get("d")),
              ("mutualFunds", "/api/mf?size=1", lambda b: b.get("dataDate")),
              ("etfs", "/api/etf?limit=1", lambda b: b.get("asOf")),
              ("economy", "/api/macro", lambda b: max([c["date"] for c in b.get("cards", []) if c.get("date")], default=None)))
    for key, path, pick in checks:
        base, _, qs = path.partition("?")
        try:
            b = await gw.json(base, dict(x.split("=") for x in qs.split("&")) if qs else None, subject=key)
            parts[key] = {"latestDataDate": pick(b)}
        except ToolError as e:
            parts[key] = {"latestDataDate": None, "error": str(e)}
        routes.append(base)
    return Out({"today": _today_ist().isoformat(), "datasets": parts}, as_of=_today_ist().isoformat(), routes=routes,
               notes=["Dates are the newest data point each dataset holds. Prices can lag the market; filings arrive after companies publish them."])


# ------------------------------------------------------------------------------------------------------------- registry
def _basic_filter_keys() -> List[str]:
    from ..screener.catalog import CATALOG, HIDDEN
    return [m.key for m in CATALOG if m.tier == "basic" and m.key not in HIDDEN]


def build_tools() -> List[Tool]:
    keys = _basic_filter_keys()
    lim = lambda default, hi, text="How many to return": {"type": "integer", "minimum": 1, "maximum": hi, "default": default, "description": text}  # noqa: E731
    sym = {"symbol": _sym_prop()}
    return [
        Tool("search_stocks", "Search companies", "Find listed Indian companies by name or symbol. Returns symbol, name and BSE code. Use this first when you only know a company name.",
             {"query": {"type": "string", "maxLength": 60, "description": "Part of a company name, or an NSE/BSE symbol"}, "limit": lim(10, 25)}, search_stocks, ["query"]),
        Tool("get_stock_quote", "Stock quote", "Latest price, day change, day range, 52-week range, volume and market cap of one company, with the time of the price.", sym, get_stock_quote, ["symbol"]),
        Tool("get_batch_quotes", "Quotes for several stocks", f"Latest prices for up to {MAX_BATCH} companies in one call. A company without data comes back with an error text and no price.",
             {"symbols": {"type": "array", "items": _sym_prop(), "minItems": 1, "maxItems": MAX_BATCH, "description": f"Up to {MAX_BATCH} NSE symbols"}}, get_batch_quotes, ["symbols"]),
        Tool("get_company_profile", "Company profile", "Name, sector, industry, website, employees, market capitalisation and business description of one company.", sym, get_company_profile, ["symbol"]),
        Tool("get_financials", "Financial statements", "Profit and loss, balance sheet and cash flow rows for one company, quarterly or annual (the quarterly view has the profit and loss only). Amounts in crore rupees.",
             {**sym, "period": {"type": "string", "enum": ["quarterly", "annual"], "default": "annual", "description": "quarterly or annual"},
              "limit": lim(8, 20, "How many of the latest periods to return")}, get_financials, ["symbol"]),
        Tool("get_ratios", "Financial ratios", "Margins, returns (ROE, ROCE) and the other ratios the FinLit website shows to a visitor, with the period each one is for, plus a short history.", sym, get_ratios, ["symbol"]),
        Tool("get_shareholding", "Shareholding pattern", "Share of promoters, foreign institutions, domestic institutions, government and the public over recent quarters.", sym, get_shareholding, ["symbol"]),
        Tool("get_price_history", "Price history", "Daily or weekly open, high, low, close and volume. Beyond about one year only weekly closes are stored.",
             {**sym, "days": {"type": "integer", "minimum": 5, "maximum": 1825, "default": 90, "description": "How many calendar days back, up to 1825"},
              "interval": {"type": "string", "enum": ["daily", "weekly"], "default": "daily", "description": "daily or weekly"}}, get_price_history, ["symbol"]),
        Tool("get_finlit_score", "FinLit score", "The FinLit financial-health score (0 to 100) and its five pillars, only where the website shows it to a visitor. Otherwise it says the score is a Silver plan feature.", sym, get_finlit_score, ["symbol"]),
        Tool("get_quarter_results", "Quarter results", "Companies that announced results for a quarter or on a date, with status. Figures such as growth are withheld, as on the free website.",
             {"quarter": {"type": "string", "pattern": r"^\d{4}-(03|06|09|12)$", "maxLength": 7, "description": "Quarter-end month, for example 2026-09"},
              "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$", "maxLength": 10, "description": "Announcement date, YYYY-MM-DD"},
              "sector": {"type": "string", "maxLength": 80, "description": "Sector name, for example Banks"},
              "limit": lim(25, 100)}, get_quarter_results),
        Tool("get_results_calendar", "Results calendar", "Companies due to announce quarterly results in the next few days, soonest first.",
             {"days": {"type": "integer", "minimum": 1, "maximum": 60, "default": 7, "description": "How many days ahead"}}, get_results_calendar),
        Tool("screen_stocks", "Stock screener", "Filter listed companies on the free FinLit screener metrics (market cap, price, P/E, ROE, ROCE, margins, growth, debt, returns). Each filter is {min, max} in the metric's unit.",
             {"filters": {"type": "object", "propertyNames": {"enum": keys}, "additionalProperties": {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}}, "additionalProperties": False},
                          "description": "Metric name to {min, max}. Metrics: " + ", ".join(keys)},
              "sector": {"type": "string", "maxLength": 80, "description": "Sector name"}, "cap": {"type": "string", "enum": ["Large", "Mid", "Small"], "description": "Company size"},
              "query": {"type": "string", "maxLength": 60, "description": "Part of a name or symbol"},
              "sort_by": {"type": "string", "enum": ["market_cap", "price", "pe", "roe", "roce", "name", "symbol", *[k for k in keys if k not in ("market_cap", "price", "pe", "roe", "roce")]], "default": "market_cap"},
              "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"}, "limit": lim(10, 25, "How many rows (the free screener shows at most 25)")}, screen_stocks),
        Tool("get_market_overview", "Market overview", "Index levels and day change (Nifty, Sensex, sector indices) with their P/E and P/B, and the India economy headline figures (inflation, GDP, and others) the website shows.", {}, get_market_overview),
        Tool("get_fii_dii_flows", "FII and DII flows", "Daily net buying and selling by foreign (FII) and domestic (DII) institutions in the cash market, in Rs crore.",
             {"days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 10, "description": "How many recent sessions"}}, get_fii_dii_flows),
        Tool("get_ipo_calendar", "IPO calendar", "Upcoming, open, closed and listed public issues with price band, dates and issue size.",
             {"status": {"type": "string", "enum": ["upcoming", "open", "closed", "listed", "all"], "default": "all", "description": "Which issues"}, "limit": lim(20, 50)}, get_ipo_calendar),
        Tool("search_funds", "Search mutual funds", "Find mutual fund schemes by name. Returns code, fund house, category, NAV and returns.",
             {"query": {"type": "string", "maxLength": 60, "description": "Part of a scheme name"}, "limit": lim(10, 25)}, search_funds, ["query"]),
        Tool("get_fund_details", "Mutual fund details", "One scheme in full: NAV, returns, fees, size, and the facts FinLit shows. Use the code from search_funds.",
             {"code": {"type": "integer", "minimum": 1, "maximum": 9999999, "description": "AMFI scheme code from search_funds"}}, get_fund_details, ["code"]),
        Tool("list_etfs", "List ETFs", "Exchange-traded funds listed on NSE with price, NAV, premium and returns.",
             {"query": {"type": "string", "maxLength": 60, "description": "Part of an ETF name or symbol"}, "limit": lim(20, 50)}, list_etfs),
        Tool("get_etf", "ETF details", "One ETF in full: price, NAV, premium or discount, returns, risk figures and recent history.", sym, get_etf, ["symbol"]),
        Tool("get_data_freshness", "Data freshness", "The date of the newest data held for prices, flows, funds, ETFs and economy figures, and optionally for one company.",
             {"symbol": _sym_prop(" (optional)")}, get_data_freshness),
    ]


TOOLS: List[Tool] = build_tools()
BY_NAME: Dict[str, Tool] = {t.name: t for t in TOOLS}
