// Graph Studio: the catalogue of things that can be drawn, and how each one is read out of the stock endpoints we already have
// (financials, ratios, price, ownership, segments). Pure functions, no React. Every number comes straight from those documents;
// nothing here estimates, fills or smooths a value.
import type { Financials, Ownership, PriceRange, Ratios, Segments, Series } from "./api";
import type { Plan } from "./auth";
import { MINUS, nf } from "./format";

export type UnitId = "cr" | "inr" | "pct" | "x" | "days" | "sh" | "idx" | "pts";
export type Basis = "annual" | "quarterly";
/** One observation. `t` is an ISO date (the period end for statements); `l` is the period label the provider uses (FY26, Mar 2026). */
export type Pt = { t: string; v: number | null; l?: string; o?: number | null; h?: number | null; lo?: number | null };

export const UNITS: Record<UnitId, { label: string; name: string }> = {
  cr: { label: "₹ Cr", name: "rupees crore" },
  inr: { label: "₹", name: "rupees" },
  pct: { label: "%", name: "per cent" },
  x: { label: "×", name: "times" },
  days: { label: "days", name: "days" },
  sh: { label: "shares", name: "shares" },
  pts: { label: "points", name: "index points" },
  idx: { label: "index (start = 100)", name: "index, first value = 100" },
};

/** price: dense daily/weekly points. periodic: one point per financial year or quarter. composition: shares of a whole (not a time series). */
export type Grain = "price" | "periodic" | "composition";
/** How a change between two readings is measured: percent for amounts, plain difference for ratios that are already percentages or multiples. */
export type Kind = "amount" | "ratio";
type Src = "price" | "ixval" | "pl" | "bs" | "cf" | "ratio" | "val" | "own" | "seg" | "ownnow";

export type Metric = {
  id: string; label: string; group: string; unit: UnitId; kind: Kind; grain: Grain; src: Src; key: string;
  periods: Basis[];            // which statement bases carry it (price-grain metrics ignore this)
  tier: Plan;                  // the plan the server needs before it sends the underlying data
  hint?: string;
};

export const GROUPS: { id: string; label: string }[] = [
  { id: "popular", label: "Popular" }, { id: "price", label: "Price" }, { id: "pl", label: "Profit & loss" }, { id: "bs", label: "Balance sheet" },
  { id: "cf", label: "Cash flow" }, { id: "returns", label: "Returns & margins" }, { id: "valuation", label: "Valuation" },
  { id: "leverage", label: "Debt & liquidity" }, { id: "efficiency", label: "Efficiency" }, { id: "holding", label: "Shareholding" }, { id: "mix", label: "Breakdowns" }, { id: "index", label: "Index valuation" },
];

const A: Basis[] = ["annual"], AQ: Basis[] = ["annual", "quarterly"];
const m = (id: string, label: string, group: string, unit: UnitId, src: Src, key: string, o: Partial<Metric> = {}): Metric =>
  ({ id, label, group, unit, kind: unit === "pct" || unit === "x" || unit === "days" ? "ratio" : "amount", grain: "periodic", src, key, periods: A, tier: "basic", ...o });

// The five ratio histories every plan receives (backend/finlit/auth/entitlements.py BASIC_HISTORY_KEYS); the rest of the history is Gold.
const BASIC_RATIO = new Set(["gross_margin", "operating_margin", "net_margin", "roe", "roce"]);
const ratio = (key: string, label: string, group: string, unit: UnitId): Metric =>
  m(key, label, group, unit, "ratio", key, { tier: BASIC_RATIO.has(key) ? "basic" : "gold" });

