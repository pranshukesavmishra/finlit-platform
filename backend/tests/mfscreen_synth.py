"""A few hundred synthetic funds for the Mutual Fund Screener tests: every table the nightly job reads is filled with seeded random but realistic figures
(month-end NAVs with a drift and a volatility per category, expense ratios by plan, fund sizes, portfolios for most fund houses, AMFI's monthly category report).
The seed is fixed, so the same funds come out every time and the tests can compute the expected answers themselves, in plain Python, from the same arrays."""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from typing import Dict, List, Tuple

from finlit import mf

NAV_DATE = date(2026, 10, 20)
CATS: List[Tuple[str, float, float, int]] = [   # category text, monthly drift, monthly volatility, number of fund families
    ("Equity Scheme - Large Cap Fund", 0.010, 0.040, 12), ("Equity Scheme - Mid Cap Fund", 0.014, 0.055, 12), ("Equity Scheme - Small Cap Fund", 0.016, 0.065, 12),
    ("Equity Scheme - Flexi Cap Fund", 0.012, 0.045, 10), ("Equity Scheme - ELSS", 0.012, 0.050, 8), ("Equity Scheme - Sectoral/Thematic Funds", 0.013, 0.060, 10),
    ("Debt Scheme - Liquid Fund", 0.0055, 0.0008, 10), ("Debt Scheme - Short Duration Fund", 0.0062, 0.004, 10), ("Debt Scheme - Corporate Bond Fund", 0.0066, 0.005, 10),
    ("Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage", 0.009, 0.025, 8), ("Other Scheme - Index Funds", 0.010, 0.040, 10),
    ("Other Scheme - Other ETFs", 0.010, 0.040, 6),
]
HOUSES = ["Alpha Mutual Fund", "Beta Mutual Fund", "Gamma Mutual Fund", "Delta Mutual Fund", "Epsilon Mutual Fund", "Zeta Mutual Fund", "Eta Mutual Fund", "Theta Mutual Fund"]
NO_PORTFOLIO_HOUSES = {"Eta Mutual Fund", "Theta Mutual Fund"}   # houses with no parsed portfolio file: their funds must show as "no data", never as zero
THEMES = ["Defence", "Pharma", "Banking and Financial Services", "Infrastructure", "Technology", "Consumption", "Energy", "Quality"]
INDEXES = ["Nifty 50", "Sensex", "Nifty Next 50", "Nifty 500", "Nifty Midcap 150", "Nifty 100"]
SECTORS = ["Banks", "IT - Software", "Pharmaceuticals", "Automobiles", "Aerospace & Defense", "Power", "Consumer Durables"]
EXIT_TEXTS = ["Nil", "1% if redeemed within 1 year", "0.25% if redeemed within 7 days", "1% for redemption within 30 days", "0.5% if redeemed within 15 days", "see the scheme document", None]


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def month_end(y: int, m: int) -> date:
    return date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)


class Fund:
    """The truth about one synthetic fund family, kept in Python so tests can recompute any filter by brute force."""
    def __init__(self, fid: int, cat: str, house: str, name: str, mu: float, sd: float, rng: random.Random):
        self.fid, self.cat, self.house, self.name = fid, cat, house, name
        self.family = f"{house}|{name}".lower()
        start_months = rng.choice([64, 64, 64, 50, 40, 30, 20, 14])   # a few young funds: they have no 5-year (some no 3-year) figure
        self.navs: Dict[Tuple[int, int], float] = {}
        v = 10.0
        y, m = 2026, 10
        keys = []
        for _ in range(start_months):
            keys.append((y, m))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        for (y, m) in reversed(keys):
            v *= max(0.2, 1 + rng.gauss(mu, sd))
            self.navs[(y, m)] = round(v, 4)
        self.launch = month_end(*min(self.navs)) - timedelta(days=rng.randint(0, 20))
        self.aum_lakh = rng.choice([None] + [10 ** rng.uniform(3.5, 6.3) for _ in range(12)])
        self.ter_reg = round(rng.uniform(0.3, 2.4), 2) if mu > 0.007 else round(rng.uniform(0.15, 1.0), 2)
        self.ter_dir = round(self.ter_reg * rng.uniform(0.35, 0.75), 2)
        self.has_ter = rng.random() > 0.15
        self.exit_text = rng.choice(EXIT_TEXTS)
        self.codes: Dict[str, int] = {}


