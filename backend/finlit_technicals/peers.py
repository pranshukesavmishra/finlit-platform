"""Leader / In line / Laggard vs industry peers: a Python port of the TradingView indicator
"Leader & Laggard vs Peers v1.0" (also the peer row of "ST/LT Score Breakdown & Peers v1.2").

From the "Leader and laggard label: developer spec" (Oct 2026). It describes the past 12 months only; it is
never a signal to act on.
  relative return(w) = stock return - index return over w = 13, 26 and 52 weeks (in points)
  rank       peers by the 52-week figure vs the sector index (ties: 26 weeks, then market cap)
  label      k = ceil(30% of ranked peers): Leader = rank <= k and 52-week figure > 0;
             Laggard = rank > n - k and 52-week figure < 0; otherwise In line
  direction  13-week figure >= +5 pts gaining, <= -5 pts weakening
  peers      need 52 weeks of prices, a fresh close and a median traded value of Rs 1 crore a day; 6+ ranked
  stability  weekly, on the last completed week; a new label must come out 2 weekly runs in a row
Weekly closes of the last COMPLETED week are used (Pine: request.security "W", close[1], lookahead on), so the
label changes once a week, after Friday's close.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import pine as P
from .stlt import clean, weekly


def norm_symbol(s: str) -> str:
    """One key for NSE symbols written in different ways (BAJAJ-AUTO = BAJAJ_AUTO, M&M = M_M)."""
    return str(s).strip().upper().replace("-", "_").replace("&", "_")

# The spec's five researched groups (curated)
LL_IT = "TCS,INFY,HCLTECH,WIPRO,TECHM,LTM,PERSISTENT,COFORGE,MPHASIS,OFSS,KPITTECH,HEXT,TATAELXSI,BSOFT"
LL_PH = "SUNPHARMA,CIPLA,DRREDDY,DIVISLAB,LUPIN,AUROPHARMA,ZYDUSLIFE,TORNTPHARM,ALKEM,MANKIND,GLENMARK,BIOCON,GLAND,IPCALAB,AJANTPHARM,ABBOTINDIA"
LL_PVB = "HDFCBANK,ICICIBANK,KOTAKBANK,AXISBANK,INDUSINDBK,IDFCFIRSTB,FEDERALBNK,BANDHANBNK,RBLBANK,YESBANK,CUB,KARURVYSYA,AUBANK"
LL_PSB = "SBIN,BANKBARODA,PNB,CANBK,UNIONBANK,INDIANB,BANKINDIA,IOB,CENTRALBK,MAHABANK,UCOBANK,PSB"
LL_AU = "MARUTI,M&M,TMPV,HYUNDAI,BAJAJ_AUTO,EICHERMOT,HEROMOTOCO,TVSMOTOR,ASHOKLEY,TMCV,BOSCHLTD,MOTHERSON,BHARATFORG,MRF,APOLLOTYRE,BALKRISIND,EXIDEIND,SONACOMS,UNOMINDA,ESCORTS"
CURATED = {1: LL_IT, 2: LL_PH, 3: LL_PVB, 4: LL_PSB, 5: LL_AU}
CURATED_NAME = {1: "IT", 2: "pharma", 3: "private bank", 4: "PSU bank", 5: "auto sector"}
CURATED_IDX = {1: "NSE:CNXIT", 2: "NSE:CNXPHARMA", 3: "NSE:NIFTYPVTBANK", 4: "NSE:CNXPSUBANK", 5: "NSE:CNXAUTO"}
PRESETS = {"auto": "Auto", "it": "IT services", "pharma": "Pharmaceuticals", "pvtbank": "Private sector banks",
           "psubank": "Public sector banks", "autosector": "Auto sector", "industry": "TradingView industry",
           "sector": "TradingView sector (wider)", "custom": "Custom list"}
INDEX_NAMES = {"": "peer average", "NSE:CNXIT": "Nifty IT", "NSE:CNXPHARMA": "Nifty Pharma", "NSE:NIFTYPVTBANK": "Nifty Pvt Bank",
               "NSE:CNXPSUBANK": "Nifty PSU Bank", "NSE:CNXAUTO": "Nifty Auto", "NSE:CNXENERGY": "Nifty Energy",
               "NSE:CNXMETAL": "Nifty Metal", "NSE:CNXREALTY": "Nifty Realty", "NSE:CNXFMCG": "Nifty FMCG",
               "NSE:CNXFINANCE": "Nifty Fin Service", "NSE:CNXMEDIA": "Nifty Media", "NSE:CNXINFRA": "Nifty Infra"}
MKT_SYMS = {1: ("NSE:NIFTY", "Nifty 50"), 2: ("NSE:NIFTYMIDCAP150", "Nifty Midcap 150"),
            3: ("NSE:NIFTYSMLCAP250", "Nifty Smallcap 250"), 0: ("NSE:CNX500", "Nifty 500")}
LABELS = {1: "Leader", 0: "In line", -1: "Laggard", None: "No label"}


def rel_text(idx: int) -> str:
    if idx == 1:
        return "IT: mixed. Leaders beat laggards in 60% of 269 checks since 2005 (35% in 2005-09, 68% 2010-14, 48% 2015-19, 74% since 2020)."
    if idx == 2:
        return "Pharma: consistent. Leaders beat laggards in 64% of 278 checks since 2005 and in every five-year period (58 / 73 / 59 / 67%)."
    if idx in (3, 4):
        return "Banks: mixed. Leaders beat laggards in 60% of 278 checks since 2005 (59 / 59 / 76%, then 43% since 2020)."
    if idx == 5:
        return "Auto: not reliable. Past leaders have not tended to stay ahead: 46% of 278 checks since 2005 (38 / 68 / 52 / 34%)."
    return "No reliability study for this group: the spec's research covers IT, pharma, banks and auto only."


def index_for(kind: str, nm: str) -> str:
    """f_llIdxFor: the NSE sector index for a TradingView industry (I) or sector (S); "" = peer average."""
    if kind == "I":
        if nm in ("Oil Refining/Marketing", "Integrated Oil", "Gas Distributors", "Electric Utilities", "Alternative Power Generation"):
            return "NSE:CNXENERGY"
        if nm in ("Steel", "Other Metals/Minerals", "Aluminum"):
            return "NSE:CNXMETAL"
        if nm == "Real Estate Development":
            return "NSE:CNXREALTY"
        if nm == "Household/Personal Care" or nm.startswith("Food:") or nm.startswith("Beverages"):
            return "NSE:CNXFMCG"
        if nm in ("Finance/Rental/Leasing", "Life/Health Insurance", "Investment Banks/Brokers", "Investment Managers",
                  "Financial Conglomerates", "Major Banks", "Regional Banks"):
            return "NSE:CNXFINANCE"
        if nm == "Movies/Entertainment":
            return "NSE:CNXMEDIA"
        if nm in ("Engineering & Construction", "Construction Materials"):
            return "NSE:CNXINFRA"
        if nm in ("Information Technology Services", "Packaged Software"):
            return "NSE:CNXIT"
        if nm.startswith("Pharmaceuticals"):
            return "NSE:CNXPHARMA"
        if nm in ("Motor Vehicles", "Auto Parts: OEM", "Automotive Aftermarket"):
            return "NSE:CNXAUTO"
        return ""
    return {"Energy Minerals": "NSE:CNXENERGY", "Utilities": "NSE:CNXENERGY", "Finance": "NSE:CNXFINANCE",
            "Technology Services": "NSE:CNXIT", "Health Technology": "NSE:CNXPHARMA", "Consumer Non-Durables": "NSE:CNXFMCG",
            "Non-Energy Minerals": "NSE:CNXMETAL", "Industrial Services": "NSE:CNXINFRA"}.get(nm, "")


def _tk(sym: str) -> str:
    return sym.split(":")[-1]


@dataclass
class PeerDB:
    """TradingView industry (I) and sector (S) lists, in the scripts' order (data/peer_groups.json)."""
    entries: List[Tuple[str, str, List[str]]]

    @classmethod
    def from_groups(cls, data: dict) -> "PeerDB":
        e = [("I", k, list(v)) for k, v in data.get("industries", {}).items()]
        e += [("S", k, list(v)) for k, v in data.get("sectors", {}).items()]
        return cls(e)

    def find(self, kind: str, key: str) -> str:
        for k, nm, lst in self.entries:
            if k == kind and nm == key:
                return ",".join(lst)
        return ""

    def find_ticker(self, tk: str) -> Optional[Tuple[str, str, List[str]]]:
        t = norm_symbol(tk)
        for k, nm, lst in self.entries:
            if t in (norm_symbol(x) for x in lst):
                return k, nm, lst
        return None

    def sector_of(self, industry: str) -> str:
        """TradingView sector of an industry: the sector list that shares the most members with it."""
        fixed = {"Building Products": "Producer Manufacturing", "Containers/Packaging": "Process Industries",
                 "Forest Products": "Non-Energy Minerals", "Office Equipment/Supplies": "Producer Manufacturing",
                 "Investment Trusts/Mutual Funds": "Miscellaneous"}      # TradingView's (FactSet) sectors
        if industry in fixed:
            return fixed[industry]
        members = {norm_symbol(x) for x in self.find("I", industry).split(",") if x}
        best, n_best = "", 0
        for k, nm, lst in self.entries:
            if k == "S":
                n = len(members & {norm_symbol(x) for x in lst})
                if n > n_best:
                    best, n_best = nm, n
        return best

    def home(self, tk: str, kind: str) -> str:
        """Name of the first group of this kind that lists the ticker ("" if none)."""
        t = norm_symbol(tk)
        for k, nm, lst in self.entries:
            if k == kind and t in (norm_symbol(x) for x in lst):
                return nm
        return ""


