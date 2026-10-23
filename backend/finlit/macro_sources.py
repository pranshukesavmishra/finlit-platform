"""India macro data: the official sources and their parsers. Each parser takes the raw answer and returns plain points; nothing here touches
the network or the database (finlit/macro.py does that), so every rule is tested against recorded answers (tests/fixtures/macro).

Sources (all public, no key):
  MoSPI eSankhyiki API  https://api.mospi.gov.in      CPI (base 2024, current and back series), WPI (bases 2011-12 and 2022-23), quarterly GDP
                                                      (bases 2011-12 and 2022-23), IIP (base 2022-23), PLFS monthly unemployment, and RBI tables
                                                      MoSPI republishes (monthly foreign exchange reserves, monthly rupee exchange rates)
  RBI website            https://www.rbi.org.in        "Current Rates" on the home page (policy rates, CRR, SLR, FBIL reference rates) and the
                                                      weekly "Bulletin Weekly Statistical Supplement - Extract" press release (reserves, bank credit,
                                                      deposits, money supply), found through RBI's press-release RSS feed
Rules: figures are reproduced as published. Where MoSPI publishes an inflation or growth rate (CPI, IIP) it is used as it is; where it
publishes only an index or a level (WPI, GDP) the year-on-year change is worked out from two figures of the SAME base year, never across a
re-base. Anything that cannot be read is skipped, never guessed.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple

MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
MONTHS3 = {k[:3]: v for k, v in MONTHS.items()}


def month_end(y: int, m: int) -> date:
    """Points are dated by the last day of their period (a month, a quarter, a week ending)."""
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def num(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "–", "NA", "N.A.", "na", "null", "None", "..", "…"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def month_of(v) -> Optional[int]:
    if isinstance(v, int):
        return v if 1 <= v <= 12 else None
    s = str(v or "").strip().lower()
    return MONTHS.get(s) or MONTHS3.get(s[:3])


Points = Dict[date, float]


@dataclass
class Parsed:
    """Points per series key, plus anything the page should say about how they were made."""
    series: Dict[str, Points] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)

    def put(self, key: str, d: date, v: Optional[float], label: Optional[str] = None) -> None:
        if v is None:
            return
        self.series.setdefault(key, {})[d] = v
        if label:
            self.labels.setdefault(key, label)

    def merge(self, other: "Parsed") -> "Parsed":
        for k, pts in other.series.items():
            self.series.setdefault(k, {}).update(pts)
        for k, v in other.labels.items():
            self.labels.setdefault(k, v)
        return self


def rows(payload) -> List[dict]:
    """The record list of a MoSPI answer ({"data": [...]}); an error answer is an empty list."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [r for r in payload["data"] if isinstance(r, dict)]
    return []


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:40]


# ---------------------------------------------------------------------------------------------------- CPI (MoSPI, base 2024)
CPI_HEAD = "CPI (General)"
SECTOR_KEY = {"Combined": "cpi", "Rural": "cpi_rural", "Urban": "cpi_urban"}


def parse_cpi(payload) -> Parsed:
    """CPI base 2024 (current series from 2025, back series 2013-2024). MoSPI publishes the year-on-year inflation rate with each index;
    that published rate is what is stored. Headline for all-India Combined, Rural and Urban; divisions (food, housing, ...) for Combined."""
    out = Parsed()
    for r in rows(payload):
        if (r.get("state") or "").strip().lower() != "all india" or r.get("group") or r.get("class") or r.get("item"):
            continue
        y, m = num(r.get("year")), month_of(r.get("month"))
        if not y or not m:
            continue
        d, sector, div = month_end(int(y), m), (r.get("sector") or "").strip(), (r.get("division") or "").strip()
        infl, idx = num(r.get("inflation")), num(r.get("index"))
        if div == CPI_HEAD:
            if sector in SECTOR_KEY:
                out.put(SECTOR_KEY[sector], d, infl)
                out.put(SECTOR_KEY[sector] + "_idx", d, idx)
        elif sector == "Combined" and div:
            key = "cpi_div_" + (str(r.get("code") or "").strip() or slug(div))
            out.put(key, d, infl, label=div)
    return out


# ---------------------------------------------------------------------------------------------------- WPI (MoSPI)
WPI_GROUPS = {   # code (both bases) -> series key
    "1000000000": "wpi", "1100000000": "wpi_primary", "1200000000": "wpi_fuel", "1300000000": "wpi_mfg", "1400000000": "wpi_food", "2000000000": "wpi_food",
}
WPI_LABEL = {"wpi": "All commodities", "wpi_primary": "Primary articles", "wpi_fuel": "Fuel and power", "wpi_mfg": "Manufactured products", "wpi_food": "Food index"}


