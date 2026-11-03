"""Runs a registry record against the screener Table (finlit/screener/data.py) and the stored Prism ratings. Pure: no database, no Redis, no clock.

Every rule of a screen becomes one `Rule` (a plain-words label and a yes/no per company), whatever it came from: a Prism parameter, a line of the Query
builder's own language (parsed and evaluated by finlit/screener/ql.py and qeval.py, so a missing figure fails exactly as it does there), a `derived` rule
(expr.py) or the theme-tag list. A company is listed when every rule holds. With nothing listed, the five companies that fail the fewest rules are returned
with the rules they missed (spec p16, "Empty result").
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..screener.ql import analyze, canonical
from ..screener.qeval import Evaluator
from . import derive, expr, themes
from .registry import DISCLAIMER, REGISTRY_VERSION, Preset, render_card
from .seed import THEME

EXPORT_MAX = 500
MISS_COUNT = 5
LEADERS = 5
LEADER_FLOOR = 1000.0
SCORED = ("RATED", "PROVISIONAL")
CONFIRMED = 20.0            # "Prism-confirmed": both technical views at +20 or more (spec p6)
NO_CHIPS = "none"           # ?chip=none is the explicit empty set


class Blocked(Exception):
    def __init__(self, preset: Preset):
        super().__init__(preset.blocked_reason or "blocked")
        self.preset = preset


class UnknownChip(ValueError):
    pass


# ------------------------------------------------------------------------------------------------------------------------------ the frame
class Frame:
    """One night's view of the market: the Table, the Prism ratings, the nightly scores, the theme tags and the theme states."""

    def __init__(self, table, prism: Dict[str, dict], as_of: date, tags: Optional[Dict[str, List[str]]] = None, industry: Optional[Dict[str, Optional[str]]] = None,
                 theme_eval: Optional[themes.ThemeEval] = None, momentum: Optional[Dict[str, float]] = None, growth: Optional[Dict[str, float]] = None,
                 caps: Optional[Dict[str, Tuple[float, float]]] = None):
        self.t, self.as_of = table, as_of
        self.symbols = table.symbols
        self.pz: List[dict] = [prism.get(s) or {} for s in self.symbols]
        self.tags = tags or {}
        self.industry = industry or {}
        self.theme_eval = theme_eval
        self.momentum = momentum if momentum is not None else derive.momentum_scores(table)
        self.growth = growth if growth is not None else derive.growth_scores(table)
        self.caps = caps if caps is not None else derive.outlier_caps(table)
        self.latest_q = table.latest_quarter()
        self.rank_scores: Dict[int, float] = {}      # set by run() for a screen that has a rank score
        self._r3: Dict[str, float] = {}
        if theme_eval is not None:
            for ind, v in theme_eval.industries.items():
                if v["r3"] is not None:
                    self._r3[ind] = v["r3"]

    # ---- fields
    def industry_of(self, i: int) -> Optional[str]:
        return self.industry.get(self.symbols[i])

    def has_prism(self, i: int) -> bool:
        z = self.pz[i]
        return z.get("prism_final") is not None and z.get("prism_status") in SCORED

    def get(self, i: int, name: str) -> Any:
        """A company's value for a field name: a Table column, a Prism field, a nightly score, or one of the screen helpers. None when unknown."""
        t = self.t
        if name in t.cols:
            v = t.cols[name][i]
            return v if v == v else None
        if name.startswith("cap:"):
            v = self.get(i, name[4:])
            lo_hi = self.caps.get(name[4:])
            return v if v is None or lo_hi is None else min(max(v, lo_hi[0]), lo_hi[1])
        z = self.pz[i]
        if name in z:
            return z[name]
        if name == "prism_score":
            return z.get("prism_final")
        sym = self.symbols[i]
        if name == "symbol":
            return sym
        if name == "name":
            return t.name[i]
        if name == "sector":
            return t.sector[i]
        if name == "industry":
            return self.industry_of(i)
        if name == "cap_bucket":
            return t.cap[i]
        if name == "has_prism":
            return 1.0 if self.has_prism(i) else 0.0
        if name == "rank_score":
            return self.rank_scores.get(i)
        if name == "w52_score":                                     # 100 minus the % below the 52-week high (the redesign's price-strength input)
            v = self.get(i, "pct_from_high")
            return None if v is None else max(0.0, 100.0 - v)
        if name == "profit_plus_balance":                           # the Basic tab's "Profitability + Balance sheet" (both pillars needed)
            a, b = self.get(i, "pillar_profitability"), self.get(i, "pillar_balance")
            return None if a is None or b is None else a + b
        if name == "high_over_low":                                 # how far the 52-week high stands above the 52-week low, in %
            hi, lo = self.get(i, "high_52w"), self.get(i, "low_52w")
            return None if hi is None or lo is None or lo <= 0 else round((hi / lo - 1.0) * 100.0, 4)
        if name == "is_large_mid":
            return None if t.cap[i] is None else (1.0 if t.cap[i] in ("Large", "Mid") else 0.0)
        if name == "momentum_score":
            return self.momentum.get(sym)
        if name == "growth_score":
            return self.growth.get(sym)
        if name == "inst_chg_1q":
            a, b = self.get(i, "own_fii_chg_1q"), self.get(i, "own_dii_chg_1q")
            return None if a is None or b is None else round(a + b, 4)
        if name == "recent_results":
            q = t.q_end[i]
            return 1.0 if (self.latest_q is not None and q == q and int(q) == self.latest_q) else 0.0
        if name == "sub_theme":
            subs = self.tags.get(sym)
            return ", ".join(subs) if subs else None
        if name == "vs_industry_3m":
            r3, base = self.get(i, "ret_3m"), self._r3.get(self.industry_of(i) or "")
            return None if r3 is None or base is None else round(r3 - base, 4)
        return None


