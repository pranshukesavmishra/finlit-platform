// Sector Pulse: the contract of GET /api/sectors, /api/sectors/{slug} and /api/technicals/{symbol}/sector (backend/finlit/sector_api.py, docs/SECTORS.md),
// the hooks that read them, and the pure helpers the pages share (filters, sorting, wording, the chart's geometry). Every number on the pages comes from these
// payloads: a figure the plan does not include arrives as null with `locked` naming the plan that opens it, and a blank always shows its reason.
// The pages describe price and breadth data; they never advise.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";
import { MINUS, dateIN } from "./format";

export type StateName = "Thrust C" | "Thrust CAP" | "Confirmed" | "Washout" | "Fading" | "Neutral";
export type StateCode = "thrust_c" | "thrust_cap" | "confirmed" | "washout" | "fading" | "neutral";
export type PlanName = "basic" | "silver" | "gold";
/** What this plan may not see yet: field -> the plan that opens it. Empty when nothing is locked. */
export type Locked = Record<string, PlanName>;

export const STATES: { name: StateName; code: StateCode }[] = [
  { name: "Thrust C", code: "thrust_c" }, { name: "Thrust CAP", code: "thrust_cap" }, { name: "Confirmed", code: "confirmed" },
  { name: "Washout", code: "washout" }, { name: "Fading", code: "fading" }, { name: "Neutral", code: "neutral" },
];

/** The few rotation fields other pages show (finlit_technicals rotation.brief). */
export type RotationBrief = {
  corner: CornerCode; corner_name: string; weeks_in_corner: number; this_week_reading_name: string | null; rank: number | null; ranked: number | null;
  rank_change_1w: number | null; rank_change_4w: number | null; strength_pts: number | null; change_pts: number | null; breadth: "broad" | "narrow" | "between" | null; breadth_name: string | null;
};
export type CornerCode = "ahead_gaining" | "ahead_slowing" | "behind_slipping" | "behind_gaining" | "middle";

export type Breadth = { above_9: number | null; above_20: number | null; above_50: number | null; lowest_50_last_30?: number | null };
export type Thrust = { type: "C" | "CAP"; date: string; sessions_ago: number } | null;
export type GroupRow = {
  name: string; slug: string; kind: "industry" | "sector"; sector: string; industries: string[]; date: string; state: StateName; state_code: StateCode; meaning: string;
  breadth: Breadth; index_vs_52w_high: number | null; last_60d_low: { sessions_ago: number; date: string } | null; higher_low_share: number | null; last_thrust: Thrust;
  /** Why the higher-low share is blank (null when it has a value). */
  higher_low_note?: string | null;
  today: { thrust_c: boolean; thrust_cap: boolean; turned_fading: boolean; confirmed: boolean }; leader_flags: number | null;
  stocks_counted: number; stocks_listed: number; stocks_traded_today: number;
  /** Counted members with no price on the last session (usually 0); `stocks_counted` is the base of the breadth readings and leaves them out. */
  members_not_traded_today?: number;
  /** Rotation reading (sectors/_board.json rows[].rotation); null when the group has fewer than 8 counted stocks or the set has no rotation yet. */
  rotation?: RotationBrief | null;
  /** The one-line story (industry page and stock card only). */
  summary?: string; rule?: string; study?: string; since?: string | null;
};
export type MarketNow = { date: string; nifty50: number | null; nifty50_200d_average: number | null; pct_vs_200d: number | null; above_200d: boolean | null; note: string | null;
  /** "200-day exponential average": the name to print for the average. */
  average_label?: string };
