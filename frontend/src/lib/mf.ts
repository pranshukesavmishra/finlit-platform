// Mutual funds: API types and hooks, the list's URL state, number text, column choices, the compare tray, search and chart geometry.
// Everything pure lives here so it is tested without the page (mf.test.ts). Data comes from AMFI via /api/mf; see backend/finlit/mf.py.
import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { apiGet, type ApiError } from "./api";
import { DEMO } from "./demo";
import { MINUS, dateIN, nf } from "./format";
import { score, tokens } from "./metricSearch";
import type { PortfolioResult } from "../holdings/types";

export const DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns.";
export const MIRROR_LABEL = "NAV history: third-party mirror of AMFI data (api.mfapi.in)";

export type Facts = { dataDate: string | null; updatedAt: string | null; source: string; disclaimer: string; excludedAmcs?: string[] };
export type FundRow = {
  code: number; name: string; amc: string; category: string; plan: string; option: string; optionClass: "Growth" | "IDCW" | "Other"; nav: number | null; navDate: string | null;
  change: number | null; changeSince?: string | null; active: boolean; r1y: number | null; r5y: number | null; retDate?: string | null;
  noReturns: "stopped" | "idcw" | "unstated" | "no_history" | "short" | null; rank?: number;
};
export type FundList = Facts & { total: number; page: number; size: number; pages: number; items: FundRow[] };
export type HotList = Facts & { basis: string | null; items: FundRow[] };
export type FilterCategory = { name: string; group: string; type: string; active: number; total: number };
export type FundFilters = Facts & {
  categories: FilterCategory[]; amcs: { name: string; active: number; total: number }[]; plans: { name: string; active: number }[]; options: { name: string; active: number }[];
  totals: { schemes: number; active: number; withHistory: number };
};
export type Ret = { value: number | null; kind: "absolute" | "cagr"; from: string | null; why: string | null };
export type Risk = {
  vol1y: { value: number | null; why: string | null }; vol3y: { value: number | null; why: string | null };
  maxDrawdown: { value: number | null; why: string | null; peak: string | null; trough: string | null; since: string | null };
};
export type RangeKey = "1M" | "6M" | "1Y" | "3Y" | "5Y" | "MAX";
export type Points = { t: string[]; v: number[] };
export type Change = { abs: number; pct: number; since: string | null };
export type HistoryInfo = { source: "amfi" | "mirror" | null; from: string | null; to?: string | null; points?: number; complete?: boolean; note: string | null };
export type FundDetail = Facts & {
  code: number; name: string; isin: string | null; isinReinvest: string | null; amc: string; category: string; categoryGroup: string; schemeType: string; plan: string;
  optionClass: FundRow["optionClass"]; option: string; active: boolean; nav: number | null; navDate: string | null; prevNav: number | null; prevDate: string | null; change: Change | null;
  returns: Record<"1m" | "6m" | "1y" | "3y" | "5y", Ret>; retDate?: string | null; risk: Risk; returnsNote: string | null; series: Partial<Record<RangeKey, Points>>; history: HistoryInfo;
  family: { code: number; name: string; plan: string; optionClass: string; option: string; nav: number | null; navDate: string | null; active: boolean }[];
  notAvailable?: { items: string[]; why: string };
};
export type CompareFund = {
  code: number; name: string; amc: string; category: string; plan: string; option: string; optionClass: string; nav: number | null; navDate: string | null; change: Change | null;
  active: boolean; returns: FundDetail["returns"]; retDate?: string | null; risk: Risk; history: HistoryInfo;
};
/** One fund fact: a value with its date and source, or the reason there is none. */
export type FactVal = { value: string | number | string[] | null; asOf?: string | null; source?: string; unit?: string } | { unavailable: string };
export type FundFacts = { code: number; facts: Record<string, FactVal>; order: string[] };
export type FundCompare = Facts & {
  funds: CompareFund[]; chart: { from: string; range: RangeKey; series: ({ code: number } & Points)[] } | null; chartNote: string | null; notAvailable: FundDetail["notAvailable"];
};

// ------------------------------------------------------------------------------------------------ number text

/** A NAV as AMFI gives it: at least 2 and at most 4 decimals (some schemes publish 8; the full value is in the tooltip). */
export function navText(n: number | null | undefined): string {
  if (n == null) return "—";
  const dec = (String(n).split(".")[1] || "").length;
  return "₹" + nf(n, Math.min(4, Math.max(2, dec)));
}
export const navFull = (n: number | null | undefined) => (n == null ? "" : `₹${n}`);

