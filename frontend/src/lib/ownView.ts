// Pure logic of the Ownership section (docs/OWNERSHIP.md): what the page shows, worked out from the stored shareholding and the stored
// ownership insights (the output of finlit_technicals.ownership.analyse()). No React, no fetching; every rule of the handover lives here so it can be tested.
import type { Ownership } from "./api";

export type GroupKey = "promoters" | "fii" | "dii" | "public" | "government";
/** Donut and legend order. */
export const GROUPS: GroupKey[] = ["promoters", "fii", "dii", "public", "government"];
/** The four groups that get a line chart and a bar pair (Government is too small to chart: the note under the charts gives its share). */
export const CHARTED: GroupKey[] = ["promoters", "fii", "dii", "public"];
export const NAME: Record<GroupKey, string> = { promoters: "Promoters", fii: "Foreign institutions", dii: "Domestic institutions", public: "Retail & others", government: "Government" };
export const DESC: Record<GroupKey, string> = {
  promoters: "Founders and their group", fii: "Foreign funds", dii: "Indian mutual funds, insurers and banks", public: "Everyday investors and others", government: "Outside the promoter group",
};
/** The only fixed colours on the page (checked for colour-blind separation): everything else uses the design tokens. */
export const COLOR: Record<GroupKey, string> = { promoters: "#2F67C1", fii: "#D9772F", dii: "#0B7A4B", public: "#8256B8", government: "#C2387A" };

export type Tone = "supportive" | "neutral" | "watch";
export const TONE: Record<Tone, { word: string; glyph: string }> = { supportive: { word: "Supportive", glyph: "+" }, neutral: { word: "Worth knowing", glyph: "i" }, watch: { word: "Watch", glyph: "!" } };

export type InsightCard = { id: string; tone: Tone; title: string; stat: string; text: string };
export type TableRow = { key: string; label: string; description?: string; now: number | null; change_1q: number | null; change_1y: number | null; change_3y: number | null; change_5y: number | null; streak?: number; spark: (number | null)[]; spark_periods: string[] };
export type Holder = { name: string; group: string; now: number | null; year_ago: number | null };
export type OwnFacts = {
  as_of?: string; compared_with?: string | null; share_count_cr?: number | null; share_count_change_1y_pct?: number | null; promoter_pledged_pct?: number | null; locked_in_pct?: number | null;
  shareholders?: number | null; shareholders_change_1y_pct?: number | null; share_count_by_period?: Record<string, number>; top_holders?: Holder[];
};
export type PremiumState = { state: "ok" | "missing"; reason: string | null; has: { structure: boolean; holders: boolean } };
/** GET /api/stocks/SYM/ownership-insights (finlit/ownership_insights.py). */
export type OwnInsights = {
  available: boolean; symbol?: string; as_of?: string; table?: TableRow[]; facts?: OwnFacts; cards?: InsightCard[]; more?: InsightCard[]; quiet_text?: string | null;
  headline?: string[]; disclaimer?: string; rules_version?: string; premium?: PremiumState; builtAt?: string | null; stored?: boolean; reason?: string;
};

// ------------------------------------------------------------------------------------------------ formatting
/** One decimal, halves rounded away from zero the way people round (18.65 -> 18.7). */
export const r1 = (v: number): number => Math.round(v * 10 + (v >= 0 ? 1e-9 : -1e-9)) / 10;
export const pc = (v: number | null | undefined): string => (v == null ? "–" : `${r1(v).toFixed(1)}%`);
export const pc2 = (v: number | null | undefined): string => (v == null ? "–" : `${v.toFixed(2)}%`);
/** "▲ +10.8 pts" / "▼ −0.2 pts" / "no change" (under 0.05 pts is rounding). */
export const signedPts = (d: number): string => (Math.abs(d) < 0.05 ? "No change" : `${d > 0 ? "▲ +" : "▼ −"}${r1(Math.abs(d)).toFixed(1)} pts`);
/** Indian style: 50.7 lakh, 1.20 crore, 76,317. */
export const lakh = (n: number): string => (n >= 1e7 ? `${(n / 1e7).toFixed(2)} crore` : n >= 1e5 ? `${(n / 1e5).toFixed(1)} lakh` : Math.round(n).toLocaleString("en-IN"));

