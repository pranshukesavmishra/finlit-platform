"""Every advanced-chart figure, worked out from the stored snapshot sections (no provider calls), with a reason code for every missing value.

One code path for both modes: `history(sections)` gives one value per financial year (oldest first) for every yearly metric;
`latest(sections, screener)` is the last year of that history plus the price-window and "today" figures, flattened to `ax_<id>` keys for
`scores.metrics` (merged in screener/compute.py). Definitions are in docs/ADVANCED-CHARTS-PLAN.md section 1 and in catalog.METRIC_LIST;
deviations are listed in docs/ADVANCED-CHARTS-API.md.

Statements are aligned by period-end DATE (the P&L, balance sheet and cash flow tables can hold different years), never by position.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .catalog import FY_IDS, HIST_KEYS, LENDER_DROP

Num = Optional[float]
Val = Tuple[Num, Optional[str]]      # (value, reason code when the value is None)
GAP_MIN, GAP_MAX = 330, 400          # days between two consecutive financial-year ends
SHARE_JUMP = 1.25                    # share count change beyond x1.25 or /1.25: per-share growth not comparable
SHARE_WITH_ACTION = 0.05             # ... or beyond 5% when a bonus or split happened between the two year ends
JUMP = math.log(1.8)                 # a one-day move above +80% / below -44%: a split, bonus or bad tick
START_DAYS = 7                       # a window's close must be within 7 days of its target date
BASIS_TOL = 0.03                     # mean of our daily closes in a year vs the provider's adjusted average price
BASIS_MIN_DAYS = 150                 # closes needed in a year to compare its average with the provider's
RECON_REL, RECON_ABS = 0.02, 0.02    # P&L identity tolerance (2%, Rs 0.02 crore)
SIGNAL_DAYS = 75                     # results are out by 60 days after the year end (SEBI); 75 leaves a margin
DECLARE_DAYS = 183                   # a final dividend is declared within about six months of the year end
VOL_SESSIONS, VOL_MIN = 756, 700
HIST_IDS = [k for k in FY_IDS] + ["ret_fy", "tsr_fy", "pe", "pb"]
WINDOW_LATEST = ["ret_fy", "tsr_fy", "pe_fy", "pb_fy", "vol3y", "mdd3y", "inst_chg", "ret_inst", "pe_sig", "pb_sig", "g_eps_sig", "g_rev_sig", "fwd12"]
TODAY_IDS = ["pe", "pb", "ev_ebitda", "ev_sales", "ev_cfo", "peg", "mcap", "dy", "fcf_yield", "cfo_yield", "sales_per_employee"]
AGG_GROWTH = {"g_rev": ("pl", "revenue"), "g_np": ("pl", "@np"), "g_ebitda": ("pl", "operating_profit"), "g_ebit": ("pl", None),
              "g_pbt": ("pl", "profit_before_tax"), "g_tax": ("pl", "tax"), "g_dep": ("pl", "depreciation"), "g_int": ("pl", "finance_costs"),
              "g_cfo": ("cf", "operating"), "g_fcf": ("cf", "free_cash_flow"), "g_capex": ("cf", "capex"), "g_assets": ("bs", "total_assets"),
              "g_bv": ("bs", "total_equity"), "g_wc": ("bs", None), "g_recv": ("bs", "receivables"), "g_inv": ("bs", "inventories"), "g_debt": ("bs", None)}
COMPONENTS = ["equity", "ta", "ca", "cl", "tl", "debt", "cash", "base", "oi", "exc", "ebit"]
TODAY_COL = {"pe": "pe", "pb": "pb", "ev_ebitda": "ev_ebitda", "ev_sales": "ev_sales", "peg": "peg", "mcap": "market_cap", "dy": "dividend_yield",
             "sales_per_employee": "sales_per_employee"}


def _n(v: Any) -> Num:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _d(v: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def _div(a: Val, b: Val, scale: float = 1.0, zero: str = "den_zero") -> Val:
    if a[0] is None:
        return None, a[1]
    if b[0] is None:
        return None, b[1]
    if b[0] == 0:
        return None, zero
    return a[0] / b[0] * scale, None


def _growth(cur: Val, prev: Val) -> Val:
    if cur[0] is None:
        return None, cur[1]
    if prev[0] is None:
        return None, prev[1]
    if prev[0] <= 0:
        return None, "base_le0"
    return (cur[0] / prev[0] - 1.0) * 100.0, None


class _Stmt:
    """One statement table keyed by period-end date."""

    def __init__(self, table: Optional[dict]):
        t = table or {}
        self.periods: List[str] = list(t.get("periods") or [])
        self.ends: List[Optional[date]] = [_d(e) for e in (t.get("periodEnds") or [])]
        self.rows: Dict[str, list] = t.get("rows") or {}
        self.pos = {e: i for i, e in enumerate(self.ends) if e is not None}

    def has(self, key: str) -> bool:
        return key in self.rows

    def at(self, key: str, end: Optional[date]) -> Val:
        if end is None or end not in self.pos:
            return None, "no_data"
        row = self.rows.get(key)
        if row is None:
            return None, "no_data"
        i = self.pos[end]
        v = _n(row[i]) if i < len(row) else None
        return (v, None) if v is not None else (None, "no_data")

    def prev_end(self, end: Optional[date]) -> Tuple[Optional[date], Optional[str]]:
        """The period before `end` in this table, or a reason (no_prev, gap)."""
        if end is None or end not in self.pos:
            return None, "no_data"
        i = self.pos[end]
        if i == 0 or self.ends[i - 1] is None:
            return None, "no_prev"
        p = self.ends[i - 1]
        if not GAP_MIN <= (end - p).days <= GAP_MAX:  # type: ignore[operator]
            return None, "gap"
        return p, None

    def growth(self, key: str, end: Optional[date], absolute: bool = False, zero_if_absent: bool = False) -> Val:
        cur = self.at_z(key, end, zero_if_absent)
        p, why = self.prev_end(end)
        prev = (None, why) if p is None else self.at_z(key, p, zero_if_absent)
        if absolute:
            cur = (abs(cur[0]) if cur[0] is not None else None, cur[1])
            prev = (abs(prev[0]) if prev[0] is not None else None, prev[1])
        return _growth(cur, prev)

    def at_z(self, key: str, end: Optional[date], zero_if_absent: bool) -> Val:
        if zero_if_absent and not self.has(key) and end in self.pos:
            return 0.0, None
        return self.at(key, end)


class _Prices:
    def __init__(self, price: Optional[dict], actions: Sequence[dict]):
        daily = (price or {}).get("daily") or {}
        pairs = [(_d(t), _n(c)) for t, c in zip(daily.get("t") or [], daily.get("c") or [])]
        pairs = [(d, c) for d, c in pairs if d is not None and c is not None and c > 0]
        self.dates = [d for d, _ in pairs]
        self.closes = [c for _, c in pairs]
        vols = daily.get("v") or []
        self.jumps = [i for i in range(1, len(self.closes)) if abs(math.log(self.closes[i] / self.closes[i - 1])) > JUMP]
        self.events = sorted(d for d in (_d(a.get("date")) for a in actions if any(k in str(a.get("type", "")) for k in ("bonus", "split"))) if d)
        self.n = len(self.closes)
        self.vols = vols

    def index_on_or_before(self, target: date) -> Optional[int]:
        lo, hi, found = 0, self.n - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.dates[mid] <= target:
                found, lo = mid, mid + 1
            else:
                hi = mid - 1
        return found

    def close_at(self, target: date) -> Tuple[Optional[int], Optional[str]]:
        if not self.n:
            return None, "short_history"
        i = self.index_on_or_before(target)
        if i is None:
            return None, "short_history"
        if (target - self.dates[i]).days > START_DAYS:
            return None, "start_gap"
        return i, None

    def clean(self, i0: int, i1: int) -> bool:
        """No jump day and no split/bonus inside (i0, i1]."""
        if any(i0 < j <= i1 for j in self.jumps):
            return False
        d0, d1 = self.dates[i0], self.dates[i1]
        return not any(d0 < e <= d1 for e in self.events)


def _quarter_end(label: Any) -> Optional[date]:
    try:
        d = datetime.strptime(str(label), "%b %Y").date()
    except ValueError:
        return None
    return _add_months(d.replace(day=1), 1) - timedelta(days=1)


class Company:
    """The parsed sections of one company and every per-year figure."""

    def __init__(self, sections: Dict[str, dict], today: Optional[date] = None):
        self.today = today or date.today()
        fin = (sections.get("financials") or {}).get("yearly") or {}
        self.pl, self.bs, self.cf = _Stmt(fin.get("pl")), _Stmt(fin.get("bs")), _Stmt(fin.get("cf"))
        ratios = sections.get("ratios") or {}
        hist = ratios.get("history") or {}
        self.hist_periods: List[str] = list(hist.get("periods") or [])
        self.hist_rows: Dict[str, list] = hist.get("rows") or {}
        vh = ratios.get("valuationHistory") or {}
        self.vh = {k: dict(zip(vh.get("periods") or [], v or [])) for k, v in (vh.get("rows") or {}).items()}
        summary = sections.get("summary") or {}
        self.is_bank = bool((summary.get("dataQuality") or {}).get("isBank"))
        events = sections.get("events") or {}
        self.actions = [a for a in events.get("actions") or [] if isinstance(a, dict) and a.get("date")]
        self.px = _Prices(sections.get("price"), self.actions)
        self.own = sections.get("ownership") or {}
        self.fys = self.pl.periods
        self.ends = self.pl.ends
        self.np_key = "net_profit_continuing" if self.pl.has("net_profit_continuing") else "net_profit"
        self.dps = self._dps_by_fy()
        eq_last = self._last_equity()
        self.neg_equity_latest = eq_last is not None and eq_last <= 0

    # ------------------------------------------------------------ helpers
    def _last_equity(self) -> Num:
        row = self.bs.rows.get("total_equity") or []
        vals = [_n(v) for v in row if _n(v) is not None]
        return vals[-1] if vals else None

    def _dps_by_fy(self) -> Dict[str, float]:
        """Dividend per share declared for each financial year (split/bonus adjusted), summed from every stored dividend, the same rule as
        events.dividends_by_fiscal_year (final dividends count for the year they follow) but without its six-year cut."""
        out: Dict[str, float] = {}
        for a in self.actions:
            if str(a.get("type", "")).endswith("dividend") and a.get("forFY"):
                out[a["forFY"]] = out.get(a["forFY"], 0.0) + (_n(a.get("adjustedAmount")) or 0.0)
        return out

    def end(self, i: int) -> Optional[date]:
        return self.ends[i] if 0 <= i < len(self.ends) else None

    def pl_at(self, key: str, i: int) -> Val:
        return self.pl.at(key, self.end(i))

    def np(self, i: int) -> Val:
        return self.pl_at(self.np_key, i)

    def base(self, i: int) -> Val:
        """Margin denominator: revenue (a lender: total income), as analytics/derived.py."""
        if self.is_bank and self.pl.has("total_income"):
            return self.pl_at("total_income", i)
        return self.pl_at("revenue", i)

    def recon_zero(self, i: int) -> bool:
        """True when operating profit + other income - finance costs - depreciation + exceptional items reconciles to profit before tax
        with every absent line taken as 0: then an absent line really is zero."""
        op, pbt = self.pl_at("operating_profit", i)[0], self.pl_at("profit_before_tax", i)[0]
        if op is None or pbt is None:
            return False
        parts = [self.pl_at(k, i)[0] for k in ("other_income", "finance_costs", "depreciation", "exceptional_items")]
        oi, fin, dep, exc = (p or 0.0 for p in parts)
        return abs(op + oi - fin - dep + exc - pbt) <= max(RECON_REL * abs(pbt), RECON_ABS)

    def pl_or_zero(self, key: str, i: int) -> Val:
        v = self.pl_at(key, i)
        if v[0] is not None:
            return v
        return (0.0, None) if self.recon_zero(i) else (None, "no_data")

    def eps(self, i: int) -> Val:
        e = self.pl_at("eps", i)
        if e[0] is None:
            return e
        if self.np_key == "net_profit_continuing":
            rep, cont = self.pl_at("net_profit", i)[0], self.pl_at("net_profit_continuing", i)[0]
            if rep and cont is not None:
                return round(e[0] * cont / rep, 2), None   # EPS on continuing profit, same share count (as screener/compute.py)
        return e

    def shares(self, i: int) -> Val:
        s = self.pl_at("diluted_shares_cr", i)
        if s[0]:
            return s
        rep, e = self.pl_at("net_profit", i)[0], self.pl_at("eps", i)[0]
        if rep is not None and e:
            return rep / e, None   # crore shares: profit / EPS (as screener/compute.py)
        return None, "no_data"

    def borrowings(self, end: Optional[date]) -> Val:
        if not self.bs.has("borrowings") and end in self.bs.pos and self.bs.at("total_equity", end)[0] is not None:
            return 0.0, None   # a balance sheet that lists no borrowings in any year: a company with none (screener/compute.py)
        return self.bs.at("borrowings", end)

    def hist(self, mid: str, i: int) -> Val:
        key = HIST_KEYS[mid]
        end = self.end(i)
        if end is not None and end.month != 3:
            return None, "non_march"
        if key not in self.hist_rows:
            if self.is_bank and mid in LENDER_DROP:
                return None, "lender"
            if self.neg_equity_latest and mid in ("roe", "de"):
                return None, "neg_equity"
            return None, "no_data"
        fy = self.fys[i] if i < len(self.fys) else None
        if fy not in self.hist_periods:
            return None, "no_fy"
        j = self.hist_periods.index(fy)
        row = self.hist_rows[key]
        v = _n(row[j]) if j < len(row) else None
        return (v, None) if v is not None else (None, "no_fy")

    def share_guard(self, i: int) -> Optional[str]:
        s1, s0 = self.shares(i)[0], self.shares(i - 1)[0] if i > 0 else None
        if s1 is None or s0 is None or s0 <= 0:
            return None
        ratio = s1 / s0
        if ratio > SHARE_JUMP or ratio < 1 / SHARE_JUMP:
            return "share_change"
        e0, e1 = self.end(i - 1), self.end(i)
        if e0 and e1 and any(e0 < ev <= e1 for ev in self.px.events) and abs(ratio - 1) > SHARE_WITH_ACTION:
            return "share_change"
        return None

    def prev_reason(self, i: int) -> Optional[str]:
        """None when P&L column i - 1 is the financial year just before column i (ends 330-400 days apart), else the reason."""
        e1, e0 = self.end(i), self.end(i - 1) if i > 0 else None
        if e1 is None:
            return "no_data"
        if e0 is None:
            return "no_prev"
        return None if GAP_MIN <= (e1 - e0).days <= GAP_MAX else "gap"

    @staticmethod
    def yoy(cur: Val, prev: Val, prev_reason: Optional[str], guard: Optional[str] = None) -> Val:
        """Growth of a P&L-dated figure: the value's own reason first, then the year gap, then the per-share guard, then the base."""
        if cur[0] is None:
            return None, cur[1]
        if prev_reason is not None:
            return None, prev_reason
        if prev[0] is None:
            return None, prev[1]
        if guard is not None:
            return None, guard
        return _growth(cur, prev)

    def pl_growth(self, key: str, i: int) -> Val:
        return self.pl.growth(key, self.end(i))

    # ------------------------------------------------------------ dividends
    def dps_at(self, i: int) -> Val:
        fy, end = (self.fys[i] if i < len(self.fys) else None), self.end(i)
        if fy is None or end is None:
            return None, "no_data"
        if fy in self.dps:
            if self.today <= end + timedelta(days=DECLARE_DAYS) and not self._final_declared(fy):
                return None, "partial"
            return self.dps[fy], None
        if not self.actions:
            return None, "no_data"
        if self.today <= end + timedelta(days=DECLARE_DAYS):
            return None, "partial"
        dated = [d for d in (_d(a.get("date")) for a in self.actions) if d is not None]
        first = min(dated) if dated else None
        if first is None or first > end:
            return None, "no_data"   # before the first stored corporate action: cannot tell "none" from "not stored"
        return 0.0, None

    def _final_declared(self, fy: str) -> bool:
        return any(a.get("forFY") == fy and a.get("type") == "final_dividend" for a in self.actions)

    # ------------------------------------------------------------ price windows
    def basis_ok(self, fy_label: Optional[str]) -> Optional[bool]:
        """Is the stored daily close series on the provider's adjusted basis in this financial year? Compares the mean of our closes in the
        year with the provider's (split/bonus adjusted) average price for the year. None when it cannot be checked."""
        avg = _n((self.vh.get("average_price") or {}).get(fy_label)) if fy_label else None
        if not avg or fy_label is None or not fy_label[2:].isdigit():
            return None
        y = 2000 + int(fy_label[2:])
        start, stop = date(y - 1, 4, 1), date(y, 3, 31)
        cs = [c for d, c in zip(self.px.dates, self.px.closes) if start <= d <= stop]
        if len(cs) < BASIS_MIN_DAYS:
            return None
        return abs(math.fsum(cs) / len(cs) / avg - 1.0) <= BASIS_TOL

    def no_later_adjustment(self, after: date) -> bool:
        """No split/bonus after `after`, and every later dividend stored with adjusted amount equal to the amount: nothing after this date
        could have re-based earlier prices."""
        if not self.actions:
            return False
        if any(e > after for e in self.px.events):
            return False
        for a in self.actions:
            d = _d(a.get("date"))
            if d and d > after and str(a.get("type", "")).endswith("dividend"):
                am, adj = _n(a.get("amount")), _n(a.get("adjustedAmount"))
                if am is not None and adj is not None and abs(am - adj) > 1e-9:
                    return False
        return True

    def price_basis(self, fy_label: Optional[str], after: date) -> bool:
        b = self.basis_ok(fy_label)
        return b if b is not None else self.no_later_adjustment(after)

    def fy_window(self, i: int) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
        e1, e0 = self.end(i), self.end(i - 1)
        if e1 is None:
            return None, "no_data"
        if e0 is None:
            return None, "no_prev"
        if not GAP_MIN <= (e1 - e0).days <= GAP_MAX:
            return None, "gap"
        i0, why0 = self.px.close_at(e0)
        if i0 is None:
            return None, why0
        i1, why1 = self.px.close_at(e1)
        if i1 is None:
            return None, why1
        if not self.px.clean(i0, i1):
            return None, "jump"
        return (i0, i1), None

    def ret_fy(self, i: int) -> Val:
        w, why = self.fy_window(i)
        if w is None:
            return None, why
        c0, c1 = self.px.closes[w[0]], self.px.closes[w[1]]
        return (c1 / c0 - 1.0) * 100.0, None

    def tsr_fy(self, i: int) -> Val:
        w, why = self.fy_window(i)
        if w is None:
            return None, why
        d0, d1 = self.px.dates[w[0]], self.px.dates[w[1]]
        c0, c1 = self.px.closes[w[0]], self.px.closes[w[1]]
        divs = [a for a in self.actions if str(a.get("type", "")).endswith("dividend") and (lambda d: d is not None and d0 < d <= d1)(_d(a.get("date")))]
        rebased = any(abs((_n(a.get("amount")) or 0.0) - (_n(a.get("adjustedAmount")) or 0.0)) > 1e-9 for a in divs)
        if rebased and not self.basis_ok(self.fys[i]):
            return None, "basis"   # adjusted dividends need adjusted closes: confirmed against the provider's adjusted yearly average
        paid = math.fsum(_n(a.get("adjustedAmount")) or 0.0 for a in divs)
        return ((c1 + paid) / c0 - 1.0) * 100.0, None

    def fy_end_close(self, i: int) -> Tuple[Optional[float], Optional[str]]:
        e1 = self.end(i)
        if e1 is None:
            return None, "no_data"
        i1, why = self.px.close_at(e1)
        if i1 is None:
            return None, why
        if not self.price_basis(self.fys[i], self.px.dates[i1]):
            return None, "basis"
        return self.px.closes[i1], None

    # ------------------------------------------------------------ one financial year
    def year(self, i: int) -> Dict[str, Val]:
        """Every yearly metric for P&L column i."""
        end = self.end(i)
        v: Dict[str, Val] = {}
        rev, op, np_ = self.pl_at("revenue", i), self.pl_at("operating_profit", i), self.np(i)
        cfo = self.cf.at("operating", end)
        fcf = self.cf.at("free_cash_flow", end)
        capex_raw = self.cf.at("capex", end)
        capex = (abs(capex_raw[0]), None) if capex_raw[0] is not None else capex_raw
        eq, ta = self.bs.at("total_equity", end), self.bs.at("total_assets", end)
        ca, cl, tl = self.bs.at("current_assets", end), self.bs.at("current_liabilities", end), self.bs.at("total_liabilities", end)
        cash = self.bs.at("cash", end)
        debt = self.borrowings(end)
        shares = self.shares(i)
        eps = self.eps(i)
        v["revenue"], v["np"], v["ebitda"], v["cfo"], v["fcf"], v["capex"], v["cur_liab"] = rev, np_, op, cfo, fcf, capex, cl
        v["opm"] = _div(op, self.base(i), 100)
        v["npm"] = _div(np_, self.base(i), 100)
        fin = self.pl_or_zero("finance_costs", i)
        pbt = self.pl_at("profit_before_tax", i)
        ebit = (pbt[0] + fin[0], None) if pbt[0] is not None and fin[0] is not None else (None, pbt[1] or fin[1])
        v["ebit_margin"] = _div(ebit, rev, 100)
        for mid in HIST_KEYS:
            v[mid] = self.hist(mid, i)
        for mid, src in (("inv_turnover", "inv_days"), ("recv_turnover", "debtor_days")):
            days = v[src]
            v[mid] = (365.0 / days[0], None) if days[0] is not None and days[0] > 0 else ((None, days[1]) if days[0] is None else (None, "den_zero"))
        v["cash_ratio"] = _div(cash, cl)
        if op[0] is not None and op[0] <= 0:
            v["nd_ebitda"] = (None, "op_le0")
        else:
            nd = (debt[0] - cash[0], None) if debt[0] is not None and cash[0] is not None else (None, debt[1] or cash[1])
            v["nd_ebitda"] = _div(nd, op)
        v["cfo_debt"] = (None, "no_debt") if debt[0] == 0 else _div(cfo, debt, zero="no_debt")
        v["cl_tl"] = _div(cl, tl, 100)
        wc = (ca[0] - cl[0], None) if ca[0] is not None and cl[0] is not None else (None, ca[1] or cl[1])
        v["wc_rev"] = _div(wc, rev, 100)
        v["ca_ta"] = _div(ca, ta, 100)
        np_pos: Val = np_ if np_[0] is None or np_[0] > 0 else (None, "np_le0")
        v["cfo_pat"] = _div(cfo, np_pos, 100)
        p_end, why = self.bs.prev_end(end)
        ta0 = self.bs.at("total_assets", p_end) if p_end else (None, why)
        avg_ta = ((ta[0] + ta0[0]) / 2.0, None) if ta[0] is not None and ta0[0] is not None else (None, ta[1] or ta0[1])
        acc = (np_[0] - cfo[0], None) if np_[0] is not None and cfo[0] is not None else (None, np_[1] or cfo[1])
        v["accruals"] = _div(acc, avg_ta, 100)
        v["oi_np"] = _div(self.pl_or_zero("other_income", i), np_pos, 100)
        v["exc_np"] = _div(self.pl_or_zero("exceptional_items", i), np_pos, 100)
        dps = self.dps_at(i)
        eps_pos: Val = eps if eps[0] is None or eps[0] > 0 else (None, "loss")
        v["payout"] = _div(dps, eps_pos, 100)
        v["div_cover"] = (None, "no_dividend") if dps[0] == 0 else _div(eps_pos, dps, zero="no_dividend")
        v["cfo_ps"] = _div(cfo, shares)
        v["eps"] = eps
        v["bvps"] = _div(eq, shares)
        # growth
        v["g_rev"] = self.pl_growth("revenue", i)
        v["g_np"] = self.pl_growth(self.np_key, i)
        prev_ok = self.prev_reason(i)
        guard = self.share_guard(i) if prev_ok is None else None
        v["g_eps"] = self.yoy(eps, self.eps(i - 1) if i > 0 else (None, "no_prev"), prev_ok, guard)
        v["g_ebitda"] = self.pl_growth("operating_profit", i)
        ebit0: Val = (None, "no_prev")
        if i > 0:
            pbt0, fin0 = self.pl_at("profit_before_tax", i - 1), self.pl_or_zero("finance_costs", i - 1)
            ebit0 = (pbt0[0] + fin0[0], None) if pbt0[0] is not None and fin0[0] is not None else (None, pbt0[1] or fin0[1])
        v["g_ebit"] = self.yoy(ebit, ebit0, prev_ok)
        v["g_pbt"] = self.pl_growth("profit_before_tax", i)
        v["g_tax"] = self.pl_growth("tax", i)
        v["g_dep"] = self.pl_growth("depreciation", i)
        v["g_int"] = self.pl_growth("finance_costs", i)
        v["g_cfo"] = self.cf.growth("operating", end)
        v["g_fcf"] = self.cf.growth("free_cash_flow", end)
        v["g_capex"] = self.cf.growth("capex", end, absolute=True)
        v["g_assets"] = self.bs.growth("total_assets", end)
        v["g_bv"] = self.bs.growth("total_equity", end)
        bv0: Val = _div(self.bs.at("total_equity", self.end(i - 1)), self.shares(i - 1)) if i > 0 else (None, "no_prev")
        v["g_bvps"] = self.yoy(v["bvps"], bv0, prev_ok, guard)
        if p_end is None:
            wc0: Val = (None, why)
        else:
            ca0, cl0 = self.bs.at("current_assets", p_end), self.bs.at("current_liabilities", p_end)
            wc0 = (ca0[0] - cl0[0], None) if ca0[0] is not None and cl0[0] is not None else (None, ca0[1] or cl0[1])
        v["g_wc"] = _growth(wc, wc0)
        v["g_recv"] = self.bs.growth("receivables", end)
        v["g_inv"] = self.bs.growth("inventories", end)
        debt0 = self.borrowings(p_end) if p_end else (None, why)
        v["g_debt"] = _growth(debt, debt0)
        v["g_dps"] = self.yoy(dps, self.dps_at(i - 1) if i > 0 else (None, "no_prev"), prev_ok)
        v["ret_fy"] = self.ret_fy(i)
        v["tsr_fy"] = self.tsr_fy(i)
        # P/E and P/B history: the provider's yearly figure (average price over the year / that year's EPS or book value)
        fy = self.fys[i] if i < len(self.fys) else None
        for mid in ("pe", "pb"):
            if end is not None and end.month != 3:
                v[mid] = (None, "non_march")
            else:
                x = _n((self.vh.get(mid) or {}).get(fy))
                v[mid] = (x, None) if x is not None and x > 0 else (None, "no_fy")
        if self.is_bank:
            for mid in LENDER_DROP:
                if mid in v:
                    v[mid] = (None, "lender")
        if self.neg_equity_latest:
            for mid in ("pb",):
                v[mid] = (None, "neg_equity")
        return v

    # ------------------------------------------------------------ the whole history
    def history(self) -> Dict[str, Any]:
        years = [self.year(i) for i in range(len(self.fys))]
        return {"fys": list(self.fys), "ends": [e.isoformat() if e else None for e in self.ends],
                "values": {m: [y[m][0] for y in years] for m in HIST_IDS},
                "miss": {m: [y[m][1] if y[m][0] is None else None for y in years] for m in HIST_IDS}}

    # ------------------------------------------------------------ windows that are not one financial year
    def vol_mdd(self) -> Tuple[Val, Val]:
        n = self.px.n
        if n < VOL_MIN:
            return (None, "short_history"), (None, "short_history")
        w0 = max(0, n - VOL_SESSIONS)
        if not self.px.clean(w0, n - 1):
            return (None, "jump"), (None, "jump")
        cs = self.px.closes[w0:]
        rets = [math.log(cs[k] / cs[k - 1]) for k in range(1, len(cs))]
        mu = math.fsum(rets) / len(rets)
        var = math.fsum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        peak, worst = cs[0], 0.0
        for c in cs:
            peak = max(peak, c)
            worst = min(worst, c / peak - 1.0)
        return (math.sqrt(var) * math.sqrt(252.0) * 100.0, None), (worst * 100.0, None)

    def ret_between(self, d0: Optional[date], d1: Optional[date]) -> Val:
        if d0 is None or d1 is None:
            return None, "no_data"
        i0, why0 = self.px.close_at(d0)
        if i0 is None:
            return None, why0
        i1, why1 = self.px.close_at(d1)
        if i1 is None:
            return None, why1
        if not self.px.clean(i0, i1):
            return None, "jump"
        return (self.px.closes[i1] / self.px.closes[i0] - 1.0) * 100.0, None

    def signal(self, years: Optional[List[Dict[str, Val]]] = None) -> Dict[str, Any]:
        """Forward variant: the latest financial year whose 12 months after (year end + 75 days) are complete in the stored prices."""
        out: Dict[str, Any] = {k: (None, "not_complete") for k in ("pe_sig", "pb_sig", "g_eps_sig", "g_rev_sig", "fwd12")}
        out["sig_fy"], out["sig_date"] = None, None
        if not self.px.n:
            return {**out, **{k: (None, "short_history") for k in ("pe_sig", "pb_sig", "g_eps_sig", "g_rev_sig", "fwd12")}}
        last = self.px.dates[-1]
        for i in range(len(self.fys) - 1, -1, -1):
            e = self.end(i)
            if e is None:
                continue
            sd = e + timedelta(days=SIGNAL_DAYS)
            fe = _add_months(sd, 12)
            if fe > last:
                continue
            yr = years[i] if years is not None else self.year(i)
            out["sig_fy"], out["sig_date"] = self.fys[i], sd.isoformat()
            out["g_eps_sig"], out["g_rev_sig"] = yr["g_eps"], yr["g_rev"]
            ins, why = self.px.close_at(sd)
            ine, why2 = self.px.close_at(fe)
            if ins is None or ine is None:
                r = why or why2
                out.update(pe_sig=(None, r), pb_sig=(None, r), fwd12=(None, r))
                return out
            if not self.px.clean(ins, ine):
                out["fwd12"] = (None, "jump")
            else:
                out["fwd12"] = ((self.px.closes[ine] / self.px.closes[ins] - 1.0) * 100.0, None)
            cs = self.px.closes[ins]
            nxt = self.fys[i + 1] if i + 1 < len(self.fys) else f"FY{(int(self.fys[i][2:]) + 1) % 100:02d}" if self.fys[i][2:].isdigit() else None
            based = self.price_basis(nxt, self.px.dates[ins])
            eps = yr["eps"]
            out["pe_sig"] = (None, "basis") if not based else ((None, eps[1]) if eps[0] is None else (None, "loss") if eps[0] <= 0 else (cs / eps[0], None))
            bv = yr["bvps"]
            out["pb_sig"] = (None, "basis") if not based else ((None, bv[1]) if bv[0] is None else (None, "neg_equity") if bv[0] <= 0 else (cs / bv[0], None))
            return out
        return out

    def latest(self, screener: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sc = screener or {}
        vals: Dict[str, Val] = {}
        years = [self.year(i) for i in range(len(self.fys))]
        if years:
            last = years[-1]
            for m in FY_IDS + ["ret_fy", "tsr_fy"]:
                vals[m] = last[m]
            i = len(years) - 1
            c, why = self.fy_end_close(i)
            eps, bv = last["eps"], last["bvps"]
            vals["pe_fy"] = (None, why) if c is None else ((None, eps[1]) if eps[0] is None else (None, "loss") if eps[0] <= 0 else (c / eps[0], None))
            vals["pb_fy"] = (None, why) if c is None else ((None, bv[1]) if bv[0] is None else (None, "neg_equity") if bv[0] <= 0 else (c / bv[0], None))
        else:
            for m in FY_IDS + ["ret_fy", "tsr_fy", "pe_fy", "pb_fy"]:
                vals[m] = (None, "no_data")
        vals["vol3y"], vals["mdd3y"] = self.vol_mdd()
        ic = _n(sc.get("own_inst_chg_1y"))
        vals["inst_chg"] = (ic, None) if ic is not None else (None, "no_data")
        vals["ret_inst"] = self.ret_between(_quarter_end(self.own.get("comparedWith")), _quarter_end(self.own.get("asOf")))
        sig = self.signal(years if years else None)
        for k in ("pe_sig", "pb_sig", "g_eps_sig", "g_rev_sig", "fwd12"):
            vals[k] = sig[k]
        # ---- today: the screener's figures, with the reason when one is missing
        for mid, col in TODAY_COL.items():
            x = _n(sc.get(col))
            vals[mid] = (x, None) if x is not None else (None, self._today_reason(mid, sc))
        cfo = vals.get("cfo", (None, "no_data"))
        fcf = vals.get("fcf", (None, "no_data"))
        ev, mcap = _n(sc.get("enterprise_value")), _n(sc.get("market_cap"))
        vals["ev_cfo"] = (None, "no_value") if ev is None else (None, cfo[1]) if cfo[0] is None else (None, "cfo_le0") if cfo[0] <= 0 else (ev / cfo[0], None)
        vals["fcf_yield"] = _div(fcf, (mcap, "no_value"), 100)
        vals["cfo_yield"] = _div(cfo, (mcap, "no_value"), 100)
        if self.is_bank:
            for mid in LENDER_DROP:
                if mid in vals:
                    vals[mid] = (None, "lender")
        # values of the "today" figures stay in their screener columns (no copy); only the reason a value is missing is kept here
        out: Dict[str, Any] = {f"ax_{k}": v for k, (v, _) in vals.items() if v is not None and k not in TODAY_COL}
        out["ax_miss"] = {k: why or "no_value" for k, (v, why) in vals.items() if v is None}
        if self.fys:
            out.update(self.components(len(self.fys) - 1))
        out["ax_fy"] = self.fys[-1] if self.fys else None
        out["ax_sig_fy"], out["ax_sig_date"] = sig["sig_fy"], sig["sig_date"]
        return {k: v for k, v in out.items() if v is not None}

    def components(self, i: int) -> Dict[str, float]:
        """Stored amounts behind the ratios (Rs crore, latest FY), used ONLY to build index aggregates as a ratio of sums
        (index.py): ax_c_<name> for levels, ax_gc_<id> / ax_gp_<id> for this year's and last year's value of each growth metric (stored only
        when both years exist and are 330-400 days apart). Lender-only-meaningless amounts are not stored for lenders."""
        end = self.end(i)
        out: Dict[str, float] = {}
        lev = {"equity": self.bs.at("total_equity", end), "ta": self.bs.at("total_assets", end), "ca": self.bs.at("current_assets", end),
               "cl": self.bs.at("current_liabilities", end), "tl": self.bs.at("total_liabilities", end), "debt": self.borrowings(end),
               "cash": self.bs.at("cash", end), "base": self.base(i), "oi": self.pl_or_zero("other_income", i), "exc": self.pl_or_zero("exceptional_items", i)}
        pbt, fin = self.pl_at("profit_before_tax", i), self.pl_or_zero("finance_costs", i)
        lev["ebit"] = (pbt[0] + fin[0], None) if pbt[0] is not None and fin[0] is not None else (None, "no_data")
        for k, (v, _) in lev.items():
            if v is not None and not (self.is_bank and k in ("ca", "cl", "tl", "debt", "cash", "ebit")):
                out[f"ax_c_{k}"] = v
        pairs: Dict[str, Tuple[Val, Val]] = {}
        for gid, (st, key) in AGG_GROWTH.items():
            stmt = {"pl": self.pl, "bs": self.bs, "cf": self.cf}[st]
            k = self.np_key if key == "@np" else key
            p_end, why = stmt.prev_end(end)
            if p_end is None:
                continue
            if gid == "g_debt":
                pairs[gid] = (self.borrowings(end), self.borrowings(p_end))
            elif gid == "g_wc":
                a1, l1, a0, l0 = (self.bs.at(x, e) for x, e in (("current_assets", end), ("current_liabilities", end), ("current_assets", p_end), ("current_liabilities", p_end)))
                pairs[gid] = ((a1[0] - l1[0], None) if a1[0] is not None and l1[0] is not None else (None, "no_data"),
                              (a0[0] - l0[0], None) if a0[0] is not None and l0[0] is not None else (None, "no_data"))
            elif gid == "g_ebit":
                j = i - 1
                if self.prev_reason(i) is not None:
                    continue
                pbt0, fin0 = self.pl_at("profit_before_tax", j), self.pl_or_zero("finance_costs", j)
                pairs[gid] = (lev["ebit"], (pbt0[0] + fin0[0], None) if pbt0[0] is not None and fin0[0] is not None else (None, "no_data"))
            else:
                c, p = stmt.at(k, end), stmt.at(k, p_end)
                if gid == "g_capex":
                    c = (abs(c[0]), None) if c[0] is not None else c
                    p = (abs(p[0]), None) if p[0] is not None else p
                pairs[gid] = (c, p)
        for gid, (c, p) in pairs.items():
            if c[0] is not None and p[0] is not None and not (self.is_bank and gid in LENDER_DROP):
                out[f"ax_gc_{gid}"], out[f"ax_gp_{gid}"] = c[0], p[0]
        return out

    def _today_reason(self, mid: str, sc: Dict[str, Any]) -> str:
        if self.is_bank and mid in LENDER_DROP:
            return "lender"
        if mid in ("pe", "peg"):
            np_ttm, np_fy = _n(sc.get("ttm_net_profit")), _n(sc.get("net_profit"))
            if (np_ttm is not None and np_ttm <= 0) or (np_ttm is None and np_fy is not None and np_fy <= 0):
                return "loss"
            if mid == "peg" and _n(sc.get("pe")) is not None:
                return "no_growth"
        if mid == "pb" and self._last_equity() is not None and self._last_equity() <= 0:  # type: ignore[operator]
            return "neg_equity"
        return "no_value"


def history(sections: Dict[str, dict], today: Optional[date] = None) -> Dict[str, Any]:
    return Company(sections, today).history()


def latest(sections: Dict[str, dict], screener: Optional[Dict[str, Any]] = None, today: Optional[date] = None) -> Dict[str, Any]:
    return Company(sections, today).latest(screener)