/** Percent with a real minus sign and an explicit plus; "—" when there is no figure. */
export function pctText(v: number | null | undefined, d = 2, plus = true): string {
  if (v == null) return "—";
  const body = nf(Math.abs(v), d) + "%";
  return v < 0 ? MINUS + body : (plus && v > 0 ? "+" : "") + body;
}
export const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");
export const dayText = (iso: string | null | undefined) => (iso ? dateIN(iso) : "—");

/** The reason a scheme has no return figures at all, in words (the server sends a short code). */
export function noReturnsText(code: FundRow["noReturns"]): string {
  switch (code) {
    case "stopped": return "This scheme has stopped publishing NAVs.";
    case "idcw": return "Returns are not worked out for IDCW (payout) options: each payout lowers the NAV. See the Growth option of the same fund.";
    case "unstated": return "AMFI does not state a Growth option for this scheme, so NAV-to-NAV returns could miss payouts.";
    case "no_history": return "NAV history for this scheme is not loaded yet.";
    case "short": return "Not enough NAV history yet.";
    default: return "";
  }
}

/** "Mid Cap Fund" etc. for a heading; AMFI's category text is "Equity Scheme - Mid Cap Fund". */
export const categoryShort = (c: string) => (c.includes(" - ") ? c.split(" - ").slice(1).join(" - ") : c);

// ------------------------------------------------------------------------------------------------ list columns

export type SortKey = "name" | "amc" | "category" | "nav" | "navDate" | "change" | "r1y" | "r5y";
export type ColId = "amc" | "category" | "plan" | "option" | "nav" | "navDate" | "change" | "r1y" | "r5y";
export type ColDef = { id: ColId; label: string; hint: string; sort: SortKey | null; num: boolean; term?: string };
/** The name column is always shown (and is the link); these can be switched on and off. */
export const COLUMNS: ColDef[] = [
  { id: "amc", label: "Fund house", hint: "The company that runs the scheme", sort: "amc", num: false },
  { id: "category", label: "Category", hint: "The group AMFI files the scheme in", sort: "category", num: false },
  { id: "plan", label: "Plan", hint: "Direct or Regular", sort: null, num: false },
  { id: "option", label: "Option", hint: "Growth or IDCW (payout)", sort: null, num: false },
  { id: "nav", label: "NAV", hint: "Net asset value of one unit, latest", sort: "nav", num: true },
  { id: "navDate", label: "NAV date", hint: "The day the NAV is for", sort: "navDate", num: true },
  { id: "change", label: "1 day", hint: "Change of the NAV against the previous NAV (its date is shown on the scheme's page)", sort: "change", num: true },
  { id: "r1y", label: "1 year", hint: "Total change in NAV over 1 year (not per year)", sort: "r1y", num: true },
  { id: "r5y", label: "5 year, per year (CAGR)", hint: "Yearly rate (CAGR) over 5 years: the rate that, compounded for five years, gives the total change", sort: "r5y", num: true },
];
export const DEFAULT_COLS: ColId[] = ["amc", "category", "nav", "change", "r1y", "r5y"];
const COLS_KEY = "finlit-mf-cols-v2";
const ALL_IDS = new Set<string>(COLUMNS.map((c) => c.id));

/** Saved column choice, cleaned of anything unknown; the default when nothing valid is saved (storage can be blocked). */
export function readCols(): ColId[] {
  try {
    const raw = JSON.parse(localStorage.getItem(COLS_KEY) || "null");
    if (Array.isArray(raw)) { const ok = raw.filter((x): x is ColId => typeof x === "string" && ALL_IDS.has(x)); if (ok.length) return COLUMNS.map((c) => c.id).filter((id) => ok.includes(id)); }
  } catch { /* blocked or corrupt: use the default */ }
  return DEFAULT_COLS;
}
export function writeCols(cols: ColId[]) { try { localStorage.setItem(COLS_KEY, JSON.stringify(cols)); } catch { /* private mode */ } }

// ------------------------------------------------------------------------------------------------ list URL state

export type ListQuery = {
  q: string; category: string; amc: string; plan: string; option: string; stopped: boolean; sort: SortKey | ""; dir: "asc" | "desc"; page: number; size: number;
  min1y: string; max1y: string; min5y: string; max5y: string; view: "" | "ready";
};
export const SIZES = [25, 50, 100];
export const EMPTY_QUERY: ListQuery = { q: "", category: "", amc: "", plan: "", option: "", stopped: false, sort: "", dir: "asc", page: 1, size: 50, min1y: "", max1y: "", min5y: "", max5y: "", view: "" };
const SORT_KEYS = new Set<string>(COLUMNS.flatMap((c) => (c.sort ? [c.sort] : [])).concat("name"));
const RANGE_FIELDS = ["min1y", "max1y", "min5y", "max5y"] as const;
/** A number typed in a range box, or "" when it is not one (so a stray letter never reaches the server). */
export const cleanNum = (s: string) => { const t = s.trim().replace(/,/g, ""); return t !== "" && Number.isFinite(Number(t)) && Math.abs(Number(t)) <= 100000 ? String(Number(t)) : ""; };

