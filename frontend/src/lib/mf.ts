// Mutual funds: API types and hooks, the list's URL state, number text, column choices, the compare tray, search and chart geometry.
// Everything pure lives here so it is tested without the page (mf.test.ts). Data comes from AMFI via /api/mf; see backend/finlit/mf.py.
import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { apiGet, type ApiError } from "./api";
import { DEMO } from "./demo";
import { MINUS, dateIN, nf } from "./format";
import { score, tokens } from "./metricSearch";
import { TAB_KEYS, classify, type TabKey } from "./mfCategories";
import type { PortfolioResult } from "../holdings/types";

export const DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns.";
export const MIRROR_LABEL = "NAV history: third-party mirror of AMFI data (api.mfapi.in)";

export type Facts = { dataDate: string | null; updatedAt: string | null; source: string; disclaimer: string; excludedAmcs?: string[] };
/** The checklist of one scheme: checks passed, checks that could be worked out, which passed (bits) and which were worked out (mask), its peer group. */
export type Checklist = { pass: number; of: number; bits: number; mask: number; peer: string };
/** Category medians a peer group's checklist used ("small-cap|Direct"): returns, expense ratio and month-end fall, with how many schemes had each. */
export type PeerStats = { r5y: number | null; n5: number; r3y: number | null; n3: number; ter: number | null; nTer: number; fall: number | null; nFall: number; n: number };
export type FundRow = {
  code: number; name: string; amc: string; category: string; plan: string; option: string; optionClass: "Growth" | "IDCW" | "Other"; nav: number | null; navDate: string | null;
  change: number | null; changeSince?: string | null; active: boolean; r1y: number | null; r3y?: number | null; r5y: number | null; retDate?: string | null;
  noReturns: "stopped" | "idcw" | "unstated" | "no_history" | "short" | null; rank?: number;
  // the category table's figures (an older cached answer may not carry them yet: treated as missing)
  sip3y?: number | null; sip5y?: number | null; fall3y?: number | null; aum?: number | null; aumAsOf?: string | null; aumKind?: "q" | "m" | null;
  ter?: number | null; terDate?: string | null; checklist?: Checklist | null;
};
export type FundList = Facts & { total: number; page: number; size: number; pages: number; items: FundRow[]; peers?: Record<string, PeerStats>; checklist?: { checks: { key: string; rule: string }[]; minPeers: number } };
export type HotList = Facts & { basis: string | null; items: FundRow[] };
export type FilterCategory = {
  name: string; group: string; type: string; active: number; total: number;
  tab?: TabKey; key?: string; label?: string; growth?: number; direct?: number; regular?: number;   // newer servers; the page works the tab out itself (classify)
};
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
export type FactVal = { value: string | number | string[] | null; asOf?: string | null; source?: string; unit?: string; note?: string } | { unavailable: string };
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

/** Fund size in rupees crore: "₹1,47,064 Cr", "₹45.30 Cr"; "—" when there is none. */
export function aumText(crore: number | null | undefined): string {
  if (crore == null) return "—";
  return "₹" + nf(crore, crore >= 100 ? 0 : 2) + " Cr";
}
/** Expense ratio, percent a year: "0.65%". */
export const terText = (v: number | null | undefined) => (v == null ? "—" : nf(v, 2) + "%");

// ------------------------------------------------------------------------------------------------ list columns

