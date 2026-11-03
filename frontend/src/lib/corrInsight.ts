/**
 * Rule-based insight text for the correlation (scatter) chart, from the developer spec "Rule-Based Insight Text for the Correlation Chart".
 * No model, no network: computed statistics, threshold rules and sentence templates. Pure: the same input always gives the same text.
 * Answers three questions: how X and Y relate across all points, where each selected company sits against the rest, and how far to trust it.
 * Comparative wording only ("higher than", "lower than", "typical company"); never advice, never cause.
 */
export type MetricCfg = { label: string; higher: string; lower: string };
export type InPoint = { s: string; x: number; y: number };
export type InSelected = { s: string; name: string; x: number | null; y: number | null; why: string | null };
export type InsightInput = {
  x: MetricCfg; y: MetricCfg;
  /** Every valid point of the cloud (the selected companies are among them). Statistics use all of them, outliers included. */
  points: InPoint[];
  selected: InSelected[];
  /** Spearman rho and its p-value from the server (rank based, robust to extreme values). */
  rho: number | null; p: number | null;
  /** Points outside the visible window (display only; the statistics still use them). */
  outside: number;
  /** "FY2025", "FY2024 to FY2025", "TTM"… shown in the footer. */
  period: string | null;
  who: string;                                     // "companies", "years", "windows"
  fx: (v: number) => string; fy: (v: number) => string;
  /** Y is a growth measure: the base-effect caveat applies (the floor per metric is still to be set by product). */
  yGrowth?: boolean;
  nameOfPeers?: string;
};
export type Insight = {
  state: "ok" | "empty";
  cloud: string;
  shape: string | null;
  companies: string[];
  comparison: string[];
  caveats: string[];
  footer: string;
};

export const MIN_N = 30;
export const MAX_BLOCKS = 3;
export const CLOSING = "Describes how the figures sit against each other; it is not a recommendation. Information only, not investment advice.";

// ------------------------------------------------------------------ metric wording

/** Words for "higher" and "lower" on an axis, from its label (the spec's axis config). A label with no entry falls back to plain "higher / lower on …". */
export function metricCfg(label: string): MetricCfg {
  const l = label.toLowerCase();
  if (/p\/e|p\/b|ev\/|price to|price\/|p\/s|peg/.test(l) && !/growth/.test(l)) return { label, higher: "more expensive", lower: "cheaper" };
  if (/growth|cagr/.test(l)) return { label, higher: "faster growing", lower: "slower growing" };
  if (/roe|roce|roa|margin|return on|profitab/.test(l)) return { label, higher: "more profitable", lower: "less profitable" };
  if (/debt|leverage|gearing/.test(l)) return { label, higher: "more leveraged", lower: "less leveraged" };
  return { label, higher: `higher on ${label}`, lower: `lower on ${label}` };
}

// ------------------------------------------------------------------ statistics

const MINUS = "−";
const sorted = (v: number[]) => [...v].sort((a, b) => a - b);
export function quantile(s: number[], p: number): number {
  if (!s.length) return NaN;
  if (s.length === 1) return s[0];
  const h = (s.length - 1) * p, lo = Math.floor(h), hi = Math.min(lo + 1, s.length - 1);
  return s[lo] + (h - lo) * (s[hi] - s[lo]);
}
const median = (v: number[]) => quantile(sorted(v), 0.5);
const iqr = (v: number[]) => { const s = sorted(v); return s.length < 2 ? 0 : quantile(s, 0.75) - quantile(s, 0.25); };
/** Share of the values strictly below v, whole percent. */
export const percentileRank = (s: number[], v: number) => { let lo = 0; for (const a of s) if (a < v) lo++; return Math.round((lo / s.length) * 100); };
function skewness(v: number[]): number {
  const n = v.length; if (n < 3) return 0;
  const m = v.reduce((a, b) => a + b, 0) / n, sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / n);
  return sd === 0 ? 0 : v.reduce((a, b) => a + ((b - m) / sd) ** 3, 0) / n;
}
/** Theil-Sen line (median of pairwise slopes), on at most 2,000 points taken at an even stride, so it stays fast and repeatable. */
export function theilSen(pts: { x: number; y: number }[]): { slope: number; intercept: number } | null {
  const step = Math.max(1, Math.ceil(pts.length / 2000)), use = pts.filter((_, i) => i % step === 0);
  const sl: number[] = [];
  for (let i = 0; i < use.length; i++) for (let j = i + 1; j < use.length; j++) { const dx = use[j].x - use[i].x; if (dx !== 0) sl.push((use[j].y - use[i].y) / dx); }
  if (!sl.length) return null;
  const slope = median(sl);
  return { slope, intercept: median(use.map((p) => p.y - slope * p.x)) };
}

