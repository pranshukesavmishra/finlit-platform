// ETFs: types, formatting, list state (URL), the compare tray, chart maths and the plain-words readings. Pure, so it is tested without the pages.
// Every figure comes from the API (finlit/etf.py); nothing is computed here except layout and wording. A blank is "—" with its reason.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, type ApiError } from "./api";
import { DEMO } from "./demo";
import { MINUS, dateIN, nf } from "./format";
import type { PortfolioResult } from "../holdings/types";

export const DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns.";
export const NOT_PUBLISHED = "Not published in our price data source";

export type Why = Record<string, string>;
export type EtfItem = {
  symbol: string; name: string; isin: string; fundHouse: string | null; category: string | null; categoryLabel: string | null; assetClass: string | null;
  price: number | null; previousClose: number | null; changePct: number | null; priceDate: string | null; volume: number | null; avgTurnover: number | null;
  ret1m: number | null; ret6m: number | null; ret1y: number | null; ret3y: number | null; ret5y: number | null; cagr3y: number | null; cagr5y: number | null;
  vol1y: number | null; mdd1y: number | null; mdd3y: number | null; mdd5y: number | null; high52: number | null; low52: number | null; from52: number | null;
  rangeFrom: string | null; firstDate: string | null; points: number; breakDate: string | null;
  nav: number | null; navDate: string | null; premium: number | null; premiumWide: boolean; why: Why; rank: number | null; hot: boolean;
};
export type Facet = { key: string; label: string; group: string; count: number };
export type EtfList = {
  items: EtfItem[]; total: number; universe: number; hotCount?: number; offset: number; limit: number; excluded: number; categories: Facet[]; groups: { key: string; label: string; count: number }[];
  asOf: string | null; updatedAt: string | null; source: string; disclaimer: string;
};
export const RANGES = ["1M", "6M", "1Y", "3Y", "5Y", "MAX"] as const;
export type RangeKey = (typeof RANGES)[number];
export const RANGE_LABEL: Record<RangeKey, string> = { "1M": "1M", "6M": "6M", "1Y": "1Y", "3Y": "3Y", "5Y": "5Y", MAX: "Max" };
export type Point = [string, number];
export type SeriesOut = { range: RangeKey; available: boolean; why?: string; grain: "daily" | "weekly"; from?: string; to?: string; points: Point[] };
export type Fact = { label: string; value: string | number; source?: string; note?: string; unit?: string };
/** The three figures every page leads with. `value` is a percent; `from`/`to` are the two closes it was worked out from (absent when the chart history is not on hand). */
export type HeadlineKey = "1d" | "1y" | "5y";
export type Headline = {
  key: HeadlineKey; label: string; value: number | null; annualised: number | null; why: string | null; basis: string;
  from: { date: string; close: number } | null; to: { date: string; close: number } | null;
};
export type EtfDetail = Omit<EtfItem, "nav"> & {
  headline: Headline[];
  returns: { key: string; label: string; price: number | null; annualised: number | null; why: string | null }[];
  risk: {
    vol1y: { value: number | null; why: string | null; days: number | null };
    drawdowns: { key: string; label: string; value: number | null; why: string | null; peak: string | null; trough: string | null }[];
    range52: { high: number | null; low: number | null; from: string | null; fromHighPct: number | null; why: string | null };
  };
  nav: { value: number; date: string; premium: number | null; premiumWhy: string | null; source: string } | null;
  facts: Fact[]; unavailable: string[]; unavailableWhy: string; series: SeriesOut; ranges: Record<RangeKey, { available: boolean; why: string | null }>;
  breakNote: string | null; priceNote: string | null; asOf: string | null; updatedAt: string | null; source: string; disclaimer: string;
};
/** One fund-house fact: a value with its date and source, or the reason it is missing. */
export type FactCell = { value?: string | number | string[] | null; asOf?: string | null; source?: string | null; unavailable?: string | null; note?: string | null };
export type EtfFacts = { symbol: string; isin: string; unavailable: string | null; facts: Record<string, FactCell>; disclaimer: string };
export type EtfCompare = {
  symbols: string[]; range: RangeKey; start: string | null; items: EtfItem[]; series: Record<string, Point[]>; notes: string[];
  asOf: string | null; updatedAt: string | null; source: string; disclaimer: string;
};

