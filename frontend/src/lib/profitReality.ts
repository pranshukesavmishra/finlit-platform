/** Profit Reality Check: is the profit real, repeatable and backed by cash? Worked out only from the company's own yearly statements.
 *  Figures are in rupees crore. Lenders (banks, NBFCs) get the one-off and normalized-profit checks only: for them operating cash flow
 *  and receivables/inventory do not mean what they mean for a manufacturer or a retailer, so those tests are skipped. */
import type { Table } from "./api";

export const THRESHOLDS = {
  cashConversionMin: 0.8,       // CFO below 80% of profit counts as a gap year
  oneOffShare: 0.15,            // exceptional or discontinued items at 15% or more of profit are flagged
  otherIncomeShare: 0.2,        // other income above 20% of pre-tax profit is treated as not core
  profitJump: 0.25,             // net profit up 25% or more
  cashFlat: 0.05,               // operating cash flow up less than 5% counts as flat
  workingCapitalGap: 10,        // percentage points faster than revenue
  taxFloor: 0, taxCap: 0.4, taxDefault: 0.25,
} as const;

export type Status = "ok" | "warn" | "flag" | "na";
export type PrYear = {
  period: string; revenue: number | null; netProfit: number | null; cfo: number | null; fcf: number | null;
  taxRate: number; taxRateAssumed: boolean;
  exceptional: number | null; discontinued: number | null; otherIncome: number | null; pretax: number | null;
  exceptionalAfterTax: number | null; otherIncomeShare: number | null; otherIncomeAdjustment: number | null;
  normalized: number | null;
  cfoToProfit: number | null; fcfToProfit: number | null; cashGap: boolean;
  exceptionalPctPretax: number | null; exceptionalPctNet: number | null; discontinuedPctNet: number | null; oneOffFlag: boolean;
  profitGrowth: number | null; cfoGrowth: number | null; profitNoCash: boolean;
  revenueGrowth: number | null; receivablesGrowth: number | null; inventoryGrowth: number | null;
  receivablesGap: number | null; inventoryGap: number | null; receivablesFlag: boolean; inventoryFlag: boolean;
};
export type Rule = { key: string; text: string; status: Status; detail: string };
export type Cumulative = { years: number; cfo: number; profit: number; ratio: number | null };
export type ProfitReality = {
  years: PrYear[]; lender: boolean; verdict: "Strong" | "Mixed" | "Needs a closer look" | null;
  rules: Rule[]; findings: string[]; cumulative: Cumulative | null; gapYears: number; gapEvaluated: number; headline: string | null; notes: string[];
};

const at = (t: Table | undefined, key: string, p: string): number | null => {
  const i = t?.periods.indexOf(p) ?? -1, v = i >= 0 ? t?.rows[key]?.[i] : null;
  return v == null || !Number.isFinite(v) ? null : v;
};
const r1 = (v: number | null, d = 1) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);
const growth = (cur: number | null, prev: number | null) => (cur == null || prev == null || !(prev > 0) ? null : cur / prev - 1);
const cr = (v: number) => "₹" + Math.round(Math.abs(v)).toLocaleString("en-IN") + " crore";
const pct = (v: number) => Math.round(v * 100) + "%";
export const fyLabel = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);

