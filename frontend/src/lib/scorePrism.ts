// FinLit Prism on the Advanced score screener: labels, columns, plain-words explanations and the reasons a Prism cell can be empty.
// Pure data and small functions (no React). Wording: the rating describes financial health from filings and prices; never advice.
import type { Row } from "./screener";

export type PrismLabel = "STRONG" | "HEALTHY" | "AVERAGE" | "WEAK" | "POOR" | "NOT RATED";
export const PRISM_LABELS: PrismLabel[] = ["STRONG", "HEALTHY", "AVERAGE", "WEAK", "POOR", "NOT RATED"];
export const LABEL_WORD: Record<PrismLabel, string> = { STRONG: "Strong", HEALTHY: "Healthy", AVERAGE: "Average", WEAK: "Weak", POOR: "Poor", "NOT RATED": "Not rated" };
/** Address form of each label (no spaces). */
export const LABEL_SLUG: Record<PrismLabel, string> = { STRONG: "strong", HEALTHY: "healthy", AVERAGE: "average", WEAK: "weak", POOR: "poor", "NOT RATED": "notrated" };
export const labelFromSlug = (s: string) => PRISM_LABELS.find((l) => LABEL_SLUG[l] === s);
export const isLabel = (v: unknown): v is PrismLabel => typeof v === "string" && (PRISM_LABELS as string[]).includes(v);

/** Colour tone of a Prism score, the same bands as the engine (and prism.ts scoreTone): 80, 65, 50, 35. */
export type Tone = "strong" | "healthy" | "average" | "weak" | "poor" | "none";
export const toneOf = (v: number | null | undefined): Tone => (v == null ? "none" : v >= 80 ? "strong" : v >= 65 ? "healthy" : v >= 50 ? "average" : v >= 35 ? "weak" : "poor");
export const labelTone = (l: string | null | undefined): Tone => (isLabel(l) && l !== "NOT RATED" ? (l.toLowerCase() as Tone) : "none");

export type PrismRangeKey = "z" | "zf" | "zv" | "zq" | "zr";
export type PrismCol = "prism_final" | "prism_fundamental" | "prism_valuation" | "prism_quality" | "prism_risk" | "prism_st_score" | "prism_lt_score";
/** The category scores of the Prism rating, in the model's order, with the range key that filters each. */
export const PRISM_PARTS: { range: PrismRangeKey; col: PrismCol; label: string; say: string }[] = [
  { range: "zf", col: "prism_fundamental", label: "Fundamentals", say: "How steadily sales and profit grow." },
  { range: "zv", col: "prism_valuation", label: "Valuation", say: "The share price against earnings, book value and the company's own history. Higher means a more modest price for what the company earns." },
  { range: "zq", col: "prism_quality", label: "Quality", say: "Financial strength: borrowing, interest cover, returns and cash backing for profit." },
  { range: "zr", col: "prism_risk", label: "Risk", say: "Market risk: price swings, largest fall, trading activity and pledged shares. Higher means lower risk." },
];
export const PRISM_NAMES: Record<PrismRangeKey, string> = { z: "Prism score", zf: "Prism Fundamentals", zv: "Prism Valuation", zq: "Prism Quality", zr: "Prism Risk" };
export const PRISM_RANGE_KEYS: PrismRangeKey[] = ["z", "zf", "zv", "zq", "zr"];
export const prismRangeValue = (r: Row, k: PrismRangeKey): number | null | undefined =>
  k === "z" ? r.prism_final : k === "zf" ? r.prism_fundamental : k === "zv" ? r.prism_valuation : k === "zq" ? r.prism_quality : r.prism_risk;

/** A rating exists with a number (RATED or PROVISIONAL). */
export const hasPrism = (r: Row) => r.prism_final != null;

export type PrismCell = "rated" | "locked" | "model-declined" | "not-yet";
/** Why a Prism cell shows what it shows. */
export function prismCell(r: Row, gold: boolean): PrismCell {
  if (hasPrism(r)) return "rated";
  if (!gold) return "locked";
  if (r.prism_state === "stored") return "model-declined";
  return "not-yet";
}
const NOW = "Open its Prism page to rate it now (about 30 seconds).";
/** The reason, in plain words, for an empty Prism column. `col` is the column asked about. */
export function prismReason(r: Row, gold: boolean, col: "final" | "part" | "st" | "lt" = "final"): string {
  const cell = prismCell(r, gold);
  if (cell === "locked") return "FinLit Prism is part of the Gold plan";
  if (cell === "not-yet") return `Not rated yet. Ratings are added every night, largest companies first. ${NOW}`;
  if (cell === "model-declined") return "Prism could not rate this company: its filed history or data is not enough for a rating. Open its Prism page for the detail.";
  if (col === "st" || col === "lt") return "The short and long term technical reading was not calculated for this rating (an older rating, or price history is incomplete). Recalculate on its Prism page.";
  if (col === "part") return "This category was not scored for this company";
  return "Not available";
}

export const PRISM_STATUS_WORD: Record<string, string> = { RATED: "Rated", PROVISIONAL: "Provisional", "NOT RATED": "Not rated" };

/** 'Rated X of Y' line, from the server's counts (or null when the page has none). */
export function coverageLine(c: { rated: number; provisional: number; total: number; per_night?: number } | null | undefined): string | null {
  if (!c || !c.total) return null;
  const n = c.rated + c.provisional;
  return `Prism has rated ${n.toLocaleString("en-IN")} of ${c.total.toLocaleString("en-IN")} companies (${Math.round((n / c.total) * 100)}%).`;
}

export const EXPLAIN = {
  finlit: "The FinLit score (0 to 100) is the average of five pillars worked out from a company's filed statements and prices: Quality, Growth, Profitability, Balance sheet and Technical. Free on every plan to see the company's own page; the full table is Silver.",
  prism: "FinLit Prism (0 to 100) is the advanced rating, Gold only. It splits a company into four parts (Fundamentals, Valuation, Quality, Risk) and weighs them into one number with a label: Strong 80 and above, Healthy 65 to 79, Average 50 to 64, Weak 35 to 49, Poor under 35. Status says how complete the data was: Rated, Provisional (a rating with limited history) or Not rated (not enough data).",
  differ: "The two scores are built differently on purpose. FinLit averages five pillars, including the price trend; Prism weighs four parts and adds valuation and risk. They can disagree, and the reason is on the company's report.",
  technical: "Short term (5 to 20 sessions) and long term (6 to 18 months) are Prism's separate reading of the price trend, from -100 to +100. They describe the trend only and are not part of the Prism score.",
} as const;

/** Counts for 'rated X of Y' from the rows themselves, for when the server sent none (Gold rows carry every figure). */
export function coverageFrom(rows: Row[]): { rated: number; provisional: number; not_rated: number; stored: number; total: number } {
  let rated = 0, provisional = 0, stored = 0;
  for (const r of rows) {
    if (r.prism_state === "stored") stored++;
    if (r.prism_status === "RATED") rated++; else if (r.prism_status === "PROVISIONAL") provisional++;
  }
  return { rated, provisional, not_rated: stored - rated - provisional, stored, total: rows.length };
}
