// Mutual Fund Screener state: the filters as one plain object, their round trip to the address bar and to the API, the active-filter chips, the preset screens,
// and the data hooks. Everything pure lives here and is tested without the page (mfScreen.test.ts). The server (backend/finlit/mfscreen) owns what each filter means.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { ApiError } from "./api";
import { loadUi, saveUi } from "./persist";
import { mfGet, type FundRow, type Facts } from "./mf";
import {
  AUMRANK_OPTS, BASIS_OPTS, CAP_OPTS, CFLOW_OPTS, CHK_EACH, CSIZE_OPTS, CSTREAK_OPTS, EXIT_OPTS, FRESH_OPTS, HOUSE_OPTS, INST_OPTS, MAT_OPTS, NUM_BY, OPTION_OPTS, PFDATE_OPTS,
  PLAN_OPTS, RK_BANDS, STRUCT_OPTS, STYLE_OPTS, TICK_DATA, TICK_FALL, TICK_LISTS, TYPE_OPTS, rangeText, type Opt,
} from "./mfScreenDefs";

// ------------------------------------------------------------------------------------------------ the query

export type SQ = {
  q: string; group: string; subs: string[]; cap: string[]; style: string[]; struct: string[]; mat: string[]; amcs: string[]; house: string[];
  plans: string[]; options: string[]; inst: string[]; status: "active" | "stopped" | "both"; family: boolean; fresh: string; aumbasis: string[]; aumrank: string[];
  launchFrom: string; launchTo: string; rng: Record<string, [string, string]>; nd: string[]; rk: string[]; chk: string; chkEach: string[]; exit: string[]; tick: string[]; tags: string[];
  sector: string; sectorMin: string; holds: string; pfdate: string[]; cflow: string[]; cstreak: string[]; csize: string[];
  sort: string; dir: "asc" | "desc"; page: number;
};
/** The page's starting point (spec section 1): Direct plan, Growth option, still publishing, mutual funds and ETFs together. */
export const DEFAULTS: SQ = {
  q: "", group: "", subs: [], cap: [], style: [], struct: [], mat: [], amcs: [], house: [], plans: ["Direct"], options: ["Growth"], inst: [], status: "active", family: false, fresh: "",
  aumbasis: [], aumrank: [], launchFrom: "", launchTo: "", rng: {}, nd: [], rk: [], chk: "", chkEach: [], exit: [], tick: [], tags: [], sector: "", sectorMin: "", holds: "", pfdate: [],
  cflow: [], cstreak: [], csize: [], sort: "aum", dir: "desc", page: 1,
};
export const EMPTY: SQ = { ...DEFAULTS, rng: {} };
export const PAGE_SIZE = 50;

type ListKey = "subs" | "cap" | "style" | "struct" | "mat" | "amcs" | "house" | "plans" | "options" | "inst" | "aumbasis" | "aumrank" | "nd" | "rk" | "chkEach" | "exit" | "tick" | "tags" | "pfdate" | "cflow" | "cstreak" | "csize";
const LISTS: ListKey[] = ["subs", "cap", "style", "struct", "mat", "amcs", "house", "plans", "options", "inst", "aumbasis", "aumrank", "nd", "rk", "chkEach", "exit", "tick", "tags", "pfdate", "cflow", "cstreak", "csize"];
/** URL / API parameter name of each list (the same on both). */
const PARAM: Record<ListKey, string> = { subs: "subs", cap: "cap", style: "style", struct: "struct", mat: "mat", amcs: "amcs", house: "house", plans: "plans", options: "options", inst: "inst",
  aumbasis: "aumbasis", aumrank: "aumrank", nd: "nd", rk: "rk", chkEach: "chk_each", exit: "exit", tick: "tick", tags: "tags", pfdate: "pfdate", cflow: "cflow", cstreak: "cstreak", csize: "csize" };
