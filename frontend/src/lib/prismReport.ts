// Pure logic of the Prism report page (arcs, contributions, factor filters and sorting, threshold ticks, history series).
// Tested in prismReport.test.ts. Nothing here invents a number: every figure comes from the report or is a plain ratio of two reported figures.
import {
  isRated, partInfo, partShare, partsOf, score1, standing,
  type BenchmarkDetail, type PartKey, type PrismLabel, type PrismMetric, type PrismRating, type PrismReport,
} from "./prism";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Score bands of the model: the lowest score of each label. */
export const THRESHOLDS = [35, 50, 65, 80];
/** Tick positions (0-100) drawn on every score bar: the label thresholds. */
export const thresholdTicks = (): number[] => [...THRESHOLDS];
/** Points ticks on a factor's points bar: below 40 holds back, 70 and above supports (the reader view's rule). */
export const POINT_TICKS = [40, 70];

/** One colour variable per part; a part the model adds later gets a spare hue, never a clash with the known four. */
const PART_VAR: Record<string, string> = { fundamental: "--pzr-c1", valuation: "--pzr-c2", quality: "--pzr-c3", risk: "--pzr-c4", technical: "--pzr-c5" };
export const partVar = (k: PartKey, index = 0) => `var(${PART_VAR[k] ?? `--pzr-c${5 + (index % 3)}`})`;

export type ArcSegment = { key: PartKey; weight: number; start: number; span: number; fill: number; score: number | null };
/** The prism ring: one arc per part, its length proportional to its weight (fractions of the circle), filled to its own score.
 *  Withheld scores (NOT RATED) give empty fills. `gap` is the fraction of the circle left between arcs. */
export function arcSegments(rating: Pick<PrismRating, "status" | "parts" | "partWeights">, gap = 0.012): ArcSegment[] {
  const keys = partsOf(rating).filter((k) => (rating.partWeights?.[k] ?? 0) > 0);
  const total = keys.reduce((s, k) => s + rating.partWeights[k], 0) || 1;
  const rated = isRated(rating);
  let at = 0;
  return keys.map((key) => {
    const weight = rating.partWeights[key] / total, score = rated ? rating.parts?.[key] ?? null : null;
    const span = Math.max(0, weight - gap);
    const seg = { key, weight, start: at + gap / 2, span, score, fill: score == null ? 0 : (span * Math.max(0, Math.min(100, score))) / 100 };
    at += weight;
    return seg;
  });
}

export type Contribution = { key: PartKey; weight: number; score: number | null; points: number; max: number; lost: number; capLost: number };
/** What each part adds to the overall score (weight x part score) and how much of its share was not earned. They add up to the final
 *  score. Returns [] when the company is not rated (category scores are withheld). Cap reductions already sit inside the part scores. */
export function contributions(rating: Pick<PrismRating, "status" | "parts" | "partWeights" | "adjustments">): Contribution[] {
  if (!isRated(rating)) return [];
  return partsOf(rating).filter((k) => (rating.partWeights?.[k] ?? 0) > 0).map((key) => {
    const weight = rating.partWeights[key], score = rating.parts?.[key] ?? null;
    const points = score == null ? 0 : weight * score, max = weight * 100;
    const capLost = Math.max(0, (rating.adjustments || []).filter((a) => a.part === key).reduce((s, a) => s + (a.pointsLost ?? 0), 0));
    return { key, weight, score, points, max, lost: Math.max(0, max - points), capLost };
  });
}
export const contributionTotal = (rows: Contribution[]) => rows.reduce((s, r) => s + r.points, 0);
/** Honest sentences for the loss and valuation caps; empty when none was applied. */
export function capNotes(rating: Pick<PrismRating, "lossCapped" | "valuationCapped" | "capPointsLost" | "loss">): string[] {
  const out: string[] = [];
  if (rating.lossCapped) {
    const cap = rating.loss?.cap, raw = rating.loss?.rawFundamental;
    out.push(`Loss rule: the Fundamentals score is limited to ${cap == null ? "a ceiling" : score1(cap)}${raw != null ? ` (it was ${score1(raw)} before the limit)` : ""} because of recent losses.`);
  }
  if (rating.valuationCapped) out.push("Valuation rule: the Valuation score is limited to 60 because Fundamentals or Quality is below 35.");
  const lost = rating.capPointsLost ?? 0;
  if (lost > 0) out.push(`Together the limits took ${score1(lost)} points off the overall score; the part scores shown already include this.`);
  return out;
}

