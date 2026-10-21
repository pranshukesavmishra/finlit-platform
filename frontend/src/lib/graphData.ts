// Graph Studio: the arithmetic behind the charts. Pure and tested. Nothing here invents a data point:
// windows cut, alignment pairs each date with the real reading on or just before it, and correlation uses only pairs where both exist.
import type { Pt, Kind, UnitId } from "./graphMetrics";

export type RangeId = "1Y" | "3Y" | "5Y" | "MAX";
export const RANGES: { id: RangeId; label: string; years: number }[] = [
  { id: "1Y", label: "1Y", years: 1 }, { id: "3Y", label: "3Y", years: 3 }, { id: "5Y", label: "5Y", years: 5 }, { id: "MAX", label: "Max", years: Infinity },
];
export const DAY = 86_400_000;
export const ms = (iso: string) => Date.parse(iso.length === 10 ? iso + "T00:00:00Z" : iso);

/** Keep the observations inside the window that ends at the series' own latest date. A few days of slack keep a year-end that falls just outside. */
export function windowPts(pts: Pt[], range: RangeId): Pt[] {
  const yrs = RANGES.find((r) => r.id === range)?.years ?? Infinity;
  if (!Number.isFinite(yrs) || !pts.length) return pts;
  const last = Math.max(...pts.filter((p) => p.v != null || p.o != null).map((p) => ms(p.t)), -Infinity);
  if (!Number.isFinite(last)) return pts;
  const from = last - yrs * 365.25 * DAY - 10 * DAY;
  return pts.filter((p) => ms(p.t) >= from);
}

// ------------------------------------------------------------------ correlation

export type Corr = { r: number | null; n: number; why?: string };
/** Pearson correlation over the pairs where both values exist. Needs at least 3 pairs and some spread in both series. */
export function pearson(xs: (number | null)[], ys: (number | null)[]): Corr {
  const a: number[] = [], b: number[] = [];
  const len = Math.min(xs.length, ys.length);
  for (let i = 0; i < len; i++) {
    const x = xs[i], y = ys[i];
    if (x != null && y != null && Number.isFinite(x) && Number.isFinite(y)) { a.push(x); b.push(y); }
  }
  const n = a.length;
  if (n < 3) return { r: null, n, why: n === 0 ? "No dates where both measures have a value." : `Only ${n} dates where both measures have a value; at least 3 are needed.` };
  const mx = a.reduce((s, v) => s + v, 0) / n, my = b.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = a[i] - mx, dy = b[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  if (sxx === 0 || syy === 0) return { r: null, n, why: "One of the measures does not change over these dates, so a correlation is not defined." };
  return { r: Math.max(-1, Math.min(1, sxy / Math.sqrt(sxx * syy))), n };
}

/** Straight line through the pairs (least squares), for the fit line on a scatter chart. */
export function fitLine(xs: number[], ys: number[]): { slope: number; intercept: number } | null {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  return { slope, intercept: my - slope * mx };
}

/** Words for |r|, used beside the number. */
export function strength(r: number): string {
  const a = Math.abs(r);
  const w = a >= 0.8 ? "strong" : a >= 0.5 ? "moderate" : a >= 0.3 ? "weak" : "very weak or none";
  return a < 0.3 ? w : `${w} ${r > 0 ? "positive" : "negative"}`;
}

export type Matrix = { r: (number | null)[][]; n: number[][] };
/** Pairwise Pearson matrix. Each pair uses only the dates where both columns have a value. */
export function corrMatrix(cols: (number | null)[][]): Matrix {
  const k = cols.length;
  const r = Array.from({ length: k }, () => Array<number | null>(k).fill(null)), n = Array.from({ length: k }, () => Array<number>(k).fill(0));
  for (let i = 0; i < k; i++) for (let j = i; j < k; j++) {
    const c = i === j ? { r: cols[i].filter((v) => v != null).length >= 3 ? 1 : null, n: cols[i].filter((v) => v != null).length } : pearson(cols[i], cols[j]);
    r[i][j] = r[j][i] = c.r; n[i][j] = n[j][i] = c.n;
  }
  return { r, n };
}

// ------------------------------------------------------------------ changes and rebasing

/** Change from one reading to the next. Amounts: percent change (not defined from a zero or negative base). Ratios: difference in their own unit. */
export function changes(vals: (number | null)[], kind: Kind): (number | null)[] {
  return vals.map((v, i) => {
    const p = i > 0 ? vals[i - 1] : null;
    if (v == null || p == null) return null;
    if (kind === "ratio") return v - p;
    return p > 0 ? ((v - p) / p) * 100 : null;
  });
}

/** Rebase so the first reading is 100. Not defined unless that first reading is above zero; returns null then. */
export function rebase(pts: Pt[]): Pt[] | null {
  const base = pts.find((p) => p.v != null);
  if (!base || (base.v as number) <= 0) return null;
  const b = base.v as number;
  return pts.map((p) => ({ ...p, v: p.v == null ? null : (p.v / b) * 100 }));
}

// ------------------------------------------------------------------ alignment

/** The last reading on or before `date`, no more than `tolDays` earlier. */
export function asOf(pts: Pt[], date: string, tolDays: number): Pt | null {
  const t = ms(date);
  let lo = 0, hi = pts.length - 1, at = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (ms(pts[mid].t) <= t) { at = mid; lo = mid + 1; } else hi = mid - 1; }
  if (at < 0) return null;
  return t - ms(pts[at].t) <= tolDays * DAY ? pts[at] : null;
}

