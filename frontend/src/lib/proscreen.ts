// The Silver/Gold screener: types, URL state, ready-made screens and number formatting. Filtering itself happens on the server.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, type ApiError } from "./api";
import { MINUS, cr, nf } from "./format";
import type { Plan } from "./ui";

export type MetricInfo = { key: string; label: string; unit: string; better: "higher" | "lower" | "none"; tier: Plan; say: string; digits: number; locked: boolean;
  stats: { min: number; p10: number; p50: number; p90: number; max: number; n: number; lo?: number; hi?: number; hist?: number[] } | null;
  hidden?: boolean; variants?: Record<string, string> | null };
export type GroupInfo = { id: string; label: string; tier: Plan; metrics: MetricInfo[] };
export type Catalog = {
  plan: Plan; total: number; updatedAt: string; groups: GroupInfo[]; sectors: { name: string; n: number }[]; industries: { name: string; sector: string | null; n: number }[];
  indices: { code: string; label: string; n: number }[]; caps: { name: string; n: number }[]; bands: { key: string; label: string; locked: boolean }[];
  limits: { rows: number | null; export: boolean }; defaultColumns: string[];
};
export type Range = { min?: number; max?: number };
export type PState = {
  ranges: Record<string, Range>; sectors: string[]; industries: string[]; indices: string[]; caps: string[]; bands: string[];
  sort?: string; dir?: "asc" | "desc"; cols?: string[];
};
export const EMPTY: PState = { ranges: {}, sectors: [], industries: [], indices: [], caps: [], bands: [] };
export type ResultRow = { symbol: string; name: string; sector: string | null; cap: string | null; band: string | null; v: Record<string, number | null> };
export type Result = { total: number; offset: number; limit: number; capped: boolean; columns: string[]; rows: ResultRow[]; took: number };

export const norm = (s: Partial<PState> | undefined): PState => ({ ...EMPTY, ...(s || {}), ranges: { ...(s?.ranges || {}) } });
export const activeCount = (s: PState) => Object.values(s.ranges).filter((r) => r && (r.min != null || r.max != null)).length + (s.sectors.length ? 1 : 0)
  + (s.industries.length ? 1 : 0) + (s.indices.length ? 1 : 0) + (s.caps.length ? 1 : 0) + (s.bands.length ? 1 : 0);

export const toBody = (s: PState, sort: { key: string; dir: "asc" | "desc" }, columns: string[], q: string, offset: number, limit: number) => ({
  filters: Object.fromEntries(Object.entries(s.ranges).filter(([, r]) => r && (r.min != null || r.max != null))),
  cats: { sector: s.sectors, industry: s.industries, index: s.indices, cap: s.caps, band: s.bands }, q, sort, columns, offset, limit,
});

/** Shareable link: the whole screen packed into one `s=` parameter. */
export const encodeState = (s: PState, sort: string, dir: string): string => {
  const o: Record<string, unknown> = {};
  if (Object.keys(s.ranges).length) o.r = s.ranges;
  (["sectors", "industries", "indices", "caps", "bands"] as const).forEach((k) => s[k].length && (o[k[0] + (k === "industries" ? "n" : k === "indices" ? "x" : "")] = s[k]));
  if (sort !== "market_cap" || dir !== "desc") o.o = [sort, dir];
  return Object.keys(o).length ? btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") : "";
};
export const decodeState = (raw: string | null): { state: PState; sort?: string; dir?: "asc" | "desc" } => {
  if (!raw) return { state: EMPTY };
  try {
    const o = JSON.parse(decodeURIComponent(escape(atob(raw.replace(/-/g, "+").replace(/_/g, "/")))));
    const arr = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === "string").slice(0, 60) : []);
    const ranges: Record<string, Range> = {};
    for (const [k, v] of Object.entries((o.r || {}) as Record<string, Range>)) if (/^[a-z0-9_]{2,40}$/.test(k) && v && typeof v === "object") ranges[k] = { min: typeof v.min === "number" ? v.min : undefined, max: typeof v.max === "number" ? v.max : undefined };
    return { state: { ranges, sectors: arr(o.s), industries: arr(o.sn), indices: arr(o.sx), caps: arr(o.c), bands: arr(o.b) }, sort: typeof o.o?.[0] === "string" ? o.o[0] : undefined, dir: o.o?.[1] === "asc" ? "asc" : "desc" };
  } catch { return { state: EMPTY }; }
};

export const useCatalog = () => useQuery<Catalog, ApiError>({ queryKey: ["screener-catalog"], queryFn: () => apiGet<Catalog>("/api/screener/catalog"), staleTime: 300_000, retry: 1 });
export const useScreen = (body: ReturnType<typeof toBody>, enabled: boolean) => useQuery<Result, ApiError>({
  queryKey: ["screener-query", body], queryFn: () => apiSend<Result>("POST", "/api/screener/query", body), enabled, placeholderData: keepPreviousData, staleTime: 60_000,
  retry: (n, e) => e.status >= 500 && n < 1,
});

export const UNIT_SUFFIX: Record<string, string> = { "%": "%", x: "×", d: " d", pts: "", n: "", flag: "", Cr: "", Rs: "" };
export function fmtMetric(m: Pick<MetricInfo, "unit" | "digits" | "key">, v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return MINUS;
  const sign = v < 0 ? MINUS : "";
  switch (m.unit) {
    case "Cr": return sign + "₹" + cr(Math.abs(v)) + " Cr";
    case "Rs": return sign + "₹" + nf(Math.abs(v), m.digits);
    case "%": return (v > 0 && /^(ret_|.*_chg_|.*_vs_|.*_yoy|.*_qoq|opm_change|dps_cagr|.*cagr)/.test(m.key) ? "+" : sign) + nf(Math.abs(v), m.digits) + "%";
    case "x": return sign + nf(Math.abs(v), m.digits) + "×";
    case "d": return nf(v, 0) + " d";
    case "flag": return v >= 1 ? "Yes" : "No";
    case "pts": return (v > 0 && /_chg_|change/.test(m.key) ? "+" : sign) + nf(Math.abs(v), m.digits);
    default: return sign + nf(Math.abs(v), m.digits);
  }
}

