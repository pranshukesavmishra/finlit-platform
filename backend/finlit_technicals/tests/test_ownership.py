"""Ownership insight rules, checked on five real companies read from FinLit on 4 Nov 2026."""
import json
import re
from pathlib import Path

from finlit_technicals import ownership as O

FX = json.loads((Path(__file__).parent / "fixtures" / "ownership.json").read_text(encoding="utf-8"))


def view(sym):
    return O.analyse({"symbol": sym, **FX[sym]})


def ids(v):
    return [s["id"] for s in v["signals"]]


def test_reliance_rotation_and_extremes():
    v = view("RELIANCE")
    assert ids(v)[:2] == ["I3", "P1"]
    assert "domestic institutions rose to 21.7% (+1.4 pts) while foreign institutions fell to 16.7% (−2.0 pts)" in v["headline"][0]
    assert "from 27.7% to 16.7%" in v["headline"][0] and "from 11.0% to 21.7%" in v["headline"][0]
    i4 = next(s for s in v["signals"] if s["id"] == "I4")
    assert i4["facts"]["lows"] == ["fii"] and i4["facts"]["highs"] == ["dii"]
    assert any("50.7 lakh" in s["text"] for s in v["signals"])                      # shareholders +15%
    assert any("NPS Trust raised its stake to 1.62% from 1.10%" in s["text"] for s in v["signals"])
    # the rotation sentence covers the two trend sentences, so they stay out of the headline
    assert not any("3 quarters in a row" in h for h in v["headline"])


def test_sbi_share_issue_is_not_a_sale():
    v = view("SBIN")
    p3 = v["signals"][0]
    assert p3["id"] == "P3" and "did not sell" in p3["text"] and p3["facts"]["share_count_change_pct"] == 3.43
    assert "P2" not in ids(v) and "S1" not in ids(v)


def test_wheels_promoters_took_part_in_the_issue():
    v = view("WHEELS")
    p1 = v["signals"][0]
    assert p1["id"] == "P1" and p1["facts"]["held_change_pct"] > 7 and "9.9%" in p1["text"]
    assert "R1" in ids(v) and "I3" not in ids(v)                                    # DII −3.4 vs FII +1.5: not a rotation
    assert any(s["id"] == "P9" and s["facts"]["locked"] > 29 for s in v["signals"])


def test_new_listing_sale_lock_in_and_float():
    v = view("LOTUSDEV")
    assert ids(v)[:3] == ["P2", "P9", "P6"]
    assert "52.0%" in v["signals"][1]["text"] and "25% public shareholding" in v["signals"][2]["text"]
    assert any(s["id"] == "I5" and s["group"] == "fii" for s in v["signals"])
    assert all(r["change_3y"] is None for r in v["table"])                          # only six filings


def test_pledge_and_steady_promoters():
    v = view("ASIANPAINT")
    assert v["signals"][0]["id"] == "P7" and "10.4%" in v["signals"][0]["text"]
    assert "P4" in ids(v)


def test_dilution_noise_and_rounding_helpers():
    assert O.pct(18.65) == "18.7%" and O.pts(-1.98) == "−2.0 pts" and O.pts(0.04) == "+0.04 pts"
    assert O.count_in(5072457) == "50.7 lakh" and O.count_in(76317) == "76,317" and O.count_in(25_000_000) == "2.50 crore"
    flat = {"periods": ["Q1", "Q2", "Q3", "Q4", "Q5"], "series": {"promoters": [45, 45.02, 45.01, 45.03, 45.02],
                                                                  "fii": [20, 20.01, 20, 20.02, 20.01],
                                                                  "dii": [10] * 5, "public": [24.98, 24.97, 24.99, 24.95, 24.97]}}
    v = O.analyse(flat)
    assert v["signals"] == [] and len(v["headline"]) == 0


def test_buyback_and_pledge_release():
    pack = {"periods": ["Q1", "Q2", "Q3", "Q4", "Q5"],
            "series": {"promoters": [60, 60, 60, 60, 61.2], "fii": [10] * 5, "dii": [10] * 5, "public": [20, 20, 20, 20, 18.8]},
            "structure": {"periods": ["Q5", "Q4", "Q3", "Q2", "Q1"], "total_shares": [98, 100, 100, 100, 100],
                          "promoter_pledged_percent": [0, 8, 9, 9, 9]}}
    v = O.analyse(pack)
    assert "S2" in ids(v) and "P8" in ids(v)
    # promoters' share count is unchanged (60% of 100 = 61.2% of 98): the stake rose through the buyback, not buying
    assert "P1" not in ids(v)


