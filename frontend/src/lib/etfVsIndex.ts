// ETF vs index fund (/etfs/compare-index-funds): types of the two endpoints (finlit/etf_vs_index.py), the shareable address state, the growth-of-100 chart
// series, the CSV of each table and the small wording helpers. Pure, so it is tested without the page. Every figure comes from the API; nothing is
// worked out here except layout, rebasing the chart to the range shown, and wording. A blank is "—" with its reason.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";
import { MINUS, csvText, dateIN, nf } from "./format";
import type { Point } from "./etf";

export const DISCLAIMER = "Information only, not investment advice. Past returns do not guarantee future returns.";
export const MAX_PRODUCTS = 4;
export const DEFAULT_SIP = 10000;
export const DEFAULT_LUMP = 100000;

// ------------------------------------------------------------------------------------------------ the options endpoint
export type IndexOpt = { key: string; label: string; code: string | null; etfCount: number; fundCount: number; ready: boolean };
export type ReturnType = "TRI" | "price" | null;
type ProductBase = { name: string; index: string; indexBasis: "benchmark" | "name"; returnType: ReturnType; benchmark: string | null };
export type EtfOpt = ProductBase & { symbol: string; fundHouse: string | null; firstDate: string | null; priceDate: string | null };
export type FundOpt = ProductBase & { code: number; amc: string; plan: string; navDate: string | null };
export type Options = { indices: IndexOpt[]; etfs: EtfOpt[]; funds: FundOpt[]; plan: string; unmatchedFunds: number; conflicts: number; asOf: string | null; source: string; disclaimer: string };

// ------------------------------------------------------------------------------------------------ the compare endpoint
export type Ret = { value: number | null; cagr: number | null; from: string | null; to: string | null; why: string | null };
export type RollStats = { count: number; median?: number; best?: number; worst?: number; mean?: number; positive?: number; why: string | null };
export type H2H = { ahead: number | null; level: number | null; behind: number | null; windows: number };
export type Td = { value: number | null; annual: number | null; why: string | null; product?: number; index?: number; from?: string; to?: string };
export type Tracking = { td: Record<string, Td>; gap: Record<string, { value: number | null; why: string | null }>; te: { value: number | null; returns: number; why: string | null; from?: string; to?: string } };
export type RiskRow = {
  volatility: number | null; volatilityWhy: string | null; maxDrawdown: { value: number | null; peak: string | null; trough: string | null }; downside: number | null; downsideWhy: string | null;
  worstRolling: { value: number; end: string } | null; worstRollingWhy: string | null; best: { value: number; date: string } | null; worst: { value: number; date: string } | null; from: string; to: string; days: number;
};
export type Calc = {
  why?: string | null; value?: number; gain?: number; gainPct?: number; cagr?: number | null; diffVsRef?: { rupees: number; pct: number } | null;
  startDate?: string; startPrice?: number; endDate?: string; endPrice?: number; units?: number;
  installments?: number; invested?: number; first?: string; last?: string; xirr?: number | null; xirrWhy?: string | null;
};
export type Fact = { value: string | null; asOf?: string | null; source?: string | null; note?: string | null; why?: string };
export type Cost = { ter: Fact; terPct: number | null; dragPerYear: number | null; exitLoad: Fact; minimum: Fact; aum: Fact };
export type Product = {
  id: string; kind: "etf" | "fund"; name: string; label: string; house: string | null; plan: string; benchmark: string | null; indexBasis: "benchmark" | "name"; returnType: ReturnType;
  basis: "price" | "nav"; source: string; first: string | null; last: string | null;
};
export type SummaryRow = { category: string; measure: string; unit: string; tol: number; leaders: string[]; level: boolean; values: Record<string, number | null>; gap: number | null; text: string; windowLabel: string | null };
export type Compare = {
  index: { key: string; label: string; code: string | null; levels: string; why: string | null }; plan: string; products: Product[];
  common: { days: number; from?: string | null; to?: string | null; why: string | null };
  returns?: Record<string, Record<string, Ret>>;
  rolling?: { stats: Record<string, RollStats>; headToHead: Record<string, H2H>; ref: string; windows: number };
  sip?: Record<string, Calc>; lump?: Record<string, Calc>; startDay?: string;
  tracking?: Record<string, Tracking>;
  risk?: Record<string, { why?: string; products?: Record<string, RiskRow>; from?: string; to?: string }>;
  chart?: { t: string[]; v: Record<string, number[]>; index: (number | null)[] | null; indexWhy: string | null };
  costs: Record<string, Cost>; etfExtra: Record<string, { premium: number | null; navDate: string | null }>;
  summary: { rows: SummaryRow[]; sentence: string; tolerances: Record<string, number> } | null;
  notes: string[]; tolerances: Record<string, number>; inputs: { sip: number; lump: number; dragBase: number }; asOf: string | null; generatedAt: string; disclaimer: string;
};

