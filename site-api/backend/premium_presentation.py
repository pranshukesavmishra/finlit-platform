"""Reader-facing commentary from an existing rating; never fetch or rescore inputs."""
try:
    from .premium_completeness import build_input_completeness
    from .premium_model_config import FLAG_RED, FLAG_GREEN
except ImportError:
    from premium_completeness import build_input_completeness
    from premium_model_config import FLAG_RED, FLAG_GREEN
PARTS = ("fundamental", "valuation", "quality", "risk")
REASONS = {
    "SALES_STREAK": ("Consistent year-on-year sales growth.", "Sales growth has been inconsistent."),
    "PROFIT_STREAK": ("Consistent year-on-year profit growth.", "Profit growth has been inconsistent."),
    "SALES_GROWTH": ("Strong recent sales growth.", "Recent sales growth is weak."),
    "PROFIT_GROWTH": ("Strong recent profit growth.", "Recent profit growth is weak."),
    "SALES_CAGR": ("Strong sales growth over the longer term.", "Longer-term sales growth is weak."),
    "PROFIT_CAGR": ("Strong profit growth over the longer term.", "Longer-term profit growth is weak."),
    "MARGIN_CHANGE": ("Operating margins have improved.", "Operating margin performance is weak."),
    "LOAN_GROWTH": ("Strong expansion in the loan book.", "Loan-book growth is weak."),
    "NETWORTH_GROWTH": ("Strong growth in net worth.", "Net-worth growth is weak."),
    "DEBT_TO_EQUITY": ("Low borrowing relative to equity.", "High borrowing relative to equity."),
    "INTEREST_COVER": ("Earnings provide a strong cushion for interest payments.", "Earnings provide a limited cushion for interest payments."),
    "FINANCIAL_LEVERAGE": ("Lower assets relative to equity support the insurer's capital position.", "High assets relative to equity indicate elevated financial leverage."),
    "ROE": ("Strong returns on shareholder equity.", "Low returns on shareholder equity."),
    "CASH_CONVERSION": ("Profits are well supported by operating cash flow.", "Operating cash flow provides weak support for reported profits."),
    "GROSS_NPA": ("Low gross non-performing loans support asset quality.", "High gross non-performing loans weaken asset quality."),
    "NET_NPA": ("Low net non-performing loans support asset quality.", "High net non-performing loans weaken asset quality."),
    "CAPITAL_ADEQUACY": ("A strong capital buffer supports the balance sheet.", "The capital buffer is limited."),
    "ROA": ("Strong profit generation relative to assets.", "Low profit generation relative to assets."),
    "SOLVENCY": ("A strong solvency buffer supports financial resilience.", "The solvency buffer is limited."),
    "PEG": ("The earnings multiple is favourable relative to profit growth.", "The earnings multiple is unfavourable relative to profit growth."),
    "VOLATILITY": ("Relatively low share-price volatility.", "High share-price volatility increases market risk."),
    "BIGGEST_FALL": ("The largest one-year share-price decline was relatively limited.", "The share price experienced a large one-year decline."),
    "TRADING_VALUE": ("Higher trading activity supports liquidity.", "Low trading activity can make entry and exit harder."),
    "PLEDGE": ("Low promoter pledging limits pledge-related risk.", "High promoter pledging increases pledge-related risk."),
}
MIXED = {
    "SALES_STREAK": "Sales growth is uneven across comparable quarters.",
    "PROFIT_STREAK": "Profit growth is uneven across comparable quarters.",
    "SALES_GROWTH": "Recent sales growth is moderate.", "PROFIT_GROWTH": "Recent profit growth is moderate.",
    "SALES_CAGR": "Longer-term sales growth is moderate.", "PROFIT_CAGR": "Longer-term profit growth is moderate.",
    "MARGIN_CHANGE": "Margin performance provides limited support.", "LOAN_GROWTH": "Loan-book growth is moderate.",
    "NETWORTH_GROWTH": "Net-worth growth is moderate.", "DEBT_TO_EQUITY": "Borrowing is at an intermediate level relative to equity.",
    "INTEREST_COVER": "Earnings provide a moderate cushion for interest payments.",
    "FINANCIAL_LEVERAGE": "Assets relative to equity indicate moderate financial leverage.",
    "ROE": "Returns on equity are moderate.", "ROA": "Returns on assets are moderate.",
    "CASH_CONVERSION": "Operating cash flow provides moderate support for profits.",
    "GROSS_NPA": "Gross non-performing loans warrant monitoring.", "NET_NPA": "Net non-performing loans warrant monitoring.",
    "CAPITAL_ADEQUACY": "The capital buffer is in the middle assessment range.", "SOLVENCY": "The solvency buffer is in the middle assessment range.",
    "PEG": "The earnings multiple offers limited support relative to profit growth.",
    "VOLATILITY": "Share-price volatility warrants monitoring.", "BIGGEST_FALL": "The one-year price decline warrants monitoring.",
    "TRADING_VALUE": "Trading activity provides moderate liquidity.", "PLEDGE": "Some promoter holdings are pledged; monitor pledge levels.",
}
LABELS = {"SALES_STREAK": "Sales streak", "PROFIT_STREAK": "Profit streak",
          "SALES_GROWTH": "Sales growth (12 months)", "SALES_CAGR": "Sales CAGR",
          "TRADING_VALUE": "Average daily trading value"}