def build(seed: int = 7) -> List[Fund]:
    rng = random.Random(seed)
    funds: List[Fund] = []
    fid = 0
    for cat, mu, sd, n in CATS:
        for i in range(n):
            house = HOUSES[(fid + i) % len(HOUSES)]
            if "Sectoral" in cat:
                nm = f"{THEMES[i % len(THEMES)]} Fund"
            elif "Index" in cat:
                nm = f"{INDEXES[i % len(INDEXES)]} Index Fund"
            elif "ETFs" in cat:
                nm = f"{INDEXES[i % len(INDEXES)]} ETF"
            else:
                nm = cat.split(" - ")[1].replace("Funds", "Fund").replace("Fund", "").strip() + f" Fund {i + 1}"
            funds.append(Fund(fid, cat, house, f"{house.replace(' Mutual Fund', '')} {nm} S{fid}", mu, sd, rng))
            fid += 1
    return funds


def reliance_fund(funds: List[Fund]) -> Fund:
    """The fund family whose first equity holding the tests call RELIANCE (a family of a house that has a portfolio file)."""
    return next(f for f in funds if f.house not in NO_PORTFOLIO_HOUSES and "Debt" not in f.cat)


def series(f: Fund) -> Tuple[List[date], List[float]]:
    """The stored month-end series: the last NAV day of each month, the current month at its latest NAV date."""
    keys = sorted(f.navs)
    days = [NAV_DATE if k == (2026, 10) else month_end(*k) for k in keys]
    return days, [f.navs[k] for k in keys]


def cagr(f: Fund, years: int) -> float | None:
    start = (2026 - years, 10)
    if start not in f.navs:
        return None
    return ((f.navs[(2026, 10)] / f.navs[start]) ** (1 / years) - 1) * 100