export const eviGet = <T,>(path: string): Promise<T> => apiGet<T>(path);
const retry = (n: number, e: ApiError) => e.status >= 500 && n < 1;
export const useEviOptions = (plan: PlanMode) => useQuery<Options, ApiError>({
  queryKey: ["evi", "options", plan], queryFn: () => eviGet<Options>(`/api/etf-vs-index/options?plan=${plan}`), staleTime: 300_000, retry,
});
export const useEviCompare = (s: PageState, enabled: boolean) => useQuery<Compare, ApiError>({
  queryKey: ["evi", "compare", compareQuery(s)], queryFn: () => eviGet<Compare>("/api/etf-vs-index/compare?" + compareQuery(s)), enabled, staleTime: 120_000, placeholderData: keepPreviousData, retry,
});

// ------------------------------------------------------------------------------------------------ address state: a comparison is a link
export type PlanMode = "Direct" | "All";
export type PageState = { index: string; etf: string[]; fund: number[]; plan: PlanMode; sip: number; lump: number; start: string; range: RangeKey; risk: string };
export const RANGE_KEYS = ["1Y", "3Y", "5Y", "MAX"] as const;
export type RangeKey = (typeof RANGE_KEYS)[number];
export const RANGE_MONTHS: Record<RangeKey, number | null> = { "1Y": 12, "3Y": 36, "5Y": 60, MAX: null };
export const DEFAULT_PAGE: PageState = { index: "nifty50", etf: [], fund: [], plan: "Direct", sip: DEFAULT_SIP, lump: DEFAULT_LUMP, start: "", range: "3Y", risk: "" };

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const amount = (v: string | null, lo: number, hi: number, d: number): number => {
  const n = Number(v);
  return v != null && v.trim() !== "" && Number.isFinite(n) && n >= lo && n <= hi ? Math.round(n * 100) / 100 : d;
};
export function validIso(v: string | null | undefined): string {
  if (!v || !ISO.test(v)) return "";
  const d = new Date(v + "T00:00:00Z");
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== v || d.getUTCFullYear() < 2000 ? "" : v;
}
/** Parse the address. Symbols are upper-cased and checked, codes must be whole numbers, and more than four products are cut (ETFs first). */
export function parsePage(sp: URLSearchParams): PageState {
  const etf = [...new Set((sp.get("etf") || "").split(",").map((s) => s.trim().toUpperCase()).filter((s) => /^[A-Z0-9&_.-]{1,24}$/.test(s)))].slice(0, MAX_PRODUCTS - 1);
  const fund = [...new Set((sp.get("fund") || "").split(",").map((s) => s.trim()).filter((s) => /^\d{1,7}$/.test(s)).map(Number).filter((n) => n > 0))].slice(0, MAX_PRODUCTS - Math.min(etf.length, MAX_PRODUCTS - 1));
  const idx = (sp.get("index") || "").toLowerCase();
  const range = (sp.get("range") || "").toUpperCase();
  return {
    index: /^[a-z0-9]{3,20}$/.test(idx) ? idx : DEFAULT_PAGE.index, etf, fund, plan: sp.get("plan") === "All" ? "All" : "Direct",
    sip: amount(sp.get("sip"), 100, 10_000_000, DEFAULT_SIP), lump: amount(sp.get("lump"), 1000, 1_000_000_000, DEFAULT_LUMP), start: validIso(sp.get("start")),
    range: (RANGE_KEYS as readonly string[]).includes(range) ? (range as RangeKey) : "3Y", risk: ["1Y", "3Y", "5Y", "all"].includes(sp.get("risk") || "") ? sp.get("risk")! : "",
  };
}
/** Only what differs from the default goes into the address. */
export function toParams(s: PageState): URLSearchParams {
  const p = new URLSearchParams();
  p.set("index", s.index);
  if (s.etf.length) p.set("etf", s.etf.join(","));
  if (s.fund.length) p.set("fund", s.fund.join(","));
  if (s.plan !== "Direct") p.set("plan", s.plan);
  if (s.sip !== DEFAULT_SIP) p.set("sip", String(s.sip));
  if (s.lump !== DEFAULT_LUMP) p.set("lump", String(s.lump));
  if (s.start) p.set("start", s.start);
  if (s.range !== DEFAULT_PAGE.range) p.set("range", s.range);
  if (s.risk) p.set("risk", s.risk);
  return p;
}
/** The API query: the chart range and the risk window are views of the same answer, so they are not part of it. */
export function compareQuery(s: PageState): string {
  const p = new URLSearchParams({ index: s.index, etf: s.etf.join(","), fund: s.fund.join(","), plan: s.plan, sip: String(s.sip), lump: String(s.lump) });
  if (s.start) p.set("start", s.start);
  return p.toString();
}
export const readyToCompare = (s: PageState): boolean => s.etf.length >= 1 && s.fund.length >= 1 && s.etf.length + s.fund.length <= MAX_PRODUCTS;

