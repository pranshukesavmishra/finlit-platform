// FinLit Prism card on the stock page: the pure rules behind its drawing (ring geometry, words, captions, sentences). No React here, so every rule has a test.
// Nothing is calculated that the report does not state: the weights, the scores, the horizons and the trend alignment all come from the stored report and the shared wording file.
import { scoreBand, type ScoreBand } from "../lib/scoreBands";
import { BANDS, fmtScore, ratingWord, scalePos, type TechHorizon, type TrendAlignment } from "../lib/prismTechnical";

/** Words for a part's score, on the same scale as the overall label (Poor < 35 <= Weak < 50 <= Average < 65 <= Healthy < 80 <= Strong). The word carries the meaning; colour only decorates. */
export const partWord = (v: number | null | undefined): [word: string, tone: "strong" | "healthy" | "mixed" | "weak" | "na"] =>
  v == null || !Number.isFinite(v) ? ["No data", "na"] : v >= 80 ? ["Strong", "strong"] : v >= 65 ? ["Healthy", "healthy"] : v >= 50 ? ["Average", "mixed"] : v >= 35 ? ["Weak", "weak"] : ["Poor", "weak"];

/** A component to draw: its name, its share of the score in percent, the CSS variable of its own colour and its score (null: no data). */
export type CardPart = { key: string; name: string; weight: number; color: string; value: number | null };

/** One line per part, in words that match what the model actually measures (lib/prism.ts PART_TEXT says the same at more length). */
export const PART_LINE: Record<string, string> = {
  fundamental: "Sales and profit growth, steadiness and margins",
  valuation: "Share price against earnings and its own history",
  quality: "Borrowing, interest cover, returns, cash backing",
  risk: "Price swings, largest fall, trading activity, pledged shares",
  technical: "Price trend and momentum signals",
};

/** "Valuation 42 of 100: Weak. Counts for 30% of the overall score." Used as the tooltip and as the accessible name of a component card and of its ring arc. */
export function partTip(name: string, value: number | null, word: string, weight: number | null): string {
  const w = weight == null ? "" : ` Counts for ${weight}% of the overall score.`;
  return value == null ? `${name}: no data.${w}` : `${name} ${fmtNum(value)} of 100: ${word}.${w}`;
}
/** A component score as the card shows it: a whole number (the overall score keeps one decimal). */
export const fmtNum = (v: number): string => String(Math.round(v));

/* ------------------------------------------------------------------ ring geometry */
export type RingPart = { key: string; weight: number; value: number | null };
export type RingArc = { key: string; /** start and end of the arc's whole span, degrees clockwise from 12 o'clock (gaps already taken off) */ a0: number; a1: number; /** the span's share of the ring, 0..1 */ share: number; /** end of the coloured part (where the score reaches), degrees */ aFill: number; band: ScoreBand; value: number | null };
export const RING_GAP = 7;   // degrees left open between two arcs

/** One arc per part: its length is its share of the total weight (any positive numbers; percent or fractions), the coloured part is the part's score out of 100, the colour follows the shared band rule. */
export function ringArcs(parts: RingPart[], gap = RING_GAP): RingArc[] {
  const total = parts.reduce((s, p) => s + Math.max(0, p.weight), 0) || 1;
  let at = 0;
  return parts.map((p) => {
    const span = (Math.max(0, p.weight) / total) * 360;
    const a0 = at + gap / 2, a1 = Math.max(a0 + 0.5, at + span - gap / 2);
    at += span;
    const v = p.value == null || !Number.isFinite(p.value) ? null : Math.max(0, Math.min(100, p.value));
    return { key: p.key, a0, a1, share: span / 360, aFill: a0 + ((a1 - a0) * (v ?? 0)) / 100, band: scoreBand(v), value: v };
  });
}
/** A point on a circle of radius r around (cx, cy); 0 degrees is 12 o'clock, clockwise. */
export const polar = (cx: number, cy: number, r: number, deg: number): [number, number] => { const a = ((deg - 90) * Math.PI) / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
/** SVG path of an arc from a0 to a1 degrees (one sweep, clockwise). */
export function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/* ------------------------------------------------------------------ the heading texts */
const COUNT_WORD = ["no", "one", "two", "three", "four", "five", "six"];
/** "Based on 4 weighted components. Higher is better (a higher Risk score means lower risk)." The Risk clause appears only when a Risk part is drawn. */
export function basedOn(n: number, hasRisk: boolean): string {
  return `Based on ${n} weighted component${n === 1 ? "" : "s"}. Higher is better${hasRisk ? " (a higher Risk score means lower risk)" : ""}.`;
}
/** "Evaluates business and financial strength using key metrics across four areas." */
export const fundSubtitle = (n: number): string => `Evaluates business and financial strength using key metrics across ${COUNT_WORD[n] ?? n} areas.`;
export const FUND_NOTE = "Fundamental score evaluates a company's business and financial strength. Technical indicators assess price trend and momentum separately and are not included in this score.";
/** If the model ever sends a technical part, it is part of the score, and the note must not say it is not. */
export const SCORE_NOTE_WITH_TECH = "The score is the weighted total of the components shown, each counted by its share.";
export const TECH_SUBTITLE = "Assesses price trend and momentum using technical indicators.";
export const TECH_SEPARATE_NOTE = "Technical analysis is not included in the fundamental score. It is shown separately to help assess price trend and momentum.";

/* ------------------------------------------------------------------ technical horizons */
/** The scale under each bar: where the labels sit (percent along the -100..+100 scale) and the band edges that get a tick, from the shared BANDS. */
export const TECH_EDGES = [BANDS.negative, BANDS.neutral, BANDS.positive, BANDS.strongPositive];
export const techEdgePos = (): number[] => TECH_EDGES.map((e) => scalePos(e));

/** "5–20 sessions" and "6–18 months" come from the report itself; nothing is assumed when it does not say. */
export const horizonCaption = (h: Pick<TechHorizon, "horizon">): string | null => h.horizon?.trim() || null;
/** "14 of 14 signals available", or null when the report counts none. */
export function signalsLine(h: Pick<TechHorizon, "availableCount" | "requiredCount">): string | null {
  return h.requiredCount > 0 ? `${h.availableCount} of ${h.requiredCount} signals available` : null;
}
/** What a screen reader hears for one horizon panel. */
export function horizonLabel(title: string, h: TechHorizon): string {
  const cap = horizonCaption(h), sig = signalsLine(h);
  if (h.score == null) return `${title}${cap ? ` (${cap})` : ""}: not available${sig ? `. ${sig}` : ""}.`;
  return `${title}${cap ? ` (${cap})` : ""}: ${fmtScore(h.score)} on a scale from minus 100 to plus 100, ${ratingWord(h.rating, h.score).word.toLowerCase()}.${sig ? ` ${sig}.` : ""}`;
}

/** The sentence under the trend alignment label, built only from the two bands the alignment already states. */
export function alignSentence(al: Pick<TrendAlignment, "stBand" | "ltBand" | "stBandWord" | "ltBandWord">): string {
  const s = al.stBandWord.toLowerCase(), l = al.ltBandWord.toLowerCase();
  return al.stBand === al.ltBand ? `Both the short-term and the long-term trend are ${s}.` : `The short-term trend is ${s}, while the long-term trend is ${l}.`;
}