# ------------------------------------------------------------------------------------------------------------------------------ chips
def resolve_chips(preset: Preset, requested: Optional[Sequence[str]]) -> List[str]:
    """The active chip ids, in registry order. No parameter at all = the chips that are on by default; `none` = no chips; an unknown id raises UnknownChip."""
    known = {c.id for c in preset.chips}
    if requested is None or len(requested) == 0:
        return [c.id for c in preset.chips if c.default]
    asked = [r for r in requested if r != NO_CHIPS]
    bad = [r for r in asked if r not in known]
    if bad:
        raise UnknownChip(f"unknown chip: {bad[0]}")
    return [c.id for c in preset.chips if c.id in set(asked)]


def chip_key(active: Sequence[str]) -> str:
    return ",".join(sorted(active)) or NO_CHIPS


class Config:
    """The record with the active chips applied."""

    def __init__(self, preset: Preset, active: Sequence[str]):
        self.preset = preset
        self.prism: Dict[str, Any] = dict(preset.prism_filters)
        self.ql: List[str] = [ln.strip() for ln in preset.ql.splitlines() if ln.strip()]
        self.derived: List[Tuple[str, str]] = list(preset.derived)
        self.rank: Tuple[Tuple[str, str], ...] = preset.rank
        self.subs: List[str] = []
        self.small_groups = False
        self.how: List[str] = list(preset.how_it_works)
        for c in [c for c in preset.chips if c.id in set(active)]:
            e = c.effect
            for k, v in (e.get("prism_set") or {}).items():
                if v is None:
                    self.prism.pop(k, None)
                else:
                    self.prism[k] = v
            self.ql = [e.get("ql_replace", {}).get(ln, ln) for ln in self.ql] + list(e.get("ql_add", ()))
            self.derived = [e.get("derived_replace", {}).get(rule, (rule, label)) if rule in e.get("derived_replace", {}) else (rule, label) for rule, label in self.derived]
            if e.get("derived_drop"):
                self.derived = [(r, lab) for r, lab in self.derived if r not in set(e["derived_drop"])]
            if e.get("ql_drop"):
                self.ql = [ln for ln in self.ql if ln not in set(e["ql_drop"])]
            self.derived += list(e.get("derived_add", ()))
            if e.get("rank"):
                self.rank = tuple(e["rank"])
            if e.get("sub"):
                self.subs.append(e["sub"])
            self.small_groups = self.small_groups or bool(e.get("small_groups"))
            self.how += list(c.how)


