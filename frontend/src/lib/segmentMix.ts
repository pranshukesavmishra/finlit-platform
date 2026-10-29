// Pure logic for the "How the mix has changed" views of the revenue-segment card: colours, stacked-chart model, axis ticks and the trend table.
// The trend numbers themselves (CAGR, share change, tags, sentences) come from the server (backend/finlit/normalize/segment_trends.py);
// nothing here recomputes them. A report stored before `insights` existed still gets a chart and a plain table.
import type { SegmentInsights, SegmentTrend, SegmentTrendRow, Segments } from "./api";
import { MINUS, nf } from "./format";

export const MIN_YEARS = 3;
export const OTHERS_COLOR = "var(--faint)";
const PALETTE = ["--k1", "--k2", "--k3", "--k4", "--k5", "--k6", "--k7", "--k8"].map((n) => `var(${n})`);
export const REMAINING = "Remaining segments";

const last = <T,>(a: T[]) => a[a.length - 1];
const pos = (v: number | null | undefined): v is number => v != null && v > 0;
const isOthers = (name: string) => name.trim().toLowerCase() === "others";

/** Every segment of the history, those reporting in the latest year first (largest first), then the ones no longer reported (by their last revenue). */
export function segmentNames(seg: Segments | undefined): string[] {
  const table = seg?.segments || {};
  const lastRev = (n: string) => { const r = table[n]?.revenue || []; for (let i = r.length - 1; i >= 0; i--) if (pos(r[i])) return r[i] as number; return 0; };
  const active = (n: string) => pos(last(table[n]?.revenue || []));
  return Object.keys(table).sort((a, b) => Number(active(b)) - Number(active(a)) || lastRev(b) - lastRev(a));
}

/** One colour per segment, the same everywhere in the card. "Others" is always neutral; named segments take --k1..--k8 in order. Past eight, the rest share one neutral colour and the chart groups them. */
export function segmentColors(names: string[]): { color: Record<string, string>; grouped: string[] } {
  const color: Record<string, string> = {}, grouped: string[] = [];
  let i = 0;
  for (const n of names) {
    if (isOthers(n)) color[n] = OTHERS_COLOR;
    else if (i < PALETTE.length) color[n] = PALETTE[i++];
    else { color[n] = "var(--muted)"; grouped.push(n); i++; }
  }
  return { color, grouped };
}

export type StackSeries = { key: string; label: string; color: string; values: (number | null)[]; shares: (number | null)[]; members?: string[] };
export type ChartModel = { years: string[]; series: StackSeries[]; totals: number[] };

/** Stacked-bar data: values in ₹ Cr and each segment's share of that year's sum of segment revenues. Missing stays null. */
export function chartModel(seg: Segments | undefined): ChartModel {
  const years = seg?.periods || [], table = seg?.segments || {};
  const names = segmentNames(seg), { color, grouped } = segmentColors(names);
  const get = (n: string, i: number) => { const v = table[n]?.revenue?.[i]; return typeof v === "number" && Number.isFinite(v) ? v : null; };
  const totals = years.map((_, i) => names.reduce((a, n) => a + (get(n, i) ?? 0), 0));
  const share = (v: number | null, i: number) => (v == null || totals[i] <= 0 ? null : (v / totals[i]) * 100);
  const series: StackSeries[] = names.filter((n) => !grouped.includes(n)).map((n) => {
    const values = years.map((_, i) => get(n, i));
    return { key: n, label: n, color: color[n], values, shares: values.map(share) };
  });
  if (grouped.length) {
    const values = years.map((_, i) => { const parts = grouped.map((n) => get(n, i)).filter((v): v is number => v != null); return parts.length ? parts.reduce((a, b) => a + b, 0) : null; });
    series.push({ key: REMAINING, label: REMAINING, color: "var(--muted)", values, shares: values.map(share), members: grouped });
  }
  return { years, series, totals };
}

/** Height of one bar's stack: only positive revenues are drawn. */
export const stackTop = (m: ChartModel, i: number, mode: "revenue" | "share") =>
  m.series.reduce((a, s) => a + Math.max(0, (mode === "revenue" ? s.values[i] : s.shares[i]) ?? 0), 0);

/** Round-number axis ticks from 0 up to a "nice" maximum >= max (about `count` steps). */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0) || !Number.isFinite(max)) return [0, 1];
  const raw = max / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) ?? 10) * mag;
  const n = Math.ceil(max / step - 1e-9);
  return Array.from({ length: n + 1 }, (_, i) => +(i * step).toFixed(6));
}

/** Axis label for a crore amount: lakh crore ("2.5 L") from 1,00,000 Cr, otherwise Indian grouping. */
export const axisCr = (v: number) => {
  if (v === 0) return "0";
  if (Math.abs(v) >= 100000) {
    const l = Math.abs(v) / 100000, d = Math.abs(l - Math.round(l)) < 1e-9 ? 0 : Math.abs(l * 10 - Math.round(l * 10)) < 1e-9 ? 1 : 2;
    return (v < 0 ? MINUS : "") + nf(l, d) + " L";
  }
  return (v < 0 ? MINUS : "") + nf(Math.abs(v), 0);
};
export const axisPct = (v: number) => `${nf(v, 0)}%`;