@dataclass
class PeerParams:
    preset: str = "Auto"
    custom: str = ""
    sec_in: str = "From the peer group"      # | "Custom index" | "Peer average (no index)"
    sec_sym: str = "NSE:CNXIT"
    share: float = 30.0
    dir_pts: float = 5.0
    min_n: int = 6
    min_liq: float = 1.0                     # Rs crore a day
    stable: bool = True
    max_peers: int = 37                      # LL_MAX: 37 in Leader & Laggard v1.0, 30 in ST/LT Breakdown v1.2
    large_cut: float = 107000.0
    mid_cut: float = 32800.0


@dataclass
class Group:
    idx: int                 # 1-5 the spec's groups · 6 industry · 7 sector · 8 group found by ticker · 0 custom list
    peers_list: str
    name: str
    sec_sym: str
    sec_name: str
    industry: str
    sector: str
    symbols: List[str]       # "NSE:XXX", the stock first


def resolve(symbol: str, db: PeerDB, p: PeerParams, industry: Optional[str] = None, sector: Optional[str] = None) -> Group:
    """The peer group exactly as the Pine code picks it. TradingView's industry / sector names come from
    `industry` / `sector` when given, otherwise from the first list in groups.json that holds the ticker."""
    tk = norm_symbol(_tk(symbol.upper()))
    ind = industry if industry is not None else db.home(tk, "I")
    sect = sector if sector is not None else (db.home(tk, "S") or db.sector_of(ind))
    ind_list, sect_list = db.find("I", ind), db.find("S", sect)
    tk_grp = db.find_ticker(tk)

    def has(lst):
        return tk in (norm_symbol(x) for x in lst.split(","))

    cur = next((k for k in (1, 2, 3, 4, 5) if has(CURATED[k])), 0)
    tv = 6 if ind_list else 7 if sect_list else 8 if tk_grp else 0
    pr = p.preset
    if pr == "IT services":
        gi = 1
    elif pr == "Pharmaceuticals":
        gi = 2
    elif pr == "Private sector banks":
        gi = 3
    elif pr == "Public sector banks":
        gi = 4
    elif pr == "Auto sector":
        gi = 5
    elif pr == "TradingView industry":
        gi = tv
    elif pr == "TradingView sector (wider)":
        gi = 7 if sect_list else tv
    elif pr == "Custom list":
        gi = 0
    else:
        gi = 0 if (p.custom and cur == 0 and tv == 0) else cur if cur > 0 else tv
    kind8, name8, list8 = tk_grp if tk_grp else ("", "", [])
    if gi in CURATED:
        lst, name, auto_idx = CURATED[gi], CURATED_NAME[gi], CURATED_IDX[gi]
    elif gi == 6:
        lst, name, auto_idx = ind_list, ind, index_for("I", ind)
    elif gi == 7:
        lst, name, auto_idx = sect_list, sect + " sector", index_for("S", sect)
    elif gi == 8:
        lst, name, auto_idx = ",".join(list8), name8 + (" sector" if kind8 == "S" else ""), index_for(kind8, name8)
    else:
        lst, name, auto_idx = p.custom, "custom-list", ""
    sec = p.sec_sym if p.sec_in == "Custom index" else "" if p.sec_in == "Peer average (no index)" else auto_idx
    # f_llBuild: the stock first, then up to max_peers others (no exchange = NSE), no duplicates
    out = ["NSE:" + _tk(symbol.strip().upper())]
    for part in lst.replace("\n", ",").replace(";", ",").split(","):
        s = part.strip().upper()
        if s and len(out) <= p.max_peers:
            sym = s if ":" in s else "NSE:" + s
            t = _tk(sym)
            if norm_symbol(t) != tk and sym not in out:
                out.append(sym)
    return Group(gi, lst, name, sec, INDEX_NAMES.get(sec, sec), ind, sect, out)


