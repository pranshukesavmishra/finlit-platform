// Prebuilt screens on the Advanced (Gold) and Basic (Silver) score screeners: the API types, the address (?preset=<id>&chip=<id>...), the two queries, client-side sorting and the CSV.
// Every number shown comes from the response; nothing is computed here except ordering and layout.
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

export type PresetChip = { id: string; label: string; default: boolean; description: string };
export type Preset = {
  id: string; name: string; group: string; cardText: string; count: number | null; asOf: string | null; status: "live" | "blocked"; blockedReason: string | null;
  /** "Top 10 of 40 that pass" or "First 25 of 129 that pass", as the card says it; null when the whole match is listed. */
  listText?: string | null;
  chips: PresetChip[]; howItWorks: string[]; locked: boolean; tab?: PresetTab;
};
/** Advanced screens are Gold (Prism fields); Basic screens are Silver (FinLit score fields). */
export type PresetTab = "advanced" | "basic";
export const PLAN_OF: Record<PresetTab, "gold" | "silver"> = { advanced: "gold", basic: "silver" };
export type PresetGroup = { id: string; name: string; presets: Preset[] };
export type PresetList = { asOf: string | null; groups: PresetGroup[]; tab?: PresetTab };

export type ColFormat = "text" | "num1" | "pct" | "score" | "cr" | "label" | "badge";
export type PresetColumn = { key: string; label: string; format: ColFormat; align?: "left" | "right" | "center" };
export type PresetRow = { symbol: string; name?: string | null; exchange?: string | null; badges?: string[] } & Record<string, unknown>;
export type ThemeState = "in_play" | "emerging" | "fading" | "closest";
/** `breadth` is the share of the sector's stocks within 15% of their 52-week high; `marketBreadth` the same for the whole market; `reason` says why a "closest" sector is not in play. */
export type Theme = { industry: string; state: ThemeState; breadth: number | null; marketBreadth?: number | null; r3?: number | null; rs3: number | null; members: number | null; small?: boolean; leaders: string[]; reason?: string | null };
export type Miss = { symbol: string; name?: string | null; exchange?: string | null; failed: string[] };
export type PresetDetail = {
  id: string; name: string; asOf: string | null; count: number; shown: number; columns: PresetColumn[]; rows: PresetRow[]; themes?: Theme[]; closestMisses?: Miss[];
  howItWorks: string[]; cardText: string; disclaimer: string;
  /** "Top 10 of 40 that pass": what the list shows of the companies that pass. */
  listText?: string; notes?: string[]; rankScoreNote?: string; emptyText?: string; ratedCount?: number;
  /** Paging (every screen but the Top 10 lists and the theme view): `pageSize` is 25; `offset` the first row's place in the ranked list (0-based); `available` how many rows can be paged to. */
  pageSize?: number; offset?: number; limit?: number; available?: number; hasMore?: boolean;
};
export const PAGE_SIZE = 25;
/** The rows a page shows, as "26–50 of 76" (the numbers come from the response). */
export function pageRange(d: Pick<PresetDetail, "count" | "offset" | "shown">): { from: number; to: number; of: number } {
  const from = (d.offset ?? 0) + 1, to = (d.offset ?? 0) + d.shown;
  return { from: Math.min(from, to + 1), to, of: d.count };
}

export const DISCLAIMER = "A screen narrows a list. It is not a recommendation.";
/** The order the groups are shown in; a group the API adds later follows these, before "Prism basics". */
export const GROUP_ORDER = ["Top rated", "Trend", "Growth", "Themes", "Value and income", "Safety", "Ownership"];
export const BASICS = "Prism basics";

/** Groups in the spec's order. A group the API omits is simply absent; unknown ones come last (but before Prism basics, which the page adds itself). */
export function orderGroups(groups: PresetGroup[]): PresetGroup[] {
  const rank = (g: PresetGroup) => { const i = GROUP_ORDER.findIndex((n) => n.toLowerCase() === g.name.trim().toLowerCase()); return i < 0 ? GROUP_ORDER.length : i; };
  return groups.map((g, i) => ({ g, i })).filter(({ g }) => g.presets.length > 0).sort((a, b) => rank(a.g) - rank(b.g) || a.i - b.i).map(({ g }) => g);
}

