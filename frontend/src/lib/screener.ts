// Shared by the Screener and Company comparison pages: one row per company, filtered and compared in the browser.
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";
import { MINUS, cr, nf } from "./format";

export type Row = {
  symbol: string; name: string | null; sector: string | null; sample?: boolean; scored?: boolean;
  overall: number | null; band: string | null;
  pillar_quality: number | null; pillar_growth: number | null; pillar_profitability: number | null; pillar_balance: number | null; pillar_technical: number | null;
  price: number | null; market_cap: number | null; pe: number | null; pb: number | null; roe: number | null; roce: number | null;
  dividend_yield: number | null; debt_to_equity: number | null; sales_cagr: number | null; profit_cagr: number | null;
  operating_margin: number | null; change_pct: number | null; return_1m: number | null; return_1y: number | null;
};
export type NumKey = Exclude<keyof Row, "symbol" | "name" | "sector" | "sample" | "band" | "scored">;

export function useUniverse(enabled = true) {
  return useQuery({
    queryKey: ["universe"], staleTime: 300_000, retry: 1, enabled,
    queryFn: async () => {
      const d = await apiGet<{ rows: Row[]; sample?: boolean }>("/api/screener/universe");
      const rows: Row[] = d.rows.map((r) => ({ ...r, name: r.name || r.symbol }));
      return { rows, sample: !!d.sample || rows.some((r) => r.sample) };
    },
  });
}

export type Metric = {
  key: NumKey; label: string; short: string; unit: "x" | "%" | "₹" | "Cr" | "pts" | ""; better: "higher" | "lower" | "none";
  say: string; model?: boolean; digits?: number;
};
export const METRICS: Record<NumKey, Metric> = {
  market_cap: { key: "market_cap", label: "Market cap", short: "Mkt cap", unit: "Cr", better: "none", say: "What the whole company is worth on the stock market." },
  price: { key: "price", label: "Share price", short: "Price", unit: "₹", better: "none", say: "Latest traded price of one share." },
  change_pct: { key: "change_pct", label: "1-day change", short: "1D", unit: "%", better: "higher", say: "How the price moved today.", digits: 1 },
  return_1m: { key: "return_1m", label: "1-month return", short: "1M", unit: "%", better: "higher", say: "Price change over the last month.", digits: 1 },
  return_1y: { key: "return_1y", label: "1-year return", short: "1Y", unit: "%", better: "higher", say: "Price change over the last year.", digits: 1 },
  pe: { key: "pe", label: "P/E ratio", short: "P/E", unit: "x", better: "lower", say: "Rupees you pay for each rupee of yearly profit.", digits: 1 },
  pb: { key: "pb", label: "P/B ratio", short: "P/B", unit: "x", better: "lower", say: "Price compared with what the books say the company owns.", digits: 2 },
  dividend_yield: { key: "dividend_yield", label: "Dividend yield", short: "Div. yield", unit: "%", better: "higher", say: "Yearly cash dividend for every ₹100 invested.", digits: 2 },
  roe: { key: "roe", label: "Return on equity", short: "ROE", unit: "%", better: "higher", say: "Profit earned on shareholders' money.", digits: 1 },
  roce: { key: "roce", label: "Return on capital", short: "ROCE", unit: "%", better: "higher", say: "Profit earned on all the money used in the business.", digits: 1 },
  operating_margin: { key: "operating_margin", label: "Operating margin", short: "Op. margin", unit: "%", better: "higher", say: "Profit from the core business out of every ₹100 of sales.", digits: 1 },
  sales_cagr: { key: "sales_cagr", label: "Sales growth (5Y a year)", short: "Sales CAGR", unit: "%", better: "higher", say: "How fast sales have grown each year over five years.", digits: 1 },
  profit_cagr: { key: "profit_cagr", label: "Profit growth (5Y a year)", short: "Profit CAGR", unit: "%", better: "higher", say: "How fast profit has grown each year over five years.", digits: 1 },
  debt_to_equity: { key: "debt_to_equity", label: "Debt to equity", short: "Debt/Equity", unit: "x", better: "lower", say: "Rupees owed for every rupee of owners' money.", digits: 2 },
  overall: { key: "overall", label: "FinLit score", short: "Score", unit: "pts", better: "higher", say: "Average of the five FinLit pillars, out of 100.", model: true, digits: 0 },
  pillar_quality: { key: "pillar_quality", label: "Quality pillar", short: "Quality", unit: "pts", better: "higher", say: "Return on money and how well profit turns into cash.", model: true, digits: 0 },
  pillar_growth: { key: "pillar_growth", label: "Growth pillar", short: "Growth", unit: "pts", better: "higher", say: "Sales and profit growth over the years.", model: true, digits: 0 },
  pillar_profitability: { key: "pillar_profitability", label: "Profitability pillar", short: "Profit", unit: "pts", better: "higher", say: "Margins and returns on money.", model: true, digits: 0 },
  pillar_balance: { key: "pillar_balance", label: "Balance sheet pillar", short: "Balance", unit: "pts", better: "higher", say: "Debt, liquidity and interest cover.", model: true, digits: 0 },
  pillar_technical: { key: "pillar_technical", label: "Technical pillar", short: "Technical", unit: "pts", better: "higher", say: "Price trend and momentum.", model: true, digits: 0 },
};