# ------------------------------------------------------------------------------------------------------------------------------ rules
class Rule:
    def __init__(self, label: str, ok: List[bool]):
        self.label, self.ok = label, ok


def _n(v: Any) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


PRISM_PARAMS = {  # filter -> (field, plain words)
    "zmin": ("prism_final", "Prism score {n} or more"), "zfmin": ("prism_fundamental", "Prism Growth & Profitability {n} or more"), "zvmin": ("prism_valuation", "Prism Valuation {n} or more"),
    "zqmin": ("prism_quality", "Prism Quality {n} or more"), "zrmin": ("prism_risk", "Prism Risk {n} or more"),
    "st": ("prism_st_score", "Short-term technical view {n} or more"), "lt": ("prism_lt_score", "Long-term technical view {n} or more"),
}


def prism_rules(fr: Frame, pf: Dict[str, Any]) -> List[Rule]:
    n, out = fr.t.n, []
    if pf.get("rated"):
        out.append(Rule("Rated by Prism", [fr.has_prism(i) for i in range(n)]))
    if pf.get("status"):
        want = pf["status"]
        out.append(Rule(f"Prism rating status is {want.title()}", [fr.pz[i].get("prism_status") == want and fr.pz[i].get("prism_final") is not None for i in range(n)]))
    if pf.get("cap"):
        out.append(Rule(f"{pf['cap']} cap (market-cap rank {'1 to 100' if pf['cap'] == 'Large' else '101 to 250' if pf['cap'] == 'Mid' else '251 onward'})", [fr.t.cap[i] == pf["cap"] for i in range(n)]))
    for key, (field, words) in PRISM_PARAMS.items():
        if key in pf:
            lim = float(pf[key])
            out.append(Rule(words.format(n=_n(pf[key])), [(fr.pz[i].get(field) is not None and fr.pz[i].get("prism_status") in SCORED and fr.pz[i][field] >= lim) for i in range(n)]))
    return out


def ql_rule(fr: Frame, line: str) -> Rule:
    a = analyze(line, "gold")
    if not a.ok:
        raise ValueError(f"preset rule does not parse: {line!r}: {[p.message for p in a.problems if p.severity == 'error']}")
    states = Evaluator(fr.t).state(a.root)
    return Rule(canonical(a.root), [s == 1 for s in states])


def derived_rule(fr: Frame, rule: str, label: str) -> Rule:
    node = expr.parse(rule)
    names = sorted(set(expr.fields_in(node)))
    n = fr.t.n
    ok = []
    for i in range(n):
        vals = {k: fr.get(i, k) for k in names}
        ok.append(expr._state(node, vals.get) is True)
    return Rule(label, ok)


def tag_rule(fr: Frame, subs: Sequence[str]) -> Rule:
    want = set(subs)
    ok = []
    for s in fr.symbols:
        have = fr.tags.get(s)
        ok.append(bool(have) and (not want or bool(want & set(have))))
    return Rule("Tagged " + THEME + (": " + " or ".join(subs) if subs else ""), ok)


def build_rules(fr: Frame, cfg: Config) -> List[Rule]:
    rules: List[Rule] = []
    if cfg.preset.kind == "tags":
        rules.append(tag_rule(fr, cfg.subs))
    rules += prism_rules(fr, cfg.prism)
    rules += [ql_rule(fr, ln) for ln in cfg.ql]
    rules += [derived_rule(fr, r, lab) for r, lab in cfg.derived]
    return rules


# ------------------------------------------------------------------------------------------------------------------------------ ranking and rows
def sort_key(fr: Frame, rank: Sequence[Tuple[str, str]]) -> Callable[[int], tuple]:
    def key(i: int) -> tuple:
        parts: List[Any] = []
        for field, direction in rank:
            v = fr.get(i, field)
            parts.append((v is None, 0.0 if v is None else (-v if direction == "desc" else v)))
        mc = fr.get(i, "market_cap")
        parts.append((mc is None, 0.0 if mc is None else -mc))
        parts.append((False, fr.symbols[i]))
        return tuple(parts)
    return key


def _pct_in(arr: Sequence[float], v: float) -> float:
    """Percentile 0..1 of v among an ascending list (average rank for ties), for a member or not."""
    n = len(arr)
    if n == 1:
        return 0.5
    lo, hi = bisect_left(arr, v), bisect_right(arr, v)
    return min(1.0, max(0.0, ((lo + hi - 1) / 2.0) / (n - 1)))


