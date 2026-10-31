/**
 * Plain-words reading of a scatter chart, built only from the chart's own numbers (no model, no network).
 * Pure: the same input always gives the same text. Describes how two measures moved together; never advice.
 */
import { fmtP, fmtR } from "./advanced";

export const ALPHA = 0.05;
/** Standard bands for |r|. */
export const BANDS: { max: number; word: string; range: string }[] = [
  { max: 0.1, word: "negligible", range: "under 0.1" },
  { max: 0.3, word: "weak", range: "0.1 to 0.3" },
  { max: 0.5, word: "moderate", range: "0.3 to 0.5" },
  { max: 0.7, word: "strong", range: "0.5 to 0.7" },
  { max: Infinity, word: "very strong", range: "0.7 or more" },
];
export const BANDS_TIP = `Size of |r|: ${BANDS.map((b) => `${b.range} ${b.word}`).join("; ")}. The sign only says whether the two measures rise together (+) or one rises as the other falls (−).`;
export const CLOSING = "Correlation is not causation. Describes how two measures moved together across companies; not a recommendation. Information only, not investment advice.";
export const CLOSING_SERIES = "Correlation is not causation. Describes how two measures moved together over time; not a recommendation. Information only, not investment advice.";
export const HOW_TO_READ = [
  "r (from −1 to +1) says how closely the dots follow a straight line: near 0 is a shapeless cloud, near ±1 is a tight line. Its sign is the direction.",
  "p asks: if the two measures were truly unrelated, how often would a sample this size look at least this lined-up? Below 0.05 is called statistically distinguishable from zero; it says nothing about how big or useful the link is.",
  "n is the number of points used. Small n makes r jumpy; a very large n can make a tiny r look significant.",
  "Companies are not independent (same sector, same market), and across about 130 charts roughly 1 in 20 will look significant by chance.",
];

export const bandOf = (r: number) => { const a = Math.abs(r); return BANDS.find((b) => a < b.max)!; };
const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
const nf = (n: number) => n.toLocaleString("en-IN");
const pct = (f: number) => `${Math.round(f * 100)}%`;

export type InfLine = { id: "p" | "agree" | "coverage" | "outliers" | "small" | "perfect" | "constant"; text: string; warn?: boolean };
export type Placement = { name: string; text: string };
export type Inference = { state: "empty" | "ok"; headline: string; lines: InfLine[]; placements: Placement[]; closing: string; howTo: string[] };

export type InfPoint = { x: number; y: number };
export type InfMarker = { name: string; x: number | null | undefined; y: number | null | undefined };
export type InfInput = {
  kind: "cross" | "history" | "tech" | "series";
  n: number | null | undefined;
  r: number | null | undefined; p?: number | null; rho?: number | null;
  xName: string; yName: string;
  /** Plural noun for the points: "companies", "financial years", "periods". */
  who?: string;
  lineDrawn?: boolean;
  /** Fitted straight line, only when drawn on linear axes: y = intercept + slope * x. */
  fit?: { slope: number; intercept: number } | null;
  left?: number | null; total?: number | null; leftReason?: string | null;
  /** Points outside the visible window while "show every point" is off. */
  outside?: number | null; allShown?: boolean;
  /** Companies/indices the user added, and the cloud they are compared with. */
  markers?: InfMarker[]; cloud?: InfPoint[];
};

export const EMPTY_TEXT = "Not enough points to say anything.";

/** Linear-interpolated quantile of a sorted array (p in 0..1). */
function quantile(sorted: number[], p: number): number {
  if (sorted.length === 1) return sorted[0];
  const h = (sorted.length - 1) * p, lo = Math.floor(h), hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}
/** Share of the cloud below v, ties counted as half (0..1). */
export function percentileRank(sorted: number[], v: number): number {
  if (!sorted.length) return NaN;
  let below = 0, eq = 0;
  for (const s of sorted) { if (s < v) below++; else if (s === v) eq++; }
  return (below + eq / 2) / sorted.length;
}
const sideOf = (f: number, name: string, who: string, tail: string) =>
  f >= 0.55 ? `a higher ${name} than ${pct(f)} of the ${who}${tail}` : f <= 0.45 ? `a lower ${name} than ${pct(1 - f)} of the ${who}${tail}` : `a ${name} close to the middle of the ${who}${tail}`;

