/** Revenue-to-Cash Intelligence: how efficiently a company's sales turn into cash, worked out only from its own yearly statements
 *  (annual P&L revenue and net profit, annual balance sheet receivables / inventory / fixed assets, annual cash flow operating, capex and free cash flow).
 *  Annual is compared with annual only: the quarterly tables are never read, so annual and trailing-twelve-month figures cannot be mixed.
 *  Every rule compares the figures as they are DISPLAYED (one decimal), so a card never says "exceeds 20 points" beside "20.0".
 *  Wording is descriptive. It never advises, and it never says a company is dishonest. Rules, thresholds and caveats: docs/REVENUE-CASH.md. */
import type { Table } from "./api";
import { MINUS, nf } from "./format";

export type Severity = "Critical" | "High" | "Moderate" | "Positive";
export type Status = "Needs attention" | "Watch" | "Healthy" | "Improving";
export type GroupId = "standard" | "capital" | "project" | "seasonal" | "trading";
export type RuleId = "ocf_negative" | "weak_consistency" | "sales_not_cash" | "receivables" | "inventory" | "debtor_days" | "fcf_negative" | "cum_ocf_profit" | "improving";

export const RULE_ORDER: RuleId[] = ["ocf_negative", "sales_not_cash", "weak_consistency", "receivables", "inventory", "debtor_days", "fcf_negative", "cum_ocf_profit", "improving"];

/** Thresholds before any industry adjustment. */
export const BASE = {
  weakOcfMargin: 5,          // % : OCF margin below this, three years running, is "weak cash conversion consistency"
  gapPp: 20,                 // percentage points by which receivables / inventory growth may exceed revenue growth
  debtorDaysRise: 20,        // % rise in debtor days
  streak: 3,                 // years for the persistent rules
  longYears: 5,              // years for the long-term cash-conversion rule
  capexIntensity: 10,        // % of revenue: "high capex"
  fixedAssetsRise: 10,       // % rise in fixed assets + CWIP: "rising fixed assets"
  healthyMargin: 5,          // % : at or above this the headline reads Healthy
} as const;

export type Adjust = { weakOcfMargin: number; gapPp: number; debtorDaysRise: number; softened: RuleId[]; caveat: string | null };
export const GROUPS: Record<GroupId, { label: string; words: RegExp | null; adjust: Adjust }> = {
  standard: { label: "General", words: null, adjust: { weakOcfMargin: BASE.weakOcfMargin, gapPp: BASE.gapPp, debtorDaysRise: BASE.debtorDaysRise, softened: [], caveat: null } },
  capital: {
    label: "Capital-intensive",
    words: /power|utilit|electric|telecom|steel|iron|cement|metal|mining|coal|oil|gas|petro|refiner|shipping|port|airline|aviation|airport|road|railway|fertili[sz]er|chemical|paper|aluminium|copper|infrastructure asset|hotel/i,
    adjust: { weakOcfMargin: BASE.weakOcfMargin, gapPp: BASE.gapPp, debtorDaysRise: BASE.debtorDaysRise, softened: ["fcf_negative"], caveat: "Capital-intensive businesses often show negative free cash flow while they build capacity, so that warning is shown one level lower." },
  },
  project: {
    label: "Project and EPC",
    words: /construct|engineering|epc|infrastructure|capital goods|industrial manufacturing|defen[cs]e|shipbuild|real estate|realty|housing develop|contract/i,
    adjust: { weakOcfMargin: 3, gapPp: 30, debtorDaysRise: 30, softened: ["weak_consistency", "receivables", "inventory", "debtor_days"], caveat: "Project and EPC businesses bill in milestones, so receivables, inventory and cash can swing from year to year. Thresholds are softened (receivables, inventory 30 points, debtor days 30%, weak margin 3%) and those warnings are shown one level lower." },
  },
  seasonal: {
    label: "Seasonal",
    words: /sugar|agri|tea|coffee|plantation|seed|fertili[sz]er|pesticide|agrochem|cotton|textile|apparel|consumer durable|air condition|fan|cooler|beverage|ice cream|fireworks|education/i,
    adjust: { weakOcfMargin: BASE.weakOcfMargin, gapPp: 30, debtorDaysRise: 30, softened: ["receivables", "inventory", "debtor_days"], caveat: "Seasonal businesses carry stock and receivables that depend on the time of year the books close. Receivables and inventory thresholds are softened to 30 points, debtor days to 30%, and those warnings are shown one level lower." },
  },
  trading: {
    label: "Trading and distribution",
    words: /trading|trader|distribut|wholesale|retail|jewel|gems|commodit|e-?commerce|supermarket|pharma distribution|import/i,
    adjust: { weakOcfMargin: 2, gapPp: 30, debtorDaysRise: 20, softened: ["weak_consistency", "inventory"], caveat: "Trading businesses run on thin margins and large stock turns. The weak-margin line is lowered to 2%, the inventory threshold to 30 points, and those warnings are shown one level lower." },
  },
};
/** Checked in this order; the first group whose words match the sector, industry or sub-industry wins. */
const GROUP_ORDER: GroupId[] = ["project", "trading", "seasonal", "capital"];
export const industryGroup = (...labels: (string | null | undefined)[]): GroupId => {
  const text = labels.filter(Boolean).join(" | ");
  return GROUP_ORDER.find((g) => GROUPS[g].words!.test(text)) ?? "standard";
};
/** Lenders: the site's isBank flag, plus insurers (their cash flow statement carries policyholder money the same way). */
export const isLenderLike = (isBank: boolean, ...labels: (string | null | undefined)[]): boolean => isBank || /\b(banks?|nbfc|insurance|insurer|housing finance)\b/i.test(labels.filter(Boolean).join(" | "));

