"""Save one stock's API responses as static JSON files (for design prototypes and offline demos).

    python scripts/export_static.py http://localhost:8000 RELIANCE ../../simpdash/data [standalone]

Files mirror the API paths: <out>/<SYMBOL>/summary.json, financials.json, price-1Y.json, ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

SECTIONS = ["financials", "ratios", "ownership", "events", "segments", "peers"]
RANGES = ["1M", "6M", "1Y", "3Y", "5Y", "MAX"]


def main(base: str, symbol: str, out: str, statement: str = "consolidated"):
    target = Path(out) / symbol.upper()
    target.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=base, timeout=10) as client:
        files = {"summary": (f"/api/stocks/{symbol}", {})}
        files.update({s: (f"/api/stocks/{symbol}/{s}", {}) for s in SECTIONS})
        files.update({f"price-{r}": (f"/api/stocks/{symbol}/price", {"range": r}) for r in RANGES})
        for name, (path, params) in files.items():
            r = client.get(path, params={**params, "statement": statement})
            r.raise_for_status()
            (target / f"{name}.json").write_text(json.dumps(r.json(), separators=(",", ":"), ensure_ascii=False))
            print(f"{name:<12} {len(r.content):>7} bytes")


if __name__ == "__main__":
    main(*sys.argv[1:5])
