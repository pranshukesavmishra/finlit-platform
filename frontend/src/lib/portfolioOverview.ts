// My portfolio tabs (Overview, Ratios, Financials): the bulk API's types and hook, and the pure logic behind the table: tab state in the address,
// the columns of each tab for each plan, sorting and filtering values, formatting, summary figures and the CSV. No React here (the table is
// components/PortfolioTabs.tsx). Information only, not investment advice: scores are descriptive, never a recommendation.
import { useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "./api";
import { MINUS, csvText, nf, capSize } from "./format";
import { marketCapText, scoreBand, type ScoreBand } from "./scoreBands";
import { LABEL_WORD, PRISM_PARTS, type PrismLabel } from "./scorePrism";

export type Model = "finlit" | "prism";
export type PlanName = "basic" | "silver" | "gold";
/** The score model a plan sees on this page: Silver the basic FinLit score, Gold only FinLit Prism. Basic sees none (the page is gated). */
export const modelFor = (plan: PlanName, admin = false): Model | null => (plan === "gold" || admin ? "prism" : plan === "silver" ? "finlit" : null);

export const MODEL_BANNER: Record<Model, string> = {
  prism: "Scores on this page use FinLit Prism, our advanced model: four fundamental parts (Fundamentals, Valuation, Quality, Risk) and two technical views (short and long term). Higher is better for the four parts; a high Risk score means lower risk.",
  finlit: "Scores on this page use the FinLit score (our basic model). Gold shows FinLit Prism, the advanced model.",
};

// ---------------------------------------------------------------------------------------------------- API shape (POST /api/portfolio/overview)

export type Fig = { value: number | null; period?: string | null; note?: string; why?: string };
export type PrismBlock = {
  state: "rated" | "provisional" | "not_rated" | "none"; final: number | null; label: string | null; status: string | null;
  parts: { fundamental: number | null; valuation: number | null; quality: number | null; risk: number | null } | null;
  shortTerm: { score: number; word: string } | null; longTerm: { score: number; word: string } | null; at: string | null; reason: string | null;
};
export type FinlitBlock = { overall: number | null; band: string | null; word: string | null; pillars: Record<"quality" | "growth" | "profitability" | "balance" | "technical", number | null> };
export type StatementCol = { available: boolean; why?: string; period: string | null; periodEnd: string | null } & Partial<Record<"revenue" | "other_income" | "operating_profit" | "finance_costs" | "net_profit" | "eps" | "tax_ratio", Fig>>;
export type Ready = {
  symbol: string; status: "ready"; name: string | null; sector: string | null; industry: string | null; isBank: boolean; basis: "consolidated" | "standalone" | null; reportAt: string | null;
  price: number | null; changePct: number | null; priceAsOf: string | null; marketCapCr: number | null;
  ratios: Record<"pe" | "pb" | "roe" | "dividend_yield" | "debt_to_equity", Fig>;
  financials: { year: StatementCol; quarter: StatementCol };
  finlit?: FinlitBlock; prism?: PrismBlock;
};
export type Waiting = { symbol: string; status: "preparing" | "unknown"; reason: string };
export type OverviewHolding = Ready | Waiting;
export type Overview = { model: Model; plan: PlanName; count: number; holdings: OverviewHolding[]; disclaimer: string };

export const isReady = (h: OverviewHolding | undefined): h is Ready => h?.status === "ready";

/** One call for the whole list (the server accepts up to 500). Asks again every 20 s while some company is still being prepared. */
export function useOverview(symbols: string[], enabled: boolean) {
  const key = symbols.join(",");
  return useQuery<Overview, ApiError>({
    queryKey: ["portfolio-overview", key],
    queryFn: () => apiSend<Overview>("POST", "/api/portfolio/overview", { symbols }),
    enabled: enabled && symbols.length > 0, retry: false, staleTime: 60_000,
    refetchInterval: (q) => (q.state.data?.holdings.some((h) => h.status === "preparing") ? 20_000 : false),
  });
}

// ---------------------------------------------------------------------------------------------------- tab state (address: ?tab=ratios&period=quarter)

export type Tab = "overview" | "ratios" | "financials";
export const TABS: { id: Tab; label: string }[] = [{ id: "overview", label: "Overview" }, { id: "ratios", label: "Ratios" }, { id: "financials", label: "Financials" }];
export const parseTab = (v: string | null | undefined): Tab => (TABS.some((t) => t.id === v) ? (v as Tab) : "overview");
export type Period = "year" | "quarter";
export const parsePeriod = (v: string | null | undefined): Period => (v === "quarter" ? "quarter" : "year");
/** The query string for a tab (the default tab and period leave no trace, so the plain address stays clean). Other parameters are kept. */
export function withTab(search: string, tab: Tab, period: Period): string {
  const p = new URLSearchParams(search);
  if (tab === "overview") p.delete("tab"); else p.set("tab", tab);
  if (tab === "financials" && period === "quarter") p.set("period", "quarter"); else p.delete("period");
  const s = p.toString();
  return s ? "?" + s : "";
}
/** Arrow keys, Home and End move between tabs (the tablist keyboard pattern); null for any other key. */
export function nextTab(current: Tab, key: string): Tab | null {
  const i = TABS.findIndex((t) => t.id === current), n = TABS.length;
  if (key === "ArrowRight") return TABS[(i + 1) % n].id;
  if (key === "ArrowLeft") return TABS[(i - 1 + n) % n].id;
  if (key === "Home") return TABS[0].id;
  if (key === "End") return TABS[n - 1].id;
  return null;
}

// ---------------------------------------------------------------------------------------------------- formatting

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-03-31" becomes "Mar-26"; anything else is returned as it came. */
export function monthYear(iso: string | null | undefined): string | null {
  const m = /^(\d{4})-(\d{2})-\d{2}/.exec(iso || "");
  return m ? `${MONTHS[Number(m[2]) - 1]}-${m[1].slice(2)}` : iso || null;
}
export const BASIS_WORD = { consolidated: "Consolidated", standalone: "Standalone" } as const;
export const money = (v: number | null | undefined, d = 0) => (v == null || !Number.isFinite(v) ? MINUS : (v < 0 ? "−" : "") + nf(v, d));
export const dash = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? MINUS : (v < 0 ? "−" : "") + nf(v, d));
export const signedPoints = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), 0);
/** The size word of a company's market value: the site's own capSize rule, as the stock page uses. */
export const sizeWord = (capCr: number | null | undefined) => capSize(capCr);
export const priceText = (v: number | null | undefined) => (v == null ? MINUS : "₹" + nf(v, 2));
export const changeText = (v: number | null | undefined) => (v == null ? MINUS : (v > 0 ? "▲ " : v < 0 ? "▼ " : "• ") + nf(Math.abs(v), 2) + "%");
/** "₹16,02,253 Cr": the same text as the market cap in the stock page header. */
export const capText = (v: number | null | undefined) => marketCapText(v) ?? MINUS;
const figTip = (f: Fig | undefined, label: string) => (f?.value != null ? [f.period ? `${label}: ${f.period}` : label, f.note].filter(Boolean).join(". ") : f?.why || `${label} is not available.`);
/** Hover text of a ratio cell: its period (and any note) when there is a value, otherwise why there is none. */
export const ratioTip = figTip;