// ------------------------------------------------------------------------------------------------ formatting
export const pct = (v: number | null | undefined, d = 2): string => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, d) + "%");
/** With an arrow and a sign, so colour is never the only cue. */
export const move = (v: number | null | undefined, d = 2): string => (v == null ? "—" : v > 0 ? `▲ +${nf(v, d)}%` : v < 0 ? `▼ ${MINUS}${nf(v, d)}%` : `${nf(0, d)}%`);
export const rupee = (v: number | null | undefined, d = 2): string => (v == null ? "—" : "₹" + nf(v, d));
/** Rupees traded in a day, in crore or lakh. */
export function traded(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e7) return "₹" + nf(v / 1e7, v >= 1e9 ? 0 : 1) + " Cr";
  if (v >= 1e5) return "₹" + nf(v / 1e5, 1) + " lakh";
  return "₹" + nf(v, 0);
}
export const day = (iso: string | null | undefined): string => (iso ? dateIN(iso) : "—");
export function stamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }) + " IST";
}
export const tone = (v: number | null | undefined): "up" | "down" | "flat" => (v == null || v === 0 ? "flat" : v > 0 ? "up" : "down");

// ------------------------------------------------------------------------------------------------ columns of the list
export type ColKey = "category" | "price" | "change" | "ret1y" | "ret5y" | "turnover" | "premium" | "fundHouse";
export type Col = {
  key: ColKey; label: string; short: string; sort: string | null; get: (i: EtfItem) => number | string | null; text: (i: EtfItem) => string;
  why?: string; term?: GlossName; def: boolean; help: string; num: boolean;
};
const num = (f: (i: EtfItem) => number | null, fmt: (v: number | null) => string, why?: string): Pick<Col, "get" | "text" | "why"> => ({ get: f, text: (i) => fmt(f(i)), why });
/** The list shows exactly three return columns: 1 day, 1 year, 5 years. 5 years is the TOTAL price change over the five years, not a yearly rate. */
export const COLUMNS: Col[] = [
  { key: "category", label: "Category", short: "Category", sort: null, def: true, num: false, help: "What the ETF follows, taken from its registered name. Blank when the name does not say clearly.", get: (i) => i.categoryLabel, text: (i) => i.categoryLabel ?? "—" },
  { key: "price", label: "Price (₹)", short: "Price", sort: "price", def: true, num: true, help: "Last close on the NSE.", ...num((i) => i.price, (v) => rupee(v)) },
  { key: "change", label: "1-day change", short: "1 day", sort: "change", def: true, num: true, help: "Change from the previous close to the last close.", ...num((i) => i.changePct, (v) => move(v), "change") },
  { key: "ret1y", label: "1-year price return", short: "1 year", sort: "ret1y", def: true, num: true, help: "Price change over 1 year. Dividends are not included.", term: "Price return", ...num((i) => i.ret1y, (v) => pct(v), "ret_1y") },
  { key: "ret5y", label: "5-year price return (total)", short: "5 years", sort: "ret5y", def: true, num: true, help: "Total price change over 5 years, not a yearly rate. Dividends are not included.", term: "Price return", ...num((i) => i.ret5y, (v) => pct(v), "ret_5y") },
  { key: "turnover", label: "Traded value a day", short: "Traded/day", sort: "turnover", def: false, num: true, help: "Average rupees traded each day over the last 20 sessions.", term: "Traded value (turnover)", ...num((i) => i.avgTurnover, traded) },
  { key: "premium", label: "Premium / discount to NAV", short: "vs NAV", sort: "premium", def: false, num: true, help: "Exchange close against AMFI's NAV of the same day.", term: "Premium and discount to NAV", ...num((i) => i.premium, (v) => pct(v), "nav_premium") },
  { key: "fundHouse", label: "Fund house", short: "Fund house", sort: null, def: false, num: false, help: "From AMFI's register.", get: (i) => i.fundHouse, text: (i) => i.fundHouse ?? "—" },
];
export const DEFAULT_COLS: ColKey[] = COLUMNS.filter((c) => c.def).map((c) => c.key);
export const COL_BY: Record<string, Col> = Object.fromEntries(COLUMNS.map((c) => [c.key, c]));

