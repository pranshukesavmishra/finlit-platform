// FII / DII page maths: pure functions over the Flows payload (ranges, cumulative lines, moving averages, percentile of a day, streak
// history, absorption of selling, calendar grids, monthly tables, plain-language summary, CSV). Nothing here estimates a missing figure:
// a null stays null, and every function says what it did with gaps. Tested in flowsMath.test.ts.
import type { Flows, FlowDay, Period } from "./flows";
import { MINUS, dateIN } from "./format";

export type SideKey = "fii" | "dii";
export type Pt = [string, number];
export const RANGES = [["1M", 1], ["3M", 3], ["6M", 6], ["1Y", 12], ["5Y", 60], ["MAX", 0]] as const;
export type RangeKey = (typeof RANGES)[number][0];
export const isRange = (s: string | null): s is RangeKey => RANGES.some((r) => r[0] === s);

export const netOf = (d: FlowDay, s: SideKey): number | null => (s === "fii" ? d.fii.net : d.dii ? d.dii.net : null);
export const combined = (d: FlowDay): number | null => (d.fii.net != null && d.dii?.net != null ? d.fii.net + d.dii.net : null);
const sumOf = (a: number[]) => a.reduce((x, y) => x + y, 0);
const day = (iso: string) => Date.parse(iso + "T00:00:00Z");
const isoOf = (t: number) => new Date(t).toISOString().slice(0, 10);

/** How much DII data there is: every session, only some, or none (some deployments cannot obtain it). */
export function diiState(f: Pick<Flows, "days" | "coverage">): "full" | "partial" | "none" {
  const n = f.days.filter((d) => d.dii?.net != null).length;
  return n === 0 ? "none" : n === f.days.length ? "full" : "partial";
}

/** Why a DII square or figure is empty: the day is before the official DII report begins ("unpublished"), or the report should have a figure and has none ("missing"). */
export const diiGap = (d: string, publishedFrom: string | null | undefined): "unpublished" | "missing" => (publishedFrom && d < publishedFrom ? "unpublished" : "missing");

/** The sessions where FII and DII both exist, with the dates they run over and their totals. FII is also given over exactly those sessions, so the two are
 *  compared like for like; the whole-range FII total is a different period. Null when no session has both. */
export function commonSpan(days: FlowDay[]): { from: string; to: string; n: number; fii: number; dii: number; overall: number } | null {
  const w = days.filter((d) => d.fii.net != null && d.dii?.net != null);
  if (!w.length) return null;
  const fii = sumOf(w.map((d) => d.fii.net!)), dii = sumOf(w.map((d) => d.dii!.net!));
  return { from: w[0].d, to: w[w.length - 1].d, n: w.length, fii, dii, overall: fii + dii };
}

/** Sessions inside the last `months` calendar months of the data (0 = all). */
export function sinceMonths<T extends { d: string }>(rows: T[], months: number): T[] {
  if (!rows.length || !months) return rows;
  const e = new Date(day(rows[rows.length - 1].d)); e.setUTCMonth(e.getUTCMonth() - months);
  const cut = isoOf(e.getTime());
  return rows.filter((r) => r.d > cut);
}
export const rangeRows = <T extends { d: string }>(rows: T[], key: RangeKey): T[] => sinceMonths(rows, RANGES.find((r) => r[0] === key)![1]);

/** Running total of daily net from the first session given. "all" adds both sides and only counts sessions where both exist. A session with
 *  no figure for that side adds nothing and is left off the line (the line never drops to zero for lack of data). */
export function cumulative(days: FlowDay[], s: SideKey | "all"): Pt[] {
  let run = 0; const out: Pt[] = [];
  for (const d of days) {
    const v = s === "all" ? combined(d) : netOf(d, s);
    if (v == null) continue;
    run += v; out.push([d.d, Math.round(run * 100) / 100]);
  }
  return out;
}

/** Trailing n-session average; null until n real values are in the window (a null session breaks it). */
export function movingAverage(vals: (number | null)[], n: number): (number | null)[] {
  const out: (number | null)[] = []; let sum = 0, cnt = 0;
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i]; if (v != null) { sum += v; cnt++; }
    if (i >= n) { const o = vals[i - n]; if (o != null) { sum -= o; cnt--; } }
    out.push(i >= n - 1 && cnt === n ? sum / n : null);
  }
  return out;
}