export type LeaderFlag = { symbol: string; group: string; group_slug: string; tier: string; tier_code: number; sessions_ago: number; new_today: boolean; quarter: number | null; state: StateName };
export type Universe = { date: string; stocks_with_industry_traded: number; meet_rules: number; counted_in_groups_with_reading: number; not_counted: number; reasons: { reason: string; stocks: number }[] };
export type StudyFigures = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
export type Board = {
  date: string; groups: number; industries: number; stocks_counted: number; universe_rules: string;
  counts: Record<StateName, number>; state_meanings: Record<StateName, string>; market: MarketNow | null; market_note: string | null;
  rows: GroupRow[]; too_few_stocks: { name: string; slug: string; kind: string; stocks_counted: number }[]; universe: Universe;
  leader_flags: LeaderFlag[] | null; leader_flag_study: string; study: { market: string; rallies: string; limits: string; figures: StudyFigures };
  disclaimer: string; locked?: Locked; plan?: PlanName;
};
export type RankedStock = {
  symbol: string; name: string; industry: string; close: number | null; traded_today: boolean; rank_6m: number | null; return_6m_pct: number | null; quarter: number | null; quarter_name: string | null;
  bottom_code: number | null; bottom: string | null; bottomed_before: boolean | null; above_20_day: boolean | null; leader_flag: { tier: string; tier_code: number; sessions_ago: number; new_today: boolean } | null;
  amfi_category: string | null; peer_label: string | null;
};
export type NotCounted = { symbol: string; name: string; industry: string; close: number | null; not_counted_because: string[] };
export type Band = { state: StateName; state_code: StateCode; from: string; to: string };
export type SectorEvent = { date: string; kind: "thrust_c" | "thrust_cap" | "turned_fading" | "confirmed" };
export type IndustryPage = GroupRow & {
  market: MarketNow | null; ranked_6m: number; rule: string; summary: string; since: string | null;
  /** Past readings use today's grouping (show under the breadth chart). */
  history_note?: string; /** The 9, 20 and 50-day averages are exponential averages. */ averages_note?: string;
  history: { dates: string[]; above_9: (number | null)[]; above_20: (number | null)[]; above_50: (number | null)[]; state_code: StateCode[]; index_vs_52w_high: (number | null)[]; stocks_counted: number[] };
  bands: Band[]; events: SectorEvent[];
  study: { state: string; market: string; rallies: string; limits: string; quarter?: string; bottom?: string; leader_flag?: string; figures?: StudyFigures };
  stocks: RankedStock[] | null; not_counted: NotCounted[] | null; universe_rules: string; leader_flag_note: string | null; disclaimer: string; locked?: Locked; plan?: PlanName;
};
export type StockSector = {
  symbol: string; name?: string | null; industry?: string | null; sector?: string | null; amfi_category?: string | null; in_group?: boolean | null;
  group: (GroupRow & { study?: string }) | null; rotation?: RotationBrief | null; market?: MarketNow | null; disclaimer?: string | null;
  rank_6m?: number | null; ranked_6m?: number | null; return_6m_pct?: number | null; quarter?: number | null; quarter_name?: string | null; bottom_code?: number | null; bottom?: string | null;
  leader_flag?: { tier: string; tier_code: number; sessions_ago: number } | null; leader_flag_text?: string | null;
  study?: { leader_flag?: string; quarter?: string; bottom?: string; limits?: string }; note?: string | null; not_counted_because?: string[] | null;
  locked?: Locked; plan?: PlanName;
};
export type SectorStatus = {
  enabled: boolean; loaded: boolean; dataDate: string | null; stocksCounted: number | null; groups: number | null; industries: number | null;
  stockFiles: number | null; stockErrors: number | null; builtAt: string | null; seconds: number | null;
  lastRun: { status: string | null; at: string | null; reason: string | null; dataDate: string | null; fetch?: { status?: string; message?: string } } | null; reason: string | null;
};