/** Where one added company or index sits relative to the cloud; null when it has no usable position or the cloud is tiny. */
export function placeMarker(m: InfMarker, cloud: InfPoint[], inp: Pick<InfInput, "xName" | "yName" | "fit" | "lineDrawn" | "who">): string | null {
  if (!ok(m.x) || !ok(m.y) || cloud.length < 5) return null;
  const who = inp.who ?? "companies";
  const xs = cloud.map((p) => p.x).sort((a, b) => a - b), ys = cloud.map((p) => p.y).sort((a, b) => a - b);
  const fx = percentileRank(xs, m.x), fy = percentileRank(ys, m.y);
  let rel: string;
  if (inp.lineDrawn && inp.fit && ok(inp.fit.slope) && ok(inp.fit.intercept)) {
    const pred = inp.fit.intercept + inp.fit.slope * m.x;
    rel = m.y > pred ? "above" : m.y < pred ? "below" : "on";
    rel = ` Its ${inp.yName} is ${rel} the trend line.`;
  } else {
    // No line drawn: compare with the middle Y of the tenth of the cloud whose X is nearest in rank.
    const byX = [...cloud].sort((a, b) => a.x - b.x), k = Math.min(byX.length, Math.max(5, Math.ceil(byX.length / 10)));
    const at = Math.round(fx * (byX.length - 1)), lo = Math.max(0, Math.min(at - Math.floor(k / 2), byX.length - k));
    const med = quantile(byX.slice(lo, lo + k).map((p) => p.y).sort((a, b) => a - b), 0.5);
    const w = m.y > med ? "above" : m.y < med ? "below" : "equal to";
    rel = ` Its ${inp.yName} is ${w} the middle value among ${who} with a similar ${inp.xName}.`;
  }
  return `${m.name} has ${sideOf(fx, inp.xName, who, " shown")}, and ${sideOf(fy, inp.yName, who, "")}.${rel}`;
}

