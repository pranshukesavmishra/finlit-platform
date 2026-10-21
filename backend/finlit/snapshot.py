"""Turn one raw FinEdge bundle into the precomputed sections the API serves.

The worker calls `build(bundle)` after fetching; the API never computes anything per request.
Each section is small enough to send on its own, so the page can paint `summary` first
(target < 20 KB) and stream the rest in parallel.

Bundle keys (raw FinEdge payloads, any may be missing):
    symbol, statement ("consolidated" | "standalone"), symbol_row,
    profile, peers, quote, pl_annual, bs_annual, cf_annual, pl_quarterly, segments,
    ratios_pr, ratios_le, ratios_li, ratios_ef, growth, basic,
    daily_quotes, daily_price_ratios, annual_price_ratios,
    shareholding, dividends, corporate_actions, announcements
"""

from __future__ import annotations

import logging

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import coverage
from . import quality as quality_checks
from .analytics import derived, indicators, insights, pricestats, returns, scoring
from .normalize import events, market, ownership, ratios, statements
from .normalize.common import parse_date
from .normalize.glossary import describe

SNAPSHOT_VERSION = 4   # 4: since-listing return, profitability ratios filled on the provider's definitions, discontinued-operations profit kept out of P/E, ROE and margins. 3: profit and equity attributable to shareholders, lender handling, calendar return windows, one EV. Older reports are rebuilt first.
SECTIONS = ("summary", "financials", "ratios", "price", "ownership", "events", "segments", "peers", "stats")
# Chart ranges are cut at ingest time so the API only ever streams stored bytes.
# Short ranges keep daily candles; long ranges are downsampled to weekly closes.
PRICE_RANGES = {"1M": (31, "daily"), "6M": (183, "daily"), "1Y": (366, "daily"),
                "3Y": (1096, "weekly"), "5Y": (1827, "weekly"), "MAX": (None, "weekly")}

# Shown as the headline metric strip on the summary card, in this order.
KEY_METRICS = ["market_cap", "pe", "pb", "dividend_yield", "roe", "roce", "debt_to_equity",
               "sales_cagr", "profit_cagr", "operating_margin", "ev_ebitda", "dividend_payout"]


from .screener import compute as screener_compute  # noqa: E402


def _rows(payload: Any, key: str = "financials") -> List[dict]:
    if isinstance(payload, dict):
        value = payload.get(key)
        return value if isinstance(value, list) else []
    return payload if isinstance(payload, list) else []


def _ordered_rows(rows: List[dict]) -> List[dict]:
    return sorted(rows, key=lambda r: r.get("year") or 0)


def _present(payload: Any) -> bool:
    if isinstance(payload, dict):
        return any(v not in (None, [], {}, "") for v in payload.values())
    return bool(payload)