// ------------------------------------------------------------------------------------------------ the series
/** Quarterly share held by each group, oldest first. `null` is a filing in which the group has no figure. */
export type OwnSeries = { periods: string[]; values: Partial<Record<GroupKey, (number | null)[]>> };

/** From the stored shareholding (`/ownership`): every filing the provider has, so the year selector reaches every year. */
export function seriesFromOwnership(o: Pick<Ownership, "periods" | "series">): OwnSeries {
  const values: OwnSeries["values"] = {};
  for (const k of GROUPS) if (o.series[k]?.some((x) => x != null)) values[k] = o.series[k].map((x) => x ?? null);
  return { periods: [...o.periods], values };
}

/** From the insights table (the newest 21 filings): used when the stored shareholding is not at hand. */
export function seriesFromTable(table: TableRow[]): OwnSeries {
  const values: OwnSeries["values"] = {};
  let periods: string[] = [];
  for (const r of table) {
    if (!(GROUPS as string[]).includes(r.key)) continue;
    values[r.key as GroupKey] = [...r.spark];
    if (r.spark_periods.length > periods.length) periods = [...r.spark_periods];
  }
  return { periods, values };
}

export const groupsOf = (s: OwnSeries): GroupKey[] => GROUPS.filter((k) => s.values[k]);
export const at = (s: OwnSeries, k: GroupKey, i: number): number | null => s.values[k]?.[i] ?? null;

// ------------------------------------------------------------------------------------------------ owners today
export type Slice = { key: GroupKey; name: string; desc: string; color: string; value: number };
/** The donut and the legend for the filing at `index`: groups with a figure, in the fixed order. */
export function slicesAt(s: OwnSeries, index: number): Slice[] {
  return groupsOf(s).flatMap((key) => { const value = at(s, key, index); return value == null ? [] : [{ key, name: NAME[key], desc: DESC[key], color: COLOR[key], value }]; });
}
export const DONUT_R = 80;
/** stroke-dasharray / offset of each slice on a circle of radius 80 (a 2-unit gap between slices, as in the reference build). */
export function donutArcs(slices: Slice[]): { key: GroupKey; dash: string; offset: number }[] {
  const C = 2 * Math.PI * DONUT_R, tot = slices.reduce((a, s) => a + s.value, 0) || 1;
  let acc = 0;
  return slices.map((s) => { const len = (s.value / tot) * C, out = { key: s.key, dash: `${Math.max(len - 2, 0.8).toFixed(2)} ${C.toFixed(2)}`, offset: -acc - 1 }; acc += len; return out; });
}

// ------------------------------------------------------------------------------------------------ who bought and who sold
export const CMP_OPTIONS: { q: number; label: string; short: string }[] = [{ q: 1, label: "Last quarter", short: "1Q" }, { q: 4, label: "1 year", short: "1Y" }, { q: 12, label: "3 years", short: "3Y" }, { q: 20, label: "5 years", short: "5Y" }];
export const SHARE_RULE_PCT = 0.5;

export type MoveMode = "trade" | "issued" | "unknown";
export type MoveRow = { key: GroupKey; name: string; color: string; before: number | null; now: number | null; delta: number | null; badge: string; barBefore: number; barNow: number };
export type Moves = { mode: MoveMode; from: string; to: string; rows: MoveRow[]; note: string; shareChangePct: number | null };

/** The share-count change between two filings, in per cent: from the per-filing counts, else (the 1-year window ending at the latest filing) the facts' own 1-year figure. */
export function shareCountChange(facts: OwnFacts | undefined, from: string, to: string, useYearFigure: boolean): number | null {
  const by = facts?.share_count_by_period ?? {}, a = by[from], b = by[to];
  if (a && b) return (b / a - 1) * 100;
  return useYearFigure && facts?.share_count_change_1y_pct != null ? facts.share_count_change_1y_pct : null;
}

