"""Provider-neutral number, date and row parsing shared by financial code."""
import calendar
import math
from datetime import date, datetime

CR = 10_000_000

def num(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def items(payload, *keys):
    if isinstance(payload, list): return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list): return items(payload[key])
    return []

def first(row, *names):
    for name in names:
        value = num(row.get(name))
        if value is not None: return value
    return None

def field_date(row):
    for key in ("period_end", "periodEnd", "date_header", "header", "quote_date", "date", "year"):
        value = str(row.get(key) or "")
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%b %Y", "%b-%Y", "%Y"):
            try:
                parsed = datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
                if fmt in ("%b %Y", "%b-%Y"):
                    parsed = parsed.replace(day=calendar.monthrange(parsed.year, parsed.month)[1])
                if fmt == "%Y": parsed = date(parsed.year, 3, 31)
                return parsed
            except ValueError: pass
    return None
