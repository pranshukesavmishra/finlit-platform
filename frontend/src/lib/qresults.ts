// Quarter results: the rows the server sends (GET /api/results/quarter), the Telegram-style one-line summary, and the CSV.
// The server decides what a plan may see and whether a company's figures are for THIS quarter; this file only formats what it is sent.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";
import { MINUS, csvText, nf } from "./format";

export type QStatus = "declared" | "awaiting" | "due" | "missing";
export type QRow = {
  date: string; symbol: string; name: string; sector: string | null; marketCap: number | null; cap: "Large" | "Mid" | "Small" | null; indices: string[];
  confirmed: boolean; periodEnd: string; loadedPeriodEnd: string | null; status: QStatus; awaiting: boolean; hasNumbers: boolean; locked: boolean;
  revenue: number | null; revenueYoY: number | null; revenueQoQ: number | null; operatingProfit: number | null; opYoY: number | null; opQoQ: number | null; opYoYWhy: string | null; opQoQWhy: string | null; opm: number | null;
  netProfit: number | null; profitYoY: number | null; profitQoQ: number | null; npm: number | null; npmChange: number | null; eps: number | null;
  gap: number | null; flagged: boolean; loss: boolean;
  /** Where the figures come from: the stored full report, or the light table (a smaller company, one provider call). Null without figures. */
  source?: "full" | "light" | null; basis?: "consolidated" | "standalone" | null;
  /** For an awaiting row: "provider" = we asked and the data provider has not published the quarter yet; "ours" = our own report is still being updated. */
  awaitingWhy?: "provider" | "ours" | null;
  /** For an awaiting row: "recent" = declared today (the provider is normally still catching up), "late" = declared on an earlier day. */
  awaitingStage?: "recent" | "late" | null;
  /** When we last asked the provider about this company (ISO, UTC), and the newest quarter the provider holds for it (ISO date). Null when not asked yet. */
  lastCheckedAt?: string | null; providerLatest?: string | null;
  /** Price position: the latest price, the 52-week range (the exchange's intraday high and low), the all-time high (highest close in our history) and how far below each
   *  high the price is, in per cent. stale* = the price is above the stored high, so the distance is shown as 0. Null when not held (or on Basic). */
  price?: number | null; high52?: number | null; low52?: number | null; ath?: number | null; athDate?: string | null;
  below52?: number | null; belowAth?: number | null; above52Low?: number | null; stale52?: boolean; staleAth?: boolean;
};
export type QSummary = {
  companies: number; declared: number; due: number; awaiting: number; awaitingProvider?: number; awaitingOurs?: number; withNumbers: number; flagged: number | null;
  medianRevenueYoY: number | null; medianProfitYoY: number | null; profitUpShare: number | null; marginUpShare: number | null; nRevenue: number | null; nProfit: number | null; nMargin: number | null;
};
export type QInfo = { key: string; label: string; fiscal: string; periodEnd: string; from: string; to: string };
export type QResp = {
  plan: "basic" | "silver" | "gold"; locked: boolean; today: string; quarter: QInfo | null; quarters: (QInfo & { total: number; declared: number; due: number })[];
  total: number; offset: number; limit: number; summary: QSummary; totals: QSummary; rows: QRow[]; days: { date: string; n: number }[];
  facets: { sectors: { name: string; n: number }[]; indices: { code: string; n: number }[] }; gapFlag?: number; updatedAt?: string;
  dates?: QDates | null; dateMeaning?: string;
  /** Null when no growth filter is on. Counts are over every company with figures (before paging). */
  growth?: GrowthSummary | null; distribution?: QDistribution;
  /** Null when no price-position filter is on. */
  price?: PriceSummary | null;
  /** Counts over the companies in the table (Silver): how many sit within 5% of each high and how many have no such high. */
  priceStrip?: { companies: number; have52: number; near52: number; haveAth: number; nearAth: number } | null;
};
export type PriceCondSummary = { key: PriceKey; band: number | null; min: number; max: number | null; met: number; missing: number };
export type PriceSummary = { join: "and" | "or"; k: number; companies: number; withFigures: number; matching: number; combined?: number; conditions: PriceCondSummary[] };
/** One filled condition as the server counted it: how many companies with figures meet it, and how many have no such figure (and so cannot). */
export type GrowthCondSummary = { metric: GrowthMetric; period: "qoq" | "yoy"; op: GrowthOp; value: number; met: number; missing: number };
/** metAll + metSome + metNone = withFigures. "Matching" is metAll with AND and metAll + metSome with OR. */
export type GrowthSummary = { join: "and" | "or"; k: number; withFigures: number; matching: number; metAll: number; metSome: number; metNone: number; conditions: GrowthCondSummary[]; combined?: number };
export type QDistribution = { total: number; sectors: { name: string; n: number }[]; caps: { name: string; n: number }[] };
/** What the server found for a date filter, before the other filters: the quarters announced in range, the nearest days with results, what we hold. */
export type QDates = {
  from: string; to: string; single: boolean; inQuarter: boolean; quarters: { key: string; label: string; fiscal: string; n: number }[];
  nearest: { date: string; n: number }[]; coverage: { earliest: string | null; latest: string | null };
};
export type QParams = {
  quarter?: string; q?: string; sector?: string; cap?: string; index?: string; scope?: "all" | "watchlist" | "portfolio"; flagged?: boolean; status?: string;
  sort?: string; dir?: "asc" | "desc"; offset?: number; limit?: number;
  date?: string; from?: string; to?: string;   // the announcement date (one day) or a from-to range, India dates as YYYY-MM-DD
} & Partial<Record<`${CellKey}Op` | `${CellKey}Value` | "join" | PriceQueryKey, string>>;

