"""The Mutual Fund Screener's filter registry and the query-string parser.

Every filter the panel can send is declared here once: the numeric fields (the SQL they work on and the histogram edges), the whitelists of the
categorical ones, and the checks. `parse` turns a query string into a list of predicates, each in a named group; `where` joins the predicates of every
group except the ones asked to be left out (that is how the counts beside an option and the histogram under a slider respect all the OTHER filters).

Safety: nothing from the request is ever put into SQL text. Field names, keys and chips are looked up in the whitelists below (an unknown one is a
ScreenError, which the API answers as HTTP 400); every value travels as a bound parameter. Counts are capped (MAX_*), so a request stays small.
No import of finlit.mf here: mf.py imports this module."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


class ScreenError(ValueError):
    """A query string the screener refuses (unknown value, out of range, too many entries). The message is safe to show."""


MAX_LIST = 80          # entries in any one repeated parameter
MAX_RANGES = 40
BIG = 1e9


# ====================================================================================== numeric fields

@dataclass(frozen=True)
class Num:
    key: str
    expr: str                 # SQL over mf_schemes and mf_screen columns; a loss or a share is stored the way the slider shows it
    edges: Tuple[float, ...]  # bin edges of the histogram, and the slider's scale (piecewise linear); values outside are counted in the end bins


def _n(key: str, expr: str, *edges: float) -> Num:
    return Num(key, expr, tuple(float(e) for e in edges))


RET = (-40, -20, -10, 0, 5, 10, 15, 20, 30, 40, 60)
RET3 = (-10, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40)
RET5 = (-5, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40)
EXC = (-20, -10, -5, -2, 0, 2, 5, 10, 20, 30)
RISK = (0, 2, 5, 8, 12, 16, 20, 25, 30, 40, 60)

NUMS: Tuple[Num, ...] = (
    # size and age
    _n("aum", "aum_lakh / 100.0", 0, 50, 100, 250, 500, 1000, 2000, 5000, 10000, 25000, 50000, 100000, 250000),
    _n("age", "x_age", 0, 1, 2, 3, 5, 7, 10, 15, 20, 30),
    _n("aum_share", "x_aum_share", 0, 0.5, 1, 2, 5, 10, 20, 50, 100),
    _n("na_chg", "x_na_chg", -30, -10, -5, -2, 2, 5, 10, 30),
    # returns
    _n("r1d", "CASE WHEN prev_nav > 0 AND nav IS NOT NULL THEN (nav / prev_nav - 1) * 100 END", -3, -1, -0.5, 0, 0.5, 1, 3),
    _n("r1m", "r1m", -10, -5, -2, 0, 2, 5, 10),
    _n("r6m", "r6m", -20, -10, -5, 0, 5, 10, 20, 40),
    _n("r1y", "r1y", *RET),
    _n("r3y", "r3y", *RET3),
    _n("r5y", "r5y", *RET5),
    _n("sip3y", "sip3y", *RET3),
    _n("sip5y", "sip5y", *RET5),
    _n("ex1y", "x_ex1y", *EXC),
    _n("ex3y", "x_ex3y", *EXC),
    _n("ex5y", "x_ex5y", *EXC),
    _n("consist", "x_consist", 0, 20, 35, 45, 55, 65, 80, 100),
    _n("up_m", "x_up_month", -5, 0, 1, 2, 4, 6, 10, 15, 20, 30),
    _n("cy1", "x_cy1", *RET),
    _n("cy2", "x_cy2", *RET),
    _n("cy3", "x_cy3", *RET),
    # cost
    _n("ter", "ter", 0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3.5),
    _n("ter_rel", "x_ter_rel", 0, 0.5, 0.7, 1.0, 1.3, 1.5, 2, 3),
    _n("ter_gap", "x_ter_gap", 0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3),
    _n("fee_share", "x_fee_share", 0, 5, 10, 15, 20, 30, 50, 100),
    _n("exit_pct", "x_exit_pct", 0, 0.25, 0.5, 1, 1.5, 2, 3, 5),
    # risk (month-end NAVs)
    _n("vol1", "x_vol1", *RISK),
    _n("vol3", "x_vol3", *RISK),
    _n("vol_rel", "x_vol_rel", 0, 0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5, 2, 3),
    _n("down_dev", "x_down_dev", 0, 1, 2, 4, 6, 8, 10, 15, 20, 30),
    _n("fall", "-mdd3y_m", 0, 2, 5, 10, 15, 20, 30, 40, 60),
    _n("worst_m", "x_worst_loss", 0, 0.25, 0.5, 1, 2, 4, 6, 10, 20, 40),
    _n("worst_12m", "x_worst12_loss", 0, 0.5, 1, 2, 5, 10, 20, 30, 50),
    _n("neg_share", "x_neg_share", 0, 10, 20, 30, 40, 50, 70, 100),
    _n("below_high", "x_below_high", 0, 10, 25, 50, 75, 100),
    _n("down_cap", "x_down_cap", 0, 50, 70, 90, 100, 110, 130, 200),
    _n("sharpe", "x_sharpe", -2, -1, 0, 0.5, 1, 1.5, 2, 3, 5),
    # portfolio
    _n("eq_pct", "x_eq_pct", 0, 10, 25, 40, 65, 80, 100),
    _n("debt_pct", "x_debt_pct", 0, 10, 25, 50, 75, 100),
    _n("cash_pct", "x_cash_pct", 0, 2, 5, 10, 25, 50, 100),
    _n("other_pct", "x_other_pct", 0, 2, 5, 10, 25, 50, 100),
    _n("n_hold", "x_n_hold", 0, 10, 25, 50, 75, 100, 150, 250, 500),
    _n("top10", "x_top10", 0, 30, 50, 70, 100),
    _n("max_hold", "x_max_hold", 0, 2, 5, 8, 12, 20, 40, 100),
    # the category's market view
    _n("cf_aum_mom", "x_cf_aum_mom", -10, -5, -2, 0, 2, 5, 10),
    _n("cf_aum_yoy", "x_cf_aum_yoy", -20, 0, 10, 20, 40, 80),
    _n("cf_folio_mom", "x_cf_folio_mom", -3, -1, 0, 1, 2, 5),
    _n("cf_share", "x_cf_share", 0, 0.5, 1, 2, 5, 10, 20, 50),
)
NUM_BY_KEY: Dict[str, Num] = {n.key: n for n in NUMS}

# ====================================================================================== whitelists

SUB_KEYS = frozenset("""contra dividend-yield elss flexi-cap focused large-mid-cap large-cap mid-cap multi-cap small-cap sectoral-thematic value equity-other
overnight liquid low-duration ultra-short money-market medium-long-duration medium-duration short-duration long-duration dynamic-bond corporate-bond credit-risk
banking-psu gilt-10y gilt floater fixed-term debt-other conservative-hybrid balanced-hybrid balanced-advantage aggressive-hybrid multi-asset arbitrage
equity-savings hybrid-other retirement childrens life-cycle solution-other gold-etf silver-etf index-debt index-funds etf-debt etf fof-overseas fof-domestic other""".split())
TABS = ("equity", "hybrid", "debt", "solution", "other")
CAP_CHIPS: Dict[str, Tuple[str, ...]] = {"large": ("large-cap",), "largemid": ("large-mid-cap",), "mid": ("mid-cap",), "small": ("small-cap",), "multiflexi": ("multi-cap", "flexi-cap")}
# SEBI's maturity band of the CATEGORY (not the fund's measured duration, which is not in our data)
MAT_BANDS: Dict[str, Tuple[str, ...]] = {"d1": ("overnight",), "d91": ("liquid",), "m3_6": ("ultra-short",), "m6_12": ("low-duration", "money-market"), "y1_3": ("short-duration",),
                                         "y3_4": ("medium-duration",), "y4_7": ("medium-long-duration",), "y7p": ("long-duration",)}
PASSIVE_KEYS = ("index-funds", "index-debt", "etf", "etf-debt", "gold-etf", "silver-etf")
STRUCTS = {"open": "lower(scheme_type) LIKE 'open%'", "close": "lower(scheme_type) LIKE 'close%'", "interval": "lower(scheme_type) LIKE 'interval%'"}
HOUSE = {"h1": "x_house_aum_cr < 1000", "h2": "x_house_aum_cr >= 1000 AND x_house_aum_cr < 25000", "h3": "x_house_aum_cr >= 25000 AND x_house_aum_cr < 100000",
         "h4": "x_house_aum_cr >= 100000"}
PLANS = ("Direct", "Regular", "Unspecified")
OPTIONS = ("Growth", "IDCW", "Other")
EXITS = {"none": "x_exit_state = 'nil'", "d7": "x_exit_state = 'read' AND x_exit_days <= 7", "d30": "x_exit_state = 'read' AND x_exit_days > 7 AND x_exit_days <= 30",
         "y1": "x_exit_state = 'read' AND x_exit_days > 30 AND x_exit_days <= 365", "y1p": "x_exit_state = 'read' AND x_exit_days > 365", "unread": "x_exit_state = 'unread'"}
AUMRANK = {"top5": "x_aum_rk <= 5", "top10": "x_aum_rk <= 10", "top25": "x_aum_rn >= 4 AND x_aum_rk * 4 <= x_aum_rn", "bottom25": "x_aum_rn >= 4 AND x_aum_rk * 4 > x_aum_rn * 3"}
RK_PERIODS = {"1y": ("x_rk1", "x_rn1"), "3y": ("x_rk3", "x_rn3"), "5y": ("x_rk5", "x_rn5")}
RK_BANDS = {"top10": "{k} <= 10", "q1": "{k} * 4 <= {n}", "q2": "{k} * 4 > {n} AND {k} * 2 <= {n}", "q3": "{k} * 2 > {n} AND {k} * 4 <= {n} * 3", "q4": "{k} * 4 > {n} * 3"}
CHECK_BITS = {"ret": 1, "ter": 2, "fall": 4, "size": 8, "age": 16}
TICKS = {
    "noneg36": "x_neg_share = 0",
    "fallless": "(chk_mask & 4) = 4 AND (chk_bits & 4) = 4",
    "worstless": "x_worst_less",
    "fall10": "mdd3y_m > -10",
    "has_ter": "ter IS NOT NULL", "has_aum": "aum_lakh IS NOT NULL", "has_launch": "x_launch IS NOT NULL",
    "has_exit": "x_exit_state IN ('nil', 'read')", "has_port": "x_port_asof IS NOT NULL",
    "has_hist3": "r3y IS NOT NULL", "has_hist5": "r5y IS NOT NULL",
    "hot": "code IN (SELECT code FROM mf_hot)",
}
# ticks the spec lists that need data we do not hold; they are refused (the panel shows them as "needs a data source", never as a working control)
TICKS_NOT_BUILT = ("has_riskometer", "has_benchmark", "has_managers", "conf80")
SORT_EXTRA = {
    "fall": "(-mdd3y_m)", "age": "x_age", "launch": "x_launch", "ex3y": "x_ex3y", "rank3y": "(x_rk3::float8 / NULLIF(x_rn3, 0))", "rank1y": "(x_rk1::float8 / NULLIF(x_rn1, 0))",
    "rank5y": "(x_rk5::float8 / NULLIF(x_rn5, 0))", "vol": "x_vol3", "sharpe": "x_sharpe", "r1m": "r1m", "r6m": "r6m", "gap": "x_ter_gap", "consist": "x_consist",
    "aumrank": "(x_aum_rk::float8 / NULLIF(x_aum_rn, 0))", "worst": "x_worst_loss", "negshare": "x_neg_share",
    "cy1": "x_cy1", "downdev": "x_down_dev",
}
TAG_RE = re.compile(r"^[a-z0-9_]{1,24}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
SECTOR_RE = re.compile(r"^[\w &,.()/\-]{1,60}$")


# ====================================================================================== predicates

Arg = Callable[[Any], str]


@dataclass(frozen=True)
class Pred:
    group: str
    sql: Callable[[Arg], str]


@dataclass
class Ctx:
    """What the parser needs from the database, worked out by the caller once per data version."""
    by_key: Dict[str, List[str]] = field(default_factory=dict)    # sub-category key -> AMFI category names
    by_tab: Dict[str, List[str]] = field(default_factory=dict)    # tab -> AMFI category names
    search: Optional[List[int]] = None                            # scheme codes found by the text search (None: no search, or nothing matched by name)
    opened: Sequence[int] = ()                                    # the site's most-opened scheme codes


@dataclass
class Screen:
    preds: List[Pred]
    family: bool
    key: list                      # the request normalised, for the cache key
    subs: List[str] = field(default_factory=list)
    ranges: Dict[str, Tuple[Optional[float], Optional[float]]] = field(default_factory=dict)


def where(preds: Sequence[Pred], exclude: Sequence[str] = ()) -> Tuple[str, List[Any]]:
    """' WHERE a AND b' (or '') and the bound values, leaving out every predicate whose group is in `exclude`."""
    args: List[Any] = []

    def arg(v: Any) -> str:
        args.append(v)
        return f"${len(args)}"
    parts = [p.sql(arg) for p in preds if p.group not in exclude]
    return (" WHERE " + " AND ".join(parts)) if parts else "", args


def source(preds: Sequence[Pred], family: bool, exclude: Sequence[str] = ()) -> Tuple[str, List[Any]]:
    """The FROM clause (with its WHERE) the list and the counts read. One row per scheme, or, with `family`, one row per fund family: the Direct Growth
    plan when it passes the filters, else the next best plan that does."""
    w, args = where(preds, exclude)
    base = f"mf_schemes LEFT JOIN mf_screen ON x_code = code{w or ' WHERE true'}"   # always a WHERE, so callers can append AND ...
    if not family:
        return base, args
    return (f"(SELECT mf_schemes.*, mf_screen.*, row_number() OVER (PARTITION BY family ORDER BY (plan = 'Direct') DESC, (option_class = 'Growth') DESC, code) AS fam_rn "  # nosec B608 - table text and WHERE come from fixed fragments; every value is a bound parameter
            f"FROM {base}) mf_schemes WHERE fam_rn = 1"), args


# ====================================================================================== parsing

def _values(params: Any, name: str, allowed: Optional[Sequence[str]] = None, limit: int = MAX_LIST, maxlen: int = 160) -> List[str]:
    out: List[str] = []
    for raw in params.getlist(name):
        parts = [raw] if name in ("amcs",) else raw.split(",")   # a fund house name may hold a comma-free "&" but never needs splitting
        for part in parts:
            v = part.strip()
            if not v:
                continue
            if len(v) > maxlen:
                raise ScreenError(f"A value of {name} is too long.")
            if allowed is not None and v not in allowed:
                raise ScreenError(f"Unknown value for {name}: {v[:40]!r}.")
            if v not in out:
                out.append(v)
    if len(out) > limit:
        raise ScreenError(f"At most {limit} values for {name}.")
    return out


def _num(s: str, what: str) -> Optional[float]:
    s = s.strip()
    if s == "":
        return None
    try:
        v = float(s)
    except ValueError:
        raise ScreenError(f"{what} is not a number.") from None
    if not math.isfinite(v) or abs(v) > BIG:
        raise ScreenError(f"{what} is out of range.")
    return v


def _day(s: str, what: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ScreenError(f"{what} must be a date as YYYY-MM-DD.") from None


def parse(params: Any, ctx: Ctx) -> Screen:
    """Query string -> Screen. `params` is a Starlette QueryParams (or anything with get and getlist). Legacy parameters (category, categories, group, amc, plan,
    option, stopped, min1y ...) are understood here too, so /api/mf?... of before still answers the same."""
    preds: List[Pred] = []
    key: list = []
    one = lambda n, d="": (params.get(n) or d)   # noqa: E731

    def add(group: str, sql: Callable[[Arg], str]) -> None:
        preds.append(Pred(group, sql))

    # ---- status: still publishing (the default), stopped, or both. Legacy `stopped=true` meant both.
    status = one("status")
    if status and status not in ("active", "stopped", "both"):
        raise ScreenError("status is active, stopped or both.")
    legacy_stopped = one("stopped").lower() in ("1", "true", "yes", "on")
    status = status or ("both" if legacy_stopped else "active")
    key.append(["status", status])
    if status == "active":
        add("status", lambda a: "active")
    elif status == "stopped":
        add("status", lambda a: "NOT active")

    # ---- search codes (resolved by the caller)
    if ctx.search is not None:
        codes = list(ctx.search)
        add("q", lambda a: f"code = ANY({a(codes)}::int[])")

    # ---- plan and option: new lists, else the legacy single values
    plans = _values(params, "plans", PLANS)
    plan = one("plan")
    if not plans and plan:
        if plan not in PLANS:
            raise ScreenError("Unknown plan.")
        plans = [plan]
    key.append(["plans", sorted(plans)])
    if plans and len(plans) < len(PLANS):
        add("plans", lambda a: f"plan = ANY({a(sorted(plans))}::text[])")
    options = _values(params, "options", OPTIONS)
    option = one("option")
    if not options:
        if option and option not in OPTIONS + ("All",):
            raise ScreenError("Unknown option.")
        options = [] if option == "All" else [option or "Growth"]
    key.append(["options", sorted(options)])
    if options and len(options) < len(OPTIONS):
        add("options", lambda a: f"option_class = ANY({a(sorted(options))}::text[])")

    # ---- category: tab, sub-category keys, legacy exact names, cap chips, style, maturity band
    group = one("group")
    if group:
        if group not in TABS:
            raise ScreenError("Unknown category group: use equity, hybrid, debt, solution or other.")
        names = list(ctx.by_tab.get(group, []))
        add("type", lambda a: f"category = ANY({a(names)}::text[])")
    key.append(["group", group])
    subs = _values(params, "subs", SUB_KEYS, limit=60)
    legacy_cats = sorted({c.strip() for c in params.getlist("categories") if c.strip()} | ({one("category")} if one("category") else set()))
    if len(legacy_cats) > 80 or any(len(c) > 160 for c in legacy_cats):
        raise ScreenError("At most 80 categories of up to 160 characters each.")
    if subs:
        names = sorted({n for k in subs for n in ctx.by_key.get(k, [])})
        add("subs", lambda a: f"category = ANY({a(names)}::text[])")
    if legacy_cats:
        add("subs", lambda a: f"category = ANY({a(legacy_cats)}::text[])")
    key.append(["subs", sorted(subs), legacy_cats])
    caps = _values(params, "cap", tuple(CAP_CHIPS))
    if caps:
        names = sorted({n for c in caps for k in CAP_CHIPS[c] for n in ctx.by_key.get(k, [])})
        add("cap", lambda a: f"category = ANY({a(names)}::text[])")
    key.append(["cap", sorted(caps)])
    styles = _values(params, "style", ("active", "passive"))
    if len(styles) == 1:
        passive = sorted({n for k in PASSIVE_KEYS for n in ctx.by_key.get(k, [])})
        add("style", (lambda a: f"category = ANY({a(passive)}::text[])") if styles[0] == "passive" else (lambda a: f"NOT (category = ANY({a(passive)}::text[]))"))
    key.append(["style", sorted(styles)])
    mats = _values(params, "mat", tuple(MAT_BANDS))
    if mats:
        names = sorted({n for m in mats for k in MAT_BANDS[m] for n in ctx.by_key.get(k, [])})
        add("mat", lambda a: f"category = ANY({a(names)}::text[])")
    key.append(["mat", sorted(mats)])
    structs = _values(params, "struct", tuple(STRUCTS))
    if structs:
        add("struct", lambda a: "(" + " OR ".join(STRUCTS[s] for s in structs) + ")")
    key.append(["struct", sorted(structs)])

    # ---- fund house
    amcs = _values(params, "amcs", None, limit=60, maxlen=120)
    if one("amc"):
        if len(one("amc")) > 120:
            raise ScreenError("amc is too long.")
        amcs = amcs + [one("amc")] if one("amc") not in amcs else amcs
    if amcs:
        add("amcs", lambda a: f"amc = ANY({a(sorted(amcs))}::text[])")
    key.append(["amcs", sorted(amcs)])
    houses = _values(params, "house", tuple(HOUSE))
    if houses:
        add("house", lambda a: "(" + " OR ".join(HOUSE[h] for h in houses) + ")")
    key.append(["house", sorted(houses)])

    # ---- instrument, freshness, family view
    insts = _values(params, "inst", ("fund", "etf"))
    if len(insts) == 1:
        add("inst", (lambda a: "COALESCE(x_is_etf, false)") if insts[0] == "etf" else (lambda a: "NOT COALESCE(x_is_etf, false)"))
    key.append(["inst", sorted(insts)])
    fresh = one("fresh")
    if fresh:
        if fresh not in ("today", "week"):
            raise ScreenError("fresh is today or week.")
        days = 0 if fresh == "today" else 7
        add("fresh", lambda a: f"nav_date >= (SELECT max(nav_date) FROM mf_schemes WHERE active) - {days}")  # nosec B608 - days is the integer 0 or 7 chosen from a two-value whitelist
    key.append(["fresh", fresh])
    family = one("family").lower() in ("1", "true", "yes", "on")
    key.append(["family", family])

    # ---- fund size basis and rank by size
    bases = _values(params, "aumbasis", ("q", "m"))
    if len(bases) == 1:
        add("aumbasis", lambda a: f"aum_kind = {a(bases[0])}")
    key.append(["aumbasis", sorted(bases)])
    aumrank = _values(params, "aumrank", tuple(AUMRANK))
    if aumrank:
        add("aumrank", lambda a: "(" + " OR ".join(AUMRANK[r] for r in aumrank) + ")")
    key.append(["aumrank", sorted(aumrank)])
    lf, lt = _day(one("launch_from"), "launch_from"), _day(one("launch_to"), "launch_to")
    if lf and lt and lf > lt:
        raise ScreenError("launch_from is after launch_to.")
    if lf:
        add("launch", lambda a: f"x_launch >= {a(lf)}")
    if lt:
        add("launch", lambda a: f"x_launch <= {a(lt)}")
    key.append(["launch", str(lf or ""), str(lt or "")])

    # ---- numeric ranges: rng=field:lo:hi, nd=field (keep funds with no figure)
    ranges: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    raw_rng = params.getlist("rng")
    if len(raw_rng) > MAX_RANGES:
        raise ScreenError(f"At most {MAX_RANGES} ranges.")
    for raw in raw_rng:
        bits = raw.split(":")
        if len(bits) != 3:
            raise ScreenError("rng is field:min:max.")
        f = bits[0].strip()
        if f not in NUM_BY_KEY:
            raise ScreenError(f"Unknown field for rng: {f[:40]!r}.")
        if f in ranges:
            raise ScreenError(f"rng for {f} given twice.")
        lo, hi = _num(bits[1], f"min of {f}"), _num(bits[2], f"max of {f}")
        if lo is None and hi is None:
            continue
        if lo is not None and hi is not None and lo > hi:
            raise ScreenError(f"min of {f} is above its max.")
        ranges[f] = (lo, hi)
    for leg, field_ in (("1y", "r1y"), ("5y", "r5y")):   # legacy min1y / max1y / min5y / max5y
        lo, hi = _num(one("min" + leg), "min" + leg), _num(one("max" + leg), "max" + leg)
        if (lo is not None or hi is not None) and field_ not in ranges:
            ranges[field_] = (lo, hi)
    nodata = _values(params, "nd", tuple(NUM_BY_KEY))
    for f, (lo, hi) in sorted(ranges.items()):
        e = NUM_BY_KEY[f].expr

        def mk(e=e, lo=lo, hi=hi, nd=f in nodata):
            def sql(a: Arg) -> str:
                c = [f"({e}) >= {a(lo)}"] if lo is not None else []
                if hi is not None:
                    c.append(f"({e}) <= {a(hi)}")
                s = " AND ".join(c)
                return f"(({s}) OR ({e}) IS NULL)" if nd else f"({s})"
            return sql
        add("rng:" + f, mk())
    key.append(["rng", sorted((f, lo, hi) for f, (lo, hi) in ranges.items()), sorted(f for f in nodata if f in ranges)])

    # ---- rank inside the category, the checklist, exit load
    rks = _values(params, "rk", None, limit=15)
    by_period: Dict[str, List[str]] = {}
    for r in rks:
        p, _, b = r.partition(":")
        if p not in RK_PERIODS or b not in RK_BANDS:
            raise ScreenError(f"Unknown rank filter: {r[:20]!r}.")
        by_period.setdefault(p, []).append(b)
    for p, bands in by_period.items():
        k, n = RK_PERIODS[p]
        add("rk:" + p, lambda a, k=k, n=n, bands=bands: "(" + " OR ".join("(" + RK_BANDS[b].format(k=k, n=n) + ")" for b in bands) + ")")
    key.append(["rk", sorted(rks)])
    chk = one("chk")
    if chk:
        if not chk.isdigit() or not 1 <= int(chk) <= 5:
            raise ScreenError("chk is a number from 1 to 5.")
        add("chk", lambda a: f"chk_pass >= {a(int(chk))}")
    key.append(["chk", chk])
    chk_each = _values(params, "chk_each", tuple(CHECK_BITS))
    for c in chk_each:
        bit = CHECK_BITS[c]
        add("chk_each", lambda a, bit=bit: f"(chk_mask & {bit}) = {bit} AND (chk_bits & {bit}) = {bit}")
    key.append(["chk_each", sorted(chk_each)])
    exits = _values(params, "exit", tuple(EXITS))
    if exits:
        add("exit", lambda a: "(" + " OR ".join(f"({EXITS[x]})" for x in exits) + ")")
    key.append(["exit", sorted(exits)])

    # ---- ticks (all must hold)
    ticks = _values(params, "tick", None, limit=20)
    for t in ticks:
        if t in TICKS_NOT_BUILT:
            raise ScreenError(f"The tick {t} needs a data source we do not hold yet.")
        if t not in TICKS and t != "opened":
            raise ScreenError(f"Unknown tick: {t[:30]!r}.")
    for t in ticks:
        if t == "opened":
            codes = list(ctx.opened)
            add("tick", lambda a, codes=codes: f"code = ANY({a(codes)}::int[])")
        else:
            add("tick", lambda a, t=t: f"({TICKS[t]})")
    key.append(["tick", sorted(ticks)])

    # ---- tags, portfolio, category view
    tags = _values(params, "tags", None, limit=40, maxlen=24)
    if any(not TAG_RE.match(t) for t in tags):
        raise ScreenError("Unknown tag.")
    if tags:
        add("tags", lambda a: f"x_tags && {a(sorted(tags))}::text[]")
    key.append(["tags", sorted(tags)])
    sector = one("sector").strip()
    smin = _num(one("sector_min"), "sector_min")
    if sector:
        if not SECTOR_RE.match(sector):
            raise ScreenError("Unknown sector.")
        if smin is not None and not 0 <= smin <= 100:
            raise ScreenError("sector_min is 0 to 100.")
        add("sector", lambda a: f"(x_sectors ->> {a(sector)})::float8 >= {a(smin or 0.0001)}")
    key.append(["sector", sector, smin])
    holds = one("holds").strip().upper()
    if holds:
        if ISIN_RE.match(holds):
            add("holds", lambda a: f"family IN (SELECT fkey FROM mf_screen_hold WHERE isin = {a(holds)})")  # nosec B608 - a() returns a bound-parameter placeholder; the sector value is never put in the text
        elif SYMBOL_RE.match(holds):
            add("holds", lambda a: f"family IN (SELECT h.fkey FROM mf_screen_hold h JOIN disclosure_isin i ON i.isin = h.isin WHERE i.symbol = {a(holds)})")  # nosec B608 - a() returns a bound-parameter placeholder; the symbol is never put in the text
        else:
            raise ScreenError("holds is an NSE symbol or an ISIN.")
    key.append(["holds", holds])
    pfd = _values(params, "pfdate", ("latest", "prev", "older"))
    if pfd:
        latest = "(SELECT max(x_port_asof) FROM mf_screen)"
        conds = {"latest": f"x_port_asof >= {latest} - 5", "prev": f"(x_port_asof < {latest} - 5 AND x_port_asof >= {latest} - 40)", "older": f"x_port_asof < {latest} - 40"}
        add("pfdate", lambda a: "(" + " OR ".join(conds[p] for p in pfd) + ")")
    key.append(["pfdate", sorted(pfd)])
    cflow = _values(params, "cflow", ("pos", "neg"))
    if len(cflow) == 1:
        add("cflow", (lambda a: "x_cf_flow > 0") if cflow[0] == "pos" else (lambda a: "x_cf_flow < 0"))
    key.append(["cflow", sorted(cflow)])
    cstreak = _values(params, "cstreak", ("up", "down"))
    if cstreak:
        add("cstreak", lambda a: "(" + " OR ".join("x_cf_streak = " + ("3" if s == "up" else "-3") for s in cstreak) + ")")
    key.append(["cstreak", sorted(cstreak)])
    csize = _values(params, "csize", ("lt1", "1to5", "gt5"))
    if csize:
        cs = {"lt1": "x_cf_share < 1", "1to5": "(x_cf_share >= 1 AND x_cf_share <= 5)", "gt5": "x_cf_share > 5"}
        add("csize", lambda a: "(" + " OR ".join(cs[c] for c in csize) + ")")
    key.append(["csize", sorted(csize)])
    return Screen(preds=preds, family=family, key=key, subs=subs, ranges=ranges)


# ====================================================================================== sub-category maps

def categories_by_key(names: Sequence[str], classify: Callable[[str], Tuple[str, str, str]]) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """(sub-category key -> category names, tab -> category names) from the distinct category texts in mf_schemes."""
    by_key: Dict[str, List[str]] = {}
    by_tab: Dict[str, List[str]] = {}
    for n in names:
        tab, key, _label = classify(n)
        by_key.setdefault(key, []).append(n)
        by_tab.setdefault(tab, []).append(n)
    return by_key, by_tab


def hist_thresholds(n: Num) -> List[float]:
    """The inner edges handed to width_bucket: bins 0 .. len(edges)-2, values beyond either end land in the end bins."""
    return list(n.edges[1:-1])
