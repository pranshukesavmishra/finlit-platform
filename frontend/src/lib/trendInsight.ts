// What the Trends cards say about a series, worked out from the very numbers the chart draws. Pure functions, no estimates:
// every figure in a sentence is read from the series passed in. The wording describes; it never advises.
import { MINUS, nf } from "./format";

export type Mode = "q" | "a";
export type Tone = "up" | "down" | "flat" | "none";
type Num = number | null | undefined;
export type Line = { text: string; tone: Tone };

export const NEUTRAL = "Not enough history to describe the trend.";

const ok = (v: Num): v is number => v != null && Number.isFinite(v);
/** Calendar-year short form of a period label: "Sep 2526" -> "Sep '26"; "FY26" stays. */
export const shortPeriod = (l: string) => l.replace(/^(\w{3}) (\d{2})(\d{2})$/, "$1 '$3");

/** Position of the newest reported figure (the highlighted bar), or -1. */
export const lastIndex = (v: Num[]): number => { for (let i = v.length - 1; i >= 0; i--) if (ok(v[i])) return i; return -1; };
/** Position of the figure a year earlier: four quarters back, or one year back. -1 when it is not reported. */
export const yearAgoIndex = (v: Num[], i: number, mode: Mode): number => { const r = i - (mode === "q" ? 4 : 1); return i >= 0 && r >= 0 && ok(v[r]) ? r : -1; };

export type Change =
  | { how: "none"; i: number; r: number; why: string }
  | { how: "pct" | "points"; i: number; r: number; cur: number; prev: number; amount: number; tone: Tone }
  | { how: "shift"; i: number; r: number; cur: number; prev: number; to: "positive" | "negative"; tone: Tone }
  | { how: "negneg"; i: number; r: number; cur: number; prev: number; tone: Tone };

/** Latest figure against the same period a year earlier. `ratio` series (margins, returns) change in percentage points; money series in per cent.
 *  A move across zero, or between two negatives, has no meaningful per-cent figure, so it is named instead of computed. */
export function yoyChange(v: Num[], mode: Mode, ratio = false): Change {
  const i = lastIndex(v);
  if (i < 0) return { how: "none", i, r: -1, why: "No reported figure." };
  const r = yearAgoIndex(v, i, mode);
  if (r < 0) return { how: "none", i, r, why: "No figure a year earlier to compare with." };
  const cur = v[i] as number, prev = v[r] as number;
  if (ratio) { const d = cur - prev, a = Math.round(Math.abs(d) * 10) / 10; return { how: "points", i, r, cur, prev, amount: d, tone: a === 0 ? "flat" : d > 0 ? "up" : "down" }; }
  if (prev < 0 && cur > 0) return { how: "shift", i, r, cur, prev, to: "positive", tone: "up" };
  if (prev > 0 && cur < 0) return { how: "shift", i, r, cur, prev, to: "negative", tone: "down" };
  if (prev < 0 && cur <= 0) return { how: "negneg", i, r, cur, prev, tone: cur === prev ? "flat" : cur > prev ? "up" : "down" };
  if (prev === 0) return { how: "none", i, r, why: "The figure a year earlier was zero." };
  const p = ((cur - prev) / prev) * 100, a = Math.round(Math.abs(p) * 10) / 10;
  return { how: "pct", i, r, cur, prev, amount: p, tone: a === 0 ? "flat" : p > 0 ? "up" : "down" };
}

const sgn = (x: number) => (x < 0 ? MINUS : "+");
/** Short text for the badge under the big value (the arrow is drawn by the card). */
export function badgeOf(c: Change): { tone: Tone; text: string; title: string } {
  if (c.how === "none") return { tone: "none", text: "YoY n/a", title: c.why };
  if (c.tone === "flat") return { tone: "flat", text: "Flat YoY", title: "Same as a year earlier." };
  if (c.how === "pct") return { tone: c.tone, text: `${sgn(c.amount)}${nf(c.amount, 1)}% YoY`, title: "Change from the same period a year earlier." };
  if (c.how === "points") return { tone: c.tone, text: `${sgn(c.amount)}${nf(c.amount, 1)} pts YoY`, title: "Change in percentage points from the same period a year earlier." };
  if (c.how === "shift") return { tone: c.tone, text: `Turned ${c.to}`, title: "A year earlier the figure was on the other side of zero." };
  return { tone: c.tone, text: `Negative, ${c.tone === "up" ? "narrower" : "wider"} YoY`, title: "Both periods are below zero, so no per-cent change is given." };
}

/** Rises (or falls) among the last 8 period-to-period steps, e.g. "7 of the last 8"; null when there are fewer than 3 steps. */
function steps(v: Num[], dir: "up" | "down"): { k: number; m: number } | null {
  const pts = v.filter(ok).slice(-9);
  if (pts.length < 4) return null;
  let k = 0;
  for (let j = 1; j < pts.length; j++) if (dir === "up" ? pts[j] > pts[j - 1] : pts[j] < pts[j - 1]) k++;
  return { k, m: pts.length - 1 };
}

