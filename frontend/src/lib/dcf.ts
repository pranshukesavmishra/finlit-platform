/** Discounted cash flow (DCF) valuation: a two-stage, ten-year free cash flow model with a Gordon growth terminal value, in the exact order of
 *  the FinLit formula sheet (inputs, projection, discounting, terminal value, enterprise value, equity value, shares, intrinsic value per
 *  share, upside, margin of safety, status), plus the checks and analysis an analyst expects around it: input validation, sanity warnings,
 *  sensitivity grids, and reverse DCF (the growth or discount rate the market price implies).
 *
 *  Units: cash flows, market capitalisation, net debt and values in ₹ crore; prices in ₹; rates in percent. Shares come out in crore
 *  (₹ crore ÷ ₹ = crore shares), so equity value (₹ crore) ÷ shares (crore) is ₹ per share. Nothing here rounds: rounding is for display. */

export type GrowthPreset = "conservative" | "moderate" | "aggressive" | "custom";
export const GROWTH_PRESETS: Record<Exclude<GrowthPreset, "custom">, { label: string; value: number }> = {
  conservative: { label: "Conservative", value: 5 },
  moderate: { label: "Moderate", value: 10 },
  aggressive: { label: "Aggressive", value: 15 },
};

export type DcfInputs = {
  fcf0: number;          // initial (base-year) free cash flow, ₹ crore
  r: number;             // discount rate, % a year
  g1: number;            // FCF growth, years 1 to 5, % a year
  g2: number;            // FCF growth, years 6 to 10, % a year
  gT: number;            // terminal (perpetual) growth after year 10, % a year
  marketCap: number;     // ₹ crore
  price: number;         // current share price, ₹
  netDebt: number;       // ₹ crore; negative for net cash
  mos: number;           // margin of safety, %
  midYear?: boolean;     // mid-year convention: cash arrives through the year, so FCF_t is discounted (t − 0.5) years (see compute for the TV)
  shares?: number | null; // shares outstanding in crore; default: market capitalisation ÷ price (formula sheet step 8)
  tvMethod?: "gordon" | "exit"; // terminal value: Gordon growth (formula sheet step 4, the default) or an exit multiple of year-10 FCF
  exitMultiple?: number | null; // EV ÷ FCF multiple at year 10, for tvMethod "exit"
};

export type DcfYear = { t: number; stage: 1 | 2; growth: number; fcf: number; factor: number; pv: number };
export type DcfStatus = "buy" | "fair" | "overvalued" | "not-meaningful";
export type DcfResult = {
  years: DcfYear[];
  sumPv: number;          // Σ PV(FCF_t), t = 1..10
  fcf11: number;          // FCF_10 × (1 + gT)
  tv: number;             // TV_10 = FCF_11 ÷ (r − gT)
  pvTv: number;           // TV_10 ÷ (1 + r)^10
  ev: number;             // enterprise value
  equity: number;         // EV − net debt
  shares: number;         // crore
  iv: number;             // intrinsic value per share, ₹
  upside: number;         // %, (IV ÷ price − 1) × 100
  buyPrice: number;       // IV × (1 − MOS ÷ 100)
  status: DcfStatus;
  tvShare: number;        // PV(TV) as % of EV
  exitMultiple: number;   // TV_10 ÷ FCF_10: the EV/FCF multiple the terminal value implies at year 10
  impliedGT: number;      // % : the perpetual growth the terminal value implies, (TV × r − FCF_10) ÷ (TV + FCF_10) (equals gT for Gordon)
  impliedFcfYield: number; // FCF_1 ÷ (market cap + net debt) × 100: what the market pays today
};
export type Issue = { field: keyof DcfInputs | "model"; text: string };
export type DcfOutcome = { result: DcfResult | null; errors: Issue[]; warnings: Issue[] };

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Problems that make the model meaningless or the arithmetic impossible: no result is shown while any exists. */
export function validate(i: DcfInputs): Issue[] {
  const e: Issue[] = [];
  const need: [keyof DcfInputs, string][] = [["fcf0", "Initial FCF"], ["r", "Discount rate"], ["g1", "Growth rate (years 1–5)"], ["g2", "Growth rate (years 6–10)"],
    ["gT", "Terminal growth rate"], ["marketCap", "Market capitalisation"], ["price", "Current share price"], ["netDebt", "Net debt"], ["mos", "Margin of safety"]];
  for (const [k, label] of need) if (!finite(i[k])) e.push({ field: k, text: `${label} is required and must be a number.` });
  if (e.length) return e;
  if (i.fcf0 <= 0) e.push({ field: "fcf0", text: "A DCF needs a positive starting free cash flow: growing a negative figure only makes it more negative. Use a normalised FCF (for example the average of the last 3 to 5 years)." });
  if (i.r <= 0) e.push({ field: "r", text: "The discount rate must be above 0%." });
  const exit = i.tvMethod === "exit";
  if (!exit && i.r <= i.gT) e.push({ field: "gT", text: `The terminal growth rate (${i.gT}%) must be below the discount rate (${i.r}%): otherwise the terminal value TV = FCF₁₁ ÷ (r − g) is infinite or negative.` });
  if (exit && (!finite(i.exitMultiple) || (i.exitMultiple as number) <= 0)) e.push({ field: "exitMultiple", text: "Enter an exit multiple (EV ÷ FCF at year 10) above 0." });
  for (const [k, label] of [["g1", "Growth rate (years 1–5)"], ["g2", "Growth rate (years 6–10)"], ["gT", "Terminal growth rate"]] as const)
    if (i[k] <= -100) e.push({ field: k, text: `${label} must be above −100%.` });
  if (i.marketCap <= 0) e.push({ field: "marketCap", text: "Market capitalisation must be above 0." });
  if (i.price <= 0) e.push({ field: "price", text: "Current share price must be above 0." });
  if (i.mos < 0 || i.mos >= 100) e.push({ field: "mos", text: "Margin of safety must be from 0% up to (not including) 100%." });
  if (i.shares != null && (!finite(i.shares) || i.shares <= 0)) e.push({ field: "shares", text: "Shares outstanding must be above 0." });
  return e;
}

