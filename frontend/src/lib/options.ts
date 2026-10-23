// Option chain (Gold): the shapes /api/options sends and the small pure helpers the page formats them with. Every figure (PCR, max pain,
// OI change, build-up, ATM, ITM) is worked out by the server (backend/finlit/options.py); nothing here recomputes or rounds it differently.
import { MINUS, nf } from "./format";

export type Buildup = "long_buildup" | "short_buildup" | "short_covering" | "long_unwinding";
export type Side = {
  securityId: number | null; oi: number | null; prevOi: number | null; oiChange: number | null; oiChangePct: number | null;
  volume: number | null; prevVolume: number | null; iv: number | null; ltp: number | null; prevClose: number | null; change: number | null; changePct: number | null;
  avgPrice: number | null; bid: number | null; bidQty: number | null; ask: number | null; askQty: number | null;
  delta: number | null; gamma: number | null; theta: number | null; vega: number | null; buildup: Buildup | null;
};
export type Row = { strike: number; ce: Side | null; pe: Side | null; atm: boolean; ceItm: boolean; peItm: boolean };
export type Totals = { strikes: number; oi: number | null; oiChange: number | null; volume: number | null; prevOi: number | null };
export type Underlying = { key: string; name: string; kind: "index" | "stock"; segment: string; securityId: number; exchange: string };
export type StockUnderlying = { key: string; name: string; securityId: number; lotSize: number | null };
export type Underlyings = { indices: Underlying[]; stocks: StockUnderlying[]; connected: boolean };
export type Expiries = { underlying: Underlying; expiries: string[]; asOf: string; state: string };
export type Chain = {
  underlying: Underlying; expiry: string; daysToExpiry: number; spot: number | null; atm: number | null; rows: Row[];
  summary: { pcrOi: number | null; pcrVolume: number | null; maxPain: { strike: number; payout: number } | null; totals: { ce: Totals; pe: Totals }; strikes: number; missing: Record<string, number> };
  maxPainCurve: { strike: number; payout: number }[]; notes: string[];
  lotSize: number | null; lotSource: string | null; lotMixed: boolean;
  asOf: string; ageSeconds: number; state: "fresh" | "stale" | "refreshing"; marketOpen: boolean; nextOpen: string | null; refreshSeconds: number;
};
export type Unit = "units" | "lots";

/** Build-up names in words, and the two-letter tag the table shows (the full name is its tooltip and is in the legend). */
export const BUILDUP: Record<Buildup, { label: string; tag: string; how: string }> = {
  long_buildup: { label: "Long build-up", tag: "LB", how: "price up, OI up" },
  short_buildup: { label: "Short build-up", tag: "SB", how: "price down, OI up" },
  short_covering: { label: "Short covering", tag: "SC", how: "price up, OI down" },
  long_unwinding: { label: "Long unwinding", tag: "LU", how: "price down, OI down" },
};

/** A strike as the exchange lists it: 25650, 1422.5, 10.25 (never trailing zeros). */
export const strikeText = (k: number) => k.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

/** A price in rupees with two decimals; unknown is a dash, never 0. */
export const price = (v: number | null | undefined) => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(v, 2));

/** A signed change: +1.25 / −0.40 / 0.00. */
export const signedNum = (v: number | null | undefined, d = 2) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d));

/** Open interest or volume in units (as the exchange reports it) or in lots (units ÷ lot size). A lot count that is not whole is shown
 *  with two decimals rather than rounded, so the conversion never hides a mismatch. */
export function count(v: number | null | undefined, unit: Unit = "units", lot: number | null = null, signed = false): string {
  if (v == null) return "—";
  const x = unit === "lots" && lot ? v / lot : v;
  const whole = Number.isInteger(x);
  const body = nf(x, whole ? 0 : 2);
  return (x < 0 ? MINUS : signed && x > 0 ? "+" : "") + body;
}

/** Compact form for chart axes and tiles: 37.9 L, 1.2 Cr (Indian lakh and crore). */
export function compact(v: number | null | undefined): string {
  if (v == null) return "—";
  const a = Math.abs(v), s = v < 0 ? MINUS : "";
  if (a >= 1e7) return s + nf(a / 1e7, 2) + " Cr";
  if (a >= 1e5) return s + nf(a / 1e5, 2) + " L";
  if (a >= 1e3) return s + nf(a / 1e3, 1) + " K";
  return s + nf(a, 0);
}

/** The rows within `n` strikes either side of the ATM strike (all of them when n is 0 or there is no ATM). */
export function around(rows: Row[], atm: number | null, n: number): Row[] {
  if (!n || atm == null) return rows;
  const i = rows.findIndex((r) => r.strike === atm);
  if (i < 0) return rows;
  return rows.slice(Math.max(0, i - n), i + n + 1);
}

/** Search the underlyings: an exact key first, then keys and names that start with the text, then names that contain it. */
export function matchUnderlyings<T extends { key: string; name: string }>(list: T[], q: string, limit = 12): T[] {
  const t = q.trim().toUpperCase();
  if (!t) return list.slice(0, limit);
  const exact = list.filter((u) => u.key === t);
  const starts = list.filter((u) => !exact.includes(u) && (u.key.startsWith(t) || u.name.toUpperCase().startsWith(t)));
  const has = list.filter((u) => !exact.includes(u) && !starts.includes(u) && (u.key.includes(t) || u.name.toUpperCase().includes(t)));
  return [...exact, ...starts, ...has].slice(0, limit);
}

/** "23 Oct 2026, 15:29:58 IST" from the server's +05:30 timestamp, whatever the reader's own time zone. */
export function istTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) + " IST";
}

/** How old the data is, in words: "12 s", "4 min", "3 h", "2 days". */
export function age(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h`;
  const d = Math.floor(seconds / 86400);
  return `${d} day${d === 1 ? "" : "s"}`;
}

/** Nice round steps for a bar chart's value axis, from 0 (or the most negative value) up to the largest. */
export function ticks(min: number, max: number, want = 4): number[] {
  const lo = Math.min(0, min), hi = Math.max(0, max);
  if (hi === lo) return [0];
  const raw = (hi - lo) / want, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.round(v / step) * step);
  if (out[out.length - 1] < hi) out.push(out[out.length - 1] + step);
  return out;
}