// ---------- the address ----------
export type PresetUrl = { preset: string | null; chips: string[] | null; trend: boolean; subs: string[] };
const NONE = "none";
/** ?preset=<id>, then `chip=<id>` repeated (the contract), plus the friendly `trend=1` and `sub=<id>`. chips === null: no chip in the address, so the screen's defaults apply. */
export function readPresetUrl(p: URLSearchParams): PresetUrl {
  const preset = (p.get("preset") || "").trim() || null;
  const raw = p.getAll("chip").map((c) => c.trim()).filter(Boolean);
  const trend = p.get("trend") === "1", subs = p.getAll("sub").map((s) => s.trim()).filter(Boolean);
  const explicit = raw.length > 0 || trend || subs.length > 0;
  return { preset, chips: explicit ? raw.filter((c) => c !== NONE) : null, trend, subs };
}
/** The chip ids a screen is asked with: the address's chips, with the friendly params mapped to the screen's own chip ids, or the defaults when the address names none. */
export function resolveChips(u: PresetUrl, preset: Preset | null): string[] {
  if (u.chips == null) return preset ? preset.chips.filter((c) => c.default).map((c) => c.id) : [];
  const ids = new Set(preset?.chips.map((c) => c.id) ?? []);
  const out = [...u.chips];
  const pick = (cands: string[], fallback: string) => out.push(cands.find((c) => ids.has(c)) ?? fallback);
  if (u.trend) pick(["trend", "trend-check", "trend_check", "trendcheck"], "trend");
  for (const s of u.subs) pick([s, `sub-${s}`, `sub_${s}`, `sub:${s}`, `sub-${s}s`], s);
  return [...new Set(out)];
}
/** The address for a screen and its chip choice: defaults leave no chip in it; an empty choice where defaults exist is written `chip=none`. */
export function presetParams(prev: URLSearchParams, id: string | null, chips: string[] | null, preset: Preset | null): URLSearchParams {
  const n = new URLSearchParams(prev);
  ["preset", "chip", "trend", "sub"].forEach((k) => n.delete(k));
  n.delete("page");
  if (!id) return n;
  n.set("preset", id);
  if (chips) {
    const defaults = (preset?.chips ?? []).filter((c) => c.default).map((c) => c.id).sort().join(",");
    if (chips.slice().sort().join(",") !== defaults) { if (chips.length) chips.forEach((c) => n.append("chip", c)); else n.append("chip", NONE); }
  }
  return n;
}

// ---------- the queries ----------
export function usePresetList(enabled = true, tab: PresetTab = "advanced") {
  return useQuery<PresetList, ApiError>({
    queryKey: ["presets", tab], staleTime: 300_000, enabled, retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 1,
    queryFn: async () => { const d = await apiGet<PresetList>("/api/screener/presets" + (tab === "basic" ? "?tab=basic" : "")); return { asOf: d.asOf ?? null, tab, groups: Array.isArray(d.groups) ? d.groups : [] }; },
  });
}
/** `offset` and `limit` page a long screen (the first page leaves them out, so it is the cached answer as sent). */
export const detailPath = (id: string, chips: string[], offset = 0, limit?: number) => {
  const q = chips.map((c) => "chip=" + encodeURIComponent(c));
  if (offset > 0) q.push("offset=" + offset);
  if (limit != null) q.push("limit=" + limit);
  return `/api/screener/presets/${encodeURIComponent(id)}` + (q.length ? "?" + q.join("&") : "");
};
export function usePresetDetail(id: string | null, chips: string[], enabled: boolean, offset = 0) {
  return useQuery<PresetDetail, ApiError>({
    queryKey: ["preset", id, [...chips].sort().join(","), offset], enabled: enabled && !!id, staleTime: 300_000, placeholderData: keepPreviousData,
    retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 1,
    queryFn: () => apiGet<PresetDetail>(detailPath(id!, chips, offset)),
  });
}

// ---------- the table ----------
export type SortState = { key: string; dir: 1 | -1 } | null;
const val = (r: PresetRow, key: string): unknown => (key === "symbol" ? r.symbol : r[key]);
/** Sorts the shown rows only (the screen's own order is the default). Missing values always go last. */
export function sortPresetRows(rows: PresetRow[], s: SortState): PresetRow[] {
  if (!s) return rows;
  return rows.map((r, i) => ({ r, i })).sort((a, b) => {
    const x = val(a.r, s.key), y = val(b.r, s.key), nx = x == null || x === "", ny = y == null || y === "";
    if (nx || ny) return nx && ny ? a.i - b.i : nx ? 1 : -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "en", { numeric: true, sensitivity: "base" });
    return c * s.dir || a.i - b.i;
  }).map((o) => o.r);
}
export const nextSortState = (s: SortState, key: string, firstDir: 1 | -1 = -1): SortState => (!s || s.key !== key ? { key, dir: firstDir } : s.dir === firstDir ? { key, dir: (firstDir * -1) as 1 | -1 } : null);

/** A theme's leaders only (the row filter behind the theme cards). */
export const rowsForTheme = (rows: PresetRow[], t: Theme | null): PresetRow[] => (t ? rows.filter((r) => t.leaders.includes(r.symbol)) : rows);

/** A breadth figure arrives as a percentage (43) or a share (0.43); both are shown as a percentage. */
export const asPct = (v: number | null | undefined): number | null => (v == null ? null : Math.abs(v) <= 1 ? v * 100 : v);
