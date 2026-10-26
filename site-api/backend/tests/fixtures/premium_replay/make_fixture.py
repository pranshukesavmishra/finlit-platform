"""Builds one replay fixture from a recorded live run (a dict {"recorded": {json([path, params]): provider answer}, "report": ...}).

    python3 make_fixture.py recorded_run.json SKIPPER.json.gz

The recording is every answer the provider gave while the PRE-speed-up code calculated the company (premium_service.generate_report with
the dashboard resolver), keyed by json.dumps([path, params], sort_keys=True). To keep the fixture small, each industry peer's two-year daily
price-ratio list is cut to the rows within 45 days before the report's price date: the model reads only the newest row of the last 31 days.
The listing of every symbol (/stock-symbols) is dropped; the test resolves the company itself.
"""
import gzip
import json
import sys
from datetime import date, timedelta

run = json.load(open(sys.argv[1]))
report = run["report"]
symbol = report["company"]["symbol"]
as_of = date.fromisoformat(report["inputMeta"]["priceAsOf"])
oldest = (as_of - timedelta(days=45)).isoformat()
recorded = {}
for key, answer in run["recorded"].items():
    path, params = json.loads(key)
    if path == "/stock-symbols":
        continue
    if path.startswith("/daily-price-ratios/") and path != f"/daily-price-ratios/{symbol}":
        rows = answer.get("price_ratios") if isinstance(answer, dict) else answer
        if isinstance(rows, list):
            kept = [row for row in rows if isinstance(row, dict) and str(row.get("quote_date") or row.get("date") or row.get("period_end") or "")[:10] >= oldest]
            answer = {**answer, "price_ratios": kept} if isinstance(answer, dict) else kept
    recorded[key] = answer
out = {"symbol": symbol, "name": report["company"]["name"], "statement": report["statementType"], "now": report["createdAt"], "group": report["rating"]["group"],
       "recorded": recorded}
with gzip.open(sys.argv[2], "wt", compresslevel=9) as handle:
    json.dump(out, handle, separators=(",", ":"))
