"""Numbers, dates, folios and one imported row. Pure functions, no database.

The browser reads the file (Excel or CSV) and finds the columns; the SERVER decides what every cell means, so there is one place for the rules below
and a hand-made request is held to the same ones. A row is either usable (`Clean`) or comes back with a status and a reason in plain words:
  ignored   not a mutual fund (a company share, a bond), or nothing held (zero units)
  invalid   units missing / not a positive number, or a sale line of a transaction statement
Nothing here guesses: a cell that cannot be read is reported, never replaced by a default (a missing cost is None, not 0).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, List, Optional, Tuple

UNITS_DP = Decimal("0.0001")
MONEY_DP = Decimal("0.01")
MAX_UNITS = Decimal("1000000000")          # a billion units: far above any real holding, below what numeric(20,4) holds
MAX_MONEY = Decimal("10000000000000")      # Rs 10 lakh crore
MIN_DATE = date(1980, 1, 1)
FOLIO_MAX = 40
NAME_MAX = 300

_MONEY_WORDS = re.compile(r"(?i)(?:rs\.?|inr|rupees?|₹)")
_GROUPED = re.compile(r"^\d{1,3}(?:,\d{2,3})+(?:\.\d+)?$")
_PLAIN = re.compile(r"^\d+(?:\.\d+)?$|^\.\d+$")
_NIL = {"", "-", "--", "—", "–", "na", "n/a", "n.a.", "nil", "null", "none", "nan", "#n/a", "not available"}


def parse_decimal(v: Any) -> Tuple[Optional[Decimal], Optional[str]]:
    """(value, problem). A blank / dash / 'NA' cell is (None, None): nothing was given. A cell that is there but is not a number is (None, 'why').
    Indian grouping (1,23,456.78), a rupee sign or 'Rs.', brackets or a leading minus for negatives, and a trailing 'CR' / 'DR' are understood."""
    if v is None or isinstance(v, bool):
        return None, None if v is None else "not a number"
    if isinstance(v, (int, float, Decimal)):
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            return None, "not a number"
        return (d, None) if d.is_finite() else (None, "not a number")
    s = unicodedata.normalize("NFKC", str(v)).replace(" ", " ").strip()
    if s.lower() in _NIL:
        return None, None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = _MONEY_WORDS.sub("", s).strip()
    m = re.match(r"^(.*?)\s*(cr|dr)\.?$", s, re.I)
    if m and m.group(1):
        neg ^= m.group(2).lower() == "dr"
        s = m.group(1).strip()
    if s.startswith("-") or s.startswith("−"):
        neg, s = not neg, s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    if s.endswith("-"):
        neg, s = not neg, s[:-1].strip()
    if not (_PLAIN.match(s) or _GROUPED.match(s)):
        return None, "not a number"
    d = Decimal(s.replace(",", ""))
    return (-d if neg else d), None


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(v: Any, today: Optional[date] = None) -> Tuple[Optional[date], Optional[str]]:
    """(date, problem). Day first (India): 15-03-2022, 15/03/2022, 15.03.22, 15 Mar 2022, 15-Mar-2022, 2022-03-15, 2022/03/15, an Excel serial number.
    A date after today or before 1980 is a problem, not a date."""
    today = today or date.today()
    if v is None:
        return None, None
    if isinstance(v, datetime):
        d: Optional[date] = v.date()
    elif isinstance(v, date):
        d = v
    else:
        d = None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if 20000 <= float(v) <= 80000:
                d = date(1899, 12, 30) + timedelta(days=int(v))
            else:
                return None, "not a date"
        else:
            s = str(v).strip()
            if s.lower() in _NIL:
                return None, None
            s = re.sub(r"\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]m)?$", "", s, flags=re.I)   # a time of day after the date is dropped
            m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
            if m:
                y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                m = re.match(r"^(\d{1,2})[-/. ]([A-Za-z]{3,9})[-/. ,]+(\d{2}|\d{4})$", s)
                if m and m.group(2)[:3].lower() in _MONTHS:
                    dd, mo, y = int(m.group(1)), _MONTHS[m.group(2)[:3].lower()], int(m.group(3))
                else:
                    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$", s)
                    if not m:
                        return None, "not a date"
                    dd, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000 if y <= (today.year % 100) else 1900
            try:
                d = date(y, mo, dd)
            except ValueError:
                return None, "not a date"
    if d is None or d < MIN_DATE:
        return None, "date is before 1980"
    if d > today:
        return None, "date is in the future"
    return d, None


def clean_folio(v: Any) -> str:
    """Upper case, spaces tidied ('1234567 / 89' -> '1234567/89'); placeholders like NA, '-' or 0 mean no folio."""
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", "" if v is None else str(v))).strip().upper()
    if isinstance(v, float) and v == int(v):
        s = str(int(v))
    s = re.sub(r"\s*/\s*", "/", s)
    if s.lower() in _NIL or re.fullmatch(r"0+", s):
        return ""
    return s[:FOLIO_MAX]


def q_units(d: Decimal) -> Decimal:
    return d.quantize(UNITS_DP, rounding=ROUND_HALF_UP)


def q_money(d: Decimal) -> Decimal:
    return d.quantize(MONEY_DP, rounding=ROUND_HALF_UP)


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_FUND_WORDS = re.compile(r"\b(fund|funds|scheme|etf|fof|elss|plan|growth|idcw|dividend|index|nifty|sensex|liquid|overnight|savings|gilt|cap|mutual)\b", re.I)
_COMPANY_END = re.compile(r"\b(ltd|ltd\.|limited|corp|corporation|inc|bank|industries|finance|services|technologies|enterprises|bonds?|debentures?|ncd|sgb)\.?\s*$", re.I)
_NOT_FUND_KIND = re.compile(r"(?i)\b(equity share|equity shares|shares?|stocks?|equities|equity|bonds?|debentures?|ncd|sgb|sovereign gold|nps|ppf|fixed deposit|fd|insurance|gold bond)\b")
_FUND_KIND = re.compile(r"(?i)\b(mutual ?fund|mf|fund|scheme|etf|fof|elss)\b")


def clean_isin(v: Any) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", "" if v is None else str(v)).upper()
    return s if ISIN_RE.match(s) else ""


def clean_amfi(v: Any) -> Optional[int]:
    """An AMFI scheme code: 5 to 6 digits (an Excel '120503.0' is fine). Anything else is no code."""
    if v is None or isinstance(v, bool):
        return None
    s = str(int(v)) if isinstance(v, float) and v == int(v) else str(v).strip()
    s = re.sub(r"\.0+$", "", s)
    return int(s) if re.fullmatch(r"\d{4,7}", s) and 0 < int(s) < 10 ** 7 else None


@dataclass
class Clean:
    """A row that can be matched and imported."""
    row: int
    name: str
    isin: str
    amfi: Optional[int]
    folio: str
    units: Decimal
    invested: Optional[Decimal]
    bought_on: Optional[date]
    warnings: List[str] = field(default_factory=list)


@dataclass
class Rejected:
    row: int
    status: str            # ignored | invalid
    reason: str
    name: str = ""
    isin: str = ""


def clean_row(raw: dict, today: Optional[date] = None) -> "Clean | Rejected":
    """One imported row (the columns the browser found, as the cells were written) -> a Clean row, or why not."""
    row = int(raw.get("row") or 0)
    name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()[:NAME_MAX]
    isin_raw = re.sub(r"[^A-Za-z0-9]", "", str(raw.get("isin") or "")).upper()
    isin = clean_isin(raw.get("isin"))
    kind = str(raw.get("kind") or "").strip()
    # not a mutual fund: a company share (ISIN INE...), a row whose asset-type column says share / bond, a company name with no fund word
    if isin_raw.startswith("INE"):
        return Rejected(row, "ignored", "A company share or bond (its ISIN starts with INE), not a mutual fund.", name, isin_raw)
    is_fund_id = isin_raw.startswith("INF") or clean_amfi(raw.get("amfi")) is not None   # an INF ISIN or an AMFI code is a fund (an ETF too), whatever the asset-type column says
    if kind and not is_fund_id and _NOT_FUND_KIND.search(kind) and not _FUND_KIND.search(kind):
        return Rejected(row, "ignored", f"Asset type \"{kind[:40]}\" is not a mutual fund.", name, isin_raw)
    if name and not isin and raw.get("amfi") in (None, "") and _COMPANY_END.search(name) and not _FUND_WORDS.search(name):
        return Rejected(row, "ignored", "Looks like a company share (no fund wording, no ISIN or AMFI code).", name, "")
    units, why = parse_decimal(raw.get("units"))
    if why:
        return Rejected(row, "invalid", f"Units: {why}.", name, isin)
    if units is None:
        return Rejected(row, "invalid", "Units are missing. The number of units held is needed to value the fund.", name, isin)
    if units < 0:
        return Rejected(row, "invalid", "Negative units: this looks like a redemption line of a transaction statement. Import a holdings (closing balance) statement.", name, isin)
    if units == 0:
        return Rejected(row, "ignored", "Zero units: nothing is held in this fund.", name, isin)
    if units > MAX_UNITS:
        return Rejected(row, "invalid", "Units are larger than any real holding.", name, isin)
    warnings: List[str] = []
    units_q = q_units(units)
    if units_q != units:
        warnings.append("Units were rounded to 4 decimal places.")
    if units_q <= 0:
        return Rejected(row, "invalid", "Units are too small to hold.", name, isin)
    invested: Optional[Decimal] = None
    inv, why_i = parse_decimal(raw.get("invested"))
    avg, why_a = parse_decimal(raw.get("avgCost"))
    if why_i:
        warnings.append(f"Invested amount ignored ({why_i}).")
    if why_a:
        warnings.append(f"Average cost ignored ({why_a}).")
    if inv is not None and not why_i:
        if inv < 0:
            warnings.append("Invested amount is negative: ignored, so the cost is unknown.")
        elif inv > MAX_MONEY:
            warnings.append("Invested amount is larger than any real holding: ignored.")
        else:
            invested = q_money(inv)
    elif avg is not None and not why_a:
        if avg < 0 or avg * units_q > MAX_MONEY:
            warnings.append("Average cost per unit is not usable: ignored, so the cost is unknown.")
        else:
            invested = q_money(avg * units_q)
    bought, why_d = parse_date(raw.get("date"), today)
    if why_d:
        warnings.append(f"Purchase date ignored ({why_d}), so XIRR cannot be worked out for this fund.")
    return Clean(row, name, isin, clean_amfi(raw.get("amfi")), clean_folio(raw.get("folio")), units_q, invested, bought, warnings)


def strict_lot(units: Any, invested: Any = None, avg_cost: Any = None, bought_on: Any = None, today: Optional[date] = None) -> Tuple[Decimal, Optional[Decimal], Optional[date]]:
    """A purchase typed in by the member (or sent back by the import review): every problem is an error with its reason, nothing is dropped quietly.
    Raises ValueError(message). Give the amount paid in total (`invested`) or per unit (`avg_cost`), not both."""
    u, why = parse_decimal(units)
    if why or u is None:
        raise ValueError("Units: enter the number of units held." if u is None and not why else f"Units: {why}.")
    if u <= 0:
        raise ValueError("Units must be above zero.")
    if u > MAX_UNITS:
        raise ValueError("Units are larger than any real holding.")
    uq = q_units(u)
    if uq <= 0:
        raise ValueError("Units are too small to hold (4 decimal places are kept).")
    inv, why_i = parse_decimal(invested)
    avg, why_a = parse_decimal(avg_cost)
    if why_i:
        raise ValueError(f"Amount invested: {why_i}.")
    if why_a:
        raise ValueError(f"Average cost: {why_a}.")
    if inv is not None and avg is not None:
        raise ValueError("Give the amount invested or the average cost per unit, not both.")
    money: Optional[Decimal] = None
    if inv is not None:
        if inv < 0 or inv > MAX_MONEY:
            raise ValueError("Amount invested must be between 0 and 10 lakh crore rupees.")
        money = q_money(inv)
    elif avg is not None:
        if avg < 0 or avg * uq > MAX_MONEY:
            raise ValueError("Average cost per unit must be 0 or more, and the total below 10 lakh crore rupees.")
        money = q_money(avg * uq)
    d, why_d = parse_date(bought_on, today)
    if why_d:
        raise ValueError(f"Purchase date: {why_d}.")
    return uq, money, d