// ------------------------------------------------------------------------------------------------ reading the API
const retry = (n: number, e: unknown) => !(e instanceof ApiError && e.status < 500) && n < 1;
const STALE = 5 * 60_000;
export const useSectorBoard = () => useQuery<Board, ApiError>({ queryKey: ["sectors", "board"], queryFn: () => apiGet<Board>("/api/sectors"), staleTime: STALE, retry });
export const useSectorPage = (slug: string) => useQuery<IndustryPage, ApiError>({ queryKey: ["sectors", "page", slug], queryFn: () => apiGet<IndustryPage>(`/api/sectors/${encodeURIComponent(slug)}`), staleTime: STALE, retry, enabled: !!slug });
export const useSectorStatus = () => useQuery<SectorStatus, ApiError>({ queryKey: ["sectors", "status"], queryFn: () => apiGet<SectorStatus>("/api/sectors/status"), staleTime: 60_000, retry });
export const useStockSector = (symbol: string, enabled = true) =>
  useQuery<StockSector, ApiError>({ queryKey: ["sectors", "stock", symbol], queryFn: () => apiGet<StockSector>(`/api/technicals/${encodeURIComponent(symbol)}/sector`), staleTime: STALE, retry, enabled: enabled && !!symbol });

/** The sentence a blank shows when a request failed: the server's own reason when it gave one ("Sector data is not loaded yet: ..."), else a plain line. */
export function failureText(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as { reason?: string; detail?: string };
    if (b?.reason) return b.reason;
    if (e.status === 404) return "There is no sector reading for this address.";
    if (e.status >= 500) return b?.detail || "The sector data could not be read just now. Please try again in a moment.";
    return e.message;
  }
  return "The sector data could not be loaded. Please check your connection and try again.";
}

// ------------------------------------------------------------------------------------------------ numbers and words
/** The board carries no averages_note (industry pages do): the same sentence, for the pages that read only the board. */
export const AVERAGES_NOTE = "The 9, 20 and 50-day averages of each stock, and the Nifty 50's 200-day average, are exponential moving averages (EMA).";
export const averageLabel = (m: { average_label?: string } | null | undefined): string => m?.average_label || "200-day exponential average";
export const pct = (v: number | null | undefined, d = 0, plus = false): string => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? MINUS : plus && v > 0 ? "+" : "") + Math.abs(v).toFixed(d) + "%");
export const level = (v: number | null | undefined): string => (v == null ? "—" : new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v));
export const count = (v: number | null | undefined): string => (v == null ? "—" : new Intl.NumberFormat("en-IN").format(v));
export const dayMonth = (iso: string | null | undefined): string => (iso ? dateIN(iso, { day: "numeric", month: "short" }) : "—");
export const fullDate = (iso: string | null | undefined): string => (iso ? dateIN(iso, { day: "numeric", month: "short", year: "numeric" }) : "—");
export const plural = (n: number, one: string, many = one + "s") => `${count(n)} ${n === 1 ? one : many}`;
export const ordinal = (n: number): string => `${n}${n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] || "th"}`;
export const stateClass = (s: string | null | undefined): string => (s ? "st-" + s.toLowerCase().replace(/[^a-z]+/g, "_").replace(/^_|_$/g, "") : "st-na");

export const thrustText = (t: Thrust): string => (t ? `${t.type} · ${t.sessions_ago} ${t.sessions_ago === 1 ? "session" : "sessions"} ago` : "None in the past year");
export const thrustLong = (t: Thrust): string => (t ? `${t.type} · ${fullDate(t.date)}` : "None");
/** "80 stocks counted (1 did not trade today)": members with no price on the last session are said, never hidden. */
export const countedText = (r: Pick<GroupRow, "stocks_counted" | "members_not_traded_today">): string =>
  `${plural(r.stocks_counted, "stock")} counted${r.members_not_traded_today ? ` (${r.members_not_traded_today} did not trade today)` : ""}`;
export const groupKindText = (r: Pick<GroupRow, "kind" | "industries" | "stocks_counted" | "members_not_traded_today">): string =>
  `${countedText(r)}${r.kind === "sector" ? ` · sector group of ${r.industries.length} small ${r.industries.length === 1 ? "industry" : "industries"}` : ""}`;
export const QUARTER = ["", "Top quarter", "2nd quarter", "3rd quarter", "Bottom quarter"];
export const flagText = (f: { tier: string } | null | undefined): string => (f ? (f.tier === "15%+" ? "15%+ below" : "10–15% below") : "None");
export const flagAge = (n: number): string => (n === 0 ? "52-week high today" : `last high ${n} ${n === 1 ? "session" : "sessions"} ago`);
export const signedPct = (v: number | null | undefined, d = 1): string => pct(v, d, true);