export const METRICS: Metric[] = [
  m("price", "Share price", "price", "inr", "price", "c", { grain: "price", kind: "amount", periods: AQ, hint: "Closing price. Daily up to one year, weekly beyond." }),
  m("volume", "Volume", "price", "sh", "price", "v", { grain: "price", kind: "amount", periods: AQ, hint: "Shares traded per bar (daily, or the weekly total on long ranges)." }),

  m("revenue", "Revenue", "pl", "cr", "pl", "revenue", { periods: AQ }),
  m("operating_profit", "Operating profit", "pl", "cr", "pl", "operating_profit", { periods: AQ }),
  m("net_profit", "Net profit", "pl", "cr", "pl", "net_profit", { periods: AQ }),
  m("profit_before_tax", "Profit before tax", "pl", "cr", "pl", "profit_before_tax", { periods: AQ }),
  m("eps", "EPS", "pl", "inr", "pl", "eps", { periods: AQ, hint: "Earnings per share, in rupees." }),
  m("expenses", "Expenses", "pl", "cr", "pl", "expenses", { periods: AQ }),
  m("depreciation", "Depreciation", "pl", "cr", "pl", "depreciation", { periods: AQ }),
  m("finance_costs", "Finance costs", "pl", "cr", "pl", "finance_costs", { periods: AQ }),
  m("tax", "Tax", "pl", "cr", "pl", "tax", { periods: AQ }),

  m("total_assets", "Total assets", "bs", "cr", "bs", "total_assets"),
  m("total_equity", "Total equity", "bs", "cr", "bs", "total_equity"),
  m("borrowings", "Borrowings", "bs", "cr", "bs", "borrowings"),
  m("cash", "Cash and equivalents", "bs", "cr", "bs", "cash"),
  m("fixed_assets", "Fixed assets", "bs", "cr", "bs", "fixed_assets"),
  m("inventories", "Inventories", "bs", "cr", "bs", "inventories"),
  m("receivables", "Receivables", "bs", "cr", "bs", "receivables"),

  m("cfo", "Operating cash flow", "cf", "cr", "cf", "operating"),
  m("cfi", "Investing cash flow", "cf", "cr", "cf", "investing"),
  m("cff", "Financing cash flow", "cf", "cr", "cf", "financing"),
  m("free_cash_flow", "Free cash flow", "cf", "cr", "cf", "free_cash_flow"),
  m("capex", "Capital expenditure", "cf", "cr", "cf", "capex"),

  ratio("roe", "ROE", "returns", "pct"), ratio("roce", "ROCE", "returns", "pct"), ratio("roa", "ROA", "returns", "pct"), ratio("rota", "Return on tangible assets", "returns", "pct"),
  ratio("gross_margin", "Gross margin", "returns", "pct"), ratio("operating_margin", "Operating margin", "returns", "pct"), ratio("ebitda_margin", "EBITDA margin", "returns", "pct"),
  ratio("ebit_margin", "EBIT margin", "returns", "pct"), ratio("pretax_margin", "Pre-tax margin", "returns", "pct"), ratio("net_margin", "Net margin", "returns", "pct"),
  ratio("effective_tax_rate", "Effective tax rate", "returns", "pct"), ratio("dividend_payout", "Dividend payout", "returns", "pct"), ratio("retention_ratio", "Retention ratio", "returns", "pct"),

  m("pe", "P/E", "valuation", "x", "val", "pe", { tier: "gold", hint: "Price to earnings at each financial year end." }),
  m("pb", "P/B", "valuation", "x", "val", "pb", { tier: "gold", hint: "Price to book value at each financial year end." }),
  m("ps", "P/S", "valuation", "x", "val", "ps", { tier: "gold", hint: "Market value to sales at each financial year end." }),
  m("average_price", "Average price (year)", "valuation", "inr", "val", "average_price", { tier: "gold", kind: "amount", hint: "Average share price over the financial year." }),

  ratio("debt_to_equity", "Debt / equity", "leverage", "x"), ratio("lt_debt_to_equity", "Long-term debt / equity", "leverage", "x"), ratio("debt_to_assets", "Debt / assets", "leverage", "x"),
  ratio("debt_to_fcf", "Debt / free cash flow", "leverage", "x"), ratio("financial_leverage", "Financial leverage", "leverage", "x"),
  ratio("current_ratio", "Current ratio", "leverage", "x"), ratio("quick_ratio", "Quick ratio", "leverage", "x"), ratio("interest_coverage", "Interest coverage", "leverage", "x"),

  ratio("asset_turnover", "Asset turnover", "efficiency", "x"), ratio("cash_conversion_cycle", "Cash conversion cycle", "efficiency", "days"),
  ratio("debtor_days", "Debtor days", "efficiency", "days"), ratio("inventory_days", "Inventory days", "efficiency", "days"), ratio("payable_days", "Payable days", "efficiency", "days"),

  m("promoters", "Promoter holding", "holding", "pct", "own", "promoters", { periods: AQ, hint: "Share of the company held by promoters, per quarter." }),
  m("fii", "Foreign institutions (FII)", "holding", "pct", "own", "fii", { periods: AQ }),
  m("dii", "Domestic institutions (DII)", "holding", "pct", "own", "dii", { periods: AQ }),
  m("public", "Retail & others", "holding", "pct", "own", "public", { periods: AQ }),

  m("ix_pe", "Index P/E", "index", "x", "ixval", "pe", { grain: "price", tier: "gold", periods: AQ, hint: "Daily price to earnings of a market index. Indices only." }),
  m("ix_pb", "Index P/B", "index", "x", "ixval", "pb", { grain: "price", tier: "gold", periods: AQ, hint: "Daily price to book value of a market index. Indices only." }),
  m("ix_dy", "Index dividend yield", "index", "pct", "ixval", "dy", { grain: "price", tier: "gold", periods: AQ, hint: "Daily dividend yield of a market index. Indices only." }),

  m("mix_segments", "Revenue by segment", "mix", "cr", "seg", "latest", { grain: "composition", kind: "amount", tier: "gold", hint: "Latest financial year; a breakdown of one company's revenue." }),
  m("mix_holding", "Shareholding pattern", "mix", "pct", "ownnow", "latest", { grain: "composition", kind: "ratio", periods: AQ, hint: "Latest quarter; who owns the company." }),
];

