// FinLit Prism: the Gold plan's advanced financial-health rating (engine 3.6.9, merged from Yusra-Khan532/financial-portfolio).
// The research API (/api/prism/*) checks the plan, keeps the signed snapshot and serves the PDF; the browser only ever sees a PrismReport.
// Shapes follow site-api/backend/premium_engine.py (rating), premium_presentation.py (review) and premium_completeness.py (completeness).
// Contract: docs/prism/CONTRACT.md.
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE, ApiError, apiGet, apiSend, apiUrl, errorBody } from "./api";
import { MINUS, nf } from "./format";

export const PRISM_NAME = "FinLit Prism";
/** On every Prism screen. Never "buy", "sell", "avoid" or "target" anywhere near the rating. */
export const PRISM_NOTE = "Describes the company's financial health from its filings and prices; not a recommendation.";

/* ------------------------------------------------------------------ types */
export type Statement = "consolidated" | "standalone";
export type PrismLabel = "STRONG" | "HEALTHY" | "AVERAGE" | "WEAK" | "POOR" | "NOT RATED";
export type PrismStatusWord = "RATED" | "PROVISIONAL" | "NOT RATED";
/** The four parts today; a part the model adds later (e.g. "technical") arrives in rating.parts / partWeights and is rendered from data. */
export type PartKey = string;
export type ModelGroup = "LIGHT" | "MFG" | "HEAVY" | "UTILITY" | "REALTY" | "BANK" | "NBFC" | "INSURANCE";
/** A actual · Z negative/loss rule · S substituted benchmark · F filled (group estimate) · N not applicable · L not supplied (excluded). */
export type FactorState = "A" | "Z" | "S" | "F" | "N" | "L";
export type FactorUnit = "%" | "pp" | "quarters" | "Cr" | "x";

/** One scored factor (premium_engine.score_company rows). `details` holds the comparison periods/values, CAGR years and streak counts. */
export type PrismMetric = {
  part: PartKey; metric: string; label: string; value: number | null; unit: FactorUnit; points: number | null;
  status: FactorState; statusLabel: string; weight: number; share: number;
  details: {
    basis?: string; note?: string | null; current?: number | null; previous?: number | null; years?: number; availableYears?: number;
    good?: number; slips?: number; judged?: number; medianYoY?: number | null; lossFill?: boolean; latestLoss?: boolean;
    operatingLoss?: boolean; opMarginNow?: number; growthUsed?: number; [k: string]: unknown;
  };
  fallbackFor: string | null; worst: number | null; best: number | null; redBoundary: number | null; greenBoundary: number | null;
  severity?: "GREEN" | "AMBER" | "RED" | "NO DATA" | "NOT APPLICABLE"; pointsEarned?: number; pointsLost?: number;
};
export type PrismLoss = {
  ttmProfit: number | null; ttmSales: number | null; basis: string | null; lossNow: boolean; latestYearLoss: boolean;
  lossYears3: number; years3: number; lossYears5: number; years5: number; netMarginPct: number | null;
  tier: string | null; cap: number | null; rawFundamental: number | null;
};
export type PrismRating = {
  modelVersion: string; baselineVersion: string; fillVersion: string; group: ModelGroup | string;
  final: number | null; label: PrismLabel; status: PrismStatusWord;
  /** Internal category scores; they can exist for NOT RATED, which never shows them. */
  parts: Record<PartKey, number | null>; partWeights: Record<PartKey, number>; coverage: Record<PartKey, number>;
  /** Weighted overall coverage, 0-1. Completeness of the inputs, not a probability. */
  confidence: number; judgedQuarters: number; dataIntegrityStatus: "PASS" | "REVIEW REQUIRED";
  metrics: PrismMetric[]; loss?: PrismLoss; lossCapped?: boolean; valuationCapped?: boolean;
  adjustments?: { metric: string; part: PartKey; rawScore: number; cap: number; pointsLost?: number }[]; capPointsLost?: number;
  alerts?: string[]; headline?: string;
};
export type ReviewItem = { metric: string; label: string; valueText: string; summary: string; comparisonText?: string };
export type ReviewPart = {
  key: PartKey; name: string; score: number | null; notes: string[];
  pros: ReviewItem[]; cons: ReviewItem[]; mixed: ReviewItem[]; unavailable: ReviewItem[]; notApplicable?: ReviewItem[];
};
export type CompletenessItem = {
  metric: string; category: string; label: string; kind: "missing" | "limitedHistory"; missingInputs: string[]; reason: string; treatment: string;
};
export type Completeness = { complete: boolean; missingFactorCount: number; limitedHistoryCount: number; items: CompletenessItem[] };
/** Reader view (premium_presentation.build_report_review). `completeness` is missing on reports stored before it existed. */
export type PrismReview = { parts: ReviewPart[]; notes: string[]; completeness?: Completeness };
export type PrismInputMeta = {
  statementType?: Statement; requestedStatementType?: Statement | null; assetQualityStatementType?: string | null; groupDefaulted?: boolean;
  quarterlyAsOf?: string | null; annualAsOf?: string | null; balanceAsOf?: string | null; ownershipAsOf?: string | null; priceAsOf?: string | null;
  chronology?: { quarterly: string[]; annual: string[] }; [k: string]: unknown;
};
export type BenchmarkDetail = {
  value: number | null; provider: string; scope: string; method: string; positiveCount?: number; observedCount?: number; universeCount?: number;
  partial?: boolean; statementBasis?: string; asOf?: string | null; retrievedAt?: string;
};
export type PrismBenchmark = {
  source?: string; asOf?: string; universeCount?: number; note?: string; policyVersion?: string;
  metrics?: Record<string, BenchmarkDetail>; reportedObservations?: { key: string; value: number; provider: string; scope?: string }[]; [k: string]: unknown;
};
export type Trend = { period: string; revenue: number | null; profit: number | null; eps: number | null };
/** Quarterly and annual tables and key ratios, copied by the research API from the engine trace (PrismReport.financialHistory). Oldest to newest. */
export type PrismHistory = {
  quarterly: { period: string; sales: number | null; profit: number | null; ebitda: number | null; eps: number | null }[];
  annual: { period: string; sales: number | null; profit: number | null; cashFlow: number | null; netWorth: number | null }[];
  latest: { key: string; label: string; value: number | null; unit: string }[];
};
export type PrismReport = {
  id: string; createdAt: string; completedAt: string; statementType: Statement; state?: string;
  company: { symbol: string; name: string; industry?: string | null; sector?: string | null; description?: string | null };
  rating: PrismRating; inputMeta: PrismInputMeta; warnings: string[]; sources: unknown[]; trends: Trend[];
  benchmark: PrismBenchmark; review?: PrismReview; financialHistory?: PrismHistory;
  /** True when served from storage instead of a fresh calculation. */
  cached: boolean;
  /** When the PDF of this calculation stops being downloadable (the signed snapshot lives 30 minutes); null once it has. */
  pdfAvailableUntil: string | null;
};
export type PrismServiceStatus = { name: string; available: boolean; reason: string | null; modelVersion: string | null };

