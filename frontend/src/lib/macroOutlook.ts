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

/** The "This company" rows of Sector impact: the company's own sector, or each reported segment sector for a revenue-weighted company.
 *  A single-sector company reads its row from its own outlook (the same stored snapshot), so the row never depends on the 35-sector table. */
export function companyRows(c: CompanyMacro, table: SectorRow[] | undefined): SectorRow[] {
  const m = c.mapping;
  if (!m) return [];
  if (m.basis === "revenue_weighted" && c.segments?.length) {
    const codes = new Set(c.segments.map((x) => x.sector));
    return (table ?? []).filter((r) => codes.has(r.sector.code)).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  }
  return [{ sector: { code: m.sector, name: m.sectorName }, status: c.status, score: c.score ?? null, label: c.label ?? "Insufficient Data", tone: c.tone ?? "none", coverage: c.coverage ?? 0,
    drivers: c.drivers ?? [], snapshotDate: c.snapshotDate ?? "", reason: c.reason ?? null }];
}

/** One reason shown in Sector impact, and the indicator it is about. `driver` is the "Top reasons" pill; a reason without a driver is a missing reading that kept the score from being shown. */
export type Reason = { code: string; driver?: Driver; sector?: string };
/** The reasons Sector impact gives for the rows it shows, in the order it shows them, one per indicator. */
export function reasonsOf(rows: SectorRow[], c: Pick<CompanyMacro, "status" | "criticalMissing" | "missing">): Reason[] {
  const out: Reason[] = [], seen = new Set<string>();
  const add = (r: Reason) => { if (!seen.has(r.code)) { seen.add(r.code); out.push(r); } };
  for (const r of rows) for (const d of r.drivers) add({ code: d.code, driver: d, sector: rows.length > 1 ? r.sector.name : undefined });
  if (c.status === "insufficient_data") for (const code of [...(c.criticalMissing ?? []), ...(c.missing ?? [])]) add({ code });
  return out;
}
/** Only the indicators that are a reason in Sector impact, in the order of the reasons. */
export function indicatorsForReasons(indicators: Indicator[] | undefined, reasons: Reason[]): { indicator: Indicator; reason: Reason }[] {
  const by = new Map((indicators ?? []).map((i) => [i.code, i]));
  return reasons.flatMap((reason) => { const indicator = by.get(reason.code); return indicator ? [{ indicator, reason }] : []; });
}

/** "+0.42" / "−0.42" with a real minus sign. */
export const signed = (v: number | null | undefined, dp = 2): string => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp);
/** "Credit +" / "Rate change −" for a driver pill. */
export const driverText = (d: Driver): string => `${shortName(d.code, d.name)} ${d.sign === "+" ? "+" : "−"}`;
export const arrow = (d: Indicator["direction"]): string => d === "up" ? "▲" : d === "down" ? "▼" : d === "flat" ? "▬" : "";
/** The reason to show in place of a missing score. */
export const insufficientText = (c: Pick<CompanyMacro, "reason" | "criticalMissing" | "missing">): string => c.reason ? `Insufficient Data: ${c.reason}` : "Insufficient Data";
/** Position (0..100 %) of a score on the bar. */
export const pct = (s: number | null | undefined): number => Math.max(0, Math.min(100, s ?? 0));
