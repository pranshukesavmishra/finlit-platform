// Graph Studio: the saved/shared shape of a view, its validation, and which chart types make sense for which data.
import type { Plan } from "./auth";
import { GRAPH_LIMITS, type ChartKind } from "./graphLimits";
import type { RangeId } from "./graphData";
import { BY_ID, isIndexSym, indexSupports, type Basis } from "./graphMetrics";

export type SeriesSpec = { s: string; m: string; as?: "bar" | "line" };
export type CellSpec = { chart: ChartKind; series: SeriesSpec[]; mode?: "corr" | "grid"; tf?: "values" | "change" | "index"; x?: number; y?: number };
export type View = { v: 1; layout: string; basis: Basis; range: RangeId; from?: number; cells: CellSpec[] };
export const LAYOUTS: Record<string, { rows: number; cols: number }> = { "1x1": { rows: 1, cols: 1 }, "1x2": { rows: 1, cols: 2 }, "2x2": { rows: 2, cols: 2 }, "2x3": { rows: 2, cols: 3 }, "3x3": { rows: 3, cols: 3 } };
export const cellCount = (layout: string) => (LAYOUTS[layout] ? LAYOUTS[layout].rows * LAYOUTS[layout].cols : 4);
export const CHART_LABEL: Record<ChartKind, string> = { line: "Line", area: "Area", column: "Column", bar: "Bar (latest values)", combo: "Combo (bars + line)", pie: "Pie", candlestick: "Candlestick", scatter: "Scatter (X vs Y)", heatmap: "Heatmap" };
const SYM = /^(IDX:[A-Z0-9]{2,24}|[A-Z0-9&_.-]{1,24})$/;   // a company symbol, or an index as IDX:code

export const defaultView = (symbol = "RELIANCE"): View => ({
  v: 1, layout: "2x2", basis: "annual", range: "5Y",
  cells: [{ chart: "line", series: [{ s: symbol, m: "price" }] }, { chart: "column", series: [{ s: symbol, m: "revenue" }] },
    { chart: "column", series: [{ s: symbol, m: "net_profit" }] }, { chart: "line", series: [{ s: symbol, m: "pe" }] }],
});

/** Make any object (from a URL, local storage or the server) into a valid view within the plan's limits. Never throws. */
export function sanitize(raw: unknown, plan: Plan): View {
  const lim = GRAPH_LIMITS[plan] ?? GRAPH_LIMITS.basic, r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  let layout = typeof r.layout === "string" && LAYOUTS[r.layout] ? r.layout : "2x2";
  while (cellCount(layout) > lim.cells) layout = layout === "3x3" ? "2x3" : layout === "2x3" ? "2x2" : "1x2";
  const companies = new Set<string>();
  const cells: CellSpec[] = (Array.isArray(r.cells) ? r.cells : []).slice(0, cellCount(layout)).map((c: Record<string, unknown>) => {
    const chart = (["line", "area", "column", "bar", "combo", "pie", "candlestick", "scatter", "heatmap"] as ChartKind[]).includes(c?.chart as ChartKind) && lim.charts.includes(c.chart as ChartKind) ? (c.chart as ChartKind) : "line";
    const series: SeriesSpec[] = [];
    for (const s of Array.isArray(c?.series) ? (c.series as Record<string, unknown>[]) : []) {
      const sym = typeof s?.s === "string" ? s.s.toUpperCase() : "";
      if (!SYM.test(sym) || typeof s.m !== "string" || !BY_ID[s.m] || series.length >= lim.series) continue;
      if (isIndexSym(sym) && !indexSupports(BY_ID[s.m])) continue;   // a revenue line for an index is meaningless: dropped, never drawn blank
      if (!isIndexSym(sym) && BY_ID[s.m].src === "ixval") continue;
      if (!isIndexSym(sym) && !companies.has(sym) && companies.size >= lim.companies) continue;   // indices count toward the series limit, not the company limit
      if (!isIndexSym(sym)) companies.add(sym); series.push({ s: sym, m: s.m, ...(s.as === "bar" || s.as === "line" ? { as: s.as } : {}) });
    }
    const n = (v: unknown) => (typeof v === "number" && v >= 0 && v < 9 ? v : undefined);
    return { chart, series, ...(c?.mode === "corr" || c?.mode === "grid" ? { mode: c.mode } : {}), ...(["values", "change", "index"].includes(c?.tf as string) ? { tf: c.tf as CellSpec["tf"] } : {}), x: n(c?.x), y: n(c?.y) };
  });
  return { v: 1, layout, basis: r.basis === "quarterly" ? "quarterly" : "annual", ...(typeof r.from === "number" && r.from >= 1990 && r.from <= new Date().getFullYear() ? { from: Math.floor(r.from) } : {}), range: (["1Y", "3Y", "5Y", "MAX"] as const).find((x) => x === r.range) ?? "5Y", cells };
}

const b64 = (s: string) => btoa(String.fromCharCode(...new TextEncoder().encode(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64 = (s: string) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0)));
export const encodeView = (v: View) => b64(JSON.stringify(v));
export function decodeView(s: string | null, plan: Plan): View | null { if (!s) return null; try { return sanitize(JSON.parse(unb64(s)), plan); } catch { return null; } }

export type Check = { ok: boolean; why?: string };
export type CellFacts = { n: number; comp: boolean; mixedComp: boolean; units: string[]; ratioUnits: boolean; maxPts: number; ohlc: boolean; priceOnly1: boolean; companies: number };
/** Is this chart type sensible for this data? A reason (never a nonsense drawing) when not. */
export function chartCheck(chart: ChartKind, f: CellFacts, plan: Plan): Check {
  if (!GRAPH_LIMITS[plan].charts.includes(chart)) return { ok: false, why: "Not in your plan" };
  if (f.n === 0) return { ok: true };
  if (f.mixedComp) return { ok: false, why: "Breakdowns can't mix with other measures" };
  if (f.comp) return chart === "pie" || chart === "bar" ? (chart === "pie" && f.n > 1 ? { ok: false, why: "One breakdown at a time" } : { ok: true }) : { ok: false, why: "A breakdown has no time axis" };
  const kinds = new Set(f.units).size;
  switch (chart) {
    case "pie": return { ok: false, why: "Only for breakdowns (segments, shareholding)" };
    case "candlestick": return f.n === 1 && f.priceOnly1 ? (f.ohlc ? { ok: true } : { ok: false, why: "Needs daily prices: use 1Y with live data" }) : { ok: false, why: "Needs one price series" };
    case "bar": return kinds > 1 ? { ok: false, why: "Mixed units on one scale" } : { ok: true };
    case "combo": return f.n < 2 ? { ok: false, why: "Needs two or more series" } : kinds > 2 ? { ok: false, why: "More than two units" } : { ok: true };
    case "scatter": case "heatmap": return f.n < (chart === "scatter" ? 2 : 1) ? { ok: false, why: "Needs two or more series" } : { ok: true };
    case "column": return f.maxPts > 400 ? { ok: false, why: "Too many points for columns" } : kinds > 2 ? { ok: false, why: "More than two units" } : { ok: true };
    default: return kinds > 2 ? { ok: false, why: "More than two units" } : { ok: true };
  }
}
