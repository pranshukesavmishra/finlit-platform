// The custom comparison answer: every chosen measure for every chosen company, a number or the reason it is blank.
import { useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "./api";

export type CmpMetric = { key: string; label: string; group: string; groupLabel: string; unit: string; better: "higher" | "lower" | "none"; digits: number; say: string; tier: string };
export type CmpCompany = { symbol: string; name: string; sector: string | null; cap: string | null; known: boolean };
export type CmpCell = { v: number | null; why: string | null };
export type CmpResult = { plan: string; companies: CmpCompany[]; metrics: CmpMetric[]; values: Record<string, Record<string, CmpCell>> };

export const useCompareMetrics = (symbols: string[], keys: string[], enabled = true) => useQuery<CmpResult, ApiError>({
  queryKey: ["compare-metrics", symbols, keys],
  queryFn: () => apiSend<CmpResult>("POST", "/api/compare/metrics", { symbols, keys }),
  enabled: enabled && symbols.length > 0 && keys.length > 0,
  staleTime: 60_000, retry: (n, e) => e.status >= 500 && n < 1,
});