# ─── weekly series lookups ──────────────────────────────────────────────────────────────────────────────
@dataclass
class _W:
    weeks: np.ndarray     # week start (datetime64), ascending
    close: np.ndarray
    tv: np.ndarray        # close x volume
    med13: np.ndarray = None   # median of the 13 weekly traded values ending at each week (ta.median(close*volume, 13))

    def __post_init__(self):
        if self.med13 is None:
            self.med13 = P.median(self.tv, 13) if len(self.tv) else np.array([])

    @classmethod
    def of(cls, df: Optional[pd.DataFrame]) -> "_W":
        if df is None or len(df) == 0:
            return cls(np.array([], dtype="datetime64[ns]"), np.array([]), np.array([]))
        w = weekly(clean(df))
        c = w["close"].to_numpy(dtype=float)
        return cls(w.index.values, c, c * w["volume"].to_numpy(dtype=float))

    def cur(self, week) -> int:
        """Position of this symbol's weekly bar for `week` (its latest bar at or before it); -1 if none."""
        return int(np.searchsorted(self.weeks, week, side="right")) - 1

    def back(self, cur: int, k: int, what: str = "close") -> float:
        j = cur - k
        a = getattr(self, what)
        return float(a[j]) if 0 <= j < len(a) else math.nan

    def median_tv(self, cur: int) -> float:
        """ta.median(close * volume, 13)[1]: the 13 weeks ending at the last completed week."""
        j = cur - 1
        return float(self.med13[j]) if 0 <= j < len(self.med13) else math.nan


