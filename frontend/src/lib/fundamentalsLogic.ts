// Pure logic for the Gold "Stock fundamentals" extras: key-factor panels, Financial Snapshot, P&L growth, bank asset quality, data notes.
// Definitions follow the upstream stock dashboard (buildMarketMetricsSnapshot, fundamentalGrowth, BankAssetQualityTable, DataQualitySection).
// Rule: a missing value is null and shows as a dash. Nothing is estimated or filled in.

export type Pt = { period: string; value: number | null; change?: number | null };
export type Row = { category?: string; label?: string; history?: Pt[] };
export const DASH = "—";

export const toNum = (v: unknown): number | null => {
  if (v == null || v === "" || typeof v === "boolean") return null;
  const n = Number(String(v).replace("%", ""));
  return Number.isFinite(n) ? n : null;
};
const normName = (s: unknown) => String(s ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
const fmtN = (v: number, d: number) => v.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: d });
/** Plain number, dash when missing. */
export const fmt = (v: number | null | undefined, d = 2) => (v == null ? DASH : fmtN(v, d));
export const fmtPct = (v: number | null | undefined, d = 1) => (v == null ? DASH : fmtN(v, d) + "%");
export const fmtSignedPct = (v: number | null | undefined, d = 1) => (v == null ? DASH : (v > 0 ? "+" : "") + fmtN(v, d) + "%");
const withUnit = (v: number | null, unit?: string) => (v == null ? DASH : fmtN(v, Math.abs(v) >= 100 ? 0 : 2) + (unit ? " " + unit : ""));

export const hist = (rows: Row[] | undefined, category: string): Pt[] => (rows || []).find((r) => r.category === category)?.history || [];
export const latest = (rows: Row[] | undefined, category: string): Pt | undefined => hist(rows, category)[0];
export const safeRatio = (a: unknown, b: unknown, mult = 100): number | null => { const x = toNum(a), y = toNum(b); return x == null || y == null || y === 0 ? null : (x / y) * mult; };

export type Ratio = { name: string; company_value: number | null; sector_value?: number | null };
export const ratioBy = (ratios: Ratio[] | undefined, names: string[]) => { const set = names.map(normName); return (ratios || []).find((r) => set.includes(normName(r.name))); };

// ---------- price series: EMA, RSI, returns (same formulas as upstream)
export type Px = { date: string; close: number | null };
export type PricePoint = { date: string; price: number; ema50: number | null; ema200: number | null; rsi: number | null };
export function pricePoints(history: Px[] | undefined): PricePoint[] {
  const rows = [...(history || [])].filter((r) => r.date && toNum(r.close) != null).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  let e50: number | null = null, e200: number | null = null;
  return rows.map((r, i) => {
    const c = Number(r.close);
    e50 = e50 == null ? c : c * (2 / 51) + e50 * (1 - 2 / 51);
    e200 = e200 == null ? c : c * (2 / 201) + e200 * (1 - 2 / 201);
    let rsi: number | null = null;
    if (i >= 14) {
      let g = 0, l = 0;
      for (let k = i - 13; k <= i; k++) { const d = Number(rows[k].close) - Number(rows[k - 1].close); if (d >= 0) g += d; else l += -d; }
      rsi = l === 0 ? 100 : 100 - 100 / (1 + g / 14 / (l / 14));
    }
    return { date: String(r.date), price: c, ema50: i >= 49 ? e50 : null, ema200: i >= 199 ? e200 : null, rsi };
  });
}
export function priceReturn(points: PricePoint[], sessions: number): number | null {
  if (points.length <= sessions) return null;
  const last = points[points.length - 1], prev = points[points.length - 1 - sessions];
  return safeRatio(last.price - prev.price, prev.price);
}

// ---------- growth helpers
export function cagr(history: Pt[], preferredYears = 5): { value: number | null; years: number; from?: string; to?: string } {
  const usable = history.filter((p) => (toNum(p.value) ?? 0) > 0);
  if (usable.length < 2) return { value: null, years: 0 };
  const years = Math.min(preferredYears, usable.length - 1), a = usable[0], b = usable[years];
  return { value: (Math.pow(Number(a.value) / Number(b.value), 1 / years) - 1) * 100, years, from: b.period, to: a.period };
}
export const cagrLabel = (prefix: string, c: { years: number }) => (c.years ? `${c.years}Y ${prefix} CAGR` : `${prefix} CAGR`);