def parse_wpi_index(payload, group_code: str) -> Points:
    """Index values of one major group (the group-level rows only; the API also returns items under it). Both bases' spellings."""
    out: Points = {}
    for r in rows(payload):
        if r.get("group") or r.get("sub_group") or r.get("subgroup") or r.get("item"):
            continue
        y, m, v = num(r.get("year")), month_of(r.get("month")), num(r.get("index_value"))
        if y and m and v:
            out[month_end(int(y), m)] = v
    return out


def yoy(points: Points) -> Points:
    """Year-on-year change in per cent of an index or level, against the same month (or quarter end) a year earlier in the SAME series,
    so never across a re-base. A missing earlier point means no figure."""
    out: Points = {}
    for d, v in points.items():
        p = points.get(month_end(d.year - 1, d.month))
        if p:
            out[d] = round((v / p - 1) * 100, 2)
    return out


# ---------------------------------------------------------------------------------------------------- GDP (MoSPI, National Accounts)
QUARTER_END = {"Q1": 6, "Q2": 9, "Q3": 12, "Q4": 3}


def fy_quarter_end(fy: str, q: str) -> Optional[date]:
    """'2026-27', 'Q1' -> 2026-06-30. Indian financial years run April to March; Q4 ends in March of the second year."""
    m = re.match(r"^(\d{4})-(\d{2,4})$", (fy or "").strip())
    if not m or q not in QUARTER_END:
        return None
    y = int(m.group(1)) + (1 if q == "Q4" else 0)
    return month_end(y, QUARTER_END[q])


def parse_gdp(payload) -> Tuple[Points, Points]:
    """Quarterly GDP levels (₹ crore): (constant prices, current prices). When a quarter appears more than once (revisions), the latest
    revision listed wins; a blank revision is the current estimate."""
    const: Points = {}
    cur: Points = {}
    for r in rows(payload):
        if (r.get("indicator") or "").strip().lower() != "gross domestic product" or (r.get("frequency") or "").lower() != "quarterly":
            continue
        d = fy_quarter_end(str(r.get("year")), str(r.get("quarter")))
        if not d:
            continue
        c, n = num(r.get("constant_price")), num(r.get("current_price"))
        if c:
            const[d] = c
        if n:
            cur[d] = n
    return const, cur


# ---------------------------------------------------------------------------------------------------- IIP and unemployment (MoSPI)
IIP_KEYS = {("General", "General"): "iip", ("Sectoral", "Mining"): "iip_mining", ("Sectoral", "Manufacturing"): "iip_mfg", ("Sectoral", "Electricity"): "iip_elec",
            ("Use-based category", "Capital Goods"): "iip_capital", ("Use-based category", "Consumer Durables"): "iip_durables",
            ("Use-based category", "Consumer Non-durables"): "iip_nondurables", ("Use-based category", "Infrastructure/ Construction Goods"): "iip_infra",
            ("Use-based category", "Primary Goods"): "iip_primarygoods", ("Use-based category", "Intermediate Goods"): "iip_intermediate"}


def parse_iip(payload) -> Parsed:
    """Index of Industrial Production: MoSPI's published year-on-year growth rate for the general index, the three sectors and the
    use-based groups (sub-sector rows are left out)."""
    out = Parsed()
    for r in rows(payload):
        if (r.get("sub_category") or "").strip():
            continue
        key = IIP_KEYS.get(((r.get("type") or "").strip(), (r.get("category") or "").strip()))
        y, m = num(r.get("year")), month_of(r.get("month"))
        if key and y and m:
            out.put(key, month_end(int(y), m), num(r.get("growth_rate")))
    return out


def parse_plfs(payload) -> Parsed:
    """PLFS monthly unemployment rate (current weekly status), all India, rural + urban, persons: aged 15 and above (the headline) and
    15-29 (youth); plus urban 15+."""
    out = Parsed()
    for r in rows(payload):
        if (r.get("state") or "").strip().lower() != "all india" or (r.get("frequency") or "").lower() != "monthly":
            continue
        if "unemployment" not in (r.get("indicator") or "").lower():
            continue
        y, m = num(r.get("year")), month_of(r.get("month"))
        if not y or not m:
            continue
        age, g, sec = (r.get("AgeGroup") or "").strip().lower(), (r.get("gender") or "").strip().lower(), (r.get("sector") or "").replace(" ", "").lower()
        if g != "person":
            continue
        d, v = month_end(int(y), m), num(r.get("value"))
        if sec == "rural+urban" and age == "15 years and above":
            out.put("unemployment", d, v)
        elif sec == "rural+urban" and age == "15-29 years":
            out.put("unemployment_youth", d, v)
        elif sec == "urban" and age == "15 years and above":
            out.put("unemployment_urban", d, v)
    return out