const SORT_KEYS = new Set(["name", "amc", "nav", "r1y", "r3y", "r5y", "sip3y", "sip5y", "aum", "ter", "fall", "age", "launch", "ex3y", "rank3y", "rank1y", "rank5y", "vol", "sharpe", "r1m", "r6m", "gap", "consist", "aumrank", "worst", "negshare", "score", "checklist"]);
const NUM_RE = /^-?\d+(\.\d+)?$/;
const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

export const cleanNum = (s: string): string => { const t = s.trim().replace(/,/g, ""); return NUM_RE.test(t) ? String(Number(t)) : ""; };

/** The address bar's parameters -> a query. Unknown field names and malformed numbers are dropped, never trusted. */
export function parseQuery(p: URLSearchParams): SQ {
  const q: SQ = { ...DEFAULTS, rng: {}, plans: [...DEFAULTS.plans], options: [...DEFAULTS.options] };
  const many = (name: string) => p.getAll(name).flatMap((v) => v.split(",")).map((s) => s.trim()).filter(Boolean);
  for (const k of LISTS) { const v = k === "amcs" ? p.getAll("amcs").map((s) => s.trim()).filter(Boolean) : many(PARAM[k]); if (v.length || p.has(PARAM[k])) q[k] = [...new Set(v)] as never; }
  q.q = (p.get("q") || "").slice(0, 80);
  q.group = ["equity", "debt", "hybrid", "solution", "other"].includes(p.get("group") || "") ? p.get("group")! : "";
  const st = p.get("status"); q.status = st === "stopped" || st === "both" ? st : "active";
  q.family = p.get("family") === "true";
  q.fresh = p.get("fresh") === "today" || p.get("fresh") === "week" ? p.get("fresh")! : "";
  q.launchFrom = /^\d{4}-\d{2}-\d{2}$/.test(p.get("launch_from") || "") ? p.get("launch_from")! : "";
  q.launchTo = /^\d{4}-\d{2}-\d{2}$/.test(p.get("launch_to") || "") ? p.get("launch_to")! : "";
  for (const r of p.getAll("rng")) { const [f, lo = "", hi = ""] = r.split(":"); if (NUM_BY[f] && (cleanNum(lo) || cleanNum(hi))) q.rng[f] = [cleanNum(lo), cleanNum(hi)]; }
  q.nd = q.nd.filter((f) => f in q.rng);
  if (p.get("option") === "All") q.options = [];
  q.chk = /^[1-5]$/.test(p.get("chk") || "") ? p.get("chk")! : "";
  q.sector = (p.get("sector") || "").slice(0, 60); q.sectorMin = cleanNum(p.get("sector_min") || "");
  q.holds = (p.get("holds") || "").toUpperCase().replace(/[^A-Z0-9&-]/g, "").slice(0, 20);
  const sort = p.get("sort") || ""; q.sort = SORT_KEYS.has(sort) ? sort : DEFAULTS.sort;
  q.dir = p.get("dir") === "asc" ? "asc" : p.get("dir") === "desc" ? "desc" : (sort && SORT_KEYS.has(sort) ? (sort === "name" || sort === "ter" || sort === "fall" || sort === "rank3y" ? "asc" : "desc") : DEFAULTS.dir);
  const pg = Number(p.get("page")); q.page = Number.isInteger(pg) && pg >= 1 && pg <= 2000 ? pg : 1;
  return q;
}

/** The parameters the SERVER gets: every choice stated, the defaults too. */
export function apiParams(q: SQ): URLSearchParams {
  const p = new URLSearchParams();
  if (q.q.trim()) p.set("q", q.q.trim());
  if (q.group) p.set("group", q.group);
  for (const k of LISTS) if (q[k].length && k !== "nd" && k !== "plans" && k !== "options") for (const v of q[k]) p.append(PARAM[k], v);
  for (const k of ["plans", "options"] as const) for (const v of q[k]) p.append(PARAM[k], v);
  if (!q.options.length) p.set("option", "All");   // no option chosen means every option: the server would otherwise default to Growth
  p.set("status", q.status);
  if (q.family) p.set("family", "true");
  if (q.fresh) p.set("fresh", q.fresh);
  if (q.launchFrom) p.set("launch_from", q.launchFrom);
  if (q.launchTo) p.set("launch_to", q.launchTo);
  for (const [f, [lo, hi]] of Object.entries(q.rng)) if (lo || hi) p.append("rng", `${f}:${lo}:${hi}`);
  for (const f of q.nd) if (f in q.rng) p.append("nd", f);
  if (q.chk) p.set("chk", q.chk);
  if (q.sector) { p.set("sector", q.sector); if (q.sectorMin) p.set("sector_min", q.sectorMin); }
  if (q.holds) p.set("holds", q.holds);
  return p;
}

