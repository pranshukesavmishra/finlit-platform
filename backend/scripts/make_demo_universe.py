"""Builds frontend/public/demo/screener.json for the no-backend demo.

RELIANCE is the real exported report. Every other row is a *fictional* sample company (symbols start with SMP-)
so the screener and comparison can be shown working end to end without presenting invented numbers as real ones.
Usage: python scripts/make_demo_universe.py ../frontend/public/demo
"""
import json, random, sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/public/demo")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finlit.snapshot import score_row  # noqa: E402

sec = {k: json.load(open(out / "RELIANCE" / f"{k}.json")) for k in ("summary", "ratios")}
real = score_row({"summary": sec["summary"]})
real = {k: v for k, v in real.items() if k not in ("statement", "model")}

SECTORS = {"Refineries & Marketing": 1, "IT Services": 3, "Private Banks": 3, "Auto & Ancillaries": 3, "FMCG": 3,
           "Pharmaceuticals": 3, "Metals & Mining": 2, "Power Utilities": 2, "Capital Goods": 3, "Insurance": 2}
PREFIX = {"Refineries & Marketing": "Energy", "IT Services": "Systems", "Private Banks": "Bank", "Auto & Ancillaries": "Motors",
          "FMCG": "Consumer", "Pharmaceuticals": "Pharma", "Metals & Mining": "Steel", "Power Utilities": "Power",
          "Capital Goods": "Engineering", "Insurance": "Assurance"}
GREEK = ["Alpha", "Beta", "Gamma", "Delta", "Omega", "Sigma"]
rnd = random.Random(2610)
clamp = lambda x, lo, hi: max(lo, min(hi, x))
band = lambda o: "strong" if o >= 78 else "healthy" if o >= 62 else "mixed" if o >= 45 else "watch"
rows = [real]
for sector, n in SECTORS.items():
    if sector == "Refineries & Marketing":
        n = 3  # real RELIANCE already lives in this sector
    for i in range(n):
        q = rnd.uniform(0.15, 0.95)  # a hidden "business quality" drives the metrics so they hang together
        roe, roce = round(5 + q * 24 + rnd.uniform(-2, 2), 1), round(6 + q * 26 + rnd.uniform(-2, 2), 1)
        pe = round(clamp(8 + q * 28 + rnd.uniform(-5, 9), 6, 70), 1)
        pb = round(clamp(pe * roe / 100 * rnd.uniform(0.8, 1.2), 0.6, 14), 1)
        de = round(clamp((1 - q) * 1.6 + rnd.uniform(-0.2, 0.3), 0.0, 2.6), 2)
        sg, pg = round(2 + q * 18 + rnd.uniform(-3, 4), 1), round(-2 + q * 24 + rnd.uniform(-6, 8), 1)
        pillars = {
            "pillar_quality": int(clamp(25 + q * 60 + rnd.uniform(-8, 8), 8, 96)),
            "pillar_growth": int(clamp(20 + (sg + pg) * 1.6 + rnd.uniform(-6, 6), 8, 96)),
            "pillar_profitability": int(clamp(22 + roe * 2.2 + rnd.uniform(-6, 6), 8, 96)),
            "pillar_balance": int(clamp(95 - de * 32 + rnd.uniform(-6, 6), 8, 96)),
            "pillar_technical": int(clamp(rnd.uniform(18, 88), 8, 96)),
        }
        overall = round(sum(pillars.values()) / 5)
        sym = f"SMP-{PREFIX[sector][:3].upper()}{i + 1}"
        rows.append({
            "symbol": sym, "name": f"Sample {PREFIX[sector]} {GREEK[i % 6]} Ltd", "sector": sector, "sample": True,
            "overall": overall, "band": band(overall), **pillars,
            "price": round(rnd.uniform(120, 4200), 2), "market_cap": round(rnd.uniform(4000, 900000), 0),
            "pe": pe, "pb": pb, "roe": roe, "roce": roce, "dividend_yield": round(clamp(rnd.uniform(0.1, 3.8) * (1.2 - q * 0.4), 0, 4.5), 2),
            "debt_to_equity": de, "sales_cagr": sg, "profit_cagr": pg, "operating_margin": round(clamp(6 + q * 26 + rnd.uniform(-3, 3), 3, 40), 1),
            "change_pct": round(rnd.uniform(-2.4, 2.8), 2), "return_1m": round(rnd.uniform(-9, 11), 1), "return_1y": round(rnd.uniform(-26, 38), 1),
        })
json.dump({"rows": rows, "sample": True}, open(out / "screener.json", "w"), separators=(",", ":"))
print(len(rows), "rows ->", out / "screener.json")
