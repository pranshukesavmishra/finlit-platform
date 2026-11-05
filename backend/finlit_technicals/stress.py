"""Stress Lab: how a macro shock (crude, the rupee, inflation, interest rates, demand, risk appetite) moves a
company's revenue, EBITDA, EPS, interest cover and fair value over the next 12 months.

    from finlit_technicals import stress as S
    co = S.company_from_pack(json.load(open("packs/ASIANPAINT.json")))      # TTM base from FinLit's own data
    r = S.run(co, S.PRESETS["2022"])                                       # -> dict, ready for json.dumps
    S.compare(co, other, S.PRESETS["rates"])                                # two companies, one shock
    today = S.today_scenario(macro, brent=[...], base_end="2026-09-30")    # shock = today vs the TTM window
    S.breaking_points(co)                                                   # crude rise / demand fall that halves EPS

Every formula is in the Stress Lab spec, section 4. Shocks are measured against the conditions in which the
company earned its last four quarters of profit (the TTM base): a shock of zero reproduces the base exactly.
Labels describe the result ("Holds up well", "Takes a clear hit", "Hit hard", "Debt cover at risk"); there is no
buy / sell wording anywhere. Pure Python, no dependencies.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MODEL_VERSION = "stress-1.0"
DATA = Path(__file__).parent / "data"
DISCLAIMER = ("Illustrative stress test built from reported financials and the stated assumptions. "
              "It is not a forecast and not investment advice.")
TAX_DEFAULT = 0.2517          # 22% + 10% surcharge + 4% cess, the rate most large companies pay
RF_DEFAULT = 7.0              # % risk-free rate for the value step (no 10-year G-sec series on FinLit yet)
ERP_DEFAULT = 6.0             # % equity risk premium
LONG_RATE_SHARE = 0.5         # long rates move about half as much as the policy rate
COVER_FLOOR = 1.5             # interest cover below this = "Debt cover at risk"


# --------------------------------------------------------------------------------------------- small helpers
def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None or not math.isfinite(x) else round(x, nd)


def _norm(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _mean(xs: Sequence[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# --------------------------------------------------------------------------------------------- exposures
@dataclass
class Exposure:
    """How a business is exposed to each shock. Field meanings: data/industry_exposure.json, "fields"."""
    crude_rm: float = 0.10
    crude_beta: float = 0.4
    import_rm: float = 0.10
    metal_rm: float = 0.0
    agri_rm: float = 0.0
    energy_opex: float = 0.15
    energy_beta: float = 0.3
    var_opex: float = 0.5
    export_rev: float = 0.05
    crude_rev: float = 0.0
    crude_rev_beta: float = 1.0
    demand_beta: float = 1.0
    pass_through: float = 0.6
    floating_debt: float = 0.6
    excluded: bool = False
    notes: List[str] = field(default_factory=list)
    source: List[str] = field(default_factory=list)

    def check(self) -> "Exposure":
        rm = self.crude_rm + self.import_rm + self.metal_rm + self.agri_rm
        if rm > 1.0 + 1e-9:
            raise ValueError(f"raw-material shares add up to {rm:.2f}, more than 1")
        if self.export_rev + self.crude_rev > 1.0 + 1e-9:
            raise ValueError("export_rev + crude_rev is more than 1")
        return self

    @property
    def domestic_rm(self) -> float:
        return max(0.0, 1.0 - self.crude_rm - self.import_rm - self.metal_rm - self.agri_rm)

    @property
    def domestic_rev(self) -> float:
        """Share of revenue priced at home in rupees, where a cost rise can be passed on."""
        return max(0.0, 1.0 - self.export_rev - self.crude_rev)


_EXPOSURE_KEYS = {f.name for f in fields(Exposure)} - {"notes", "source"}
_LEVEL_NAMES = {"sectors": "sector", "industries": "industry", "basic_industries": "basic industry",
                "companies": "company"}


class ExposureTable:
    """data/industry_exposure.json with the lookup order defaults < sector < industry < basic industry < company."""

    def __init__(self, table: Optional[dict] = None, path: Optional[Path] = None):
        if table is None:
            table = json.loads(Path(path or DATA / "industry_exposure.json").read_text(encoding="utf-8"))
        self.table = table
        self._levels = {lvl: {_norm(k): (k, v) for k, v in table.get(lvl, {}).items()}
                        for lvl in ("sectors", "industries", "basic_industries", "companies")}

    def lookup(self, *, symbol: str = "", basic: str = "", industry: str = "", sector: str = "",
               override: Optional[dict] = None) -> Exposure:
        e = Exposure(**{k: v for k, v in self.table.get("defaults", {}).items() if k in _EXPOSURE_KEYS})
        e.source = ["defaults"]
        for lvl, name in (("sectors", sector), ("industries", industry), ("basic_industries", basic),
                          ("companies", symbol)):
            hit = self._levels[lvl].get(_norm(name)) if name else None
            if hit:
                key, vals = hit
                for k, v in vals.items():
                    if k in _EXPOSURE_KEYS:
                        setattr(e, k, v)
                if vals.get("note"):
                    e.notes.append(vals["note"])
                e.source.append(f"{_LEVEL_NAMES[lvl]}: {key}")
        for k, v in (override or {}).items():
            if k in _EXPOSURE_KEYS:
                setattr(e, k, v)
        if override:
            e.source.append("override")
        return e.check()

    def unmatched(self, names: Iterable[str], level: str = "basic_industries") -> List[str]:
        """Names (e.g. every profile.sector on the site) with no row at this level: fill these in first."""
        return sorted({n for n in names if n and _norm(n) not in self._levels[level]})


_TABLE: Dict[str, ExposureTable] = {}


def exposures() -> ExposureTable:
    if "t" not in _TABLE:
        _TABLE["t"] = ExposureTable()
    return _TABLE["t"]


def nse_sector_of(industry: str) -> str:
    """NSE sector (22) of an NSE industry (58), from data/nse_industries.json."""
    if "map" not in _TABLE:
        st = json.loads((DATA / "nse_industries.json").read_text(encoding="utf-8")).get("stocks", {})
        _TABLE["map"] = {_norm(v[0]): v[1] for v in st.values() if isinstance(v, list) and len(v) >= 2}
    return _TABLE["map"].get(_norm(industry), "")


# --------------------------------------------------------------------------------------------- company base
@dataclass
class Company:
    """The base the shocks act on: trailing four quarters (TTM), Rs crore, cost split from the income statement."""
    symbol: str
    name: str
    revenue: float
    rm: float                   # raw materials: materials consumed + traded goods bought + change in inventories
    emp: float                  # employee benefit expense
    opex: float                 # other expenses
    other_income: float
    dep: float
    interest: float
    tax_rate: float
    shares: float               # crore
    debt: float = 0.0
    cash: float = 0.0           # cash + investments
    price: Optional[float] = None
    beta: float = 1.0
    growth: float = 6.0         # % long-run nominal earnings growth for the value step
    exposure: Exposure = field(default_factory=Exposure)
    base_label: str = "TTM"
    base_end: Optional[str] = None
    reported_eps: Optional[float] = None
    calibration: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def ebitda(self) -> float:
        return self.revenue - self.rm - self.emp - self.opex

    @property
    def pbt(self) -> float:
        return self.ebitda + self.other_income - self.dep - self.interest

    @property
    def eps(self) -> float:
        return self.pbt * (1 - self.tax_rate) / self.shares if self.shares else float("nan")


def statement_rows(premium: dict) -> dict:
    """premium/fundamentals response (or its incomeStatement) -> {"periods": [...newest first], "rows": {category: [...]}}."""
    inc = premium.get("incomeStatement", premium)
    items = inc.get("income_statement", inc if isinstance(inc, list) else [])
    if not items:
        raise ValueError("no income_statement in this response")
    periods = [h["period"] for h in items[0]["history"]]
    rows = {}
    for it in items:
        by = {h["period"]: _f(h.get("value")) for h in it.get("history", [])}
        rows[it.get("category") or it.get("label")] = [by.get(p) for p in periods]
    return {"periods": periods, "rows": rows}


def pack_from_site(stock: dict, financials: dict, premium_yearly: dict, premium_quarterly: dict) -> dict:
    """Assemble the input 'pack' from four FinLit API responses: /api/stocks/SYM, /api/stocks/SYM/financials,
    /api/premium/fundamentals?...&period=yearly and ...&period=quarterly (consolidated)."""
    bs = financials.get("yearly", {}).get("bs", {})
    q = financials.get("quarterly", {}).get("pl", {})
    shares = (q.get("rows", {}).get("diluted_shares_cr") or [None])[-1]
    return {
        "symbol": (stock.get("profile") or {}).get("symbol") or financials.get("meta", {}).get("symbol"),
        "profile": stock.get("profile", {}), "quote": stock.get("quote", {}), "dataQuality": stock.get("dataQuality", {}),
        "yearly": statement_rows(premium_yearly), "quarterly": statement_rows(premium_quarterly),
        "bs": {"periods": bs.get("periods", []), **{k: bs.get("rows", {}).get(k) for k in
                                                     ("borrowings", "cash", "investments", "total_equity")}},
        "shares_cr": shares,
    }


_ALIASES = {
    "revenue": ("revenue",), "operating_profit": ("operating_profit", "ebitda"),
    "other_income": ("other_income",), "interest": ("interest", "finance_costs"), "depreciation": ("depreciation",),
    "exceptional": ("exceptional_items",), "pbt": ("profit_before_tax",), "tax": ("tax_expense", "tax"),
    "eps": ("eps",), "cogs": ("cost_of_goods_sold",), "materials": ("costOfMaterialsConsumed",),
    "traded": ("purchasesOfStockInTrade",), "inv_change": ("changesInInventories",),
    "emp": ("employee_benefit_expense",), "opex": ("otherExpenses",),
}


def _row(tbl: dict, key: str) -> List[Optional[float]]:
    rows = {_norm(k): v for k, v in tbl.get("rows", {}).items()}
    for a in _ALIASES[key]:
        if _norm(a) in rows:
            return [_f(x) for x in rows[_norm(a)]]
    return [None] * len(tbl.get("periods", []))


def _sum(xs: Sequence[Optional[float]]) -> Optional[float]:
    return None if any(x is None for x in xs) else float(sum(xs))


def _quarter_end(label: str) -> Optional[str]:
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", label or "")
    if not m:
        return None
    mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(1).lower()) + 1
    days = {2: 28, 4: 30, 6: 30, 9: 30, 11: 30}.get(mon, 31)
    return f"{m.group(2)}-{mon:02d}-{days:02d}"


def _cost_split(tbl: dict, idx: Sequence[int]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    cogs = _sum([_row(tbl, "cogs")[i] for i in idx])
    if cogs is None:
        parts = [_row(tbl, k) for k in ("materials", "traded", "inv_change")]
        cogs = _sum([sum(p[i] or 0.0 for p in parts) if any(p[i] is not None for p in parts) else None for i in idx])
    return cogs, _sum([_row(tbl, "emp")[i] for i in idx]), _sum([_row(tbl, "opex")[i] for i in idx])


def company_from_pack(pack: dict, *, table: Optional[ExposureTable] = None, override: Optional[dict] = None,
                      base: str = "ttm", beta: Optional[float] = None, growth: Optional[float] = None,
                      macro_fy: Optional[dict] = None, calibrate_history: bool = True) -> Company:
    """Build the TTM base from a pack (see pack_from_site). base='ttm' (last four quarters) or 'fy' (latest year).
    Costs come from the quarterly detail lines when present, else the latest year's split applied to TTM costs."""
    prof = pack.get("profile", {}) or {}
    dq = pack.get("dataQuality", {}) or {}
    sym = pack.get("symbol") or prof.get("symbol", "")
    if dq.get("isBank"):
        raise ValueError(f"{sym}: banks, NBFCs and insurers are not covered by Stress Lab v1")
    notes: List[str] = []
    y, q = pack.get("yearly") or {}, pack.get("quarterly") or {}
    if base.startswith(("fy:", "q:")):              # one past year or quarter, for back-tests
        kind, per = base.split(":", 1)
        tbl = y if kind == "fy" else q
        labels = [str(p) for p in tbl.get("periods", [])]
        if per not in labels:
            raise ValueError(f"{sym}: no {per} in the {'yearly' if kind == 'fy' else 'quarterly'} statement")
        idx = [labels.index(per)]
        label = f"FY{per[-2:]}" if kind == "fy" else per
        base_end = f"{per}-03-31" if kind == "fy" else _quarter_end(per)
    else:
        use_q = base == "ttm" and len(q.get("periods", [])) >= 4 and _sum(_row(q, "revenue")[:4]) is not None
        tbl, idx = (q, range(4)) if use_q else (y, range(1))
        if not use_q and base == "ttm":
            notes.append("Fewer than four quarters available: the base is the latest full year.")
        label = (f"TTM {q['periods'][3]} to {q['periods'][0]}" if use_q else f"FY{str(y['periods'][0])[-2:]}")
        base_end = _quarter_end(q["periods"][0]) if use_q else (f"{y['periods'][0]}-03-31" if y.get("periods") else None)

    rev = _sum([_row(tbl, "revenue")[i] for i in idx])
    op = _sum([_row(tbl, "operating_profit")[i] for i in idx])
    rm, emp, opex = _cost_split(tbl, idx)
    if None in (rev, op):
        raise ValueError(f"{sym}: revenue or operating profit missing for {label}")
    if None in (rm, emp, opex):                      # quarterly lines missing: latest year's split on TTM costs
        yrm, yemp, yop = _cost_split(y, range(1))
        if None in (yrm, yemp, yop):
            raise ValueError(f"{sym}: no cost split (materials / employees / other expenses) in the income statement")
        tot = yrm + yemp + yop
        costs = rev - op
        rm, emp, opex = costs * yrm / tot, costs * yemp / tot, costs * yop / tot
        notes.append("Cost split taken from the latest full year and applied to TTM costs.")
    if op is not None and rev is not None:
        gap = (rev - op) - (rm + emp + opex)
        if abs(gap) > 0.02 * rev:
            notes.append(f"Costs differ from revenue minus operating profit by Rs {gap:,.0f} cr; the difference is "
                         "treated as other expenses.")
        opex += gap                                   # make EBITDA match the reported operating profit exactly
    oi = _sum([_row(tbl, "other_income")[i] for i in idx]) or 0.0
    dep = _sum([_row(tbl, "depreciation")[i] for i in idx]) or 0.0
    intr = _sum([_row(tbl, "interest")[i] for i in idx]) or 0.0
    exc = _sum([_row(tbl, "exceptional")[i] or 0.0 for i in idx]) or 0.0
    pbt = _sum([_row(tbl, "pbt")[i] for i in idx])
    tax = _sum([_row(tbl, "tax")[i] for i in idx])
    t = TAX_DEFAULT
    if pbt and tax is not None and pbt - exc > 0:
        t = _clip(tax / (pbt - exc), 0.15, 0.35)
    eps_rep = _sum([_row(tbl, "eps")[i] for i in idx])

    bs = pack.get("bs", {}) or {}
    last = lambda k: next((v for v in reversed(bs.get(k) or []) if v is not None), 0.0)  # noqa: E731
    shares = _f(pack.get("shares_cr"))
    if not shares and eps_rep:
        shares = (_sum([_row(tbl, "pbt")[i] for i in idx]) or 0) * (1 - t) / eps_rep
        notes.append("Share count estimated from EPS.")
    basic = prof.get("sector") or prof.get("subIndustry") or ""
    industry = prof.get("industry") or ""
    sector = nse_sector_of(industry) or industry
    exp = (table or exposures()).lookup(symbol=sym, basic=basic, industry=industry, sector=sector, override=override)
    if exp.excluded:
        raise ValueError(f"{sym}: {' '.join(exp.notes) or 'not covered by Stress Lab v1'}")

    g = growth
    if g is None:
        revs = [v for v in _row(y, "revenue") if v]
        if len(revs) >= 6 and revs[5] > 0:
            g = ((revs[0] / revs[5]) ** (1 / 5) - 1) * 100
        g = _clip(g if g is not None else 6.0, 3.0, 8.0)
    co = Company(symbol=sym, name=prof.get("name", sym), revenue=rev, rm=rm, emp=emp, opex=opex, other_income=oi,
                 dep=dep, interest=intr, tax_rate=t, shares=shares or float("nan"), debt=last("borrowings"),
                 cash=last("cash") + last("investments"), price=_f((pack.get("quote") or {}).get("price")),
                 beta=beta if beta is not None else 1.0, growth=g, exposure=exp, base_label=label, base_end=base_end,
                 reported_eps=eps_rep, notes=notes)
    if beta is None:
        co.notes.append("Beta not supplied: 1.0 used (compute it from two years of weekly returns vs Nifty 50).")
    if rev and not 0.05 <= rm / rev <= 0.95:
        co.notes.append(f"Raw materials are {rm / rev:.0%} of revenue: check the cost lines.")
    if eps_rep and co.eps == co.eps and abs(co.eps / eps_rep - 1) > 0.25:
        co.notes.append(f"Model EPS ({co.eps:.2f}) differs from reported EPS ({eps_rep:.2f}) by more than 25% "
                        "(exceptional items or minority interests).")
    if calibrate_history:
        cal = calibrate(pack, exp, macro_fy=macro_fy)
        co.calibration = cal
        co.exposure = replace(exp, pass_through=cal["pass_through"]["value"], var_opex=cal["var_opex"]["value"],
                              demand_beta=cal["demand_beta"]["value"], notes=list(exp.notes), source=list(exp.source))
    return co


