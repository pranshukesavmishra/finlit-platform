"""Deterministic implementation of the owner's v3.6.1 rules, hardened for missing inputs.
No network, database or wall-clock dependencies. Includes the requested BANK
valuation fallbacks and owner-confirmed financial Quality replacements.
"""
import math
import statistics
try:
    from backend.premium_model_config import (
        GROUPS, PART_WEIGHTS, FILL_DEFAULT, FILL_OVERRIDES, TRADING_VALUE_STEPS,
        LOSS_ADJUSTED_FUNDAMENTAL, LOSS_FAMILY, LOSS_CAPS,
        DEEP_LOSS_MARGIN, DEEP_LOSS_EXTRA, LOSS_CAP_FLOOR,
        CAGR_MAX_YEARS, CAGR_PREFERRED_YEARS, CAGR_MIN_YEARS,
        MODEL_VERSION, BASELINE_VERSION, FILL_VERSION, RATING_BANDS,
        QUARTERS_STORED, QUARTERS_JUDGED, POINTS_PER_GOOD_QUARTER,
        MISS_PENALTY, STREAK_MAGNITUDE_SHARE, PROFIT_TURNAROUND_POINTS,
        LOSS_NARROWED_POINTS, CASH_LOSS_POINTS, IC_NOT_APPLICABLE_DE,
        PEG_CORE_GROUPS, PEG_MIN_PROFIT_STREAK, PEG_GROWTH_CAP,
        PROVISIONAL_BELOW, NOT_RATED_BELOW, PROVISIONAL_MIN_QUARTERS,
        FLAG_RED, FLAG_GREEN, PLEDGE_ALERT, VALUE_TRAP,
    )
except ImportError:
    from premium_model_config import (
        GROUPS, PART_WEIGHTS, FILL_DEFAULT, FILL_OVERRIDES, TRADING_VALUE_STEPS,
        LOSS_ADJUSTED_FUNDAMENTAL, LOSS_FAMILY, LOSS_CAPS,
        DEEP_LOSS_MARGIN, DEEP_LOSS_EXTRA, LOSS_CAP_FLOOR,
        CAGR_MAX_YEARS, CAGR_PREFERRED_YEARS, CAGR_MIN_YEARS,
        MODEL_VERSION, BASELINE_VERSION, FILL_VERSION, RATING_BANDS,
        QUARTERS_STORED, QUARTERS_JUDGED, POINTS_PER_GOOD_QUARTER,
        MISS_PENALTY, STREAK_MAGNITUDE_SHARE, PROFIT_TURNAROUND_POINTS,
        LOSS_NARROWED_POINTS, CASH_LOSS_POINTS, IC_NOT_APPLICABLE_DE,
        PEG_CORE_GROUPS, PEG_MIN_PROFIT_STREAK, PEG_GROWTH_CAP,
        PROVISIONAL_BELOW, NOT_RATED_BELOW, PROVISIONAL_MIN_QUARTERS,
        FLAG_RED, FLAG_GREEN, PLEDGE_ALERT, VALUE_TRAP,
    )