/** The address bar: only what differs from the defaults, so a fresh page has a clean address. */
export function queryToParams(q: SQ): URLSearchParams {
  const p = apiParams(q);
  if (same(q.plans, DEFAULTS.plans)) p.delete("plans");
  else if (!q.plans.length) p.set("plans", "");
  if (same(q.options, DEFAULTS.options)) p.delete("options");
  else if (!q.options.length) { p.delete("option"); p.set("options", ""); }
  if (q.status === "active") p.delete("status");
  if (q.sort !== DEFAULTS.sort || q.dir !== DEFAULTS.dir) { p.set("sort", q.sort); p.set("dir", q.dir); }
  if (q.page > 1) p.set("page", String(q.page));
  return p;
}
export const isDefault = (q: SQ) => queryToParams({ ...q, page: 1, sort: DEFAULTS.sort, dir: DEFAULTS.dir }).toString() === "";

/** The list request: the same parameters plus the page, the sort and `extra` (the screener's figures on every row). */
export function listPath(q: SQ): string {
  const p = apiParams(q);
  p.set("sort", q.sort); p.set("dir", q.dir); p.set("page", String(q.page)); p.set("size", String(PAGE_SIZE)); p.set("extra", "true");
  return "/api/mf?" + p.toString();
}
export function facetPath(q: SQ): string {
  const p = apiParams(q);
  p.set("screen", "true");
  return "/api/mf/filters?" + p.toString();
}

// ------------------------------------------------------------------------------------------------ what the server answers

export type Hist = { edges: number[]; bins: number[]; n: number; m: number };
export type ExtraFigs = {
  age: number | null; launch: string | null; ckey: string | null; tags: string[]; isEtf: boolean; r1m: number | null; r6m: number | null;
  ex: Record<"1y" | "3y" | "5y", number | null>; rank: Record<"1y" | "3y" | "5y", { rank: number; of: number } | null>; aumRank: { rank: number; of: number } | null; aumShare: number | null; naChg: number | null;
  houseAum: number | null; terRel: number | null; terGap: number | null; feeShare: number | null; exit: { state: string | null; pct: number | null; days: number | null };
  risk: { vol1: number | null; vol3: number | null; worstMonth: number | null; worstYear: number | null; negShare: number | null; belowHigh: number | null; downCapture: number | null; sharpe: number | null; consistency: number | null };
  portfolio: { asOf: string; equity: number | null; debt: number | null; cash: number | null; other: number | null; holdings: number | null; top10: number | null; largest: number | null; sector: string | null; sectorPct: number | null } | null;
  category: { month: string | null; flow: number | null; streak: number | null; aumMom: number | null; aumYoy: number | null; share: number | null; folioMom: number | null };
};
export type ScreenRow = FundRow & { x?: ExtraFigs };
export type ScreenList = Facts & { total: number; page: number; size: number; pages: number; items: ScreenRow[] };
export type ScreenFacets = {
  total: number; numeric: Record<string, Hist>; type: Record<string, number>; subs: { key: string; label: string; tab: string; n: number }[]; cap: Record<string, number>; style: Record<string, number>;
  mat: Record<string, number>; struct: Record<string, number>; amcs: { name: string; n: number }[]; house: Record<string, number>; plans: Record<string, number>; options: Record<string, number>;
  inst: Record<string, number>; status: Record<string, number>; fresh: Record<string, number>; aumbasis: Record<string, number>; aumrank: Record<string, number>; exit: Record<string, number>;
  chk: Record<string, number>; chk_each: Record<string, number>; tick: Record<string, number>; rk: Record<string, number>; tags: { tag: string; kind: string; label: string; n: number }[];
  sectors: { name: string; n: number }[]; portfolio: Record<string, number>; cflow: Record<string, number>; cstreak: Record<string, number>; csize: Record<string, number>;
  built: { rows: number; run: string | null; portfolioDate: string | null; flowMonth: string | null; tagged: number; indexTagged: number };
  scatter: { points: [number, string, number, number][]; eligible: number; shown: number };
  flows: { key: string; label: string; months: string[]; net: (number | null)[] }[];
};
export type FacetAnswer = Facts & { totals: { schemes: number; active: number; withHistory: number }; amcs: { name: string; active: number; total: number }[]; screen?: ScreenFacets };