def build(bundle: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, dict]:
    symbol = str(bundle["symbol"]).upper()
    statement = bundle.get("statement") or "consolidated"
    generated_at = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()

    # ---------------------------------------------------------------- statements
    pl_rows = _rows(bundle.get("pl_annual"))
    pl = statements.profit_and_loss(pl_rows, "yearly")
    bs = statements.balance_sheet(_rows(bundle.get("bs_annual")), "yearly")
    cf = statements.cash_flow(_rows(bundle.get("cf_annual")), "yearly")
    pl_q = statements.profit_and_loss(_rows(bundle.get("pl_quarterly")), "quarterly")

    # ---------------------------------------------------------------- market
    prof = market.profile(bundle.get("profile"), bundle.get("symbol_row"))
    live = market.quote(bundle.get("quote"), symbol)
    history = market.price_history(bundle.get("daily_quotes"))
    closes_by_day = dict(zip(history["t"], history["c"]))
    price = live.get("price") or market.latest_close(history)
    live_day = parse_date(live.get("asOf"))
    if live_day and live_day.year < 1990:  # FinEdge sends 0001-01-01 for quotes it has no date for
        live_day = None
    as_of: Optional[date] = live_day or (parse_date(history["t"][-1]) if history["t"] else None)
    # The live quote is newer than the last daily bar (end-of-day files land after the close). Add it as
    # a provisional bar so the header price, chart, returns and technicals all agree with each other.
    provisional = _append_live_bar(history, live, as_of)
    last_day = parse_date(history["t"][-1]) if history["t"] else None
    technical = indicators.technical_snapshot(history["c"])

    actions = events.corporate_actions(bundle.get("dividends"), bundle.get("corporate_actions"))
    dividend_yield = returns.dividend_yield_ttm(actions, price, as_of)
    trailing = returns.trailing_returns(history, actions)
    holding = ownership.shareholding(bundle.get("shareholding"))

    # ---------------------------------------------------------------- ratios & derived metrics
    family_payloads = {
        "pr": bundle.get("ratios_pr"), "le": bundle.get("ratios_le"), "li": bundle.get("ratios_li"),
        "ef": bundle.get("ratios_ef"), "basic": bundle.get("basic"), "gr": bundle.get("growth"),
    }
    first_pass = ratios.build_ratios(family_payloads)
    market_cap = live.get("marketCapCr") or prof.get("marketCapCr")
    lender = statements.is_bank(pl_rows)
    computed = derived.compute(statements.calc_view(pl), bs, cf, first_pass["latest"], bundle.get("basic"), market_cap, dividend_yield, lender, statements.calc_view(pl_q))
    growth_from_quarter = computed.pop("growth_basis", None) == "quarter"
    computed.update(_valuation_at_price(bundle.get("daily_price_ratios"), closes_by_day, price))
    dividends_fy = events.dividends_by_fiscal_year(actions)
    fy = (pl.get("periods") or [None])[-1]
    computed["dividend_payout"] = _payout(dividends_fy, pl, fy)
    years = computed.get("sales_cagr_years")
    derived_periods = {
        **{k: "Today" for k in ("pe", "pb", "ps", "pfcf", "market_cap")},
        "dividend_yield": "TTM", "ev_ebitda": "TTM",
        **{k: fy for k in ("opm", "npm", "cfo_to_pat", "fcf_to_pat", "sales_growth_latest", "profit_growth_latest",
                           "dividend_payout") if fy},
        "liabilities_to_assets": (bs.get("periods") or [None])[-1],
        "revenue_cagr_3y": "3Y", "revenue_cagr_5y": "5Y",
        "sales_cagr": f"{years}Y" if years else None, "profit_cagr": f"{computed.get('profit_cagr_years')}Y" if computed.get("profit_cagr_years") else None,
    }
    if growth_from_quarter:   # growth measured over one quarter says so, instead of passing for a full-year figure
        derived_periods.update({"sales_growth_latest": "Latest quarter vs year ago", "profit_growth_latest": "Latest quarter vs year ago"})
    ratio_view = ratios.build_ratios(family_payloads, computed, {k: v for k, v in derived_periods.items() if v})
    _fill_profitability(ratio_view, pl, bs, lender)
    _adjust_for_discontinued(ratio_view, pl, pl_q, bs, market_cap)
    _apply_applicability(ratio_view, lender, statements.latest(bs, "total_equity"))

    metrics: Dict[str, Optional[float]] = {k: v["value"] for k, v in ratio_view["latest"].items()}
    metrics.update({k: v for k, v in computed.items() if v is not None})
    metrics.update({k: technical.get(k) for k in ("vsEma50Pct", "vsEma200Pct", "rsi14")})

    score = scoring.score(metrics)
    _explain_gaps(score, lender=lender, annual=len(pl.get("periods") or []), quarterly=len(pl_q.get("periods") or []), days=len(history["t"]))
    notes = insights.notes(metrics, holding.get("latest") or [])
    peers = events.peer_symbols(bundle.get("peers"), symbol)

    # ---------------------------------------------------------------- data quality
    expected = ("profile", "quote", "pl_annual", "bs_annual", "cf_annual", "pl_quarterly", "daily_quotes",
                "ratios_pr", "shareholding")
    quality = {
        "missing": [k for k in expected if not _present(bundle.get(k))],
        "notes": ratio_view.get("notes", []),
        "provisionalLastBar": provisional,
        "removedBadTicks": history["removedBadTicks"],
        "statement": statement,
        "isBank": lender,
        "priceAsOf": history["t"][-1] if history["t"] else None,
        "fundamentalsAsOf": (pl.get("periods") or [None])[-1],
        # Cross-checks of the statements against their own components (empty when everything ties out), see normalize/statements.py
        "plReconcile": statements.reconcile(pl_rows),
        "epsSignRepaired": pl.get("epsSignRepaired") or [],
        # Years where consolidated and standalone revenue differ by more than 1% (the worker fetches the other basis when it can)
        "basisGaps": statements.basis_gaps(pl_rows, _rows(bundle.get("pl_annual_standalone"))) if statement == "consolidated" and bundle.get("pl_annual_standalone") else [],
    }
    if quality["plReconcile"]:
        logging.getLogger("finlit.snapshot").warning("P&L does not tie out for %s: %s", symbol, quality["plReconcile"][:6])
    if quality["basisGaps"]:
        logging.getLogger("finlit.snapshot").warning("consolidated vs standalone revenue differ >1%% for %s: %s", symbol, quality["basisGaps"])

    meta = {"symbol": symbol, "statement": statement, "generatedAt": generated_at,
            "version": SNAPSHOT_VERSION, "scoreModel": score["model"]}

    one_year = market.slice_since(history, f"{(last_day or date.today()).year - 1}-{(last_day or date.today()):%m-%d}")
    spark = market.weekly(one_year)
    range52 = {
        "high": live.get("high52") or (max(one_year["c"]) if one_year["c"] else None),
        "low": live.get("low52") or (min(one_year["c"]) if one_year["c"] else None),
    }

    key_metrics = []
    for key in KEY_METRICS:
        entry = ratio_view["latest"].get(key)
        if entry:
            key_metrics.append({"key": key, "value": entry["value"], "unit": entry.get("unit"),
                                "label": entry.get("label"), "period": entry.get("period")})

    if pl_rows and not (pl.get("rows") or {}).get("revenue"):   # the provider has results but none of the lines we know for sales: say so, so the mapping can be added
        quality["notes"] = [*quality.get("notes", []), "Sales could not be read from this company's results format."]
        logging.getLogger("finlit.snapshot").warning("revenue not mapped for %s; fields: %s", symbol, sorted(k for k, v in _ordered_rows(pl_rows)[-1].items() if v not in (None, 0, ""))[:40])

    summary = {
        "meta": meta,
        "profile": prof,
        "quote": {**live, "price": price, "asOf": live.get("asOf") or quality["priceAsOf"]},
        "range52": range52,
        "sparkline": {"t": spark["t"], "c": spark["c"]},
        "score": {"overall": score["overall"], "band": score["band"], "model": score["model"],
                  "pillars": [{k: p[k] for k in ("key", "label", "score", "band", "coverage", "reason") if k in p} for p in score["pillars"]]},
        "thesis": insights.thesis(score, metrics),
        "strengths": notes["strengths"],
        "watchouts": notes["watchouts"],
        "keyMetrics": key_metrics,
        "returns": trailing,
        "dataQuality": quality,
    }

    financials = {"meta": meta, "unit": "Cr", "yearly": {"pl": pl, "bs": bs, "cf": cf}, "quarterly": {"pl": pl_q}}

    ratio_section = {
        "meta": meta,
        **ratio_view,
        "valuationHistory": ratios.valuation_history(bundle.get("annual_price_ratios")),
        "score": score,  # full pillar inputs for the "how this score is built" drawer
        "glossary": {k: describe(k) for k in {*ratio_view["latest"], *ratio_view["history"]["rows"], "rsi14", *(i["key"] for p in score["pillars"] for i in p["inputs"])}},
    }

    price_section = {"meta": meta, "daily": history, "technical": technical, "returns": trailing}

    events_section = {
        "meta": meta,
        "actions": actions,
        "dividendsByFY": dividends_fy,
        "dividendYieldTtm": dividend_yield,
        "announcements": events.announcements(bundle.get("announcements")),
    }

    # Moving averages are computed once on the full daily history, then sampled on each range's dates,
    # so a 1M chart still shows a true 200-day average.
    ema50 = dict(zip(history["t"], indicators.ema(history["c"], 50))) if history["c"] else {}
    ema200 = dict(zip(history["t"], indicators.ema(history["c"], 200))) if history["c"] else {}
    first_day = parse_date(history["t"][0]) if history["t"] else None
    ranges = {}
    for label, (days, grain) in PRICE_RANGES.items():
        start = last_day - timedelta(days=days) if days and last_day else first_day
        cut = market.slice_since(history, start.isoformat()) if days and last_day else history
        series = cut if grain == "daily" else market.weekly(cut)
        out = {k: series[k] for k in ("t", "o", "h", "l", "c", "v") if k in series}
        out["ema50"] = [_r(ema50.get(t)) for t in series["t"]]
        out["ema200"] = [_r(ema200.get(t)) for t in series["t"]]
        ranges[f"price-{label}"] = {
            "meta": meta, "range": label, "grain": grain, "technical": technical, "series": out,
            # False when history does not reach back to the start of the range (e.g. 5Y on a 2-year listing).
            "complete": bool(first_day and start and first_day <= start + timedelta(days=7)) or label == "MAX",
            "startsAt": series["t"][0] if series["t"] else None,
            "provisionalLastBar": provisional,
        }

    sections = {
        **ranges,
        "summary": summary,
        "financials": financials,
        "ratios": ratio_section,
        "price": price_section,
        "ownership": {"meta": meta, **holding},
        "events": events_section,
        "segments": {"meta": meta, **events.segments(bundle.get("segments"))},
        "peers": {"meta": meta, "symbols": peers},
        "stats": {"meta": meta, **pricestats.build(history)},
    }
    summary["dataQuality"]["checks"] = quality_checks.run(sections, today=(now or datetime.now(timezone.utc)).date())
    summary["dataQuality"]["coverage"] = coverage.assess(bundle, sections)   # what the provider sent against what this report shows
    return sections


