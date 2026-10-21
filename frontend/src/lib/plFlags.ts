/** P&L divergence flags: eight situations where revenue and profit tell different stories, worked out from a company's own reported
 *  yearly and quarterly profit-and-loss series (₹ crore). Pure and side-effect free. The same rules are in backend/finlit/plflags.py (the
 *  automatic alerts); both are checked against the shared cases in fixtures/plFlags.cases.json so they cannot drift apart.
 *
 *  Principles
 *  - A flag is information ("worth a closer look"), never a verdict or advice. It says what the reported numbers did, not why.
 *  - Missing data never makes a flag: a missing, non-finite or unaligned figure means that comparison is skipped.
 *  - Revenue growth needs a positive earlier revenue. Profit growth in per cent needs a positive earlier profit; on a zero or negative
 *    base only the direction (better or worse) is used, and the size tests (cases 1 and 5) are skipped, except a swing from a loss to a
 *    profit, which case 5 reports in words.
 *  - Comparisons are against the same period a year earlier (found by period end date, so a missing quarter cannot shift the match).
 *    Quarter on quarter is used only for case 1, as the founder's table says; quarter-on-quarter moves in other cases are mostly season.
 *  - A move smaller than DEAD_BAND per cent counts as flat, so rounding noise cannot create a flag.
 *  Judgement calls beyond the founder's table (each is a named constant below): case 1 also needs profit up at least MIN_PROFIT_JUMP per
 *  cent, otherwise 1% revenue growth against 4% profit growth would be "more than 3x"; case 4 reads "near zero" as up to NEAR_ZERO per cent.
 *  When one situation is a sharper version of another in the same period only the sharper one is shown (5 over 1 and 2, 4 over 3,
 *  8 over 2 and 3 for quarters), so a member gets one message, not three. */
import type { Table } from "./api";

export const T = {
  deadBand: 0.5,          // per cent: smaller moves count as flat
  ratio: 3,               // case 1: profit growth more than 3x revenue growth
  minProfitJump: 10,      // case 1: ...and profit up at least this much in per cent
  revenueSharp: 20,       // case 4: revenue growth above this
  nearZero: 2,            // case 4: profit growth at or below this counts as barely growing
  profitSharp: 30,        // case 5: profit growth above this
  flatBand: 5,            // case 5: revenue growth within -5..+5
  runQuarters: 2,         // case 8: opposite directions for this many quarters in a row
} as const;

export type Severity = "watch" | "caution";
export type Scope = "annual" | "quarterly";
export type Basis = "yoy" | "qoq" | "run";
export type CaseNo = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
export type PlFlag = {
  case: CaseNo; id: string; severity: Severity; scope: Scope; basis: Basis;
  period: string;           // the latest period the flag is about, e.g. "FY26" or "Mar 2026"
  against: string;          // what it is compared with, e.g. "FY25"
  title: string; text: string; why: string;
  revenueGrowth: number | null; profitGrowth: number | null; operatingGrowth: number | null;
  rows: string[];           // P&L row keys to highlight
  periods: string[];        // period labels (column headers) to highlight
  key: string;              // unique per case + scope + period, also the alert de-duplication key
};
export type PlInput = { annual?: Table | null; quarterly?: Table | null };

export const CASES: Record<CaseNo, { id: string; title: string; severity: Severity; why: string }> = {
  1: { id: "profit_outgrows_revenue", title: "Profit is growing much faster than revenue", severity: "watch", why: "Profit can be lifted by one-off items or unusual cost savings." },
  2: { id: "revenue_down_profit_up", title: "Revenue fell while profit rose", severity: "watch", why: "Worth checking for one-off gains, cost cuts or a change in margins." },
  3: { id: "revenue_up_profit_down", title: "Revenue rose while profit fell", severity: "caution", why: "Costs may be rising faster than sales, or profitability may be weakening." },
  4: { id: "revenue_up_profit_flat", title: "Revenue rose sharply but profit did not follow", severity: "caution", why: "Growth that does not reach profit may be of lower quality." },
  5: { id: "profit_up_revenue_flat", title: "Profit rose sharply on flat revenue", severity: "watch", why: "Earnings may be leaning on non-operating gains or exceptional savings." },
  6: { id: "both_down", title: "Revenue and profit both fell", severity: "caution", why: "This can be a sign of a business slowdown." },
  7: { id: "net_up_operating_down", title: "Net profit rose while operating profit fell", severity: "watch", why: "Non-operating income or tax effects may be driving the earnings." },
  8: { id: "persistent_divergence", title: "Revenue and profit have moved in opposite directions for several quarters", severity: "caution", why: "A repeating gap can point to a structural change or unusual earnings." },
};

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const at = (t: Table | null | undefined, key: string, i: number): number | null => num(t?.rows?.[key]?.[i]);