export function fmt(m: Metric, v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const d = m.digits ?? 2, sign = v < 0 ? MINUS : "";
  switch (m.unit) {
    case "Cr": return sign + "₹" + cr(Math.abs(v)) + " Cr";
    case "₹": return sign + "₹" + nf(v, 2);
    case "%": return (v > 0 && (m.key === "change_pct" || m.key.startsWith("return")) ? "+" : sign) + nf(v, d) + "%";
    case "x": return sign + nf(v, d) + "×";
    default: return sign + nf(v, d);
  }
}

export const BAND_LABEL: Record<string, string> = { strong: "Strong", healthy: "Healthy", mixed: "Mixed", watch: "Watch" };

/* ---------------- filter catalogue ---------------- */
export type FilterDef = { key: NumKey; group: string; step?: number; hint?: string };
export type Group = { id: string; label: string; model?: boolean; filters: FilterDef[] };
export const GROUPS: Group[] = [
  { id: "size", label: "Size & Price", filters: [{ key: "market_cap", group: "size", step: 1000, hint: "₹ Cr" }, { key: "price", group: "size", step: 50, hint: "₹" }] },
  { id: "returns", label: "Returns", filters: [{ key: "change_pct", group: "returns", step: 0.5, hint: "%" }, { key: "return_1m", group: "returns", step: 1, hint: "%" }, { key: "return_1y", group: "returns", step: 5, hint: "%" }] },
  { id: "valuation", label: "Valuation", filters: [{ key: "pe", group: "valuation", step: 1, hint: "×" }, { key: "pb", group: "valuation", step: 0.5, hint: "×" }, { key: "dividend_yield", group: "valuation", step: 0.25, hint: "%" }] },
  { id: "profit", label: "Profitability", filters: [{ key: "roe", group: "profit", step: 1, hint: "%" }, { key: "roce", group: "profit", step: 1, hint: "%" }, { key: "operating_margin", group: "profit", step: 1, hint: "%" }] },
  { id: "growth", label: "Growth", filters: [{ key: "sales_cagr", group: "growth", step: 1, hint: "%" }, { key: "profit_cagr", group: "growth", step: 1, hint: "%" }] },
  { id: "health", label: "Financial Health", filters: [{ key: "debt_to_equity", group: "health", step: 0.1, hint: "×" }] },
  { id: "model", label: "FinLit model", model: true, filters: (["overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical"] as NumKey[]).map((key) => ({ key, group: "model", step: 5, hint: "0–100" })) },
  { id: "sector", label: "Sector", filters: [] },
];

