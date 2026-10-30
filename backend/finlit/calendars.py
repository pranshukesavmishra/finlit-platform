"""IPO and results calendars from the data provider (FinEdge), refreshed daily.

Results: every announced board-meeting date becomes a `result` item in the feed (the same table the exchange filings use), so the
Results calendar shows past filings and upcoming dates together, through the end of the window we ask for.
IPOs: copied into the `ipos` table under a provider key; IPOs added by hand are left alone. Status (open, upcoming, closed, listed)
is worked out from the dates when the page is drawn, so it never goes stale between refreshes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta
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


def ipo_rows(payload: Any) -> List[tuple]:
    out, seen_names = [], set()
    for r in rows_of(payload):
        name = " ".join(str(r.get("company_name") or r.get("name") or "").split())[:160]
        start, end = parse_date(r.get("start_date") or r.get("open_date")), parse_date(r.get("end_date") or r.get("close_date"))
        if not name or not start or not end or end < start or name.lower() in seen_names:   # the provider sometimes lists an issue twice
            continue
        seen_names.add(name.lower())
        sym = str(r.get("symbol") or "").strip().upper() or None
        band = [x for x in numbers(r.get("price_range")) if x > 0]
        sec = f"{r.get('security_type') or ''} {r.get('exchange') or ''}".lower()
        kind = "sme" if "sme" in sec else "mainboard"
        listing = parse_date(r.get("listing_date"))
        ext = hashlib.sha1(f"ipo|{sym or name.lower()}|{start}".encode()).hexdigest()  # nosec B324 - provider key, not security
        note = " · ".join(x for x in (str(r.get("ipo_status") or "").strip(), _subscribed(r.get("subscription"))) if x)[:200] or None
        out.append((name, sym, kind, None, start, end, listing, min(band) if band else None, max(band) if band else None, None, issue_size_cr(r.get("issue_size"), max(band) if band else None), None, note, ext))
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
        payload = await client.get("/ipo-calendar", {"from_date": (today - timedelta(days=ipo_back)).isoformat(), "to_date": (today + timedelta(days=days_ahead)).isoformat()}, timeout=40)
        rows = ipo_rows(payload)
        if rows:
            async with store.pool.acquire() as conn, conn.transaction():
                # The provider's list is the truth for its window: replace it, so a moved date never leaves a second copy behind.
                await conn.execute("DELETE FROM ipos WHERE source = 'FinEdge' AND open_date >= $1", today - timedelta(days=ipo_back))
                await conn.executemany(
                    "INSERT INTO ipos (name, symbol, kind, sector, open_date, close_date, listing_date, price_low, price_high, lot_size, issue_size_cr, listing_price, note, ext_key, source) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'FinEdge') ON CONFLICT (ext_key) WHERE ext_key IS NOT NULL DO UPDATE SET "
                    "name = EXCLUDED.name, symbol = EXCLUDED.symbol, kind = EXCLUDED.kind, open_date = EXCLUDED.open_date, close_date = EXCLUDED.close_date, "
                    "listing_date = COALESCE(EXCLUDED.listing_date, ipos.listing_date), price_low = EXCLUDED.price_low, price_high = EXCLUDED.price_high, "
                    "issue_size_cr = COALESCE(EXCLUDED.issue_size_cr, ipos.issue_size_cr), note = EXCLUDED.note, updated_at = now()", rows)
            counts["ipos"] = len(rows)
    except Exception as exc:
        rep["errors"]["ipos"] = why(exc)
        log.warning("IPO calendar not refreshed: %s", why(exc))
    log.info("calendars refreshed: %s", counts)
    return counts