// ------------------------------------------------------------ growth filters
// A grid of up to six thresholds: Revenue, Operating profit and Net profit, each against the quarter before (QoQ) and the same quarter a year earlier (YoY).
// An empty cell is off. The filled cells combine with AND ("all") or OR ("any"). The state lives in the page address under the names the server reads, and the
// SERVER does the filtering, so the counts and the table always cover every matching company.
export type GrowthMetric = "revenue" | "operatingProfit" | "netProfit";
export type GrowthPeriod = "qoq" | "yoy";
export type GrowthOp = ">=" | ">" | "<=" | "<";
export const GROWTH_METRICS: [GrowthMetric, string][] = [["revenue", "Revenue"], ["operatingProfit", "Operating profit"], ["netProfit", "Net profit"]];
export const GROWTH_OPS: GrowthOp[] = [">=", ">", "<=", "<"];
export const GROWTH_PERIODS: [GrowthPeriod, string][] = [["qoq", "QoQ"], ["yoy", "YoY"]];
/** The grid cells, row by row; the key is also the query name (<key>Op, <key>Value). */
export const GROWTH_CELLS = ["revQoQ", "revYoY", "opQoQ", "opYoY", "npQoQ", "npYoY"] as const;
export type CellKey = (typeof GROWTH_CELLS)[number];
export const CELL_OF: Record<CellKey, [GrowthMetric, GrowthPeriod]> = {
  revQoQ: ["revenue", "qoq"], revYoY: ["revenue", "yoy"], opQoQ: ["operatingProfit", "qoq"], opYoY: ["operatingProfit", "yoy"], npQoQ: ["netProfit", "qoq"], npYoY: ["netProfit", "yoy"],
};
/** Which row field each cell reads: the SAME rounded figure the table shows. */
export const FIELD_OF: Record<CellKey, keyof QRow> = { revQoQ: "revenueQoQ", revYoY: "revenueYoY", opQoQ: "opQoQ", opYoY: "opYoY", npQoQ: "profitQoQ", npYoY: "profitYoY" };
export const cellKeyOf = (m: GrowthMetric, p: GrowthPeriod): CellKey => GROWTH_CELLS.find((k) => CELL_OF[k][0] === m && CELL_OF[k][1] === p) as CellKey;
export const GROWTH_KEYS: string[] = [...GROWTH_CELLS.flatMap((k) => [k + "Op", k + "Value"]), "join", "qoqMetric", "qoqOp", "qoqValue", "yoyMetric", "yoyOp", "yoyValue"];
export type GrowthCond = { op: GrowthOp; value: string };
export type GrowthJoin = "and" | "or";
export type GrowthState = { cells: Record<CellKey, GrowthCond>; join: GrowthJoin };
export const DEFAULT_COND: GrowthCond = { op: ">=", value: "" };
export const emptyCells = (): Record<CellKey, GrowthCond> => Object.fromEntries(GROWTH_CELLS.map((k) => [k, DEFAULT_COND])) as Record<CellKey, GrowthCond>;
export const DEFAULT_GROWTH: GrowthState = { cells: emptyCells(), join: "and" };
/** The same rule the server applies: a plain decimal, optional sign, no exponent or words. */
export const VALUE_RE = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;
export const cleanValue = (v: string) => v.trim().replace(/\u2212/g, "-");   // a typed or pasted minus sign (U+2212) counts as a minus
export const valueProblem = (v: string): string | null => {
  const t = cleanValue(v);
  if (t === "") return null;
  if (!VALUE_RE.test(t) || !Number.isFinite(Number(t))) return "Type a number such as 1, -2.5 or 12 (per cent).";
  return Math.abs(Number(t)) > 1_000_000 ? "That number is too large." : null;
};
const opOf = (o: string | null): GrowthOp => (o && (GROWTH_OPS as string[]).includes(o) ? (o as GrowthOp) : DEFAULT_COND.op);
/** Reads the address. Links shared before the grid existed carried one metric per column (?qoqMetric=revenue&qoqOp=>=&qoqValue=5&yoyMetric=...): each is placed in
 *  its grid cell, so those links still open with the same filter. A grid cell in the address wins over an old-style value for the same cell. */