def rank_scores_of(fr: Frame, terms: Sequence[Tuple[str, float]], member: Callable[[int], bool]) -> Dict[int, float]:
    """100 x the weighted sum of each input's percentile among its own size bucket's members. A company missing an input has no score (never a zero)."""
    pops: Dict[Tuple[str, str], List[float]] = {}
    for i in range(fr.t.n):
        b = fr.t.cap[i]
        if b is None or not member(i):
            continue
        for f, _ in terms:
            v = fr.get(i, f)
            if v is not None:
                pops.setdefault((b, f), []).append(v)
    for arr in pops.values():
        arr.sort()
    out: Dict[int, float] = {}
    for i in range(fr.t.n):
        b = fr.t.cap[i]
        if b is None:
            continue
        tot, ok = 0.0, True
        for f, w in terms:
            v, arr = fr.get(i, f), pops.get((b, f))
            if v is None or not arr:
                ok = False
                break
            tot += w * _pct_in(arr, v)
        if ok:
            out[i] = round(100.0 * tot, 4)
    return out


def rank_member(preset: Preset) -> Callable[[Frame], Callable[[int], bool]]:
    """Who counts in the percentile population: the bucket's Prism-rated companies (Advanced tab) or the bucket's companies of Rs 1,000 Cr or more (Basic tab)."""
    if preset.tab == "basic":
        return lambda fr: (lambda i: (fr.get(i, "market_cap") or 0) >= LEADER_FLOOR)
    return lambda fr: (lambda i: fr.pz[i].get("prism_status") == "RATED" and fr.pz[i].get("prism_final") is not None)


def apply_sector_cap(fr: Frame, order: Sequence[int], cap: int) -> List[int]:
    """The ordered list with at most `cap` companies from one Sector label (a company with no label counts as one group of its own)."""
    if not cap:
        return list(order)
    seen: Dict[str, int] = {}
    out: List[int] = []
    for i in order:
        k = fr.t.sector[i] or "(no sector)"
        if seen.get(k, 0) >= cap:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(i)
    return out


VIEW_FIELD = (("Short-term technical view", "prism_st_score"), ("Long-term technical view", "prism_lt_score"))


def view_notes(fr: Frame, rules: List[Rule]) -> List[str]:
    """How many rated companies were left out only because a technical view is blank (mostly recent listings), said on the card."""
    out = []
    for r in rules:
        field = next((f for w, f in VIEW_FIELD if r.label.startswith(w)), None)
        if field is None:
            continue
        n = sum(1 for i in range(fr.t.n) if fr.has_prism(i) and fr.get(i, field) is None and all(o.ok[i] for o in rules if o is not r))
        if n:
            out.append(f"{n} rated {'company has' if n == 1 else 'companies have'} no {'short' if field == 'prism_st_score' else 'long'}-term technical view yet "
                       f"(mostly recent listings), so {'it is' if n == 1 else 'they are'} left out.")
    return out


def _fmt(v: Any, fmt: str) -> Any:
    if v is None:
        return None
    if fmt == "label":
        return str(v).title()
    if isinstance(v, float):
        return round(v, 2)
    return v


def _row(fr: Frame, preset: Preset, i: int, pos: int, extra: Sequence[str] = ()) -> dict:
    row: Dict[str, Any] = {"symbol": fr.symbols[i], "name": fr.t.name[i]}
    for c in preset.columns:
        if c.key == "rank":
            row["rank"] = pos
        elif c.key == "name":
            continue
        elif c.key == "prism_status":
            s = fr.pz[i].get("prism_status")
            row["prism_status"] = s.title() if s in SCORED else None
        else:
            row[c.key] = _fmt(fr.get(i, c.key), c.format)
    row["badges"] = badges(fr, preset, i) + [b for b in extra if b]
    return row


