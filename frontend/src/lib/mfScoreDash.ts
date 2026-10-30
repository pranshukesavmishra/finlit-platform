// The Funds category cards: what each card says about the Health score of its Direct-plan funds. Pure functions, so the rules are tested apart from the page.
// The server sends the numbers to Gold only; a plan below that gets `locked` and nothing to show here but a lock.
import { scoreBand, type ScoreBand } from "./scoreBands";
import { scoreText, type CategoryScore, type CategoryScores } from "./mfScore";
import type { Card } from "./mfCategories";

export type CardScoreView =
  | { kind: "loading" }
  | { kind: "locked" }
  | { kind: "unavailable" }                                  // the score request failed: say so, show no number
  | { kind: "notRun" }                                       // "Not scored yet": the score job has not run
  | { kind: "none" }                                         // the job has run but no Direct-plan fund of this category has a score
  | { kind: "scored"; median: string; band: ScoreBand; n: number; line: string; shares: Shares; label: string };
export type Shares = { green: number; orange: number; red: number };

/** Whole-number shares of the three bands that add up to 100 (largest-remainder rounding), so the bar and the legend never disagree. Zeros stay zero. */
export function bandShares(c: Pick<CategoryScore, "green" | "orange" | "red">): Shares {
  const n = c.green + c.orange + c.red;
  if (n <= 0) return { green: 0, orange: 0, red: 0 };
  const keys = ["green", "orange", "red"] as const;
  const exact = keys.map((k) => (c[k] / n) * 100), base = exact.map(Math.floor);
  let left = 100 - base.reduce((a, b) => a + b, 0);
  const order = exact.map((e, i) => [e - base[i], i] as const).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (const [, i] of order) { if (left <= 0) break; if (c[keys[i]] > 0) { base[i]++; left--; } }
  return { green: base[0], orange: base[1], red: base[2] };
}

export const medianLine = (median: number, n: number) => `median ${scoreText(median)} of ${n.toLocaleString("en-IN")} scored fund${n === 1 ? "" : "s"}`;

export function cardScoreView(key: string, data: CategoryScores | undefined, opts: { canSee: boolean; loading: boolean; failed: boolean }): CardScoreView {
  if (!opts.canSee || data?.locked) return { kind: "locked" };
  if (opts.loading && !data) return { kind: "loading" };
  if (!data) return opts.failed ? { kind: "unavailable" } : { kind: "loading" };
  if (!data.runDate) return { kind: "notRun" };
  const c = data.items[key];
  if (!c || !(c.n > 0) || c.median == null) return { kind: "none" };
  const band = scoreBand(c.median);
  return { kind: "scored", median: scoreText(c.median), band, n: c.n, line: medianLine(c.median, c.n), shares: bandShares(c),
    label: `Health score of Direct-plan funds: ${medianLine(c.median, c.n)}. ${c.green} green, ${c.orange} orange, ${c.red} red.` };
}

/** The funds list for a card, ordered by the Health score, best-scoring first (Gold; the server refuses that order below). Direct plan is the list's default. */
export const scoreSortHref = (c: Pick<Card, "tab" | "key">): string => `/funds?${new URLSearchParams({ tab: c.tab, cats: c.key, sort: "score", dir: "desc" })}`;