def value_text(row):
    value = row.get("value")
    if value is None:
        return "Not available"
    unit = row.get("unit", "")
    if unit == "quarters": return f"{value:g} growth quarters"
    if unit == "Cr": return f"INR {value:,.2f} crore"
    return f"{value:,.2f}{unit if unit in ('%', 'x') else ' ' + unit}".strip()


def factor(row, group):
    metric, state = row["metric"], row["status"]
    label = LABELS.get(metric, row["label"])
    cagr_years = row.get("details", {}).get("years", 0) if metric in ("SALES_CAGR", "PROFIT_CAGR") else 0
    if cagr_years:
        label += f" ({cagr_years}-year)"
    item = {"metric": metric, "label": label, "valueText": value_text(row)}
    if metric=='FINANCIAL_LEVERAGE' and row.get('details',{}).get('source'):
        item['comparisonText'] = 'Source: ' + row['details']['source'] + '.'
    if state == "N":
        return "notApplicable", dict(item, summary="Not applicable to this assessment.")
    if state in ("F", "L") or row.get("points") is None:
        if row.get("details",{}).get("invalid"):
            return "unavailable", dict(item,valueText="Invalid",summary=row['details']['note'])
        summary = "Not reported; an estimate is used in the assessment." if state == "F" else "Not reported; not assessed."
        return "unavailable", dict(item, valueText="Not available", summary=summary)
    points = row["points"]
    bucket = "pros" if points >= FLAG_GREEN else "cons" if points < FLAG_RED else "mixed"
    if "_VS_" in metric:
        multiple = "P/E" if metric.startswith("PE_") else "P/B" if metric.startswith("PB_") else "EV/EBITDA"
        comparison = "industry peers" if metric.endswith("INDUSTRY") or state == "S" else "the company's own history"
        if state == "S": label = f"{multiple} vs industry (history unavailable)"
        reason = f"{multiple} is relatively {'low' if bucket == 'pros' else 'high'} against {comparison}." if bucket != "mixed" else f"{multiple} is in the middle assessment range against {comparison}."
    elif bucket == "mixed":
        reason = MIXED.get(metric, "In the middle assessment range.")
    else:
        reason = REASONS.get(metric, ("Supports the assessment.", "Holds back the assessment."))[bucket == "cons"]
    if cagr_years and row.get("value") is not None:
        subject = "sales" if metric == "SALES_CAGR" else "profit"
        quality = {"pros": "Strong", "cons": "Weak", "mixed": "Moderate"}[bucket]
        reason = f"{quality} {subject} growth over the {cagr_years}-year period."
    if row.get("value") is None:
        note = row.get("details", {}).get("note")
        if note in ("Loss to profit", "Loss narrowed", "Loss not narrowed"):
            reason = {"Loss to profit": "The business returned to profit.", "Loss narrowed": "Losses narrowed, but the business remains loss-making.", "Loss not narrowed": "Losses have not narrowed."}[note]
        elif metric == "INTEREST_COVER" and points == 100:
            reason = "No interest expense is reported for the year."
        elif metric == "CASH_CONVERSION" and note and note.startswith("Three-year loss"):
            reason = "Operating cash flow is positive despite a three-year loss." if note.endswith("positive") and not note.endswith("non-positive") else "Both three-year profits and operating cash flow are non-positive."
        else:
            reason = "Losses or a non-positive comparison prevent a meaningful ratio."
        item["valueText"] = "Not meaningful"
    if metric == "PLEDGE" and row.get("value") == 0:
        reason = "No promoter shares are reported as pledged."
    if metric.endswith("STREAK"):
        info = row.get("details", {})
        reason += f" {info.get('good', 0)} growth quarters across {info.get('judged', 0)} comparable quarters."
        if metric == "PROFIT_STREAK":
            reason += " Loss-making quarters do not count as growth quarters."
            if info.get("lossFill"):
                reason += " Current losses limit the assessment despite the short record."
    info = row.get("details", {})
    if info.get("latestLoss"):
        period = "latest financial year" if metric == "PROFIT_CAGR" else "latest comparison period"
        reason = f"Net profit is zero or negative in the {period}; this factor provides no support to the assessment."
        if row.get("value") is None:
            item["valueText"] = "Zero or negative profit"
    if info.get("operatingLoss"):
        reason = f"The current operating margin is {info['opMarginNow']:.2f}%; margin improvement provides no support until the margin turns positive."
    if state == "S":
        reason += " Industry data is used because company history is unavailable."
    if row.get("fallbackFor") == "PE_VS_INDUSTRY":
        reason += " Company history is used because the industry P/E benchmark is unavailable."
    if row.get("fallbackFor") == "PB_VS_INDUSTRY":
        label = "Return on equity (industry P/B unavailable)"
        reason += " Used in place of the unavailable industry P/B comparison."
    if row.get("fallbackFor") == "CAPITAL_ADEQUACY":
        label = "Interest coverage (capital adequacy unavailable)"
        reason += " Used in place of unavailable capital adequacy."
    return bucket, dict(item, label=label, summary=reason)