const STALE = 300_000;
export const useScreenList = (q: SQ) => useQuery<ScreenList, ApiError>({ queryKey: ["mfs", "list", listPath(q)], queryFn: () => mfGet<ScreenList>(listPath(q)), staleTime: STALE, placeholderData: keepPreviousData });
/** The counts for the panel. Page and sort do not change them, so they are left out of the key. */
export const useScreenFacets = (q: SQ) => useQuery<FacetAnswer, ApiError>({ queryKey: ["mfs", "facets", facetPath(q)], queryFn: () => mfGet<FacetAnswer>(facetPath(q)), staleTime: STALE, placeholderData: keepPreviousData });
export const useStockSearch = (term: string) => useQuery<{ items: { symbol: string; isin: string; families: number }[] }, ApiError>({
  queryKey: ["mfs", "stocks", term], queryFn: () => mfGet(`/api/mf/screen/stocks?q=${encodeURIComponent(term)}`), enabled: /^[A-Za-z0-9&-]{2,20}$/.test(term), staleTime: 600_000, retry: false });

// ------------------------------------------------------------------------------------------------ editing

export const toggleIn = <T,>(list: T[], v: T): T[] => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
/** Set (or with both ends empty, clear) the range of one field. */
export function withRange(q: SQ, field: string, lo: string, hi: string): SQ {
  const rng = { ...q.rng };
  if (!lo && !hi) { delete rng[field]; return { ...q, rng, nd: q.nd.filter((f) => f !== field), page: 1 }; }
  rng[field] = [lo, hi];
  return { ...q, rng, page: 1 };
}
export const rangeOf = (q: SQ, field: string): [number | null, number | null] => { const r = q.rng[field]; return r ? [r[0] === "" ? null : Number(r[0]), r[1] === "" ? null : Number(r[1])] : [null, null]; };

// ------------------------------------------------------------------------------------------------ active filters (the removable chips)

export type Chip = { id: string; label: string; clear: (q: SQ) => SQ };
const optLabel = (opts: Opt[], v: string) => opts.find((o) => o.v === v)?.label ?? v;
const listChips = (q: SQ, key: ListKey, prefix: string, opts: Opt[] | null, skipDefault?: string[]): Chip[] => {
  if (skipDefault && same(q[key], skipDefault)) return [];
  return q[key].map((v) => ({ id: `${key}:${v}`, label: `${prefix}${opts ? optLabel(opts, v) : v}`, clear: (s) => ({ ...s, [key]: s[key].filter((x) => x !== v), page: 1 }) as SQ }));
};
const RK_PERIOD = { "1y": "1 year", "3y": "3 years", "5y": "5 years" } as const;