# ---------------------------------------------------------------------------------------------------- RBI tables MoSPI republishes
def parse_rbi_reserves_monthly(payload) -> Points:
    """Foreign exchange reserves, end of month, total, US$ million -> US$ billion."""
    out: Points = {}
    for r in rows(payload):
        if (r.get("foreign_exchange_reserve_type") or "").strip() != "Total" or "US" not in (r.get("foreign_exchange_reserve_currency") or ""):
            continue
        y, m, v = num(r.get("year")), month_of(r.get("month")), num(r.get("value"))
        if y and m and v:
            out[month_end(int(y), m)] = round(v / 1000, 3)
    return out


def parse_rbi_usdinr_monthly(payload) -> Points:
    """Rupees per US dollar, monthly average of the reference rate."""
    out: Points = {}
    for r in rows(payload):
        if (r.get("currency") or "").strip().upper() not in ("US DOLLAR", "USD", "US $") or (r.get("reference_rate") or "").strip() != "Average":
            continue
        y, m, v = num(r.get("year")), month_of(r.get("month")), num(r.get("value"))
        if y and m and v:
            out[month_end(int(y), m)] = v
    return out


# ---------------------------------------------------------------------------------------------------- RBI website
def text_of(fragment: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fragment, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


RATE_LABELS = {
    "repo": r"Policy Repo Rate", "sdf": r"Standing Deposit Facility Rate", "msf": r"Marginal Standing Facility Rate", "bank_rate": r"Bank Rate",
    "reverse_repo": r"Fixed Reverse Repo Rate", "crr": r"CRR", "slr": r"SLR",
}
FX_LABELS = {"usdinr": r"INR\s*/\s*1\s*USD", "gbpinr": r"INR\s*/\s*1\s*GBP", "eurinr": r"INR\s*/\s*1\s*EUR", "jpyinr": r"INR\s*/\s*100\s*JPY"}


def parse_rbi_home(page: str) -> Optional[dict]:
    """The 'Current Rates' panel of RBI's home page: policy rates and reserve ratios (per cent) and FBIL reference rates with their time.
    None when the panel is not there (a redesign): the caller then keeps the last good reading."""
    t = text_of(page)
    i = t.find("Current Rates")
    if i < 0:
        return None
    seg = t[i:i + 2500]
    out: dict = {"rates": {}, "fx": {}}
    for k, lab in RATE_LABELS.items():
        m = re.search(lab + r"\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*%", seg)
        if m:
            out["rates"][k] = float(m.group(1))
    for k, lab in FX_LABELS.items():
        m = re.search(lab + r"\s*:\s*([0-9]+(?:\.[0-9]+)?)", seg)
        if m:
            out["fx"][k] = float(m.group(1))
    m = re.search(r"As at\s+([0-9.: ]+[ap]m)\s+of\s+([A-Za-z]+ \d{1,2}, \d{4})", seg)
    out["fxAsOf"] = datetime.strptime(m.group(2), "%B %d, %Y").date().isoformat() if m else None
    if "repo" not in out["rates"]:
        return None
    return out


def latest_wss_link(rss: str) -> Optional[Tuple[str, str]]:
    """(link, publication date) of the newest 'Weekly Statistical Supplement - Extract' press release in RBI's RSS feed."""
    for item in re.findall(r"<item>(.*?)</item>", rss, re.S):
        title = text_of(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", item, re.S) or [None, ""])[1]))
        if re.search(r"Weekly Statistical Supplement\s*[–-]\s*Extract", title, re.I):
            link = (re.search(r"<link>(.*?)</link>", item, re.S) or [None, ""])[1].strip()
            pub = (re.search(r"<pubDate>(.*?)</pubDate>", item, re.S) or [None, ""])[1].strip()
            if re.match(r"^https://(www\.)?rbi\.org\.in/", link):
                return link, pub
    return None


def _table_rows(seg: str) -> List[List[str]]:
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S | re.I):
        cells = [text_of(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if any(cells):
            out.append(cells)
    return out


def _section(page: str, start: str, stop: Optional[str]) -> str:
    i = page.find(start)
    if i < 0:
        return ""
    j = page.find(stop, i + len(start)) if stop else -1
    return page[i:j if j > 0 else len(page)]


def _date_words(s: str) -> Optional[date]:
    m = re.search(r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s+(\d{4})", s)
    if not m or not month_of(m.group(1)):
        return None
    return date(int(m.group(3)), month_of(m.group(1)), int(m.group(2)))


def parse_wss_extract(page: str) -> Optional[dict]:
    """RBI's weekly WSS extract press release: foreign exchange reserves (US$ million, with the week's, financial year's and year's change
    as RBI states them), bank credit and aggregate deposit growth year on year, and M3 growth year on year. None if the reserves table
    is not there."""
    res = _section(page, "Foreign Exchange Reserves", "Scheduled Commercial Banks")
    if not res:
        return None
    asof = _date_words(text_of(res[:600]))
    items: Dict[str, dict] = {}
    names = {"Total Reserves": "total", "Foreign Currency Assets": "fca", "Gold": "gold", "SDRs": "sdr", "Reserve Position in the IMF": "imf"}
    for cells in _table_rows(res):
        label = re.sub(r"^\d+(\.\d+)*\s*", "", cells[0]).replace("#", "").replace("*", "").strip()
        if label in names and len(cells) >= 9:
            v = [num(c) for c in cells[1:9]]   # ₹ cr, US$ mn for: level, week, end-March, year
            items[names[label]] = {"inr": v[0], "usd": v[1], "weekUsd": v[3], "fyUsd": v[5], "yearUsd": v[7]}
    if "total" not in items or asof is None:
        return None
    out: dict = {"reservesAsOf": asof.isoformat(), "reserves": items}
    banks = _section(page, "Scheduled Commercial Banks", "Money Stock")
    if banks:
        bas = _date_words(text_of(banks[:800]).replace("Oct.", "Oct").replace("Sept.", "Sep"))
        for cells in _table_rows(banks):
            lab = cells[0].lower()
            if "growth (per cent)" in lab and len(cells) >= 7:
                key = "deposits_yoy" if lab.startswith("2.1a") else "credit_yoy" if lab.startswith("7.1a") else None
                if key:
                    out[key] = num(cells[-1])
        out["banksAsOf"] = bas.isoformat() if bas else None
    money = _section(page, "Money Stock", "Liquidity Operations")
    if money:
        for cells in _table_rows(money):
            if cells[0].strip() == "M3" and len(cells) >= 13:
                out["m3_yoy"] = num(cells[-1])
        head = text_of(money[:1500])
        m = re.search(r"Mar\.\s*31\s*\|?\s*([A-Z][a-z]{2})\.?\s*(\d{1,2})", head)
        mm = re.search(r"Outstanding as on.*?(\d{4})", head)
        if m and mm and month_of(m.group(1)):
            out["moneyAsOf"] = date(int(mm.group(1)), month_of(m.group(1)), int(m.group(2))).isoformat()
    return out


def last_friday(y: int, m: int) -> date:
    d = month_end(y, m)
    return date.fromordinal(d.toordinal() - (d.weekday() - 4) % 7)


def wss_reserve_points(w: dict) -> Points:
    """Weekly reserves in US$ billion: the week itself and the two earlier weeks RBI states the change against, worked out exactly from
    RBI's own variation figures: the same week a year earlier (52 weeks back) and end-March (the last Friday of March that opened the
    financial year)."""
    asof = date.fromisoformat(w["reservesAsOf"])
    t = w["reserves"]["total"]
    out: Points = {asof: round(t["usd"] / 1000, 3)}
    if t.get("yearUsd") is not None:
        out[date.fromordinal(asof.toordinal() - 364)] = round((t["usd"] - t["yearUsd"]) / 1000, 3)
    if t.get("fyUsd") is not None:
        fy_start = asof.year if asof.month >= 4 else asof.year - 1
        out[last_friday(fy_start, 3)] = round((t["usd"] - t["fyUsd"]) / 1000, 3)
    return out


# ---------------------------------------------------------------------------------------------------- policy repo rate decisions
@dataclass(frozen=True)
class Decision:
    date: date
    rate: float
    change_bp: int
    source: str


def repo_series(decisions: Iterable[Decision], today: date) -> Points:
    """Month-end repo rate from the list of decisions (a step line: the rate in force at each month end), up to today."""
    ds = sorted(decisions, key=lambda x: x.date)
    if not ds:
        return {}
    out: Points = {}
    y, m = ds[0].date.year, ds[0].date.month
    k = 0
    while (y, m) <= (today.year, today.month):
        end = month_end(y, m)
        while k + 1 < len(ds) and ds[k + 1].date <= end:
            k += 1
        if ds[k].date <= end:
            out[min(end, today)] = ds[k].rate
        y, m = (y + (m == 12), m % 12 + 1)
    return out