/** Before and after bars for `sel` against `sel - q`. "Bought" and "sold" are said only when the share count is known and did not move by 0.5% or more. */
export function movesFor(s: OwnSeries, sel: number, q: number, facts: OwnFacts | undefined, latest: number): Moves {
  const cmp = Math.max(0, sel - Math.min(q, sel)), from = s.periods[cmp], to = s.periods[sel];
  const change = shareCountChange(facts, from, to, sel === latest && sel - cmp === 4);
  const mode: MoveMode = change == null ? "unknown" : Math.abs(change) >= SHARE_RULE_PCT - 1e-9 ? "issued" : "trade";
  const keys = CHARTED.filter((k) => s.values[k]);
  const vmax = Math.max(1, ...keys.flatMap((k) => [at(s, k, sel) ?? 0, at(s, k, cmp) ?? 0])) * 1.08;
  const rows = keys.map((key) => {
    const before = at(s, key, cmp), now = at(s, key, sel), delta = before == null || now == null || cmp === sel ? null : now - before;
    const word = (up: boolean) => (mode === "trade" ? (up ? "Bought" : "Sold") : up ? "Up" : "Down");
    const badge = delta == null ? "Not filed" : Math.abs(delta) < 0.05 ? "No change" : `${delta > 0 ? "▲" : "▼"} ${word(delta > 0)} ${r1(Math.abs(delta)).toFixed(1)} pts`;
    return { key, name: NAME[key], color: COLOR[key], before, now, delta, badge, barBefore: ((before ?? 0) / vmax) * 100, barNow: ((now ?? 0) / vmax) * 100 };
  });
  const note = mode === "trade" ? "No new shares were issued in this period, so a rise means buying and a fall means selling."
    : mode === "issued" ? `The share count ${change! > 0 ? "rose" : "fell"} by ${Math.abs(change!).toFixed(1)}% in this period (${change! > 0 ? "new shares were issued" : "shares were bought back"}), so a change in share is not always buying or selling; the badges say Up or Down.`
    : `The share count for ${from} is not in the data, so a change may include new shares issued; the badges say Up or Down.`;
  return { mode, from, to, rows, note, shareChangePct: change };
}

// ------------------------------------------------------------------------------------------------ the line charts
export const WINDOWS: { w: number; label: string }[] = [{ w: 4, label: "1Y" }, { w: 12, label: "3Y" }, { w: 20, label: "5Y" }];
export type ChartPoint = { i: number; period: string; value: number | null };
export type ChartModel = {
  key: GroupKey; name: string; color: string; points: ChartPoint[]; first: ChartPoint | null; last: ChartPoint | null; change: number | null;
  lo: number; hi: number; step: number; ticks: { value: number; top: number }[]; path: string; yOf: (v: number) => number; xOf: (n: number) => number;
};

/** The y-scale of one chart: lowest to highest value in the window, widened to at least 4 pts around the middle, plus 8% padding; labels every 1, 2, 5 or 10 (the first step that gives at most four). */
export function yScale(values: number[]): { lo: number; hi: number; step: number; ticks: number[] } {
  let lo = Math.min(...values), hi = Math.max(...values);
  if (hi - lo < 4) { const m = (hi + lo) / 2; lo = m - 2; hi = m + 2; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const step = [1, 2, 5, 10].find((t) => (hi - lo) / t <= 4) ?? 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) ticks.push(t);
  return { lo, hi, step, ticks };
}

/** The filings in a window ending at the newest one: 5, 13 or 21 (fewer when the history is shorter). */
export function windowIndexes(n: number, w: number): number[] {
  const last = n - 1, win = Math.min(w, last);
  return Array.from({ length: win + 1 }, (_, k) => last - win + k);
}

