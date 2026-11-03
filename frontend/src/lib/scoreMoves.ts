/**
 * "How the scores have moved": pure helpers for the combined history of the four Prism scores (0 to 100) and the two technical views (−100 to +100).
 * Same input, same words. It describes how figures moved; it never forecasts and never advises.
 */
import { valueOf, withValue, type HistPoint, type Series } from "./prismHistory";
import { trendWord } from "./scoreScreen";

export type Period = "1M" | "3M" | "6M" | "1Y";
export const PERIODS: { id: Period; days: number; words: string }[] = [
  { id: "1M", days: 31, words: "month" }, { id: "3M", days: 92, words: "3 months" }, { id: "6M", days: 183, words: "6 months" }, { id: "1Y", days: 366, words: "year" },
];
export type Show = "all" | "business" | "technical";
export const BUSINESS: Series[] = ["fundamental", "valuation", "quality", "risk"];
export const TECHNICAL: Series[] = ["shortTerm", "longTerm"];
export const seriesFor = (show: Show): Series[] => (show === "business" ? BUSINESS : show === "technical" ? TECHNICAL : [...BUSINESS, ...TECHNICAL]);
export const isTechnical = (s: Series) => s === "shortTerm" || s === "longTerm";

const DAY = 86_400_000;
/** The points in the last `period` counted back from the newest recorded day (never from today: a gap in recording is not filled in). */
export function inPeriod(points: HistPoint[], period: Period): HistPoint[] {
  if (!points.length) return [];
  const last = Date.parse(points[points.length - 1].day), from = last - PERIODS.find((p) => p.id === period)!.days * DAY;
  return points.filter((p) => Date.parse(p.day) >= from);
}

/** The site's band words for a 0-100 Prism score (Strong 80 and above, Healthy 65, Average 50, Weak 35, Poor below). */
export const bandWord = (v: number): string => (v >= 80 ? "Strong" : v >= 65 ? "Healthy" : v >= 50 ? "Average" : v >= 35 ? "Weak" : "Poor");
/** The site's own descriptive words for a technical view (−100 to +100), the same as on the screeners and the report. */
export const trendBand = (v: number): string => trendWord(v) ?? "—";
export const readingNow = (s: Series, v: number): string => (isTechnical(s) ? trendBand(v) : bandWord(v));

export type Move = { s: Series; from: number; to: number; delta: number; fromDay: string; toDay: string };
/** First and newest figure of each series in the window (a series needs two figures to have a move). */
export function movesOf(points: HistPoint[], series: Series[]): Move[] {
  const out: Move[] = [];
  for (const s of series) {
    const v = withValue(points, s); if (v.length < 2) continue;
    const a = valueOf(v[0], s)!, b = valueOf(v[v.length - 1], s)!;
    out.push({ s, from: a, to: b, delta: Math.round((b - a) * 10) / 10, fromDay: v[0].day, toDay: v[v.length - 1].day });
  }
  return out;
}

export const NAME: Record<Series, string> = { final: "Prism", fundamental: "Growth & Profitability", valuation: "Valuation", quality: "Quality", risk: "Risk", shortTerm: "Short-term view", longTerm: "Long-term view" };
const num = (v: number) => (v < 0 ? "−" : "") + String(Math.abs(Math.round(v * 10) / 10));
const pts = (n: number) => `${num(Math.abs(n))} point${Math.abs(n) === 1 ? "" : "s"}`;

/** The one-sentence summary above the chart: the biggest mover and the steadiest score in the window. */
export function moveSentence(points: HistPoint[], series: Series[], period: Period): string {
  const mv = movesOf(points, series), when = PERIODS.find((p) => p.id === period)!.words;
  const lead = `Over the last ${when === "month" || when === "year" ? when : when}`;
  if (!mv.length) return "There are not enough recorded days in this period to say how the scores moved.";
  const abs = (m: Move) => Math.abs(m.delta), biggest = [...mv].sort((a, b) => abs(b) - abs(a))[0];
  const word = (m: Move, v: number) => (isTechnical(m.s) ? trendBand(v).toLowerCase() : bandWord(v).toLowerCase());
  const label = (m: Move) => (isTechnical(m.s) ? NAME[m.s] : `${NAME[m.s]} score`);
  if (abs(biggest) === 0) return `${lead}, none of the ${mv.length === 1 ? "" : mv.length + " "}${mv.length === 1 ? "scores" : "scores"} changed: ${mv.map((m) => `${NAME[m.s]} ${num(m.to)}`).join(", ")}.`;
  const rest = mv.filter((m) => m !== biggest);
  const first = `${lead}, the ${label(biggest)} ${biggest.delta > 0 ? "rose" : "fell"} ${pts(biggest.delta)}, from ${num(biggest.from)} to ${num(biggest.to)} (${word(biggest, biggest.to)}).`;
  if (!rest.length) return first;
  const steady = [...rest].sort((a, b) => abs(a) - abs(b))[0];
  return `${first} The ${label(steady)} was the steadiest, ${steady.delta === 0 ? `unchanged at ${num(steady.to)}` : `moving ${pts(steady.delta)}`}.`;
}

/** Days on which a Prism re-rating moved at least one of the four business scores (they change only then, so they move in steps). */
export function reRated(points: HistPoint[]): string[] {
  const out: string[] = [];
  for (let i = 1; i < points.length; i++) if (BUSINESS.some((s) => { const a = valueOf(points[i - 1], s), b = valueOf(points[i], s); return a != null && b != null && a !== b; })) out.push(points[i].day);
  return out;
}