# Ratios that mean nothing for a lender (a bank or NBFC): its "debt" is its raw material, it has no gross margin or working capital,
# and its operating cash flow moves with deposits and loans. They are neither shown nor scored for lenders.
NOT_FOR_LENDERS = ("gross_margin", "ebitda_margin", "ebit_margin", "current_ratio", "quick_ratio", "asset_turnover", "debt_to_equity", "lt_debt_to_equity",
                   "debt_to_assets", "interest_coverage", "debt_to_fcf", "debtor_days", "inventory_days", "payable_days", "cash_conversion_cycle",
                   "cfo_to_pat", "fcf_to_pat", "ev_ebitda", "pfcf", "liabilities_to_assets")
# With zero or negative equity these ratios flip sign or explode and say the opposite of the truth.
NOT_FOR_NEGATIVE_EQUITY = ("roe", "debt_to_equity", "lt_debt_to_equity", "financial_leverage", "pb")


def _apply_applicability(ratio_view: dict, lender: bool, equity: Optional[float]) -> None:
    drop = set(NOT_FOR_LENDERS if lender else ()) | set(NOT_FOR_NEGATIVE_EQUITY if equity is not None and equity <= 0 else ())
    if not drop:
        return
    for k in drop:
        ratio_view["latest"].pop(k, None)
        ratio_view["history"]["rows"].pop(k, None)
    for g in ratio_view.get("groups", []):
        g["keys"] = [k for k in g["keys"] if k not in drop]


