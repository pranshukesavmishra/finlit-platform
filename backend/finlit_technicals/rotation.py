"""Sector rotation: which NSE industry groups are pulling ahead of the average industry, and how their ranks change.

Built on the sector engine's groups (the same counted stocks, the same equal-weighted group indices as Sector Pulse):

    eng = SectorEngine(NseHistory("/srv/finlit/nse"))
    rot = Rotation(eng)
    rot.view()                    # the rotation page: corners, ranking with rank changes, paths, rank history
    rot.group_view("banks")       # one group's rotation card (industry page, stock page)

Two numbers place each group, both measured against the average industry (every group with a reading, weighted
equally, so a few large companies cannot dominate):

    strength  6-month return minus the average industry's 6-month return, in points
    change    last month's return minus the average industry's, in points

    Ahead and gaining      strength above 0 and change above 0
    Ahead but slowing      strength above 0 and change 0 or below
    Behind and slipping    strength 0 or below and change 0 or below
    Behind but gaining     strength 0 or below and change above 0

A group moves to a new corner only after two weekly closes in it, so one week's wiggle does not count as a move.

The rotation rank orders the groups each week by a 0-100 score: the 3, 6 and 12-month returns against the average
industry (weights 0.3, 0.4, 0.3, each ranked across groups) make up three quarters, and the share of the group's
stocks above their 50-day average (ranked the same way) the last quarter. Rank changes are measured against the previous weekly close and four weeks back.

Everything here describes past prices. The study figures (data/rotation_study.json) are past averages from
2017-2026 and are shown next to each corner; they are not forecasts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from .sectors import STATE_CODES, STATE_NAMES, GroupResult, slug

CORNERS = ["ahead_gaining", "ahead_slowing", "behind_slipping", "behind_gaining", "middle"]
CORNER_NAMES = {
    "ahead_gaining": "Ahead and gaining",
    "ahead_slowing": "Ahead but slowing",
    "behind_slipping": "Behind and slipping",
    "behind_gaining": "Behind but gaining",
    "middle": "Near the average",
}
CORNER_MEANING = {
    "ahead_gaining": "Ahead of the average industry over 6 months, and still gaining ground last month",
    "ahead_slowing": "Ahead over 6 months, but behind the average last month",
    "behind_slipping": "Behind the average industry over 6 months, and still losing ground last month",
    "behind_gaining": "Behind over 6 months, but ahead of the average last month",
    "middle": "Close to the average industry over 6 months",
}
BREADTH_NAMES = {"broad": "Broad", "narrow": "Narrow", "between": "In between", None: None}
DISCLAIMER = ("Describes past prices of NSE industry groups against the average industry; not a recommendation to buy, "
              "sell or hold any security. Study results are past averages and do not predict future returns.")
METHOD = {
    "benchmark": ("The average industry: every NSE industry or sector group with a reading that day, each weighted "
                  "equally. Each group is itself the equal-weighted average of its counted stocks."),
    "strength": "6-month return of the group minus the average industry's, in points.",
    "change": "Last month's return of the group minus the average industry's, in points.",
    "corner": ("Strength above 0 is ahead, otherwise behind. Change above 0 is gaining, otherwise slowing (when ahead) "
               "or slipping (when behind). A group moves to a new corner only after two weekly closes in it."),
    "breadth": "Share of the group's counted stocks above their 50-day average: 50% or more is broad, under 40% narrow.",
    "rank": ("A 0-100 score: the 3, 6 and 12-month returns against the average industry, ranked across groups and "
             "weighted 0.3, 0.4 and 0.3, make up three quarters; the breadth reading, ranked the same way, makes up "
             "the last quarter. Rank 1 has the highest score. Changes compare with the previous weekly close."),
    "week": "Weekly readings use each week's last session. The current week uses its latest session until it closes.",
}


@dataclass
class RotationParams:
    strength_sessions: int = 126       # 6 months
    change_sessions: int = 21          # 1 month
    middle_pts: float = 0.0            # |strength| at or below this: near the average (0 = four corners only)
    confirm_weeks: int = 2             # weekly closes in a new corner before it counts
    min_mem: int = 8                   # counted stocks a group needs for a reading (as Sector Pulse)
    broad: float = 50.0
    narrow: float = 40.0
    rank_windows: tuple = ((63, 0.3), (126, 0.4), (252, 0.3))
    breadth_weight: float = 0.25
    move_places: int = 3               # rank moves of this many places or more are flagged
    tail_weeks: int = 8
    history_weeks: int = 26
    year_sessions: int = 252


@dataclass
class Frames:
    """Daily group data, dates x groups."""
    ew: pd.DataFrame          # equal-weighted group index
    ok: pd.DataFrame          # group has a reading that day (enough counted stocks)
    p50: pd.DataFrame         # share of counted stocks above their 50-day average
    state: pd.DataFrame       # Sector Pulse state code (int)
    kind: Dict[str, str] = field(default_factory=dict)


def frames_from(groups: Mapping[str, GroupResult], min_mem: int = 8) -> Frames:
    names = sorted(groups)
    if not names:
        raise ValueError("no groups")
    dates = groups[names[0]].dates
    ew = pd.DataFrame({g: groups[g].ew for g in names}, index=dates, dtype=float)
    n = pd.DataFrame({g: groups[g].n_act for g in names}, index=dates)
    ok = (n >= min_mem) & ew.notna() & (ew > 0)
    p50 = pd.DataFrame({g: groups[g].p50 for g in names}, index=dates, dtype=float).where(ok)
    st = pd.DataFrame({g: groups[g].state for g in names}, index=dates)
    return Frames(ew=ew.where(ok), ok=ok, p50=p50, state=st, kind={g: groups[g].kind for g in names})


def benchmark(fr: Frames) -> pd.Series:
    """The average industry as an index: each day, the mean of the daily returns of groups with a reading."""
    r = fr.ew.pct_change(fill_method=None).where(fr.ok & fr.ok.shift(1, fill_value=False))
    return (1 + r.mean(axis=1).fillna(0)).cumprod() * 100


def relative(fr: Frames, bench: pd.Series, n: int) -> pd.DataFrame:
    """Group return minus the average industry's return over the last n sessions, in points."""
    g = (fr.ew / fr.ew.shift(n) - 1) * 100
    b = (bench / bench.shift(n) - 1) * 100
    return g.sub(b, axis=0)


