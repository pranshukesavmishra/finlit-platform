// Pure logic of the Score screener: scores per company, filters, sorting, paging, presets, summary numbers, URL state and CSV.
// No score is computed differently here than on the stock page: Fundamental is the average of the four business pillars, Technical is the
// technical pillar, Overall is the FinLit overall score as stored. A missing score is null and never passes a score filter or counts as zero.
import { csvText } from "./format";
import { scoreBand } from "./scoreBands";
import type { Row } from "./screener";
import { LABEL_WORD, LABEL_SLUG, PRISM_LABELS, PRISM_NAMES, PRISM_RANGE_KEYS, isLabel, labelFromSlug, prismRangeValue, hasPrism, type PrismCol, type PrismLabel, type PrismRangeKey } from "./scorePrism";

export type Cap = "Large" | "Mid" | "Small";
export type Band = "low" | "mid" | "high";
export type Pillar = "pillar_quality" | "pillar_growth" | "pillar_profitability" | "pillar_balance";
export type Item = Row & { cap: Cap | null; f: number | null; t: number | null };
export type BandKey = "f" | "t" | "q" | "g" | "p" | "b";
export type RangeKey = "f" | "t" | "o" | PrismRangeKey;
export type SortKey = "name" | "price" | "market_cap" | "sector" | "f" | "t" | "overall" | Pillar | PrismCol;
export type Range = { min: number | null; max: number | null };

export const CAPS: Cap[] = ["Large", "Mid", "Small"];
export const BAND_KEYS: BandKey[] = ["f", "t", "q", "g", "p", "b"];
export const RANGE_KEYS: RangeKey[] = ["f", "t", "o", ...PRISM_RANGE_KEYS];
/** The three score bands. They follow the FinLit model: Strong 78 and above, Watch under 45; "mid" joins its Healthy (62+) and Mixed (45+) bands. */
export const BANDS: Record<Band, { label: string; short: string; min: number; max: number }> = {
  low: { label: "Under 45 (Watch)", short: "<45", min: 0, max: 44 },
  mid: { label: "45 to 77 (Mixed, Healthy)", short: "45–77", min: 45, max: 77 },
  high: { label: "78 and above (Strong)", short: "78+", min: 78, max: 100 },
};
export const BAND_ORDER: Band[] = ["low", "mid", "high"];
export const FUNDAMENTAL = ["pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance"] as const;
export const PILLARS: { k: "q" | "g" | "p" | "b"; col: Pillar; label: string; short: string; say: string }[] = [
  { k: "q", col: "pillar_quality", label: "Quality", short: "Quality", say: "Steady earnings, clean accounts, cash that matches profit." },
  { k: "g", col: "pillar_growth", label: "Growth", short: "Growth", say: "How fast sales and profit have grown over 3 to 5 years." },
  { k: "p", col: "pillar_profitability", label: "Profitability", short: "Profit.", say: "Margins and returns on the money in the business." },
  { k: "b", col: "pillar_balance", label: "Balance sheet", short: "Balance", say: "Debt, interest cover and liquidity." },
];
export const NAMES: Record<BandKey | RangeKey, string> = { f: "Fundamental", t: "Technical", q: "Quality", g: "Growth", p: "Profitability", b: "Balance sheet", o: "Overall", ...PRISM_NAMES };
export const PAGE_SIZES = [5, 10, 20, 50];

/** Colour level of a score: the site's one colour rule (green 70+, orange 50 to 69, red under 50), see lib/scoreBands.ts. Colour only decorates; the model's word and the number carry the meaning. */
export const level = scoreBand;
/** The model's four band names for a score. */
export const bandName = (v: number | null) => (v == null ? null : v >= 78 ? "Strong" : v >= 62 ? "Healthy" : v >= 45 ? "Mixed" : "Watch");

/** Fundamental score = the average of the four business pillars (needs at least three); Technical = the price-trend pillar.
 *  Size buckets follow SEBI's rule: the 100 largest companies are Large, the next 150 Mid, the rest Small (ranked among the companies loaded here). */