/** The measures offered first, as in the mock-ups. */
export const POPULAR = ["price", "revenue", "net_profit", "operating_profit", "eps", "pe", "roe", "roce", "free_cash_flow", "debt_to_equity", "promoters"];
export const BY_ID: Record<string, Metric> = Object.fromEntries(METRICS.map((x) => [x.id, x]));
export const isMetricId = (id: unknown): id is string => typeof id === "string" && id in BY_ID;

export const metricsIn = (group: string, q = ""): Metric[] => {
  const needle = q.trim().toLowerCase();
  const base = group === "popular" ? POPULAR.map((id) => BY_ID[id]) : METRICS.filter((x) => x.group === group);
  const pool = needle ? METRICS : base;
  return needle ? pool.filter((x) => (x.label + " " + x.id + " " + (GROUPS.find((g) => g.id === x.group)?.label ?? "")).toLowerCase().includes(needle)) : pool;
};

// ------------------------------------------------------------------ reading the endpoints

/** The documents one company contributes. Any may be missing (not loaded, not available, or trimmed by the plan). */
/** Indices travel through Graph Studio as "IDX:" + the provider's code (IDX:NIF50). */
export const IDX = "IDX:";
export const isIndexSym = (s: string) => s.startsWith(IDX);
export const indexCode = (s: string) => s.slice(IDX.length);
/** What an index can show: its level (the price measure, in points) and its valuation history. Everything else is a company statement. */
export const indexSupports = (mt: Metric) => mt.id === "price" || mt.src === "ixval";
/** The measure as it reads for this symbol: an index has a level in points, not a share price. */
export const metricFor = (sym: string, mt: Metric): Metric => (isIndexSym(sym) && mt.id === "price" ? { ...mt, label: "Index level", unit: "pts", hint: "Daily closing level in index points." } : mt);
export const unsupportedWhy = (sym: string, mt: Metric): string | null =>
  isIndexSym(sym) ? (indexSupports(mt) ? null : "Companies report this; an index does not.") : mt.src === "ixval" ? "Only for indices." : null;

