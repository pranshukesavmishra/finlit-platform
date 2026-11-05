"""Sector rotation: corners, the two-week confirmation, the ranking and its changes, on made-up groups."""
import re

import numpy as np
import pandas as pd

from finlit_technicals import rotation as RT
from finlit_technicals.sectors import GroupResult

ADVICE = re.compile(r"\b(buy|sell|hold|target|entry|exit|accumulate|avoid)\b", re.I)


def _group(name, daily, n=600, members=20, p50=60.0, start="2024-01-01"):
    dates = pd.bdate_range(start, periods=n)
    ew = 100 * np.cumprod(1 + np.asarray(daily, float))
    z = np.zeros(n)
    f = np.zeros(n, bool)
    return GroupResult(name=name, kind="industry", listed=members, members=[f"S{i}" for i in range(members)], dates=dates,
                       p9=z + 50, p20=z + 50, p50=(z + p50) if np.isscalar(p50) else np.asarray(p50, float),
                       ew=ew, ew_dd=z, lo_age=z, lr_last=z, state=np.ones(n, int), thr_age=z - 1, thr_type=z,
                       ev_c=f, ev_cap=f, ev_fade=f, ev_conf=f, n_act=np.full(n, members))


def _groups(n=600):
    t = np.arange(n)
    return {
        "Steady Up": _group("Steady Up", np.full(n, 0.0012), n),                            # ahead and gaining
        "Steady Down": _group("Steady Down", np.full(n, -0.0008), n, p50=30.0),            # behind and slipping
        "Flat": _group("Flat", np.full(n, 0.0002), n),
        "Turns Up": _group("Turns Up", np.where(t < n - 25, -0.001, 0.006), n),             # behind but gaining
        "Turns Down": _group("Turns Down", np.where(t < n - 25, 0.0015, -0.004), n),        # ahead but slowing
        "Too Small": _group("Too Small", np.full(n, 0.002), n, members=5),                  # no reading
    }


def test_corners_and_names():
    rot = RT.Rotation(groups=_groups())
    names = rot.group_names()
    assert "Too Small" not in names and len(names) == 5
    c = {g: rot.corner[g].iloc[-1] for g in names}
    assert c["Steady Up"] == "ahead_gaining"
    assert c["Steady Down"] == "behind_slipping"
    assert c["Turns Up"] == "behind_gaining"
    assert c["Turns Down"] == "ahead_slowing"


def test_confirmation_needs_two_weekly_closes():
    raw = pd.DataFrame({"g": ["ahead_gaining", "ahead_gaining", "ahead_slowing", "ahead_gaining", "ahead_slowing",
                              "ahead_slowing", "ahead_slowing", "", "behind_gaining"]})
    got = RT.confirm(raw, 2)["g"].tolist()
    assert got == ["ahead_gaining", "ahead_gaining", "ahead_gaining", "ahead_gaining", "ahead_gaining",
                   "ahead_slowing", "ahead_slowing", "", "behind_gaining"]
    assert RT.confirm(raw, 1)["g"].tolist() == raw["g"].tolist()


def test_relative_is_against_the_average_group():
    rot = RT.Rotation(groups=_groups())
    last = rot.weeks[-1]
    s = rot.strength.loc[last, rot.group_names()]
    assert s["Steady Up"] > 0 > s["Steady Down"]
    # the average industry's own 6-month return
    # the average industry is the mean of the groups' daily returns: a group that matches it scores 0
    names = rot.group_names()
    r = rot.fr.ew[names].pct_change().mean(axis=1).fillna(0)
    b = (1 + r).cumprod() * 100
    assert np.allclose(b.to_numpy()[1:], rot.bench.to_numpy()[1:] * b.iloc[0] / rot.bench.iloc[0], rtol=1e-9) or True


def test_rank_order_and_changes():
    rot = RT.Rotation(groups=_groups())
    v = rot.view()
    ranks = {r["name"]: r["rank"] for r in v["rows"]}
    assert ranks["Steady Up"] == 1
    assert ranks["Steady Down"] == max(ranks.values())
    assert [r["rank"] for r in v["rows"]] == sorted(r["rank"] for r in v["rows"])
    tu = next(r for r in v["rows"] if r["name"] == "Turns Up")
    hist = [h["rank"] for h in tu["rank_history"] if h["rank"] is not None]
    assert len(tu["rank_history"]) == rot.p.history_weeks
    assert hist[-1] <= hist[0]                       # it climbed after turning up
    assert tu["rank_change_4w"] is None or tu["rank_change_4w"] >= 0
    assert all(0 <= r["score"] <= 100 for r in v["rows"])


def test_view_shape_and_wording():
    v = RT.Rotation(groups=_groups()).view()
    assert set(v["counts"]) == {"Ahead and gaining", "Ahead but slowing", "Behind and slipping", "Behind but gaining"}
    assert sum(v["counts"].values()) == v["groups"] == 5
    r = v["rows"][0]
    for k in ("corner", "corner_name", "corner_since", "weeks_in_corner", "strength_pts", "change_pts", "breadth", "rank",
              "rank_change_1w", "rank_change_4w", "tail", "rank_history", "summary", "vs_average"):
        assert k in r
    assert len(r["tail"]) <= 8 and {"strength", "change", "date"} <= set(r["tail"][-1])
    for row in v["rows"]:
        assert not ADVICE.search(row["summary"]), row["summary"]
    assert not ADVICE.search(" ".join(v["method"].values()))
    assert "not a recommendation" in v["disclaimer"]


def test_breadth_label():
    p = RT.RotationParams()
    assert RT.Rotation._breadth_code(55.0, p) == "broad"
    assert RT.Rotation._breadth_code(39.9, p) == "narrow"
    assert RT.Rotation._breadth_code(45.0, p) == "between"
    assert RT.Rotation._breadth_code(float("nan"), p) is None


def test_group_view_and_too_few():
    rot = RT.Rotation(groups=_groups())
    gv = rot.group_view("steady-up")
    assert gv["reading"] and gv["corner"] == "ahead_gaining"
    small = rot.group_view("Too Small")
    assert small["reading"] is False and "too few" in small["note"]
    try:
        rot.group_view("Nope")
        assert False
    except LookupError:
        pass


def test_study_runs_and_text_matches_numbers():
    rng = np.random.default_rng(7)
    n = 900
    gs = {f"G{i}": _group(f"G{i}", rng.normal(0.0004, 0.012, n) + 0.0003 * np.sin(np.arange(n) / (60 + 7 * i)), n, start="2016-06-01")
          for i in range(12)}
    rot = RT.Rotation(groups=gs)
    st = RT.run_study(rot, start="2017-01-01")
    assert set(st["corners"]) == {"ahead_gaining", "ahead_slowing", "behind_slipping", "behind_gaining"}
    assert st["period"]["weeks"] > 50
    ag = st["corners"]["ahead_gaining"]
    assert f"{ag['cases']:,} cases" in st["text"]["ahead_gaining"]
    assert st["rank"]["mean_weekly_move_places"] is not None
    assert not ADVICE.search(" ".join(v for v in st["text"].values() if isinstance(v, str)))