/** "▲ +3.8 pp" / "▼ −0.4 pp" for a change in share or margin. */
export const pp = (n: number | null | undefined, d = 1) => (n == null ? "—" : Math.abs(n) < 0.05 && d === 1 ? "0.0 pp" : (n > 0 ? "▲ +" : "▼ " + MINUS) + nf(n, d) + " pp");
export const cagrText = (n: number | null | undefined) => (n == null ? "—" : (n > 0 ? "+" : n < 0 ? MINUS : "") + nf(n, 1) + "%");

export type MixStatus = "ok" | "short" | "single" | "none";
/** Which empty state (if any) applies. The server's `insights.status` wins; for older reports it is worked out from the table. */
export function mixStatus(seg: Segments | undefined): { status: MixStatus; text: string } {
  const names = Object.keys(seg?.segments || {}), years = seg?.periods?.length || 0;
  if (seg?.insights && ["ok", "short", "single", "none"].includes(seg.insights.status)) {
    const t = seg.insights.statusText;
    return { status: seg.insights.status, text: t || (seg.insights.status === "single" ? "This company reports a single business segment." : seg.insights.status === "none" ? "Segment history is not available for this company." : "") };
  }
  if (!names.length || !years) return { status: "none", text: "Segment history is not available for this company." };
  if (names.length === 1) return { status: "single", text: "This company reports a single business segment." };
  if (years < MIN_YEARS) return { status: "short", text: `Only ${years} year${years === 1 ? "" : "s"} of segment data ${years === 1 ? "is" : "are"} available, so no trends are drawn yet (at least ${MIN_YEARS} comparable years are needed).` };
  return { status: "ok", text: "" };
}

export type TableRow = {
  name: string; color: string; trend: SegmentTrend | null; trendLabel: string | null; revenue: number | null; sharePct: number | null; shareChangePp: number | null;
  cagrPct: number | null; window: [string, string] | null; years: number; yoyPct: number | null; marginPct: number | null; marginChangePp: number | null;
  spark: (number | null)[]; notReported: boolean; lastReported: string | null; lastRevenue: number | null; flag: string | null; note: string | null;
};

/** One row per segment for the trends table: server numbers when `insights` exists, otherwise a plain latest-year row worked out from the series. */
export function tableRows(seg: Segments | undefined): TableRow[] {
  if (!seg) return [];
  const names = segmentNames(seg), { color } = segmentColors(names), table = seg.segments || {};
  const byName = new Map<string, SegmentTrendRow>((seg.insights?.rows || []).map((r) => [r.name, r]));
  const total = (i: number) => names.reduce((a, n) => a + (table[n]?.revenue?.[i] ?? 0), 0);
  const li = (seg.periods?.length || 0) - 1;
  return names.map((name): TableRow => {
    const rev = table[name]?.revenue || [], ebit = table[name]?.ebit || [], r = byName.get(name);
    const base = { name, color: color[name], spark: rev.map((v) => (typeof v === "number" ? v : null)) };
    if (r) {
      const gone = r.trend === "discontinued";
      const flag = r.definitionChanged ? r.definitionNote : null;
      return { ...base, trend: r.trend, trendLabel: r.trendLabel, revenue: gone ? null : r.revenue, sharePct: gone ? null : r.sharePct, shareChangePp: r.shareChangePp, cagrPct: r.cagrPct, window: r.window, years: r.years,
        yoyPct: r.yoyPct, marginPct: r.marginPct, marginChangePp: r.marginChangePp, notReported: gone, lastReported: r.lastReported, lastRevenue: r.lastRevenue ?? null, flag, note: r.note };
    }
    const now = rev[li] ?? null, before = li > 0 ? rev[li - 1] ?? null : null, t = li >= 0 ? total(li) : 0;
    const gone = !pos(now);
    return { ...base, trend: null, trendLabel: null, revenue: gone ? null : now, sharePct: !gone && t > 0 ? ((now as number) / t) * 100 : null, shareChangePp: null, cagrPct: null, window: null, years: 0,
      yoyPct: pos(now) && pos(before) ? ((now as number) / (before as number) - 1) * 100 : null, marginPct: pos(now) && ebit[li] != null ? ((ebit[li] as number) / (now as number)) * 100 : null, marginChangePp: null,
      notReported: gone, lastReported: null, lastRevenue: null, flag: null, note: null };
  });
}

export type SortKey = "default" | "share" | "growth";
/** Sorts without losing the "not reported now" rows: they always stay at the bottom. Missing values sort after present ones. */
export function sortRows(rows: TableRow[], key: SortKey): TableRow[] {
  if (key === "default") return rows;
  const pick = (r: TableRow) => (key === "share" ? r.sharePct : r.cagrPct);
  return [...rows].sort((a, b) => Number(a.notReported) - Number(b.notReported) || (pick(b) ?? -Infinity) - (pick(a) ?? -Infinity));
}

/** Plain-words summary of the chart for screen readers: the years covered and the latest mix. */
export function chartSummary(m: ChartModel): string {
  if (!m.years.length) return "No segment history.";
  const i = m.years.length - 1;
  const parts = m.series.filter((s) => (s.shares[i] ?? 0) > 0).map((s) => `${s.label} ${nf(s.shares[i] as number, 1)}%`);
  return `Stacked bar chart of revenue by segment for each fiscal year, ${m.years[0]} to ${m.years[i]}. Latest year ${m.years[i]}: ${parts.join(", ")}. The table below the chart lists every value.`;
}

export type { SegmentInsights };
