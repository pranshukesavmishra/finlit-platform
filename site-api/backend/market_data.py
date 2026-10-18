"""Public market feeds: explicit schemas, bounded requests, and no credentials."""
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import math
import re


ENDPOINTS = {
    "ipo": "/ipo-calendar",
    "results": "/results-calendar",
    "announcements": "/corp-announcements",
    "transcripts": "/investor-call-transcripts",
    "indices": "/index/market-price/daily-feed",
    "valuations": "/index/valuation/historical",
}


def market_params(section, from_date=None, to_date=None, symbol=None, index_symbol=None):
    if section not in ENDPOINTS:
        raise ValueError("Unknown market section.")
    if section == "indices":
        return {}
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    short_window = section in {"announcements", "transcripts"}
    start = from_date or today - timedelta(days=6 if short_window else 7)
    end = to_date or (today if short_window or section == "valuations" else today + timedelta(days=15))
    if not isinstance(start, date) or not isinstance(end, date) or end < start:
        raise ValueError("Choose a valid date range with the end on or after the start.")
    if (end - start).days > (7 if short_window else 366):
        raise ValueError("Announcements and transcripts support a maximum 7-day range." if short_window else "Choose a date range of at most one year.")
    params = {"from_date": start.isoformat(), "to_date": end.isoformat()}
    if symbol and short_window:
        if not re.fullmatch(r"[A-Za-z0-9.&-]{1,30}", symbol.strip()):
            raise ValueError("Enter a valid company symbol.")
        params["symbol"] = symbol.strip().upper()
    if section == "valuations":
        if not index_symbol or not re.fullmatch(r"[A-Za-z0-9_.& -]{1,60}", index_symbol.strip()):
            raise ValueError("Select an index to view its valuation history.")
        params["index_symbol"] = index_symbol.strip()
    return params


def safe_document_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.strip())
        return value.strip() if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("%", ""))
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def normalize_market_payload(section, payload):
    if isinstance(payload, list):
        source = payload
    elif isinstance(payload, dict):
        source = next((payload[key] for key in ("data", "rows", "results", "items", "announcements", "transcripts") if isinstance(payload.get(key), list)), None)
        if source is None:
            if not payload:
                source = []
            else:
                raise ValueError("The provider returned an unexpected market-data response.")
    else:
        raise ValueError("The provider returned an unexpected market-data response.")
    rows = []
    seen = set()
    for item in source:
        if not isinstance(item, dict):
            continue
        if section == "ipo":
            row = {key: item.get(key) for key in ("symbol", "company_name", "security_type", "ipo_status", "start_date", "end_date", "price_range", "issue_size", "subscription", "current_bids")}
            exchanges = item.get("exchange") or []
            row["exchange"] = ", ".join(str(value) for value in exchanges) if isinstance(exchanges, list) else str(exchanges)
            identity = (row["symbol"], row["company_name"], row["start_date"], row["security_type"])
        elif section == "results":
            row = {key: item.get(key) for key in ("symbol", "company_name", "expected_result_date")}
            identity = (row["symbol"], row["expected_result_date"])
        elif section in {"announcements", "transcripts"}:
            row = {
                "symbol": item.get("stock_symbol") or item.get("nse_code") or item.get("bse_code"),
                "category": item.get("category"),
                "description": item.get("description"),
                "date": item.get("announcement_date") or item.get("ex_date"),
                "document_url": safe_document_url(item.get("pdf_file_link")) or safe_document_url(item.get("pdf_file_link_hist")),
            }
            identity = (row["symbol"], row["date"], row["description"], row["document_url"])
        else:
            row = {key: item.get(key) for key in ("index_symbol", "index_name", "quote_date")}
            for key in ("close_price", "open_price", "high_price", "low_price", "change_pct", "points_change", "pe", "pb", "div_yield", "market_cap", "volume", "turnover"):
                row[key] = number(item.get(key))
            if section == "valuations":
                row["index_symbol"] = row["index_symbol"] or (payload.get("index_symbol") if isinstance(payload, dict) else None)
            identity = (row["index_symbol"], row["quote_date"])
        if identity in seen or not any(value is not None and value != "" for value in identity):
            continue
        seen.add(identity)
        rows.append(row)
    if section == "results":
        rows.sort(key=lambda row: str(row.get("expected_result_date") or "9999"))
    elif section in {"announcements", "transcripts"}:
        rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    elif section == "indices":
        rows.sort(key=lambda row: str(row.get("index_name") or row.get("index_symbol") or ""))
    elif section == "valuations":
        rows.sort(key=lambda row: str(row.get("quote_date") or ""), reverse=True)
    return rows


def normalize_commodity_list(payload):
    if not isinstance(payload, list):
        raise ValueError("Unexpected commodity list.")
    items = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "")
        if re.fullmatch(r"[0-9]{1,12}", code) and row.get("name"):
            items[code] = {"code": code, "name": str(row["name"]), "weight": number(row.get("weight"))}
    return sorted(items.values(), key=lambda row: row["name"].casefold())


def normalize_commodity_history(payload):
    if not isinstance(payload, list):
        raise ValueError("Unexpected commodity history.")
    rows = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            period = datetime.strptime(str(row.get("date_header")), "%b-%Y")
        except ValueError:
            continue
        key = period.strftime("%Y-%m")
        rows[key] = {"period": key, "label": row["date_header"], "value": number(row.get("value"))}
    return sorted(rows.values(), key=lambda row: row["period"], reverse=True)


def normalize_commodity_changes(payload):
    if not isinstance(payload, dict):
        raise ValueError("Unexpected commodity changes.")
    rows = payload.get("pct_change", payload.get("pct_changes"))
    if not isinstance(rows, list):
        raise ValueError("Unexpected commodity changes.")
    return [{"period": str(row["index"]), "value": number(row.get("change_pct"))}
            for row in rows if isinstance(row, dict) and row.get("index")]