# --------------------------------------------------------------------------------------------- calibration
def load_macro_fy(path: Optional[Path] = None) -> dict:
    return json.loads(Path(path or DATA / "macro_fy.json").read_text(encoding="utf-8"))


def _fy_label(period: str) -> str:
    s = str(period)
    m = re.search(r"(\d{4})$", s) or re.search(r"FY(\d{2})", s, re.I)
    if not m:
        return s
    v = m.group(1)
    return f"FY{v[-2:]}"


def input_inflation(e: Exposure, *, crude_inr: float, fx: float, wpi: float, cpi: float, agri: float,
                    metals: Optional[float] = None) -> Tuple[float, float]:
    """Raw-material and other-expense inflation (fractions) for given moves in crude (in rupees), USD/INR, WPI
    manufactured products, CPI and farm prices. Metals default to WPI manufactured products."""
    m = wpi if metals is None else metals
    rm = (e.crude_rm * e.crude_beta * crude_inr + e.import_rm * fx + e.metal_rm * m + e.agri_rm * agri
          + e.domestic_rm * wpi)
    opex = e.energy_opex * e.energy_beta * crude_inr + (1 - e.energy_opex) * cpi
    return rm, opex


def _slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    return None if vx <= 1e-12 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx


def calibrate(pack: dict, e: Exposure, *, macro_fy: Optional[dict] = None, min_shock: float = 0.04) -> dict:
    """Pass-through, variable share of other expenses and demand sensitivity from the company's own yearly history,
    each shrunk towards the industry value by how much evidence there is. Returns values and the working."""
    mf = macro_fy or load_macro_fy()
    years = mf["years"]
    col = {k: dict(zip(years, mf[k])) for k in mf if isinstance(mf.get(k), list) and k != "years"}
    y = pack.get("yearly") or {}
    per = [_fy_label(p) for p in y.get("periods", [])]
    rev = dict(zip(per, _row(y, "revenue")))
    cogs = dict(zip(per, _cost_split_series(y)))
    opx = dict(zip(per, _row(y, "opex")))
    chron = [p for p in sorted(per, key=lambda s: int(s[2:])) if p in col.get("usdinr", {})]

    pass_rows, w_sum, wp_sum = [], 0.0, 0.0
    lev_x, lev_y, dem_x, dem_y = [], [], [], []
    prev = None                                        # the previous year's row, to spot catch-up years
    for a, b in zip(chron, chron[1:]):
        if not all(v for v in (rev.get(a), rev.get(b))):
            continue
        fx = col["usdinr"][b] / col["usdinr"][a] - 1
        crude_inr = (col["brent_usd"][b] * col["usdinr"][b]) / (col["brent_usd"][a] * col["usdinr"][a]) - 1
        pi, _ = input_inflation(e, crude_inr=crude_inr, fx=fx, wpi=col["wpi_mfg"][b] / 100,
                                cpi=col["cpi"][b] / 100, agri=col["wpi_primary"][b] / 100)
        s0 = cogs.get(a) / rev[a] if cogs.get(a) else None
        s1 = cogs.get(b) / rev[b] if cogs.get(b) else None
        row = {"year": b, "input_inflation_pct": _r(pi * 100), "rm_share_before": _r(s0, 4), "rm_share_after": _r(s1, 4)}
        if s0 and s1 and abs(pi) >= min_shock:
            implied_price = (1 + pi) * s0 / s1 - 1
            p = implied_price / (pi * s0)
            row.update(implied_price_rise_pct=_r(implied_price * 100), pass_through=_r(p, 3))
            catch_up = (prev is not None and prev.get("pass_through") is not None and prev["pass_through"] < 0.9
                        and abs(prev["_pi"]) >= abs(pi))
            if catch_up:
                # prices still catching up on last year's bigger shock: report the two-year figure instead
                cum = (1 + prev["_pi"]) * (1 + pi) - 1
                p2 = ((1 + cum) * prev["_s0"] / s1 - 1) / (cum * prev["_s0"])
                row["catch_up_year"] = True
                prev["two_year_pass_through"] = _r(p2, 3)
            else:
                p = _clip(p, -0.2, 1.2)
                w_sum += abs(pi)
                wp_sum += abs(pi) * p
            row["_pi"], row["_s0"] = pi, s0
        pass_rows.append(row)
        prev = row if "_pi" in row else None
        g_rev = math.log(rev[b] / rev[a])
        if opx.get(a) and opx.get(b):
            lev_x.append(g_rev - col["wpi_mfg"][b] / 100)
            lev_y.append(math.log(opx[b] / opx[a]) - col["cpi"][b] / 100)
        if "gdp" in col:
            dem_x.append(col["gdp"][b])
            dem_y.append((g_rev - col["wpi_mfg"][b] / 100) * 100)

    def shrink(est: Optional[float], prior: float, n: int, k: float, lo: float, hi: float) -> dict:
        if est is None or n == 0:
            return {"value": prior, "estimate": None, "years_used": 0, "weight_on_history": 0.0, "industry_value": prior}
        w = n / (n + k)
        return {"value": _r(_clip(w * _clip(est, lo, hi) + (1 - w) * prior, lo, hi), 3), "estimate": _r(est, 3),
                "years_used": n, "weight_on_history": _r(w, 2), "industry_value": prior}

    n_pass = sum(1 for r in pass_rows if "pass_through" in r and not r.get("catch_up_year"))
    for r in pass_rows:
        r.pop("_pi", None)
        r.pop("_s0", None)
    out = {
        "pass_through": shrink(wp_sum / w_sum if w_sum else None, e.pass_through, n_pass, 2.0, 0.1, 1.0),
        "var_opex": shrink(_slope(lev_x, lev_y), e.var_opex, len(lev_x), 4.0, 0.2, 0.9),
        "demand_beta": shrink(_slope([x - _mean(dem_x) for x in dem_x], dem_y) if dem_x else None, e.demand_beta,
                              len(dem_x), 6.0, 0.2, 2.5),
        "years": pass_rows,
        "method": "pass-through = implied price rise / (input inflation x raw-material share), weighted by the size "
                  "of the input shock; years with input inflation under 4% and catch-up years (prices still adjusting "
                  "to the previous year's larger shock) are left out; then shrunk to the industry value",
    }
    out["pass_through"]["value"] = _r(out["pass_through"]["value"], 3)
    return out