export type Year = {
  period: string; revenue: number | null; ocf: number | null; netProfit: number | null; fcf: number | null; capex: number | null;
  revenueGrowth: number | null; ocfMargin: number | null;
  receivablesGrowth: number | null; receivablesBasis: Basis | null; inventoryGrowth: number | null; inventoryBasis: Basis | null;
  receivablesGap: number | null; inventoryGap: number | null;
  debtorDays: number | null; debtorDaysBefore: number | null; debtorDaysChange: number | null; fixedAssetsRise: number | null;
};
export type Basis = "average" | "year-end";
export type Warning = {
  id: RuleId; text: string; severity: Severity; baseSeverity: Severity; why: string; investigate: string | null;
  pattern: string; note: string | null;
};
export type RevenueCash = {
  state: "ok" | "lender" | "nodata";
  group: GroupId; caveat: string | null; benchmark: string;
  years: Year[]; latest: Year | null;
  status: Status | null; statusLine: string;
  warnings: Warning[]; reading: string; next: string; notes: string[];
  notEvaluated: string[];
};

const at = (t: Table | undefined, key: string, p: string): number | null => {
  const i = t?.periods.indexOf(p) ?? -1, v = i >= 0 ? t?.rows[key]?.[i] : null;
  return v == null || !Number.isFinite(v) ? null : v;
};
/** One decimal, never "-0". */
export const r1 = (v: number): number => Math.round(v * 10) / 10 || 0;
const rn = (v: number | null): number | null => (v == null ? null : r1(v));

/** "−6.4%", "0.0%": rounds first, so a value that rounds to zero carries no minus sign. */
export function fmtPct(v: number | null | undefined, d = 1, plus = false): string {
  if (v == null || !Number.isFinite(v)) return "n/a";
  const k = Math.round(Math.abs(v) * 10 ** d) / 10 ** d;
  return (k === 0 ? "" : v < 0 ? MINUS : plus ? "+" : "") + nf(k, d) + "%";
}
/** "−₹312 crore", "₹1,234 crore", "₹4.5 crore". */
export function fmtCr(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "n/a";
  const d = Math.abs(v) < 10 ? 1 : 0, k = Math.round(Math.abs(v) * 10 ** d) / 10 ** d;
  return (k === 0 ? "" : v < 0 ? MINUS : "") + "₹" + nf(k, d) + " crore";
}
const pp = (v: number) => nf(Math.abs(r1(v)), 1);