export function chipsFor(q: SQ, subLabel: (k: string) => string = (k) => k, tagLabel: (k: string) => string = (k) => k): Chip[] {
  const out: Chip[] = [];
  if (q.q.trim()) out.push({ id: "q", label: `Search: ${q.q.trim()}`, clear: (s) => ({ ...s, q: "", page: 1 }) });
  if (q.group) out.push({ id: "group", label: `Type: ${optLabel(TYPE_OPTS, q.group)}`, clear: (s) => ({ ...s, group: "", subs: [], page: 1 }) });
  out.push(...q.subs.map((v) => ({ id: `subs:${v}`, label: subLabel(v), clear: (s: SQ) => ({ ...s, subs: s.subs.filter((x) => x !== v), page: 1 }) })));
  out.push(...listChips(q, "cap", "Cap: ", CAP_OPTS), ...listChips(q, "style", "Style: ", STYLE_OPTS), ...listChips(q, "struct", "", STRUCT_OPTS), ...listChips(q, "mat", "Maturity (category band): ", MAT_OPTS));
  out.push(...listChips(q, "amcs", "", null).map((c) => ({ ...c, label: c.label.replace(/\s*mutual fund\s*$/i, "") })), ...listChips(q, "house", "House size: ", HOUSE_OPTS));
  if (!same(q.plans, DEFAULTS.plans)) out.push(...(q.plans.length ? listChips(q, "plans", "Plan: ", PLAN_OPTS) : [{ id: "plans:all", label: "All plans", clear: (s: SQ) => ({ ...s, plans: [...DEFAULTS.plans], page: 1 }) }]));
  if (!same(q.options, DEFAULTS.options)) out.push(...(q.options.length ? listChips(q, "options", "Option: ", OPTION_OPTS) : [{ id: "options:all", label: "All options", clear: (s: SQ) => ({ ...s, options: [...DEFAULTS.options], page: 1 }) }]));
  out.push(...listChips(q, "inst", "", INST_OPTS));
  if (q.status !== "active") out.push({ id: "status", label: q.status === "stopped" ? "Stopped publishing" : "Including stopped funds", clear: (s) => ({ ...s, status: "active", page: 1 }) });
  if (q.family) out.push({ id: "family", label: "One row per fund family", clear: (s) => ({ ...s, family: false, page: 1 }) });
  if (q.fresh) out.push({ id: "fresh", label: optLabel(FRESH_OPTS, q.fresh), clear: (s) => ({ ...s, fresh: "", page: 1 }) });
  out.push(...listChips(q, "aumbasis", "Size basis: ", BASIS_OPTS), ...listChips(q, "aumrank", "Size rank: ", AUMRANK_OPTS));
  if (q.launchFrom || q.launchTo) out.push({ id: "launch", label: `Launched ${q.launchFrom || "…"} to ${q.launchTo || "…"}`, clear: (s) => ({ ...s, launchFrom: "", launchTo: "", page: 1 }) });
  for (const f of Object.keys(q.rng)) {
    const d = NUM_BY[f]; const [lo, hi] = rangeOf(q, f);
    out.push({ id: `rng:${f}`, label: `${d.label}: ${rangeText(d, lo, hi)}${q.nd.includes(f) ? " (and no data)" : ""}`, clear: (s) => withRange(s, f, "", "") });
  }
  out.push(...q.rk.map((r) => { const [p, b] = r.split(":"); return { id: `rk:${r}`, label: `Rank in category, ${RK_PERIOD[p as keyof typeof RK_PERIOD] ?? p}: ${optLabel(RK_BANDS, b)}`, clear: (s: SQ) => ({ ...s, rk: s.rk.filter((x) => x !== r), page: 1 }) }; }));
  if (q.chk) out.push({ id: "chk", label: `Checklist: ${q.chk}+ of 5 passed`, clear: (s) => ({ ...s, chk: "", page: 1 }) });
  out.push(...q.chkEach.map((v) => ({ id: `chk_each:${v}`, label: `Check: ${optLabel(CHK_EACH, v)}`, clear: (s: SQ) => ({ ...s, chkEach: s.chkEach.filter((x) => x !== v), page: 1 }) })));
  out.push(...listChips(q, "exit", "Exit load: ", EXIT_OPTS));
  out.push(...q.tick.map((v) => ({ id: `tick:${v}`, label: optLabel([...TICK_FALL, ...TICK_DATA, ...TICK_LISTS], v), clear: (s: SQ) => ({ ...s, tick: s.tick.filter((x) => x !== v), page: 1 }) })));
  out.push(...q.tags.map((v) => ({ id: `tags:${v}`, label: tagLabel(v), clear: (s: SQ) => ({ ...s, tags: s.tags.filter((x) => x !== v), page: 1 }) })));
  if (q.sector) out.push({ id: "sector", label: `Sector: ${q.sector}${q.sectorMin ? ` at least ${q.sectorMin}%` : ""}`, clear: (s) => ({ ...s, sector: "", sectorMin: "", page: 1 }) });
  if (q.holds) out.push({ id: "holds", label: `Holds ${q.holds}`, clear: (s) => ({ ...s, holds: "", page: 1 }) });
  out.push(...listChips(q, "pfdate", "Portfolio: ", PFDATE_OPTS), ...listChips(q, "cflow", "Category net flow: ", CFLOW_OPTS), ...listChips(q, "cstreak", "", CSTREAK_OPTS), ...listChips(q, "csize", "Category size: ", CSIZE_OPTS));
  return out;
}

