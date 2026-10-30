// Profit and revenue outlook (Gold): API types, the hook, and the pure weight-balancing logic for the "Set your own" sliders.
// All forecast arithmetic is on the server (backend/finlit/outlook/model.py); the chart series, ticks and formats are in lib/outlookChart.ts.
import { useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "./api";

export type Kind = "profit" | "revenue";
export type Horizon = "short" | "mid" | "long";
export type Weights = Record<string, number>;
export type RateRow = {
  key: string; label: string; who: "company" | "sector"; weightPct: number; effectiveWeightPct: number; valuePct: number | null; rawPct: number | null; capped: boolean;
  contributionPts: number | null; status: "ok" | "unavailable"; method: string | null; reason: string | null; detail: string | null;
};
export type YearRow = { period: string; valueCr: number; growthPct: number; changeCr: number };
export type HistoryPoint = { period: string; valueCr: number | null; reportedCr: number | null; adjusted: boolean };
export type Outlook = {
  symbol: string; statement: string; kind: Kind; mode: "model" | "custom"; name: string | null; isLender: boolean; asOf: { yearly: string | null }; reportGeneratedAt: string | null;
  weights: Weights; defaultWeights: Weights; adjustedYears: string[];
  horizon: { key: Horizon; years: number; label: string; span: string };
  history: { unit: string; points: HistoryPoint[] };
  rate: { ratePct: number | null; rows: RateRow[]; unavailable: string[]; weightLeftPct: number };
  forecast: { available: boolean; reason: string | null; base: { period: string; valueCr: number } | null; years: YearRow[]; rule: string };
  inputCapPct: number; minPeers: number; disclaimer: string;
};

export const HORIZONS: { key: Horizon; label: string; span: string; years: number }[] = [
  { key: "short", label: "Short-term", span: "1 year", years: 1 }, { key: "mid", label: "Mid-term", span: "3 years", years: 3 }, { key: "long", label: "Long-term", span: "5 years", years: 5 },
];
export const KIND_LABEL: Record<Kind, string> = { profit: "Profit", revenue: "Revenue" };

/** The team's proposed starting weights (percent) for each horizon: the same numbers the server uses (it is the source; this copy lets the sliders start from them and "Reset" return to them). */
export const DEFAULT_WEIGHTS: Record<Kind, Record<Horizon, Weights>> = {
  revenue: {
    short: { co_1y: 50, co_3y: 10, co_5y: 5, sec_1y: 25, sec_3y: 5, sec_5y: 5 },
    mid: { co_1y: 10, co_3y: 40, co_5y: 10, sec_1y: 20, sec_3y: 10, sec_5y: 10 },
    long: { co_1y: 5, co_3y: 15, co_5y: 40, sec_1y: 20, sec_3y: 5, sec_5y: 15 },
  },
  profit: {
    short: { co_1y: 35, co_3y: 10, co_5y: 5, sec_1y: 25, sec_3y: 5, sec_5y: 5, margin: 15 },
    mid: { co_1y: 10, co_3y: 25, co_5y: 10, sec_1y: 20, sec_3y: 10, sec_5y: 10, margin: 15 },
    long: { co_1y: 5, co_3y: 15, co_5y: 30, sec_1y: 20, sec_3y: 5, sec_5y: 15, margin: 10 },
  },
};
/** Names of the parameters, in table order (the server sends the same labels with every result; these show on the sliders before the first result). */
export const PARAM_LABELS: Record<Kind, Record<string, string>> = {
  revenue: { co_1y: "Company revenue growth (1Y)", co_3y: "Company revenue CAGR (3Y)", co_5y: "Company revenue CAGR (5Y)", sec_1y: "Sector revenue growth (1Y)", sec_3y: "Sector revenue CAGR (3Y)", sec_5y: "Sector revenue CAGR (5Y)" },
  profit: { co_1y: "Company net profit growth (1Y)", co_3y: "Company net profit CAGR (3Y)", co_5y: "Company net profit CAGR (5Y)", sec_1y: "Sector net profit growth (1Y)", sec_3y: "Sector net profit CAGR (3Y)", sec_5y: "Sector net profit CAGR (5Y)", margin: "Net profit margin trend" },
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
export const isDefault = (kind: Kind, horizon: Horizon, w: Weights) => Object.entries(DEFAULT_WEIGHTS[kind][horizon]).every(([l, x]) => Math.abs((w[l] ?? NaN) - x) < 1e-9);
export const signedPct = (v: number, d = 1) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}%`;

export function useOutlook(symbol: string | undefined, kind: Kind, horizon: Horizon, weights: Weights | null, enabled: boolean) {
  const key = weights ? Object.entries(weights).sort().map(([k, v]) => `${k}${v}`).join(",") : "model";
  return useQuery<Outlook, ApiError>({
    queryKey: ["outlook2", symbol, kind, horizon, key],
    queryFn: () => apiSend<Outlook>("POST", `/api/outlook/${encodeURIComponent(symbol as string)}`, weights ? { kind, horizon, weights } : { kind, horizon }),
    enabled: enabled && !!symbol, retry: false, staleTime: 300_000,
  });
}