export function withScores(rows: Row[]): Item[] {
  const rank = new Map(rows.filter((r) => (r.market_cap ?? 0) > 0 && r.price != null).sort((a, b) => (b.market_cap as number) - (a.market_cap as number)).map((r, i) => [r.symbol, i + 1]));
  return rows.map((r) => {
    const parts = FUNDAMENTAL.map((k) => r[k]).filter((v): v is number => v != null);
    const n = rank.get(r.symbol);
    return { ...r, f: parts.length >= 3 ? Math.round(parts.reduce((a, b) => a + b, 0) / parts.length) : null, t: r.pillar_technical,
      cap: n == null ? null : n <= 100 ? "Large" : n <= 250 ? "Mid" : "Small" };
  });
}

/** Why a score is missing, in plain words (for the dash tooltip and screen readers). */
export function missingReason(r: Item, key: "f" | "t" | "overall" | Pillar, locked: boolean): string {
  if (locked) return "Scores are part of the Silver plan";
  if (r.scored === false) return "Not scored yet. Open the report to score it now";
  if (key === "f") return "Needs at least 3 of the 4 business pillars, and this company has fewer";
  return "Not enough data to score";
}

// ---------- filters ----------
export type Filters = {
  caps: Cap[]; sectors: string[];
  bands: Record<BandKey, Band[]>;
  ranges: Record<RangeKey, Range>;
  labels: PrismLabel[];     // FinLit Prism rating labels (any of these)
  rated: boolean;           // only companies that have a Prism score
};
export const emptyFilters = (): Filters => ({
  caps: [], sectors: [],
  bands: { f: [], t: [], q: [], g: [], p: [], b: [] },
  ranges: Object.fromEntries(RANGE_KEYS.map((k) => [k, { min: null, max: null }])) as Filters["ranges"],
  labels: [], rated: false,
});
export const cloneFilters = (f: Filters): Filters => ({ caps: [...f.caps], sectors: [...f.sectors], bands: Object.fromEntries(BAND_KEYS.map((k) => [k, [...f.bands[k]]])) as Filters["bands"],
  ranges: Object.fromEntries(RANGE_KEYS.map((k) => [k, { ...f.ranges[k] }])) as Filters["ranges"], labels: [...f.labels], rated: f.rated });

export const inBands = (v: number | null, bands: Band[]) => !bands.length || (v != null && bands.some((b) => v >= BANDS[b].min && v <= BANDS[b].max));
export const inRange = (v: number | null, r: Range) => (r.min == null && r.max == null) || (v != null && (r.min == null || v >= r.min) && (r.max == null || v <= r.max));
const rangeValue = (r: Item, k: RangeKey) => (k === "f" ? r.f : k === "t" ? r.t : k === "o" ? r.overall : prismRangeValue(r, k) ?? null);
const bandValue = (r: Item, k: BandKey) => (k === "f" ? r.f : k === "t" ? r.t : r[PILLARS.find((x) => x.k === k)!.col]);

/** True when the company passes every filter. `skip` leaves one group out (used for the live counts beside the size and sector options). */
export function passes(r: Item, f: Filters, skip?: "caps" | "sectors"): boolean {
  if (skip !== "caps" && f.caps.length && !(r.cap && f.caps.includes(r.cap))) return false;
  if (skip !== "sectors" && f.sectors.length && !(r.sector && f.sectors.includes(r.sector))) return false;
  if (f.rated && !hasPrism(r)) return false;
  if (f.labels.length && !(isLabel(r.prism_label) && f.labels.includes(r.prism_label))) return false;
  return BAND_KEYS.every((k) => inBands(bandValue(r, k), f.bands[k])) && RANGE_KEYS.every((k) => inRange(rangeValue(r, k), f.ranges[k]));
}
export const applyFilters = (items: Item[], f: Filters) => items.filter((r) => passes(r, f));