export type Range = { min?: number; max?: number };
export type State = { ranges: Partial<Record<NumKey, Range>>; sectors: string[]; bands: string[] };
export const EMPTY: State = { ranges: {}, sectors: [], bands: [] };

export function applyFilters(rows: Row[], f: State): Row[] {
  return rows.filter((r) => {
    for (const k in f.ranges) {
      const rg = f.ranges[k as NumKey]!, v = r[k as NumKey];
      if (rg.min == null && rg.max == null) continue;
      if (v == null) return false;
      if (rg.min != null && v < rg.min) return false;
      if (rg.max != null && v > rg.max) return false;
    }
    if (f.sectors.length && (!r.sector || !f.sectors.includes(r.sector))) return false;
    if (f.bands.length && (!r.band || !f.bands.includes(r.band))) return false;
    return true;
  });
}
export const activeCount = (f: State) => Object.values(f.ranges).filter((r) => r && (r.min != null || r.max != null)).length + (f.sectors.length ? 1 : 0) + (f.bands.length ? 1 : 0);

export type Quick = { id: string; label: string; says: string; model?: boolean; state: State };
const q = (ranges: State["ranges"], extra: Partial<State> = {}): State => ({ ...EMPTY, ranges, ...extra });
export const QUICK: Quick[] = [
  { id: "large", label: "Large, established companies", says: "Market cap above ₹1,00,000 Cr", state: q({ market_cap: { min: 100000 } }) },
  { id: "lowdebt", label: "Low debt", says: "Debt to equity below 0.5×", state: q({ debt_to_equity: { max: 0.5 } }) },
  { id: "div", label: "Dividend payers", says: "Dividend yield above 2%", state: q({ dividend_yield: { min: 2 } }) },
  { id: "value", label: "Value picks", says: "P/E under 15× and P/B under 2×", state: q({ pe: { max: 15 }, pb: { max: 2 } }) },
  { id: "roe", label: "High return on equity", says: "ROE above 15%", state: q({ roe: { min: 15 } }) },
  { id: "strong", label: "FinLit Strong", says: "FinLit score of 78 or more", model: true, state: q({ overall: { min: 78 } }) },
  { id: "compounders", label: "Quality compounders", says: "Quality 70+ and Growth 60+", model: true, state: q({ pillar_quality: { min: 70 }, pillar_growth: { min: 60 } }) },
  { id: "safe", label: "Safe and profitable", says: "Balance sheet 70+ and Profitability 60+", model: true, state: q({ pillar_balance: { min: 70 }, pillar_profitability: { min: 60 } }) },
  { id: "oversold", label: "Sound but out of favour", says: "Quality 55+ with Technical 35 or less", model: true, state: q({ pillar_quality: { min: 55 }, pillar_technical: { max: 35 } }) },
];

/* ---------------- distribution helpers (how a company sits against every other company) ---------------- */
export type Dist = { sorted: number[]; p10: number; p50: number; p90: number; min: number; max: number };
export function distOf(rows: Row[], k: NumKey): Dist | null {
  const sorted = rows.map((r) => r[k]).filter((v): v is number => v != null).sort((a, b) => a - b);
  if (sorted.length < 5) return null;
  const at = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(p * (sorted.length - 1)))];
  return { sorted, p10: at(0.1), p50: at(0.5), p90: at(0.9), min: sorted[0], max: sorted[sorted.length - 1] };
}
/** 0–100: share of companies this value beats (direction-aware). null where "better" has no meaning. */
export function percentile(d: Dist | null, k: NumKey, v: number | null | undefined): number | null {
  const m = METRICS[k];
  if (!d || v == null || m.better === "none") return null;
  const worse = d.sorted.filter((x) => (m.better === "higher" ? x < v : x > v)).length;
  return Math.round((worse / d.sorted.length) * 100);
}