// ------------------------------------------------------------------ wording

const rho2 = (r: number) => (r < 0 ? MINUS : "") + Math.abs(r).toFixed(2);
const strengthOf = (a: number) => (a < 0.1 ? null : a < 0.3 ? "a weak" : a < 0.5 ? "a moderate" : "a strong");
const nf = (n: number) => n.toLocaleString("en-IN");
const lc = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
type Quad = "hh" | "hl" | "lh" | "ll";
const QUAD_SAY = (q: Quad, x: MetricCfg, y: MetricCfg) => ({
  hh: `It is ${x.higher} and ${y.higher} than the typical company.`,
  hl: `It is ${x.higher} but ${y.lower} than the typical company.`,
  lh: `It is ${x.lower} but ${y.higher} than the typical company.`,
  ll: `It is ${x.lower} and ${y.lower} than the typical company.`,
}[q]);
const QUAD_AREA = (q: Quad, x: MetricCfg, y: MetricCfg) => ({
  hh: `${x.higher} and ${y.higher}`, hl: `${x.higher} and ${y.lower}`, lh: `${x.lower} and ${y.higher}`, ll: `${x.lower} and ${y.lower}`,
}[q]);
const band = (pct: number) => (pct >= 75 ? "top quartile" : pct <= 25 ? "bottom quartile" : "mid-range");

