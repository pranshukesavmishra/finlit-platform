/** DuPont analysis and the margin story, worked out from the company's own statements (no new data needed).
 *  ROE = net margin x asset turnover x equity multiplier. Every figure uses the same year-end balance sheet, so the three factors
 *  multiply back to exactly net profit over equity. The five-factor version splits net margin into tax burden, interest burden and EBIT margin. */
import type { Table } from "./api";

export type DupontYear = {
  period: string; netMargin: number | null; turnover: number | null; multiplier: number | null; roe: number | null;
  taxBurden: number | null; interestBurden: number | null; ebitMargin: number | null;   // five-factor (not for lenders)
  underlyingMargin: number | null; flag: string | null;                                  // net margin without discontinued operations; why a year is unusual
};
export type Factor = { key: "netMargin" | "turnover" | "multiplier"; label: string; first: number | null; last: number | null; changePct: number | null; verdict: "up" | "down" | "flat"; shareOfMove: number | null };
export type Dupont = { years: DupontYear[]; lender: boolean; factors: Factor[]; roeFirst: number | null; roeLast: number | null; from: string | null; to: string | null; words: string[] };

const at = (t: Table | undefined, key: string, p: string): number | null => {
  const i = t?.periods.indexOf(p) ?? -1, v = i >= 0 ? t?.rows[key]?.[i] : null;
  return v == null || !Number.isFinite(v) ? null : v;
};
const div = (a: number | null, b: number | null) => (a == null || b == null || b === 0 ? null : a / b);
const r2 = (v: number | null, d = 2) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);

export function dupont(pl: Table | undefined, bs: Table | undefined, lender: boolean, maxYears = 8): Dupont {
  const periods = (pl?.periods ?? []).filter((p) => bs?.periods.includes(p)).slice(-maxYears);
  const years: DupontYear[] = periods.map((p) => {
    const sales = lender ? at(pl, "total_income", p) ?? at(pl, "revenue", p) : at(pl, "revenue", p);
    const np = at(pl, "net_profit", p), pbt = at(pl, "profit_before_tax", p), fin = at(pl, "finance_costs", p), disc = at(pl, "discontinued_profit", p), exc = at(pl, "exceptional_items", p);
    const assets = at(bs, "total_assets", p), equity = at(bs, "total_equity", p);
    const ebit = pbt != null && fin != null ? pbt + fin : null;
    const eqOk = equity != null && equity > 0 ? equity : null;
    const nm = div(np, sales), tu = div(sales, assets), em = div(assets, eqOk), roe = div(np, eqOk);
    let flag: string | null = null;
    if (disc != null && np && Math.abs(disc) / Math.abs(np) >= 0.15) flag = `Profit includes ₹${Math.round(Math.abs(disc)).toLocaleString("en-IN")} crore from discontinued operations, so this year's margin is not the business's usual level.`;
    else if (exc != null && pbt && Math.abs(exc) / Math.abs(pbt) >= 0.25) flag = `One-off items are ${Math.round((Math.abs(exc) / Math.abs(pbt)) * 100)}% of pre-tax profit this year.`;
    return {
      period: p, netMargin: r2(nm == null ? null : nm * 100), turnover: r2(tu), multiplier: r2(em), roe: r2(roe == null ? null : roe * 100),
      taxBurden: lender ? null : r2(div(np, pbt)), interestBurden: lender ? null : r2(div(pbt, ebit)), ebitMargin: lender ? null : r2(div(ebit, sales) == null ? null : (div(ebit, sales) as number) * 100),
      underlyingMargin: disc != null && disc !== 0 && sales ? r2(((np ?? 0) - disc) / sales * 100) : null, flag,
    };
  });
  const usable = years.filter((y) => y.roe != null && y.netMargin != null && y.turnover != null && y.multiplier != null);
  const a = usable[0], b = usable[usable.length - 1];
  const factors: Factor[] = [];
  let words: string[] = [];
  if (a && b && a !== b) {
    const keys: [Factor["key"], string][] = [["netMargin", "Net profit / revenue"], ["turnover", "Revenue / total assets"], ["multiplier", "Total assets / total equity"]];
    const positive = [a, b].every((y) => (y.netMargin as number) > 0 && (y.roe as number) > 0);
    const total = positive ? Math.log((b.roe as number) / (a.roe as number)) : null;
    for (const [k, label] of keys) {
      const f = a[k] as number, l = b[k] as number, rel = f ? (l / f - 1) * 100 : null;
      factors.push({ key: k, label, first: f, last: l, changePct: r2(rel, 1), verdict: rel == null || Math.abs(rel) < 3 ? "flat" : rel > 0 ? "up" : "down",
        shareOfMove: total != null && Math.abs(total) > 0.02 && f > 0 && l > 0 ? r2((Math.log(l / f) / total) * 100, 0) : null });
    }
    const v = (k: Factor["key"]) => factors.find((f) => f.key === k)!.verdict;
    const w = (k: Factor["key"], name: string) => (v(k) === "flat" ? `${name} was about the same` : `${name} ${v(k) === "up" ? "rose" : "fell"}`);
    const roeMove = (b.roe as number) - (a.roe as number);
    words = [`From ${a.period} to ${b.period}: ${w("netMargin", "net margin")}, ${w("turnover", "asset turnover")} and ${w("multiplier", "the equity multiplier")}.`,
      Math.abs(roeMove) < 1 ? `Return on equity was broadly stable (${a.roe}% to ${b.roe}%).` : `Return on equity ${roeMove > 0 ? "rose" : "fell"} from ${a.roe}% to ${b.roe}%.`];
    if (v("multiplier") === "up" && roeMove > 0 && v("netMargin") !== "up") words.push("Part of the higher return comes from using more borrowed or other people's money, not from earning more on each ₹100 of sales.");
    words.push("The equity multiplier is total assets over equity: it reflects all liabilities and the balance-sheet structure, not only borrowing.");
  }
  return { years, lender, factors, roeFirst: a?.roe ?? null, roeLast: b?.roe ?? null, from: a && b && a !== b ? a.period : null, to: a && b && a !== b ? b.period : null, words };
}

