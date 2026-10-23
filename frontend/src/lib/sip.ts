// SIP (systematic investment plan) maths for the SIP calculator. Pure and side-effect free, so every figure is tested (sip.test.ts).
//
// The FinLit formula sheet (the default):
//   P = monthly SIP, r = expected annual return in per cent, i = r / 1200 (monthly rate), n = 12 × t months
//   SIP paid at the END of each month:   FV = P × ((1 + i)^n − 1) / i
//   total invested = P × n,  wealth gained = FV − P × n
// Options beyond the sheet, each stated on the page:
//   - paid at the START of each month (an "annuity due"): every instalment earns one month more, FV × (1 + i). Many apps use this.
//   - effective annual compounding: i = (1 + r/100)^(1/12) − 1, so 12% a year is exactly 12% after a year (the sheet's r/12 gives 12.68%).
//   - a yearly step-up (per cent or fixed rupees), a one-time amount at the start, inflation, and an equity capital-gains tax estimate.
// Every figure is worked out month by month in full precision; rounding to the rupee happens only on screen. When there is no step-up,
// the month-by-month result equals the closed formula above (checked in the tests to a fraction of a paisa).

export type Timing = "end" | "start";
export type Compounding = "monthly" | "effective";
export type StepUp = { kind: "none" | "pct" | "amount"; value: number };
export type SipInput = {
  monthly: number; years: number; months?: number; annualReturn: number;
  timing?: Timing; compounding?: Compounding; stepUp?: StepUp; lumpSum?: number;
};
export type YearRow = { year: number; sip: number; invested: number; value: number; gain: number; investedInYear: number };
export type SipResult = {
  n: number; i: number; invested: number; value: number; gain: number; lumpValue: number; sipValue: number;
  years: YearRow[];                 // one row per year (a part year at the end when months are given)
  monthly: { m: number; invested: number; value: number }[];   // every month, for the chart
  multiple: number;                 // value ÷ invested
};

export const LIMITS = { monthlyMin: 100, monthlyMax: 1_000_000, yearsMax: 50, returnMin: 0, returnMax: 30, lumpMax: 100_000_000 } as const;

/** Monthly rate in decimal for an annual return in per cent. */
export function monthlyRate(annualReturn: number, compounding: Compounding = "monthly"): number {
  return compounding === "effective" ? Math.pow(1 + annualReturn / 100, 1 / 12) - 1 : annualReturn / 1200;
}

/** The sheet's closed formula (end of month), with the zero-return case (FV = P × n) handled exactly. */
export function sipFutureValue(P: number, i: number, n: number, timing: Timing = "end"): number {
  if (n <= 0 || P === 0) return 0;
  const base = Math.abs(i) < 1e-12 ? n : (Math.pow(1 + i, n) - 1) / i;
  return P * base * (timing === "start" ? 1 + i : 1);
}

const clamp = (v: number, lo: number, hi: number) => (Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : lo);
/** The SIP amount paid in a given year (1-based) after the step-up. */
export function sipInYear(P: number, year: number, step: StepUp | undefined): number {
  if (!step || step.kind === "none" || !step.value) return P;
  return step.kind === "pct" ? P * Math.pow(1 + step.value / 100, year - 1) : P + step.value * (year - 1);
}

/** Month-by-month projection. A month's instalment is added at its start or end; the whole balance then grows by i for the month. */
export function project(inp: SipInput): SipResult {
  const P = clamp(inp.monthly, 0, LIMITS.monthlyMax), lump = clamp(inp.lumpSum ?? 0, 0, LIMITS.lumpMax);
  const n = Math.round(clamp(inp.years, 0, LIMITS.yearsMax) * 12 + clamp(inp.months ?? 0, 0, 11));
  const i = monthlyRate(clamp(inp.annualReturn, LIMITS.returnMin, LIMITS.returnMax), inp.compounding);
  const start = inp.timing === "start";
  let bal = lump, lumpBal = lump, invested = lump, yInvested = 0;
  const years: YearRow[] = [], monthly: SipResult["monthly"] = [{ m: 0, invested, value: bal }];
  for (let m = 1; m <= n; m++) {
    const year = Math.ceil(m / 12), amt = sipInYear(P, year, inp.stepUp);
    if (start) bal += amt;
    bal *= 1 + i;
    lumpBal *= 1 + i;
    if (!start) bal += amt;
    invested += amt; yInvested += amt;
    monthly.push({ m, invested, value: bal });
    if (m % 12 === 0 || m === n) {
      years.push({ year: m / 12, sip: amt, invested, value: bal, gain: bal - invested, investedInYear: yInvested });
      yInvested = 0;
    }
  }
  return { n, i, invested, value: bal, gain: bal - invested, lumpValue: lumpBal, sipValue: bal - lumpBal, years, monthly, multiple: invested ? bal / invested : 0 };
}