def loss_review_note(rating):
    loss = rating.get("loss", {})
    if not rating.get("lossCapped"):
        return None
    tier = loss["tier"]
    if tier == "recovering":
        reason = "profit has returned, but the recent annual loss record means the recovery is not yet established"
    else:
        reason = f"net profit over the {loss['basis']} is zero or negative"
        if tier.startswith("chronic"):
            reason += f", with losses in {loss['lossYears5']} of the last {loss['years5']} financial years"
        elif tier.startswith("persistent"):
            reason += f", with losses in {loss['lossYears3']} of the last {loss['years3']} financial years"
        if tier.endswith("deep"):
            reason += f"; the net loss is {abs(loss['netMarginPct']):.1f}% of sales"
    return f"The Fundamental score is limited to {loss['cap']:g}/100 because {reason}."


def benchmark_disclosure(row, item, report):
    metric = row["metric"]
    if "_VS_" not in metric:
        if row["status"] == "F":
            item["comparisonText"] = f"Group estimate used: {row['points']:g}/100."
        elif metric in ("SALES_CAGR", "PROFIT_CAGR"):
            years = row.get("details", {}).get("years", 0)
            periods = report.get("inputMeta", {}).get("chronology", {}).get("annual", [])
            if years and len(periods) > years:
                item["comparisonText"] = f"Period used: {periods[-years-1]} to {periods[-1]}."
        return item
    prefix = metric.split("_VS_")[0].lower()
    ratio = {"pe": "P/E", "pb": "P/B", "ev_ebitda": "EV/EBITDA"}[prefix]
    history = metric.endswith("HISTORY") and row["status"] != "S"
    key = ("own_5y_median_" if history else "industry_median_") + prefix
    inputs = report.get("inputs", {})
    info = inputs.get("benchmark_details", {}).get(key, {})
    value = inputs.get(key)
    if row["status"] == "F":
        reason = "Insufficient benchmark data."
        if value is not None and value > 0:
            reason = f"The {ratio} benchmark is available, but the company's comparable ratio could not be calculated."
        elif history and info:
            reason = f"Only {info['positiveCount']} positive historical observations are available; at least {info['minimumCount']} are required."
        elif info.get("positiveCount") is not None:
            reason = f"Only {info['positiveCount']} positive peer observations are available; at least 5 are required."
        item["summary"] = reason + " A group estimate is used in the assessment."
        item["comparisonText"] = f"Group estimate used: {row['points']:g}/100."
        return item
    if value is None or not info:
        return item
    scope, provider = info["scope"], info["provider"]
    if scope == "sector":
        item["label"] = f"{ratio} vs sector" + (" (history unavailable)" if row["status"] == "S" else "")
        item["summary"] = item["summary"].replace("industry peers", "the sector benchmark").replace("Industry data", "Sector data")
    current = next((r["value"] for r in report.get("calculationTrace", {}).get("latest", []) if r["key"] == prefix), None)
    current_text = f"Company {ratio}: {current:.2f}x. " if current is not None else ""
    benchmark_label = "Own-history median" if history else "Sector benchmark" if scope == "sector" else "Industry peer median"
    description = f"{current_text}{benchmark_label}: {value:.2f}x. Source: {provider}."
    if info.get("method") == "available peer median":
        description += f" Uses {info['positiveCount']} positive multiples; {info['observedCount']} of {info['universeCount']} peer records available."
    if row["status"] == "S":
        own = inputs.get("benchmark_details", {}).get("own_5y_median_" + prefix, {})
        if own:
            description += f" Own history has {own['positiveCount']} eligible observations; {own['minimumCount']} required."
    item["comparisonText"] = description
    return item


