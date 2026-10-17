"""DEVELOPMENT ONLY: adds the fictional "SMP-" sample companies to the scores table so the screener, comparison and
dashboard have a universe to work on before real FinEdge data is loaded. Never run against production.

    python scripts/seed_dev_universe.py ../frontend/public/demo/screener.json
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finlit.config import get_settings  # noqa: E402
from finlit.store import Store  # noqa: E402


async def main(path: str) -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to seed sample companies in production.")
    rows = [r for r in json.load(open(path))["rows"] if str(r["symbol"]).startswith("SMP-")]
    store = await Store.connect(settings)
    try:
        async with store.pool.acquire() as conn:
            for r in rows:
                await store._upsert_score(conn, {**r, "statement": "consolidated", "model": "v1"})
        print(f"seeded {len(rows)} sample companies")
    finally:
        await store.close()


asyncio.run(main(sys.argv[1]))