/** Steps 2 to 12 of the formula sheet. Call only with inputs that passed validate(). */
export function compute(i: DcfInputs): DcfResult {
  const r = i.r / 100, g1 = i.g1 / 100, g2 = i.g2 / 100, gT = i.gT / 100;
  const years: DcfYear[] = [];
  let fcf = i.fcf0;
  for (let t = 1; t <= 10; t++) {
    const stage = t <= 5 ? 1 : 2, g = stage === 1 ? g1 : g2;
    fcf = fcf * (1 + g);                                                     // FCF_t = FCF_0 (1+g1)^t for t ≤ 5; FCF_{t−1} (1+g2) after
    const factor = 1 / Math.pow(1 + r, i.midYear ? t - 0.5 : t);
    years.push({ t, stage, growth: stage === 1 ? i.g1 : i.g2, fcf, factor, pv: fcf * factor });
  }
  const sumPv = years.reduce((s, y) => s + y.pv, 0);
  const fcf10 = years[9].fcf;
  const fcf11 = fcf10 * (1 + gT);
  const exit = i.tvMethod === "exit";
  const tv = exit ? (i.exitMultiple as number) * fcf10 : fcf11 / (r - gT);
  // Gordon TV values the cash flows from year 11 on; with the mid-year convention they arrive mid-year too, so it is discounted 9.5 years, the
  // same convention as the explicit years. An exit multiple is a price at the end of year 10, so it is always discounted 10 years.
  const pvTv = tv / Math.pow(1 + r, i.midYear && !exit ? 9.5 : 10);
  const ev = sumPv + pvTv;
  const equity = ev - i.netDebt;
  const shares = i.shares != null && i.shares > 0 ? i.shares : i.marketCap / i.price;
  const iv = equity / shares;
  const upside = (iv / i.price - 1) * 100;
  const buyPrice = iv * (1 - i.mos / 100);
  const status: DcfStatus = iv <= 0 ? "not-meaningful" : i.price <= buyPrice ? "buy" : i.price > iv ? "overvalued" : "fair";
  return {
    years, sumPv, fcf11, tv, pvTv, ev, equity, shares, iv, upside, buyPrice, status,
    tvShare: ev > 0 ? (pvTv / ev) * 100 : NaN,
    exitMultiple: tv / fcf10,
    impliedGT: ((tv * r - fcf10) / (tv + fcf10)) * 100,
    impliedFcfYield: (years[0].fcf / (i.marketCap + i.netDebt)) * 100,
  };
}