export function chartFor(s: OwnSeries, key: GroupKey, w: number): ChartModel | null {
  const idx = windowIndexes(s.periods.length, w);
  const points = idx.map((i) => ({ i, period: s.periods[i], value: at(s, key, i) }));
  const have = points.filter((p) => p.value != null) as (ChartPoint & { value: number })[];
  if (have.length < 2) return null;
  const { lo, hi, step, ticks } = yScale(have.map((p) => p.value));
  const yOf = (v: number) => (1 - (v - lo) / (hi - lo)) * 100;
  const n = Math.max(idx.length - 1, 1), xOf = (k: number) => (k / n) * 100;
  const path = points.map((p, k) => [p, k] as const).filter(([p]) => p.value != null).map(([p, k], j) => `${j ? "L" : "M"}${(xOf(k) * 10).toFixed(1)} ${(yOf(p.value as number) * 10).toFixed(1)}`).join(" ");
  const first = have[0], last = have[have.length - 1];
  return { key, name: NAME[key], color: COLOR[key], points, first, last, change: last.value - first.value, lo, hi, step, ticks: ticks.map((value) => ({ value, top: yOf(value) })), path, yOf, xOf };
}

/** "Indian funds have held more than foreign funds since Mar 2025." from the newest crossing of the two lines (null when they never cross). */
export function crossoverNote(s: OwnSeries): string | null {
  let cross: { i: number; dii: boolean } | null = null;
  for (let i = 1; i < s.periods.length; i++) {
    const [f0, d0, f1, d1] = [at(s, "fii", i - 1), at(s, "dii", i - 1), at(s, "fii", i), at(s, "dii", i)];
    if (f0 == null || d0 == null || f1 == null || d1 == null) continue;
    if ((d0 - f0) * (d1 - f1) < 0) cross = { i, dii: d1 - f1 > 0 };
  }
  return cross ? `${cross.dii ? "Indian funds have held more than foreign funds since" : "Foreign funds have held more than Indian funds since"} ${s.periods[cross.i]}.` : null;
}

export function chartNote(s: OwnSeries): string {
  const gov = at(s, "government", s.periods.length - 1);
  return ["Each chart has its own scale, at least 4 pts tall, so small moves stay small.", gov != null ? `Government holds ${pc(gov)}.` : "", crossoverNote(s) ?? ""].filter(Boolean).join(" ");
}

/** Spoken summary of one chart. */
export const chartLabel = (m: ChartModel): string => `${m.name} went from ${pc(m.first?.value)} in ${m.first?.period} to ${pc(m.last?.value)} in ${m.last?.period}`;

// ------------------------------------------------------------------------------------------------ the numbers and the CSV
export const fmt2 = (v: number | null): string => (v == null ? "–" : `${v.toFixed(2)}%`);

export function csvText(s: OwnSeries): string {
  const keys = groupsOf(s);
  return [["Filing", ...keys.map((k) => NAME[k])].join(","), ...s.periods.map((p, i) => [p, ...keys.map((k) => at(s, k, i) ?? "")].join(","))].join("\n");
}

// ------------------------------------------------------------------------------------------------ also from the filing, named holders
export type FactItem = { label: string; value: string; note: string };
/** The four small cards. Each says why when its number is not in the data. */
export function factItems(f: OwnFacts | undefined, why: string | null): FactItem[] {
  const none = why ?? "Not in the data";
  const holders = f?.shareholders, pledge = f?.promoter_pledged_pct, shares = f?.share_count_cr, lock = f?.locked_in_pct, chg = f?.share_count_change_1y_pct, hch = f?.shareholders_change_1y_pct;
  return [
    { label: "Shareholders", value: holders ? lakh(holders) : "–", note: holders ? (hch == null ? "" : `${hch > 0 ? "+" : hch < 0 ? "−" : ""}${Math.abs(Math.round(hch))}% in a year`) : none },
    { label: "Promoter shares pledged", value: pledge == null ? "–" : `${r1(pledge).toFixed(1)}%`, note: pledge == null ? none : pledge > 0 ? "of promoters’ shares" : "None pledged" },
    { label: "Shares outstanding", value: shares ? `${Math.round(shares).toLocaleString("en-IN")} crore` : "–", note: shares ? (chg == null ? "" : Math.abs(chg) < SHARE_RULE_PCT ? "Unchanged in a year" : `${chg > 0 ? "+" : "−"}${Math.abs(chg).toFixed(1)}% in a year`) : none },
    { label: "Shares under lock-in", value: lock == null ? "–" : `${r1(lock).toFixed(1)}%`, note: lock == null ? none : lock > 0 ? "cannot be sold yet" : "No lock-in" },
  ];
}
