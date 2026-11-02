/**
 * Plain-words reading of every Chart builder chart that is not a scatter (the scatter has its own, lib/chartInference.ts).
 * Built only from the numbers on the chart (no model, no network); the same input always gives the same text. It describes what the figures did:
 * where they started and ended, the highest and lowest, how often they rose, the biggest single move, and (for two lines) how closely they moved together.
 * It never predicts and never advises. A period with no figure is skipped and counted, never filled in.
 */
import { bandOf } from "./chartInference";
import { pearson } from "./graphData";
import { fmtValue, type Pt, type UnitId } from "./graphMetrics";

export type ReadLine = { text: string; warn?: boolean };
export type Reading = { headline: string; lines: ReadLine[]; closing: string };
export type ReadSeries = { label: string; unit: UnitId; pts: Pt[] };

export const READING_CLOSING = "Describes what the figures did; it is not a forecast or a recommendation. Information only, not investment advice.";
const lab = (p: Pt) => p.l ?? p.t.slice(0, 10);
const num = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
const plural = (n: number, one: string, many = one + "s") => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
const sgn = (v: number) => (v < 0 ? "−" : "+");

/** "up 8.4%" / "down 3.1%" / "up 2.5 percentage points": a % of a percentage is never quoted, and a start at or below zero has no % change. */
export function moved(from: number, to: number, unit: UnitId): string {
  const d = to - from;
  if (d === 0) return "unchanged";
  const dir = d > 0 ? "up" : "down";
  if (unit === "pct") return `${dir} ${Math.abs(d).toFixed(2)} percentage points`;
  if (from <= 0 || unit === "x") return `${dir} ${fmtValue(Math.abs(d), unit).replace(/^[+−]/, "")}`;
  return `${dir} ${Math.abs((d / from) * 100).toFixed(1)}%`;
}

type Valid = { p: Pt; v: number };
const valid = (pts: Pt[]): Valid[] => pts.filter((p) => num(p.v)).map((p) => ({ p, v: p.v as number }));

