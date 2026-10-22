"""Correlation and regression statistics for the advanced charts, in pure Python (no numpy or scipy on the server).

Precision rules: every sum is math.fsum (exactly rounded), means and centred sums are two-pass, the t distribution is the regularised
incomplete beta function by a Lentz continued fraction with math.lgamma, and its inverse is found by bisection to 1e-12. Reference values
(Anscombe's quartet, scipy-generated cases) live in tests/fixtures/advanced/stats_reference.json and are checked by tests/test_advanced_stats.py.

`analyse(points)` takes [(x, y, label)] already in the computation space (log10 applied by the caller for a log axis) and returns the
`stats` object documented in docs/ADVANCED-CHARTS-API.md section 6, plus the line decision (first failing rule wins).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Num = Optional[float]
Z975 = 1.959963984540054        # standard normal 97.5% point (Fisher interval for r)
MIN_LINE_N = 10
ALPHA = 0.05
MIN_ABS_R = 0.30
CURVE_P = 0.01
CURVE_DR2 = 0.10
PULL = 0.25
BAND_POINTS = 60
EPS_LEVERAGE = 1e-12

DECISION_TEXT = {
    "few": "Too few points for a reliable line (n = {n}).",
    "no_spread": "No line: the values do not vary.",
    "not_significant": "No reliable linear relationship (p = {p}).",
    "weak": "Statistically detectable but too weak to be useful (explains under 9%).",
    "one_company": "No line: the line depends on one company ({name}).",
    "curved": "No straight line: the relationship is curved.",
    "pulled": "Extreme values pull the straight line: both the straight line and a robust (Theil-Sen) line are drawn.",
    "ok": "A straight line is drawn with its 95% band.",
}


# ---------------------------------------------------------------- distributions

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz, Numerical Recipes 6.4)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 10001):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(ln_front) * _betacf(a, b, x) / a
    return 1.0 - math.exp(ln_front) * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value of Student's t with `df` degrees of freedom: I_{df/(df+t^2)}(df/2, 1/2)."""
    if math.isinf(t):
        return 0.0
    if t == 0:
        return 1.0
    return min(1.0, max(0.0, betainc(df / 2.0, 0.5, df / (df + t * t))))


def t_crit(df: float, two_sided_alpha: float = ALPHA) -> float:
    """t* with P(|T| > t*) = alpha, by bisection on the CDF to 1e-12 (absolute, on t)."""
    lo, hi = 0.0, 1.0
    while t_two_sided_p(hi, df) > two_sided_alpha:
        hi *= 2.0
    for _ in range(400):
        mid = (lo + hi) / 2.0
        if t_two_sided_p(mid, df) > two_sided_alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2.0


def _p_from_r(r: float, n: int) -> Tuple[Num, Num]:
    """(t, two-sided p) for a correlation r on n points; |r| = 1 gives (inf, 0)."""
    df = n - 2
    if df < 1:
        return None, None
    if abs(r) >= 1.0:
        return math.copysign(math.inf, r), 0.0
    t = r * math.sqrt(df / (1.0 - r * r))
    return t, t_two_sided_p(t, df)


# ---------------------------------------------------------------- building blocks

def mean(xs: Sequence[float]) -> float:
    return math.fsum(xs) / len(xs)