/* ------------------------------------------------------------------ words and tones (status in words, never by colour alone) */
export const KNOWN_PARTS: PartKey[] = ["fundamental", "valuation", "quality", "risk"];
const PART_TEXT: Record<string, { name: string; what: string }> = {
  fundamental: { name: "Fundamentals", what: "Business performance: how steadily revenue and profit grow." },
  valuation: { name: "Valuation", what: "The share price against earnings, book value and the company's own history." },
  quality: { name: "Quality", what: "Financial strength: borrowing, interest cover, returns and cash backing for profit." },
  risk: { name: "Risk", what: "Market risk: price swings, the largest fall, trading activity and pledged shares. A higher score means lower risk." },
  technical: { name: "Technical", what: "Price trend and momentum signals." },
};
const titleCase = (k: string) => k.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());
/** Name and one-line meaning of a part; an unknown part falls back to its key so it still shows. */
export const partInfo = (k: PartKey) => PART_TEXT[k] ?? { name: titleCase(k), what: "" };
/** The parts to show, from the data: every key in partWeights/parts (known ones first, in their usual order), nothing invented. */
export const partsOf = (r: Pick<PrismRating, "parts" | "partWeights">): PartKey[] => {
  const keys = [...new Set([...Object.keys(r.partWeights || {}), ...Object.keys(r.parts || {})])];
  return [...KNOWN_PARTS.filter((k) => keys.includes(k)), ...keys.filter((k) => !KNOWN_PARTS.includes(k))];
};
export const LABEL_WORD: Record<PrismLabel, string> = { STRONG: "Strong", HEALTHY: "Healthy", AVERAGE: "Average", WEAK: "Weak", POOR: "Poor", "NOT RATED": "Not rated" };
export type Tone = "strong" | "healthy" | "average" | "weak" | "poor" | "none";
const LABEL_TONE: Record<PrismLabel, Tone> = { STRONG: "strong", HEALTHY: "healthy", AVERAGE: "average", WEAK: "weak", POOR: "poor", "NOT RATED": "none" };
/** A label in words plus its colour token (defined in prism.css for both themes). */
export const labelTone = (label: PrismLabel) => { const tone = LABEL_TONE[label] ?? "none"; return { word: LABEL_WORD[label] ?? label, tone, token: `--pz-${tone}` }; };
/** The same bands as the engine (RATING_BANDS), for a category score. */
export const scoreTone = (score: number | null | undefined): Tone =>
  score == null ? "none" : score >= 80 ? "strong" : score >= 65 ? "healthy" : score >= 50 ? "average" : score >= 35 ? "weak" : "poor";