export type SortKey = "name" | "amc" | "category" | "nav" | "navDate" | "change" | "r1y" | "r3y" | "r5y" | "sip3y" | "sip5y" | "aum" | "ter" | "checklist";
export type ColId = "amc" | "category" | "plan" | "option" | "nav" | "navDate" | "change" | "r1y" | "r3y" | "r5y" | "sip3y" | "sip5y" | "aum" | "ter" | "checklist";
/** `group` puts neighbouring columns under one heading in the table ("Returns", "SIP returns"). */
export type ColDef = { id: ColId; label: string; hint: string; sort: SortKey | null; num: boolean; group?: "ret" | "sip" };
export const COL_GROUPS = { ret: "Returns", sip: "SIP returns (XIRR)" } as const;
/** The name column (with the fund house, plan and option under it) is always shown and is the link; these can be switched on and off. */
export const COLUMNS: ColDef[] = [
  { id: "amc", label: "Fund house", hint: "The company that runs the scheme (also shown under the scheme's name)", sort: "amc", num: false },
  { id: "category", label: "Category", hint: "The group AMFI files the scheme in", sort: "category", num: false },
  { id: "plan", label: "Plan", hint: "Direct or Regular", sort: null, num: false },
  { id: "option", label: "Option", hint: "Growth or IDCW (payout)", sort: null, num: false },
  { id: "nav", label: "NAV", hint: "Net asset value of one unit, latest", sort: "nav", num: true },
  { id: "navDate", label: "NAV date", hint: "The day the NAV is for", sort: "navDate", num: true },
  { id: "change", label: "1 day", hint: "Change of the NAV against the previous NAV (its date is shown on the scheme's page)", sort: "change", num: true, group: "ret" },
  { id: "r1y", label: "1 year", hint: "Total change in NAV over 1 year (not per year)", sort: "r1y", num: true, group: "ret" },
  { id: "r3y", label: "3 yrs p.a.", hint: "Yearly rate (CAGR) over 3 years, not the three-year total", sort: "r3y", num: true, group: "ret" },
  { id: "r5y", label: "5 yrs p.a.", hint: "Yearly rate (CAGR) over 5 years: the rate that, compounded for five years, gives the total change", sort: "r5y", num: true, group: "ret" },
  { id: "sip3y", label: "3 yrs", hint: "Yearly rate (XIRR) of a monthly SIP of equal amounts over the last 3 years, valued at the latest NAV", sort: "sip3y", num: true, group: "sip" },
  { id: "sip5y", label: "5 yrs", hint: "Yearly rate (XIRR) of a monthly SIP of equal amounts over the last 5 years, valued at the latest NAV", sort: "sip5y", num: true, group: "sip" },
  { id: "aum", label: "Fund size", hint: "Assets under management (AUM), all plans of the scheme together, rupees crore", sort: "aum", num: true },
  { id: "ter", label: "Expense ratio", hint: "Total expense ratio (TER) of this plan, percent a year", sort: "ter", num: true },
  { id: "checklist", label: "Checklist", hint: "How many of five plain checks the scheme passes against its category (see the legend below the table)", sort: "checklist", num: true },
];
export const DEFAULT_COLS: ColId[] = ["category", "nav", "r1y", "r3y", "r5y", "sip3y", "sip5y", "aum", "ter", "checklist"];
const COLS_KEY = "finlit-mf-cols-v3";
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

/** The list's state, kept in the page address. `tab` and `cats` choose the categories: cats null = the whole tab, [] = none ticked, else sub-category
 *  keys (mfCategories.classify). `plan` "" = every plan. EMPTY_QUERY means "no filter at all" (other pages search with it); /funds starts from PAGE_DEFAULTS. */
export type ListQuery = {
  q: string; amc: string; plan: string; option: string; stopped: boolean; sort: SortKey | ""; dir: "asc" | "desc"; page: number; size: number;
  min1y: string; max1y: string; min5y: string; max5y: string; view: "" | "ready"; tab: TabKey | "all"; cats: string[] | null;
};
export const SIZES = [25, 50, 100];
export const EMPTY_QUERY: ListQuery = { q: "", amc: "", plan: "", option: "", stopped: false, sort: "", dir: "asc", page: 1, size: 50, min1y: "", max1y: "", min5y: "", max5y: "", view: "", tab: "all", cats: null };
/** What /funds shows with nothing in its address: every Equity category, Direct plans, Growth options. */
export const PAGE_DEFAULTS: ListQuery = { ...EMPTY_QUERY, tab: "equity", plan: "Direct" };
const SORT_KEYS = new Set<string>(COLUMNS.flatMap((c) => (c.sort ? [c.sort] : [])).concat("name"));
const RANGE_FIELDS = ["min1y", "max1y", "min5y", "max5y"] as const;
const TAB_SET = new Set<string>([...TAB_KEYS, "all"]);
const CAT_KEY = /^[a-z0-9-]{1,40}$/;
/** A number typed in a range box, or "" when it is not one (so a stray letter never reaches the server). */
export const cleanNum = (s: string) => { const t = s.trim().replace(/,/g, ""); return t !== "" && Number.isFinite(Number(t)) && Math.abs(Number(t)) <= 100000 ? String(Number(t)) : ""; };
/** Sub-category keys from the address: valid keys only, each once, sorted (so one choice has one address). */
export const cleanCats = (s: string): string[] => [...new Set(s.split(",").map((x) => x.trim()).filter((x) => CAT_KEY.test(x)))].sort().slice(0, 40);