function avgRatio(num: Pt[], den: Pt[], count = 5): number | null {
  const by = new Map(den.map((p) => [p.period, toNum(p.value)]));
  const vals = num.slice(0, count).map((p) => { const d = by.get(p.period), n = toNum(p.value); return d && n != null ? n / d : null; }).filter((v): v is number => v != null && Number.isFinite(v));
  return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
}

/** Dividend as a percent of the latest price over the trailing window. Null when there are no actions to read at all. */
export function dividendReturn(actions: { type?: string; ex_date?: string; amount?: unknown }[] | undefined, price: number | null, months: number, endDate?: string): number | null {
  if (!price || !actions?.length) return null;
  const end = endDate ? new Date(endDate + "T00:00:00") : new Date();
  const cutoff = new Date(end.getTime()); cutoff.setMonth(cutoff.getMonth() - months);
  let total = 0;
  for (const a of actions) {
    if (!/divid/i.test(a.type || "")) continue;
    const d = a.ex_date ? new Date(String(a.ex_date).slice(0, 10) + "T00:00:00") : null;
    if (d && !Number.isNaN(d.getTime()) && (d < cutoff || d > end)) continue;
    total += toNum(a.amount) || 0;
  }
  return (total / price) * 100;
}

// ---------- key factors
export type Factor = { label: string; value: number | null; text: string; bench?: number | null; benchText?: string; note?: string };
export type SnapshotRow = { label: string; text: string; value: number | null; change: number | null; changeText: string };
export type Panels = { dna: { label: string; text: string }[]; valuation: Factor[]; quality: Factor[]; technicals: Factor[]; snapshot: SnapshotRow[]; isBank: boolean };

export type FundInput = {
  profile?: { sector?: string; industry?: string; marketCap?: unknown };
  instrument?: { name?: string };
  quote?: { price?: number };
  ratios?: Ratio[];
  incomeStatement?: { units_in?: string; income_statement?: Row[] };
  balanceSheet?: { units_in?: string; balance_sheet?: Row[]; history?: { period?: string; total_asset?: unknown }[] };
  cashFlow?: { units_in?: string; cash_flow?: Row[] };
  shareholding?: Row[];
  priceHistory?: Px[];
  corporateActions?: { type?: string; ex_date?: string; amount?: unknown }[];
};

export const isBankLike = (d: Pick<FundInput, "profile" | "instrument">) => /\bbank\b|banking|nbfc|financial services/.test([d.profile?.sector, d.profile?.industry, d.instrument?.name].filter(Boolean).join(" ").toLowerCase());