/** Reading of one or more lines / bars / areas over time. `periodic` = one point per year or quarter, otherwise dense prices. */
export function readTimeSeries(series: ReadSeries[], basis: "annual" | "quarterly", opts: { change?: boolean } = {}): Reading | null {
  const usable = series.map((s) => ({ s, v: valid(s.pts), all: s.pts.length })).filter((x) => x.v.length >= 2);
  if (!usable.length) return null;
  const lines: ReadLine[] = [];
  for (const { s, v, all } of usable) {
    const first = v[0], last = v[v.length - 1];
    const dense = v.length > 60;
    const unit = s.unit;
    const mv = opts.change ? null : moved(first.v, last.v, unit);
    lines.push({ text: opts.change
      ? `${s.label}: the latest figure is ${fmtValue(last.v, unit)} (${lab(last.p)}), against ${fmtValue(first.v, unit)} at the start of the window (${lab(first.p)}).`
      : `${s.label} went from ${fmtValue(first.v, unit)} (${lab(first.p)}) to ${fmtValue(last.v, unit)} (${lab(last.p)}), ${mv}.` });
    let hi = v[0], lo = v[0];
    for (const x of v) { if (x.v > hi.v) hi = x; if (x.v < lo.v) lo = x; }
    if (hi.v !== lo.v) lines.push({ text: `Highest: ${fmtValue(hi.v, unit)} (${lab(hi.p)}). Lowest: ${fmtValue(lo.v, unit)} (${lab(lo.p)}).${last === hi ? " The latest figure is the highest in the window." : last === lo ? " The latest figure is the lowest in the window." : ""}` });
    else lines.push({ text: `Every figure in the window is ${fmtValue(hi.v, unit)}: it did not change.` });
    if (!dense) {
      let up = 0, down = 0, big = { d: 0, at: v[1] };
      for (let i = 1; i < v.length; i++) {
        const d = v[i].v - v[i - 1].v;
        if (d > 0) up++; else if (d < 0) down++;
        const rel = v[i - 1].v !== 0 && unit !== "pct" ? d / Math.abs(v[i - 1].v) : d;
        if (Math.abs(rel) > Math.abs(big.d)) big = { d: rel, at: v[i] };
      }
      const word = basis === "annual" ? "year" : "quarter";
      lines.push({ text: `It rose in ${plural(up, word)} and fell in ${plural(down, word)} out of ${v.length - 1}.${big.d !== 0 ? ` The biggest single move was ${unit === "pct" ? `${sgn(big.d)}${Math.abs(big.d).toFixed(2)} percentage points` : `${sgn(big.d)}${Math.abs(big.d * 100).toFixed(1)}%`} in ${lab(big.at.p)}.` : ""}` });
    } else {
      let up = 0;
      for (let i = 1; i < v.length; i++) if (v[i].v > v[i - 1].v) up++;
      const peak = v.reduce((m, x) => (x.v > m.v ? x : m), v[0]);
      const dd = last.v < peak.v ? ((last.v / peak.v) - 1) * 100 : 0;
      lines.push({ text: `${v.length.toLocaleString("en-IN")} readings, ${lab(first.p)} to ${lab(last.p)}; ${Math.round((up / (v.length - 1)) * 100)}% of the readings were higher than the one before.${dd < -0.05 ? ` The latest is ${Math.abs(dd).toFixed(1)}% below the highest in the window.` : ""}` });
    }
    if (all > v.length) lines.push({ text: `${plural(all - v.length, "period")} have no figure and are skipped, not filled in.`, warn: true });
    if (v.length < 5) lines.push({ text: `Only ${v.length} figures: treat any pattern as a hint.`, warn: true });
  }
  if (usable.length >= 2 && !opts.change) {
    const a = usable[0], b = usable[1];
    const byT = new Map(b.v.map((x) => [x.p.t, x.v]));
    const xs: number[] = [], ys: number[] = [];
    for (const x of a.v) { const y = byT.get(x.p.t); if (y != null) { xs.push(x.v); ys.push(y); } }
    const c = pearson(xs, ys);
    if (c.r != null) lines.push({ text: `${a.s.label} and ${b.s.label} moved ${c.r >= 0 ? "together" : "in opposite directions"} on ${c.n} shared dates: r = ${c.r.toFixed(2).replace("-", "−")} (${bandOf(c.r).word}). Two lines that both trend over time often look related; this is not proof that one drives the other.` });
    else if (c.n > 0) lines.push({ text: c.why ?? "Too few shared dates to compare the two lines.", warn: true });
  }
  const f = usable[0];
  const head = usable.length === 1
    ? `${f.s.label} ${f.v[f.v.length - 1].v >= f.v[0].v ? (f.v[f.v.length - 1].v === f.v[0].v ? "ended where it started" : "ended higher than it started") : "ended lower than it started"} over ${lab(f.v[0].p)} to ${lab(f.v[f.v.length - 1].p)}.`
    : `${usable.length} series over ${lab(f.v[0].p)} to ${lab(f.v[f.v.length - 1].p)}, each described below.`;
  return { headline: head, lines, closing: READING_CLOSING };
}

/** A pie or breakdown: the largest part, the top three together, and how spread out the whole is. */
export function readBreakdown(label: string, cats: { name: string; value: number }[]): Reading | null {
  const c = cats.filter((x) => num(x.value) && x.value > 0).sort((a, b) => b.value - a.value);
  const total = c.reduce((s, x) => s + x.value, 0);
  if (c.length < 2 || total <= 0) return null;
  const pc = (x: number) => ((x / total) * 100).toFixed(1) + "%";
  const lines: ReadLine[] = [{ text: `${c[0].name} is the largest part at ${pc(c[0].value)}${c[1] ? `, then ${c[1].name} at ${pc(c[1].value)}` : ""}.` }];
  if (c.length >= 4) lines.push({ text: `The top three together make up ${pc(c[0].value + c[1].value + c[2].value)} of the whole; ${c.length - 3 === 1 ? "the other part has" : `the other ${c.length - 3} parts share`} ${pc(total - c[0].value - c[1].value - c[2].value)}.` });
  const hhi = c.reduce((s, x) => s + (x.value / total) ** 2, 0);
  lines.push({ text: hhi >= 0.5 ? "The whole rests mostly on one part." : hhi >= 0.25 ? "A few parts carry most of the whole." : "The whole is spread over many parts." });
  return { headline: `${label}: ${c.length} parts, led by ${c[0].name} (${pc(c[0].value)}).`, lines, closing: READING_CLOSING };
}

