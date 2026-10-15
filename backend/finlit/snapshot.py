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

from .analytics import derived, indicators, insights, returns, scoring
from .normalize import events, market, ownership, ratios, statements
from .normalize.common import parse_date
from .normalize.glossary import describe

SNAPSHOT_VERSION = 1
SECTIONS = ("summary", "financials", "ratios", "price", "ownership", "events", "segments", "peers")
# Chart ranges are cut at ingest time so the API only ever streams stored bytes.
# Short ranges keep daily candles; long ranges are downsampled to weekly closes.
PRICE_RANGES = {"1M": (31, "daily"), "6M": (183, "daily"), "1Y": (366, "daily"),
                "3Y": (1096, "weekly"), "5Y": (1827, "weekly"), "MAX": (None, "weekly")}

# Shown as the headline metric strip on the summary card, in this order.
KEY_METRICS = ["market_cap", "pe", "pb", "dividend_yield", "roe", "roce", "debt_to_equity",
               "sales_cagr", "profit_cagr", "opm", "ev_ebitda", "dividend_payout"]


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
    last_day = parse_date(history["t"][-1]) if history["t"] else None
    price = live.get("price") or market.latest_close(history)
    as_of: Optional[date] = parse_date(live.get("asOf")) or last_day
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
    computed.update(ratios.price_ratio_latest(bundle.get("daily_price_ratios")))
    ratio_view = ratios.build_ratios(family_payloads, computed)

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
        "dividendsByFY": events.dividends_by_fiscal_year(actions),
        "dividendYieldTtm": dividend_yield,
        "announcements": events.announcements(bundle.get("announcements")),
    }

    ranges = {}
    for label, (days, grain) in PRICE_RANGES.items():
        cut = market.slice_since(history, (last_day - timedelta(days=days)).isoformat()) if days and last_day else history
        series = cut if grain == "daily" else market.weekly(cut)
        ranges[f"price-{label}"] = {"meta": meta, "range": label, "grain": grain,
                                    "series": {k: series[k] for k in ("t", "o", "h", "l", "c", "v") if k in series}}

    return {
        **ranges,
        "summary": summary,
        "financials": financials,
        "ratios": ratio_section,
        "price": price_section,
        "ownership": {"meta": meta, **holding},
        "events": events_section,
        "segments": {"meta": meta, **events.segments(bundle.get("segments"))},
        "peers": {"meta": meta, "symbols": peers},
    }


def score_row(sections: Dict[str, dict]) -> dict:
    """Flat row for the `scores` table (screener filters read this, not the JSON)."""
    s = sections["summary"]
    metrics = {m["key"]: m["value"] for m in s["keyMetrics"]}
    pillars = {p["key"]: p["score"] for p in s["score"]["pillars"]}
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
    }