@dataclass
class PeerRow:
    symbol: str
    status: int                       # 0 ranked · 1 no data · 2 under 52 weeks · 3 thin trading · 4 stale price
    r13: float = math.nan
    r26: float = math.nan
    r52: float = math.nan
    liq: float = math.nan             # Rs crore a day
    mcap: float = math.nan


@dataclass
class Run:
    """One weekly run (the first daily bar of a new week)."""
    date: pd.Timestamp                # the run's daily bar
    ref_week: pd.Timestamp            # the completed week it ranks
    state: int                        # 0 ranked · 1 off / no peers · 2 not enough history · 3 thin · 4 too few peers · 5 waiting
    raw: Optional[int]
    pub: Optional[int]
    rank: Optional[int]
    ranked: int
    k: int
    rel13: float
    rel26: float
    rel52: float
    rel52m: float
    bench_name: str
    mkt_name: str
    rows: List[PeerRow] = field(default_factory=list)
    b13: float = math.nan
    b52: float = math.nan
    m52: float = math.nan             # the market index's 52-week return


@dataclass
class PeerResult:
    symbol: str
    group: Group
    params: PeerParams
    last: Optional[Run]
    runs: List[Run]
    pub: Optional[int]
    pub_since: Optional[pd.Timestamp]
    changed: bool
    hist: List[int]
    notes: List[str] = field(default_factory=list)

    # ── text pieces, as the Pine tables word them ──
    @property
    def chip(self) -> str:
        return LABELS[self.pub]

    @property
    def direction(self) -> int:
        r = self.last
        if r is None or math.isnan(r.rel13):
            return 0
        return 1 if r.rel13 * 100 >= self.params.dir_pts - 1e-9 else -1 if r.rel13 * 100 <= -self.params.dir_pts + 1e-9 else 0

    def line(self) -> str:
        r, p, g = self.last, self.params, self.group
        if r is None and len(g.symbols) >= 2:
            return "Waiting for a completed week of data"
        if r is None or r.state == 1:
            return f"No peer group for this stock (industry: {g.industry or 'none'}). Pick a group or list the peers"
        if r.state == 5:
            return "Waiting for a completed week of data"
        if r.state == 2:
            return "Not enough price history to compare with peers yet"
        if r.state == 3:
            return f"Excluded: median traded value under Rs {p.min_liq:g} cr a day"
        if r.state == 4:
            return f"Too few comparable companies to rank ({r.ranked} ranked, need {p.min_n})"
        d = self.direction
        return (f"{ordinal(r.rank)} of {r.ranked} {g.name} peers · {pts(r.rel52)} vs {r.bench_name} · {pts(r.rel52m)} vs "
                f"{r.mkt_name} (12 months)" + (" · gaining over 3 months" if d == 1 else " · weakening over 3 months" if d == -1 else ""))

    def pending(self) -> str:
        r = self.last
        if r is not None and r.state == 0 and self.pub is not None and r.raw != self.pub:
            return f"this week: {LABELS[r.raw]} (shows if it holds next week)"
        return ""

    def counts(self) -> Dict[int, int]:
        return {c: sum(1 for v in self.hist if v == c) for c in (1, 0, -1)}


