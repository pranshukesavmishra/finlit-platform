/** EPS calculator maths: earnings per share, P/E, a future-EPS and price scenario, PEG and the growth a target price needs.
 *  Units: profit and dividends in ₹ crore, shares in crore, so profit ÷ shares is ₹ per share; rates in percent; prices in ₹.
 *  Nothing here rounds: rounding (round2) is for display only, so a displayed price is never built from a displayed EPS.
 *  Every result is a scenario from the inputs given, not a forecast. */

export const MINUS = "−";
export const LIMITS = { growthMin: -50, growthMax: 100, peMax: 200, yearsMin: 1, yearsMax: 30, peMin: 0 } as const;

/** "1,23,456.5" or "₹ 2,000" -> number; empty or junk -> NaN. */
export const parseNum = (s: string) => { const t = s.replace(/[,\s₹%x×]/g, ""); return t === "" || !/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t) ? NaN : Number(t); };

/** Round half away from zero to 2 decimals, correcting binary noise (1.005 -> 1.01). */
export const round2 = (x: number) => (Number.isFinite(x) ? Math.sign(x) * Math.round(Math.abs(x) * 100 * (1 + Number.EPSILON)) / 100 : x);
export const fix2 = (x: number) => { const r = round2(x); return (Object.is(r, -0) ? 0 : r).toFixed(2); };
/** Signed percent for display: "+17.49%", "−3.20%", "0.00%". */
export const pctText = (x: number, signed = true) => { const r = round2(x); return (r > 0 && signed ? "+" : r < 0 ? MINUS : "") + Math.abs(r).toFixed(2) + "%"; };

/** EPS = (net profit − preference dividends) ÷ weighted average shares. Null when shares are not a positive number. */
export function eps(netProfit: number, prefDividends: number, shares: number): number | null {
  if (![netProfit, prefDividends, shares].every(Number.isFinite) || shares <= 0) return null;
  return (netProfit - prefDividends) / shares;
}

export type NotMeaningful = { value: null; reason: string };
/** Current P/E = price ÷ EPS. Not meaningful for a loss or zero EPS (a negative multiple says nothing) or a price that is not positive. */
export function pe(price: number, epsValue: number | null): { value: number; reason?: undefined } | NotMeaningful {
  if (epsValue == null || !Number.isFinite(epsValue)) return { value: null, reason: "EPS could not be worked out from the inputs." };
  if (!Number.isFinite(price) || price <= 0) return { value: null, reason: "The share price must be above zero." };
  if (epsValue < 0) return { value: null, reason: "EPS is negative (a loss per share), so a P/E ratio is not meaningful." };
  if (epsValue === 0) return { value: null, reason: "EPS is zero, so price ÷ EPS is undefined." };
  return { value: price / epsValue };
}

/** Future EPS = current EPS × (1 + g)^n, g in percent. */
export const futureEps = (epsNow: number, growthPct: number, years: number) => epsNow * Math.pow(1 + growthPct / 100, years);
/** Implied future price = future EPS × target P/E. */
export const futurePrice = (epsFuture: number, targetPe: number) => epsFuture * targetPe;
/** Potential price return, percent = (future price ÷ current price − 1) × 100. */
export const priceReturn = (future: number, current: number) => (future / current - 1) * 100;

export type Case = { growth: number; targetPe: number };
export type Projection = { eps: number; price: number; returnPct: number };
/** A scenario from today's EPS and price. Null unless EPS > 0, price > 0, growth and multiple within limits and years a whole number in range. */
export function project(epsNow: number | null, price: number, c: Case, years: number): Projection | null {
  if (epsNow == null || !(epsNow > 0) || !(price > 0) || !checkCase(c, years).ok) return null;
  const e = futureEps(epsNow, c.growth, years), p = futurePrice(e, c.targetPe);
  return { eps: e, price: p, returnPct: priceReturn(p, price) };
}

export function checkCase(c: Case, years: number): { ok: boolean; growth?: string; targetPe?: string; years?: string } {
  const r: { ok: boolean; growth?: string; targetPe?: string; years?: string } = { ok: true };
  if (!Number.isFinite(c.growth)) r.growth = "Enter the yearly EPS growth as a number.";
  else if (c.growth < LIMITS.growthMin || c.growth > LIMITS.growthMax) r.growth = `Growth must be between ${LIMITS.growthMin}% and ${LIMITS.growthMax}% a year.`;
  if (!Number.isFinite(c.targetPe)) r.targetPe = "Enter the target P/E as a number.";
  else if (c.targetPe <= LIMITS.peMin || c.targetPe > LIMITS.peMax) r.targetPe = `Target P/E must be above 0 and at most ${LIMITS.peMax}.`;
  if (!Number.isInteger(years) || years < LIMITS.yearsMin || years > LIMITS.yearsMax) r.years = `Use a whole number of years from ${LIMITS.yearsMin} to ${LIMITS.yearsMax}.`;
  r.ok = !r.growth && !r.targetPe && !r.years;
  return r;
}

/** EPS and the implied price for year 0 (today) to `years`, at one growth rate and target P/E. */
export function path(epsNow: number, c: Case, years: number): { year: number; eps: number; price: number }[] {
  return Array.from({ length: years + 1 }, (_, t) => { const e = futureEps(epsNow, c.growth, t); return { year: t, eps: e, price: futurePrice(e, c.targetPe) }; });
}

/** PEG = P/E ÷ growth (%). Needs a positive P/E and positive growth; the growth is the one assumed here, not a history. */
export function peg(peValue: number | null, growthPct: number): { value: number | null; reason?: string } {
  if (peValue == null) return { value: null, reason: "Needs a meaningful P/E." };
  if (!Number.isFinite(growthPct) || growthPct <= 0) return { value: null, reason: "Needs growth above zero." };
  return { value: peValue / growthPct };
}

/** Growth a year (%) that takes today's EPS to the EPS a target price needs at a given target P/E:
 *  g = ((target price ÷ target P/E) ÷ EPS)^(1/n) − 1. Null with a reason when no such rate exists. */
export function requiredGrowth(targetPrice: number, targetPe: number, epsNow: number | null, years: number): { value: number; reason?: undefined } | NotMeaningful {
  if (epsNow == null || !(epsNow > 0)) return { value: null, reason: "Needs a positive EPS today." };
  if (!Number.isFinite(targetPrice) || targetPrice <= 0) return { value: null, reason: "The target price must be above zero." };
  if (!Number.isFinite(targetPe) || targetPe <= 0) return { value: null, reason: "The target P/E must be above zero." };
  if (!Number.isInteger(years) || years < 1) return { value: null, reason: "Years must be a whole number from 1." };
  return { value: (Math.pow(targetPrice / targetPe / epsNow, 1 / years) - 1) * 100 };
}

/** Rows = growth rates, columns = target multiples. Each cell is null where the pair is outside the limits or EPS/price are unusable. */
export function sensitivity(epsNow: number | null, price: number, growths: number[], pes: number[], years: number): (Projection | null)[][] {
  return growths.map((g) => pes.map((p) => project(epsNow, price, { growth: g, targetPe: p }, years)));
}
/** `centre` plus steps either side, kept inside [lo, hi]; the centre is always the middle value that remains in range. */
export function around(centre: number, step: number, count: number, lo: number, hi: number): number[] {
  const half = Math.floor(count / 2), out: number[] = [];
  for (let k = -half; k <= half; k++) { const v = Math.round((centre + k * step) * 1e6) / 1e6; if (v >= lo && v <= hi) out.push(v); }
  return out;
}
