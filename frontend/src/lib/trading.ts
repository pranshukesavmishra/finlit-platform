// How the share trades: surveillance flag, F&O and lot size, the broker's margin-trading leverage (GET /api/stocks/{symbol}/trading, from the
// broker Dhan's daily instrument file) and the day's price band from the live quote. Only what is positively known is ever shown.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError, type Quote } from "./api";

export type Trading = {
  symbol: string; matched: boolean; exchange?: "NSE" | "BSE"; asOf?: string | null;
  surveillance?: { stage: string | null } | null;   // present only when the file flags the share Y (under ASM/GSM)
  fno?: { lotSize: number | null } | null;
  mtf?: { leverage: number } | null;               // already rounded down to one decimal by the server, and always above 1
};

export const useTrading = (symbol: string, enabled = true) => useQuery<Trading, ApiError>({
  queryKey: ["stock", symbol, "/trading"], queryFn: () => apiGet<Trading>(`/api/stocks/${encodeURIComponent(symbol)}/trading`),
  staleTime: 5 * 60_000, retry: 1, enabled: enabled && !!symbol,
});

export type Band = { upper: number; lower: number; at: "upper" | "lower" | null };
/** The day's price band (circuit limits) of this quote, and whether the price sits on either end; null without both limits, as the
 * alert does (alertengine.circuit_state): the same quote's price and band, so they always belong to the same moment. */
export function priceBand(q: Partial<Quote> | null | undefined): Band | null {
  const up = q?.upperCircuit, lo = q?.lowerCircuit, p = q?.price;
  if (up == null || lo == null || !(lo > 0 && lo < up)) return null;
  return { upper: up, lower: lo, at: p == null || !(p > 0) ? null : p >= up ? "upper" : p <= lo ? "lower" : null };
}

/** "4.5×", "2×": the server already rounded down, so this only drops a trailing ".0". */
export const leverageText = (x: number) => `${Number.isInteger(x) ? x : x.toFixed(1)}×`;

/** The exchange's stage or category text as the file gives it ("II", "ASM LT Stage 2"); a bare roman or digit stage gets the word "stage". */
export const stageText = (s: string | null | undefined): string | null => {
  const t = (s || "").trim();
  if (!t) return null;
  return /^([IVX]+|\d+)$/i.test(t) ? `stage ${t.toUpperCase()}` : t;
};