// ---- dates and alignment
const day = (s: unknown): number | null => {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(s)) return null;
  const t = Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
  return Number.isFinite(t) ? t / 86400000 : null;
};
const RANGE = { year: [335, 395], quarter: [75, 105] } as const;
/** Index of the period that ended about one year (or one quarter) before period i, matched on period end dates; null if there is none. */
export function priorIndex(t: Table | null | undefined, i: number, back: "year" | "quarter"): number | null {
  const ends = t?.periodEnds;
  const cur = day(ends?.[i]);
  if (cur == null) return annualFallback(t, i, back);
  const [lo, hi] = RANGE[back], target = back === "year" ? 365 : 91;
  let best: number | null = null, bestD = Infinity;
  for (let j = 0; j < i; j++) {
    const e = day(ends?.[j]); if (e == null) continue;
    const d = cur - e;
    if (d >= lo && d <= hi && Math.abs(d - target) < bestD) { best = j; bestD = Math.abs(d - target); }
  }
  return best;
};
/** Yearly tables without end dates: FY26 follows FY25. Never used for quarters. */
function annualFallback(t: Table | null | undefined, i: number, back: "year" | "quarter"): number | null {
  if (back !== "year" || i < 1) return null;
  const a = /^FY(\d{2})$/.exec(t?.periods?.[i] ?? ""), b = /^FY(\d{2})$/.exec(t?.periods?.[i - 1] ?? "");
  return a && b && (+a[1] - +b[1] + 100) % 100 === 1 ? i - 1 : null;
}

// ---- growth helpers
type Move = { cur: number; prev: number; pct: number | null; dir: -1 | 0 | 1 };
/** Change from prev to cur. pct divides by the size of the earlier figure, so a loss that shrinks reads as an improvement; dir is the
 *  direction (flat inside the dead band). null when either figure is missing. */
export function move(cur: number | null, prev: number | null): Move | null {
  if (cur == null || prev == null) return null;
  if (prev === 0) return { cur, prev, pct: null, dir: cur > 0 ? 1 : cur < 0 ? -1 : 0 };
  const pct = ((cur - prev) / Math.abs(prev)) * 100;
  return { cur, prev, pct, dir: Math.abs(pct) < T.deadBand ? 0 : cur > prev ? 1 : -1 };
}
/** Revenue growth only exists against a positive earlier revenue. */
const revMove = (cur: number | null, prev: number | null) => (prev != null && prev > 0 ? move(cur, prev) : null);
/** Per-cent growth that is meaningful only on a positive earlier figure. */
const pctPos = (m: Move | null) => (m && m.prev > 0 ? m.pct : null);

const r1 = (v: number) => Math.round(v * 10) / 10;
const pc = (v: number) => `${r1(Math.abs(v)).toFixed(1)}%`;
const crore = (v: number) => "₹" + Math.round(Math.abs(v)).toLocaleString("en-IN") + " crore";
const verb = (m: Move) => (m.dir > 0 ? "rose" : m.dir < 0 ? "fell" : "was flat");
const money = (v: number) => (v < 0 ? "a loss of " : "a profit of ") + crore(v);

