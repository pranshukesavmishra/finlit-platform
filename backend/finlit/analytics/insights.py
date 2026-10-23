"""Rule-based, plain-English research notes. Every sentence is traceable to a number.

Wording follows the compliance rule: research language, never advice
("Research summary, not a recommendation").
"""

from __future__ import annotations

from typing import Dict, List, Optional


def _f(value: Optional[float], digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def notes(m: Dict[str, Optional[float]], ownership_latest: List[dict]) -> dict:
    strengths: List[dict] = []
    watchouts: List[dict] = []

    def add(bucket, key, title, text, metric_value):
        bucket.append({"key": key, "title": title, "text": text, "value": metric_value})

    roe = m.get("roe")
    if roe is not None and roe >= 15:
        add(strengths, "roe", "High return on equity", f"ROE of {_f(roe)}% — the business earns well on shareholders' money.", roe)
    elif roe is not None and roe < 8:
        add(watchouts, "roe", "Low return on equity", f"ROE of {_f(roe)}% is below what most investors look for (15%+).", roe)

    cfo = m.get("cfo_to_pat")
    if cfo is not None and cfo >= 100:
        add(strengths, "cfo_to_pat", "Profit backed by cash", f"Operating cash flow was {_f(cfo, 0)}% of reported profit.", cfo)
    elif cfo is not None and cfo < 70:
        add(watchouts, "cfo_to_pat", "Weak cash conversion", f"Only {_f(cfo, 0)}% of reported profit turned into operating cash.", cfo)

    de = m.get("debt_to_equity")
    if de is not None and de <= 0.5:
        add(strengths, "debt_to_equity", "Conservative debt", f"Debt is {_f(de, 2)}× equity.", de)
    elif de is not None and de > 1:
        add(watchouts, "debt_to_equity", "High debt", f"Debt is {_f(de, 2)}× equity.", de)

    ic = m.get("interest_coverage")
    if ic is not None and ic < 2:
        add(watchouts, "interest_coverage", "Thin interest cover", f"Operating profit covers interest only {_f(ic)} times.", ic)

    exc = m.get("exceptional_share")
    if exc is not None and exc >= 50:
        add(watchouts, "exceptional_share", "Profit includes a large one-off gain", f"One-off items are {_f(exc, 0)}% of pre-tax profit, so this year's profit and the ratios built on it overstate what the business earns regularly.", exc)

    sales, profit = m.get("sales_cagr"), m.get("profit_cagr")
    if sales is not None and sales >= 10:
        add(strengths, "sales_cagr", "Steady sales growth", f"Sales compounded at {_f(sales)}% a year over {int(m.get('sales_cagr_years') or 5)} years.", sales)
    elif sales is not None and sales < 4:
        add(watchouts, "sales_cagr", "Slow sales growth", f"Sales grew only {_f(sales)}% a year over {int(m.get('sales_cagr_years') or 5)} years.", sales)
    if sales is not None and profit is not None and profit < sales - 3:
        add(watchouts, "profit_cagr", "Profit lagging sales", f"Profit grew {_f(profit)}% a year against {_f(sales)}% for sales — margins are under pressure.", profit)

    npm = m.get("npm")
    if npm is not None and npm < 5:
        add(watchouts, "npm", "Thin margins", f"Net margin of {_f(npm)}% leaves little cushion if input costs swing.", npm)

    pe, sector_pe = m.get("pe"), m.get("sector_pe")
    if pe is not None and sector_pe and pe < sector_pe * 0.8:
        add(strengths, "pe", "Priced below sector", f"P/E of {_f(pe)}× against {_f(sector_pe)}× for the sector.", pe)
    elif pe is not None and sector_pe and pe > sector_pe * 1.3:
        add(watchouts, "pe", "Priced above sector", f"P/E of {_f(pe)}× against {_f(sector_pe)}× for the sector.", pe)

    dy = m.get("dividend_yield")
    if dy is not None and dy >= 3:
        add(strengths, "dividend_yield", "Strong dividend yield", f"Dividends paid over the last 12 months are {_f(dy, 2)}% of today's price.", dy)

    cr = m.get("current_ratio")
    if cr is not None and cr < 1:
        add(watchouts, "current_ratio", "Short-term bills exceed short-term assets", f"Current ratio of {_f(cr, 2)}.", cr)

    rsi, vs200 = m.get("rsi14"), m.get("vsEma200Pct")
    if rsi is not None and rsi < 30:
        add(watchouts, "rsi14", "Heavy recent selling", f"RSI of {_f(rsi)} is in the oversold zone.", rsi)
    elif rsi is not None and rsi > 70:
        add(watchouts, "rsi14", "Heavy recent buying", f"RSI of {_f(rsi)} is in the overbought zone.", rsi)
    if vs200 is not None and vs200 < -5:
        add(watchouts, "vsEma200Pct", "Below long-term trend", f"Price is {_f(abs(vs200))}% below its 200-day average.", vs200)
    elif vs200 is not None and vs200 > 5:
        add(strengths, "vsEma200Pct", "Above long-term trend", f"Price is {_f(vs200)}% above its 200-day average.", vs200)

    for item in ownership_latest or []:
        change = item.get("change1yPts")
        if item["key"] == "fii" and change is not None and change <= -2:
            add(watchouts, "fii", "Foreign investors selling", f"FII holding fell {_f(abs(change), 2)} pts over the year.", change)
        if item["key"] == "promoters" and change is not None and change <= -1:
            add(watchouts, "promoters", "Promoters reduced stake", f"Promoter holding fell {_f(abs(change), 2)} pts over the year.", change)
        if item["key"] == "dii" and change is not None and change >= 2:
            add(strengths, "dii", "Domestic institutions buying", f"DII holding rose {_f(change, 2)} pts over the year.", change)

    return {"strengths": strengths[:5], "watchouts": watchouts[:5]}


def thesis(score: dict, m: Dict[str, Optional[float]]) -> Optional[str]:
    pillars = {p["key"]: p for p in score.get("pillars", []) if p.get("score") is not None}
    if not pillars:
        return None
    quality = pillars.get("quality", {}).get("score")
    technical = pillars.get("technical", {}).get("score")
    growth = pillars.get("growth", {}).get("score")
    lead = "A high-quality" if quality and quality >= 78 else "A sound" if quality and quality >= 62 else "A mixed-quality" if quality and quality >= 45 else "A weak"
    body = "business"
    if growth is not None:
        body += " with strong growth" if growth >= 78 else " with steady growth" if growth >= 62 else " with modest growth" if growth >= 45 else " with weak growth"
    tail = ""
    if technical is not None:
        tail = "; the share price trend is strong." if technical >= 78 else "; the share price trend is healthy." if technical >= 62 else "; the share price trend is mixed." if technical >= 45 else "; the share price has been weak recently."
    return f"{lead} {body}{tail or '.'}"
