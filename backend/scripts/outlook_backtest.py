"""Back-test the profit and revenue outlook model on the stored company histories (for the team's review; nothing here is shown on the site).

    cd backend && python scripts/outlook_backtest.py [--statement consolidated] [--limit 800] [--min-history 3] > ../docs/outlook/backtest-latest.md

Needs DATABASE_URL and REDIS_URL (the same settings the API uses). Method and how to read the tables: docs/outlook/BACKTEST.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import orjson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finlit.outlook.backtest import Company, run, sample_ok, summarise  # noqa: E402
from finlit.outlook.inputs import build_inputs  # noqa: E402
from finlit.outlook.model import hist_from_inputs  # noqa: E402
from finlit.screener.data import get_table  # noqa: E402
from finlit.store import Store  # noqa: E402


async def load(statement: str, limit: int):
    store = await Store.connect()
    table = await get_table(store)
    out = []
    for i, sym in enumerate(table.symbols):
        if len(out) >= limit:
            break
        got = await store.get_section(sym, statement, "financials")
        if not got:
            continue
        fin = orjson.loads(got[0])
        summ = await store.get_section(sym, statement, "summary")
        lender = bool(((orjson.loads(summ[0]) if summ else {}).get("dataQuality") or {}).get("isBank"))
        inp = build_inputs({"dataQuality": {"isBank": lender}}, fin, None, None)
        if len(inp.fy) >= 4:
            out.append(Company(sym, hist_from_inputs(inp), table.sector[i], table.industry[i], table.cap[i]))
    return out


def md(rows, head):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--statement", default="consolidated")
    ap.add_argument("--limit", type=int, default=800)
    ap.add_argument("--min-history", type=int, default=3)
    a = ap.parse_args()
    universe = asyncio.run(load(a.statement, a.limit))
    rows = run(universe, min_history=a.min_history)
    print(f"# Outlook back-test: {len(universe)} companies, {len(rows)} forecasts with a later actual\n")
    for by, title in (("horizon", "By horizon"), ("sector", "By horizon and sector"), ("size", "By horizon and size bucket")):
        print(f"## {title}\n")
        s = summarise(rows, by)
        print(md([[x["kind"], x["group"], x["n"], x["maeCr"], x["mapePct"], x["medianApePct"], x["biasPct"], "" if sample_ok(x["n"]) else "few"] for x in s],
                 ["Kind", "Group", "Forecasts", "MAE (Rs Cr)", "MAPE %", "Median APE %", "Bias %", "Sample"]))
        print()


if __name__ == "__main__":
    main()