export function parseQuery(sp: URLSearchParams): ListQuery {
  const get = (k: string) => sp.get(k) || "";
  const size = Number(get("size")), page = Number(get("page"));
  const q: ListQuery = {
    ...EMPTY_QUERY, q: get("q").slice(0, 80), category: get("category"), amc: get("amc"), plan: ["Direct", "Regular", "Unspecified"].includes(get("plan")) ? get("plan") : "",
    option: ["Growth", "IDCW", "Other"].includes(get("option")) ? get("option") : "", stopped: get("stopped") === "1",
    sort: SORT_KEYS.has(get("sort")) ? (get("sort") as SortKey) : "", dir: get("dir") === "desc" ? "desc" : "asc",
    page: Number.isInteger(page) && page >= 1 && page <= 2000 ? page : 1, size: SIZES.includes(size) ? size : 50, view: get("view") === "ready" ? "ready" : "",
  };
  for (const f of RANGE_FIELDS) q[f] = cleanNum(get(f));
  return q;
}
/** Only what differs from the defaults goes into the address, so links stay short. */
export function queryToParams(q: ListQuery): URLSearchParams {
  const p = new URLSearchParams();
  for (const k of ["q", "category", "amc", "plan", "option", "sort", ...RANGE_FIELDS] as const) if (q[k]) p.set(k, q[k]);
  if (q.stopped) p.set("stopped", "1");
  if (q.view) p.set("view", q.view);
  if (q.sort && q.dir === "desc") p.set("dir", "desc");
  if (q.page > 1) p.set("page", String(q.page));
  if (q.size !== 50) p.set("size", String(q.size));
  return p;
}
/** The API address for a list query. */
export function listPath(q: ListQuery): string {
  const p = new URLSearchParams();
  for (const k of ["q", "category", "amc", "plan", "option", ...RANGE_FIELDS] as const) if (q[k]) p.set(k, q[k]);
  if (q.stopped) p.set("stopped", "true");
  if (q.sort) { p.set("sort", q.sort); p.set("dir", q.dir); }
  p.set("page", String(q.page)); p.set("size", String(q.size));
  return `/api/mf?${p}`;
}
export const activeFilterCount = (q: ListQuery) => ["category", "amc", "plan", "option", ...RANGE_FIELDS].filter((k) => q[k as keyof ListQuery]).length + (q.stopped ? 1 : 0);

/** Page numbers to show around the current one: 1 … 4 5 [6] 7 8 … 40. */
export function pageWindow(page: number, pages: number): (number | "…")[] {
  const keep = new Set([1, pages, page - 2, page - 1, page, page + 1, page + 2].filter((n) => n >= 1 && n <= pages));
  const out: (number | "…")[] = [];
  let prev = 0;
  for (const n of [...keep].sort((a, b) => a - b)) { if (n - prev === 2) out.push(prev + 1); else if (n - prev > 2) out.push("…"); out.push(n); prev = n; }
  return out;
}

// ------------------------------------------------------------------------------------------------ search (for the filter menus)

