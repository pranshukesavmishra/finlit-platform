// Mutual Fund Insights: the API types and hook, Indian-unit number text (lakh crore, crore, lakh) and the chart series.
// Pure helpers live here so they are tested without the page (mfInsights.test.ts). Data: AMFI's monthly category report via /api/mf/insights
// (backend/finlit/mf_insights.py). Amounts arrive in rupees crore; folios and schemes are counts.
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import { DEMO } from "./demo";
import { MINUS, nf } from "./format";
import type { LineSeries } from "./mf";

export type Kpi = { value: number | null; prev: number | null; change: number | null; changePct: number | null };
export type InsightItem = {
  name: string; heading: string; section: "open" | "close" | "interval" | "fof_domestic"; sectionLabel: string; schemes: number | null; folios: number | null;
  mobilized: number | null; redemption: number | null; netFlow: number | null; aum: number | null; aaum: number | null;
};
export type InsightGroup = {
  key: "equity" | "debt" | "hybrid" | "solution" | "other"; label: string; schemes: number | null; folios: number | null; netFlow: number | null; aum: number | null;
  aaum: number | null; share: number | null; prevAum: number | null; prevNetFlow: number | null; items: InsightItem[];
};
type Base = { source: string; sourcePage: string; disclaimer: string; unit: "crore"; coverage: string };
export type InsightsEmpty = Base & { status: "empty"; reason: string };
export type InsightsOk = Base & {
  status: "ok"; month: string; asOf: string; prevMonth: string | null; released: string | null; updatedAt: string; sourceUrl: string | null;
  kpis: { aum: Kpi; netFlow: Kpi & { mobilized: number | null; redemption: number | null }; folios: Kpi; equityAum: Kpi };
  series: { t: string[]; aum: (number | null)[]; netFlow: (number | null)[]; folios: (number | null)[]; equityAum: (number | null)[] };
  gaps: string[]; groups: InsightGroup[]; fofDomestic: (InsightItem & { note: string }) | null;
};
export type Insights = InsightsEmpty | InsightsOk;

// ------------------------------------------------------------------------------------------------ number text

const LAKH = 1e5, CRORE = 1e7;
const sign = (n: number, plus: boolean) => (n < 0 ? MINUS : plus && n > 0 ? "+" : "");

/** Rupees crore as people read industry sums: ₹82.64 L cr from ₹1 lakh crore up, else whole crore (₹41,354 cr). */
export function money(cr: number | null | undefined, plus = false): string {
  if (cr == null) return "—";
  const a = Math.abs(cr);
  return sign(cr, plus) + "₹" + (a >= LAKH ? nf(a / LAKH, 2) + " L cr" : nf(a, 0) + " cr");
}

/** A count of folios (investor accounts): 28.62 cr, 27.13 lakh, or the plain number below a lakh. */
export function folios(n: number | null | undefined, plus = false): string {
  if (n == null) return "—";
  const a = Math.abs(n);
  return sign(n, plus) + (a >= CRORE ? nf(a / CRORE, 2) + " cr" : a >= LAKH ? nf(a / LAKH, 2) + " lakh" : nf(a, 0));
}

export const pctSigned = (n: number | null | undefined, d = 2) => (n == null ? "" : sign(n, true) + nf(Math.abs(n), d) + "%");
export const tone = (n: number | null | undefined) => (n == null || n === 0 ? "" : n > 0 ? "pos" : "neg");

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** '2026-09' or '2026-09-30' -> 'Sep 2026'; short -> 'Sep 26'. */
export function monthLabel(iso: string, short = false): string {
  const y = iso.slice(0, 4), m = Number(iso.slice(5, 7));
  if (!/^\d{4}$/.test(y) || !(m >= 1 && m <= 12)) return iso;
  return `${MON[m - 1]} ${short ? y.slice(2) : y}`;
}

/** "▲ +₹0.45 L cr (+0.52%) vs Aug 2026", or why there is no comparison. */
export function changeText(k: Kpi, fmt: (n: number, plus?: boolean) => string, prevMonth: string | null): string {
  if (k.change == null || !prevMonth) return "No report for the month before, so no comparison.";
  const pct = k.changePct == null ? "" : ` (${pctSigned(k.changePct)})`;
  return `${fmt(k.change, true)}${pct} vs ${monthLabel(prevMonth)}`;
}

// ------------------------------------------------------------------------------------------------ chart

export type TrendKey = "aum" | "netFlow" | "folios";
export const TRENDS: { key: TrendKey; label: string; kind: "area" | "bars"; text: (n: number) => string; axis: (n: number) => string; caption: string }[] = [
  { key: "aum", label: "Industry AUM", kind: "area", text: (n) => money(n), axis: (n) => (n === 0 ? "0" : nf(n / LAKH, Math.abs(n) >= 10 * LAKH ? 0 : 1) + " L"),
    caption: "Net assets under management of all mutual fund schemes at each month end (rupees lakh crore)." },
  { key: "netFlow", label: "Net flows", kind: "bars", text: (n) => money(n, true), axis: (n) => (n === 0 ? "0" : sign(n, false) + nf(Math.abs(n) / LAKH, 1) + " L"),
    caption: "Money put in minus money taken out over each month, all schemes (rupees lakh crore). Liquid and other debt funds swing hard at quarter ends." },
  { key: "folios", label: "Folios", kind: "area", text: (n) => folios(n), axis: (n) => (n === 0 ? "0" : nf(n / CRORE, 0) + " cr"),
    caption: "Investor accounts (folios) at each month end. One person can hold many folios, so this is not the number of investors." },
];

/** One trend as a chart series: months without a figure are left out (the chart is scaled by date, so a gap shows as a straight joint). */
export function trendSeries(d: InsightsOk, key: TrendKey): LineSeries {
  const t: string[] = [], v: number[] = [];
  d.series.t.forEach((day, i) => { const x = d.series[key][i]; if (x != null) { t.push(day); v.push(x); } });
  return { key, label: TRENDS.find((x) => x.key === key)!.label, t, v };
}

export const GROUP_COLORS: Record<InsightGroup["key"], string> = { equity: "var(--k1)", debt: "var(--k2)", hybrid: "var(--k3)", solution: "var(--k5)", other: "var(--k7)" };

// ------------------------------------------------------------------------------------------------ data

const DEMO_EMPTY: InsightsEmpty = {
  status: "empty", reason: "This demo preview has no AMFI figures loaded; the live site shows AMFI's monthly category report.", source: "AMFI Monthly Category Report",
  sourcePage: "https://www.amfiindia.com/research-information/amfi-monthly", disclaimer: "Information only, never advice.", unit: "crore", coverage: "",
};

export const useMfInsights = () =>
  useQuery<Insights, ApiError>({
    queryKey: ["mf", "insights"], queryFn: () => (DEMO ? Promise.resolve(DEMO_EMPTY) : apiGet<Insights>("/api/mf/insights")), staleTime: 600_000,
    retry: (n, e) => e.status >= 500 && n < 2,
  });