// ---------------------------------------------------------------------------------------------------- scores

/** The plan's model score of a holding (null when none yet), its word, and the colour band (the one rule of lib/scoreBands.ts). */
export function scoreOf(h: OverviewHolding | undefined, model: Model): { value: number | null; word: string | null; band: ScoreBand } {
  if (!isReady(h)) return { value: null, word: null, band: "na" };
  if (model === "prism") {
    const p = h.prism, v = p && p.state !== "not_rated" ? p.final : null;
    return { value: v, word: v == null ? null : LABEL_WORD[p!.label as PrismLabel] ?? p!.label, band: scoreBand(v) };
  }
  const v = h.finlit?.overall ?? null;
  return { value: v, word: v == null ? null : h.finlit?.word ?? null, band: scoreBand(v) };
}
/** Why a holding has no score of the plan's model, in plain words (null when it has one). */
export function scoreWhy(h: OverviewHolding | undefined, model: Model): string | null {
  if (!h) return "Scores are loading.";
  if (!isReady(h)) return h.reason;
  if (scoreOf(h, model).value != null) return null;
  if (model === "finlit") return "FinLit has no overall score for this company yet: its report did not have enough figures to score.";
  const p = h.prism;
  if (!p || p.state === "none") return "Not rated yet. Open its Prism page to rate it now (about 30 seconds).";
  return p.reason || "Prism could not rate this company: its filed history or data is not enough for a rating.";
}