PROFIT_FILL_CELLS = ("roe",)   # same definition as the provider's (profit over closing equity), so single missing years can be filled safely


def _fill_profitability(ratio_view: dict, pl: dict, bs: dict, lender: bool) -> None:
    """The provider leaves some margin and return ratios out for some companies (and some single years). Where our own statements hold the
    figures, work them out, so the profitability table is as complete as the company's statements allow. A row the provider supplies is never
    replaced: its blank years are filled only for ratios defined the same way (return on equity); an absent row is filled whole."""
    hist = ratio_view.get("history") or {}
    periods, rows = hist.get("periods") or [], hist.setdefault("rows", {})
    if not periods:
        return
    def series(table: dict, key: str) -> Dict[str, Optional[float]]:
        return dict(zip(table.get("periods") or [], (table.get("rows") or {}).get(key) or []))
    rev, tot, oth = series(pl, "revenue"), series(pl, "total_income"), series(pl, "other_income")
    # The provider measures margins against TOTAL INCOME (sales plus other income): checked on hundreds of company-years, net and pre-tax
    # margin match 99%, operating margin is (operating profit - depreciation + other income) over total income. Same definitions here, so a
    # filled year sits on the same scale as the provider's other years.
    inc = {p: tot.get(p) or ((rev.get(p) or 0) + (oth.get(p) or 0) or None) for p in periods}
    op, dep, pbt, fin, tax, np_ = series(pl, "operating_profit"), series(pl, "depreciation"), series(pl, "profit_before_tax"), series(pl, "finance_costs"), series(pl, "tax"), series(pl, "net_profit")
    eq, assets, cl = series(bs, "total_equity"), series(bs, "total_assets"), series(bs, "current_liabilities")

    def pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return round(a / b * 100, 2) if a is not None and b else None

    def ebit(p: str) -> Optional[float]:
        return pbt[p] + fin[p] if pbt.get(p) is not None and fin.get(p) is not None else None
    calc = {
        "net_margin": lambda p: pct(np_.get(p), inc[p]),
        "pretax_margin": lambda p: pct(pbt.get(p), inc[p]),
        "operating_margin": lambda p: pct(op[p] - dep[p] + (oth.get(p) or 0), inc[p]) if op.get(p) is not None and dep.get(p) is not None else None,
        "effective_tax_rate": lambda p: pct(tax.get(p), pbt.get(p)) if (pbt.get(p) or 0) > 0 and tax.get(p) is not None else None,
        "ebit_margin": lambda p: pct(ebit(p), inc[p]) if not lender else None,
        "ebitda_margin": lambda p: pct(ebit(p) + dep[p], inc[p]) if not lender and ebit(p) is not None and dep.get(p) is not None else None,
        "roe": lambda p: pct(np_.get(p), eq.get(p)) if (eq.get(p) or 0) > 0 else None,
        "roa": lambda p: pct(np_.get(p), assets.get(p)),
        "roce": lambda p: pct(ebit(p), assets[p] - cl[p]) if not lender and ebit(p) is not None and assets.get(p) is not None and cl.get(p) is not None and assets[p] - cl[p] > 0 else None,
    }
    filled: List[str] = []
    for key, fn in calc.items():
        have = rows.get(key)
        if have and any(v is not None for v in have):
            if key not in PROFIT_FILL_CELLS:
                continue
            new = [v if v is not None else fn(p) for v, p in zip(have, periods)]
        else:
            new = [fn(p) for p in periods]
        if any(v is not None for v in new) and new != (have or []):
            rows[key] = new
            filled.append(key)
    if filled:
        ratio_view.setdefault("notes", []).append("Some profitability ratios were worked out by FinLit from the company's own statements because the data provider did not send them: " + ", ".join(k.replace("_", " ") for k in filled) + ".")