export function buildPanels(d: FundInput, annual?: FundInput): Panels {
  const a = annual || d, isBank = isBankLike(d), inc = d.incomeStatement?.income_statement, incA = a.incomeStatement?.income_statement || inc, cfA = a.cashFlow?.cash_flow || d.cashFlow?.cash_flow;
  const unit = d.incomeStatement?.units_in, cfUnit = d.cashFlow?.units_in, bsUnit = d.balanceSheet?.units_in;
  const price = toNum(d.quote?.price);
  const pe = ratioBy(d.ratios, ["P/E", "PE", "Price Earnings"]), pb = ratioBy(d.ratios, ["P/B", "PB", "Price Book"]);
  const roe = ratioBy(d.ratios, ["ROE", "Return On Equity"]), roce = ratioBy(d.ratios, ["ROCE", "Return On Capital"]);
  const de = ratioBy(d.ratios, ["Debt / Equity", "Debt Equity", "Total Debt To Equity"]);
  const dyR = ratioBy(d.ratios, ["Dividend Yield", "DividendYield"]);
  const evEbit = ratioBy(d.ratios, ["EV/EBIT", "Enterprise Value To EBIT"]), evEbitda = ratioBy(d.ratios, ["EV/EBITDA"]), evSales = ratioBy(d.ratios, ["EV/Sales", "Enterprise Value To Sales"]);
  const tax = ratioBy(d.ratios, ["Effective Tax Rate", "Tax Rate"]);
  const pts = pricePoints(d.priceHistory), lp = pts[pts.length - 1];
  const divRet = dividendReturn(d.corporateActions, price, 12, lp?.date);
  const dy = toNum(dyR?.company_value) ?? divRet;
  const rev = latest(inc, "revenue"), np = latest(inc, "net_profit"), op = latest(inc, "operating_profit"), fin = latest(inc, "financing_profit"), intr = latest(inc, "interest"), exc = latest(inc, "exceptional_items");
  const cfo = latest(d.cashFlow?.cash_flow, "operating"), bs = d.balanceSheet?.history?.[0];
  const fii = latest(d.shareholding, "fii"), dii = latest(d.shareholding, "other_dii"), mf = latest(d.shareholding, "mutual_funds");
  const instVals = [fii, dii, mf].map((p) => toNum(p?.value));
  const inst = instVals.every((v) => v == null) ? null : instVals.reduce<number>((s, v) => s + (v || 0), 0);
  const salesC = cagr(hist(incA, "revenue")), ebitC = cagr(hist(incA, "operating_profit"));
  const annualNp = latest(incA, "net_profit"), annualCfo = latest(cfA, "operating");
  const debtH = hist((a.balanceSheet?.balance_sheet), "borrowings"), eqH = hist(a.balanceSheet?.balance_sheet, "equity"), cashH = hist(a.balanceSheet?.balance_sheet, "cash_and_cash_equivalents");
  const netDebt = debtH.map((p) => ({ ...p, value: (toNum(p.value) || 0) - (toNum(cashH.find((c) => c.period === p.period)?.value) || 0) }));
  const ebitInt = avgRatio(hist(incA, "operating_profit"), hist(incA, "interest"));
  const ndEq = avgRatio(netDebt, eqH) ?? toNum(de?.company_value);
  const payout = safeRatio(dyR?.company_value, pe?.company_value);
  const f = (label: string, value: number | null, text: string, extra: Partial<Factor> = {}): Factor => ({ label, value, text, ...extra });
  const pctF = (label: string, v: number | null, extra: Partial<Factor> = {}) => f(label, v, fmtPct(v), extra);

  const mcap = toNum(d.profile?.marketCap);
  const dna = [
    { label: "Industry", text: d.profile?.industry || d.profile?.sector || DASH },
    { label: "Market cap", text: mcap != null ? `₹${fmtN(mcap, 0)} Cr` : DASH },
    { label: "P/E", text: fmt(toNum(pe?.company_value)) }, { label: "Industry P/E", text: fmt(toNum(pe?.sector_value)) },
    { label: "Dividend yield", text: fmtPct(dy) }, { label: "Debt to equity", text: fmt(toNum(de?.company_value)) },
    { label: "Return on equity", text: fmtPct(toNum(roe?.company_value)) }, { label: "Price to book", text: fmt(toNum(pb?.company_value)) },
    { label: isBank ? "Interest earned" : "Net sales", text: withUnit(toNum(rev?.value), unit) }, { label: "Net profit", text: withUnit(toNum(np?.value), unit) },
  ];
  const valuation = [
    f("P/E ratio", toNum(pe?.company_value), fmt(toNum(pe?.company_value)), { bench: toNum(pe?.sector_value), benchText: fmt(toNum(pe?.sector_value)) }),
    f("Price to book", toNum(pb?.company_value), fmt(toNum(pb?.company_value)), { bench: toNum(pb?.sector_value), benchText: fmt(toNum(pb?.sector_value)) }),
    f("EV to EBIT", toNum(evEbit?.company_value), fmt(toNum(evEbit?.company_value)), { bench: toNum(evEbit?.sector_value), benchText: fmt(toNum(evEbit?.sector_value)) }),
    f("EV to EBITDA", toNum(evEbitda?.company_value), fmt(toNum(evEbitda?.company_value)), { bench: toNum(evEbitda?.sector_value), benchText: fmt(toNum(evEbitda?.sector_value)) }),
    f("EV to sales", toNum(evSales?.company_value), fmt(toNum(evSales?.company_value)), { bench: toNum(evSales?.sector_value), benchText: fmt(toNum(evSales?.sector_value)) }),
    pctF("Dividend yield", dy), pctF("ROCE (latest)", toNum(roce?.company_value), { bench: toNum(roce?.sector_value), benchText: fmtPct(toNum(roce?.sector_value)) }),
    pctF("ROE (latest)", toNum(roe?.company_value), { bench: toNum(roe?.sector_value), benchText: fmtPct(toNum(roe?.sector_value)) }),
  ];
  const quality = [
    pctF(cagrLabel("Sales", salesC), salesC.value, { note: salesC.from ? `${salesC.from} to ${salesC.to}` : undefined }),
    pctF(cagrLabel("EBIT", ebitC), ebitC.value, { note: ebitC.from ? `${ebitC.from} to ${ebitC.to}` : undefined }),
    f("EBIT to interest", ebitInt, fmt(ebitInt), { note: "Average of up to 5 years, times" }),
    f("Net debt to equity", ndEq, fmt(ndEq), { note: "Average of up to 5 years, times" }),
    pctF("Tax ratio", toNum(tax?.company_value)), pctF("Dividend payout", payout, { note: "Dividend yield ÷ P/E" }),
    pctF("Institutional holding", inst, { note: "FII + other DII + mutual funds" }), pctF("ROCE", toNum(roce?.company_value)), pctF("ROE", toNum(roe?.company_value)),
    pctF("Cash from operations ÷ net profit", safeRatio(annualCfo?.value, annualNp?.value), { note: "Latest year" }),
  ];
  const vs = (p: number | null, e: number | null) => (e ? safeRatio(p == null ? null : p - e, e) : null);
  const technicals = [
    f("RSI (14)", lp?.rsi ?? null, fmt(lp?.rsi ?? null, 1), { note: "Above 70 stretched, below 30 weak" }),
    pctF("Price vs 50-day average", lp ? vs(lp.price, lp.ema50) : null), pctF("Price vs 200-day average", lp ? vs(lp.price, lp.ema200) : null),
    pctF("1-month price return", priceReturn(pts, 21)), pctF("6-month price return", priceReturn(pts, 126)), pctF("1-year price return", priceReturn(pts, 252)),
  ];
  const sn = (label: string, p: Pt | undefined, u?: string, nameChange = true): SnapshotRow => { const v = toNum(p?.value), c = nameChange ? toNum(p?.change) : null; return { label, value: v, text: withUnit(v, u), change: c, changeText: fmtSignedPct(c) }; };
  const opm = safeRatio(op?.value, rev?.value), nm = safeRatio(np?.value, rev?.value);
  const snapshot: SnapshotRow[] = [
    sn(isBank ? "Interest earned" : "Net sales", rev, unit), sn(isBank ? "Financing profit" : "Operating profit", isBank ? fin : op, unit), sn(isBank ? "Interest expended" : "Interest", intr, unit), sn("Exceptional items", exc, unit),
    { label: "Operating margin", value: opm, text: fmtPct(opm), change: null, changeText: DASH }, { label: "Net margin", value: nm, text: fmtPct(nm), change: null, changeText: DASH },
    sn("Operating cash flow", cfo, cfUnit), { label: "Total assets", value: toNum(bs?.total_asset), text: withUnit(toNum(bs?.total_asset), bsUnit), change: null, changeText: DASH }, sn("Net profit", np, unit),
  ];
  return { dna, valuation, quality, technicals, snapshot, isBank };
}

