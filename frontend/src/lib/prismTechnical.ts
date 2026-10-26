// FinLit Prism, technical assessment (short term and long term): types, a forgiving parser, and the ONE place where the model's words
// become the site's words.
//
// The assessment is additive and independent: `report.technicalAssessment` sits beside `rating` in the stored report. It is NOT a fifth part of the
// 0-100 Prism score and never changes it. Older reports do not have the field; `parseTechnical` then returns null and the screens say so calmly.
// Model: docs of the upstream repo, premium-st-lt-model.md (model st-lt-14.3). The browser never receives factor weights or hashes, and this
// file never reads, shows or requires them.
//
// COMPLIANCE (owner's rule): the site never gives buy / sell / hold / avoid advice and is not SEBI registered. The model's own rating words
// (Strong Buy, Buy, Hold, Reduce, Sell) and verdict labels (STRONG BUY ... SELL / AVOID) are therefore NEVER shown. Everything a person reads
// about a rating goes through `ratingWord`, `verdictView` and `safeText` below; lib/prismTechnical.test.ts asserts that no rendered string
// contains one of the forbidden words.
import { MINUS } from "./format";
import WORDING from "./technicalWording.json";

export const TECH_NAME = "Technical view";
/** What the technical view is, in plain words. Shown wherever it appears, next to the general Prism line. */
export const TECH_NOTE = "Describes recent price and trend behaviour from past prices. It does not predict prices and is not a recommendation.";

/* ------------------------------------------------------------------ types */
export type FactorStatus = "available" | "unavailable" | "disabled";
export type TechFactor = { key: string; label: string; signal: number | null; status: FactorStatus; detail: string };
export type TechHorizon = {
  /** -100..+100 at full precision, or null when a required signal is missing. Rounded only for display (`fmtScore`). */
  score: number | null;
  /** The model's own rating word. Never displayed; `ratingWord` maps it. */
  rating: string | null;
  status: "ready" | "incomplete";
  /** For example "5–20 sessions" or "6–18 months". */
  horizon: string | null;
  availableCount: number; requiredCount: number;
  stageCapped: boolean;
  factors: TechFactor[];
};
export type TechObservations = {
  stage: 1 | 2 | 3 | 4 | null; freshStage2: boolean | null; slope150Pct: number | null;
  benchmark: string | null; benchmarksUsed: string[]; beta: number | null; rsRatingST: number | null; rsRatingLT: number | null;
};
export type TechBenchmarkSource = { name: string; provider: string | null; asOf: string | null; bars: number | null };
export type TechAssessment = {
  modelVersion: string | null; status: "ready" | "incomplete"; asOf: string | null; provider: string | null;
  dailyBars: number | null; usableDailyBars: number | null; fresh: boolean | null;
  shortTerm: TechHorizon; longTerm: TechHorizon;
  /** The model's combined verdict. Never displayed as given; `verdictView` maps it. */
  verdict: { label: string | null; tone: string | null };
  notes: string[]; observations: TechObservations; benchmarkSources: TechBenchmarkSource[];
};

/* ------------------------------------------------------------------ parser (never throws) */
const rec = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);
const count = (v: unknown): number => { const n = num(v); return n != null && n >= 0 ? Math.floor(n) : 0; };
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter((s): s is string => s != null) : []);

function parseFactor(v: unknown): TechFactor | null {
  const f = rec(v); if (!f) return null;
  const key = str(f.key), label = str(f.label);
  if (!key || !label) return null;
  const status: FactorStatus = f.status === "available" || f.status === "disabled" ? f.status : "unavailable";
  let signal = num(f.signal);
  if (signal != null && (signal < -1 || signal > 1)) signal = null;       // the model never sends this; treat it as no signal rather than draw it
  if (status !== "available") signal = null;
  if (status === "available" && signal == null) return { key, label, signal: null, status: "unavailable", detail: str(f.detail) ?? str(f.reason) ?? str(f.observation) ?? "" };
  return { key, label, signal, status, detail: str(f.detail) ?? str(f.reason) ?? str(f.observation) ?? "" };
}

function parseHorizon(v: unknown): TechHorizon {
  const h = rec(v) ?? {};
  let score = num(h.score);
  if (score != null && (score < -100 || score > 100)) score = null;
  const factors = (Array.isArray(h.factors) ? h.factors : []).map(parseFactor).filter((f): f is TechFactor => f != null);
  return {
    score, rating: str(h.rating), status: score != null && h.status !== "incomplete" ? "ready" : "incomplete", horizon: str(h.horizon),
    availableCount: count(h.availableCount), requiredCount: count(h.requiredCount), stageCapped: h.stageCapped === true && score != null, factors,
  };
}

function parseObservations(v: unknown): TechObservations {
  const o = rec(v) ?? {};
  const st = num(o.stage);
  return {
    stage: st === 1 || st === 2 || st === 3 || st === 4 ? st : null, freshStage2: typeof o.freshStage2 === "boolean" ? o.freshStage2 : null, slope150Pct: num(o.slope150Pct),
    benchmark: str(o.benchmark), benchmarksUsed: strs(o.benchmarksUsed), beta: num(o.beta), rsRatingST: num(o.rsRatingST), rsRatingLT: num(o.rsRatingLT),
  };
}