def median(xs: Sequence[float]) -> float:
    v = sorted(xs)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def ranks(xs: Sequence[float]) -> List[float]:
    """Average ranks (1-based); tied values share the mean of the ranks they span."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def moments(xs: Sequence[float], ys: Sequence[float]) -> Dict[str, float]:
    """Two-pass centred sums."""
    xb, yb = mean(xs), mean(ys)
    dx = [x - xb for x in xs]
    dy = [y - yb for y in ys]
    return {"xbar": xb, "ybar": yb, "sxx": math.fsum(d * d for d in dx), "syy": math.fsum(d * d for d in dy),
            "sxy": math.fsum(a * b for a, b in zip(dx, dy))}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Num:
    m = moments(xs, ys)
    if m["sxx"] <= 0 or m["syy"] <= 0:
        return None
    return max(-1.0, min(1.0, m["sxy"] / math.sqrt(m["sxx"] * m["syy"])))


def theil_sen(xs: Sequence[float], ys: Sequence[float]) -> Optional[Tuple[float, float]]:
    """Exact median of the pairwise slopes over pairs with different x; intercept = median(y - b x). None when every x is equal."""
    n = len(xs)
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(n) for j in range(i + 1, n) if xs[j] != xs[i]]
    if not slopes:
        return None
    b = median(slopes)
    return b, median([y - b * x for x, y in zip(xs, ys)])


def _fit(xs: Sequence[float], ys: Sequence[float]) -> Optional[Dict[str, Any]]:
    """OLS of y on x with the Pearson figures. None when n < 3 or there is no spread."""
    n = len(xs)
    if n < 3:
        return None
    m = moments(xs, ys)
    if m["sxx"] <= 0 or m["syy"] <= 0:
        return None
    r = max(-1.0, min(1.0, m["sxy"] / math.sqrt(m["sxx"] * m["syy"])))
    b = m["sxy"] / m["sxx"]
    a = m["ybar"] - b * m["xbar"]
    res = [y - a - b * x for x, y in zip(xs, ys)]
    sse = math.fsum(e * e for e in res)
    t, p = _p_from_r(r, n)
    return {"n": n, **m, "r": r, "b": b, "a": a, "res": res, "sse": sse, "s": math.sqrt(sse / (n - 2)), "t": t, "p": p}


def _quadratic(xs: Sequence[float], ys: Sequence[float], lin: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Test for curvature: add a centred x^2 term. Done by orthogonalising z = xc^2 against (1, xc) so the quadratic coefficient is
    Szy / Szz on the residualised z (numerically stable, no 3x3 normal-equation solve). t-test on c2 with n - 3 df; dR2 = R2_quad - R2_lin."""
    n = len(xs)
    if n < 4:
        return None
    xb = lin["xbar"]
    xc = [x - xb for x in xs]
    z = [c * c for c in xc]
    zb = mean(z)
    zc = [v - zb for v in z]
    g = math.fsum(a * b for a, b in zip(zc, xc)) / lin["sxx"]
    zr = [a - g * b for a, b in zip(zc, xc)]           # z with the linear part removed
    szz = math.fsum(v * v for v in zr)
    if szz <= 1e-300 * max(1.0, math.fsum(v * v for v in zc)):
        return None
    yb = lin["ybar"]
    szy = math.fsum(a * (y - yb) for a, y in zip(zr, ys))
    c2 = szy / szz
    sse_q = max(0.0, lin["sse"] - szy * szy / szz)
    df = n - 3
    dr2 = (szy * szy / szz) / lin["syy"]
    if sse_q <= 0:
        p = 0.0 if c2 != 0 else 1.0
    else:
        se = math.sqrt(sse_q / df / szz)
        p = t_two_sided_p(c2 / se, df)
    return {"c2": c2, "p": p, "dR2": dr2}


# ---------------------------------------------------------------- the full analysis

def analyse(points: Sequence[Tuple[float, float, Any]], back_x: Optional[Callable[[float], float]] = None,
            back_y: Optional[Callable[[float], float]] = None, name_of: Optional[Callable[[Any], str]] = None) -> Optional[Dict[str, Any]]:
    """points = [(x, y, label)] in computation space, ordered (callers sort by symbol so ties break the same way every time).
    back_x / back_y transform computation space back to data units for the line and band (10**v for a log axis)."""
    n = len(points)
    if n == 0:
        return None
    bx = back_x or (lambda v: v)
    by = back_y or (lambda v: v)
    nm = name_of or (lambda lab: str(lab))
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    labels = [p[2] for p in points]
    m = moments(xs, ys)
    out: Dict[str, Any] = {"n": n, "mean": {"x": m["xbar"], "y": m["ybar"]}, "sxx": m["sxx"], "syy": m["syy"], "sxy": m["sxy"],
                           "pearson": None, "spearman": None, "ols": None, "theilSen": None, "influence": None, "curvature": None,
                           "line": None, "tsLine": None, "band": None}
    fit = _fit(xs, ys) if n >= 3 else None
    if fit:
        r = fit["r"]
        ci = None
        if n >= MIN_LINE_N and abs(r) < 1:
            zr = math.atanh(r)
            half = Z975 / math.sqrt(n - 3)
            ci = [math.tanh(zr - half), math.tanh(zr + half)]
        out["pearson"] = {"r": r, "r2": r * r, "t": None if math.isinf(fit["t"]) else fit["t"], "df": n - 2, "p": fit["p"], "ci": ci}
        tc = t_crit(n - 2)
        se = fit["s"] / math.sqrt(fit["sxx"])
        out["ols"] = {"slope": fit["b"], "intercept": fit["a"], "se": se, "ci": [fit["b"] - tc * se, fit["b"] + tc * se], "s": fit["s"], "tCrit": tc}
        rx, ry = ranks(xs), ranks(ys)
        rho = pearson(rx, ry)
        if rho is not None:
            out["spearman"] = {"rho": rho, "p": _p_from_r(rho, n)[1] if n >= MIN_LINE_N else None}
    ts = theil_sen(xs, ys) if n >= 2 else None
    if ts:
        out["theilSen"] = {"slope": ts[0], "intercept": ts[1]}

    # influence: leverage and Cook's distance; refit without the most influential point
    if fit and n >= 4:
        best_i, best_d = None, -1.0
        lev_best = None
        for i in range(n):
            h = 1.0 / n + (xs[i] - fit["xbar"]) ** 2 / fit["sxx"]
            if h >= 1.0 - EPS_LEVERAGE:
                d = math.inf
            elif fit["s"] == 0:
                d = 0.0
            else:
                d = fit["res"][i] ** 2 / (2.0 * fit["s"] ** 2) * h / (1.0 - h) ** 2
            if d > best_d:
                best_i, best_d, lev_best = i, d, h
        xs1 = xs[:best_i] + xs[best_i + 1:]
        ys1 = ys[:best_i] + ys[best_i + 1:]
        f1 = _fit(xs1, ys1)
        out["influence"] = {"max": {"label": labels[best_i], "name": nm(labels[best_i]), "cook": None if math.isinf(best_d) else best_d, "leverage": min(1.0, lev_best)},
                            "without": None if f1 is None else {"n": n - 1, "r": f1["r"], "p": f1["p"], "slope": f1["b"]}}
        out["curvature"] = _quadratic(xs, ys, fit)

    out["decision"] = _decide(out, n)
    line = out["decision"]["line"]
    if line != "none":
        x0, x1 = min(xs), max(xs)
        a, b = fit["a"], fit["b"]  # type: ignore[index]
        out["line"] = {"x0": bx(x0), "y0": by(a + b * x0), "x1": bx(x1), "y1": by(a + b * x1)}
        if line == "ols_ts":
            tb, ta = ts  # type: ignore[misc]
            out["tsLine"] = {"x0": bx(x0), "y0": by(ta + tb * x0), "x1": bx(x1), "y1": by(ta + tb * x1)}
        tc, s = out["ols"]["tCrit"], fit["s"]  # type: ignore[index]
        band = []
        for k in range(BAND_POINTS):
            xv = x0 + (x1 - x0) * k / (BAND_POINTS - 1)
            yh = a + b * xv
            half = tc * s * math.sqrt(1.0 / n + (xv - fit["xbar"]) ** 2 / fit["sxx"])  # type: ignore[index]
            band.append({"x": bx(xv), "lo": by(yh - half), "y": by(yh), "hi": by(yh + half)})
        out["band"] = band
    out["rounded"] = rounded(out)
    return out