def ordinal(n: int) -> str:
    m100, m10 = n % 100, n % 10
    return f"{n}" + ("th" if 11 <= m100 <= 13 else "st" if m10 == 1 else "nd" if m10 == 2 else "rd" if m10 == 3 else "th")


def pts(x: float) -> str:
    return "n/a" if x is None or math.isnan(x) else ("+" if x >= 0 else "") + f"{x * 100:.1f} pts"


def _ahead(a: PeerRow, b: PeerRow) -> bool:
    """f_llAhead: a ranks ahead of b (higher 52-week figure, then 26-week, then market cap)."""
    def nz(x):
        return 0.0 if math.isnan(x) else x
    return a.r52 > b.r52 or (a.r52 == b.r52 and (a.r26 > b.r26 or (a.r26 == b.r26 and nz(a.mcap) > nz(b.mcap))))


def ordered(rows: Sequence[PeerRow]) -> List[int]:
    """The peers table order (Pine's insertion: ranked rows by _ahead, ties keep list order)."""
    ordv: List[int] = []
    for i, r in enumerate(rows):
        if r.status != 0:
            continue
        pos = len(ordv)
        for k, j in enumerate(ordv):
            if _ahead(r, rows[j]):
                pos = k
                break
        ordv.insert(pos, i)
    return ordv