def _adjust_for_discontinued(ratio_view: dict, pl: dict, pl_q: dict, bs: dict, market_cap: Optional[float]) -> None:
    """When profit from discontinued operations is material (a demerger gain, a sold business), the provider's P/E, return on equity, return on
    assets and net margin are inflated by profit that will not come back (Tata Motors FY26: a P/E of 1.3 and ROE of 71% on a loss-making
    continuing business). Replace those years with the continuing-operations figure and say so."""
    rows = pl.get("rows") or {}
    cont = rows.get("net_profit_continuing")
    if not cont:
        return
    hist = ratio_view.get("history") or {}
    periods, hrows = hist.get("periods") or [], hist.setdefault("rows", {})
    ppl = pl.get("periods") or []
    np_c = dict(zip(ppl, cont)); np_r = dict(zip(ppl, rows.get("net_profit") or []))
    changed: List[str] = []
    for p in periods:
        if p not in np_c or np_c[p] == np_r.get(p):
            continue
        for key, base in (("roe", dict(zip(bs.get("periods") or [], (bs.get("rows") or {}).get("total_equity") or []))),
                          ("roa", dict(zip(bs.get("periods") or [], (bs.get("rows") or {}).get("total_assets") or [])))):
            if key in hrows and base.get(p):
                hrows[key][periods.index(p)] = round(np_c[p] / base[p] * 100, 2) if (key != "roe" or base[p] > 0) else None
        inc = dict(zip(ppl, (rows.get("total_income") or rows.get("revenue") or [])))
        if "net_margin" in hrows and inc.get(p):
            hrows["net_margin"][periods.index(p)] = round(np_c[p] / inc[p] * 100, 2)
        changed.append(p)
    if not changed:
        return
    latest = ratio_view.get("latest") or {}
    for key in ("roe", "roa", "net_margin"):
        if key in latest and key in hrows and periods and periods[-1] in changed:
            v = hrows[key][-1]
            if v is None:
                latest.pop(key, None)
            else:
                latest[key]["value"] = v
    # P/E on the last four quarters' continuing profit (a loss means no P/E at all)
    qrows = pl_q.get("rows") or {}
    qn, qd = (qrows.get("net_profit") or [])[-4:], (qrows.get("discontinued_profit") or [])[-4:]
    if "pe" in latest and market_cap and len(qn) == 4 and None not in qn:
        ttm = sum(qn) - sum(x or 0 for x in qd)
        if sum(x or 0 for x in qd) and abs(sum(x or 0 for x in qd)) >= MATERIAL_DISCONTINUED_PE * abs(sum(qn)):
            if ttm > 0:
                latest["pe"]["value"] = round(market_cap / ttm, 2)
            else:
                latest.pop("pe", None)
    ratio_view.setdefault("notes", []).append(
        f"Profit from discontinued operations is excluded from return on equity, return on assets, net margin and P/E for {', '.join(changed)} "
        "(a one-off such as a demerger gain does not repeat). The reported net profit is unchanged in the statements.")