// ------------------------------------------------------------------------------------------------ preset screens (spec section 14)

export type PresetDef = { id: string; label: string; say: string; set: (q: SQ) => SQ; off?: string };
const base = (): SQ => ({ ...DEFAULTS, rng: {}, plans: [...DEFAULTS.plans], options: [...DEFAULTS.options] });
const rng = (q: SQ, field: string, lo = "", hi = ""): SQ => withRange(q, field, lo, hi);
/** Presets are plain filter settings; a preset is a starting point and everything stays editable. Names describe, they do not recommend. */
export const PRESETS: PresetDef[] = [
  { id: "lowcost-large", label: "Large caps at lower cost", say: "Large Cap, Direct plan, expense ratio at or below the category median, fund size above ₹2,000 Cr.",
    set: () => rng(rng({ ...base(), cap: ["large"] }, "ter_rel", "", "1"), "aum", "2000") },
  { id: "steady-mid", label: "Mid caps ahead of category, steadily", say: "Mid Cap, 5-year return above the category median, ahead of peers in over 55% of months, fell less than the category.",
    set: () => rng(rng({ ...base(), cap: ["mid"], tick: ["fallless"] }, "ex5y", "0"), "consist", "55") },
  { id: "small-fell-less", label: "Small caps that fell less", say: "Small Cap, biggest fall smaller than the category median, 3-year return above the category median.",
    set: () => rng({ ...base(), cap: ["small"], tick: ["fallless"] }, "ex3y", "0") },
  { id: "short-debt", label: "Short-term debt, no falling month", say: "Debt, Liquid / Money Market / Ultra Short, no falling month in 3 years, expense ratio at or below the category median.",
    set: () => rng({ ...base(), group: "debt", subs: ["liquid", "money-market", "ultra-short"], tick: ["noneg36"] }, "ter_rel", "", "1") },
  { id: "debt-calm", label: "Debt with a small worst month and low fee share", say: "Debt, worst month a loss of no more than 0.5%, fee share of return under 15%.",
    set: () => rng(rng({ ...base(), group: "debt" }, "worst_m", "", "0.5"), "fee_share", "", "15") },
  { id: "cheap-index", label: "Index funds and ETFs, lowest expense ratio first", say: "Passive funds tracking the Nifty 50 or the Sensex, cheapest first.",
    set: () => ({ ...base(), style: ["passive"], tags: ["i_nifty50", "i_sensex"], plans: ["Direct", "Regular", "Unspecified"], sort: "ter", dir: "asc" }) },
  { id: "defence", label: "Defence and aerospace funds", say: "Funds tagged Defence & Aerospace, fund size above ₹500 Cr.", set: () => rng({ ...base(), tags: ["defence"] }, "aum", "500") },
  { id: "ai-tech", label: "AI and technology funds", say: "Technology and AI tags, India and overseas.", set: () => ({ ...base(), tags: ["ai", "semis", "robotics", "cloud", "cyber", "it", "g_nasdaq"] }) },
  { id: "elss-record", label: "Tax saver (ELSS) with a five-year record", say: "ELSS, five years or older, 5-year return above the category median.", set: () => rng(rng({ ...base(), subs: ["elss"] }, "age", "5"), "ex5y", "0") },
  { id: "steady-hybrid", label: "Hybrid funds with steady months", say: "Hybrid, no falling month in 3 years, equity share 10 to 40%.", set: () => rng({ ...base(), group: "hybrid", tick: ["noneg36"] }, "eq_pct", "10", "40") },
  { id: "score-cost", label: "Health score 65+ at low cost", say: "Needs the score filter, which lives in the Gold Fund score screener.", set: () => base(), off: "Score filters are in the Fund score screener (Gold)." },
];
const presetKey = (q: SQ) => queryToParams({ ...q, page: 1, sort: q.sort, dir: q.dir }).toString();
/** A preset is "on" while every filter it sets is still as it set it (more filters on top do not switch it off). */
export function presetOn(q: SQ, p: PresetDef): boolean {
  if (p.off) return false;
  const want = new URLSearchParams(presetKey(p.set(base()))), have = new URLSearchParams(presetKey(q));
  if (![...want.keys()].length) return false;
  const rows = (u: URLSearchParams) => new Set([...u.entries()].map(([k, v]) => `${k}=${v}`));
  const h = rows(have);
  const w = [...rows(want)];
  return w.length > 0 && w.every((r) => h.has(r)) && rows(have).size === w.length;
}