/** Why a figure is blank, in plain words: the API's own reason, else a generic one. */
export function whyBlank(i: EtfItem, c: Col): string {
  if (c.key === "premium" && i.nav == null) return "No NAV found in AMFI's file for this ETF";
  if (c.key === "category") return "The fund's name does not say clearly what it follows";
  if (c.key === "fundHouse") return "Not found in AMFI's register";
  if (c.key === "turnover") return "Too few trading days to average";
  if (c.key === "change") return (c.why && i.why?.[c.why]) || "No previous close to compare with";
  return (c.why && i.why?.[c.why]) || "Not enough price history";
}

// ------------------------------------------------------------------------------------------------ glossary words used on the pages
/** Every glossary term the ETF pages explain. The test checks each one exists in the glossary (or in the pending list of new terms). */
export const GLOSSARY_NAMES = [
  "ETF (exchange-traded fund)", "Net asset value (NAV)", "Premium and discount to NAV", "Price return", "Absolute and annualised return", "CAGR (compound annual growth rate)",
  "Volatility", "Drawdown", "52-week high and low", "Traded value (turnover)", "Tracking error", "Assets under management (AUM)", "Expense ratio", "Benchmark",
  "Liquid ETF (1-day rate or overnight ETF)", "Gold ETF and silver ETF", "G-Sec ETF (gilt ETF)", "Factor ETF (smart-beta or strategy ETF)", "Overseas (international) ETF", "Sector and thematic ETF",
] as const;
export type GlossName = (typeof GLOSSARY_NAMES)[number];
/** The glossary entry that explains an ETF category, for the (i) next to it. */
export const CATEGORY_TERM: Record<string, GlossName> = {
  liquid: "Liquid ETF (1-day rate or overnight ETF)", gsec: "G-Sec ETF (gilt ETF)", bond: "G-Sec ETF (gilt ETF)", gold: "Gold ETF and silver ETF", silver: "Gold ETF and silver ETF",
  intl: "Overseas (international) ETF", factor: "Factor ETF (smart-beta or strategy ETF)",
  ...Object.fromEntries(["psu_bank", "pvt_bank", "financial", "bank", "ev", "auto", "health", "it", "internet", "fmcg", "consumption", "metal", "commodities", "energy", "power", "infra", "psu", "realty", "chemicals", "defence", "manufacturing", "theme"].map((k) => [k, "Sector and thematic ETF" as GlossName])),
};