def _decide(st: Dict[str, Any], n: int) -> Dict[str, str]:
    def d(line: str, rule: str, **kw: Any) -> Dict[str, str]:
        return {"line": line, "rule": rule, "text": DECISION_TEXT[rule].format(**kw)}
    if n < MIN_LINE_N:
        return d("none", "few", n=n)
    if st["sxx"] <= 0 or st["syy"] <= 0 or st["pearson"] is None:
        return d("none", "no_spread")
    p, r = st["pearson"]["p"], st["pearson"]["r"]
    if p >= ALPHA:
        return d("none", "not_significant", p=fmt_p(p))
    if abs(r) < MIN_ABS_R:
        return d("none", "weak")
    b = st["ols"]["slope"]
    inf = st["influence"]
    ts = st["theilSen"]
    w = inf["without"] if inf else None
    if inf is not None and (w is None or _sign(w["slope"]) != _sign(b) or w["p"] is None or w["p"] >= ALPHA or abs(w["r"]) < MIN_ABS_R):
        return d("none", "one_company", name=inf["max"]["name"])
    if ts is None or _sign(ts["slope"]) != _sign(b):
        return d("none", "one_company", name=inf["max"]["name"] if inf else "")
    cv = st["curvature"]
    if cv is not None and cv["p"] < CURVE_P and cv["dR2"] >= CURVE_DR2:
        return d("none", "curved")
    if abs(ts["slope"] - b) > PULL * abs(b):
        return d("ols_ts", "pulled")
    return d("ols", "ok")


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


# ---------------------------------------------------------------- display strings (the plan's rounding rules)

def fmt_p(p: Num) -> str:
    if p is None:
        return "n/a"
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3g}"


def sig(v: Num, digits: int = 3) -> Optional[str]:
    if v is None or not math.isfinite(v):
        return None
    if v == 0:
        return "0"
    return f"{v:.{digits}g}" if 1e-4 <= abs(v) < 1e6 else f"{v:.{digits - 1}e}"


def rounded(st: Dict[str, Any]) -> Dict[str, Optional[str]]:
    pr, sp, ols = st.get("pearson"), st.get("spearman"), st.get("ols")
    return {"r": f"{pr['r']:.2f}" if pr else None, "rho": f"{sp['rho']:.2f}" if sp else None, "p": fmt_p(pr["p"]) if pr else None,
            "slope": sig(ols["slope"]) if ols else None, "r2pct": f"{round(pr['r2'] * 100)}%" if pr else None}


def round_sig(v: Any, digits: int = 6) -> Any:
    """Recursively round floats to `digits` significant figures for JSON output; inf/nan become None."""
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return float(f"{v:.{digits}g}")
    if isinstance(v, dict):
        return {k: round_sig(x, digits) for k, x in v.items()}
    if isinstance(v, list):
        return [round_sig(x, digits) for x in v]
    return v


# ---------------------------------------------------------------- quantiles (type 7, as R's default and numpy's "linear")

def quantile7(sorted_xs: Sequence[float], q: float) -> float:
    n = len(sorted_xs)
    h = (n - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, n - 1)
    return sorted_xs[lo] + (h - lo) * (sorted_xs[hi] - sorted_xs[lo])
