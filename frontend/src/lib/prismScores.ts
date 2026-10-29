// Gold only: the stored FinLit Prism scores of the companies the search shows (GET /api/prism/scores). Nothing is calculated here; a company
// with no stored rating is "not rated yet". Technical scores are signed (-100..+100) and read exactly as on the Prism card.
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiGet } from "./api";
import { fmtScore, scoreBand, type TrendTone } from "./prismTechnical";
import { bandVar, scoreBand as band100 } from "./scoreBands";

export const PRISM_PARTS = ["fundamental", "valuation", "quality", "risk"] as const;
export type PrismPartKey = (typeof PRISM_PARTS)[number];
export type TechScore = { score: number | null; word: string };
export type PrismScore = {
  rated: boolean; final: number | null; label: string | null; status: string | null;
  parts: Record<PrismPartKey, number | null> | null; shortTerm: TechScore; longTerm: TechScore;
};
/** Missing key: not asked yet / loading. null: asked, no stored rating. "error": the request failed. */
export type PrismScoreMap = Record<string, PrismScore | null | "error">;

export const BATCH = 40;
export const PART_LABEL: Record<PrismPartKey, string> = { fundamental: "Fundamentals", valuation: "Valuation", quality: "Quality", risk: "Risk" };
export const TECH_LABEL = { shortTerm: "Short-term technical", longTerm: "Long-term technical" } as const;
export const TECH_TIP = "Signed score from −100 to +100 for the price trend: +50 or more strongly positive, +20 to +50 positive, −20 to +20 neutral, −20 to −50 negative, −50 or less strongly negative. It describes past prices and is not a recommendation.";
export const NOT_RATED_TIP = "FinLit Prism has not been calculated for this company yet. Open Prism to start the calculation.";
export const OLD_REPORT_TIP = "This stored Prism report was made before the technical view existed. Open Prism and recalculate to add it.";

/** The symbols not yet known, in chunks of at most BATCH. */
export function missingChunks(symbols: readonly string[], known: PrismScoreMap, size = BATCH): string[][] {
  const need = [...new Set(symbols)].filter((s) => !(s in known));
  const out: string[][] = [];
  for (let i = 0; i < need.length; i += size) out.push(need.slice(i, i + size));
  return out;
}
/** Signed score as on the Prism card: "+34" / "−15" / "0". */
export const techText = fmtScore;
export const techFill = (score: number | null) => (score == null ? 0 : Math.max(0, Math.min(100, (score + 100) / 2)));
/** Colour of a technical score: its trend band (strongly positive / positive green, neutral orange, negative red). */
export function techColor(score: number | null): string {
  const t: TrendTone = scoreBand(score);
  return t === "na" ? "var(--faint)" : t === "strongpos" || t === "pos" ? "var(--gain)" : t === "neutral" ? "var(--warn)" : "var(--loss)";
}
/** Colour of a 0-100 score by the shared rule (green 70+, orange 50-69, red below 50, grey when missing). */
export const finalColor = (v: number | null | undefined) => bandVar(band100(v));

/** Fetches the stored scores of the given (visible) symbols, once each, batched, after a pause so scrolling and typing do not storm the server. */
export function usePrismScores(symbols: readonly string[], enabled: boolean, waitMs = 250): PrismScoreMap {
  const qc = useQueryClient();
  const [known, setKnown] = useState<PrismScoreMap>({});
  const key = useMemo(() => [...new Set(symbols)].sort().join(","), [symbols]);
  const asked = useRef(new Set<string>());      // asked already (answered or on the way): never asked twice
  useEffect(() => {
    if (!enabled || !key) return;
    const t = window.setTimeout(() => {
      for (const chunk of missingChunks(key.split(","), Object.fromEntries([...asked.current].map((x) => [x, null])))) {
        chunk.forEach((x) => asked.current.add(x));
        const q = chunk.slice().sort().join(",");
        qc.fetchQuery({ queryKey: ["prism-scores", q], queryFn: () => apiGet<{ scores: Record<string, PrismScore> }>(`/api/prism/scores?symbols=${encodeURIComponent(q)}`), staleTime: 60_000 })
          .then((r) => setKnown((k) => ({ ...k, ...Object.fromEntries(chunk.map((s) => [s, r.scores[s] ?? null])) })))
          .catch(() => { chunk.forEach((x) => asked.current.delete(x)); setKnown((k) => ({ ...k, ...Object.fromEntries(chunk.map((s) => [s, "error" as const])) })); });
      }
    }, waitMs);
    return () => window.clearTimeout(t);
  }, [key, enabled, qc, waitMs]);
  return known;
}
