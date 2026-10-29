// The one band rule for a 0-100 score: green from 70, orange from 50 to 69, red below 50 (the founder's rule). Tiny on purpose.
export type ScoreBand = "green" | "orange" | "red";
export const scoreBand100 = (score: number | null | undefined): ScoreBand | null =>
  score == null || !Number.isFinite(score) ? null : score >= 70 ? "green" : score >= 50 ? "orange" : "red";
const VAR: Record<ScoreBand, string> = { green: "var(--gain)", orange: "var(--warn)", red: "var(--loss)" };
/** CSS colour of a 0-100 score; the muted colour for a missing one. */
export const scoreBandColor = (score: number | null | undefined): string => { const b = scoreBand100(score); return b ? VAR[b] : "var(--faint)"; };