/** Horizontal bars (latest value of each series, or a breakdown): leader, trailer and the gap between them. */
export function readBars(rows: { label: string; v: number }[], unit: UnitId): Reading | null {
  const r = rows.filter((x) => num(x.v));
  if (r.length < 2) return null;
  const s = [...r].sort((a, b) => b.v - a.v), top = s[0], bot = s[s.length - 1];
  const lines: ReadLine[] = [{ text: `${top.label} is the highest at ${fmtValue(top.v, unit)}; ${bot.label} is the lowest at ${fmtValue(bot.v, unit)}.` }];
  if (bot.v > 0 && unit !== "pct") lines.push({ text: `The highest is ${(top.v / bot.v).toFixed(1)} times the lowest.` });
  else lines.push({ text: `The gap between them is ${fmtValue(top.v - bot.v, unit).replace(/^[+−]/, "")}.` });
  return { headline: `${top.label} leads ${r.length - 1} other${r.length - 1 === 1 ? "" : "s"} on the latest figure.`, lines, closing: READING_CLOSING };
}

/** Candlesticks: the range, the net move and the largest day. */
export function readCandles(pts: Pt[]): Reading | null {
  const c = pts.filter((p) => num(p.v) && num(p.h) && num(p.lo));
  if (c.length < 2) return null;
  const first = c[0], last = c[c.length - 1];
  const hi = c.reduce((m, p) => ((p.h as number) > (m.h as number) ? p : m), c[0]), lo = c.reduce((m, p) => ((p.lo as number) < (m.lo as number) ? p : m), c[0]);
  const lines: ReadLine[] = [
    { text: `The last close is ${fmtValue(last.v, "inr")} (${lab(last)}), ${moved(first.v as number, last.v as number, "inr")} from the first close in the window (${fmtValue(first.v, "inr")}, ${lab(first)}).` },
    { text: `The highest price in the window is ${fmtValue(hi.h, "inr")} (${lab(hi)}); the lowest is ${fmtValue(lo.lo, "inr")} (${lab(lo)}).` },
  ];
  let big = c[0], bigR = 0;
  for (const p of c) { const o = p.o as number; if (num(o) && o !== 0) { const r = Math.abs(((p.v as number) - o) / o); if (r > bigR) { bigR = r; big = p; } } }
  if (bigR > 0) lines.push({ text: `The largest move from open to close in one candle was ${(bigR * 100).toFixed(1)}% (${lab(big)}).` });
  return { headline: `${c.length.toLocaleString("en-IN")} candles, ${lab(first)} to ${lab(last)}.`, lines, closing: READING_CLOSING };
}

/** A correlation matrix: the pair that moved most closely together, the pair least alike, and how many pairs were too thin to judge. */
export function readCorrelationMatrix(labels: string[], r: (number | null)[][], n: number[][]): Reading | null {
  const pairs: { a: string; b: string; r: number; n: number }[] = [];
  let thin = 0;
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const v = r[i]?.[j];
    if (v == null) thin++; else pairs.push({ a: labels[i], b: labels[j], r: v, n: n[i]?.[j] ?? 0 });
  }
  if (!pairs.length) return null;
  const strongest = pairs.reduce((m, x) => (Math.abs(x.r) > Math.abs(m.r) ? x : m), pairs[0]);
  const weakest = pairs.reduce((m, x) => (Math.abs(x.r) < Math.abs(m.r) ? x : m), pairs[0]);
  const f = (x: number) => x.toFixed(2).replace("-", "−");
  const lines: ReadLine[] = [{ text: `The closest pair is ${strongest.a} and ${strongest.b}: r = ${f(strongest.r)} (${bandOf(strongest.r).word}, ${strongest.r >= 0 ? "moving together" : "moving in opposite directions"}), over ${strongest.n} shared dates.` }];
  if (pairs.length > 1) lines.push({ text: `The least alike is ${weakest.a} and ${weakest.b}: r = ${f(weakest.r)} (${bandOf(weakest.r).word}).` });
  if (thin) lines.push({ text: `${plural(thin, "pair")} had too few shared dates (or no variation) to compare.`, warn: true });
  lines.push({ text: "Series that both trend over time often look related; correlation is not causation." });
  return { headline: `${pairs.length} pairs compared across ${labels.length} series.`, lines, closing: READING_CLOSING };
}
