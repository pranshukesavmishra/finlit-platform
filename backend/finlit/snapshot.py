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

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import quality as quality_checks
from .analytics import derived, indicators, insights, pricestats, returns, scoring
from .normalize import events, market, ownership, ratios, statements
from .normalize.common import parse_date
from .normalize.glossary import describe

SNAPSHOT_VERSION = 1
SECTIONS = ("summary", "financials", "ratios", "price", "ownership", "events", "segments", "peers", "stats")
# Chart ranges are cut at ingest time so the API only ever streams stored bytes.
# Short ranges keep daily candles; long ranges are downsampled to weekly closes.
PRICE_RANGES = {"1M": (31, "daily"), "6M": (183, "daily"), "1Y": (366, "daily"),
                "3Y": (1096, "weekly"), "5Y": (1827, "weekly"), "MAX": (None, "weekly")}

# Shown as the headline metric strip on the summary card, in this order.
KEY_METRICS = ["market_cap", "pe", "pb", "dividend_yield", "roe", "roce", "debt_to_equity",
               "sales_cagr", "profit_cagr", "operating_margin", "ev_ebitda", "dividend_payout"]


def _rows(payload: Any, key: str = "financials") -> List[dict]:
    if isinstance(payload, dict):
        value = payload.get(key)
        return value if isinstance(value, list) else []
    return payload if isinstance(payload, list) else []


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
    as_of: Optional[date] = parse_date(live.get("asOf")) or (parse_date(history["t"][-1]) if history["t"] else None)
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
    computed = derived.compute(pl, bs, cf, first_pass["latest"], bundle.get("basic"), market_cap, dividend_yield)
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
        "sales_cagr": f"{years}Y" if years else None, "profit_cagr": f"{computed.get('profit_cagr_years')}Y" if computed.get("profit_cagr_years") else None,
    }
    ratio_view = ratios.build_ratios(family_payloads, computed, {k: v for k, v in derived_periods.items() if v})

    metrics: Dict[str, Optional[float]] = {k: v["value"] for k, v in ratio_view["latest"].items()}
    metrics.update({k: v for k, v in computed.items() if v is not None})
    metrics.update({k: technical.get(k) for k in ("vsEma50Pct", "vsEma200Pct", "rsi14")})

    score = scoring.score(metrics)
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
        "isBank": statements.is_bank(pl_rows),
        "priceAsOf": history["t"][-1] if history["t"] else None,
        "fundamentalsAsOf": (pl.get("periods") or [None])[-1],
    }

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

    summary = {
        "meta": meta,
        "profile": prof,
        "quote": {**live, "price": price, "asOf": live.get("asOf") or quality["priceAsOf"]},
        "range52": range52,
        "sparkline": {"t": spark["t"], "c": spark["c"]},
        "score": {"overall": score["overall"], "band": score["band"], "model": score["model"],
                  "pillars": [{k: p[k] for k in ("key", "label", "score", "band", "coverage")} for p in score["pillars"]]},
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
        "glossary": {k: describe(k) for k in ratio_view["latest"]},
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
    return sections


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
    }
