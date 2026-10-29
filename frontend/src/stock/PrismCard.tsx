// FinLit Prism on the stock page, data side: the newest stored report for a company, read without calculating anything.
// The comparison block (PrismCompare.tsx) draws it; calculating a report is a separate, explicit action (generatePrism).
// Contract: docs/prism/CONTRACT.md. Anything unexpected leaves the page as it was: the state is "hidden", never an error screen.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend } from "../lib/api";
import type { PrismPart } from "./prismWords";

export type PrismLabel = "STRONG" | "HEALTHY" | "AVERAGE" | "WEAK" | "POOR" | "NOT RATED";
export type PrismStatus = "RATED" | "PROVISIONAL" | "NOT RATED";
/** What the reader view of a part says about one factor. */
export type PrismReviewItem = { metric: string; label: string; valueText: string; summary: string };
/** The part of `GET /api/prism/reports/latest` the stock page reads (the full report is typed on the Prism page). `technical` arrives with the model's fifth part. */
export type PrismLatest = {
  id: string; createdAt: string; completedAt: string; statementType: "consolidated" | "standalone";
  company: { symbol: string; name: string };
  rating: { final: number | null; label: PrismLabel; status: PrismStatus; parts: Partial<Record<PrismPart | "technical", number | null>>; partWeights?: Partial<Record<PrismPart | "technical", number>>; confidence: number; modelVersion?: string; notRatedReasons?: { code: "classification" | "insufficient_history" | "low_confidence" | "data_integrity"; text: string }[] };
  review?: { parts?: { key: string; name: string; pros?: PrismReviewItem[]; cons?: PrismReviewItem[]; unavailable?: PrismReviewItem[]; notes?: string[] }[]; notes?: string[]; completeness?: { complete: boolean; missingFactorCount: number; limitedHistoryCount: number; items: { label: string; reason: string; treatment: string }[] } };
  pdfAvailableUntil?: string | null;
  /** The independent short-term / long-term technical assessment (not a part of the score). Absent from older reports; read it with parseTechnical. */
  technicalAssessment?: unknown;
};
export type PrismCardState = { kind: "report"; report: PrismLatest } | { kind: "none" } | { kind: "locked" } | { kind: "hidden" };

export const LABEL: Record<PrismLabel, [word: string, tone: string]> = {
  STRONG: ["Strong", "strong"], HEALTHY: ["Healthy", "healthy"], AVERAGE: ["Average", "mixed"], WEAK: ["Weak", "weak"], POOR: ["Poor", "weak"], "NOT RATED": ["Not rated", "na"],
};
export const STATUS: Record<PrismStatus, string> = { RATED: "Rated", PROVISIONAL: "Provisional rating", "NOT RATED": "Not rated" };

const isReport = (r: unknown): r is PrismLatest => {
  const x = r as PrismLatest | null;
  return !!x && typeof x === "object" && !!x.rating && typeof x.rating.label === "string" && x.rating.label in LABEL && x.rating.status in STATUS && !!x.rating.parts;
};

/** Ask for the stored report. "none" only for the API's own `{"status": "none"}`; a refusal is "locked"; anything else is "hidden". */
export async function loadPrismLatest(symbol: string, statement: string): Promise<PrismCardState> {
  try {
    const r = await apiGet<unknown>(`/api/prism/reports/latest?symbol=${encodeURIComponent(symbol)}&statement=${encodeURIComponent(statement)}`);
    return isReport(r) ? { kind: "report", report: r } : { kind: "hidden" };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404 && e.body.status === "none") return { kind: "none" };
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return { kind: "locked" };
    return { kind: "hidden" };
  }
}

export const usePrismLatest = (symbol: string, statement: string, enabled: boolean) =>
  useQuery<PrismCardState>({ queryKey: ["prism-latest", symbol, statement], queryFn: () => loadPrismLatest(symbol, statement), enabled: enabled && !!symbol, staleTime: 60_000, retry: false });

/** Calculate (or recalculate) the rating. Only ever called from a button; usually takes under half a minute (the Prism page starts one by itself and follows it). */
export async function generatePrism(symbol: string, statement: string, refresh: boolean): Promise<PrismLatest> {
  const r = await apiSend<unknown>("POST", "/api/prism/reports", { symbol, statement, refresh });
  if (!isReport(r)) throw new ApiError(502, { status: "unavailable", detail: "The rating came back in a form we could not read." });
  return r;
}

/** The sentence a person is told when a calculation does not work, in plain words. */
export function generateFailure(e: unknown): string {
  const st = e instanceof ApiError ? e.status : 0;
  if (st === 429) return e instanceof ApiError && e.body.status === "limit" ? (e.body.detail || "You have used today's Prism calculations.")
    : "Other companies are being calculated right now (the service does one at a time). Please try again in a minute; nothing is lost.";
  if (st === 403 || st === 401) return "FinLit Prism is part of the Gold plan.";
  if (st === 404) return "We could not find financial data for this company, so there is nothing to rate.";
  return "The rating could not be calculated right now. Nothing was changed. Please try again in a few minutes.";
}

const one = (v: number) => (Math.round(v * 10) / 10).toFixed(1);
export const pct = (v: number) => `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`;
export const fmtScore = one;

/** The words a screen reader hears for the whole rating. */
export function prismSummary(r: PrismLatest["rating"]): string {
  const cov = `${pct(r.confidence)} of inputs available`;
  if (r.status === "NOT RATED" || r.final == null) return `FinLit Prism: not rated. ${cov}.`;
  return `FinLit Prism rating: ${LABEL[r.label][0]}, ${one(r.final)} out of 100, ${STATUS[r.status].toLowerCase()}. ${cov}.`;
}
