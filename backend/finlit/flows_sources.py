"""FII / DII institutional flows: the permitted official sources and their parsers. Each parser takes the raw answer and returns plain values;
nothing here touches the network or the database (finlit/flows.py does that), so every rule is tested against recorded answers
(tests/fixtures/flows).

Sources (all public, no key, plain GET or the site's own date form, honest User-Agent, no robots.txt rule against any of these paths):
  NSDL FPI Monitor     https://www.fpi.nsdl.co.in    FPI (FII) daily trends: Latest.aspx (latest reporting day), Monthly.aspx (the month so far) and
                                                     Archive.aspx (the site's own "To Date" form: every reporting day of that month up to the date,
                                                     back to 2008). Equity, debt, hybrid, mutual funds, AIFs, in Rs crore and US$ million.
  NSDL DII report      https://www.fpi.nsdl.co.in    Users/DIIGenerateReport.aspx?Rep=L (latest) and ?Rep=A (the "Enter Date" form, one day): domestic
                                                     institutions (banks, insurance, mutual funds, AIFs, others) by instrument and route. NSDL began
                                                     publishing it on 1 June 2026; there is nothing earlier.
  NSE archive files    https://archives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv   participant-wise open interest in equity
                                                     derivatives (Client, DII, FII, Pro), contracts, one plain CSV per trading day.
Equity flows are the STOCK EXCHANGE route (secondary market, buy/sell on the exchanges), the figure that compares with the exchanges' own FII/DII
cash-market reports; the primary-market route (IPO/QIP allotments, off-market) is kept apart and only appears inside the all-asset FPI view.
Anything that cannot be read is skipped, never guessed.
"""
from __future__ import annotations

import csv
import html as htmllib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE_CELL = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
MAX_CRORE = 150_000.0       # no single day's flow of one investor class is anywhere near this: larger means a misread cell
TOLERANCE = 0.15            # published net = gross purchases - gross sales; two decimals now, one decimal in the older years: a rounding step either way is fine


def parse_date(s: str) -> Optional[date]:
    m = DATE_CELL.match((s or "").strip())
    if not m or m.group(2).lower() not in MON:
        return None
    try:
        return date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def num(v) -> Optional[float]:
    """'(9569.57)' is -9569.57; blanks and dashes are not a number."""
    s = htmllib.unescape(str(v or "")).replace("\xa0", " ").replace(",", "").strip()
    if s in ("", "-", "--", "NA", "N.A.", "nil", "Nil"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip().removeprefix("Rs.").strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def _cells(row: str) -> List[str]:
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I):
        c = re.sub(r"<[^>]+>", " ", c)
        out.append(re.sub(r"\s+", " ", htmllib.unescape(c).replace("\xa0", " ")).strip())
    return out


def _rows(page: str) -> List[List[str]]:
    return [c for c in (_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)) if c]


@dataclass
class Leg:
    buy: Optional[float]
    sell: Optional[float]
    net: Optional[float]
    usd: Optional[float] = None

    def ok(self) -> bool:
        if self.buy is None or self.sell is None or self.net is None:
            return False
        return (0 <= self.buy <= MAX_CRORE and 0 <= self.sell <= MAX_CRORE and abs(self.net) <= MAX_CRORE
                and abs((self.buy - self.sell) - self.net) <= TOLERANCE)


def _leg(c: List[str]) -> Optional[Leg]:
    if len(c) < 3:
        return None
    return Leg(num(c[0]), num(c[1]), num(c[2]), num(c[3]) if len(c) > 3 else None)


# ------------------------------------------------------------------------------------------------ NSDL: FPI (FII)
@dataclass
class FpiDay:
    d: date
    equity: Optional[Leg] = None            # stock-exchange route
    equity_primary: Optional[Leg] = None
    equity_total: Optional[Leg] = None      # sub-total: both routes
    debt_net: Optional[float] = None        # sub-totals of Debt (general limit, VRR, FAR), both routes
    hybrid_net: Optional[float] = None
    mf_net: Optional[float] = None
    aif_net: Optional[float] = None
    total: Optional[Leg] = None
    rate: Optional[float] = None            # rupees per US dollar NSDL converted at
    problems: List[str] = field(default_factory=list)