/** Where a day's net sits among all sessions of that side: for a selling day the share of sessions with less selling (or any buying), for a
 *  buying day the share with less buying. Null for a flat day or no data. */
export function percentileOf(days: FlowDay[], s: SideKey, value: number | null): { pct: number; n: number } | null {
  if (value == null || value === 0) return null;
  const all = days.map((d) => netOf(d, s)).filter((v): v is number => v != null);
  if (all.length < 2) return null;
  const below = all.filter((v) => (value < 0 ? v > value : v < value)).length;
  return { pct: Math.round((below / all.length) * 1000) / 10, n: all.length };
}

export type Run = { side: "buying" | "selling"; days: number; from: string; to: string; sum: number; touchesStart: boolean; current: boolean };
/** Every run of consecutive same-direction sessions. A flat or missing session ends a run. */
export function runs(days: FlowDay[], s: SideKey): Run[] {
  const out: Run[] = []; let cur: Run | null = null;
  days.forEach((d, i) => {
    const v = netOf(d, s), side = v == null || v === 0 ? null : v > 0 ? "buying" : "selling";
    if (side && cur && cur.side === side) { cur.days++; cur.to = d.d; cur.sum += v!; }
    else {
      if (cur) out.push(cur);
      cur = side ? { side, days: 1, from: d.d, to: d.d, sum: v!, touchesStart: i === 0, current: false } : null;
    }
  });
  if (cur) { (cur as Run).current = true; out.push(cur); }
  out.forEach((r) => (r.sum = Math.round(r.sum * 100) / 100));
  return out;
}
/** The longest runs of one direction (ties: the more recent first). */
export const topRuns = (days: FlowDay[], s: SideKey, side: "buying" | "selling", n = 5): Run[] =>
  runs(days, s).filter((r) => r.side === side).sort((a, b) => b.days - a.days || b.to.localeCompare(a.to)).slice(0, n);

export type Absorb = { sessions: number; sellDays: number; fiiSold: number; diiNetOnThoseDays: number; ratio: number | null; diiBoughtDays: number };
/** When FII sold, how much DII bought: over the last n sessions where both are published. ratio = DII net / FII selling on FII-selling days. */
export function absorption(days: FlowDay[], n: number): Absorb | null {
  const both = days.filter((d) => d.fii.net != null && d.dii?.net != null).slice(-n);
  if (!both.length) return null;
  const sells = both.filter((d) => d.fii.net! < 0);
  const fiiSold = -sumOf(sells.map((d) => d.fii.net!)), dii = sumOf(sells.map((d) => d.dii!.net!));
  return { sessions: both.length, sellDays: sells.length, fiiSold: Math.round(fiiSold), diiNetOnThoseDays: Math.round(dii), ratio: fiiSold > 0 ? dii / fiiSold : null, diiBoughtDays: sells.filter((d) => d.dii!.net! > 0).length };
}

