"""Dividends, corporate actions, announcements, peers and segment revenue."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .common import crore, fiscal_year_label, iso, parse_date, rnd, to_number


# ---------------------------------------------------------------- dividends & corporate actions

def _kind(text: str) -> str:
    t = (text or "").lower()
    if "bonus" in t:
        return "bonus"
    if "split" in t or "sub-division" in t or "subdivision" in t:
        return "split"
    if "buyback" in t or "buy back" in t:
        return "buyback"
    if "rights" in t:
        return "rights"
    if "dividend" in t:
        if "interim" in t:
            return "interim_dividend"
        if "special" in t:
            return "special_dividend"
        return "final_dividend"
    return "other"


def corporate_actions(dividend_payload: Any, actions_payload: Any = None) -> List[dict]:
    """Merge /dividend and /corporate-actions/all, parse every date format, and de-duplicate.

    Fixes two live-site bugs:
    * dates like '05-Jun-2026' were unparseable in the browser, so every dividend counted
      for every return period (BPCL showed 89.14% at all horizons);
    * the same dividend arrives from both endpoints and was counted twice.
    """
    raw: List[dict] = []
    if isinstance(dividend_payload, dict):
        raw += [dict(r, _src="dividend") for r in dividend_payload.get("dividend") or [] if isinstance(r, dict)]
    elif isinstance(dividend_payload, list):
        raw += [dict(r, _src="dividend") for r in dividend_payload if isinstance(r, dict)]
    if isinstance(actions_payload, list):
        raw += [dict(r, _src="actions") for r in actions_payload if isinstance(r, dict)]
    elif isinstance(actions_payload, dict):
        for key in ("corporate_actions", "actions", "data"):
            if isinstance(actions_payload.get(key), list):
                raw += [dict(r, _src="actions") for r in actions_payload[key] if isinstance(r, dict)]

    seen = set()
    out = []
    for row in raw:
        when = parse_date(row.get("ex_date") or row.get("exDate") or row.get("date") or row.get("record_date") or row.get("announcement_date"))
        text = row.get("subject") or row.get("purpose") or row.get("dividend_type") or row.get("action") or row.get("type") or ""
        kind = _kind(f"{row.get('dividend_type') or ''} {text}")
        amount = to_number(row.get("amount"))
        adjusted = to_number(row.get("adj_amount"))
        if adjusted is None:
            adjusted = amount
        key = (when, kind if not kind.endswith("dividend") else "dividend", round(amount or 0, 4))
        if when is None or key in seen:
            continue
        seen.add(key)
        out.append({
            "date": when.isoformat(),
            "type": kind,
            "title": _title(kind, amount, row.get("ratio")),
            "amount": rnd(amount, 4),
            "adjustedAmount": rnd(adjusted, 4),
            "ratio": row.get("ratio"),
            "paidInFY": fiscal_year_label(when),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def _title(kind: str, amount: Optional[float], ratio: Any) -> str:
    names = {"interim_dividend": "Interim dividend", "final_dividend": "Final dividend", "special_dividend": "Special dividend",
             "bonus": "Bonus issue", "split": "Stock split", "buyback": "Buyback", "rights": "Rights issue", "other": "Corporate action"}
    base = names.get(kind, "Corporate action")
    if kind.endswith("dividend") and amount is not None:
        return f"{base} · ₹{amount:g} per share"
    if ratio:
        return f"{base} · {ratio}"
    return base


def dividends_between(actions: List[dict], start: date, end: date) -> float:
    """Sum of split/bonus-adjusted dividends with ex-date in (start, end]."""
    total = 0.0
    for action in actions:
        if not action["type"].endswith("dividend"):
            continue
        when = parse_date(action["date"])
        if when and start < when <= end:
            total += action.get("adjustedAmount") or 0
    return total


def dividends_by_fiscal_year(actions: List[dict], years: int = 6) -> dict:
    totals: Dict[str, float] = {}
    for action in actions:
        if action["type"].endswith("dividend") and action.get("paidInFY"):
            totals[action["paidInFY"]] = round(totals.get(action["paidInFY"], 0) + (action.get("adjustedAmount") or 0), 4)
    periods = sorted(totals, key=lambda p: int(p[2:]))[-years:]
    return {"periods": periods, "dps": [totals[p] for p in periods]}


# ---------------------------------------------------------------- announcements

NOISE = {"Trading Window", "Copy of Newspaper Publication", "Shareholders meeting"}


def announcements(payload: Any, limit: int = 25) -> List[dict]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("announcements") or []
    out = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        when = parse_date(row.get("announcement_date"))
        category = (row.get("category") or "General").strip()
        link = row.get("pdf_file_link") or None
        key = (when, category, link)
        if when is None or key in seen or category in NOISE:
            continue
        seen.add(key)
        out.append({
            "date": when.isoformat(),
            "time": str(row.get("announcement_date") or "")[11:16] or None,
            "category": category,
            "description": (row.get("description") or "").strip(),
            "link": link,
        })
    out.sort(key=lambda r: (r["date"], r["time"] or ""), reverse=True)
    return out[:limit]


# ---------------------------------------------------------------- peers & segments

def peer_symbols(payload: Any, self_symbol: str) -> List[str]:
    items = payload.get("peers") if isinstance(payload, dict) else payload
    out = []
    for item in items or []:
        symbol = item.get("symbol") if isinstance(item, dict) else item
        symbol = str(symbol or "").strip().upper()
        if symbol and symbol != self_symbol.upper() and symbol not in out:
            out.append(symbol)
    return out[:12]


def segments(payload: Any, limit: int = 6) -> dict:
    rows = payload.get("segment_revenues") if isinstance(payload, dict) else None
    periods = []
    for row in rows or []:
        header = str(row.get("header") or "")
        label = fiscal_year_label(parse_date(f"28-{header[:3]}-{header[-4:]}")) if len(header) >= 8 else None
        if not label or not header.startswith("Mar"):
            continue
        periods.append((label, row))
    periods.sort(key=lambda p: int(p[0][2:]))
    periods = periods[-limit:]
    def key_of(name: str) -> str:  # "Oil & Gas" and "Oil and Gas" are the same segment
        return " ".join(name.lower().replace("&", " and ").split())

    display: Dict[str, str] = {}
    for _, row in periods:  # oldest -> newest, so the latest spelling wins
        for seg in row.get("segments") or []:
            if seg.get("name"):
                display[key_of(seg["name"])] = seg["name"].strip()
    table = {key: {"revenue": [], "ebit": []} for key in display}
    for _, row in periods:
        by_key = {key_of(s.get("name") or ""): s.get("data") or {} for s in row.get("segments") or []}
        for key in display:
            data = by_key.get(key, {})
            table[key]["revenue"].append(crore(data.get("segmentRevenue")))
            table[key]["ebit"].append(crore(data.get("segmentProfitLossBeforeTaxAndFinanceCosts")))
    # Keep only segments that report something in the latest year.
    table = {display[k]: v for k, v in table.items() if v["revenue"] and v["revenue"][-1] not in (None, 0)}
    names = list(table)
    latest_total = sum((table[n]["revenue"][-1] or 0) for n in names) if periods else 0
    summary = []
    for name in names:
        revenue = table[name]["revenue"]
        now = revenue[-1] if revenue else None
        before = revenue[-2] if len(revenue) > 1 else None
        summary.append({
            "name": name, "revenue": now, "ebit": table[name]["ebit"][-1] if revenue else None,
            "sharePct": round(now / latest_total * 100, 2) if now and latest_total else None,
            "growthPct": round((now / before - 1) * 100, 2) if now and before else None,
        })
    summary.sort(key=lambda s: s["revenue"] or 0, reverse=True)
    return {"unit": "Cr", "periods": [p for p, _ in periods], "segments": table, "latest": summary}