export type Ready = { id: string; label: string; says: string; tier: Plan; state: Partial<PState> };
const r = (o: Record<string, Range>): Partial<PState> => ({ ranges: o });
export const READY: Ready[] = [
  { id: "large", label: "Large, established companies", says: "Market cap above ₹1,00,000 Cr", tier: "basic", state: r({ market_cap: { min: 100000 } }) },
  { id: "lowdebt", label: "Low debt", says: "Debt to equity below 0.5×", tier: "basic", state: r({ debt_to_equity: { max: 0.5 } }) },
  { id: "div", label: "Dividend payers", says: "Dividend yield above 2%", tier: "basic", state: r({ dividend_yield: { min: 2 } }) },
  { id: "value", label: "Value picks", says: "P/E under 15× and P/B under 2×", tier: "silver", state: r({ pe: { min: 0.1, max: 15 }, pb: { min: 0.1, max: 2 } }) },
  { id: "roe", label: "High return on equity", says: "ROE above 15% and ROCE above 15%", tier: "basic", state: r({ roe: { min: 15 }, roce: { min: 15 } }) },
  { id: "garp", label: "Growth at a fair price", says: "PEG under 1.5, profit growth 5Y above 15%, ROE above 15%", tier: "silver", state: r({ peg: { min: 0.01, max: 1.5 }, profit_cagr_5y: { min: 15 }, roe: { min: 15 } }) },
  { id: "cheap_own", label: "Cheap against its own history", says: "P/E at least 15% below its own average, profit still growing", tier: "silver", state: r({ pe_vs_median_5y: { max: -15 }, profit_growth: { min: 0 }, pe: { min: 0.1 } }) },
  { id: "cheap_sector", label: "Cheaper than its sector", says: "P/E 20% below the sector median with ROE above 12%", tier: "silver", state: r({ pe_vs_sector: { max: -20 }, roe: { min: 12 } }) },
  { id: "netcash", label: "Net cash balance sheet", says: "More cash and investments than debt, interest cover above 5×", tier: "silver", state: r({ net_debt: { max: 0 }, interest_coverage: { min: 5 } }) },
  { id: "cashrich", label: "Profits backed by cash", says: "Operating cash above 90% of profit, free cash flow positive", tier: "silver", state: r({ cfo_to_pat: { min: 90 }, fcf: { min: 0.01 }, net_profit: { min: 0.01 } }) },
  { id: "compounder", label: "Steady compounders", says: "Sales and profit growth above 12% for 5 years, ROCE above 15%", tier: "silver", state: r({ sales_cagr_5y: { min: 12 }, profit_cagr_5y: { min: 12 }, roce: { min: 15 } }) },
  { id: "surge", label: "Quarterly profit surge", says: "Profit up 25%+ on last year's quarter, sales also rising", tier: "silver", state: r({ q_profit_yoy: { min: 25 }, q_sales_yoy: { min: 5 } }) },
  { id: "steadyq", label: "Four strong quarters", says: "Sales and profit beat the year-ago quarter in each of the last four", tier: "silver", state: r({ q_sales_up: { min: 4 }, q_profit_up: { min: 4 } }) },
  { id: "divgrow", label: "Reliable dividend growers", says: "Paid dividends in 6 of 6 years, growing, yield above 1%", tier: "silver", state: r({ div_years: { min: 6 }, dps_cagr: { min: 5 }, dividend_yield: { min: 1 } }) },
  { id: "buying", label: "Promoters and funds buying", says: "Promoters and institutions both added to their stake this year", tier: "silver", state: r({ own_promoters_chg_1y: { min: 0.25 }, own_inst_chg_1y: { min: 0.5 } }) },
  { id: "newhigh", label: "Near a 52-week high with volume", says: "Within 3% of the high and trading 1.5× average volume", tier: "silver", state: r({ near_high: { min: 1 }, volume_vs_avg: { min: 1.5 } }) },
  { id: "oversold", label: "Oversold quality", says: "RSI under 35 but ROE above 12% and debt under 1×", tier: "silver", state: r({ rsi14: { max: 35 }, roe: { min: 12 }, debt_to_equity: { max: 1 } }) },
  { id: "clean", label: "No red flags", says: "None of the eight warnings apply, large and mid companies", tier: "silver", state: { ranges: { flag_count: { max: 0 } }, caps: ["Large", "Mid"] } },
  { id: "strong", label: "FinLit Strong", says: "FinLit score of 78 or more", tier: "gold", state: r({ overall: { min: 78 } }) },
  { id: "modelcompound", label: "Quality compounders (model)", says: "Quality 70+ and Growth 60+", tier: "gold", state: r({ pillar_quality: { min: 70 }, pillar_growth: { min: 60 } }) },
  { id: "safe", label: "Safe and profitable (model)", says: "Balance sheet 70+ and Profitability 60+", tier: "gold", state: r({ pillar_balance: { min: 70 }, pillar_profitability: { min: 60 } }) },
  { id: "improving", label: "Improving scores", says: "FinLit score up 5+ points since last quarter", tier: "gold", state: r({ score_change: { min: 5 }, overall: { min: 50 } }) },
  { id: "outfavour", label: "Sound but out of favour", says: "Quality 55+ with the Technical pillar 35 or less", tier: "gold", state: r({ pillar_quality: { min: 55 }, pillar_technical: { max: 35 } }) },
];
