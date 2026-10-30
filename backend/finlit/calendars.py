"""IPO and results calendars from the data provider (FinEdge), refreshed daily.

Results: every announced board-meeting date becomes a `result` item in the feed (the same table the exchange filings use), so the
Results calendar shows past filings and upcoming dates together, through the end of the window we ask for.
IPOs: copied into the `ipos` table under a provider key; IPOs added by hand are left alone. Status (open, upcoming, closed, listed)
is worked out from the dates when the page is drawn, so it never goes stale between refreshes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

log = logging.getLogger("finlit.calendars")
LIST_KEYS = ("data", "rows", "results", "items", "ipos", "calendar")
SOURCE_RESULTS = "FinEdge results calendar"
IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> date:
    """The Indian calendar day, whatever the server clock's zone is (a one-off `docker compose exec` may not carry TZ)."""
    return datetime.now(IST).date()


def why(exc: BaseException) -> str:
    """A short reason for a log line or the status page: the exception class, plus the provider's HTTP status and first words when it sent one."""
    status = getattr(exc, "status", None)
    text = " ".join(str(exc).split())[:120]
    return f"{type(exc).__name__}" + (f" HTTP {status}" if status else "") + (f": {text}" if text else "")


def rows_of(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in LIST_KEYS:
            if isinstance(payload.get(k), list):
                return [r for r in payload[k] if isinstance(r, dict)]
    return []


def parse_date(v: Any) -> Optional[date]:
    if not v:
        return None
    full = " ".join(str(v).split())
    for s in (full, full[:10]):   # "2026-07-21T00:00:00" and "21-Oct-2026" both appear
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %B %Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


NUM = re.compile(r"\d[\d,]*\.?\d*")


def numbers(text: Any) -> List[float]:
    out = []
    for m in NUM.findall(str(text or "")):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def issue_size_cr(text: Any, price: Optional[float] = None) -> Optional[float]:
    """Issue size to crore rupees: reads '1,250 Cr', '48 crore', '12.5 lakh' or a plain amount in rupees."""
    n = numbers(text)
    if not n:
        return None
    low = str(text).lower()
    v = n[0]
    if "lakh" in low:
        v /= 100
    elif "cr" not in low and v > 1e5:
        if price:
            v = v * price / 1e7   # the provider gives the number of shares offered: size = shares x issue price
        else:
            return None
    return round(v, 2) if v > 0 else None


def result_rows(payload: Any) -> List[tuple]:
    out, seen = [], set()
    for r in rows_of(payload):
        sym = str(r.get("symbol") or "").strip().upper()
        when = parse_date(r.get("expected_result_date") or r.get("date") or r.get("result_date"))
        if not sym or not when or (sym, when) in seen:
            continue
        seen.add((sym, when))
        name = " ".join(str(r.get("company_name") or r.get("name") or sym).split())[:160]
        key = hashlib.sha1(f"rc|{sym}|{when}".encode()).hexdigest()  # nosec B324 - de-duplication key, not security
        out.append(("result", f"{name}: board meeting for results", sym, name, SOURCE_RESULTS, None, when, "Results date", None, None, True, key))
    return out


def _subscribed(v: Any) -> str:
    n = numbers(v)
    return f"Subscribed {n[0]:,.2f}x".replace(".00x", "x") if n else ""


# ------------------------------------------------------------------ tolerant field reading
def _norm(k: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _index(r: dict) -> Dict[str, Any]:
    """The row by normalised key ('Lead Managers', 'lead_managers' and 'leadManagers' are one key); the first non-empty value of a key wins."""
    out: Dict[str, Any] = {}
    for k, v in r.items():
        n = _norm(k)
        if n and n not in out and v not in (None, "", [], {}):
            out[n] = v
    return out


def _pick(ix: Dict[str, Any], *aliases: str) -> Any:
    for a in aliases:
        v = ix.get(_norm(a))
        if v is not None:
            return v
    return None


def _text(v: Any, n: int = 200) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    t = " ".join(str(v).split())
    return t[:n] if t and t.lower() not in ("na", "n/a", "nan", "none", "null", "-", "--", "nil") else None


def _num(v: Any, lo: float = 0.0, hi: float = 1e12) -> Optional[float]:
    if isinstance(v, bool) or v is None or isinstance(v, (dict, list)):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        n = numbers(v)
        if not n:
            return None
        x = n[0]
    return x if lo <= x <= hi and x == x else None


def _names(v: Any, limit: int = 12) -> List[str]:
    """A list of names from a list or from 'A, B & C' / 'A; B' / one name per line."""
    if isinstance(v, str):
        parts = re.split(r"\s*(?:[;\n|]|,(?!\s*(?:Inc|Ltd|Limited|LLP)\b)|\s&\s|\band\b)\s*", v)
    elif isinstance(v, list):
        parts = [x.get("name") if isinstance(x, dict) else x for x in v]
    else:
        return []
    out: List[str] = []
    for p in parts:
        t = _text(p, 90)
        if t and t not in out:
            out.append(t)
    return out[:limit]


def _https(v: Any) -> Optional[str]:
    t = _text(v, 400)
    return t if t and re.match(r"^https://[^\s<>\"']+$", t) else None


def _subscription(ix: Dict[str, Any]) -> Dict[str, float]:
    """Times subscribed: overall and by investor category, from a number, a '12.3x' string, a dict or a list of {category, times}; flat keys too."""
    out: Dict[str, float] = {}
    cat = {"qib": "qib", "qualifiedinstitutionalbuyers": "qib", "qualifiedinstitutional": "qib", "nii": "nii", "hni": "nii", "nib": "nii", "bnii": "nii", "snii": "nii", "noninstitutional": "nii",
           "noninstitutionalinvestors": "nii", "hniNii".lower(): "nii", "retail": "retail", "rii": "retail", "retailindividual": "retail", "retailindividualinvestors": "retail",
           "employee": "employees", "employees": "employees", "shareholder": "shareholders", "shareholders": "shareholders", "total": "overall", "overall": "overall"}

    def put(name: Any, val: Any) -> None:
        key = cat.get(_norm(name))
        if key is None:
            for frag, k in (("qib", "qib"), ("institutionalbuyer", "qib"), ("retail", "retail"), ("employee", "employees"), ("shareholder", "shareholders"), ("nii", "nii"), ("hni", "nii"), ("noninstitutional", "nii"), ("total", "overall"), ("overall", "overall")):
                if frag in _norm(name):
                    key = k
                    break
        x = _num(val, 0, 1e5)
        if key and x is not None and key not in out:
            out[key] = round(x, 2)

    sub = _pick(ix, "subscription", "subscription_status", "subscribed", "times_subscribed", "subscription_times", "subscription_details")
    if isinstance(sub, dict):
        for k, v in sub.items():
            if isinstance(v, dict):
                v = _pick({_norm(a): b for a, b in v.items()}, "times", "subscription", "subscribed", "x", "value")
            put(k, v)
    elif isinstance(sub, list):
        for item in sub:
            if isinstance(item, dict):
                i2 = {_norm(a): b for a, b in item.items()}
                put(_pick(i2, "category", "name", "investor_category", "type", "investor") or "", _pick(i2, "times", "subscription", "subscribed", "x", "value", "times_subscribed"))
    elif sub is not None:
        put("overall", sub)
    for name, aliases in (("overall", ("overall_subscription", "total_subscription", "total_subscribed", "subscription_total", "subscribed_total", "subscription_overall")),
                          ("qib", ("qib_subscription", "subscription_qib", "qib_subscribed", "qib", "qib_times")),
                          ("nii", ("nii_subscription", "hni_subscription", "subscription_nii", "subscription_hni", "nii", "hni", "nii_times")),
                          ("retail", ("retail_subscription", "rii_subscription", "subscription_retail", "subscription_rii", "retail", "rii", "retail_times")),
                          ("employees", ("employee_subscription", "subscription_employee", "employee")),
                          ("shareholders", ("shareholder_subscription", "subscription_shareholder", "shareholder"))):
        if name not in out:
            put(name, _pick(ix, *aliases))
    return out


def _pct(v: Any) -> Optional[float]:
    x = _num(v, 0, 100)
    return round(x, 2) if x is not None else None


def _objectives(v: Any) -> List[str]:
    if isinstance(v, str):
        items = re.split(r"\s*(?:\n|;|\|)\s*", v)
    elif isinstance(v, list):
        items = [x.get("objective") or x.get("name") or x.get("title") if isinstance(x, dict) else x for x in v]
    else:
        return []
    out = []
    for i in items:
        t = _text(i, 220)
        if t:
            out.append(t)
    return out[:8]


def details_of(r: dict, size_price: Optional[float] = None) -> Dict[str, Any]:
    """Every extra fact the provider's row carries that we know how to read, by tolerant alias; absent facts are left out, never filled in."""
    ix = _index(r)
    d: Dict[str, Any] = {}

    def put(k: str, v: Any) -> None:
        if v not in (None, "", [], {}):
            d[k] = v

    put("issueType", _text(_pick(ix, "issue_type", "ipo_type", "type_of_issue", "issue_category", "price_type", "pricing_type", "issue_method")))
    ex = _pick(ix, "exchange", "exchanges", "listing_exchange", "listing_exchanges", "listed_on", "listing_at", "bourse")
    exs = [e for e in (re.findall(r"NSE|BSE", " ".join(map(str, ex)) .upper() if isinstance(ex, list) else str(ex).upper()) if ex else []) ]
    put("exchange", list(dict.fromkeys(exs)))
    put("registrar", _text(_pick(ix, "registrar", "registrar_name", "registrar_to_the_issue", "registrar_to_issue", "ipo_registrar")))
    put("leadManagers", _names(_pick(ix, "lead_managers", "lead_manager", "book_running_lead_managers", "book_running_lead_manager", "brlm", "merchant_bankers", "merchant_banker", "managers", "underwriters")))
    sub = _subscription(ix)
    put("subscription", sub)
    for k, aliases in (("allotmentDate", ("allotment_date", "basis_of_allotment_date", "basis_of_allotment", "allotment", "allotment_finalisation_date", "allotment_on")),
                       ("refundDate", ("refund_date", "initiation_of_refunds", "initiation_of_refund", "refunds", "refund_initiation_date", "unblocking_date")),
                       ("creditDate", ("credit_date", "credit_of_shares_date", "credit_of_shares_to_demat", "demat_credit_date", "shares_credit_date"))):
        dt = parse_date(_pick(ix, *aliases))
        put(k, dt.isoformat() if dt else None)
    put("faceValue", _num(_pick(ix, "face_value", "fv", "facevalue", "face_value_per_share"), 0.0001, 100000))
    put("minInvestmentProvided", _num(_pick(ix, "min_investment", "minimum_investment", "min_amount", "minimum_amount", "min_application_amount", "minimum_bid_amount"), 1, 1e9))
    put("issuePrice", _num(_pick(ix, "issue_price", "final_issue_price", "offer_price", "final_price"), 0.01, 1e6))
    put("freshIssueCr", issue_size_cr(_pick(ix, "fresh_issue", "fresh_issue_size", "fresh_issue_amount", "fresh_shares", "fresh_issue_shares"), size_price))
    put("ofsCr", issue_size_cr(_pick(ix, "offer_for_sale", "ofs", "ofs_size", "offer_for_sale_size", "offer_for_sale_amount", "ofs_shares", "offer_for_sale_shares"), size_price))
    put("promoterPrePct", _pct(_pick(ix, "promoter_holding_pre", "promoter_holding_pre_issue", "pre_issue_promoter_holding", "promoter_holding_before", "promoter_pre_issue", "promoter_holding_before_issue", "pre_ipo_promoter_holding")))
    put("promoterPostPct", _pct(_pick(ix, "promoter_holding_post", "promoter_holding_post_issue", "post_issue_promoter_holding", "promoter_holding_after", "promoter_post_issue", "promoter_holding_after_issue", "post_ipo_promoter_holding")))
    put("objectives", _objectives(_pick(ix, "objectives", "objects_of_the_issue", "objects_of_issue", "objective", "use_of_proceeds", "purpose", "objects")))
    docs = {k: _https(_pick(ix, *al)) for k, al in (("drhp", ("drhp", "drhp_link", "drhp_url", "draft_red_herring_prospectus", "drhp_document")), ("rhp", ("rhp", "rhp_link", "rhp_url", "red_herring_prospectus", "rhp_document")),
                                                      ("prospectus", ("prospectus", "prospectus_link", "prospectus_url", "offer_document", "offer_document_link", "document_url", "document_link")))}
    put("docs", {k: v for k, v in docs.items() if v})
    put("about", _text(_pick(ix, "about", "description", "company_description", "business", "about_company"), 600))
    put("statusText", _text(_pick(ix, "ipo_status", "status")))
    return d


_SECRETISH = re.compile(r"key|token|secret|password|auth", re.I)


def slim(v: Any, depth: int = 0, limit: int = 600) -> Any:
    """A small, JSON-safe copy of a provider value: long strings cut, deep or long containers trimmed, secret-looking keys dropped."""
    if isinstance(v, str):
        return v if len(v) <= limit else v[:limit] + "…"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if depth >= 3:
        return None
    if isinstance(v, list):
        return [slim(x, depth + 1, limit) for x in v[:12]]
    if isinstance(v, dict):
        return {str(k)[:60]: slim(x, depth + 1, limit) for k, x in list(v.items())[:40] if not _SECRETISH.search(str(k))}
    return str(v)[:limit]


def raw_of(r: dict, budget: int = 6000) -> Dict[str, Any]:
    """The provider's row, kept small: fields whose JSON is over 1,500 characters are dropped, then the largest are dropped until it fits `budget`."""
    out = {k: v for k, v in slim(r).items() if len(json.dumps(v, default=str)) <= 1500}
    while out and len(json.dumps(out, default=str)) > budget:
        out.pop(max(out, key=lambda k: len(json.dumps(out[k], default=str))))
    return out


def ipo_fields(payload: Any, window_from: date, window_to: date) -> Dict[str, Any]:
    """What the provider's /ipo-calendar rows really carry: every key seen, one full sample row (the one with most fields), counts and the window asked.
    Shown read-only at /api/results/status so a missing field can be read off a browser page."""
    rows = rows_of(payload)
    keys = sorted({str(k) for r in rows for k in r})
    best = max(rows, key=lambda r: sum(v not in (None, "", [], {}) for v in r.values()), default=None)
    return {"seenKeys": keys[:120], "sample": slim(best, limit=200) if best else None, "rowCount": len(rows), "windowFrom": window_from.isoformat(), "windowTo": window_to.isoformat(),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def ipo_rows(payload: Any) -> List[tuple]:
    """Rows for the `ipos` table: the 14 columns of the original insert (name .. note, ext key), then the raw provider row and the parsed extras (both as JSON text)."""
    out, seen_names = [], set()
    for r in rows_of(payload):
        ix = _index(r)
        name = " ".join(str(_pick(ix, "company_name", "name", "issuer", "issuer_name", "ipo_name", "company") or "").split())[:160]
        start, end = parse_date(_pick(ix, "start_date", "open_date", "opening_date", "issue_open", "issue_open_date", "bidding_start_date")), parse_date(_pick(ix, "end_date", "close_date", "closing_date", "issue_close", "issue_close_date", "bidding_end_date"))
        if not name or not start or not end or end < start or name.lower() in seen_names:   # the provider sometimes lists an issue twice
            continue
        seen_names.add(name.lower())
        sym = _text(_pick(ix, "symbol", "ticker", "nse_symbol", "scrip", "trading_symbol"), 24)
        sym = sym.upper() if sym and re.match(r"^[A-Za-z0-9&._-]{1,24}$", sym) else None
        lo, hi = _num(_pick(ix, "price_low", "min_price", "lower_price", "price_band_low")), _num(_pick(ix, "price_high", "max_price", "upper_price", "price_band_high"))
        band = [x for x in numbers(_pick(ix, "price_range", "price_band", "issue_price_range", "price", "issue_price", "offer_price")) if x > 0]
        if lo and hi and lo > hi:
            lo, hi = hi, lo
        if not (lo or hi) and band:
            lo, hi = min(band), max(band)
        elif (lo or hi) and not (lo and hi):
            lo = hi = lo or hi
        sec = f"{_pick(ix, 'security_type') or ''} {_pick(ix, 'exchange') or ''} {_pick(ix, 'issue_type', 'ipo_type', 'category', 'board', 'segment') or ''}".lower()
        kind = "sme" if "sme" in sec else "mainboard"
        listing = parse_date(_pick(ix, "listing_date", "list_date", "listing_on", "listed_date", "date_of_listing"))
        ext = hashlib.sha1(f"ipo|{sym or name.lower()}|{start}".encode()).hexdigest()  # nosec B324 - provider key, not security
        status_txt = str(_pick(ix, "ipo_status") or "").strip()
        note = " · ".join(x for x in (status_txt, _subscribed(_pick(ix, "subscription"))) if x)[:200] or None
        lot = _num(_pick(ix, "lot_size", "market_lot", "lot", "min_lot", "minimum_lot_size", "bid_lot", "min_bid_quantity", "minimum_bid_quantity"), 1, 10_000_000)
        lp = _num(_pick(ix, "listing_price", "list_price", "listed_price", "listing_day_price", "listing_open_price", "listing_day_open"), 0.01, 1e6)
        sector = _text(_pick(ix, "sector", "industry", "industry_name"), 60)
        details = details_of(r, hi)
        size = issue_size_cr(_pick(ix, "issue_size", "total_issue_size", "issue_amount", "issue_size_cr", "size", "total_issue_amount"), hi)
        out.append((name, sym, kind, sector, start, end, listing, lo, hi, int(lot) if lot else None, size, lp, note, ext, json.dumps(raw_of(r), default=str), json.dumps(details, default=str)))
    return out


async def refresh_calendars(client, store, days_back: int = 100, days_ahead: int = 120, ipo_back: int = 90, report: Optional[dict] = None) -> Dict[str, int]:
    """Pull results dates and IPOs; returns how many of each were stored. A provider failure leaves the old data in place.
    `report` (optional) is filled with the reasons: errors per part, rows the provider sent and rows dropped, and the newest date stored."""
    today = today_ist()
    counts = {"results": 0, "ipos": 0}
    rep = report if report is not None else {}
    rep.setdefault("errors", {})
    try:
        payload = await client.get("/results-calendar", {"from_date": (today - timedelta(days=days_back)).isoformat(), "to_date": (today + timedelta(days=days_ahead)).isoformat()}, timeout=40)
        sent = rows_of(payload)
        rows = result_rows(payload)
        rep["resultsSent"], rep["resultsDropped"] = len(sent), len(sent) - len(rows)
        if sent and len(rows) < len(sent):
            log.warning("results calendar: %d of %d rows had no usable symbol or date and were skipped (first row keys: %s)", len(sent) - len(rows), len(sent), sorted(sent[0])[:12])
        if not sent:
            rep["errors"]["results"] = "the provider sent no rows"
            log.warning("results calendar not refreshed: the provider sent no rows for %s to %s", today - timedelta(days=days_back), today + timedelta(days=days_ahead))
        elif not rows:
            rep["errors"]["results"] = f"{len(sent)} rows sent, none with a symbol and a readable date (keys: {', '.join(sorted(sent[0])[:10])})"
            log.warning("results calendar not refreshed: %s", rep["errors"]["results"])
        if rows:
            # Delete only what the provider's answer covers: if it sends upcoming dates alone, the past dates already stored (the record that a company's
            # meeting has happened) stay. Rows from the earliest date it sent (at the latest from today) onward are replaced, so a date that moved never leaves a second copy.
            floor = min(today, max(today - timedelta(days=days_back), min(r[6] for r in rows)))   # never above today: a future date that moved or was dropped is always replaced
            async with store.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM feed_items WHERE source = $1 AND item_date >= $2", SOURCE_RESULTS, floor)
                    await conn.executemany("INSERT INTO feed_items (kind, title, symbol, company, source, link, item_date, category, period, summary, auto, dedupe) "
                                           "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT (dedupe) DO NOTHING", rows)
            counts["results"] = len(rows)
            rep["newestSent"] = max(r[6] for r in rows).isoformat()
            rep["oldestSent"] = min(r[6] for r in rows).isoformat()
    except Exception as exc:
        rep["errors"]["results"] = why(exc)
        log.warning("results calendar not refreshed: %s", why(exc))
    try:
        w_from, w_to = today - timedelta(days=ipo_back), today + timedelta(days=days_ahead)
        payload = await client.get("/ipo-calendar", {"from_date": w_from.isoformat(), "to_date": w_to.isoformat()}, timeout=40)
        rep["ipoFields"] = ipo_fields(payload, w_from, w_to)   # what the provider really sends, for /api/results/status
        rows = ipo_rows(payload)
        if rows:
            async with store.pool.acquire() as conn, conn.transaction():
                # The provider's list is the truth for its window: replace it, so a moved date never leaves a second copy behind.
                await conn.execute("DELETE FROM ipos WHERE source = 'FinEdge' AND open_date >= $1", today - timedelta(days=ipo_back))
                await conn.executemany(
                    "INSERT INTO ipos (name, symbol, kind, sector, open_date, close_date, listing_date, price_low, price_high, lot_size, issue_size_cr, listing_price, note, ext_key, raw, details, source) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb,$16::jsonb,'FinEdge') ON CONFLICT (ext_key) WHERE ext_key IS NOT NULL DO UPDATE SET "
                    "name = EXCLUDED.name, symbol = EXCLUDED.symbol, kind = EXCLUDED.kind, sector = COALESCE(EXCLUDED.sector, ipos.sector), open_date = EXCLUDED.open_date, close_date = EXCLUDED.close_date, "
                    "listing_date = COALESCE(EXCLUDED.listing_date, ipos.listing_date), price_low = EXCLUDED.price_low, price_high = EXCLUDED.price_high, "
                    "lot_size = COALESCE(EXCLUDED.lot_size, ipos.lot_size), listing_price = COALESCE(EXCLUDED.listing_price, ipos.listing_price), raw = EXCLUDED.raw, details = EXCLUDED.details, "
                    "issue_size_cr = COALESCE(EXCLUDED.issue_size_cr, ipos.issue_size_cr), note = EXCLUDED.note, updated_at = now()", rows)
            counts["ipos"] = len(rows)
    except Exception as exc:
        rep["errors"]["ipos"] = why(exc)
        log.warning("IPO calendar not refreshed: %s", why(exc))
    log.info("calendars refreshed: %s", counts)
    return counts