/** Filter buttons above the table. */
export type FilterKey = "all" | "thrust" | "washout" | "fading" | "flags";
export const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" }, { key: "thrust", label: "Fresh thrusts" }, { key: "washout", label: "Washout" }, { key: "fading", label: "Fading" }, { key: "flags", label: "With leader flags" },
];
export const inFilter = (r: GroupRow, f: FilterKey): boolean =>
  f === "all" ? true : f === "thrust" ? r.state_code === "thrust_c" || r.state_code === "thrust_cap" : f === "washout" ? r.state_code === "washout" : f === "fading" ? r.state_code === "fading" : (r.leader_flags ?? 0) > 0;
export const filterCounts = (rows: GroupRow[]): Record<FilterKey, number | null> => ({
  all: rows.length, thrust: rows.filter((r) => inFilter(r, "thrust")).length, washout: rows.filter((r) => inFilter(r, "washout")).length, fading: rows.filter((r) => inFilter(r, "fading")).length,
  flags: rows.some((r) => r.leader_flags == null) ? null : rows.filter((r) => inFilter(r, "flags")).length,
});

/** The order the board arrives in: fresh thrusts first, then Washout, then Fading ("Neutral" and "Confirmed" between). */
const STATE_ORDER: Record<string, number> = { thrust_cap: 0, thrust_c: 1, confirmed: 2, washout: 3, fading: 4, neutral: 5 };
export type SortKey = "name" | "state" | "above_9" | "above_20" | "above_50" | "index" | "higher_low" | "thrust" | "flags" | "counted";
export const SORT_LABEL: Record<SortKey, string> = { name: "Industry", state: "State", above_9: "9-day", above_20: "20-day", above_50: "50-day", index: "Index vs 52-week high", higher_low: "Higher-low share", thrust: "Last thrust", flags: "Leader flags", counted: "Stocks counted" };
const num = (r: GroupRow, k: SortKey): number | string | null =>
  k === "name" ? r.name.toLowerCase() : k === "state" ? STATE_ORDER[r.state_code] ?? 9 : k === "above_9" ? r.breadth.above_9 : k === "above_20" ? r.breadth.above_20 : k === "above_50" ? r.breadth.above_50
  : k === "index" ? r.index_vs_52w_high : k === "higher_low" ? r.higher_low_share : k === "thrust" ? (r.last_thrust ? r.last_thrust.sessions_ago : null) : k === "flags" ? r.leader_flags : r.stocks_counted;
/** Sort a copy of the rows; missing values always go last, whichever way it sorts, and ties keep the board's own order. */
export function sortRows(rows: GroupRow[], key: SortKey | null, dir: "asc" | "desc"): GroupRow[] {
  const idx = new Map(rows.map((r, i) => [r.slug, i]));
  if (!key) return [...rows];
  return [...rows].sort((a, b) => {
    const x = num(a, key), y = num(b, key);
    if (x == null && y == null) return (idx.get(a.slug) ?? 0) - (idx.get(b.slug) ?? 0);
    if (x == null) return 1;
    if (y == null) return -1;
    const c = typeof x === "string" ? x.localeCompare(String(y)) : (x as number) - (y as number);
    return c !== 0 ? (dir === "asc" ? c : -c) : (idx.get(a.slug) ?? 0) - (idx.get(b.slug) ?? 0);
  });
}

/** The two reasons about traded value are shown as one bar (the design merges "under Rs 1 crore" and "under Rs 2 crore"). */
export function mergedReasons(reasons: { reason: string; stocks: number }[]): { reason: string; stocks: number }[] {
  const traded = reasons.filter((r) => /median traded value under Rs [12] crore/.test(r.reason));
  const rest = reasons.filter((r) => !traded.includes(r));
  const out = traded.length ? [{ reason: "median traded value too low (under Rs 1 crore, or under Rs 2 crore to join)", stocks: traded.reduce((s, r) => s + r.stocks, 0) }, ...rest] : rest;
  return out.sort((a, b) => b.stocks - a.stocks);
}

