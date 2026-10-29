"""POST /api/portfolio/overview: one bulk read for the My portfolio page (Silver and Gold).

For up to 500 symbols it returns, per company, only the few figures the page's Overview, Ratios and Financials tabs list, taken straight from the
stored report sections (summary, ratios, financials: jsonb paths, so no whole report leaves the database) and from the newest FinLit Prism rating
(prism_reports.card, Gold only). Three queries in all, whatever the number of companies. Nothing is computed here that the stock page does not show,
except the tax ratio (tax over profit before tax, from two rows of the same yearly statement, and only when both exist).

Plan rules, applied here and never left to the page:
  Silver  the basic FinLit score block (overall, band and the five pillars); no Prism field at all.
  Gold    FinLit Prism only (rating, the four parts and the two technical readings); no FinLit score block at all.
  Basic   refused (403 plan_required), as the other member tools are.
A company with no stored report is `status: "preparing"` (and is queued for building, within the same per-visitor and total limits as opening its
page) or `status: "unknown"` (not a company FinLit lists), each with a reason. A blank figure carries the reason in `why`.
Information only, not investment advice.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

import orjson
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from .auth.entitlements import has
from .auth.routes import SYMBOL, Ctx, fail, ip_of, secure_ctx
from .prism_screen import PARTS
from .technical_wording import rating_word

router = APIRouter(prefix="/api/portfolio")
MAX_SYMBOLS = 500
CACHE_SECONDS = 60
QUEUE_PER_CALL = 12            # the page used to start 12 at a time; the rest follow on its next poll
VERSION = 1                    # bump when the shape changes (part of the cache key)
DISCLAIMER = "Information only, not investment advice."

RATIO_KEYS = ("pe", "pb", "roe", "dividend_yield", "debt_to_equity", "market_cap")
PL_ROWS = ("revenue", "other_income", "operating_profit", "finance_costs", "profit_before_tax", "tax", "net_profit", "eps")
PILLARS = ("quality", "growth", "profitability", "balance", "technical")
BAND_WORD = {"strong": "Strong", "healthy": "Healthy", "mixed": "Mixed", "watch": "Watch"}


class OverviewIn(BaseModel):
    symbols: List[str] = Field(default_factory=list)


def _obj(pairs: List[str], base: str) -> str:
    """SQL: jsonb_build_object of the listed keys, each read from `base`.<key> (constant names only, never request values)."""
    return "jsonb_build_object(" + ", ".join(f"'{k}', j #> '{{{base},{k}}}'" for k in pairs) + ")"


_SNAP_SQL = (
    "WITH pick AS (SELECT DISTINCT ON (symbol) symbol, statement FROM snapshots WHERE symbol = ANY($1::text[]) AND section = 'summary' "  # nosec B608 - constant names only; symbols are bound
    "ORDER BY symbol, (statement = 'consolidated') DESC) "
    "SELECT p.symbol, p.statement, s.section, "
    "CASE s.section "
    "WHEN 'summary' THEN jsonb_build_object('quote', j #> '{quote}', "
    "'profile', jsonb_build_object('name', j #> '{profile,name}', 'sector', j #> '{profile,sector}', 'industry', j #> '{profile,industry}', "
    "'subIndustry', j #> '{profile,subIndustry}', 'marketCapCr', j #> '{profile,marketCapCr}'), "
    "'isBank', j #> '{dataQuality,isBank}', 'chosen', j #> '{dataQuality,basis,chosen}', 'statement', j #> '{meta,statement}', "
    "'generatedAt', j #> '{meta,generatedAt}', 'score', CASE WHEN $2::boolean THEN j #> '{score}' END) "
    "WHEN 'ratios' THEN jsonb_build_object('latest', " + _obj(list(RATIO_KEYS), "latest") + ", 'blanks', j #> '{blanks}') "
    "WHEN 'financials' THEN jsonb_build_object('yearly', jsonb_build_object('periods', j #> '{yearly,pl,periods}', 'ends', j #> '{yearly,pl,periodEnds}', "
    "'rows', " + _obj(list(PL_ROWS), "yearly,pl,rows") + ", 'equity', j #> '{yearly,bs,rows,total_equity}'), "
    "'quarterly', jsonb_build_object('periods', j #> '{quarterly,pl,periods}', 'ends', j #> '{quarterly,pl,periodEnds}', "
    "'rows', " + _obj(list(PL_ROWS), "quarterly,pl,rows") + ")) END AS part "
    "FROM pick p JOIN snapshots s ON s.symbol = p.symbol AND s.statement = p.statement AND s.section IN ('summary', 'ratios', 'financials') "
    "CROSS JOIN LATERAL (SELECT s.body::jsonb AS j) x")

_PRISM_SQL = ("SELECT DISTINCT ON (symbol) symbol, final, label, status, generated_at, card, "
              "CASE WHEN status = 'NOT RATED' THEN report #> '{rating,notRatedReasons}' END AS reasons "
              "FROM prism_reports WHERE symbol = ANY($1::text[]) ORDER BY symbol, (statement = 'consolidated') DESC, generated_at DESC")


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") else None


def _load(v: Any) -> Any:
    return orjson.loads(v) if isinstance(v, (str, bytes)) else v


def clean_symbols(raw: List[str]) -> List[str]:
    """Upper-case, de-duplicated (order kept) symbols; anything that is not a stock symbol is a 400 (so a bad list is never half answered)."""
    out: List[str] = []
    for s in raw:
        sym = str(s).strip().upper()
        if not SYMBOL.match(sym):
            raise fail(400, "invalid_symbol", "That is not a stock symbol.")
        if sym not in out:
            out.append(sym)
    return out


# ---------------------------------------------------------------------------------------------------------- one company

def _ratio(sym_ratios: Dict[str, Any], key: str, lender: bool, equity: Optional[float], net_profit: Optional[float], label: str) -> Dict[str, Any]:
    """{value, period, note} for a ratio the stock page shows, or {value: None, why} with the reason in plain words."""
    entry = (sym_ratios.get("latest") or {}).get(key)
    value = _num((entry or {}).get("value")) if isinstance(entry, dict) else None
    if value is not None:
        out = {"value": value, "period": entry.get("period")}
        if entry.get("note"):
            out["note"] = entry["note"]
        return out
    blanks = sym_ratios.get("blanks") or {}
    if key in ("debt_to_equity",) and lender:
        why = "Not applicable to banks and lenders: their debt is their raw material."
    elif key in ("roe", "debt_to_equity", "pb") and equity is not None and equity <= 0:
        why = f"{label} is not shown because shareholders' equity is zero or negative."
    elif key == "pe" and net_profit is not None and net_profit <= 0:
        why = "Loss-making: the latest full year's net profit is zero or negative, so P/E is not meaningful."
    elif blanks.get(key):
        why = blanks[key]
    else:
        why = f"{label} is not in this company's report (the data provider sent none)."
    return {"value": None, "why": why}


def _statement(table: Dict[str, Any], lender: bool) -> Dict[str, Any]:
    """The newest column of a yearly or quarterly P&L as the Financials tab's fields, each {value, why}."""
    periods = table.get("periods") or []
    if not periods:
        return {"period": None, "periodEnd": None, "available": False, "why": "No profit and loss statement is stored for this company yet."}
    i = len(periods) - 1
    rows = table.get("rows") or {}

    def get(name: str) -> Optional[float]:
        r = rows.get(name)
        return _num(r[i]) if isinstance(r, list) and i < len(r) else None
    ends = table.get("ends") or []
    out: Dict[str, Any] = {"period": periods[i], "periodEnd": ends[i] if i < len(ends) else None, "available": True}
    labels = {"revenue": "Net sales", "other_income": "Other income", "operating_profit": "Operating profit", "finance_costs": "Interest paid",
              "net_profit": "Net profit", "eps": "EPS"}
    for name, label in labels.items():
        v = get(name)
        if name == "operating_profit" and lender:
            out[name] = {"value": None, "why": "Not applicable to banks and lenders: their interest is their business, so there is no operating profit."}
        elif v is None:
            out[name] = {"value": None, "why": f"{label} is not in the {periods[i]} statement."}
        else:
            out[name] = {"value": v}
    pbt, tax = get("profit_before_tax"), get("tax")
    if pbt is not None and tax is not None and pbt > 0:
        out["tax_ratio"] = {"value": round(tax / pbt * 100, 2), "note": "Tax divided by profit before tax, from the same statement."}
    elif pbt is not None and tax is not None:
        out["tax_ratio"] = {"value": None, "why": "Profit before tax is zero or negative, so a tax ratio is not meaningful."}
    else:
        out["tax_ratio"] = {"value": None, "why": f"Tax or profit before tax is not in the {periods[i]} statement."}
    return out