/** A sentence that states what a set of factors says. Used as the chart's aria-label. Never mentions a missing value as if it were known. */
export function valuationSentence(rows: Factor[]): string {
  const pairs = rows.filter((r) => r.value != null && r.bench != null && r.bench !== 0 && /P\/E|book/i.test(r.label));
  if (!pairs.length) return "Valuation: no company-against-industry comparison is available.";
  const parts = pairs.map((r) => { const diff = ((r.value as number) / (r.bench as number) - 1) * 100; return `${r.label} ${r.text} against industry ${r.benchText}, ${Math.abs(diff) < 3 ? "about the same" : diff > 0 ? `${Math.round(diff)}% above` : `${Math.round(-diff)}% below`}`; });
  return "Valuation: " + parts.join("; ") + ".";
}
export function signedSentence(title: string, rows: Factor[]): string {
  const ok = rows.filter((r) => r.value != null);
  if (!ok.length) return `${title}: no figures are available.`;
  const pos = ok.filter((r) => (r.value as number) > 0).length, neg = ok.filter((r) => (r.value as number) < 0).length;
  const best = [...ok].sort((a, b) => (b.value as number) - (a.value as number))[0];
  return `${title}: ${ok.length} of ${rows.length} figures available, ${pos} positive and ${neg} negative. Highest is ${best.label} at ${best.text}.`;
}
export function snapshotSentence(rows: SnapshotRow[], unitless = false): string {
  const ch = rows.filter((r) => r.change != null);
  if (!ch.length) return "Financial snapshot: no period-on-period changes are available.";
  const up = ch.filter((r) => (r.change as number) > 0).length;
  return `Financial snapshot: ${up} of ${ch.length} reported lines rose against the previous period${unitless ? "" : ""}.`;
}