def compute(stock_daily: pd.DataFrame, daily: Dict[str, pd.DataFrame], group: Group, p: PeerParams = PeerParams(),
            sector_daily: Optional[pd.DataFrame] = None, market_daily: Optional[Dict[str, pd.DataFrame]] = None,
            shares: Optional[Dict[str, float]] = None, cap_class: Optional[int] = None, on: bool = True,
            cache: Optional[dict] = None) -> PeerResult:
    """Run the weekly label over the stock's whole history and return the last state.

    stock_daily   the stock's daily bars (its weeks set the runs)
    daily         {"NSE:SYM": daily bars} for the peers (missing ones count as "not found / no data")
    sector_daily  the group's sector index (None: the equal-weighted peer average is used)
    market_daily  {"NSE:NIFTY" / "NSE:NIFTYMIDCAP150" / "NSE:NIFTYSMLCAP250" / "NSE:CNX500": daily bars}
    shares        {"NSE:SYM": shares outstanding} for market caps (tie-break, and the stock's size bucket)
    cap_class     1 large, 2 mid, 3 small: fixes the stock's size bucket (market index)
    cache         a dict kept between calls to reuse the peers' weekly series (batch runs)
    """
    shares = shares or {}
    market_daily = market_daily or {}
    syms = group.symbols
    stock = clean(stock_daily)
    notes: List[str] = []
    def wk(key, df):
        # weekly series, reused across stocks in a batch run (cache: any dict kept between calls)
        if cache is None or df is None or len(df) == 0:
            return _W.of(df)
        ck = (key, len(df), df.index[-1])
        if ck not in cache:
            cache[ck] = _W.of(df)
        return cache[ck]

    w_syms = [_W.of(stock)] + [wk(s, daily.get(s)) for s in syms[1:]]
    w_sec = wk(group.sec_sym, sector_daily) if group.sec_sym else None
    w_mkt = {k: wk(k, v) for k, v in market_daily.items()}
    if group.sec_sym and (sector_daily is None or len(sector_daily) == 0):
        notes.append(f"{group.sec_name} prices not available: the peer average is the sector benchmark")
    missing = [s for s in syms[1:] if daily.get(s) is None or len(daily.get(s)) == 0]
    if missing:
        notes.append(f"no prices for {len(missing)} peer(s): {', '.join(_tk(s) for s in missing[:8])}{' …' if len(missing) > 8 else ''}")

    sw = w_syms[0]
    runs: List[Run] = []
    pub: Optional[int] = None
    raw_prev: Optional[int] = None
    pub_t: Optional[pd.Timestamp] = None
    hist: List[int] = []
    changed = False
    if len(stock) == 0:
        return PeerResult(_tk(syms[0]), group, p, None, [], None, None, False, [], notes + ["no prices for the stock"])
    first_day = pd.Series(stock.index, index=pd.DatetimeIndex(stock.index)).groupby(
        stock.index - pd.to_timedelta(stock.index.weekday, unit="D")).first()
    first_close = stock["close"].groupby(stock.index - pd.to_timedelta(stock.index.weekday, unit="D")).first()
    sh0 = shares.get(syms[0])
    n_sym = len(syms)
    for j in range(1, len(sw.weeks)):
        week = sw.weeks[j]
        ref = sw.weeks[j - 1]
        day = first_day.iloc[j]
        close_day = float(first_close.iloc[j])
        if cap_class is not None:
            cap = int(cap_class)
        elif sh0:
            mc = sh0 * close_day / 1e7
            cap = 1 if mc >= p.large_cut else 2 if mc >= p.mid_cut else 3
        else:
            cap = 0
        mkt_sym, mkt_name = MKT_SYMS[cap]
        rows: List[PeerRow] = []
        ref_t = None
        for i in range(n_sym):
            ws = w_syms[i]
            cur = ws.cur(week)
            q0, q13, q26, q52 = (ws.back(cur, k) for k in (1, 14, 27, 53)) if cur >= 0 else (math.nan,) * 4
            qt = ws.weeks[cur - 1] if cur - 1 >= 0 else None
            ql = ws.median_tv(cur) / 5 / 1e7 if cur >= 0 else math.nan
            shr = shares.get(syms[i])
            qm = shr * q0 / 1e7 if (shr and not math.isnan(q0)) else math.nan
            stc = 1 if math.isnan(q0) else 2 if (math.isnan(q52) or q52 <= 0) else 3 if (not math.isnan(ql) and ql < p.min_liq) else 0
            if i == 0:
                ref_t = qt
            elif stc == 0 and ref_t is not None and qt is not None and qt < ref_t:
                stc = 4
            r = PeerRow(syms[i], stc, liq=ql, mcap=qm)
            if not math.isnan(q0):
                if not math.isnan(q13) and q13 > 0:
                    r.r13 = q0 / q13 - 1
                if not math.isnan(q26) and q26 > 0:
                    r.r26 = q0 / q26 - 1
                if not math.isnan(q52) and q52 > 0:
                    r.r52 = q0 / q52 - 1
            rows.append(r)
        s13 = s26 = s52 = m52 = math.nan
        if on and w_sec is not None:
            cur = w_sec.cur(week)
            if cur >= 0:
                x0, x13, x26, x52 = (w_sec.back(cur, k) for k in (1, 14, 27, 53))
                if not math.isnan(x52) and x52 > 0 and x13 > 0 and x26 > 0:
                    s13, s26, s52 = x0 / x13 - 1, x0 / x26 - 1, x0 / x52 - 1
        wm = w_mkt.get(mkt_sym)
        if on and wm is not None:
            cur = wm.cur(week)
            if cur >= 0:
                y0, y52 = wm.back(cur, 1), wm.back(cur, 53)
                if not math.isnan(y52) and y52 > 0:
                    m52 = y0 / y52 - 1
        ranked = [r for r in rows if r.status == 0]
        n_r = len(ranked)
        avg_used = math.isnan(s52)
        if avg_used:
            b13 = sum(r.r13 for r in ranked) / n_r if n_r else math.nan
            b26 = sum(r.r26 for r in ranked) / n_r if n_r else math.nan
            b52 = sum(r.r52 for r in ranked) / n_r if n_r else math.nan
        else:
            b13, b26, b52 = s13, s26, s52
        bench_name = "peer average" if avg_used else group.sec_name
        k = math.ceil(p.share / 100.0 * n_r)
        self_st = rows[0].status
        state = (1 if (not on or n_sym < 2) else 5 if ref_t is None else 2 if self_st in (1, 2) else 3 if self_st == 3
                 else 4 if (n_r < p.min_n or math.isnan(b52)) else 0)
        rank = rel13 = rel26 = rel52 = rel52m = None
        raw = None
        if state == 0:
            rank = 1 + sum(1 for jx in range(n_sym) if jx != 0 and rows[jx].status == 0 and _ahead(rows[jx], rows[0]))
            rel13, rel26, rel52 = rows[0].r13 - b13, rows[0].r26 - b26, rows[0].r52 - b52
            rel52m = rows[0].r52 - m52 if not math.isnan(m52) else math.nan
            raw = 1 if (rank <= k and rel52 > 0) else -1 if (rank > n_r - k and rel52 < 0) else 0
        # the weekly run: publish a new label only when the same raw label came out two runs in a row
        pub_old = pub
        if raw is None:
            if state in (2, 3, 4):
                pub, pub_t = None, None
        elif pub is None or not p.stable or raw == raw_prev:
            if pub is None or pub != raw:
                pub, pub_t = raw, pd.Timestamp(day)
        raw_prev = raw
        hist.append(9 if pub is None else pub)
        if len(hist) > 52:
            hist.pop(0)
        changed = pub is not None and pub_old is not None and pub != pub_old
        nan = math.nan
        runs.append(Run(pd.Timestamp(day), pd.Timestamp(ref), state, raw, pub, rank, n_r, k,
                        nan if rel13 is None else rel13, nan if rel26 is None else rel26, nan if rel52 is None else rel52,
                        nan if rel52m is None else rel52m, bench_name, mkt_name, rows, b13, b52, m52))
    last = runs[-1] if runs else None
    if not runs:
        notes.append("no completed week yet")
    return PeerResult(_tk(syms[0]), group, p, last, runs, pub, pub_t, changed if runs else False, hist, notes)