export const growthFromParams = (sp: URLSearchParams): GrowthState => {
  const cells = emptyCells();
  for (const [per] of GROWTH_PERIODS) {
    const value = sp.get(per + "Value") || "";
    if (value === "") continue;
    const m = sp.get(per + "Metric");
    const metric = GROWTH_METRICS.some(([x]) => x === m) ? (m as GrowthMetric) : "netProfit";   // the old default metric was net profit
    cells[cellKeyOf(metric, per)] = { op: opOf(sp.get(per + "Op")), value };
  }
  for (const k of GROWTH_CELLS) {
    const value = sp.get(k + "Value") || "", o = sp.get(k + "Op");
    if (value !== "" || o) cells[k] = { op: opOf(o), value };
  }
  return { cells, join: sp.get("join") === "or" ? "or" : "and" };
};
/** A condition is on when its value is a valid number. */
export const condOn = (c: GrowthCond) => cleanValue(c.value) !== "" && valueProblem(c.value) === null;
export const onCells = (g: GrowthState): CellKey[] => GROWTH_CELLS.filter((k) => condOn(g.cells[k]));
export const growthOn = (g: GrowthState) => onCells(g).length > 0;
export const growthIsDefault = (g: GrowthState) => JSON.stringify(g) === JSON.stringify(DEFAULT_GROWTH);
/** Write the state into a copy of the address: only what differs from the defaults, so a clean address stays clean. Old-style keys are dropped (the grid keys replace them). */
export function growthToParams(sp: URLSearchParams, g: GrowthState): URLSearchParams {
  const n = new URLSearchParams(sp);
  for (const k of GROWTH_KEYS) n.delete(k);
  for (const k of GROWTH_CELLS) {
    const c = g.cells[k], v = cleanValue(c.value);
    if (v !== "" || c.op !== DEFAULT_COND.op) n.set(k + "Op", c.op);
    if (v !== "") n.set(k + "Value", v);
  }
  if (g.join === "or") n.set("join", "or");
  return n;
}
/** The query values the server reads. An invalid value is left out (the field shows its message), never sent. */
export const growthQuery = (g: GrowthState): Partial<QParams> => {
  const out: Record<string, string> = {};
  for (const k of onCells(g)) { out[k + "Op"] = g.cells[k].op; out[k + "Value"] = cleanValue(g.cells[k].value); }
  if (growthOn(g)) out.join = g.join;
  return out;
};
/** Does this row meet the condition in this cell? A missing figure never does (the same rule as the server). */
export function cellHit(r: QRow, k: CellKey, c: GrowthCond): boolean {
  if (!condOn(c) || !r.hasNumbers) return false;
  const v = r[FIELD_OF[k]] as number | null, t = Number(cleanValue(c.value));
  return v == null ? false : c.op === ">=" ? v >= t : c.op === ">" ? v > t : c.op === "<=" ? v <= t : v < t;
}
export const metricLabel = (m: GrowthMetric) => GROWTH_METRICS.find(([x]) => x === m)?.[1] || m;
export const periodLabel = (p: GrowthPeriod) => (p === "qoq" ? "QoQ" : "YoY");
export const opWords = (o: GrowthOp) => ({ ">=": "at least", ">": "more than", "<=": "at most", "<": "less than" })[o];
/** Quick fills for the grid. Each sets all six cells (so it replaces what was typed) and the join. */
export type GrowthPreset = { id: string; label: string; hint: string; cells: Partial<Record<CellKey, GrowthCond>>; join: GrowthJoin };
const four = (op: GrowthOp, value: string): Partial<Record<CellKey, GrowthCond>> => ({ revQoQ: { op, value }, revYoY: { op, value }, npQoQ: { op, value }, npYoY: { op, value } });
export const GROWTH_PRESETS: GrowthPreset[] = [
  { id: "growing", label: "Revenue and net profit both growing", hint: "Revenue and net profit growth above 0% on the quarter before and on a year ago: all four conditions", cells: four(">", "0"), join: "and" },
  { id: "strong", label: "10% or more on all four", hint: "Revenue and net profit growth of at least 10% on the quarter before and on a year ago: all four conditions", cells: four(">=", "10"), join: "and" },
];
export const applyPreset = (p: GrowthPreset): GrowthState => ({ cells: { ...emptyCells(), ...p.cells }, join: p.join });
/** The preset the grid exactly equals, if any (so its button can show as pressed). */
export const activePreset = (g: GrowthState): string | null => GROWTH_PRESETS.find((p) => JSON.stringify(applyPreset(p)) === JSON.stringify({ ...g, cells: Object.fromEntries(GROWTH_CELLS.map((k) => [k, { op: g.cells[k].op, value: cleanValue(g.cells[k].value) }])) }))?.id ?? null;