// ---------- growth (YoY / QoQ), from the statement rows
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
export function periodIndex(label: string, period: "yearly" | "quarterly"): number | null {
  const text = String(label || ""), year = text.match(/\b(19\d{2}|20\d{2})\b/);
  if (!year || /TTM|YTD/i.test(text)) return null;
  if (period === "yearly") return Number(year[1]);
  const m = MONTHS.findIndex((n) => new RegExp(`^${n}`, "i").test(text.trim()));
  return m >= 0 ? Number(year[1]) * 12 + m : null;
}
export const GROWTH_METRICS = [
  { key: "revenue", label: "Revenue growth", match: /^(revenue|net_?sales|total_?income|interest_?earned)$/i, color: "var(--c1)" },
  { key: "profit", label: "Net profit growth", match: /^(net_?profit|pat)$/i, color: "var(--gold)" },
  { key: "eps", label: "EPS growth", match: /^(eps|basic_?eps|diluted_?eps|basic_?re_?in_?r|diluted_?re_?in_?r)$/i, color: "var(--c3)" },
] as const;
export type GrowthKey = (typeof GROWTH_METRICS)[number]["key"];
export type GrowthPoint = { period: string } & Record<GrowthKey, number | null> & { reasons: Partial<Record<GrowthKey, string>> };

/** Growth % = (current − comparison) ÷ comparison × 100, newest last. Null (shown as a dash) when the value or the matching earlier period is missing, or the comparison is zero or negative. */
export function buildGrowth(rows: Row[], period: "yearly" | "quarterly", basis: "yoy" | "qoq"): GrowthPoint[] {
  const series = GROWTH_METRICS.map((m) => {
    const row = (rows || []).find((r) => r.history?.length && (m.match.test(r.category || "") || m.match.test((r.label || "").replace(/\s+/g, "_"))));
    const by = new Map<number, { period: string; value: number | null }>();
    (row?.history || []).forEach((p) => { const i = periodIndex(p.period, period); if (i != null) by.set(i, { period: p.period, value: toNum(p.value) }); });
    return { m, by };
  });
  const all = series.flatMap((s) => [...s.by.keys()]);
  if (!all.length) return [];
  const step = period === "yearly" ? 1 : 3, lag = period === "yearly" ? 1 : basis === "qoq" ? 3 : 12;
  const end = Math.max(...all), start = Math.max(Math.min(...all), end - step * (period === "yearly" ? 9 : 23));
  const out: GrowthPoint[] = [];
  for (let i = start; i <= end; i += step) {
    const label = series.map((s) => s.by.get(i)?.period).find(Boolean) || (period === "yearly" ? String(i) : `${MONTHS[i % 12][0].toUpperCase()}${MONTHS[i % 12].slice(1)} ${Math.floor(i / 12)}`);
    const pt = { period: label, revenue: null, profit: null, eps: null, reasons: {} } as GrowthPoint;
    for (const { m, by } of series) {
      const cur = by.get(i)?.value ?? null, prev = by.get(i - lag)?.value ?? null;
      const reason = cur == null ? "Reported value unavailable" : prev == null ? "Matching earlier period unavailable" : prev <= 0 ? "Earlier value is zero or negative" : null;
      pt[m.key] = reason ? null : ((cur as number) - (prev as number)) / (prev as number) * 100;
      if (reason) pt.reasons[m.key] = reason;
    }
    out.push(pt);
  }
  return out;
}
export function growthSentence(data: GrowthPoint[], basisLabel: string): string {
  const last = data[data.length - 1];
  if (!last) return "Growth: not enough comparable data.";
  const bit = (m: (typeof GROWTH_METRICS)[number]) => `${m.label.replace(" growth", "").toLowerCase()} ${last[m.key] == null ? "not available" : fmtSignedPct(last[m.key], 1)}`;
  return `Growth ${basisLabel} for ${last.period}: ${GROWTH_METRICS.map(bit).join(", ")}.`;
}