# ─── text output ────────────────────────────────────────────────────────────────────────────────────────
def _why(r: PeerRow) -> str:
    return {1: "not found / no data", 2: "under 52 weeks of prices", 3: f"thin: Rs {r.liq:.1f} cr/day", 4: "stale price"}.get(r.status, "")


def table_rows(res: PeerResult, full: bool = False) -> List[Tuple[str, str, str, str, str, str]]:
    """Rows of the peers table: (#, stock, status, vs sector 12M, vs sector 3M, vs market 12M)."""
    r = res.last
    if r is None:
        return []
    rows = r.rows
    ordv = ordered(rows)
    n_r = len(ordv)
    kk = math.ceil(res.params.share / 100.0 * n_r)
    out = []
    for k, i in enumerate(ordv):
        if full or k < 10 or i == 0:
            x52 = rows[i].r52 - r.b52
            lab = 1 if (k + 1 <= kk and x52 > 0) else -1 if (k + 1 > n_r - kk and x52 < 0) else 0
            shown = res.pub if (i == 0 and res.params.stable and res.pub is not None) else lab
            status = LABELS[shown] + (f" ({LABELS[lab]} this wk)" if shown != lab else "")
            x13 = rows[i].r13 - r.b13
            xm = rows[i].r52 - r.m52
            out.append((str(k + 1), _tk(rows[i].symbol) + (" ◀" if i == 0 else ""), status, pts(x52), pts(x13), pts(xm)))
        elif k == 10:
            more = n_r - 10 - (1 if ordv.index(0) >= 10 else 0) if 0 in ordv else n_r - 10
            out.append(("…", f"{more} more", "", "", "", ""))
    for i, row in enumerate(rows):
        if row.status != 0:
            out.append(("–", _tk(row.symbol) + (" ◀" if i == 0 else ""), "Not ranked: " + _why(row), "", "", ""))
    return out