/** The last reading in each calendar month. */
export function monthEnds(pts: Pt[]): Pt[] {
  const out: Pt[] = [];
  for (const p of pts) {
    if (p.v == null) continue;
    const key = p.t.slice(0, 7);
    if (out.length && out[out.length - 1].t.slice(0, 7) === key) out[out.length - 1] = p; else out.push(p);
  }
  return out;
}

export type AlignInput = { pts: Pt[]; grain: "price" | "periodic" };
export type Aligned = { dates: string[]; labels: string[]; cols: (number | null)[][]; maxGap: number };

/**
 * Put several series on one list of dates so they can be compared reading for reading.
 * Any statement series present: the dates are theirs (the dates every statement series shares, or the longest one's if they differ) and price-type series
 * give their last close on or before each period end. Price series only: month-end closes. Never forward-fills a statement figure onto daily dates.
 */
export function alignSeries(inputs: AlignInput[], basis: "annual" | "quarterly"): Aligned {
  const periodic = inputs.filter((i) => i.grain === "periodic");
  const tol = basis === "annual" ? 120 : 50;       // a company whose year ends in December still pairs with a March-year peer; the gap is reported
  let dates: string[], labels: string[];
  if (periodic.length) {
    const anchor = periodic.reduce((a, b) => (b.pts.filter((p) => p.v != null).length > a.pts.filter((p) => p.v != null).length ? b : a));
    const pts = anchor.pts.filter((p) => p.v != null);
    dates = pts.map((p) => p.t); labels = pts.map((p) => p.l ?? p.t);
  } else {
    const first = inputs[0] ? monthEnds(inputs[0].pts) : [];
    dates = first.map((p) => p.t); labels = first.map((p) => p.t.slice(0, 7));
  }
  let maxGap = 0;
  const cols = inputs.map((inp) => {
    const src = inp.grain === "price" && !periodic.length ? monthEnds(inp.pts) : inp.pts.filter((p) => p.v != null);
    return dates.map((d) => {
      const hit = asOf(src, d, inp.grain === "price" ? (periodic.length ? 7 : 31) : tol);
      if (!hit) return null;
      if (inp.grain === "periodic") maxGap = Math.max(maxGap, Math.round((ms(d) - ms(hit.t)) / DAY));
      return hit.v;
    });
  });
  return { dates, labels, cols, maxGap };
}

// ------------------------------------------------------------------ axes

/** Group units onto at most two axes. null when more than two different units are present. */
export function axisUnits(units: UnitId[]): UnitId[] | null {
  const u = [...new Set(units)];
  return u.length <= 2 ? u : null;
}

/** Plain "nice" tick positions covering [min, max]. */
export function ticks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) { const pad = Math.abs(min) || 1; min -= pad / 2; max += pad / 2; }
  const span = max - min;
  let step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = span / count / step;
  step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max + step * 1e-9; t += step) out.push(+t.toFixed(10));
  return out;
}

/** Domain with a little headroom; `zero` forces the baseline in (bars and areas must start at zero to be honest). */
export function domain(vals: number[], zero: boolean): [number, number] {
  if (!vals.length) return [0, 1];
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  if (lo === hi) { const pad = Math.abs(lo) || 1; lo -= pad / 2; hi += pad / 2; }
  const pad = (hi - lo) * 0.06;
  return [zero && lo === 0 ? 0 : lo - (lo < 0 || !zero ? pad : 0), zero && hi === 0 ? 0 : hi + pad];
}

// ------------------------------------------------------------------ export

/** One CSV cell. Text that could be read as a formula by a spreadsheet is stored as plain text. */
export function csvCell(v: string | number | null | undefined): string {
  if (v == null) return "";
  let s = String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = "'" + s;
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
export const csvRow = (cells: (string | number | null | undefined)[]) => cells.map(csvCell).join(",");