/** The margin story: each margin over the last few years with the change from the first to the last year in basis points
 *  (1 percentage point = 100 bps), plus findings such as "gross margin recovered but operating margin did not". */
export type MarginRow = { key: string; label: string; values: (number | null)[]; bps: number | null };
export function marginTrend(periods: string[], rows: Record<string, (number | null)[]>, show = 4): { periods: string[]; rows: MarginRow[]; findings: string[] } {
  const n = periods.length, from = Math.max(0, n - show), ps = periods.slice(from);
  const defs: [string, string][] = [["gross_margin", "Gross margin"], ["operating_margin", "Operating margin"], ["ebitda_margin", "EBITDA margin"], ["ebit_margin", "EBIT margin"], ["pretax_margin", "Pre-tax margin"], ["net_margin", "Net margin"]];
  const out: MarginRow[] = defs.filter(([k]) => rows[k]?.some((v) => v != null)).map(([k, label]) => {
    const values = (rows[k] ?? []).slice(from), a = values.find((v) => v != null), b = [...values].reverse().find((v) => v != null);
    return { key: k, label, values, bps: a != null && b != null && values.filter((v) => v != null).length > 1 ? Math.round((b - a) * 100) : null };
  });
  const find = (k: string) => out.find((r) => r.key === k);
  const findings: string[] = [], g = find("gross_margin"), o = find("operating_margin"), nm = find("net_margin");
  if (g?.bps != null && o?.bps != null && g.bps > 50 && o.bps < -50) findings.push(`Gross margin improved (${g.bps > 0 ? "+" : ""}${g.bps} bps) but operating margin fell (${o.bps} bps): costs below the gross profit line grew faster than sales. The expense lines are worth a look.`);
  if (g?.bps != null && o?.bps != null && g.bps < -50 && o.bps > 50) findings.push(`Operating margin improved (+${o.bps} bps) even though gross margin fell (${g.bps} bps): the company saved on costs below gross profit.`);
  if (nm) {
    const vals = nm.values.filter((v): v is number => v != null);
    if (vals.length >= 3) { const sorted = [...vals].sort((x, y) => x - y), med = sorted[sorted.length >> 1]; const i = nm.values.findIndex((v) => v != null && med && v > med * 1.4 && v - med > 4);
      if (i >= 0) findings.push(`Net margin in ${ps[i]} (${nm.values[i]}%) stands well above the other years. Check for one-off or discontinued-operations profit before treating it as the usual level.`); }
  }
  return { periods: ps, rows: out, findings };
}

/** "53% of ROE move" under a component card. Nothing when the share cannot be worked out (loss year, ROE barely moved). A negative share means the factor pushed against the move. */
export function shareText(f: Pick<Factor, "shareOfMove">): string {
  if (f.shareOfMove == null) return "";
  return f.shareOfMove < 0 ? `offsets ${Math.abs(f.shareOfMove)}% of the ROE move` : `${f.shareOfMove}% of the ROE move`;
}

/** The plain-words summary under the DuPont block. Describes what moved; never says what to do. Empty when there are not two comparable years. */
export function dupontSummary(d: Dupont): string {
  if (!d.from || !d.to || d.roeFirst == null || d.roeLast == null || d.factors.length < 3) return "";
  const v = (k: Factor["key"]) => d.factors.find((f) => f.key === k)?.verdict ?? "flat";
  const w = (k: Factor["key"], name: string) => (v(k) === "flat" ? `${name} was about the same` : `${name} ${v(k) === "up" ? "rose" : "fell"}`);
  const move = d.roeLast - d.roeFirst;
  const roe = Math.abs(move) < 1 ? `ROE was broadly stable, from ${d.roeFirst.toFixed(2)}% to ${d.roeLast.toFixed(2)}%` : `ROE ${move > 0 ? "rose" : "fell"} from ${d.roeFirst.toFixed(2)}% to ${d.roeLast.toFixed(2)}%`;
  return `From ${d.from} to ${d.to}, ${roe}. ${w("netMargin", "Net profit margin")}, ${w("turnover", "asset turnover")} and ${w("multiplier", "the equity multiplier")}.`;
}
