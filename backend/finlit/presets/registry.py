"""The registry of prebuilt screens: every screen defined ONCE, as data (spec p15, "Screen definition: one record per screen, versioned").

Nothing here runs. engine.py reads these records; the API, the nightly job, the cards, the "How this screen works" text and the CSV export are all built from them.
To add or change a screen, edit the record, bump REGISTRY_VERSION (it is part of every cache key) and add a test (docs/PRESETS.md, "How to add a screen").

Record fields (spec names in brackets)
  id, name, group, card_text           what the user sees; names describe, never advise (a test scans every name and card for the banned words)
  prism_filters                        the page's own Prism parameters: zmin (Prism score), zfmin / zvmin / zqmin / zrmin (Growth & Profitability / Valuation / Quality / Risk
                                       part, "or more"), zvbelow (Valuation strictly BELOW the number: with zvmin=50 on its twin it makes a clean split, nobody falls between), st / lt (short / long-term technical view score, "or more"), rated=1 (has a Prism score; Provisional
                                       included and badged), status="RATED" (Rated only: the three Top-10 screens), cap = Large | Mid | Small (the site's size buckets)
  ql                                   rules in the Query builder's own language, one condition per line (same parser, same units, same missing-data rule: unknown fails)
  derived                              rules that need a nightly field or a Prism part: (rule, plain-words label), see expr.py for the little language
  rank                                 ((field, "desc" | "asc"), ...): first key, then tie-breaks; a missing value ranks last; "cap:<field>" ranks on the figure held
                                       between its 1st and 99th percentile (spec p16); market cap then symbol decide what is left
  limit                                10 for the Top-10 screens, else 25 (the full count is always reported). A screen of 25 pages: the API serves the rest 25 at a time
                                       (?offset=25), up to EXPORT_MAX rows; the Top-10 screens never page
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

from .seed import slug
from .theme_map import SUBTHEMES as THEME_SUBS

REGISTRY_VERSION = 6      # 6: caps, tags and sector themes read the Sector LABEL (not the macro sector or the Industry); the two valuation views split at 50; the screens page by 25
DISCLAIMER = "A screen narrows a list. It is not a recommendation."
BANNED_WORDS = ("best", "buy", "multibagger", "sell", "top pick", "undervalued gem")   # in names and card text, never (spec p2: names describe, never advise)
RUN_GUARD = ("coalesce(ret_1y, 0) <= 300", "1-year return no more than 300%")   # a stock that has run far past that is not a steady leader: kept out of the Top 10 and momentum lists
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
    tab: str = "advanced"     # advanced (Gold: Prism fields) | basic (Silver: FinLit score fields)
    # a weighted rank score (redesign pdf, "Top 10"): ((field, weight), ...). Each input is turned into its percentile among the company's own size bucket
    # (the bucket's Prism-rated companies on the Advanced tab; the bucket's companies of Rs 1,000 Cr or more on the Basic tab); the score is 100 x the weighted sum.
    rank_score: Tuple[Tuple[str, float], ...] = ()
    sector_cap: int = 0       # at most this many companies from one Sector label in the list (0 = no cap)
    fill: Tuple[str, ...] = ()   # rule labels a company may fail and still fill a short list (badged "Trend not confirmed")
    list_text: str = ""       # what the card says about its list when it shows fewer than all that pass, e.g. "Top 10"

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
FUND = Col("prism_fundamental", "Growth & Profitability", "score")
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
FINLIT = Col("overall", "FinLit IQ", "score")


R3M = Col("ret_3m", "3-month return", "pct")
R6M = Col("ret_6m", "6-month return", "pct")
W52 = Col("pct_from_high", "Below 52-week high", "pct")
RSC = Col("rank_score", "Rank score", "score")
SUBT = Col("sub_theme", "Sub-theme", "text", "left")
TOP_COLS = (RANK, STOCK, SECTOR, PRISM, PLABEL, FUND, VAL, QUAL, RISK, STS, LTS, R3M, R6M, R1Y, W52, MCAP, RSC)
# a Prism-rated stock shows its Rated / Provisional status as a badge on every screen but the Top-10 ones (which are Rated only)
with_status = lambda cols: tuple(cols) + (PSTATUS,)   # noqa: E731
VIEWS = (STS, LTS)

PROVISIONAL = Chip("include-provisional", "Include provisional", "Also lists companies with a Provisional Prism rating (a rating built on limited history), each with its badge.", False,
                   _m(prism_set={"status": None}), ("Provisional ratings are included, with a Provisional badge.",))
TURNING_UP = Chip("turning-up", "Turning up", "Keeps only names whose short-term technical view is 0 or more: the price has stopped falling.", False,
                  _m(derived_add=(("prism_st_score >= 0", "Short-term technical view 0 or more"),)), ("Turning up: the short-term technical view must be 0 or more.",))
ALL_CAPS = Chip("all-caps", "All caps", "Also lists small caps (the default is large and mid caps).", False, _m(derived_drop=("is_large_mid = 1",)), ("All caps: small caps are included.",))
FAST_G = Chip("fast-growers", "Fast growers", "Raises the Growth & Profitability cut-off from 75 to 85.", False, _m(prism_set={"zfmin": 85}), ("Fast growers: Prism Growth & Profitability 85 or more.",))
SHOW_ALL_THEME = Chip("show-all-theme", "Show all theme members", "Drops the Growth & Profitability and Risk gates: every theme member of Rs 1,000 Cr or more is listed.", False,
                      _m(derived_drop=("has_prism = 0 or (prism_fundamental >= 50 and prism_risk >= 40)",)), ("Every theme member of Rs 1,000 Cr or more is listed, whatever its Growth & Profitability and Risk.",))
SMALL_GROUPS = Chip("small-groups", "Include small groups", "Also lists sectors with 5 to 7 companies, which are too few to call a theme with the same confidence.", False,
                    _m(small_groups=True), ("Small groups (5 to 7 companies) are included.",))
SUB_CHIPS = tuple(Chip(slug(sub), sub, f"Only companies in {sub}. Pick several to see any of them.", False, _m(sub=sub), (f"Sub-theme: {sub}.",)) for sub in THEME_SUBS)

TOP_RANK = (("prism_final", 0.40), ("prism_valuation", 0.075), ("prism_risk", 0.075), ("prism_lt_score", 0.15), ("prism_st_score", 0.05), ("momentum_score", 0.15), ("w52_score", 0.10))
TOP_ORDER = (("rank_score", "desc"), ("prism_quality", "desc"), ("prism_final", "desc"))


def _top(n: int, bucket: str, label: str) -> Preset:
    risk = 60 if bucket == "Small" else 50
    filters = {"cap": bucket, "rated": 1, "status": "RATED", "zmin": 60, "zqmin": 50, "zrmin": risk}
    how = [f"Only {label} caps: companies ranked {'1 to 100' if bucket == 'Large' else '101 to 250' if bucket == 'Mid' else '251 onward'} by market cap, as the site buckets them.",
           "Only companies with a full Prism rating (Provisional ratings appear only with the Include provisional chip, with their badge).",
           f"Gates: Prism score 60 or more, Quality 50 or more, Risk {risk} or more, long-term technical view above -20, no more than 30% below the 52-week high, and a 1-year return of 300% or less.",
           "Ranked by a weighted score, 55% business and 45% price. Each input is the company's percentile among the rated companies of its size group: Prism score 40%, Valuation 7.5%, Risk 7.5%, "
           "long-term view 15%, short-term view 5%, momentum 15% (the momentum score of the Momentum leaders screen), and 52-week position 10% (100 minus the % below the high).",
           "At most 3 companies from one Sector label. Ties go to the higher Quality, then the higher Prism score.",
           "If fewer than 10 pass, the list is filled with the next names that fail only the trend or the 52-week gate, badged Trend not confirmed."]
    return Preset(f"highest-rated-{label}", f"Highest-rated {label} caps", "top-rated", f"The 10 {label} caps with the strongest mix of Prism rating, valuation, risk and price strength.", "rules",
                  _m(**filters), "Below 52-week high <= 30", (("prism_lt_score > -20", "Long-term technical view above -20"), RUN_GUARD), TOP_ORDER, 10, TOP_COLS, (PROVISIONAL,), tuple(how), True, None, ("provisional",),
                  f"p4 (Top 10, {label})", "advanced", TOP_RANK, 3, ("technical view", "52-week high"))


LT_ST_COLS = (STS, LTS)

PRESETS: List[Preset] = [
    _top(1, "Large", "large"),
    _top(2, "Mid", "mid"),
    _top(3, "Small", "small"),

    Preset("momentum-leaders", "Momentum leaders", "trend", "Rated stocks in an uptrend near their 52-week high, ranked by 3-, 6- and 12-month returns against the market.", "rules",
           _m(zmin=50, rated=1, lt=20),
           "Below 52-week high <= 15\n3-month return > 0\n6-month return > 0\nMarket cap >= 1000",
           (("prism_st_score >= 0", "Short-term technical view 0 or more"), RUN_GUARD),
           (("momentum_score", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, Col("momentum_score", "Momentum score", "score"), R3M, R6M, R1Y, W52, STS, LTS, PRISM, SECTOR, MCAP)), (),
           ("Rated by Prism with a score of 50 or more.", "Long-term technical view +20 or more (price above its long-term average) and short-term view 0 or more (not stretched down).",
            "No more than 15% below its 52-week high; 3-month and 6-month returns both positive; 1-year return 300% or less; market cap Rs 1,000 Cr or more.",
            "Ranked by the momentum score: 100 x (0.3 x P3M + 0.4 x P6M + 0.3 x P12M), P being the percentile (0 to 1) of that period's return among stocks of Rs 1,000 Cr or more."),
           False, None, ("provisional",), "p10 (Momentum leaders)"),

    Preset("at-52-week-high", "At a 52-week high", "trend", "Within 5% of the 52-week high with a positive short-term view.", "rules",
           _m(rated=1, zmin=50, st=20), "Below 52-week high <= 5", (), (("prism_st_score", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, STS, LTS, W52, R3M, R6M, PRISM, SECTOR, MCAP)), (),
           ("Rated by Prism with a score of 50 or more.", "No more than 5% below the 52-week high.", "Short-term technical view +20 or more.", "Ranked by the short-term view."),
           False, None, ("provisional",), "p10 (At a 52-week high)"),

    Preset("both-views-positive", "Positive on both technical views", "trend", "Large and mid caps whose short-term and long-term technical views are both positive.", "rules",
           _m(rated=1, st=20, lt=20), "", (("is_large_mid = 1", "Large or mid cap"),), (("prism_final", "desc"),), 25,
           with_status((STOCK, PRISM, STS, LTS, ST, LT, R6M, W52, SECTOR, MCAP)), (ALL_CAPS,),
           ("Rated by Prism.", "Short-term and long-term technical views both +20 or more.", "Large and mid caps by default; the All caps chip adds small caps.", "Ranked by Prism score."),
           False, None, ("provisional",), "p10 (merged with F&O stocks)"),

    Preset("consistent-growers", "Consistent growers", "growth", "Companies with strong Growth & Profitability, quality and risk scores together.", "rules",
           _m(rated=1, zfmin=75, zqmin=60, zrmin=50), "", (), (("prism_fundamental", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, FUND, QUAL, RISK, PRISM, STS, LTS, R6M, SECTOR, MCAP)), (FAST_G,),
           ("Prism Growth & Profitability 75 or more, Quality 60 or more, Risk 50 or more.", "Ranked by Growth & Profitability. The Fast growers chip raises the cut-off to 85."),
           False, None, ("provisional",), "p11 (Consistent growers)"),

    Preset("emerging-tech", "Emerging tech", "themes", "Companies in new-technology businesses (electronics, defence and shipbuilding, software and data, digital platforms, fintech, EVs, clean energy), still growing.",
           "tags", _m(), "Market cap >= 1000",
           (("has_prism = 0 or (prism_fundamental >= 50 and prism_risk >= 40)", "Rated: Growth & Profitability 50 or more and Risk 40 or more"),),
           (("has_prism", "desc"), ("rank_score", "desc")), 25,
           with_status((STOCK, SUBT, PRISM, FUND, RISK, STS, LTS, R6M, W52, SECTOR, MCAP)), (SHOW_ALL_THEME,) + SUB_CHIPS,
           ("Companies in a sub-theme: every company whose Sector label belongs to it (for example Aerospace & Defense, Ship Building, Explosives, Consumer Electronics, E-Retail, Exchange and Data Platform) joined with a short named list that the research team reviews every quarter. The sub-theme is shown as a column.",
            "Market cap Rs 1,000 Cr or more.", "Rated or Provisional by Prism: Growth & Profitability 50 or more (still growing) and Risk 40 or more. No trend gate: the two technical views are shown as columns.",
            "Ranked by the same weighted score as the Top 10 lists. Companies Prism has not rated yet are listed below, by market cap, with no score."),
           False, None, ("provisional", "unrated"), "p6-9 (Emerging tech)", "advanced", TOP_RANK),

    Preset("sector-themes", "Sector themes in play", "themes", "Sectors where more stocks sit near their 52-week high than in the market as a whole, and the companies leading them.", "themes",
           _m(), "", (), (("has_prism", "desc"), ("prism_final", "desc"), ("overall", "desc")), 25,
           with_status((STOCK, SECTOR, PRISM, STS, LTS, R3M, Col("vs_industry_3m", "3-month return against the sector median (points)", "num1"), W52, MCAP)), (SMALL_GROUPS,),
           ("Every night each sector (by its Sector label) is scored on breadth, the share of its stocks within 15% of their 52-week high, and its median 3-month return against the whole market; stocks of Rs 1,000 Cr or more.",
            "In play: breadth at least 40% and 15 points above the market's, and median 3-month return at least 5 points above the market's.",
            "Leaders (up to 5 per sector): market cap Rs 1,000 Cr or more, within 15% of their 52-week high, 3-month return above the sector median; rated companies first by Prism score, then unrated by FinLit IQ.",
            "Generic labels (Capital Goods, Financial Services, Services, FMCG, Healthcare, Information Technology) and groups under 8 companies are left out of theme status.",
            "With fewer than 3 sectors in play, the 3 with the highest relative 3-month return among those with breadth above the market are shown as Closest to qualifying."),
           False, None, ("provisional",), "p12 (Sector themes in play)"),

    Preset("quality-fair-price", "Quality at a fair price", "value-income", "Strong quality and growth & profitability without a stretched valuation.", "rules",
           _m(rated=1, zqmin=70, zfmin=60, zvmin=60), "", (), (("prism_final", "desc"), ("prism_quality", "desc")), 25,
           with_status((STOCK, PRISM, QUAL, FUND, VAL, RISK, STS, LTS, R6M, SECTOR, MCAP)), (),
           ("Prism Quality 70 or more, Growth & Profitability 60 or more, Valuation 60 or more.", "Ranked by Prism score."), False, None, ("provisional",), "p12 (Quality at a fair price)"),

    Preset("quality-off-highs", "Quality off its highs", "value-income", "High quality, 25%+ below the 52-week high.", "rules",
           _m(rated=1, zqmin=75, zfmin=65, zrmin=50), "Below 52-week high >= 25", (), (("prism_final", "desc"), ("prism_quality", "desc")), 25,
           with_status((STOCK, PRISM, QUAL, FUND, RISK, STS, LTS, W52, R6M, SECTOR, MCAP)), (TURNING_UP,),
           ("Prism Quality 75 or more, Growth & Profitability 65 or more, Risk 50 or more.", "At least 25% below the 52-week high.", "Both technical views are shown; the Turning up chip keeps names whose short-term view is 0 or more.", "Ranked by Prism score."),
           False, None, ("provisional",), "p12 (Quality off its highs)"),

    Preset("value-with-quality", "Value with quality", "value-income", "Cheaper-valued companies that also score well on quality, risk and growth & profitability.", "rules",
           _m(rated=1, zvmin=75, zqmin=60, zrmin=60, zfmin=50), "", (), (("prism_valuation", "desc"), ("prism_final", "desc")), 25,
           with_status((STOCK, VAL, QUAL, RISK, FUND, PRISM, STS, LTS, R6M, SECTOR, MCAP)), (),
           ("Prism Valuation 75 or more, Quality 60 or more, Risk 60 or more, Growth & Profitability 50 or more.", "Ranked by Valuation, highest first (a higher Valuation score means cheaper)."),
           False, None, ("provisional",), "p13 (Value with quality)"),

    Preset("low-risk-compounders", "Low-risk compounders", "safety", "Companies that score high on risk, quality and growth & profitability together.", "rules",
           _m(rated=1, zrmin=80, zqmin=75, zfmin=65), "", (), (("prism_final", "desc"),), 25,
           with_status((STOCK, PRISM, RISK, QUAL, FUND, STS, LTS, R6M, SECTOR, MCAP)), (),
           ("Prism Risk 80 or more (a higher Risk score means lower risk), Quality 75 or more, Growth & Profitability 65 or more.", "Ranked by Prism score."),
           False, None, ("provisional",), "p13 (Low-risk compounders)"),

    Preset("low-volatility", "Low-volatility names", "safety", "Low risk score and a narrow 52-week range.", "rules", _m(rated=1, zrmin=80, zmin=60), "", (("high_over_low <= 35", "52-week high no more than 35% above the 52-week low"),),
           (("prism_risk", "desc"), ("prism_final", "desc")), 25, with_status((STOCK, RISK, Col("high_over_low", "52-week high above the low", "pct"), PRISM, QUAL, STS, LTS, R6M, SECTOR, MCAP)), (),
           ("Prism Risk 80 or more and Prism score 60 or more.", "The 52-week high is no more than 35% above the 52-week low.", "Ranked by the Prism Risk part."), False, None, ("provisional",), "p13 (Low-volatility names)"),

    Preset("higher-risk-list", "Higher-risk list", "safety", "Companies with more warning signs than usual. Read the company page before acting.", "rules",
           _m(rated=1), "", (("prism_risk < 40 or prism_final < 35 or (pct_from_high >= 40 and prism_lt_score <= -50)", "Risk below 40, or Prism below 35, or 40% or more below the high with a long-term view of -50 or lower"),),
           (("prism_risk", "asc"), ("prism_final", "asc")), 25, with_status((STOCK, RISK, PRISM, PLABEL, W52, LTS, R6M, SECTOR, MCAP)), (),
           ("Rated by Prism.", "Prism Risk below 40, or Prism score below 35, or 40% or more below the 52-week high with a long-term technical view of -50 or lower.", "Ranked by the Risk part, lowest first. This is a caution list, not a recommendation."),
           False, None, ("provisional",), "p14 (Higher-risk list)"),

    # ---- not built: the data does not exist yet. Listed so the cards can say so in plain words, never computed.
    Preset("rating-upgrades", "Rating upgrades", "top-rated", "Companies whose Prism rating moved up a band, or whose score rose 8 points or more, in the last 30 days.", "blocked",
           blocked_reason="Needs rating history; coming once weekly rating snapshots start.", spec="p9"),
    Preset("psu-stocks", "PSU stocks", "ownership", "Public-sector companies with a Prism score of 55 or more, ranked by Prism score.", "blocked",
           blocked_reason="Needs a maintained list of public-sector companies; coming once that list is shown as a column.", spec="p14"),
]

# the page's existing four quick views (frontend/src/lib/scoreScreen.ts, PRISM_PRESETS): listed under "Prism basics", handled by the page itself
QUICK_VIEWS: List[Preset] = [
    Preset("strongsafe", "Prism strong and lower risk", "prism-basics", "A Prism score of 80 or more (Strong) and Prism Risk 65 or more (a higher Risk score means lower risk).", "quickview", _m(zmin=80, zrmin=65, rated=1)),
    Preset("fairvalue", "Strong Growth & Profitability at a fair valuation", "prism-basics", "Prism Growth & Profitability 65 or more and Prism Valuation 50 or more.", "quickview", _m(zfmin=65, zvmin=50, rated=1)),
    Preset("weakvalue", "Growth & Profitability strong but valuation weak", "prism-basics", "Prism Growth & Profitability 65 or more but Prism Valuation below 50.", "quickview", _m(zfmin=65, zvbelow=50, rated=1)),
]


# ------------------------------------------------------------------------------------------------------------------------------ the Basic tab (Silver)
# Built only from what the Basic score screener shows: the FinLit IQ, its pillars (Quality, Growth, Profitability, Balance sheet, Technical), the Growth & Profitability
# score (the average of the four business pillars, needs 3 of 4), market cap, Sector, 52-week and return fields. Every rule is a "derived" rule with a plain-words label.
BASIC_GROUP = {"top": "top-rated", "trend": "trend", "growth": "growth", "themes": "themes", "value": "value-income", "safety": "safety"}
B_FUND = Col("fundamental_score", "Growth & Profitability score", "score")
B_TECH = Col("pillar_technical", "Technical", "score")
B_QUAL = Col("pillar_quality", "Quality", "score")
B_GROW = Col("pillar_growth", "Growth", "score")
B_PROF = Col("pillar_profitability", "Profitability", "score")
B_BAL = Col("pillar_balance", "Balance sheet", "score")
B_MOM = Col("momentum_score", "Momentum score", "score")
B_PB = Col("profit_plus_balance", "Profitability + Balance sheet", "score")
B_BASE = (RANK, STOCK, FINLIT, B_FUND, B_TECH)
B_TAIL = (R3M, R6M, R1Y, W52, SECTOR, MCAP)
B_RANK_SCORE = (("fundamental_score", 0.50), ("pillar_technical", 0.20), ("momentum_score", 0.15), ("w52_score", 0.10), ("pillar_quality", 0.05))
B_TOP_ORDER = (("rank_score", "desc"), ("fundamental_score", "desc"), ("overall", "desc"))
MC1000 = ("market_cap >= 1000", "Market cap Rs 1,000 Cr or more")
MC2000 = ("market_cap >= 2000", "Market cap Rs 2,000 Cr or more")
B_NOTE = "A company with a blank score drops out of any rule that uses that score."


def _bal(minimum: int, blank: str = "any") -> Tuple[str, str]:
    """Balance sheet at `minimum` or more; a blank is allowed (blank = any company) or only for banks (blank = bank)."""
    if blank == "bank":
        return (f"pillar_balance >= {minimum} or (coalesce(pillar_balance, -1) = -1 and is_bank = 1)", f"Balance sheet {minimum} or more (blank allowed for banks)")
    return (f"coalesce(pillar_balance, 100) >= {minimum}", f"Balance sheet {minimum} or more (blank allowed)")


def _bt(bucket: str, label: str) -> Preset:
    small = bucket == "Small"
    rules = (("fundamental_score >= 65", "Growth & Profitability score 65 or more"), ("pillar_technical >= 45", "Technical 45 or more"), ("pillar_quality >= 50", "Quality 50 or more"),
             _bal(55 if small else 45, "bank"), ("pct_from_high <= 30", "No more than 30% below the 52-week high"), RUN_GUARD, MC1000)
    how = (f"Only {label} caps: companies ranked {'1 to 100' if bucket == 'Large' else '101 to 250' if bucket == 'Mid' else '251 onward'} by market cap, as the site buckets them.",
           "Market cap Rs 1,000 Cr or more" + (": thinly traded micro caps are left out." if small else "."),
           f"Gates: Growth & Profitability score 65 or more, Technical 45 or more, Quality 50 or more, Balance sheet {55 if small else 45} or more (a blank is allowed for banks), "
           "no more than 30% below the 52-week high, and a 1-year return of 300% or less.",
           "Ranked by a weighted score: each input is the company's percentile among the companies of its size group with a market cap of Rs 1,000 Cr or more: Growth & Profitability 50%, "
           "Technical 20%, momentum 15% (the momentum score of the Momentum leaders card), 52-week position 10% (100 minus the % below the high) and Quality 5%.",
           "At most 3 companies from one Sector label. Ties go to the higher Growth & Profitability score, then the higher FinLit IQ.", B_NOTE)
    return Preset(f"basic-top-{label}", f"Top 10 {label} caps", BASIC_GROUP["top"], f"The 10 {label} caps with the strongest mix of business scores and price strength, from the FinLit score.", "rules",
                  _m(cap=bucket), "", rules, B_TOP_ORDER, 10, B_BASE + (B_QUAL, B_BAL, R3M, R6M, W52, SECTOR, MCAP, RSC), (), how, True, None, (), f"p5 (Top 10, {label}, Basic)", "basic", B_RANK_SCORE, 3)


def _bp(pid, name, group, text, rules, rank, cols, how, **kw) -> Preset:
    return Preset(pid, name, BASIC_GROUP[group], text, "rules", _m(), "", tuple(rules), tuple(rank), 25, tuple(cols), (), tuple(how) + (B_NOTE,), False, None, (), kw.pop("spec", "p15-17"), "basic", **kw)


B_THEME_RULES = (MC1000, ("pillar_growth >= 55", "Growth 55 or more"), _bal(40))
BASIC: List[Preset] = [
    _bt("Large", "large"), _bt("Mid", "mid"), _bt("Small", "small"),
    _bp("basic-strong-both", "Strong on both", "top", "Growth & Profitability score and Technical both 78 or more.",
        (("fundamental_score >= 78", "Growth & Profitability score 78 or more"), ("pillar_technical >= 78", "Technical 78 or more"), MC1000), (("overall", "desc"),),
        B_BASE + B_TAIL, ("Growth & Profitability score 78 or more and Technical 78 or more.", "Market cap Rs 1,000 Cr or more.", "Ranked by FinLit IQ.")),
    _bp("basic-strong-business-lagging", "Strong business, price lagging", "value", "Growth & Profitability score 78 or more while the Technical score is below 45, and how far below the 52-week high.",
        (("fundamental_score >= 78", "Growth & Profitability score 78 or more"), ("pillar_technical < 45", "Technical below 45"), MC1000), (("fundamental_score", "desc"), ("overall", "desc")),
        (RANK, STOCK, B_FUND, B_TECH, W52, FINLIT, R3M, R6M, R1Y, SECTOR, MCAP),
        ("Growth & Profitability score 78 or more and Technical below 45: a strong business whose price has not followed.", "Market cap Rs 1,000 Cr or more.", "Ranked by Growth & Profitability score; the % below the 52-week high is shown.")),
    _bp("basic-strong-trend-weaker-business", "Strong trend, weaker business", "safety", "A caution view: Technical 78 or more while the Growth & Profitability score is below 45.",
        (("pillar_technical >= 78", "Technical 78 or more"), ("fundamental_score < 45", "Growth & Profitability score below 45"), MC1000), (("pillar_technical", "desc"), ("overall", "desc")),
        (RANK, STOCK, B_TECH, B_FUND, FINLIT, W52, R3M, R6M, R1Y, SECTOR, MCAP),
        ("Technical 78 or more and Growth & Profitability score below 45: the price is strong but the business scores are weak. This is a caution view, not a signal.", "Market cap Rs 1,000 Cr or more.", "Ranked by Technical.")),
    _bp("basic-strong-all-four", "Strong on all four pillars", "top", "Quality, Growth, Profitability and Balance sheet all 78 or more.",
        (("pillar_quality >= 78", "Quality 78 or more"), ("pillar_growth >= 78", "Growth 78 or more"), ("pillar_profitability >= 78", "Profitability 78 or more"), ("pillar_balance >= 78", "Balance sheet 78 or more"), MC1000),
        (("overall", "desc"),), (RANK, STOCK, FINLIT, B_QUAL, B_GROW, B_PROF, B_BAL, B_TECH, W52, SECTOR, MCAP),
        ("Quality, Growth, Profitability and Balance sheet all 78 or more.", "Market cap Rs 1,000 Cr or more.", "Ranked by FinLit IQ.")),
    _bp("basic-growth-leaders", "Growth leaders", "growth", "High growth with real profitability, a sound balance sheet and a price that is not falling apart.",
        (("pillar_growth >= 78", "Growth 78 or more"), ("pillar_profitability >= 60", "Profitability 60 or more"), _bal(50), ("pillar_technical >= 45", "Technical 45 or more"), MC2000),
        (("pillar_growth", "desc"), ("fundamental_score", "desc")), (RANK, STOCK, B_GROW, B_PROF, B_BAL, B_FUND, B_TECH, FINLIT, R6M, W52, SECTOR, MCAP),
        ("Growth 78 or more, Profitability 60 or more, Balance sheet 50 or more (a blank is allowed), Technical 45 or more.", "Market cap Rs 2,000 Cr or more.", "Ranked by Growth, then Growth & Profitability score.")),
    _bp("basic-profitable-debt-light", "Profitable and debt-light", "safety", "Profitability and Balance sheet both 78 or more.",
        (("pillar_profitability >= 78", "Profitability 78 or more"), ("pillar_balance >= 78", "Balance sheet 78 or more"), MC1000), (("profit_plus_balance", "desc"), ("overall", "desc")),
        (RANK, STOCK, B_PB, B_PROF, B_BAL, FINLIT, B_TECH, W52, SECTOR, MCAP),
        ("Profitability 78 or more and Balance sheet 78 or more.", "Market cap Rs 1,000 Cr or more.", "Ranked by Profitability plus Balance sheet.")),
    _bp("basic-quality-compounders", "Quality compounders", "growth", "Top Quality with growth, profitability and a sound balance sheet.",
        (("pillar_quality >= 78", "Quality 78 or more"), ("pillar_growth >= 60", "Growth 60 or more"), ("pillar_profitability >= 70", "Profitability 70 or more"), _bal(60), MC1000),
        (("fundamental_score", "desc"), ("overall", "desc")), (RANK, STOCK, B_QUAL, B_GROW, B_PROF, B_BAL, B_FUND, FINLIT, B_TECH, SECTOR, MCAP),
        ("Quality 78 or more, Growth 60 or more, Profitability 70 or more, Balance sheet 60 or more (a blank is allowed).", "Market cap Rs 1,000 Cr or more.", "Ranked by Growth & Profitability score.")),
    _bp("basic-momentum-leaders", "Momentum leaders", "trend", "Strong Technical score, within 15% of the 52-week high, with 3- and 6-month returns up.",
        (("pillar_technical >= 75", "Technical 75 or more"), ("fundamental_score >= 55", "Growth & Profitability score 55 or more"), ("pct_from_high <= 15", "No more than 15% below the 52-week high"),
         ("ret_3m > 0", "3-month return above 0"), ("ret_6m > 0", "6-month return above 0"), RUN_GUARD, MC2000), (("momentum_score", "desc"), ("pillar_technical", "desc")),
        (RANK, STOCK, B_MOM, R3M, R6M, R1Y, W52, B_TECH, B_FUND, FINLIT, SECTOR, MCAP),
        ("Technical 75 or more, Growth & Profitability score 55 or more, no more than 15% below the 52-week high, 3-month and 6-month returns both positive, 1-year return 300% or less.", "Market cap Rs 2,000 Cr or more (the fastest movers below that are thinly traded).",
         "Ranked by the momentum score: 100 x (0.3 x P3M + 0.4 x P6M + 0.3 x P12M), P being the percentile (0 to 1) of that period's return among stocks of Rs 1,000 Cr or more.")),
    _bp("basic-near-high", "Near 52-week high", "trend", "Within 5% of the 52-week high with a strong Technical score.",
        (("pct_from_high <= 5", "No more than 5% below the 52-week high"), ("pillar_technical >= 75", "Technical 75 or more"), ("fundamental_score >= 55", "Growth & Profitability score 55 or more"), MC2000),
        (("pillar_technical", "desc"), ("momentum_score", "desc")), (RANK, STOCK, W52, B_TECH, B_MOM, B_FUND, FINLIT, R3M, R6M, SECTOR, MCAP),
        ("No more than 5% below the 52-week high, Technical 75 or more, Growth & Profitability score 55 or more.", "Market cap Rs 2,000 Cr or more.", "Ranked by Technical, then momentum score.")),
    _bp("basic-quality-off-highs", "Quality off its highs", "value", "High Quality and Growth & Profitability, 25% or more below the 52-week high.",
        (("pillar_quality >= 78", "Quality 78 or more"), ("fundamental_score >= 70", "Growth & Profitability score 70 or more"), ("pct_from_high >= 25", "At least 25% below the 52-week high"), MC1000),
        (("fundamental_score", "desc"), ("overall", "desc")), (RANK, STOCK, B_QUAL, B_FUND, W52, B_TECH, FINLIT, R6M, SECTOR, MCAP),
        ("Quality 78 or more, Growth & Profitability score 70 or more, at least 25% below the 52-week high.", "Market cap Rs 1,000 Cr or more.", "Ranked by Growth & Profitability score.")),
    Preset("basic-emerging-tech", "Emerging tech", BASIC_GROUP["themes"], "Companies in new-technology businesses (electronics, defence and shipbuilding, software and data, digital platforms, fintech, EVs, clean energy), still growing.",
           "tags", _m(), "", B_THEME_RULES, (("rank_score", "desc"), ("overall", "desc")), 25,
           (RANK, STOCK, SUBT, FINLIT, B_FUND, B_TECH, B_GROW, B_BAL, R6M, W52, SECTOR, MCAP, RSC), SUB_CHIPS,
           ("Companies in a sub-theme: every company whose Sector label belongs to it (for example Aerospace & Defense, Ship Building, Explosives, Consumer Electronics, E-Retail, Exchange and Data Platform) joined with a short named list that the research team reviews every quarter. The sub-theme is shown as a column.",
            "Market cap Rs 1,000 Cr or more, Growth 55 or more, Balance sheet 40 or more (a blank is allowed).",
            "Ranked by a theme rank score: 50% Growth & Profitability score, 30% Technical, 20% Growth, each a percentile among companies of its size group of Rs 1,000 Cr or more.", B_NOTE),
           False, None, (), "p6-9 (Emerging tech, Basic)", "basic", (("fundamental_score", 0.50), ("pillar_technical", 0.30), ("pillar_growth", 0.20))),
    Preset("basic-sector-themes", "Sector themes in play", BASIC_GROUP["themes"], "Sectors where more stocks sit near their 52-week high than in the market as a whole, and the companies leading them.", "themes",
           _m(), "", (), (("rank_score", "desc"), ("overall", "desc")), 25, (RANK, STOCK, SECTOR, FINLIT, B_FUND, B_TECH, R3M, Col("vs_industry_3m", "3-month return against the sector median (points)", "num1"), W52, MCAP),
           (SMALL_GROUPS,),
           ("Every night each sector (by its Sector label) is scored on breadth, the share of its stocks within 15% of their 52-week high, and its median 3-month return against the whole market; stocks of Rs 1,000 Cr or more.",
            "In play: breadth at least 40% and 15 points above the market's, and median 3-month return at least 5 points above the market's.",
            "Leaders (up to 5 per sector): market cap Rs 1,000 Cr or more, within 15% of their 52-week high, 3-month return above the sector median; ranked by the Top 10 rank score of the Basic tab.",
            "Generic labels (Capital Goods, Financial Services, Services, FMCG, Healthcare, Information Technology) and groups under 8 companies are left out of theme status."),
           False, None, (), "p12 (Sector themes, Basic)", "basic", B_RANK_SCORE),
    _bp("basic-caution-list", "Caution list", "safety", "Companies with more warning signs than usual. Read the company page before acting.",
        (("overall < 45 or pillar_balance < 35 or (pct_from_high >= 40 and pillar_technical <= 25)", "FinLit IQ below 45, or Balance sheet below 35, or 40% or more below the high with Technical 25 or less"), MC1000),
        (("overall", "asc"),), (RANK, STOCK, FINLIT, B_BAL, B_TECH, W52, R6M, SECTOR, MCAP),
        ("FinLit IQ below 45 (Watch), or Balance sheet below 35, or 40% or more below the 52-week high with Technical 25 or less.", "Market cap Rs 1,000 Cr or more.", "Ranked by FinLit IQ, lowest first. This is a caution list, not a recommendation.")),
]

ADVANCED: List[Preset] = list(PRESETS)
PRESETS = PRESETS + BASIC

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