export function parseQuery(sp: URLSearchParams): ListQuery {
  const get = (k: string) => sp.get(k) || "";
  const size = Number(get("size")), page = Number(get("page")), plan = get("plan");
  const q: ListQuery = {
    ...PAGE_DEFAULTS, q: get("q").slice(0, 80), amc: get("amc"), plan: plan === "All" ? "" : ["Direct", "Regular", "Unspecified"].includes(plan) ? plan : PAGE_DEFAULTS.plan,
    option: ["Growth", "IDCW", "Other", "All"].includes(get("option")) ? get("option") : "", stopped: get("stopped") === "1",
    sort: SORT_KEYS.has(get("sort")) ? (get("sort") as SortKey) : "", dir: get("dir") === "desc" ? "desc" : "asc",
    page: Number.isInteger(page) && page >= 1 && page <= 2000 ? page : 1, size: SIZES.includes(size) ? size : 50, view: get("view") === "ready" ? "ready" : "",
    tab: TAB_SET.has(get("tab")) ? (get("tab") as TabKey | "all") : PAGE_DEFAULTS.tab, cats: sp.has("cats") ? cleanCats(get("cats")) : null,
  };
  if (q.tab === "all") q.cats = null;
  // an older link names one AMFI category exactly (/funds?category=Equity Scheme - Mid Cap Fund): its tab, with its sub-category ticked
  const old = get("category").trim().slice(0, 160);
  if (old && !sp.has("tab") && !sp.has("cats")) { const c = classify(old); q.tab = c.tab; q.cats = [c.key]; }
  for (const f of RANGE_FIELDS) q[f] = cleanNum(get(f));
  return q;
}
/** Only what differs from the page's defaults goes into the address, so links stay short. */
export function queryToParams(q: ListQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (q.tab !== PAGE_DEFAULTS.tab) p.set("tab", q.tab);
  if (q.tab !== "all" && q.cats) p.set("cats", [...q.cats].sort().join(","));
  for (const k of ["q", "amc", "option", "sort", ...RANGE_FIELDS] as const) if (q[k]) p.set(k, q[k]);
  if (q.plan !== PAGE_DEFAULTS.plan) p.set("plan", q.plan || "All");
  if (q.stopped) p.set("stopped", "1");
  if (q.view) p.set("view", q.view);
  if (q.sort && q.dir === "desc") p.set("dir", "desc");
  if (q.page > 1) p.set("page", String(q.page));
  if (q.size !== 50) p.set("size", String(q.size));
  return p;
}
/** The API address for a list query. Ticked sub-categories go as the exact AMFI names they cover (`names`: see catNames); a whole tab as group=<tab>;
 *  "all" sends no category at all. */
