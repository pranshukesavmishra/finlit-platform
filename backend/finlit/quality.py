"""Data quality gate. Every snapshot is checked before it is published.

- critical: the data is very likely wrong (units, parsing, identities broken). The worker refuses to
  publish and keeps serving the last good snapshot, so users never see a broken page.
- warning:  publishable, but the page shows a "data note" and the issue is logged for review.
- The accounting identities below hold exactly on real FinEdge data (RELIANCE FY26: assets 1,165,809 =
  equity 566,235 + liabilities 599,574; price × shares = market cap within 0.01%), so they make good
  tripwires for unit and parsing bugs like the ones on the current site.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from .normalize.common import parse_date

CRITICAL, WARNING = "critical", "warning"


def _latest(table: dict, key: str) -> Optional[float]:
    values = [v for v in ((table or {}).get("rows", {}).get(key) or []) if v is not None]
    return values[-1] if values else None


def _aligned_latest(table: dict, *keys: str):
    """Latest period where every key has a value."""
    rows = (table or {}).get("rows", {})
    columns = [rows.get(k) or [] for k in keys]
    for i in range(min((len(c) for c in columns), default=0) - 1, -1, -1):
        values = [c[i] for c in columns]
        if all(v is not None for v in values):
            return (table.get("periods") or [None] * (i + 1))[i], values
    return None, None


def _gap(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-9) * 100


def run(sections: Dict[str, dict], today: Optional[date] = None) -> dict:
    today = today or date.today()
    issues: List[dict] = []
    passed: List[str] = []

    def check(key: str, ok: bool, severity: str, message: str, **detail):
        if ok:
            passed.append(key)
        else:
            issues.append({"key": key, "severity": severity, "message": message, **detail})

    summary = sections.get("summary", {})
    yearly = sections.get("financials", {}).get("yearly", {})
    pl, bs = yearly.get("pl", {}), yearly.get("bs", {})
    quote = summary.get("quote", {})
    price = quote.get("price")
    is_bank = summary.get("dataQuality", {}).get("isBank")

    # ---- prices
    if price is not None:
        check("price_positive", price > 0, CRITICAL, "Share price is zero or negative.", value=price)
    daily = sections.get("price", {}).get("daily", {})
    closes, days = daily.get("c") or [], daily.get("t") or []
    if price and closes:
        gap = _gap(price, closes[-1])
        check("quote_matches_history", gap <= 20, WARNING,
              f"Live price differs from the last daily close by {gap:.1f}%.", value=round(gap, 2))
    if days:
        age = (today - parse_date(days[-1])).days
        check("price_fresh", age <= 7, WARNING, f"Latest daily price is {age} days old.", value=age)
        removed = len(daily.get("removedBadTicks") or [])
        check("few_bad_ticks", removed <= max(3, len(days) // 100), WARNING,
              f"{removed} bad price points were removed from the chart.", value=removed)

    # ---- accounting identities
    period, values = _aligned_latest(bs, "total_assets", "total_equity", "total_liabilities")
    if values:
        assets, equity, liabilities = values
        minority = _latest(bs, "minority_interest") or 0
        candidates = [_gap(assets, equity + liabilities), _gap(assets, equity + liabilities + minority)]
        gap = min(candidates)
        check("balance_sheet_balances", gap <= 2, CRITICAL if gap > 10 else WARNING,
              f"{period}: assets differ from equity + liabilities by {gap:.1f}%.", value=round(gap, 2), period=period)

    period, values = _aligned_latest(pl, "eps", "diluted_shares_cr", "net_profit")
    if values and values[2] > 0 and values[0] > 0:
        eps, shares, profit = values
        gap = _gap(eps * shares, profit)
        check("eps_matches_profit", gap <= 15, WARNING,
              f"{period}: EPS × shares differs from net profit by {gap:.1f}%.", value=round(gap, 2), period=period)

    shares = _latest(pl, "diluted_shares_cr")
    market_cap = quote.get("marketCapCr")
    if price and shares and market_cap:
        gap = _gap(price * shares, market_cap)
        # A 10x or 100x gap means a crore/lakh/rupee unit slip somewhere.
        check("market_cap_consistent", gap <= 25, CRITICAL if gap > 60 else WARNING,
              f"Price × shares differs from market cap by {gap:.1f}%.", value=round(gap, 2))

    # ---- statements present and plausible
    revenue = _latest(pl, "revenue")
    check("has_revenue", revenue is not None and (revenue > 0 or is_bank), WARNING, "No positive revenue in the latest year.")
    profit, income = _latest(pl, "net_profit"), _latest(pl, "total_income")
    if profit is not None and income:
        check("profit_below_income", profit <= income * 1.05 or profit < 0, WARNING,
              "Net profit is larger than total income (possible exceptional gain or parsing issue).")
    fy = summary.get("dataQuality", {}).get("fundamentalsAsOf")
    if fy and fy.startswith("FY"):
        fy_end = date(2000 + int(fy[2:]), 3, 31)
        months = (today.year - fy_end.year) * 12 + today.month - fy_end.month
        check("fundamentals_fresh", months <= 18, WARNING, f"Latest annual results are {fy} ({months} months old).", value=months)

    # ---- ratios and returns within believable ranges
    metrics = {m["key"]: m["value"] for m in summary.get("keyMetrics", [])}
    bounds = {"pe": (0, 1000), "pb": (0, 200), "dividend_yield": (0, 20), "roe": (-200, 200), "roce": (-200, 200),
              "dividend_payout": (0, 300), "debt_to_equity": (0, 50)}
    for key, (low, high) in bounds.items():
        value = metrics.get(key)
        if value is not None:
            check(f"range_{key}", low <= value <= high, WARNING, f"{key} = {value} is outside the believable range.", value=value)
    for r in summary.get("returns", []):
        if r.get("dividend") is not None:
            # The current site showed 89% dividend return at every horizon; a real one is a few % a year.
            years = {"1M": 1 / 12, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5}.get(r["period"], 1)
            check(f"dividend_return_{r['period']}", r["dividend"] <= 15 * max(years, 1), CRITICAL,
                  f"{r['period']} dividend return of {r['dividend']}% is not believable.", value=r["dividend"])

    # ---- composition data adds up
    holdings = sections.get("ownership", {}).get("latest") or []
    if holdings:
        total = sum(h.get("value") or 0 for h in holdings)
        check("shareholding_sums_to_100", abs(total - 100) <= 1.5, WARNING, f"Shareholding adds up to {total:.2f}%.", value=round(total, 2))
    segments = sections.get("segments", {}).get("latest") or []
    if segments:
        total = sum(s.get("sharePct") or 0 for s in segments)
        check("segments_sum_to_100", abs(total - 100) <= 1, WARNING, f"Segment shares add up to {total:.2f}%.", value=round(total, 2))

    critical = [i for i in issues if i["severity"] == CRITICAL]
    return {
        "status": "rejected" if critical else ("warnings" if issues else "ok"),
        "passed": len(passed),
        "total": len(passed) + len(issues),
        "issues": issues,
    }