export const STATUS_WORD: Record<PrismStatusWord, string> = { RATED: "Rated", PROVISIONAL: "Provisional", "NOT RATED": "Not rated" };
export const STATUS_TEXT: Record<PrismStatusWord, string> = {
  RATED: "Enough verified history and coverage for a full rating.",
  PROVISIONAL: "The financial history or data coverage is limited, so the label is capped at Healthy.",
  "NOT RATED": "There is not enough verified information for an overall rating, so no category scores are shown.",
};
export const STATE_WORD: Record<FactorState, string> = {
  A: "Reported or calculated", Z: "Loss rule applied", S: "Industry benchmark in place of own history",
  F: "Estimated (group estimate)", N: "Not applicable", L: "Not reported, left out of the score",
};
export type Standing = "pros" | "cons" | "mixed" | "unavailable" | "notApplicable";
export const STANDING_WORD: Record<Standing, string> = { pros: "Supports", cons: "Holds back", mixed: "Mixed", unavailable: "Not available", notApplicable: "Not applicable" };
/** Where a factor sits in the reader view: the same thresholds as premium_presentation (>= 70 supports, < 40 holds back). */
export function standing(row: Pick<PrismMetric, "status" | "points">): Standing {
  if (row.status === "N") return "notApplicable";
  if (row.status === "F" || row.status === "L" || row.points == null) return "unavailable";
  return row.points >= 70 ? "pros" : row.points < 40 ? "cons" : "mixed";
}
export const isRated = (r: Pick<PrismRating, "status">) => r.status !== "NOT RATED";
export const incomeWord = (group: string) => (group === "BANK" || group === "NBFC" ? "Net interest income" : group === "INSURANCE" ? "Net premium income" : "Revenue");
export const statementWord = (s?: string | null) => (s === "standalone" ? "Standalone" : "Consolidated");
/** "counts for 40% of the overall score" */
export const partShare = (weights: Record<PartKey, number> | undefined, key: PartKey) => Math.round((weights?.[key] ?? 0) * 100);
export const score1 = (v: number | null | undefined) => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, 1));
export const pctWhole = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** A factor's value with its unit, in the site's style (real minus, ×, ₹ Cr). */
export function factorValue(row: Pick<PrismMetric, "value" | "unit">): string {
  const v = row.value;
  if (v == null) return "—";
  const n = (d = 2) => (v < 0 ? MINUS : "") + nf(v, d);
  switch (row.unit) {
    case "%": return n() + "%";
    case "pp": return n() + " pts";
    case "quarters": return `${nf(v, 0)} of 10 quarters`;
    case "Cr": return "₹" + n() + " Cr";
    default: return n() + "×";
  }
}

const crore = (v: number | null | undefined) => (v == null ? "—" : "₹" + (v < 0 ? MINUS : "") + nf(v, Math.abs(v) >= 100 ? 0 : 2) + " Cr");
/** Plain-language comparison behind a factor, from the engine's details; null when there is nothing to add. */
export function factorDetail(row: PrismMetric, group: string): string | null {
  const d = row.details || {};
  const income = row.metric.startsWith("SALES") ? incomeWord(group).toLowerCase() : "net profit";
  if (row.metric.endsWith("_STREAK") && d.judged != null) {
    if (!d.judged) return "No comparable quarters yet.";
    return `${d.good ?? 0} growth quarters${d.slips ? ` and ${d.slips} forgiven slip${d.slips === 1 ? "" : "s"}` : ""} across ${d.judged} of 10 comparable quarters.`;
  }
  if (/_GROWTH$/.test(row.metric) && ("current" in d || "basis" in d) && (row.metric.startsWith("SALES") || row.metric.startsWith("PROFIT"))) {
    if (d.current == null || d.previous == null) return d.basis && d.basis !== "Insufficient history" ? `${d.basis}: a comparison period is missing.` : "Not enough history for a comparison.";
    return `${d.basis}: ${income} ${crore(d.current)} against ${crore(d.previous)}.`;
  }
  if (row.metric.endsWith("_CAGR")) {
    if (d.years) return `${d.years}-year period: ${income} from ${crore(d.previous)} to ${crore(d.current)}.`;
    return "Needs at least two consecutive annual results ending in the latest financial year.";
  }
  if (row.metric === "PEG" && d.growthUsed != null) return `Profit growth used: ${nf(d.growthUsed, 1)}% a year (capped at 40%).`;
  if (d.operatingLoss && d.opMarginNow != null) return `The current operating margin is ${(d.opMarginNow < 0 ? MINUS : "") + nf(d.opMarginNow, 2)}%.`;
  const note = typeof d.note === "string" ? d.note : null;
  return note && note !== "Core group" ? note.replace(/\.?$/, ".") : null;
}