/** Counts shown beside each size and sector option: companies that pass every other filter in the draft, so the numbers follow what you are setting. */
export function facetCounts(items: Item[], f: Filters) {
  const caps = { Large: 0, Mid: 0, Small: 0 } as Record<Cap, number>;
  for (const r of items) if (r.cap && passes(r, f, "caps")) caps[r.cap]++;
  const m = new Map<string, number>();
  for (const r of items) if (r.sector) { if (passes(r, f, "sectors")) m.set(r.sector, (m.get(r.sector) || 0) + 1); else if (!m.has(r.sector)) m.set(r.sector, 0); }
  const sectors = [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return { caps, sectors };
}

// ---------- validation ----------
export type Problems = Partial<Record<RangeKey, string>>;
/** Problems with the min-max boxes: outside 0 to 100, or a minimum above the maximum. */
export function validate(f: Filters): Problems {
  const out: Problems = {};
  for (const k of RANGE_KEYS) {
    const { min, max } = f.ranges[k];
    if ([min, max].some((v) => v != null && (!Number.isFinite(v) || v < 0 || v > 100))) out[k] = "Use numbers from 0 to 100.";
    else if (min != null && max != null && min > max) out[k] = "The minimum is above the maximum.";
  }
  return out;
}

// ---------- presets (defined only by score bands and ranges) ----------
export type Preset = { id: string; label: string; say: string; f: Band[]; t: Band[] };
export const PRESETS: Preset[] = [
  { id: "both", label: "Strong on both", say: "Fundamental 78 and above and Technical 78 and above.", f: ["high"], t: ["high"] },
  { id: "fund", label: "Strong fundamentals, weak trend", say: "Fundamental 78 and above and Technical under 45.", f: ["high"], t: ["low"] },
  { id: "trend", label: "Strong trend, weaker fundamentals", say: "Technical 78 and above and Fundamental under 78.", f: ["low", "mid"], t: ["high"] },
];
/** A preset sets the Fundamental and Technical bands and clears their min-max boxes; every other filter stays as it was. */
export function withPreset(f: Filters, p: Preset): Filters {
  const n = cloneFilters(f);
  n.bands.f = [...p.f]; n.bands.t = [...p.t];
  n.ranges.f = { min: null, max: null }; n.ranges.t = { min: null, max: null };
  return n;
}
const same = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
export const activePreset = (f: Filters) => PRESETS.find((p) => same(f.bands.f, p.f) && same(f.bands.t, p.t) && f.ranges.f.min == null && f.ranges.f.max == null && f.ranges.t.min == null && f.ranges.t.max == null)?.id ?? null;

/** Views that use the FinLit score and the Prism rating together (Gold). A preset OWNS the Prism score, its four categories, the rating labels, the
 *  "rated only" switch and the FinLit Overall range: choosing it sets those exactly (cleared where it names nothing), every other filter stays. */
export type PrismPreset = { id: string; label: string; say: string; ranges: Partial<Record<RangeKey, Range>>; labels: PrismLabel[]; rated: boolean };
const min = (n: number): Range => ({ min: n, max: null });
export const PRISM_PRESETS: PrismPreset[] = [
  { id: "bothscores", label: "FinLit and Prism both strong", say: "FinLit overall 78 or more and a Prism rating of Strong or Healthy.", ranges: { o: min(78) }, labels: ["STRONG", "HEALTHY"], rated: true },
  { id: "qualityvalue", label: "Quality at a fair valuation", say: "Prism Quality 65 or more and Prism Valuation 50 or more. Valuation is higher when the price is more modest for what the company earns.", ranges: { zq: min(65), zv: min(50) }, labels: [], rated: true },
  { id: "steady", label: "Steady and lower risk", say: "Prism Fundamentals 65 or more and Prism Risk 65 or more (a higher Risk score means lower risk).", ranges: { zf: min(65), zr: min(65) }, labels: [], rated: true },
  { id: "prismstrong", label: "Prism Strong", say: "A Prism rating of Strong (80 and above).", ranges: {}, labels: ["STRONG"], rated: true },
  { id: "differ", label: "The two scores differ", say: "FinLit overall 78 or more but a Prism rating of Average, Weak or Poor. Open the report to see why.", ranges: { o: min(78) }, labels: ["AVERAGE", "WEAK", "POOR"], rated: true },
];
const OWNED: RangeKey[] = ["o", ...PRISM_RANGE_KEYS];
const none = (): Range => ({ min: null, max: null });
export function withPrismPreset(f: Filters, p: PrismPreset): Filters {
  const n = cloneFilters(f);
  OWNED.forEach((k) => { n.ranges[k] = { ...none(), ...(p.ranges[k] || {}) }; });
  n.labels = [...p.labels]; n.rated = p.rated;
  return n;
}
export const activePrismPreset = (f: Filters) => PRISM_PRESETS.find((p) => f.rated === p.rated && same(f.labels, p.labels)
  && OWNED.every((k) => { const want = { ...none(), ...(p.ranges[k] || {}) }; return f.ranges[k].min === want.min && f.ranges[k].max === want.max; }))?.id ?? null;
/** Clearing a Prism preset again removes what it set. */
export const withoutPrismPreset = (f: Filters): Filters => withPrismPreset(f, { id: "", label: "", say: "", ranges: {}, labels: [], rated: false });

// ---------- chips ----------
export type Chip = { id: string; label: string };
const rangeText = (r: Range) => (r.min != null && r.max != null ? `${r.min} to ${r.max}` : r.min != null ? `${r.min} or more` : `${r.max} or less`);
/** One chip per active filter (one per selected sector), each removable on its own. */
export function chipsFor(f: Filters): Chip[] {
  const out: Chip[] = [];
  if (f.caps.length) out.push({ id: "caps", label: `Market cap: ${CAPS.filter((c) => f.caps.includes(c)).join(", ")}` });
  f.sectors.forEach((s) => out.push({ id: "sector:" + s, label: s }));
  BAND_KEYS.forEach((k) => { if (f.bands[k].length) out.push({ id: "band:" + k, label: `${NAMES[k]}: ${BAND_ORDER.filter((b) => f.bands[k].includes(b)).map((b) => BANDS[b].short).join(", ")}` }); });
  RANGE_KEYS.forEach((k) => { const r = f.ranges[k]; if (r.min != null || r.max != null) out.push({ id: "range:" + k, label: `${NAMES[k]}: ${rangeText(r)}` }); });
  if (f.labels.length) out.push({ id: "labels", label: `Prism rating: ${PRISM_LABELS.filter((l) => f.labels.includes(l)).map((l) => LABEL_WORD[l]).join(", ")}` });
  if (f.rated) out.push({ id: "rated", label: "Only companies rated by Prism" });
  return out;
}
export function removeChip(f: Filters, id: string): Filters {
  const n = cloneFilters(f);
  if (id === "caps") n.caps = [];
  else if (id.startsWith("sector:")) n.sectors = n.sectors.filter((s) => s !== id.slice(7));
  else if (id.startsWith("band:")) n.bands[id.slice(5) as BandKey] = [];
  else if (id.startsWith("range:")) n.ranges[id.slice(6) as RangeKey] = { min: null, max: null };
  else if (id === "labels") n.labels = [];
  else if (id === "rated") n.rated = false;
  return n;
}

// ---------- sorting and paging ----------
export type Sort = { key: SortKey; dir: 1 | -1 };
export const DEFAULT_SORT: Sort = { key: "market_cap", dir: -1 };
const sortValue = (r: Item, k: SortKey) => (k === "name" ? r.name || r.symbol : r[k]);
/** Stable sort; companies with no value for the column always go last, in either direction. */
export function sortRows(rows: Item[], s: Sort): Item[] {
  return rows.map((r, i) => ({ r, i, v: sortValue(r, s.key) })).sort((a, b) => {
    if (a.v == null && b.v == null) return a.i - b.i;
    if (a.v == null) return 1;
    if (b.v == null) return -1;
    const c = typeof a.v === "string" ? a.v.localeCompare(b.v as string) : (a.v as number) - (b.v as number);
    return c * s.dir || a.i - b.i;
  }).map((x) => x.r);
}
/** Clicking a heading: same column flips the direction, a new column starts high-to-low (A to Z for text). */
const firstDir = (key: SortKey): 1 | -1 => (key === "name" || key === "sector" ? 1 : -1);
export const nextSort = (s: Sort, key: SortKey): Sort => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : firstDir(key) });