def _cost_split_series(tbl: dict) -> List[Optional[float]]:
    n = len(tbl.get("periods", []))
    cogs = _row(tbl, "cogs")
    if all(v is None for v in cogs):
        parts = [_row(tbl, k) for k in ("materials", "traded", "inv_change")]
        cogs = [None if all(p[i] is None for p in parts) else sum(p[i] or 0.0 for p in parts) for i in range(n)]
    return cogs


# --------------------------------------------------------------------------------------------- scenarios
@dataclass
class Scenario:
    """Shocks in the units people talk in. Percent numbers: crude=45 means Brent 45% higher than in the base."""
    name: str = "Custom"
    crude: float = 0.0          # % change in Brent, US$
    usdinr: float = 0.0         # % change in USD/INR (+ = rupee weaker)
    cpi: float = 0.0            # pp extra consumer inflation (wages, services)
    wpi: Optional[float] = None  # pp extra wholesale inflation on domestic materials (None = same as cpi)
    rate_bp: float = 0.0        # change in borrowing rates, basis points
    demand: float = 0.0         # % change in volumes for the average company (scaled by demand_beta)
    erp_bp: float = 0.0         # change in the equity risk premium, basis points
    metals: Optional[float] = None  # % change in metal prices (None = same as wpi)
    agri: Optional[float] = None    # pp extra farm-price inflation (None = same as wpi)
    persistence: str = "one_year"   # "one_year": earnings return to the base path after a year; "permanent"
    description: str = ""
    as_of: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)

    @property
    def rupee_value_pct(self) -> float:
        """The same move said the other way: the rupee's value against the dollar, % (negative = weaker)."""
        return (1 / (1 + self.usdinr / 100) - 1) * 100


