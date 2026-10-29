"""Builds backend/finlit/data/leadership_groups.json, the peer lists behind the Leader / In line / Laggard label, from the team's package
(finlit_technicals v1.1: finlit_technicals/data/peer_groups.json and the five curated groups of peers.py).

    python backend/scripts/make_leadership_groups.py /path/to/finlit_technicals/data/peer_groups.json            (rewrites the data file)

To refresh the lists (the package says its lists are 'as of 27 Oct 2026'): get a newer peer_groups.json from the team, run this, run the tests, commit the
data file. The order inside every list is kept (the first group that holds a stock is its home). Nothing else reads the package.
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "finlit" / "data" / "leadership_groups.json"
AS_OF = "2026-10-27"

# The developer spec's five researched groups (peers.py LL_IT ... LL_AU), with the NSE sector index each is measured against.
CURATED = [
    ("it", "IT", "NSE:CNXIT", "TCS,INFY,HCLTECH,WIPRO,TECHM,LTM,PERSISTENT,COFORGE,MPHASIS,OFSS,KPITTECH,HEXT,TATAELXSI,BSOFT"),
    ("pharma", "pharma", "NSE:CNXPHARMA", "SUNPHARMA,CIPLA,DRREDDY,DIVISLAB,LUPIN,AUROPHARMA,ZYDUSLIFE,TORNTPHARM,ALKEM,MANKIND,GLENMARK,BIOCON,GLAND,IPCALAB,AJANTPHARM,ABBOTINDIA"),
    ("private-bank", "private bank", "NSE:NIFTYPVTBANK", "HDFCBANK,ICICIBANK,KOTAKBANK,AXISBANK,INDUSINDBK,IDFCFIRSTB,FEDERALBNK,BANDHANBNK,RBLBANK,YESBANK,CUB,KARURVYSYA,AUBANK"),
    ("psu-bank", "PSU bank", "NSE:CNXPSUBANK", "SBIN,BANKBARODA,PNB,CANBK,UNIONBANK,INDIANB,BANKINDIA,IOB,CENTRALBK,MAHABANK,UCOBANK,PSB"),
    ("auto-sector", "auto sector", "NSE:CNXAUTO", "MARUTI,M&M,TMPV,HYUNDAI,BAJAJ_AUTO,EICHERMOT,HEROMOTOCO,TVSMOTOR,ASHOKLEY,TMCV,BOSCHLTD,MOTHERSON,BHARATFORG,MRF,APOLLOTYRE,BALKRISIND,EXIDEIND,SONACOMS,UNOMINDA,ESCORTS"),
]
# NSE index code (the package's) -> this site's index code and name (indices.py)
INDEX_MAP = {"NSE:CNXIT": ("NIFIT", "Nifty IT"), "NSE:CNXPHARMA": ("NIFPHA", "Nifty Pharma"), "NSE:NIFTYPVTBANK": ("NIFPRIBAN", "Nifty Private Bank"),
             "NSE:CNXPSUBANK": ("NIFPSUBAN", "Nifty PSU Bank"), "NSE:CNXAUTO": ("NIFAUT", "Nifty Auto"), "NSE:CNXENERGY": ("NIFENE", "Nifty Energy"),
             "NSE:CNXMETAL": ("NIFMET", "Nifty Metal"), "NSE:CNXREALTY": ("NIFREA", "Nifty Realty"), "NSE:CNXFMCG": ("NIFFMC", "Nifty FMCG"),
             "NSE:CNXFINANCE": ("NIFFINSER", "Nifty Financial Services"), "NSE:CNXMEDIA": ("NIFMED", "Nifty Media"), "NSE:CNXINFRA": ("NIFINF", "Nifty Infrastructure")}
# The spec's own backtest (Leader & Laggard vs Peers v1.0 developer spec, since 2005): share of 4-weekly checks where the top 30% beat the bottom 30% over the
# next 6 months. IT, pharma and banks (both bank groups) and auto only. Shown on the reliability card until this site's own backtest has enough history.
SPEC_RELIABILITY = {
    "it": {"checks": 269, "hit": 0.60, "periods": [("2005-09", 0.35), ("2010-14", 0.68), ("2015-19", 0.48), ("2020-26", 0.74)]},
    "pharma": {"checks": 278, "hit": 0.64, "periods": [("2005-09", 0.58), ("2010-14", 0.73), ("2015-19", 0.59), ("2020-26", 0.67)]},
    "private-bank": {"checks": 278, "hit": 0.60, "periods": [("2005-09", 0.59), ("2010-14", 0.59), ("2015-19", 0.76), ("2020-26", 0.43)]},
    "psu-bank": {"checks": 278, "hit": 0.60, "periods": [("2005-09", 0.59), ("2010-14", 0.59), ("2015-19", 0.76), ("2020-26", 0.43)]},
    "auto-sector": {"checks": 278, "hit": 0.46, "periods": [("2005-09", 0.38), ("2010-14", 0.68), ("2015-19", 0.52), ("2020-26", 0.34)]},
}


def index_for(kind: str, name: str) -> str:
    """f_llIdxFor of the indicator: the NSE sector index for a TradingView industry (I) or sector (S); '' = the equal-weighted peer average."""
    if kind == "I":
        if name in ("Oil Refining/Marketing", "Integrated Oil", "Gas Distributors", "Electric Utilities", "Alternative Power Generation"):
            return "NSE:CNXENERGY"
        if name in ("Steel", "Other Metals/Minerals", "Aluminum"):
            return "NSE:CNXMETAL"
        if name == "Real Estate Development":
            return "NSE:CNXREALTY"
        if name == "Household/Personal Care" or name.startswith("Food:") or name.startswith("Beverages"):
            return "NSE:CNXFMCG"
        if name in ("Finance/Rental/Leasing", "Life/Health Insurance", "Investment Banks/Brokers", "Investment Managers", "Financial Conglomerates", "Major Banks", "Regional Banks"):
            return "NSE:CNXFINANCE"
        if name == "Movies/Entertainment":
            return "NSE:CNXMEDIA"
        if name in ("Engineering & Construction", "Construction Materials"):
            return "NSE:CNXINFRA"
        if name in ("Information Technology Services", "Packaged Software"):
            return "NSE:CNXIT"
        if name.startswith("Pharmaceuticals"):
            return "NSE:CNXPHARMA"
        if name in ("Motor Vehicles", "Auto Parts: OEM", "Automotive Aftermarket"):
            return "NSE:CNXAUTO"
        return ""
    return {"Energy Minerals": "NSE:CNXENERGY", "Utilities": "NSE:CNXENERGY", "Finance": "NSE:CNXFINANCE", "Technology Services": "NSE:CNXIT",
            "Health Technology": "NSE:CNXPHARMA", "Consumer Non-Durables": "NSE:CNXFMCG", "Non-Energy Minerals": "NSE:CNXMETAL", "Industrial Services": "NSE:CNXINFRA"}.get(name, "")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build(src: dict) -> dict:
    groups = []
    for gid, name, nse, symbols in CURATED:
        groups.append({"id": "pl-" + gid, "kind": "curated", "name": name, "index": nse, "symbols": symbols.split(","), "reliability": SPEC_RELIABILITY[gid]})
    for name, symbols in src.get("industries", {}).items():
        groups.append({"id": "pl-" + slug(name), "kind": "industry", "name": name, "index": index_for("I", name) or None, "symbols": list(symbols)})
    for name, symbols in src.get("sectors", {}).items():
        groups.append({"id": "pl-" + slug(name) + "-sector", "kind": "sector", "name": name + " sector", "index": index_for("S", name) or None, "symbols": list(symbols)})
    ids = [g["id"] for g in groups]
    assert len(ids) == len(set(ids)), "group ids must be unique"
    return {"_comment": "Peer lists of the Leader / In line / Laggard label (backend/finlit/leadership.py). Generated by backend/scripts/make_leadership_groups.py from finlit_technicals "
                        "v1.1 (TradingView industries and sectors: the 35 largest liquid NSE stocks each, plus the developer spec's five researched groups). The order is kept: "
                        "the first group that holds a stock is its home (curated, then industry, then sector).",
            "asOf": AS_OF, "source": "finlit_technicals v1.1, data/peer_groups.json (27 Oct 2026) and peers.py", "indexMap": {k: {"code": v[0], "name": v[1]} for k, v in INDEX_MAP.items()},
            "groups": groups}


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    data, dump = build(src), lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    lines = ["{"] + [f'"{k}":{dump(data[k])},' for k in ("_comment", "asOf", "source", "indexMap")] + ['"groups":['] + [dump(g) + ("," if i < len(data["groups"]) - 1 else "") for i, g in enumerate(data["groups"])] + ["]", "}"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT, len(json.loads(OUT.read_text())["groups"]), "groups")