// ------------------------------------------------------------------------------------------------------------- calendar
export type Cell = { d: string; col: number; row: number; v: number | null };
export type Cal = { cells: Cell[]; cols: number; months: { col: number; label: string }[]; scale: number };
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** GitHub-style grid: columns are weeks (Monday first), rows are Monday to Friday. Weekend sessions are not drawn (they stay in the totals). */
export function calendar(days: FlowDay[], s: SideKey, weeks = 53): Cal {
  if (!days.length) return { cells: [], cols: 0, months: [], scale: 1 };
  const end = day(days[days.length - 1].d), wd = (new Date(end).getUTCDay() + 6) % 7;
  const start = end - wd * 864e5 - (weeks - 1) * 7 * 864e5;
  const cells: Cell[] = [], months: Cal["months"] = []; let lastM = -1;
  for (const d of days) {
    const t = day(d.d); if (t < start) continue;
    const row = (new Date(t).getUTCDay() + 6) % 7; if (row > 4) continue;
    const col = Math.floor((t - start) / (7 * 864e5)); cells.push({ d: d.d, col, row, v: netOf(d, s) });
    const m = new Date(t).getUTCMonth(); if (m !== lastM && row <= 4) { if (!months.length || col - months[months.length - 1].col >= 3) months.push({ col, label: MON[m] }); lastM = m; }
  }
  const mags = cells.map((c) => (c.v == null ? 0 : Math.abs(c.v))).filter((v) => v > 0).sort((a, b) => a - b);
  const scale = mags.length ? mags[Math.min(mags.length - 1, Math.floor(mags.length * 0.92))] : 1;
  return { cells, cols: weeks, months, scale };
}
/** -4..4: sign is direction, size is how big against the scale (the 92nd percentile of that side's calendar). 0 = nothing/flat/unknown. */
export function level(v: number | null, scale: number): number {
  if (v == null || v === 0 || scale <= 0) return 0;
  const k = Math.max(1, Math.ceil(Math.min(1, Math.abs(v) / scale) * 4));
  return v > 0 ? k : -k;
}
/** Total of a side over the last `months` calendar months of the data (for DII: over the sessions that have it; see commonSpan for the period). */
export function totalSince(days: FlowDay[], s: SideKey, months: number): number | null {
  const v = sinceMonths(days, months).map((d) => netOf(d, s)).filter((x): x is number => x != null);
  return v.length ? Math.round(sumOf(v)) : null;
}

// ------------------------------------------------------------------------------------------------------------- monthly table
export type MonthGrid = { years: string[]; cell: (y: string, m: number) => number | null; total: (y: string) => number | null; maxAbs: number };
export function monthGrid(f: Pick<Flows, "monthly" | "yearly" | "days">, s: SideKey): MonthGrid {
  const mp = new Map<string, number | null>(), yr = new Map<string, number | null>();
  const sumBy = new Map<string, { v: number; any: boolean }>();
  if (f.monthly.length) f.monthly.forEach((r) => mp.set(r.m, r[s]));
  else for (const d of f.days) { const v = netOf(d, s), k = d.d.slice(0, 7), e = sumBy.get(k) || { v: 0, any: false }; if (v != null) { e.v += v; e.any = true; } sumBy.set(k, e); }
  sumBy.forEach((e, k) => mp.set(k, e.any ? Math.round(e.v) : null));
  const ys = new Map<string, { v: number; any: boolean }>();
  if (f.yearly.length) f.yearly.forEach((r) => yr.set(r.y, r[s]));
  else mp.forEach((v, k) => { const y = k.slice(0, 4), e = ys.get(y) || { v: 0, any: false }; if (v != null) { e.v += v; e.any = true; } ys.set(y, e); });
  ys.forEach((e, y) => yr.set(y, e.any ? Math.round(e.v) : null));
  const years = [...new Set([...mp.keys()].map((k) => k.slice(0, 4)))].sort().reverse();
  const cell = (y: string, m: number) => mp.get(`${y}-${String(m + 1).padStart(2, "0")}`) ?? null;
  const vals = [...mp.values()].filter((v): v is number => v != null).map(Math.abs).sort((a, b) => a - b);
  return { years, cell, total: (y) => yr.get(y) ?? null, maxAbs: vals.length ? vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.95))] : 1 };
}