// ------------------------------------------------------------------------------------------------ list state in the address bar
export type Bounds = [number | null, number | null];
export const FILTERS = [
  { key: "ret1y", label: "1-year price return", unit: "%" },
  { key: "ret5y", label: "5-year price return (total)", unit: "%" },
] as const;
export type FilterKey = (typeof FILTERS)[number]["key"];
export type ListState = { q: string; category: string[]; asset: string[]; sort: string; order: "asc" | "desc"; bounds: Partial<Record<FilterKey, Bounds>>; offset: number };
export const PAGE = 40;
export const DEFAULT_STATE: ListState = { q: "", category: [], asset: [], sort: "turnover", order: "desc", bounds: {}, offset: 0 };
const SORTS = new Set(["name", ...COLUMNS.map((c) => c.sort).filter(Boolean) as string[]]);
const bound = (v: string | null): number | null => {
  if (v == null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && Math.abs(n) <= 100000 ? n : null;
};

export function parseState(sp: URLSearchParams): ListState {
  const sort = sp.get("sort") || "";
  const s: ListState = {
    ...DEFAULT_STATE, bounds: {},
    q: (sp.get("q") || "").slice(0, 60),
    category: (sp.get("category") || "").split(",").filter(Boolean).slice(0, 30),
    asset: (sp.get("asset") || "").split(",").filter(Boolean).slice(0, 10),
    sort: SORTS.has(sort) ? sort : "turnover",
    order: sp.get("order") === "asc" ? "asc" : sp.get("order") === "desc" ? "desc" : (sort === "name" ? "asc" : "desc"),
    offset: Math.max(0, Math.min(5000, Math.floor(Number(sp.get("offset")) || 0))),
  };
  for (const f of FILTERS) {
    const lo = bound(sp.get(f.key + "Min")), hi = bound(sp.get(f.key + "Max"));
    if (lo != null || hi != null) s.bounds[f.key] = [lo, hi];
  }
  return s;
}

/** Only what differs from the default goes into the address, so the plain list has a plain link. */
export function toParams(s: ListState): URLSearchParams {
  const p = new URLSearchParams();
  if (s.q.trim()) p.set("q", s.q.trim());
  if (s.category.length) p.set("category", s.category.join(","));
  if (s.asset.length) p.set("asset", s.asset.join(","));
  if (s.sort !== DEFAULT_STATE.sort || s.order !== (s.sort === "name" ? "asc" : "desc")) { p.set("sort", s.sort); p.set("order", s.order); }
  for (const f of FILTERS) {
    const b = s.bounds[f.key];
    if (b?.[0] != null) p.set(f.key + "Min", String(b[0]));
    if (b?.[1] != null) p.set(f.key + "Max", String(b[1]));
  }
  if (s.offset) p.set("offset", String(s.offset));
  return p;
}
export function apiQuery(s: ListState, limit = PAGE): string {
  const p = toParams(s);
  p.set("sort", s.sort); p.set("order", s.order); p.set("limit", String(limit));
  return p.toString();
}
export const activeFilters = (s: ListState): number => s.category.length + s.asset.length + Object.keys(s.bounds).length;

/** Clicking a column: a new column starts from its natural order (name A to Z, figures high to low); the same column flips. */
export function nextSort(s: ListState, key: string): ListState {
  if (s.sort === key) return { ...s, order: s.order === "desc" ? "asc" : "desc", offset: 0 };
  return { ...s, sort: key, order: key === "name" ? "asc" : "desc", offset: 0 };
}

// ------------------------------------------------------------------------------------------------ the compare tray (kept in this browser only)
export const MAX_COMPARE = 4;
const TRAY_KEY = "finlit-etf-compare";
export function parseSymbols(raw: string | null | undefined): string[] {
  const out: string[] = [];
  for (const s of (raw || "").split(",")) {
    const t = s.trim().toUpperCase();
    if (/^[A-Z0-9&_.-]{1,24}$/.test(t) && !out.includes(t)) out.push(t);
  }
  return out.slice(0, MAX_COMPARE);
}
const readTray = (): string[] => { try { return parseSymbols(localStorage.getItem(TRAY_KEY)); } catch { return []; } };
const writeTray = (s: string[]) => { try { localStorage.setItem(TRAY_KEY, s.join(",")); } catch { /* private mode: the tray lives for this page only */ } window.dispatchEvent(new Event("etf-tray")); };
let memory: string[] | null = null;
export function useTray() {
  const [tray, setTray] = useState<string[]>(() => memory ?? readTray());
  useEffect(() => {
    const sync = () => { memory = readTray(); setTray(memory); };
    window.addEventListener("etf-tray", sync); window.addEventListener("storage", sync);
    return () => { window.removeEventListener("etf-tray", sync); window.removeEventListener("storage", sync); };
  }, []);
  const set = (next: string[]) => { memory = parseSymbols(next.join(",")); writeTray(memory); setTray(memory); };
  return {
    tray, set, has: (s: string) => tray.includes(s), full: tray.length >= MAX_COMPARE,
    toggle: (s: string) => (tray.includes(s) ? set(tray.filter((x) => x !== s)) : tray.length < MAX_COMPARE ? set([...tray, s]) : undefined),
    remove: (s: string) => set(tray.filter((x) => x !== s)), clear: () => set([]),
  };
}

// ------------------------------------------------------------------------------------------------ data
async function etfGet<T>(path: string): Promise<T> {
  if (DEMO) return (await import("../etf/demo")).demoGet<T>(path);
  return apiGet<T>(path);
}
const retry = (n: number, e: ApiError) => e.status >= 500 && n < 1;
export const useEtfList = (s: ListState) => useQuery<EtfList, ApiError>({
  queryKey: ["etf", "list", apiQuery(s)], queryFn: () => etfGet<EtfList>("/api/etf?" + apiQuery(s)), placeholderData: keepPreviousData, staleTime: 60_000, retry,
});
export const useEtf = (symbol: string, range: RangeKey) => useQuery<EtfDetail, ApiError>({
  queryKey: ["etf", "detail", symbol, range], queryFn: () => etfGet<EtfDetail>(`/api/etf/${encodeURIComponent(symbol)}?range=${range}`), placeholderData: keepPreviousData, staleTime: 60_000, retry,
});
export const useEtfCompare = (symbols: string[], range: RangeKey) => useQuery<EtfCompare, ApiError>({
  queryKey: ["etf", "compare", symbols.join(","), range], enabled: symbols.length >= 2, placeholderData: keepPreviousData, staleTime: 60_000, retry,
  queryFn: () => etfGet<EtfCompare>(`/api/etf/compare?symbols=${encodeURIComponent(symbols.join(","))}&range=${range}`),
});
export const useEtfFacts = (symbol: string) => useQuery<EtfFacts, ApiError>({
  queryKey: ["etf", "facts", symbol], queryFn: () => etfGet<EtfFacts>(`/api/etf/${encodeURIComponent(symbol)}/facts`), staleTime: 300_000, retry,
});
/** The portfolio, or { unavailable } with the reason: exactly what the shared HoldingsSection takes. */
export const useEtfPortfolio = (symbol: string) => useQuery<PortfolioResult, ApiError>({
  queryKey: ["etf", "portfolio", symbol], staleTime: 300_000, retry,
  queryFn: async () => {
    const r = await etfGet<PortfolioResult & { unavailable?: string | null }>(`/api/etf/${encodeURIComponent(symbol)}/portfolio`);
    return r.unavailable ? { unavailable: r.unavailable } : r;
  },
});
export const useEtfSearch = (q: string) => useQuery<EtfList, ApiError>({
  queryKey: ["etf", "search", q], queryFn: () => etfGet<EtfList>(`/api/etf?q=${encodeURIComponent(q)}&limit=8&sort=turnover&order=desc`), enabled: q.trim().length > 0, staleTime: 60_000, placeholderData: keepPreviousData, retry,
});

// ------------------------------------------------------------------------------------------------ chart maths
const MS = 86_400_000;
export const t = (iso: string): number => Date.parse(iso + "T00:00:00Z");

/** Round tick values that frame [lo, hi]: about `n` of them, steps of 1, 2, 2.5 or 5 times a power of ten. */
export function niceTicks(lo: number, hi: number, n = 5): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  if (hi - lo < 1e-9) { const e = Math.max(Math.abs(lo) * 0.01, 0.5); lo -= e; hi += e; }
  const raw = (hi - lo) / Math.max(1, n - 1), mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.999; v += step) out.push(Math.round(v / step) * step);
  return out;
}