/** Net profit described in words, safe on negative and zero bases. */
function profitWords(m: Move): string {
  if (m.prev <= 0 || m.cur <= 0) {
    if (m.prev < 0 && m.cur > 0) return `net profit turned from ${money(m.prev)} to ${money(m.cur)}`;
    if (m.prev > 0 && m.cur < 0) return `net profit turned from ${money(m.prev)} to ${money(m.cur)}`;
    return `net result moved from ${m.prev === 0 ? "zero" : money(m.prev)} to ${m.cur === 0 ? "zero" : money(m.cur)}`;
  }
  return `net profit ${verb(m)} ${m.pct == null ? "" : pc(m.pct)}`.trim();
}

type Pair = { rev: Move | null; np: Move | null; op: Move | null };
function pairAt(t: Table, i: number, j: number): Pair {
  return { rev: revMove(at(t, "revenue", i), at(t, "revenue", j)), np: move(at(t, "net_profit", i), at(t, "net_profit", j)), op: move(at(t, "operating_profit", i), at(t, "operating_profit", j)) };
}

type Hit = { no: CaseNo; text: string };
/** Cases 1 to 7 for one pair of periods. */
function evaluate(p: Pair): Hit[] {
  const out: Hit[] = [];
  const { rev, np, op } = p;
  if (rev && np) {
    const rg = rev.pct, pg = pctPos(np);
    const flatRev = rg != null && rg >= -T.flatBand && rg <= T.flatBand;
    // 5: profit sharply up on flat revenue (a swing from a loss to a profit counts)
    const five = flatRev && ((pg != null && pg > T.profitSharp) || (np.prev < 0 && np.cur > 0));
    if (five) out.push({ no: 5, text: `Revenue was nearly flat (${rg! >= 0 ? "+" : "-"}${pc(rg!)}) while ${profitWords(np)}.` });
    // 1: profit growth more than 3x revenue growth (revenue growing, profit growth on a positive base)
    if (!five && rg != null && rg > T.flatBand && pg != null && pg >= T.minProfitJump && pg > T.ratio * rg)
      out.push({ no: 1, text: `Revenue grew ${pc(rg)} but net profit grew ${pc(pg)}, more than ${T.ratio} times as fast.` });
    // 2: revenue down, profit up (superseded by 5)
    if (!five && rev.dir < 0 && np.dir > 0) out.push({ no: 2, text: `Revenue ${verb(rev)} ${pc(rev.pct!)} while ${profitWords(np)}.` });
    // 4: revenue sharply up, profit barely moves or falls
    const barely = np.pct != null ? np.pct <= T.nearZero : np.cur <= 0;
    const four = rg != null && rg > T.revenueSharp && barely;
    if (four) out.push({ no: 4, text: `Revenue grew ${pc(rg!)} but ${profitWords(np)}.` });
    // 3: revenue up, profit down (superseded by 4)
    if (!four && rev.dir > 0 && np.dir < 0) out.push({ no: 3, text: `Revenue grew ${pc(rev.pct!)} while ${profitWords(np)}.` });
    // 6: both down
    if (rev.dir < 0 && np.dir < 0) out.push({ no: 6, text: `Revenue fell ${pc(rev.pct!)} and ${profitWords(np)}.` });
  }
  // 7: net profit up while operating profit down
  if (np && op && np.dir > 0 && op.dir < 0) out.push({ no: 7, text: `${profitWords(np)[0].toUpperCase() + profitWords(np).slice(1)}, while operating profit fell${op.pct != null && op.prev > 0 ? " " + pc(op.pct) : ""}.` });
  return out;
}

function build(no: CaseNo, scope: Scope, basis: Basis, t: Table, i: number, j: number, text: string, p: Pair | null, extraPeriods: string[] = []): PlFlag {
  const c = CASES[no], period = t.periods[i], against = t.periods[j];
  const rows = no === 7 ? ["net_profit", "operating_profit"] : ["revenue", "net_profit"];
  const periods = [period, against, ...extraPeriods].filter((x, k, a) => x && a.indexOf(x) === k);
  return {
    case: no, id: c.id, severity: c.severity, scope, basis, period, against, title: c.title, text: `${text} Compared with ${against}.`, why: c.why,
    revenueGrowth: p?.rev?.pct == null ? null : r1(p.rev.pct), profitGrowth: pctPos(p?.np ?? null) == null ? null : r1(pctPos(p!.np)!), operatingGrowth: pctPos(p?.op ?? null) == null ? null : r1(pctPos(p!.op)!),
    rows: rows.filter((k) => !!t.rows?.[k]), periods, key: `${no}:${scope}:${period}`,
  };
}

