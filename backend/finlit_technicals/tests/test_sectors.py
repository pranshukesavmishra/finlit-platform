"""Tests for the NSE data layer (nse.py), the universe rules (universe.py), the sector engine on NSE industries
(sectors.py), the downloader's parsers (fetch.py), and the batch / command line / Flask sector paths."""
import contextlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import nse_fixture as F
from finlit_technicals import MemorySource, NseHistory, SectorEngine, UniverseRules
from finlit_technicals import batch as B
from finlit_technicals import fetch as FE
from finlit_technicals import sectors as SE
from finlit_technicals.universe import build_universe

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("buy", "sell", "accumulate", "avoid", "full size", "half size", "target", "stop loss")


def strict(d):
    json.dumps(d, allow_nan=False)
    return d


def no_advice(d):
    text = json.dumps({k: v for k, v in d.items() if k != "disclaimer"}).lower()
    for w in FORBIDDEN:
        assert w not in text, w


def folder(tmp_path, days=F.DAYS):
    return F.write_folder(tmp_path / "nse", days)


# ─── data layer ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_history_reads_adjusts_and_links(tmp_path):
    d = folder(tmp_path)
    nse = NseHistory(d)
    p = nse.panel
    assert len(p.dates) == F.DAYS                                   # the holiday copy is dropped
    ts = nse.daily("TATASTEEL")
    raw_jump = 0.1
    jump = ts["close"].iloc[F.SPLIT_DAY] / ts["close"].iloc[F.SPLIT_DAY - 1]
    assert abs(jump - 1) < 0.05 and abs(jump - raw_jump) > 0.5      # the 1:10 split leaves no gap
    assert abs(ts["volume"].iloc[F.SPLIT_DAY - 1] - 1e7) < 1        # volumes before it are in today's shares
    assert nse.key(F.RENAMED_FROM) == "VRAJ" and len(nse.daily(F.RENAMED_FROM)) == F.DAYS
    assert nse.key(F.LINK_OLD) == F.LINK_NEW and len(nse.daily(F.LINK_NEW)) == F.DAYS - 2
    assert len(nse.daily(F.DELISTED)) == F.DELIST_DAY
    assert nse.key("BAJAJ_AUTO") is None and nse.daily("NOSUCH") is None
    n = nse.index("NSE:NIFTY")
    assert len(n) == F.DAYS and list(n.columns) == ["open", "high", "low", "close", "volume"]
    assert nse.index("NSE:CNXMETAL") is None
    assert nse.names()["SAIL"] == "Sail Limited"
    assert (d / ".finlit_cache" / "panel.pkl").exists()
    again = NseHistory(d).panel                                     # from the cache
    assert again.keys == p.keys and np.allclose(again.cum, p.cum)


def test_bundled_data_files():
    from finlit_technicals.industries import load_industries
    from finlit_technicals.nse import BUNDLED_ACTIONS, load_actions
    assert BUNDLED_ACTIONS.exists() and len(load_actions(BUNDLED_ACTIONS)) > 1000
    cls = load_industries()
    assert len(cls) > 2800 and cls["TATASTEEL"] == ("Ferrous Metals", "Metals & Mining") and cls["HDFC"][0] == "Finance"
    assert SE.study_figures()["C"]["cases"] == 476


def test_an_unrecorded_split_is_still_removed(tmp_path):
    d = folder(tmp_path)
    (d / "ref" / "corporate_actions.txt").write_text("")
    ts = NseHistory(d, cache=False).daily("TATASTEEL")
    assert abs(ts["close"].iloc[F.SPLIT_DAY] / ts["close"].iloc[F.SPLIT_DAY - 1] - 1) < 0.05