// ------------------------------------------------------------ price position filters
// How far the latest price is below the 52-week high and below the all-time high, in eight bands (half-open: 0-5 holds 0 up to but not 5, ... the last holds 50 and more)
// or a typed minimum / maximum. Each measure is off ("Any") by default. The two combine with AND ("Match all") or OR ("Match any"), and with the growth filters by AND.
// 52-week high = the exchange's intraday high; all-time high = the highest close in our price history: different bases, said on the page.
export type PriceKey = "w52" | "ath";
export type PriceQueryKey = "p52" | "p52min" | "p52max" | "pAth" | "pAthMin" | "pAthMax" | "pJoin";
export const PRICE_KEYS: PriceKey[] = ["w52", "ath"];
export const PRICE_WORD: Record<PriceKey, string> = { w52: "52-week high", ath: "all-time high" };
export const PRICE_FIELD: Record<PriceKey, "below52" | "belowAth"> = { w52: "below52", ath: "belowAth" };
const PRICE_Q: Record<PriceKey, [PriceQueryKey, PriceQueryKey, PriceQueryKey]> = { w52: ["p52", "p52min", "p52max"], ath: ["pAth", "pAthMin", "pAthMax"] };
export const PRICE_PARAM_KEYS: string[] = [...PRICE_KEYS.flatMap((k) => PRICE_Q[k]), "pJoin"];
export const BAND_EDGES: [number, number | null][] = [[0, 5], [5, 10], [10, 15], [15, 20], [20, 30], [30, 40], [40, 50], [50, null]];
export const bandLabel = (i: number, k: PriceKey) => (i < BAND_EDGES.length - 1 ? `${BAND_EDGES[i][0]}\u2013${BAND_EDGES[i][1]}% below ${PRICE_WORD[k]}` : `Above 50% below ${PRICE_WORD[k]}`);
export const bandShort = (i: number) => (i < BAND_EDGES.length - 1 ? `${BAND_EDGES[i][0]}\u2013${BAND_EDGES[i][1]}%` : "50% or more");
/** The band a distance falls in: half-open [lo, hi), the last one open-ended. */
export const bandOf = (v: number): number => BAND_EDGES.findIndex(([lo, hi]) => v >= lo && (hi == null || v < hi));
export type PriceSide = { band: string; min: string; max: string };   // band "" = Any; a typed range is used when band is ""
export type PriceState = { w52: PriceSide; ath: PriceSide; join: GrowthJoin };
export const NO_SIDE: PriceSide = { band: "", min: "", max: "" };
export const DEFAULT_PRICE: PriceState = { w52: NO_SIDE, ath: NO_SIDE, join: "and" };
export const rangeProblem = (v: string): string | null => {
  const t = v.trim();
  if (t === "") return null;
  if (!/^(\d+(\.\d*)?|\.\d+)$/.test(t) || Number(t) > 100) return "Type a number from 0 to 100 (per cent).";
  return null;
};
export const sideOn = (s: PriceSide) => (s.band !== "" && Number(s.band) >= 0 && Number(s.band) < BAND_EDGES.length) || ((s.min.trim() !== "" || s.max.trim() !== "") && !rangeProblem(s.min) && !rangeProblem(s.max) && !(s.min.trim() !== "" && s.max.trim() !== "" && Number(s.min) > Number(s.max)));
export const priceOn = (p: PriceState) => PRICE_KEYS.some((k) => sideOn(p[k]));
export const priceIsDefault = (p: PriceState) => JSON.stringify(p) === JSON.stringify(DEFAULT_PRICE);
export const priceFromParams = (sp: URLSearchParams): PriceState => {
  const side = (k: PriceKey): PriceSide => {
    const [b, lo, hi] = PRICE_Q[k], band = sp.get(b) || "";
    if (/^[0-7]$/.test(band)) return { band, min: "", max: "" };
    return { band: "", min: rangeProblem(sp.get(lo) || "") ? "" : (sp.get(lo) || "").trim(), max: rangeProblem(sp.get(hi) || "") ? "" : (sp.get(hi) || "").trim() };
  };
  return { w52: side("w52"), ath: side("ath"), join: sp.get("pJoin") === "or" ? "or" : "and" };
};
/** Writes only what differs from the defaults; the growth and other parameters in `sp` are untouched. */
export function priceToParams(sp: URLSearchParams, p: PriceState): URLSearchParams {
  const n = new URLSearchParams(sp);
  for (const k of PRICE_PARAM_KEYS) n.delete(k);
  for (const k of PRICE_KEYS) {
    const [b, lo, hi] = PRICE_Q[k], s = p[k];
    if (s.band !== "") n.set(b, s.band);
    else { if (s.min.trim() !== "") n.set(lo, s.min.trim()); if (s.max.trim() !== "") n.set(hi, s.max.trim()); }
  }
  if (p.join === "or") n.set("pJoin", "or");
  return n;
}
/** The query the server reads: only valid, filled measures (an invalid typed value is never sent). */
export const priceQuery = (p: PriceState): Partial<QParams> => {
  const out: Record<string, string> = {};
  for (const k of PRICE_KEYS) {
    const [b, lo, hi] = PRICE_Q[k], s = p[k];
    if (!sideOn(s)) continue;
    if (s.band !== "") out[b] = s.band; else { if (s.min.trim() !== "") out[lo] = s.min.trim(); if (s.max.trim() !== "") out[hi] = s.max.trim(); }
  }
  if (priceOn(p)) out.pJoin = p.join;
  return out;
};
/** Does this row meet the measure? Same rule as the server: no figure never does; a band is half-open, a typed range includes both ends. */
export function priceHit(r: QRow, k: PriceKey, s: PriceSide): boolean {
  const v = r[PRICE_FIELD[k]];
  if (v == null || !sideOn(s)) return false;
  if (s.band !== "") { const [lo, hi] = BAND_EDGES[Number(s.band)]; return v >= lo && (hi == null || v < hi); }
  return (s.min.trim() === "" || v >= Number(s.min)) && (s.max.trim() === "" || v <= Number(s.max));
}
export const sideText = (s: PriceSide, k: PriceKey) => (s.band !== "" ? bandLabel(Number(s.band), k) : `${s.min.trim() !== "" ? s.min.trim() + "%" : "0%"} to ${s.max.trim() !== "" ? s.max.trim() + "%" : "100%"} below ${PRICE_WORD[k]}`);
export type PricePreset = { id: string; label: string; hint: string; price: PriceState; growth?: GrowthPreset };
const side = (band: string, min = "", max = ""): PriceSide => ({ band, min, max });
export const PRICE_PRESETS: PricePreset[] = [
  { id: "near52", label: "Near the 52-week high", hint: "Less than 5% below the 52-week high", price: { ...DEFAULT_PRICE, w52: side("0") } },
  { id: "deepAth", label: "Deep below the all-time high", hint: "40% or more below the all-time high", price: { ...DEFAULT_PRICE, ath: side("", "40") } },
  { id: "growthNear", label: "Growth and near 52-week high", hint: "Revenue and net profit growth above 0%, and less than 5% below the 52-week high: both blocks apply together", price: { ...DEFAULT_PRICE, w52: side("0") }, growth: GROWTH_PRESETS[0] },
];
/** The preset the card's two states exactly equal, if any. */
export const activePricePreset = (g: GrowthState, p: PriceState): string | null =>
  PRICE_PRESETS.find((x) => JSON.stringify(x.price) === JSON.stringify(p) && (x.growth ? activePreset(g) === x.growth.id : !growthOn(g)))?.id ?? null;