// ------------------------------------------------------------------------------------------------------------- split, periods, words
export type Split = { left: { label: string; pct: number; side: "buying" | "selling" }; right: { label: string; pct: number; side: "buying" | "selling" } } | null;
/** The two institutions' share of the day's net activity by size. "FII selling 54% / 46% DII support" when FII sold and DII bought. */
export function splitOf(l: Flows["latest"]): Split {
  if (!l || l.fii.net == null || l.dii?.net == null) return null;
  const a = Math.abs(l.fii.net), b = Math.abs(l.dii.net), t = a + b; if (t === 0) return null;
  const fs = l.fii.net < 0 ? "selling" : "buying", ds = l.dii.net < 0 ? "selling" : "buying";
  const fl = `FII ${l.fii.net === 0 ? "flat" : fs}`, dl = fs === "selling" && ds === "buying" ? "DII support" : `DII ${l.dii.net === 0 ? "flat" : ds}`;
  const fp = Math.round((a / t) * 100);
  return { left: { label: fl, pct: fp, side: fs }, right: { label: dl, pct: 100 - fp, side: ds } };
}
export const perDay = (p: Period, which: "fii" | "dii"): number | null => {
  const v = which === "fii" ? p.fii : p.diiNet; return v == null || !p.days ? null : v / p.days;
};
export function ageLabel(latest: string, today: string): string {
  const n = Math.round((day(today) - day(latest)) / 864e5);
  return n <= 0 ? "today" : n === 1 ? "yesterday" : `${n} days ago`;
}
export function corrWords(r: number | null): string {
  if (r == null) return "not enough data";
  const a = Math.abs(r), w = a < 0.1 ? "almost no" : a < 0.3 ? "a weak" : a < 0.5 ? "a moderate" : a < 0.7 ? "a fairly strong" : "a strong";
  return a < 0.1 ? "almost no relationship" : `${w} ${r > 0 ? "positive" : "negative"} relationship`;
}
export function pearson(a: number[], b: number[]): number | null {
  const n = Math.min(a.length, b.length); if (n < 10) return null;
  const ma = sumOf(a.slice(0, n)) / n, mb = sumOf(b.slice(0, n)) / n; let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; }
  return saa && sbb ? sab / Math.sqrt(saa * sbb) : null;
}
/** Correlation of one side's daily net with the index's same-day % move, over the sessions given. Null when the index series is missing. */
export function indexCorrelation(days: FlowDay[], index: { d: string; close: number }[] | null | undefined, s: SideKey): number | null {
  if (!index?.length) return null;
  const cl = new Map(index.map((p, i) => [p.d, i])); const a: number[] = [], b: number[] = [];
  for (const d of days) { const i = cl.get(d.d), v = netOf(d, s); if (i == null || i === 0 || v == null) continue; a.push(v); b.push(index[i].close / index[i - 1].close - 1); }
  return pearson(a, b);
}

// ------------------------------------------------------------------------------------------------------------- table + CSV
export type SortKey = "d" | "fii" | "dii" | "all";
export function filterDays(days: FlowDay[], q: string): FlowDay[] {
  const toks = q.toLowerCase().split(/\s+/).filter(Boolean); if (!toks.length) return days;
  return days.filter((d) => { const t = new Date(day(d.d)), hay = `${d.d} ${t.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })} ${MON[t.getUTCMonth()]}`.toLowerCase(); return toks.every((k) => hay.includes(k)); });
}
export function sortDays(days: FlowDay[], key: SortKey, asc: boolean): FlowDay[] {
  const val = (d: FlowDay) => (key === "d" ? day(d.d) : key === "all" ? combined(d) : netOf(d, key));
  const dir = asc ? 1 : -1;
  return [...days].sort((x, y) => { const a = val(x), b = val(y); if (a == null && b == null) return 0; if (a == null) return 1; if (b == null) return -1; return (a - b) * dir; });
}
export function toCsv(days: FlowDay[]): string {
  const c = (v: number | null | undefined) => (v == null ? "" : String(v));
  const rows = days.map((d) => [d.d, c(d.fii.buy), c(d.fii.sell), c(d.fii.net), c(d.dii?.buy), c(d.dii?.sell), c(d.dii?.net), c(combined(d))].join(","));
  return ["Date,FII buy (Rs crore),FII sell (Rs crore),FII net (Rs crore),DII buy (Rs crore),DII sell (Rs crore),DII net (Rs crore),Combined net (Rs crore)", ...rows].join("\n") + "\n";
}

// ------------------------------------------------------------------------------------------------------------- plain-language summary
/** 509032 -> "5,09,032" (Indian grouping, whole rupees crore, no sign). */
export const grp = (v: number, d = 0) => Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
/** "−₹5,09,032 Cr" / "+₹1,200 Cr"; null shows a dash. */
export const inr = (v: number | null | undefined, o: { sign?: boolean; d?: number; unit?: string } = {}) =>
  v == null ? "—" : `${v < 0 ? MINUS : o.sign && v > 0 ? "+" : ""}₹${grp(v, o.d ?? 0)}${o.unit === "" ? "" : " " + (o.unit ?? "Cr")}`;
