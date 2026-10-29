// Profit and revenue outlook (Gold): API types, the hook, and the pure weight-balancing logic for the "Set your own" sliders.
// No thresholds or formulas live here: the server sends group names, percentages and scores only.
import { useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "./api";
import { scoreBand, type ScoreBand } from "./scoreBands";

export type Kind = "profit" | "revenue";
export type Weights = Record<string, number>;
export type OutlookBand = { key: ScoreBand; color: string; word: string };
export type OutlookGroup = {
  letter: string; name: string; weightPct: number; effectiveWeightPct: number; score: number | null; band: OutlookBand;
  coverage: { measured: number; total: number }; status: "ok" | "unavailable"; reason: string | null;
};
export type OutlookRange =
  | { available: false; reason: string }
  | { available: true; label: string; metric: string; baselineQuarter: string; baselineAmountCr: number; baseline: string; low: number; mid: number; high: number;
      lowCr: number; midCr: number; highCr: number; capped: string[]; cappedNote: string | null; tilted: boolean; basedOn: string };
export type Outlook = {
  symbol: string; statement: string; kind: Kind; mode: "model" | "custom"; name: string | null; isLender: boolean;
  asOf: { yearly: string | null; quarterly: string | null }; reportGeneratedAt: string | null;
  score: { value: number | null; band: OutlookBand; reason: string | null };
  coverage: { measured: number; total: number; weightPct: number };
  groups: OutlookGroup[]; range: OutlookRange; disclaimer: string;
};

/** The model's own default group weights (the same numbers the server uses), so "Set your own" can start from them and "Reset" can return to them. Group names come from the server. */
export const DEFAULT_WEIGHTS: Record<Kind, Weights> = {
  profit: { A: 25, B: 15, C: 15, D: 10, E: 10, F: 10, G: 5, H: 5, I: 5 },
  revenue: { A: 25, B: 15, C: 15, D: 10, E: 10, F: 10, G: 10, H: 5 },
};

export const TOTAL_TENTHS = 1000;
const toTenths = (v: number) => Math.round(v * 10);

/** Change one group's percentage; the others rebalance in proportion to what they hold, so the total stays exactly 100 (one decimal place).
 *  The changed value is clamped to 0..100. If the others hold nothing, they share the rest equally. Largest-remainder rounding keeps the sum exact. */
export function rebalance(weights: Weights, letter: string, value: number): Weights {
  const letters = Object.keys(weights);
  if (!letters.includes(letter)) return { ...weights };
  const v = Math.max(0, Math.min(TOTAL_TENTHS, Number.isFinite(value) ? toTenths(value) : 0));
  const others = letters.filter((l) => l !== letter);
  if (!others.length) return { [letter]: 100 };
  const rest = TOTAL_TENTHS - v;
  const held = others.reduce((s, l) => s + Math.max(0, weights[l]), 0);
  const raw = others.map((l) => (held > 0 ? (Math.max(0, weights[l]) / held) * rest : rest / others.length));
  const base = raw.map(Math.floor);
  let left = rest - base.reduce((s, x) => s + x, 0);
  raw.map((r, i) => ({ i, f: r - base[i] })).sort((a, b) => b.f - a.f || a.i - b.i).forEach(({ i }) => { if (left > 0) { base[i] += 1; left -= 1; } });
  const out: Weights = { [letter]: v / 10 };
  others.forEach((l, i) => { out[l] = base[i] / 10; });
  return Object.fromEntries(letters.map((l) => [l, out[l]]));
}

export const totalOf = (w: Weights) => Object.values(w).reduce((s, x) => s + toTenths(x), 0) / 10;
export const isDefault = (kind: Kind, w: Weights) => Object.entries(DEFAULT_WEIGHTS[kind]).every(([l, x]) => Math.abs((w[l] ?? NaN) - x) < 1e-9);

/** Colour band of an outlook score: the site's shared rule (scoreBands.ts). */
export const outlookBand = (v: number | null | undefined): ScoreBand => scoreBand(v);
export const outlookWord = (v: number | null | undefined) => (v == null ? "Not available" : v >= 70 ? "Supportive" : v >= 50 ? "Mixed" : "Subdued");

/** Where a value sits on a track from `min` to `max` (0..100 %), for the range graphic. */
export const rangePos = (v: number, min: number, max: number) => (max === min ? 50 : Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100)));
export const signedPct = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;

export function useOutlook(symbol: string | undefined, kind: Kind, weights: Weights | null, enabled: boolean) {
  const key = weights ? Object.entries(weights).sort().map(([k, v]) => `${k}${v}`).join(",") : "model";
  return useQuery<Outlook, ApiError>({
    queryKey: ["outlook", symbol, kind, key],
    queryFn: () => apiSend<Outlook>("POST", `/api/outlook/${encodeURIComponent(symbol as string)}`, weights ? { kind, weights } : { kind }),
    enabled: enabled && !!symbol, retry: false, staleTime: 300_000,
  });
}
