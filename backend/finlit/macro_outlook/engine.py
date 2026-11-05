"""The scoring engine of the Macro & Sector Outlook: pure functions, no database, no network, no clock (docs/MACRO-OUTLOOK.md, PRD sections 3 to 6).

    observations (value, observation date, publication date, revision)
      -> known_series(as_of)                 only what was public at the as-of date, the latest revision published by then
      -> indicator_result                    Level Signal and Momentum Signal, each capped to [-1, +1]; Indicator Signal = their average
      -> score_sector                        Contribution = Signal x Sensitivity x Weight, aggregated over the VALID indicators only,
                                             MacroScore = 50 + 50 x tanh(WeightedSignal / K), coverage and critical-indicator rules, drivers

Signal convention: a positive signal means the indicator is HIGH or RISING against its reference, a negative one LOW or FALLING. Whether that helps or
hurts a sector is the sector's sensitivity coefficient (+1 helps, -1 hurts); the signal never says "good" or "bad" by itself.

Aggregation (fixed, versioned): WeightedSignal = signal_scale x (sum of contributions of valid indicators) / (sum of the weights of valid indicators).
The PRD's trial K of 3 belongs to an unnormalised sum; with the weights normalised as the PRD recommends, the average lies in [-1, +1], so the model
carries `signal_scale` to put it back on the range K was meant for. Both are configuration, stored with every model version and every snapshot.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VALID_STATUSES = ("Available", "Revised")
EPS = 1e-9
SIGNAL_DP = 6
CONTRIBUTION_DP = 8


def clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def finite(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


# ------------------------------------------------------------------------------------------------------------ observations
@dataclass(frozen=True)
class Obs:
    """One stored observation (or one revision of it)."""
    observation_date: date
    publication_date: date
    value: float
    revision: int = 1
    status: str = "Available"           # Invalid rows are kept for the data-health view and never used
    basis: str = ""                     # how the publication date is known (pub_date_basis)


def known_series(rows: Iterable[Obs], as_of: date) -> List[Obs]:
    """The series as it was known at `as_of`: per observation date, the latest revision already published; invalid rows left out; oldest first.
    This is the look-ahead rule: nothing published after `as_of` is visible, however old the observation it describes."""
    best: Dict[date, Obs] = {}
    for r in rows:
        if r.publication_date > as_of or r.observation_date > as_of:
            continue
        cur = best.get(r.observation_date)
        if cur is None or r.revision > cur.revision:
            best[r.observation_date] = r
    return [o for _, o in sorted(best.items()) if o.status != "Invalid"]


# ------------------------------------------------------------------------------------------------------------ normalisation
def _nearest(series: Sequence[Obs], target: date, tolerance_days: float, before: date) -> Optional[Obs]:
    best, gap = None, None
    for o in series:
        if o.observation_date >= before:
            continue
        g = abs((o.observation_date - target).days)
        if g <= tolerance_days and (gap is None or g < gap):
            best, gap = o, g
    return best


def _window(series: Sequence[Obs], end: date, days: int) -> List[float]:
    start = end - timedelta(days=days)
    return [o.value for o in series if start < o.observation_date <= end]


def level_signal(norm: Dict[str, Any], series: Sequence[Obs]) -> Optional[float]:
    """The Level Signal in [-1, +1]: where the latest reading stands against its configured reference.
    threshold    clip((x - neutral) / scale)
    hump         rises like threshold up to `peak`, then falls back towards zero over `fall` (an overheated reading is not better than a healthy one)
    pct_vs_mean  clip((x / mean of the last `window_days` - 1) x 100 / scale_pct)
    percentile   the share of the last `window_days` readings below x, mapped to [-1, +1]
    zscore       clip((x - mean) / sd / cap) over the last `window_days`"""
    cfg = norm.get("level") or {}
    method = cfg.get("method")
    if not series or not method or method == "none":
        return None
    last = series[-1]
    x = last.value
    if method == "threshold":
        scale = finite(cfg.get("scale")) or 0.0
        return clip((x - float(cfg["neutral"])) / scale) if scale > 0 else None
    if method == "hump":
        neutral, scale, peak, fall = float(cfg["neutral"]), float(cfg["scale"]), float(cfg["peak"]), float(cfg["fall"])
        if scale <= 0 or fall <= 0:
            return None
        if x <= peak:
            return clip((x - neutral) / scale)
        top = clip((peak - neutral) / scale)
        return clip(top * (1.0 - (x - peak) / fall))
    window = _window(series, last.observation_date, int(cfg.get("window_days", 365)))
    if method == "pct_vs_mean":
        if len(window) < int(cfg.get("min_points", 3)):
            return None
        mean = sum(window) / len(window)
        scale = float(cfg.get("scale_pct", 3.0))
        return clip((x / mean - 1.0) * 100.0 / scale) if mean > 0 and scale > 0 else None
    if method == "percentile":
        if len(window) < int(cfg.get("min_points", 12)):
            return None
        below = sum(1 for v in window if v < x) + 0.5 * sum(1 for v in window if v == x)
        return clip(2.0 * below / len(window) - 1.0)
    if method == "zscore":
        if len(window) < int(cfg.get("min_points", 12)):
            return None
        mean = sum(window) / len(window)
        sd = math.sqrt(sum((v - mean) ** 2 for v in window) / len(window))
        cap = float(cfg.get("cap", 3.0))
        return clip((x - mean) / sd / cap) if sd > 0 and cap > 0 else None
    return None


def momentum_signal(norm: Dict[str, Any], series: Sequence[Obs]) -> Optional[float]:
    """The Momentum Signal in [-1, +1]: the change over `lookback_days` (the observation closest to that date, within a quarter of the span), divided by
    the typical change `scale` (percentage points for `change`, per cent for `pct_change`). None when there is no comparable earlier reading."""
    cfg = norm.get("momentum") or {}
    method = cfg.get("method")
    if not series or not method or method == "none":
        return None
    last = series[-1]
    lookback = int(cfg.get("lookback_days", 90))
    then = _nearest(series, last.observation_date - timedelta(days=lookback), max(5.0, 0.25 * lookback), last.observation_date)
    if then is None:
        return None
    scale = float(cfg.get("scale", 1.0))
    if scale <= 0:
        return None
    if method == "change":
        return clip((last.value - then.value) / scale)
    if method == "pct_change":
        return clip(((last.value / then.value) - 1.0) * 100.0 / scale) if then.value > 0 else None
    return None


@dataclass
class IndicatorResult:
    code: str
    name: str
    status: str                          # Available | Stale | Missing | Invalid | Revised
    value: Optional[float] = None
    unit: str = ""
    observation_date: Optional[date] = None
    publication_date: Optional[date] = None
    pub_basis: str = ""
    revision: int = 1
    prev_value: Optional[float] = None
    prev_observation_date: Optional[date] = None
    level: Optional[float] = None
    momentum: Optional[float] = None
    signal: Optional[float] = None       # final, None unless the indicator is valid
    age_days: Optional[int] = None
    reason: str = ""

    @property
    def valid(self) -> bool:
        return self.status in VALID_STATUSES and self.signal is not None


def indicator_result(code: str, name: str, unit: str, norm: Dict[str, Any], stale_after_days: int, series: Sequence[Obs], as_of: date) -> IndicatorResult:
    """One indicator at one as-of date. A missing or stale indicator gets NO signal (never a neutral zero); a signal is the average of the parts that
    can be computed, and a missing momentum is reported, never filled."""
    if not series:
        return IndicatorResult(code, name, "Missing", unit=unit, reason="no observation had been published by this date")
    last = series[-1]
    prev = series[-2] if len(series) > 1 else None
    res = IndicatorResult(code, name, "Revised" if last.revision > 1 else "Available", last.value, unit, last.observation_date, last.publication_date, last.basis, last.revision,
                          prev.value if prev else None, prev.observation_date if prev else None, age_days=(as_of - last.observation_date).days)
    if res.age_days is not None and res.age_days > stale_after_days:
        res.status = "Stale"
        res.reason = f"latest reading is {res.age_days} days old (limit {stale_after_days})"
        return res
    lv, mo = level_signal(norm, series), momentum_signal(norm, series)
    parts = [p for p in (lv, mo) if p is not None]
    if not parts:
        res.status, res.reason = "Missing", "not enough history to compute a signal"
        return res
    res.level = None if lv is None else round(lv, SIGNAL_DP)
    res.momentum = None if mo is None else round(mo, SIGNAL_DP)
    res.signal = round(clip(sum(parts) / len(parts)), SIGNAL_DP)
    if mo is None and (norm.get("momentum") or {}).get("method") not in (None, "none"):
        res.reason = "momentum unavailable (no earlier reading to compare with): the signal is the level alone"
    return res


# ------------------------------------------------------------------------------------------------------------ the sector score
@dataclass(frozen=True)
class Rule:
    """One row of the sensitivity matrix for one sector."""
    indicator: str
    coefficient: float
    weight: float
    critical: bool = False
    method: str = ""


@dataclass(frozen=True)
class ModelConfig:
    version: int
    k: float
    signal_scale: float
    min_coverage: float
    bands: Tuple[Tuple[float, str], ...]            # (minimum rounded score, label), highest first
    stale_after_hours: int = 48

    def as_json(self) -> Dict[str, Any]:
        return {"version": self.version, "k": self.k, "signalScale": self.signal_scale, "minCoverage": self.min_coverage,
                "bands": [{"min": m, "label": l} for m, l in self.bands], "staleAfterHours": self.stale_after_hours}


DEFAULT_BANDS: Tuple[Tuple[float, str], ...] = ((80, "Strong Tailwind"), (65, "Tailwind"), (45, "Neutral"), (25, "Headwind"), (0, "Strong Headwind"))
INSUFFICIENT = "Insufficient Data"


def band_of(score: float, bands: Sequence[Tuple[float, str]]) -> str:
    """The label of the whole-number score (half up), so that the label always agrees with the number shown."""
    shown = math.floor(score + 0.5)
    for lo, label in sorted(bands, key=lambda b: -b[0]):
        if shown >= lo:
            return label
    return sorted(bands, key=lambda b: b[0])[0][1]


def tone_of(label: str) -> str:
    return {"Strong Tailwind": "up2", "Tailwind": "up", "Neutral": "flat", "Headwind": "down", "Strong Headwind": "down2"}.get(label, "none")


@dataclass
class Contribution:
    indicator: str
    name: str
    status: str
    coefficient: float
    weight: float
    critical: bool
    counted: bool
    value: Optional[float] = None
    unit: str = ""
    observation_date: Optional[date] = None
    publication_date: Optional[date] = None
    pub_basis: str = ""
    level: Optional[float] = None
    momentum: Optional[float] = None
    signal: Optional[float] = None
    contribution: Optional[float] = None
    direction: str = "excluded"          # positive | negative | neutral | excluded
    reason: str = ""
    priority: int = 100


@dataclass
class SectorScore:
    status: str                          # ok | insufficient_data
    score: Optional[float]
    label: str
    weighted_signal: Optional[float]
    coverage: float
    min_coverage: float
    contributions: List[Contribution]
    drivers: List[Contribution]
    critical_missing: List[str]
    missing: List[str]
    reason: str = ""
    inputs_hash: str = ""


def tanh_score(weighted_signal: float, k: float) -> float:
    return round(max(0.0, min(100.0, 50.0 + 50.0 * math.tanh(weighted_signal / k))), 2)


def aggregate(contribs: Sequence[Tuple[float, float]], cfg: ModelConfig) -> Tuple[float, float]:
    """(weighted signal, score) from (contribution, weight) pairs of the valid indicators. The single place the formula lives, so a stored snapshot can be
    recomputed from its stored contributions and give the same score (tests do exactly that)."""
    total_w = sum(abs(w) for _, w in contribs)
    if total_w <= 0:
        raise ValueError("no weight")
    ws = round(cfg.signal_scale * sum(c for c, _ in contribs) / total_w, 6)
    return ws, tanh_score(ws, cfg.k)


def driver_order(c: Contribution) -> Tuple:
    """Largest absolute contribution first; ties (to 6 decimals) by the configured priority (lower first), then the fresher observation, then the code."""
    fresh = -(c.observation_date.toordinal() if c.observation_date else 0)
    return (-round(abs(c.contribution or 0.0), 6), c.priority, fresh, c.indicator)


def rank_drivers(contribs: Sequence[Contribution], n: int = 2) -> List[Contribution]:
    live = [c for c in contribs if c.counted and c.contribution is not None and abs(c.contribution) > EPS]
    return sorted(live, key=driver_order)[:n]


def inputs_fingerprint(sector: str, version: int, items: Iterable[Contribution]) -> str:
    rows = [[c.indicator, c.status, None if c.value is None else round(c.value, 6), str(c.observation_date), str(c.publication_date), c.coefficient, c.weight, c.critical]
            for c in sorted(items, key=lambda c: c.indicator)]
    return hashlib.sha256(json.dumps([sector, version, rows], sort_keys=True).encode()).hexdigest()[:32]


def score_sector(sector: str, rules: Sequence[Rule], results: Dict[str, IndicatorResult], cfg: ModelConfig, priorities: Optional[Dict[str, int]] = None) -> SectorScore:
    """The sector's macro score from its sensitivity rules and the indicator results. Missing, stale and invalid indicators are EXCLUDED (never zero-filled).
    Coverage = valid weight / total active weight. Below the minimum coverage, or with a critical indicator not valid, the answer is Insufficient Data."""
    priorities = priorities or {}
    items: List[Contribution] = []
    for r in rules:
        res = results.get(r.indicator)
        base = dict(indicator=r.indicator, name=res.name if res else r.indicator, coefficient=r.coefficient, weight=r.weight, critical=r.critical,
                    priority=priorities.get(r.indicator, 100))
        if res is not None:
            base.update(status=res.status, value=res.value, unit=res.unit, observation_date=res.observation_date, publication_date=res.publication_date,
                        pub_basis=res.pub_basis, level=res.level, momentum=res.momentum)
        if res is not None and res.valid:
            sig = res.signal
            c = round(sig * r.coefficient * r.weight, CONTRIBUTION_DP)
            direction = "positive" if c > EPS else "negative" if c < -EPS else "neutral"
            items.append(Contribution(**base, signal=sig, counted=True, contribution=c, direction=direction, reason=res.reason))
        else:
            why = (res.reason if res else "indicator not configured") or res.status.lower()
            items.append(Contribution(**{**base, "status": base.get("status", "Missing")}, counted=False, reason=why))
    total_w = sum(c.weight for c in items)
    valid = [c for c in items if c.counted]
    valid_w = sum(c.weight for c in valid)
    coverage = round(valid_w / total_w, 4) if total_w > 0 else 0.0
    critical_missing = [c.indicator for c in items if c.critical and not c.counted]
    missing = [c.indicator for c in items if not c.counted]
    fp = inputs_fingerprint(sector, cfg.version, items)
    names = {c.indicator: c.name for c in items}
    if not valid or coverage + EPS < cfg.min_coverage or critical_missing:
        why = []
        if critical_missing:
            why.append("missing critical: " + ", ".join(names[m] for m in critical_missing))
        if coverage + EPS < cfg.min_coverage or not valid:
            others = [names[m] for m in missing if m not in critical_missing]
            why.append(f"coverage {coverage * 100:.0f}% is below the {cfg.min_coverage * 100:.0f}% minimum" + (": missing " + ", ".join(others) if others else ""))
        return SectorScore("insufficient_data", None, INSUFFICIENT, None, coverage, cfg.min_coverage, items, [], critical_missing, missing, "; ".join(why), fp)
    ws, score = aggregate([(c.contribution, c.weight) for c in valid], cfg)
    return SectorScore("ok", score, band_of(score, cfg.bands), ws, coverage, cfg.min_coverage, items, rank_drivers(valid), critical_missing, missing, "", fp)


def recompute_from_stored(contribs: Sequence[Dict[str, Any]], cfg: ModelConfig) -> Tuple[float, float]:
    """Recompute (weighted signal, score) from the stored contribution rows of a snapshot: the audit that the formula is reproducible."""
    pairs = [(float(c["contribution"]), float(c["weight"])) for c in contribs if c.get("counted")]
    return aggregate(pairs, cfg)


# ------------------------------------------------------------------------------------------------------------ words (describe, never advise)
def value_text(value: Optional[float], unit: str) -> str:
    if value is None:
        return "no reading"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "bp":
        return f"{value:+.0f} bp"
    if unit in ("$/bbl", "$/mmBtu", "$/t"):
        return f"${value:,.2f}" + ("/bbl" if unit == "$/bbl" else "/mmBtu" if unit == "$/mmBtu" else "/t")
    if unit == "₹":
        return f"₹{value:.2f}"
    if unit == "pp":
        return f"{value:+.2f} pp"
    return f"{value:g} {unit}".strip()


def signal_word(signal: Optional[float]) -> str:
    if signal is None:
        return ""
    return "high or rising" if signal >= 0.25 else "low or falling" if signal <= -0.25 else "near its reference"


def explain(label: str, sector_name: str, contribs: Sequence[Contribution], rules_all: Sequence[Rule], names: Dict[str, str], per_side: int = 3) -> Dict[str, Any]:
    """The short interpretation, built only from the actual contributions: what supports the sector, what weighs on it, and what to keep an eye on
    (the sector's most influential indicators that are not already listed, and any critical input that is missing). Facts and arithmetic only."""
    live = [c for c in contribs if c.counted and c.contribution is not None and abs(c.contribution) > EPS]
    sup = sorted([c for c in live if c.contribution > 0], key=driver_order)[:per_side]
    adv = sorted([c for c in live if c.contribution < 0], key=driver_order)[:per_side]

    def item(c: Contribution) -> Dict[str, Any]:
        return {"code": c.indicator, "name": c.name, "value": c.value, "unit": c.unit, "valueText": value_text(c.value, c.unit), "signal": c.signal,
                "contribution": c.contribution, "reading": signal_word(c.signal)}
    shown = {c.indicator for c in sup + adv}
    watch: List[Dict[str, Any]] = []
    by_code = {c.indicator: c for c in contribs}
    for r in sorted(rules_all, key=lambda r: (-abs(r.coefficient) * r.weight, r.indicator)):
        c = by_code.get(r.indicator)
        if r.indicator in shown or len(watch) >= 3:
            continue
        if c is not None and not c.counted:
            watch.append({"code": r.indicator, "name": names.get(r.indicator, r.indicator), "why": "no usable reading" + (" (critical input)" if r.critical else ""), "critical": r.critical})
        elif c is not None and (r.critical or abs(r.coefficient) * r.weight >= 0.75):
            watch.append({"code": r.indicator, "name": c.name, "why": "large weight in this sector" if not r.critical else "critical input", "critical": r.critical})
    if not live:
        headline = f"{sector_name}: no indicator is moving the score at present."
    else:
        lead = max(live, key=lambda c: abs(c.contribution))
        headline = f"{sector_name}: {label}. Largest effect is {lead.name} ({'supporting' if lead.contribution > 0 else 'weighing'})."
    return {"headline": headline, "supporting": [item(c) for c in sup], "adverse": [item(c) for c in adv], "monitor": watch}