/** Tolerant search of menu options (fund houses, categories): spaces, hyphens and one or two typos do not matter. Best match first; all when the query is empty. */
export function searchOptions<T>(items: T[], query: string, label: (t: T) => string): T[] {
  if (!tokens(query).length) return items;
  return items.map((t, i) => ({ t, i, s: score(query, label(t)) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.i - b.i).map((x) => x.t);
}

// ------------------------------------------------------------------------------------------------ the compare tray (kept in this browser)

export const TRAY_MAX = 4;
const TRAY_KEY = "finlit-mf-compare-v1";
export function trayToggle(list: number[], code: number, max = TRAY_MAX): { list: number[]; full: boolean } {
  if (list.includes(code)) return { list: list.filter((c) => c !== code), full: false };
  if (list.length >= max) return { list, full: true };
  return { list: [...list, code], full: false };
}
let tray: number[] | null = null;
const listeners = new Set<() => void>();
function loadTray(): number[] {
  if (tray) return tray;
  try { const raw = JSON.parse(localStorage.getItem(TRAY_KEY) || "[]"); tray = Array.isArray(raw) ? raw.filter((n) => Number.isInteger(n) && n > 0).slice(0, TRAY_MAX) : []; } catch { tray = []; }
  return tray!;
}
function setTray(next: number[]) { tray = next; try { localStorage.setItem(TRAY_KEY, JSON.stringify(next)); } catch { /* private mode */ } listeners.forEach((l) => l()); }
/** The funds chosen for comparison (2 to 4 are compared). Returns [list, toggle, clear]; toggle answers false when the tray is full. */
export function useTray(): [number[], (code: number) => boolean, () => void] {
  const list = useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; }, loadTray, () => []);
  return [list, (code) => { const r = trayToggle(loadTray(), code); if (!r.full) setTray(r.list); return !r.full; }, () => setTray([])];
}
export const compareUrl = (codes: number[]) => `/funds/compare?ids=${codes.join(",")}`;
/** ?ids=1,2,3 -> up to 4 distinct positive whole numbers. */
export function parseIds(s: string | null): number[] {
  return [...new Set((s || "").split(",").map((x) => Number(x.trim())).filter((n) => Number.isInteger(n) && n > 0 && n < 1e7))].slice(0, TRAY_MAX);
}

// ------------------------------------------------------------------------------------------------ chart geometry

export type LineSeries = { key: string; label: string; t: string[]; v: number[] };
export type Tick = { at: number; label: string };
/** Round tick values covering [lo, hi] with about n steps (1, 2, 5 times a power of ten). */
export function niceTicks(lo: number, hi: number, n = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}
const dayNum = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86_400_000;
/** Lines for a time-scaled chart (x by date, not by index, so funds with different start days line up). Pure: no DOM. */
export function buildLines(series: LineSeries[], W: number, H: number, pad = { l: 52, r: 16, t: 14, b: 28 }) {
  const pts = series.flatMap((s) => s.t.map((t, i) => [dayNum(t), s.v[i]] as const));
  if (pts.length < 2) return null;
  const x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]));
  let lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  const padv = (hi - lo || Math.abs(hi) * 0.02 || 1) * 0.08; lo -= padv; hi += padv;
  const yt = niceTicks(lo, hi, 4);
  const X = (d: number) => pad.l + ((d - x0) / (x1 - x0 || 1)) * (W - pad.l - pad.r), Y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (H - pad.t - pad.b);
  const lines = series.map((s) => {
    const xy = s.t.map((t, i) => [X(dayNum(t)), Y(s.v[i])] as const);
    return { key: s.key, d: xy.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(""), xy };
  });
  const span = x1 - x0, xt: Tick[] = [];
  const fmt = (d: number) => dateIN(new Date(d * 86_400_000).toISOString().slice(0, 10), span > 200 ? { month: "short", year: "numeric" } : { day: "numeric", month: "short" });
  for (let k = 0; k <= 4; k++) { const d = x0 + (span * k) / 4; xt.push({ at: X(d), label: fmt(Math.round(d)) }); }
  return { lines, yTicks: yt.map((v) => ({ at: Y(v), v })), xTicks: xt, X, Y, lo, hi, x0, x1, pad };
}
/** Nearest point index of a series to an x position (in chart units), for the hover read-out. */
export function nearestIndex(xs: number[], x: number): number {
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
  return Math.abs(xs[lo] - x) <= Math.abs(xs[hi] - x) ? lo : hi;
}

// ------------------------------------------------------------------------------------------------ data hooks

async function mfGet<T>(path: string): Promise<T> {
  if (DEMO) return (await import("./mfDemo")).demoMf<T>(path);
  return apiGet<T>(path);
}
const STALE = 300_000;
export const useFundList = (q: ListQuery) =>
  useQuery<FundList, ApiError>({ queryKey: ["mf", "list", listPath(q)], queryFn: () => mfGet<FundList>(listPath(q)), staleTime: STALE, placeholderData: (prev) => prev });