/** Below-high wording for a table cell: "At 52-week high", "12.4%", or null when not held. */
export const atHigh = (v: number, k: PriceKey) => v === 0 ? `At ${PRICE_WORD[k]}` : "";
export const priceWhy = (r: QRow, k: PriceKey): string => {
  if (r.price == null) return "No current price is held for this company.";
  return k === "w52" ? "No 52-week high is held for this company." : "No long price history is held for this company yet, so there is no all-time high.";
};
/** Share in per cent for a legend, one decimal; 0 when there is nothing to divide. */
export const pctOf = (n: number, total: number) => (total > 0 ? (n / total) * 100 : 0);

export const PAGE = 50;
export const GAP_FLAG = 15;
export const GAP_LABEL = "Profit and sales moved apart";

export const queryString = (p: QParams) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "" && v !== false && !(k === "scope" && v === "all") && !(k === "offset" && v === 0)) u.set(k, String(v));
  return u.toString();
};

export const useQuarterResults = (p: QParams) => useQuery({
  queryKey: ["quarter-results", queryString(p)], staleTime: 60_000, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1, placeholderData: keepPreviousData,
  queryFn: () => apiGet<QResp>(`/api/results/quarter?${queryString({ limit: PAGE, ...p })}`),
});

/** The alert for this gap, ready to create: /alerts reads symbol, metric and value from the link. */
export const gapAlertLink = (symbol: string) => `/alerts?symbol=${encodeURIComponent(symbol)}&metric=rev_profit_gap&value=${GAP_FLAG}`;