export function chartInference(inp: InfInput): Inference {
  const closing = inp.kind === "cross" ? CLOSING : CLOSING_SERIES;
  const n = ok(inp.n) ? inp.n : 0;
  if (n < 3) return { state: "empty", headline: EMPTY_TEXT, lines: [], placements: [], closing, howTo: HOW_TO_READ };
  const who = inp.who ?? "companies", x = inp.xName, y = inp.yName, lines: InfLine[] = [];
  const r = ok(inp.r) ? inp.r : null;

  // (1) headline: direction and strength
  let headline: string;
  if (r == null) {
    headline = `No correlation can be measured between ${x} and ${y} here: one of them takes the same value everywhere.`;
    lines.push({ id: "constant", text: "A measure that never changes has no direction to compare with." });
  } else {
    const R = fmtR(r), band = bandOf(r);
    if (Math.abs(r) >= 1 - 1e-9) {
      headline = `${x} and ${y} line up exactly (r = ${R}): every one of the ${nf(n)} ${who} sits on one straight line.`;
      lines.push({ id: "perfect", warn: true, text: "A perfect fit usually means one measure is computed from the other, or that there are too few points; it does not show two independent things agreeing." });
    } else if (band.word === "negligible") {
      headline = `Negligible relationship (r = ${R}): ${x} says almost nothing about ${y} across these ${who}.`;
    } else {
      headline = `A ${band.word} ${r > 0 ? "positive" : "negative"} relationship (r = ${R}): ${who} with a higher ${x} tended to have a ${r > 0 ? "higher" : "lower"} ${y}.`;
    }
  }

  // (2) is it distinguishable from zero
  const p = ok(inp.p) ? inp.p : null;
  if (r != null) {
    if (p == null) lines.push({ id: "p", text: "A p-value could not be worked out for this chart, so we cannot say whether this is distinguishable from zero." });
    else if (p < ALPHA) lines.push({ id: "p", text: `It is statistically distinguishable from zero (${p < 0.001 ? "p < 0.001" : `p = ${fmtP(p)}`}, below 0.05). Points are not independent (companies in a sector move together) and about 1 in 20 of the 130 charts would look significant by chance, so treat p as a rough guide. ${n >= 1000 ? "With this many points even a tiny r is significant; judge the size from r." : "It says nothing about size; judge that from r."}` });
    else lines.push({ id: "p", text: `It is not distinguishable from zero (p = ${fmtP(p)}, not below 0.05): a pattern this weak is common between unrelated measures at this sample size. That is not proof that no relationship exists.` });
  }

  // (3) Pearson against Spearman
  const rho = ok(inp.rho) ? inp.rho : null;
  if (r != null && rho != null) {
    const d = Math.abs(rho) - Math.abs(r);
    if (Math.sign(rho) !== Math.sign(r) && Math.abs(rho) >= 0.1 && Math.abs(r) >= 0.1) lines.push({ id: "agree", warn: true, text: `The two measures disagree on direction (Pearson r = ${fmtR(r)}, Spearman rho = ${fmtR(rho)}): the pattern depends on a few extreme points, so do not read a direction into it.` });
    else if (d >= 0.1) lines.push({ id: "agree", text: `The rank-based correlation (Spearman rho = ${fmtR(rho)}) is stronger than the linear one (r = ${fmtR(r)}): the relationship may be curved or driven by a few extreme points.` });
    else if (d <= -0.1) lines.push({ id: "agree", text: `The linear correlation (r = ${fmtR(r)}) is stronger than the rank-based one (Spearman rho = ${fmtR(rho)}): a few extreme points may be doing much of the work.` });
    else lines.push({ id: "agree", text: `The linear (r = ${fmtR(r)}) and rank-based (Spearman rho = ${fmtR(rho)}) measures agree.` });
  }

  // (4) sample size and coverage
  if (n < 30) lines.push({ id: "small", warn: true, text: `Small sample: only ${nf(n)} ${who}. One more or one fewer can move the result a lot.` });
  if (inp.kind === "cross" && ok(inp.left) && ok(inp.total) && inp.total > 0) {
    const used = Math.max(0, inp.total - inp.left), cov = used / inp.total;
    if (inp.left > 0) {
      const warn = cov < 0.5;
      lines.push({ id: "coverage", warn, text: `${nf(used)} of the ${nf(inp.total)} ${who} in the filters are used (${pct(cov)}); ${nf(inp.left)} are left out${inp.leftReason ? `, mainly because ${inp.leftReason}` : ""}.${warn ? " Under half are covered, so this describes the companies that have both figures, not the whole selection." : ""}` });
    } else lines.push({ id: "coverage", text: `All ${nf(inp.total)} ${who} in the filters are used.` });
  }

  // (5) points outside the drawn window
  if (ok(inp.outside) && inp.outside > 0 && !inp.allShown) {
    const one = inp.outside === 1;
    lines.push({ id: "outliers", text: `${nf(inp.outside)} extreme point${one ? " lies" : "s lie"} outside the drawn window (1st to 99th percentile). ${one ? "It is" : "They are"} still counted in the statistics; tick “Show every point” to see ${one ? "it" : "them"}.` });
  }

  // (6) where the added companies / indices sit
  const placements: Placement[] = [];
  for (const m of inp.markers ?? []) { const t = placeMarker(m, inp.cloud ?? [], inp); if (t) placements.push({ name: m.name, text: t }); }

  return { state: "ok", headline, lines, placements, closing, howTo: HOW_TO_READ };
}

/** Two-sided p-value for Pearson r with n pairs (Student t, n - 2 degrees of freedom); null when it cannot be worked out. */
export function pFromR(r: number | null | undefined, n: number): number | null {
  if (!ok(r) || n < 3) return null;
  if (Math.abs(r) >= 1) return 0;
  const df = n - 2, t = r * Math.sqrt(df / (1 - r * r));
  return incBeta(df / (df + t * t), df / 2, 0.5);
}
function lgamma(z: number): number {
  const c = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
  let y = z, tmp = z + 5.5; tmp -= (z + 0.5) * Math.log(tmp);
  let ser = 1.000000000190015; for (const cj of c) ser += cj / ++y;
  return -tmp + Math.log(2.5066282746310005 * ser / z);
}
function betaCf(x: number, a: number, b: number): number {
  const TINY = 1e-30;
  let c = 1, d = 1 - (a + b) * x / (a + 1); if (Math.abs(d) < TINY) d = TINY; d = 1 / d; let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m;
    let e = m * (b - m) * x / ((a + m2 - 1) * (a + m2));
    d = 1 + e * d; if (Math.abs(d) < TINY) d = TINY; c = 1 + e / c; if (Math.abs(c) < TINY) c = TINY; d = 1 / d; h *= d * c;
    e = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1));
    d = 1 + e * d; if (Math.abs(d) < TINY) d = TINY; c = 1 + e / c; if (Math.abs(c) < TINY) c = TINY; d = 1 / d;
    const del = d * c; h *= del; if (Math.abs(del - 1) < 3e-12) break;
  }
  return h;
}
function incBeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? bt * betaCf(x, a, b) / a : 1 - bt * betaCf(1 - x, b, a) / b;
}
