// India macro page: types for /api/macro and the pure helpers (range cut, alignment, correlation, heat colours, CSV). Tested in macro.test.ts.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";

export type Pt = [string, number];
export type Card = {
  key: string; label: string; value: number; unit: string; date: string; period: string; prev: number | null; prevPeriod: string | null; change: number | null;
  changeUnit: string; changePct?: number; yearAgo: number | null; yearChange?: number; source: string; sourceUrl: string | null; what: string | null; spark: Pt[];
  lastDecision?: { date: string; bp: number; url: string };
};
export type SeriesOut = { label: string; unit: string; freq: "M" | "Q" | "W" | "F" | "D"; source: string; sourceUrl: string | null; what: string | null; note: string | null; breaks: { d: string; label: string }[]; points: Pt[] };
export type Insight = { key: string; tone: "info" | "warn"; title: string; text: string };
export type Macro = {
  updatedAt: string; today: string; cards: Card[]; insights: Insight[];
  targetWatch: { target: number; band: [number, number]; quarters: { q: string; avg: number }[]; streak: number; side: "above" | "below" | null; lastQuarter: string | null; rule: string };
  series: Record<string, SeriesOut>; cpiDivisions: { key: string; label: string; points: Pt[] }[];
  rates: { rates: Record<string, number>; fx: Record<string, number>; fxAsOf: string | null; seenOn: string } | null;
  reserves: { reservesAsOf: string; link: string; reserves: Record<string, { inr: number; usd: number; weekUsd: number; fyUsd: number; yearUsd: number }> } | null;
  decisions: { date: string; rate: number; bp: number; url: string }[];
  coverage: { key: string; label: string; source: string; from: string; latest: string; observations: number; ageDays: number }[];
  runs: Record<string, { status: string; at: string }>; issues: string[]; sources: { name: string; url: string; covers: string }[]; disclaimer: string;
};

export const useMacro = () => useQuery<Macro, ApiError>({ queryKey: ["macro"], queryFn: () => apiGet<Macro>("/api/macro"), staleTime: 300_000, retry: 1 });

export const RANGES = [["1Y", 12], ["3Y", 36], ["5Y", 60], ["10Y", 120], ["Max", 0]] as const;
export type RangeKey = (typeof RANGES)[number][0];

const ym = (d: string) => +d.slice(0, 4) * 12 + +d.slice(5, 7);
/** The points of the last `months` months counted back from the newest point (0 = all). */
export function cut(points: Pt[], months: number): Pt[] {
  if (!months || !points.length) return points;
  const end = ym(points[points.length - 1][0]);
  return points.filter((p) => ym(p[0]) > end - months);
}

/** Two series aligned by calendar month (quarterly and weekly points land in their month): only months both have. */
export function align(a: Pt[], b: Pt[]): [number, number, string][] {
  const m = new Map(b.map((p) => [p[0].slice(0, 7), p[1]]));
  const out: [number, number, string][] = [];
  for (const [d, v] of a) { const w = m.get(d.slice(0, 7)); if (w != null) out.push([v, w, d]); }
  return out;
}

/** Pearson correlation of aligned pairs; null with fewer than 12 months in common or no variation. */
export function correlation(pairs: [number, number, string][]): number | null {
  const n = pairs.length;
  if (n < 12) return null;
  const mx = pairs.reduce((s, p) => s + p[0], 0) / n, my = pairs.reduce((s, p) => s + p[1], 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (const [x, y] of pairs) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2; }
  return sxx && syy ? Math.round((sxy / Math.sqrt(sxx * syy)) * 100) / 100 : null;
}

export const corrWords = (r: number | null): string => {
  if (r == null) return "Not enough months in common";
  const a = Math.abs(r), s = a >= 0.7 ? "strongly" : a >= 0.4 ? "moderately" : a >= 0.2 ? "weakly" : "hardly";
  return a < 0.2 ? "The two hardly move together" : `They move ${s} ${r > 0 ? "together" : "in opposite directions"}`;
};

/** 0..1 position of v between lo and hi (clamped). */
export const frac = (v: number, lo: number, hi: number) => (hi > lo ? Math.min(1, Math.max(0, (v - lo) / (hi - lo))) : 0);

/** Heat-map cell colour for an inflation rate: cool below the 4% target, warm above, hot above the 6% limit (token colours, light and dark safe). */
export function heat(v: number | null): { bg: string; strong: boolean } {
  if (v == null) return { bg: "transparent", strong: false };
  if (v > 6) return { bg: `color-mix(in srgb, var(--loss) ${Math.round(35 + Math.min(40, (v - 6) * 8))}%, transparent)`, strong: true };
  if (v > 4) return { bg: `color-mix(in srgb, var(--warn) ${Math.round(18 + (v - 4) * 10)}%, transparent)`, strong: false };
  if (v >= 2) return { bg: `color-mix(in srgb, var(--gain) ${Math.round(14 + (4 - v) * 7)}%, transparent)`, strong: false };
  return { bg: `color-mix(in srgb, var(--k1) ${Math.round(24 + (2 - v) * 8)}%, transparent)`, strong: true };
}

export const fmt = (v: number, unit: string): string => {
  const d = unit === "₹" || unit === "US$ bn" ? (Math.abs(v) >= 100 ? 1 : 2) : 2;
  const s = Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
  return (v < 0 ? "−" : "") + (unit === "₹" ? "₹" : unit === "US$ bn" ? "US$ " : "") + s + (unit === "%" ? "%" : unit === "US$ bn" ? " bn" : unit === "pp" ? " pp" : "");
};
export const signed = (v: number, unit: string) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), unit === "pp" ? "pp" : unit).replace(/^US\$ /, "");

export function toCsv(keys: string[], series: Record<string, SeriesOut>): string {
  const dates = [...new Set(keys.flatMap((k) => series[k]?.points.map((p) => p[0]) || []))].sort();
  const by = keys.map((k) => new Map(series[k]?.points));
  const q = (s: string) => `"${s.replace(/"/g, '""')}"`;
  return [["Date", ...keys.map((k) => q(`${series[k]?.label} (${series[k]?.unit})`))].join(","), ...dates.map((d) => [d, ...by.map((m) => m.get(d) ?? "")].join(","))].join("\n");
}