export function profitReality(pl: Table | undefined, bs: Table | undefined, cf: Table | undefined, lender: boolean, maxYears = 8): ProfitReality {
  const T = THRESHOLDS;
  const periods = (pl?.periods ?? []).slice(-maxYears - 1);   // one extra year gives the first shown year something to grow from
  const all: PrYear[] = periods.map((p, i) => {
    const prev = i > 0 ? periods[i - 1] : null;
    const revenue = lender ? at(pl, "total_income", p) ?? at(pl, "revenue", p) : at(pl, "revenue", p);
    const prevRevenue = prev ? (lender ? at(pl, "total_income", prev) ?? at(pl, "revenue", prev) : at(pl, "revenue", prev)) : null;
    const np = at(pl, "net_profit", p), pbt = at(pl, "profit_before_tax", p), tax = at(pl, "tax", p);
    const exc = at(pl, "exceptional_items", p), disc = at(pl, "discontinued_profit", p), oi = at(pl, "other_income", p);
    const cfo = at(cf, "operating", p), fcf = at(cf, "free_cash_flow", p);
    const haveRate = pbt != null && pbt > 0 && tax != null;
    const taxRate = haveRate ? Math.min(T.taxCap, Math.max(T.taxFloor, tax / pbt)) : T.taxDefault;
    const excAT = exc == null ? null : exc * (1 - taxRate);
    const oiShare = !lender && oi != null && pbt != null && pbt > 0 ? oi / pbt : null;
    const oiAdj = oiShare != null && oiShare > T.otherIncomeShare ? (oi! - T.otherIncomeShare * pbt!) * (1 - taxRate) : null;
    const normalized = np == null ? null : np - (disc ?? 0) - (excAT ?? 0) - (oiAdj ?? 0);
    const cfoToProfit = !lender && cfo != null && np != null && np > 0 ? cfo / np : null;
    const fcfToProfit = !lender && fcf != null && np != null && np > 0 ? fcf / np : null;
    const excPbt = exc != null && pbt ? Math.abs(exc) / Math.abs(pbt) : null;
    const excNet = exc != null && np ? Math.abs(exc) / Math.abs(np) : null;
    const discNet = disc != null && np ? Math.abs(disc) / Math.abs(np) : null;
    const pg = growth(np, at(pl, "net_profit", prev ?? ""));
    const cg = prev == null ? null : (() => { const c0 = at(cf, "operating", prev); return c0 != null && c0 > 0 && cfo != null ? cfo / c0 - 1 : c0 != null && c0 <= 0 && cfo != null && cfo <= c0 ? -1 : null; })();
    const rg = growth(revenue, prevRevenue);
    const recG = lender || !prev ? null : growth(at(bs, "receivables", p), at(bs, "receivables", prev));
    const invG = lender || !prev ? null : growth(at(bs, "inventories", p), at(bs, "inventories", prev));
    const recGap = recG != null && rg != null ? (recG - rg) * 100 : null, invGap = invG != null && rg != null ? (invG - rg) * 100 : null;
    return {
      period: p, revenue, netProfit: np, cfo: lender ? null : cfo, fcf: lender ? null : fcf, taxRate, taxRateAssumed: !haveRate,
      exceptional: exc, discontinued: disc, otherIncome: oi, pretax: pbt, exceptionalAfterTax: excAT == null ? null : r1(excAT, 0),
      otherIncomeShare: r1(oiShare == null ? null : oiShare * 100), otherIncomeAdjustment: oiAdj == null ? null : r1(oiAdj, 0),
      normalized: r1(normalized, 0),
      cfoToProfit: r1(cfoToProfit, 2), fcfToProfit: r1(fcfToProfit, 2), cashGap: cfoToProfit != null && cfoToProfit < T.cashConversionMin,
      exceptionalPctPretax: r1(excPbt == null ? null : excPbt * 100, 0), exceptionalPctNet: r1(excNet == null ? null : excNet * 100, 0),
      discontinuedPctNet: r1(discNet == null ? null : discNet * 100, 0),
      oneOffFlag: (excPbt != null && excPbt >= T.oneOffShare) || (excNet != null && excNet >= T.oneOffShare) || (discNet != null && discNet >= T.oneOffShare),
      profitGrowth: r1(pg == null ? null : pg * 100), cfoGrowth: r1(cg == null ? null : cg * 100),
      profitNoCash: !lender && pg != null && pg >= T.profitJump && cg != null && cg < T.cashFlat,
      revenueGrowth: r1(rg == null ? null : rg * 100), receivablesGrowth: r1(recG == null ? null : recG * 100), inventoryGrowth: r1(invG == null ? null : invG * 100),
      receivablesGap: r1(recGap), inventoryGap: r1(invGap),
      receivablesFlag: recGap != null && recGap >= T.workingCapitalGap, inventoryFlag: invGap != null && invGap >= T.workingCapitalGap,
    };
  });
  const years = all.slice(-maxYears);
  // A year with no data at all is dropped, so the table does not fill up with empty columns.
  const shown = years.filter((y) => y.netProfit != null || y.cfo != null);
  const out: ProfitReality = { years: shown, lender, verdict: null, rules: [], findings: [], cumulative: null, gapYears: 0, gapEvaluated: 0, headline: null, notes: [] };
  if (!shown.length) return out;

  const last = shown[shown.length - 1], prevY = shown.length > 1 ? shown[shown.length - 2] : null;
  const rules: Rule[] = [], findings: { sev: number; t: string }[] = [];

  // Cash backing over the last five years
  const five = shown.slice(-5).filter((y) => y.netProfit != null && y.cfo != null);
  const na = (key: string, text: string, why: string): Rule => ({ key, text, status: "na", detail: why });
  const cashTxt = "Five-year operating cash flow is at least 80% of five-year profit";
  if (lender) {
    out.notes.push("This is a lender (bank or NBFC). Its loans and deposits sit inside operating cash flow, so cash conversion and working-capital tests are not shown. The one-off and normalized-profit checks still apply.");
    rules.push(na("cash5", cashTxt, "Skipped for lenders"), na("gaps", "No more than one year with cash flow below 80% of profit", "Skipped for lenders"), na("nocash", "Profit did not jump while operating cash flow stayed flat", "Skipped for lenders"), na("wc", "Receivables and inventory are not outgrowing sales", "Skipped for lenders"));
  } else {
    if (five.length >= 3) {
      const cfo = five.reduce((a, y) => a + (y.cfo as number), 0), profit = five.reduce((a, y) => a + (y.netProfit as number), 0);
      out.cumulative = { years: five.length, cfo: Math.round(cfo), profit: Math.round(profit), ratio: profit > 0 ? r1(cfo / profit, 2) : null };
      if (profit > 0) {
        const ratio = cfo / profit, st: Status = ratio >= T.cashConversionMin ? "ok" : ratio >= 0.5 ? "warn" : "flag";
        rules.push({ key: "cash5", text: cashTxt, status: st, detail: `${five.length}-year operating cash flow ${cr(cfo)} against profit ${cr(profit)} (${pct(ratio)}).` });
        if (st !== "ok") findings.push({ sev: st === "flag" ? 3 : 2, t: `Over ${five.length} years the company turned ${pct(ratio)} of its profit into operating cash (${cr(cfo)} of ${cr(profit)}).` });
      } else rules.push(na("cash5", cashTxt, "Total profit over the period is not positive, so the ratio has no meaning"));
    } else rules.push(na("cash5", cashTxt, "Fewer than three years with both profit and cash flow"));

    const ev = shown.filter((y) => y.cfoToProfit != null), gaps = ev.filter((y) => y.cashGap).length;
    out.gapYears = gaps; out.gapEvaluated = ev.length;
    const gapTxt = "No more than one year with operating cash flow below 80% of profit";
    if (ev.length >= 3) {
      const st: Status = gaps <= 1 ? "ok" : gaps === 2 ? "warn" : "flag";
      rules.push({ key: "gaps", text: gapTxt, status: st, detail: `${gaps} of ${ev.length} profitable years fell below 80%.` });
      if (st !== "ok") findings.push({ sev: st === "flag" ? 3 : 2, t: `Operating cash flow was below 80% of profit in ${gaps} of ${ev.length} profitable years, so the gap between earnings and cash keeps repeating.` });
    } else rules.push(na("gaps", gapTxt, "Fewer than three profitable years with cash flow data"));

    const nc = shown.filter((y) => y.profitNoCash);
    const ncTxt = "Profit did not jump while operating cash flow stayed flat (latest year)";
    if (last.profitGrowth != null && last.cfoGrowth != null) {
      rules.push({ key: "nocash", text: ncTxt, status: last.profitNoCash ? "flag" : "ok", detail: `Net profit ${last.profitGrowth > 0 ? "+" : ""}${last.profitGrowth}%, operating cash flow ${last.cfoGrowth > 0 ? "+" : ""}${last.cfoGrowth}% in ${fyLabel(last.period)}.` });
      if (last.profitNoCash) out.headline = `Profit rose but cash did not: net profit grew ${last.profitGrowth}% in ${fyLabel(last.period)} while operating cash flow ${last.cfoGrowth < 0 ? "fell " + Math.abs(last.cfoGrowth) + "%" : "grew only " + last.cfoGrowth + "%"}.`;
    } else rules.push(na("nocash", ncTxt, "Needs profit and cash flow for the last two years, with positive profit and cash flow in the earlier year"));
    for (const y of nc) if (y !== last) findings.push({ sev: 1, t: `In ${fyLabel(y.period)} profit rose ${y.profitGrowth}% while operating cash flow did not keep up (${y.cfoGrowth}%).` });

    const wcTxt = "Receivables and inventory are not outgrowing sales by 10 points or more (latest year or two years running)";
    const runs = (f: (y: PrYear) => boolean) => !!prevY && f(last) && f(prevY);
    const wcData = shown.some((y) => y.receivablesGap != null || y.inventoryGap != null);
    if (wcData) {
      const lf = last.receivablesFlag || last.inventoryFlag, two = runs((y) => y.receivablesFlag) || runs((y) => y.inventoryFlag);
      const st: Status = two ? "flag" : lf ? "warn" : "ok";
      rules.push({ key: "wc", text: wcTxt, status: st, detail: st === "ok" ? "Neither grew 10 or more points faster than revenue in the latest year." : two ? "At least one of them outgrew sales by 10 points or more two years running." : "At least one of them outgrew sales by 10 points or more in the latest year." });
      if (last.receivablesFlag) findings.push({ sev: two ? 3 : 2, t: `Receivables grew ${last.receivablesGrowth}% in ${fyLabel(last.period)} against revenue growth of ${last.revenueGrowth}%: the company is collecting from customers more slowly or selling more on credit.` });
      if (last.inventoryFlag) findings.push({ sev: two ? 3 : 2, t: `Inventory grew ${last.inventoryGrowth}% in ${fyLabel(last.period)} against revenue growth of ${last.revenueGrowth}%: stock is piling up faster than it sells.` });
    } else rules.push(na("wc", wcTxt, "Receivables and inventory are not reported for enough years"));
  }
  if (out.headline) findings.push({ sev: 4, t: out.headline });

  // Normalized profit (works for lenders too, except the other-income step)
  const gapTxt = "Normalized profit is within 15% of reported profit in the latest year (30% or more is flagged)";
  if (last.netProfit != null && last.normalized != null && last.netProfit > 0) {
    const d = (last.netProfit - last.normalized) / last.netProfit, st: Status = Math.abs(d) < 0.15 ? "ok" : Math.abs(d) < 0.3 ? "warn" : "flag";
    rules.push({ key: "norm", text: gapTxt, status: st, detail: `Reported ${cr(last.netProfit)}, normalized ${last.normalized < 0 ? "−" : ""}${cr(last.normalized)} (${d >= 0 ? "" : "+"}${pct(d)} ${d >= 0 ? "lower" : "higher"}).` });
    if (st !== "ok") findings.push({ sev: st === "flag" ? 3 : 2, t: `Stripping out one-offs${last.otherIncomeAdjustment ? " and unusually high other income" : ""}, ${fyLabel(last.period)} profit would be about ${last.normalized < 0 ? "a loss of " : ""}${cr(last.normalized)} instead of the reported ${cr(last.netProfit)}.` });
  } else rules.push(na("norm", gapTxt, "Latest-year profit is missing or not positive"));

  const recent = shown.slice(-5), oneOffs = recent.filter((y) => y.oneOffFlag);
  const ooTxt = "One-off items reach 15% of profit in no more than one of the last five years";
  if (recent.some((y) => y.exceptional != null || y.discontinued != null)) {
    const st: Status = oneOffs.length <= 1 ? "ok" : oneOffs.length === 2 ? "warn" : "flag";
    rules.push({ key: "oneoff", text: ooTxt, status: st, detail: `${oneOffs.length} of the last ${recent.length} years had exceptional or discontinued items at 15% or more of profit.` });
    if (st !== "ok") findings.push({ sev: st === "flag" ? 3 : 2, t: `Exceptional or discontinued items were 15% or more of profit in ${oneOffs.length} of the last ${recent.length} years (${oneOffs.map((y) => fyLabel(y.period)).join(", ")}). "One-off" items that keep coming back are part of the normal picture.` });
  } else rules.push(na("oneoff", ooTxt, "No exceptional or discontinued items are reported"));
  if (last.oneOffFlag && !findings.some((f) => /One-off|Stripping|Exceptional/.test(f.t))) {
    const bits = [last.discontinuedPctNet != null && last.discontinuedPctNet >= 15 ? `discontinued operations ${last.discontinuedPctNet}% of net profit` : "", last.exceptionalPctPretax != null && last.exceptionalPctPretax >= 15 ? `exceptional items ${last.exceptionalPctPretax}% of pre-tax profit` : ""].filter(Boolean);
    if (bits.length) findings.push({ sev: 2, t: `${fyLabel(last.period)} includes one-off profit or loss: ${bits.join(" and ")}.` });
  }

  out.rules = rules;
  out.findings = findings.sort((a, b) => b.sev - a.sev).slice(0, 4).map((f) => f.t);
  const usable = rules.filter((r) => r.status !== "na");
  const flags = usable.filter((r) => r.status === "flag").length, warns = usable.filter((r) => r.status === "warn").length;
  const need = lender ? 1 : 3;
  if (usable.length >= need) out.verdict = flags >= 2 || rules.some((r) => r.key === "nocash" && r.status === "flag") ? "Needs a closer look" : flags === 1 || warns >= 2 ? "Mixed" : "Strong";
  if (last.taxRateAssumed && (last.exceptional != null || last.otherIncomeAdjustment != null)) out.notes.push(`A tax rate of ${pct(T.taxDefault)} was assumed for ${fyLabel(last.period)} because the company's own effective rate could not be worked out.`);
  return out;
}
