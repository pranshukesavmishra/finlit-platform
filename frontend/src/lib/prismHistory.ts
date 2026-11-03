// The Prism score over time: the shape of /api/prism/history and the pure helpers the chart uses (tested in prismHistory.test.ts).
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

export type HistPoint = {
  day: string; modelVersion: string | null; final: number | null; label: string | null; status: string | null;
  parts: { fundamental: number | null; valuation: number | null; quality: number | null; risk: number | null };
  shortTerm: number | null; longTerm: number | null;
};
export type PrismHistory = { symbol: string; statement: string; points: HistPoint[]; firstDay: string | null; note: string };

export const usePrismHistory = (symbol: string, statement: string, enabled: boolean) =>
  useQuery<PrismHistory, ApiError>({
    queryKey: ["prism-history", symbol, statement], enabled: enabled && !!symbol, staleTime: 300_000, retry: false,
    queryFn: () => apiGet<PrismHistory>(`/api/prism/history?symbol=${encodeURIComponent(symbol)}&statement=${encodeURIComponent(statement)}`),
  });

export type Series = "final" | "fundamental" | "valuation" | "quality" | "risk" | "shortTerm" | "longTerm";
export const valueOf = (p: HistPoint, s: Series): number | null =>
  s === "final" ? p.final : s === "shortTerm" ? p.shortTerm : s === "longTerm" ? p.longTerm : p.parts[s];

/** Points on which a series has a figure; the others (a day it was not worked out) are skipped, never drawn as zero. */
export const withValue = (points: HistPoint[], s: Series): HistPoint[] => points.filter((p) => valueOf(p, s) != null);

/** One point per calendar week (Monday to Sunday): the LAST day recorded in that week, as recorded (nothing averaged or filled in). */
export function toWeekly(points: HistPoint[]): HistPoint[] {
  const weekOf = (day: string) => {
    const d = new Date(day + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return d.toISOString().slice(0, 10);
  };
  const last = new Map<string, HistPoint>();
  for (const p of [...points].sort((a, b) => (a.day < b.day ? -1 : 1))) last.set(weekOf(p.day), p);
  return [...last.values()];
}

/** The days on which the model version differs from the day before: a jump there can be a new formula, not a changed business. */
export function modelChanges(points: HistPoint[]): { day: string; from: string; to: string }[] {
  const out: { day: string; from: string; to: string }[] = [];
  let prev: string | null = null;
  for (const p of points) {
    if (p.modelVersion && prev && p.modelVersion !== prev) out.push({ day: p.day, from: prev, to: p.modelVersion });
    if (p.modelVersion) prev = p.modelVersion;
  }
  return out;
}

/** What to say when there is too little to draw (a line needs two days with a figure). Empty string when the chart can be drawn. */
export function emptyReason(points: HistPoint[], s: Series): string {
  const n = withValue(points, s).length;
  if (n >= 2) return "";
  if (!points.length) return "No days are recorded for this company yet. The history starts on the day recording began and earlier days are never estimated.";
  const first = points[0].day;
  const day = new Date(first + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  return n === 1 ? `Only one day is recorded so far (${day}). A line needs at least two days with a figure; it fills in as the daily updates run.`
    : `This figure has not been worked out on any day recorded so far (the first is ${day}).`;
}

/** The change between the first and the newest figure of a series, for the one-line summary, or null with fewer than two figures. */
export function changeOver(points: HistPoint[], s: Series): { from: string; to: string; delta: number } | null {
  const v = withValue(points, s);
  if (v.length < 2) return null;
  const a = valueOf(v[0], s)!, b = valueOf(v[v.length - 1], s)!;
  return { from: v[0].day, to: v[v.length - 1].day, delta: Math.round((b - a) * 10) / 10 };
}
