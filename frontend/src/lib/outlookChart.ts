// Profit and revenue outlook chart: the pure parts (series split, joint point, y-axis ticks and units, label thinning, text summary, CSV rows).
// Drawn by charts/OutlookChart.tsx. Reported years are solid, estimate years dashed; the estimate line starts at the last reported point.
import { MINUS, nf } from "./format";
import { labelEvery } from "./chartAxis";
import { csvRow } from "./graphData";
import { KIND_LABEL, type HistoryPoint, type Kind, type YearRow } from "./outlook";

export type ChartPoint = { period: string; value: number | null; status: "actual" | "estimate"; alt: number | null; adjusted: boolean; reported: number | null };
export type Series = {
  points: ChartPoint[];
  lastActual: number;          // index of the last reported point that has a value (the joint with the estimate line); -1 when none
  firstEstimate: number;       // index of the first estimate year; -1 when there is no estimate
  hasAlt: boolean;
};

/** Reported years (history, oldest first) followed by the estimate years. `alt` is a second estimate (the model's, when the user's own weights are in use) for the same years. */
export function buildSeries(history: HistoryPoint[], estimate: YearRow[] | null | undefined, alt?: YearRow[] | null): Series {
  const points: ChartPoint[] = history.map((h) => ({ period: h.period, value: h.valueCr, status: "actual", alt: null, adjusted: h.adjusted, reported: h.reportedCr }));
  let lastActual = -1;
  points.forEach((p, i) => { if (p.value != null) lastActual = i; });
  const est = lastActual >= 0 && lastActual === points.length - 1 ? estimate ?? [] : [];   // an estimate continues only from a reported latest year
  est.forEach((y, k) => points.push({ period: y.period, value: y.valueCr, status: "estimate", alt: alt?.[k]?.valueCr ?? null, adjusted: false, reported: null }));
  return { points, lastActual, firstEstimate: est.length ? points.length - est.length : -1, hasAlt: !!alt && est.length > 0 && alt.length === est.length };
}

/** Change of point `i` against the previous year (annual figures: the previous period and the same period a year earlier are the same). */
export function changeVs(points: ChartPoint[], i: number): { abs: number; pct: number | null } | null {
  const a = points[i]?.value, b = points[i - 1]?.value;
  if (a == null || b == null) return null;
  return { abs: a - b, pct: b > 0 ? (a / b - 1) * 100 : null };
}

// ---------------------------------------------------------------------------------------------------------- axis
/** Round axis for [lo, hi]: about `target` ticks at 1, 2, 2.5 or 5 times a power of ten. Zero is a tick whenever the data crosses it. */
export function niceTicks(lo: number, hi: number, target = 5): { min: number; max: number; step: number; ticks: number[] } {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { min: 0, max: 1, step: 0.25, ticks: [0, 0.25, 0.5, 0.75, 1] };
  if (hi === lo) { const pad = Math.abs(hi) * 0.1 || 1; lo -= pad; hi += pad; }
  const raw = (hi - lo) / Math.max(1, target - 1), pow = 10 ** Math.floor(Math.log10(raw)), f = raw / pow;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * pow;
  const min = Math.floor(lo / step + 1e-9) * step, max = Math.ceil(hi / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = min, k = 0; v <= max + step / 1e6 && k < 40; v += step, k++) ticks.push(Math.abs(v) < step / 1e6 ? 0 : +v.toFixed(10));
  return { min, max, step, ticks };
}

/** The y-range: from zero (so the size of a change is not exaggerated), or from a rounded floor when every value is far above zero. Always holds the zero line when a value is negative. */
export function chartDomain(values: number[]): { min: number; max: number; step: number; ticks: number[] } {
  if (!values.length) return niceTicks(0, 1);
  const lo = Math.min(...values), hi = Math.max(...values);
  if (lo < 0) return niceTicks(lo, Math.max(hi, 0));
  if (hi > 0 && lo >= 0.6 * hi) return niceTicks(lo - (hi - lo) * 0.5, hi + (hi - lo) * 0.1 || hi * 0.05);
  return niceTicks(0, hi);
}

/** Axis unit: lakh crore (1,00,000 crore) once the largest figure is that big, else crore. `fmt` prints a tick with just enough decimals. */
export function axisUnit(maxAbs: number, step: number): { name: string; fmt: (v: number) => string } {
  const lakh = maxAbs >= 100000, div = lakh ? 100000 : 1, s = step / div;
  let dec = 0;
  while (dec < 3 && Math.abs(s * 10 ** dec - Math.round(s * 10 ** dec)) > 1e-6) dec++;   // just enough decimals to tell the ticks apart
  return { name: lakh ? "₹ lakh crore" : "₹ crore", fmt: (v) => (v < 0 ? MINUS : "") + nf(v / div, dec) };
}

