/** Earnings Quality Intelligence: a quick, descriptive read of the Profit Reality Check numbers already loaded for the section.
 *  Pure arithmetic and fixed rules (documented in docs/EARNINGS-INTELLIGENCE.md): no model, no network, nothing invented.
 *  Describes earnings quality from the filings. It never labels a company, never scores it down for negative cash flow alone and never gives advice. */
import { fyLabel, type PrYear, type ProfitReality } from "./profitReality";

export const MINUS = "−";
export const INTEL_THRESHOLDS = {
  cashConversion: 0.8,       // operating cash flow / profit below this is a weak year (same as the Profit Reality Check)
  repeatYears: 2,            // weak in this many of the last three years counts as repeated
  workingCapitalGap: 10,     // receivables / inventory growth minus revenue growth, in points
  normalizedWatch: 0.15, normalizedUnstable: 0.3,
  fcfStrong: 0.6, fcfAdequate: 0.2,   // three-year free cash flow / profit
  otherIncomeShare: 20,      // per cent of pre-tax profit
} as const;

export type ModuleKey = "cash" | "receivables" | "inventory" | "normalized" | "fcf" | "sustain";
export type Tone = "ok" | "watch" | "alert" | "na";
export type IntelModule = { key: ModuleKey; name: string; icon: string; badge: string; tone: Tone; facts: string[]; rule: string };
export type Intel = {
  lender: boolean; softened: boolean;
  pill: { label: string; tone: Tone };
  stats: { label: string; value: string; sub: string }[];
  happening: string;
  questions: string[];
  modules: IntelModule[];
  meaning: { why: string; risks: string[]; where: string };
  caveats: string[];
  peer: string;
};

const LENDER_RE = /\b(bank|banks|nbfc|insurance|insurer|housing finance|microfinance|lending|credit)\b/i;
const SOFT_RE = /(construction|infrastructure|engineering|capital goods|real estate|realty|shipbuild|defen[cs]e|sugar|fertili[sz]er|cement|steel|metal|mining|power|airline|aviation|hotel|agri|seasonal|cyclical|auto)/i;
export const isLenderSector = (sector?: string | null, industry?: string | null) => LENDER_RE.test(`${sector ?? ""} ${industry ?? ""}`);
export const isSoftSector = (sector?: string | null, industry?: string | null) => SOFT_RE.test(`${sector ?? ""} ${industry ?? ""}`);