// ------------------------------------------------------------ dates
// "Date" on this page means the day the company ANNOUNCED its results (the exchange filing's date, or the board-meeting date until the filing is out),
// as an Indian calendar date. Everything here works on plain YYYY-MM-DD text so the browser's own time zone can never move a day.
export const DATE_MEANING = "Date means the day the company announced (declared) its results: the date on its exchange filing, or its board-meeting date until the filing is out. All dates are Indian (IST) calendar dates.";
export const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export const todayIST = (now: Date = new Date()) => now.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
export const isRealDay = (v: string) => ISO_DAY.test(v) && new Date(v + "T00:00:00Z").toISOString().slice(0, 10) === v;
export const addDays = (iso: string, n: number) => new Date(new Date(iso + "T00:00:00Z").getTime() + n * 86_400_000).toISOString().slice(0, 10);
const weekday = (iso: string) => new Date(iso + "T00:00:00Z").getUTCDay();   // 0 = Sunday
export const isWeekend = (iso: string) => weekday(iso) === 0 || weekday(iso) === 6;
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const weekdayName = (iso: string) => DAYS[weekday(iso)];
export const longDay = (iso: string) => `${DAYS[weekday(iso)].slice(0, 3)}, ${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;   // fixed wording: the same in every browser
export const mondayOf = (iso: string) => addDays(iso, -((weekday(iso) + 6) % 7));
export const quarterStartOf = (iso: string) => `${iso.slice(0, 4)}-${String(Math.floor((Number(iso.slice(5, 7)) - 1) / 3) * 3 + 1).padStart(2, "0")}-01`;   // calendar quarter: Jan, Apr, Jul, Oct

export type DateSel = { date?: string; from?: string; to?: string };
export type DateChip = { id: string; label: string; sel: { date: string } | { from: string; to: string } };

/** The quick choices, worked out from today's Indian date. "This quarter" is the calendar quarter's announcements so far (1 Oct to today, in October). */
export const dateChips = (today: string): DateChip[] => [
  { id: "today", label: "Today", sel: { date: today } },
  { id: "yesterday", label: "Yesterday", sel: { date: addDays(today, -1) } },
  { id: "week", label: "This week", sel: { from: mondayOf(today), to: today } },
  { id: "last7", label: "Last 7 days", sel: { from: addDays(today, -6), to: today } },
  { id: "quarter", label: "This quarter", sel: { from: quarterStartOf(today), to: today } },
];

/** Which chip the current selection is exactly (so it can show as pressed). A single day that is also a one-day range counts as the same. */
export const activeChip = (sel: DateSel, today: string): string | null => {
  const from = sel.date || sel.from, to = sel.date || sel.to || (sel.from ? today : undefined);
  if (!from || !to) return null;
  for (const c of dateChips(today)) {
    const cf = "date" in c.sel ? c.sel.date : c.sel.from, ct = "date" in c.sel ? c.sel.date : c.sel.to;
    if (cf === from && ct === to) return c.id;
  }
  return null;
};

/** A plain-words problem with a date choice, or null when it is fine. The server checks the same rules; this only saves a round trip. */
export function dateProblem(sel: DateSel, today: string): string | null {
  const bad = (v?: string) => !!v && !isRealDay(v);
  if (bad(sel.date) || bad(sel.from) || bad(sel.to)) return "Enter a real date as day, month and year.";
  if (sel.to && !sel.from) return "Choose the from date as well as the to date.";
  const hi = [sel.date, sel.from, sel.to].filter(Boolean).sort().pop();
  if (hi && hi > today) return `Results can be looked up for dates up to today (${longDay(today)}, India time).`;
  if (sel.from && sel.to && sel.from > sel.to) return "The from date is after the to date.";
  return null;
}

/** The selection a page address carries (?date= or ?from=&to=). A single day wins over a range. */
export const dateFromParams = (sp: URLSearchParams): DateSel => {
  const date = sp.get("date") || "", from = sp.get("from") || "", to = sp.get("to") || "";
  return date ? { date } : from || to ? { from: from || undefined, to: to || undefined } : {};
};

export const describeSel = (sel: DateSel, today: string) =>
  sel.date ? `announced on ${longDay(sel.date)}` : sel.from ? (sel.from === (sel.to || today) ? `announced on ${longDay(sel.from)}` : `announced from ${longDay(sel.from)} to ${longDay(sel.to || today)}`) : "";

// ------------------------------------------------------------ text
const rs = (v: number) => `Rs${nf(Math.abs(v), 2)} CR`;
const dir = (v: number) => (v >= 0 ? "UP" : "DOWN");
const pc = (v: number) => `${Math.round(Math.abs(v))}%`;
const move = (v: number | null, tag: string) => (v == null ? null : `${dir(v)} ${pc(v)} (${tag})`);

/** One line in the style of a results alert channel:
 *  "DLF Q2 FY27: NET PROFIT UP 10% AT Rs1,260.58 CR (YOY), UP 3% (QOQ) / REVENUE DOWN 23% AT Rs... / OPM 20.1%, NPM 13.3% / EPS Rs2.20"
 *  Only what is known is said: a growth rate that cannot be worked out (the year-ago profit was a loss) is left out, never guessed. */
export function headline(r: Pick<QRow, "symbol" | "revenue" | "revenueYoY" | "revenueQoQ" | "netProfit" | "profitYoY" | "profitQoQ" | "opm" | "npm" | "eps">, fiscal?: string): string | null {
  const part = (label: string, v: number | null, yoy: number | null, qoq: number | null) => {
    if (v == null) return null;
    const moves = [yoy == null ? null : `${dir(yoy)} ${pc(yoy)} AT ${rs(v)} (YOY)`, move(qoq, "QOQ")].filter(Boolean) as string[];
    if (yoy == null) return `${label} AT ${rs(v)}${qoq == null ? "" : ", " + moves.join(", ")}`;
    return `${label} ${moves.join(", ")}`;
  };
  const np = r.netProfit != null && r.netProfit < 0
    ? `NET LOSS AT ${rs(r.netProfit)}${[move(r.profitQoQ, "QOQ")].filter(Boolean).map((x) => ", " + x).join("")}`
    : part("NET PROFIT", r.netProfit, r.profitYoY, r.profitQoQ);
  const margins = [r.opm == null ? null : `OPM ${nf(r.opm, 1)}%`, r.npm == null ? null : `NPM ${r.npm < 0 ? MINUS : ""}${nf(r.npm, 1)}%`].filter(Boolean).join(", ");
  const parts = [np, part("REVENUE", r.revenue, r.revenueYoY, r.revenueQoQ), margins || null, r.eps == null ? null : `EPS ${r.eps < 0 ? "-" : ""}Rs${nf(r.eps, 2)}`].filter(Boolean) as string[];
  return parts.length ? `${r.symbol}${fiscal ? " " + fiscal : ""}: ${parts.join(" / ")}` : null;
}

export const signedPct = (v: number | null, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(v, d)}%`);