export const FINLIT_PILLARS = [["quality", "Quality"], ["growth", "Growth"], ["profitability", "Profit."], ["balance", "Balance"], ["technical", "Technical"]] as const;
export const PRISM_FOUR = PRISM_PARTS.map((p) => ({ key: p.col.replace("prism_", "") as "fundamental" | "valuation" | "quality" | "risk", label: p.label, say: p.say }));
export const PRISM_TECH = [["shortTerm", "Short term", "Prism's short term (5 to 20 sessions) price-trend reading, from −100 to +100"], ["longTerm", "Long term", "Prism's long term (6 to 18 months) price-trend reading, from −100 to +100"]] as const;

// ---------------------------------------------------------------------------------------------------- columns

export type Col = {
  id: string; label: string; hint?: string; num?: boolean;
  sort?: (h: Ready) => number | string | null;   // value to sort by (null sorts last)
  csv: (h: Ready) => string | number | null;      // spreadsheet value
};
const csvFig = (f: Fig | undefined) => (f?.value == null ? null : f.value);
const statementOf = (h: Ready, p: Period) => h.financials[p];
const stmt = (k: "revenue" | "other_income" | "operating_profit" | "finance_costs" | "net_profit" | "eps" | "tax_ratio", p: Period) => (h: Ready) => csvFig(statementOf(h, p)[k]);

const shareCols: Col[] = [
  { id: "share", label: "Share", hint: "Name, symbol and sector", sort: (h) => h.symbol, csv: (h) => h.symbol },
];
const scoreCol = (model: Model): Col => ({
  id: "score", label: model === "prism" ? "Prism score" : "FinLit score", num: true, hint: model === "prism" ? "FinLit Prism, 0 to 100" : "FinLit score, 0 to 100",
  sort: (h) => scoreOf(h, model).value, csv: (h) => scoreOf(h, model).value,
});
const priceCols: Col[] = [
  { id: "price", label: "Latest price", num: true, sort: (h) => h.price, csv: (h) => h.price },
  { id: "change", label: "Today (%)", num: true, hint: "Change since the previous close", sort: (h) => h.changePct, csv: (h) => h.changePct },
];
const capCol: Col = { id: "cap", label: "Market cap", num: true, hint: "Market value in rupees crore, and the size word (the site's own bands)", sort: (h) => h.marketCapCr, csv: (h) => h.marketCapCr };

