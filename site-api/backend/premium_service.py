"""Calculate on-demand reports from explicit model inputs without storing report history."""
from datetime import datetime, timezone
import hashlib
import json
try:
    from .premium_data import adapt_inputs
    from .premium_provider import fetch_inputs
    from .premium_benchmarks import resolve_report_benchmarks
    from .premium_engine import score_company
    from .premium_trace import build_calculation_trace
    from .premium_presentation import build_report_review
    from .premium_technical import build_technical_assessment, resolve_technical_prices
    from .premium_technical_sources import load_benchmark_history
except ImportError:
    from premium_data import adapt_inputs
    from premium_provider import fetch_inputs
    from premium_benchmarks import resolve_report_benchmarks
    from premium_engine import score_company
    from premium_trace import build_calculation_trace
    from premium_presentation import build_report_review
    from premium_technical import build_technical_assessment, resolve_technical_prices
    from premium_technical_sources import load_benchmark_history


def generate_report(get, symbol, name, statement_type, report_id, created_at, dashboard_load=None):
    now = datetime.now(timezone.utc)
    sourcing = {}
    requested_basis = statement_type
    if dashboard_load:
        raw, sources, statement_type, sourcing = dashboard_load(symbol, statement_type, now)
    else:
        raw, sources = fetch_inputs(get, symbol, statement_type, now)
    inputs, group, profile, meta, warnings, trends = adapt_inputs(raw, symbol, now.date(), statement_type)
    meta['dashboardSources'] = sourcing
    meta['requestedStatementType'] = requested_basis
    meta['dataRecovery'] = sourcing.get('notes', [])
    recovery = [note for note in sourcing.get('notes', []) if not note.startswith('Calculated FinEdge')]
    warnings.extend(recovery)
    if statement_type != requested_basis:
        warnings.append(f'The dashboard resolved {requested_basis} financials to {statement_type}; this entire report uses that same effective statement basis.')
    benchmarks, benchmark_meta = resolve_report_benchmarks(
        get, raw, statement_type, now.date(), group, meta.get("priceAsOf")
    )
    inputs.setdefault("benchmark_details", {}).update(benchmark_meta["metrics"])
    inputs.update(benchmarks)
    rating = score_company(inputs, group)
    if any(not source["available"] for source in sources):
        warnings.append("Some provider requests failed. Missing metrics are explicitly identified in the scorecard; values were not guessed.")
    if not benchmarks:
        warnings.append("No verified industry valuation medians were available. Corresponding valuation metrics use group fills and reduce data confidence.")
    report = {"id": report_id, "state": "ready", "createdAt": created_at, "completedAt": datetime.now(timezone.utc).isoformat(),
            "statementType": statement_type, "company": {"symbol": symbol, "name": profile.get("name") or name or symbol,
                "industry": profile.get("industry"), "sector": profile.get("sector"), "description": profile.get("description")},
            "rating": rating, "calculationTrace": build_calculation_trace(inputs, rating, meta), "inputs": inputs, "inputMeta": meta, "warnings": warnings,
            "sources": sources, "trends": trends, "benchmark": benchmark_meta,
            "inputHash": hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest()}

    report["review"] = build_report_review(report)
    technical_prices = raw.get("technicalPriceInput")
    if technical_prices is None:
        technical_prices = resolve_technical_prices(raw.get("prices"), "FinEdge", now.date())
    technical_benchmarks = raw.get("technicalBenchmarks")
    if technical_benchmarks is None:
        technical_benchmarks = load_benchmark_history(get, now.date(), required_dates=[row['date'] for row in technical_prices.get('bars',[])[-505:]])
    report["technicalAssessment"] = build_technical_assessment(technical_prices, now.date(), technical_benchmarks, inputs.get("shares"))
    return report
