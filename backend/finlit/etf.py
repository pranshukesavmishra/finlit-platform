"""ETFs: list, detail and compare for exchange-traded funds listed on NSE.

Where each figure comes from (nothing else is shown):
  * the list of ETFs and their ISINs     Upstox instrument list (NSE_EQ, instrument type EQ, ISIN starting INF)
  * prices and history                   Upstox quotes and daily candles (10 years at most, one call per ETF)
  * NAV, registered name, fund house     AMFI's NAVAll.txt, matched by ISIN only
Upstox does NOT publish AUM, expense ratio, tracking error, holdings, benchmark, launch date or fund manager, so the pages say so instead of
showing a made-up or empty number. Every figure derived from prices is "price return": dividends are not included.

Hot and cold (migration 038): the 100 ETFs with the highest traded value (average of close x volume over 20 sessions, from Upstox candles) are
"hot": their 10-year packed history stays in Postgres and their ready-made list rows are in the etf_hot table and in Redis. Every other ETF is
"cold": its narrow row (price, 1-day / 1-year / 5-year and the other figures, computed every night from the full 10 years) still covers
lists, sorts and filters, but its candle history is fetched from Upstox when somebody opens it and cached in Redis for 14 days.

Honesty rules the code enforces:
  * a price series with a day-to-day move beyond +/-40% (an unadjusted split, a face-value change, a bad tick) or with repeated dates is
    treated as unreliable BEFORE the last such day: figures that would need earlier prices are withheld with the reason, never computed;
  * a return needs a price on or before the look-back date (within 10 days); a young ETF shows "Listed less than N years";
  * the nightly job only adds and updates rows. A short or empty provider answer, an expired token or a shrunken instrument list leaves the
    stored rows exactly as they were.
"""

from __future__ import annotations

import asyncio
import calendar
import codecs
import json
import logging
import math
import re
import statistics
import time
import zlib
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import quote as urlquote

import httpx
from fastapi import APIRouter, Request, Response

from .auth.routes import fail
from .upstox import UpstoxClient, UpstoxError, UpstoxTokenExpired

log = logging.getLogger("finlit.etf")
router = APIRouter(prefix="/api/etf")

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
IST = timezone(timedelta(hours=5, minutes=30))
QUOTE_BATCH = 200            # Upstox accepts up to 500 keys per quote call; 200 keeps the URL short
BREAK_MOVE = 0.40            # a one-day move beyond this is a split or a bad price, not a market move (ETFs have 20% circuit limits)
GAP_DAYS = 10                # a look-back price must exist within this many days before the target date
MIN_VOL_DAYS = 150           # trading days needed in the last year for a volatility figure
SHRINK_LIMIT = 0.80          # refuse to touch the list when fewer than this share of the stored ETFs came back
MIN_INSTRUMENTS = 100        # ... or when fewer than this many came back at all
FULL_EVERY_DAYS = 7          # the whole 10 years are re-fetched about weekly; the other nights only add the last weeks
TAIL = 260                   # sessions of daily high/low kept (52-week range)
PREMIUM_LIMIT = 100.0        # a price more than this far from the NAV is certainly the wrong day or unit, so no premium is shown (wide gaps below it are real: overseas ETFs)
PREMIUM_NOTE = 10.0          # beyond this gap the page adds a plain note
HOT_N = 100                  # ETFs kept ready (ranked by traded value)
HIST_TTL = 14 * 86400        # a cold ETF's chart history stays in Redis this long after it was last fetched
DATA_TTL = 25 * 3600         # the nightly job rewrites the Redis copies; a missed night still serves yesterday's for a day
ALL_KEY, HOT_KEY = "etf:all:v1", "etf:hot:v1"
DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns."
SOURCE = "Prices: NSE via Upstox. NAV, scheme names and fund houses: AMFI."
NOT_PUBLISHED = "Not published in our price data source"
UNAVAILABLE = ["Assets under management (AUM)", "Expense ratio", "Tracking error", "Holdings", "Benchmark index", "Launch date", "Fund manager"]

# ---------------------------------------------------------------------------------------------------------------- categories
# Ordered, first match wins, matched against upper-case text with every run of other characters turned into one space.
# Anything that does not match stays unclassified ("—"). The words come from the real list of 355 ETFs and are checked in tests.
_CATS: List[Tuple[str, str, str, str]] = [
    # key, label, asset class, pattern
    ("hybrid", "Equity and debt blend", "hybrid", r"HYBRID|MOMENTUM \d+ PLUS"),
    ("liquid", "Liquid / overnight", "debt", r"LIQ|1D RATE|OVERNIGHT"),
    ("gsec", "G-Sec / gilt", "debt", r"(?:^| )G SEC|GSEC|GILT|GOVT SEC"),
    ("bond", "Other bond", "debt", r"AAA BOND|SDL|CORPORATE BOND|TARGET MATURITY|BHARAT BOND|BBETF"),
    ("gold", "Gold", "gold", r"GOLD"),
    ("silver", "Silver", "silver", r"SILV"),
    ("intl", "International", "international", r"S P 500|NASDAQ|NYSE|FANG|HANG ?SENG|HNGSNG|MAHKTECH|MAFANG|MASPTOP|MON100|MONQ50"),
    ("psu_bank", "PSU bank", "equity", r"PSU ?BA?N?K|PSBK|BANK ?PSU"),
    ("pvt_bank", "Private bank", "equity", r"PVT ?B|PRIVATE B"),
    ("financial", "Financial services", "equity", r"FINANCIAL|BFSI|FINIETF|ICICIFIN|CAPITAL MARKET|INSUR"),
    ("bank", "Bank", "equity", r"BANK|BNK|BKETF"),
    ("ev", "EV and new-age auto", "equity", r"(?:^| )EV(?: |$)|NEW AGE AUTO|EVIETF|EVINDIA|GROWWEV"),
    ("auto", "Auto", "equity", r"AUTO"),
    ("health", "Healthcare and pharma", "equity", r"PHARMA|HEALTH|HOSPI"),
    ("it", "IT", "equity", r"(?:^| )(?:IT|IT(?:BEES|ETF|BETA|AXIS|ADD|IETF)|[A-Z]*(?:ETFIT|NIFIT|KOTAKIT|DSPIT))(?: |$)"),
    ("internet", "Internet and digital", "equity", r"INTERNET|DIGITAL|GROWWNET"),
    ("fmcg", "FMCG", "equity", r"FMCG"),
    ("consumption", "Consumption", "equity", r"CONSUM|(?:^| )CONS(?: |$)"),
    ("metal", "Metal", "equity", r"METAL"),
    ("commodities", "Commodities", "equity", r"COMMO"),
    ("energy", "Energy, oil and gas", "equity", r"ENERGY|OIL ?(?:AND )?GAS|OILIETF|OILGAS"),
    ("power", "Power", "equity", r"POWER"),
    ("infra", "Infrastructure", "equity", r"INFRA"),
    ("psu", "PSU / PSE", "equity", r"CPSE|PSE|RAILWAY|(?:^| )PSU(?: |$)"),
    ("realty", "Realty", "equity", r"REALTY|RLTY"),
    ("chemicals", "Chemicals", "equity", r"CHEM"),
    ("defence", "Defence", "equity", r"DEFEN"),
    ("manufacturing", "Manufacturing", "equity", r"MANUF|MFG|MAKE ?IN ?INDIA|MAKEINDIA"),
    ("theme", "Other themes", "equity", r"TOUR|IPO|MNC|SERVICE"),
    ("factor", "Factor / strategy", "equity", r"MOMENTUM|ALPHA|QUALITY|QLITY|VALUE|NV20|LOW ?VOL|LOVOL|EQUAL|DIVID|DIVOPP|SHARIAH|ESG"),
    ("sensex_next", "Sensex Next", "equity", r"SENSEX NEXT|SNXT|NEXT ?30|SENSEX NXT"),
    ("sensex", "Sensex", "equity", r"SENSEX"),
    ("next50", "Nifty Next 50", "equity", r"NEXT ?50|NXT ?50|NN50|JUNIOR"),
    ("largemid", "Large and midcap", "equity", r"LARGE ?MID|ELM250"),
    ("multicap", "Multicap", "equity", r"MULTI ?CAP"),
    ("midcap", "Midcap", "equity", r"MID ?CAP|MID ?(?:50|100|150)(?: |$)|M150"),
    ("smallcap", "Smallcap", "equity", r"SMALL|SML"),
    ("nifty50", "Nifty 50", "equity", r"NIFTY ?50(?:\b)|NIFTY ETF|NIFTY ?BEES"),
    ("broad", "Broad market", "equity", r"NIFTY ?(?:100|200|500|TOTAL)|BSE ?(?:500|200|100)|TOTAL MARKET|MSCI|TOP ?(?:20|100)(?: |$)"),
]
CATEGORIES: Dict[str, Dict[str, str]] = {k: {"key": k, "label": lab, "group": grp} for k, lab, grp, _ in _CATS}
_CAT_RE = [(k, re.compile(p)) for k, _, _, p in _CATS]
GROUPS = {"equity": "Equity", "gold": "Gold", "silver": "Silver", "debt": "Debt", "international": "International", "hybrid": "Blend"}