// ------------------------------------------------------------------------------------------------ formatting
export const day = (iso: string | null | undefined): string => (iso ? dateIN(iso) : "—");
export const pc = (v: number | null | undefined, d = 2): string => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, d) + "%");
/** Percentage points, signed. */
export const pp = (v: number | null | undefined, d = 2): string => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d) + " pts");
export const sgn = (v: number | null | undefined, d = 2): string => (v == null ? "—" : v > 0 ? `▲ +${nf(v, d)}%` : v < 0 ? `▼ ${MINUS}${nf(v, d)}%` : `${nf(0, d)}%`);
export const inr = (v: number | null | undefined, d = 0): string => (v == null ? "—" : (v < 0 ? MINUS : "") + "₹" + nf(v, d));
export const rtLabel = (t: ReturnType): string => (t === "TRI" ? "Total return (TRI) benchmark" : t === "price" ? "Price-return benchmark" : "Benchmark return type not stated");
export const rtShort = (t: ReturnType): string => (t === "TRI" ? "TRI" : t === "price" ? "Price" : "Type not stated");
export const kindLabel = (p: { kind: string }): string => (p.kind === "etf" ? "ETF" : "Index fund");

/** "₹1,00,000 ÷ ₹250.12 (12 Jan 2021) = 399.8 units × ₹412.50 (29 Oct 2026) = ₹1,64,900": the lump-sum arithmetic in words. */
export function lumpSentence(amountIn: number, c: Calc): string | null {
  if (c.value == null || c.startPrice == null || c.endPrice == null || c.units == null) return null;
  return `${inr(amountIn)} ÷ ${inr(c.startPrice, 4)} (${day(c.startDate)}) = ${nf(c.units, 4)} units × ${inr(c.endPrice, 4)} (${day(c.endDate)}) = ${inr(c.value, 2)}`;
}
/** "0.05% × ₹10,00,000 = ₹500 a year": only the expense ratio, nothing else. */
export function dragSentence(c: Cost, base: number): string | null {
  return c.terPct == null || c.dragPerYear == null ? null : `${nf(c.terPct, 2)}% × ${inr(base)} = ${inr(c.dragPerYear)} a year`;
}