def _group(name: str) -> Optional[str]:
    n = name.lower()
    if n == "equity":
        return "equity"
    if n.startswith("debt"):
        return "debt"
    if n == "hybrid":
        return "hybrid"
    if n.startswith("mutual fund"):
        return "mf"
    if n.startswith("aif"):
        return "aif"
    return None


def parse_fpi(page: str) -> List[FpiDay]:
    """Every reporting day in an NSDL 'Daily Trends in FPI Investments' table (Latest, Monthly or Archive page), oldest first.
    The derivative-trades table that follows on the Latest page is not read. A day whose equity stock-exchange row is missing or does
    not add up (net != purchases - sales) is returned with `equity` None and the reason in `problems`."""
    start = page.find("Daily Trends in FPI Investments")
    if start < 0:
        return []
    end = page.find("Daily Trends in FPI Derivative", start)
    days: List[FpiDay] = []
    cur: Optional[FpiDay] = None
    group = route = None
    debt: Dict[str, float] = {}

    def close():
        nonlocal cur, debt
        if cur is not None:
            cur.debt_net = round(sum(debt.values()), 2) if debt else None
            if cur.equity is not None and not cur.equity.ok():
                cur.problems.append(f"equity stock-exchange row does not add up: {cur.equity}")
                cur.equity = None
            if cur.equity_total is not None and not cur.equity_total.ok():
                cur.equity_total = None
            if cur.total is not None and not cur.total.ok():
                cur.total = None
            days.append(cur)
        cur, debt = None, {}

    for c in _rows(page[start:end if end > 0 else len(page)]):
        d = parse_date(c[0])
        if d is not None and len(c) >= 7:
            close()
            cur = FpiDay(d)
            if len(c) >= 8 and num(c[2]) is None:                       # date, group, route, 4 figures, rate
                group, route, fig = _group(c[1]), c[2], c[3:8]
            else:                                                       # the 2008 layout: no route column
                group, route, fig = _group(c[1]), None, c[2:7]
            rate = num(fig[4]) if len(fig) > 4 else None
            if rate is not None:
                cur.rate = rate
            _store(cur, group, route, fig[:4], debt)
        elif cur is None:
            continue
        elif c[0].lower() == "total" and len(c) >= 4:
            cur.total = _leg(c[1:5])
        elif len(c) >= 6 and c[0] and num(c[0]) is None:                # group, route, 4 figures
            group, route = _group(c[0]), c[1]
            _store(cur, group, route, c[2:6], debt)
        elif len(c) >= 5 and num(c[0]) is None:                         # route, 4 figures (same group as the row above)
            route = c[0]
            _store(cur, group, route, c[1:5], debt)
    close()
    return [x for x in days if x.d]


def _store(day: FpiDay, group: Optional[str], route: Optional[str], fig: List[str], debt: Dict[str, float]) -> None:
    leg = _leg(fig)
    if leg is None or group is None:
        return
    r = (route or "").lower()
    sub = r in ("sub-total", "subtotal")
    if group == "equity":
        if r == "stock exchange":
            day.equity = leg
        elif r.startswith("primary"):
            day.equity_primary = leg
        elif sub or route is None:
            day.equity_total = leg
    elif sub and leg.net is not None:
        if group == "debt":
            debt[f"debt{len(debt)}"] = leg.net
        elif group == "hybrid":
            day.hybrid_net = leg.net
        elif group == "mf":
            day.mf_net = leg.net
        elif group == "aif":
            day.aif_net = leg.net


def fpi_header_date(page: str) -> Optional[date]:
    """The date in 'Daily Trends in FPI Investments on 23-Oct-2026' (Latest) or '... up to 15-Jan-2021' (Archive)."""
    m = re.search(r"Daily Trends in FPI Investments\s+(?:on|up\s*to|upto)\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", re.sub(r"\s+", " ", page), re.I)
    return parse_date(m.group(1)) if m else None


# ------------------------------------------------------------------------------------------------ NSDL: DII
@dataclass
class DiiDay:
    d: date
    equity: Leg                                   # all DII, equity, stock-exchange route
    by_type: Dict[str, Leg]                       # Bank, Insurance, MFs, AIFs, Others
    rate: Optional[float] = None
    problems: List[str] = field(default_factory=list)