/** All flags for the latest annual and latest quarterly period. Empty when the data does not support any. */
export function plFlags(input: PlInput | null | undefined): PlFlag[] {
  const out: PlFlag[] = [];
  const a = input?.annual, q = input?.quarterly;
  if (a?.periods?.length) {
    const i = a.periods.length - 1, j = priorIndex(a, i, "year");
    if (j != null) { const p = pairAt(a, i, j); for (const h of evaluate(p)) out.push(build(h.no, "annual", "yoy", a, i, j, h.text, p)); }
  }
  if (q?.periods?.length) {
    const i = q.periods.length - 1, y = priorIndex(q, i, "year"), s = priorIndex(q, i, "quarter");
    if (y != null) { const p = pairAt(q, i, y); for (const h of evaluate(p)) out.push(build(h.no, "quarterly", "yoy", q, i, y, h.text, p)); }
    // case 1 only, quarter on quarter
    if (s != null) {
      const p = pairAt(q, i, s);
      const h = evaluate(p).find((x) => x.no === 1);   // when the year-on-year check already flagged case 1 for this quarter, dedupe keeps that one
      if (h) out.push(build(1, "quarterly", "qoq", q, i, s, h.text, p));
    }
    const run = divergenceRun(q);
    if (run && run.length >= T.runQuarters) {
      const last = run[0], first = run[run.length - 1];
      const names = run.slice().reverse().map((r) => q.periods[r.i]);
      const yago = run.map((r) => q.periods[r.j]);
      const words = run.every((r) => r.rev > 0) ? "Revenue rose while profit fell" : run.every((r) => r.rev < 0) ? "Revenue fell while profit rose" : "Revenue and profit moved in opposite directions";
      const f = build(8, "quarterly", "run", q, last.i, last.j, `${words} (each against the same quarter a year earlier) in ${run.length} quarters in a row, from ${q.periods[first.i]} to ${q.periods[last.i]}.`, pairAt(q, last.i, last.j), [...names, ...yago]);
      out.push(f);
    }
  }
  return dedupe(out);
}

type RunStep = { i: number; j: number; rev: number };
/** Latest quarters (newest first) in which revenue and net profit moved in opposite directions against the same quarter a year earlier,
 *  counted back without a gap. Each step must be one quarter earlier than the last one. */
export function divergenceRun(q: Table): RunStep[] | null {
  const steps: RunStep[] = [];
  let i: number | null = q.periods.length - 1;
  while (i != null && i >= 0) {
    const j = priorIndex(q, i, "year");
    if (j == null) break;
    const p = pairAt(q, i, j);
    if (!p.rev || !p.np || p.rev.dir === 0 || p.np.dir === 0 || p.rev.dir === p.np.dir) break;
    steps.push({ i, j, rev: p.rev.dir });
    i = priorIndex(q, i, "quarter");
  }
  return steps.length ? steps : null;
}

/** Keeps the sharper flag when two describe the same period: 8 over 2 and 3 (quarters), and one flag per case, scope and period. */
function dedupe(list: PlFlag[]): PlFlag[] {
  const seen = new Set<string>();
  const hasRun = list.some((f) => f.case === 8);
  const out = list.filter((f) => {
    if (hasRun && f.scope === "quarterly" && (f.case === 2 || f.case === 3) && f.basis === "yoy") return false;
    if (seen.has(f.key)) return false;
    seen.add(f.key); return true;
  });
  return out.sort((x, y) => x.case - y.case);
}

/** Highlight map for the table view: row key -> period labels, per scope. */
export function highlightMap(flags: PlFlag[], enabled: boolean = true): Record<Scope, Record<string, Set<string>>> {
  const m: Record<Scope, Record<string, Set<string>>> = { annual: {}, quarterly: {} };
  if (!enabled) return m;
  for (const f of flags) for (const r of f.rows) { const s = (m[f.scope][r] ??= new Set()); f.periods.forEach((p) => s.add(p)); }
  return m;
}