def test_corporate_action_lines_and_factors():
    import datetime as dt
    day = dt.date(2024, 1, 5)
    assert FE.action_lines("A", day, "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share", "10") == ["A 20240105 1/10 S"]
    assert FE.action_lines("A", day, " Fv Splt Frm Rs 10 To Rs 2", "10") == ["A 20240105 2/10 S"]
    assert FE.action_lines("A", day, "Bonus- 1:2", "2") == ["A 20240105 2/3 B"]
    assert FE.action_lines("A", day, "Bonus 1:1 And Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", "10") == ["A 20240105 1/2 B", "A 20240105 2/10 S"]
    assert FE.action_lines("A", day, "Rights Issue 4:17@ Premium Rs 390/-", "10") == ["A 20240105 R 4:17 390 10"]
    assert FE.action_lines("A", day, "Scheme Of Arrangement - Bonus Ncrps 4:1", "1") == []
    assert FE.action_lines("A", day, "Demerger", "10") == ["A 20240105 D"]
    assert FE.action_lines("A", day, "Interim Dividend - Rs 5 Per Share", "1") == []
    from finlit_technicals.nse import adjustment_factors, load_actions
    dates = pd.bdate_range("2024-01-01", periods=6)
    close = np.array([[100.0, 100, 100], [101, 100, 100], [50, 66, 90], [51, 67, 91], [52, 68, 20], [53, 69, 21]])
    opens = close.copy()
    p = Path(__file__).parent / "_acts.txt"
    p.write_text("X 20240103 1/2 B\nY 20240103 R 1:2 0 1\nX 20240103 1/2 B\n")
    try:
        acts = load_actions(p)
    finally:
        p.unlink()
    assert len(acts) == 2                                           # the repeated line counts once
    f, rep = adjustment_factors(dates, ["X", "Y", "Z"], close, opens, acts, {})
    assert f[2, 0] == 0.5 and abs(f[2, 1] - (2 * 100 + 1) / 300) < 1e-9 and rep["rights"] == 1
    assert abs(f[4, 2] - 20 / 91) < 1e-9 and rep["unrecorded"] == 1   # a 78% gap no price band allows


# ─── universe ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_universe_rules_and_reasons(tmp_path):
    eng = SectorEngine(NseHistory(folder(tmp_path)))
    eng._build()
    col, m = eng.col, eng.member
    for s in F.FERROUS + [F.LINK_NEW]:
        assert m[-1, col[s]], s
    expect = {F.LOW_VALUE: "median traded value", F.LOCKED: "price band", F.PENNY: "price under Rs 20",
              F.TO_BE: "EQ series", F.SMALL_CAP: "market cap", F.DELISTED: "no trade on NSE since"}
    for s, why in expect.items():
        assert not m[-1, col[s]], s
        assert any(why in r for r in eng._stock_reasons(s)), (s, eng._stock_reasons(s))
    assert m[F.BE_DAY - 5, col[F.TO_BE]] and not m[F.BE_DAY, col[F.TO_BE]]       # leaves the day it moves to BE
    from finlit_technicals.universe import why_not
    assert any("fewer than 126 sessions" in r for r in why_not(eng.universe, col[F.IPO], F.IPO_DAY + 50))
    assert not m[F.IPO_DAY + 100, col[F.IPO]] and m[-1, col[F.IPO]]                # joins after seasoning
    assert eng.category.get("SAIL") == "Small Cap"


def test_join_and_leave_floors():
    days = 300
    cal = pd.bdate_range("2024-01-01", periods=days)
    c = np.full(days, 100.0)
    vol_a = np.r_[np.full(200, 3e5), np.full(100, 1.5e5)]          # Rs 3 cr a day, then Rs 1.5 cr
    vol_b = np.full(days, 1.5e5)                                    # Rs 1.5 cr a day throughout
    df = lambda v: pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": v}, index=cal)  # noqa: E731
    p = SE.panel_from_source(MemorySource({"A": df(vol_a), "B": df(vol_b)}), ["A", "B"])
    u = build_universe(p, UniverseRules(scale_value=False, use_mcap=False))
    assert u.member[150, 0] and u.member[-1, 0]                    # A joined above Rs 2 cr and stays above Rs 1 cr
    assert not u.member[:, 1].any()                                 # B never reached Rs 2 cr