export type InsightSpec = {
  kind: "flow" | "ratio" | "pair" | "mix";
  /** Sentence subject, e.g. "Revenue", "EPS". */
  name: string;
  labels: string[];
  mode: Mode;
  series: { label: string; values: Num[] }[];
  /** Amount with its unit, e.g. "₹56,616 Cr" (flow, pair). */
  money: (v: number) => string;
  /** "reached X in FY26, up from Y in FY22" style (compares with the first period drawn) instead of the year-on-year form. */
  since?: boolean;
};

const lower = (s: string) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const lab = (labels: string[], i: number) => shortPeriod(labels[i] ?? "");

function flowLine(s: InsightSpec): Line {
  const v = s.series[0]?.values ?? [], ratio = s.kind === "ratio", c = yoyChange(v, s.mode, ratio);
  if (c.how === "none") return { text: NEUTRAL, tone: "none" };
  const { name } = s, at = lab(s.labels, c.i), was = lab(s.labels, c.r);
  if (ratio && c.how === "points") {
    const word = c.tone === "flat" ? `is unchanged YoY, at ${nf(c.cur, 1)}%` : `is ${nf(c.cur, 1)}%, ${c.tone === "up" ? "up" : "down"} ${nf(Math.abs(c.amount), 1)} points YoY`;
    return { text: `${name} ${word}.`, tone: c.tone };
  }
  if (c.how === "shift") return { text: `${name} turned ${c.to}, from ${s.money(c.prev)} in ${was} to ${s.money(c.cur)} in ${at}.`, tone: c.tone };
  if (c.how === "negneg") return { text: `${name} stayed negative at ${s.money(c.cur)}, against ${s.money(c.prev)} in ${was}.`, tone: c.tone };
  if (c.how !== "pct") return { text: NEUTRAL, tone: "none" };
  if (s.since) {
    const f = v.findIndex(ok);
    if (f >= 0 && f < c.i) { const first = v[f] as number, cur = c.cur; return { text: `${name} reached ${s.money(cur)} in ${at}, ${cur > first ? "up from" : cur < first ? "down from" : "level with"} ${s.money(first)} in ${lab(s.labels, f)}.`, tone: cur > first ? "up" : cur < first ? "down" : "flat" }; }
  }
  if (c.tone === "flat") return { text: `${name} is little changed YoY, at ${s.money(c.cur)}.`, tone: "flat" };
  const up = c.tone === "up", st = steps(v, up ? "up" : "down");
  return { text: `${name} is ${up ? "up" : "down"} ${nf(Math.abs(c.amount), 1)}% YoY${st ? `, ${up ? "rising" : "falling"} in ${st.k} of the last ${st.m} periods` : ""}.`, tone: c.tone };
}

function pairLine(s: InsightSpec, ratio: boolean): Line {
  const parts: { t: string; tone: Tone }[] = [];
  s.series.forEach((x, j) => {
    const c = yoyChange(x.values, s.mode, ratio);
    if (c.how === "none" || c.how === "negneg") return;
    const nm = j === 0 ? x.label : lower(x.label);
    if (c.how === "shift") parts.push({ t: `${nm} turned ${c.to}`, tone: c.tone });
    else if (c.tone === "flat") parts.push({ t: `${nm} was little changed YoY`, tone: "flat" });
    else if (c.how === "points") parts.push({ t: `${nm} ${c.tone === "up" ? "rose" : "fell"} ${nf(Math.abs(c.amount), 1)} points YoY`, tone: c.tone });
    else parts.push({ t: `${nm} ${c.tone === "up" ? "rose" : "fell"} ${nf(Math.abs(c.amount), 1)}% YoY`, tone: c.tone });
  });
  if (!parts.length) return { text: NEUTRAL, tone: "none" };
  const tone: Tone = parts.every((p) => p.tone === parts[0].tone) ? parts[0].tone : "flat";
  return { text: parts.map((p) => p.t).join(", while ") + ".", tone };
}

function mixLine(s: InsightSpec): Line {
  const n = Math.max(0, ...s.series.map((x) => lastIndex(x.values)));
  const items = s.series.map((x) => ({ label: x.label, v: x.values[n] })).filter((x) => ok(x.v) && (x.v as number) > 0) as { label: string; v: number }[];
  const total = items.reduce((a, b) => a + b.v, 0);
  if (items.length < 2 || total <= 0) return { text: NEUTRAL, tone: "none" };
  const top = items.reduce((a, b) => (b.v > a.v ? b : a));
  return { text: `${top.label} is the largest of ${items.length} segments, ${nf((top.v / total) * 100, 1)}% of ${lab(s.labels, n)} revenue.`, tone: "flat" };
}

/** The one-line reading under a Trends chart, or the neutral line when the series cannot support one. */
export function insightLine(s: InsightSpec): Line {
  if (!s.series.length) return { text: NEUTRAL, tone: "none" };
  if (s.kind === "mix") return mixLine(s);
  if (s.kind === "pair") return pairLine(s, false);
  return s.series.length > 1 ? pairLine(s, s.kind === "ratio") : flowLine(s);
}
