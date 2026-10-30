"""Exit-load text -> points by the step table of spec Section 6.3.

Read the text for the highest load percentage L and the longest holding period D in days, then apply the first rule that fits:
  Nil, or no exit load                100
  load only for D <= 7 days            90
  load only for D <= 30 days           80
  D <= 365 days and L <= 1%            60
  D <= 365 days and L > 1%             30
  D > 365 days                         10
  cannot be read                       None (state F: never a guess)
A load above 0% with no holding period, or with D = 0, is unreadable. A percentage that is a free allowance ("up to 10% of units can be redeemed
without load") is not a load and is ignored."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "fifteen": 15, "eighteen": 18, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(_WORDS) + r")"
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s*cent|percent)", re.I)
_PERIOD = re.compile(_NUM + r"\s*(?:-\s*)?(days?|weeks?|months?|years?|yrs?|yr)\b", re.I)
_NIL = re.compile(r"\b(nil|no\s+exit\s+load|no\s+load|not\s+applicable|zero)\b", re.I)
_ALLOWANCE = re.compile(r"(?:of|upto|up\s+to)\s+(?:the\s+)?(?:units|investment|allotted\s+units|amount|holding)|(?:units|investment)\s*\)?\s*(?:can|may|are|is)\b", re.I)


@dataclass(frozen=True)
class ExitLoad:
    points: Optional[int]       # None: unreadable (state F)
    load: Optional[float]       # highest percentage L
    days: Optional[int]         # longest holding period D
    rule: str                   # which row of the table fired, or why it could not be read


def _num(s: str) -> float:
    s = s.lower()
    return float(_WORDS[s]) if s in _WORDS else float(s)


def _days(n: float, unit: str) -> int:
    u = unit.lower()
    if u.startswith("day"):
        return round(n)
    if u.startswith("week"):
        return round(n * 7)
    if u.startswith("month"):
        return round(n * 365 / 12)
    return round(n * 365)


def parse(text: Optional[str]) -> ExitLoad:
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return ExitLoad(None, None, None, "no text")
    t = re.sub(r"^\W*(?:entry\s*load\s*[:\-]?\s*(?:nil|not applicable|n\.?a\.?)\s*[,;.]?\s*)?exit\s*load\s*[:\-]?\s*", "", t, flags=re.I).strip() or t
    loads = []
    for m in _PCT.finditer(t):
        tail = t[m.end(): m.end() + 40]
        if _ALLOWANCE.match(tail.strip()) or re.match(r"\s*(?:of|upto|up to)\s+(?:the\s+)?(?:units|investment)", tail, re.I):
            continue   # a free allowance, not a load
        loads.append(float(m.group(1)))
    periods = [_days(_num(m.group(1)), m.group(2)) for m in _PERIOD.finditer(t)]
    if loads and max(loads) > 0:
        L = max(loads)
        D = max(periods) if periods else None
        if not D:
            return ExitLoad(None, L, D, "a load with no holding period")
        if D <= 7:
            return ExitLoad(90, L, D, "load only for 7 days or less")
        if D <= 30:
            return ExitLoad(80, L, D, "load only for 30 days or less")
        if D <= 365:
            return ExitLoad(60 if L <= 1 else 30, L, D, "within a year, load at most 1%" if L <= 1 else "within a year, load above 1%")
        return ExitLoad(10, L, D, "holding period above a year")
    if _NIL.search(t) or (loads and max(loads) == 0):
        return ExitLoad(100, 0.0, None, "nil")
    return ExitLoad(None, None, None, "text not readable")