async def seed(store, funds: List[Fund]) -> None:
    """Fill mf_schemes, mf_monthly, mf_facts, mf_ter, the portfolio and exit-load disclosures, the industry report and the ETF list."""
    async with store.pool.acquire() as conn:
        await conn.execute("TRUNCATE mf_history, mf_backfill, mf_meta, mf_schemes, mf_facts, mf_ter, mf_screen_hold, mf_cat_flow, mf_industry, mf_industry_months, mf_hot, "
                           "disclosure_portfolios, disclosure_facts, disclosure_isin, etf_funds CASCADE")
        code = 100000
        for f in funds:
            for plan, opt, lab in (("Direct", "Growth", "Growth"), ("Regular", "Growth", "Growth"), ("Direct", "IDCW", "IDCW Payout")):
                code += 1
                f.codes[f"{plan}|{opt}"] = code
                days, navs = series(f)
                r1, r3, r5 = (cagr(f, 1), cagr(f, 3), cagr(f, 5)) if opt == "Growth" else (None, None, None)
                dm = [d.toordinal() for d in days]
                sip3, sip5, fall = (mf.dashboard_figures(dm, navs, NAV_DATE.toordinal(), navs[-1]) if opt == "Growth" else (None, None, None))
                isin = f"INF{code:09d}"[:12]
                await conn.execute(
                    """INSERT INTO mf_schemes (code, name, isin, amc, scheme_type, category, plan, option_class, option_label, family, nav, nav_date, prev_nav, prev_date, active, has_hist,
                                               r1y, r3y, r5y, sip3y, sip5y, mdd3y_m, metrics_date)
                       VALUES ($1,$2,$3,$4,'Open Ended',$5,$6,$7,$8,$9,$10,$11,$12,$13,true,true,$14,$15,$16,$17,$18,$19,$11)""",
                    code, f"{f.name} - {plan} Plan - {lab}", isin, f.house, f.cat, plan, opt, lab, f.family, navs[-1], NAV_DATE, navs[-1] * 0.999, NAV_DATE - timedelta(days=1),
                    r1, r3, r5, sip3, sip5, fall)
                if opt == "Growth":
                    await conn.execute("INSERT INTO mf_monthly (code, days, navs) VALUES ($1, $2, $3)", code, days, navs)
                await conn.execute("INSERT INTO mf_facts (code, base_name, name_key, launch_date, aum_lakh, aum_end, aum_label) VALUES ($1,$2,$3,$4,$5,$6,'July - September 2026')",
                                   code, f.name, f.family.replace(" ", "").replace("|", ""), f.launch, f.aum_lakh / 3 if f.aum_lakh else None, date(2026, 9, 30) if f.aum_lakh else None)
            if f.has_ter:
                await conn.execute("INSERT INTO mf_ter (name_key, name, category, ter_regular, ter_direct, ter_date) VALUES ($1,$2,$3,$4,$5,'2026-10-19') ON CONFLICT DO NOTHING",
                                   f.family.replace(" ", "").replace("|", ""), f.name, f.cat, f.ter_reg, f.ter_dir)
            if "ETFs" in f.cat:
                await conn.execute("INSERT INTO etf_funds (symbol, isin, instrument_key, exchange_name, display_name, category) VALUES ($1,$2,$3,$4,$5,'other') ON CONFLICT DO NOTHING",
                                   f"ETF{f.fid}", f"INF{f.codes['Direct|Growth']:09d}"[:12], f"NSE_EQ|{f.fid}", f.name, f.name)
            if f.exit_text is not None:
                await conn.execute("INSERT INTO disclosure_facts (fkey, kind, as_of, value, source) VALUES ($1,'exitload','2026-09-30',$2::jsonb,'test')", f.family, json.dumps({"text": f.exit_text}))
            if f.house not in NO_PORTFOLIO_HOUSES:
                rng = random.Random(f.fid)
                sector = rng.choice(SECTORS)
                eq = 0 if "Debt" in f.cat else (rng.uniform(60, 98) if "Hybrid" not in f.cat else rng.uniform(30, 70))
                rows = []
                left = eq
                for k in range(rng.randint(12, 45)):
                    p = round(left * rng.uniform(0.04, 0.2), 2) if k < 30 else round(left * 0.3, 2)
                    left -= p
                    rows.append([f"Stock {k}", f"INE{(f.fid * 100 + k):09d}"[:12], sector if k % 2 == 0 else rng.choice(SECTORS), "e", p, 100, 1000])
                debt = 100 - eq - 2
                rows.append(["Bond A", f"INE9{f.fid:08d}"[:12], None, "d", round(debt, 2), 10, 100])
                rows.append(["Cash", None, None, "c", 2.0, None, None])
                for as_of, scale in (("2026-09-30", 1.0), ("2026-08-31", 0.97), ("2026-07-31", 0.93)):
                    await conn.execute("""INSERT INTO disclosure_portfolios (fkey, as_of, amc, scheme_name, source, source_url, net_assets_lakh, pct_total, n, holdings)
                                          VALUES ($1,$2,$3,$4,'test','http://x',$5,100,$6,$7::jsonb)""",
                                       f.family, date.fromisoformat(as_of), f.house, f.name, (f.aum_lakh or 50000.0) * scale, len(rows), json.dumps(rows))
        holder = reliance_fund(funds)
        for sym, n in (("RELIANCE", 0), ("HDFCBANK", 1)):
            await conn.execute("INSERT INTO disclosure_isin (isin, symbol) VALUES ($1, $2)", f"INE{holder.fid * 100 + n:09d}"[:12], sym)
        # AMFI's monthly category report: 14 months of the categories above
        groups = {"Equity Scheme": "equity", "Debt Scheme": "debt", "Hybrid Scheme": "hybrid", "Other Scheme": "other"}
        rng = random.Random(3)
        for i in range(14):
            y, m = divmod(2025 * 12 + 8 + i, 12)
            month = date(y, m + 1, 1)
            tot_aum, tot_net = 0.0, 0.0
            for pos, (cat, mu, sd, n) in enumerate(CATS):
                head, label = cat.split(" - ")
                label = {"Sectoral/Thematic Funds": "Sectoral/Thematic Funds", "ELSS": "ELSS", "Index Funds": "Index Funds", "Other ETFs": "Other ETFs"}.get(label, label)
                aum = 5000 * (1 + pos) * (1 + 0.02 * i) * (1 + 0.1 * (pos % 3))
                net = (aum * 0.01 * rng.uniform(-1, 3)) if pos % 4 else -aum * 0.01 * rng.uniform(0.1, 1)
                tot_aum += aum
                tot_net += net
                await conn.execute("""INSERT INTO mf_industry (month, key, pos, section, heading, category, grp, schemes, folios, mobilized, redemption, net_flow, aum, aaum)
                                      VALUES ($1,$2,$3,'A','x',$4,$5,10,$6,$7,$8,$9,$10,$10)""", month, f"k{pos}", pos, label, groups[head], 1_000_000 + 1000 * i * (pos + 1),
                                   max(net, 0), max(-net, 0), net, aum)
            await conn.execute("INSERT INTO mf_industry_months (month, status, aum, net_flow) VALUES ($1,'ok',$2,$3)", month, tot_aum, tot_net)
        await conn.execute("INSERT INTO mf_meta (key, value) VALUES ('refresh', $1::jsonb)", json.dumps({"navDate": NAV_DATE.isoformat(), "at": "2026-10-20T16:00:00+00:00"}))
    await mf.derive_dashboard(store)