// ------------------------------------------------------------------------------------------------ saved screens (this browser only)

export type Saved = { name: string; query: string };
const validSaved = (d: unknown): Saved[] | null => (Array.isArray(d) ? d.filter((x): x is Saved => !!x && typeof x.name === "string" && typeof x.query === "string").slice(0, 8) : null);
export const loadSaved = (): Saved[] => loadUi("mfscreen.saved", 1, validSaved, []);
export const storeSaved = (s: Saved[]) => saveUi("mfscreen.saved", 1, s.slice(0, 8));

// ------------------------------------------------------------------------------------------------ small helpers for the page

/** One row's value for a numeric field, for the columns that follow the active filters. */
export function figureOf(r: ScreenRow, f: string): number | null {
  const x = r.x;
  switch (f) {
    case "aum": return r.aum ?? null; case "r1d": return r.change; case "r1y": return r.r1y; case "r3y": return r.r3y ?? null; case "r5y": return r.r5y;
    case "sip3y": return r.sip3y ?? null; case "sip5y": return r.sip5y ?? null; case "ter": return r.ter ?? null; case "fall": return r.fall3y == null ? null : -r.fall3y;
  }
  if (!x) return null;
  switch (f) {
    case "age": return x.age; case "aum_share": return x.aumShare; case "na_chg": return x.naChg; case "r1m": return x.r1m; case "r6m": return x.r6m;
    case "ex1y": return x.ex["1y"]; case "ex3y": return x.ex["3y"]; case "ex5y": return x.ex["5y"]; case "consist": return x.risk.consistency;
    case "ter_rel": return x.terRel; case "ter_gap": return x.terGap; case "fee_share": return x.feeShare; case "exit_pct": return x.exit.pct;
    case "vol1": return x.risk.vol1; case "vol3": return x.risk.vol3; case "worst_m": return x.risk.worstMonth; case "worst_12m": return x.risk.worstYear;
    case "neg_share": return x.risk.negShare; case "below_high": return x.risk.belowHigh; case "down_cap": return x.risk.downCapture; case "sharpe": return x.risk.sharpe;
    case "eq_pct": return x.portfolio?.equity ?? null; case "debt_pct": return x.portfolio?.debt ?? null; case "cash_pct": return x.portfolio?.cash ?? null; case "other_pct": return x.portfolio?.other ?? null;
    case "n_hold": return x.portfolio?.holdings ?? null; case "top10": return x.portfolio?.top10 ?? null; case "max_hold": return x.portfolio?.largest ?? null;
    case "cf_aum_mom": return x.category.aumMom; case "cf_aum_yoy": return x.category.aumYoy; case "cf_folio_mom": return x.category.folioMom; case "cf_share": return x.category.share;
  }
  return null;
}

export const COVER_NOTE = "Funds with no figure for a measure are left out while a range is set on it, unless you switch on “Include funds with no data”.";