PRESETS: Dict[str, Scenario] = {
    "2022": Scenario("2022 commodity and rate shock", crude=45, usdinr=8.7, cpi=2.5, wpi=5.0, rate_bp=250, demand=-3,
                     erp_bp=50, description="Crude up by half, rupee down 8%, RBI hiking 250 bp: FY22 to FY23"),
    "2020": Scenario("2020 lockdown", crude=-50, usdinr=5.3, cpi=1.0, wpi=0.0, rate_bp=-115, demand=-25, erp_bp=200,
                     description="Demand collapse with crude halving and rates cut: Q1 FY21"),
    "oil": Scenario("Oil spike", crude=50, usdinr=3.0, cpi=1.0, wpi=2.0,
                    description="Crude up by half with a slightly weaker rupee; nothing else moves"),
    "rupee": Scenario("Rupee slide", usdinr=10.0, cpi=0.5, wpi=1.0, description="Rupee 9% weaker against the dollar"),
    "rates": Scenario("Rates up", rate_bp=150, erp_bp=25, description="Borrowing costs up 150 bp"),
    "slowdown": Scenario("Demand slowdown", demand=-10, rate_bp=-50, erp_bp=100,
                         description="Volumes 10% lower for the average company, rates eased 50 bp"),
}


def _points(series: Any) -> List[Tuple[str, float]]:
    pts = series.get("points") or series.get("data") if isinstance(series, dict) else series
    out = []
    for p in pts or []:
        d, v = (p[0], p[1]) if isinstance(p, (list, tuple)) else (p.get("date") or p.get("d"), p.get("value", p.get("v")))
        if d and _f(v) is not None:
            out.append((str(d)[:10], float(v)))
    return sorted(out)


def _window(pts: List[Tuple[str, float]], start: str, end: str) -> List[float]:
    return [v for d, v in pts if start < d <= end]


def _months(start: str, end: str) -> int:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return (b.year - a.year) * 12 + b.month - a.month


def today_scenario(macro: dict, *, brent: Sequence, base_end: str, brent_now: Optional[float] = None,
                   usdinr_now: Optional[float] = None, usdinr: Optional[Sequence] = None, as_of: Optional[str] = None,
                   months: int = 12, name: str = "Today") -> Scenario:
    """Today's conditions measured against the base window (the 12 months to base_end, the company's TTM).
    macro = FinLit /api/macro JSON (or its 'series'); brent = [(date, US$)] daily, monthly or quarterly averages
    stamped at period end; usdinr = optional [(date, rate)] monthly averages used when FinLit's series has gaps.
    Prices: level now / window average - 1. Inflation and rates: latest minus window average (the base profits
    were earned under the window's conditions; the shock is how far today differs)."""
    s = macro.get("series", macro)
    end = base_end
    start = _shift_month_end(end, -months)
    inputs: Dict[str, Any] = {"base_window": [start, end]}
    warn: List[str] = []

    b = _points(brent)
    b_base = _mean(_window(b, start, end))
    b_now = brent_now if brent_now is not None else (b[-1][1] if b else None)
    if b_base is None or b_now is None:
        raise ValueError("no Brent prices in the base window")
    fx_site = [(d, v) for d, v in _points(s.get("usdinr", [])) if len(d) == 10]
    fx_site_m = [(d, v) for d, v in fx_site if start < d <= end]
    fx_src = "FinLit usdinr"
    fx_pts = fx_site
    if len(fx_site_m) < months - 2:
        warn.append(f"FinLit's USD/INR series has {len(fx_site_m)} of {months} months in the base window")
        if usdinr is None:
            raise ValueError(warn[-1] + "; pass usdinr= monthly averages from another source")
        fx_pts, fx_src = _points(usdinr), "usdinr argument"
    fx_base = _mean(_window(fx_pts, start, end))
    fx_now = usdinr_now if usdinr_now is not None else (fx_site[-1][1] if fx_site else fx_pts[-1][1])
    inputs.update(brent_now=b_now, brent_base=_r(b_base), usdinr_now=fx_now, usdinr_base=_r(fx_base, 4),
                  usdinr_source=fx_src)

    def gap(key: str, label: str) -> Optional[float]:
        pts = _points(s.get(key, []))
        w = _window(pts, start, end)
        if not pts or not w:
            warn.append(f"{label}: no data in the base window")
            return None
        inputs[key] = {"latest": pts[-1][1], "latest_date": pts[-1][0], "base_avg": _r(_mean(w))}
        return pts[-1][1] - _mean(w)

    cpi = gap("cpi", "CPI")
    wpi = gap("wpi_mfg", "WPI manufactured products")
    agri = gap("wpi_primary", "WPI primary articles")
    repo = gap("repo", "Repo rate")
    gdp = gap("gdp", "Real GDP growth")
    inputs["warnings"] = warn
    sc = Scenario(name=name, crude=(b_now / b_base - 1) * 100, usdinr=(fx_now / fx_base - 1) * 100,
                  cpi=cpi or 0.0, wpi=wpi, agri=agri, rate_bp=(repo or 0.0) * 100, demand=gdp or 0.0, erp_bp=0.0,
                  description=f"Brent, rupee, inflation, repo and GDP growth now vs their average over {start[:7]} "
                              f"to {end[:7]}, held for a year", as_of=as_of, inputs=inputs)
    for k in ("crude", "usdinr", "cpi", "rate_bp", "demand"):
        setattr(sc, k, round(getattr(sc, k), 2))
    sc.wpi = None if wpi is None else round(wpi, 2)
    sc.agri = None if agri is None else round(agri, 2)
    return sc