export function generateInsight(inp: InsightInput): Insight {
  const { x, y, points, who } = inp;
  const n = points.length;
  const footer = `Based on ${inp.period ? inp.period + " data" : "the latest stored data"}, ${nf(n)} ${who}.`;
  const caveats: string[] = [];
  const empty = (cloud: string): Insight => ({ state: "empty", cloud, shape: null, companies: [], comparison: [], caveats, footer });

  // selected companies that cannot be placed: only a caveat (never described with numbers)
  for (const c of inp.selected) if (c.x == null || c.y == null) caveats.push(`${c.name} is not plotted${c.why ? ": " + lc(c.why.replace(/[.\s]+$/, "")) + "." : "."}`);

  if (n < 3) return empty(`There are too few ${who} with both ${x.label} and ${y.label} to say anything.`);
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y), sx = sorted(xs), sy = sorted(ys);
  if (sx[0] === sx[n - 1]) return empty(`No variation in ${x.label}, so no relationship can be measured.`);
  if (sy[0] === sy[n - 1]) return empty(`No variation in ${y.label}, so no relationship can be measured.`);

  const rho = inp.rho, small = n < MIN_N, reliable = inp.p != null ? inp.p < 0.05 : true;
  const mx = quantile(sx, 0.5), my = quantile(sy, 0.5);

  // ---- 5.2 cloud sentence
  let cloud: string;
  let noRelation = false;
  if (rho == null) { cloud = `Across ${nf(n)} ${who}, the relationship between ${x.label} and ${y.label} could not be worked out.`; noRelation = true; }
  else if (small) { cloud = `Across ${nf(n)} ${who} there are too few points for a reliable pattern between ${x.label} and ${y.label} (rho = ${rho2(rho)}).`; noRelation = true; }
  else {
    const st = strengthOf(Math.abs(rho));
    if (!st) { cloud = `Across ${nf(n)} ${who}, ${x.label} and ${y.label} show no meaningful relationship (rho = ${rho2(rho)}).`; noRelation = true; }
    else {
      const dir = rho > 0 ? "positive" : "negative", tend = rho > 0 ? "higher" : "lower";
      cloud = reliable
        ? `Across ${nf(n)} ${who} there is ${st} ${dir} relationship (rho = ${rho2(rho)}): ${who} with higher ${x.label} tend to have ${tend} ${y.label}.`
        : `Across ${nf(n)} ${who} there may be ${st} ${dir} relationship (rho = ${rho2(rho)}), but it is not statistically reliable.`;
    }
  }

  // ---- 5.3 shape note: no linear pattern but uneven spread
  let shape: string | null = null;
  if (rho != null && Math.abs(rho) < 0.15 && !small) {
    const low = points.filter((p) => p.x < mx).map((p) => p.y), high = points.filter((p) => p.x >= mx).map((p) => p.y), ih = iqr(high);
    if (ih > 0 && low.length > 1 && high.length > 1) {
      const ratio = iqr(low) / ih;
      if (ratio > 2 || ratio < 0.5) shape = `There is no linear pattern, but ${y.label} varies much more among ${who} with ${ratio > 2 ? "lower" : "higher"} ${x.label}.`;
    }
  }

  // ---- 5.4 company blocks, 5.5 comparison
  const ts = theilSen(points), res = ts ? points.map((p) => p.y - (ts.intercept + ts.slope * p.x)) : null;
  const mad = res ? median(res.map((r) => Math.abs(r - median(res)))) : 0, resMed = res ? median(res) : 0;
  const placed = inp.selected.filter((c) => c.x != null && c.y != null).map((c) => {
    const px = percentileRank(sx, c.x as number), py = percentileRank(sy, c.y as number);
    const q: Quad = ((c.x as number) >= mx ? "h" : "l") + ((c.y as number) >= my ? "h" : "l") as Quad;
    return { c, px, py, q };
  });
  const companies = placed.map(({ c, px, py, q }) => {
    const parts = [`${c.name} has ${x.label} of ${inp.fx(c.x as number)} (${band(px)}, higher than ${px}% of ${who}) and ${y.label} of ${inp.fy(c.y as number)} (${band(py)}, higher than ${py}% of ${who}).`];
    const centre = px >= 40 && px <= 60 && py >= 40 && py <= 60;
    parts.push(centre ? "It sits close to the middle of the cloud on both measures." : QUAD_SAY(q, x, y));
    if (res && mad > 0 && !noRelation) {
      const z = ((c.y as number) - (ts!.intercept + ts!.slope * (c.x as number)) - resMed) / (1.4826 * mad);
      if (Math.abs(z) > 1) parts.push(`Relative to the overall trend, it sits ${z > 0 ? "above" : "below"} the line.`);
    }
    return parts.join(" ");
  });
  const comparison: string[] = [];
  for (let i = 0; i < placed.length && comparison.length < MAX_BLOCKS; i++) for (let j = i + 1; j < placed.length && comparison.length < MAX_BLOCKS; j++) {
    const a = placed[i], b = placed[j];
    comparison.push(a.q === b.q
      ? `${a.c.name} and ${b.c.name} sit in the same area of the chart (${QUAD_AREA(a.q, x, y)}).`
      : `${a.c.name} has ${a.px > b.px ? "higher" : a.px < b.px ? "lower" : "about the same"} ${x.label} than ${b.c.name} (percentile ${a.px} vs ${b.px}), while ${y.label} is ${a.py > b.py ? "higher" : a.py < b.py ? "lower" : "about the same"} (${a.py} vs ${b.py}).`);
  }

  // ---- 6 caveats
  if (rho != null && !small && Math.abs(rho) < 0.3) caveats.push("A weak correlation does not mean one measure drives the other.");
  if (n > 0 && inp.outside / n > 0.05) caveats.push(`Statistics include ${nf(inp.outside)} points outside the visible window.`);
  if (small) caveats.push(`Too few ${who} for a reliable pattern.`);
  for (const [m, v] of [[x, xs], [y, ys]] as [MetricCfg, number[]][]) if (Math.abs(skewness(v)) > 3) caveats.push(`${m.label} is heavily skewed by a few extreme values, so rank-based statistics are used.`);
  // base effect ("Growth looks large because the starting value was very small"): needs a per-metric floor from product, not yet set (spec section 12)

  return { state: "ok", cloud, shape, companies, comparison, caveats, footer };
}