LABELS = {
    "SALES_STREAK": "Sales streak", "PROFIT_STREAK": "Profit streak",
    "SALES_GROWTH": "Sales growth (12 months)", "PROFIT_GROWTH": "Profit growth (12 months)",
    "SALES_CAGR": "Sales CAGR", "PROFIT_CAGR": "Profit CAGR", "MARGIN_CHANGE": "Operating margin change",
    "LOAN_GROWTH": "Loan growth", "NETWORTH_GROWTH": "Net worth growth",
    "DEBT_TO_EQUITY": "Debt / equity", "INTEREST_COVER": "Interest cover", "ROE": "Return on equity",
    "CASH_CONVERSION": "Cash conversion", "GROSS_NPA": "Gross NPA", "NET_NPA": "Net NPA",
    "CAPITAL_ADEQUACY": "Capital adequacy", "ROA": "Return on assets", "SOLVENCY": "Solvency ratio",
    "PE_VS_INDUSTRY": "P/E vs industry", "PE_VS_HISTORY": "P/E vs own history", "PEG": "PEG",
    "PB_VS_INDUSTRY": "P/B vs industry", "PB_VS_HISTORY": "P/B vs own history",
    "EV_EBITDA_VS_INDUSTRY": "EV/EBITDA vs industry", "VOLATILITY": "Annualised volatility",
    "BIGGEST_FALL": "Maximum drawdown (1 year)", "TRADING_VALUE": "Daily trading value (Cr)",
    "PLEDGE": "Promoter pledged shares",
}
PERCENT_METRICS = {"SALES_GROWTH", "PROFIT_GROWTH", "SALES_CAGR", "PROFIT_CAGR", "LOAN_GROWTH", "NETWORTH_GROWTH", "ROE", "GROSS_NPA", "NET_NPA", "CAPITAL_ADEQUACY", "ROA", "VOLATILITY", "BIGGEST_FALL", "PLEDGE"}
STATES = {"A": "Actual", "Z": "Negative / loss rule", "S": "Substituted", "F": "Filled", "N": "Not applicable", "L": "Not supplied"}

