"""Section 8 company mode (advanced/tech.py): no look-ahead, non-overlapping windows, beta = slope on a synthetic exact case,
split/jump exclusion, volume windows by hand."""

import math
from datetime import date, timedelta

import pytest

from finlit.advanced import tech


def series(n, start=date(2022, 1, 3), f=lambda k: 100 + 10 * math.sin(k / 9.0) + 0.05 * k, vol=lambda k: 1000 + k):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return {"daily": {"t": [x.isoformat() for x in days], "c": [f(k) for k in range(n)], "v": [vol(k) for k in range(n)]}}


@pytest.mark.parametrize("kind", ["rsi", "macd", "p52h"])
def test_no_look_ahead(kind):
    closes = series(600)["daily"]["c"]
    full = tech.indicator(closes, kind)
    for k in (260, 300, 451, 599):
        assert tech.indicator(closes[:k + 1], kind)[k] == full[k]          # appending future closes changes nothing at k


@pytest.mark.parametrize("h", [5, 20, 60])
def test_non_overlapping_grid_and_forward_return(h):
    p = series(500)
    out = tech.run(p, [], "rsi", h)
    days = p["daily"]["t"]
    idx = [days.index(pt["d"]) for pt in out["points"]]
    assert all(b - a == h for a, b in zip(idx, idx[1:])) and idx[-1] == len(days) - 1 - h
    c = p["daily"]["c"]
    for k, pt in zip(idx, out["points"]):
        assert pt["y"] == pytest.approx((c[k + h] / c[k] - 1) * 100, rel=1e-12)
    assert out["n"] == len(out["points"]) and out["pair"] == "8.5"


def test_jump_windows_left_out():
    p = series(400)
    c = p["daily"]["c"]
    for k in range(300, 400):
        c[k] = c[k] / 2      # an unadjusted 1:1 bonus at day 300
    out = tech.run(p, [], "rsi", 20)
    days = p["daily"]["t"]
    for pt in out["points"]:
        k = days.index(pt["d"])
        assert not (k - tech.LOOKBACK["rsi"] < 300 <= k + 20)
    assert any(e["code"] == "jump" and e["count"] >= 1 for e in out["excluded"])
    act = [{"date": p["daily"]["t"][250], "type": "split"}]      # an action alone also excludes its windows
    out2 = tech.run(series(400), act, "p52h", 5)
    assert all(not (days.index(pt["d"]) - 251 < 250 <= days.index(pt["d"]) + 5) for pt in out2["points"])


def test_beta_is_the_slope():
    n, start = 900, date(2021, 1, 4)
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    m, s, mc, sc = 100.0, 50.0, [], []
    for k, day in enumerate(days):
        if day.weekday() == 4:                       # all of a week's move happens on Friday
            r = 0.02 * math.sin(k / 5.0)
            m *= 1 + r
            s *= 1 + 1.5 * r
        mc.append(m)
        sc.append(s)
    price = {"daily": {"t": [x.isoformat() for x in days], "c": sc, "v": [1] * n}}
    out = tech.run(price, [], "beta", 5, list(zip(days, mc)))
    assert out["n"] == tech.BETA_WEEKS and out["beta"] == pytest.approx(1.5, rel=1e-6)
    assert out["stats"]["pearson"]["r"] == pytest.approx(1.0)
    short = tech.run({"daily": {"t": price["daily"]["t"][:300], "c": sc[:300], "v": [1] * 300}}, [], "beta", 5, list(zip(days, mc)))
    assert short["beta"] is None and short["n"] < tech.BETA_MIN


def test_volume_growth_by_hand():
    p = series(60, f=lambda k: 100 + k, vol=lambda k: 100 if k < 20 else 200 if k < 40 else 300)
    out = tech.run(p, [], "volg", 20)
    last = out["points"][-1]
    assert last["x"] == pytest.approx((300 * 20 / (200 * 20) - 1) * 100) and last["y"] == pytest.approx(abs((159 / 139) - 1) * 100)
    assert len(out["points"]) == 1      # sessions 0-19 have no earlier window to compare with


def test_bad_inputs():
    with pytest.raises(ValueError):
        tech.run(series(100), [], "rsi", 7)
    with pytest.raises(ValueError):
        tech.run(series(100), [], "nope", 5)