export function columnsFor(tab: Tab, model: Model, period: Period = "year"): Col[] {
  if (tab === "overview") {
    const score = model === "prism"
      ? [...PRISM_FOUR.map((p): Col => ({ id: "p_" + p.key, label: p.label, num: true, hint: p.say, sort: (h) => h.prism?.parts?.[p.key] ?? null, csv: (h) => h.prism?.parts?.[p.key] ?? null })),
         ...PRISM_TECH.map(([k, label, hint]): Col => ({ id: "t_" + k, label, num: true, hint, sort: (h) => h.prism?.[k]?.score ?? null, csv: (h) => h.prism?.[k]?.score ?? null }))]
      : FINLIT_PILLARS.map(([k, label]): Col => ({ id: "f_" + k, label, num: true, hint: `${label} pillar, 0 to 100`, sort: (h) => h.finlit?.pillars[k] ?? null, csv: (h) => h.finlit?.pillars[k] ?? null }));
    return [...shareCols, ...priceCols, capCol, scoreCol(model), ...score];
  }
  if (tab === "ratios") {
    const r = (k: keyof Ready["ratios"], label: string, hint: string): Col => ({ id: k, label, num: true, hint, sort: (h) => h.ratios[k].value, csv: (h) => csvFig(h.ratios[k]) });
    return [...shareCols, scoreCol(model), ...priceCols, capCol,
      r("dividend_yield", "Dividend yield (%)", "Dividends of the last 12 months over the price"), r("pe", "P/E", "Price to earnings, as the stock page shows it"),
      r("roe", "ROE (%)", "Return on equity"), r("debt_to_equity", "Debt to equity (x)", "Borrowings to shareholders' equity. Not shown for banks and lenders"), r("pb", "P/BV (x)", "Price to book value")];
  }
  const word = period === "year" ? "year" : "quarter";
  return [...shareCols, scoreCol(model), ...priceCols,
    { id: "yearEnd", label: period === "year" ? "Year end" : "Quarter end", hint: `The latest full ${word} in the stored statements, and whether it is the consolidated or standalone statement`, sort: (h) => statementOf(h, period).periodEnd, csv: (h) => monthYear(statementOf(h, period).periodEnd) },
    { id: "basis", label: "Statement", hint: "Consolidated or standalone: the basis this company's report uses", sort: (h) => h.basis, csv: (h) => (h.basis ? BASIS_WORD[h.basis] : null) },
    { id: "revenue", label: "Net sales / revenue (₹ Cr)", num: true, hint: "Revenue from operations. For banks and lenders: interest earned and fees", sort: (h) => statementOf(h, period).revenue?.value ?? null, csv: stmt("revenue", period) },
    { id: "other_income", label: "Other income (₹ Cr)", num: true, sort: (h) => statementOf(h, period).other_income?.value ?? null, csv: stmt("other_income", period) },
    { id: "operating_profit", label: "Operating profit (₹ Cr)", num: true, hint: "Not shown for banks and lenders", sort: (h) => statementOf(h, period).operating_profit?.value ?? null, csv: stmt("operating_profit", period) },
    { id: "finance_costs", label: "Interest paid (₹ Cr)", num: true, hint: "Finance costs", sort: (h) => statementOf(h, period).finance_costs?.value ?? null, csv: stmt("finance_costs", period) },
    { id: "tax_ratio", label: "Tax ratio (%)", num: true, hint: "Tax divided by profit before tax, from the same statement", sort: (h) => statementOf(h, period).tax_ratio?.value ?? null, csv: stmt("tax_ratio", period) },
    { id: "net_profit", label: "Net profit (₹ Cr)", num: true, sort: (h) => statementOf(h, period).net_profit?.value ?? null, csv: stmt("net_profit", period) },
    { id: "eps", label: "EPS (₹)", num: true, hint: "Earnings per share", sort: (h) => statementOf(h, period).eps?.value ?? null, csv: stmt("eps", period) }];
}

/** The figure behind a ratio or financials column, for its "why blank" text; null when the column has no blank-figure reason. */
export function blankWhy(h: Ready, col: string, period: Period): string | null {
  if (col in h.ratios) { const f = h.ratios[col as keyof Ready["ratios"]]; return f.value == null ? f.why || "Not available." : null; }
  const s = statementOf(h, period);
  if (!s.available) return s.why || "No statement is stored for this company yet.";
  const f = s[col as "revenue"];
  return f && f.value == null ? f.why || "Not in the statement." : null;
}

// ---------------------------------------------------------------------------------------------------- rows: filter, sort, summary

export type Line = { symbol: string; name?: string | null; ov?: OverviewHolding };
export type BandFilter = ScoreBand | null;
export const BAND_CHIPS: { band: ScoreBand; label: string; rule: string }[] = [
  { band: "hi", label: "Green", rule: "70 or more" }, { band: "mid", label: "Orange", rule: "50 to 69" }, { band: "lo", label: "Red", rule: "under 50" }, { band: "na", label: "Not scored", rule: "no score yet" },
];
export const bandCounts = (lines: Line[], model: Model): Record<ScoreBand, number> => {
  const out: Record<ScoreBand, number> = { hi: 0, mid: 0, lo: 0, na: 0 };
  lines.forEach((l) => { out[scoreOf(l.ov, model).band]++; });
  return out;
};

