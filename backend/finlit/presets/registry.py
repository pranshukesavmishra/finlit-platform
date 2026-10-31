"""The registry of prebuilt screens: every screen defined ONCE, as data (spec p15, "Screen definition: one record per screen, versioned").

Nothing here runs. engine.py reads these records; the API, the nightly job, the cards, the "How this screen works" text and the CSV export are all built from them.
To add or change a screen, edit the record, bump REGISTRY_VERSION (it is part of every cache key) and add a test (docs/PRESETS.md, "How to add a screen").

Record fields (spec names in brackets)
  id, name, group, card_text           what the user sees; names describe, never advise (a test scans every name and card for the banned words)
  prism_filters                        the page's own Prism parameters: zmin (Prism score), zfmin / zvmin / zqmin / zrmin (Fundamentals / Valuation / Quality / Risk
                                       part, "or more"), st / lt (short / long-term technical view score, "or more"), rated=1 (has a Prism score; Provisional
                                       included and badged), status="RATED" (Rated only: the three Top-10 screens), cap = Large | Mid | Small (the site's size buckets)
  ql                                   rules in the Query builder's own language, one condition per line (same parser, same units, same missing-data rule: unknown fails)
  derived                              rules that need a nightly field or a Prism part: (rule, plain-words label), see expr.py for the little language
  rank                                 ((field, "desc" | "asc"), ...): first key, then tie-breaks; a missing value ranks last; "cap:<field>" ranks on the figure held
                                       between its 1st and 99th percentile (spec p16); market cap then symbol decide what is left
  limit                                10 for the Top-10 screens, else 25 (the full count is always reported)
  columns, chips                       the table and the optional chips; a chip changes the rules through `effect` (below)
  how_it_works                         plain-words rule lines
Chip effect keys: prism_set {key: value | None to drop}, ql_add (lines), ql_replace {old line: new line}, derived_add ((rule, label), ...),
  derived_replace {old rule: (rule, label)}, rank (replaces the ranking), sub (a sub-theme to keep; several chips = any of them), small_groups (screen 7)
Kinds: rules (prism_filters + ql + derived), tags (rules among theme-tagged companies), themes (screen 7), quickview (the page's own four views: handled
  by the front-end), blocked (cannot run yet: `blocked_reason` says what data is missing).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Tuple

from .seed import SEED, slug

REGISTRY_VERSION = 1
DISCLAIMER = "A screen narrows a list. It is not a recommendation."
BANNED_WORDS = ("best", "buy", "multibagger", "sell", "top pick", "undervalued gem")   # in names and card text, never (spec p2: names describe, never advise)
LIQUIDITY_FLOOR_CR = 1000   # market cap, until the average-volume data is fixed (spec p2-3)


def _m(**kw) -> Mapping:
    return MappingProxyType(dict(kw))


@dataclass(frozen=True)
class Col:
    key: str
    label: str
    format: str = "text"      # text | num1 | pct | score | cr | label | badge
    align: str = "right"


@dataclass(frozen=True)
class Chip:
    id: str
    label: str
    description: str
    default: bool = False
    effect: Mapping = field(default_factory=lambda: _m())
    how: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    group: str
    card_text: str
    kind: str = "rules"
    prism_filters: Mapping = field(default_factory=lambda: _m())
    ql: str = ""
    derived: Tuple[Tuple[str, str], ...] = ()
    rank: Tuple[Tuple[str, str], ...] = ()
    limit: int = 25
    columns: Tuple[Col, ...] = ()
    chips: Tuple[Chip, ...] = ()
    how_it_works: Tuple[str, ...] = ()
    top10: bool = False
    blocked_reason: Optional[str] = None
    badges: Tuple[str, ...] = ("provisional",)
    spec: str = ""            # where in the spec pdf

    @property
    def status(self) -> str:
        return "blocked" if self.kind == "blocked" else "live"


GROUPS: List[Tuple[str, str]] = [("top-rated", "Top rated"), ("trend", "Trend"), ("growth", "Growth"), ("themes", "Themes"), ("value-income", "Value and income"),
                                 ("safety", "Safety"), ("ownership", "Ownership"), ("prism-basics", "Prism basics")]

# ------------------------------------------------------------------------------------------------------------------------------ columns
RANK = Col("rank", "#", "text", "right")
STOCK = Col("name", "Stock", "text", "left")
PRISM = Col("prism_final", "Prism score", "score")
PLABEL = Col("prism_label", "Prism rating", "label", "left")
PSTATUS = Col("prism_status", "Rating status", "badge", "left")
FUND = Col("prism_fundamental", "Fundamentals", "score")
VAL = Col("prism_valuation", "Valuation", "score")
QUAL = Col("prism_quality", "Quality", "score")
RISK = Col("prism_risk", "Risk", "score")
ST = Col("prism_st", "Short-term view", "label", "left")
LT = Col("prism_lt", "Long-term view", "label", "left")
STS = Col("prism_st_score", "Short-term view score", "score")
LTS = Col("prism_lt_score", "Long-term view score", "score")
R1Y = Col("ret_1y", "1-year return", "pct")
MCAP = Col("market_cap", "Market cap (Rs Cr)", "cr")
SECTOR = Col("sector", "Sector", "text", "left")
INDUSTRY = Col("industry", "Industry", "text", "left")
FINLIT = Col("overall", "FinLit score", "score")


TOP_COLS = (RANK, STOCK, PRISM, PLABEL, FUND, VAL, QUAL, RISK, ST, LT, R1Y, MCAP)
# a Prism-rated stock shows its Rated / Provisional status as a badge on every screen but the Top-10 ones (which are Rated only)
with_status = lambda cols: tuple(cols) + (PSTATUS,)   # noqa: E731

TREND_CHECK = Chip("trend-check", "Trend check", "Keeps only stocks whose long-term technical view is above -20, so top scorers in a downtrend drop out.", False,
                   _m(derived_add=(("prism_lt_score > -20", "Long-term technical view above -20"),)),
                   ("Trend check on: the long-term technical view must be above -20.",))


def _top(n: int, bucket: str, label: str, extra: Mapping = None) -> Preset:
    filters = {"cap": bucket, "rated": 1, "status": "RATED"}
    filters.update(extra or {})
    card = f"The 10 {label} caps with the highest Prism score."
    if bucket == "Small":
        card += " Small caps are ranked among the {n} that Prism has rated so far."
    how = [f"Only {label} caps: companies ranked {'1 to 100' if bucket == 'Large' else '101 to 250' if bucket == 'Mid' else '251 onward'} by market cap, as the site buckets them.",
           "Only companies with a full Prism rating (Provisional ratings are left out of this screen).",
           "At most 2 red flags (a missing red-flag count, as for banks, counts as 0)."]
    if bucket == "Small":
        how.append("Prism Risk part 40 or more.")
    how.append("Ranked by Prism score, highest first; ties go to the higher Quality part, then the higher Risk part. The first 10 are shown.")
    return Preset(f"highest-rated-{label}", f"Highest-rated {label} caps", "top-rated", card, "rules", _m(**filters), "",
                  (("coalesce(flag_count, 0) <= 2", "At most 2 red flags (missing counts as 0)"),),
                  (("prism_final", "desc"), ("prism_quality", "desc"), ("prism_risk", "desc")), 10, TOP_COLS, (TREND_CHECK,), tuple(how), True, None, (), f"p4 (screen {n})")


BEYOND = Chip("beyond-rated", "Beyond rated stocks", "Drops the Prism rule and adds FinLit score 60 or more, market cap Rs 2,000 Cr or more and yearly volatility 60% or less. Off by default: the top of that list is fast-moving small caps.", False,
              _m(prism_set={"zmin": None, "rated": None}, ql_add=("FinLit score >= 60", "Market cap >= 2000", "Volatility (yearly) <= 60")),
              ("Beyond rated stocks: no Prism rule; FinLit score 60 or more, market cap Rs 2,000 Cr or more, yearly volatility 60% or less.",))
RATED_ONLY = Chip("rated-only", "Rated only", "Keeps the names Prism has rated (Provisional ratings included, with their badge).", True, _m(prism_set={"rated": 1}),
                  ("Rated only: the company has a Prism score (Rated or Provisional).",))
FAST = Chip("fast-growers", "Fast growers", "Raises the cut-offs to 20% / 20% / 15% / 15% and ROCE 15%.", False,
            _m(ql_replace={"Sales growth 3 years >= 15": "Sales growth 3 years >= 20", "Profit growth 3 years >= 15": "Profit growth 3 years >= 20",
                           "Sales growth vs same quarter last year >= 10": "Sales growth vs same quarter last year >= 15",
                           "Profit growth vs same quarter last year >= 10": "Profit growth vs same quarter last year >= 15"},
               derived_replace={"is_bank = 1 or roce >= 12": ("is_bank = 1 or roce >= 15", "ROCE 15% or more (banks and lenders exempt)")}),
            ("Fast growers: 3-year sales and profit growth 20% or more, latest-quarter sales and profit growth 15% or more, ROCE 15% or more.",))
SORT_GROWTH = Chip("sort-growth", "Sort by growth", "Reorders the list by 3-year sales growth.", False, _m(rank=(("sales_cagr_3y", "desc"), ("prism_final", "desc"))),
                   ("Sorted by 3-year sales growth, highest first.",))
SMALL_GROUPS = Chip("small-groups", "Include small groups", "Also lists industries with 5 to 7 companies, which are too few to call a theme with the same confidence.", False,
                    _m(small_groups=True), ("Small groups (5 to 7 companies) are included.",))

SUB_CHIPS = tuple(Chip(slug(sub), sub, f"Only companies tagged {sub}. Pick several to see any of them.", False, _m(sub=sub), (f"Sub-theme: {sub}.",)) for sub in SEED)

PRESETS: List[Preset] = [
    _top(1, "Large", "large"),
    _top(2, "Mid", "mid"),
    _top(3, "Small", "small", {"zrmin": 40}),

    Preset("momentum-leaders", "Momentum leaders", "trend", "Rated stocks in an uptrend near their 52-week high, ranked by 3-, 6- and 12-month returns against the market.", "rules",
           _m(zmin=50, rated=1),
           "Price against 50-day average > 0\nPrice against 200-day average > 0\nBelow 52-week high <= 15\n3-month return > 0\n6-month return > 0\n"
           "RSI (14 days) >= 50\nRSI (14 days) <= 80\nMarket cap >= 1000",
           (("vs_ema200 > vs_ema50", "50-day average above the 200-day average"),),
           (("momentum_score", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("momentum_score", "Momentum score", "score"), Col("ret_3m", "3-month return", "pct"), Col("ret_6m", "6-month return", "pct"), R1Y,
                        Col("pct_from_high", "Below 52-week high", "pct"), ST, LT, PRISM, SECTOR)), (BEYOND,),
           ("Rated by Prism with a score of 50 or more.", "Price above both its 50-day and 200-day average, and the 50-day average above the 200-day.",
            "No more than 15% below its 52-week high; 3-month and 6-month returns both positive.", "RSI (14 days) between 50 and 80: rising, not stretched.",
            "Market cap Rs 1,000 Cr or more.",
            "Ranked by the momentum score: 100 x (0.3 x P3M + 0.4 x P6M + 0.3 x P12M), P being the percentile (0 to 1) of that period's return among stocks of Rs 1,000 Cr or more."),
           False, None, ("provisional", "prism_confirmed"), "p5-6 (screen 4)"),

    Preset("consistent-growers", "Consistent growers", "growth", "Sales and profit up at least 15% a year for 3 years and still rising in the latest quarter.", "rules",
           _m(),
           "Sales growth 3 years >= 15\nProfit growth 3 years >= 15\nSales growth vs same quarter last year >= 10\nProfit growth vs same quarter last year >= 10\n"
           "Quarters of rising sales (last 4, year on year) >= 3\nMarket cap >= 1000",
           (("is_bank = 1 or roce >= 12", "ROCE 12% or more (banks and lenders exempt)"), ("is_bank = 1 or debt_to_equity <= 1", "Debt to equity 1 or less (banks and lenders exempt)"),
            ("bankzero(flag_count) <= 1", "At most 1 red flag")),
           (("growth_score", "desc"), ("prism_fundamental", "desc")), 25,
           with_status((STOCK, Col("growth_score", "Growth score", "score"), Col("sales_cagr_3y", "Sales growth, 3 years a year", "pct"), Col("profit_cagr_3y", "Profit growth, 3 years a year", "pct"),
                        Col("q_sales_yoy", "Sales growth, latest quarter", "pct"), Col("q_profit_yoy", "Profit growth, latest quarter", "pct"), Col("roce", "ROCE", "pct"),
                        Col("debt_to_equity", "Debt to equity", "num1"), PRISM, FUND)), (RATED_ONLY, FAST),
           ("Sales and profit both growing 15% a year or more over 3 years.", "Latest quarter: sales up 10% or more and profit up 10% or more on the same quarter last year.",
            "Sales higher than a year earlier in at least 3 of the last 4 quarters.", "ROCE 12% or more and debt to equity 1 or less (banks and lenders are exempt from both).",
            "At most 1 red flag; market cap Rs 1,000 Cr or more.",
            "Ranked by growth score: the average percentile of the four growth numbers, each capped at its 5th and 95th percentile first. Quarter growth is capped at 200% and counts only "
            "when the latest quarter's sales were Rs 50 Cr or more. Ties go to the Prism Fundamentals part."),
           False, None, ("provisional",), "p6-7 (screen 5)"),

    Preset("emerging-tech", "Emerging tech", "themes", "Companies in new-technology businesses (electronics, defence tech, data centres, software products, digital platforms, fintech, EVs, clean energy), still growing sales.",
           "tags", _m(),
           "Market cap >= 1000\nSales growth 3 years >= 15 OR Sales growth vs same quarter last year >= 20",
           (("bankzero(flag_count) <= 2", "At most 2 red flags"),),
           (("has_prism", "desc"), ("prism_final", "desc"), ("overall", "desc")), 25,
           with_status((STOCK, Col("sub_theme", "Sub-theme", "text", "left"), PRISM, FINLIT, Col("sales_cagr_3y", "Sales growth, 3 years a year", "pct"),
                        Col("q_sales_yoy", "Sales growth, latest quarter", "pct"), Col("profit_cagr_3y", "Profit growth, 3 years a year", "pct"), MCAP)),
           (SORT_GROWTH,) + SUB_CHIPS,
           ("Only companies on the research team's theme list (reviewed every quarter, IPOs added as they list); one company can carry several sub-themes.",
            "Market cap Rs 1,000 Cr or more.", "3-year sales growth 15% a year or more, OR sales up 20% or more on the same quarter last year.", "At most 2 red flags.",
            "Loss-making companies stay in (many platforms are), with a Loss-making badge.", "Rated companies first by Prism score, then unrated ones by FinLit score."),
           False, None, ("provisional", "unrated", "loss_making"), "p7-10 (screen 6)"),

    Preset("sector-themes", "Sector themes in play", "themes", "Industries where more stocks are rising than in the market as a whole, and the companies leading them.", "themes",
           _m(), "", (), (("has_prism", "desc"), ("prism_final", "desc"), ("overall", "desc")), 25,
           with_status((STOCK, INDUSTRY, PRISM, FINLIT, Col("ret_3m", "3-month return", "pct"), Col("vs_industry_3m", "3-month return against the industry median (points)", "num1"),
                        Col("vs_ema50", "Price against 50-day average", "pct"), MCAP)), (SMALL_GROUPS,),
           ("Every night each industry is scored on breadth (share of stocks above their 50-day and 200-day averages) and 3-month return against the whole market; stocks of Rs 500 Cr or more.",
            "In play: B50 at least 40% and 15 points above the market's, B200 at or above the market's, and 3-month return (RS3) at least 5 points above the market's.",
            "Emerging: B50 up 20 points or more in 20 sessions, now 10 points above the market, RS3 at or above 0. Fading: was in play in the last 20 sessions, now RS3 below 0 or B50 under 5 points above the market.",
            "Leaders (up to 5 per theme): market cap Rs 1,000 Cr or more, above their 50-day average, 3-month return above the industry median; rated companies first by Prism score, then unrated by FinLit score.",
            "Generic industries (Capital Goods, Financial Services, Services, FMCG, Healthcare, Information Technology) and groups under 8 companies are left out of theme status.",
            "With fewer than 3 industries in play, the 3 with the highest RS3 among those with B50 above the market are shown as Closest to qualifying."),
           False, None, ("provisional",), "p10-12 (screen 7)"),

    Preset("quality-fair-price", "Quality at a fair price", "value-income", "Strong quality and fundamentals without a stretched valuation.", "rules",
           _m(zqmin=70, zfmin=60, zvmin=50), "PEG Ratio > 0\nPEG Ratio <= 1.5", (), (("prism_final", "desc"), ("prism_quality", "desc")), 25,
           with_status((STOCK, PRISM, QUAL, FUND, VAL, Col("peg", "PEG ratio", "num1"), Col("pe", "P/E", "num1"), MCAP)), (),
           ("Prism Quality 70 or more, Fundamentals 60 or more, Valuation 50 or more.", "PEG ratio above 0 and at most 1.5.", "Ranked by Prism score."), False, None, ("provisional",), "p12 (screen 8)"),

    Preset("results-standouts", "Results-season standouts", "growth", "Latest quarter: sales up 20%+, profit up 25%+.", "rules", _m(),
           "Sales growth vs same quarter last year >= 20\nProfit growth vs same quarter last year >= 25\nMarket cap >= 1000",
           (("recent_results = 1", "Reported the latest quarter (the Show only recent results check)"),),
           (("cap:q_profit_yoy", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("q_sales_yoy", "Sales growth, latest quarter", "pct"), Col("q_profit_yoy", "Profit growth, latest quarter", "pct"), Col("q_revenue", "Latest quarter sales (Rs Cr)", "cr"), PRISM, MCAP)), (),
           ("Reported the latest quarter's results (the Show only recent results check).", "Sales up 20% or more on the same quarter last year; profit up 25% or more.",
            "Market cap Rs 1,000 Cr or more.", "Ranked by profit growth, capped at 200% (and at the 1st and 99th percentile) so a tiny base does not top the list."),
           False, None, ("provisional",), "p12 (screen 9)"),

    Preset("near-high-volume", "Near 52-week high on volume", "trend", "Within 5% of the high, volume 1.5x normal, short-term view positive.", "rules",
           _m(rated=1, zmin=50, st=20), "Below 52-week high <= 5\nVolume against 20-day average >= 1.5", (), (("prism_st_score", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, STS, Col("pct_from_high", "Below 52-week high", "pct"), Col("volume_vs_avg", "Volume against 20-day average", "num1"), PRISM, LT, MCAP)), (),
           ("Rated by Prism with a score of 50 or more.", "No more than 5% below the 52-week high.", "Volume at least 1.5 times its 20-day average.", "Short-term technical view +20 or more.",
            "Ranked by the short-term view."), False, None, ("provisional",), "p13 (screen 10)"),

    Preset("quality-off-highs", "Quality off its highs", "value-income", "High quality, 25%+ below the 52-week high.", "rules",
           _m(zqmin=75, zfmin=65, zrmin=50), "Below 52-week high >= 25", (), (("prism_final", "desc"), ("prism_quality", "desc")), 25,
           with_status((STOCK, PRISM, QUAL, FUND, RISK, Col("pct_from_high", "Below 52-week high", "pct"), MCAP)), (),
           ("Prism Quality 75 or more, Fundamentals 65 or more, Risk 50 or more.", "At least 25% below the 52-week high.", "Ranked by Prism score."), False, None, ("provisional",), "p13 (screen 11)"),

    Preset("cheaper-than-history", "Cheaper than its own history", "value-income", "Quality company, P/E 20%+ below its 5-year median.", "rules",
           _m(zqmin=65, zfmin=55), "P/E vs own 5Y median <= -20", (), (("pe_vs_median_5y", "asc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("pe_vs_median_5y", "P/E against own 5-year median", "pct"), Col("pe", "P/E", "num1"), Col("pe_median_5y", "Median P/E (5 years)", "num1"), PRISM, QUAL, FUND, MCAP)), (),
           ("P/E at least 20% below its own 5-year median.", "Prism Quality 65 or more and Fundamentals 55 or more.", "Ranked by P/E against its own median, lowest first."), False, None, ("provisional",), "p13 (screen 12)"),

    Preset("dividend-payers", "Steady dividend payers", "value-income", "Dividend paid 6 years running, yield 2.5%+.", "rules", _m(),
           "Dividend yield >= 2.5\nYears of dividends (last 6) >= 6\nDividend payout <= 75\nMarket cap >= 1000",
           (("bankzero(flag_count) <= 1", "At most 1 red flag"),), (("dividend_yield", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("dividend_yield", "Dividend yield", "pct"), Col("div_years", "Years of dividends (last 6)", "num1"), Col("dividend_payout", "Dividend payout", "pct"), PRISM, MCAP)), (),
           ("Dividend yield 2.5% or more.", "Dividends paid in each of the last 6 years.", "Payout 75% of profit or less.", "At most 1 red flag; market cap Rs 1,000 Cr or more.", "Ranked by dividend yield."),
           False, None, ("provisional",), "p13 (screen 13)"),

    Preset("debt-free-compounders", "Debt-free compounders", "safety", "Almost no debt, ROCE 20%+, rising profit.", "rules", _m(),
           "Debt to equity <= 0.1\nReturn on capital employed >= 20\nSales growth 3 years >= 12\nYears of rising profit (last 5) >= 4\nMarket cap >= 1000", (),
           (("cap:roce", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("roce", "ROCE", "pct"), Col("debt_to_equity", "Debt to equity", "num1"), Col("sales_cagr_3y", "Sales growth, 3 years a year", "pct"),
                        Col("years_profit_up", "Years of rising profit (last 5)", "num1"), PRISM, MCAP)), (),
           ("Debt to equity 0.1 or less.", "ROCE 20% or more.", "Sales growth 12% a year or more over 3 years.", "Profit rose in at least 4 of the last 5 years.", "Market cap Rs 1,000 Cr or more.",
            "Ranked by ROCE (held between its 1st and 99th percentile so one extreme figure does not lead)."), False, None, ("provisional",), "p13 (screen 14)"),

    Preset("institutions-buying", "Institutions buying", "ownership", "FII + DII stake up 1 point or more last quarter.", "rules",
           _m(rated=1, zmin=55),
           "Foreign institutions change (last quarter) + Domestic institutions change (last quarter) >= 1\nPromoter holding change (1 year) >= -1", (),
           (("inst_chg_1q", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("inst_chg_1q", "Foreign + domestic institutions, change last quarter (points)", "num1"), Col("own_fii_chg_1q", "Foreign institutions, change last quarter (points)", "num1"),
                        Col("own_dii_chg_1q", "Domestic institutions, change last quarter (points)", "num1"), Col("own_promoters_chg_1y", "Promoter holding, change in a year (points)", "num1"), PRISM, MCAP)), (),
           ("Rated by Prism with a score of 55 or more.", "Foreign plus domestic institutions' stake up 1 point or more last quarter.", "Promoter stake down no more than 1 point in a year.",
            "Ranked by the change in institutional stake."), False, None, ("provisional",), "p13 (screen 15)"),

    Preset("low-volatility", "Low-volatility names", "safety", "Low risk score and low price swings.", "rules", _m(zrmin=80, zmin=60), "Volatility (yearly) <= 25", (),
           (("prism_risk", "desc"), ("cap:volatility", "asc"), ("prism_final", "desc")), 25,
           with_status((STOCK, RISK, Col("volatility", "Volatility (yearly)", "pct"), PRISM, QUAL, MCAP)), (),
           ("Prism Risk part 80 or more and Prism score 60 or more.", "Yearly volatility 25% or less.", "Ranked by the Prism Risk part."), False, None, ("provisional",), "p14 (screen 16)"),

    Preset("fno-both-positive", "F&O stocks, both views positive", "trend", "F&O stocks with both technical views positive.", "rules", _m(st=20, lt=20), "Has futures & options (F&O) = yes", (),
           (("prism_final", "desc"),), 25, with_status((STOCK, PRISM, STS, LTS, ST, LT, MCAP)), (),
           ("Has futures and options contracts on NSE.", "Short-term and long-term technical views both +20 or more.", "Ranked by Prism score."), False, None, ("provisional",), "p14 (screen 17)"),

    Preset("higher-risk-list", "Higher-risk list", "safety", "Companies with more warning signs than usual. Read the red flags on each company page before acting.", "rules",
           _m(rated=1), "", (("prism_risk < 40 or flag_count >= 3", "Prism Risk below 40, or 3 or more red flags"),),
           (("prism_risk", "asc"), ("flag_count", "desc")), 25,
           with_status((STOCK, RISK, Col("flag_count", "Red flags", "num1"), PRISM, PLABEL, MCAP)), (),
           ("Rated by Prism.", "Prism Risk part below 40, or 3 or more red flags.", "Ranked by the Risk part, lowest first. This is a caution list, not a sell list."), False, None, ("provisional",), "p14 (screen 18)"),

    # ---- not built: the data does not exist yet (spec p14 and p17). Listed so the cards can say so, never computed.
    Preset("rating-upgrades", "Rating upgrades", "top-rated", "Companies whose Prism rating moved up a band, or whose score rose 8 points or more, in the last 30 days.", "blocked",
           blocked_reason="Needs weekly Prism snapshots: the store keeps only the newest rating per company (prism_reports has one row per company and basis), so there is no history to compare. "
                          "Start the weekly snapshots and fill 'Score change since last quarter', then turn this screen on.", spec="p14 and p17"),
    Preset("psu-stocks", "PSU stocks", "ownership", "Public-sector companies with a Prism score of 55 or more, ranked by Prism score.", "blocked",
           blocked_reason="Needs an is_psu flag derived from the shareholding pattern (promoter = central or state government). Government holding never exceeds 49% in the data, because "
                          "government stakes sit under promoters, so the flag cannot be derived yet.", spec="p14 and p17"),
]

# the page's existing four quick views (frontend/src/lib/scoreScreen.ts, PRISM_PRESETS): listed under "Prism basics", handled by the page itself
QUICK_VIEWS: List[Preset] = [
    Preset("strongsafe", "Prism strong and lower risk", "prism-basics", "A Prism score of 80 or more (Strong) and Prism Risk 65 or more (a higher Risk score means lower risk).", "quickview", _m(zmin=80, zrmin=65, rated=1)),
    Preset("fairvalue", "Strong fundamentals at a fair valuation", "prism-basics", "Prism Fundamentals 65 or more and Prism Valuation 50 or more.", "quickview", _m(zfmin=65, zvmin=50, rated=1)),
    Preset("bothtech", "Positive on both technical views", "prism-basics", "Prism's short-term and long-term technical views are both Positive (above the Neutral band).", "quickview", _m()),
    Preset("weakvalue", "Fundamentals strong but valuation weak", "prism-basics", "Prism Fundamentals 65 or more but Prism Valuation 50 or less.", "quickview", _m(zfmin=65, rated=1)),
]

ALL: List[Preset] = PRESETS + QUICK_VIEWS
BY_ID: Dict[str, Preset] = {p.id: p for p in ALL}


def render_card(p: Preset, n: Optional[int] = None) -> str:
    """The card text; `{n}` is how many companies Prism has rated in the bucket (the small-cap sentence), or "those" when not known."""
    if "{n}" not in p.card_text:
        return p.card_text
    return p.card_text.replace("the {n} that", f"the {n} that" if n else "those that")


def group_name(gid: str) -> str:
    return dict(GROUPS)[gid]


def chip_by_id(p: Preset, cid: str) -> Optional[Chip]:
    return next((c for c in p.chips if c.id == cid), None)