# ─── the engine on NSE industries ─────────────────────────────────────────────────────────────────────────────────
def test_groups_and_views(tmp_path):
    eng = SectorEngine(NseHistory(folder(tmp_path)))
    b = strict(eng.board())
    names = {r["name"]: r for r in b["rows"]}
    assert "Ferrous Metals" in names and names["Ferrous Metals"]["kind"] == "industry"
    assert names["Ferrous Metals"]["stocks_counted"] == 16          # 14 + the ISIN-linked rename + the seasoned IPO
    few = {x["name"]: x for x in b["too_few_stocks"]}
    assert few["Oil Gas & Consumable Fuels"]["kind"] == "sector" and few["Oil Gas & Consumable Fuels"]["stocks_counted"] == 4
    assert b["market"]["above_200d"] is True and b["market"]["note"]
    assert "Rs 2 crore" in b["universe_rules"] and b["study"]["figures"]["C"]["cases"] == 476
    u = b["universe"]
    assert u["meet_rules"] == u["counted_in_groups_with_reading"] + sum(x["stocks_counted"] for x in b["too_few_stocks"])
    assert u["counted_in_groups_with_reading"] == b["stocks_counted"]
    assert u["not_counted"] == u["stocks_with_industry_traded"] - u["meet_rules"] > 0
    why = {x["reason"]: x["stocks"] for x in u["reasons"]}
    assert any("traded value" in r for r in why) and any("price under Rs 20" in r for r in why)
    no_advice(b)
    d = strict(eng.industry("ferrous-metals", history_sessions=50))
    assert d["slug"] == "ferrous-metals" and len(d["history"]["dates"]) == 50
    counted = [s["symbol"] for s in d["stocks"]]
    assert "VRAJ" in counted and F.LINK_NEW in counted and F.LOW_VALUE not in counted
    assert [s["rank_6m"] for s in d["stocks"] if s["rank_6m"]] == list(range(1, d["ranked_6m"] + 1))
    out = {x["symbol"]: x for x in d["not_counted"]}
    assert F.LOW_VALUE in out and F.DELISTED not in out              # delisted stocks are not listed today
    assert d["bands"][0]["from"] == d["history"]["dates"][0] and d["bands"][-1]["to"] == d["history"]["dates"][-1]
    no_advice(d)
    s = strict(eng.stock(F.RENAMED_FROM))
    assert s["symbol"] == "VRAJ" and s["in_group"] and s["industry"] == "Ferrous Metals" and s["quarter"] in (1, 2, 3, 4)
    s2 = strict(eng.stock(F.DELISTED))
    assert s2["in_group"] is False and "no trade on NSE since" in s2["note"]
    s3 = strict(eng.stock("GAIL"))
    assert s3["group"]["name"] == "Oil Gas & Consumable Fuels" and s3["group"]["state_code"] == "none"
    assert s3["industry"] == "Gas"
    for bad in ("NOSUCH",):
        try:
            eng.stock(bad)
            raise AssertionError("unknown stock accepted")
        except LookupError:
            pass
    try:
        eng.industry("Steel")
        raise AssertionError("a TradingView industry name accepted")
    except LookupError:
        pass
    assert eng.industry("Gas")["name"] == "Oil Gas & Consumable Fuels"   # a small industry opens its sector group


def test_thrust_washout_and_leader_flag(tmp_path):
    eng = SectorEngine(NseHistory(folder(tmp_path, days=552)))
    g = eng.group("Ferrous Metals")
    assert np.nanmin(g.p50[500:550]) < 40                            # washed out in the fall
    ev = np.where(g.ev_c | g.ev_cap)[0]
    assert any(550 <= i <= 551 for i in ev), ev                      # the rebound days are a thrust
    assert g.flag_tier[F.LEADER] == 2                                # 52-week highs while the industry was down
    row = eng.board()["rows"][0]
    assert row["name"] == "Ferrous Metals" and row["state_code"] in ("thrust_c", "thrust_cap")
    # breadth is the plain share of counted stocks above their 9-day EMA
    i = 300
    from finlit_technicals import pine as P
    cols = [eng.col[s] for s in g.members if eng.member[i, eng.col[s]] and not np.isnan(eng.panel.adj[i, eng.col[s]])]
    above = []
    for j in cols:
        x = pd.Series(eng.panel.adj[:, j]).dropna()
        e = P.ema(x.to_numpy(), 9)
        pos = x.index.get_loc(i)
        above.append(float(x.iloc[pos] > e[pos]))
    assert abs(g.p9[i] - 100 * sum(above) / len(above)) < 1e-9