def badges(fr: Frame, preset: Preset, i: int) -> List[str]:
    out: List[str] = []
    z = fr.pz[i]
    if "provisional" in preset.badges and z.get("prism_status") == "PROVISIONAL":
        out.append("Provisional")
    if "prism_confirmed" in preset.badges:
        st, lt = z.get("prism_st_score"), z.get("prism_lt_score")
        if st is not None and lt is not None and st >= CONFIRMED and lt >= CONFIRMED:
            out.append("Prism-confirmed")
    if "unrated" in preset.badges and not fr.has_prism(i):
        out.append("Not rated by Prism")
    if "loss_making" in preset.badges and fr.get(i, "flag_loss") == 1:
        out.append("Loss-making")
    return out


def closest_misses(fr: Frame, rules: List[Rule]) -> List[dict]:
    """The MISS_COUNT companies that fail the fewest rules, each with the rules it missed (only companies with a stored report and a market cap are considered)."""
    mc = fr.t.cols["market_cap"]
    best: List[Tuple[int, float, str, int]] = []
    for i in range(fr.t.n):
        if not fr.t.full[i] or mc[i] != mc[i]:
            continue
        failed = sum(1 for r in rules if not r.ok[i])
        best.append((failed, -mc[i], fr.symbols[i], i))
    best.sort()
    out = []
    for failed, _, sym, i in best[:MISS_COUNT]:
        if failed:
            out.append({"symbol": sym, "name": fr.t.name[i], "failed": [r.label for r in rules if not r.ok[i]]})
    return out


def _columns(preset: Preset) -> List[dict]:
    return [{"key": c.key, "label": c.label, "format": c.format, "align": c.align} for c in preset.columns]


def _base(fr: Frame, preset: Preset, cfg: Config, active: Sequence[str], count: int, rows: List[dict]) -> dict:
    return {"id": preset.id, "name": preset.name, "asOf": fr.as_of.isoformat(), "count": count, "shown": len(rows), "columns": _columns(preset), "rows": rows,
            "chips": list(active), "howItWorks": cfg.how, "cardText": preset.card_text, "disclaimer": DISCLAIMER, "version": REGISTRY_VERSION}


# ------------------------------------------------------------------------------------------------------------------------------ run
def run(fr: Frame, preset: Preset, requested: Optional[Sequence[str]] = None) -> dict:
    """The answer for one screen and chip set. Raises Blocked for a screen that cannot run, UnknownChip for a bad chip."""
    if preset.kind == "blocked":
        raise Blocked(preset)
    if preset.kind == "quickview":
        raise Blocked(preset)
    active = resolve_chips(preset, requested)
    cfg = Config(preset, active)
    fr.rank_scores = rank_scores_of(fr, preset.rank_score, rank_member(preset)(fr)) if preset.rank_score else {}
    if preset.kind == "themes":
        return run_themes(fr, preset, cfg, active)
    rules = build_rules(fr, cfg)
    n = fr.t.n
    idx = [i for i in range(n) if all(r.ok[i] for r in rules)]
    if preset.id == "results-standouts" and fr.latest_q is None:
        idx = []      # no reporting quarter can be told: say nothing rather than guess (the Query builder's recent check refuses the same way)
    key = sort_key(fr, cfg.rank)
    idx.sort(key=key)
    listed = apply_sector_cap(fr, idx, preset.sector_cap)
    filled: List[int] = []
    if preset.fill and len(listed) < preset.limit:
        # a short list: the next names that fail ONLY a gate this screen allows to fail (the trend and 52-week gates), badged
        soft = [r for r in rules if any(w.lower() in r.label.lower() for w in preset.fill)]
        hard = [r for r in rules if r not in soft]
        have = set(idx)
        cand = sorted((i for i in range(n) if i not in have and all(r.ok[i] for r in hard)), key=key)
        taken = apply_sector_cap(fr, listed + cand, preset.sector_cap)
        filled = [i for i in taken if i not in set(listed)][:preset.limit - len(listed)]
    rows = [_row(fr, preset, i, pos) for pos, i in enumerate(listed[:preset.limit], 1)]
    rows += [_row(fr, preset, i, pos, ("Trend not confirmed",)) for pos, i in enumerate(filled, len(rows) + 1)]
    out = _base(fr, preset, cfg, active, len(idx), rows)
    if preset.rank_score:
        out["rankScoreNote"] = "Ranked by a weighted score: each input is the company's percentile among its own size group."
    notes = view_notes(fr, rules)
    if notes:
        out["notes"] = notes
    if preset.limit < len(idx) or preset.top10:
        out["listText"] = f"Top {preset.limit} of {len(idx)} that pass" if preset.top10 else f"First {preset.limit} of {len(idx)}"
    out["cardText"] = render_card(preset, sum(1 for i in range(n) if fr.t.cap[i] == preset.prism_filters.get("cap") and fr.pz[i].get("prism_status") == "RATED") or None) if "{n}" in preset.card_text else preset.card_text
    out["ratedCount"] = sum(1 for i in idx if fr.has_prism(i))
    if preset.id == "fno-both-positive":
        out["of"] = {"label": "F&O stocks", "n": sum(1 for i in range(n) if fr.t.cols["fno"][i] == 1.0)}
    if preset.id == "highest-rated-small":
        out["of"] = {"label": "rated small caps", "n": sum(1 for i in range(n) if fr.t.cap[i] == "Small" and fr.pz[i].get("prism_status") == "RATED")}
    if not idx:
        out["closestMisses"] = closest_misses(fr, rules)
        out["emptyText"] = "No company meets every rule today."
    out["exportRows"] = [_row(fr, preset, i, pos) for pos, i in enumerate(listed[:EXPORT_MAX], 1)]
    return out