/** Group counts for the sentence under the board's title: "37 groups with a reading (31 NSE industries and 6 sector groups)". */
export const groupsLine = (b: Pick<Board, "groups" | "industries" | "stocks_counted" | "date">): string =>
  `Data as of ${fullDate(b.date)}, after the close · ${count(b.stocks_counted)} stocks counted · ${b.groups} groups with a reading (${b.industries} NSE industries and ${b.groups - b.industries} sector groups) · industries as classified by NSE`;

// ------------------------------------------------------------------------------------------------ the breadth chart
export type ChartGeo = { x: (i: number) => number; y: (v: number) => number; path: (vals: (number | null)[]) => string; bandRects: { x: number; w: number; state: StateName; code: StateCode; from: string; to: string }[]; marks: { x: number; kind: SectorEvent["kind"]; date: string }[] };
/** Pixel positions for the three lines, the state bands and the event markers: one x per session (the bands and events are matched to the history's dates). */
export function chartGeometry(page: Pick<IndustryPage, "history" | "bands" | "events">, left: number, right: number, top: number, bottom: number): ChartGeo {
  const dates = page.history.dates, n = dates.length;
  const step = n > 1 ? (right - left) / (n - 1) : 0;
  const x = (i: number) => left + i * step;
  const y = (v: number) => bottom - (Math.max(0, Math.min(100, v)) / 100) * (bottom - top);
  const at = new Map(dates.map((d, i) => [d, i]));
  const firstOnOrAfter = (d: string) => { const i = dates.findIndex((x2) => x2 >= d); return i < 0 ? n - 1 : i; };
  const lastOnOrBefore = (d: string) => { for (let i = n - 1; i >= 0; i--) if (dates[i] <= d) return i; return 0; };
  const path = (vals: (number | null)[]) => {
    let s = "", pen = false;
    vals.forEach((v, i) => { if (v == null) { pen = false; return; } s += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`; pen = true; });
    return s;
  };
  const bandRects = page.bands.map((b) => {
    const a = firstOnOrAfter(b.from), z = lastOnOrBefore(b.to);
    return { x: x(a) - step / 2, w: Math.max(step, (z - a + 1) * step), state: b.state, code: b.state_code, from: b.from, to: b.to };
  }).filter((r) => r.w > 0);
  const marks = page.events.filter((e) => at.has(e.date)).map((e) => ({ x: x(at.get(e.date) as number), kind: e.kind, date: e.date }));
  return { x, y, path, bandRects, marks };
}
export const EVENT_WORD: Record<SectorEvent["kind"], string> = { thrust_c: "Thrust C", thrust_cap: "Thrust CAP", turned_fading: "Turned Fading", confirmed: "Confirmed" };

/** What a screen reader hears for the chart: the story in words, from the data only. */
export function chartSummary(p: Pick<IndustryPage, "name" | "history" | "events" | "since" | "state">): string {
  const n = p.history.dates.length;
  if (!n) return `${p.name}: no breadth history to draw.`;
  const last = n - 1, ev = (k: SectorEvent["kind"]) => p.events.filter((e) => e.kind === k).length;
  return `Breadth over ${n} sessions from ${fullDate(p.history.dates[0])} to ${fullDate(p.history.dates[last])}: the share of ${p.name} stocks above their 9, 20 and 50-day averages. `
    + `Today ${pct(p.history.above_9[last])}, ${pct(p.history.above_20[last])} and ${pct(p.history.above_50[last])}. In the period: ${ev("thrust_c")} Thrust C, ${ev("thrust_cap")} Thrust CAP, ${ev("turned_fading")} turned Fading. Now ${p.state}${p.since ? ` since ${dayMonth(p.since)}` : ""}.`;
}