export type Frame = { x0: number; x1: number; y0: number; y1: number; tMin: number; tMax: number; vMin: number; vMax: number };
/** Pixel frame for the series: x by calendar date (so a weekly and a daily series line up), y padded a little and rounded to tick values. */
export function frameOf(series: Point[][], w: number, h: number, pad = { l: 52, r: 14, t: 12, b: 26 }): Frame | null {
  const pts = series.flat();
  if (pts.length < 2) return null;
  const ts = pts.map((p) => t(p[0])), vs = pts.map((p) => p[1]);
  const tMin = Math.min(...ts), tMax = Math.max(...ts);
  const ticks = niceTicks(Math.min(...vs), Math.max(...vs), 5);
  return { x0: pad.l, x1: w - pad.r, y0: h - pad.b, y1: pad.t, tMin, tMax: tMax === tMin ? tMin + MS : tMax, vMin: ticks[0], vMax: ticks[ticks.length - 1] };
}
export const px = (f: Frame, iso: string): number => f.x0 + ((t(iso) - f.tMin) / (f.tMax - f.tMin)) * (f.x1 - f.x0);
export const py = (f: Frame, v: number): number => f.y0 + ((v - f.vMin) / (f.vMax - f.vMin || 1)) * (f.y1 - f.y0);
export function linePath(f: Frame, pts: Point[]): string {
  return pts.map((p, i) => `${i ? "L" : "M"}${px(f, p[0]).toFixed(1)},${py(f, p[1]).toFixed(1)}`).join("");
}
/** Index of the point nearest to a pixel x (points are in date order). */
export function nearest(f: Frame, pts: Point[], x: number): number {
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (px(f, pts[mid][0]) <= x) lo = mid; else hi = mid; }
  return Math.abs(px(f, pts[lo][0]) - x) <= Math.abs(px(f, pts[hi][0]) - x) ? lo : hi;
}
/** Dates for the x axis: at most `max`, evenly spread in time, first and last included, no two closer than `gap` pixels. */
export function dateTicks(f: Frame, max: number, gap = 70): string[] {
  const n = Math.max(2, Math.min(max, Math.floor((f.x1 - f.x0) / gap)));
  const out: string[] = [];
  for (let i = 0; i < n; i++) out.push(new Date(f.tMin + ((f.tMax - f.tMin) * i) / (n - 1)).toISOString().slice(0, 10));
  return out;
}
export function axisDate(iso: string, spanDays: number): string {
  const d = new Date(iso + "T00:00:00Z");
  return spanDays <= 200 ? d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }) : d.toLocaleDateString("en-IN", { month: "short", year: "2-digit", timeZone: "UTC" });
}
export const spanDays = (f: Frame): number => (f.tMax - f.tMin) / MS;