def _states(p9, p20, p50, **kw):
    n = len(p9)
    st = SE.group_states(np.array(p9, float), np.array(p20, float), np.array(p50, float), np.full(n, np.nan),
                         SE.SectorParams(**kw))
    return [SE.STATE_CODES[int(x)] for x in st[0]], st[5]


def test_fading_lasts_20_sessions():
    # 5 sessions Confirmed, then breadth breaks and stays weak for 70 sessions
    p9 = [80] * 5 + [40] * 70
    p20 = [80] * 5 + [40] * 70
    p50 = [80] * 5 + [35] * 70
    st, ev_fade = _states(p9, p20, p50)
    assert st[:5] == ["confirmed"] * 5
    assert st[5:25] == ["fading"] * 20                                # the printed rule: Fading lasts 20 sessions
    assert st[25:] == ["washout"] * 50                                # then the state falls back to Washout
    assert int(ev_fade.sum()) == 1
    old, _ = _states(p9, p20, p50, fade_once=False)                   # 2.4.0: re-set on every weak session
    assert old[25:79].count("fading") == 50                           # ... so it lasted 60 + 20 sessions


def test_a_new_thrust_ends_fading():
    # Confirmed, a breakdown and a washout, then a broad 9-day thrust 25 sessions later, inside the 60-session
    # memory of Confirmed and with the 50-day share still under 50%
    p9 = [80] * 5 + [10] * 25 + [90] * 25
    p20 = [80] * 5 + [10] * 25 + [60] * 25
    p50 = [80] * 5 + [20] * 25 + [45] * 25
    st, _ = _states(p9, p20, p50)
    assert st[5:25] == ["fading"] * 20 and st[25:30] == ["washout"] * 5
    assert st[30:50] == ["thrust_c"] * 20                             # "lasts 20 sessions or until a new thrust"
    old, _ = _states(p9, p20, p50, fade_once=False)
    assert old[30] == "thrust_c" and old[31] == "fading"              # the 2.4.0 bug: one session of thrust
    # a thrust that really fails still turns Fading, once
    p9b = [80] * 5 + [10] * 25 + [90] * 3 + [20] * 30
    p20b = [80] * 5 + [10] * 25 + [60] * 3 + [20] * 30
    p50b = [80] * 5 + [20] * 25 + [45] * 3 + [20] * 30
    st2, ev2 = _states(p9b, p20b, p50b)
    assert st2[30:33] == ["thrust_c"] * 3 and st2[33:53] == ["fading"] * 20 and st2[53] == "washout"
    assert int(ev2[30:].sum()) == 1


def test_single_industry_sector_group_and_counts(tmp_path):
    from finlit_technicals.industries import build_groups
    keys = [f"S{i}" for i in range(16)]
    cls = {k: ("Big Industry", "Sector A") for k in keys[:10]}
    cls.update({k: ("Small One", "Sector B") for k in keys[10:13]})                  # alone in its sector
    cls.update({k: ("Small Two", "Sector C") for k in keys[13:15]})
    cls[keys[15]] = ("Small Three", "Sector C")                                       # two small industries
    groups, meta = build_groups(keys, [True] * 16, cls)
    assert meta["Small One"]["kind"] == "industry" and "Sector B" not in groups       # named after the industry
    assert meta["Sector C"]["kind"] == "sector" and meta["Sector C"]["industries"] == ["Small Three", "Small Two"]
    # a counted stock without a price on the last day is left out of the group count and of the totals alike
    eng = SectorEngine(NseHistory(folder(tmp_path)))
    eng._build()
    j = next(c for c in eng.groups["Ferrous Metals"] if eng.member[-1, c])
    eng.panel.close[-1, j] = np.nan
    eng.panel.adj[-1, j] = np.nan
    b = strict(eng.board())
    row = next(r for r in b["rows"] if r["name"] == "Ferrous Metals")
    assert row["members_not_traded_today"] == 1 and row["stocks_counted"] == row["stocks_traded_today"] == 15
    u = b["universe"]
    assert u["meet_rules"] == u["counted_in_groups_with_reading"] + sum(x["stocks_counted"] for x in b["too_few_stocks"])
    assert b["market"]["average_label"] == "200-day exponential average"
    d = eng.industry("ferrous-metals")
    assert "exponential" in d["averages_note"] and "grouped" in d["history_note"]