export function visibleLines(lines: Line[], q: string, band: BandFilter, model: Model): Line[] {
  const needle = q.trim().toLowerCase();
  return lines.filter((l) => (band == null || scoreOf(l.ov, model).band === band)
    && (!needle || [l.symbol, l.name || "", isReady(l.ov) ? l.ov.sector || "" : "", isReady(l.ov) ? l.ov.industry || "" : ""].join(" ").toLowerCase().includes(needle)));
}

/** Sort lines by a column: companies without a value go last in either direction; text sorts by locale, numbers by size. */
export function sortLines(lines: Line[], col: Col | undefined, dir: 1 | -1): Line[] {
  if (!col?.sort) return lines;
  const val = (l: Line) => (isReady(l.ov) ? col.sort!(l.ov) : col.id === "share" ? l.symbol : null);
  return [...lines].sort((a, b) => {
    const x = val(a), y = val(b);
    if (x == null && y == null) return a.symbol.localeCompare(b.symbol);
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number)) * dir;
  });
}

export type Summary = {
  shares: number; scored: number; preparing: number; unknown: number; average: number | null; bands: Record<ScoreBand, number>;
  sectors: { name: string; count: number }[];
  parts: { label: string; value: number }[];      // average of each part (the basic pillars or the Prism parts), shares counted equally
};
/** Equal-weighted summary of the list (quantities are not used: the page takes share names only). */
export function summarize(lines: Line[], model: Model): Summary {
  const scores = lines.map((l) => scoreOf(l.ov, model).value).filter((v): v is number => v != null);
  const sectors = new Map<string, number>();
  lines.forEach((l) => { if (isReady(l.ov) && l.ov.sector) sectors.set(l.ov.sector, (sectors.get(l.ov.sector) || 0) + 1); });
  const ready = lines.map((l) => l.ov).filter(isReady);
  const defs: { label: string; get: (h: Ready) => number | null | undefined }[] = model === "prism"
    ? PRISM_FOUR.map((p) => ({ label: p.label, get: (h) => h.prism?.parts?.[p.key] }))
    : FINLIT_PILLARS.map(([k, label]) => ({ label, get: (h) => h.finlit?.pillars[k] }));
  const parts = defs.flatMap((d) => { const v = ready.map(d.get).filter((x): x is number => x != null); return v.length ? [{ label: d.label, value: v.reduce((a, b) => a + b, 0) / v.length }] : []; });
  return {
    shares: lines.length, scored: scores.length, preparing: lines.filter((l) => !l.ov || l.ov.status === "preparing").length, unknown: lines.filter((l) => l.ov?.status === "unknown").length,
    average: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null, bands: bandCounts(lines, model),
    sectors: [...sectors.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)), parts,
  };
}

// ---------------------------------------------------------------------------------------------------- CSV (one per tab)

const q = (s: string) => `"${csvText(s).replace(/"/g, '""')}"`;
const cell = (v: string | number | null | undefined) => (v == null ? "" : typeof v === "number" ? (Number.isFinite(v) ? String(v) : "") : q(v));
export const csvName = (tab: Tab, period: Period) => `FinLit-portfolio-${tab}${tab === "financials" ? "-" + (period === "quarter" ? "latest-quarter" : "latest-year") : ""}.csv`;

/** The CSV of a tab as shown (same columns, same order). A company that is not ready has its symbol and a Note with the reason. Shares count equally; no weighted total. */
export function toCsv(lines: Line[], tab: Tab, model: Model, period: Period): string {
  const body = columnsFor(tab, model, period).filter((c) => c.id !== "share");
  const head = ["Symbol", "Company", "Sector", ...body.map((c) => c.label), "Note"];
  const rows = lines.map((l) => {
    const h = l.ov;
    const values = isReady(h) ? body.map((c) => c.csv(h)) : body.map(() => null);
    return [cell(l.symbol), cell(l.name || (isReady(h) ? h.name : "") || ""), cell(isReady(h) ? h.sector : ""), ...values.map(cell),
      cell(isReady(h) ? scoreWhy(h, model) || "" : h?.reason || "Scores are loading.")].join(",");
  });
  return [head.map(q).join(","), ...rows].join("\n");
}