def num(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def scale(value, worst, best):
    return min(100., max(0., (value - worst) / (best - worst) * 100))


def fill(group, metric):
    return FILL_OVERRIDES.get(group, {}).get(metric, FILL_DEFAULT)


def complete_sum(values, length):
    values = values[-length:]
    return sum(values) if len(values) == length and all(num(v) is not None for v in values) else None


def recent(series, annual):
    if len(series) >= 8:
        return complete_sum(series[-4:], 4), complete_sum(series[-8:-4], 4), "Trailing 4 quarters vs previous 4 quarters"
    if len(series) >= 5:
        return num(series[-1]), num(series[-5]), "Latest quarter vs same quarter last year (short-history fallback)"
    return (num(annual[-1]), num(annual[-2]), "Latest financial year vs previous year (short-history fallback)") if len(annual) >= 2 else (None, None, "Insufficient history")


def reported_start(series):
    """Drop only leading empty slots; retain missing quarters inside a record."""
    first = next((i for i, value in enumerate(series) if num(value) is not None), len(series))
    return series[first:]


def cagr_window(annual):
    """Latest consecutive annual window: prefer 5 years, then 3, then available.

    The adapter retains missing calendar years as None. Never skip a missing
    year or move the end of the calculation to an older reporting period.
    """
    available = []
    for value in reversed(annual[-(CAGR_MAX_YEARS + 1):]):
        value = num(value)
        if value is None:
            break
        available.append(value)
    span = max(0, len(available) - 1)
    if span < CAGR_MIN_YEARS:
        return [], 0, span
    years = next((n for n in CAGR_PREFERRED_YEARS if span >= n), span)
    return list(reversed(available[:years + 1])), years, span


def growth(new, old, years, limits):
    if new is None or old is None:
        return None, None, "Missing comparison"
    if old <= 0:
        points = float(PROFIT_TURNAROUND_POINTS) if new > 0 else float(LOSS_NARROWED_POINTS) if new > old else 0.
        return points, None, "Loss to profit" if new > 0 else "Loss narrowed" if new > old else "Loss not narrowed"
    value = ((new / old) ** (1 / years) - 1) * 100 if new > 0 else -100.
    return scale(value, *limits), value, None


def loss_profile(d):
    """Owner loss tiers, without turning gaps in period-aligned inputs into zero."""
    profit_q, sales_q = d.get("net_profit_q", [])[-QUARTERS_STORED:], d.get("sales_q", [])[-QUARTERS_STORED:]
    profit_y, sales_y = d.get("net_profit_y", []), d.get("sales_y", [])
    if len(profit_q) >= 4:
        profit, sales, basis = complete_sum(profit_q, 4), complete_sum(sales_q, 4), "last 4 quarters"
    elif profit_y:
        profit, sales, basis = num(profit_y[-1]), num(sales_y[-1]) if sales_y else None, "latest year"
    else:
        profit, sales, basis = None, None, None
    last3, last5 = profit_y[-3:], profit_y[-5:]
    return {"ttmProfit": profit, "ttmSales": sales, "basis": basis,
            "lossNow": profit is not None and profit <= 0,
            "latestYearLoss": bool(profit_y) and num(profit_y[-1]) is not None and num(profit_y[-1]) <= 0,
            "lossYears3": sum(num(v) is not None and num(v) <= 0 for v in last3), "years3": len(last3),
            "lossYears5": sum(num(v) is not None and num(v) <= 0 for v in last5), "years5": len(last5),
            "netMarginPct": profit / sales * 100 if profit is not None and sales is not None and sales > 0 else None}


def loss_tier(group, profile):
    if profile["ttmProfit"] is None:
        return None, None
    caps = LOSS_CAPS[LOSS_FAMILY[group]]
    if profile["lossNow"]:
        chronic = profile["lossYears5"] >= 4 or (profile["years5"] >= 3 and profile["lossYears5"] == profile["years5"])
        tier = "chronic" if chronic else "persistent" if profile["lossYears3"] >= 2 else "loss"
        cap = caps[tier]
        if profile["netMarginPct"] is not None and profile["netMarginPct"] <= -DEEP_LOSS_MARGIN:
            tier, cap = tier + " + deep", max(LOSS_CAP_FLOOR, cap - DEEP_LOSS_EXTRA)
        return tier, cap
    if profile["latestYearLoss"] or profile["lossYears3"] >= 2:
        return "recovering", caps["recovering"]
    return None, None


def streak(series, best, group, metric, *, profit_rule=False, loss_now=False):
    series = series[-QUARTERS_STORED:]
    pairs = [(i, num(series[i]), num(series[i - 4])) for i in range(4, len(series))]
    judged = sum(new is not None and old is not None for _, new, old in pairs)
    fill_points = 0. if profit_rule and loss_now else fill(group, metric)
    if not judged:
        return (0. if profit_rule and loss_now else None), {
            "good": 0, "slips": 0, "judged": 0, "medianYoY": None,
            "lossFill": profit_rule and loss_now, "fillPoints": fill_points,
        }, (1. if profit_rule and loss_now else 0.)
    run, last_bad = [], None
    for index, new, old in reversed(pairs):
        if new is None or old is None:
            last_bad = None
            continue
        good = new > old and (new > 0 if profit_rule else True)
        if not good and last_bad == index + 1:
            run.pop()
            break
        p, yoy, _ = growth(new, old, 1, (0, best))
        run.append((good, p, yoy))
        last_bad = None if good else index
    while run and not run[-1][0]:
        run.pop()
    good = sum(item[0] for item in run)
    slips = len(run) - good
    magnitude = statistics.median([item[1] for item in run if item[0]]) if good else 0.
    base = max(0., POINTS_PER_GOOD_QUARTER * good - MISS_PENALTY * slips) * QUARTERS_JUDGED / judged
    own = base * (1 - STREAK_MAGNITUDE_SHARE + STREAK_MAGNITUDE_SHARE * magnitude / 100)
    credibility = judged / QUARTERS_JUDGED
    yoys = [item[2] for item in run if item[0] and item[2] is not None]
    return own * credibility + fill_points * (1 - credibility), {
        "good": good, "slips": slips, "judged": judged, "base": base,
        "ownPoints": own, "magnitudePoints": magnitude, "credibility": credibility, "fillPoints": fill_points, "medianYoY": statistics.median(yoys) if yoys else None,
        "lossFill": profit_rule and loss_now and credibility < 1,
    }, credibility


def label(score):
    return next((name for threshold, name in RATING_BANDS if score >= threshold), RATING_BANDS[-1][1])


def score_company(d, group):
    if group not in GROUPS:
        raise ValueError("Unsupported model group")
    config = GROUPS[group]
    limits = config["limits"]
    points, values, statuses, details, credits = {}, {}, {}, {}, {}

    def put(metric, value, status="A", detail=None, explicit_points=None):
        value = num(value)
        values[metric] = value
        if value is not None or explicit_points is not None:
            points[metric] = explicit_points if explicit_points is not None else scale(value, *limits[metric])
            statuses[metric] = status
        if detail:
            details[metric] = detail

    def ratio(a, b):
        a, b = num(a), num(b)
        return a / b if a is not None and b is not None and b > 0 else None

    sales_q, profit_q = d.get("sales_q", [])[-QUARTERS_STORED:], d.get("net_profit_q", [])[-QUARTERS_STORED:]
    op_q = d.get("operating_profit_q", [])[-QUARTERS_STORED:]
    profile = loss_profile(d)
    loss_now = LOSS_ADJUSTED_FUNDAMENTAL and profile["lossNow"]
    for prefix, q, annual_key in (("SALES", sales_q, "sales_y"), ("PROFIT", profit_q, "net_profit_y")):
        metric = prefix + "_STREAK"
        p, info, credit = streak(q, limits[prefix + "_GROWTH"][1], group, metric,
                               profit_rule=LOSS_ADJUSTED_FUNDAMENTAL and prefix == "PROFIT", loss_now=loss_now)
        put(metric, info["good"] if p is not None else None,
            status="Z" if info.get("lossFill") and not info["judged"] else "A", explicit_points=p, detail=info)
        if p is None:
            points.pop(metric, None)
        credits[metric] = credit
        annual = d.get(annual_key, [])[-(CAGR_MAX_YEARS + 1):]
        new, old, basis = recent(reported_start(q), annual)
        p, value, note = growth(new, old, 1, limits[prefix + "_GROWTH"])
        put(prefix + "_GROWTH", value, detail={"basis": basis, "note": note, "current": new, "previous": old}, explicit_points=p)
        if LOSS_ADJUSTED_FUNDAMENTAL and prefix == "PROFIT" and new is not None and new <= 0:
            put("PROFIT_GROWTH", value, "Z", {"basis": basis, "note": "Latest profit is non-positive", "current": new, "previous": old, "latestLoss": True}, 0.)
        cagr_annual, n, available_years = cagr_window(annual)
        p, value, note = growth(cagr_annual[-1], cagr_annual[0], n, limits[prefix + "_CAGR"]) if n else (None, None, "At least 2 consecutive annual observations ending in the latest financial year required")
        cagr_detail = {"years": n, "availableYears": available_years, "note": note,
                       "current": cagr_annual[-1] if cagr_annual else num(annual[-1]) if annual else None,
                       "previous": cagr_annual[0] if cagr_annual else None}
        put(prefix + "_CAGR", value, detail=cagr_detail, explicit_points=p)
        if LOSS_ADJUSTED_FUNDAMENTAL and prefix == "PROFIT" and annual and num(annual[-1]) is not None and num(annual[-1]) <= 0:
            put("PROFIT_CAGR", value, "Z", {**cagr_detail, "note": "Latest annual profit is non-positive", "latestLoss": True}, 0.)

    nw, debt = num(d.get("net_worth")), num(d.get("total_debt"))
    annual_nw = nw  # Supplied model uses latest net worth, not average or prior year-end equity.
    annual_assets = d.get("total_assets")
    annual_profit = num(d.get("net_profit_y", [None])[-1]) if d.get("net_profit_y") else None
    if group in ("BANK", "NBFC"):
        value = ratio(d.get("loans_now"), d.get("loans_1y_ago"))
        put("LOAN_GROWTH", (value - 1) * 100 if value is not None else None)
        for metric, key in (("GROSS_NPA", "gross_npa_pct"), ("NET_NPA", "net_npa_pct"), ("CAPITAL_ADEQUACY", "capital_adequacy_pct")):
            put(metric, d.get(key))
        value = ratio(annual_profit, annual_assets)
        put("ROA", value * 100 if value is not None else None)
    elif group == "INSURANCE":
        value = ratio(nw, d.get("net_worth_1y_ago"))
        put("NETWORTH_GROWTH", (value - 1) * 100 if value is not None else None)
        put("SOLVENCY", d.get("solvency_ratio"))
        value = ratio(annual_profit, annual_nw)
        put("ROE", value * 100 if value is not None else None, explicit_points=0. if annual_nw is not None and annual_nw <= 0 else None)
    else:
        sn, so, _ = recent(sales_q, [])
        on, oo, _ = recent(op_q, [])
        now, before = ratio(on, sn), ratio(oo, so)
        put("MARGIN_CHANGE", (now - before) * 100 if now is not None and before is not None else None)
        if LOSS_ADJUSTED_FUNDAMENTAL and now is not None and before is not None and now <= 0:
            put("MARGIN_CHANGE", (now - before) * 100, "Z", {"note": "Current operating margin is non-positive", "operatingLoss": True, "opMarginNow": now * 100}, 0.)
        de = ratio(debt, nw)
        put("DEBT_TO_EQUITY", de, explicit_points=0. if nw is not None and nw <= 0 else None)
        if de is not None and de < IC_NOT_APPLICABLE_DE:
            statuses["INTEREST_COVER"] = "N"
            details["INTEREST_COVER"] = {"note": f"Debt / equity is below {IC_NOT_APPLICABLE_DE:g}"}
        else:
            interest, pbt = num(d.get("interest_cost")), num(d.get("profit_before_tax"))
            put("INTEREST_COVER", (pbt + interest) / interest if pbt is not None and interest is not None and interest > 0 else None,
                explicit_points=100. if interest == 0 else None)
        value = ratio(annual_profit, annual_nw)
        put("ROE", value * 100 if value is not None else None, explicit_points=0. if annual_nw is not None and annual_nw <= 0 else None)
        p3 = complete_sum(d.get("net_profit_y", []), 3)
        c3 = complete_sum(d.get("operating_cash_flow_y", []), 3)
        if p3 is not None and p3 <= 0 and c3 is not None:
            put("CASH_CONVERSION", None, "Z", {"note": "Three-year loss; operating cash flow " + ("positive" if c3 > 0 else "non-positive")}, float(CASH_LOSS_POINTS["cash_positive" if c3 > 0 else "cash_negative"]))
        else:
            put("CASH_CONVERSION", ratio(c3, p3))

    if group in ("BANK", "NBFC", "INSURANCE"):
        # Owner-confirmed unconditional replacement of capital adequacy/solvency.
        # Missing expense is not zero, and the non-financial D/E exclusion does
        # not remove a required financial-sector factor.
        interest, pbt = num(d.get("interest_cost")), num(d.get("profit_before_tax"))
        valid = pbt is not None and interest is not None and interest >= 0
        put("INTEREST_COVER", (pbt + interest) / interest if valid and interest > 0 else None,
            explicit_points=100. if valid and interest == 0 else None)

    price, shares = num(d.get("price")), num(d.get("shares"))
    eq = d.get("eps_q", [])
    eps = complete_sum(eq, 4) if len(eq) >= 4 else num(d.get("eps_ttm"))
    if eps is None and len(eq) < 4:
        eps = num(d.get("eps_fy"))
    pe = ratio(price, eps) if price is not None and price > 0 else None
    pb = ratio(price * shares, nw) if price is not None and price > 0 and shares is not None and shares > 0 else None
    loss, negative_nw = eps is not None and eps <= 0, nw is not None and nw <= 0
    for prefix, current, negative in (("PE", pe, loss), ("PB", pb, negative_nw)):
        industry, history = num(d.get(f"industry_median_{prefix.lower()}")), num(d.get(f"own_5y_median_{prefix.lower()}"))
        for suffix, benchmark in (("INDUSTRY", industry), ("HISTORY", history)):
            metric = prefix + "_VS_" + suffix
            if negative:
                put(metric, None, "Z", {"note": "Non-positive EPS" if prefix == "PE" else "Non-positive net worth"}, 0.)
            elif suffix == "HISTORY" and (benchmark is None or benchmark <= 0) and industry is not None and industry > 0:
                put(metric, ratio(current, industry), "S", {"note": "Industry median substituted for unavailable own history"})
            else:
                put(metric, ratio(current, benchmark))
    g = values.get("PROFIT_CAGR")
    if g is None:
        g = values.get("PROFIT_GROWTH")
    core = group in PEG_CORE_GROUPS
    if loss or (pe is not None and g is not None and g <= 0):
        put("PEG", None, "Z", {"note": "Loss-making or non-positive profit growth"}, 0.)
    elif pe is not None and g is not None and g > 0 and (core or details["PROFIT_STREAK"]["good"] >= PEG_MIN_PROFIT_STREAK):
        put("PEG", pe / min(g, PEG_GROWTH_CAP), detail={"growthUsed": min(g, PEG_GROWTH_CAP), "note": "Core group" if core else f"At least {PEG_MIN_PROFIT_STREAK} actual good profit quarters"})
    elif not core:
        statuses["PEG"] = "N"
        details["PEG"] = {"note": "Optional PEG eligibility requirements not met"}
    if group not in ("BANK", "NBFC", "INSURANCE"):
        ebitda = complete_sum(op_q, 4)
        if ebitda is not None and ebitda <= 0:
            put("EV_EBITDA_VS_INDUSTRY", None, "Z", {"note": "Non-positive EBITDA"}, 0.)
        else:
            ev = price * shares + debt - num(d.get("cash")) if all(v is not None for v in (price, shares, debt, num(d.get("cash")))) else None
            put("EV_EBITDA_VS_INDUSTRY", ratio(ratio(ev, ebitda), d.get("industry_median_ev_ebitda")))
    for metric, key in (("VOLATILITY", "volatility_pct"), ("BIGGEST_FALL", "biggest_fall_pct"), ("TRADING_VALUE", "trading_value_cr"), ("PLEDGE", "promoter_pledged_pct")):
        value = num(d.get(key))
        if metric == "PLEDGE" and value is None:
            statuses[metric] = "L"
            continue
        if metric == "TRADING_VALUE" and value is not None:
            put(metric, value, explicit_points=next((p for threshold, p in TRADING_VALUE_STEPS if value >= threshold), 0))
        else:
            put(metric, value)

    effective_weights = {part: dict(weights) for part, weights in config["weights"].items()}
    fallbacks = {}
    # Owner-requested BANK overrides: replace the original slot rather than add
    # a second contribution. A genuine zero/loss score is available data.
    if group == "BANK" and points.get("PE_VS_INDUSTRY") is None and points.get("PE_VS_HISTORY") is not None:
        effective_weights["valuation"] = {
            ("PE_VS_HISTORY" if metric == "PE_VS_INDUSTRY" else metric): weight
            for metric, weight in effective_weights["valuation"].items()
        }
        fallbacks["PE_VS_HISTORY"] = "PE_VS_INDUSTRY"
    if group == "BANK" and points.get("PB_VS_INDUSTRY") is None:
        roe = ratio(annual_profit, annual_nw)
        put("ROE", roe * 100 if roe is not None else None)
        if points.get("ROE") is not None:
            effective_weights["valuation"] = {
                ("ROE" if metric == "PB_VS_INDUSTRY" else metric): weight
                for metric, weight in effective_weights["valuation"].items()
            }
            fallbacks["ROE"] = "PB_VS_INDUSTRY"
    parts, coverage, rows = {}, {}, []
    for part, weights in effective_weights.items():
        base = sum(w for metric, w in weights.items() if statuses.get(metric) != "N")
        denominator = sum(w for metric, w in weights.items() if statuses.get(metric) not in ("N", "L"))
        numerator = real = 0.
        for metric, weight in weights.items():
            state = statuses.get(metric, "A")
            if state not in ("N", "L"):
                if points.get(metric) is None:
                    points[metric], state = fill(group, metric), "F"
                else:
                    real += weight * credits.get(metric, 1.)
                numerator += weight * points[metric]
            statuses[metric] = state
            share = weight / denominator if denominator and state not in ("N", "L") else 0.
            lower, upper = limits.get(metric, (None, None))
            rows.append({"part": part, "metric": metric, "label": LABELS[metric], "value": values.get(metric),
                         "points": points.get(metric) if state not in ("N", "L") else None,
                         "status": state, "statusLabel": STATES[state], "weight": weight, "share": share,
                         "details": details.get(metric, {}), "fallbackFor": fallbacks.get(metric), "worst": lower, "best": upper,
                         "unit": "%" if metric in PERCENT_METRICS else "pp" if metric == "MARGIN_CHANGE" else "quarters" if metric.endswith("STREAK") else "Cr" if metric == "TRADING_VALUE" else "x",
                         "redBoundary": lower + (upper - lower) * .4 if lower is not None else None,
                         "greenBoundary": lower + (upper - lower) * .7 if lower is not None else None})
        parts[part] = numerator / denominator if denominator else None
        coverage[part] = real / base if base else 1.
    raw_fundamental = parts["fundamental"]
    tier, fundamental_cap = loss_tier(group, profile) if LOSS_ADJUSTED_FUNDAMENTAL else (None, None)
    loss_capped = fundamental_cap is not None and raw_fundamental is not None and raw_fundamental > fundamental_cap
    adjustments = []
    if loss_capped:
        parts["fundamental"] = float(fundamental_cap)
        adjustments.append({"metric": "LOSS_CAP", "part": "fundamental", "rawScore": raw_fundamental, "cap": fundamental_cap})
    valuation_capped = False
    if parts["valuation"] is not None and parts["valuation"] > VALUE_TRAP["cap"] and any(parts[p] is not None and parts[p] < VALUE_TRAP["limit"] for p in ("fundamental", "quality")):
        valuation_capped = True
        adjustments.append({"metric": "WEAK_BUSINESS_CAP", "part": "valuation", "rawScore": parts["valuation"], "cap": float(VALUE_TRAP["cap"])})
        parts["valuation"] = float(VALUE_TRAP["cap"])
    total_weight = sum(w for p, w in PART_WEIGHTS.items() if parts[p] is not None)
    for adjustment in adjustments:
        adjustment["pointsLost"] = PART_WEIGHTS[adjustment["part"]] / total_weight * (adjustment["rawScore"] - adjustment["cap"])
    cap = sum(adjustment["pointsLost"] for adjustment in adjustments)
    final = sum(PART_WEIGHTS[p] * value for p, value in parts.items() if value is not None) / total_weight
    confidence = min(1., max(0., sum(PART_WEIGHTS[p] * value for p, value in coverage.items())))
    judged = min(details["SALES_STREAK"]["judged"], details["PROFIT_STREAK"]["judged"])
    enough = sum(num(v) is not None for v in sales_q) >= 4 or sum(num(v) is not None for v in d.get("sales_y", [])) >= 2
    status = "NOT RATED" if confidence < NOT_RATED_BELOW or not enough else "PROVISIONAL" if confidence < PROVISIONAL_BELOW or judged < PROVISIONAL_MIN_QUARTERS else "RATED"
    if d.get("rating_blockers"):
        status = "NOT RATED"
    rating = "NOT RATED" if status == "NOT RATED" else label(final)
    if status == "PROVISIONAL" and rating == "STRONG":
        rating = "HEALTHY"
    for row in rows:
        share = PART_WEIGHTS[row["part"]] / total_weight * row["share"]
        row["pointsEarned"] = share * (row["points"] or 0)
        row["pointsLost"] = share * (100 - (row["points"] or 0)) if row["share"] else 0.
        row["severity"] = "NO DATA" if row["status"] in ("F", "L") else "NOT APPLICABLE" if row["status"] == "N" else "RED" if row["points"] < FLAG_RED else "AMBER" if row["points"] < FLAG_GREEN else "GREEN"
    actual = [row for row in rows if row["status"] in ("A", "Z", "S")]
    strengths = sorted([row for row in actual if row["points"] >= FLAG_GREEN], key=lambda row: -row["pointsEarned"])[:3]
    weaknesses = sorted([row for row in actual if row["points"] < FLAG_RED], key=lambda row: -row["pointsLost"])[:3]
    alerts = list(d.get("rating_blockers", [])) + list(d.get("rating_cautions", []))
    if status != "RATED": alerts.append(f"{status}: {confidence * 100:.0f}% data confidence and {judged} comparable quarters.")
    filled = [row["label"] for row in rows if row["status"] == "F"]
    if filled: alerts.append("Filled using the supplied group snapshot: " + ", ".join(filled) + ".")
    if statuses.get("PLEDGE") == "L": alerts.append("Promoter pledge is unknown; excluded from the Risk score and counted as missing in confidence.")
    if values.get("PLEDGE") is not None and values["PLEDGE"] >= PLEDGE_ALERT: alerts.append(f"Promoter pledged shares are at least {PLEDGE_ALERT:g}%.")
    if loss: alerts.append("Trailing EPS is zero or negative.")
    if negative_nw: alerts.append("Net worth is zero or negative.")
    if values.get("INTEREST_COVER") is not None and values["INTEREST_COVER"] < 1.5: alerts.append("Interest cover is below 1.5 times.")
    if loss_capped: alerts.append(f"Loss rule ({tier}) capped Fundamental at {fundamental_cap} (before cap: {raw_fundamental:.1f}).")
    if valuation_capped: alerts.append(f"Weak-business rule capped Valuation at {VALUE_TRAP['cap']:g}.")
    if judged < QUARTERS_JUDGED: alerts.append(f"Short record: streak scores reflect the available comparable quarters ({judged}/{QUARTERS_JUDGED} minimum across sales and profit).")
    for metric, series in (("Sales", sales_q), ("Net profit", profit_q)):
        if len(series) >= 6 and all(num(series[i]) is not None for i in (-1, -2, -5, -6)) and series[-1] <= series[-5] and series[-2] <= series[-6]:
            alerts.append(f"{metric} did not beat last year in either of the latest two quarters; the growth run is broken.")
    best_part = max(parts, key=lambda p: PART_WEIGHTS[p] * (parts[p] or 0))
    worst_part = max(parts, key=lambda p: PART_WEIGHTS[p] * (100 - (parts[p] or 0)))
    headline = "Not rated: insufficient verified inputs or unresolved data integrity issues." if status == "NOT RATED" else f"{rating.title()} assessment: {best_part.title()} contributes most to the score; {worst_part.title()} accounts for the largest shortfall."
    return {"modelVersion": MODEL_VERSION, "baselineVersion": BASELINE_VERSION, "fillVersion": FILL_VERSION,
            "group": group, "final": final if status != "NOT RATED" else None, "label": rating, "status": status,
            "confidence": confidence, "coverage": coverage, "dataIntegrityStatus": "REVIEW REQUIRED" if d.get("rating_cautions") or d.get("rating_blockers") else "PASS", "parts": parts, "partWeights": PART_WEIGHTS,
            "judgedQuarters": judged, "metrics": rows, "strengths": strengths, "weaknesses": weaknesses,
            "flags": [row for row in actual if row["points"] < FLAG_GREEN], "alerts": alerts,
            "valuationCapped": valuation_capped, "lossCapped": loss_capped,
            "loss": dict(profile, tier=tier, cap=fundamental_cap, rawFundamental=raw_fundamental),
            "adjustments": adjustments, "capPointsLost": cap, "headline": headline}