const abs = Math.abs;
/** ₹ crore with the site's minus sign: −₹1,012 Cr */
export const crSigned = (v: number) => (Math.round(v) < 0 ? MINUS : "") + "₹" + abs(Math.round(v)).toLocaleString("en-IN") + " Cr";
export const pctSigned = (v: number, d = 1, plus = false) => { const r = Math.round(abs(v) * 10 ** d) / 10 ** d; return (v < 0 && r > 0 ? MINUS : plus && r > 0 ? "+" : "") + r.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%"; };
const pct0 = (v: number) => pctSigned(v, 0);
const NED = "Not enough data";

const last3 = <T,>(a: T[]) => a.slice(-3);

function cashModule(ys: PrYear[], soft: boolean, five: ProfitReality["cumulative"]): IntelModule {
  const T = INTEL_THRESHOLDS, base = { key: "cash" as const, name: "Profit vs Cash Flow", icon: "activity" };
  const rule = "Latest year and the last three years: weak when operating cash flow is negative or below 80% of a positive profit. One weak year is Watch; weak in the latest year and in two of the last three is Red flag; otherwise Steady.";
  const l = ys[ys.length - 1];
  if (!l || l.netProfit == null || l.cfo == null) return { ...base, badge: NED, tone: "na", facts: ["Net profit and operating cash flow are needed for the latest year."], rule };
  const weak = (y: PrYear) => y.netProfit != null && y.cfo != null && y.netProfit > 0 && (y.cfo < 0 || y.cfo / y.netProfit < T.cashConversion);
  const ev = last3(ys).filter((y) => y.netProfit != null && y.cfo != null && y.netProfit > 0);
  const w = ev.filter(weak).length, lw = weak(l);
  const facts = [`${fyLabel(l.period)}: operating cash flow ${crSigned(l.cfo)} against net profit ${crSigned(l.netProfit)}${l.cfoToProfit != null ? ` (${pct0(l.cfoToProfit * 100)})` : ""}.`];
  if (ev.length >= 2) facts.push(`Weak cash conversion in ${w} of the last ${ev.length} profitable years.`);
  let badge = "Steady", tone: Tone = "ok";
  const fiveWeak = !!five && five.profit > 0 && five.cfo / five.profit < T.cashConversion;
  if (facts && five && five.profit > 0) facts.push(`${five.years}-year operating cash flow ${crSigned(five.cfo)} against net profit ${crSigned(five.profit)} (${pct0((five.cfo / five.profit) * 100)}).`);
  if (lw && ((ev.length >= 3 && w >= T.repeatYears) || fiveWeak)) { badge = soft ? "Watch" : "Red flag"; tone = soft ? "watch" : "alert"; if (soft) facts.push("Shown as Watch rather than Red flag: this industry often has project-based or seasonal cash cycles."); }
  else if (lw || w >= T.repeatYears) { badge = "Watch"; tone = "watch"; }
  return { ...base, badge, tone, facts, rule };
}

function wcModule(key: "receivables" | "inventory", ys: PrYear[]): IntelModule {
  const T = INTEL_THRESHOLDS, rec = key === "receivables";
  const base = { key, name: rec ? "Receivables Quality" : "Inventory Efficiency", icon: rec ? "wallet" : "layers" };
  const rule = `Growth of ${rec ? "receivables" : "inventory"} minus revenue growth. Investigate when the latest year is 10 or more points ahead of revenue, or the average of the last three years is. Otherwise OK.`;
  const gapOf = (y: PrYear) => (rec ? y.receivablesGap : y.inventoryGap), growOf = (y: PrYear) => (rec ? y.receivablesGrowth : y.inventoryGrowth);
  const l = ys[ys.length - 1], g = l ? gapOf(l) : null;
  if (!l || g == null) return { ...base, badge: NED, tone: "na", facts: [`${rec ? "Receivables" : "Inventory"} and revenue are needed for two consecutive years.`], rule };
  const gaps = last3(ys).map(gapOf).filter((x): x is number => x != null), avg = gaps.reduce((a, b) => a + b, 0) / gaps.length;
  const facts = [`${rec ? "Receivables" : "Inventory"} grew ${pctSigned(growOf(l) as number, 1)} vs revenue ${pctSigned(l.revenueGrowth as number, 1)} in ${fyLabel(l.period)}.`];
  if (gaps.length >= 2) facts.push(`Average gap over the last ${gaps.length} years: ${pctSigned(avg, 1, true).replace("%", " points")}.`);
  const bad = g >= T.workingCapitalGap || (gaps.length >= 2 && avg >= T.workingCapitalGap);
  return { ...base, badge: bad ? "Investigate" : "OK", tone: bad ? "watch" : "ok", facts, rule };
}

function normModule(ys: PrYear[]): IntelModule {
  const T = INTEL_THRESHOLDS, base = { key: "normalized" as const, name: "Normalized Earnings", icon: "bars" };
  const rule = "Gap between reported and normalized profit, as a share of reported profit. Unstable when the latest year is 30% or more apart, or 15% or more apart in two of the last three years. Otherwise Relatively stable.";
  const l = ys[ys.length - 1];
  if (!l || l.netProfit == null || l.normalized == null || !(l.netProfit > 0)) return { ...base, badge: NED, tone: "na", facts: ["A positive reported profit and a normalized profit are needed for the latest year."], rule };
  const gap = (y: PrYear) => (y.netProfit != null && y.normalized != null && y.netProfit > 0 ? abs(y.netProfit - y.normalized) / y.netProfit : null);
  const gs = last3(ys).map(gap).filter((x): x is number => x != null), lg = gap(l) as number, n15 = gs.filter((x) => x >= T.normalizedWatch).length;
  const facts = [`${fyLabel(l.period)}: reported ${crSigned(l.netProfit)}, normalized ${crSigned(l.normalized)} (${pct0(lg * 100)} apart).`];
  if (gs.length >= 2) facts.push(`15% or more apart in ${n15} of the last ${gs.length} years.`);
  const bad = lg >= T.normalizedUnstable || n15 >= 2;
  return { ...base, badge: bad ? "Unstable" : "Relatively stable", tone: bad ? "watch" : "ok", facts, rule };
}

function fcfModule(ys: PrYear[]): IntelModule {
  const T = INTEL_THRESHOLDS, base = { key: "fcf" as const, name: "Free Cash Flow", icon: "coins" };
  const rule = "Free cash flow divided by net profit, added up over the last three years (at least two years with both). Strong at 60% or more, Adequate from 20% to 60%, Weak below 20% or negative.";
  const ev = last3(ys).filter((y) => y.fcf != null && y.netProfit != null);
  const np = ev.reduce((a, y) => a + (y.netProfit as number), 0), fcf = ev.reduce((a, y) => a + (y.fcf as number), 0);
  if (ev.length < 2 || !(np > 0)) return { ...base, badge: NED, tone: "na", facts: ["Free cash flow and a positive net profit are needed for at least two of the last three years."], rule };
  const ratio = fcf / np, l = ev[ev.length - 1];
  const facts = [`${ev.length}-year free cash flow ${crSigned(fcf)} against net profit ${crSigned(np)} (${pct0(ratio * 100)}).`, `${fyLabel(l.period)}: free cash flow ${crSigned(l.fcf as number)}.`];
  const badge = ratio >= T.fcfStrong ? "Strong" : ratio >= T.fcfAdequate ? "Adequate" : "Weak";
  return { ...base, badge, tone: badge === "Strong" ? "ok" : badge === "Adequate" ? "ok" : "watch", facts, rule };
}

function sustainModule(ys: PrYear[]): IntelModule {
  const T = INTEL_THRESHOLDS, base = { key: "sustain" as const, name: "Earnings Sustainability", icon: "quality" };
  const rule = "One-off items (exceptional or discontinued) at 15% or more of profit, or other income above 20% of pre-tax profit. Review when either shows in two of the last three years; otherwise OK.";
  const r3 = last3(ys);
  if (!r3.some((y) => y.exceptional != null || y.discontinued != null || y.otherIncomeShare != null)) return { ...base, badge: NED, tone: "na", facts: ["No one-off items or other income are reported."], rule };
  const oo = r3.filter((y) => y.oneOffFlag).length, oi = r3.filter((y) => y.otherIncomeShare != null && y.otherIncomeShare > T.otherIncomeShare).length;
  const l = ys[ys.length - 1], facts = [`One-off items at 15% or more of profit in ${oo} of the last ${r3.length} years.`];
  if (r3.some((y) => y.otherIncomeShare != null)) facts.push(`Other income above 20% of pre-tax profit in ${oi} of the last ${r3.length} years${l.otherIncomeShare != null ? ` (${fyLabel(l.period)}: ${pctSigned(l.otherIncomeShare, 0)})` : ""}.`);
  const bad = oo >= T.repeatYears || oi >= T.repeatYears;
  return { ...base, badge: bad ? "Review" : "OK", tone: bad ? "watch" : "ok", facts, rule };
}

export function earningsIntel(r: ProfitReality, sector?: string | null, industry?: string | null): Intel | null {
  const ys = r.years;
  if (!ys.length) return null;
  const lender = r.lender || isLenderSector(sector, industry), soft = !lender && isSoftSector(sector, industry);
  const l = ys[ys.length - 1], p = ys.length > 1 ? ys[ys.length - 2] : null;
  const useYs = lender ? ys.map((y) => ({ ...y, cfo: null, fcf: null, cfoToProfit: null, fcfToProfit: null, receivablesGap: null, inventoryGap: null, receivablesGrowth: null, inventoryGrowth: null })) : ys;
  const mods: IntelModule[] = lender ? [normModule(useYs), sustainModule(useYs)] : [cashModule(ys, soft, r.cumulative), wcModule("receivables", ys), wcModule("inventory", ys), normModule(ys), fcfModule(ys), sustainModule(ys)];
  const m = (k: ModuleKey) => mods.find((x) => x.key === k);
  const cash = m("cash");

  const pill: Intel["pill"] = lender ? { label: "Cash-flow analysis not comparable", tone: "na" }
    : !cash || cash.tone === "na" ? { label: "Not enough data", tone: "na" }
    : cash.badge === "Red flag" ? { label: "Weak cash backing", tone: "alert" }
    : cash.badge === "Watch" ? { label: "Cash backing to watch", tone: "watch" }
    : { label: "Cash backing steady", tone: "ok" };

  const stats: Intel["stats"] = [];
  stats.push({ label: "Profit growth", value: l.profitGrowth == null ? "Not available" : pctSigned(l.profitGrowth, 1, true), sub: l.profitGrowth == null ? "Needs a positive profit in the earlier year" : `${fyLabel(l.period)} YoY` });
  if (lender) stats.push({ label: "Operating cash flow", value: "Not compared", sub: "Cash-flow analysis is not comparable for lenders" });
  else stats.push({ label: "Operating cash flow", value: l.cfo == null ? "Not available" : crSigned(l.cfo), sub: l.cfo == null ? "Not reported" : fyLabel(l.period) });

  // What is happening: assembled from fixed phrases, only the ones the numbers support.
  const parts: string[] = [];
  const pg = l.profitGrowth;
  const profitWord = pg == null ? null : pg >= 5 ? "growing" : pg <= -5 ? "falling" : "broadly flat";
  if (!lender && profitWord && l.cfo != null && l.netProfit != null) {
    const weakCash = l.cfo < 0 || (l.netProfit > 0 && l.cfo / l.netProfit < INTEL_THRESHOLDS.cashConversion);
    const weakened = p?.cfo != null && l.cfo < p.cfo;
    if (weakCash) parts.push(`Profit is ${profitWord}, but cash generation ${weakened ? (l.cfo < 0 || (l.netProfit > 0 && l.cfo / l.netProfit < 0.5) ? "has weakened significantly" : "has weakened") : "is below profit"}${l.cfo < 0 ? " (operating cash flow is negative)" : ""}.`);
    else parts.push(`Profit is ${profitWord}, and operating cash flow is in line with it.`);
  } else if (profitWord) parts.push(`Profit is ${profitWord}.`);
  if (!lender) {
    const rf = mods.find((x) => x.key === "receivables")?.badge === "Investigate" && l.receivablesFlag, inf = mods.find((x) => x.key === "inventory")?.badge === "Investigate" && l.inventoryFlag;
    if (rf && inf) parts.push("Receivables and inventory are also growing faster than revenue.");
    else if (rf) parts.push("Receivables are also growing faster than revenue.");
    else if (inf) parts.push("Inventory is also growing faster than revenue.");
  } else parts.push("Cash-flow and working-capital checks are left out for lenders.");
  const nm = m("normalized");
  if (nm?.badge === "Unstable") parts.push("Reported profit differs noticeably from normalized profit.");
  const happening = parts.length ? parts.join(" ") : "There is not enough reported data to describe the earnings picture.";

  const q: string[] = [];
  if (!lender) {
    if (m("receivables")?.badge === "Investigate" && l.receivablesGrowth != null) q.push(`How efficiently is the company collecting from customers? Receivables grew ${pctSigned(l.receivablesGrowth, 1)} against revenue growth of ${pctSigned(l.revenueGrowth as number, 1)}.`);
    if (m("inventory")?.badge === "Investigate" && l.inventoryGrowth != null) q.push(`Is inventory accumulating faster than it sells? Inventory grew ${pctSigned(l.inventoryGrowth, 1)} against revenue growth of ${pctSigned(l.revenueGrowth as number, 1)}.`);
    if (cash && (cash.badge === "Watch" || cash.badge === "Red flag")) q.push("How consistent is cash conversion from year to year, and is the gap tied to a project, a season or a one-time build-up?");
  }
  if (m("sustain")?.badge === "Review" || (l.otherIncomeShare != null && l.otherIncomeShare > INTEL_THRESHOLDS.otherIncomeShare) || nm?.badge === "Unstable") q.push("How much of the profit comes from non-operating income or one-off items?");

  const caveats = ["Some businesses have seasonal or project-based cash cycles."];
  if (soft) caveats.push("This industry often has project-based, seasonal or cyclical cash flows, so the Profit vs Cash Flow status is softened.");
  if (lender) caveats.push("Banks, NBFCs and insurers carry loans and deposits inside operating cash flow, so cash-flow analysis is not comparable for lenders.");

  const risks: string[] = [];
  if (!lender) {
    if (cash && cash.tone !== "ok" && cash.tone !== "na") risks.push("When profit runs ahead of cash for several years, the reported profit may not be turning into money the business can use.");
    if (m("receivables")?.badge === "Investigate") risks.push("Receivables growing faster than revenue can mean slower collection or more sales on credit, which ties up cash.");
    if (m("inventory")?.badge === "Investigate") risks.push("Inventory growing faster than revenue can mean stock is building up, which ties up cash and can lead to later write-downs.");
  }
  if (nm?.badge === "Unstable" || m("sustain")?.badge === "Review") risks.push("Profit that leans on one-off items or other income may not repeat in the same size.");
  const meaning = {
    why: lender ? "Profit is an accounting measure, so it helps to see how much of it is repeatable once one-off items are set aside." : "Profit is an accounting measure; operating cash flow is the cash the business actually received. Seeing them side by side shows how much of the profit is backed by cash.",
    risks, where: lender ? "Where to look: the notes on exceptional items and other income in the annual report." : "Where to look: the cash flow statement, the receivables and inventory notes, and the notes on exceptional items in the annual report.",
  };
  return { lender, softened: soft, pill, stats, happening, questions: q, modules: mods, meaning, caveats, peer: "Peer comparison: not available" };
}
