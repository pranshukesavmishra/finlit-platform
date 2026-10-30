// A small, clearly synthetic answer of /api/etf-vs-index/options and /compare for the page tests: "Sample ETF" and "Sample Index Fund" follow a made-up path.
import type { Compare, Options } from "../etfVsIndex";

export const OPTIONS: Options = {
  indices: [
    { key: "nifty50", label: "Nifty 50", code: "NIF50", etfCount: 2, fundCount: 3, ready: true },
    { key: "sensex", label: "BSE Sensex", code: "SNSXSENSEX", etfCount: 1, fundCount: 0, ready: false },
  ],
  etfs: [
    { symbol: "SAMPLEETF", name: "Sample ETF Nifty 50", fundHouse: "Sample AMC", index: "nifty50", indexBasis: "benchmark", returnType: "TRI", benchmark: "Nifty 50 TRI", firstDate: "2016-01-04", priceDate: "2026-10-29" },
    { symbol: "OTHERETF", name: "Other ETF Nifty 50", fundHouse: "Other AMC", index: "nifty50", indexBasis: "name", returnType: null, benchmark: null, firstDate: "2016-01-04", priceDate: "2026-10-29" },
    { symbol: "SENSEXETF", name: "Sample ETF Sensex", fundHouse: "Sample AMC", index: "sensex", indexBasis: "name", returnType: null, benchmark: null, firstDate: null, priceDate: null },
  ],
  funds: [
    { code: 910001, name: "Sample Nifty 50 Index Fund - Direct Plan - Growth", amc: "Sample Mutual Fund", plan: "Direct", index: "nifty50", indexBasis: "benchmark", returnType: "TRI", benchmark: "Nifty 50 TRI", navDate: "2026-10-29" },
    { code: 910002, name: "Other Nifty 50 Index Fund - Direct Plan - Growth Option", amc: "Other Mutual Fund", plan: "Direct", index: "nifty50", indexBasis: "name", returnType: null, benchmark: null, navDate: "2026-10-29" },
    { code: 910003, name: "Third Nifty 50 Index Fund - Direct Plan - Growth", amc: "Third Mutual Fund", plan: "Direct", index: "nifty50", indexBasis: "name", returnType: null, benchmark: null, navDate: "2026-10-29" },
  ],
  plan: "Direct", unmatchedFunds: 1, conflicts: 0, asOf: "2026-10-29", source: "test", disclaimer: "Information only, not investment advice. Past returns do not guarantee future returns.",
};