def _shift_month_end(d: str, months: int) -> str:
    x = date.fromisoformat(d)
    m = x.year * 12 + (x.month - 1) + months
    yy, mm = divmod(m, 12)
    mm += 1
    nxt = date(yy + (mm == 12), (mm % 12) + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1).isoformat()


def macro_fy_from_series(macro: dict, brent: Sequence, usdinr: Optional[Sequence] = None,
                         first: int = 2018, last: Optional[int] = None) -> dict:
    """Rebuild data/macro_fy.json from FinLit /api/macro and a Brent series (EIA). For the nightly job."""
    s = macro.get("series", macro)

    def fy(d: str) -> int:
        return int(d[:4]) + (1 if int(d[5:7]) >= 4 else 0)

    def avg(pts: List[Tuple[str, float]], monthly_only: bool = True) -> Dict[int, float]:
        g: Dict[int, List[float]] = {}
        for d, v in pts:
            g.setdefault(fy(d), []).append(v)
        return {k: sum(v) / len(v) for k, v in g.items()}

    cols = {"brent_usd": avg(_points(brent)),
            "usdinr": avg(_points(usdinr) if usdinr is not None else _points(s.get("usdinr", []))),
            **{k: avg(_points(s.get(k, []))) for k in ("cpi", "wpi_mfg", "wpi_primary", "wpi_fuel", "gdp")}}
    last = last or max(max(v) for v in cols.values() if v)
    yrs = [y for y in range(first, last + 1) if all(y in c for c in cols.values())]
    return {"as_of": date.today().isoformat(), "years": [f"FY{y % 100:02d}" for y in yrs],
            **{k: [round(c[y], 2) for y in yrs] for k, c in cols.items()}}


# --------------------------------------------------------------------------------------------- the model
def _engine(co: Company, sc: Scenario) -> Dict[str, Any]:
    e = co.exposure
    c, f = sc.crude / 100, sc.usdinr / 100
    cpi = sc.cpi / 100
    wpi = (sc.cpi if sc.wpi is None else sc.wpi) / 100
    agri = wpi if sc.agri is None else sc.agri / 100
    met = wpi if sc.metals is None else sc.metals / 100
    q = e.demand_beta * sc.demand / 100
    c_inr = (1 + c) * (1 + f) - 1
    cr_part, fx_part = c * (1 + f), f                     # c_inr = crude part + rupee part

    R, RM, EMP, OPX = co.revenue, co.rm, co.emp, co.opex
    v = e.var_opex
    opex_vol = OPX * ((1 - v) + v * (1 + q))
    # input-price cost increase at the new volume, split by cause
    dC = {
        "crude": RM * (1 + q) * e.crude_rm * e.crude_beta * cr_part + opex_vol * e.energy_opex * e.energy_beta * cr_part,
        "rupee": RM * (1 + q) * (e.crude_rm * e.crude_beta + e.import_rm) * fx_part
                 + opex_vol * e.energy_opex * e.energy_beta * fx_part,
        "commodities": RM * (1 + q) * (e.metal_rm * met + e.agri_rm * agri),
        "inflation": RM * (1 + q) * e.domestic_rm * wpi + opex_vol * (1 - e.energy_opex) * cpi + EMP * cpi,
    }
    dC_total = sum(dC.values())
    pass_share = e.pass_through * e.domestic_rev
    price_gain = pass_share * dC_total
    rev_fx = R * (1 + q) * (e.export_rev * f + e.crude_rev * e.crude_rev_beta * fx_part)
    rev_crude = R * (1 + q) * e.crude_rev * e.crude_rev_beta * cr_part

    R1 = R * (1 + q) + rev_fx + rev_crude + price_gain
    RM1 = RM * (1 + q) + RM * (1 + q) * (e.crude_rm * e.crude_beta * c_inr + e.import_rm * f + e.metal_rm * met
                                         + e.agri_rm * agri + e.domestic_rm * wpi)
    OPX1 = opex_vol * (1 + e.energy_opex * e.energy_beta * c_inr + (1 - e.energy_opex) * cpi)
    EMP1 = EMP * (1 + cpi)
    E1 = R1 - RM1 - OPX1 - EMP1
    dr = sc.rate_bp / 10000
    I1 = max(0.0, co.interest + co.debt * e.floating_debt * dr)
    OI1 = co.other_income + co.cash * dr * 0.5            # half of liquid funds reprice within the year
    PBT1 = E1 + OI1 - co.dep - I1
    t = co.tax_rate
    eps0, eps1 = co.eps, PBT1 * (1 - t) / co.shares

    volume = q * (R - RM - v * OPX)                       # contribution margin on the extra / lost volume
    drivers_rs = {
        "demand": volume,
        "crude": rev_crude - dC["crude"] * (1 - pass_share),
        "rupee": rev_fx - dC["rupee"] * (1 - pass_share),
        "inflation": -dC["inflation"] * (1 - pass_share),
        "commodities": -dC["commodities"] * (1 - pass_share),
        "interest": -(I1 - co.interest) + (OI1 - co.other_income),
    }
    return dict(R1=R1, RM1=RM1, OPX1=OPX1, EMP1=EMP1, E1=E1, I1=I1, OI1=OI1, PBT1=PBT1, eps0=eps0, eps1=eps1,
                q=q, c_inr=c_inr, dC=dC, dC_total=dC_total, price_gain=price_gain, pass_share=pass_share,
                drivers_rs=drivers_rs)


def _cover(ebitda: float, oi: float, dep: float, interest: float) -> Optional[float]:
    return None if interest <= 0.005 * max(1.0, abs(ebitda)) else (ebitda + oi - dep) / interest


def _value_move(co: Company, sc: Scenario, eps0: float, eps1: float) -> Optional[Dict[str, float]]:
    if not (eps0 > 0):
        return None
    k = (RF_DEFAULT + co.beta * ERP_DEFAULT) / 100
    g = min(co.growth / 100, k - 0.03)
    k1 = k + LONG_RATE_SHARE * sc.rate_bp / 10000 + co.beta * sc.erp_bp / 10000
    g1 = min(g, k1 - 0.03)
    base = eps0 / (k - g)
    if sc.persistence == "permanent":
        new = eps1 / (k1 - g1) if eps1 > 0 else 0.0
    else:
        new = eps1 / (1 + k1) + eps0 * (1 + g1) / ((k1 - g1) * (1 + k1))
    return {"move_pct": (new / base - 1) * 100, "k_pct": k * 100, "k_new_pct": k1 * 100, "g_pct": g * 100}


def _label(eps_chg: Optional[float], cover1: Optional[float], has_debt: bool) -> Tuple[str, str]:
    if has_debt and cover1 is not None and cover1 < COVER_FLOOR:
        return "Debt cover at risk", "Operating profit would cover interest less than 1.5 times"
    if eps_chg is None:
        return "Not comparable", "Loss in the base period, so a percentage change in EPS is not meaningful"
    if eps_chg <= -30:
        return "Hit hard", "Earnings per share fall by 30% or more"
    if eps_chg <= -10:
        return "Takes a clear hit", "Earnings per share fall by 10% to 30%"
    if eps_chg >= 10:
        return "Gains under this shock", "Earnings per share rise by 10% or more"
    return "Holds up well", "Earnings per share move by less than 10%"