def test_site_pack_and_wording():
    own = {"meta": {"symbol": "X"}, "periods": FX["RELIANCE"]["periods"], "series": FX["RELIANCE"]["series"]}
    prem = {"ownershipStructure": [{"category": "total_shares", "history": [{"period": p, "value": 100} for p in FX["RELIANCE"]["periods"][::-1]]}],
            "shareholdingDetails": [{"label": "Institutions domestic", "children": [
                {"label": "LIFE INSURANCE CORPORATION OF INDIA", "history": [{"period": "a", "value": 7.1}, {}, {}, {}, {"period": "e", "value": 6.5}]}]}]}
    pack = O.pack_from_site(own, prem)
    assert pack["holders"] == [["LIFE INSURANCE CORPORATION OF INDIA", "dii", 7.1, 6.5]]
    v = O.analyse(pack)
    assert any("Life Insurance Corporation of India raised its stake to 7.10% from 6.50%" in s["text"] for s in v["signals"])
    for sym in [k for k in FX if not k.startswith("_")]:
        txt = json.dumps(O.analyse({"symbol": sym, **FX[sym]}))
        assert not re.search(r"\b(should|buy now|accumulate|avoid|exit|target price|recommend|bullish|bearish|undervalued)\b", txt, re.I)
    assert len(O.rules_table()) == 21


def test_quiet_text_cli_and_flask(tmp_path):
    import io
    import sys
    from contextlib import redirect_stdout
    flat = {"periods": ["Q1", "Q2", "Q3", "Q4", "Q5"], "series": {"promoters": [45] * 5, "fii": [20] * 5, "dii": [10] * 5, "public": [25] * 5}}
    assert O.analyse(flat)["quiet_text"] == O.QUIET and view("RELIANCE")["quiet_text"] is None
    packs = tmp_path / "packs"
    packs.mkdir()
    for sym in ("RELIANCE", "SBIN"):
        (packs / f"{sym}.json").write_text(json.dumps(FX[sym]), encoding="utf-8")
    (packs / "BROKEN.json").write_text("{", encoding="utf-8")
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert O.cli(["ownership", str(packs / "RELIANCE.json")]) == 0
        assert O.cli(["ownership-batch", "--packs", str(packs), "--out", str(tmp_path / "out")]) == 0
    txt = buf.getvalue()
    assert "RELIANCE ownership, Sep 2026" in txt and "Also in this filing:" in txt and "2 written, 1 failed" in txt
    assert json.loads((tmp_path / "out" / "SBIN.json").read_text(encoding="utf-8"))["signals"][0]["id"] == "P3"
    try:
        import flask  # noqa: F401
    except ImportError:
        return
    sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
    import os
    os.environ["FINLIT_OWNERSHIP"] = str(packs)
    import flask_app
    c = flask_app.create_app(str(tmp_path), str(tmp_path / "site")).test_client()
    assert c.get("/api/ownership/reliance/insights").get_json()["headline"][1].startswith("Promoters raised")
    assert c.get("/api/ownership/NOSUCH/insights").status_code == 404
    assert len(c.get("/api/ownership/rules").get_json()["rules"]) == 21
    r = c.post("/api/ownership/insights", json={"ownership": {"meta": {"symbol": "X"}, **{k: FX["SBIN"][k] for k in ("periods", "series")}}})
    assert r.status_code == 200 and r.get_json()["symbol"] == "X"
    assert c.post("/api/ownership/insights", json={}).status_code == 400


def test_short_cards_for_the_page():
    v = view("RELIANCE")
    assert [c["title"] for c in v["cards"]] == ["Indian funds buying what foreign funds sell", "Promoters raised their stake",
                                                "Foreign funds at 5-year low, Indian funds at high"]
    assert v["cards"][0]["stat"] == "Indian +1.4 pts, foreign −2.0 pts in a year"
    assert v["cards"][1]["stat"] == "50.0% → 50.4% in a year"
    assert len(v["more"]) == len(v["signals"]) - 3 and v["more"][0]["title"] == "Foreign funds selling"
    for sym in [k for k in FX if not k.startswith("_")]:
        w = O.analyse({"symbol": sym, **FX[sym]})
        for c in w["cards"] + w["more"]:
            assert c["title"] and c["stat"] and len(c["title"]) <= 64, (sym, c)
    assert view("WHEELS")["more"][1]["title"] == "Promoters at 5-year low, foreign funds and retail at highs"


def test_share_count_history_for_the_page():
    v = view("RELIANCE")
    sc = v["facts"]["share_count_by_period"]
    assert sc["Sep 2026"] == 1353.25 and "Sep 2023" in sc and "Sep 2021" not in sc       # filings before Sep 2023 not in the fixture
    assert view("SBIN")["facts"]["share_count_by_period"]["Sep 2025"] == 923.062
