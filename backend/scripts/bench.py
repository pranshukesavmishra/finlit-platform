"""Measure API latency over real HTTP.

    python scripts/bench.py http://localhost:8000 RELIANCE --n 300

Reports p50/p95/p99 for cold-ish (first) and warm requests, per endpoint, plus bytes on the
wire with gzip. Run against the VPS from a laptop in India to see what users get.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

ENDPOINTS = ["/api/stocks/{s}", "/api/stocks/{s}/financials", "/api/stocks/{s}/ratios", "/api/stocks/{s}/price?range=1Y",
             "/api/stocks/{s}/ownership", "/api/stocks/{s}/events", "/api/stocks/search-index"]


def pct(samples, q):
    return statistics.quantiles(samples, n=100)[q - 1] if len(samples) > 2 else max(samples)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("symbol")
    parser.add_argument("--n", type=int, default=200)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, headers={"Accept-Encoding": "gzip"}, http2=False) as client:
        print(f"{'endpoint':<36} {'bytes(gz)':>10} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'server ms':>10}")
        for template in ENDPOINTS:
            path = template.format(s=args.symbol)
            samples, server = [], []
            size = 0
            for _ in range(args.n):
                t = time.perf_counter()
                r = await client.get(path)
                samples.append((time.perf_counter() - t) * 1000)
                r.raise_for_status()
                size = int(r.headers.get("content-length") or len(r.content))
                timing = r.headers.get("server-timing", "")
                if "dur=" in timing:
                    server.append(float(timing.split("dur=")[1]))
            print(f"{path:<36} {size:>10} {statistics.median(samples):>8.2f} {pct(samples, 95):>8.2f} {pct(samples, 99):>8.2f} "
                  f"{(statistics.median(server) if server else float('nan')):>10.2f}")

        # A full page load: summary first, then everything else in parallel.
        t = time.perf_counter()
        await client.get(f"/api/stocks/{args.symbol}")
        first_paint = (time.perf_counter() - t) * 1000
        await asyncio.gather(*(client.get(p.format(s=args.symbol)) for p in ENDPOINTS[1:]))
        print(f"\npage data: summary {first_paint:.1f} ms, all sections {(time.perf_counter() - t) * 1000:.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())