def test_other_sources_use_the_same_rules():
    cal, px = F.paths(400)
    stocks = {s: pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}, index=cal)
              for s, c in px.items() if s in F.FERROUS}
    eng = SectorEngine(MemorySource(stocks))
    assert eng.rules.use_mcap is False
    b = strict(eng.board())
    assert [r["name"] for r in b["rows"]] == ["Ferrous Metals"] and b["rows"][0]["stocks_counted"] == len(F.FERROUS)
    assert b["market"] is None


# ─── downloader ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_fetch_parsers_and_housekeeping(tmp_path):
    import datetime as dt
    import gzip
    import zipfile
    old = ("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
           "20MICRONS,EQ,35.15,36.5,35.1,36.05,36,35.15,26584,951425.6,02-JAN-2017,410,INE144J01027,\n")
    ud = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,"
          "FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,"
          "TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n2024-10-28,2024-10-28,CM,NSE,"
          "STK,24715,INE09XN01023,AKUMS,EQ,,,,,AKUMS DRUGS,849.50,877.90,846.55,865.90,865.00,848.25,,865.25,,,71857,62166289.65,5811,F1,1,,,,,\n")
    full = ("SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, "
            "TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n20MICRONS, EQ, 28-Oct-2026, 188.69, 187.80, "
            "187.84, 156.76, 158.60, 161.04, 165.51, 1133822, 1876.57, 17308, 304588, 26.86\n").encode()

    def z(text):
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("x.csv", text)
        return bio.getvalue()
    r = FE.parse(z(old), "old", dt.date(2017, 1, 2))
    assert r[0][1:3] == ["20MICRONS", "EQ"] and r[0][7] == "36.05" and r[0][11] == "951425.6"
    r = FE.parse(z(ud), "udiff", dt.date(2024, 10, 28))
    assert r[0][1] == "AKUMS" and r[0][10] == "71857.0"
    r = FE.parse(full, "full", dt.date(2026, 10, 28))
    assert r[0][11] == repr(1876.57 * 1e5)
    try:
        FE.parse(full, "full", dt.date(2026, 10, 29))               # NSE's holiday copy of the day before
        raise AssertionError("stale file accepted")
    except FE.StaleFile:
        pass
    assert [k for k, _ in FE.urls_for(dt.date(2019, 3, 4))] == ["old"]
    assert [k for k, _ in FE.urls_for(dt.date(2024, 3, 4))] == ["old", "udiff", "full"]
    assert [k for k, _ in FE.urls_for(dt.date(2025, 3, 4))] == ["udiff", "full"]
    assert len(FE.urls_for(dt.date(2025, 3, 8))) == 1               # weekends: one try
    # housekeeping: repeated days set aside, yearly files rebuilt, the _stale folder ignored
    FE.HERE = tmp_path
    y = tmp_path / "bhav" / "2020"
    y.mkdir(parents=True)
    rows = [["2020-12-24", f"S{i}", "EQ", "", f"{1.0 + i}", "2", "0.5", "1.5", "1.5", "1.4", f"{100 + i}", "10", "1"] for i in range(30)]
    for name, rr in (("20201224", rows), ("20201225", rows), ("20201228", [r[:4] + ["9"] * 4 + r[8:] for r in rows])):
        with gzip.open(y / f"{name}.csv.gz", "wt", newline="") as g:
            import csv
            w = csv.writer(g)
            w.writerow(FE.COLS)
            w.writerows(rr)
    FE.LOG = open(tmp_path / "log.txt", "a")
    FE.drop_stale_days()
    FE.join_years()
    assert sorted(p.name for p in y.iterdir()) == ["20201224.csv.gz", "20201228.csv.gz"]
    assert (tmp_path / "bhav" / "_stale" / "20201225.csv.gz").exists() and not (tmp_path / "bhav__stale.csv.gz").exists()
    assert len(FE.day_files("bhav")) == 2 and (tmp_path / "bhav_2020.csv.gz").exists()
    assert isinstance(FE.amfi_candidates(), dict)
    try:
        FE.main([])
        raise AssertionError("ran without --dir")
    except SystemExit as e:
        assert e.code == 2