// ---------- bank asset quality
export const ASSET_QUALITY: [string, string][] = [["gross_npa_percent", "Gross NPA %"], ["net_npa_percent", "Net NPA %"], ["cet1_ratio", "CET1 ratio %"]];
export function assetQualityTable(rows: Row[] | undefined): { periods: string[]; rows: { category: string; label: string; values: (number | null)[] }[] } {
  const found = ASSET_QUALITY.map(([category, label]) => ({ category, label, history: (rows || []).find((r) => r.category === category)?.history || [] })).filter((r) => r.history.some((p) => toNum(p.value) != null));
  const periods: string[] = [];
  found.forEach((r) => r.history.forEach((p) => { if (p.period && !periods.includes(p.period)) periods.push(p.period); }));
  return { periods, rows: found.map((r) => ({ category: r.category, label: r.label, values: periods.map((p) => toNum(r.history.find((x) => x.period === p)?.value)) })) };
}
export function assetQualitySentence(t: ReturnType<typeof assetQualityTable>): string {
  const g = t.rows.find((r) => r.category === "gross_npa_percent");
  if (!g) return "Asset quality: gross NPA is not available.";
  const v = g.values.map((x, i) => [t.periods[i], x] as const).filter(([, x]) => x != null) as [string, number][];
  if (v.length < 2) return `Asset quality: gross NPA ${fmtPct(v[0]?.[1], 2)} in ${v[0]?.[0]}.`;
  const [np, nv] = v[0], [op, ov] = v[v.length - 1];
  return `Gross NPA ${nv < ov ? "fell" : nv > ov ? "rose" : "was unchanged"} from ${fmtPct(ov, 2)} in ${op} to ${fmtPct(nv, 2)} in ${np}.`;
}

// ---------- data notes
export type DataFlag = { severity?: string; section?: string; metric?: string; code?: string; message?: string; periods?: { period: string; finedge?: unknown; fallbackProvider?: unknown; differencePercent?: unknown }[] };
const SECTION_NAMES: Record<string, string> = { incomeStatement: "Income statement", balanceSheet: "Balance sheet", cashFlow: "Cash flow", ratios: "Ratios", profitabilityRatios: "Profitability ratios", bankAssetQuality: "Bank asset quality", revenueSegments: "Revenue segments",
  shareholding: "Shareholding", ownershipStructure: "Ownership structure", corporateActions: "Corporate actions", competitors: "Peers", priceHistory: "Price history", quote: "Latest price", profile: "Company profile", sourceResolution: "Source choice" };
export const sectionName = (s?: string) => (s && SECTION_NAMES[s]) || (s || "Data").replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
/** Sections that did not come from the primary provider, as plain sentences. */
export function fallbackSources(sources: Record<string, string> | undefined): { section: string; source: string }[] {
  return Object.entries(sources || {}).filter(([, v]) => v && !/^finedge$/i.test(String(v))).map(([k, v]) => ({ section: sectionName(k), source: String(v).replace(/^finedge:/i, "FinEdge ").replace(/^\w/, (c) => c.toUpperCase()) }));
}
export const dataNoteCount = (flags: DataFlag[] | undefined, sources: Record<string, string> | undefined) => (flags || []).filter((f) => f.message).length + fallbackSources(sources).length;