MATERIAL_DISCONTINUED_PE = 0.15


def _explain_gaps(score: dict, lender: bool, annual: int, quarterly: int, days: int) -> None:
    """Say why a pillar has no score, in plain words, instead of a bare "insufficient data"."""
    for p in score["pillars"]:
        if p["score"] is not None:
            continue
        if p["key"] == "balance" and lender:
            why = "Not scored for banks and lenders: deposits and loans are their business, not debt, so debt and cash-flow tests do not apply."
        elif p["key"] == "technical":
            why = (f"Listed only {days} trading days ago: the trend indicators need about three months of prices." if days < 60 else "The price history is too short for the trend indicators.")
        elif annual == 0 and quarterly == 0:
            why = "No results have been filed yet. This company was listed recently."
        elif p["key"] == "growth" and annual < 2 and quarterly < 5:
            why = "Growth needs two years of results (or five quarters); this company has filed " + ("one year so far." if annual == 1 else "less than that so far.")
        else:
            why = "The data provider has not reported the figures this needs."
        p["reason"] = why
    if score["overall"] is None:
        score["band"] = {"key": "insufficient", "label": "Not scored yet"}


def _r(value: Optional[float]) -> Optional[float]:
    return round(value, 2) if value is not None else None


def _append_live_bar(history: dict, live: dict, as_of: Optional[date]) -> bool:
    price = live.get("price")
    if not price or not as_of or not history["t"] or as_of <= parse_date(history["t"][-1]):
        return False
    history["t"].append(as_of.isoformat())
    history["o"].append(live.get("open") or price)
    history["h"].append(max(v for v in (live.get("high"), price) if v is not None))
    history["l"].append(min(v for v in (live.get("low"), price) if v is not None))
    history["c"].append(price)
    history["v"].append(live.get("volume"))
    return True