export function pageOf<T>(rows: T[], page: number, size: number) {
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const p = Math.min(Math.max(0, page), pages - 1);
  return { page: p, pages, view: rows.slice(p * size, (p + 1) * size), from: rows.length ? p * size + 1 : 0, to: Math.min((p + 1) * size, rows.length) };
}
/** Page numbers to show: first, last, and two either side of the current one, with null for a gap. */
export function pageList(page: number, pages: number): (number | null)[] {
  const keep = new Set([0, pages - 1, page - 2, page - 1, page, page + 1, page + 2].filter((n) => n >= 0 && n < pages));
  const out: (number | null)[] = []; let prev = -1;
  [...keep].sort((a, b) => a - b).forEach((n) => { if (n - prev > 1) out.push(null); out.push(n); prev = n; });
  return out;
}

// ---------- summary ----------
export function median(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x != null).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = v.length >> 1;
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}
export function summarize(rows: Item[]) {
  return { found: rows.length, sectors: new Set(rows.map((r) => r.sector).filter(Boolean)).size,
    medF: median(rows.map((r) => r.f)), medT: median(rows.map((r) => r.t)),
    nF: rows.filter((r) => r.f != null).length, nT: rows.filter((r) => r.t != null).length,
    medZ: median(rows.map((r) => r.prism_final ?? null)), nZ: rows.filter(hasPrism).length };
}
/** Sector shares of the result: the biggest `top` sectors, the rest as "Other sectors", and companies with no sector listed. */
export function concentration(rows: Item[], top = 5): { label: string; n: number; pct: number }[] {
  if (!rows.length) return [];
  const m = new Map<string, number>(); let none = 0;
  rows.forEach((r) => (r.sector ? m.set(r.sector, (m.get(r.sector) || 0) + 1) : none++));
  const sorted = [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const out = sorted.slice(0, top).map(([label, n]) => ({ label, n }));
  const rest = sorted.slice(top).reduce((a, [, n]) => a + n, 0);
  if (rest) out.push({ label: "Other sectors", n: rest });
  if (none) out.push({ label: "Sector not listed", n: none });
  return out.map((x) => ({ ...x, pct: (x.n / rows.length) * 100 }));
}

// ---------- URL state ----------
export type State = { filters: Filters; sort: Sort; size: number; page: number };
export const SORT_KEYS: SortKey[] = ["name", "price", "market_cap", "sector", "f", "t", "overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance",
  "prism_final", "prism_fundamental", "prism_valuation", "prism_quality", "prism_risk", "prism_st_score", "prism_lt_score"];
const num = (s: string | null) => { if (s == null || s.trim() === "") return null; const n = Number(s); return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : null; };
const parseBands = (s: string | null): Band[] => BAND_ORDER.filter((b) => (s || "").split(",").includes(b));

/** Reads the address. Unknown or broken values are ignored, so a hand-edited link never breaks the page. Old links (?cap=Large&sector=X&f=high) still work. */
export function parseState(p: URLSearchParams): State {
  const f = emptyFilters();
  const caps = (p.get("cap") || "").split(",");
  f.caps = CAPS.filter((c) => caps.includes(c));
  f.sectors = [...new Set(p.getAll("sector").filter(Boolean))];
  BAND_KEYS.forEach((k) => { f.bands[k] = parseBands(p.get(k)); });
  RANGE_KEYS.forEach((k) => {
    let min = num(p.get(k + "min")), max = num(p.get(k + "max"));
    if (min != null && max != null && min > max) [min, max] = [max, min];
    f.ranges[k] = { min, max };
  });
  f.labels = (p.get("pl") || "").split(",").map(labelFromSlug).filter((l): l is PrismLabel => !!l).sort((a, b) => PRISM_LABELS.indexOf(a) - PRISM_LABELS.indexOf(b));
  f.rated = p.get("rated") === "1";
  const key = SORT_KEYS.find((k) => k === p.get("sort"));
  const sort: Sort = key ? { key, dir: p.get("dir") === "asc" ? 1 : p.get("dir") === "desc" ? -1 : firstDir(key) } : DEFAULT_SORT;
  const size = PAGE_SIZES.find((n) => n === Number(p.get("size"))) ?? 10;
  const page = Math.max(0, (Math.floor(Number(p.get("page"))) || 1) - 1);
  return { filters: f, sort, size, page };
}
export function serializeState(s: State): URLSearchParams {
  const p = new URLSearchParams(), f = s.filters;
  if (f.caps.length) p.set("cap", CAPS.filter((c) => f.caps.includes(c)).join(","));
  f.sectors.forEach((x) => p.append("sector", x));
  BAND_KEYS.forEach((k) => { if (f.bands[k].length) p.set(k, BAND_ORDER.filter((b) => f.bands[k].includes(b)).join(",")); });
  RANGE_KEYS.forEach((k) => { const r = f.ranges[k]; if (r.min != null) p.set(k + "min", String(r.min)); if (r.max != null) p.set(k + "max", String(r.max)); });
  if (f.labels.length) p.set("pl", PRISM_LABELS.filter((l) => f.labels.includes(l)).map((l) => LABEL_SLUG[l]).join(","));
  if (f.rated) p.set("rated", "1");
  if (s.sort.key !== DEFAULT_SORT.key || s.sort.dir !== DEFAULT_SORT.dir) { p.set("sort", s.sort.key); p.set("dir", s.sort.dir === 1 ? "asc" : "desc"); }
  if (s.size !== 10) p.set("size", String(s.size));
  if (s.page > 0) p.set("page", String(s.page + 1));
  return p;
}
export const filtersKey = (f: Filters) => serializeState({ filters: f, sort: DEFAULT_SORT, size: 10, page: 0 }).toString();

// ---------- CSV ----------
const cell = (s: string) => (/[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s);
const n = (v: number | null | undefined) => (v == null ? "" : String(v));
/** The filters in words, one line each, for the export header. */
export function describeFilters(f: Filters): string[] {
  const c = chipsFor(f);
  return c.length ? c.map((x) => x.label) : ["None (all companies)"];
}
/** Rows as CSV with a commented header (filters, sort, data date, what a blank means). A missing value is a blank cell, never 0.
 *  `prism` adds the FinLit Prism columns (Gold); a plan without them gets the original columns and a line saying why. */
export function toCsv(rows: Item[], o: { filters: Filters; sort: Sort; scope: "selected" | "filtered"; total: number; asOf: string | null; exportedOn: string; prism?: boolean; prismAsOf?: string | null }): string {
  const head = [
    "# FinLit Score screener export",
    `# Exported on: ${o.exportedOn}`,
    `# Scores computed on: ${o.asOf ?? "date not available"}`,
    `# Rows: ${rows.length} (${o.scope === "selected" ? "selected rows only" : "all filtered rows"}; ${o.total} companies match the filters)`,
    ...describeFilters(o.filters).map((x, i) => `# ${i === 0 ? "Filters: " : "         "}${x}`),
    `# Sorted by: ${o.sort.key} ${o.sort.dir === 1 ? "ascending" : "descending"}`,
    "# Blank cell = not available (not scored, not enough data, not rated yet, or not in your plan). It is never zero.",
    "# Fundamental = average of the four business pillars (needs 3 of 4). Technical = the technical pillar. Overall = the FinLit overall score.",
    ...(o.prism ? [`# Prism = the FinLit Prism rating, 0 to 100, with its label and status; Fundamentals, Valuation, Quality and Risk are its four parts (a higher Risk score means lower risk). Ratings as of: ${o.prismAsOf ?? "date not available"}.`,
      "# Technical short term (5 to 20 sessions) and long term (6 to 18 months) are Prism's separate price-trend readings, -100 to +100, with a descriptive word."] : ["# FinLit Prism columns are part of the Gold plan and are not in this file."]),
    "# Describes financial health and price trend from filings and prices. It is information, not a recommendation.",
  ];
  const cols = ["Symbol", "Name", "Sector", "Size", "Price (Rs)", "Market cap (Rs Cr)", "Fundamental", "Quality", "Growth", "Profitability", "Balance sheet", "Technical", "Overall",
    ...(o.prism ? ["Prism", "Prism label", "Prism status", "Prism Fundamentals", "Prism Valuation", "Prism Quality", "Prism Risk", "Technical short term", "Technical short term score", "Technical long term", "Technical long term score", "Prism rated on"] : [])];
  const lines = rows.map((r) => [csvText(r.symbol), csvText(r.name || r.symbol), csvText(r.sector || ""), r.cap ? r.cap + " cap" : "", n(r.price), n(r.market_cap), n(r.f),
    n(r.pillar_quality), n(r.pillar_growth), n(r.pillar_profitability), n(r.pillar_balance), n(r.t), n(r.overall),
    ...(o.prism ? [n(r.prism_final), csvText(r.prism_label ? LABEL_WORD[r.prism_label as PrismLabel] ?? r.prism_label : ""), csvText(r.prism_status ?? ""), n(r.prism_fundamental), n(r.prism_valuation), n(r.prism_quality), n(r.prism_risk),
      csvText(r.prism_st ?? ""), n(r.prism_st_score), csvText(r.prism_lt ?? ""), n(r.prism_lt_score), r.prism_at ?? ""] : [])].map(cell).join(","));
  return [...head, cols.join(","), ...lines].join("\r\n") + "\r\n";
}