const ret = (value: number | null, cagr: number | null = null, why: string | null = null) => ({ value, cagr, from: value == null ? null : "2025-10-29", to: "2026-10-29", why });
const risk = (vol: number, mdd: number) => ({
  volatility: vol, volatilityWhy: null, maxDrawdown: { value: mdd, peak: "2024-09-27", trough: "2025-03-28" }, downside: vol * 0.7, downsideWhy: null, worstRolling: { value: -9.5, end: "2025-04-01" }, worstRollingWhy: null,
  best: { value: 3.1, date: "2024-06-04" }, worst: { value: -3.4, date: "2024-06-03" }, from: "2021-10-29", to: "2026-10-29", days: 1300,
});
const t = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2021, 9, 29 + i * 50)).toISOString().slice(0, 10)).filter((d) => d <= "2026-10-29");
export const COMPARE: Compare = {
  index: { key: "nifty50", label: "Nifty 50", code: "NIF50", levels: "price index, dividends not included", why: null }, plan: "Direct",
  products: [
    { id: "SAMPLEETF", kind: "etf", name: "Sample ETF Nifty 50", label: "SAMPLEETF", house: "Sample AMC", plan: "Exchange traded", benchmark: "Nifty 50 TRI", indexBasis: "benchmark", returnType: "TRI", basis: "price", source: "NSE closing price", first: "2016-01-04", last: "2026-10-29" },
    { id: "910001", kind: "fund", name: "Sample Nifty 50 Index Fund - Direct Plan - Growth", label: "Sample Nifty 50 Index Fund", house: "Sample Mutual Fund", plan: "Direct", benchmark: null, indexBasis: "name", returnType: null, basis: "nav", source: "AMFI NAV", first: "2016-01-04", last: "2026-10-29" },
  ],
  common: { days: 1300, from: "2021-10-29", to: "2026-10-29", why: null },
  returns: Object.fromEntries(["SAMPLEETF", "910001"].map((id, k) => [id, {
    "1M": ret(1.2 - k * 0.01), "3M": ret(3.4 - k * 0.01), "6M": ret(6.1), "1Y": ret(11.2 - k * 0.05), "3Y": ret(38.5, 11.45 - k * 0.1), "5Y": ret(null, null, "Common history starts on 29 Oct 2021, after the 5 years start date (29 Oct 2021)."),
    since: ret(80.2 - k, 12.5 - k * 0.1),
  }])),
  rolling: {
    ref: "SAMPLEETF", windows: 1000,
    stats: { SAMPLEETF: { count: 1000, median: 11.9, best: 31.2, worst: -4.1, mean: 12.3, positive: 88.5, why: null }, "910001": { count: 1000, median: 11.8, best: 31.0, worst: -4.3, mean: 12.1, positive: 88.1, why: null } },
    headToHead: { "910001": { ahead: 12.5, level: 3.5, behind: 84, windows: 1000 } },
  },
  sip: { SAMPLEETF: { installments: 61, invested: 610000, units: 2500.1234, value: 900000, gain: 290000, gainPct: 47.54, first: "2021-10-29", last: "2026-10-29", endDate: "2026-10-29", endPrice: 360, xirr: 14.2, xirrWhy: null },
         "910001": { installments: 61, invested: 610000, units: 2490.1, value: 895000, gain: 285000, gainPct: 46.72, first: "2021-10-29", last: "2026-10-29", endDate: "2026-10-29", endPrice: 359.4, xirr: 14.1, xirrWhy: null, diffVsRef: { rupees: -5000, pct: -0.56 } } },
  lump: { SAMPLEETF: { startDate: "2021-10-29", startPrice: 200, endDate: "2026-10-29", endPrice: 360, units: 500, value: 180000, gain: 80000, gainPct: 80, cagr: 12.5, diffVsRef: null },
          "910001": { startDate: "2021-10-29", startPrice: 200.5, endDate: "2026-10-29", endPrice: 359.4, units: 498.7531, value: 179251.87, gain: 79251.87, gainPct: 79.25, cagr: 12.4, diffVsRef: { rupees: -748.13, pct: -0.42 } } },
  startDay: "2021-10-29",
  tracking: {
    SAMPLEETF: { td: { "1Y": { value: 1.1, annual: null, why: null, product: 11.2, index: 10.1 }, "3Y": { value: 4.0, annual: 1.28, why: null, product: 38.5, index: 34.5 }, "5Y": { value: null, annual: null, why: "Common history starts on 29 Oct 2021." } }, gap: {}, te: { value: 0.12, returns: 1250, why: null, from: "2021-10-29", to: "2026-10-29" } },
    "910001": { td: { "1Y": { value: 1.05, annual: null, why: null, product: 11.15, index: 10.1 }, "3Y": { value: 3.9, annual: 1.25, why: null, product: 38.4, index: 34.5 }, "5Y": { value: null, annual: null, why: "Common history starts on 29 Oct 2021." } },
      gap: { "1Y": { value: -0.05, why: null }, "3Y": { value: -0.1, why: null }, "5Y": { value: null, why: "Common history starts on 29 Oct 2021." } }, te: { value: 0.31, returns: 1250, why: null, from: "2021-10-29", to: "2026-10-29" } },
  },
  risk: {
    "1Y": { products: { SAMPLEETF: risk(11.2, -8.1), "910001": risk(11.3, -8.2) }, from: "2025-10-29", to: "2026-10-29" },
    "3Y": { products: { SAMPLEETF: risk(12.2, -12.1), "910001": risk(12.3, -12.2) }, from: "2023-10-29", to: "2026-10-29" },
    "5Y": { why: "Common history starts on 29 Oct 2021, less than 5 years before 29 Oct 2026." },
    all: { products: { SAMPLEETF: risk(13.2, -14.1), "910001": risk(13.3, -14.2) }, from: "2021-10-29", to: "2026-10-29" },
  },
  chart: { t, v: { SAMPLEETF: t.map((_, i) => 200 + i * 4.1), "910001": t.map((_, i) => 200.5 + i * 4.05) }, index: t.map((_, i) => 18000 + i * 300), indexWhy: null },
  costs: {
    SAMPLEETF: { ter: { value: "0.05% a year", asOf: "2026-10-01", source: "AMFI, TER of mutual fund schemes" }, terPct: 0.05, dragPerYear: 500, exitLoad: { value: "None when sold on the stock exchange", source: "NSE trading rules" }, minimum: { value: "1 unit, bought on the stock exchange", source: "NSE trading rules" }, aum: { value: null, why: "AUM not loaded." } },
    "910001": { ter: { value: "0.20% a year", asOf: "2026-10-01", source: "AMFI, TER of mutual fund schemes" }, terPct: 0.2, dragPerYear: 2000, exitLoad: { value: null, why: "Exit load is stated in each scheme's own documents." }, minimum: { value: null, why: "A minimum SIP amount is stated in each scheme's own documents." }, aum: { value: null, why: "AUM not loaded." } },
  },
  etfExtra: { SAMPLEETF: { premium: 0.04, navDate: "2026-10-29" } },
  summary: {
    rows: [
      { category: "Returns", measure: "Higher return over 3 years", unit: "% a year", tol: 0.25, leaders: [], level: true, values: { SAMPLEETF: 11.45, "910001": 11.35 }, gap: 0, text: "Higher return over 3 years: level (within 0.25 percentage points)", windowLabel: "3Y" },
      { category: "Cost", measure: "Lower expense ratio", unit: "% a year", tol: 0.02, leaders: ["SAMPLEETF"], level: false, values: { SAMPLEETF: 0.05, "910001": 0.2 }, gap: 0.15, text: "Lower expense ratio: SAMPLEETF", windowLabel: null },
      { category: "Tracking", measure: "Smaller tracking error", unit: "% a year", tol: 0.1, leaders: ["SAMPLEETF"], level: false, values: { SAMPLEETF: 0.12, "910001": 0.31 }, gap: 0.19, text: "Smaller tracking error: SAMPLEETF", windowLabel: null },
      { category: "Risk", measure: "Smaller maximum fall", unit: "%", tol: 0.5, leaders: [], level: true, values: { SAMPLEETF: 12.1, "910001": 12.2 }, gap: 0, text: "Smaller maximum fall: level (within 0.5 percentage points)", windowLabel: "3Y" },
    ],
    sentence: "Up to 29 Oct 2026, on the days all of these have a price: lower expense ratio (% a year): SAMPLEETF 0.05, Sample Nifty 50 Index Fund 0.20. Differences of this size can reverse in other periods. Information only, not investment advice.",
    tolerances: { return: 0.25, cost: 0.02, tracking: 0.1, fall: 0.5, volatility: 0.3 },
  },
  notes: ["An ETF is measured on its exchange closing price (its NAV history is not stored), a fund on its AMFI NAV."], tolerances: { return: 0.25, cost: 0.02, tracking: 0.1, fall: 0.5, volatility: 0.3 },
  inputs: { sip: 10000, lump: 100000, dragBase: 1000000 }, asOf: "2026-10-29", generatedAt: "2026-10-30T08:00:00+00:00", disclaimer: "Information only, not investment advice.",
};