def _valuation_at_price(daily_ratios: Any, closes_by_day: Dict[str, float], price: Optional[float]) -> Dict[str, Optional[float]]:
    """FinEdge's daily P/E, P/B, P/S and P/FCF are computed at that day's close. Re-price them at the
    live quote so they agree with the price in the header (RELIANCE: 41.36x at ₹1,198.50 is 40.86x at ₹1,184)."""
    latest = ratios.price_ratio_latest(daily_ratios)
    as_of = latest.pop("asOf", None)
    close = closes_by_day.get(as_of) if as_of else None
    if not price or not close:
        return latest
    factor = price / close
    return {k: (round(v * factor, 2) if v is not None else None) for k, v in latest.items()}


def _payout(dividends_fy: dict, pl: dict, fy: Optional[str]) -> Optional[float]:
    """Dividend declared for the year ÷ EPS for the same year (RELIANCE FY26: ₹6 ÷ ₹32.40 = 18.5%)."""
    if not fy or fy not in dividends_fy.get("periods", []):
        return None
    dps = dividends_fy["dps"][dividends_fy["periods"].index(fy)]
    eps_row = dict(zip(pl.get("periods") or [], (pl.get("rows") or {}).get("eps") or []))
    eps = eps_row.get(fy)
    return round(dps / eps * 100, 2) if dps and eps and eps > 0 else None


def score_row(sections: Dict[str, dict]) -> dict:
    """Flat row for the `scores` table (screener filters read this, not the JSON)."""
    s = sections["summary"]
    metrics = {m["key"]: m["value"] for m in s["keyMetrics"]}
    pillars = {p["key"]: p["score"] for p in s["score"]["pillars"]}
    returns = {r["period"]: r.get("price") for r in s.get("returns", [])}
    return {
        "symbol": s["meta"]["symbol"],
        "statement": s["meta"]["statement"],
        "model": s["score"]["model"],
        "overall": s["score"]["overall"],
        "band": s["score"]["band"]["key"],
        **{f"pillar_{k}": v for k, v in pillars.items()},
        "price": s["quote"].get("price"),
        "market_cap": metrics.get("market_cap"),
        "pe": metrics.get("pe"),
        "roe": metrics.get("roe"),
        "dividend_yield": metrics.get("dividend_yield"),
        "sector": s["profile"].get("sector"),
        "name": s["profile"].get("name"),
        "pb": metrics.get("pb"),
        "roce": metrics.get("roce"),
        "debt_to_equity": metrics.get("debt_to_equity"),
        "sales_cagr": metrics.get("sales_cagr"),
        "profit_cagr": metrics.get("profit_cagr"),
        "operating_margin": metrics.get("operating_margin"),
        "change_pct": s["quote"].get("changePct"),
        "return_1m": returns.get("1M"),
        "return_1y": returns.get("1Y"),
        "industry": s["profile"].get("industry"),
        "macro_sector": s["profile"].get("macroSector"),
        "metrics": screener_compute.compute(sections),
    }