/** A figure in words: ₹43,851 Cr, or ₹1.23 lakh crore from one lakh crore. */
export const fmtCr = (v: number | null | undefined) => (v == null ? "—" : `${v < 0 ? MINUS : ""}₹${Math.abs(v) >= 100000 ? nf(Math.abs(v) / 100000, 2) + " lakh crore" : nf(Math.abs(v), 0) + " Cr"}`);
export const fmtChange = (c: { abs: number; pct: number | null } | null) => (c == null ? "not available" : `${c.abs >= 0 ? "up" : "down"} ${fmtCr(Math.abs(c.abs))}${c.pct == null ? "" : ` (${c.pct >= 0 ? "+" : MINUS}${nf(Math.abs(c.pct), 1)}%)`}`);

/** Which x labels to print so none collide: every `n`th counted back from the last point. Returns a predicate on the index. */
export function labelIndices(count: number, plotWidth: number, longest: number): (i: number) => boolean {
  const every = labelEvery(count, plotWidth, longest, 6.4, 12);
  return (i) => (count - 1 - i) % every === 0;
}

// ---------------------------------------------------------------------------------------------------------- text
export function chartSummary(kind: Kind, s: Series, who: string): string {
  const name = KIND_LABEL[kind], act = s.points.filter((p) => p.status === "actual" && p.value != null), est = s.points.filter((p) => p.status === "estimate");
  if (!act.length) return `${name}: no reported figures are stored for this company.`;
  const l = act[act.length - 1], first = act[0];
  const i = s.points.indexOf(l), ch = changeVs(s.points, i);
  let t = `${name}: reported ${fmtCr(l.value)} in ${l.period}${ch ? `, ${fmtChange(ch)} on the year before` : ""}; ${act.length} reported years from ${first.period}.`;
  if (est.length) t += ` Estimate: ${est.map((p) => `${fmtCr(p.value)} for ${p.period}`).join(", ")} (${who}). An estimate from the company's own history and its sector, not a prediction.`;
  else t += " No estimate is shown for this company.";
  return t;
}

export const tooltipText = (s: Series, i: number): string => {
  const p = s.points[i];
  if (!p || p.value == null) return p ? `${p.period}: not reported.` : "";
  const ch = changeVs(s.points, i);
  return `${p.period}, ${p.status === "actual" ? "reported" : "estimate"} ${fmtCr(p.value)}${ch ? `, ${fmtChange(ch)} on the year before` : ""}${p.alt != null ? `; FinLit model ${fmtCr(p.alt)}` : ""}${p.adjusted ? `; adjusted for one-off items (reported ${fmtCr(p.reported)})` : ""}`;
};

/** Rows of the chart's own table (and its CSV): period, status, value, change on the year before, and the second estimate when drawn. */
export function tableRows(s: Series): (string | number)[][] {
  return s.points.map((p, i) => {
    const ch = changeVs(s.points, i);
    return [p.period, p.value == null ? "Not reported" : p.status === "actual" ? "Reported" : "Estimate", p.value == null ? "—" : fmtCr(p.value), ch ? fmtChange(ch).replace(/^(up|down) /, (m) => (m === "up " ? "+" : MINUS)) : "—", ...(s.hasAlt ? [p.alt == null ? "—" : fmtCr(p.alt)] : [])];
  });
}

export function chartCsv(kind: Kind, symbol: string, s: Series, who: string, horizonLabel: string): string {
  const rows: (string | number | null)[][] = [
    [`${KIND_LABEL[kind]} of ${symbol}, Rs crore. Reported years are from the company's results; estimate years come from ${who} and ${horizonLabel} horizon. Estimates from past results, not a prediction or advice.`],
    ["Period", "Type", "Value (Rs crore)", "Change on year before (%)", ...(s.hasAlt ? ["FinLit model estimate (Rs crore)"] : []), "Note"],
  ];
  s.points.forEach((p, i) => {
    const ch = changeVs(s.points, i);
    rows.push([p.period, p.value == null ? "Not reported" : p.status === "actual" ? "Reported" : "Estimate", p.value, ch?.pct == null ? null : +ch.pct.toFixed(2), ...(s.hasAlt ? [p.alt] : []), p.adjusted ? `Adjusted for one-off items; reported figure ${p.reported ?? ""}` : ""]);
  });
  return "﻿" + rows.map(csvRow).join("\n");
}
