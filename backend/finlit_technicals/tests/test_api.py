"""Tests for the website layer: sources, JSON output, batch, command line and the Flask example."""
import contextlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from finlit_technicals import CsvFolder, MemorySource, canonical, peer_label, score
from finlit_technicals import api as A
from finlit_technicals import batch as B
from finlit_technicals import peers as PR

ROOT = Path(__file__).resolve().parents[1]


def synth(n, seed, start="2023-06-01", drift=0.0004, vol=0.018, p0=100.0):
    r = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    c = p0 * np.exp(np.cumsum(r.normal(drift, vol, n)))
    o = c * np.exp(r.normal(0, 0.006, n))
    h = np.maximum(o, c) * np.exp(np.abs(r.normal(0, 0.008, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(r.normal(0, 0.008, n)))
    v = r.lognormal(13, 0.5, n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)


def steel_world(tmp: Path) -> Path:
    """A CsvFolder with SAMBHV, its Steel peers and every index the two indicators ask for."""
    d = tmp / "prices"
    (d / "stocks").mkdir(parents=True)
    (d / "indices").mkdir(parents=True)
    g = PR.resolve("SAMBHV", A.peer_db(), PR.PeerParams(max_peers=37))
    for k, s in enumerate(g.symbols):
        df = synth(700, 100 + k, drift=0.0003 * (k % 5 - 2))
        df.index.name = "date"
        df.to_csv(d / "stocks" / f"{s.split(':')[-1]}.csv")
    for k, code in enumerate(["CNX500", "NIFTY", "CNXMIDCAP", "CNXSMALLCAP", "NIFTYMIDCAP150", "NIFTYSMLCAP250", "CNXMETAL"]):
        df = synth(700, 300 + k, vol=0.01, p0=10000)
        df.index.name = "date"
        df.to_csv(d / "indices" / f"{code}.csv")
    return d


def no_nan(x):
    if isinstance(x, dict):
        return all(no_nan(v) for v in x.values())
    if isinstance(x, list):
        return all(no_nan(v) for v in x)
    return not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def test_score_json(tmp_path):
    src = CsvFolder(steel_world(tmp_path))
    d = score("sambhv", src, cap="small")
    json.dumps(d, allow_nan=False)                                   # strict JSON
    assert no_nan(d)
    assert d["symbol"] == "SAMBHV" and d["benchmark"] == "Smallcap 100"
    st, lt = d["short_term"], d["long_term"]
    assert len(st["components"]) == 15 and len(lt["components"]) == 14
    assert [c["key"] for c in st["components"]][:3] == ["ema_stack", "price_vs_ema20", "macd"]
    assert all(c["how"] for c in st["components"] + lt["components"])
    on = [c for c in st["components"] if c["on"]]
    assert abs(sum(c["points"] for c in on) - st["score"]) < 0.05       # points are rounded to 2 decimals
    assert sum(c["weight"] for c in st["components"]) == st["divisor"] == 96 and lt["divisor"] == 92
    v = d["trend_alignment"]
    assert v["label"] == A.S.alignment(st["band_code"], lt["band_code"])
    assert st["band"] == {1: "Positive", 0: "Neutral", -1: "Negative"}[st["band_code"]]
    assert st["rating"] == A.S.RATINGS[st["rating_code"]] and lt["rating"] == A.S.RATINGS[lt["rating_code"]]
    assert len(v["cells"]) == 9 and sum(c["current"] for c in v["cells"]) == 1
    cur = [c for c in v["cells"] if c["current"]][0]
    assert cur["label"] == v["label"] and cur["code"] == v["code"]
    # no trade-call wording anywhere in the output
    text = json.dumps(d).lower()
    for word in ("buy", "sell", "verdict", "accumulate", "avoid", "reduce", "invest\"", "don't invest", "wait for"):
        assert word not in text, word
    pr = d["peers"]
    assert pr["group"]["name"] == "Steel" and pr["benchmarks"]["sector"] == "Nifty Metal"
    assert pr["benchmarks"]["market"] == "Nifty Smallcap 250" and "table" not in pr
    assert pr["indicator"].startswith("ST/LT Score Breakdown")


def test_market_cap_picks_the_benchmark(tmp_path):
    src = CsvFolder(steel_world(tmp_path))
    assert score("SAMBHV", src, peers=False)["benchmark"] == "Nifty 500"           # unknown cap
    assert score("SAMBHV", src, peers=False, market_cap_cr=4500)["benchmark"] == "Smallcap 100"
    assert score("SAMBHV", src, peers=False, market_cap_cr=50000)["benchmark"] == "Midcap 100"
    assert score("SAMBHV", src, peers=False, market_cap_cr=200000)["benchmark"] == "Nifty 50"
    assert score("SAMBHV", src, peers=False, cap="large", bench="nifty500")["benchmark"] == "Nifty 500"
    assert peer_label("SAMBHV", src, market_cap_cr=50000)["benchmarks"]["market"] == "Nifty Midcap 150"
    try:
        score("SAMBHV", src, cap="tiny")
        raise AssertionError("bad cap accepted")
    except ValueError:
        pass


def test_peer_label_json(tmp_path):
    src = CsvFolder(steel_world(tmp_path))
    d = peer_label("SAMBHV", src, cap="small", table="all", history_weeks=20)
    json.dumps(d, allow_nan=False)
    assert d["indicator"] == "Leader & Laggard vs Peers v1.0"
    assert d["state"] == 0 and d["label"] in ("Leader", "In line", "Laggard") and d["label_code"] in (1, 0, -1)
    assert d["ranked"] == len(d["table"]) == 35 and d["table_more"] == 0 and d["not_ranked"] == []
    assert [t["rank"] for t in d["table"]] == list(range(1, 36))
    x = [t["vs_sector_12m"] for t in d["table"]]
    assert x == sorted(x, reverse=True)
    me = [t for t in d["table"] if t["is_self"]][0]
    assert me["rank"] == d["rank"] and me["vs_sector_12m"] == d["relative_return_pts"]["vs_sector_12m"]
    assert len(d["history"]) == 20 and d["history"][-1]["week"] == d["week_ranked"]
    top = peer_label("SAMBHV", src, cap="small", table="top10", history_weeks=0)
    assert len(top["table"]) in (10, 11) and top["table_more"] == 35 - len(top["table"]) and "history" not in top
    peers = peer_label("SAMBHV", src, peer_list="JSWSTEEL,TATASTEEL,SAIL,JSL,GPIL,KSL,NSLNISP", table=None)
    assert peers["group"]["kind"] == "custom" and peers["benchmarks"]["sector_is_peer_average"] and "table" not in peers


def test_peer_caps_break_ties_and_spellings(tmp_path):
    src = CsvFolder(steel_world(tmp_path))
    d = peer_label("SAMBHV", src, cap="small", peer_caps={"JSWSTEEL": 300000, "TATASTEEL": 200000})
    assert d["state"] == 0
    assert canonical("m_m") == "M&M" and canonical("NSE:bajaj-auto") == "BAJAJ_AUTO"


def test_missing_data(tmp_path):
    root = steel_world(tmp_path)
    (root / "indices" / "CNXMETAL.csv").unlink()
    for s in ("JSWSTEEL", "TATASTEEL"):
        (root / "stocks" / f"{s}.csv").unlink()
    d = peer_label("SAMBHV", CsvFolder(root), cap="small")
    assert d["benchmarks"]["sector_is_peer_average"] and any("no prices for 2 peer" in n for n in d["notes"])
    assert {x["symbol"] for x in d["not_ranked"]} == {"JSWSTEEL", "TATASTEEL"}
    try:
        score("NOSUCH", CsvFolder(root))
        raise AssertionError("missing stock accepted")
    except LookupError:
        pass
    mem = MemorySource({"ABC": synth(30, 1)})                         # a 30-day listing, nothing else
    d = score("ABC", mem)
    json.dumps(d, allow_nan=False)
    assert d["peers"]["label"] == "No label" and any("daily bars" in n for n in d["notes"])


def test_csv_reader_variants(tmp_path):
    d = tmp_path / "p"
    (d / "stocks").mkdir(parents=True)
    df = synth(300, 5)
    out = df.reset_index().rename(columns={"index": "Date", "close": "Close", "volume": "Volume", "open": "Open",
                                           "high": "High", "low": "Low"})
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize("Asia/Kolkata").astype(str)
    out.to_csv(d / "stocks" / "M_M.csv", index=False)
    got = CsvFolder(d).daily("M&M")
    assert len(got) == 300 and list(got.columns) == ["open", "high", "low", "close", "volume"]
    assert got.index[0] == pd.Timestamp(df.index[0]) and abs(got["close"].iloc[-1] - df["close"].iloc[-1]) < 1e-9


def test_batch(tmp_path):
    src = CsvFolder(steel_world(tmp_path))
    caps_csv = tmp_path / "caps.csv"
    caps_csv.write_text("symbol,mcap_cr,cap\nSAMBHV,4500,\nJSWSTEEL,240000,\n", encoding="utf-8")
    syms = ["SAMBHV", "JSWSTEEL", "NOSUCH"]
    res = B.run(syms, src, tmp_path / "out", caps=B.read_caps(caps_csv))
    assert [r["symbol"] for r in res] == syms and "error" in res[2] and "error" not in res[0]
    one = json.loads((tmp_path / "out" / "SAMBHV.json").read_text())
    assert one["score"]["benchmark"] == "Smallcap 100" and one["peers"]["benchmarks"]["market"] == "Nifty Smallcap 250"
    assert json.loads((tmp_path / "out" / "JSWSTEEL.json").read_text())["score"]["benchmark"] == "Nifty 50"
    summ = json.loads((tmp_path / "out" / "_summary.json").read_text())
    assert summ["meta"]["stocks"] == 3 and summ["meta"]["errors"] == 1
    # the same numbers as the one-stock functions
    direct = score("SAMBHV", src, market_cap_cr=4500, peer_caps={"SAMBHV": 4500, "JSWSTEEL": 240000})
    assert direct["short_term"] == one["score"]["short_term"] and direct["trend_alignment"] == one["score"]["trend_alignment"]
    line = [x for x in summ["stocks"] if x["symbol"] == "SAMBHV"][0]
    assert {"st_band", "lt_band", "trend_alignment", "trend_alignment_code"} <= set(line) and "verdict" not in line
    u = B.universe()
    assert len(u) == len(set(u)) > 1000 and "SAMBHV" in u


def _cli(args):
    from finlit_technicals.__main__ import main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(args)
    return code, buf.getvalue()


def test_cli(tmp_path):
    data = str(steel_world(tmp_path))
    code, out = _cli(["score", "SAMBHV", "--data", data, "--cap", "small"])
    assert code == 0 and "SHORT-TERM SCORE" in out and "TREND ALIGNMENT" in out and "Steel peers" in out
    assert "buy" not in out.lower() and "sell" not in out.lower()
    code, out = _cli(["score", "SAMBHV", "--data", data, "--json", "--no-peers"])
    assert code == 0 and json.loads(out)["benchmark"] == "Nifty 500"
    code, out = _cli(["peers", "SAMBHV", "--data", data, "--all", "--weeks", "3"])
    assert code == 0 and "Peers · Steel · vs Nifty Metal" in out and "Week ranked" in out
    code, out = _cli(["peers", "NOSUCH", "--data", data])
    assert code == 2
    code, out = _cli(["batch", "--data", data, "--out", str(tmp_path / "o"), "--symbols", "SAMBHV,SAIL"])
    assert code == 0 and (tmp_path / "o" / "SAIL.json").exists()


def test_flask_example(tmp_path):
    try:
        import flask  # noqa: F401
    except ImportError:
        return                                                          # Flask is only for the example
    sys.path.insert(0, str(ROOT / "examples"))
    import flask_app
    data = steel_world(tmp_path)
    B.run(["SAMBHV"], CsvFolder(data), tmp_path / "site")
    app = flask_app.create_app(str(data), str(tmp_path / "site"))
    c = app.test_client()
    r = c.get("/api/technicals/sambhv/score")
    assert r.status_code == 200 and r.get_json()["symbol"] == "SAMBHV"
    assert list(r.get_json().keys())[:2] == ["indicator", "symbol"]          # order kept
    r = c.get("/api/technicals/SAMBHV/peers?cap=small&table=all&weeks=4")
    assert r.status_code == 200 and len(r.get_json()["history"]) == 4
    assert c.get("/api/technicals/SAIL/score").status_code == 200           # not precomputed: live
    assert c.get("/api/technicals/NOSUCH/score").status_code == 404
    assert c.get("/api/technicals/SAMBHV/score?cap=tiny").status_code == 400
    assert c.get("/api/technicals/summary").get_json()["meta"]["stocks"] == 1