function parseSources(v: unknown): TechBenchmarkSource[] {
  const o = rec(v); if (!o) return [];
  return Object.entries(o).flatMap(([name, s]) => { const r = rec(s); return r ? [{ name, provider: str(r.provider), asOf: str(r.asOf), bars: num(r.bars) }] : []; });
}

/** Read `report.technicalAssessment`. Null for a report that has none (older snapshots) or for something that is not an assessment at all.
 *  Missing or odd fields become nulls, empty lists or "incomplete"; it never throws and never invents a number. Weights and hashes are not read. */
export function parseTechnical(raw: unknown): TechAssessment | null {
  try {
    const a = rec(raw); if (!a) return null;
    if (!rec(a.shortTerm) && !rec(a.longTerm)) return null;
    const shortTerm = parseHorizon(a.shortTerm), longTerm = parseHorizon(a.longTerm), v = rec(a.verdict) ?? {};
    return {
      modelVersion: str(a.modelVersion), status: shortTerm.score != null && longTerm.score != null && a.status !== "incomplete" ? "ready" : "incomplete",
      asOf: str(a.asOf), provider: str(a.provider), dailyBars: num(a.dailyBars), usableDailyBars: num(a.usableDailyBars), fresh: typeof a.fresh === "boolean" ? a.fresh : null,
      shortTerm, longTerm, verdict: { label: str(v.label), tone: str(v.tone) }, notes: strs(a.notes), observations: parseObservations(a.observations), benchmarkSources: parseSources(a.benchmarkSources),
    };
  } catch { return null; }
}

/* ------------------------------------------------------------------ the one words table */
export type TrendTone = "strongpos" | "pos" | "neutral" | "neg" | "strongneg" | "na";

/** The wording table is ONE json file (lib/technicalWording.json), an identical copy of site-api/backend/technical_wording.json, which the PDF
 *  reads: the web view and the PDF can never disagree (a test in each suite compares the two files byte for byte). */
export const BANDS = WORDING.bands as { strongPositive: number; positive: number; neutral: number; negative: number };

/** The model's rating words (upstream premium_technical.score_rating) -> the site's descriptive trend words. The ONLY place the two meet. */
export const RATING_WORD = WORDING.ratings as Record<string, { word: string; tone: TrendTone }>;
const NA = { word: "Not available", tone: "na" as TrendTone };

/** The band of a full-precision score: >= 50 strongly positive, >= 20 positive, > -20 neutral, > -50 negative, else strongly negative
 *  (so exactly -50 is the lowest band). The boundaries come from BANDS, which the legend on screen prints too. */
export function scoreBand(score: number | null): TrendTone {
  if (score == null || !Number.isFinite(score)) return "na";
  return score >= BANDS.strongPositive ? "strongpos" : score >= BANDS.positive ? "pos" : score > BANDS.neutral ? "neutral" : score > BANDS.negative ? "neg" : "strongneg";
}
const BAND_WORD = WORDING.bandWords as Record<TrendTone, string>;

/** The word and tone for a horizon. The model's rating is used when it is one we know; otherwise the full-precision score decides.
 *  A rating word we do not know is never shown. A horizon without a score is "Not available" whatever its rating says. */
export function ratingWord(rating: string | null | undefined, score: number | null): { word: string; tone: TrendTone } {
  if (score == null || !Number.isFinite(score)) return NA;
  const known = rating ? RATING_WORD[rating.trim().toLowerCase().replace(/\s+/g, " ")] : undefined;
  if (known && known.tone !== "na") return known;
  const tone = scoreBand(score);
  return { word: BAND_WORD[tone], tone };
}

export type VerdictTone = "pos" | "mixed" | "neg" | "na";
/** The model's verdict labels with the tone it sends for each (premium_technical.combine_verdict), from the shared wording file. */
const VERDICTS = WORDING.verdicts as Record<string, VerdictTone>;
const TONE_ALIAS = WORDING.toneAlias as Record<string, VerdictTone>;
export const VERDICT_WORD = WORDING.verdictWords as Record<VerdictTone, string>;

const normLabel = (s: string) => s.replace(/[‘’ʼ]/g, "'").replace(/\s+/g, " ").trim().toUpperCase();

/** The combined verdict as the site words it. Needs both scores (as the model does). The tone comes from the label, then from the model's own
 *  tone field; the sentence under the chip names each horizon so the chip is never read on its own. */
export function verdictView(a: Pick<TechAssessment, "shortTerm" | "longTerm" | "verdict">): { tone: VerdictTone; word: string; detail: string } {
  const st = a.shortTerm, lt = a.longTerm;
  if (st.score == null || lt.score == null) return { tone: "na", word: VERDICT_WORD.na, detail: "A combined view needs both the short-term and the long-term score." };
  const label = a.verdict.label ? normLabel(a.verdict.label) : "";
  const tone = VERDICTS[label] ?? (a.verdict.tone ? TONE_ALIAS[a.verdict.tone.trim().toLowerCase()] : undefined) ?? "na";
  const s = ratingWord(st.rating, st.score).word.toLowerCase(), l = ratingWord(lt.rating, lt.score).word.toLowerCase();
  return { tone, word: VERDICT_WORD[tone], detail: `Short term ${s}; long term ${l}.` };
}

