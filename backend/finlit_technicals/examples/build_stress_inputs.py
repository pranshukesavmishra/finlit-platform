"""Nightly job for Stress Lab: one pack per company from FinLit's own API, and today's macro inputs.

    FINLIT_API=https://finlitventures.com FINLIT_API_HEADER="Authorization: Bearer <service token>" \\
    EIA_API_KEY=<free key from eia.gov> python examples/build_stress_inputs.py --symbols ASIANPAINT,BERGEPAINT --out packs

Run it on the server after the nightly fundamentals and macro refresh, then:
    python -m finlit_technicals stress-batch --packs packs --today packs/_today.json --out site_data/stress
On the server it is simpler to read the same tables from the database; the field names are the API's.
Tokens are read from the environment and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finlit_technicals import stress  # noqa: E402

API = os.environ.get("FINLIT_API", "https://finlitventures.com").rstrip("/")
EIA = "https://api.eia.gov/v2/petroleum/pri/spt/data/"


def get(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "finlit-stress-job/1.0"})
    h = os.environ.get("FINLIT_API_HEADER")
    if h and url.startswith(API) and ":" in h:
        k, v = h.split(":", 1)
        req.add_header(k.strip(), v.strip())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def brent_daily(start: str = "2017-04-01"):
    """Europe Brent spot (series RBRTE), daily, from EIA's API v2. Public-domain data; needs a free API key."""
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise SystemExit("set EIA_API_KEY (free from eia.gov/opendata) or pass --brent-csv")
    url = (f"{EIA}?api_key={key}&frequency=daily&data[0]=value&facets[series][]=RBRTE&start={start}"
           "&sort[0][column]=period&sort[0][direction]=asc&length=5000")
    rows, offset = [], 0
    while True:
        d = get(url + f"&offset={offset}")["response"]["data"]
        rows += [[r["period"], float(r["value"])] for r in d if r.get("value") is not None]
        if len(d) < 5000:
            return rows
        offset += 5000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="comma separated, or a file with one symbol per line")
    ap.add_argument("--out", default="packs")
    ap.add_argument("--brent-csv", help="date,price CSV instead of the EIA API")
    ap.add_argument("--usdinr-json", help="[[date, rate], ...] monthly averages, while FinLit's series has gaps")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    syms = (Path(a.symbols).read_text().split() if Path(a.symbols).exists() else a.symbols.split(","))
    bad = []
    for s in [x.strip().upper() for x in syms if x.strip()]:
        try:
            q = f"query={s}&statement_type=consolidated"
            pack = stress.pack_from_site(get(f"{API}/api/stocks/{s}"), get(f"{API}/api/stocks/{s}/financials"),
                                         get(f"{API}/api/premium/fundamentals?{q}&period=yearly", 120),
                                         get(f"{API}/api/premium/fundamentals?{q}&period=quarterly", 120))
            pack["symbol"] = s
            (out / f"{s}.json").write_text(json.dumps(pack), encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - keep going, report at the end
            bad.append(f"{s}: {e}")
    macro = get(f"{API}/api/macro")
    if a.brent_csv:
        brent = [[ln.split(",")[0], float(ln.split(",")[1])] for ln in Path(a.brent_csv).read_text().splitlines()[1:] if ln]
    else:
        brent = brent_daily()
    today = {"as_of": macro.get("today"), "series": macro["series"], "brent": brent}
    if a.usdinr_json:
        today["usdinr"] = json.loads(Path(a.usdinr_json).read_text())
    (out / "_today.json").write_text(json.dumps(today), encoding="utf-8")
    (out / "_macro_fy.json").write_text(json.dumps(stress.macro_fy_from_series(macro, brent, today.get("usdinr"))),
                                        encoding="utf-8")
    print(f"{len(syms) - len(bad)} packs written to {out}; today's inputs in _today.json")
    for b in bad:
        print("  skipped", b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