export function listPath(q: ListQuery, names?: string[] | null): string {
  const p = new URLSearchParams();
  if (q.tab !== "all") { if (q.cats === null) p.set("group", q.tab); else for (const n of [...(names || [])].sort()) p.append("categories", n); }
  for (const k of ["q", "amc", "plan", "option", ...RANGE_FIELDS] as const) if (q[k]) p.set(k, q[k]);
  if (q.stopped) p.set("stopped", "true");
  if (q.sort) { p.set("sort", q.sort); p.set("dir", q.dir); }
  p.set("page", String(q.page)); p.set("size", String(q.size));
  return `/api/mf?${p}`;
}
/** The page's order when none is chosen: largest funds first (a neutral order, not a ranking), or best match while searching. */
export const effectiveQuery = (q: ListQuery): ListQuery => (q.sort || q.q.trim() ? q : { ...q, sort: "aum", dir: "desc" });
/** Filters beyond the category choice and the page's defaults (Direct plan, Growth option). */
export const activeFilterCount = (q: ListQuery) => ["amc", "option", ...RANGE_FIELDS].filter((k) => q[k as keyof ListQuery]).length + (q.stopped ? 1 : 0) + (q.plan !== PAGE_DEFAULTS.plan ? 1 : 0);

// ------------------------------------------------------------------------------------------------ categories on the page

export type SubCat = { key: string; label: string; names: string[]; count: number };
/** How many schemes of a category the current plan and option choice shows (the server sends Growth counts per plan; an older answer only `active`). */
export function catCount(c: FilterCategory, q: Pick<ListQuery, "plan" | "option" | "stopped">): number {
  if (q.stopped) return c.total;
  if (q.option === "" || q.option === "Growth") {
    if (q.plan === "Direct" && c.direct != null) return c.direct;
    if (q.plan === "Regular" && c.regular != null) return c.regular;
    if (q.plan === "" && c.growth != null) return c.growth;
  }
  return c.active;
}
/** The sub-categories of a tab with the AMFI names each covers and its count for the current choice, A to Z. Empty ones are left out unless ticked. */
export function subCats(cats: FilterCategory[] | undefined, tab: TabKey, q: Pick<ListQuery, "plan" | "option" | "stopped" | "cats">): SubCat[] {
  const by = new Map<string, SubCat>();
  for (const c of cats || []) {
    const k = classify(c.name);
    if (k.tab !== tab) continue;
    const s = by.get(k.key) || { key: k.key, label: k.label, names: [], count: 0 };
    s.names.push(c.name); s.count += catCount(c, q);
    by.set(k.key, s);
  }
  return [...by.values()].filter((s) => s.count > 0 || q.cats?.includes(s.key)).sort((a, b) => a.label.localeCompare(b.label));
}
/** Tick or untick one sub-category. `cats` null means all are ticked; ticking the last missing one gives null again (one address for "all"). */
export function toggleCat(cats: string[] | null, key: string, allKeys: string[]): string[] | null {
  const cur = new Set(cats ?? allKeys);
  if (cur.has(key)) cur.delete(key); else cur.add(key);
  return allKeys.every((k) => cur.has(k)) ? null : [...cur].sort();
}
/** "Select all": everything when some or none are ticked, nothing when all are. */
export const toggleAll = (cats: string[] | null): string[] | null => (cats === null ? [] : null);
/** A row's value for a sort key, for sorting rows already in the browser (the ready list). */
export function rowSortValue(r: FundRow, key: SortKey): number | string | null {
  if (key === "checklist") return r.checklist ? r.checklist.pass * 8 + r.checklist.of : null;
  const v = r[key];
  return v == null ? null : (v as number | string);
}
/** The exact AMFI names behind ticked sub-category keys of a tab (what the list API is asked for). */
export function catNames(cats: FilterCategory[] | undefined, tab: TabKey, keys: string[]): string[] {
  const want = new Set(keys);
  return (cats || []).filter((c) => { const k = classify(c.name); return k.tab === tab && want.has(k.key); }).map((c) => c.name).sort();
}

// ------------------------------------------------------------------------------------------------ the checklist

