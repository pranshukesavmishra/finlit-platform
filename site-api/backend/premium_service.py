"""Calculate on-demand reports from explicit model inputs without storing report history."""
from datetime import datetime, timezone, date
import hashlib
import json
try:
    from .premium_data import fetch_inputs, adapt_inputs, peer_benchmark
    from .premium_engine import score_company
    from .premium_trace import build_calculation_trace
    from .premium_presentation import build_report_review
    from .benchmark_resolution import select_reported_benchmarks
except ImportError:
    from premium_data import fetch_inputs, adapt_inputs, peer_benchmark
    from premium_engine import score_company
    from premium_trace import build_calculation_trace
    from premium_presentation import build_report_review
    from benchmark_resolution import select_reported_benchmarks


def generate_report(get, symbol, name, statement_type, report_id, created_at, dashboard_load=None, observations=None):
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
    # Match benchmark observations to the report price date, not a later market close.
    try: benchmark_date = date.fromisoformat(meta.get("priceAsOf") or now.date().isoformat())
    except ValueError: benchmark_date = now.date()
    reported, reported_meta = select_reported_benchmarks(raw.get("benchmarkObservations", []))
    wanted = [key for key in ("pe", "pb") if "industry_median_" + key not in reported]
    if group in ("HEAVY", "UTILITY") and "industry_median_ev_ebitda" not in reported:
        wanted.append("ev_ebitda")
    kept = {} if observations is None else {"observations": observations}
    benchmarks, benchmark_meta = peer_benchmark(get, raw.get("peers", {}), statement_type, min(benchmark_date, now.date()), group, wanted, **kept)
    benchmarks.update(reported)
    benchmark_meta.setdefault("metrics", {}).update(reported_meta)
    providers = sorted({item["provider"] for item in benchmark_meta["metrics"].values() if item.get("value") is not None})
    if providers:
        benchmark_meta["source"] = " / ".join(providers)
    benchmark_meta["reportedObservations"] = raw.get("benchmarkObservations", [])
    benchmark_meta["policyVersion"] = "2026-10-24-provider-first"
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
    return report
