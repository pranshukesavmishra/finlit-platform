"""Reported valuation benchmarks shared by the dashboard and premium report."""
try:
    from .financial_records import num
except ImportError:
    from financial_records import num

RATIO_KEYS = {"P/E": "pe", "P/B": "pb", "EV/EBITDA": "ev_ebitda"}


def number(value):
    return num(value.replace(",", "").strip() if isinstance(value, str) else value)


def reported_benchmarks(finedge_rows, upstox_rows, retrieved_at):
    observations = []
    for provider, rows in (("FinEdge", finedge_rows), ("Upstox", upstox_rows)):
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            key = RATIO_KEYS.get(str(row.get("name") or "").upper())
            if not key:
                continue
            # Do not relabel a provider's sector comparison as an industry median.
            fields = ("sector_value",) if provider == "Upstox" else ("industry_value", "industryValue", "peerMedian")
            value = next((number(row[field]) for field in fields if number(row.get(field)) is not None), None)
            if value is None:
                continue
            observations.append({"key": key, "value": value, "provider": provider,
                                 "scope": "sector" if provider == "Upstox" else "industry",
                                 "method": "reported benchmark", "retrievedAt": retrieved_at,
                                 "statementBasis": "unspecified", "asOf": None})
    return observations


def select_reported_benchmarks(observations):
    values, details = {}, {}
    # Explicit provider benchmarks precede calculated peer medians.
    for provider in ("FinEdge", "Upstox"):
        for item in observations:
            key, value = item.get("key"), number(item.get("value"))
            if item.get("provider") != provider or key not in RATIO_KEYS.values() or value is None or value <= 0:
                continue
            target = "industry_median_" + key  # Existing scoring slot; scope is disclosed separately.
            if target not in values:
                values[target], details[target] = value, dict(item)
    return values, details


def merge_sector_values(company_ratios, upstox_ratios):
    """Keep FinEdge company values; fill each missing comparison independently."""
    lookup = {str(r.get("name") or "").upper(): r for r in upstox_ratios if isinstance(r, dict)}
    result = []
    for row in company_ratios:
        merged = dict(row)
        other = lookup.get(str(row.get("name") or "").upper(), {})
        if number(merged.get("sector_value")) is None and number(other.get("sector_value")) is not None:
            merged.update(sector_value=number(other["sector_value"]), sector_source="Upstox")
        result.append(merged)
    return result