/** The five checks, in the server's bit order (finlit.mf.CHECKS). */
export const CHECKS: { key: "ret" | "ter" | "fall" | "size" | "age"; label: string; rule: string }[] = [
  { key: "ret", label: "Long-term return", rule: "5-year return (per year) above the category median; the 3-year return when the scheme has no 5-year figure" },
  { key: "ter", label: "Costs", rule: "Expense ratio (TER) below the category median" },
  { key: "fall", label: "Falls", rule: "Largest fall between month-end NAVs over the last 3 years smaller than the category median" },
  { key: "size", label: "Fund size", rule: "Fund size at least ₹500 crore (all plans together)" },
  { key: "age", label: "Track record", rule: "At least 5 years since launch" },
];
const RET5 = 32;
export type CheckLine = { key: string; state: "pass" | "fail" | "unknown"; text: string };
const p2 = (v: number | null | undefined) => (v == null ? "—" : pctText(v, 2, false));
/** Each check of a scheme in words, with the scheme's figure and the category median it was held against. */
export function checklistLines(r: FundRow, peers?: Record<string, PeerStats>): CheckLine[] {
  const c = r.checklist;
  if (!c) return [];
  const m = peers?.[c.peer];
  const state = (i: number): CheckLine["state"] => (!(c.mask & (1 << i)) ? "unknown" : c.bits & (1 << i) ? "pass" : "fail");
  const few = "Fewer than 3 schemes of the category have this figure, so there is nothing to compare with.";
  const ret = state(0) === "unknown" ? (r.r5y == null && r.r3y == null ? "No 3-year or 5-year return yet." : few)
    : c.bits & RET5 ? `5-year return ${p2(r.r5y)} a year; category median ${p2(m?.r5y)}${m ? ` (${m.n5} schemes)` : ""}.`
      : `3-year return ${p2(r.r3y)} a year; category median ${p2(m?.r3y)}${m ? ` (${m.n3} schemes)` : ""}. No 5-year figure yet.`;
  const ter = state(1) === "unknown" ? (r.ter == null ? "Expense ratio not in AMFI's latest TER file." : few) : `Expense ratio ${terText(r.ter)}; category median ${terText(m?.ter)}.`;
  const fall = state(2) === "unknown" ? (r.fall3y == null ? "Needs 3 years of month-end NAVs." : few) : `Largest month-end fall in 3 years ${p2(r.fall3y)}; category median ${p2(m?.fall)}.`;
  const size = state(3) === "unknown" ? "Fund size is not in the AMFI or fund-house files loaded." : `Fund size ${aumText(r.aum)}; the floor is ₹500 Cr.`;
  const age = state(4) === "unknown" ? "Launch date not known." : state(4) === "pass" ? "5 years or more since launch." : "Launched less than 5 years ago.";
  return [ret, ter, fall, size, age].map((text, i) => ({ key: CHECKS[i].key, state: state(i), text: `${CHECKS[i].label}: ${text}` }));
}

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

export async function mfGet<T>(path: string): Promise<T> {
  if (DEMO) return (await import("./mfDemo")).demoMf<T>(path);
  return apiGet<T>(path);
}
const STALE = 300_000;
/** A page of schemes. With ticked sub-categories (q.cats) it needs their AMFI `names` (catNames) and waits until they are known; none ticked asks nothing. */
export const useFundList = (q: ListQuery, names?: string[] | null, enabled = true) => {
  const path = listPath(q, names);
  const ready = q.tab === "all" || q.cats === null || (names != null && names.length > 0);
  return useQuery<FundList, ApiError>({ queryKey: ["mf", "list", path], queryFn: () => mfGet<FundList>(path), staleTime: STALE, placeholderData: (prev) => prev, enabled: enabled && ready });
};
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
  if (typeof v === "number") {
    const n = nf(v, Math.abs(v) >= 100 ? 0 : 2);
    if (f.unit === "crore") return `₹${n} Cr`;
    if (f.unit === "percent") return `${nf(v, 2)}%`;
    if (f.unit === "rupees") return `₹${n}`;
    return n + (f.unit ? ` ${f.unit}` : "");
  }
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? dateIN(v) : v;
}
/** Order of the fact rows: the server's order, then any extra key. */
export const factKeys = (f: FundFacts) => [...f.order, ...Object.keys(f.facts).filter((k) => !f.order.includes(k))].filter((k) => k in f.facts);