def leaders_of(fr: Frame, idx: Sequence[int], r3: Optional[float], rank: Optional[Sequence[Tuple[str, str]]] = None) -> List[int]:
    """A sector's leaders: market cap Rs 1,000 Cr or more, within 15% of the 52-week high, 3-month return above the sector's median; rated companies first."""
    pick = []
    for i in idx:
        mc, below, ret3 = fr.get(i, "market_cap"), fr.get(i, "pct_from_high"), fr.get(i, "ret_3m")
        if mc is None or mc < LEADER_FLOOR or below is None or below > themes.NEAR_HIGH or ret3 is None or r3 is None or ret3 <= r3:
            continue
        pick.append(i)
    pick.sort(key=sort_key(fr, rank or (("has_prism", "desc"), ("prism_final", "desc"), ("overall", "desc"))))
    return pick[:LEADERS]


def run_themes(fr: Frame, preset: Preset, cfg: Config, active: Sequence[str]) -> dict:
    ev = fr.theme_eval
    cards: List[dict] = []
    rows: List[dict] = []
    in_play_n = 0
    if ev is not None:
        market = ev.market

        def card(ind: str, state: str, leaders: List[int], reason: Optional[str] = None) -> dict:
            v = ev.industries[ind]
            return {"industry": ind, "state": state, "breadth": v["b50"], "r3": v["r3"], "rs3": v["rs3"], "members": v["members"], "small": v["small"],
                    "leaders": [fr.symbols[i] for i in leaders], "marketBreadth": market.b50, "reason": reason}

        names = sorted((k for k, v in ev.industries.items() if v["state"] == "in_play" and (cfg.small_groups or not v["small"])),
                       key=lambda k: -(ev.industries[k]["rs3"] or 0))
        for ind in names:
            v = ev.industries[ind]
            lead = leaders_of(fr, v["idx"], v["r3"], cfg.rank if preset.rank_score else None)
            cards.append(card(ind, "in_play", lead))
            for i in lead:
                r = _row(fr, preset, i, len(rows) + 1)
                r["industry"] = ind
                r["state"] = "in_play"
                rows.append(r)
        in_play_n = len(names)
        for state in ("emerging", "fading"):
            for ind, v in sorted(ev.industries.items()):
                if v["state"] == state and (cfg.small_groups or not v["small"]):
                    cards.append(card(ind, state, []))
        for ind in ev.closest:
            cards.append(card(ind, "closest", [], themes.why_not(ev.industries[ind], market)))
    out = _base(fr, preset, cfg, active, in_play_n, rows)
    out["themes"] = cards
    out["market"] = None if ev is None else {"breadth": ev.market.b50, "r3": ev.market.r3, "members": ev.market.members}
    out["closestTitle"] = "Closest to qualifying"
    out["exportRows"] = list(rows)
    return out


def how_it_works(preset: Preset) -> List[str]:
    return list(preset.how_it_works)