/** Assumptions that are allowed but deserve a second look; shown beside the result, never instead of it. */
export function warnings(i: DcfInputs, res: DcfResult): Issue[] {
  const w: Issue[] = [];
  const exit = i.tvMethod === "exit";
  if (exit && (res.impliedGT > 6 || res.impliedGT >= i.r)) w.push({ field: "exitMultiple", text: `An exit multiple of ${i.exitMultiple}× implies ${res.impliedGT.toFixed(2)}% growth a year forever after year 10${res.impliedGT >= i.r ? ", at or above the discount rate" : ""}: check it against the Gordon method.` });
  if (!exit && i.gT > 6) w.push({ field: "gT", text: `A terminal growth of ${i.gT}% a year forever is above India's long-run nominal growth assumptions (most analysts use 4% to 6%, and never more than the risk-free rate, about 6.5%).` });
  if (!exit && i.gT < 0) w.push({ field: "gT", text: "A negative terminal growth assumes the business shrinks forever." });
  if (!exit && i.r - i.gT < 2) w.push({ field: "gT", text: `The gap between discount rate and terminal growth is only ${(i.r - i.gT).toFixed(2)} points: the terminal value, and so the answer, swings sharply with small changes.` });
  if (i.r < 9) w.push({ field: "r", text: `A ${i.r}% discount rate is below what Indian equities usually need (cost of equity is typically 11% to 14%: the 10-year government bond yield plus an equity risk premium).` });
  if (i.r > 20) w.push({ field: "r", text: `A ${i.r}% discount rate is very high for a listed Indian company; check it.` });
  for (const [k, label] of [["g1", "years 1–5"], ["g2", "years 6–10"]] as const)
    if (i[k] > 30) w.push({ field: k, text: `${i[k]}% a year for five years (${label}) means FCF multiplies by ${Math.pow(1 + i[k] / 100, 5).toFixed(1)}×; few companies sustain that.` });
  if (i.g2 > i.g1 + 5) w.push({ field: "g2", text: "Growth in years 6–10 is well above years 1–5; growth usually slows as a business matures." });
  if (!exit && i.g2 < i.gT) w.push({ field: "g2", text: "Growth in years 6–10 is below the terminal growth: the model then speeds up again after year 10." });
  if (res.tvShare > 75) w.push({ field: "model", text: `${res.tvShare.toFixed(0)}% of the enterprise value comes from the terminal value (beyond year 10): the result rests mostly on the terminal assumptions.` });
  if (res.equity <= 0) w.push({ field: "netDebt", text: "Net debt is larger than the enterprise value: the equity has no value in this model, so there is no meaningful intrinsic value per share." });
  if (i.shares == null) {
    const implied = i.marketCap / i.price;
    if (!(implied > 0)) w.push({ field: "marketCap", text: "Shares outstanding could not be worked out from market capitalisation and price." });
  }
  return w;
}

export function run(i: DcfInputs): DcfOutcome {
  const errors = validate(i);
  if (errors.length) return { result: null, errors, warnings: [] };
  const result = compute(i);
  return { result, errors, warnings: warnings(i, result) };
}

/** Intrinsic value per share for every pair of values of two inputs (rows × columns). A cell is null where the model is undefined
 *  (for example a discount rate at or below the terminal growth). */
export function sensitivity(i: DcfInputs, rowKey: keyof DcfInputs, rows: number[], colKey: keyof DcfInputs, cols: number[]): (number | null)[][] {
  return rows.map((rv) => cols.map((cv) => {
    const x = { ...i, [rowKey]: rv, [colKey]: cv } as DcfInputs;
    return validate(x).length ? null : compute(x).iv;
  }));
}

/** Evenly spaced values around a centre: around(12, 1, 2) -> [10, 11, 12, 13, 14]. Rounded to 4 decimals so 0.1-steps stay exact. */
export const around = (centre: number, step: number, each = 2) =>
  Array.from({ length: each * 2 + 1 }, (_, k) => Math.round((centre + (k - each) * step) * 1e4) / 1e4);

/** Solve f(x) = target for x in [lo, hi] by bisection, f monotonic on the interval. null when the target is outside f's range there. */
function solve(f: (x: number) => number, target: number, lo: number, hi: number): number | null {
  let flo = f(lo) - target, fhi = f(hi) - target;
  if (!Number.isFinite(flo) || !Number.isFinite(fhi) || flo * fhi > 0) return null;
  for (let k = 0; k < 200 && hi - lo > 1e-10; k++) {
    const mid = (lo + hi) / 2, fm = f(mid) - target;
    if (fm === 0) return mid;
    if (fm * flo < 0) { hi = mid; fhi = fm; } else { lo = mid; flo = fm; }
  }
  return (lo + hi) / 2;
}

/** Reverse DCF: the FCF growth for years 1–5 (others unchanged) at which the intrinsic value equals the current price. Intrinsic value rises
 *  with that growth (all FCFs positive), so the answer is unique when it exists in −50% to +150%. */
export function impliedGrowth(i: DcfInputs): number | null {
  if (validate(i).length) return null;
  return solve((g) => compute({ ...i, g1: g }).iv, i.price, -50, 150);
}