/** Value in today's money: divided by (1 + inflation) for every year that passes (months counted as part years). */
export const realValue = (value: number, inflationPct: number, months: number) => value / Math.pow(1 + inflationPct / 100, months / 12);

/** The monthly SIP that reaches `target`. FV is a straight line in P (also with a per-cent step-up), so it is solved exactly from two runs. */
export function requiredMonthly(target: number, inp: Omit<SipInput, "monthly">): number | null {
  const base = project({ ...inp, monthly: 0 }).value;              // the lump sum alone (and a fixed-rupee step-up, which does not scale with P)
  const one = project({ ...inp, monthly: 1 }).value - base;
  if (one <= 0) return null;
  const need = (target - base) / one;
  return need <= 0 ? 0 : need;
}

/** Months until the value first reaches `target` (null if not within the 50-year limit). */
export function monthsToTarget(target: number, inp: Omit<SipInput, "years" | "months">): number | null {
  const r = project({ ...inp, years: LIMITS.yearsMax, months: 0 });
  const hit = r.monthly.find((x) => x.value >= target);
  return hit ? hit.m : null;
}

/** First month the gains are larger than the money put in (the point where returns do more of the work than you). */
export function gainsOvertake(r: SipResult): number | null {
  const hit = r.monthly.find((x) => x.m > 0 && x.value - x.invested > x.invested);
  return hit ? hit.m : null;
}

/** Round amounts the corpus crosses, with the month each one is first reached. */
export function milestones(r: SipResult, marks = [1e5, 5e5, 1e6, 2.5e6, 5e6, 1e7, 2.5e7, 5e7, 1e8, 2.5e8, 5e8, 1e9]): { amount: number; m: number }[] {
  const out: { amount: number; m: number }[] = [];
  for (const a of marks) {
    if (r.monthly[0].value >= a) continue;
    const hit = r.monthly.find((x) => x.value >= a);
    if (hit) out.push({ amount: a, m: hit.m });
  }
  return out;
}

/** What waiting costs: the same plan started `delayYears` later, ending on the same date (so it runs that much shorter). */
export function delayCost(inp: SipInput, delayYears: number): { value: number; lost: number; investedLess: number } {
  const full = project(inp);
  const total = full.n - delayYears * 12;
  if (total <= 0) return { value: 0, lost: full.value, investedLess: full.invested };
  const late = project({ ...inp, years: Math.floor(total / 12), months: total % 12 });
  return { value: late.value, lost: full.value - late.value, investedLess: full.invested - late.invested };
}

// ------------------------------------------------------------------------------------------------- capital gains tax (equity funds)
// Each instalment is its own purchase. When everything is sold at the end, an instalment held more than 12 months is a long-term gain,
// otherwise short-term. Rates are inputs (shown on the page, with the date they were set); the default is the rule for equity-oriented
// funds from 23 July 2024: long-term 12.5% on gains above ₹1.25 lakh a year, short-term 20%, plus 4% health and education cess.
// Surcharge, other income, debt funds (taxed at slab rates) and indexation are not modelled: the page says so.
export type TaxRules = { ltcgPct: number; stcgPct: number; exemption: number; cessPct: number };
export const EQUITY_TAX_2024: TaxRules = { ltcgPct: 12.5, stcgPct: 20, exemption: 125_000, cessPct: 4 };
export type TaxResult = { longGain: number; shortGain: number; taxable: number; tax: number; afterTax: number };

