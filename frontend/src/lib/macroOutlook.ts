// Macro & Sector Outlook (backend/finlit/macro_outlook): the company page's section reads stored snapshots only. Describes a sector's macroeconomic
// backdrop; never a company assessment and never a recommendation.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

export type Tone = "up2" | "up" | "flat" | "down" | "down2" | "none";
export type Stale = { isStale: boolean; since: string | null; message: string | null; reason: string | null };
export type Driver = { code: string; name: string; contribution: number; sign: "+" | "-"; value: number | null; unit: string; valueText: string; viaSector?: string };
export type Sens = { coefficient: number; weight: number; critical: boolean; contribution: number | null; counted: boolean; reason: string | null };
export type Indicator = {
  code: string; name: string; group: string; unit: string; frequency: string; value: number | null; valueText: string | null; prevValue: number | null; prevText: string | null; prevDate: string | null;
  change: number | null; direction: "up" | "down" | "flat" | "none"; signal: number | null; level: number | null; momentum: number | null; observationDate: string | null; publicationDate: string | null;
  dateBasis: string; source: string; sourceUrl: string | null; status: "Available" | "Stale" | "Missing" | "Invalid" | "Revised"; detail: string | null; note: string | null; sensitivity?: Sens | null;
};
export type Item = { code: string; name: string; valueText?: string; signal?: number | null; contribution?: number; reading?: string; why?: string; critical?: boolean };
export type Explanation = { headline?: string; supporting?: Item[]; adverse?: Item[]; monitor?: Item[] };
export type Delta = { score: number; change: number; date: string } | null;
export type CompanyMacro = {
  status: "ok" | "insufficient_data" | "not_mapped" | "pending"; symbol: string; company: string; modelVersion: number; stale: Stale; disclaimer: string; assumptionsNote: string;
  reason?: string | null; mapping?: { sector: string; sectorName: string; effectiveFrom: string; source: string; rule: string | null; basis: "primary" | "revenue_weighted"; note: string };
  segments?: { sector: string; name: string; weight: number; score: number | null; label: string; tone: Tone }[];
  score?: number | null; label?: string; tone?: Tone; coverage?: number; minCoverage?: number; snapshotDate?: string; asOf?: string; basis?: "live" | "reconstructed";
  drivers?: Driver[]; missing?: string[]; criticalMissing?: string[]; explanation?: Explanation; deltas?: Record<string, Delta>;
  indicators?: Indicator[]; groups?: { code: string; name: string }[]; signalNote?: string; note?: string;
};
export type SectorRow = { sector: { code: string; name: string }; status: string; score: number | null; label: string; tone: Tone; coverage: number; drivers: Driver[]; snapshotDate: string; reason: string | null };
export type SectorImpact = { modelVersion: number; asOf: string | null; count: number; sectors: SectorRow[]; stale: Stale; disclaimer: string };
export type HistoryPoint = { date: string; score: number | null; label: string; status: string; basis: "live" | "reconstructed" };
export type History = { sector: { code: string; name: string }; period: string; points: HistoryPoint[]; midpoint: number; note: string };
export type Methodology = {
  modelVersion: number; assumptionsNote: string; disclaimer: string; scoreMeaning: string; bands: { min: number; label: string }[]; normalisation: string; sensitivities: string; formula: string[];
  drivers: string; sources: string; updates: string; limitations: string[]; indicators: { code: string; name: string; group: string; unit: string; frequency: string; source: string }[];
};

const Q = { staleTime: 10 * 60_000, retry: false } as const;
export const useCompanyMacro = (symbol: string, enabled = true) => useQuery<CompanyMacro, ApiError>({ queryKey: ["macro-outlook", symbol], enabled: enabled && !!symbol, ...Q,
  queryFn: () => apiGet<CompanyMacro>(`/api/stocks/${encodeURIComponent(symbol)}/macro-outlook`) });
export const useSectorImpact = (enabled = true) => useQuery<SectorImpact, ApiError>({ queryKey: ["macro-impact"], enabled, ...Q, queryFn: () => apiGet<SectorImpact>("/api/macro/sector-impact") });
export const useMacroHistory = (sector: string, period: string, enabled = true) => useQuery<History, ApiError>({ queryKey: ["macro-history", sector, period], enabled: enabled && !!sector, ...Q,
  queryFn: () => apiGet<History>(`/api/macro/sectors/${encodeURIComponent(sector)}/history?period=${period}`) });
export const useMacroMethod = (enabled: boolean) => useQuery<Methodology, ApiError>({ queryKey: ["macro-method"], enabled, ...Q, queryFn: () => apiGet<Methodology>("/api/macro/methodology") });

export const SHORT: Record<string, string> = { CPI: "CPI", FOOD_CPI: "Food CPI", WPI: "WPI", REPO_RATE: "Repo rate", REPO_ACTION: "Rate change", BANK_CREDIT: "Credit", DEPOSIT_GROWTH: "Deposits", GDP: "GDP",
  IIP: "IIP", IIP_CAPITAL: "Capital goods IIP", IIP_INFRA: "Infra IIP", IIP_DURABLES: "Durables IIP", IIP_NONDURABLES: "Non-durables IIP", UNEMPLOYMENT: "Jobless rate", USDINR: "USD/INR",
  BRENT: "Brent", COPPER: "Copper", ALUMINIUM: "Aluminium", NATGAS: "Gas" };
export const shortName = (code: string, fallback = code) => SHORT[code] ?? fallback;
export const PERIODS = ["1M", "3M", "6M", "1Y", "ALL"] as const;
export const GROUP_ICON: Record<string, string> = { inflation: "percent", monetary: "gauge", credit: "wallet", growth: "growth", currency: "rupee", commodities: "coins" };

/** "+0.42" / "−0.42" with a real minus sign. */
export const signed = (v: number | null | undefined, dp = 2): string => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp);
/** "Credit +" / "Rate change −" for a driver pill. */
export const driverText = (d: Driver): string => `${shortName(d.code, d.name)} ${d.sign === "+" ? "+" : "−"}`;
export const arrow = (d: Indicator["direction"]): string => d === "up" ? "▲" : d === "down" ? "▼" : d === "flat" ? "▬" : "";
/** The reason to show in place of a missing score. */
export const insufficientText = (c: Pick<CompanyMacro, "reason" | "criticalMissing" | "missing">): string => c.reason ? `Insufficient Data: ${c.reason}` : "Insufficient Data";
/** Position (0..100 %) of a score on the bar. */
export const pct = (s: number | null | undefined): number => Math.max(0, Math.min(100, s ?? 0));