/** Reverse DCF: the discount rate (the return the price offers) at which the intrinsic value equals the current price, with every growth
 *  assumption unchanged. Intrinsic value falls as the rate rises, so the answer is unique; searched between terminal growth and 100%. */
export function impliedReturn(i: DcfInputs): number | null {
  if (validate(i).length) return null;
  return solve((r) => compute({ ...i, r }).iv, i.price, i.gT + 0.01, 100);
}

export const STATUS_TEXT: Record<DcfStatus, { label: string; text: string }> = {
  buy: { label: "Price below estimated value", text: "The current price is at or below the buy price (intrinsic value less the margin of safety) on these assumptions (undervalued)." },
  fair: { label: "Price near estimated value", text: "The current price is between the buy price and the intrinsic value on these assumptions (fairly valued)." },
  overvalued: { label: "Price above estimated value", text: "The current price is above the intrinsic value on these assumptions (overvalued)." },
  "not-meaningful": { label: "Not meaningful", text: "Equity value is zero or negative in this model, so there is no intrinsic value per share to compare with the price." },
};

/** Short pill text for the verdict banner. */
export const STATUS_PILL: Record<DcfStatus, string> = { buy: "Undervalued on this model", fair: "Fairly valued on this model", overvalued: "Overvalued on this model", "not-meaningful": "Not meaningful" };

export type Scenario = { key: "bear" | "base" | "bull"; label: string; probability: number; g1: number; g2: number; r: number };
/** Bear, base and bull cases: each its own growth and discount rate, the rest shared. The weighted value is Σ pᵢ × IVᵢ (probabilities in %,
 *  they must add up to 100). A case whose inputs fail validation makes the weighted value unavailable rather than silently left out. */
export function scenarios(i: DcfInputs, cases: Scenario[]): { rows: { s: Scenario; iv: number | null; upside: number | null }[]; weighted: number | null; probabilityTotal: number } {
  const rows = cases.map((s) => {
    const x = { ...i, g1: s.g1, g2: s.g2, r: s.r };
    if (validate(x).length) return { s, iv: null, upside: null };
    const res = compute(x);
    return { s, iv: res.equity > 0 ? res.iv : null, upside: res.equity > 0 ? res.upside : null };
  });
  const probabilityTotal = cases.reduce((t, s) => t + s.probability, 0);
  const ok = Math.abs(probabilityTotal - 100) < 1e-9 && rows.every((r) => r.iv != null);
  return { rows, weighted: ok ? rows.reduce((t, r) => t + (r.s.probability / 100) * (r.iv as number), 0) : null, probabilityTotal };
}

export function defaultScenarios(i: DcfInputs): Scenario[] {
  return [
    { key: "bear", label: "Bear", probability: 25, g1: i.g1 - 5, g2: i.g2 - 3, r: i.r + 1 },
    { key: "base", label: "Base", probability: 50, g1: i.g1, g2: i.g2, r: i.r },
    { key: "bull", label: "Bull", probability: 25, g1: i.g1 + 5, g2: i.g2 + 3, r: i.r - 1 },
  ];
}

export type CostOfCapital = { rf: number; beta: number; erp: number; kd: number; tax: number; debtWeight: number };
/** CAPM and WACC: cost of equity Ke = Rf + β × ERP; WACC = E/(D+E) × Ke + D/(D+E) × Kd × (1 − t). All in %; debtWeight = D/(D+E) in %. */
export function costOfCapital(c: CostOfCapital): { ke: number; kdAfterTax: number; wacc: number } {
  const ke = c.rf + c.beta * c.erp, kdAfterTax = c.kd * (1 - c.tax / 100), w = c.debtWeight / 100;
  return { ke, kdAfterTax, wacc: (1 - w) * ke + w * kdAfterTax };
}
/** India defaults, October 2026: 10-year G-sec yield about 6.7–6.9% (RBI / CCIL), equity risk premium about 7% (Damodaran's total ERP for
 *  India, Incwert's 2026 recommendation 6.5–7.5%), corporate tax 25.17% (section 115BAA). Users should check Rf on the day they value. */
export const INDIA_DEFAULTS: CostOfCapital = { rf: 6.8, beta: 1, erp: 7, kd: 9, tax: 25.17, debtWeight: 0 };

/** Margin of safety by how uncertain the business's cash flows are (Morningstar's uncertainty bands for a 5-star price). */
export const MOS_PRESETS = [{ label: "Low uncertainty", value: 20 }, { label: "Medium", value: 30 }, { label: "High", value: 40 }, { label: "Very high", value: 50 }];