def status_text(res: PeerResult) -> str:
    """The status box: label, rank line, pending label, reliability note."""
    L = [f"[{res.chip}] {res.symbol} · {res.line()}"]
    if res.pending():
        L.append("  " + res.pending())
    r = res.last
    if r is not None and r.state == 0:
        L.append(f"  Relative return vs {r.bench_name}: 3M {pts(r.rel13)} · 6M {pts(r.rel26)} · 12M {pts(r.rel52)}   ·   "
                 f"vs {r.mkt_name}: 12M {pts(r.rel52m)}")
        L.append(f"  Top {r.k} of {r.ranked} can be Leaders (12-month figure above 0), bottom {r.k} Laggards (below 0)."
                 + (" No sector index: the benchmark is the equal-weighted average of the ranked peers." if r.bench_name == "peer average" else ""))
    cnt = res.counts()
    since = f"Label since {res.pub_since:%d %b %Y}. " if res.pub_since is not None else ""
    L.append(f"  {since}Last {len(res.hist)} weekly runs: Leader {cnt[1]} · In line {cnt[0]} · Laggard {cnt[-1]}.")
    L.append(f"  Held here? {rel_text(res.group.idx)} A historical frequency, not a probability of future returns.")
    L.append("  Describes past price performance over 12 months; not a recommendation.")
    for nt in res.notes:
        L.append(f"  note: {nt}")
    return "\n".join(L)


def peers_table_text(res: PeerResult, full: bool = False) -> str:
    r = res.last
    if r is None:
        return ""
    mkt = r.mkt_name
    head = f"Peers · {res.group.name} · vs {r.bench_name} · week of {r.ref_week:%d %b %Y}"
    cols = ("#", "Stock", "Status", "vs sector 12M", "vs sector 3M", f"vs {mkt} 12M")
    rows = table_rows(res, full)
    ranked = [x for x in rows if x[0] not in ("…", "–")]
    wid = [max([len(cols[c])] + [len(x[c]) for x in ranked]) for c in range(6)]
    L = [head, "  " + "  ".join(cols[c].ljust(wid[c]) if c < 3 else cols[c].rjust(wid[c]) for c in range(6))]
    for x in rows:
        if x[0] in ("…", "–"):
            L.append("  " + "  ".join([x[0].ljust(wid[0]), x[1].ljust(wid[1]), x[2]]).rstrip())
        else:
            L.append("  " + "  ".join(x[c].ljust(wid[c]) if c < 3 else x[c].rjust(wid[c]) for c in range(6)))
    L.append("  Status = this week's rank. This stock's own label changes only after 2 weekly runs in a row.")
    return "\n".join(L)


def history_text(res: PeerResult, weeks: int = 12) -> str:
    """The indicator's pane as a table: the label and the 12-month points for the last N weekly runs."""
    L = ["Week ranked     Label     Rank    vs sector 12M   vs market 12M   vs sector 3M"]
    for r in res.runs[-weeks:]:
        rk = f"{r.rank}/{r.ranked}" if r.rank else "-"
        L.append(f"{r.ref_week:%d %b %Y}     {LABELS[r.pub]:<8}  {rk:<6}  {pts(r.rel52):>13}   {pts(r.rel52m):>13}   {pts(r.rel13):>12}")
    return "\n".join(L)
