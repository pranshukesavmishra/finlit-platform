// Fund Compare, head to head: two funds of one category over 1, 3, 5 or 10 years (see backend/finlit/mf_compare.py). API types and hooks, the page's
// URL state, which periods each pair can show, and the plain-English line under each card. Pure helpers are tested in mfCompare.test.ts.
// The lines state what the NAVs did, never what to buy: no "better", no "should".
import { useQuery } from "@tanstack/react-query";
import { apiGet, ApiError } from "./api";
import { DEMO } from "./demo";
import { MINUS, dateIN, nf } from "./format";
import type { Facts, FactVal } from "./mf";

export type Period = "1Y" | "3Y" | "5Y" | "10Y";
export type Card = "returns" | "risk" | "consistency" | "costs";
export type Plan = "Direct" | "Regular";
export const PERIODS: Period[] = ["1Y", "3Y", "5Y", "10Y"];
export const PERIOD_MONTHS: Record<Period, number> = { "1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120 };
export const CARDS: { id: Card; title: string; sub: string }[] = [
  { id: "returns", title: "Returns", sub: "CAGR & rolling returns" },
  { id: "risk", title: "Risk", sub: "Volatility & drawdown" },
  { id: "consistency", title: "Consistency", sub: "Winning periods" },
  { id: "costs", title: "Costs & benchmark", sub: "Expense ratio & alpha" },
];
export const DEFAULT_PERIOD: Period = "5Y";
/** Shown first when the address names no category (the owner's example); any wording of it, see backend mf_compare.cat_key. */
export const DEFAULT_CATEGORY = /^flexi\s*cap/i;

// ------------------------------------------------------------------------------------------------ API types

export type CompareCategory = { name: string; short: string; group: string; direct: number; regular: number; variants?: string[] };
export type CategoryList = Facts & { categories: CompareCategory[] };
export type CompareFundItem = { code: number; name: string; amc: string; launch: string | null; r1y: number | null; r5y: number | null };
export type FundList = Facts & { category: string; plan: Plan; funds: CompareFundItem[] };

export type Side = "a" | "b" | "cat";
export type Why = { value: number | null; why: string | null };
export type Points = { t: string[]; v: number[] };
export type RollStats = { min: number | null; minAt: string | null; median: number | null; max: number | null; maxAt: string | null; positive: number | null; count: number; why: string | null };
export type RetBlock = { value: number | null; from: string | null; to: string | null; growth: number | null; why: string | null };
export type RiskBlock = {
  volatility: Why; downside: Why; sharpe: Why;
  maxDrawdown: Why & { peak: string | null; trough: string | null; recovered: string | null };
  worstMonth: Why & { month: string | null }; bestMonth: Why & { month: string | null };
};
export type Tally = { a: number; b: number; ties: number; n: number; why: string | null };
export type FundMeta = {
  code: number; name: string; amc: string; category: string; plan: string; option: string; nav: number | null; navDate: string | null;
  history: { source: "amfi" | "mirror" | null; from: string | null; to: string | null; note: string | null };
};
export type CostFacts = { ter: FactVal; terPct: number | null; aum: FactVal; exitLoad: FactVal; benchmark: FactVal; managers: FactVal; riskometer: FactVal; launchDate: FactVal };
export type HeadToHead = Facts & {
  period: Period; months: number; from: string | null; to: string | null; pending: boolean;
  funds: { a: FundMeta; b: FundMeta }; why: { a: string | null; b: string | null }; planNote: string | null;
  category: { name: string; short: string; plan: Plan; members: number | null; eligible: number | null; membersAtStart: number | null; note: string | null; why: string | null; pending: boolean; survivorship: string };
  returns: {
    kind: "cagr" | "absolute"; funds: Record<Side, RetBlock>;
    rolling: { months: number; label: string; kind: "cagr" | "absolute"; funds: Record<Side, RollStats>; chart: Partial<Record<Side, Points>> };
    growth: Partial<Record<Side, Points>>;
  };
  risk: { funds: Record<Side, RiskBlock>; riskFree: number; note: string };
  consistency: {
    window: { months: number; label: string }; rolling: Tally; months: Tally;
    years: Tally & { rows: { year: number; a: number | null; b: number | null; cat: number | null }[] };
    vsCategory: Record<"a" | "b", { beat: number | null; n: number; pct: number | null; why: string | null }>;
  };
  costs: { funds: { a: CostFacts; b: CostFacts }; alpha: Record<"a" | "b", Why>; alphaBasis: string; alphaNote: string };
};

// ------------------------------------------------------------------------------------------------ URL state

export type H2HState = { category: string; plan: Plan; a: number; b: number; period: Period; card: Card };
const code = (s: string | null) => { const n = Number(s); return Number.isInteger(n) && n > 0 && n < 1e7 ? n : 0; };

/** The head-to-head compare is the default view of /funds/compare; the 2 to 4 scheme compare is the one with ?ids= in the address. */
export const isMultiCompare = (sp: URLSearchParams) => sp.has("ids");

export function parseH2H(sp: URLSearchParams): H2HState {
  const p = sp.get("period"), c = sp.get("card");
  const a = code(sp.get("a")), b = code(sp.get("b"));
  return {
    category: (sp.get("category") || "").slice(0, 160), plan: sp.get("plan") === "Regular" ? "Regular" : "Direct", a, b: b === a ? 0 : b,
    period: PERIODS.includes(p as Period) ? (p as Period) : DEFAULT_PERIOD, card: CARDS.some((x) => x.id === c) ? (c as Card) : "returns",
  };
}
/** Only what differs from the defaults goes into the address. */
export function h2hToParams(s: H2HState): URLSearchParams {
  const p = new URLSearchParams();
  if (s.category) p.set("category", s.category);
  if (s.plan !== "Direct") p.set("plan", s.plan);
  if (s.a) p.set("a", String(s.a));
  if (s.b) p.set("b", String(s.b));
  if (s.period !== DEFAULT_PERIOD) p.set("period", s.period);
  if (s.card !== "returns") p.set("card", s.card);
  return p;
}
export const h2hPath = (a: number, b: number, period: Period) => `/api/mf-compare?a=${a}&b=${b}&period=${period}`;

/** The category entry the address means: AMFI words some categories two ways ("Equity Scheme -" / "Equity Schemes -"), and the server lists both
 *  as one entry named after the commoner wording, so an older link with the other wording still finds it. Without a category: Flexi Cap. */
export function pickCategory(cats: CompareCategory[] | undefined, wanted: string): CompareCategory | undefined {
  if (!cats) return undefined;
  if (wanted) return cats.find((c) => c.name === wanted || c.variants?.includes(wanted));
  return cats.find((c) => /^equity/i.test(c.group) && DEFAULT_CATEGORY.test(c.short));
}

// ------------------------------------------------------------------------------------------------ names, periods

const PLAN_TAIL = /\s*[-–]?\s*\b(?:(?:direct|regular)(?:\s+plan)?|growth(?:\s+(?:option|plan))?)\s*$/i;
/** "Parag Parikh Flexi Cap Fund - Direct Plan - Growth" -> "Parag Parikh Flexi Cap Fund": the plan and option are the same for both funds and shown once.
 *  Only trailing plan and option words go ("ICICI Prudential Growth Fund - Series 3" and "... - Equity Plan" keep their names). */
export function shortName(name: string): string {
  let s = name.trim(), prev = "";
  while (s !== prev) { prev = s; const t = s.replace(PLAN_TAIL, "").trim(); if (t) s = t; }
  return s.replace(/\s*[-–]\s*$/, "") || name;
}

const addMonths = (iso: string, months: number) => {
  const [y, m, d] = iso.split("-").map(Number);
  const t = y * 12 + (m - 1) + months, yy = Math.floor(t / 12), mm = t - yy * 12;
  const last = new Date(Date.UTC(yy, mm + 1, 0)).getUTCDate();
  return `${yy}-${String(mm + 1).padStart(2, "0")}-${String(Math.min(d, last)).padStart(2, "0")}`;
};
/** Whether a period can be shown for the chosen pair, from each fund's launch date (AMFI's scheme master) and the data date. A fund whose launch
 *  date is not loaded is not held back here: the server says why if its NAV history turns out shorter. */
export function periodBlock(period: Period, funds: (Pick<CompareFundItem, "name" | "launch"> | undefined)[], dataDate: string | null | undefined): string | null {
  if (!dataDate) return null;
  const start = addMonths(dataDate, -PERIOD_MONTHS[period]);
  const young = funds.filter((f): f is Pick<CompareFundItem, "name" | "launch"> => !!f && !!f.launch && f.launch > start);
  if (!young.length) return null;
  const f = young.sort((x, y) => (x.launch! < y.launch! ? 1 : -1))[0];
  return `${shortName(f.name)} was launched on ${dateIN(f.launch!)}, less than ${periodWords(period)} before ${dateIN(dataDate)}.`;
}
export const periodWords = (p: Period) => (p === "1Y" ? "1 year" : `${PERIOD_MONTHS[p] / 12} years`);

// ------------------------------------------------------------------------------------------------ number text

export const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : (v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
export const signedPct = (v: number | null | undefined, d = 1) => (v == null ? "—" : (v < 0 ? MINUS : v > 0 ? "+" : "") + nf(Math.abs(v), d) + "%");
export const rupees = (v: number | null | undefined) => (v == null ? "—" : "₹" + Math.round(v).toLocaleString("en-IN"));
export const points = (v: number) => `${nf(Math.abs(v), 1)} point${Math.abs(v) >= 0.95 && Math.abs(v) < 1.05 ? "" : "s"}`;
/** A share like "64% (788 of 1,230)". */
export const share = (k: number, n: number) => (n ? `${Math.round((100 * k) / n)}% (${k.toLocaleString("en-IN")} of ${n.toLocaleString("en-IN")})` : "—");

// ------------------------------------------------------------------------------------------------ the plain-English lines (facts only, never advice)

type Names = { a: string; b: string };
const over = (d: Pick<HeadToHead, "period">) => `Over ${periodWords(d.period)}`;
/** How a gap between two figures reads: "about the same" below `same` points, "slightly" below `slight` points. Falls are measured in tens of
 *  percent, volatility in single digits, so each has its own scale. */
const size = (gap: number, same: number, slight: number) => (Math.abs(gap) < same ? "same" : Math.abs(gap) < slight ? "slightly " : "");
const FALL = [0.5, 3] as const, SWING = [0.25, 1] as const;

export function returnsLine(d: Pick<HeadToHead, "period" | "returns" | "risk">, n: Names): string {
  const ra = d.returns.funds.a.value, rb = d.returns.funds.b.value;
  if (ra == null || rb == null) return `${over(d)}, the two funds cannot be compared: ${ra == null ? n.a : n.b} has no figure for the whole period.`;
  const perYear = d.returns.kind === "cagr";
  const unit = perYear ? " a year" : "";
  const gap = ra - rb;
  let s = Math.abs(gap) < 0.05
    ? `${over(d)}, both funds returned the same${unit} (${pct(ra)}).`
    : `${over(d)}, ${gap > 0 ? n.a : n.b} returned ${points(gap)}${unit} more than ${gap > 0 ? n.b : n.a} (${pct(gap > 0 ? ra : rb)} against ${pct(gap > 0 ? rb : ra)}${perYear ? " a year" : ""}).`;
  const da = d.risk.funds.a.maxDrawdown.value, db = d.risk.funds.b.maxDrawdown.value;
  if (da != null && db != null && Math.abs(gap) >= 0.05) {
    const w = gap > 0 ? da : db, l = gap > 0 ? db : da;   // the worst fall of the fund that returned more, and of the other
    const g = size(w - l, ...FALL);
    s = s.slice(0, -1) + (g === "same" ? `, with about the same worst fall (${pct(w)} against ${pct(l)}).` : `, with a ${g}${w < l ? "deeper" : "shallower"} worst fall (${pct(w)} against ${pct(l)}).`);
  }
  return s;
}

export function riskLine(d: Pick<HeadToHead, "period" | "risk">, n: Names): string {
  const va = d.risk.funds.a.volatility.value, vb = d.risk.funds.b.volatility.value;
  const da = d.risk.funds.a.maxDrawdown.value, db = d.risk.funds.b.maxDrawdown.value;
  if (va == null || vb == null) return `${over(d)}, the risk of the two funds cannot be compared: ${va == null ? n.a : n.b} has too little NAV history for the period.`;
  const g = size(va - vb, ...SWING);
  let s = g === "same" ? `${over(d)}, the NAVs of both funds swung about as much (volatility ${pct(va)} and ${pct(vb)} a year)`
    : `${over(d)}, ${va < vb ? n.a : n.b}'s NAV swung ${g}less than ${va < vb ? n.b : n.a}'s (volatility ${pct(Math.min(va, vb))} against ${pct(Math.max(va, vb))} a year)`;
  if (da != null && db != null) {
    const f = size(da - db, ...FALL);
    s += f === "same" ? `, and their worst falls were about as deep (${pct(da)} and ${pct(db)}).` : `; ${da < db ? n.a : n.b} had the ${f}deeper worst fall (${pct(Math.min(da, db))} against ${pct(Math.max(da, db))}).`;
  } else s += ".";
  return s;
}

export function consistencyLine(d: Pick<HeadToHead, "period" | "consistency">, n: Names): string {
  const c = d.consistency, r = c.rolling;
  if (!r.n) return `${over(d)}, there is no whole ${c.window.label} window in which both funds have a figure, so the two cannot be compared this way.`;
  const lead = r.a >= r.b ? "a" : "b", k = lead === "a" ? r.a : r.b;
  let s = r.a === r.b ? `${over(d)}, each fund was ahead in half of the ${c.window.label} windows (${r.a.toLocaleString("en-IN")} each).`
    : `${over(d)}, ${n[lead]} was ahead in ${share(k, r.n)} of the ${c.window.label} windows`;
  if (r.a !== r.b) {
    const y = c.years;
    s += y.n ? ` and in ${y[lead]} of ${y.n} calendar year${y.n > 1 ? "s" : ""}.` : c.months.n ? ` and in ${c.months[lead]} of ${c.months.n} calendar months.` : ".";
  }
  return s;
}

export function costsLine(d: Pick<HeadToHead, "period" | "costs">, n: Names): string {
  const ta = d.costs.funds.a.terPct, tb = d.costs.funds.b.terPct;
  const parts: string[] = [];
  if (ta != null && tb != null) {
    parts.push(Math.abs(ta - tb) < 0.005 ? `Both funds charge the same expense ratio (${nf(ta, 2)}% a year).`
      : `${ta < tb ? n.a : n.b} charges ${nf(Math.abs(ta - tb), 2)} percentage points a year less in expenses (${nf(Math.min(ta, tb), 2)}% against ${nf(Math.max(ta, tb), 2)}%).`);
  }
  const al = d.costs.alpha;
  const rel = (v: number) => (Math.abs(v) < 0.05 ? "the same as" : `${points(v)} ${v > 0 ? "more" : "less"} than`);
  if (al.a.value != null && al.b.value != null) parts.push(`${over(d)}, ${n.a} returned ${rel(al.a.value)} the category average a year, ${n.b} ${rel(al.b.value)} it.`);
  else if (al.a.value != null || al.b.value != null) { const k = al.a.value != null ? "a" : "b"; parts.push(`${over(d)}, ${n[k]} returned ${rel(al[k].value!)} the category average a year.`); }
  return parts.join(" ") || "The expense ratios and the category average are not available for these two funds yet.";
}

/** The one-line summary on each "Compare what matters" card once the numbers are in (figures only). */
export function cardTeaser(card: Card, d: HeadToHead): string | null {
  switch (card) {
    case "returns": { const a = d.returns.funds.a.value, b = d.returns.funds.b.value; return a == null || b == null ? null : `${pct(a)} vs ${pct(b)}${d.returns.kind === "cagr" ? " a year" : ""}`; }
    case "risk": { const a = d.risk.funds.a.maxDrawdown.value, b = d.risk.funds.b.maxDrawdown.value; return a == null || b == null ? null : `Worst fall ${pct(a)} vs ${pct(b)}`; }
    case "consistency": { const r = d.consistency.rolling; return r.n ? `A ahead in ${Math.round((100 * r.a) / r.n)}% of windows` : null; }
    case "costs": { const a = d.costs.funds.a.terPct, b = d.costs.funds.b.terPct; return a == null || b == null ? null : `TER ${nf(a, 2)}% vs ${nf(b, 2)}%`; }
  }
}

// ------------------------------------------------------------------------------------------------ data hooks

async function get<T>(path: string): Promise<T> {
  if (DEMO) throw new ApiError(503, { status: "demo", detail: "Fund Compare needs the live site: this preview holds a few schemes, not whole categories." });
  return apiGet<T>(path);
}
const HOUR = 3_600_000;
export const useCompareCategories = () => useQuery<CategoryList, ApiError>({ queryKey: ["mfc", "cats"], queryFn: () => get<CategoryList>("/api/mf-compare/categories"), staleTime: HOUR, retry: 1 });
export const useCompareFunds = (category: string, plan: Plan) =>
  useQuery<FundList, ApiError>({
    queryKey: ["mfc", "funds", category, plan], queryFn: () => get<FundList>(`/api/mf-compare/funds?${new URLSearchParams({ category, plan })}`),
    enabled: !!category, staleTime: HOUR, retry: 1,
  });
export const useHeadToHead = (a: number, b: number, period: Period) =>
  useQuery<HeadToHead, ApiError>({
    queryKey: ["mfc", "h2h", a, b, period], queryFn: () => get<HeadToHead>(h2hPath(a, b, period)), enabled: a > 0 && b > 0 && a !== b,
    staleTime: 300_000, placeholderData: (prev) => prev, retry: (k, e) => e.status >= 500 && k < 2,
    refetchInterval: (q) => (q.state.data?.pending ? 4000 : false),   // the category average is being worked out on the server: ask again shortly
  });

// ------------------------------------------------------------------------------------------------ chart curve, table highlights

/** An SVG path through the points that is smooth but never overshoots (monotone cubic, Fritsch-Carlson): a curve never dips below a low or above a high
 *  that is not in the data, so a smoothed NAV line still tells the truth about its peaks and troughs. */
export function smoothPath(xy: readonly (readonly [number, number])[]): string {
  const n = xy.length, f = (v: number) => v.toFixed(1);
  if (n === 0) return "";
  if (n < 3) return xy.map((p, i) => `${i ? "L" : "M"}${f(p[0])},${f(p[1])}`).join("");
  const dx: number[] = [], m: number[] = [], t: number[] = new Array(n).fill(0);
  for (let i = 0; i < n - 1; i++) { dx[i] = xy[i + 1][0] - xy[i][0] || 1e-9; m[i] = (xy[i + 1][1] - xy[i][1]) / dx[i]; }
  t[0] = m[0]; t[n - 1] = m[n - 2];
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
    if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
  }
  let d = `M${f(xy[0][0])},${f(xy[0][1])}`;
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3;
    d += `C${f(xy[i][0] + h)},${f(xy[i][1] + t[i] * h)} ${f(xy[i + 1][0] - h)},${f(xy[i + 1][1] - t[i + 1] * h)} ${f(xy[i + 1][0])},${f(xy[i + 1][1])}`;
  }
  return d;
}

/** Which of the two funds has the higher ("high") or lower ("low") figure; null when either is missing or the two are level. Only a fact about the
 *  past (used to shade a cell), never a recommendation. */
export function leader(a: number | null | undefined, b: number | null | undefined, dir: "high" | "low"): "a" | "b" | null {
  if (a == null || b == null || Math.abs(a - b) < 0.005) return null;
  return (a > b) === (dir === "high") ? "a" : "b";
}