export const useHotList = (enabled: boolean) => useQuery<HotList, ApiError>({ queryKey: ["mf", "hot"], queryFn: () => mfGet<HotList>("/api/mf/hot"), staleTime: STALE, enabled });
export const useFundFacts = (code: number) => useQuery<FundFacts, ApiError>({ queryKey: ["mf", "facts", code], queryFn: () => mfGet<FundFacts>(`/api/mf/${code}/facts`), staleTime: 3_600_000, retry: 1 });
export const useFundPortfolio = (code: number) => useQuery<PortfolioResult, ApiError>({ queryKey: ["mf", "portfolio", code], queryFn: () => mfGet<PortfolioResult>(`/api/mf/${code}/portfolio`), staleTime: 3_600_000, retry: 1 });
export const useFundFilters = () => useQuery<FundFilters, ApiError>({ queryKey: ["mf", "filters"], queryFn: () => mfGet<FundFilters>("/api/mf/filters"), staleTime: 3_600_000 });
export const useFundDetail = (code: number) =>
  useQuery<FundDetail, ApiError>({ queryKey: ["mf", "detail", code], queryFn: () => mfGet<FundDetail>(`/api/mf/${code}`), staleTime: STALE, retry: (n, e) => e.status >= 500 && n < 2 });
export const useFundCompare = (codes: number[], range: RangeKey) =>
  useQuery<FundCompare, ApiError>({
    queryKey: ["mf", "compare", codes.join(","), range], queryFn: () => mfGet<FundCompare>(`/api/mf/compare?ids=${codes.join(",")}&range=${range}`),
    enabled: codes.length >= 2, staleTime: STALE, placeholderData: (prev) => prev, retry: (n, e) => e.status >= 500 && n < 2,
  });

// ------------------------------------------------------------------------------------------------ the three return figures and the fund facts

/** The only return columns shown for a scheme: 1 day, 1 year (total change), 5 year (per year, CAGR). Anything else lives in the Risk area of the scheme's page. */
export const RETURN_LABELS = {
  d1: "1 day", y1: "1 year", y5: "5 year, per year (CAGR)",
} as const;
export const RETURN_HOW = {
  d1: "Change of the latest NAV against the NAV before it.",
  y1: "Total change in NAV over one year. Not a yearly rate.",
  y5: "Yearly rate (CAGR) over five years: (latest NAV ÷ NAV five years ago) ^ (365 ÷ days between the two NAVs) − 1. Not the total change over five years.",
} as const;

export type RetTile = { key: keyof typeof RETURN_LABELS; label: string; value: number | null; note: string; how: string };
/** The three tiles of the returns block with the reason each missing figure is missing. `note` is the date line under the figure, or the reason for a dash. */
export function retTiles(d: Pick<FundDetail, "change" | "returns" | "retDate" | "navDate" | "returnsNote" | "optionClass" | "active">): RetTile[] {
  const why = (r: Ret) => r.why || d.returnsNote || "No figure.";
  const day: RetTile = d.change
    ? { key: "d1", label: RETURN_LABELS.d1, value: d.change.pct, note: `NAV of ${d.navDate ? dateIN(d.navDate) : "latest"} against NAV of ${d.change.since ? dateIN(d.change.since) : "the previous NAV"}`, how: RETURN_HOW.d1 }
    : { key: "d1", label: RETURN_LABELS.d1, value: null, note: d.active ? "The previous NAV is not on file yet." : "This scheme has stopped publishing NAVs.", how: RETURN_HOW.d1 };
  const tile = (key: "y1" | "y5", r: Ret): RetTile => ({
    key, label: RETURN_LABELS[key], value: r.value, how: RETURN_HOW[key],
    note: r.value == null ? why(r) : r.from ? `NAV of ${dateIN(r.from)} to ${d.navDate ? dateIN(d.navDate) : "latest"}` : `Worked out from AMFI history${d.retDate ? `, as of ${dateIN(d.retDate)}` : ""}`,
  });
  return [day, tile("y1", d.returns["1y"]), tile("y5", d.returns["5y"])];
}

export const FACT_LABELS: Record<string, string> = {
  aum: "Fund size (AUM)", terRegular: "Expense ratio, Regular plan", terDirect: "Expense ratio, Direct plan", exitLoad: "Exit load", benchmark: "Benchmark index",
  managers: "Fund managers", riskometer: "Risk-o-meter", launchDate: "Launch date", minInvestment: "Minimum investment", category: "Category (SEBI/AMFI)", amc: "Fund house",
};
/** A fact's value as text; "" when it has none. */
export function factValueText(f: FactVal): string {
  if ("unavailable" in f) return "";
  const v = f.value;
  if (v == null || (Array.isArray(v) && !v.length)) return "";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "number") return nf(v, Math.abs(v) >= 100 ? 0 : 2) + (f.unit ? ` ${f.unit}` : "");
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? dateIN(v) : v;
}
/** Order of the fact rows: the server's order, then any extra key. */
export const factKeys = (f: FundFacts) => [...f.order, ...Object.keys(f.facts).filter((k) => !f.order.includes(k))].filter((k) => k in f.facts);
