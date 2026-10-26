"""Builds snapshot_example.json from the site backend's own pure scoring pieces (engine 3.6.10 plus the ST/LT technical assessment).

Run from the repository root with the site backend's venv (it needs PyJWT only for premium_snapshot):

    site-api: PYTHONPATH=site-api:site-api/backend site-venv/bin/python backend/tests/fixtures/prism/make_fixture.py site-api/backend backend/tests/fixtures/prism/snapshot_example.json

Everything is produced by the real functions: premium_engine.score_company, premium_trace.build_calculation_trace,
premium_presentation.build_report_review, premium_technical.resolve_technical_prices / build_technical_assessment and
premium_snapshot.issue. No provider is called, so the OHLCV candles and the four index series are SYNTHETIC: a seeded, deterministic random walk
of 700 weekday sessions (the ST/LT model needs 505 aligned observations for a fully rated assessment) with the sample company's own share count.
The scores are therefore real engine output for made-up prices; they say nothing about any company.
"""
import hashlib
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

site = Path(sys.argv[1])
sys.path.insert(0, str(site))
from premium_engine import score_company
from premium_trace import build_calculation_trace
from premium_presentation import build_report_review
from premium_snapshot import issue
from premium_technical import build_technical_assessment, resolve_technical_prices

ASOF = date(2026, 10, 16)
inputs = json.loads((site / "tests" / "premium_example.json").read_text())
rating = score_company(inputs, "MFG")
meta = {"quarterlyAsOf": "2026-06-30", "annualAsOf": "2026-03-31", "balanceAsOf": "2026-03-31", "ownershipAsOf": "2026-06-30", "priceAsOf": "2026-10-16",
        "chronology": {"quarterly": [f"{2023 + (i + 2) // 4}-{((i + 2) % 4) * 3 + 3:02d}" for i in range(14)], "annual": [str(y) for y in range(2021, 2027)]}}


def sessions(count):
    days, current = [], ASOF
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return list(reversed(days))


def walk(seed, start, drift, vol):
    rng, price, out = random.Random(seed), start, []
    for _ in range(700):
        move = rng.gauss(drift, vol)
        opened, price = price, price * (1 + move)
        high = max(opened, price) * (1 + abs(rng.gauss(0, vol / 3)))
        low = min(opened, price) * (1 - abs(rng.gauss(0, vol / 3)))
        out.append((opened, high, low, price, int(rng.uniform(0.5, 1.5) * 1_000_000)))
    return out


days = sessions(700)
stock = [{"date": d.isoformat(), "open": round(o, 2), "high": round(h, 2), "low": round(lo, 2), "close": round(c, 2), "volume": v}
         for d, (o, h, lo, c, v) in zip(days, walk(11, 100.0, 0.0006, 0.013))]
benchmarks = {}
for n, (name, seed) in enumerate((("Nifty 500", 21), ("Nifty 50", 22), ("Nifty Midcap 100", 23), ("Nifty Smallcap 100", 24))):
    series = walk(seed, 1000.0, 0.0004, 0.009)
    benchmarks[name] = {"provider": "FinEdge", "bars": [{"date": d.isoformat(), "close": round(row[3], 2)} for d, row in zip(days, series)]}
technical = build_technical_assessment(resolve_technical_prices(stock, "FinEdge", ASOF), ASOF, benchmarks, inputs["shares"])
assert technical["status"] == "ready", technical["notes"]

report = {"id": "a" * 32, "state": "ready", "createdAt": "2026-10-18T00:00:00+00:00", "completedAt": "2026-10-18T00:01:10+00:00",
          "statementType": "consolidated", "company": {"symbol": "TCS", "name": "Sample Engineering Ltd", "industry": "Capital Goods / Engineering",
          "sector": "Industrials", "description": "A sample company built from the model's worked example."},
          "rating": rating, "calculationTrace": build_calculation_trace(inputs, rating, meta), "inputs": inputs, "inputMeta": meta,
          "warnings": ["Test warning"], "sources": [{"section": "annual", "available": True, "retrievedAt": "2026-10-18T00:00:00+00:00"}],
          "trends": [{"period": "2026", "revenue": 4295, "profit": 346, "eps": 36.2}],
          "benchmark": {"source": "Test universe", "asOf": "2026-10-16", "universeCount": 6, "fetchedCount": 6, "note": "Verified test fixture"},
          "inputHash": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()}
report["review"] = build_report_review(report)
report["technicalAssessment"] = technical      # premium_service attaches it after the review, before the snapshot is signed
snap = issue(report, "prism:fixture", "f" * 40)
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(snap, sort_keys=True, separators=(",", ":")) + "\n")
print(len(out.read_bytes()), sorted(snap))