const money = (v: number) => `₹${grp(v)} crore`;
const verb = (v: number, pos: string, neg: string) => (v > 0 ? pos : neg);
/** Rule-based readings of what the figures say. Describes the past only: no advice, no forecast. Without DII data it speaks of FII only. */
export function summarize(f: Flows): string[] {
  const out: string[] = [], l = f.latest, st = diiState(f);
  if (l && l.fii.net != null) {
    const when = dateIN(l.d, { day: "numeric", month: "short", year: "numeric" });
    let s = `On ${when}, foreign portfolio investors (FII/FPI) were net ${verb(l.fii.net, "buyers", "sellers")} of ${money(l.fii.net)} in the cash market`;
    if (l.dii?.net != null) {
      s += `, while domestic institutions (DII) were net ${verb(l.dii.net, "buyers", "sellers")} of ${money(l.dii.net)}`;
      if (l.fii.net < 0 && l.dii.net > 0) s += l.dii.net >= -l.fii.net ? ", which more than offset the foreign selling" : `, which offset ${Math.round((l.dii.net / -l.fii.net) * 100)}% of the foreign selling`;
      else if (l.fii.net > 0 && l.dii.net < 0) s += `, so the two sides took opposite positions`;
    }
    out.push(s + ".");
  }
  const sf = f.streaks.fii, sd = f.streaks.dii;
  if (sf && sf.side !== "flat" && sf.days > 0) {
    let s = `FIIs have been net ${sf.side} for ${sf.days} session${sf.days === 1 ? "" : "s"} in a row (${money(sf.sum)} in total)`;
    if (sd && sd.side !== "flat" && sd.days > 0) s += `; DIIs have been net ${sd.side} for ${sd.days}`;
    out.push(s + ".");
  }
  if (f.last30.fii != null) {
    let s = `Over the last ${f.last30.days} sessions FIIs were net ${verb(f.last30.fii, "buyers", "sellers")} of ${money(f.last30.fii)}`;
    if (f.last30.dii != null) s += ` and DIIs net ${verb(f.last30.dii, "buyers", "sellers")} of ${money(f.last30.dii)}`;
    out.push(s + ".");
  }
  if (l?.fii.net) {
    const p = percentileOf(f.days, "fii", l.fii.net);
    if (p) out.push(`The latest FII ${l.fii.net < 0 ? "selling" : "buying"} was bigger than ${p.pct.toFixed(0)}% of the ${p.n.toLocaleString("en-IN")} sessions in our data.`);
  }
  if (st !== "none") {
    const a = absorption(f.days, 90);
    if (a && a.ratio != null && a.sellDays >= 5) out.push(`On the ${a.sellDays} days in the last ${a.sessions} sessions when FIIs sold, DIIs were net buyers on ${a.diiBoughtDays} of them and bought ${Math.round(a.ratio * 100)}% as much as the FIIs sold.`);
  }
  const fy = f.periods.find((p) => p.key === "fy" || /financial year/i.test(p.label));
  if (fy && fy.fii != null) out.push(`For ${fy.label.toLowerCase()} (${fy.days} sessions) FIIs are net ${verb(fy.fii, "buyers", "sellers")} of ${money(fy.fii)}${fy.diiNet != null ? ` and DIIs net ${verb(fy.diiNet, "buyers", "sellers")} of ${money(fy.diiNet)}` : ""}.`);
  const c = f.correlation;
  if (c && c.fiiVsIndex != null) out.push(`Across ${c.days.toLocaleString("en-IN")} sessions, daily FII flow and the ${c.label} have had ${corrWords(c.fiiVsIndex)} (${c.fiiVsIndex.toFixed(2).replace("-", MINUS)}). Moving together does not mean one causes the other.`);
  if (st === "none") out.push("DII figures are not available from the sources we can use, so this reading covers FII/FPI flows only.");
  return out;
}