// ------------------------------------------------------------ CSV
const cell = (v: string | number | boolean | null | undefined) => {
  if (v == null || v === "") return "";
  const s = csvText(String(v));
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export const CSV_HEAD = ["Declared on", "Symbol", "Company", "Sector", "Market cap (Rs Cr)", "Status", "Revenue (Rs Cr)", "Revenue YoY %", "Revenue QoQ %", "Operating profit (Rs Cr)", "Operating profit YoY %", "Operating profit QoQ %", "OPM %",
  "Net profit (Rs Cr)", "Profit YoY %", "Profit QoQ %", "NPM %", "Net margin change YoY (pts)", "EPS (Rs)", "Revenue vs profit gap (pts)", "Profit and sales moved apart",
  "Price (Rs)", "52-week high (Rs)", "52-week low (Rs)", "Below 52-week high %", "Above 52-week low %", "All-time high (Rs)", "All-time high date", "Below all-time high %", "Price above a stored high"];
const dayShort = (iso: string) => { const d = new Date(iso + "T00:00:00"); return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" }); };
/** The honest reason a declared company has no figures yet: the data provider is behind, or our own report is still being updated. */
export const awaitingText = (date: string, why?: "provider" | "ours" | null): string =>
  why === "provider" ? `Declared on ${dayShort(date)}; the data provider has not published the figures yet` : "Declared, report being updated";
const istTime = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }) + " IST on " + d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" }); };
/** The sentence under a declared company that has no figures yet. Declared today: the usual lag. Declared on an earlier day: say it is still loading, that we are
 *  retrying, when we last asked and what the provider holds, so a stuck company is visible and not passed off as normal. */