def week_ends(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The last session of each calendar week; the latest session closes the current week."""
    s = pd.Series(dates, index=dates)
    return pd.DatetimeIndex(s.groupby(dates.to_period("W")).max().values)


def raw_corners(strength: pd.DataFrame, change: pd.DataFrame, middle: float) -> pd.DataFrame:
    x, y = strength, change
    if middle > 0:
        c = np.select([(x > middle) & (y > 0), (x > middle) & (y <= 0), (x < -middle) & (y <= 0), (x < -middle) & (y > 0)],
                      CORNERS[:4], "middle")
    else:
        c = np.select([(x > 0) & (y > 0), (x > 0) & (y <= 0), (x <= 0) & (y <= 0)], CORNERS[:3], "behind_gaining")
    out = pd.DataFrame(c, index=x.index, columns=x.columns)
    return out.where(x.notna() & y.notna(), "")


def confirm(raw: pd.DataFrame, k: int = 2) -> pd.DataFrame:
    """A group takes a new corner only after k consecutive weekly readings in it."""
    if k <= 1:
        return raw.copy()
    out = {}
    for g in raw.columns:
        cur, cand, n, col = "", "", 0, []
        for v in raw[g].values:
            if v == "":
                cur, cand, n = "", "", 0
                col.append("")
                continue
            if cur == "":
                cur = v
            elif v == cur:
                cand, n = "", 0
            else:
                n = n + 1 if v == cand else 1
                cand = v
                if n >= k:
                    cur, cand, n = v, "", 0
            col.append(cur)
        out[g] = col
    return pd.DataFrame(out, index=raw.index)


def rank_score(rel: Dict[int, pd.DataFrame], p50: pd.DataFrame, p: RotationParams) -> pd.DataFrame:
    """0-100 score per row (date), from the ranks of the 1/3/6-month relative returns and the breadth reading."""
    trend = None
    wsum = 0.0
    for n, w in p.rank_windows:
        r = rel[n].rank(axis=1, pct=True)
        trend = r * w if trend is None else trend + r * w
        wsum += w
    trend = trend / wsum
    have = trend.notna()
    br = p50.where(have).rank(axis=1, pct=True)
    score = trend * (1 - p.breadth_weight) + br.fillna(0.5) * p.breadth_weight
    return (score * 100).where(have)


def ranks(score: pd.DataFrame) -> pd.DataFrame:
    return score.rank(axis=1, ascending=False, method="min")


def _r(x, nd=1):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _d(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d")


class Rotation:
    """Rotation readings for every group, computed once from a SectorEngine (or from GroupResults directly)."""

    def __init__(self, engine=None, params: RotationParams = RotationParams(),
                 groups: Optional[Mapping[str, GroupResult]] = None, study_file: Optional[str] = None):
        self.eng = engine
        self.p = params
        if groups is None:
            if engine is None:
                raise ValueError("give a SectorEngine or the groups")
            engine._build()
            groups = {g: engine.group(g) for g in engine.groups}
        self.fr = frames_from(groups, params.min_mem)
        self.meta = getattr(engine, "meta", {}) if engine is not None else {}
        self.study_file = study_file or str(Path(__file__).parent / "data" / "rotation_study.json")
        self._compute()

    # ------------------------------------------------------------------ computing
    def _compute(self):
        p, fr = self.p, self.fr
        self.bench = benchmark(fr)
        windows = sorted({p.strength_sessions, p.change_sessions, p.year_sessions, *[n for n, _ in p.rank_windows]})
        self.rel = {n: relative(fr, self.bench, n) for n in windows}
        self.weeks = week_ends(fr.ew.index)
        W = self.weeks
        self.strength = self.rel[p.strength_sessions].loc[W]
        self.change = self.rel[p.change_sessions].loc[W]
        self.raw = raw_corners(self.strength, self.change, p.middle_pts)
        self.corner = confirm(self.raw, p.confirm_weeks)
        self.score = rank_score({n: self.rel[n].loc[W] for n, _ in p.rank_windows}, fr.p50.loc[W], p)
        self.rank = ranks(self.score)

    def _since(self, g: str) -> tuple:
        col = self.corner[g].values
        cur = col[-1]
        i = len(col) - 1
        while i > 0 and col[i - 1] == cur:
            i -= 1
        prev = col[i - 1] if i > 0 and col[i - 1] else None
        return self.weeks[i], len(col) - i, prev

    @staticmethod
    def _breadth_code(v, p: RotationParams):
        if v is None or not np.isfinite(v):
            return None
        return "broad" if v >= p.broad else "narrow" if v < p.narrow else "between"

    def group_names(self) -> List[str]:
        """Groups with a reading on the latest session."""
        last = self.fr.ok.iloc[-1]
        return sorted(g for g in self.fr.ok.columns if bool(last[g]) and self.corner[g].iloc[-1] != "")

    def row(self, g: str) -> Dict[str, Any]:
        p, W = self.p, self.weeks
        t = W[-1]
        code = self.corner[g].iloc[-1]
        raw = self.raw[g].iloc[-1]
        since, weeks_in, prev = self._since(g)
        rk = self.rank[g]
        valid = rk.notna()
        r_now = rk.iloc[-1]
        r_1w = rk.iloc[-2] if len(rk) > 1 else np.nan
        r_4w = rk.iloc[-5] if len(rk) > 4 else np.nan
        hist = rk.iloc[-p.history_weeks:]
        b50 = self.fr.p50[g].iloc[-1]
        bcode = self._breadth_code(b50, p)
        st = int(self.fr.state[g].iloc[-1])
        tail = []
        for d in W[-p.tail_weeks:]:
            x, y = self.strength.at[d, g], self.change.at[d, g]
            if np.isfinite(x) and np.isfinite(y):
                tail.append({"date": _d(d), "strength": _r(x), "change": _r(y), "corner": self.raw.at[d, g]})
        meta = self.meta.get(g, {})
        out = {
            "name": g, "slug": slug(g), "kind": meta.get("kind", self.fr.kind.get(g)), "sector": meta.get("sector"),
            "industries": meta.get("industries", [g]),
            "corner": code, "corner_name": CORNER_NAMES.get(code), "corner_since": _d(since), "weeks_in_corner": int(weeks_in),
            "previous_corner": prev, "previous_corner_name": CORNER_NAMES.get(prev),
            "this_week_reading": raw if raw != code else None,
            "this_week_reading_name": CORNER_NAMES.get(raw) if raw != code else None,
            "strength_pts": _r(self.strength[g].iloc[-1]), "change_pts": _r(self.change[g].iloc[-1]),
            "vs_average": {f"{n}d": _r(self.rel[n][g].loc[t]) for n in sorted(self.rel)},
            "breadth_above_50": _r(b50), "breadth": bcode, "breadth_name": BREADTH_NAMES[bcode],
            "sector_state": STATE_NAMES.get(st), "sector_state_code": STATE_CODES.get(st),
            "rank": int(r_now) if np.isfinite(r_now) else None,
            "ranked": int(valid.iloc[-1] and self.rank.iloc[-1].notna().sum()),
            "score": _r(self.score[g].iloc[-1], 0),
            "rank_change_1w": int(r_1w - r_now) if np.isfinite(r_1w) and np.isfinite(r_now) else None,
            "rank_change_4w": int(r_4w - r_now) if np.isfinite(r_4w) and np.isfinite(r_now) else None,
            "rank_best_26w": int(hist.min()) if hist.notna().any() else None,
            "rank_worst_26w": int(hist.max()) if hist.notna().any() else None,
            "tail": tail,
            "rank_history": [{"date": _d(d), "rank": int(v) if np.isfinite(v) else None, "corner": self.corner.at[d, g] or None}
                             for d, v in hist.items()],
        }
        out["summary"] = self.summary(out)
        return out

    def summary(self, r: Dict[str, Any]) -> str:
        """One plain-English paragraph (descriptive only)."""
        nm, s, c = r["name"], r["strength_pts"], r["change_pts"]
        if s is None or c is None:
            return f"{nm} has too little history for a rotation reading."
        ahead = "ahead of" if s >= 0 else "behind"
        last = "ahead of" if c > 0 else "behind"
        txt = (f"Over 6 months {nm} is {abs(s):.1f} points {ahead} the average industry, and last month it was "
               f"{abs(c):.1f} points {last} it. ")
        if r["weeks_in_corner"] == 1 and r["previous_corner"]:
            txt += f"It moved from {r['previous_corner_name']} to {r['corner_name']} this week."
        elif r["weeks_in_corner"] == 1:
            txt += f"It is {r['corner_name']}."
        else:
            txt += f"It has been {r['corner_name']} for {r['weeks_in_corner']} weeks (since {pd.Timestamp(r['corner_since']):%d %b})."
        if r["this_week_reading"]:
            txt += f" This week's reading is {r['this_week_reading_name']}; one more weekly close there would move it."
        if r["rank"] is not None:
            ch = r["rank_change_1w"]
            mv = "" if not ch else f", {'up' if ch > 0 else 'down'} {abs(ch)} place{'s' if abs(ch) != 1 else ''} on the week"
            txt += f" Its rotation rank is {r['rank']} of {r['ranked']}{mv}."
        if r["breadth"] == "narrow" and r["corner"] == "ahead_gaining":
            txt += f" Only {r['breadth_above_50']:.0f}% of its stocks are above their 50-day average, so the lead is narrow."
        elif r["breadth"] == "broad" and r["corner"] == "ahead_gaining":
            txt += f" {r['breadth_above_50']:.0f}% of its stocks are above their 50-day average, so the lead is broad."
        return txt

    # ------------------------------------------------------------------ views
    def study(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(Path(self.study_file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def view(self) -> Dict[str, Any]:
        """The rotation page."""
        p = self.p
        names = self.group_names()
        rows = [self.row(g) for g in names]
        sector_rows = {}
        if self.eng is not None:
            try:
                for r in self.eng.board()["rows"]:
                    sector_rows[r["name"]] = r
            except Exception:  # noqa: BLE001 - the board is extra context
                sector_rows = {}
        for r in rows:
            b = sector_rows.get(r["name"])
            r["leader_flags"] = b["leader_flags"] if b else None
            r["stocks_counted"] = b["stocks_counted"] if b else int(self.fr.ok[r["name"]].iloc[-1])
        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["name"]))
        used = CORNERS if p.middle_pts > 0 else CORNERS[:4]
        counts = {CORNER_NAMES[c]: sum(1 for r in rows if r["corner"] == c) for c in used}
        moved = [r for r in rows if r["weeks_in_corner"] == 1 and r["previous_corner"]]
        climbers = sorted([r for r in rows if (r["rank_change_4w"] or 0) >= p.move_places], key=lambda r: -r["rank_change_4w"])[:5]
        fallers = sorted([r for r in rows if (r["rank_change_4w"] or 0) <= -p.move_places], key=lambda r: r["rank_change_4w"])[:5]
        market = self.eng.market() if self.eng is not None else None
        t = self.weeks[-1]
        return {
            "date": _d(t),
            "week_closed": bool(t.dayofweek >= 4),
            "groups": len(rows),
            "benchmark": METHOD["benchmark"],
            "average_industry": {"return_1m": _r((self.bench.iloc[-1] / self.bench.iloc[-1 - p.change_sessions] - 1) * 100),
                                 "return_6m": _r((self.bench.iloc[-1] / self.bench.iloc[-1 - p.strength_sessions] - 1) * 100)},
            "market": market,
            "counts": counts,
            "corner_meanings": {CORNER_NAMES[c]: CORNER_MEANING[c] for c in used},
            "rows": rows,
            "moved_this_week": [{"name": r["name"], "slug": r["slug"], "from": r["previous_corner_name"], "to": r["corner_name"]} for r in moved],
            "climbers_4w": [{"name": r["name"], "slug": r["slug"], "rank": r["rank"], "change": r["rank_change_4w"]} for r in climbers],
            "fallers_4w": [{"name": r["name"], "slug": r["slug"], "rank": r["rank"], "change": r["rank_change_4w"]} for r in fallers],
            "rank_weeks": [_d(d) for d in self.weeks[-p.history_weeks:]],
            "method": METHOD,
            "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(p).items()},
            "study": self.study(),
            "disclaimer": DISCLAIMER,
        }

    def group_view(self, name: str) -> Dict[str, Any]:
        """One group's rotation card. `name` is a group name or slug."""
        for g in self.fr.ew.columns:
            if name == g or slug(name) == slug(g):
                if g not in self.group_names():
                    return {"name": g, "slug": slug(g), "reading": False,
                            "note": f"Fewer than {self.p.min_mem} counted stocks, too few for a rotation reading."}
                r = self.row(g)
                r["reading"] = True
                st = self.study() or {}
                r["study"] = (st.get("corners") or {}).get(r["corner"])
                return r
        raise LookupError(f"{name}: no such group")


def rotation_view(engine, **kw) -> Dict[str, Any]:
    return Rotation(engine, **kw).view()


# ---------------------------------------------------------------------- the study
def _nw_t(s: pd.Series, lag: int) -> Optional[float]:
    v = s.dropna().to_numpy()
    n = len(v)
    if n < 20:
        return None
    e = v - v.mean()
    var = (e @ e) / n
    for L in range(1, lag + 1):
        var += 2 * (1 - L / (lag + 1)) * (e[L:] @ e[:-L]) / n
    return float(v.mean() / np.sqrt(var / n))


def _stats(x: pd.Series) -> Dict[str, Any]:
    x = x.dropna()
    return {"cases": int(x.size), "mean": _r(x.mean(), 2), "median": _r(x.median(), 2), "beat": _r((x > 0).mean() * 100)}


def run_study(rot: "Rotation", nifty_close: Optional[pd.Series] = None, start: str = "2017-01-01",
              sector_indices: Optional[pd.DataFrame] = None, broad_index: Optional[pd.Series] = None) -> Dict[str, Any]:
    """Past results by corner and by rank, with the same rules the site runs. Forward returns are each group's return
    minus the average industry's over the next 1, 3 and 6 months, measured from each weekly close. Averages are taken
    week by week (each week's groups first), and t-statistics allow for the overlapping windows."""
    fr, b, p = rot.fr, rot.bench, rot.p
    W = rot.weeks[(rot.weeks >= start) & (rot.weeks <= fr.ew.index[-1 - 126])]
    F = {h: relative(fr, b, h).shift(-h).loc[W] for h in (21, 63, 126)}
    C = rot.corner.loc[W]
    above = None
    if nifty_close is not None:
        n50 = nifty_close.reindex(fr.ew.index).ffill()
        above = (n50 > n50.ewm(span=200, adjust=False).mean()).loc[W].to_numpy()
    out: Dict[str, Any] = {"period": {"from": _d(W[0]), "to": _d(W[-1]), "weeks": int(len(W)),
                                      "groups_per_week_median": int(fr.ok.loc[W].sum(axis=1).median())}}
    corners = {}
    for c in CORNERS[:4] + (["middle"] if p.middle_pts > 0 else []):
        m = C == c
        s3 = _stats(F[63].where(m).stack())
        corners[c] = {"name": CORNER_NAMES[c], "cases": s3["cases"], "next_1m": _r(F[21].where(m).stack().mean(), 2),
                      "next_3m": s3["mean"], "median_3m": s3["median"], "beat_3m": s3["beat"],
                      "next_6m": _r(F[126].where(m).stack().mean(), 2)}
    sp = F[63].where(C == "ahead_gaining").mean(axis=1) - F[63].where(C == "behind_slipping").mean(axis=1)
    spread = {"points": _r(sp.mean(), 2), "t": _r(_nw_t(sp, 13), 1),
              "without_2020": _r(sp[sp.index.year != 2020].mean(), 2), "since_2022": _r(sp[sp.index >= "2022-01-01"].mean(), 2)}
    if above is not None:
        spread["above_200d"] = _r(sp[above].mean(), 2)
        spread["below_200d"] = _r(sp[~above].mean(), 2)
    out["corners"], out["spread_3m"] = corners, spread
    pb = fr.p50.loc[W]
    br = {}
    for c in ("ahead_gaining", "behind_gaining"):
        m = C == c
        br[c] = {"broad": _stats(F[63].where(m & (pb >= p.broad)).stack()),
                 "narrow": _stats(F[63].where(m & (pb < p.narrow)).stack())}
    out["breadth"] = br
    runs, moves = [], {}
    for g in C.columns:
        prev, n = None, 0
        for v in C[g].values:
            if v == "":
                if prev:
                    runs.append(n)
                prev, n = None, 0
                continue
            if v == prev:
                n += 1
            else:
                if prev:
                    runs.append(n)
                    moves[(prev, v)] = moves.get((prev, v), 0) + 1
                prev, n = v, 1
    tot: Dict[str, int] = {}
    for (a, _), k in moves.items():
        tot[a] = tot.get(a, 0) + k
    out["moves"] = {"median_weeks": float(np.median(runs)) if runs else None, "mean_weeks": _r(np.mean(runs)) if runs else None,
                    "next_corner": {a: {bb: round(k / tot[a] * 100) for (aa, bb), k in sorted(moves.items()) if aa == a} for a in tot}}
    S, Rk = rot.score.loc[W], rot.rank.loc[W]
    pct = S.rank(axis=1, pct=True)
    rk = {}
    for h, lab in ((21, "1m"), (63, "3m"), (126, "6m")):
        d = F[h].where(pct > 2 / 3).mean(axis=1) - F[h].where(pct <= 1 / 3).mean(axis=1)
        rk[lab] = _r(d.mean(), 2)
        if h == 63:
            rk["t_3m"] = _r(_nw_t(d, 13), 1)
            rk["weeks_positive_3m"] = _r((d > 0).mean() * 100)
            rk["by_year_3m"] = {str(y): _r(v, 1) for y, v in d.groupby(d.index.year).mean().items()}
            if above is not None:
                rk["above_200d"], rk["below_200d"] = _r(d[above].mean(), 2), _r(d[~above].mean(), 2)
    up = (rot.rank.shift(4) - rot.rank).loc[W]
    rk["climbed_5_in_4w_next_3m"] = _stats(F[63].where(up >= 5).stack())
    rk["fell_5_in_4w_next_3m"] = _stats(F[63].where(up <= -5).stack())
    rk["mean_weekly_move_places"] = _r(np.nanmean(Rk.diff().abs().to_numpy()), 1)
    out["rank"] = rk
    if sector_indices is not None and broad_index is not None:
        px = sector_indices.reindex(fr.ew.index).ffill()
        bi = broad_index.reindex(fr.ew.index).ffill()
        rel = lambda n: ((px / px.shift(n) - 1) * 100).sub((bi / bi.shift(n) - 1) * 100, axis=0)
        x, y = rel(p.strength_sessions).loc[rot.weeks], rel(p.change_sessions).loc[rot.weeks]
        cc = confirm(raw_corners(x, y, p.middle_pts), p.confirm_weeks).loc[W]
        f = rel(63).shift(-63).loc[W]
        d = f.where(cc == "ahead_gaining").mean(axis=1) - f.where(cc == "behind_slipping").mean(axis=1)
        out["sector_indices"] = {"indices": int(px.notna().all().sum()), "benchmark": "Nifty 500",
                                 "spread_3m": _r(d.mean(), 2), "t": _r(_nw_t(d, 13), 1),
                                 "by_year_3m": {str(yy): _r(v, 1) for yy, v in d.groupby(d.index.year).mean().items()}}
    out["text"] = study_text(out)
    return out


def _safe(d):
    if isinstance(d, dict):
        return {k: _safe(v) for k, v in d.items()}
    return _Missing() if d is None else d


class _Missing:
    def __format__(self, spec):
        return "n/a"


def study_text(s: Dict[str, Any]) -> Dict[str, Any]:
    """Plain-English sentences built from the study numbers, so the page text always matches them."""
    s = _safe(s)
    c, sp, br, mv, rk = s["corners"], s["spread_3m"], s["breadth"], s["moves"], s["rank"]
    nx = mv["next_corner"]
    f = lambda v: "n/a" if isinstance(v, _Missing) else f"{v:+.1f}"
    txt = {
        "ahead_gaining": (f"{c['ahead_gaining']['cases']:,} cases: over the next 3 months these groups did {f(c['ahead_gaining']['next_3m'])} "
                          f"points against the average industry, and {c['ahead_gaining']['beat_3m']:.0f}% beat it. With broad breadth "
                          f"{f(br['ahead_gaining']['broad']['mean'])}; with narrow breadth {f(br['ahead_gaining']['narrow']['mean'])}."),
        "ahead_slowing": (f"{c['ahead_slowing']['cases']:,} cases: {f(c['ahead_slowing']['next_3m'])} points over the next 3 months "
                          f"({c['ahead_slowing']['beat_3m']:.0f}% beat the average). {nx.get('ahead_slowing', {}).get('ahead_gaining', 0)}% of moves "
                          f"out of this corner went back to Ahead and gaining."),
        "behind_slipping": (f"{c['behind_slipping']['cases']:,} cases: {f(c['behind_slipping']['next_3m'])} points over the next 3 months; "
                            f"{c['behind_slipping']['beat_3m']:.0f}% beat the average industry."),
        "behind_gaining": (f"{c['behind_gaining']['cases']:,} cases: {f(c['behind_gaining']['next_3m'])} points over the next 3 months "
                           f"({c['behind_gaining']['beat_3m']:.0f}% beat the average). Only {nx.get('behind_gaining', {}).get('ahead_gaining', 0)}% "
                           f"of moves out of this corner led to Ahead and gaining; {nx.get('behind_gaining', {}).get('behind_slipping', 0)}% went back "
                           f"to Behind and slipping. It has usually been a bounce, not the start of a lead."),
        "spread": (f"Groups Ahead and gaining did {sp['points']:.1f} points better over the next 3 months than groups Behind and "
                   f"slipping, averaged week by week."
                   + (f" The gap was {sp['above_200d']:.1f} points when the Nifty 50 was above its 200-day exponential average and "
                      f"{sp['below_200d']:.1f} when it was below." if "above_200d" in sp else "")),
        "rank": (f"The top third by rotation rank did {rk['3m']:.1f} points better over the next 3 months than the bottom third, "
                 f"in {rk['weeks_positive_3m']:.0f}% of weeks. Groups that climbed 5 or more places in 4 weeks did "
                 f"{f(rk['climbed_5_in_4w_next_3m']['mean'])} points over the next 3 months; groups that fell 5 or more did "
                 f"{f(rk['fell_5_in_4w_next_3m']['mean'])}."),
        "stay": f"A group stayed a median of {mv['median_weeks']:.0f} weeks in a corner (mean {mv['mean_weeks']:.1f}).",
        "limits": [
            "Groups often move together in the same weeks, so the cases are not independent; averages are taken week by week.",
            "The rules (6 months, 1 month, two weekly closes, the rank weights) were chosen after testing a few versions on this "
            "same data, so expect live results to be weaker.",
            "Each company's NSE industry is today's label, even for earlier years.",
            "Returns ignore costs and taxes; the groups are equal-weighted, so they lean towards mid and small companies.",
        ],
    }
    si = s.get("sector_indices")
    if isinstance(si, dict):
        txt["sector_indices"] = (f"The same rules on {si['indices']} of NSE's own sector indices, which are weighted by company size, "
                                 f"against the Nifty 500: {si['spread_3m']:+.1f} points over 3 months, with no reliable pattern year "
                                 f"to year. The pattern lives in how the typical stock of an industry moves.")
        txt["limits"].insert(1, txt["sector_indices"])
    return txt


# ---------------------------------------------------------------------- files and command line
def write_files(rot: "Rotation", out_dir) -> Dict[str, Any]:
    """site_data/rotation/_map.json (the page) and <slug>.json (one card per group). Returns the map."""
    from .api import jsonable
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    v = rot.view()
    (out / "_map.json").write_text(json.dumps(jsonable(v), ensure_ascii=False), encoding="utf-8")
    for r in v["rows"]:
        (out / f"{r['slug']}.json").write_text(json.dumps(jsonable(rot.group_view(r["slug"])), ensure_ascii=False),
                                               encoding="utf-8")
    return v


def brief(row: Dict[str, Any]) -> Dict[str, Any]:
    """The few rotation fields other pages show (Sector Pulse rows, the stock page, the screener)."""
    keys = ("corner", "corner_name", "weeks_in_corner", "this_week_reading_name", "rank", "ranked", "rank_change_1w",
            "rank_change_4w", "strength_pts", "change_pts", "breadth", "breadth_name")
    return {k: row.get(k) for k in keys}


def map_text(v: Dict[str, Any]) -> str:
    L = [f"Sector rotation · {v['date']} · {v['groups']} groups against the average industry "
         f"(6 months {v['average_industry']['return_6m']:+.1f}%, 1 month {v['average_industry']['return_1m']:+.1f}%)",
         "  " + " · ".join(f"{k} {n}" for k, n in v["counts"].items()), "",
         f"  {'#':>3} {'1w':>4} {'4w':>4} {'Group':<36} {'Corner':<21} {'Wks':>3} {'6M pts':>7} {'1M pts':>7} {'Breadth':>8}"]
    mv = lambda x: "" if not x else f"{x:+d}"
    for r in v["rows"]:
        L.append(f"  {r['rank'] or '-':>3} {mv(r['rank_change_1w']):>4} {mv(r['rank_change_4w']):>4} {r['name'][:36]:<36} "
                 f"{r['corner_name']:<21} {r['weeks_in_corner']:>3} {r['strength_pts']:>+7.1f} {r['change_pts']:>+7.1f} "
                 f"{(r['breadth_above_50'] if r['breadth_above_50'] is not None else float('nan')):>7.0f}%"
                 + (f"  (this week: {r['this_week_reading_name']})" if r["this_week_reading_name"] else ""))
    L += ["", v["disclaimer"]]
    return "\n".join(L)


def cli(argv: List[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="finlit_technicals rotation", description="Sector rotation by NSE industry group")
    ap.add_argument("command", choices=["rotation", "rotation-batch", "rotation-study"])
    ap.add_argument("group", nargs="?", help="rotation: one group's card (name or slug); default: the whole map")
    ap.add_argument("--nse", required=True, help="NSE folder kept by fetch-nse")
    ap.add_argument("--out", help="rotation-batch: output folder (for example site_data/rotation)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from .nse import NseHistory
    from .sectors import SectorEngine
    from .api import jsonable
    src = NseHistory(a.nse)
    eng = SectorEngine(src)
    rot = Rotation(eng)
    if a.command == "rotation-batch":
        if not a.out:
            print("rotation-batch needs --out")
            return 2
        v = write_files(rot, a.out)
        print(f"{v['groups']} groups written to {a.out} ({v['date']})")
        return 0
    if a.command == "rotation-study":
        n50 = src.index("NSE:NIFTY")
        st = run_study(rot, None if n50 is None else pd.to_numeric(n50["close"], errors="coerce"))
        Path(rot.study_file).write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"study written to {rot.study_file}: {st['period']['from']} to {st['period']['to']}, {st['period']['weeks']} weeks")
        return 0
    try:
        d = rot.group_view(a.group) if a.group else rot.view()
    except LookupError as e:
        print(str(e))
        return 2
    if a.json or a.group:
        print(json.dumps(jsonable(d), indent=1, ensure_ascii=False))
    else:
        print(map_text(d))
    return 0