/** Growth of a balance-sheet item in year i: average balance (this year's and last year's year-end) against the earlier average when three year-ends exist, otherwise year-end against year-end. */
function balanceGrowth(vals: (number | null)[], i: number): { g: number | null; basis: Basis | null } {
  const c = vals[i], p1 = vals[i - 1], p2 = vals[i - 2];
  if (c != null && p1 != null && p2 != null && (p1 + p2) / 2 > 0) return { g: ((c + p1) / 2 / ((p1 + p2) / 2) - 1) * 100, basis: "average" };
  if (c != null && p1 != null && p1 > 0) return { g: (c / p1 - 1) * 100, basis: "year-end" };
  return { g: null, basis: null };
}
/** Debtor days = receivables / revenue x 365, on average receivables when the three year-ends exist for both years compared, otherwise on year-end receivables for both. */
function debtorDaysPair(rec: (number | null)[], rev: (number | null)[], i: number): { now: number | null; before: number | null; basis: Basis | null } {
  const R = (j: number) => rev[j] != null && (rev[j] as number) > 0 ? (rev[j] as number) : null;
  const avgOk = [i, i - 1, i - 2].every((j) => rec[j] != null) && R(i) != null && R(i - 1) != null;
  if (avgOk) return { now: (((rec[i] as number) + (rec[i - 1] as number)) / 2 / (R(i) as number)) * 365, before: (((rec[i - 1] as number) + (rec[i - 2] as number)) / 2 / (R(i - 1) as number)) * 365, basis: "average" };
  if (rec[i] != null && rec[i - 1] != null && R(i) != null && R(i - 1) != null) return { now: ((rec[i] as number) / (R(i) as number)) * 365, before: ((rec[i - 1] as number) / (R(i - 1) as number)) * 365, basis: "year-end" };
  return { now: null, before: null, basis: null };
}

export function buildYears(pl: Table | undefined, bs: Table | undefined, cf: Table | undefined, window = 8): Year[] {
  const P = (pl?.periods ?? []).slice(-window);
  const col = (t: Table | undefined, k: string) => P.map((p) => at(t, k, p));
  const rev = col(pl, "revenue"), np = col(pl, "net_profit"), ocf = col(cf, "operating"), capexR = col(cf, "capex"), fcfR = col(cf, "free_cash_flow");
  const rec = col(bs, "receivables"), inv = col(bs, "inventories"), fa = col(bs, "fixed_assets"), cw = col(bs, "cwip");
  return P.map((period, i): Year => {
    const revenue = rev[i], prev = i > 0 ? rev[i - 1] : null;
    const revG = revenue != null && prev != null && prev > 0 ? (revenue / prev - 1) * 100 : null;
    const margin = revenue != null && revenue > 0 && ocf[i] != null ? ((ocf[i] as number) / revenue) * 100 : null;
    const fcf = fcfR[i] ?? (ocf[i] != null && capexR[i] != null ? (ocf[i] as number) + (capexR[i] as number) : null);   // capex is stored negative
    const rg = balanceGrowth(rec, i), ig = balanceGrowth(inv, i);
    const dd = debtorDaysPair(rec, rev, i);
    const gross = (j: number) => (fa[j] != null || cw[j] != null ? (fa[j] ?? 0) + (cw[j] ?? 0) : null);
    const g0 = i > 0 ? gross(i - 1) : null, g1 = gross(i);
    const gR = rn(revG);
    return {
      period, revenue, ocf: ocf[i], netProfit: np[i], fcf, capex: capexR[i],
      revenueGrowth: gR, ocfMargin: rn(margin),
      receivablesGrowth: rn(rg.g), receivablesBasis: rg.basis, inventoryGrowth: rn(ig.g), inventoryBasis: ig.basis,
      receivablesGap: rg.g != null && gR != null ? r1(r1(rg.g) - gR) : null, inventoryGap: ig.g != null && gR != null ? r1(r1(ig.g) - gR) : null,
      debtorDays: dd.now == null ? null : r1(dd.now), debtorDaysBefore: dd.before == null ? null : r1(dd.before), debtorDaysChange: dd.now != null && dd.before != null && dd.before > 0 ? r1((dd.now / dd.before - 1) * 100) : null,
      fixedAssetsRise: g0 != null && g1 != null && g0 > 0 ? r1((g1 / g0 - 1) * 100) : null,
    };
  });
}

const down = (s: Severity): Severity => (s === "Critical" ? "High" : s === "High" ? "Moderate" : s);

/** How often the per-year condition held, in the years that can be judged. */
function pattern(all: Year[], test: (y: Year) => boolean | null, window = 5): { n: number; m: number; text: string; single: boolean } {
  const ys = all.slice(-window).map(test).filter((v): v is boolean => v != null);
  const n = ys.filter(Boolean).length, m = ys.length;
  if (m < BASE.streak) return { n, m, text: `Based on only ${m} year${m === 1 ? "" : "s"} of data`, single: false };
  const latestOnly = n === 1 && test(all[all.length - 1]) === true;
  return { n, m, text: latestOnly ? "This year only" : `${n} of the last ${m} years`, single: latestOnly };
}