export type IndexLevels = { rows: { d: string; c: number }[] };
export type IndexVal = { rows: { d: string; pe: number | null; pb: number | null; dy: number | null }[] };
export type Bundle = { ixl?: IndexLevels; ixv?: IndexVal; fin?: Financials; ratios?: Ratios; own?: Ownership; seg?: Segments; price?: PriceRange };

const MONTHS: Record<string, number> = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const iso = (y: number, mo: number, d: number) => `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const lastDay = (y: number, mo: number) => new Date(Date.UTC(y, mo, 0)).getUTCDate();

/** "Sep 2023" -> 2023-09-30. Null for anything else. */
export function monthEnd(label: string): string | null {
  const mt = /^([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$/.exec(label.trim());
  const mo = mt ? MONTHS[mt[1].toLowerCase()] : 0;
  return mt && mo ? iso(+mt[2], mo, lastDay(+mt[2], mo)) : null;
}
/** "FY26" -> 2026-03-31 (the Indian financial year ends on 31 March). Used only when the statement gives no period end. */
export function fyEnd(label: string): string | null {
  const mt = /^FY(\d{2})$/.exec(label.trim());
  return mt ? iso(2000 + +mt[1], 3, 31) : null;
}

const finite = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const zip = (dates: (string | null)[], labels: string[], vals: Series | undefined): Pt[] =>
  (vals ?? []).map((v, i) => ({ t: dates[i] ?? "", v: finite(v), l: labels[i] })).filter((p) => p.t !== "");

export type Status = "unsupported" | "ok" | "loading" | "locked" | "noperiod" | "nodata" | "error";
export type Extracted = { status: Status; pts: Pt[]; note?: string; ohlc?: boolean; cats?: { name: string; value: number; note?: string }[] };

/** Read one metric for one company. `plan` decides whether a missing row is "locked by the plan" or simply "no data". */
export function extract(mt: Metric, b: Bundle, basis: Basis, plan: Plan, loaded: boolean): Extracted {
  const RANKN: Record<Plan, number> = { basic: 0, silver: 1, gold: 2 };
  const missing = (): Extracted => ({ status: !loaded ? "loading" : RANKN[plan] < RANKN[mt.tier] ? "locked" : "nodata", pts: [] });
  if (mt.src === "ixval" || b.ixl) {   // an index series (see Bundle): daily points, no statement periods
    const rows = mt.src === "ixval" ? b.ixv?.rows : b.ixl?.rows;
    if (!rows) return missing();
    const key = mt.src === "ixval" ? mt.key : "c";
    const pts = rows.map((r): Pt => ({ t: r.d, v: finite((r as unknown as Record<string, unknown>)[key]) }));
    return { status: pts.some((p) => p.v != null) ? "ok" : "nodata", pts };
  }
  if (mt.grain !== "price" && mt.grain !== "composition" && !mt.periods.includes(basis)) return { status: "noperiod", pts: [] };

  if (mt.src === "price") {
    const s = b.price?.series;
    if (!s) return missing();
    const arr = (s as unknown as Record<string, Series | number[] | undefined>)[mt.key];
    if (!arr) return { status: "nodata", pts: [] };
    const hasO = mt.key === "c" && Array.isArray(s.o) && Array.isArray(s.h) && Array.isArray(s.l) && s.o.length === s.t.length;
    const pts = s.t.map((t, i): Pt => ({
      t, v: finite(arr[i]),
      ...(hasO ? { o: finite(s.o![i]), h: finite(s.h![i]), lo: finite(s.l![i]) } : {}),
    }));
    return { status: pts.some((p) => p.v != null) ? "ok" : "nodata", pts, ohlc: hasO && pts.some((p) => p.o != null && p.h != null && p.lo != null) };
  }
  if (mt.src === "pl" || mt.src === "bs" || mt.src === "cf") {
    const t = !b.fin ? undefined : basis === "quarterly" ? b.fin.quarterly.pl : b.fin.yearly[mt.src];
    if (!t) return missing();
    const pts = zip(t.periodEnds, t.periods, t.rows[mt.key]);
    return { status: pts.some((p) => p.v != null) ? "ok" : "nodata", pts };
  }
  if (mt.src === "ratio" || mt.src === "val") {
    const h = mt.src === "ratio" ? b.ratios?.history : b.ratios?.valuationHistory;
    if (!h) return missing();
    const row = (h.rows as Record<string, Series | undefined>)[mt.key];
    if (!row) return missing();
    const ends = new Map<string, string>();
    b.fin?.yearly.pl.periods.forEach((p, i) => ends.set(p, b.fin!.yearly.pl.periodEnds[i]));
    const pts = zip(h.periods.map((p) => ends.get(p) ?? fyEnd(p)), h.periods, row);
    return { status: pts.some((p) => p.v != null) ? "ok" : "nodata", pts };
  }
  if (mt.src === "own") {
    const o = b.own;
    if (!o) return missing();
    const row = o.series[mt.key];
    if (!row) return { status: "nodata", pts: [] };
    let pts = zip(o.periods.map(monthEnd), o.periods, row);
    if (basis === "annual") pts = pts.filter((p) => p.t.slice(5, 7) === "03");   // the March quarter closes the financial year
    return { status: pts.some((p) => p.v != null) ? "ok" : "nodata", pts };
  }
  if (mt.src === "seg") {
    const sg = b.seg;
    if (!sg) return missing();
    const cats = sg.latest.filter((x) => x.revenue != null).map((x) => ({ name: x.name, value: x.revenue as number, note: x.includes?.length ? "Includes " + x.includes.join(", ") : undefined }));
    return { status: cats.length ? "ok" : RANKN[plan] < RANKN[mt.tier] ? "locked" : "nodata", pts: [], cats };
  }
  if (mt.src === "ownnow") {
    const o = b.own;
    if (!o) return missing();
    const cats = o.latest.filter((x) => x.value != null).map((x) => ({ name: x.label, value: x.value as number }));
    return { status: cats.length ? "ok" : "nodata", pts: [], cats };
  }
  return { status: "nodata", pts: [] };
}

// ------------------------------------------------------------------ number formats (Indian grouping, true minus)

const trim = (n: number, d: number) => nf(n, d).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
const sign = (v: number) => (v < 0 ? MINUS : "");

/** Full value for a tooltip, table or CSV-adjacent text. */
export function fmtValue(v: number | null | undefined, unit: UnitId): string {
  if (v == null || !Number.isFinite(v)) return "—";
  switch (unit) {
    case "cr": return sign(v) + "₹" + nf(v, Math.abs(v) >= 1000 ? 0 : 2) + " Cr";
    case "inr": return sign(v) + "₹" + nf(v, 2);
    case "pct": return sign(v) + nf(v, 2) + "%";
    case "x": return sign(v) + nf(v, 2) + "×";
    case "days": return sign(v) + nf(v, 0) + " days";
    case "sh": return sign(v) + nf(v, 0);
    case "idx": return sign(v) + nf(v, 1);
    case "pts": return sign(v) + nf(v, 2);
  }
}
/** Short value for an axis tick or a heat-map cell. */
export function fmtTick(v: number, unit: UnitId): string {
  const a = Math.abs(v);
  if (unit === "cr") return sign(v) + (a >= 1e5 ? trim(a / 1e5, 1) + "L" : trim(a, a >= 100 ? 0 : 1));
  if (unit === "sh") return sign(v) + (a >= 1e9 ? trim(a / 1e9, 1) + "B" : a >= 1e6 ? trim(a / 1e6, 1) + "M" : a >= 1e3 ? trim(a / 1e3, 1) + "K" : trim(a, 0));
  const body = trim(a, a >= 100 ? 0 : a >= 10 ? 1 : 2);
  return sign(v) + body + (unit === "pct" ? "%" : unit === "x" ? "×" : "");
}
