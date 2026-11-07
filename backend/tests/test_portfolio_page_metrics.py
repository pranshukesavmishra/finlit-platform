"""The Equity portfolio page engine against the handover pack: its 7 tests, the two stored sample pages reproduced from the pack's CSVs, and the wording check."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from finlit.portfolio_page import inputs, metrics as pm

DATA = Path(__file__).parent / "fixtures" / "portfolio_page"


def synthetic(n_weeks=105, blocks=((4, 0.8), (3, 0.6), (5, 0.0)), seed=7):
    rng = np.random.default_rng(seed)
    market = rng.normal(0, 0.02, n_weeks)
    cols, meta, k = {}, {}, 0
    for b, (size, rho) in enumerate(blocks):
        f = rng.normal(0, 0.03, n_weeks)
        for _ in range(size):
            e = rng.normal(0, 0.03, n_weeks)
            r = 0.002 + np.sqrt(rho) * f + np.sqrt(1 - rho) * e
            cols[f"S{k:02d}"] = 100 * np.cumprod(1 + r)
            meta[f"S{k:02d}"] = {"name": f"Share {k}", "sector": f"Sector {b}", "size": "L", "mcap_cr": 1000 * (k + 1)}
            k += 1
    idx = pd.date_range("2024-11-01", periods=n_weeks, freq="W-FRI")
    nifty = pd.Series(10000 * np.cumprod(1 + market), index=idx)
    return pd.DataFrame(cols, index=idx), nifty, meta


def test_effective_stocks_limits():
    assert math.isclose(pm.effective_stocks(np.eye(10)), 10, rel_tol=1e-9)
    assert math.isclose(pm.effective_stocks(np.ones((10, 10))), 1, rel_tol=1e-6)
    C = np.full((5, 5), 0.3) + 0.7 * np.eye(5)
    assert math.isclose(pm.effective_stocks(C), 25 / (5 + 20 * 0.09), rel_tol=1e-9)


def test_score_formula_and_bands():
    s = pm.diversification_score(15, 8)
    assert (s["score"], s["band"]) == (100, "Widely spread")
    s = pm.diversification_score(1, 1)
    assert (s["score"], s["band"]) == (0, "Concentrated")
    s = pm.diversification_score(6.3, 4.8)
    assert s["comovement"] == 68 and s["sector_spread"] == 75 and s["score"] == 71


def test_page_on_synthetic_blocks():
    wc, nifty, meta = synthetic()
    p = pm.build_page(wc, nifty, meta)
    assert p["weeks"] == pm.WEEKS
    assert [g["letter"] for g in p["groups"]][:2] == ["A", "B"]
    assert set(p["groups"][0]["members"]) == {"S00", "S01", "S02", "S03"}
    n = len(meta)
    assert p["segments"]["same"]["pairs"] + p["segments"]["cross"]["pairs"] == n * (n - 1) // 2
    assert p["segments"]["same"]["avg"] > p["segments"]["cross"]["avg"]
    for mode in ("eq", "mc"):
        assert abs(sum(p["share_risk"][mode].values()) - 100) < 0.05
        assert len(p["summary"][mode]) <= 5
    assert p["order"][:4] == p["groups"][0]["members"]


def test_wording_limits_on_every_reading():
    wc, nifty, meta = synthetic()
    readings = pm.build_page(wc, nifty, meta)["readings"]
    for name in ("sample_12", "sample_40"):
        readings += json.loads((DATA / f"{name}.json").read_text())["page"]["readings"]
    assert readings
    for x in readings:
        assert not pm.BANNED_WORDS.search(x["text"]), x["text"]


def test_too_few_shares_and_short_history():
    wc, nifty, meta = synthetic(blocks=((2, 0.5),))
    p = pm.build_page(wc, nifty, meta)
    assert [x["rule"] for x in p["readings"]] == ["D3"]
    wc, nifty, meta = synthetic()
    wc.iloc[:70, 0] = np.nan
    p = pm.build_page(wc, nifty, meta)
    assert "S00" in p["short_history"] and "S00" not in p["order"]
    assert any(x["rule"] == "D1" for x in p["readings"])


def test_tied_largest_sector_names_both():
    wc, nifty, meta = synthetic(blocks=((3, 0.5), (3, 0.5), (2, 0.0)))
    texts = [x["text"] for x in pm.build_page(wc, nifty, meta)["readings"] if x["rule"] == "C1" and x["mode"] == "eq"]
    assert texts == ["Sector 0 and Sector 1 are the largest sectors at 37.5% each."]


SAMPLES = [("sample_12", 71, 6.3, 0.55, 0.18, 2), ("sample_40", 84, 8.5, 0.49, 0.23, 7)]


def test_sample_figures():
    for name, score, eff, same, cross, groups in SAMPLES:
        p = json.loads((DATA / f"{name}.json").read_text())["page"]
        assert p["score"]["score"] == score and p["score"]["effective_stocks"] == eff, name
        assert p["segments"]["same"]["avg"] == same and p["segments"]["cross"]["avg"] == cross, name
        assert len(p["groups"]) == groups, name


@pytest.mark.parametrize("name", ["sample_12", "sample_40"])
def test_build_page_reproduces_the_stored_sample(name):
    stored = json.loads((DATA / f"{name}.json").read_text())
    closes = pd.read_csv(DATA / f"{name}_weekly_close.csv", index_col="week_ending", parse_dates=True)
    nifty = closes.pop("NIFTY 50")
    page = pm.build_page(closes, nifty, stored["inputs"]["meta"])
    assert json.dumps(page, sort_keys=True) == json.dumps(stored["page"], sort_keys=True)


@pytest.mark.parametrize("name", ["sample_12", "sample_40"])
def test_site_inputs_give_the_same_page_as_the_csv(name):
    """The same closes arriving as the site stores them (dated bars, mid-week dates, daily NIFTY rows) land on the same Fridays and the same page."""
    stored = json.loads((DATA / f"{name}.json").read_text())
    closes = pd.read_csv(DATA / f"{name}_weekly_close.csv", index_col="week_ending", parse_dates=True)
    nifty = closes.pop("NIFTY 50")
    prices = {s: {"t": [(d - pd.Timedelta(days=2)).strftime("%Y-%m-%d") for d in closes.index], "c": closes[s].tolist()} for s in closes.columns}   # Wednesday bars
    rows = [{"d": d.strftime("%Y-%m-%d"), "c": float(c)} for d, c in nifty.items()]
    week = inputs.iso_key((closes.index[-1] + pd.Timedelta(days=3)).strftime("%Y-%m-%d"))     # the week after the last Friday is the unfinished one
    page = inputs.run(prices, rows, stored["inputs"]["meta"], week)
    extra = page.pop("first_k")                           # the one addition to the pack's object: long lists only
    assert (extra is None) == (page["layout"] == "short") and (extra is None or extra["k"] == 12 and extra["rest"] == 28)
    assert json.dumps(page, sort_keys=True) == json.dumps(stored["page"], sort_keys=True)
