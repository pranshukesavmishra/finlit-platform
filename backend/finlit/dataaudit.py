"""Read-only data audit: where is data missing, stale, or the wrong kind? (`python -m finlit.worker audit-data`, docs/DATA-AUDIT.md)

One founder-run command. It reads the real tables feature by feature and reports, per feature: how many rows, how new the newest row is against
the cadence the feature needs (STALE), which key columns are empty beyond a sensible share (MISSING), and values of the wrong kind (WRONG:
non-positive prices, future dates, scores outside 0-100, absurd ratios, duplicate or badly written symbols, orphan rows, text where a number belongs).

Gentle on the live database by construction: every check runs in a READ ONLY transaction with statement_timeout 20 s, queries run one after the
other on one connection, big tables are sampled (TABLESAMPLE, or LIMIT when the table cannot be sampled), counts are capped, and the whole run
stops starting new queries after a time budget. A missing table, a missing column or a slow query becomes a finding "could not check: ..."; nothing
here raises out of run_audit(). It never writes (Redis is only read), never reads the users table beyond a row count, and prints no secret:
provider settings are shown only as True/False.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import asyncpg

STATEMENT_TIMEOUT_MS = 20_000
SAMPLE_ROWS = 50_000            # rows examined per big table (10 000 with --quick)
QUICK_SAMPLE_ROWS = 10_000
COUNT_CAP = 100_000             # a rule counts at most this many matching rows
EXACT_COUNT_CAP = 200_000       # above this a table's row count is the planner's estimate
BUDGET_SECONDS = 100            # no new query starts after this; the run is promised to end under two minutes
SEVERITIES = ("WRONG", "MISSING", "STALE", "UNCHECKED", "OK")
RANK = {s: i for i, s in enumerate(SEVERITIES)}
GROUPS = ("stocks", "screeners", "funds", "etfs", "indices", "commodities", "macro", "flows", "news", "logos", "dhan", "jobs", "keys")
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass
class Finding:
    severity: str
    feature: str
    what: str
    count: Optional[int] = None
    of: Optional[int] = None
    examples: List[str] = field(default_factory=list)
    cause: str = ""
    sampled: bool = False
    group: str = ""

    def as_dict(self) -> dict:
        return {"severity": self.severity, "group": self.group, "feature": self.feature, "what": self.what, "count": self.count, "of": self.of,
                "sampled": self.sampled, "examples": self.examples, "cause": self.cause}


@dataclass(frozen=True)
class N:
    """A column that should not be empty: MISSING when more than `thr` percent of the rows have NULL or ''. `where` limits which rows count."""
    col: str
    thr: float
    cause: str = ""
    where: Optional[str] = None


@dataclass(frozen=True)
class R:
    """A rule over rows (alias t). `cond` matches the bad rows; or `group` + `having` for a group-wise rule (duplicates, sums)."""
    what: str
    cond: str = "true"
    sev: str = "WRONG"
    cause: str = ""
    key: Optional[str] = None
    group: Optional[str] = None
    having: Optional[str] = None
    heavy: bool = False          # skipped by --quick


@dataclass(frozen=True)
class T:
    group: str
    feature: str
    table: str
    key: str
    date: Optional[str] = None               # SQL over t: the date that says how new the data is
    cadence: Optional[float] = None          # days the newest date may be old before STALE
    date_label: str = "updated"
    base: str = "true"
    nulls: Tuple[N, ...] = ()
    rules: Tuple[R, ...] = ()
    job: Optional[str] = None                # the supervisor job that fills it (for the likely-cause text)
    future_ok: bool = False
    note: str = ""


_ISIN_BAD = "t.isin IS NOT NULL AND t.isin !~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'"
_SYM_BAD = "t.symbol <> upper(btrim(t.symbol)) OR t.symbol ~ '\\s'"
_ORPHAN = "NOT EXISTS (SELECT 1 FROM companies c WHERE c.symbol = t.symbol)"
_ORPHAN_R = R("rows for a symbol that is not in the company list (orphan)", _ORPHAN, cause="a company was removed from the universe; run refresh-universe, then prune")


def _score_rule(name: str, cols: Sequence[str]) -> R:
    return R(f"{name} outside 0-100", " OR ".join(f"t.{c} < 0 OR t.{c} > 100" for c in cols), cause="the scoring code or an old model version wrote it; re-run the job that fills this table")


TABLES: Tuple[T, ...] = (
    # ------------------------------------------------------------------ stock pages
    T("stocks", "Stock universe", "companies", "t.symbol", "t.updated_at", 10, job="universe",
      nulls=(N("name", 1), N("sector", 25, "sector comes with the report: run ingest-all"), N("industry", 35, "industry comes with the report: run ingest-all"),
             N("nse_code", 30), N("website", 85, "logos need the website: run refresh-universe, then ingest-all")),
      rules=(R("symbol has spaces or is not upper case", _SYM_BAD, cause="symbols are stored trimmed and upper case; fix at the source (refresh-universe)"),
             R("same symbol twice (ignoring case and spaces)", group="upper(btrim(t.symbol))", having="count(*) > 1", cause="two rows differ only by case or spaces; delete the wrong one"),
             R("same NSE code on two symbols", "t.nse_code IS NOT NULL AND btrim(t.nse_code) <> ''", group="upper(btrim(t.nse_code))", having="count(*) > 1", cause="provider list has a duplicate code; run refresh-universe"))),
    T("stocks", "Stock scores (summary page)", "scores", "t.symbol", "t.updated_at", 4, job="score",
      nulls=(N("overall", 10), N("price", 10), N("market_cap", 15), N("pe", 60, "loss-making companies have no P/E; above this share it is a data gap"), N("roe", 35),
             N("pb", 45), N("roce", 50), N("sector", 20), N("industry", 35), N("return_1y", 45, "needs a year of prices: run backfill-history"), N("metrics", 30, "run rebuild-metrics")),
      rules=(_score_rule("overall or pillar score", ("overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical")),
             R("price zero or negative", "t.price <= 0"), R("market cap zero or negative", "t.market_cap <= 0"),
             R("P/E negative or above 5000", "t.pe < 0 OR t.pe > 5000", cause="a unit or sign error in the report; re-ingest the company"),
             R("ROE or ROCE beyond +-1000 percent", "abs(t.roe) > 1000 OR abs(t.roce) > 1000"),
             R("P/B beyond +-1000 or debt/equity above 1000", "abs(t.pb) > 1000 OR t.debt_to_equity > 1000"),
             R("dividend yield negative or above 50 percent", "t.dividend_yield < 0 OR t.dividend_yield > 50"),
             R("day change beyond +-100 percent", "abs(t.change_pct) > 100"), R("one-year return below -100 percent", "t.return_1y < -100"),
             R("numbers stored as text inside the metrics column", "t.metrics IS NOT NULL AND EXISTS (SELECT 1 FROM jsonb_each(t.metrics) e WHERE jsonb_typeof(e.value) = 'string' AND (e.value #>> '{}') ~ '^-?[0-9][0-9.,]*%?$')",
               cause="a metric was written as a string; run rebuild-metrics", heavy=True),
             _ORPHAN_R)),
    T("stocks", "Score history", "score_history", "t.symbol", "t.day", 5, date_label="day", job="score",
      rules=(_score_rule("overall score", ("overall",)),)),
    T("stocks", "Daily prices (technicals input)", "price_daily", "t.symbol", "t.day", 5, date_label="day", job="quotes",
      nulls=(N("volume", 40), N("open", 25), N("high", 25), N("low", 25)),
      rules=(R("close price zero or negative", "t.close <= 0"), R("high below low", "t.high < t.low"),
             R("close outside the day's high-low", "t.close > t.high * 1.001 OR t.close < t.low * 0.999", cause="a bad candle from the provider"),
             R("negative volume", "t.volume < 0"), _ORPHAN_R)),
    T("stocks", "Live quotes (price, market cap, 52-week)", "listing_quotes", "t.symbol", "t.updated_at", 4, job="listing",
      nulls=(N("price", 5), N("market_cap", 10), N("high52", 10), N("low52", 10), N("traded_at", 15)),
      rules=(R("price zero or negative", "t.price <= 0"), R("market cap zero or negative", "t.market_cap <= 0"),
             R("52-week high below low", "t.high52 < t.low52"),
             R("price far outside the 52-week range", "t.high52 > 0 AND t.low52 > 0 AND (t.price > t.high52 * 1.5 OR t.price < t.low52 * 0.5)", cause="usually a split or bonus not adjusted in the range; run refresh-listing"),
             R("day change beyond +-100 percent", "abs(t.change_pct) > 100"), R("trade time in the future", "t.traded_at > now() + interval '1 day'"), _ORPHAN_R)),
    T("stocks", "Quarterly results", "quarter_light", "t.symbol || ' ' || t.quarter", "t.checked_at", 10, date_label="checked", job="results-light",
      nulls=(N("revenue", 40, "the quarterly P&L was not read: run refresh-results-light", where="t.filled"), N("net_profit", 40, where="t.filled"), N("period_end", 30)),
      rules=(R("quarter ends in the future", "t.period_end > current_date"), R("margin above 100 percent", "t.opm > 100 OR t.npm > 100", cause="revenue or profit in the wrong unit"),
             R("negative revenue", "t.revenue < 0"), R("EPS beyond +-100000", "abs(t.eps) > 100000"),
             R("quarter label disagrees with the period end", "t.period_end IS NOT NULL AND to_char(t.period_end, 'YYYY-MM') <> t.quarter"), _ORPHAN_R)),
    T("stocks", "Stored report sections (snapshots)", "snapshots", "t.symbol || '/' || t.statement || '/' || t.section", "t.generated_at", 3, date_label="generated", job="ingest",
      nulls=(N("etag", 1),),
      rules=(R("section body empty ({}, [] or null)", "pg_column_size(t.body) <= 10", sev="MISSING", cause="the provider sent nothing for this section; run ingest on the symbol"),
             R("section older than 45 days", "t.generated_at < now() - interval '45 days'", sev="STALE", cause="outside the daily ingest rotation; run ingest-all or refresh-stale"),
             _ORPHAN_R)),
    T("stocks", "Prism ratings and technicals", "prism_reports", "t.symbol", "t.generated_at", 7, date_label="generated", job="prism",
      nulls=(N("final", 40, "NOT RATED companies have no final; run audit-prism to see why"), N("label", 40), N("status", 1), N("model_version", 5), N("card", 30, "run precompute-prism")),
      rules=(R("Prism final outside 0-100", "t.final < 0 OR t.final > 100"), R("report is not a JSON object", "jsonb_typeof(t.report) <> 'object'", heavy=True), _ORPHAN_R)),
    T("stocks", "Provider vs report check", "data_coverage", "t.symbol", "t.checked_at", 3, date_label="checked", job="coverage",
      rules=(R("report differs from the provider's figures", "jsonb_array_length(t.mismatches) > 0", cause="run compare-provider on these symbols"),)),
    T("stocks", "Leader / Laggard labels", "leadership", "t.symbol", "t.as_of", 10, date_label="as of", job="leadership",
      nulls=(N("label", 40), N("group_id", 20), N("rel52", 40, "needs a year of weekly prices: run backfill-history")),
      rules=(R("rank higher than the number ranked", "t.rank > t.ranked"), R("label carried over for more than 3 runs", "t.stale_runs > 3", sev="STALE", cause="no fresh prices for this company; run refresh-leadership"),
             _ORPHAN_R)),
    T("stocks", "Earnings calls", "earnings_calls", "t.symbol || ' FY' || t.fiscal_year || 'Q' || t.quarter", "t.created_at", 4, date_label="found", job="earnings-calls",
      nulls=(N("call_date", 40), N("transcript_url", 30)),
      rules=(R("call marked read but no text stored", "t.status IN ('text_ok', 'answered') AND t.text_chars = 0"), R("call date in the future", "t.call_date > current_date + 1"),
             R("transcript failed or unreadable", "t.status IN ('failed', 'unreadable')", sev="MISSING", cause="open the note column; run refresh-earnings-calls (needs GEMINI_API_KEY)"))),
    T("stocks", "Earnings-call answers", "earnings_call_answers", "t.call_id::text || '/' || t.question_id", "t.generated_at", 4, date_label="generated", job="earnings-calls",
      rules=(R("answer failed validation", "NOT t.validated", sev="MISSING", cause="see reject_reason; run refresh-earnings-calls"), R("answer is JSON null", "t.answer = 'null'::jsonb"))),
    # ------------------------------------------------------------------ screeners
    T("screeners", "Prebuilt screens (cache)", "preset_results", "t.preset_id", "t.computed_at", 3, date_label="computed", job="presets",
      rules=(R("screen result empty", "t.body IN ('{}'::jsonb, '[]'::jsonb, 'null'::jsonb)", sev="MISSING", cause="run refresh-presets"),
             R("screen result is not an object or list", "jsonb_typeof(t.body) NOT IN ('object', 'array')"), R("screen dated in the future", "t.as_of > current_date + 1"))),
    T("screeners", "Momentum and growth scores", "preset_scores", "t.symbol", "t.updated_at", 3, job="presets",
      nulls=(N("momentum_score", 40, "needs 12 months of prices"), N("growth_score", 40)),
      rules=(_score_rule("momentum or growth score", ("momentum_score", "growth_score")), _ORPHAN_R)),
    T("screeners", "Preset run facts", "preset_meta", "t.key", "t.updated_at", 3, job="presets"),
    T("screeners", "ATH and price position", "price_history_long", "t.symbol", "t.tried_at", 14, date_label="tried", job="ath",
      nulls=(N("ath", 50, "run backfill-history"), N("ath_date", 50), N("first_date", 30)),
      rules=(R("ATH zero or negative", "t.ath <= 0"), R("ATH date in the future", "t.ath_date > current_date + 1"),
             R("dates and closes lists differ in length", "cardinality(t.dates) <> cardinality(t.closes)", heavy=True),
             R("history is empty", "cardinality(t.dates) = 0", sev="MISSING", cause="the provider had no history; run backfill-history"),
             R("ATH below the latest weekly close", "t.ath IS NOT NULL AND cardinality(t.closes) > 0 AND t.ath < t.closes[cardinality(t.closes)] * 0.999", cause="ATH was not recomputed; run backfill-history", heavy=True),
             _ORPHAN_R)),
    T("screeners", "Industry breadth", "industry_breadth_daily", "t.industry", "t.as_of", 4, date_label="as of", job="presets",
      rules=(R("breadth percentage outside 0-100", "t.b50 < 0 OR t.b50 > 100 OR t.b200 < 0 OR t.b200 > 100"),)),
    # ------------------------------------------------------------------ mutual funds
    T("funds", "Mutual fund schemes (NAV, returns, SIP, AUM)", "mf_schemes", "t.code::text", "t.nav_date", 5, date_label="NAV date", base="t.active", job="mf",
      nulls=(N("isin", 20), N("nav", 1), N("nav_date", 1), N("category", 1), N("amc", 1), N("r1y", 45, "needs a year of NAV history: run backfill-mf", where="t.has_hist"),
             N("r3y", 65, "run backfill-mf"), N("r5y", 80, "run backfill-mf"), N("vol1y", 50), N("mdd", 50), N("sip3y", 65), N("sip5y", 80),
             N("aum_lakh", 45, "run refresh-facts"), N("metrics_date", 45)),
      rules=(R("NAV zero or negative", "t.nav <= 0", cause="AMFI row parsed wrong; run refresh-mf"), R("previous NAV zero or negative", "t.prev_nav <= 0"),
             R("NAV moved more than 50 percent in a day", "t.nav > 0 AND t.prev_nav > 0 AND abs(t.nav / t.prev_nav - 1) > 0.5", cause="a bad AMFI row, or a merger/payout not adjusted"),
             R("NAV older than 7 days on an active scheme", "t.nav_date < current_date - 7", sev="STALE", cause="the scheme stopped reporting; check AMFI, or run refresh-mf"),
             R("returns older than 10 days", "t.metrics_date < current_date - 10", sev="STALE", cause="run refresh-mf (it recomputes returns)"),
             R("1-year return below -100 or above 1000 percent", "t.r1y < -100 OR t.r1y > 1000"), R("3- or 5-year return below -100 or above 300 percent", "t.r3y < -100 OR t.r3y > 300 OR t.r5y < -100 OR t.r5y > 300"),
             R("volatility negative or above 300", "t.vol1y < 0 OR t.vol1y > 300 OR t.vol3y < 0 OR t.vol3y > 300"), R("max drawdown beyond +-100", "abs(t.mdd) > 100"),
             R("SIP return below -100 or above 300 percent", "t.sip3y < -100 OR t.sip3y > 300 OR t.sip5y < -100 OR t.sip5y > 300"), R("AUM negative", "t.aum_lakh < 0"),
             R("ISIN is not 12 characters in the ISIN pattern", _ISIN_BAD), R("name has leading or trailing spaces", "t.name <> btrim(t.name)"),
             R("same ISIN on two active schemes", "t.isin IS NOT NULL AND btrim(t.isin) <> ''", group="t.isin", having="count(*) > 1", cause="AMFI lists one ISIN twice; check the scheme master"))),
    T("funds", "Fund NAV history, monthly (mf_monthly)", "mf_monthly", "t.code::text", "t.days[cardinality(t.days)]", 40, date_label="newest month point", job="mf",
      rules=(R("days and NAVs lists differ in length", "cardinality(t.days) <> cardinality(t.navs)", heavy=True), R("no monthly points", "cardinality(t.days) = 0", sev="MISSING", cause="run backfill-mf"),
             R("a monthly NAV is zero or negative", "EXISTS (SELECT 1 FROM unnest(t.navs) x WHERE x <= 0)", cause="run backfill-mf for the fund house", heavy=True))),
    T("funds", "Fund NAV history, daily (mf_history)", "mf_history", "t.code::text", "t.d1", 6, date_label="last NAV", job="mf",
      rules=(R("first date after last date", "t.d0 > t.d1"), R("no points", "t.n <= 0"), R("history marked incomplete", "NOT t.complete", sev="MISSING", cause="run backfill-mf (resumable)"))),
    T("funds", "Fund facts (AUM, launch)", "mf_facts", "t.code::text", "t.updated_at", 10, job="facts",
      nulls=(N("aum_lakh", 40, "run refresh-facts"), N("launch_date", 30), N("aum_end", 40)),
      rules=(R("launch date in the future or before 1990", "t.launch_date > current_date OR t.launch_date < date '1990-01-01'"), R("AUM negative", "t.aum_lakh < 0"),
             R("AUM period older than 150 days", "t.aum_end < current_date - 150", sev="STALE", cause="AMFI publishes quarterly average AUM; run refresh-facts"),
             R("fact row for a scheme that does not exist", "NOT EXISTS (SELECT 1 FROM mf_schemes s WHERE s.code = t.code)", heavy=True))),
    T("funds", "Fund expense ratios (TER)", "mf_ter", "t.name_key", "t.ter_date", 45, date_label="TER date", job="facts",
      nulls=(N("ter_regular", 15), N("ter_direct", 25)),
      rules=(R("TER below 0 or above 5 percent", "t.ter_regular < 0 OR t.ter_regular > 5 OR t.ter_direct < 0 OR t.ter_direct > 5"), R("direct plan costs more than regular", "t.ter_direct > t.ter_regular"))),
    T("funds", "Fund Health Score", "mf_scores", "t.key", "t.run_date", 4, date_label="run date", job="score-mf",
      nulls=(N("final", 40, "NOT RATED funds have none; run score-mf"), N("label", 40), N("category", 20)),
      rules=(_score_rule("health score or part score", ("final", "perf", "risk", "cost", "quality", "percentile")), R("rank beyond group size", "t.rank > t.rank_of"),
             R("NAV date in the future", "t.nav_date > current_date + 1"))),
    T("funds", "Fund Screener figures (mf_screen)", "mf_screen", "t.x_code::text", "t.x_run", 4, date_label="run", job="mf-screen",
      nulls=(N("x_ter_rel", 50), N("x_vol1", 50), N("x_aum_rk", 50), N("x_rk1", 50), N("x_launch", 40), N("x_consist", 60)),
      rules=(R("volatility negative", "t.x_vol1 < 0 OR t.x_vol3 < 0"), R("exit load beyond 0-100 percent", "t.x_exit_pct < 0 OR t.x_exit_pct > 100"),
             R("rank larger than peer count", "t.x_rk1 > t.x_rn1 OR t.x_rk3 > t.x_rn3 OR t.x_rk5 > t.x_rn5"), R("fund age negative", "t.x_age < 0"),
             R("launch date in the future", "t.x_launch > current_date"))),
    T("funds", "Fund holdings (screener)", "mf_screen_hold", "t.fkey || ':' || t.isin", "t.as_of", 45, date_label="as of", job="portfolios",
      rules=(R("holding percent outside 0-100", "t.pct < 0 OR t.pct > 100"), R("holding ISIN malformed", "t.isin !~ '^[A-Z0-9]{12}$'"),
             R("a fund's holdings add up to more than 105 percent", group="t.fkey", having="sum(t.pct) > 105", cause="portfolio file read twice; run refresh-portfolios"))),
    T("funds", "Fund portfolios (monthly files)", "disclosure_portfolios", "t.fkey || ':' || t.as_of::text", "t.as_of", 45, date_label="as of", job="portfolios",
      nulls=(N("net_assets_lakh", 30), N("benchmark", 60)),
      rules=(R("holdings add up to under 50 or over 105 percent", "t.pct_total < 50 OR t.pct_total > 105", cause="the fund house's file was read partly; run refresh-portfolios"),
             R("no holdings", "t.n <= 0"), R("holdings are not a list", "jsonb_typeof(t.holdings) <> 'array'", heavy=True))),
    T("funds", "Fund house industry report", "mf_industry_months", "t.month::text", "t.month", 75, date_label="month", job="industry",
      nulls=(N("aum", 30),), rules=(R("negative AUM or flows in", "t.aum < 0 OR t.mobilized < 0 OR t.redemption < 0"),)),
    T("funds", "Category averages", "mf_cat_avg", "t.category || ' / ' || t.plan", "t.nav_date", 5, date_label="NAV date", job="mf",
      nulls=(N("blob", 30),), rules=(R("more eligible funds than members", "t.eligible > t.members"),)),
    T("funds", "Fund hot list", "mf_hot", "t.code::text", "t.built_at", 4, date_label="built", job="mf"),
    # ------------------------------------------------------------------ ETFs
    T("etfs", "ETFs", "etf_funds", "t.symbol", "t.price_date", 5, date_label="price date", base="t.active", job="etf",
      nulls=(N("price", 10), N("price_date", 10), N("ret_1y", 45), N("ret_3y", 65), N("category", 30), N("fund_house", 30), N("isin", 5)),
      rules=(R("price zero or negative", "t.price <= 0"), R("price older than 10 days", "t.price_date < current_date - 10", sev="STALE", cause="run refresh-etf --resume"),
             R("1-year return below -100 or above 1000 percent", "t.ret_1y < -100 OR t.ret_1y > 1000"), R("volatility negative", "t.vol_1y < 0"), R("52-week high below low", "t.high52 < t.low52"),
             R("price far outside the 52-week range", "t.high52 > 0 AND t.low52 > 0 AND (t.price > t.high52 * 1.5 OR t.price < t.low52 * 0.5)"),
             R("NAV zero or negative", "t.nav <= 0"), R("premium to NAV beyond +-50 percent", "abs(t.nav_premium) > 50"),
             R("symbol has spaces or is not upper case", _SYM_BAD), R("ISIN malformed", _ISIN_BAD))),
    T("etfs", "ETF price history", "etf_history", "t.symbol", "t.updated_at", 5, job="etf",
      rules=(R("dates and closes differ in length", "cardinality(t.dates) <> cardinality(t.closes)", heavy=True), R("no history", "cardinality(t.dates) = 0", sev="MISSING", cause="run refresh-etf --resume"),
             R("a close is zero or negative", "EXISTS (SELECT 1 FROM unnest(t.closes) x WHERE x <= 0)", heavy=True))),
    T("etfs", "ETF hot list", "etf_hot", "t.symbol", "t.built_at", 5, date_label="built", job="etf"),
    # ------------------------------------------------------------------ indices
    T("indices", "Index constituents (heatmap members)", "index_members", "t.index_code || ':' || t.symbol",
      rules=(_ORPHAN_R, R("symbol has spaces or is not upper case", _SYM_BAD))),
    T("indices", "Dhan index list", "dhan_indices", "t.exch || ':' || t.symbol", "t.loaded_at", 10, date_label="loaded", job="instruments",
      nulls=(N("name", 30),), rules=(R("symbol blank or has spaces", "btrim(t.symbol) = '' OR t.symbol ~ '\\s'"),)),
    # ------------------------------------------------------------------ commodities
    T("commodities", "Dhan commodity contracts", "dhan_commodity_contracts", "t.symbol || ':' || t.expiry::text", "t.loaded_at", 10, date_label="loaded", job="commodities",
      nulls=(N("upper_limit", 50), N("lower_limit", 50)),
      rules=(R("contract already expired", "t.expiry < current_date", sev="STALE", cause="run refresh-commodities to load current contracts"), R("tick size zero or negative", "t.tick_paise <= 0"),
             R("upper limit below lower limit", "t.upper_limit < t.lower_limit"))),
    T("commodities", "Commodity day snapshots", "commodity_snapshots", "t.symbol", "t.day", 5, date_label="day", job="commodities",
      rules=(R("value zero or negative", "t.value <= 0"),)),
    # ------------------------------------------------------------------ macro
    T("macro", "Macro series (MoSPI, RBI)", "macro_points", "t.series || ':' || t.d::text", "t.d", 120, date_label="newest point", job="macro",
      rules=(R("value is NaN", "t.v = 'NaN'::float8"), R("date in the future", "t.d > current_date + 1"))),
    T("macro", "Macro run facts", "macro_meta", "t.key", "t.updated_at", 3, job="macro"),
    # ------------------------------------------------------------------ FII / DII
    T("flows", "FII / DII daily flows", "flows_daily", "t.d::text", "t.d", 5, date_label="day", job="flows",
      nulls=(N("fii_net", 20), N("dii_net", 40, "DII history is filled by backfill-dii"), N("fpi_total_net", 30)),
      rules=(R("row dated on a weekend", "extract(dow FROM t.d) IN (0, 6)", cause="a manual or misparsed row; delete it"),
             R("FII buy minus sell does not equal net", "t.fii_buy IS NOT NULL AND t.fii_sell IS NOT NULL AND t.fii_net IS NOT NULL AND abs(t.fii_buy - t.fii_sell - t.fii_net) > 1 + 0.01 * abs(t.fii_net)"),
             R("DII buy minus sell does not equal net", "t.dii_buy IS NOT NULL AND t.dii_sell IS NOT NULL AND t.dii_net IS NOT NULL AND abs(t.dii_buy - t.dii_sell - t.dii_net) > 1 + 0.01 * abs(t.dii_net)"),
             R("buy or sell negative", "t.fii_buy < 0 OR t.fii_sell < 0 OR t.dii_buy < 0 OR t.dii_sell < 0"), R("net flow beyond +-200000 crore", "abs(t.fii_net) > 200000 OR abs(t.dii_net) > 200000"))),
    T("flows", "Participant open interest", "flows_oi", "t.d::text || ':' || t.participant || ':' || t.instrument", "t.d", 5, date_label="day", job="flows-nse",
      nulls=(N("long_", 10), N("short_", 10)), rules=(R("long or short negative", "t.long_ < 0 OR t.short_ < 0"),)),
    T("flows", "Nifty closes for flows", "flows_index", "t.code || ':' || t.d::text", "t.d", 5, date_label="day", job="flows",
      rules=(R("close zero or negative", "t.close <= 0"),)),
    # ------------------------------------------------------------------ news, filings, calendars
    T("news", "News", "feed_items", "t.id::text", "t.item_date", 3, date_label="item date", base="t.kind = 'news'",
      nulls=(N("link", 40), N("source", 30)),
      rules=(R("link is not a web address", "t.link IS NOT NULL AND t.link !~* '^https?://'"), R("symbol has spaces or lower case", "t.symbol IS NOT NULL AND t.symbol <> upper(btrim(t.symbol))"))),
    T("news", "Exchange filings (documents)", "feed_items", "t.id::text", "t.item_date", 4, date_label="item date", base="t.kind = 'document'",
      nulls=(N("link", 40), N("symbol", 40), N("category", 40)),
      rules=(R("link is not a web address", "t.link IS NOT NULL AND t.link !~* '^https?://'"),)),
    T("news", "Results calendar (past and declared)", "feed_items", "t.id::text", "t.item_date", 10, date_label="item date", base="t.kind = 'result' AND t.item_date <= current_date", future_ok=True, job="calendars",
      nulls=(N("symbol", 30), N("period", 40))),
    T("news", "IPO calendar", "ipos", "t.name", "t.updated_at", 3, job="calendars", future_ok=True,
      nulls=(N("price_high", 35), N("lot_size", 35), N("issue_size_cr", 45), N("sector", 60)),
      rules=(R("price band high below low", "t.price_high < t.price_low"), R("lot size zero or negative", "t.lot_size <= 0"), R("issue size zero or negative", "t.issue_size_cr <= 0"),
             R("listing before opening", "t.listing_date < t.open_date"), R("opening date before 2000", "t.open_date < date '2000-01-01'"))),
    # ------------------------------------------------------------------ logos
    T("logos", "Company logos", "logos", "t.owner_key", "t.fetched_at", 60, date_label="fetched", base="t.owner_kind = 'stock'", job="logos",
      nulls=(N("domain", 70, "needs the company website: run refresh-universe"),),
      rules=(R("status ok but no image", "t.status = 'ok' AND t.bytes IS NULL"), R("status ok but not an image", "t.status = 'ok' AND (t.mime IS NULL OR t.mime NOT LIKE 'image/%')"),
             R("image has zero width or height", "t.status = 'ok' AND (t.width <= 0 OR t.height <= 0)"), R("key has spaces or lower case", "t.owner_key <> upper(btrim(t.owner_key))"))),
    T("logos", "Fund-house logos", "logos", "t.owner_key", "t.fetched_at", 60, date_label="fetched", base="t.owner_kind = 'amc'", job="logos",
      rules=(R("status ok but no image", "t.status = 'ok' AND t.bytes IS NULL"),)),
    # ------------------------------------------------------------------ Dhan instruments
    T("dhan", "Dhan instruments (ISIN, surveillance, F&O)", "dhan_instruments", "t.exch || ':' || t.symbol", "t.loaded_at", 10, date_label="loaded", job="instruments",
      nulls=(N("isin", 40), N("name", 30), N("series", 20)),
      rules=(R("symbol has spaces or is not upper case", _SYM_BAD), R("F&O stock without a lot size", "t.fno AND coalesce(t.lot_size, 0) <= 0"),
             R("negative margin leverage", "t.mtf_leverage < 0"), R("ISIN malformed", _ISIN_BAD))),
    T("dhan", "Dhan option lots", "dhan_option_lots", "t.exch || ':' || t.underlying || ':' || t.expiry::text", "t.loaded_at", 10, date_label="loaded", job="instruments",
      rules=(R("lot size zero or negative", "t.lot_size <= 0"), R("expiry already passed", "t.expiry < current_date", sev="STALE", cause="run refresh-instruments"))),
)

# Coverage checks: rows of one table that should exist for rows of another. (group, feature, what, rows-lacking FROM/WHERE, key, total FROM/WHERE, threshold %, cause)
COVERAGE: Tuple[Tuple[str, str, str, str, str, str, float, str], ...] = (
    ("stocks", "Stock scores (summary page)", "companies with no score row", "companies t WHERE NOT EXISTS (SELECT 1 FROM scores s WHERE s.symbol = t.symbol)", "t.symbol", "companies t", 70,
     "only the top INGEST_LIMIT companies are loaded in full; run ingest-all, then score-all"),
    ("stocks", "Live quotes (price, market cap, 52-week)", "companies with no live quote", "companies t WHERE NOT EXISTS (SELECT 1 FROM listing_quotes q WHERE q.symbol = t.symbol)", "t.symbol", "companies t", 30,
     "run refresh-listing"),
    ("stocks", "Prism ratings and technicals", "scored companies with no Prism rating", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM prism_reports p WHERE p.symbol = t.symbol)", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 70, "run precompute-prism"),
    ("stocks", "Quarterly results", "scored companies with no quarterly result row", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM quarter_light q WHERE q.symbol = t.symbol)", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 80, "run refresh-results-light"),
    ("stocks", "Leader / Laggard labels", "scored companies with no leadership row", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM leadership l WHERE l.symbol = t.symbol)", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 70, "run refresh-leadership"),
    ("screeners", "ATH and price position", "scored companies with no long price history", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM price_history_long h WHERE h.symbol = t.symbol)", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 60, "run backfill-history"),
    ("screeners", "Momentum and growth scores", "scored companies with no momentum/growth score", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM preset_scores p WHERE p.symbol = t.symbol)", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 70, "run refresh-presets"),
    ("indices", "Index constituents (heatmap members)", "index members with no live quote (blank heatmap tile)", "index_members t WHERE NOT EXISTS (SELECT 1 FROM listing_quotes q WHERE q.symbol = t.symbol)", "t.index_code || ':' || t.symbol",
     "index_members t", 15, "run refresh-listing; or refresh-indices if the member list is old"),
    ("funds", "Mutual fund schemes (NAV, returns, SIP, AUM)", "active Growth schemes with NAV history but no monthly series", "mf_schemes t WHERE t.active AND t.option_class = 'Growth' AND t.has_hist AND NOT EXISTS (SELECT 1 FROM mf_monthly m WHERE m.code = t.code)", "t.code::text",
     "mf_schemes t WHERE t.active AND t.option_class = 'Growth' AND t.has_hist", 40, "run backfill-mf"),
    ("funds", "Fund Health Score", "active Growth schemes with no health score row", "mf_schemes t WHERE t.active AND t.option_class = 'Growth' AND NOT EXISTS (SELECT 1 FROM mf_scores s WHERE s.code = t.code)", "t.code::text",
     "mf_schemes t WHERE t.active AND t.option_class = 'Growth'", 60, "run score-mf"),
    ("funds", "Fund facts (AUM, launch)", "active Growth schemes with no fund-facts row", "mf_schemes t WHERE t.active AND t.option_class = 'Growth' AND NOT EXISTS (SELECT 1 FROM mf_facts f WHERE f.code = t.code)", "t.code::text",
     "mf_schemes t WHERE t.active AND t.option_class = 'Growth'", 40, "run refresh-facts"),
    ("logos", "Company logos", "scored companies without a usable logo", "(SELECT DISTINCT symbol FROM scores) t WHERE NOT EXISTS (SELECT 1 FROM logos l WHERE l.owner_kind = 'stock' AND l.owner_key = t.symbol AND l.status = 'ok')", "t.symbol",
     "(SELECT DISTINCT symbol FROM scores) t", 60, "run refresh-logos (needs the website: refresh-universe first)"),
)

# Snapshot sections expected for every company that has a summary: (section, tolerated percent without it, why it can be absent)
SNAP_SECTIONS: Tuple[Tuple[str, float, str], ...] = (
    ("financials", 5, ""), ("ratios", 5, "ratios and ratio history"), ("stats", 10, ""), ("price", 10, ""),
    ("ownership", 15, "shareholding pattern"), ("events", 35, "dividends and corporate actions"), ("peers", 20, ""),
    ("segments", 90, "many companies report one segment, so this one is lenient"),
)


class Ctx:
    def __init__(self, conn: asyncpg.Connection, redis: Any, settings: Any, quick: bool, validate: bool = False):
        self.conn, self.redis, self.settings, self.quick, self.validate = conn, redis, settings, quick, validate
        self.findings: List[Finding] = []
        self.started = time.monotonic()
        self.jobs: Dict[str, dict] = {}      # job name -> {"cmd": str, "state": dict|None, "off": str|None}
        self.sample_rows = QUICK_SAMPLE_ROWS if quick else SAMPLE_ROWS
        self.skipped_for_time = False

    # ------------------------------------------------------------ plumbing
    def out_of_time(self) -> bool:
        if time.monotonic() - self.started > BUDGET_SECONDS:
            self.skipped_for_time = True
            return True
        return False

    async def q(self, sql: str, *args: Any) -> List[asyncpg.Record]:
        """One query inside its own savepoint, so a failing query does not poison the read-only transaction around it."""
        async with self.conn.transaction():
            return await self.conn.fetch(sql, *args)

    def add(self, severity: str, group: str, feature: str, what: str, count: Optional[int] = None, of: Optional[int] = None, examples: Sequence[Any] = (), cause: str = "", sampled: bool = False) -> None:
        self.findings.append(Finding(severity, feature, what, count, of, [str(e)[:40] for e in examples if e is not None][:3], cause, sampled, group))

    def cannot(self, group: str, feature: str, what: str, exc: BaseException) -> None:
        self.add("UNCHECKED", group, feature, f"could not check: {what}: {_why(exc)}", cause="a missing table or column means the migrations have not run (run: python -m finlit.worker migrate); a timeout means the table is big or the database is busy")

    def job_hint(self, job: Optional[str]) -> str:
        if not job or job not in self.jobs:
            return ""
        j = self.jobs[job]
        st, off = j["state"], j["off"]
        if off:
            return f"job '{job}' is switched off ({off})"
        if st is None or st.get("last_success_at") is None:
            return f"job '{job}' has never succeeded (run: python -m finlit.worker {j['cmd']})"
        fails = st.get("consecutive_failures") or 0
        age_h = (time.time() - st["last_success_at"].timestamp()) / 3600
        txt = f"job '{job}' last ok {age_h / 24:.1f}d ago" if age_h >= 48 else f"job '{job}' last ok {age_h:.0f}h ago"
        return txt + (f", failing {fails} times in a row ({st.get('state_reason') or 'see jobs-status'})" if fails else "") + f"; run: python -m finlit.worker {j['cmd']}"

    # ------------------------------------------------------------ a table
    async def table_exists(self, name: str) -> bool:
        return bool((await self.q("SELECT to_regclass($1) IS NOT NULL AS ok", name))[0]["ok"])

    async def count_rule(self, group: str, feature: str, what: str, from_where: str, key: str, sev: str, cause: str, args: Tuple[Any, ...] = (), of: Optional[int] = None,
                         sampled: bool = False, group_by: Optional[str] = None, having: Optional[str] = None) -> Optional[int]:
        if group_by:
            inner = f"SELECT {group_by}::text AS k FROM {from_where} GROUP BY {group_by} HAVING {having} LIMIT {COUNT_CAP + 1}"  # nosec B608 - fragments are constants of this module; no value is interpolated
        else:
            inner = f"SELECT {key}::text AS k FROM {from_where} LIMIT {COUNT_CAP + 1}"  # nosec B608 - fragments are constants of this module; no value is interpolated
        row = (await self.q(f"SELECT count(*) AS n, (array_agg(k))[1:3] AS ex FROM ({inner}) s", *args))[0]  # nosec B608 - inner is built from constant fragments above
        n = int(row["n"])
        if n:
            label = what + (f" ({COUNT_CAP:,}+ counted, stopped there)" if n > COUNT_CAP else "")
            self.add(sev, group, feature, label, min(n, COUNT_CAP), of, row["ex"] or [], cause, sampled)
        return n

    async def run_table(self, t: T) -> None:
        feat = t.feature
        if not IDENT.match(t.table):
            return
        try:
            if not await self.table_exists(t.table):
                self.cannot(t.group, feat, f"table {t.table} does not exist", RuntimeError("run the migrations"))
                return
        except Exception as exc:
            self.cannot(t.group, feat, "table lookup", exc)
            return
        hint = self.job_hint(t.job)
        # --- row count (exact up to a cap, else the planner's estimate) and the sampling source
        try:
            est = (await self.q("SELECT coalesce(reltuples, -1)::bigint AS est FROM pg_class WHERE oid = to_regclass($1)", t.table))[0]["est"]
            if t.base == "true" and est > EXACT_COUNT_CAP:
                rows, exact = int(est), False
            else:
                rows = (await self.q(f"SELECT count(*) AS n FROM (SELECT 1 FROM {t.table} t WHERE {t.base} LIMIT {EXACT_COUNT_CAP + 1}) s"))[0]["n"]  # nosec B608 - table name matched against ^[a-z_]+$ and base is a constant of this module
                exact = rows <= EXACT_COUNT_CAP
        except Exception as exc:
            self.cannot(t.group, feat, f"row count of {t.table}", exc)
            return
        if rows == 0 and not self.validate:
            self.add("MISSING", t.group, feat, f"{t.table} is EMPTY (0 rows)", 0, cause=(hint + "; " if hint else "") + "nothing to show on the site for this feature until the job fills it")
            return
        sampled = rows > self.sample_rows
        args: Tuple[Any, ...] = ()
        src = f"{t.table} t"
        if sampled:
            args = (min(100.0, max(0.001, self.sample_rows * 100.0 / max(rows, 1))),)
            src = f"{t.table} t TABLESAMPLE SYSTEM ($1::float8)"
            try:
                await self.q(f"SELECT 1 FROM {src} LIMIT 1", *args)  # nosec B608 - table name matched against ^[a-z_]+$
            except Exception:
                args, src = (), f"(SELECT * FROM {t.table} LIMIT {self.sample_rows}) t"  # nosec B608 - table name matched against ^[a-z_]+$
        where = t.base
        # --- newest date against cadence
        newest, age = None, None
        if t.date:
            try:
                r = (await self.q(f"SELECT max({t.date})::date AS newest, current_date - max({t.date})::date AS age FROM {t.table} t WHERE {t.base}"))[0]  # nosec B608 - fragments are constants of this module
                newest, age = r["newest"], r["age"]
            except Exception as exc:
                self.cannot(t.group, feat, f"newest {t.date_label} in {t.table}", exc)
        bad_before = len(self.findings)
        n_txt = f"{rows:,}" if exact else f"~{rows:,}"
        if newest is None and t.date:
            prof_sev, prof = "MISSING", f"{n_txt} rows but every {t.date_label} date is empty"
        elif t.date and t.cadence is not None and age is not None and age > t.cadence:
            prof_sev, prof = "STALE", f"{n_txt} rows; newest {t.date_label} {newest} is {age} days old (should be within {t.cadence:g})"
        elif t.date:
            prof_sev, prof = "OK", f"{n_txt} rows; newest {t.date_label} {newest} ({age} days old, limit {t.cadence:g})" if t.cadence is not None else f"{n_txt} rows; newest {t.date_label} {newest}"
        else:
            prof_sev, prof = "OK", f"{n_txt} rows"
        if sampled:
            prof += f"; other checks on a random sample of about {self.sample_rows:,}"
        # --- empty columns
        await self._nulls(t, src, args, where, sampled, hint)
        # --- wrong kinds
        if t.date and not t.future_ok:
            await self._rule(t, R("date in the future", f"({t.date})::date > current_date + 1", cause="a clock or parsing error at the source"), src, args, where, sampled, hint)
        for rule in t.rules:
            if self.quick and rule.heavy:
                continue
            if self.out_of_time():
                break
            await self._rule(t, rule, src, args, where, sampled, hint)
        problems = len(self.findings) - bad_before
        cause = hint if prof_sev != "OK" else ""
        if prof_sev == "STALE" and not cause:
            cause = f"the job that fills {t.table} has not run lately; check jobs-status"
        self.add(prof_sev, t.group, feat, prof + ("" if prof_sev != "OK" or not problems else "; see problems above"), rows, None, [], cause)

    async def _nulls(self, t: T, src: str, args: Tuple[Any, ...], base: str, sampled: bool, hint: str) -> None:
        if not t.nulls:
            return
        def isnull(n: N) -> str:
            return f"(t.{n.col} IS NULL OR btrim(t.{n.col}::text) = '')"
        sel = []
        for i, n in enumerate(t.nulls):
            w = f"({n.where})" if n.where else "true"
            sel.append(f"count(*) FILTER (WHERE {w} AND {isnull(n)}) AS n{i}, count(*) FILTER (WHERE {w}) AS d{i}")
        results: Dict[int, Tuple[int, int]] = {}
        try:
            row = (await self.q(f"SELECT {', '.join(sel)} FROM {src} WHERE {base}", *args))[0]  # nosec B608 - column names and fragments are constants of this module; the sample percent is a bound parameter
            results = {i: (row[f"n{i}"], row[f"d{i}"]) for i in range(len(t.nulls))}
        except Exception:
            for i, n in enumerate(t.nulls):      # one column at a time: the failing one (missing column) becomes its own finding
                try:
                    w = f"({n.where})" if n.where else "true"
                    row = (await self.q(f"SELECT count(*) FILTER (WHERE {w} AND {isnull(n)}) AS a, count(*) FILTER (WHERE {w}) AS b FROM {src} WHERE {base}", *args))[0]  # nosec B608 - constants of this module; sample percent is bound
                    results[i] = (row["a"], row["b"])
                except Exception as exc:
                    self.cannot(t.group, t.feature, f"column {t.table}.{n.col}", exc)
        for i, (nn, dd) in results.items():
            n = t.nulls[i]
            if not dd or nn * 100.0 / dd <= n.thr:
                continue
            ex: List[Any] = []
            try:
                w = f"({n.where}) AND " if n.where else ""
                ex = [r["k"] for r in await self.q(f"SELECT {t.key}::text AS k FROM {src} WHERE {base} AND {w}{isnull(n)} LIMIT 3", *args)]  # nosec B608 - constants of this module; sample percent is bound
            except Exception:
                pass
            pct = nn * 100.0 / dd
            cause = "; ".join(x for x in (n.cause, hint) if x) or "the job that fills this column has not run or the provider sends nothing"
            self.add("MISSING", t.group, t.feature, f"{t.table}.{n.col} empty in {pct:.0f}% of rows (allowed {n.thr:g}%)" + (f" where {n.where}" if n.where else ""), nn, dd, ex, cause, sampled)

    async def _rule(self, t: T, rule: R, src: str, args: Tuple[Any, ...], base: str, sampled: bool, hint: str) -> None:
        try:
            if rule.group:
                cond = f"({base}) AND ({rule.cond})"
                await self.count_rule(t.group, t.feature, rule.what, f"{src} WHERE {cond}", rule.key or rule.group, rule.sev, rule.cause or hint, args, None, sampled, group_by=rule.group, having=rule.having)
            else:
                await self.count_rule(t.group, t.feature, rule.what, f"{src} WHERE ({base}) AND ({rule.cond})", rule.key or t.key, rule.sev, rule.cause or hint, args, None, sampled)
        except Exception as exc:
            self.cannot(t.group, t.feature, rule.what, exc)


def _why(exc: BaseException) -> str:
    msg = " ".join(str(exc).split())[:140]
    msg = re.sub(r"(postgres(ql)?|redis|rediss)://\S+", r"\1://...", msg)
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


# ---------------------------------------------------------------------- custom checks

async def check_coverage(ctx: Ctx, groups: Optional[set]) -> None:
    for group, feature, what, lacking, key, total, thr, cause in COVERAGE:
        if groups is not None and group not in groups:
            continue
        if ctx.out_of_time():
            return
        try:
            tables = set(re.findall(r"(?:FROM|JOIN)\s+([a-z_]+)", lacking + " " + total))
            missing = [x for x in sorted(tables) if not await ctx.table_exists(x)]
            if missing:
                ctx.cannot(group, feature, f"coverage '{what}' needs table {', '.join(missing)}", RuntimeError("table does not exist"))
                continue
            tot = (await ctx.q(f"SELECT count(*) AS n FROM (SELECT 1 FROM {total} LIMIT {COUNT_CAP + 1}) s"))[0]["n"]  # nosec B608 - constant fragments of this module; no value is interpolated
            if tot == 0:
                continue
            lack = (await ctx.q(f"SELECT count(*) AS n, (array_agg(k))[1:3] AS ex FROM (SELECT {key}::text AS k FROM {lacking} LIMIT {COUNT_CAP + 1}) s"))[0]  # nosec B608 - constant fragments of this module; no value is interpolated
            pct = lack["n"] * 100.0 / tot
            capped = tot > COUNT_CAP
            if pct > thr:
                ctx.add("MISSING", group, feature, f"{what}: {pct:.0f}% (allowed {thr:g}%)", lack["n"], tot, lack["ex"] or [], cause, capped)
            else:
                ctx.add("OK", group, feature, f"{what}: {pct:.0f}% (allowed {thr:g}%)", lack["n"], tot)
        except Exception as exc:
            ctx.cannot(group, feature, what, exc)


async def check_snapshots(ctx: Ctx) -> None:
    feature = "Stored report sections (snapshots)"
    try:
        if not await ctx.table_exists("snapshots"):
            return
        rows = await ctx.q("SELECT section, count(*) AS n FROM snapshots GROUP BY section")
        have = {r["section"]: r["n"] for r in rows}
        base = have.get("summary", 0)
        if not base:
            if have:
                ctx.add("MISSING", "stocks", feature, "no 'summary' section stored, so the stock summary page has nothing to show", 0, cause="run ingest-all")
            return
        for section, thr, why in SNAP_SECTIONS:
            have_n = have.get(section, 0)
            pct = max(0.0, (base - have_n) * 100.0 / base)
            label = f"companies with a summary but no '{section}' section" + (f" ({why})" if why else "")
            if pct > thr:
                ex = [r["k"] for r in await ctx.q("SELECT s.symbol AS k FROM snapshots s WHERE s.section = 'summary' AND NOT EXISTS (SELECT 1 FROM snapshots x WHERE x.symbol = s.symbol AND x.statement = s.statement AND x.section = $1) LIMIT 3", section)]
                ctx.add("MISSING", "stocks", feature, f"{label}: {pct:.0f}% (allowed {thr:g}%)", base - have_n, base, ex, "the provider call for this section failed or returned nothing; run ingest on the symbol, or refresh-short-history")
            else:
                ctx.add("OK", "stocks", feature, f"{label}: {pct:.0f}% (allowed {thr:g}%)", max(base - have_n, 0), base)
    except Exception as exc:
        ctx.cannot("stocks", feature, "section coverage", exc)


async def check_flows_coverage(ctx: Ctx) -> None:
    feature = "FII / DII daily flows"
    try:
        if not await ctx.table_exists("flows_daily"):
            return
        r = (await ctx.q("SELECT count(*) FILTER (WHERE fii_net IS NOT NULL) AS nf, count(*) FILTER (WHERE dii_net IS NOT NULL) AS nd, min(d) FILTER (WHERE fii_net IS NOT NULL) AS f0, "
                         "min(d) FILTER (WHERE dii_net IS NOT NULL) AS d0, max(d) FILTER (WHERE fii_net IS NOT NULL) AS f1, max(d) FILTER (WHERE dii_net IS NOT NULL) AS d1, current_date AS today FROM flows_daily"))[0]
        if not r["nf"] and not r["nd"]:
            return
        text = f"FII from {r['f0']} ({r['nf']:,} days, to {r['f1']}); DII from {r['d0']} ({r['nd']:,} days, to {r['d1']})"
        short = [n for n, a, b in (("FII", r["f0"], r["nf"]), ("DII", r["d0"], r["nd"])) if a is None or (r["today"] - a).days < 365]
        if short:
            ctx.add("MISSING", "flows", feature, f"coverage is under one year for {' and '.join(short)}: {text}", cause="run refresh-flows; DII history fills with backfill-dii (insert-only, resumable)")
        else:
            ctx.add("OK", "flows", feature, f"coverage start dates: {text}")
    except Exception as exc:
        ctx.cannot("flows", feature, "coverage start dates", exc)


async def check_macro_series(ctx: Ctx) -> None:
    feature = "Macro series (MoSPI, RBI)"
    try:
        if not await ctx.table_exists("macro_points"):
            return
        rows = await ctx.q("SELECT series, count(*) AS n, max(d) AS newest, current_date - max(d) AS age FROM macro_points GROUP BY series")
        if not rows:
            return
        stale = [r for r in rows if r["age"] > 150]
        thin = [r for r in rows if r["n"] < 3]
        hint = ctx.job_hint("macro")
        if stale:
            ctx.add("STALE", "macro", feature, f"{len(stale)} of {len(rows)} series have no point in the last 150 days", len(stale), len(rows), [f"{r['series']} ({r['age']}d)" for r in stale], hint or "run refresh-macro")
        if thin:
            ctx.add("MISSING", "macro", feature, f"{len(thin)} of {len(rows)} series hold fewer than 3 points", len(thin), len(rows), [r["series"] for r in thin], hint or "run refresh-macro")
        if not stale and not thin:
            ctx.add("OK", "macro", feature, f"{len(rows)} series, every one has a point in the last 150 days")
    except Exception as exc:
        ctx.cannot("macro", feature, "series check", exc)


async def check_calendars(ctx: Ctx) -> None:
    try:
        if await ctx.table_exists("feed_items"):
            n = (await ctx.q("SELECT count(*) AS n FROM feed_items WHERE kind = 'result' AND item_date >= current_date"))[0]["n"]
            if n == 0:
                ctx.add("MISSING", "news", "Results calendar (upcoming)", "no upcoming result dates held", 0, cause=ctx.job_hint("calendars") or "run refresh-calendars")
            else:
                ctx.add("OK", "news", "Results calendar (upcoming)", f"{n:,} upcoming result dates", n)
        if await ctx.table_exists("ipos"):
            n = (await ctx.q("SELECT count(*) AS n FROM ipos WHERE close_date >= current_date"))[0]["n"]
            ctx.add("OK" if n else "MISSING", "news", "IPO calendar (upcoming)", f"{n:,} IPOs open or upcoming" if n else "no open or upcoming IPO held (true on a quiet week)", n, cause="" if n else (ctx.job_hint("calendars") or "run refresh-calendars"))
    except Exception as exc:
        ctx.cannot("news", "Calendars", "upcoming dates", exc)


async def check_members_count(ctx: Ctx) -> None:
    """Counts only. The users table is never read beyond a number."""
    try:
        if await ctx.table_exists("users"):
            n = (await ctx.q("SELECT count(*) AS n FROM users"))[0]["n"]
            ctx.add("OK", "jobs", "Members (count only)", f"{n:,} accounts (nothing else is read)", n)
    except Exception as exc:
        ctx.cannot("jobs", "Members (count only)", "count", exc)


async def check_jobs(ctx: Ctx) -> None:
    feature = "Background jobs"
    try:
        if not await ctx.table_exists("job_state"):
            ctx.cannot("jobs", feature, "table job_state does not exist", RuntimeError("run the migrations"))
            return
        rows = {r["job"]: dict(r) for r in await ctx.q("SELECT job, last_success_at, last_attempt_at, last_status, consecutive_failures, state, state_reason FROM job_state")}
        try:
            from .jobs.registry import build_jobs, disabled_reason
            jobs = [j for j in build_jobs(os.environ) if not j.external]
        except Exception as exc:
            ctx.cannot("jobs", feature, "job registry", exc)
            jobs = []
        ctx.jobs = {}
        for j in jobs:
            off = None
            try:
                off = disabled_reason(j, os.environ)
            except Exception:
                pass
            ctx.jobs[j.name] = {"cmd": j.command, "state": rows.get(j.name), "off": off, "sla": j.sla.hours if j.sla.kind == "hours" else None}
        if not jobs:
            ctx.add("OK" if rows else "MISSING", "jobs", feature, f"{len(rows)} job state rows (registry unavailable)", len(rows))
            return
        now = time.time()
        healthy, off_names = 0, []
        for j in jobs:
            info, st = ctx.jobs[j.name], rows.get(j.name)
            if info["off"]:
                off_names.append(j.name)
                continue
            if st is None or st["last_success_at"] is None:
                ctx.add("MISSING", "jobs", f"Job {j.name}", "has never succeeded" + (f" (last status {st['last_status']})" if st and st["last_status"] else ""), cause=f"run: python -m finlit.worker {j.command}")
                continue
            age_h = (now - st["last_success_at"].timestamp()) / 3600
            fails = st["consecutive_failures"] or 0
            limit = (info["sla"] or 0) * 1.5
            if fails >= 3:
                ctx.add("STALE", "jobs", f"Job {j.name}", f"failing {fails} times in a row; last ok {age_h / 24:.1f} days ago", fails, cause=f"{st['state_reason'] or 'see jobs-status'}; run: python -m finlit.worker {j.command}")
            elif limit and age_h > limit:
                ctx.add("STALE", "jobs", f"Job {j.name}", f"last ok {age_h:.0f}h ago, expected within {info['sla']:g}h", cause=f"run: python -m finlit.worker {j.command}")
            else:
                healthy += 1
        if off_names:
            first = next(ctx.jobs[n]["off"] for n in off_names)
            ctx.add("MISSING", "jobs", feature, f"{len(off_names)} jobs are switched off by settings: {', '.join(off_names[:6])}", len(off_names), len(jobs), off_names, first)
        ctx.add("OK", "jobs", feature, f"{healthy} of {len(jobs)} scheduled jobs have a recent success and no repeated failure", healthy, len(jobs))
    except Exception as exc:
        ctx.cannot("jobs", feature, "job state", exc)


async def check_commodities_redis(ctx: Ctx) -> None:
    feature = "Commodity prices (Redis)"
    if ctx.redis is None:
        ctx.cannot("commodities", feature, "Redis", RuntimeError("no Redis connection"))
        return
    now = time.time()
    keys = {"cmd:mcx": 21600, "cmd:intl": 21600, "cmd:hb": 600, "cmd:cfg": None}
    for key, limit in keys.items():
        try:
            raw = await ctx.redis.get(key)
        except Exception as exc:
            ctx.cannot("commodities", feature, f"read {key}", exc)
            continue
        hint = "the price loop is not running: it is started as the 'commodities' process (python -m finlit.worker refresh-commodities --loop)"
        if raw is None:
            ctx.add("MISSING", "commodities", feature, f"{key} is not in Redis", 0, cause=hint)
            continue
        try:
            if key == "cmd:hb":
                age = now - float(raw)
                ctx.add("STALE" if age > limit else "OK", "commodities", feature, f"{key} heartbeat {age:.0f}s old", cause=hint if age > limit else "")
                continue
            blob = json.loads(raw)
            if key == "cmd:cfg":
                ctx.add("OK", "commodities", feature, f"{key} present ({len(blob) if hasattr(blob, '__len__') else 1} entries)")
                continue
            if key == "cmd:mcx":
                items = blob.get("items") or {}
                t = blob.get("t")
                bad = [k for k, v in items.items() if not isinstance(v, dict) or v.get("price") in (None, "", "0", 0) or _bad_number(v.get("price"))]
                err = blob.get("err")
            else:
                items = blob.get("quotes") or {}
                t = max([v.get("ts", 0) for v in items.values() if isinstance(v, dict)] or [0]) or None
                bad = [k for k, v in items.items() if not isinstance(v, dict) or _bad_number(v.get("usd"))]
                err = blob.get("err") or None
            if not items:
                ctx.add("MISSING", "commodities", feature, f"{key} holds no items", 0, cause=hint + ("; vendor error: " + str(err)[:80] if err else ""))
                continue
            if bad:
                ctx.add("WRONG", "commodities", feature, f"{key}: price missing, zero or not a number", len(bad), len(items), bad, "a vendor answer was refused; check the key in settings and refresh-commodities logs")
            if t and now - float(t) > limit:
                ctx.add("STALE", "commodities", feature, f"{key} newest reading is {(now - float(t)) / 3600:.1f}h old", cause=hint)
            elif not bad:
                ctx.add("OK", "commodities", feature, f"{key}: {len(items)} items" + (f", newest {now - float(t):.0f}s old" if t else ""))
        except Exception as exc:
            ctx.cannot("commodities", feature, f"parse {key}", exc)


def _bad_number(v: Any) -> bool:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return True
    return not (x > 0) or x != x


def check_keys(ctx: Ctx) -> None:
    s = ctx.settings
    def has(name: str) -> bool:
        return bool(getattr(s, name, ""))
    dhan = has("dhan_client_id") and (has("dhan_access_token") or (has("dhan_pin") and has("dhan_totp_secret")))
    wanted = (("FINEDGE_API_KEY", has("finedge_api_key"), "company reports, quotes, results"), ("DHAN_CLIENT_ID + token or PIN/TOTP", dhan, "daily candles, MCX commodity prices, technicals"),
              ("METALS_DEV_API_KEY", has("metals_dev_api_key"), "international metal prices and USD/INR"), ("METALPRICEAPI_KEY", has("metalprice_api_key"), "crude oil and gas international prices"),
              ("UPSTOX_ACCESS_TOKEN", has("upstox_access_token"), "ETF prices and candles"), ("GEMINI_API_KEY", has("gemini_api_key"), "earnings-call answers"),
              ("RESEND_API_KEY", has("resend_api_key"), "alert and digest emails"))
    for name, ok, use in wanted:
        ctx.add("OK" if ok else "MISSING", "keys", "Provider settings", f"{name} is set: {ok}  (feeds: {use})", cause="" if ok else f"add {name} to /opt/finlit/.env.aws and restart (value never shown here)")
    ctx.add("OK" if getattr(s, "commodity_mcx_display_cleared", False) else "MISSING", "keys", "Provider settings", f"COMMODITY_MCX_DISPLAY_CLEARED is set: {bool(getattr(s, 'commodity_mcx_display_cleared', False))}",
            cause="" if getattr(s, "commodity_mcx_display_cleared", False) else "until set, the commodities page never says 'Live' (a business decision, not a fault)")


# ---------------------------------------------------------------------- the run

def _selected(only: Optional[Sequence[str]]) -> Tuple[Optional[set], List[str]]:
    if not only:
        return None, []
    wanted: set = set()
    unknown: List[str] = []
    for item in only:
        for part in str(item).lower().split(","):
            part = part.strip()
            if not part:
                continue
            hits = {g for g in GROUPS if g == part or g.startswith(part)}
            (wanted.update(hits) if hits else unknown.append(part))
    return wanted, unknown


async def run_audit(settings: Any, only: Optional[Sequence[str]] = None, quick: bool = False, redis: Any = None, validate: bool = False) -> dict:
    """Run every selected check. Never raises. `validate` (tests only) also runs the rules on empty tables, to prove each query is valid SQL."""
    from .store import _redis, prepare_dsn
    started = time.monotonic()
    groups, unknown = _selected(only)
    meta: Dict[str, Any] = {"quick": quick, "only": sorted(groups) if groups else None, "unknownFeatures": unknown, "validGroups": list(GROUPS)}
    conn = None
    own_redis = False
    findings: List[Finding] = []
    try:
        dsn, extra = prepare_dsn(settings.database_url)
        extra = {k: v for k, v in extra.items() if k == "statement_cache_size"}
        conn = await asyncpg.connect(dsn, timeout=15, command_timeout=STATEMENT_TIMEOUT_MS / 1000 + 10, **extra)
        if redis is None:
            try:
                redis, own_redis = _redis(settings.redis_url), True
            except Exception:
                redis = None
        ctx = Ctx(conn, redis, settings, quick, validate)
        want = lambda g: groups is None or g in groups
        await _guard(ctx, "jobs", "Background jobs", lambda: _in_tx(ctx, check_jobs))      # first: later checks quote its state in their likely-cause text
        if want("jobs"):
            await _guard(ctx, "jobs", "Members (count only)", lambda: _in_tx(ctx, check_members_count))
        else:
            ctx.findings = [f for f in ctx.findings if f.group != "jobs"]
        if want("keys"):
            check_keys(ctx)
        for t in TABLES:
            if not want(t.group):
                continue
            if ctx.out_of_time():
                ctx.add("UNCHECKED", t.group, t.feature, f"skipped: the {BUDGET_SECONDS}s time budget was used up", cause="run again with --only <feature> to check the rest")
                continue
            await _guard(ctx, t.group, t.feature, lambda t=t: _in_tx(ctx, lambda c: c.run_table(t)))
        extras: List[Tuple[str, Callable]] = [("stocks", check_snapshots), ("flows", check_flows_coverage), ("macro", check_macro_series), ("news", check_calendars)]
        for grp, fn in extras:
            if want(grp) and not ctx.out_of_time():
                await _guard(ctx, grp, fn.__name__, lambda fn=fn: _in_tx(ctx, fn))
        if (groups is None or groups) and not ctx.out_of_time():
            await _guard(ctx, "stocks", "Coverage", lambda: _in_tx(ctx, lambda c: check_coverage(c, groups)))
        if want("commodities"):
            await _guard(ctx, "commodities", "Commodity prices (Redis)", lambda: check_commodities_redis(ctx))
        findings = ctx.findings
        meta["skippedForTime"] = ctx.skipped_for_time
    except Exception as exc:          # the database itself cannot be reached
        findings.append(Finding("UNCHECKED", "Database", f"could not check: cannot connect or run: {_why(exc)}", cause="check DATABASE_URL and that the database container is up (docker compose ps)", group="jobs"))
    finally:
        for closer in ((conn.close() if conn else None), (redis.aclose() if (own_redis and redis is not None) else None)):
            if closer is not None:
                try:
                    await closer
                except Exception:
                    pass
    findings.sort(key=lambda f: (RANK.get(f.severity, 9), f.group, f.feature))
    meta["seconds"] = round(time.monotonic() - started, 1)
    meta["counts"] = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    return {"meta": meta, "findings": [f.as_dict() for f in findings]}


async def _in_tx(ctx: Ctx, fn: Callable) -> None:
    """READ ONLY transaction, 20 s per statement, for one check."""
    async with ctx.conn.transaction(readonly=True):
        await ctx.conn.execute("SELECT set_config('statement_timeout', $1, true)", str(STATEMENT_TIMEOUT_MS))
        await fn(ctx)


async def _guard(ctx: Ctx, group: str, feature: str, call: Callable) -> None:
    try:
        await call()
    except Exception as exc:
        ctx.cannot(group, feature, "the check itself", exc)


# ---------------------------------------------------------------------- output

def _fit(text: Any, width: int) -> str:
    s = " ".join(str(text if text is not None else "").split())
    return s if len(s) <= width else s[: max(0, width - 1)] + "~"


def render(result: dict) -> str:
    meta, fs = result["meta"], result["findings"]
    c = meta["counts"]
    lines = ["FinLit data audit (read-only)  " + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + f"   mode: {'quick' if meta['quick'] else 'full'}   took {meta['seconds']}s",
             "  ".join(f"{s}: {c.get(s, 0)}" for s in SEVERITIES), "~ after a count = measured on a random sample of the table.  Worst first: WRONG, MISSING, STALE, UNCHECKED, OK.", ""]
    if meta.get("unknownFeatures"):
        lines.append(f"unknown --only value(s): {', '.join(meta['unknownFeatures'])}.  Valid: {', '.join(meta['validGroups'])}")
    if meta.get("skippedForTime"):
        lines.append(f"NOTE: the {BUDGET_SECONDS}s budget ran out; some checks were skipped. Re-run with --only <feature>.")
    head = f"{'SEV':<9} {'FEATURE':<26} {'WHAT':<58} {'COUNT':<17} {'EXAMPLES':<32} LIKELY CAUSE / WHAT TO RUN"
    lines += [head, "-" * len(head)]
    for f in fs:
        n = ""
        if f["count"] is not None:
            n = f"{f['count']:,}" + (f" of {f['of']:,}" if f["of"] else "") + ("~" if f["sampled"] else "")
        lines.append(f"{f['severity']:<9} {_fit(f['feature'], 26):<26} {_fit(f['what'], 58):<58} {_fit(n, 17):<17} {_fit(', '.join(f['examples']), 32):<32} {_fit(f['cause'], 90)}")
    if not fs:
        lines.append("(nothing was checked)")
    return "\n".join(lines)


async def run_cli(settings: Any, only: Optional[Sequence[str]], quick: bool, json_path: str) -> int:
    """Entry for `python -m finlit.worker audit-data`. Always returns 0."""
    try:
        result = await run_audit(settings, only=only, quick=quick)
        print(render(result))
        try:
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2, default=str)
            print(f"\nJSON written to {json_path}")
        except OSError as exc:
            print(f"\n(could not write {json_path}: {exc})")
    except Exception as exc:       # pragma: no cover - run_audit does not raise; this keeps the promise anyway
        print(f"audit could not run: {_why(exc)}")
    return 0