DRIVER_NAMES = {"demand": "Demand / volumes", "crude": "Crude oil", "rupee": "Rupee",
                "inflation": "Wages and general inflation", "commodities": "Metals and farm prices",
                "interest": "Interest rates"}


def run(co: Company, sc: Scenario) -> Dict[str, Any]:
    """One company, one scenario -> the numbers the page shows."""
    x = _engine(co, sc)
    e0, e1 = co.ebitda, x["E1"]
    eps0, eps1 = x["eps0"], x["eps1"]
    eps_chg = (eps1 / eps0 - 1) * 100 if eps0 > 0 else None
    cov0 = _cover(e0, co.other_income, co.dep, co.interest)
    cov1 = _cover(e1, x["OI1"], co.dep, x["I1"])
    has_debt = co.debt > 0 and co.interest > 0
    label, why = _label(eps_chg, cov1, has_debt)
    score = None
    if eps_chg is not None:
        score = _clip(100 + 1.25 * eps_chg, 0, 100)
    elif e0 > 0:
        score = _clip(100 + 1.25 * (e1 / e0 - 1) * 100, 0, 100)
    if score is not None and has_debt and cov1 is not None and cov1 < COVER_FLOOR:
        score = min(score, 30.0)
    per_share = (1 - co.tax_rate) / co.shares
    drivers = [{"key": k, "name": DRIVER_NAMES[k], "rs_cr": _r(v, 1),
                "eps_pct": _r(v * per_share / eps0 * 100, 2) if eps0 > 0 else None}
               for k, v in x["drivers_rs"].items()]
    drivers.sort(key=lambda d: d["rs_cr"])
    val = _value_move(co, sc, eps0, eps1)
    return {
        "symbol": co.symbol, "name": co.name, "scenario": scenario_dict(sc), "base_label": co.base_label,
        "base": {"revenue": _r(co.revenue, 1), "ebitda": _r(e0, 1), "ebitda_margin_pct": _r(e0 / co.revenue * 100),
                 "other_income": _r(co.other_income, 1), "depreciation": _r(co.dep, 1), "interest": _r(co.interest, 1),
                 "pbt": _r(co.pbt, 1), "eps": _r(eps0), "interest_cover": _r(cov0, 1)},
        "stressed": {"revenue": _r(x["R1"], 1), "ebitda": _r(e1, 1), "ebitda_margin_pct": _r(e1 / x["R1"] * 100),
                     "other_income": _r(x["OI1"], 1), "interest": _r(x["I1"], 1), "pbt": _r(x["PBT1"], 1),
                     "eps": _r(eps1), "interest_cover": _r(cov1, 1)},
        "change_pct": {"revenue": _r((x["R1"] / co.revenue - 1) * 100), "ebitda": _r((e1 / e0 - 1) * 100) if e0 > 0 else None,
                       "eps": _r(eps_chg), "margin_pts": _r((e1 / x["R1"] - e0 / co.revenue) * 100)},
        "value": None if val is None else {k: _r(v) for k, v in val.items()},
        "score": _r(score, 0), "label": label, "label_reason": why,
        "drivers": drivers,
        "working": {"volume_change_pct": _r(x["q"] * 100), "crude_in_rupees_pct": _r(x["c_inr"] * 100),
                    "cost_increase_rs_cr": {k: _r(v, 1) for k, v in x["dC"].items()},
                    "cost_increase_total_rs_cr": _r(x["dC_total"], 1),
                    "recovered_through_prices_rs_cr": _r(x["price_gain"], 1),
                    "share_recovered": _r(x["pass_share"], 3)},
        "assumptions": company_dict(co),
        "model": MODEL_VERSION, "disclaimer": DISCLAIMER,
    }


def explain(r: Dict[str, Any]) -> List[str]:
    """Plain sentences for the page, from a run() result. Descriptive only."""
    L = []
    ch = r["change_pct"]
    sc = r["scenario"]["name"]
    if ch["eps"] is not None and ch["ebitda"] is not None:
        L.append(f"Under '{sc}', {r['name']}'s earnings per share move {ch['eps']:+.1f}% "
                 f"(EBITDA {ch['ebitda']:+.1f}%, revenue {ch['revenue']:+.1f}%).")
    worst = r["drivers"][0]
    if worst["rs_cr"] < 0:
        L.append(f"The biggest drag is {worst['name'].lower()}: about Rs {abs(worst['rs_cr']):,.0f} crore of "
                 f"pre-tax profit.")
    w = r["working"]
    if w["cost_increase_total_rs_cr"] and abs(w["cost_increase_total_rs_cr"]) > 1:
        L.append(f"Input costs change by Rs {w['cost_increase_total_rs_cr']:,.0f} crore; about "
                 f"{w['share_recovered'] * 100:.0f}% of that is recovered through prices within the year.")
    cov = r["stressed"]["interest_cover"]
    if cov is not None and r["base"]["interest_cover"] is not None:
        L.append(f"Operating profit covers interest {cov:.1f} times after the shock "
                 f"({r['base']['interest_cover']:.1f} times before).")
    L.append(f"Label: {r['label']}. {r['label_reason']}.")
    return L


def compare(a: Company, b: Company, sc: Scenario) -> Dict[str, Any]:
    ra, rb = run(a, sc), run(b, sc)
    ea, eb = ra["change_pct"]["eps"], rb["change_pct"]["eps"]
    summary = None
    if ea is not None and eb is not None:
        lo, hi = (ra, rb) if ea < eb else (rb, ra)
        gap = abs(ea - eb)
        if gap < 3:
            summary = f"Both companies are affected about equally ({ea:+.1f}% and {eb:+.1f}% in EPS)."
        else:
            d = lo["drivers"][0]["name"].lower()
            summary = (f"{lo['name']} is more exposed to this shock: EPS {lo['change_pct']['eps']:+.1f}% against "
                       f"{hi['change_pct']['eps']:+.1f}% for {hi['name']}, mainly through {d}.")
    return {"scenario": scenario_dict(sc), "a": ra, "b": rb, "summary": summary, "disclaimer": DISCLAIMER}


def _solve(f, lo: float, hi: float, target: float, it: int = 60) -> Optional[float]:
    flo, fhi = f(lo) - target, f(hi) - target
    if flo * fhi > 0:
        return None
    for _ in range(it):
        mid = (lo + hi) / 2
        fm = f(mid) - target
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def breaking_points(co: Company) -> Dict[str, Any]:
    """The single shock, others at zero, that halves EPS (crude rise, demand fall) or takes interest cover below
    1.5 times (rate rise). None = not reached within the range tried."""
    if not co.eps > 0:
        return {"crude_pct": None, "demand_pct": None, "rate_bp": None, "note": "Loss in the base period"}
    eps = lambda sc: _engine(co, sc)["eps1"]  # noqa: E731
    half = co.eps / 2
    crude = _solve(lambda x: eps(Scenario(crude=x)), 0, 500, half)
    if crude is None and eps(Scenario(crude=-60)) <= half:
        crude = _solve(lambda x: eps(Scenario(crude=x)), -95, 0, half)
    demand = _solve(lambda x: eps(Scenario(demand=x)), -95, 0, half)

    def cover_at(bp: float) -> float:
        x = _engine(co, Scenario(rate_bp=bp))
        c = _cover(x["E1"], x["OI1"], co.dep, x["I1"])
        return 1e9 if c is None else c
    rate = _solve(cover_at, 0, 3000, COVER_FLOOR) if co.debt * co.exposure.floating_debt > 0 else None
    return {"crude_pct": _r(crude, 1), "demand_pct": _r(demand, 1), "rate_bp": _r(rate, 0),
            "how": "each found alone, with every other shock at zero; crude and demand halve EPS, the rate rise "
                   "takes interest cover below 1.5 times; searched up to +500% crude, -95% demand, +3,000 bp"}