export function revenueCash(pl: Table | undefined, bs: Table | undefined, cf: Table | undefined, opts: { lender: boolean; labels?: (string | null | undefined)[] }): RevenueCash {
  const group = industryGroup(...(opts.labels ?? [])), adj = GROUPS[group].adjust;
  const out: RevenueCash = { state: "ok", group, caveat: adj.caveat, benchmark: "Industry benchmark not available", years: [], latest: null, status: null, statusLine: "", warnings: [], reading: "", next: "", notes: [], notEvaluated: [] };
  if (opts.lender) return { ...out, state: "lender", caveat: null, notes: ["Operating cash flow and working capital do not mean the same for a bank, NBFC or insurer: deposits, loans and policyholder money run through the cash flow statement."] };
  const all = buildYears(pl, bs, cf);
  const years = all.slice(-5).filter((y) => y.revenue != null || y.ocf != null);
  const last = all[all.length - 1];
  if (!last || last.revenue == null || !years.length) return { ...out, state: "nodata" };
  out.years = all.slice(-5); out.latest = last;
  const L = last;
  const win = all.slice(-5);

  // Headline
  const m = L.ocfMargin;
  const improving3 = improvement(win);
  if (m == null) { out.status = null; out.statusLine = `Operating cash flow was not reported for ${L.period}.`; }
  else if (m < 0) { out.status = "Needs attention"; out.statusLine = "Operating cash flow was negative."; }
  else if (m < BASE.healthyMargin) { out.status = improving3 ? "Improving" : "Watch"; out.statusLine = improving3 ? "Low, but higher each year for three years." : `Positive but under ${BASE.healthyMargin}% of revenue.`; }
  else { out.status = "Healthy"; out.statusLine = `At or above ${BASE.healthyMargin}% of revenue.`; }

  const ws: Warning[] = [];
  const push = (id: RuleId, base: Severity, text: string, why: string, investigate: string | null, p: { text: string }, extra: string | null = null, lower = false) => {
    let sev = lower ? down(base) : base, note = extra;
    if (adj.softened.includes(id) && base !== "Positive") { if (!lower) sev = down(base); note = [note, `Shown one level lower for a ${GROUPS[group].label.toLowerCase()} business.`].filter(Boolean).join(" "); }
    ws.push({ id, text, severity: sev, baseSeverity: base, why, investigate, pattern: p.text, note });
  };

  // 1 + 3: operating cash flow against revenue
  if (L.ocfMargin != null && L.ocfMargin < 0 && L.ocf != null && L.revenue != null) {
    push("ocf_negative", "Critical", "Revenue is not generating positive operating cash",
      `${L.period} operating cash flow was ${fmtCr(L.ocf)} on revenue of ${fmtCr(L.revenue)}, an OCF margin of ${fmtPct(L.ocfMargin)}.`,
      "Where did the cash go: receivables, inventory, or payments to suppliers?", pattern(all, (y) => (y.ocfMargin == null ? null : y.ocfMargin < 0)));
  }
  if (L.revenueGrowth != null && L.revenueGrowth > 0 && L.ocf != null && L.ocfMargin != null && L.ocfMargin < 0) {
    push("sales_not_cash", "Critical", "Sales growth is not translating into cash",
      `Revenue grew ${fmtPct(L.revenueGrowth)} in ${L.period} while operating cash flow was ${fmtCr(L.ocf)}.`,
      "working capital requirements and customer collections", pattern(all, (y) => (y.revenueGrowth == null || y.ocfMargin == null ? null : y.revenueGrowth > 0 && y.ocfMargin != null && y.ocfMargin < 0)));
  }
  // 2: weak for three years running
  const t3 = all.slice(-BASE.streak);
  if (t3.length === BASE.streak && t3.every((y) => y.ocfMargin != null && y.ocfMargin < adj.weakOcfMargin)) {
    push("weak_consistency", "High", "Weak cash conversion consistency",
      `OCF margin was under ${fmtPct(adj.weakOcfMargin, 0)} in each of the last 3 years: ${t3.map((y) => `${y.period} ${fmtPct(y.ocfMargin)}`).join(", ")}.`,
      "the operating cash flow trend and what is held back in working capital", pattern(all, (y) => (y.ocfMargin == null ? null : y.ocfMargin < adj.weakOcfMargin)));
  }
  // 4 + 5: receivables / inventory outgrowing revenue
  const gapRule = (id: RuleId, label: string, g: number | null, gap: number | null, basis: Basis | null, key: "receivablesGap" | "inventoryGap", inv: string, hint: string) => {
    if (g == null || gap == null || L.revenueGrowth == null || !(gap > adj.gapPp)) return;
    push(id, "High", inv, `${label} grew ${fmtPct(g)}, exceeding revenue growth (${fmtPct(L.revenueGrowth)}) by ${pp(gap)} percentage points.`, hint,
      pattern(all, (y) => (y[key] == null ? null : (y[key] as number) > adj.gapPp)), basis ? `Measured on ${basis} balances.` : null);
  };
  gapRule("receivables", "Receivables", L.receivablesGrowth, L.receivablesGap, L.receivablesBasis, "receivablesGap", "Customer collection risk", "customer collections and debtor days");
  gapRule("inventory", "Inventory", L.inventoryGrowth, L.inventoryGap, L.inventoryBasis, "inventoryGap", "Inventory accumulation risk", "inventory days and how fast the stock is selling");
  // 6: debtor days
  if (L.debtorDaysChange != null && L.debtorDaysChange > adj.debtorDaysRise && L.debtorDays != null && L.debtorDaysBefore != null) {
    const before = L.debtorDaysBefore;
    push("debtor_days", "High", "Collection efficiency deteriorating",
      `Debtor days rose from about ${nf(before, 0)} to ${nf(L.debtorDays, 0)} days in ${L.period} (${fmtPct(L.debtorDaysChange, 1, true)}).`,
      "payment terms given to customers and overdue balances", pattern(all, (y) => (y.debtorDaysChange == null ? null : y.debtorDaysChange > adj.debtorDaysRise)));
  }
  // 7: free cash flow negative three years running (expansion downgrade)
  if (t3.length === BASE.streak && t3.every((y) => y.fcf != null && y.fcf < 0)) {
    const expansion = expanding(L);
    let extra: string | null = null;
    if (expansion) { extra = `Shown one level lower: capital spending was ${fmtPct(expansion.intensity)} of revenue, fixed assets and work in progress rose ${fmtPct(expansion.fa)} and revenue grew ${fmtPct(L.revenueGrowth)} in ${L.period}, which can look like planned expansion.`; }
    push("fcf_negative", "High", "Expansion may require external funding",
      `Free cash flow was negative in each of the last 3 years: ${t3.map((y) => `${y.period} ${fmtCr(y.fcf)}`).join(", ")}.`,
      "how the spending is funded: borrowings, new equity or cash on hand", pattern(all, (y) => (y.fcf == null ? null : y.fcf < 0)), extra, !!expansion);
  }
  // 8: five years of operating cash flow against five years of profit
  const five = all.slice(-BASE.longYears);
  if (five.length === BASE.longYears && five.every((y) => y.ocf != null && y.netProfit != null)) {
    const o = five.reduce((a, y) => a + (y.ocf as number), 0), n = five.reduce((a, y) => a + (y.netProfit as number), 0);
    if (n > 0 && o < n) push("cum_ocf_profit", "High", "Earnings have weak cash backing",
      `Over ${five[0].period} to ${L.period} operating cash flow totalled ${fmtCr(o)} against net profit of ${fmtCr(n)}, ${fmtPct((o / n) * 100, 0)} of profit.`,
      "the gap between reported profit and operating cash flow, year by year", { text: "5-year view" });
  } else out.notEvaluated.push("Cumulative cash against profit needs five years of both figures.");
  // 9: improvement
  if (improving3) {
    const ys = win.slice(-4);
    push("improving", "Positive", "Cash conversion improving",
      `OCF margin rose in each of the last 3 years: ${ys.map((y) => `${y.period} ${fmtPct(y.ocfMargin)}`).join(" → ")}.`, null, { text: "3 years running" });
  }
  if (t3.length < BASE.streak || t3.some((y) => y.ocfMargin == null)) out.notEvaluated.push("Persistent-pattern rules need three years of reported data.");

  out.warnings = ws.sort((a, b) => sevRank(a.severity) - sevRank(b.severity) || RULE_ORDER.indexOf(a.id) - RULE_ORDER.indexOf(b.id));
  const text = describe(L, out.warnings);
  out.reading = text.reading; out.next = text.next;
  if (group !== "standard") out.notes.push(GROUPS[group].label + ": " + (adj.caveat ?? ""));
  return out;
}

