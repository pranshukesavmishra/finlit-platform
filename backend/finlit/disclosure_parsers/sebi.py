"""The SEBI-prescribed monthly portfolio statement, as every fund house publishes it in Excel.

One sheet is one scheme: a title (scheme name, 'as on' date), a header row (Name of the Instrument | ISIN | Industry / Rating | Quantity | Market value
(Rs. in Lakhs) | % to Net Assets ...), section headings (EQUITY & EQUITY RELATED, DEBT INSTRUMENTS, MONEY MARKET, TREPS ...), the holding rows, sub totals and a
GRAND TOTAL. The fund houses differ in wording, column order, whether percents are fractions (0.0148) or percents (1.48) and whether there are .xls or .xlsx
files, so everything is found by reading the header text, never by fixed positions. A sheet that does not look like a portfolio returns a reason, not a guess.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .model import Holding, Portfolio, isin_ok

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_RES = [
    re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})\b", re.I),             # September 30, 2026 / September 30,2026
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s,.-]+{_MON}\.?[\s,.-]+(\d{{4}})\b", re.I),     # 30 September 2026, 30-Sep-2026
    re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b"),                                          # 30/09/2026
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                                                    # 2026-09-30
    re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b"),                                  # 30-09-2026, 30-09-26 (Tata)
]


def parse_date_text(s: str) -> Optional[date]:
    for i, rx in enumerate(DATE_RES):
        m = rx.search(s)
        if not m:
            continue
        try:
            if i == 0:
                return date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
            if i == 1:
                return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
            if i == 2:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if i == 3:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            y = int(m.group(3))
            return date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
        except (ValueError, KeyError):
            continue
    return None


def excel_serial(v) -> Optional[date]:
    if isinstance(v, float) and 40000 < v < 60000:
        return date(1899, 12, 30) + timedelta(days=int(v))
    return None


def txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else repr(v)
    return re.sub(r"[ \t\r\f\v\xa0]+", " ", str(v)).strip()


def num(v) -> Optional[float]:
    """A cell as a number; None for blanks, NIL, dashes and text."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("\xa0", " ").strip()
    if not s or s.lower() in ("nil", "-", "--", "na", "n.a.", "n.a", "#"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()%").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


# -------------------------------------------------------------------------------------------------- header

def _find_cols(row: List) -> Optional[Dict[str, int]]:
    cols: Dict[str, int] = {}
    for i, c in enumerate(row):
        t = txt(c).lower()
        if not t:
            continue
        if "isin" in t and "isin" not in cols:
            cols["isin"] = i
        elif re.search(r"%|percent", t) and re.search(r"nav|net\s*asset|aum|asset", t) and "pct" not in cols:
            cols["pct"] = i
        elif re.search(r"market|fair|value|\(rs", t) and not re.search(r"%|percent", t) and "value" not in cols and "ytm" not in t:
            cols["value"] = i
        elif re.search(r"quantity|qty|no\.? of (units|shares)|number of", t) and "qty" not in cols:
            cols["qty"] = i
        elif re.search(r"industry|rating|sector", t) and ("sector" not in cols or (re.search(r"industry|sector", t) and not re.search(r"industry|sector", txt(row[cols["sector"]]).lower()))):
            cols["sector"] = i         # separate 'Rating' and 'Industry' columns (quant): the industry one
        elif re.search(r"name|instrument|issuer|security|scrip|particulars", t) and "name" not in cols and "isin" not in t:
            cols["name"] = i
    if "isin" in cols and "pct" in cols and "name" in cols:
        return cols
    return None


def _value_unit(header_cell: str) -> Optional[float]:
    t = header_cell.lower()
    if re.search(r"lakh|lac\b|lacs", t):
        return 1.0
    if re.search(r"crore|\bcr\b", t):
        return 100.0
    return None


# -------------------------------------------------------------------------------------------------- sections

CASH_NAME = re.compile(r"\b(treps?|tri[- ]?party|reverse\s*repo|repo\b|cblo|cash|net\s+receivable|net\s+current\s+assets?|other\s+current\s+assets?|receivables?|margin|collateral|payables?)\b", re.I)
_HEAD = [
    ("cash", re.compile(r"treps|tri[- ]?party|reverse\s*repo|\bcblo\b|cash|net\s+receivable|net\s+current|other\s+current", re.I)),
    ("equity", re.compile(r"^\W*(\(?[a-z]\)\s*)?equity|\bequities\b|equity\s*(&|and)\s*equity\s*related|equity\s+shares|equity\s+and\s+equity", re.I)),
    ("debt", re.compile(r"debt|bonds?\b|\bncd|debentures?|government\s+securit|g-?sec|gilt|treasury\s+bills?|t-?bills?|certificates?\s+of\s+deposit|commercial\s+papers?|money\s+market|securiti[sz]ed|pass\s+through|zero\s+coupon|state\s+development|\bsdl\b|fixed\s+deposit|deposit", re.I)),
    ("other", re.compile(r"derivative|futures|options|mutual\s+fund\s+units|units\s+of|\betfs?\b|reits?|invits?|alternative|\baif\b|foreign|overseas|gold|silver|commodit|others?\b|preference|warrants?", re.I)),
]
_SUBHEAD = re.compile(r"^\W*(\(?[a-z0-9]{1,3}\)\s*)?(listed|unlisted|awaiting|privately|private placement|rated|unrated|thinly|securiti)", re.I)
TOTAL_ROW = re.compile(r"^\W*(sub\s*-?\s*total|total)\b|^.*[a-z)]\s+(sub\s*-?\s*)?total\W*$", re.I)     # 'TOTAL ...' or 'EQUITY & EQUITY RELATED TOTAL' (Tata)
GRAND_ROW = re.compile(r"^\W*(grand\s*total|total\s*net\s*assets|net\s*assets\b|total\s*assets|total\s*aum|grand\s*total)", re.I)
RATING_LIKE = re.compile(r"\b(aaa|aa\+?|aa-|a1\+|a1|a\+|sovereign|unrated|crisil|icra|care|ind\s?a|fitch|brickwork|acuite|nil)\b|^[ab]{1,3}[+-]?$", re.I)


NA_TEXT = re.compile(r"^\s*(n\.?\s*a\.?|not applicable|-+)\s*$", re.I)
OTHER_LABELS = frozenset(["foreign security", "foreign securities", "mutual funds", "mutual fund", "commodity", "commodities", "reit", "invit", "reits", "invits", "etf", "overseas etf",
                          "units of mutual fund", "foreign mutual fund", "overseas mutual fund", "gold", "silver", "others", "other"])


def heading_class(text: str) -> Optional[str]:
    t = text.strip()
    if not t or _SUBHEAD.match(t):
        return None
    for cls, rx in _HEAD:
        if rx.search(t):
            return cls
    return None


def clean_name(s: str) -> str:
    s = txt(s)
    s = re.sub(r"[\s\*#@\$\^]+$", "", s)          # footnote marks after the name (**, #, $, ^)
    return s.strip()


# -------------------------------------------------------------------------------------------------- title

TITLE_SKIP = re.compile(r"portfolio\s+(statement|details|as\s+on)|monthly\s+portfolio|\bas\s+(on|at)\b|^\(?\s*an?\s+(open|close|interval)|^\(|statement|mutual\s+fund\s*$|^scheme\s*(name)?\s*:?\s*$|name of the instrument|^sr\.?\s*no|^page|^annexure|^details of|^scheme (risk|code)|^back\s+to\s+(index|top)"
                        r"|asset\s+management\s+(company|co\b)|investment\s+manager|^registered\s+office|\bCIN\b", re.I)


def split_title(cell: str) -> Tuple[str, List[str]]:
    """Scheme name from a title cell: the whole cell with line breaks as spaces (fund houses wrap names mid-way), cut at the '(An open ended ...)' description,
    with '(formerly known as X)' / '(Ex X)' moved to aliases."""
    full = re.sub(r"\s+", " ", cell.strip())
    full = re.sub(r"\s*\(\s*an?\s+[a-z][\s\S]*$", "", full, flags=re.I) if re.search(r"\(\s*an?\s+[a-z]", full, re.I) and not re.match(r"^\(", full) else full
    aliases: List[str] = []
    m = re.search(r"\(\s*(?:formerly(?:\s+known\s+as)?|ex|erstwhile(?:\s+known\s+as)?|earlier(?:\s+known\s+as)?)\b[\s:\-]*([^)]+)\)", full, re.I)
    if m:
        aliases.append(re.sub(r"\s+", " ", m.group(1)).strip())
    main = re.sub(r"\(\s*(?:formerly|ex|erstwhile|earlier)\b[^)]*\)", "", full, flags=re.I)
    main = re.sub(r"\s+", " ", main).strip(" -:")
    m2 = re.match(r"^(?:name of the scheme|scheme name|scheme)\s*[:\-]\s*(.+)$", main, re.I)
    if m2:
        main = m2.group(1).strip()
    main = re.sub(r"^[A-Z]{1,4}\d{1,4}\s*[-:]\s*(?=[A-Za-z])", "", main)   # a fund house's own sheet code in front of the name ('IB01-Groww Large Cap Fund')
    return main, aliases


_TITLE_OF = re.compile(r"^(?:monthly\s+)?portfolio(?:\s+statement)?\s+of\s+(.+?)\s+(?:as\s+(?:on|at)|for\s+the\s+(?:month|period))\b", re.I)


def find_title(head_rows: List[List]) -> Tuple[str, List[str]]:
    for row in head_rows:
        for c in row:
            t = txt(c)
            if not t or isinstance(c, float):
                continue
            first = re.split(r"[\n\r]+", t)[0].strip()
            m = _TITLE_OF.match(first)           # 'Portfolio of Kotak Services Fund as on 30-Sep-2026'
            if m:
                main, al = split_title(m.group(1))
                if main:
                    return main, al
            if len(first) < 6 or TITLE_SKIP.search(first) or " " not in first:
                continue
            main, al = split_title(t)
            if main:
                return main, al
    return "", []


# -------------------------------------------------------------------------------------------------- the parser

# 'Benchmark: X', 'Benchmark Name : X', and 'Benchmark Riskometer: X' (DSP names the index on its risk-o-meter caption)
BENCH = re.compile(r"benchmark\s*(?:name|risk\s*-?\s*o\s*-?\s*meter)?\s*[-:]\s*(.+)", re.I)
RISK_WORDS = re.compile(r"^(low|low to moderate|moderate|moderately high|high|very high)\s*(risk)?\s*$", re.I)


def bench_of(text: str) -> Optional[str]:
    m = BENCH.search(text)
    v = m.group(1).strip() if m else ""
    return v if v and not RISK_WORDS.match(v) and not v.lower().startswith("risk") else None


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


class NotAPortfolio(Exception):
    pass


def parse_rows(rows: Iterable[List], source_name: str, source_url: str, as_of_hint: Optional[date] = None, name_hint: Optional[str] = None) -> Portfolio:
    """Parse one sheet. Raises NotAPortfolio(reason) when it is not one (an index sheet, a different layout)."""
    it = iter(rows)
    head: List[List] = []
    cols: Optional[Dict[str, int]] = None
    header_row: List = []
    for row in it:
        head.append(row)
        cols = _find_cols(row)
        if cols:
            header_row = row
            break
        if len(head) > 40:
            break
    if not cols:
        raise NotAPortfolio("no header row with name, ISIN and % to net assets columns")
    above = head[:-1]
    title, aliases = find_title(above)
    if name_hint:
        if title and title.lower() != name_hint.lower():
            aliases = [title] + aliases
        title = name_hint
    own_names = {_alnum(t) for t in [title, *aliases] if t and _alnum(t)}
    as_of: Optional[date] = None
    for r in above:
        for c in r:
            t = txt(c)
            if isinstance(c, str) and re.search(r"\bas\s+(on|at)\b|\bfor the (month|period)\b|\bas of\b", t, re.I):
                d = parse_date_text(t)
                if d:
                    as_of = d
                    break
        if as_of:
            break
    if as_of is None:
        for r in above:
            for c in r:
                d = excel_serial(c)
                if d:
                    as_of = d
                    break
            if as_of:
                break
    as_of = as_of or as_of_hint
    if as_of is None:
        raise NotAPortfolio("no 'as on' date found above the header")
    unit = _value_unit(txt(header_row[cols["value"]])) if "value" in cols else None
    maxcol = max(cols.values())
    sector_header = txt(header_row[cols["sector"]]).lower() if "sector" in cols else ""

    holdings: List[Holding] = []
    net_assets: Optional[float] = None
    grand_pct: Optional[float] = None
    benchmark: Optional[str] = None
    cur = "other"
    seen_heading = False
    done = False
    raw_pcts: List[float] = []
    star_rows = 0          # rows whose percent is a '*' / '<0.01' marker instead of a number: not listed
    hedge_sum = 0.0
    hedge_rows = 0         # futures / options hedge lines with a negative percent: exposures, not additive to net assets, not listed
    dup_rows = 0           # a holding row repeated verbatim on the very next row (quant): counted once
    last_holding: Tuple[int, tuple] = (-2, ())
    rown = -1
    in_deriv = False
    nca_parts = 0          # cash lines dropped because the 'Net Current Assets' line after them is their sum
    swap_rows: List[Holding] = []   # swap lines (Tata: notional with a pseudo-ISIN 'IRSSWAP...'; HSBC: 'PAY_x% &REC_OIS_...') and long futures/options exposures

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    isin_first = cols["isin"] < cols["name"]
    # the name header can span several columns with each row's name in a later one (Kotak: header in A, names in C): look rightwards up to the next column
    name_end = min([i for i in cols.values() if i > cols["name"]], default=cols["name"] + 1)
    for row in it:
        rown += 1
        name_raw = cell(row, "name")
        label_in_isin = False
        if isin_first and not (isinstance(name_raw, str) and name_raw.strip()):
            # ISIN column first (Franklin Templeton): headings, totals, cash and 'Net Assets' rows carry their label in the ISIN column
            alt = cell(row, "isin")
            if isinstance(alt, str) and alt.strip() and not re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", alt.strip().upper()):
                name_raw, label_in_isin = alt, True
        name = clean_name(name_raw) if isinstance(name_raw, str) else ""
        if not name:
            for c in row[cols["name"] + 1:name_end]:
                if isinstance(c, str) and clean_name(c):
                    name = clean_name(c)
                    break
        if not done:
            if not benchmark:
                benchmark = bench_of(" ".join(txt(c) for c in row if isinstance(c, str)))
        if not name:
            # benchmark note rows sit under the table (Invesco): keep scanning for them, nothing else
            if done:
                for c in row:
                    if isinstance(c, str) and not benchmark:
                        benchmark = bench_of(c)
            continue
        pct_raw = cell(row, "pct")
        pct = num(pct_raw)
        if done:
            if not benchmark:
                benchmark = bench_of(name)
            continue
        if GRAND_ROW.match(name) and pct is not None:
            net_assets = num(cell(row, "value"))
            if net_assets is not None and unit:
                net_assets *= unit
            grand_pct = pct
            done = True
            continue
        if TOTAL_ROW.match(name):
            rest = _alnum(re.sub(r"^\W*(sub\s*-?\s*)?total\W*", "", name, flags=re.I))
            if rest and rest in own_names:
                # 'TOTAL : UTI Large Cap Fund' (UTI): the scheme's own total closes the table (futures exposure, dividend tables follow)
                tv = num(cell(row, "value"))
                if tv is not None and unit:
                    net_assets = tv * unit
                if pct is not None:
                    grand_pct = pct
                done = True
            continue
        isin_raw = "" if label_in_isin else txt(cell(row, "isin")).upper().replace(" ", "")
        if (pct is not None and not isin_raw and num(cell(row, "qty")) is None and not CASH_NAME.search(name)
                and (heading_class(name) in ("equity", "debt", "other") or _SUBHEAD.match(name))):
            # a section heading that carries its own sub-total (ICICI: 'Equity & Equity Related Instruments ... 97.9%'): a heading, not a holding
            hc = heading_class(name)
            if hc:
                cur, seen_heading, in_deriv = hc, True, bool(re.search(r"derivative|futures|options", name, re.I))
            continue
        if pct is None:
            if isinstance(pct_raw, str) and re.match(r"^\s*(\*+|\$+|<\s*[\d.]+\s*%?|less than.*)\s*$", pct_raw) and not heading_class(name) and (isin_raw or num(cell(row, "value")) is not None):
                star_rows += 1
                continue
            # a heading (or a NIL line)
            hc = heading_class(name)
            if hc and not isin_raw:
                cur = hc
                seen_heading = True
                in_deriv = bool(re.search(r"derivative|futures|options", name, re.I))
            continue
        if re.match(r"^\W*(plan|regular|direct)\b.*(growth|idcw|dividend|option)", name, re.I) and not isin_raw:
            continue      # the NAV table under the total
        if isin_raw and not re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", isin_raw):
            isin_raw = ""
        isin = isin_raw or None          # kept as published; the validator checks the check digit and storage drops a failing one
        cls = cur
        if CASH_NAME.search(name) and not isin_raw:
            cls = "cash"
        sec_probe = txt(cell(row, "sector"))
        deriv_row = in_deriv or bool(re.search(r"\b(futures?|options?|swaps?|derivatives?)\b", sec_probe, re.I))
        if deriv_row and cls != "cash" and pct < 0 and (not isin_raw or in_deriv):
            # a short future / option line; inside a derivatives block it may carry the underlying share's ISIN (quant)
            hedge_rows += 1
            hedge_sum += pct
            continue
        if not isin_raw and deriv_row and cls != "cash":
            cls = "other"
            if pct > 0:
                # a long future / option line: an exposure that some files count in their total and others (Bandhan) do not; decided after the table
                swap_rows.append(Holding(name=name, isin=None, sector=None, asset_class="other", pct_nav=pct, qty=num(cell(row, "qty")),
                                         value_lakh=num(cell(row, "value")) * unit if num(cell(row, "value")) is not None and unit else None))
                continue
        if pct < 0 and cls != "cash" and (num(cell(row, "qty")) or 0) < 0:
            hedge_rows += 1     # a short futures leg printed among the shares, with the share's ISIN and a negative quantity (Tata)
            hedge_sum += pct
            continue
        if re.match(r"^\W*(irs|interest\s+rate\s+swaps?)\b|^\W*pay_.*&\s*rec_", name, re.I):
            sw_value = num(cell(row, "value"))      # a swap line: its notional may or may not be inside the file's total; decided after the table
            swap_rows.append(Holding(name=name, isin=None, sector=None, asset_class="other", pct_nav=pct, qty=num(cell(row, "qty")),
                                     value_lakh=sw_value * unit if sw_value is not None and unit else None))
            continue
        if not seen_heading and cls == "other" and isin_raw:
            cls = "equity" if isin_raw.startswith("INE") and isin_raw[7:9] == "01" else cls
        sec_raw = txt(cell(row, "sector"))
        if (cls == "other" and sec_raw and isin_raw and sec_raw.lower() not in OTHER_LABELS and not RATING_LIKE.search(sec_raw) and not NA_TEXT.match(sec_raw)
                and ((isin_raw.startswith("INE") and isin_raw[7:9] == "01") or not isin_raw.startswith("IN"))):
            cls = "equity"            # an arbitrage / foreign-securities block holds ordinary shares: the row itself says so (equity ISIN, an industry)
        sector: Optional[str] = None
        if sec_raw and cls == "equity" and not isinstance(cell(row, "sector"), float):
            sector = re.sub(r"[\s\^\*#]+$", "", sec_raw)
        value = num(cell(row, "value"))
        if value is not None:
            value = value * unit if unit else None
        qty = num(cell(row, "qty"))
        key = (name, isin, pct, qty, value)
        if last_holding == (rown - 1, key):
            dup_rows += 1
            last_holding = (rown, key)
            continue
        last_holding = (rown, key)
        if cls == "cash" and not isin and re.search(r"net\s+current\s+assets?", name, re.I):
            # Bandhan lists 'Cash Margin', 'Net Receivables/Payables' and then 'Net Current Assets' as their sum: keep the sum, drop the parts
            acc, k = 0.0, 0
            big = max((abs(x) for x in raw_pcts), default=0.0) > 1.5
            while k < len(holdings) and holdings[-1 - k].asset_class == "cash" and holdings[-1 - k].isin is None:
                acc += holdings[-1 - k].pct_nav
                k += 1
                if k >= 2 and abs(acc - pct) <= k * (0.006 if big else 0.00006):
                    del holdings[-k:]
                    del raw_pcts[-k:]
                    nca_parts += k
                    break
        holdings.append(Holding(name=name, isin=isin, sector=sector, asset_class=cls, pct_nav=pct, qty=qty, value_lakh=value))
        raw_pcts.append(pct)
    swaps_left_out = 0
    if swap_rows:
        base = sum(raw_pcts)
        target = grand_pct if grand_pct is not None else (1.0 if abs(base - 1.0) < abs(base - 100.0) else 100.0)
        s_sum = sum(h.pct_nav for h in swap_rows)
        off = lambda b: min(abs(b - target), abs(b + hedge_sum - target))      # the validator may count the short hedge lines or not
        if off(base + s_sum) <= max(off(base), 0.0025 * abs(target)):      # kept unless they clearly push the total off (> 0.25 points)
            holdings.extend(swap_rows)
            raw_pcts.extend(h.pct_nav for h in swap_rows)
        else:
            swaps_left_out = len(swap_rows)
    # percent scale: fractions (sum about 1) or percents (sum about 100)
    ref = grand_pct if grand_pct is not None else sum(raw_pcts)
    scale = 100.0 if abs(ref - 1.0) < abs(ref - 100.0) else 1.0
    notes: List[str] = []
    if scale == 100.0:
        notes.append("percent column published as fractions; multiplied by 100")
        for h in holdings:
            h.pct_nav = round(h.pct_nav * 100.0, 6)
        grand_pct = round(grand_pct * 100.0, 6) if grand_pct is not None else None
        if hedge_sum:   # the hedge block usually shares the table's unit, but some files print it in percent beside fraction holdings: take the one that adds up
            listed = sum(h.pct_nav for h in holdings)
            target = grand_pct if grand_pct is not None else 100.0
            hedge_sum = min((hedge_sum * 100.0, hedge_sum), key=lambda hs: abs(listed + hs - target))
    else:
        grand_pct = round(grand_pct, 6) if grand_pct is not None else None
    if star_rows:
        notes.append(f"{star_rows} row(s) published with a '*' marker instead of a number (below the file's display threshold) are not listed")
    if dup_rows:
        notes.append(f"{dup_rows} row(s) repeated verbatim on the next line of the file are counted once")
    if nca_parts:
        notes.append(f"{nca_parts} cash line(s) summed by the file's 'Net Current Assets' line are shown as that one line")
    if swaps_left_out:
        notes.append(f"{swaps_left_out} derivative exposure line(s) (swap notional, long futures/options) are outside the file's total and are not listed")
    if hedge_rows:
        notes.append(f"{hedge_rows} futures/options hedge line(s) with a negative percent are exposures, not part of net assets, and are not listed")
    return Portfolio(scheme_key=title, as_of=as_of, source_name=source_name, source_url=source_url, holdings=holdings, scheme_name=title,
                     net_assets_lakh=net_assets, published_total_pct=grand_pct, benchmark=benchmark, notes=notes, aliases=aliases,
                     hedge_pct=round(hedge_sum, 6))


def open_workbook(path: str):
    """A workbook object for a file on disk, chosen by what is inside (a file called .xls can be an .xlsx and the other way round)."""
    with open(path, "rb") as fh:
        magic = fh.read(8)
    if magic[:4] == b"PK\x03\x04":
        from .xlsx import Workbook
        return Workbook(path)
    if magic == bytes.fromhex("d0cf11e0a1b11ae1"):
        from .xls import XlsWorkbook
        return XlsWorkbook(path)
    raise NotAPortfolio("not an Excel file (neither .xlsx nor .xls)")