/* ------------------------------------------------------------------ safe wording of model-provided text */
/** Words the site never shows (as whole words or word starts). From the shared wording file. */
export const FORBIDDEN = new RegExp(WORDING.forbidden, "i");

/** Whole-label rewrites for model text that is built around an advice word. Checked first. */
const PHRASES: [RegExp, string][] = (WORDING.phrases as [string, string][]).map(([re, to]) => [new RegExp(re, "gi"), to]);
/** Single-word rewrites for anything left. Descriptive, not advice. */
const WORDS = WORDING.words as Record<string, string>;
const matchCase = (from: string, to: string) => (from[0] && from[0] === from[0].toUpperCase() && from[0] !== from[0].toLowerCase() ? to[0].toUpperCase() + to.slice(1) : to);

/** Model-provided text (factor labels, observations, notes) as it may be shown: advice words are replaced by descriptive ones. Idempotent. */
export function safeText(text: string | null | undefined): string {
  if (!text) return "";
  let out = text;
  for (const [re, to] of PHRASES) out = out.replace(re, (m) => matchCase(m, to));
  out = out.replace(new RegExp(FORBIDDEN.source, "gi"), (m) => { const to = WORDS[m.toLowerCase()]; return to ? matchCase(m, to) : "—"; });
  return out;
}

/* ------------------------------------------------------------------ display helpers */
/** Digits to show: the fewest (0 to 4) at which the shown number still sits in the same rating band as the true score, so "+20" is never
 *  drawn for 19.96 (which is Neutral). Rounding is for display only; nothing is rounded before a label is decided. */
export function fmtScore(score: number | null | undefined): string {
  if (score == null || !Number.isFinite(score)) return "—";
  const band = scoreBand(score);
  for (let d = 0; d <= 4; d++) {
    const r = Number(score.toFixed(d));
    if (scoreBand(r) === band || d === 4) {
      if (r === 0) return "0";
      return (r > 0 ? "+" : MINUS) + Math.abs(r).toFixed(d);
    }
  }
  return "—";
}

/** Where a score sits on the -100..+100 scale, 0..100 for CSS. */
export const scalePos = (score: number | null): number => (score == null ? 50 : (Math.max(-100, Math.min(100, score)) + 100) / 2);

export type FactorGroup = "supporting" | "adverse" | "neutral" | "unavailable";
export const FACTOR_GROUP_WORD: Record<FactorGroup | "all", string> = { all: "All signals", supporting: "Supporting", adverse: "Adverse", neutral: "Neutral", unavailable: "Unavailable" };
/** A factor's group; null for a factor that is switched off (it is listed in a note, not among the signals). */
export function factorGroup(f: TechFactor): FactorGroup | null {
  if (f.status === "disabled") return null;
  if (f.status === "unavailable" || f.signal == null) return "unavailable";
  return f.signal > 0 ? "supporting" : f.signal < 0 ? "adverse" : "neutral";
}
export const filterTechFactors = (rows: TechFactor[], filter: FactorGroup | "all") => rows.filter((f) => { const g = factorGroup(f); return g != null && (filter === "all" || g === filter); });
export const disabledFactors = (rows: TechFactor[]) => rows.filter((f) => f.status === "disabled");

/** Wording for how strong a signal is, from -1 to +1. */
export function signalWord(signal: number): string {
  const a = Math.abs(signal);
  if (a === 0) return "Neutral";
  return (signal > 0 ? "Supporting" : "Adverse") + (a >= 0.75 ? ", strong" : a >= 0.5 ? "" : ", mild");
}

export const STAGE_WORD: Record<1 | 2 | 3 | 4, string> = {
  1: "Stage 1: basing (price moving sideways after a decline)",
  2: "Stage 2: advancing (price trending up)",
  3: "Stage 3: topping (the advance is losing strength)",
  4: "Stage 4: declining (price trending down)",
};

/** True when the assessment is recent enough to be a current view; false/unknown are both worded as "may be out of date". */
export const isFresh = (a: TechAssessment) => a.fresh === true;

/** Every string a screen shows about an assessment, for the compliance scan in tests. */
export function allShownText(a: TechAssessment): string[] {
  const out: string[] = [];
  for (const h of [a.shortTerm, a.longTerm]) {
    out.push(ratingWord(h.rating, h.score).word, h.horizon ?? "");
    for (const f of h.factors) out.push(safeText(f.label), safeText(f.detail));
  }
  const v = verdictView(a); out.push(v.word, v.detail);
  out.push(...a.notes.map(safeText), a.observations.benchmark ?? "", ...a.observations.benchmarksUsed, ...a.benchmarkSources.map((s) => `${s.name} ${s.provider ?? ""}`));
  return out;
}
