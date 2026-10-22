"""Generates backend/tests/fixtures/advanced/stats_reference.json with scipy/numpy (throwaway venv, never a repo dependency)."""
import json, sys, math
import numpy as np, scipy
from scipy import stats

def lcg(seed):
    s = seed
    while True:
        s = (1103515245 * s + 12345) % (2**31)
        yield s / 2**31

def gen_random(n, seed, slope, noise):
    g = lcg(seed); xs, ys = [], []
    for _ in range(n):
        x = round(next(g) * 100, 4)
        e = (next(g) + next(g) + next(g) - 1.5) * noise
        xs.append(x); ys.append(round(slope * x + 5 + e, 4))
    return xs, ys

ax = [10, 8, 13, 9, 11, 14, 6, 4, 12, 7, 5]
D = {
 "anscombe_I": (ax, [8.04,6.95,7.58,8.81,8.33,9.96,7.24,4.26,10.84,4.82,5.68]),
 "anscombe_II": (ax, [9.14,8.14,8.74,8.77,9.26,8.10,6.13,3.10,9.13,7.26,4.74]),
 "anscombe_III": (ax, [7.46,6.77,12.74,7.11,7.81,8.84,6.08,5.39,8.15,6.42,5.73]),
 "anscombe_IV": ([8,8,8,8,8,8,8,19,8,8,8], [6.58,5.76,7.71,8.84,8.47,7.04,5.25,12.50,5.56,7.91,6.89]),
}
D["random_pos_n60"] = gen_random(60, 7, 0.35, 40)
xs, ys = gen_random(200, 11, -0.8, 90); D["random_neg_n200"] = (xs, ys)
D["ties_n30"] = ([float(i % 5) for i in range(30)], [float((i * 7) % 4) + (i % 5) * 0.5 for i in range(30)])
xs, ys = gen_random(40, 3, 1.2, 15); D["offset_1e6_n40"] = ([x + 1e6 for x in xs], [y + 5e5 for y in ys])
xs, ys = gen_random(25, 19, 0.0, 50); D["noise_n25"] = (xs, ys)
D["exact_line"] = ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], [2*x+1 for x in [1,2,3,4,5,6,7,8,9,10,11,12]])

out = {"generator": "scipy " + scipy.__version__ + ", numpy " + np.__version__ + ", python " + sys.version.split()[0], "datasets": {}}
for name, (x, y) in D.items():
    x = np.array(x, float); y = np.array(y, float); n = len(x)
    rec = {"x": x.tolist(), "y": y.tolist(), "n": n}
    lr = stats.linregress(x, y)
    rec.update(r=float(lr.rvalue), slope=float(lr.slope), intercept=float(lr.intercept), se_slope=float(lr.stderr), p=float(lr.pvalue))
    rho = stats.spearmanr(x, y)
    rec.update(rho=float(rho.statistic), rho_p=float(rho.pvalue))
    ts = stats.theilslopes(y, x, method="joint")
    rec.update(ts_slope=float(ts.slope), ts_intercept=float(ts.intercept))
    tc = float(stats.t.ppf(0.975, n - 2)); rec["t_crit"] = tc
    if abs(lr.rvalue) < 1:
        z = np.arctanh(lr.rvalue); h = stats.norm.ppf(0.975) / math.sqrt(n - 3)
        rec["fisher_ci"] = [float(np.tanh(z - h)), float(np.tanh(z + h))]
        res = y - lr.intercept - lr.slope * x; s = math.sqrt((res**2).sum() / (n - 2))
        xb = x.mean(); sxx = ((x - xb)**2).sum()
        x0 = float(x.min()); rec["band_at_min"] = [float(lr.intercept + lr.slope * x0 - tc * s * math.sqrt(1/n + (x0-xb)**2/sxx)),
                                                    float(lr.intercept + lr.slope * x0 + tc * s * math.sqrt(1/n + (x0-xb)**2/sxx))]
        # quadratic term on centred x, OLS by lstsq, t-test n-3 df
        xc = x - xb; X = np.column_stack([np.ones(n), xc, xc**2])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None); r_q = y - X @ beta; sse_q = (r_q**2).sum()
        cov = sse_q / (n - 3) * np.linalg.inv(X.T @ X); tq = beta[2] / math.sqrt(cov[2, 2])
        syy = ((y - y.mean())**2).sum()
        rec.update(c2=float(beta[2]), c2_p=float(2 * stats.t.sf(abs(tq), n - 3)), dR2=float((1 - sse_q/syy) - lr.rvalue**2))
        h_ii = 1/n + (x-xb)**2/sxx
        with np.errstate(divide="ignore", invalid="ignore"):
            cook = res**2 / (2 * s**2) * h_ii / (1 - h_ii)**2
        rec["cook_max_index"] = int(np.nanargmax(np.where(h_ii >= 1 - 1e-12, np.inf, cook)))
    out["datasets"][name] = rec
out["t_crit"] = {str(df): float(stats.t.ppf(0.975, df)) for df in (1, 2, 5, 9, 30, 100, 1000)}
out["t_p"] = [[t, df, float(2 * stats.t.sf(t, df))] for t, df in ((2, 10), (1, 5), (4.241455, 9), (0.5, 1), (10, 3), (3.5, 200), (25, 800))]
json.dump(out, open(sys.argv[1], "w"), indent=1)
print("ok", list(out["datasets"]))