export type FactorFilter = "all" | "strengths" | "concerns" | "estimated";
export type FactorSort = "model" | "high" | "low";
export const FILTER_WORD: Record<FactorFilter, string> = { all: "All factors", strengths: "Strengths", concerns: "Concerns", estimated: "Estimated or missing" };
/** The word for a factor's input state, as the model defines it (A actual, Z loss rule, S substituted, F estimated, L not supplied, N not applicable). */
export const BADGE_WORD: Record<PrismMetric["status"], string> = { A: "Actual", Z: "Actual, loss rule", S: "Substituted", F: "Estimated", N: "Not applicable", L: "Not available" };
export function matchesFilter(row: Pick<PrismMetric, "status" | "points">, f: FactorFilter): boolean {
  if (f === "all") return true;
  if (f === "estimated") return row.status === "F" || row.status === "L";
  const s = standing(row);
  return f === "strengths" ? s === "pros" : s === "cons";
}
export const filterFactors = <T extends Pick<PrismMetric, "status" | "points">>(rows: T[], f: FactorFilter): T[] => rows.filter((r) => matchesFilter(r, f));
/** Sort by points; factors without points always go last. Stable: ties keep the model's order. */
export function sortFactors<T extends Pick<PrismMetric, "points">>(rows: T[], how: FactorSort): T[] {
  if (how === "model") return rows;
  const dir = how === "high" ? -1 : 1;
  return rows.map((r, i) => ({ r, i })).sort((a, b) => {
    const x = a.r.points, y = b.r.points;
    if (x == null && y == null) return a.i - b.i;
    if (x == null) return 1;
    if (y == null) return -1;
    return x === y ? a.i - b.i : (x - y) * dir;
  }).map((o) => o.r);
}

export type ValueBar = { pos: number; red: number | null; green: number | null };
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
/** Where a factor's value sits between its 0-point value (left) and its 100-point value (right), with the red and green boundaries as
 *  ticks. Null when the model gave no bounds (streaks, trading value) or there is no real value. Works for lower-is-better factors too. */
export function valueBar(row: Pick<PrismMetric, "value" | "worst" | "best" | "redBoundary" | "greenBoundary" | "status">): ValueBar | null {
  const { value, worst, best } = row;
  if (value == null || worst == null || best == null || worst === best || row.status === "N" || row.status === "L" || row.status === "F") return null;
  const at = (v: number) => clamp01((v - worst) / (best - worst));
  return { pos: at(value), red: row.redBoundary == null ? null : at(row.redBoundary), green: row.greenBoundary == null ? null : at(row.greenBoundary) };
}

/** Top strength and biggest drag of a part. Only factors with a real or substituted value count: estimates never appear as a strength or drag. */
export function topFactors(rows: PrismMetric[]): { strength: PrismMetric | null; drag: PrismMetric | null } {
  const real = rows.filter((r) => (r.status === "A" || r.status === "S" || r.status === "Z") && r.points != null);
  const strength = real.filter((r) => r.points! >= 70).sort((a, b) => b.points! - a.points! || (b.pointsEarned ?? 0) - (a.pointsEarned ?? 0))[0] ?? null;
  const lost = (r: PrismMetric) => r.pointsLost ?? ((100 - r.points!) * (r.share ?? 0));
  const drag = real.filter((r) => r.points! < 70).sort((a, b) => lost(b) - lost(a))[0] ?? null;
  return { strength, drag };
}

export const bandLabel = (score: number | null | undefined): PrismLabel =>
  score == null ? "NOT RATED" : score >= 80 ? "STRONG" : score >= 65 ? "HEALTHY" : score >= 50 ? "AVERAGE" : score >= 35 ? "WEAK" : "POOR";

/** Whole days from a data date to the calculation; null when either is missing. */
export function daysBefore(asOf: string | null | undefined, calculated: string): number | null {
  if (!asOf) return null;
  const a = Date.parse(asOf), b = Date.parse(calculated);
  return Number.isNaN(a) || Number.isNaN(b) ? null : Math.max(0, Math.round((b - a) / 86_400_000));
}
export const ageWords = (d: number | null) => (d == null ? "Date unavailable" : d === 0 ? "Same day as the calculation" : `${d} day${d === 1 ? "" : "s"} before the calculation`);