/* ------------------------------------------------------------------ the review (port of upstream lib/premiumReportReview.js) */
/** The report's own reader view. A report stored before review existed is still readable: factors are grouped here without
 *  treating estimated or excluded inputs as company facts, and the page asks for a recalculation for the full commentary. */
export function prismReview(report: Pick<PrismReport, "review" | "rating">): PrismReview & { legacy?: boolean } {
  if (report.review) return report.review;
  const rated = isRated(report.rating);
  const parts = partsOf(report.rating).map((key): ReviewPart => {
    const part: ReviewPart = { key, name: key[0].toUpperCase() + key.slice(1), score: rated ? report.rating.parts[key] : null, notes: [], pros: [], cons: [], mixed: [], unavailable: [] };
    report.rating.metrics.filter((row) => row.part === key && row.status !== "N").forEach((row) => {
      const missing = row.status === "F" || row.status === "L" || row.points == null;
      const bucket = missing ? "unavailable" : row.points! >= 70 ? "pros" : row.points! < 40 ? "cons" : "mixed";
      part[bucket].push({
        metric: row.metric, label: row.label,
        valueText: row.value == null || missing ? "Not available" : `${Number(row.value).toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${row.unit || ""}`,
        summary: missing ? (row.status === "F" ? "Not reported; an estimate is used in the assessment." : "Not reported; not assessed.") : row.status === "S" ? "Industry data is used because company history is unavailable." : "",
      });
    });
    return part;
  });
  return { parts, notes: ["Recalculate this report for the latest factor commentary and review notes."], legacy: true };
}

/** The reader item for one factor, if the review has it (to borrow its comparison text). */
export const reviewItem = (review: PrismReview, part: PartKey, metric: string): ReviewItem | undefined => {
  const p = review.parts.find((x) => x.key === part);
  return p && [...p.pros, ...p.cons, ...p.mixed, ...p.unavailable, ...(p.notApplicable || [])].find((i) => i.metric === metric);
};

/* ------------------------------------------------------------------ growth maths (port of upstream lib/fundamentalGrowth.js) */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const toNum = (v: unknown): number | null => (v === null || v === undefined || v === "" || typeof v === "boolean" || !Number.isFinite(Number(v)) ? null : Number(v));
function indexOfPeriod(label: unknown, period: "yearly" | "quarterly"): number | null {
  const text = String(label || "");
  const year = text.match(/\b(19\d{2}|20\d{2})\b/);
  if (!year || /TTM|YTD/i.test(text)) return null;
  if (period === "yearly") return Number(year[1]);
  const month = MONTHS.findIndex((name) => new RegExp(`^${name}\\b`, "i").test(text));
  if (month >= 0) return Number(year[1]) * 12 + month;
  const quarter = text.match(/^Q([1-4])\s/);
  return quarter ? Number(year[1]) * 12 + Number(quarter[1]) * 3 - 1 : null;
}
export type GrowthKey = "revenue" | "profit" | "eps";
export const GROWTH_METRICS: { key: GrowthKey; label: string; aliases: string[] }[] = [
  { key: "revenue", label: "Revenue growth", aliases: ["revenue"] },
  { key: "profit", label: "Net profit growth", aliases: ["netprofit"] },
  { key: "eps", label: "EPS growth", aliases: ["eps", "basicreinr", "basiceps", "dilutedreinr", "dilutedeps"] },
];
export type HistoryRow = { category: string; history?: { period: string; value: unknown }[] };
export type GrowthDetail = { current: number | null; previous: number | null; comparison: string | null; reason: string | null };
export type GrowthPoint = { period: string } & Partial<Record<GrowthKey, number | null>> & Partial<Record<`${GrowthKey}Detail`, GrowthDetail>>;
const keyOf = (row: HistoryRow) => String(row.category || "").toLowerCase().replace(/[^a-z0-9]/g, "");

/** Growth = (current − comparison) ÷ comparison × 100 against the exact previous year (or quarter). Gaps stay gaps; a missing,
 *  zero or negative comparison is not meaningful (null) with the reason kept. Up to six visible years (24 quarters). */