def build_report_review(report):
    rating = report["rating"]
    parts = []
    for key in PARTS:
        part = {"key": key, "name": key.title(), "score": rating["parts"].get(key) if rating["status"] != "NOT RATED" else None, "notes": [],
                **{bucket: [] for bucket in ("pros", "cons", "mixed", "unavailable", "notApplicable")}}
        for row in rating["metrics"]:
            if row["part"] == key:
                bucket, item = factor(row, rating["group"])
                item = benchmark_disclosure(row, item, report)
                if row["metric"] == "SOLVENCY" and any("solvency ratio has unverified units" in caution for caution in report.get("inputs", {}).get("rating_cautions", [])):
                    item["summary"] = "The reported solvency value requires a unit check against the issuer disclosure; interpret this factor with caution."
                part[bucket].append(item)
        parts.append(part)
    loss_note = loss_review_note(rating)
    if loss_note:
        parts[0]["notes"].append(loss_note)
    notes = []
    benchmark = report.get("benchmark", {})
    if any(i.get("provider") == "Upstox" for i in benchmark.get("metrics", {}).values()):
        notes.append("Upstox comparisons use its reported sector benchmark. The provider does not specify its statement basis, valuation date or aggregation method.")
    for observation in benchmark.get("reportedObservations", []):
        if observation.get("provider") == "Upstox" and observation.get("value", 0) <= 0:
            ratio = {"pe": "P/E", "pb": "P/B", "ev_ebitda": "EV/EBITDA"}.get(observation.get("key"))
            if ratio:
                notes.append(f"Upstox reports sector {ratio} of {observation['value']:.2f}x. It is excluded because this comparison requires a positive benchmark.")
    if any(row.get("fallbackFor") == "PB_VS_INDUSTRY" for row in rating["metrics"]):
        notes.append("The industry P/B comparison is unavailable; the Valuation assessment uses return on equity instead.")
    if any(row.get("fallbackFor") == "CAPITAL_ADEQUACY" for row in rating["metrics"]):
        notes.append("Capital adequacy is unavailable; the Quality assessment uses interest coverage instead.")
    if any(row['metric']=='FINANCIAL_LEVERAGE' for row in rating['metrics']):
        notes.append("Insurance financial leverage uses assets divided by equity. Its 5x–20x scoring range is provisional, pending calibration against insurers' historical data.")
    missing = [r["label"] for p in parts for r in p["unavailable"]]
    if missing: notes.append("Unavailable information: " + ", ".join(missing) + ". Estimates are not presented as company strengths or weaknesses.")
    for warning in report.get("warnings", []):
        if "bank asset-quality disclosures use" in warning:
            notes.append("Asset-quality ratios use the bank's separately reported statement basis; other financial results use the basis stated on this report.")
        elif "non-controlling interests" in warning:
            notes.append("Book equity includes non-controlling interests; provider valuation benchmarks may use a different equity basis.")
        elif "quote share count conflicts" in warning:
            notes.append("Share-count differences may affect valuation comparisons.")
    inputs = report.get("inputs", {})
    # Preserve substantive data concerns in plain language; omit provider plumbing.
    for message in inputs.get("rating_blockers", []) + inputs.get("rating_cautions", []):
        if "solvency ratio has unverified units" in message: notes.append("The solvency ratio's units need verification against the issuer disclosure; interpret the Quality assessment with caution.")
        elif "classification" in message: notes.append("The company's industry classification needs confirmation; the overall rating is withheld.")
        elif "Quarterly" in message: notes.append("Quarterly results are incomplete or more than 200 days old.")
        elif "freshness" in message: notes.append("The market price is more than 10 days old.")
        elif "date is unverified" in message: notes.append("The market-price date could not be confirmed.")
        elif "Share-count" in message: notes.append("The reported share count needs review following possible corporate actions.")
        elif "ratio" in message: notes.append("Calculated valuation ratios differ from the data provider's ratios; use caution when comparing valuations.")
        elif "closing prices" in message: notes.append("Gaps in the price history limit the market-risk assessment.")
        else: notes.append("Some financial information could not be fully verified; treat the assessment with caution.")
    meta = report.get("inputMeta", {})
    requested = meta.get("requestedStatementType")
    if requested and requested != report["statementType"]:
        notes.append(f"{requested.title()} statements were unavailable; this report uses {report['statementType']} statements.")
    if rating["status"] == "PROVISIONAL": notes.append("This assessment is provisional because the available financial history or data coverage is limited.")
    if rating["status"] == "NOT RATED": notes.append("There is insufficient verified information to provide an overall rating.")
    if rating.get("valuationCapped"): notes.append("Weak business fundamentals or financial quality limit the valuation assessment.")
    return {"parts": parts, "notes": list(dict.fromkeys(notes)), "completeness": build_input_completeness(report)}