def _finlit(score: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    score = score or {}
    overall = _num(score.get("overall"))
    band = (score.get("band") or {}).get("key") if isinstance(score.get("band"), dict) else None
    pillars = {p.get("key"): _num(p.get("score")) for p in score.get("pillars") or [] if isinstance(p, dict)}
    return {"overall": overall, "band": band if overall is not None else None, "word": BAND_WORD.get(band) if overall is not None else None,
            "pillars": {k: pillars.get(k) for k in PILLARS}}


def prism_block(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The Prism part of a holding. state: 'rated' | 'provisional' | 'not_rated' (the model looked and declined: `reason` says why) | 'none' (no stored rating)."""
    if not row:
        return {"state": "none", "final": None, "label": None, "status": None, "parts": None, "shortTerm": None, "longTerm": None, "at": None, "reason": None}
    card = _load(row.get("card")) or {}
    status, final = row.get("status"), _num(row.get("final"))
    state = "not_rated" if status == "NOT RATED" or final is None else "provisional" if status == "PROVISIONAL" else "rated"
    parts = card.get("parts") if isinstance(card.get("parts"), dict) else {}
    reasons = _load(row.get("reasons")) or []
    reason = next((r.get("text") for r in reasons if isinstance(r, dict) and r.get("text")), None) if state == "not_rated" else None
    if state == "not_rated" and not reason:
        reason = "Prism could not rate this company: its filed history or data is not enough for a rating."

    def horizon(key: str) -> Optional[Dict[str, Any]]:
        h = card.get(key) if isinstance(card.get(key), dict) else {}
        score = _num(h.get("score"))
        return {"score": round(score, 1), "word": rating_word(h.get("rating"), score)} if score is not None else None
    return {"state": state, "final": final, "label": row.get("label"), "status": status,
            "parts": {k: _num(parts.get(k)) for k in PARTS} if state != "not_rated" else None,
            "shortTerm": horizon("st"), "longTerm": horizon("lt"),
            "at": row["generated_at"].date().isoformat() if row.get("generated_at") else None, "reason": reason}


def holding(sym: str, parts: Dict[str, Any], prism: Optional[Dict[str, Any]], gold: bool) -> Dict[str, Any]:
    """One stored company as the page's row. `prism` is read only for Gold, and the FinLit score block only for Silver."""
    s, r, f = parts.get("summary") or {}, parts.get("ratios") or {}, parts.get("financials") or {}
    prof, quote = s.get("profile") or {}, s.get("quote") or {}
    lender = bool(s.get("isBank"))
    yearly = f.get("yearly") or {}
    yrows = yearly.get("rows") or {}
    profit = [v for v in (yrows.get("net_profit") or []) if v is not None]
    net_profit = _num(profit[-1]) if profit else None
    equity_rows = [v for v in (yearly.get("equity") or []) if v is not None]
    equity = _num(equity_rows[-1]) if equity_rows else None
    labels = {"pe": "P/E", "pb": "P/B", "roe": "ROE", "dividend_yield": "Dividend yield", "debt_to_equity": "Debt to equity", "market_cap": "Market cap"}
    cap = _num(prof.get("marketCapCr")) or _num(quote.get("marketCapCr"))
    basis = s.get("chosen") or s.get("statement")
    out: Dict[str, Any] = {
        "symbol": sym, "status": "ready", "name": prof.get("name"), "sector": prof.get("sector"), "industry": prof.get("industry") or prof.get("subIndustry"),
        "isBank": lender, "basis": basis if basis in ("consolidated", "standalone") else None, "reportAt": s.get("generatedAt"),
        "price": _num(quote.get("price")), "changePct": _num(quote.get("changePct")), "priceAsOf": quote.get("asOf"), "marketCapCr": cap,
        "ratios": {k: _ratio(r, k, lender, equity, net_profit, labels[k]) for k in RATIO_KEYS if k != "market_cap"},
        "financials": {"year": _statement(yearly, lender), "quarter": _statement(f.get("quarterly") or {}, lender)},
    }
    if gold:
        out["prism"] = prism_block(prism)
    else:
        out["finlit"] = _finlit(s.get("score"))
    return out


# ---------------------------------------------------------------------------------------------------------- the route

async def member_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "silver"):
        raise fail(403, "plan_required", "My portfolio scores are part of the Silver plan.", plan="silver")
    return ctx


async def _queue(request: Request, missing: List[str]) -> Dict[str, str]:
    """Queue the report build for companies we list but have not stored (same guards as opening a stock page). Returns each one's reason."""
    store, settings = request.app.state.store, request.app.state.settings
    listed = {r["symbol"] for r in await store.pool.fetch("SELECT symbol FROM companies WHERE symbol = ANY($1::text[])", missing)}
    why: Dict[str, str] = {}
    started = 0
    for sym in missing:
        if sym not in listed:
            why[sym] = ""
            continue
        why[sym] = "Its report is being prepared. This takes about a minute the first time."
        if started >= QUEUE_PER_CALL:
            continue
        try:
            if not await store.redis.set(f"pending:{sym}:consolidated", 1, nx=True, ex=300):
                continue                      # already being prepared: this ask must not use up the allowance
            allowed, _ = await request.app.state.limiter.hit("queue", ip_of(request), settings.queue_limit_per_hour, 3600, fail_open=False)
            if not allowed or await store.queue_length() >= settings.queue_max_pending:
                await store.redis.delete(f"pending:{sym}:consolidated")
                why[sym] = "Preparation is busy right now; it will be retried the next time this page refreshes."
                continue
            await store.enqueue(sym, "consolidated")
            started += 1
        except Exception:
            why[sym] = "Preparation could not be started right now; it will be retried the next time this page refreshes."
    return why


@router.post("/overview")
async def overview(request: Request, body: OverviewIn, ctx: Ctx = Depends(member_ctx)):
    if len(body.symbols) > MAX_SYMBOLS:
        raise fail(400, "too_many", f"Send at most {MAX_SYMBOLS} symbols at a time.")
    symbols = clean_symbols(body.symbols)
    gold = ctx.role == "admin" or has(ctx.plan, "gold")
    store = request.app.state.store
    key = f"pfo:{VERSION}:{'gold' if gold else 'silver'}:{hashlib.sha1('|'.join(sorted(symbols)).encode()).hexdigest()}"  # nosec B324 - cache key
    headers = {"Cache-Control": "private, no-store", "Vary": "Cookie"}
    try:
        hit = await store.redis.get(key)
    except Exception:
        hit = None
    if hit is not None:
        return Response(content=hit, media_type="application/json", headers=headers)

    parts: Dict[str, Dict[str, Any]] = {}
    if symbols:
        for r in await store.pool.fetch(_SNAP_SQL, symbols, not gold):
            parts.setdefault(r["symbol"], {})[r["section"]] = _load(r["part"])
    prism_rows = {r["symbol"]: dict(r) for r in await store.pool.fetch(_PRISM_SQL, symbols)} if gold and symbols else {}
    ready = [s for s in symbols if (parts.get(s) or {}).get("summary")]
    missing = [s for s in symbols if s not in ready]
    why = await _queue(request, missing) if missing else {}

    rows: List[Dict[str, Any]] = []
    for s in symbols:
        if s in ready:
            rows.append(holding(s, parts[s], prism_rows.get(s), gold))
        elif why.get(s):
            rows.append({"symbol": s, "status": "preparing", "reason": why[s]})
        else:
            rows.append({"symbol": s, "status": "unknown", "reason": "FinLit does not list a company with this symbol, so there is no report to read."})
    payload = orjson.dumps({"model": "prism" if gold else "finlit", "plan": "gold" if gold else "silver", "count": len(rows), "holdings": rows,
                            "disclaimer": DISCLAIMER})
    if not missing:      # a list with companies still being prepared is asked again soon, so it is not kept
        try:
            await store.redis.set(key, payload, ex=CACHE_SECONDS)
        except Exception:
            pass
    return Response(content=payload, media_type="application/json", headers=headers)