def _text(s: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(s or "").upper().replace("S&P", "S P").replace("&", " AND ")).strip()


def category_of(text: str) -> Optional[str]:
    """The first rule that matches this name, or None."""
    t = _text(text)
    if not t:
        return None
    for key, rx in _CAT_RE:
        if rx.search(t):
            return key
    return None


def classify(scheme_name: Optional[str], short_name: Optional[str], exchange_name: str, symbol: str) -> Optional[str]:
    """Category of an ETF, or None when the names do not say clearly.
    AMFI's registered scheme name decides when it has a rule; otherwise Upstox's short name and the exchange name + symbol must agree, or
    only one of them may speak. Two names that point to different categories mean the data is unreliable, so the answer is None."""
    a = category_of(scheme_name or "")
    if a:
        return a
    b, c = category_of(short_name or ""), category_of(f"{exchange_name} {symbol}")
    if b and c:
        return b if b == c else None
    return b or c


# ---------------------------------------------------------------------------------------------------------------- source parsing
def iter_json_array(chunks: Iterable[bytes]) -> Iterator[dict]:
    """Objects of a (possibly gzip-compressed) JSON array, one by one, so the 125,000-row instrument list is never held in memory.
    A stream that ends before the array's closing bracket (a cut-off download) raises instead of passing as a short list."""
    dec, buf, started, closed, raw, pos = json.JSONDecoder(), "", False, False, None, 0
    text_dec = codecs.getincrementaldecoder("utf-8")()
    for chunk in chunks:
        if raw is None:
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS) if chunk[:2] == b"\x1f\x8b" else False
        buf = buf[pos:] + text_dec.decode(raw.decompress(chunk) if raw else chunk)
        pos = 0
        while not closed:
            while pos < len(buf) and buf[pos] in " \r\n\t,":
                pos += 1
            if pos >= len(buf):
                break
            if not started:
                if buf[pos] != "[":
                    raise ValueError("not a JSON array")
                started, pos = True, pos + 1
                continue
            if buf[pos] == "]":
                closed = True
                break
            try:
                obj, end = dec.raw_decode(buf, pos)
            except json.JSONDecodeError:
                break                                  # the object continues in the next chunk
            if isinstance(obj, dict):
                yield obj
            pos = end
    if not closed or (raw and not raw.eof):
        raise ValueError("truncated instrument list")


def is_etf(row: dict) -> bool:
    return row.get("segment") == "NSE_EQ" and row.get("instrument_type") == "EQ" and str(row.get("isin") or "").startswith("INF") \
        and bool(row.get("trading_symbol")) and bool(row.get("instrument_key"))


def parse_amfi(text: str, isins: Iterable[str]) -> Dict[str, dict]:
    """{isin: {name, house, nav, date}} for the wanted ISINs. NAVAll.txt lists a fund house line, then its schemes, ';' separated:
    code;ISIN payout/growth;ISIN reinvestment;name;plan;option;NAV;date."""
    want, out, house = set(isins), {}, None
    for line in text.splitlines():
        t = line.strip()
        if not t:
            continue
        p = [x.strip() for x in t.split(";")]
        if len(p) >= 8 and p[0].isdigit():
            try:
                nav, d = float(p[6]), datetime.strptime(p[7], "%d-%b-%Y").date()
            except ValueError:
                continue                               # "N.A." or an unreadable date: no figure rather than a guess
            for hit in {p[1], p[2]} & want:
                if nav > 0 and (hit not in out or d > out[hit]["date"]):
                    out[hit] = {"name": p[3], "house": re.sub(r"\s*Mutual Fund\s*$", "", house or "", flags=re.I) or None, "nav": nav, "date": d}
        elif ";" not in t and not t.startswith(("Open Ended", "Close Ended", "Interval", "Scheme Code")):
            house = t
    return out