export function buildFundamentalGrowth(rows: HistoryRow[] = [], period: "yearly" | "quarterly" = "yearly", basis: "yoy" | "qoq" = "yoy"): GrowthPoint[] {
  const series = GROWTH_METRICS.map((metric) => {
    const row = metric.aliases.map((alias) => rows.find((item) => keyOf(item) === alias && item.history?.length)).find(Boolean);
    const values = new Map<number, { period: string; value: number | null }>();
    (row?.history || []).forEach((point) => { const index = indexOfPeriod(point.period, period); if (index !== null) values.set(index, { period: point.period, value: toNum(point.value) }); });
    return { ...metric, values };
  });
  const indices = series.flatMap((metric) => [...metric.values.keys()]);
  if (!indices.length) return [];
  const step = period === "yearly" ? 1 : 3;
  const lag = period === "yearly" ? 1 : basis === "qoq" ? 3 : 12;
  const end = Math.max(...indices);
  const start = Math.max(Math.min(...indices), end - step * (period === "yearly" ? 5 : 23));
  const result: GrowthPoint[] = [];
  for (let index = start; index <= end; index += step) {
    const fallback = period === "yearly" ? String(index) : `${MONTHS[index % 12]} ${Math.floor(index / 12)}`;
    const row: GrowthPoint = { period: series.map((metric) => metric.values.get(index)?.period).find(Boolean) || fallback };
    series.forEach((metric) => {
      const current = metric.values.get(index)?.value ?? null;
      const previousPoint = metric.values.get(index - lag);
      const previous = previousPoint?.value ?? null;
      const reason = current === null ? "Reported value unavailable" : previous === null ? "Matching comparison period unavailable" : previous <= 0 ? "Zero or negative comparison value" : null;
      row[metric.key] = reason ? null : ((current! - previous!) / previous!) * 100;
      row[`${metric.key}Detail`] = { current, previous, comparison: previousPoint?.period || null, reason };
    });
    result.push(row);
  }
  return result;
}
/** The report's annual trends in the shape buildFundamentalGrowth reads. */
export const trendRows = (trends: Trend[]): HistoryRow[] => [
  { category: "revenue", history: trends.map((t) => ({ period: t.period, value: t.revenue })) },
  { category: "net_profit", history: trends.map((t) => ({ period: t.period, value: t.profit })) },
  { category: "eps", history: trends.map((t) => ({ period: t.period, value: t.eps })) },
];
export const growthPercent = (v: number | null | undefined) => (v == null ? "N/M" : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(v, 1)}%`);

/* ------------------------------------------------------------------ chart conclusions, in words (each chart's aria-label) */
const amount = (v: number, unit: "Cr" | "eps") => (unit === "Cr" ? crore(v) : "₹" + (v < 0 ? MINUS : "") + nf(v, 2));
/** "Revenue rose from ₹2,400 Cr in 2021 to ₹4,295 Cr in 2026." Gaps are skipped, not filled. */
export function trendSentence(label: string, trends: Trend[], key: "revenue" | "profit" | "eps"): string {
  const pts = trends.filter((t) => t[key] != null) as (Trend & Record<typeof key, number>)[];
  if (pts.length < 2) return `${label}: not enough reported years for a trend.`;
  const a = pts[0], b = pts[pts.length - 1], unit = key === "eps" ? "eps" : "Cr";
  const verb = b[key] > a[key] ? "rose" : b[key] < a[key] ? "fell" : "was unchanged";
  return verb === "was unchanged" ? `${label} was ${amount(b[key], unit)} in both ${a.period} and ${b.period}.` : `${label} ${verb} from ${amount(a[key], unit)} in ${a.period} to ${amount(b[key], unit)} in ${b.period}.`;
}
/** The latest year's growth figures in one sentence. */
export function growthSentence(points: GrowthPoint[], incomeLabel = "Revenue"): string {
  const last = points[points.length - 1];
  if (!last || GROWTH_METRICS.every((m) => last[m.key] == null)) return "Not enough comparable years to show growth.";
  const word = (k: GrowthKey) => (k === "revenue" ? incomeLabel.toLowerCase() : k === "profit" ? "net profit" : "EPS");
  return `Growth against the previous year, ${last.period}: ` + GROWTH_METRICS.map((m) => `${word(m.key)} ${growthPercent(last[m.key])}`).join(", ") + ".";
}
/** Category scores in one sentence, with the highest and lowest; withheld when not rated. */
export function partsSentence(rating: Pick<PrismRating, "status" | "parts" | "partWeights">): string {
  if (!isRated(rating)) return "Category scores are withheld because the company is not rated.";
  const known = partsOf(rating).filter((k) => rating.parts[k] != null);
  if (!known.length) return "No category scores are available.";
  const hi = known.reduce((a, b) => (rating.parts[b]! > rating.parts[a]! ? b : a)), lo = known.reduce((a, b) => (rating.parts[b]! < rating.parts[a]! ? b : a));
  return "Category scores out of 100: " + known.map((k) => `${partInfo(k).name} ${score1(rating.parts[k])}`).join(", ") + `. Highest: ${partInfo(hi).name}. Lowest: ${partInfo(lo).name}.`;
}
export function ringSentence(rating: Pick<PrismRating, "status" | "final" | "label">): string {
  return isRated(rating) && rating.final != null
    ? `${PRISM_NAME} score ${score1(rating.final)} out of 100: ${LABEL_WORD[rating.label]}. Status: ${STATUS_WORD[rating.status]}.`
    : `${PRISM_NAME}: not rated. There is not enough verified information for an overall score.`;
}

/* ------------------------------------------------------------------ errors and retries (intent of upstream lib/premiumReportPolling.js) */
/** A failure worth retrying by itself: no answer at all, a timeout, a busy service or a server error. Permanent answers stop. */
export const transient = (e: { status?: number } | null | undefined) => !e?.status || e.status === 408 || e.status === 429 || e.status >= 500;
/** 2.5 s, 5 s, 10 s, then every 15 s. */
export const backoff = (failures: number, intervalMs = 2500) => Math.min(intervalMs * 2 ** failures, 15000);

export type Problem = { kind: "locked" | "missing" | "limit" | "unavailable" | "invalid" | "expired" | "offline" | "other"; title: string; text: string; retryAt?: Date };
const waitWords = (s: number) => (s < 60 ? "less than a minute" : s < 5400 ? `about ${Math.round(s / 60)} minute${Math.round(s / 60) === 1 ? "" : "s"}` : `about ${Math.round(s / 3600)} hours`);
const clock = (d: Date) => d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });
/** What to tell the member for a failed Prism request, in words. */
export function prismProblem(err: unknown, now = Date.now()): Problem {
  const e = err instanceof ApiError ? err : null;
  const status = e?.status ?? 0;
  const detail = e?.body.detail;
  if (status === 401 || status === 403) return { kind: "locked", title: `${PRISM_NAME} is part of Gold`, text: "Sign in with a Gold plan to open and calculate Prism ratings." };
  if (status === 404) return { kind: "missing", title: "We could not find this company", text: "Check the symbol, or choose the company from the search box." };
  if (status === 410) return { kind: "expired", title: "The PDF window has passed", text: "The PDF of a calculation can be downloaded for 30 minutes. Recalculate to download a fresh PDF." };
  if (status === 422) return { kind: "invalid", title: "That request was not accepted", text: detail || "Choose a listed company and a statement basis, then try again." };
  if (status === 429 && e?.body.status === "busy") {
    const secs = e.body.retryAfter || 30;
    return { kind: "unavailable", title: `${PRISM_NAME} is busy`, text: `Other ratings are being calculated right now. Please try again in ${waitWords(secs)}.` };
  }
  if (status === 429) {
    const secs = e?.body.retryAfter || 0;
    const at = secs ? new Date(now + secs * 1000) : undefined;
    const when = at ? ` You can try again in ${waitWords(secs)}, at ${clock(at)} IST.` : " Please try again a little later.";
    return { kind: "limit", title: "Calculation limit reached", text: (detail ? detail.replace(/\.?$/, ".") : "Each member can calculate 20 Prism ratings a day, and only two run at once.") + when, retryAt: at };
  }
  if (status >= 500) return { kind: "unavailable", title: `${PRISM_NAME} is not available right now`, text: "The rating service or a data provider did not answer. Please try again in a few minutes." };
  if (!status) return { kind: "offline", title: "The connection was interrupted", text: "We could not reach FinLit. Check your connection and try again." };
  return { kind: "other", title: "Something went wrong", text: detail || "Please try again." };
}

/* ------------------------------------------------------------------ the PDF of exactly this calculation */
export const prismPdfUrl = (id: string) => `/api/prism/reports/${encodeURIComponent(id)}/pdf`;
/** The PDF stays downloadable while the signed snapshot lives (30 minutes); afterwards the page offers a recalculation. */
export const pdfOpen = (r: Pick<PrismReport, "pdfAvailableUntil">, now = Date.now()) => !!r.pdfAvailableUntil && Date.parse(r.pdfAvailableUntil) > now;
export const pdfName = (r: Pick<PrismReport, "company" | "statementType" | "createdAt">) =>
  `FinLit-Prism-${r.company.symbol}-${r.statementType}-${r.createdAt.slice(0, 10)}.pdf`.replace(/[^\w.-]+/g, "-");

/** Fetch the PDF and save it. A 410 (snapshot gone) or any other refusal is thrown as an ApiError for the page to explain. */
export async function downloadPrismPdf(r: PrismReport): Promise<void> {
  const res = await fetch(apiUrl(prismPdfUrl(r.id)), { headers: { Accept: "application/pdf" }, credentials: API_BASE ? "include" : "same-origin", cache: "no-store" });
  if (!res.ok) {
    let body: ApiError["body"] = {};
    try { body = errorBody(await res.json()); } catch { /* not JSON */ }
    throw new ApiError(res.status, body);
  }
  const href = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = href; a.download = pdfName(r); a.rel = "noreferrer";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 30_000);
}

/* ------------------------------------------------------------------ data hooks */
const SYMBOL = /^[A-Z0-9&_.-]{1,24}$/;
export const cleanSymbol = (s: string | undefined) => { const v = (s || "").trim().toUpperCase(); return SYMBOL.test(v) ? v : null; };
export const latestKey = (symbol: string, statement: Statement) => ["prism", "latest", symbol, statement] as const;

export const usePrismStatus = () =>
  useQuery<PrismServiceStatus, ApiError>({ queryKey: ["prism", "status"], queryFn: () => apiGet("/api/prism/status", { cache: "no-store" }), staleTime: 300_000, retry: 1 });

/** The newest stored report for a company and basis, without calculating; null when there is none yet (404 "none"). */
export const useLatestPrism = (symbol: string, statement: Statement, enabled = true) =>
  useQuery<PrismReport | null, ApiError>({
    queryKey: latestKey(symbol, statement), enabled: enabled && !!symbol, staleTime: 60_000, gcTime: 1_800_000,
    queryFn: async () => {
      try { return await apiGet<PrismReport>(`/api/prism/reports/latest?symbol=${encodeURIComponent(symbol)}&statement=${statement}`, { cache: "no-store" }); }
      catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
    },
    retry: (n, e) => transient(e) && e.status !== 429 && n < 3, retryDelay: (n) => backoff(n),
  });

/** Calculate (or reuse a report under 6 hours old unless `refresh`). Never retried by itself: each calculation counts toward the daily limit.
 *  The answer replaces the company's current report, so the page always shows exactly one calculation. */
export function useGeneratePrism() {
  const qc = useQueryClient();
  return useMutation<PrismReport, ApiError, { symbol: string; statement: Statement; refresh?: boolean }>({
    mutationFn: ({ symbol, statement, refresh = false }) => apiSend<PrismReport>("POST", "/api/prism/reports", { symbol, statement, refresh }),
    onSuccess: (report, v) => {
      qc.setQueryData(latestKey(v.symbol, v.statement), report);
      qc.invalidateQueries({ queryKey: ["prism-latest", v.symbol] });   // the stock page's card reads the same report under its own key
    },
  });
}

/* ------------------------------------------------------------------ a calculation that runs behind the page
 * POST /api/prism/reports {background: true} answers at once; the page then asks GET /api/prism/jobs with a growing pause until the rating is
 * stored. Nothing here animates in a loop: the bar only moves forward with the honest elapsed time, and a calculation that does not finish
 * ends as a failure with a Retry button (it never waits for ever). */
export type PrismJob = {
  state: "working" | "ready" | "failed" | "none"; startedAt?: number; elapsedSeconds?: number; expectedSeconds?: number; pollSeconds?: number;
  status?: number; code?: string; detail?: string; retry?: number | null;
};
/** The longest the page waits for one calculation before it says so (the service gives up on its own at about three minutes). */
export const CALC_GIVE_UP_MS = 200_000;
const POLL_STEPS = [1000, 1000, 1500, 2000, 2000, 3000, 3000, 4000, 5000];
/** How long to wait before asking again after `attempt` answers: 1 s, 1 s, 1.5 s, 2 s ... never more than 5 s. */
export const pollDelay = (attempt: number) => POLL_STEPS[Math.min(Math.max(0, attempt), POLL_STEPS.length - 1)];
/** How full the bar is, 0 to 0.95: it follows the usual time, slows down once that has passed and never claims to be finished before the rating is. */
export function progressFraction(elapsedSeconds: number, expectedSeconds: number): number {
  const expected = Math.max(3, expectedSeconds || 12), t = Math.max(0, elapsedSeconds);
  return t <= expected ? 0.85 * (t / expected) : Math.min(0.95, 0.85 + 0.10 * (1 - Math.exp(-(t - expected) / expected)));
}
/** The failure of a job, in words, as a Problem for the page (the same shape as a failed request). */
export function jobProblem(job: Pick<PrismJob, "status" | "code" | "detail" | "retry">): Problem {
  if (job.status === 404) return prismProblem(new ApiError(404, { status: "not_found" }));
  if (job.status === 422) return prismProblem(new ApiError(422, { status: "bad_request", detail: job.detail }));
  if (job.status === 429) return prismProblem(new ApiError(429, { status: job.code === "limit" ? "limit" : "busy", detail: job.detail, retryAfter: job.retry || undefined }));
  if (job.status === 401 || job.status === 403) return prismProblem(new ApiError(job.status, {}));
  return { kind: "unavailable", title: "The rating could not be calculated", text: job.detail || "The data providers did not answer in time. Nothing was changed. Please try again." };
}
const SLOW: Problem = { kind: "unavailable", title: "This is taking longer than usual", text: "The rating has not finished yet. Nothing was changed. Try again, or come back in a few minutes: it keeps going in the background." };
export type Calc = { phase: "idle" } | { phase: "working"; startedAt: number; expectedSeconds: number } | { phase: "failed"; problem: Problem; retryable: boolean };

/** Start (or join) a calculation behind the page and follow it until the stored rating can be shown. `start()` is for the button and for the
 *  automatic start; the returned `calc` says what to draw. When the rating is ready the company's latest report is loaded into the page. */
export function usePrismCalculation(symbol: string, statement: Statement) {
  const qc = useQueryClient();
  const [calc, setCalc] = useState<Calc>({ phase: "idle" });
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const run = useRef(0);                       // which start() is current: an older one's answers are ignored
  const stop = () => { run.current += 1; clearTimeout(timer.current); };
  useEffect(() => () => stop(), []);           // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { stop(); setCalc({ phase: "idle" }); }, [symbol, statement]);   // another company: forget this one's progress
  const finish = useCallback(async (mine: number) => {
    try { await qc.invalidateQueries({ queryKey: latestKey(symbol, statement) }); } finally { if (run.current === mine) setCalc({ phase: "idle" }); }
    qc.invalidateQueries({ queryKey: ["prism-latest", symbol] });
  }, [qc, symbol, statement]);
  const follow = useCallback((mine: number, startedAt: number) => {
    let attempt = 0, failures = 0;
    const ask = async () => {
      if (run.current !== mine) return;
      if (Date.now() - startedAt > CALC_GIVE_UP_MS) { setCalc({ phase: "failed", problem: SLOW, retryable: true }); return; }
      try {
        const job = await apiGet<PrismJob>(`/api/prism/jobs?symbol=${encodeURIComponent(symbol)}&statement=${statement}`, { cache: "no-store" });
        if (run.current !== mine) return;
        failures = 0;
        if (job.state === "ready") { await finish(mine); return; }
        if (job.state === "failed") { setCalc({ phase: "failed", problem: jobProblem(job), retryable: job.status !== 429 || job.code !== "limit" }); return; }
        if (job.state === "none") { setCalc({ phase: "failed", problem: jobProblem({}), retryable: true }); return; }
      } catch (e) {
        if (run.current !== mine) return;
        if (!transient(e as ApiError) || ++failures > 3) { setCalc({ phase: "failed", problem: prismProblem(e), retryable: transient(e as ApiError) }); return; }
      }
      timer.current = setTimeout(ask, pollDelay(++attempt));
    };
    timer.current = setTimeout(ask, pollDelay(0));
  }, [symbol, statement, finish]);
  const start = useCallback(async (refresh = false) => {
    stop();
    const mine = run.current;
    const startedAt = Date.now();
    setCalc({ phase: "working", startedAt, expectedSeconds: 12 });
    try {
      const r = await apiSend<{ status?: string; elapsedSeconds?: number; expectedSeconds?: number; rating?: unknown }>("POST", "/api/prism/reports", { symbol, statement, refresh, background: true });
      if (run.current !== mine) return;
      if (r?.status === "working") {
        const begun = startedAt - Math.max(0, r.elapsedSeconds ?? 0) * 1000;     // a calculation somebody else started has already been running
        const expected = r.expectedSeconds ?? 12;
        setCalc({ phase: "working", startedAt: begun, expectedSeconds: expected });
        follow(mine, begun);
      } else if (r?.rating) {                                                     // a stored rating answered at once
        qc.setQueryData(latestKey(symbol, statement), r);
        qc.invalidateQueries({ queryKey: ["prism-latest", symbol] });
        setCalc({ phase: "idle" });
      } else setCalc({ phase: "failed", problem: jobProblem({}), retryable: true });
    } catch (e) {
      if (run.current === mine) setCalc({ phase: "failed", problem: prismProblem(e), retryable: prismProblem(e).kind !== "limit" && prismProblem(e).kind !== "locked" });
    }
  }, [symbol, statement, qc, follow]);
  return { calc, start };
}

/* ------------------------------------------------------------------ the companies a member opened lately (this browser only) */
const RECENT = "finlit-prism-recent";
export function readPrismRecent(): string[] {
  try { const v = JSON.parse(localStorage.getItem(RECENT) || "[]"); return Array.isArray(v) ? v.filter((x) => typeof x === "string" && SYMBOL.test(x)).slice(0, 8) : []; } catch { return []; }
}
export function pushPrismRecent(symbol: string) {
  try { localStorage.setItem(RECENT, JSON.stringify([symbol, ...readPrismRecent().filter((s) => s !== symbol)].slice(0, 8))); } catch { /* private mode */ }
}
