"""Small, dependency-free parsing helpers shared by every normalizer.

FinEdge returns money in rupees, ratios as fractions, and dates in several
formats ("2026-09-28", "2026-09-25 22:49:04", "05-Jun-2026", "Mar 2026").
Everything is normalised here so the rest of the code only sees ISO dates,
crore values and plain floats.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

RUPEES_PER_CRORE = 10_000_000

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def to_number(value: Any) -> Optional[float]:
    """Parse numbers that may arrive as strings with %, commas or dashes."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None  # NaN guard
    text = str(value).strip().replace(",", "").replace("%", "").replace("₹", "")
    if text in {"", "-", "—", "NA", "N/A", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def crore(value: Any, digits: int = 2) -> Optional[float]:
    """Rupees -> ₹ crore."""
    number = to_number(value)
    return None if number is None else round(number / RUPEES_PER_CRORE, digits)


def pct(value: Any, digits: int = 2) -> Optional[float]:
    """Fraction (0.0693) -> percent (6.93)."""
    number = to_number(value)
    return None if number is None else round(number * 100, digits)


def rnd(value: Any, digits: int = 2) -> Optional[float]:
    number = to_number(value)
    return None if number is None else round(number, digits)


def parse_date(value: Any) -> Optional[date]:
    """Accepts ISO dates/datetimes, DD-Mon-YYYY, DD-MM-YYYY, DD/MM/YYYY and Unix seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if re.fullmatch(r"(19|20)\d{6}", text):  # FinEdge statement periods: 20260331
        return _safe_date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date() if value > 100_000_000 else None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return _safe_date(int(match[1]), int(match[2]), int(match[3]))
    match = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3})[A-Za-z]*[-/ ](\d{4})$", text)
    if match and match[2].lower() in _MONTHS:
        return _safe_date(int(match[3]), _MONTHS[match[2].lower()], int(match[1]))
    match = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", text)
    if match:
        return _safe_date(int(match[3]), int(match[2]), int(match[1]))
    return None


def iso(value: Any) -> Optional[str]:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def month_label(value: Any) -> Optional[str]:
    """'2026-03-31' -> 'Mar 2026'."""
    parsed = parse_date(value)
    return parsed.strftime("%b %Y") if parsed else None


def fiscal_year_label(period_end: Any, fallback_year: Any = None) -> Optional[str]:
    """Indian fiscal year label from the period end: FY ending Mar 2026 -> 'FY26'."""
    parsed = parse_date(period_end)
    if parsed:
        year = parsed.year + (1 if parsed.month > 3 else 0)
        return f"FY{year % 100:02d}"
    if fallback_year:
        return f"FY{int(fallback_year) % 100:02d}"
    return None


def quarter_label(period_end: Any) -> Optional[str]:
    """'2026-06-30' -> 'Jun 2026' (quarter-end month), the convention Indian investors read."""
    return month_label(period_end)


def first(row: dict, keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def sum_present(*values: Any) -> Optional[float]:
    numbers = [to_number(v) for v in values]
    numbers = [n for n in numbers if n is not None]
    return sum(numbers) if numbers else None