/** Series of the compare chart for a demo/offline use: each ETF's closes from `start` on, scaled to 100 at (or just before) `start`. */
export function rebase(series: Record<string, Point[]>, start: string): Record<string, Point[]> {
  const out: Record<string, Point[]> = {};
  for (const [sym, pts] of Object.entries(series)) {
    let i = 0;
    for (let k = 0; k < pts.length; k++) if (pts[k][0] <= start) i = k;
    const base = pts[i]?.[1];
    if (!base) continue;
    out[sym] = pts.slice(i).map((p) => [p[0], Math.round((p[1] / base) * 100000) / 1000] as Point);
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ plain words
/** A typical day's move is the yearly volatility divided by the square root of 252 trading days. */
export const typicalDay = (annualPct: number): number => annualPct / Math.sqrt(252);
export function volReading(v: number | null): string | null {
  if (v == null) return null;
  const d = typicalDay(v);
  return `Over the last year the price swung about ${nf(v, 1)}% on a yearly basis. On a typical day that is a move of roughly ${nf(d, d < 0.1 ? 2 : 1)}% up or down.`;
}
export function fallReading(d: { label: string; value: number | null; peak: string | null; trough: string | null }): string | null {
  if (d.value == null) return null;
  if (d.value === 0) return `In the last ${d.label} the price never closed below an earlier high.`;
  return `The worst fall in the last ${d.label} was ${nf(Math.abs(d.value), 1)}%, from a high on ${day(d.peak)} to a low on ${day(d.trough)}.`;
}
export function rangeReading(price: number | null, high: number | null, low: number | null): string | null {
  if (price == null || high == null || low == null) return null;
  const below = (1 - price / high) * 100, above = (price / low - 1) * 100;
  return `The price is ${nf(below, 1)}% below its high of ${rupee(high)} and ${nf(above, 1)}% above its low of ${rupee(low)}.`;
}
/** Where the price sits between the low (0) and the high (100) of the range. */
export const rangePosition = (price: number | null, high: number | null, low: number | null): number | null =>
  price == null || high == null || low == null || high <= low ? null : Math.max(0, Math.min(100, ((price - low) / (high - low)) * 100));
export function premiumReading(nav: { value: number; date: string; premium: number | null } | null): string | null {
  if (!nav || nav.premium == null) return null;
  const p = nav.premium, a = nf(Math.abs(p), 2);
  return `On ${day(nav.date)} the exchange close was ${p === 0 ? "equal to" : `${a}% ${p > 0 ? "above" : "below"}`} the NAV (${rupee(nav.value, 4)}). ${p > 0 ? "A premium means buyers paid more on the exchange than the holdings were worth that day." : p < 0 ? "A discount means the exchange price was lower than the holdings were worth that day." : ""}`.trim();
}
export function summaryOfSeries(name: string, s: SeriesOut): string {
  if (!s.available || s.points.length < 2) return `${name}: no price chart for this range.`;
  const vs = s.points.map((p) => p[1]), a = s.points[0], b = s.points[s.points.length - 1];
  return `${name} price from ${day(a[0])} (${rupee(a[1])}) to ${day(b[0])} (${rupee(b[1])}). Lowest ${rupee(Math.min(...vs))}, highest ${rupee(Math.max(...vs))}.`;
}