# ─── batch, command line, Flask ───────────────────────────────────────────────────────────────────────────────────
def test_batch_writes_nse_pages(tmp_path):
    d = folder(tmp_path)
    nse = NseHistory(d)
    syms = B.nse_symbols(SectorEngine(nse))
    assert "SAIL" in syms and F.DELISTED not in syms and F.TO_BE not in syms
    B.run(["SAIL", "VRAJ", F.LOW_VALUE], nse, tmp_path / "out")
    board = json.loads((tmp_path / "out" / "sectors" / "_board.json").read_text())
    assert board["rows"][0]["name"] == "Ferrous Metals"
    page = json.loads((tmp_path / "out" / "sectors" / "ferrous-metals.json").read_text())
    assert {s["symbol"] for s in page["stocks"]} >= {"SAIL", "VRAJ"}
    one = json.loads((tmp_path / "out" / "VRAJ.json").read_text())
    assert one["sector"]["group"]["name"] == "Ferrous Metals" and one["score"]["symbol"] == "VRAJ"
    low = json.loads((tmp_path / "out" / f"{F.LOW_VALUE}.json").read_text())
    assert low["sector"]["in_group"] is False
    summ = json.loads((tmp_path / "out" / "_summary.json").read_text())["stocks"]
    assert summ[0]["sector_state"] == page["state"]
    B.run(["SAIL"], nse, tmp_path / "out2", sectors=False)
    assert not (tmp_path / "out2" / "sectors").exists()


def _cli(args):
    from finlit_technicals.__main__ import main
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(args)
    return code, buf.getvalue()


def test_cli_sector_commands(tmp_path):
    d = str(folder(tmp_path))
    code, out = _cli(["sectors", "--nse", d])
    assert code == 0 and "SECTOR PULSE" in out and "Ferrous Metals" in out and "Too few counted stocks" in out
    code, out = _cli(["industry", "Ferrous Metals", "--nse", d, "--sessions", "50"])
    assert code == 0 and "FERROUS METALS" in out and "Not counted" in out
    code, out = _cli(["industry", "ferrous-metals", "--nse", d, "--json"])
    assert code == 0 and json.loads(out)["slug"] == "ferrous-metals"
    code, out = _cli(["stock-sector", F.RENAMED_FROM, "--nse", d])
    assert code == 0 and "VRAJ · NSE industry Ferrous Metals" in out
    code, out = _cli(["industry", "Nowhere", "--nse", d])
    assert code == 2
    code, out = _cli(["sectors"])
    assert code == 2 and "--nse" in out


def test_flask_sector_endpoints(tmp_path):
    try:
        import flask  # noqa: F401
    except ImportError:
        return
    sys.path.insert(0, str(ROOT / "examples"))
    import flask_app
    d = folder(tmp_path)
    c = flask_app.create_app(site_data=str(tmp_path / "none"), nse=str(d)).test_client()        # live
    r = c.get("/api/sectors")
    assert r.status_code == 200 and r.get_json()["rows"][0]["name"] == "Ferrous Metals"
    assert len(c.get("/api/sectors/ferrous-metals?sessions=30").get_json()["history"]["dates"]) == 30
    assert c.get("/api/technicals/VRAJ/sector").get_json()["group"]["name"] == "Ferrous Metals"
    assert c.get("/api/sectors/nowhere").status_code == 404
    assert c.get("/api/sectors/..%2F_summary").status_code == 404
    B.run(["SAIL"], NseHistory(d), tmp_path / "site")                                       # precomputed
    c2 = flask_app.create_app(site_data=str(tmp_path / "site"), nse=str(d)).test_client()
    assert c2.get("/api/sectors/ferrous-metals").get_json()["name"] == "Ferrous Metals"
    assert c2.get("/api/technicals/SAIL/sector").get_json()["symbol"] == "SAIL"
    assert not math.isnan(c2.get("/api/sectors").get_json()["rows"][0]["breadth"]["above_9"])