export const awaitingNote = (r: Pick<QRow, "date" | "awaitingWhy" | "awaitingStage" | "lastCheckedAt" | "providerLatest">): string => {
  const prov = r.awaitingWhy === "provider";
  if (r.awaitingStage !== "late") return prov ? `${awaitingText(r.date, "provider")}. We check again every hour.` : "Declared, report being updated. Figures appear here as soon as the company's report is refreshed.";
  const last = r.lastCheckedAt ? istTime(r.lastCheckedAt) : "";
  const held = r.providerLatest ? new Date(r.providerLatest + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" }) : "";
  return `Declared on ${dayShort(r.date)}; still loading, we are retrying. ` + (prov ? "The data provider has not published this quarter" + (held ? ` (its newest is ${held})` : "") + "." : "Our report has not been rebuilt for this quarter yet.") + (last ? ` Last checked ${last}.` : " Not checked yet.");
};
/** One plain status line per row (the CSV's Status column). */
export const statusText = (r: Pick<QRow, "status" | "date" | "awaitingWhy">): string =>
  r.status === "awaiting" ? awaitingText(r.date, r.awaitingWhy) : ({ declared: "Declared", due: "Due", missing: "Figures not stored", awaiting: "" } as Record<QStatus, string>)[r.status];

export function csvOf(rows: QRow[], quarterLabel: string): string {
  const lines = [[`Quarter: ${quarterLabel}`], CSV_HEAD].map((l) => l.map(cell).join(","));
  for (const r of rows) {
    lines.push([r.date, r.symbol, r.name, r.sector, r.marketCap, statusText(r), r.revenue, r.revenueYoY, r.revenueQoQ, r.operatingProfit, r.opYoY, r.opQoQ, r.opm, r.netProfit, r.profitYoY, r.profitQoQ, r.npm, r.npmChange, r.eps, r.gap,
      r.hasNumbers ? (r.flagged ? "Yes" : "No") : "", r.price, r.high52, r.low52, r.below52, r.above52Low, r.ath, r.athDate, r.belowAth,
      [r.stale52 ? "52-week high" : "", r.staleAth ? "all-time high" : ""].filter(Boolean).join(" and ")].map(cell).join(","));
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}