def parse_dii(page: str) -> Optional[DiiDay]:
    """The NSDL 'DII Report on <date>': the 'Total / Equity / Stock Exchange' row, cross-checked against the sum of the investor types.
    None when the page says 'No Data Found' (holiday, or not yet published) or is not a DII report."""
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    m = re.search(r"DII Report on (\d{1,2}-[A-Za-z]{3}-\d{4})", flat)
    if not m:
        return None
    d = parse_date(m.group(1))
    if d is None:
        return None
    rate = re.search(r"Conversion\s*\(1 USD TO INR\)\s*:\s*([\d.]+)", flat)
    total: Optional[Leg] = None
    by_type: Dict[str, Leg] = {}
    for c in _rows(page):
        if len(c) >= 7 and c[1] == "Equity" and c[2] == "Stock Exchange":
            leg = _leg(c[3:7])
            if c[0] == "Total":
                total = leg
            elif c[0] and leg is not None:
                by_type[c[0]] = leg
    if total is None or not total.ok():
        return None
    out = DiiDay(d, total, by_type, float(rate.group(1)) if rate else None)
    if by_type:                                       # the published total is the sum of the investor types: a mismatch means a misread table
        for name, attr in (("buy", "buy"), ("sell", "sell"), ("net", "net")):
            s = round(sum(getattr(v, attr) or 0 for v in by_type.values()), 2)
            if abs(s - (getattr(total, attr) or 0)) > 0.5:
                out.problems.append(f"investor types add up to {s} {name}, the report's total says {getattr(total, attr)}")
    return out


# ------------------------------------------------------------------------------------------------ NSE: participant-wise open interest
PARTICIPANTS = {"client": "Client", "dii": "DII", "fii": "FII", "pro": "Pro"}
INSTRUMENTS = ["Index Futures", "Index Options", "Stock Futures", "Stock Options"]


@dataclass
class OiDay:
    d: date
    rows: Dict[tuple, tuple]                      # (participant, instrument) -> (long, short) contracts


def _oi_date(title: str) -> Optional[date]:
    m = re.search(r"as on\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", title)
    if not m or m.group(1)[:3].lower() not in MON:
        return None
    try:
        return date(int(m.group(3)), MON[m.group(1)[:3].lower()], int(m.group(2)))
    except ValueError:
        return None


def parse_participant_oi(text: str) -> Optional[OiDay]:
    """NSE's fao_participant_oi CSV. Index/stock futures: long and short open contracts. Options: calls and puts held long added together,
    and held short added together (the file gives each leg; the sum is what a participant is long or short in contracts)."""
    lines = [l for l in text.replace("\r", "").split("\n") if l.strip()]
    if len(lines) < 3 or "Participant wise Open Interest" not in lines[0]:
        return None
    d = _oi_date(lines[0])
    if d is None:
        return None
    head = [h.strip().lower() for h in next(csv.reader([lines[1]]))]
    need = ["future index long", "future index short", "future stock long", "future stock short", "option index call long", "option index put long",
            "option index call short", "option index put short", "option stock call long", "option stock put long", "option stock call short", "option stock put short"]
    if not head or any(n not in head for n in need):
        return None
    ix = {n: head.index(n) for n in need}
    rows: Dict[tuple, tuple] = {}
    for line in lines[2:]:
        c = next(csv.reader([line]))
        who = PARTICIPANTS.get(c[0].strip().lower())
        if not who:
            continue
        v = {n: num(c[i]) if i < len(c) else None for n, i in ix.items()}

        def pair(a, b):
            return None if a is None or b is None else (int(a), int(b))
        rows[(who, "Index Futures")] = pair(v["future index long"], v["future index short"])
        rows[(who, "Stock Futures")] = pair(v["future stock long"], v["future stock short"])
        for inst, k in (("Index Options", "option index"), ("Stock Options", "option stock")):
            lc, lp, sc, sp = v[k + " call long"], v[k + " put long"], v[k + " call short"], v[k + " put short"]
            rows[(who, inst)] = None if None in (lc, lp, sc, sp) else (int(lc + lp), int(sc + sp))
    return OiDay(d, {k: v for k, v in rows.items() if v is not None}) if rows else None