const sevRank = (s: Severity) => ({ Critical: 0, High: 1, Moderate: 2, Positive: 3 })[s];

/** Three year-on-year rises in OCF margin (four margins in a row, each higher than the one before). */
function improvement(win: Year[]): boolean {
  const ys = win.slice(-4);
  return ys.length === 4 && ys.every((y) => y.ocfMargin != null) && ys.every((y, i) => i === 0 || (y.ocfMargin as number) > (ys[i - 1].ocfMargin as number));
}
/** Planned expansion: capital spending of at least 10% of revenue, fixed assets plus work in progress up at least 10%, and revenue growing. */
function expanding(L: Year): { intensity: number; fa: number } | null {
  if (L.capex == null || L.revenue == null || !(L.revenue > 0) || L.fixedAssetsRise == null || L.revenueGrowth == null) return null;
  const intensity = r1((Math.abs(L.capex) / L.revenue) * 100);
  return intensity >= BASE.capexIntensity && L.fixedAssetsRise >= BASE.fixedAssetsRise && L.revenueGrowth > 0 ? { intensity, fa: L.fixedAssetsRise } : null;
}

function describe(L: Year, ws: Warning[]): { reading: string; next: string } {
  const has = (id: RuleId) => ws.some((w) => w.id === id);
  const g = L.revenueGrowth, m = L.ocfMargin;
  const rev = g == null ? "" : g >= 10 ? "Revenue expansion is strong" : g > 0 ? "Revenue is growing" : g < 0 ? "Revenue fell" : "Revenue was flat";
  const cash = m == null ? "" : m < BASE.healthyMargin ? "cash conversion is weak" : "cash conversion is healthy";
  const parts: string[] = [];
  if (rev && cash) parts.push(`${rev}${m != null && m < BASE.healthyMargin && g != null && g > 0 ? ", but " : ", and "}${cash}.`);
  else if (cash) parts.push(cash[0].toUpperCase() + cash.slice(1) + ".");
  if (m != null && m < 0) parts.push(`Operating cash flow was negative in ${L.period}.`);
  const rec = has("receivables") || has("debtor_days"), inv = has("inventory");
  if (rec || inv) {
    const what = rec && inv ? "receivables and inventory" : rec ? "receivables" : "inventory";
    const rising = (!rec || (L.receivablesGrowth ?? 0) > 0) && (!inv || (L.inventoryGrowth ?? 0) > 0);
    parts.push(rising ? `Rising ${what} may be contributing to working capital pressure.` : `${cap(what)} growing faster than revenue may be contributing to working capital pressure.`);
  }
  if (has("cum_ocf_profit")) parts.push("Over five years, reported profit has been only partly matched by operating cash.");
  if (has("fcf_negative")) parts.push("Spending on assets has exceeded operating cash for three years.");
  if (has("improving")) parts.push("Operating cash margin has risen for three years running.");
  if (!ws.length) parts.push("None of the rules used here was triggered.");
  const next: string[] = [];
  const cashy = ws.some((w) => ["ocf_negative", "sales_not_cash", "weak_consistency", "cum_ocf_profit"].includes(w.id));
  if (rec || cashy) next.push("debtor days");
  if (inv || cashy) next.push("inventory days");
  if (cashy || has("improving")) next.push("operating cash flow trend", "cash flow from operations over the last five years");
  if (has("fcf_negative")) next.push("capital spending and how it is funded");
  const items = [...new Set(next)];
  const nextText = items.length ? cap(joinList(items)) + "." : "The cash flow statement over the last five years, to see the pattern behind the headline figure.";
  return { reading: parts.join(" "), next: nextText };
}
const joinList = (a: string[]) => (a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]);
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** For the tooltip beside an indicator: which balances the growth was measured on. */
export const basisNote = (b: Basis | null): string =>
  b === "average" ? "Measured on average balances: the mean of this year's and last year's year-end figure, against the same mean a year earlier." : b === "year-end" ? "Measured on year-end balances, because the earlier years needed for an average were not reported." : "Not available: the balance sheet item or the earlier year is missing.";