export function equityTax(inp: SipInput, rules: TaxRules = EQUITY_TAX_2024): TaxResult {
  const r = project(inp), i = r.i, start = inp.timing === "start";
  let longGain = 0, shortGain = 0;
  const add = (amount: number, heldMonths: number) => {
    const g = amount * (Math.pow(1 + i, heldMonths) - 1);
    if (heldMonths > 12) longGain += g; else shortGain += g;
  };
  if (inp.lumpSum) add(clamp(inp.lumpSum, 0, LIMITS.lumpMax), r.n);
  for (let m = 1; m <= r.n; m++) add(sipInYear(clamp(inp.monthly, 0, LIMITS.monthlyMax), Math.ceil(m / 12), inp.stepUp), r.n - m + (start ? 1 : 0));
  const ltTaxable = Math.max(0, longGain - rules.exemption), stTaxable = Math.max(0, shortGain);
  const tax = (ltTaxable * rules.ltcgPct / 100 + stTaxable * rules.stcgPct / 100) * (1 + rules.cessPct / 100);
  return { longGain, shortGain, taxable: ltTaxable + stTaxable, tax, afterTax: r.value - tax };
}

// ------------------------------------------------------------------------------------------------- words and the share link
/** ₹ in the Indian way, whole rupees: ₹5,75,097. */
export const rupees = (v: number) => (v < 0 ? "−" : "") + "₹" + Math.round(Math.abs(v)).toLocaleString("en-IN");
/** Short form for chart axes and milestones: ₹12.5 L, ₹3.2 Cr. */
export function short(v: number): string {
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (a >= 1e7) return `${s}₹${trim(a / 1e7)} Cr`;
  if (a >= 1e5) return `${s}₹${trim(a / 1e5)} L`;
  if (a >= 1e3) return `${s}₹${trim(a / 1e3)}k`;
  return `${s}₹${Math.round(a)}`;
}
const trim = (x: number) => (x >= 100 ? Math.round(x).toString() : x.toFixed(2).replace(/\.?0+$/, ""));
/** "12 years 3 months", "11 months". */
export function duration(months: number): string {
  const y = Math.floor(months / 12), m = months % 12;
  return [y ? `${y} year${y === 1 ? "" : "s"}` : "", m ? `${m} month${m === 1 ? "" : "s"}` : ""].filter(Boolean).join(" ") || "0 months";
}

export type SipState = Required<Omit<SipInput, "stepUp">> & { stepKind: StepUp["kind"]; stepValue: number; inflation: number; tax: boolean };
export const DEFAULT_STATE: SipState = { monthly: 2500, years: 10, months: 0, annualReturn: 12, timing: "end", compounding: "monthly", lumpSum: 0, stepKind: "none", stepValue: 10, inflation: 6, tax: false };
const KEYS: [keyof SipState, string][] = [["monthly", "p"], ["years", "y"], ["months", "mo"], ["annualReturn", "r"], ["timing", "t"], ["compounding", "c"], ["lumpSum", "l"], ["stepKind", "sk"], ["stepValue", "sv"], ["inflation", "inf"], ["tax", "tax"]];

/** The calculator's inputs as a short query string (the shareable link), only what differs from the defaults. */
export function toQuery(s: SipState): string {
  const q = new URLSearchParams();
  for (const [k, short] of KEYS) if (s[k] !== DEFAULT_STATE[k]) q.set(short, String(s[k]));
  return q.toString();
}
/** Inputs from a link, every value checked and kept inside the limits; anything unreadable falls back to the default. */
export function fromQuery(sp: URLSearchParams): SipState {
  const out: SipState = { ...DEFAULT_STATE };
  const num = (k: string, lo: number, hi: number, d: number) => { const v = Number(sp.get(k)); return sp.has(k) && Number.isFinite(v) ? clamp(v, lo, hi) : d; };
  out.monthly = num("p", 0, LIMITS.monthlyMax, out.monthly);
  out.years = Math.round(num("y", 0, LIMITS.yearsMax, out.years));
  out.months = Math.round(num("mo", 0, 11, out.months));
  out.annualReturn = num("r", LIMITS.returnMin, LIMITS.returnMax, out.annualReturn);
  out.lumpSum = num("l", 0, LIMITS.lumpMax, 0);
  out.stepValue = num("sv", 0, 1_000_000, out.stepValue);
  out.inflation = num("inf", 0, 20, out.inflation);
  if (sp.get("t") === "start") out.timing = "start";
  if (sp.get("c") === "effective") out.compounding = "effective";
  const sk = sp.get("sk"); if (sk === "pct" || sk === "amount") out.stepKind = sk;
  out.tax = sp.get("tax") === "true";
  return out;
}
export const toInput = (s: SipState): SipInput => ({ monthly: s.monthly, years: s.years, months: s.months, annualReturn: s.annualReturn, timing: s.timing, compounding: s.compounding, lumpSum: s.lumpSum, stepUp: { kind: s.stepKind, value: s.stepValue } });