/* ---- financial history series */
export type Series = { period: string; value: number | null }[];
/** "2023-03", "Mar 2023" and "2023" as a month number; null when no year is found. */
export function monthIndex(period: string): number | null {
  const iso = period.match(/^(\d{4})-(\d{2})/);
  if (iso) return Number(iso[1]) * 12 + Number(iso[2]) - 1;
  const named = period.match(/^([A-Za-z]{3})\w*\s+(\d{4})/);
  if (named) { const m = MONTHS.findIndex((x) => x.toLowerCase() === named[1].toLowerCase()); return m >= 0 ? Number(named[2]) * 12 + m : null; }
  const y = period.match(/^(\d{4})$/);
  return y ? Number(y[1]) * 12 : null;
}
/** Growth against the same period one year earlier, in %. Null where the period or its comparison is missing, or the comparison is not positive.
 *  Annual series are one year apart, so the comparison is the previous year; quarterly series compare with the same quarter a year before. */
export function yoy(series: Series, stepMonths = 12): (number | null)[] {
  const byIdx = new Map<number, number | null>();
  series.forEach((p) => { const i = monthIndex(p.period); if (i != null) byIdx.set(i, p.value); });
  return series.map((p) => {
    const i = monthIndex(p.period);
    if (i == null || p.value == null) return null;
    const prev = byIdx.get(i - stepMonths);
    return prev == null || prev <= 0 ? null : ((p.value - prev) / prev) * 100;
  });
}
/** a / b in %, null when either is missing or b is not positive. Used for margins and returns on the reported numbers. */
export const ratioPct = (a: number | null | undefined, b: number | null | undefined): number | null => (a == null || b == null || b <= 0 ? null : (a / b) * 100);
export const periodLabel = (p: string) => { const i = p.match(/^(\d{4})-(\d{2})$/); return i ? `${MONTHS[Number(i[2]) - 1]} ${i[1].slice(2)}` : p; };

export type PeerRow = { key: "pe" | "pb" | "ev_ebitda"; label: string; company: number | null; benchmark: number | null; own: number | null; detail?: BenchmarkDetail };
/** Valuation multiples against the benchmark, from the report's latest ratios and its benchmark block. */
export function peerRows(report: Pick<PrismReport, "financialHistory" | "benchmark">): PeerRow[] {
  const latest = new Map((report.financialHistory?.latest || []).map((r) => [r.key, r.value]));
  const bm = report.benchmark?.metrics || {};
  return ([["pe", "P/E"], ["pb", "P/B"], ["ev_ebitda", "EV/EBITDA"]] as const).map(([key, label]) => {
    const detail = bm[`industry_median_${key}`];
    return { key, label, company: latest.get(key) ?? null, benchmark: detail?.value ?? latest.get(`industry_median_${key}`) ?? null, own: latest.get(`own_5y_median_${key}`) ?? null, detail };
  }).filter((r) => r.company != null || r.benchmark != null);
}

/** Plain-words part weights and label rules for the "how this is calculated" panel. */
export function howRules(rating: Pick<PrismRating, "partWeights" | "parts">): string[] {
  const w = partsOf(rating).map((k) => `${partInfo(k).name} ${partShare(rating.partWeights, k)}%`).join(", ");
  return [
    `The overall score is a weighted mean of the part scores: ${w}.`,
    "Each part scores its factors from 0 to 100 against ranges set for the company's industry group, and averages them by weight.",
    "Labels: 80 and above Strong, 65 to 79 Healthy, 50 to 64 Average, 35 to 49 Weak, below 35 Poor.",
    "Not rated: less than half of the inputs are available, or there is too little income history. No score and no category scores are shown.",
    "Provisional: under 80% of inputs, or fewer than six comparable quarters. The label is then capped at Healthy.",
    "A factor with no value is estimated from a group figure or left out, and is always marked. Estimates are never shown as strengths or concerns.",
    "A recent loss limits the Fundamentals score, and weak Fundamentals or Quality limit Valuation to 60. Any limit that applied is listed under the score.",
  ];
}