// ------------------------------------------------------------------------------------------------ chart: growth of 100 on the range shown
const addMonths = (iso: string, months: number): string => {
  const d = new Date(iso + "T00:00:00Z");
  const y = d.getUTCFullYear(), m = d.getUTCMonth() - months, dd = d.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return new Date(Date.UTC(y, m, Math.min(dd, last))).toISOString().slice(0, 10);
};
const dayDiff = (a: string, b: string): number => (Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86_400_000;
export type Growth = { start: string; series: Record<string, Point[]>; index: Point[] | null; indexWhy: string | null } | { start: null; why: string };

/** Each product's chart points from the first plotted date on the range, scaled to 100 on that date. The range is cut at a date that exists in the (thinned) series,
 *  so the start is exactly the first date shown. A range longer than the history on file is refused with the reason. */
export function growthOf100(chart: NonNullable<Compare["chart"]>, ids: string[], range: RangeKey): Growth {
  const t = chart.t;
  if (t.length < 2) return { start: null, why: "Not enough common dates for a chart." };
  const months = RANGE_MONTHS[range];
  let i0 = 0;
  if (months != null) {
    const target = addMonths(t[t.length - 1], months);
    if (t[0] > target && dayDiff(target, t[0]) > 10) return { start: null, why: `The common history starts on ${day(t[0])}, after the start of the last ${months / 12} year${months > 12 ? "s" : ""}.` };
    i0 = t.findIndex((d) => d >= target);
    if (i0 < 0 || i0 >= t.length - 1) i0 = 0;
  }
  const series: Record<string, Point[]> = {};
  for (const id of ids) {
    const v = chart.v[id];
    if (!v || !v[i0]) continue;
    series[id] = t.slice(i0).map((d, k) => [d, Math.round((v[i0 + k] / v[i0]) * 100000) / 1000] as Point);
  }
  let index: Point[] | null = null;
  let indexWhy = chart.indexWhy;
  if (chart.index) {
    const base = chart.index[i0];
    if (base) index = t.slice(i0).flatMap((d, k) => { const x = chart.index![i0 + k]; return x == null ? [] : [[d, Math.round((x / base) * 100000) / 1000] as Point]; });
    else indexWhy = indexWhy ?? `Index levels start after ${day(t[i0])}.`;
  }
  return { start: t[i0], series, index, indexWhy };
}

// ------------------------------------------------------------------------------------------------ CSV of each shown table
export type Cell = string | number | null;
export const toCsv = (rows: Cell[][]): string => rows.map((r) => r.map((c) => {
  const s = c == null ? "" : csvText(String(c));
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}).join(",")).join("\r\n") + "\r\n";

const PERIOD_LABEL: Record<string, string> = { "1M": "1 month", "3M": "3 months", "6M": "6 months", "1Y": "1 year", "3Y": "3 years (a year)", "5Y": "5 years (a year)", since: "Since the first common date" };
export const RETURN_ROWS = ["1M", "3M", "6M", "1Y", "3Y", "5Y", "since"] as const;
export const periodLabel = (k: string): string => PERIOD_LABEL[k] ?? k;
const num = (v: number | null | undefined): Cell => (v == null ? "" : v);
const blank = (why: string | null | undefined): string => (why ? `Not available: ${why}` : "Not available");

export type SectionId = "performance" | "cost" | "tracking" | "risk" | "calculator" | "summary";
/** Rows of one section's tables as the page shows them (a blank cell carries its reason). */
export function sectionRows(d: Compare, id: SectionId, riskKey = "all"): Cell[][] {
  const ps = d.products, head: Cell[] = ["Measure", ...ps.map((p) => p.label)];
  const out: Cell[][] = [[`${d.index.label}: ${kindLine(d)}. As of ${d.asOf ?? ""}. ${DISCLAIMER}`], head];
  if (id === "performance" && d.returns && d.rolling) {
    for (const k of RETURN_ROWS) {
      out.push([`Return, ${periodLabel(k)} (%)`, ...ps.map((p) => d.returns![p.id][k].value ?? blank(d.returns![p.id][k].why))]);
      if (k === "3Y" || k === "5Y") out.push([`Yearly rate (CAGR), ${k.replace("Y", " years")} (%)`, ...ps.map((p) => num(d.returns![p.id][k].cagr))]);
    }
    for (const [label, key] of [["Median", "median"], ["Best", "best"], ["Worst", "worst"]] as const) out.push([`1-year rolling return, ${label.toLowerCase()} (%)`, ...ps.map((p) => d.rolling!.stats[p.id][key] ?? blank(d.rolling!.stats[p.id].why))]);
    out.push(["1-year rolling windows with a gain (%)", ...ps.map((p) => num(d.rolling!.stats[p.id].positive))]);
    out.push([`SIP XIRR (%), ${day(d.startDay)} to ${day(d.asOf)}`, ...ps.map((p) => d.sip?.[p.id]?.xirr ?? blank(d.sip?.[p.id]?.xirrWhy ?? d.sip?.[p.id]?.why))]);
  } else if (id === "cost") {
    out.push(["Expense ratio (% a year)", ...ps.map((p) => d.costs[p.id].terPct ?? blank(d.costs[p.id].ter.why))]);
    out.push([`Expense ratio on ${inr(d.inputs.dragBase)} (₹ a year)`, ...ps.map((p) => num(d.costs[p.id].dragPerYear))]);
    out.push(["Exit load", ...ps.map((p) => d.costs[p.id].exitLoad.value ?? blank(d.costs[p.id].exitLoad.why))]);
    out.push(["Minimum investment", ...ps.map((p) => d.costs[p.id].minimum.value ?? blank(d.costs[p.id].minimum.why))]);
    out.push(["Brokerage, bid-ask spread and impact cost are not included"]);
  } else if (id === "tracking" && d.tracking) {
    for (const k of ["1Y", "3Y", "5Y"]) out.push([`Difference from the price index, ${k.replace("Y", " year")} (points)`, ...ps.map((p) => d.tracking![p.id].td[k].value ?? blank(d.tracking![p.id].td[k].why))]);
    out.push(["Tracking error (% a year)", ...ps.map((p) => d.tracking![p.id].te.value ?? blank(d.tracking![p.id].te.why))]);
    for (const k of ["1Y", "3Y", "5Y"]) out.push([`Return minus ${ps[0].label}, ${k.replace("Y", " year")} (points)`, ...ps.map((p) => (p.id === ps[0].id ? "" : d.tracking![p.id].gap[k]?.value ?? blank(d.tracking![p.id].gap[k]?.why)))]);
  } else if (id === "risk" && d.risk) {
    const w = d.risk[riskKey];
    for (const [label, fn] of [
      ["Volatility (% a year)", (r: RiskRow) => r.volatility ?? blank(r.volatilityWhy)], ["Maximum fall (%)", (r: RiskRow) => num(r.maxDrawdown.value)],
      ["Maximum fall, from", (r: RiskRow) => r.maxDrawdown.peak ?? ""], ["Maximum fall, to", (r: RiskRow) => r.maxDrawdown.trough ?? ""],
      ["Downside deviation (% a year)", (r: RiskRow) => r.downside ?? blank(r.downsideWhy)], ["Worst 1-year rolling return (%)", (r: RiskRow) => r.worstRolling?.value ?? blank(r.worstRollingWhy)],
      ["Best day (%)", (r: RiskRow) => num(r.best?.value)], ["Worst day (%)", (r: RiskRow) => num(r.worst?.value)],
    ] as [string, (r: RiskRow) => Cell][]) out.push([label, ...ps.map((p) => (w?.products?.[p.id] ? fn(w.products[p.id]) : blank(w?.why)))]);
  } else if (id === "calculator") {
    out.push([`Lump sum of ${inr(d.inputs.lump)} from ${day(d.startDay)}: value (₹)`, ...ps.map((p) => d.lump?.[p.id]?.value ?? blank(d.lump?.[p.id]?.why))]);
    out.push(["Lump sum: difference from the first product (₹)", ...ps.map((p) => num(d.lump?.[p.id]?.diffVsRef?.rupees))]);
    out.push([`Monthly SIP of ${inr(d.inputs.sip)}: invested (₹)`, ...ps.map((p) => num(d.sip?.[p.id]?.invested))]);
    out.push(["SIP: value (₹)", ...ps.map((p) => d.sip?.[p.id]?.value ?? blank(d.sip?.[p.id]?.why))]);
    out.push(["SIP: difference from the first product (₹)", ...ps.map((p) => num(d.sip?.[p.id]?.diffVsRef?.rupees))]);
    out.push(["SIP: XIRR (%)", ...ps.map((p) => d.sip?.[p.id]?.xirr ?? blank(d.sip?.[p.id]?.xirrWhy ?? d.sip?.[p.id]?.why))]);
  } else if (id === "summary" && d.summary) {
    const names = Object.fromEntries(ps.map((p) => [p.id, p.label]));
    out.length = 1;
    out.push(["Category", "Measure", "Ahead", "Values"]);
    for (const r of d.summary.rows) out.push([r.category, r.measure, r.level ? "Level" : r.leaders.map((k) => names[k]).join(" and ") || "Not enough data", Object.entries(r.values).map(([k, v]) => `${names[k]}: ${v ?? "n/a"}`).join("; ")]);
    out.push([d.summary.sentence]);
  }
  return out;
}
const kindLine = (d: Compare): string => d.products.map((p) => `${p.label} (${kindLabel(p)}, ${p.basis === "nav" ? "NAV" : "closing price"})`).join("; ");

export function downloadCsv(name: string, rows: Cell[][]): void {
  const url = URL.createObjectURL(new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The tiles of the dashboard, in order. "Summary by category" is the section the mockup calls the FinLit verdict: it describes, and never names a winner. */
export const TILES: { id: SectionId; title: string; sub: string; icon: string }[] = [
  { id: "performance", title: "Performance", sub: "CAGR, rolling returns, XIRR", icon: "growth" },
  { id: "cost", title: "Cost analysis", sub: "Expense and ownership costs", icon: "rupee" },
  { id: "tracking", title: "Tracking quality", sub: "Error and difference", icon: "gauge" },
  { id: "risk", title: "Risk analysis", sub: "Volatility and drawdown", icon: "activity" },
  { id: "calculator", title: "Investment calculator", sub: "Compare final wealth", icon: "wallet" },
  { id: "summary", title: "Summary by category", sub: "Who was ahead on each measure", icon: "check" },
];