def sensitivities(co: Company) -> Dict[str, Optional[float]]:
    """EPS change (%) for one standard step in each driver, for the 'what moves this company' chart."""
    steps = {"crude +10%": Scenario(crude=10), "rupee 5% weaker": Scenario(usdinr=5.26),
             "inflation +1 pt": Scenario(cpi=1), "rates +100 bp": Scenario(rate_bp=100),
             "volumes -5%": Scenario(demand=-5)}
    out = {}
    for k, sc in steps.items():
        x = _engine(co, sc)
        out[k] = _r((x["eps1"] / x["eps0"] - 1) * 100, 2) if x["eps0"] > 0 else None
    return out


# --------------------------------------------------------------------------------------------- back-tests
def backtest_years(pack: dict, *, macro_fy: Optional[dict] = None, pass_through: str = "industry",
                   min_shock: float = 4.0) -> List[Dict[str, Any]]:
    """Replay each past year: base = year A as reported, scenario = what actually happened to crude, the rupee and
    prices between A and B, volume = revenue growth less WPI manufactured-products inflation. Compares the
    predicted EBITDA margin with the reported one. pass_through='industry' keeps the industry value (out of
    sample); 'calibrated' uses the company's own estimate (in sample, flatters the model)."""
    mf = macro_fy or load_macro_fy()
    col = {k: dict(zip(mf["years"], mf[k])) for k in mf if isinstance(mf.get(k), list) and k != "years"}
    y = pack.get("yearly") or {}
    per = [str(p) for p in y.get("periods", [])]
    rev = dict(zip(per, _row(y, "revenue")))
    op = dict(zip(per, _row(y, "operating_profit")))
    out = []
    base_co = company_from_pack(pack, base="fy", calibrate_history=(pass_through == "calibrated"), macro_fy=mf)
    for a, b in zip(sorted(per), sorted(per)[1:]):
        fa, fb = _fy_label(a), _fy_label(b)
        if fa not in col["usdinr"] or fb not in col["usdinr"] or not (rev.get(a) and rev.get(b) and op.get(b)):
            continue
        co = company_from_pack(pack, base=f"fy:{a}", calibrate_history=False)
        co.exposure = replace(base_co.exposure, notes=[], source=[])
        crude = (col["brent_usd"][fb] / col["brent_usd"][fa] - 1) * 100
        fx = (col["usdinr"][fb] / col["usdinr"][fa] - 1) * 100
        vol = ((rev[b] / rev[a]) / (1 + col["wpi_mfg"][fb] / 100) - 1) * 100
        sc = Scenario(name=f"{fa} to {fb} as it happened", crude=crude, usdinr=fx, cpi=col["cpi"][fb],
                      wpi=col["wpi_mfg"][fb], agri=col["wpi_primary"][fb],
                      demand=vol / co.exposure.demand_beta if co.exposure.demand_beta else 0.0)
        x = _engine(co, sc)
        pi, _ = input_inflation(co.exposure, crude_inr=x["c_inr"], fx=fx / 100, wpi=col["wpi_mfg"][fb] / 100,
                                cpi=col["cpi"][fb] / 100, agri=col["wpi_primary"][fb] / 100)
        m0 = co.ebitda / co.revenue * 100
        pred, act = x["E1"] / x["R1"] * 100, op[b] / rev[b] * 100
        out.append({"from": fa, "to": fb, "input_inflation_pct": _r(pi * 100), "volume_pct": _r(vol),
                    "margin_before": _r(m0), "margin_predicted": _r(pred), "margin_reported": _r(act),
                    "change_predicted_pts": _r(pred - m0), "change_reported_pts": _r(act - m0),
                    "error_pts": _r(pred - act), "shock_year": abs(pi * 100) >= min_shock,
                    "pass_through_used": co.exposure.pass_through})
    return out