def tidy_scheme(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = re.sub(r"\s+", " ", name).strip()
    n = re.sub(r"\s*-\s*(?:Growth|IDCW|Dividend)(?:\s+(?:Option|Plan))?\s*$", "", n, flags=re.I)
    return n or None


def display_name(scheme: Optional[str], short: Optional[str], exchange: str) -> str:
    s, sh = tidy_scheme(scheme), (short or "").strip() or None
    if s and not (s == s.upper() and sh):             # AMFI sometimes sends the whole name in capitals; Upstox's short name reads better then
        return s
    return sh or s or re.sub(r"^.*?AMC\s*-\s*|^QUANT_AMC\s*-\s*", "", exchange).strip() or exchange


def ist_date(ms: Any) -> Optional[date]:
    try:
        v = int(ms)
        return datetime.fromtimestamp(v / 1000, IST).date() if v > 0 else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# ---------------------------------------------------------------------------------------------------------------- price series
def parse_candles(rows: Any) -> Tuple[List[tuple], Optional[date]]:
    """Upstox daily candles [timestamp, o, h, l, c, volume, oi] (newest first) -> ([(date, o, h, l, c, v)] oldest first, last repeated date).
    Rows that are not usable (no close, close <= 0) are dropped; a high/low that does not contain the open and close is widened to."""
    seen: Dict[date, tuple] = {}
    dup: Optional[date] = None
    for r in rows if isinstance(rows, list) else []:
        try:
            d = date.fromisoformat(str(r[0])[:10])
            o, h, l, c = (float(r[i]) for i in (1, 2, 3, 4))
            v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
        except (TypeError, ValueError, IndexError):
            continue
        if not all(math.isfinite(x) for x in (o, h, l, c, v)) or c <= 0 or o <= 0:
            continue
        h, l = max(h, o, c), min(l if l > 0 else c, o, c)
        if d in seen:
            dup = max(dup, d) if dup else d
        seen[d] = (d, o, h, l, c, v)
    return [seen[d] for d in sorted(seen)], dup


def find_break(dates: Sequence[date], closes: Sequence[float], dup: Optional[date] = None) -> Optional[date]:
    """First day of the clean run at the end of the series: the latest day whose move from the day before exceeds 40%, or the latest
    repeated date. None when the whole series is clean."""
    cut: Optional[date] = dup
    for i in range(len(closes) - 1, 0, -1):
        if abs(closes[i] / closes[i - 1] - 1) > BREAK_MOVE:
            cut = max(cut, dates[i]) if cut else dates[i]
            break
    return cut


def month_back(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


PERIODS = (("1m", 1, "1 month"), ("6m", 6, "6 months"), ("1y", 12, "1 year"), ("3y", 36, "3 years"), ("5y", 60, "5 years"))
LABEL = {k: lab for k, _, lab in PERIODS}


def _lookback(dates: Sequence[date], first_ok: int, target: date) -> Tuple[Optional[int], Optional[str]]:
    """Index of the last price on or before `target`, or (None, why)."""
    i = bisect_right(dates, target) - 1
    if i < 0:
        return None, "listed"
    if i < first_ok:
        return None, "break"
    if (target - dates[i]).days > GAP_DAYS:
        return None, "sparse"
    return i, None


def drawdown(closes: Sequence[float], dates: Sequence[date]) -> Tuple[float, date, date]:
    """Largest fall from a peak to a later low, as a fraction (negative), with the peak and trough dates."""
    peak_i, worst, best_peak, best_trough = 0, 0.0, 0, 0
    for i, c in enumerate(closes):
        if c > closes[peak_i]:
            peak_i = i
        dd = c / closes[peak_i] - 1
        if dd < worst:
            worst, best_peak, best_trough = dd, peak_i, i
    return worst, dates[best_peak], dates[best_trough]


def build_metrics(dates: Sequence[date], closes: Sequence[float], highs: Sequence[float] = (), lows: Sequence[float] = (),
                  dup: Optional[date] = None, as_of: Optional[date] = None) -> dict:
    """Everything derived from the stored daily closes. Returns are percentages. `highs`/`lows` line up with the END of `dates`.
    Keys with no figure are None and `reasons[key]` says why (plain words)."""
    out: Dict[str, Any] = {k: None for k in ("ret_1m", "ret_6m", "ret_1y", "ret_3y", "ret_5y", "cagr_3y", "cagr_5y", "vol_1y", "mdd_1y", "mdd_3y", "mdd_5y",
                                             "high52", "low52", "range_from")}
    reasons: Dict[str, str] = {}
    extra: Dict[str, Any] = {}
    n = len(closes)
    out.update(first_date=dates[0] if n else None, points=n, break_date=None, reasons=reasons, extra=extra)
    if n < 2:
        reasons["all"] = "Not enough price history yet"
        return out
    brk = find_break(dates, closes, dup)
    first_ok = bisect_right(dates, brk) - 1 if brk else 0
    if brk and brk > dates[0]:
        out["break_date"] = brk
        extra["break_note"] = "Prices before %s are left out of every figure: the source shows a jump there that looks like a split or a bad price." % brk.strftime("%d %b %Y")
    else:
        first_ok = 0
    last_i, L = n - 1, dates[-1]
    if as_of and (as_of - L).days > 7:
        reasons["price"] = "Last traded on %s" % L.strftime("%d %b %Y")

    def why(label: str, code: str) -> str:
        return {"break": "Price history has a break on %s (suspected split or bad price), so this is withheld" % (brk.strftime("%d %b %Y") if brk else ""),
                "sparse": "Too few trades around the start of this period"}.get(code, "Listed less than %s" % label)

    base: Dict[str, int] = {}
    for key, months, label in PERIODS:
        i, code = _lookback(dates, first_ok, month_back(L, months))
        if i is None:
            for k in ((f"ret_{key}",) + ((f"cagr_{key}",) if key in ("3y", "5y") else ()) + ((f"mdd_{key}",) if key in ("1y", "3y", "5y") else ()) + (("vol_1y",) if key == "1y" else ())):
                reasons[k] = why(label, code)
            continue
        base[key] = i
        out[f"ret_{key}"] = (closes[last_i] / closes[i] - 1) * 100
        if key in ("3y", "5y"):
            years = (L - dates[i]).days / 365.25
            out[f"cagr_{key}"] = ((closes[last_i] / closes[i]) ** (1 / years) - 1) * 100 if years > 0 else None
        if key in ("1y", "3y", "5y"):
            dd, pk, tr = drawdown(closes[i:], dates[i:])
            out[f"mdd_{key}"] = dd * 100
            extra[f"mdd_{key}"] = {"peak": (pk).isoformat(), "trough": tr.isoformat()}
    if "1y" in base:
        i = base["1y"]
        rets = [closes[j] / closes[j - 1] - 1 for j in range(i + 1, n)]
        if len(rets) >= MIN_VOL_DAYS:
            out["vol_1y"] = statistics.stdev(rets) * math.sqrt(252) * 100
            extra["vol_days"] = len(rets)
        else:
            reasons["vol_1y"] = "Traded on only %d days in the last year" % len(rets)
    # 52-week range: daily highs and lows of the last 365 days (closing prices where no high/low is stored); a young ETF shows its range since the first usable day
    start = max(L - timedelta(days=365), dates[first_ok])
    i0 = bisect_right(dates, start - timedelta(days=1))
    hs = list(highs) + [None] * 0
    off = n - len(hs)
    win_hi = [(hs[j - off] if j >= off else closes[j]) for j in range(i0, n)]
    lo_src = list(lows)
    win_lo = [(lo_src[j - off] if j >= off and j - off < len(lo_src) else closes[j]) for j in range(i0, n)]
    if win_hi:
        out["high52"], out["low52"], out["range_from"] = max(win_hi), min(win_lo), dates[i0]
        if dates[i0] > L - timedelta(days=360):
            reasons["range"] = "Range since %s: the price history is shorter than 52 weeks" % dates[i0].strftime("%d %b %Y")
    return out


def avg_turnover(closes: Sequence[float], volumes: Sequence[float], sessions: int = 20) -> Optional[float]:
    """Average of close x volume over the last sessions (rupees traded per day); needs at least 10 sessions with trades."""
    pairs = [(c, v) for c, v in zip(closes[-len(volumes):] if volumes else [], volumes) if v > 0][-sessions:]
    return sum(c * v for c, v in pairs) / len(pairs) if len(pairs) >= 10 else None


def premium_of(dates: Sequence[date], closes: Sequence[float], nav: Optional[float], nav_date: Optional[date]) -> Tuple[Optional[float], Optional[str]]:
    """Price against NAV in percent, using the ETF's own close on the NAV's day. Never mixes two different days."""
    if not nav or not nav_date:
        return None, None
    i = bisect_right(dates, nav_date) - 1
    if i < 0 or dates[i] != nav_date:
        return None, "The ETF did not trade on the NAV date (%s)" % nav_date.strftime("%d %b %Y")
    p = (closes[i] / nav - 1) * 100
    if abs(p) > PREMIUM_LIMIT:
        return None, "Price and NAV are more than %d%% apart, so no premium or discount is shown" % PREMIUM_LIMIT
    return p, None


def weekly(dates: Sequence[date], vals: Sequence[float]) -> Tuple[List[date], List[float]]:
    """Last close of each week, keeping the very first and the very last point."""
    buckets: Dict[Tuple[int, int], int] = {}
    for i, d in enumerate(dates):
        iso = d.isocalendar()
        buckets[(iso[0], iso[1])] = i
    idx = sorted(buckets.values())
    if idx and idx[0] != 0:
        idx.insert(0, 0)
    return [dates[i] for i in idx], [vals[i] for i in idx]


RANGES = {"1M": 1, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60, "MAX": None}
DAILY_MAX = 520


def series_for(dates: Sequence[date], closes: Sequence[float], rng: str, brk: Optional[date]) -> dict:
    """Points [date, close] of one chart range, from the base price on/before the start (so the chart starts on the exact look-back day).
    `available` is False with a reason when the ETF has no clean history that far back."""
    n = len(dates)
    first_ok = (bisect_right(dates, brk) - 1) if brk else 0
    first_ok = max(first_ok, 0)
    if not n:
        return {"range": rng, "available": False, "why": "No price history", "grain": "daily", "points": []}
    months = RANGES[rng]
    if months is None:
        i0 = first_ok
    else:
        i0, code = _lookback(dates, first_ok, month_back(dates[-1], months))
        if i0 is None:
            lab = {1: "1 month", 6: "6 months", 12: "1 year", 36: "3 years", 60: "5 years"}[months]
            return {"range": rng, "available": False, "grain": "daily", "points": [],
                    "why": ("Price history has a break on %s (suspected split or bad price)" % brk.strftime("%d %b %Y")) if code == "break" and brk else
                    "Too few trades around the start of this period" if code == "sparse" else "Listed less than " + lab}
    d, c = list(dates[i0:]), list(closes[i0:])
    grain = "daily"
    if len(d) > DAILY_MAX:
        d, c = weekly(d, c)
        grain = "weekly"
    return {"range": rng, "available": True, "grain": grain, "from": d[0].isoformat(), "to": d[-1].isoformat(), "points": [[x.isoformat(), round(y, 4)] for x, y in zip(d, c)]}


def rebase(series: Dict[str, Tuple[Sequence[date], Sequence[float]]], start: date) -> Dict[str, List[list]]:
    """Each ETF's closes from `start` on, scaled so its price on (or just before) `start` is 100. Own dates are kept."""
    out: Dict[str, List[list]] = {}
    for sym, (d, c) in series.items():
        i = bisect_right(d, start) - 1
        if i < 0:
            i = 0
        base = c[i]
        pts = [(d[j], c[j] / base * 100) for j in range(i, len(d))]
        if len(pts) > DAILY_MAX:
            wd, wv = weekly([p[0] for p in pts], [p[1] for p in pts])
            pts = list(zip(wd, wv))
        out[sym] = [[x.isoformat(), round(y, 3)] for x, y in pts]
    return out


# ---------------------------------------------------------------------------------------------------------------- nightly refresh
def quote_candle(q: dict, last_candle: Optional[date], now: datetime) -> Optional[tuple]:
    """Today's candle from an Upstox quote, for the day Upstox's history has not published yet. Only when the market has closed
    (so the close is final) and only for a later day than the history's last candle."""
    d = ist_date(q.get("last_trade_time"))
    if d is None or (last_candle and d <= last_candle):
        return None
    n = now.astimezone(IST)
    if d >= n.date() and n.hour * 60 + n.minute < 15 * 60 + 45:
        return None                                    # still trading (or just closed): the price is not a close yet
    o = q.get("ohlc") or {}
    try:
        vals = [float(x) for x in (o.get("open"), o.get("high"), o.get("low"), q.get("last_price"))]
        vol = float(q.get("volume") or 0)
    except (TypeError, ValueError):
        return None
    op, hi, lo, cl = vals
    if not all(math.isfinite(x) and x > 0 for x in vals) or hi < lo:
        return None
    return (d, op, max(hi, op, cl), min(lo, op, cl), cl, vol)


def merge_series(old: Optional[dict], fresh: Sequence[tuple]) -> Tuple[List[date], List[float], List[float], List[float], List[float]]:
    """Stored series + newly fetched candles (the new ones win on the same day) -> dates, closes, and the last TAIL sessions' highs, lows, volumes."""
    rows: Dict[date, Tuple[float, float, float, float]] = {}
    if old:
        off = len(old["dates"]) - len(old["highs"])
        vols = old.get("volumes") or []
        voff = len(old["dates"]) - len(vols)
        for i, (d, c) in enumerate(zip(old["dates"], old["closes"])):
            j, k = i - off, i - voff
            rows[d] = (c, old["highs"][j] if 0 <= j < len(old["highs"]) else c, old["lows"][j] if 0 <= j < len(old["lows"]) else c, vols[k] if 0 <= k < len(vols) else 0.0)
    for d, _o, h, l, c, v in fresh:
        rows[d] = (c, h, l, v)
    ds = sorted(rows)
    return ds, [rows[d][0] for d in ds], [rows[d][1] for d in ds[-TAIL:]], [rows[d][2] for d in ds[-TAIL:]], [rows[d][3] for d in ds[-TAIL:]]


async def fetch_instruments(http: httpx.AsyncClient) -> List[dict]:
    """The ETFs of the Upstox instrument list. The file is read in pieces and only ETF rows are kept."""
    chunks: List[bytes] = []
    async with http.stream("GET", INSTRUMENTS_URL) as r:
        if r.status_code != 200:
            raise UpstoxError(f"instrument list HTTP {r.status_code}")
        async for c in r.aiter_bytes():
            chunks.append(c)
    seen, out = set(), []
    for row in iter_json_array(chunks):
        if is_etf(row) and row["trading_symbol"] not in seen:
            seen.add(row["trading_symbol"])
            out.append(row)
    return out


async def refresh(store, settings, *, transport: Optional[httpx.AsyncBaseTransport] = None, now: Optional[datetime] = None) -> dict:
    """Nightly refresh, called by `python -m finlit.worker refresh-etf`. Upsert only: see the module docstring.
    `transport` and `now` exist so tests can run it over recorded answers."""
    started = datetime.now(timezone.utc)
    now = now or started
    today = now.astimezone(IST).date()
    summary: Dict[str, Any] = {"status": "ok"}
    client = UpstoxClient(settings, getattr(store, "redis", None), transport=transport)
    if not client.enabled:
        return {"status": "skipped", "reason": "UPSTOX_ACCESS_TOKEN is not set"}
    http = httpx.AsyncClient(transport=transport, timeout=60, follow_redirects=True)
    try:
        async with store.pool.acquire() as conn:
            stored_active = await conn.fetchval("SELECT count(*) FROM etf_funds WHERE active")
            insts = await fetch_instruments(http)
            if len(insts) < MIN_INSTRUMENTS or (stored_active and len(insts) < SHRINK_LIMIT * stored_active):
                summary.update(status="refused", reason=f"the instrument list has {len(insts)} ETFs (stored: {stored_active}); nothing was changed")
                await _log_run(conn, started, summary)
                return summary
            amfi: Dict[str, dict] = {}
            try:
                r = await http.get(AMFI_URL)
                if r.status_code == 200:
                    amfi = parse_amfi(r.content.decode("utf-8", "replace"), [i["isin"] for i in insts])
                else:
                    summary["amfi"] = f"HTTP {r.status_code}: NAV and names kept as stored"
            except httpx.HTTPError as exc:
                summary["amfi"] = f"{type(exc).__name__}: NAV and names kept as stored"
            summary.update(instruments=len(insts), amfi_matched=len(amfi))
            await _upsert_meta(conn, insts, amfi)
            old_hist = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, dates, closes, highs, lows, volumes, full_at FROM etf_history")}
            old_fund = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, nav, nav_date, extra FROM etf_funds")}

            # ---- today's quotes (two calls). A missing or empty batch only means no same-day candle; it never changes a stored row.
            quotes: Dict[str, dict] = {}
            keys = [i["instrument_key"] for i in insts]
            try:
                for k in range(0, len(keys), QUOTE_BATCH):
                    data = await client.get("/v2/market-quote/quotes", {"instrument_key": ",".join(keys[k:k + QUOTE_BATCH])})
                    for q in (data.values() if isinstance(data, dict) else []):
                        if isinstance(q, dict) and q.get("instrument_token"):
                            quotes[q["instrument_token"]] = q
            except UpstoxError as exc:
                summary["quotes_error"] = str(exc)
            summary["quotes"] = len(quotes)

            sem = asyncio.Semaphore(3)
            stats: Dict[str, Any] = {"full": 0, "incremental": 0, "adjusted": 0, "kept": [], "updated": 0, "no_history": [], "quote_disagree": []}

            async def candles(key: str, frm: date):
                async with sem:
                    data = await client.get(f"/v3/historical-candle/{urlquote(key, safe='')}/days/1/{today.isoformat()}/{frm.isoformat()}")
                return parse_candles(data.get("candles") if isinstance(data, dict) else None)

            async def one(inst: dict) -> dict:
                """Fetch what this ETF needs: the whole 10 years (new ETF, weekly, or after a provider adjustment) or just the last weeks."""
                sym, key, old = inst["trading_symbol"], inst["instrument_key"], old_hist.get(inst["trading_symbol"])
                res: Dict[str, Any] = {"inst": inst, "old": old, "fresh": None, "dup": None, "full": False}
                try:
                    full_due = old is None or (now - old["full_at"]).days >= FULL_EVERY_DAYS or (today - old["dates"][-1]).days > 30
                    if not full_due:
                        fresh, dup = await candles(key, old["dates"][-1] - timedelta(days=40))
                        had = dict(zip(old["dates"][-60:], old["closes"][-60:]))
                        if any(d in had and abs(c / had[d] - 1) > 0.005 for d, _o, _h, _l, c, _v in fresh):
                            full_due = True                        # the provider changed prices we already hold (split or adjustment)
                            stats["adjusted"] += 1
                        else:
                            res.update(fresh=fresh, dup=dup)
                            stats["incremental"] += 1
                    if full_due:
                        fresh, dup = await candles(key, today - timedelta(days=3650))
                        stats["full"] += 1
                        if old and len(fresh) < SHRINK_LIMIT * len(old["dates"]):
                            stats["kept"].append(sym)              # a short answer: keep what is stored
                        elif fresh:
                            res.update(fresh=fresh, dup=dup, full=True)
                except UpstoxTokenExpired:
                    raise
                except UpstoxError as exc:
                    log.info("etf %s: %s", sym, exc)
                    stats["kept"].append(sym)
                return res

            try:
                results = await asyncio.gather(*[one(i) for i in insts])
            except UpstoxTokenExpired:
                summary.update(status="token_expired", reason="Upstox access token expired during the run: stored rows kept")
                await _log_run(conn, started, summary)
                return summary

            kept_hist: Dict[str, tuple] = {}                       # fresh series by symbol, written below for the hot ETFs only
            for res in results:
                inst, old, fresh = res["inst"], res["old"], res["fresh"]
                sym = inst["trading_symbol"]
                if fresh is None and old is None:
                    stats["no_history"].append(sym)
                    continue
                cands = list(fresh or [])
                last_known = max([c[0] for c in cands] + ([old["dates"][-1]] if old and not res["full"] else []))
                q = quotes.get(inst["instrument_key"])
                qc = quote_candle(q, last_known, now) if q else None
                if qc:
                    cands.append(qc)
                ds, cs, hs, ls, vs = merge_series(None if res["full"] else old, cands)
                if len(ds) < 2:
                    stats["no_history"].append(sym)
                    continue
                if q and not qc:                                   # the quote's price must agree with the stored close of the same day
                    ld, px = ist_date(q.get("last_trade_time")), _num(q.get("last_price"))
                    if ld in ds and px and abs(px / cs[ds.index(ld)] - 1) > 0.005:
                        stats["quote_disagree"].append(sym)
                prev_dup = (_jsond(old_fund.get(sym, {}).get("extra")).get("dup"))
                if res["full"]:
                    dup = res["dup"]
                else:                                              # a repeated date seen on an earlier night still counts
                    dup = max([x for x in (res["dup"], date.fromisoformat(prev_dup) if prev_dup else None) if x], default=None)
                m = build_metrics(ds, cs, hs, ls, dup, today)
                if dup:
                    m["extra"]["dup"] = dup.isoformat()
                a = amfi.get(inst["isin"])
                nav, nav_date = (a["nav"], a["date"]) if a else (old_fund.get(sym, {}).get("nav"), old_fund.get(sym, {}).get("nav_date"))
                prem, why = premium_of(ds, cs, nav, nav_date)
                if why:
                    m["reasons"]["nav_premium"] = why
                await _write_row(conn, sym, ds, cs, vs, m, nav, nav_date, prem)
                kept_hist[sym] = (ds, cs, hs, ls, vs, res["full"])
                stats["updated"] += 1
            # ETFs that left the list are marked inactive (never deleted), and only because the list passed the size check above
            await conn.execute("UPDATE etf_funds SET active = false, updated_at = now() WHERE active AND NOT (symbol = ANY($1::text[]))", [i["trading_symbol"] for i in insts])
            hot = await rank_hot(conn)
            for sym in hot:                                        # packed history is kept for the hot ETFs only
                if sym in kept_hist:
                    await _write_hist(conn, sym, *kept_hist[sym])
            summary["pruned_history"] = int((await conn.execute("DELETE FROM etf_history WHERE NOT (symbol = ANY($1::text[]))", list(hot))).split()[-1])
            summary["hot"] = len(hot)
            summary["cold_cached"] = await _refresh_cold_cache(store, kept_hist, hot)
            await publish(store, conn)
            summary.update(stats, calls=client.calls)
            if stats["kept"] or stats["no_history"] or not quotes:
                summary["status"] = "partial"
            await _log_run(conn, started, summary)
    except UpstoxTokenExpired:
        summary.update(status="token_expired", reason="Upstox access token expired: stored rows kept")
    except (UpstoxError, httpx.HTTPError, ValueError) as exc:
        summary.update(status="failed", reason=f"{type(exc).__name__}: {exc}; stored rows kept")
        log.warning("etf refresh failed: %s", exc)
    finally:
        await client.aclose()
        await http.aclose()
    return summary


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _jsond(v: Any) -> dict:
    v = json.loads(v) if isinstance(v, str) else v
    return v if isinstance(v, dict) else {}


async def _log_run(conn, started: datetime, summary: dict) -> None:
    slim = {k: (v if not isinstance(v, list) else {"count": len(v), "sample": v[:10]}) for k, v in summary.items() if k != "status"}
    await conn.execute("INSERT INTO etf_runs(started_at, status, detail) VALUES($1, $2, $3::jsonb)", started, summary.get("status", "ok"), json.dumps(slim, default=str))
    await conn.execute("DELETE FROM etf_runs WHERE id NOT IN (SELECT id FROM etf_runs ORDER BY id DESC LIMIT 60)")


async def _upsert_meta(conn, insts: List[dict], amfi: Dict[str, dict]) -> None:
    rows = []
    for i in insts:
        a = amfi.get(i["isin"])
        scheme = a["name"] if a else None
        short = (i.get("short_name") or "").strip() or None
        cat = classify(scheme, short, i.get("name") or "", i["trading_symbol"])
        rows.append((i["trading_symbol"], i["isin"], i["instrument_key"], i.get("name") or i["trading_symbol"], short, scheme, a["house"] if a else None,
                     display_name(scheme, short, i.get("name") or i["trading_symbol"]), cat, CATEGORIES[cat]["group"] if cat else None))
    await conn.executemany(
        """INSERT INTO etf_funds (symbol, isin, instrument_key, exchange_name, short_name, scheme_name, fund_house, display_name, category, asset_class)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
           ON CONFLICT (symbol) DO UPDATE SET isin = EXCLUDED.isin, instrument_key = EXCLUDED.instrument_key, exchange_name = EXCLUDED.exchange_name,
             short_name = EXCLUDED.short_name, scheme_name = COALESCE(EXCLUDED.scheme_name, etf_funds.scheme_name),
             fund_house = COALESCE(EXCLUDED.fund_house, etf_funds.fund_house),
             display_name = CASE WHEN EXCLUDED.scheme_name IS NULL AND etf_funds.scheme_name IS NOT NULL THEN etf_funds.display_name ELSE EXCLUDED.display_name END,
             category = CASE WHEN EXCLUDED.scheme_name IS NULL AND etf_funds.scheme_name IS NOT NULL THEN etf_funds.category ELSE EXCLUDED.category END,
             asset_class = CASE WHEN EXCLUDED.scheme_name IS NULL AND etf_funds.scheme_name IS NOT NULL THEN etf_funds.asset_class ELSE EXCLUDED.asset_class END,
             active = true, updated_at = now()""", rows)


async def _write_row(conn, sym, ds, cs, vs, m, nav, nav_date, prem) -> None:
    prev = cs[-2]
    last_vol = vs[-1] if vs and vs[-1] > 0 else None
    turnover = avg_turnover(cs, vs)
    change: Optional[float] = (cs[-1] / prev - 1) * 100         # exactly the last two stored closes
    if m.get("break_date") == ds[-1]:                            # the newest move is itself the suspected split / bad price
        change = None
        m["reasons"]["change"] = "Price jumped by more than %d%% on %s (suspected split or bad price), so the 1-day change is withheld" % (BREAK_MOVE * 100, ds[-1].strftime("%d %b %Y"))
    await conn.execute(
        """UPDATE etf_funds SET price=$2, prev_close=$3, change_pct=$4, price_date=$5, volume=$6, avg_turnover=$7,
             ret_1m=$8, ret_6m=$9, ret_1y=$10, ret_3y=$11, ret_5y=$12, cagr_3y=$13, cagr_5y=$14, vol_1y=$15, mdd_1y=$16, mdd_3y=$17, mdd_5y=$18,
             high52=$19, low52=$20, range_from=$21, first_date=$22, points=$23, break_date=$24, reasons=$25::jsonb, extra=$26::jsonb,
             nav=$27, nav_date=$28, nav_premium=$29, updated_at=now() WHERE symbol=$1""",
        sym, cs[-1], prev, change, ds[-1], int(last_vol) if last_vol else None, turnover,
        m["ret_1m"], m["ret_6m"], m["ret_1y"], m["ret_3y"], m["ret_5y"], m["cagr_3y"], m["cagr_5y"], m["vol_1y"], m["mdd_1y"], m["mdd_3y"], m["mdd_5y"],
        m["high52"], m["low52"], m["range_from"], m["first_date"], m["points"], m["break_date"], json.dumps(m["reasons"]), json.dumps(m["extra"]),
        nav, nav_date, prem)


async def _write_hist(conn, sym, ds, cs, hs, ls, vs, full: bool) -> None:
    await conn.execute(
        """INSERT INTO etf_history (symbol, dates, closes, highs, lows, volumes, full_at) VALUES ($1,$2,$3,$4,$5,$6, now())
           ON CONFLICT (symbol) DO UPDATE SET dates=EXCLUDED.dates, closes=EXCLUDED.closes, highs=EXCLUDED.highs, lows=EXCLUDED.lows,
             volumes=EXCLUDED.volumes, full_at = CASE WHEN $7 THEN now() ELSE etf_history.full_at END, updated_at = now()""",
        sym, ds, cs, hs, ls, vs, full)


async def rank_hot(conn) -> List[str]:
    """Rank the active ETFs by average traded value (close x volume, 20 sessions) and mark the top HOT_N hot. Returns the hot symbols, most traded first.
    An ETF without a traded-value figure is never hot."""
    async with conn.transaction():
        await conn.execute("UPDATE etf_funds SET turnover_rank = NULL, hot = false WHERE turnover_rank IS NOT NULL OR hot")
        await conn.execute(
            """WITH r AS (SELECT symbol, row_number() OVER (ORDER BY avg_turnover DESC, symbol) AS rn FROM etf_funds WHERE active AND avg_turnover IS NOT NULL)
               UPDATE etf_funds f SET turnover_rank = r.rn::int, hot = r.rn <= $1 FROM r WHERE f.symbol = r.symbol""", HOT_N)
        return [r["symbol"] for r in await conn.fetch("SELECT symbol FROM etf_funds WHERE hot ORDER BY turnover_rank")]


def _pack_hist(ds: Sequence[date], cs: Sequence[float]) -> bytes:
    return zlib.compress(json.dumps({"d": [d.isoformat() for d in ds], "c": list(cs)}, separators=(",", ":")).encode(), 6)


def _unpack_hist(raw: bytes) -> Optional[dict]:
    try:
        o = json.loads(zlib.decompress(raw))
        ds, cs = [date.fromisoformat(x) for x in o["d"]], [float(x) for x in o["c"]]
        return {"dates": ds, "closes": cs} if len(ds) == len(cs) and len(ds) > 1 else None
    except (ValueError, KeyError, TypeError, zlib.error):
        return None


async def _refresh_cold_cache(store, series: Dict[str, tuple], hot: Sequence[str]) -> int:
    """A cold ETF somebody opened lately has its chart history in Redis: bring it up to date with tonight's fetch (its 14 days are kept as they were)."""
    redis, n = getattr(store, "redis", None), 0
    if redis is None:
        return 0
    hotset = set(hot)
    for sym, (ds, cs, *_rest) in series.items():
        if sym in hotset:
            continue
        try:
            if await redis.set(f"etf:hist:{sym}", _pack_hist(ds, cs), xx=True, keepttl=True):
                n += 1
        except Exception:                                    # Redis is a cache here; the row in Postgres is what matters
            return n
    return n


def _pack_rows(rows: Sequence[dict]) -> str:
    return json.dumps([{k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in r.items()} for r in rows], separators=(",", ":"), default=str)


_DATES = ("price_date", "range_from", "first_date", "break_date", "nav_date")
_STAMPS = ("updated_at", "first_seen")


def _unpack_rows(raw: Any) -> List[dict]:
    rows = json.loads(raw)
    for r in rows:
        for k in _DATES:
            if r.get(k):
                r[k] = date.fromisoformat(r[k])
        for k in _STAMPS:
            if r.get(k):
                r[k] = datetime.fromisoformat(r[k])
    return rows


async def publish(store, conn) -> None:
    """After a night's refresh: rebuild the etf_hot table, and the two Redis copies (every ETF's narrow row, and the ready-made hot list)."""
    rows = [dict(r) for r in await conn.fetch("SELECT * FROM etf_funds WHERE active ORDER BY avg_turnover DESC NULLS LAST, symbol")]
    items = [row_view(r) for r in sorted((r for r in rows if r.get("hot")), key=lambda r: r["turnover_rank"])]
    async with conn.transaction():
        await conn.execute("DELETE FROM etf_hot")
        await conn.executemany("INSERT INTO etf_hot(rank, symbol, body) VALUES($1,$2,$3::jsonb)", [(i["rank"], i["symbol"], json.dumps(i)) for i in items])
    redis = getattr(store, "redis", None)
    if redis is None:
        return
    try:
        await redis.set(ALL_KEY, _pack_rows(rows), ex=DATA_TTL)
        await redis.set(HOT_KEY, json.dumps(_hot_blob(rows, items), separators=(",", ":"), default=str), ex=DATA_TTL)
    except Exception as exc:                                  # the database copy is complete; readers fall back to it
        log.warning("etf redis publish failed: %s", exc)


# ---------------------------------------------------------------------------------------------------------------- reading
CACHE_SECONDS = 120
FLAT_WHY = "The price barely moves for this ETF: it pays out its earnings instead of growing the price, so a price change of about 0% says nothing about what it earned."
LIST_FIELDS = {"name": "display_name", "price": "price", "change": "change_pct", "ret1m": "ret_1m", "ret6m": "ret_6m", "ret1y": "ret_1y", "ret3y": "ret_3y",
               "ret5y": "ret_5y", "cagr3y": "cagr_3y", "cagr5y": "cagr_5y", "vol1y": "vol_1y", "mdd1y": "mdd_1y", "mdd3y": "mdd_3y", "mdd5y": "mdd_5y",
               "turnover": "avg_turnover", "premium": "nav_premium", "from52": "from52"}
FILTER_KEYS = {k: v for k, v in LIST_FIELDS.items() if k not in ("name", "price", "change", "turnover", "from52")}
SYMBOL_RE = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")


def _round(v: Optional[float], d: int = 2) -> Optional[float]:
    return None if v is None or not math.isfinite(v) else round(v, d) + 0.0      # + 0.0 turns -0.0 into 0.0


def _words(s: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _allow(n: int) -> int:
    return 0 if n <= 3 else 1 if n <= 5 else 2


def _dist(a: str, b: str) -> int:
    """Edit distance counting a swap of neighbours as one edit."""
    d = [[i] + [0] * len(b) for i in range(len(a) + 1)]
    d[0] = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def search_score(query: str, hay_words: List[str], joined: str) -> int:
    """0 = no match. Every word of the query must match: exactly or as the start of a word (90), inside a word or the run-together text
    (60), or within a typo or two of the start of a word (40). 'nifty bees', 'niftybees' and 'nifti bees' all find NIFTYBEES."""
    qw = _words(query)
    if not qw:
        return 1
    total = 0
    for q in qw:
        best = 0
        for w in hay_words:
            if w == q:
                best = max(best, 100)
            elif w.startswith(q):
                best = max(best, 90)
            elif len(q) >= 3 and q in w:
                best = max(best, 60)
            elif len(q) >= 4 and not any(ch.isdigit() for ch in q) and (_dist(q, w) <= _allow(len(q)) or _dist(q, w[:len(q)]) <= _allow(len(q))):
                best = max(best, 40)
        if not best and len(q) >= 3 and q in joined:
            best = 55
        if not best:
            return 0
        total += best
    return total // len(qw)


def row_view(r: dict) -> dict:
    """One ETF as the list and compare endpoints show it. Percent figures are rounded to two places."""
    reasons = _jsond(r.get("reasons"))
    r = dict(r)
    for k in ("ret_1m", "ret_6m", "ret_1y", "ret_3y", "ret_5y", "cagr_3y", "cagr_5y"):   # a price return that rounds to 0.00% is not a figure worth showing
        if r.get(k) is not None and abs(r[k]) < 0.005:
            r[k], reasons[k] = None, FLAT_WHY
    cat = CATEGORIES.get(r["category"]) if r.get("category") else None
    price, hi = r.get("price"), r.get("high52")
    return {
        "symbol": r["symbol"], "name": r["display_name"], "isin": r["isin"], "fundHouse": r.get("fund_house"),
        "category": cat["key"] if cat else None, "categoryLabel": cat["label"] if cat else None, "assetClass": r.get("asset_class"),
        "price": _round(price, 4), "previousClose": _round(r.get("prev_close"), 4), "changePct": _round(r.get("change_pct")), "priceDate": r["price_date"].isoformat() if r.get("price_date") else None,
        "volume": r.get("volume"), "avgTurnover": _round(r.get("avg_turnover"), 0),
        "ret1m": _round(r.get("ret_1m")), "ret6m": _round(r.get("ret_6m")), "ret1y": _round(r.get("ret_1y")), "ret3y": _round(r.get("ret_3y")), "ret5y": _round(r.get("ret_5y")),
        "cagr3y": _round(r.get("cagr_3y")), "cagr5y": _round(r.get("cagr_5y")), "vol1y": _round(r.get("vol_1y")),
        "mdd1y": _round(r.get("mdd_1y")), "mdd3y": _round(r.get("mdd_3y")), "mdd5y": _round(r.get("mdd_5y")),
        "high52": _round(hi, 4), "low52": _round(r.get("low52"), 4), "from52": _round((price / hi - 1) * 100) if price and hi else None,
        "rangeFrom": r["range_from"].isoformat() if r.get("range_from") else None,
        "firstDate": r["first_date"].isoformat() if r.get("first_date") else None, "points": r.get("points") or 0,
        "breakDate": r["break_date"].isoformat() if r.get("break_date") else None,
        "nav": _round(r.get("nav"), 4), "navDate": r["nav_date"].isoformat() if r.get("nav_date") else None, "premium": _round(r.get("nav_premium")),
        "premiumWide": r.get("nav_premium") is not None and abs(r["nav_premium"]) > PREMIUM_NOTE,
        "why": reasons, "rank": r.get("turnover_rank"), "hot": bool(r.get("hot")),
    }


def _facets(rows: Sequence[dict]) -> Tuple[List[dict], List[dict]]:
    facets: Dict[str, int] = {}
    for r in rows:
        facets[r.get("category") or "none"] = facets.get(r.get("category") or "none", 0) + 1
    cats = [{**CATEGORIES[k], "count": n} for k, n in sorted(facets.items(), key=lambda kv: -kv[1]) if k in CATEGORIES] + \
           ([{"key": "none", "label": "Not classified", "group": "none", "count": facets["none"]}] if facets.get("none") else [])
    groups = [{"key": k, "label": v, "count": sum(1 for r in rows if r.get("asset_class") == k)} for k, v in GROUPS.items()]
    return cats, groups


def _meta(rows: Sequence[dict]) -> dict:
    dates = [r["price_date"] for r in rows if r.get("price_date")]
    return {"asOf": max(dates).isoformat() if dates else None, "updatedAt": max((r["updated_at"] for r in rows), default=None)}


def _hot_blob(rows: Sequence[dict], items: List[dict]) -> dict:
    """The default list page (most traded first) with everything but the paging already worked out. Built by the nightly job."""
    cats, groups = _facets(rows)
    return {"items": items, "universe": len(rows), "categories": cats, "groups": groups, **_meta(rows)}


async def _load(app) -> dict:
    """All active ETFs (their narrow rows, about 355), kept in this process for two minutes. Order of lookup: this process, Redis (written by the
    nightly job), Postgres. One short read; nothing runs in the background."""
    cache = getattr(app.state, "etf_cache", None)
    if cache and time.time() - cache["at"] < CACHE_SECONDS:
        return cache
    store, rows = app.state.store, None
    try:
        raw = await store.redis.get(ALL_KEY)
        rows = _unpack_rows(raw) if raw else None
    except Exception:                                          # Redis down or an unreadable copy: Postgres decides
        rows = None
    if rows is None:
        async with store.pool.acquire() as conn:
            rows = [dict(r) for r in await conn.fetch("SELECT * FROM etf_funds WHERE active ORDER BY avg_turnover DESC NULLS LAST, symbol")]
        try:
            await store.redis.set(ALL_KEY, _pack_rows(rows), ex=DATA_TTL)
        except Exception:
            pass
    words = {}
    for r in rows:                                             # the typo-tolerant search index: every ETF's words, split once
        cat = CATEGORIES.get(r["category"], {}).get("label", "") if r.get("category") else ""
        w = _words(f"{r['display_name']} {r['symbol']} {r.get('scheme_name') or ''} {r.get('short_name') or ''} {r.get('fund_house') or ''} {cat} {r['isin']}")
        words[r["symbol"]] = (w, "".join(w))
    cache = {"at": time.time(), "rows": rows, "by": {r["symbol"]: r for r in rows}, "words": words, **_meta(rows)}
    app.state.etf_cache = cache
    return cache


async def _hot(app) -> Optional[dict]:
    """The ready-made hot list: this process (60 s), Redis, then the etf_hot table. None when there is nothing hot (before the first nightly run)."""
    c = getattr(app.state, "etf_hot", None)
    if c and time.time() - c["at"] < 60:
        return c["blob"]
    blob = None
    try:
        raw = await app.state.store.redis.get(HOT_KEY)
        blob = json.loads(raw) if raw else None
    except Exception:
        blob = None
    if blob is None:
        async with app.state.store.pool.acquire() as conn:
            items = [json.loads(r["body"]) if isinstance(r["body"], str) else r["body"] for r in await conn.fetch("SELECT body FROM etf_hot ORDER BY rank")]
        if items:
            blob = _hot_blob((await _load(app))["rows"], items)
    app.state.etf_hot = {"at": time.time(), "blob": blob}
    return blob


def _default(o: Any) -> str:
    return o.isoformat() if isinstance(o, (date, datetime)) else str(o)


def _json(body: Any, status: int = 200, cache: int = CACHE_SECONDS) -> Response:
    return Response(content=json.dumps(body, separators=(",", ":"), default=_default), status_code=status, media_type="application/json",
                    headers={"Cache-Control": f"public, max-age={cache}"})


def _csv(v: Optional[str], allowed: Iterable[str], limit: int = 30) -> List[str]:
    out = [x for x in (v or "").split(",") if x][:limit]
    ok = set(allowed)
    return [x for x in out if x in ok]


def _bound(v: Optional[str]) -> Optional[float]:
    try:
        f = float(v) if v is not None and v != "" else None
    except ValueError:
        return None
    return f if f is not None and math.isfinite(f) and abs(f) <= 100000 else None


def headline(v: dict, reasons: dict, dates: Optional[Sequence[date]], closes: Optional[Sequence[float]], brk: Optional[date]) -> List[dict]:
    """The three return figures every page leads with: 1 day, 1 year, 5 years (price return, dividends not included).
    `value` is the stored figure; `from`/`to` are the two closes it was worked out from, found again in the history so the page can show them.
    The 5-year value is the TOTAL change over five years (`annualised` is the same change as a yearly rate)."""
    out = []
    n = len(dates) if dates else 0
    L = dates[-1] if n else None
    first_ok = max(bisect_right(dates, brk) - 1, 0) if (n and brk) else 0
    for key, label in (("1d", "1 day"), ("1y", "1 year"), ("5y", "5 years")):
        val = v["changePct"] if key == "1d" else v[f"ret{key}"]
        why = None if val is not None else (reasons.get("change") if key == "1d" else reasons.get(f"ret_{key}")) or "Not enough price history"
        frm = to = None
        if val is not None and n >= 2:
            if key == "1d":
                i = n - 2
            else:
                i, _code = _lookback(dates, first_ok, month_back(L, 12 if key == "1y" else 60))
            if i is not None:
                frm, to = {"date": dates[i].isoformat(), "close": round(closes[i], 4)}, {"date": L.isoformat(), "close": round(closes[-1], 4)}
        out.append({"key": key, "label": label, "value": val, "annualised": v["cagr5y"] if key == "5y" else None, "why": why, "from": frm, "to": to,
                    "basis": "Change from the previous close" if key == "1d" else "Price change, dividends not included" + (" (total over the five years, not per year)" if key == "5y" else "")})
    return out


@router.get("")
async def list_etfs(request: Request, q: str = "", category: str = "", asset: str = "", sort: str = "turnover", order: str = "", limit: int = 40, offset: int = 0):
    qp = request.query_params
    q = q.strip()[:60]
    cats = _csv(category, [*CATEGORIES, "none"])
    assets = _csv(asset, GROUPS)
    sort = sort if sort in LIST_FIELDS else "turnover"
    desc = (order or ("asc" if sort == "name" else "desc")).lower() != "asc"
    limit, offset = max(1, min(limit, 100)), max(0, min(offset, 5000))
    ranges = {k: (_bound(qp.get(k + "Min")), _bound(qp.get(k + "Max"))) for k in FILTER_KEYS}
    ranges = {k: v for k, v in ranges.items() if v[0] is not None or v[1] is not None}
    if not (q or cats or assets or ranges) and sort == "turnover" and desc:            # the default page: ready-made, no work at all
        hot = await _hot(request.app)
        if hot and offset + limit <= len(hot["items"]):
            return _json({"items": hot["items"][offset:offset + limit], "total": hot["universe"], "universe": hot["universe"], "hotCount": len(hot["items"]), "offset": offset,
                          "limit": limit, "excluded": 0, "categories": hot["categories"], "groups": hot["groups"], "asOf": hot["asOf"], "updatedAt": hot["updatedAt"],
                          "source": SOURCE, "disclaimer": DISCLAIMER})
    cache = await _load(request.app)
    rows = cache["rows"]

    views = []
    scored: Dict[str, int] = {}
    for r in rows:
        if q:
            words, joined = cache["words"][r["symbol"]]
            s = search_score(q, words, joined)
            if not s:
                continue
            qj = "".join(_words(q))
            if len(qj) >= 5 and _dist(qj, r["symbol"].lower()) <= _allow(len(qj)):
                s += 50                                    # the run-together query is the symbol, give or take a typo: put that ETF first
            scored[r["symbol"]] = s
        views.append(r)
    pool = views
    if cats:
        pool = [r for r in pool if (r.get("category") or "none") in cats]
    if assets:
        pool = [r for r in pool if r.get("asset_class") in assets]
    excluded = 0
    for k, (lo, hi) in ranges.items():
        col = LIST_FIELDS[k]
        keep = []
        for r in pool:
            v = r.get(col)
            if v is None:
                excluded += 1
            elif (lo is None or v >= lo) and (hi is None or v <= hi):
                keep.append(r)
        pool = keep
    col = LIST_FIELDS[sort]

    def val(r):
        if col == "from52":
            return (r["price"] / r["high52"] - 1) if r.get("price") and r.get("high52") else None
        return r.get(col)
    have = [r for r in pool if val(r) is not None]
    miss = [r for r in pool if val(r) is None]
    have.sort(key=(lambda r: str(val(r)).lower()) if col == "display_name" else val, reverse=desc)
    ordered = have + miss
    if q and sort == "turnover":
        ordered.sort(key=lambda r: -scored.get(r["symbol"], 0))            # a search ranks by how well the words match; ties keep the most-traded first
    page = ordered[offset:offset + limit]
    fc, fg = _facets(rows)
    body = {"items": [row_view(r) for r in page], "total": len(ordered), "universe": len(rows), "hotCount": sum(1 for r in rows if r.get("hot")), "offset": offset, "limit": limit,
            "excluded": excluded, "categories": fc, "groups": fg,
            "asOf": cache["asOf"], "updatedAt": cache["updatedAt"], "source": SOURCE, "disclaimer": DISCLAIMER}
    return _json(body)


async def cold_history(app, r: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Daily closes of an ETF that is not hot: Redis first (14 days), else fetched from Upstox now (one call) and cached. Never beyond the stored
    close, so the chart ends on the same day and price as the figures. Returns (history, None) or (None, why)."""
    store, sym = app.state.store, r["symbol"]
    key = f"etf:hist:{sym}"
    try:
        raw = await store.redis.get(key)
        h = _unpack_hist(raw) if raw else None
        if h:
            return h, None
    except Exception:
        pass
    settings = getattr(app.state, "settings", None)
    if settings is None or not settings.upstox_access_token:
        return None, "The price chart for this ETF is not stored and the price source is not connected right now"
    lock = f"etf:histlock:{sym}"
    try:
        got = await store.redis.set(lock, b"1", nx=True, ex=30)
    except Exception:
        got = True
    if not got:                                              # another visitor is fetching it: wait a moment for their result
        for _ in range(12):
            await asyncio.sleep(0.25)
            try:
                raw = await store.redis.get(key)
            except Exception:
                break
            h = _unpack_hist(raw) if raw else None
            if h:
                return h, None
        return None, "The price chart is being prepared; please try again in a moment"
    client = UpstoxClient(settings, store.redis)
    try:
        today = datetime.now(IST).date()
        data = await client.get(f"/v3/historical-candle/{urlquote(r['instrument_key'], safe='')}/days/1/{today.isoformat()}/{(today - timedelta(days=3650)).isoformat()}")
        rows, _dup = parse_candles(data.get("candles") if isinstance(data, dict) else None)
        last = r.get("price_date")
        rows = [c for c in rows if not last or c[0] <= last]
        if rows and last and r.get("price") and rows[-1][0] < last:              # tonight's close came from the quote; the candle list may not have it yet
            rows.append((last, r["price"], r["price"], r["price"], r["price"], 0.0))
        if len(rows) < 2:
            return None, "The price source returned no usable history for this ETF"
        ds, cs = [c[0] for c in rows], [c[4] for c in rows]
        try:
            await store.redis.set(key, _pack_hist(ds, cs), ex=HIST_TTL)
        except Exception:
            pass
        return {"dates": ds, "closes": cs}, None
    except UpstoxTokenExpired:
        return None, "The price source did not accept our access right now"
    except (UpstoxError, httpx.HTTPError):
        return None, "The price source did not answer"
    finally:
        await client.aclose()
        try:
            await store.redis.delete(lock)
        except Exception:
            pass


async def _history(app, symbol: str, r: Optional[dict] = None) -> Tuple[Optional[dict], Optional[str]]:
    async with app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT dates, closes FROM etf_history WHERE symbol = $1", symbol)
    if row:
        return dict(row), None
    return await cold_history(app, r) if r else (None, "No price history")


def _parse_symbols(raw: str) -> List[str]:
    out: List[str] = []
    for s in raw.split(","):
        s = s.strip().upper()
        if s and s not in out:
            out.append(s)
    return out


@router.get("/compare")
async def compare(request: Request, symbols: str = "", range: str = "1Y"):
    syms = _parse_symbols(symbols)
    rng = range.upper()
    if not 2 <= len(syms) <= 4 or any(not SYMBOL_RE.match(s) for s in syms):
        raise fail(400, "bad_symbols", "Choose 2 to 4 ETFs to compare.")
    if rng not in RANGES:
        raise fail(400, "bad_range", "Range must be one of 1M, 6M, 1Y, 3Y, 5Y, MAX.")
    cache = await _load(request.app)
    missing = [s for s in syms if s not in cache["by"]]
    if missing:
        raise fail(404, "unknown_etf", "No ETF with the symbol " + ", ".join(missing) + ".")
    hist = dict(zip(syms, await asyncio.gather(*[_history(request.app, s, cache["by"][s]) for s in syms])))
    items, usable = [], {}
    for s in syms:
        r, h = cache["by"][s], hist[s][0]
        v = row_view(r)
        items.append(v)
        if h and len(h["dates"]) > 1:
            brk = r.get("break_date")
            k = max(bisect_right(h["dates"], brk) - 1, 0) if brk else 0
            usable[s] = (h["dates"][k:], h["closes"][k:])
    notes: List[str] = []
    if len(usable) < len(syms):
        notes.append("Some of these ETFs have no price history we can show right now, so they are left out of the chart. Their figures in the table are unaffected.")
    start, series = None, {}
    if usable:
        last = max(d[-1] for d, _ in usable.values())
        months = RANGES[rng]
        target = month_back(last, months) if months else date.min
        # the chart starts on the latest of: the range's start day and the day each ETF's usable history begins
        firsts = {s: d[0] for s, (d, _) in usable.items()}
        start = max([target] + list(firsts.values()))
        late = [s for s, f in firsts.items() if f == start and start > target + timedelta(days=GAP_DAYS) and start - min(firsts.values()) > timedelta(days=GAP_DAYS)]
        if late:
            notes.append("The chart starts on %s, the first day all of these ETFs have usable prices (%s has no earlier prices in our data)." % (start.strftime("%d %b %Y"), ", ".join(late)))
        series = rebase(usable, start)
        for s in syms:
            if s in usable and cache["by"][s].get("break_date"):
                notes.append("%s: prices before %s are left out because the source shows a jump there that looks like a split or a bad price." % (s, cache["by"][s]["break_date"].strftime("%d %b %Y")))
    return _json({"symbols": syms, "range": rng, "start": start.isoformat() if start else None, "items": items, "series": series, "notes": notes,
                  "asOf": cache["asOf"], "updatedAt": cache["updatedAt"], "source": SOURCE, "disclaimer": DISCLAIMER})


@router.get("/{symbol}")
async def detail(request: Request, symbol: str, range: str = "1Y"):
    sym, rng = symbol.upper(), range.upper()
    if not SYMBOL_RE.match(sym):
        raise fail(404, "unknown_etf", "No ETF with that symbol.")
    if rng not in RANGES:
        raise fail(400, "bad_range", "Range must be one of 1M, 6M, 1Y, 3Y, 5Y, MAX.")
    cache = await _load(request.app)
    r = cache["by"].get(sym)
    if not r:
        raise fail(404, "unknown_etf", "No ETF with that symbol.")
    h, hwhy = await _history(request.app, sym, r)
    brk = r.get("break_date")
    extra = _jsond(r.get("extra"))
    reasons = _jsond(r.get("reasons"))
    v = row_view(r)
    for k in ("1m", "6m", "1y", "3y", "5y"):   # a return withheld because it rounds to 0.00% says why, on the page
        if r.get(f"ret_{k}") is not None and v[f"ret{k}"] is None:
            reasons[f"ret_{k}"] = FLAT_WHY
    returns = []
    for key, _m, label in PERIODS:
        returns.append({"key": key, "label": label, "price": v[f"ret{key}"], "annualised": v.get(f"cagr{key}") if key in ("3y", "5y") else None, "why": reasons.get(f"ret_{key}")})
    risk = {"vol1y": {"value": v["vol1y"], "why": reasons.get("vol_1y"), "days": extra.get("vol_days")},
            "drawdowns": [{"key": k, "label": LABEL[k], "value": v[f"mdd{k}"], "why": reasons.get(f"mdd_{k}"), "peak": (extra.get(f"mdd_{k}") or {}).get("peak"),
                           "trough": (extra.get(f"mdd_{k}") or {}).get("trough")} for k in ("1y", "3y", "5y")],
            "range52": {"high": v["high52"], "low": v["low52"], "from": v["rangeFrom"], "fromHighPct": v["from52"], "why": reasons.get("range")}}
    nav = {"value": v["nav"], "date": v["navDate"], "premium": v["premium"], "premiumWhy": reasons.get("nav_premium"), "source": "AMFI"} if v["nav"] else None
    facts = [{"label": "NSE symbol", "value": sym}, {"label": "ISIN", "value": r["isin"]}, {"label": "Exchange", "value": "NSE"},
             {"label": "Fund house", "value": r.get("fund_house"), "source": "AMFI"}, {"label": "AMFI scheme name", "value": tidy_scheme(r.get("scheme_name")), "source": "AMFI"},
             {"label": "Price history in our data from", "value": v["firstDate"], "note": "Not the launch date: our price source goes back 10 years at most"},
             {"label": "Average daily traded value (20 sessions)", "value": v["avgTurnover"], "unit": "INR"}]
    ser = series_for(h["dates"], h["closes"], rng, brk) if h else {"range": rng, "available": False, "why": hwhy or "No price history", "points": [], "grain": "daily"}
    avail = {}
    if h:
        for k in RANGES:
            s = series_for(h["dates"], h["closes"], k, brk) if k != rng else ser
            avail[k] = {"available": s["available"], "why": s.get("why")}
    head = headline(v, reasons, h["dates"] if h else None, h["closes"] if h else None, brk)
    return _json({**v, "headline": head, "returns": returns, "risk": risk, "nav": nav, "facts": [f for f in facts if f["value"] is not None], "unavailable": UNAVAILABLE, "unavailableWhy": NOT_PUBLISHED,
                  "series": ser, "ranges": avail, "breakNote": extra.get("break_note"), "priceNote": reasons.get("price"),
                  "asOf": v["priceDate"], "updatedAt": r["updated_at"], "source": SOURCE, "disclaimer": DISCLAIMER})


# ---------------------------------------------------------------------------------------------------------------- holdings and facts
# Both come from finlit.disclosure (fund-house portfolio and factsheet disclosures, read by another module). That module may be missing or
# may fail; the page then says so with a reason instead of showing an empty or made-up panel.
PORTFOLIO_WAIT = "Holdings are not available yet: the fund-house disclosure source is not connected"
FACTS_WAIT = "Fund facts are not available yet: the fund-house disclosure source is not connected"


async def _disclosure(name: str, app, isin: str) -> Tuple[Any, Optional[str]]:
    try:
        from . import disclosure                              # noqa: PLC0415  (loaded lazily: the module is owned elsewhere and may not exist yet)
        fn = getattr(disclosure, name)
    except (ImportError, AttributeError):
        return None, PORTFOLIO_WAIT if name == "get_portfolio" else FACTS_WAIT
    try:
        res = fn(app.state.store.pool, isin)
        if asyncio.iscoroutine(res):
            res = await res
    except Exception as exc:                                  # a failing disclosure read must never break the ETF page
        log.warning("etf %s %s failed: %s", name, isin, type(exc).__name__)
        return None, "The disclosure data could not be read right now"
    if not res:
        return None, "No disclosure has been published or found for this ETF yet"
    return res, None


@router.get("/{symbol}/portfolio")
async def portfolio(request: Request, symbol: str):
    sym = symbol.upper()
    r = (await _load(request.app))["by"].get(sym) if SYMBOL_RE.match(sym) else None
    if not r:
        raise fail(404, "unknown_etf", "No ETF with that symbol.")
    res, why = await _disclosure("get_portfolio", request.app, r["isin"])
    base = {"symbol": sym, "isin": r["isin"], "disclaimer": DISCLAIMER}
    if why or not isinstance(res, dict):
        return _json({**base, "unavailable": why or "No portfolio found", "holdings": [], "exited": [], "summary": None, "asOf": None}, cache=60)
    return _json({**base, **res}, cache=300)                  # no "unavailable" key at all: the page tells a portfolio from a reason by that key


@router.get("/{symbol}/facts")
async def facts(request: Request, symbol: str):
    sym = symbol.upper()
    r = (await _load(request.app))["by"].get(sym) if SYMBOL_RE.match(sym) else None
    if not r:
        raise fail(404, "unknown_etf", "No ETF with that symbol.")
    res, why = await _disclosure("get_facts", request.app, r["isin"])
    base = {"symbol": sym, "isin": r["isin"], "disclaimer": DISCLAIMER}
    if why or not isinstance(res, dict):
        return _json({**base, "unavailable": why or "No facts found", "facts": {}}, cache=60)
    return _json({**base, "facts": res, "unavailable": None}, cache=300)
