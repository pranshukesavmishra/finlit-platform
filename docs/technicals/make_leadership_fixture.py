"""Builds frontend/src/lib/__fixtures__/leadershipList.json: a /api/stocks/TCS/leadership answer for a stock on the indicator's IT list, with the numbers taken from
the package's own output (finlit_technicals v1.1 peer_label) on synthetic prices (the real prices of the IT names are not in this repository).
    python3 docs/technicals/make_leadership_fixture.py /path/to/finlit_technicals_repo_root
Only the words (display line, reliability sentence) come from this site's own functions, so the page shows exactly what the API would send. Used by
frontend/src/stock/Leadership.test.tsx and for the screenshots; nothing here is a real company's figure.
"""
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(sys.argv[1])))
sys.path.insert(0, str(ROOT / "backend"))
import pandas as pd  # noqa: E402
from finlit_technicals import MemorySource, peer_label  # noqa: E402
from finlit import leadership as L  # noqa: E402

NAMES = {"TCS": "Tata Consultancy Services", "INFY": "Infosys", "HCLTECH": "HCL Technologies", "WIPRO": "Wipro", "TECHM": "Tech Mahindra", "LTM": "LTIMindtree", "PERSISTENT": "Persistent Systems",
         "COFORGE": "Coforge", "MPHASIS": "Mphasis", "OFSS": "Oracle Financial Services Software", "KPITTECH": "KPIT Technologies", "HEXT": "Hexaware Technologies", "TATAELXSI": "Tata Elxsi", "BSOFT": "Birlasoft"}
END = date(2026, 10, 23)


def gauss(r):
    return math.sqrt(-2 * math.log(1 - r.random())) * math.cos(2 * math.pi * r.random())


def frame(seed, weeks, drift, vol, p0, thin=False, tail=0):
    r = random.Random(seed)
    price, rows = p0, []
    fridays = [END - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]
    for d in fridays[: weeks - tail]:
        price *= math.exp(drift + vol * gauss(r))
        v = math.exp(13.5 + 0.4 * gauss(r)) * (0.0005 if thin else 1)
        for k in range(5):
            day = d - timedelta(days=4 - k)
            rows.append((day, price, price, price, price, v / 5))
    f = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    f.index = pd.DatetimeIndex(f.index)
    return f


def build(seed):
    r = random.Random(seed)
    stocks = {s: frame(seed * 100 + i, 150, 0.0010 + 0.0016 * gauss(r), 0.03, 100 + 40 * i, thin=(s == "OFSS")) for i, s in enumerate(NAMES) if s not in ("HEXT", "BSOFT")}
    stocks["BSOFT"] = frame(seed * 100 + 99, 40, 0.0010, 0.03, 100)      # under a year of prices
    src = MemorySource(stocks, {"NSE:CNXIT": frame(seed + 1, 150, 0.0012, 0.015, 30000), "NSE:NIFTY": frame(seed + 2, 150, 0.0010, 0.012, 24000)})
    return peer_label("TCS", src, cap="large", table="all", history_weeks=52, group="it")


if __name__ == "__main__":
    d = None
    for seed in range(1, 80):
        d = build(seed)
        if d["pending"] and d["state"] == 0 and d["not_ranked"] and 0 < d["rank"] and d["table_more"] == 0 and d["label"] == "Leader" and d["direction"]:
            break
    assert d and d["pending"], "no seed produced a label that differs from this week's answer"
    code = {"Leader": "leader", "In line": "in_line", "Laggard": "laggard", None: None}
    rel = d["relative_return_pts"]
    f = lambda x: None if x is None else round(x / 100, 6)
    label, raw = code[d["label"]], code[d["this_week"]]
    shown = L.display(label=label, rank=d["rank"], ranked=d["ranked"], group_short="IT", sector_name=d["benchmarks"]["sector"], market_name=d["benchmarks"]["market"], rel52=f(rel["vs_sector_12m"]),
                      rel52_market=f(rel["vs_market_12m"]), direction=d["direction"] if d["direction"] in ("gaining", "weakening") else None, fundamental=None, fund_rank=None, fund_n=None)
    shown["pending"] = L.pending_line(raw, label)
    groups, _ = L.load_lists()
    it = next(g for g in groups if g.id == "pl-it")
    reliability = L.spec_reliability(it)
    reliability["sentence"] = L.reliability_sentence("IT", reliability)
    reliability["source"] = "spec"
    peers = []
    for t in d["table"]:
        peers.append({"symbol": t["symbol"], "name": NAMES[t["symbol"]], "rank": t["rank"], "label": code[t["status"]], "rawLabel": code[t["this_week"]], "direction": None,
                      "rel13": f(t["vs_sector_3m"]), "rel52": f(t["vs_sector_12m"]), "rel52Market": f(t["vs_market_12m"]), "marketCap": None})
    reasons = {"not found / no data": ("no_prices", L.UNRANKED_TEXT["no_prices"]), "under 52 weeks of prices": ("history", L.UNRANKED_TEXT["history"])}
    not_ranked = [{"symbol": n["symbol"], "name": NAMES[n["symbol"]], "reason": reasons.get(n["reason"], ("liquidity", "Too thinly traded"))[0],
                   "text": reasons.get(n["reason"], ("liquidity", L.UNRANKED_TEXT["liquidity"]))[1]} for n in d["not_ranked"]]
    out = {"available": True, "asOf": END.isoformat(), "stale": False, "held": False,
           "peerGroup": {"id": "pl-it", "name": "IT", "short": "IT", "kind": "industry", "ranked": d["ranked"], "source": "list", "listed": 14, "listAsOf": "2026-10-27", "leaderSlots": d["leader_slots"]},
           "benchmarks": {"sector": {"code": "NIFIT", "name": d["benchmarks"]["sector"], "kind": "index", "ret52": None}, "market": {"code": "NIF50", "name": d["benchmarks"]["market"], "ret52": None}},
           "rel": {"w13": f(rel["vs_sector_3m"]), "w26": f(rel["vs_sector_6m"]), "w52": f(rel["vs_sector_12m"]), "w52Market": f(rel["vs_market_12m"])},
           "rank": d["rank"], "label": label, "rawLabel": raw, "direction": d["direction"] if d["direction"] in ("gaining", "weakening") else None,
           "fundamentalNote": None, "fundamentalRank": None, "fundamentalOf": None, "labelSince": d["since"], "sectorReliability": reliability, "display": shown, "peers": peers,
           "notRanked": not_ranked, "runs52": {"leader": d["runs_last_52"]["leader"], "in_line": d["runs_last_52"]["in_line"], "laggard": d["runs_last_52"]["laggard"], "total": d["runs_last_52"]["runs"]}}
    path = ROOT / "frontend/src/lib/__fixtures__/leadershipList.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path, d["status"], "|", d["pending"], "|", [n["symbol"] for n in d["not_ranked"]])