def backtest_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Direction hit rate and mean absolute error of the margin change, all years and shock years only."""
    def stats(rs):
        if not rs:
            return {"years": 0}
        hits = sum(1 for r in rs if (r["change_predicted_pts"] >= 0) == (r["change_reported_pts"] >= 0))
        return {"years": len(rs), "direction_right": hits,
                "mean_abs_error_pts": _r(sum(abs(r["error_pts"]) for r in rs) / len(rs)),
                "mean_abs_change_reported_pts": _r(sum(abs(r["change_reported_pts"]) for r in rs) / len(rs))}
    return {"all_years": stats(rows), "shock_years": stats([r for r in rows if r["shock_year"]])}


# --------------------------------------------------------------------------------------------- JSON for the site
def scenario_dict(sc: Scenario) -> Dict[str, Any]:
    d = asdict(sc)
    d["rupee_value_pct"] = _r(sc.rupee_value_pct)
    return d


def company_dict(co: Company) -> Dict[str, Any]:
    e = co.exposure
    return {
        "base_label": co.base_label, "base_end": co.base_end,
        "revenue": _r(co.revenue, 1), "raw_materials": _r(co.rm, 1), "employees": _r(co.emp, 1),
        "other_expenses": _r(co.opex, 1), "raw_material_share_pct": _r(co.rm / co.revenue * 100),
        "other_income": _r(co.other_income, 1), "depreciation": _r(co.dep, 1), "interest": _r(co.interest, 1),
        "tax_rate_pct": _r(co.tax_rate * 100), "shares_cr": _r(co.shares, 3), "debt": _r(co.debt, 1),
        "cash_and_investments": _r(co.cash, 1), "beta": co.beta, "growth_pct": _r(co.growth),
        "reported_eps_ttm": _r(co.reported_eps), "model_eps": _r(co.eps),
        "exposure": {k: getattr(e, k) for k in sorted(_EXPOSURE_KEYS) if k != "excluded"},
        "exposure_source": e.source, "exposure_notes": e.notes,
        "calibration": {k: co.calibration[k] for k in ("pass_through", "var_opex", "demand_beta") if k in co.calibration},
        "notes": co.notes,
    }


def stress_page(co: Company, scenarios: Optional[Dict[str, Scenario]] = None) -> Dict[str, Any]:
    """Everything the single-company page needs: every scenario, the breaking points and the sensitivities."""
    scs = scenarios or PRESETS
    runs = {k: run(co, sc) for k, sc in scs.items()}
    for r in runs.values():
        r.pop("assumptions", None)
        r["explain"] = explain(r)
    return {"symbol": co.symbol, "name": co.name, "assumptions": company_dict(co), "scenarios": runs,
            "breaking_points": breaking_points(co), "sensitivities": sensitivities(co),
            "calibration_years": co.calibration.get("years", []), "model": MODEL_VERSION, "disclaimer": DISCLAIMER}


def beta_from_returns(stock: Sequence[float], index: Sequence[float], blume: bool = True) -> Optional[float]:
    """Beta from two aligned series of weekly returns (two years = 104 weeks recommended), Blume-adjusted."""
    n = min(len(stock), len(index))
    if n < 26:
        return None
    b = _slope(list(index[-n:]), list(stock[-n:]))
    if b is None:
        return None
    return round(0.67 * b + 0.33 if blume else b, 3)


# --------------------------------------------------------------------------------------------- files and command line
def load_today(path_or_dict: Any, base_end: str, as_of: Optional[str] = None) -> Scenario:
    """Today's scenario from a 'today inputs' file written by the nightly job:
    {"series": <FinLit /api/macro series> (or the whole /api/macro JSON), "brent": [[date, US$], ...] (daily from EIA),
     "brent_now": optional, "usdinr": [[date, rate], ...] optional monthly averages, "usdinr_now": optional}."""
    d = path_or_dict if isinstance(path_or_dict, dict) else json.loads(Path(path_or_dict).read_text(encoding="utf-8"))
    brent = d.get("brent") or d.get("brent_daily") or d.get("brent_quarterly") or d.get("brent_monthly")
    return today_scenario(d, brent=brent, base_end=base_end, brent_now=d.get("brent_now"),
                          usdinr_now=d.get("usdinr_now"), usdinr=d.get("usdinr") if isinstance(d.get("usdinr"), list)
                          else d.get("usdinr_monthly"), as_of=as_of or d.get("as_of"))


def _text(r: Dict[str, Any]) -> str:
    b, s, ch = r["base"], r["stressed"], r["change_pct"]
    sc = r["scenario"]
    L = [f"{r['name']} ({r['symbol']}) · base {r['base_label']} · scenario: {sc['name']}",
         f"  shocks: crude {sc['crude']:+.1f}%  USD/INR {sc['usdinr']:+.1f}% (rupee {sc['rupee_value_pct']:+.1f}%)  "
         f"CPI {sc['cpi']:+.1f} pt  WPI {sc['wpi'] if sc['wpi'] is not None else sc['cpi']:+.1f} pt  "
         f"rates {sc['rate_bp']:+.0f} bp  demand {sc['demand']:+.1f}%  ERP {sc['erp_bp']:+.0f} bp",
         f"  {'':14}{'base':>10}{'stressed':>11}{'change':>9}",
         f"  {'Revenue':14}{b['revenue']:>10,.0f}{s['revenue']:>11,.0f}{ch['revenue']:>+8.1f}%",
         f"  {'EBITDA':14}{b['ebitda']:>10,.0f}{s['ebitda']:>11,.0f}{(ch['ebitda'] or 0):>+8.1f}%",
         f"  {'EBITDA margin':14}{b['ebitda_margin_pct']:>9.1f}%{s['ebitda_margin_pct']:>10.1f}%{ch['margin_pts']:>+7.1f}pt",
         f"  {'EPS (model)':14}{b['eps']:>10.2f}{s['eps']:>11.2f}{(ch['eps'] or 0):>+8.1f}%"]
    if b["interest_cover"] is not None and s["interest_cover"] is not None:
        L.append(f"  {'Interest cover':14}{b['interest_cover']:>9.1f}x{s['interest_cover']:>10.1f}x")
    if r["value"]:
        L.append(f"  {'Value':14}{'':>10}{'':>11}{r['value']['move_pct']:>+8.1f}%   (k {r['value']['k_pct']:.1f}% -> "
                 f"{r['value']['k_new_pct']:.1f}%, g {r['value']['g_pct']:.1f}%)")
    L.append(f"  Score {r['score']:.0f}/100 · {r['label']}")
    L.append("  What drives it (EPS points): " + " · ".join(f"{d['name']} {d['eps_pct']:+.1f}" for d in r["drivers"]
                                                            if d["eps_pct"] is not None and abs(d["eps_pct"]) >= 0.05))
    L += ["  " + x for x in explain(r)]
    return "\n".join(L)


def cli(argv: Sequence[str]) -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="finlit_technicals stress", description="Stress Lab")
    ap.add_argument("command", choices=["stress", "stress-page", "stress-backtest", "stress-batch"])
    ap.add_argument("pack", nargs="?", help="company pack JSON (see pack_from_site)")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="a preset scenario")
    ap.add_argument("--today", help="today inputs JSON (macro series + Brent)")
    ap.add_argument("--compare", help="a second company pack")
    ap.add_argument("--set", action="append", default=[], help="custom shock, e.g. --set crude=30 --set rate_bp=100")
    ap.add_argument("--beta", type=float)
    ap.add_argument("--packs", help="stress-batch: folder of <SYMBOL>.json packs")
    ap.add_argument("--out", help="stress-batch / stress-page: output folder or file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(list(argv))
    try:
        if a.command == "stress-batch":
            if not (a.packs and a.out):
                print("stress-batch needs --packs and --out")
                return 2
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            done, bad = 0, []
            mf_file = Path(a.packs) / "_macro_fy.json"
            mf = json.loads(mf_file.read_text(encoding="utf-8")) if mf_file.exists() else None
            for p in sorted(Path(a.packs).glob("*.json")):
                if p.name.startswith("_"):
                    continue
                try:
                    co = company_from_pack(json.loads(p.read_text(encoding="utf-8")), macro_fy=mf)
                    scs = dict(PRESETS)
                    if a.today:
                        scs = {"today": load_today(a.today, co.base_end), **scs}
                    (out / f"{co.symbol}.json").write_text(json.dumps(stress_page(co, scs), ensure_ascii=False),
                                                           encoding="utf-8")
                    done += 1
                except (ValueError, KeyError, ZeroDivisionError) as e:
                    bad.append({"file": p.name, "error": str(e)})
            (out / "_summary.json").write_text(json.dumps({"written": done, "skipped": bad}, indent=1), encoding="utf-8")
            print(f"{done} companies written to {out}, {len(bad)} skipped (see _summary.json)")
            return 0
        if not a.pack:
            print("give a company pack JSON")
            return 2
        co = company_from_pack(json.loads(Path(a.pack).read_text(encoding="utf-8")), beta=a.beta)
        if a.command == "stress-backtest":
            rows = backtest_years(json.loads(Path(a.pack).read_text(encoding="utf-8")))
            res = {"years": rows, "summary": backtest_summary(rows)}
            if a.json:
                print(json.dumps(res, indent=1))
            else:
                print(f"{'years':12}{'input infl':>11}{'volume':>8}{'margin':>8}{'predicted':>10}{'reported':>9}{'error':>7}")
                for r in rows:
                    print(f"{r['from']}->{r['to']:6}{r['input_inflation_pct']:>10.1f}%{r['volume_pct']:>7.1f}%"
                          f"{r['margin_before']:>7.1f}%{r['margin_predicted']:>9.1f}%{r['margin_reported']:>8.1f}%"
                          f"{r['error_pts']:>+7.1f}")
                print(json.dumps(res["summary"]))
            return 0
        if a.command == "stress-page":
            scs = dict(PRESETS)
            if a.today:
                scs = {"today": load_today(a.today, co.base_end), **scs}
            page = stress_page(co, scs)
            txt = json.dumps(page, indent=1, ensure_ascii=False)
            if a.out:
                Path(a.out).write_text(txt, encoding="utf-8")
                print(f"written {a.out}")
            else:
                print(txt)
            return 0
        if a.today:
            sc = load_today(a.today, co.base_end)
        elif a.preset:
            sc = replace(PRESETS[a.preset])
        else:
            sc = Scenario()
        for kv in a.set:
            k, v = kv.split("=", 1)
            if k not in {f.name for f in fields(Scenario)}:
                raise ValueError(f"unknown shock {k}")
            setattr(sc, k, float(v))
        if a.set and not a.preset and not a.today:
            sc.name = "Custom"
        if a.compare:
            other = company_from_pack(json.loads(Path(a.compare).read_text(encoding="utf-8")))
            res = compare(co, other, sc)
            print(json.dumps(res, indent=1, ensure_ascii=False) if a.json else
                  "\n\n".join([_text(res["a"]), _text(res["b"]), res["summary"] or ""]))
        else:
            r = run(co, sc)
            print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else _text(r))
            if not a.json:
                bp = breaking_points(co)
                fmt = lambda v, u: "not reached" if v is None else f"{v:+,.0f}{u}"  # noqa: E731
                print(f"  Breaking points (each alone): crude {fmt(bp['crude_pct'], '%')} halves EPS · demand "
                      f"{fmt(bp['demand_pct'], '%')} halves EPS · rates {fmt(bp['rate_bp'], ' bp')} take cover under 1.5x")
                print("  " + DISCLAIMER)
        return 0
    except (ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
