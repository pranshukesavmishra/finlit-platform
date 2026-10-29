/** The maths behind the "Decoding ROE" block under the DuPont card: normalized ROE, ROA, data gaps with reasons, anomaly checks, insight cards from the rule config,
 *  the ROE quality score, the five-factor waterfall, the what-if arithmetic, the "how is this calculated" lines and the CSV. Pure functions only, so the component has no logic of its own.
 *
 *  The share of an ROE move that each factor explains uses the LOG method (the same one the existing DuPont tiles use): because ROE = margin x turnover x multiplier,
 *  ln(ROE last / ROE first) = ln(margin ratio) + ln(turnover ratio) + ln(multiplier ratio), so the three shares always add to 100%.
 *  Per cent changes do not add up across multiplied factors, which is why logs are used. A log is undefined for a zero or negative value (for example a loss year),
 *  so the shares are left blank there and the waterfall falls back to step-by-step substitution. */
import type { Table } from "./api";
import { csvRow } from "./graphData";
import { MINUS, nf } from "./format";
import { DRIVER_NAME, DUPONT_LIMITS as L, INSIGHT_RULES, MEASURE_FORMAT, QUALITY_SCORE, type InsightRule, type Measure } from "./dupontRules";

export type Basis = "year-end" | "average";
export type View = "reported" | "normalized";
export type Why = { short: string; long: string };
export type FiveFactors = { taxBurden: number; interestBurden: number; ebitMargin: number; turnover: number; multiplier: number };
export type DeepYear = {
  period: string; label: string;
  sales: number | null; pat: number | null; pbt: number | null; tax: number | null; exceptional: number | null; discontinued: number | null;
  endAssets: number | null; endEquity: number | null; baseAssets: number | null; baseEquity: number | null; averaged: boolean; fellBack: boolean;
  netMargin: number | null; turnover: number | null; multiplier: number | null; roa: number | null; roe: number | null;                 // per cent, times, times, per cent, per cent (2 decimals, like the DuPont card)
  normPat: number | null; normMargin: number | null; normRoa: number | null; normRoe: number | null;
  taxRate: number; taxRateFallback: boolean; taxRateClamped: boolean;
  oneOff: number; oneOffShare: number | null; lowQuality: boolean; notMeaningful: boolean;
  five: FiveFactors | null; rawRoe: number | null;                                                                                  // unrounded five-factor inputs for the waterfall
  why: { netMargin: Why | null; turnover: Why | null; multiplier: Why | null; roe: Why | null; oneOff: Why | null };
  complete: boolean;
};
export type Anomaly = { period: string; label: string; kind: "margin-high" | "oneoff-implausible" | "step-multiplier" | "step-margin"; text: string; target: "financials" };

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const at = (t: Table | undefined, key: string, p: string): number | null => { const i = t?.periods.indexOf(p) ?? -1; return i >= 0 ? num(t?.rows[key]?.[i]) : null; };
const div = (a: number | null, b: number | null) => (a == null || b == null || b === 0 ? null : a / b);
const r = (v: number | null, d = 2) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);
const sg = (v: number, d = 1) => (v < 0 ? MINUS : "") + nf(v, d);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const crore = (v: number) => (v < 0 ? MINUS : "") + nf(v, 0);

/** "FY23" is the year to March 2023, as everywhere else on the stock page. */
export const periodLabel = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);

// ------------------------------------------------------------------------------------------------ the year table

export function deepYears(pl: Table | undefined, bs: Table | undefined, lender: boolean, basis: Basis = "year-end", maxYears = 8): DeepYear[] {
  const all = (pl?.periods ?? []).filter((p) => bs?.periods.includes(p));
  const out: DeepYear[] = all.map((p, i) => {
    const sales = lender ? at(pl, "total_income", p) ?? at(pl, "revenue", p) : at(pl, "revenue", p);
    const pat = at(pl, "net_profit", p), pbt = at(pl, "profit_before_tax", p), tax = at(pl, "tax", p), fin = at(pl, "finance_costs", p), exc = at(pl, "exceptional_items", p), disc = at(pl, "discontinued_profit", p);
    const endAssets = at(bs, "total_assets", p), endEquity = at(bs, "total_equity", p);
    const prev = i > 0 ? all[i - 1] : null, pa = prev ? at(bs, "total_assets", prev) : null, pe = prev ? at(bs, "total_equity", prev) : null;
    const canAverage = basis === "average" && pa != null && pe != null && pe > 0 && endAssets != null && endEquity != null && endEquity > 0;
    const baseAssets = canAverage ? ((endAssets as number) + (pa as number)) / 2 : endAssets;
    const baseEquityRaw = canAverage ? ((endEquity as number) + (pe as number)) / 2 : endEquity;
    const baseEquity = baseEquityRaw != null && baseEquityRaw > 0 ? baseEquityRaw : null;
    const fellBack = basis === "average" && !canAverage && baseEquity != null;
    const thin = baseEquity != null && baseAssets != null && baseAssets > 0 && baseEquity / baseAssets < L.nearZeroEquityShare;
    const notMeaningful = thin;
    const eq = notMeaningful ? null : baseEquity;
    const nm = div(pat, sales), tu = div(sales, baseAssets), em = div(baseAssets, eq), roe = div(pat, eq), roa = div(pat, baseAssets);

    // one-offs and the tax rate used on them
    const e = exc ?? 0, d = disc ?? 0, oneOff = Math.abs(e) + Math.abs(d);
    const rawRate = pbt != null && pbt > 0 && tax != null ? tax / pbt : null;
    const taxRate = rawRate == null ? L.fallbackTaxRate : clamp(rawRate, 0, L.taxRateMax);
    const taxRateClamped = rawRate != null && (rawRate < 0 || rawRate > L.taxRateMax);
    const share = pbt != null && pbt !== 0 ? oneOff / Math.abs(pbt) : pbt === 0 && oneOff === 0 ? 0 : null;
    const lowQuality = share != null ? share > L.lowQualityShare : pbt === 0 && oneOff > 0;
    const normPat = pat == null ? null : pat - e * (1 - taxRate) - d;      // exceptional items are before tax; discontinued profit is already after tax

    // five-factor inputs (not for lenders): tax burden x interest burden x EBIT margin x turnover x multiplier = ROE exactly
    const ebit = pbt != null && fin != null ? pbt + fin : null;
    const f5 = lender ? null : { taxBurden: div(pat, pbt), interestBurden: div(pbt, ebit), ebitMargin: div(ebit, sales), turnover: tu, multiplier: em };
    const five = f5 && Object.values(f5).every((v) => v != null) ? (f5 as FiveFactors) : null;

    // reasons for every blank
    const noRev: Why = { short: "no revenue", long: sales === 0 ? "Revenue is zero for this year, so margins and turnover cannot be worked out." : `${lender ? "Total income" : "Revenue"} is not reported for this year, so margins and turnover cannot be worked out.` };
    const noProfit: Why = { short: "net profit not available", long: "Net profit is not reported for this year." };
    const noAssets: Why = { short: "assets not available", long: "Total assets are not reported on this year's balance sheet." };
    const hasParts = at(bs, "equity_capital", p) != null || at(bs, "reserves", p) != null;
    const equityWhy: Why | null = endEquity == null
      ? { short: "equity data not available", long: `The balance sheet for this year has no total equity figure from the data provider${hasParts ? " (share capital or reserves are reported, but not their total)" : ""}, so the equity multiplier and ROE cannot be worked out.` }
      : baseEquity == null
        ? { short: (baseEquityRaw as number) < 0 ? "negative equity" : "zero equity", long: `${canAverage ? "Average equity" : "Total equity"} is ${(baseEquityRaw as number) < 0 ? "negative" : "zero"} (₹${crore(baseEquityRaw as number)} crore), so the equity multiplier and ROE are not meaningful.` }
        : notMeaningful ? { short: "ROE not meaningful", long: `Equity (₹${crore(baseEquity)} crore) is under ${nf(L.nearZeroEquityShare * 100, 0)}% of total assets, so the equity multiplier is above ${nf(1 / L.nearZeroEquityShare, 0)}× and ROE is not meaningful.` }
          : null;
    const roeWhy: Why | null = roe != null ? null : pat == null ? noProfit : equityWhy ? (equityWhy.short === "equity data not available" ? equityWhy : { short: "ROE not meaningful", long: equityWhy.long }) : noProfit;
    const why = {
      netMargin: nm != null ? null : sales == null || sales === 0 ? noRev : pat == null ? noProfit : null,
      turnover: tu != null ? null : sales == null || sales === 0 ? noRev : noAssets,
      multiplier: em != null ? null : baseAssets == null || baseAssets === 0 ? noAssets : equityWhy,
      roe: roeWhy,
      oneOff: share != null ? null : pbt == null ? { short: "pre-tax profit not available", long: "Pre-tax profit is not reported for this year, so the one-off share cannot be worked out." } : { short: "pre-tax profit is zero", long: "Pre-tax profit is zero, so a one-off share cannot be worked out." },
    } as DeepYear["why"];
    const y: DeepYear = {
      period: p, label: periodLabel(p), sales, pat, pbt, tax, exceptional: exc, discontinued: disc, endAssets, endEquity, baseAssets, baseEquity, averaged: canAverage, fellBack,
      netMargin: r(nm == null ? null : nm * 100), turnover: r(tu), multiplier: r(em), roa: r(roa == null ? null : roa * 100), roe: r(roe == null ? null : roe * 100),
      normPat, normMargin: r(div(normPat, sales) == null ? null : (div(normPat, sales) as number) * 100), normRoa: r(div(normPat, baseAssets) == null ? null : (div(normPat, baseAssets) as number) * 100),
      normRoe: r(div(normPat, eq) == null ? null : (div(normPat, eq) as number) * 100),
      taxRate, taxRateFallback: rawRate == null, taxRateClamped, oneOff, oneOffShare: share, lowQuality, notMeaningful, five, rawRoe: roe == null ? null : roe * 100, why,
      complete: false,
    };
    y.complete = y.roe != null && y.netMargin != null && y.turnover != null && y.multiplier != null;
    return y;
  });
  return out.slice(-maxYears);
}

export const completeness = (years: DeepYear[]) => ({ complete: years.filter((y) => y.complete).length, total: years.length, missing: years.filter((y) => !y.complete).map((y) => y.label) });

/** The blanks in the main rows, grouped by reason: "Mar 2019, Mar 2020: equity data not available..." (for the visible list under the table). */
export function gapList(years: DeepYear[]): { labels: string[]; reason: Why }[] {
  const groups = new Map<string, { labels: string[]; reason: Why }>();
  for (const y of years) {
    const seen = new Set<string>();
    for (const w of [y.why.netMargin, y.why.turnover, y.why.multiplier, y.why.roe]) {
      if (!w || seen.has(w.long)) continue;
      seen.add(w.long);
      const g = groups.get(w.long) ?? { labels: [], reason: w }; g.labels.push(y.label); groups.set(w.long, g);
    }
  }
  return [...groups.values()];
}

// ------------------------------------------------------------------------------------------------ averages

export type Average = { window: number; years: number; used: string[]; lowQuality: string[]; noData: string[]; reported: number | null; normalized: number | null };
/** Simple mean of the annual ROE over the last `n` years shown. Low-quality years and years without a meaningful ROE are left out, and listed. */
export function averages(years: DeepYear[], n: number): Average {
  const win = years.slice(-n), used = win.filter((y) => !y.lowQuality && y.roe != null), mean = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? r(v.reduce((a, b) => a + b, 0) / v.length, 1) : null; };
  return { window: n, years: win.length, used: used.map((y) => y.label), lowQuality: win.filter((y) => y.lowQuality).map((y) => y.label), noData: win.filter((y) => !y.lowQuality && y.roe == null).map((y) => y.label),
    reported: mean(used.map((y) => y.roe)), normalized: mean(used.map((y) => y.normRoe)) };
}

// ------------------------------------------------------------------------------------------------ anomalies

export function anomalies(years: DeepYear[]): Anomaly[] {
  const out: Anomaly[] = [];
  years.forEach((y, i) => {
    const push = (kind: Anomaly["kind"], text: string) => out.push({ period: y.period, label: y.label, kind, text, target: "financials" });
    if (y.netMargin != null && y.netMargin > L.implausibleMarginPct) push("margin-high", `Net margin of ${nf(y.netMargin, 1)}% is above ${L.implausibleMarginPct}%: likely a tiny revenue base or a data issue. Check the revenue and profit lines.`);
    if (y.oneOffShare != null && y.oneOffShare > L.implausibleOneOffShare) push("oneoff-implausible", `One-off items work out to ${nf(y.oneOffShare * 100, 0)}% of pre-tax profit: an implausible ratio, likely a tiny pre-tax profit or a data issue. Read it as a caution, not a measurement.`);
    const p = i > 0 ? years[i - 1] : null;
    if (p) {
      const step = (a: number | null, b: number | null) => (a != null && b != null && a > 0 && b > 0 ? b / a - 1 : null);
      const em = step(p.multiplier, y.multiplier), nm = step(p.netMargin, y.netMargin);
      if (em != null && Math.abs(em) > L.stepChange) push("step-multiplier", `The equity multiplier went from ${nf(p.multiplier as number, 2)}× to ${nf(y.multiplier as number, 2)}× in one year (${em > 0 ? "+" : MINUS}${nf(Math.abs(em) * 100, 0)}%). ${L.stepPrompt}`);
      if (nm != null && Math.abs(nm) > L.stepChange) push("step-margin", `Net margin went from ${nf(p.netMargin as number, 1)}% to ${nf(y.netMargin as number, 1)}% in one year (${nm > 0 ? "+" : MINUS}${nf(Math.abs(nm) * 100, 0)}%). ${L.stepPrompt}`);
    }
  });
  return out;
}

// ------------------------------------------------------------------------------------------------ the move between two years (log method) and the badge

export type Move = { first: DeepYear; last: DeepYear; roeChange: number; shares: { netMargin: number | null; turnover: number | null; multiplier: number | null }; change: { netMargin: number | null; turnover: number | null; multiplier: number | null } };
/** First and last year with all three factors, and each factor's share of the ROE move (rounded factors, as the DuPont tiles do). */
export function move(years: DeepYear[]): Move | null {
  const u = years.filter((y) => y.roe != null && y.netMargin != null && y.turnover != null && y.multiplier != null);
  const a = u[0], b = u[u.length - 1];
  if (!a || !b || a === b) return null;
  const positive = (a.netMargin as number) > 0 && (b.netMargin as number) > 0 && (a.roe as number) > 0 && (b.roe as number) > 0, total = positive ? Math.log((b.roe as number) / (a.roe as number)) : null;
  const sh = (k: "netMargin" | "turnover" | "multiplier") => { const f = a[k] as number, l = b[k] as number; return total != null && Math.abs(total) > 0.02 && f > 0 && l > 0 ? r((Math.log(l / f) / total) * 100, 0) : null; };
  const ch = (k: "netMargin" | "turnover" | "multiplier") => ((a[k] as number) ? r(((b[k] as number) / (a[k] as number) - 1) * 100, 1) : null);
  return { first: a, last: b, roeChange: (b.roe as number) - (a.roe as number), shares: { netMargin: sh("netMargin"), turnover: sh("turnover"), multiplier: sh("multiplier") },
    change: { netMargin: ch("netMargin"), turnover: ch("turnover"), multiplier: ch("multiplier") } };
}

export type Driver = { key: "netMargin" | "turnover" | "multiplier"; name: string; share: number } | null;
/** The factor with the largest absolute log share of the ROE move. Null when the shares are undefined (loss year) or ROE barely moved. */
export function driver(m: Move | null): Driver {
  if (!m) return null;
  const c = (Object.entries(m.shares) as ["netMargin" | "turnover" | "multiplier", number | null][]).filter(([, s]) => s != null) as ["netMargin" | "turnover" | "multiplier", number][];
  if (!c.length) return null;
  const [key, share] = c.sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]))[0];
  return { key, name: DRIVER_NAME[key], share };
}

// ------------------------------------------------------------------------------------------------ insight cards from the rule config

export type Ctx = Partial<Record<Measure, number | null>>;
export function insightContext(years: DeepYear[]): Ctx {
  const m = move(years), ctx: Ctx = {};
  if (m) {
    Object.assign(ctx, { roeChange: r(m.roeChange, 1), roeFirst: m.first.roe, roeLast: m.last.roe, emShare: m.shares.multiplier, marginShare: m.shares.netMargin, turnoverShare: m.shares.turnover,
      emFirst: m.first.multiplier, emLast: m.last.multiplier, marginFirst: m.first.netMargin, marginLast: m.last.netMargin, turnoverFirst: m.first.turnover, turnoverLast: m.last.turnover,
      turnoverChange: m.change.turnover, marginChange: m.change.netMargin });
    const shares = [m.first.oneOffShare, m.last.oneOffShare].filter((v): v is number => v != null);
    ctx.endpointOneOffPct = shares.length ? Math.round(Math.max(...shares) * 100) : null;
  }
  const idx = years.map((y, i) => (y.multiplier != null ? i : -1)).filter((i) => i >= 0), li = idx[idx.length - 1];
  if (li != null) { ctx.emLatest = years[li].multiplier; const p = years[li - 1]; ctx.emDelta = p && p.multiplier != null ? r((years[li].multiplier as number) - p.multiplier) : null; }
  const win = years.slice(-L.cvYears).map((y) => y.netMargin).filter((v): v is number => v != null);
  if (win.length >= L.cvMinYears) {
    const mean = win.reduce((a, b) => a + b, 0) / win.length, std = Math.sqrt(win.reduce((a, b) => a + (b - mean) ** 2, 0) / win.length);   // population standard deviation
    if (mean > 0) Object.assign(ctx, { marginMean: r(mean, 1), marginStd: r(std, 1), marginCv: r(std / mean, 2) });
  }
  return ctx;
}

const cmp = (a: number, op: string, b: number) => (op === ">" ? a > b : op === "<" ? a < b : op === ">=" ? a >= b : a <= b);
const SIGNED = new Set<string>(["roeChange", "emDelta", "turnoverChange", "marginChange"]);
const token = (name: string, v: number | null | undefined, threshold: number): string => {
  if (name === "threshold") return String(threshold);
  if (v == null || !Number.isFinite(v)) return MINUS;
  const f = MEASURE_FORMAT[name as Measure], d = f === "pct0" ? 0 : f === "pct1" || f === "pp1" ? 1 : 2;
  return (SIGNED.has(name) && v > 0 ? "+" : "") + sg(v, d);
};
const fill = (s: string, ctx: Ctx, threshold: number) => s.replace(/\{(\w+)\}/g, (_, k) => token(k, (ctx as Record<string, number | null | undefined>)[k], threshold));

export type InsightCard = { id: string; text: string; evidence: string[]; importance: number };
/** Cards for the rules whose conditions hold, most important first, capped. `skip` holds sentences already shown elsewhere (never repeated). */
export function evaluateInsights(ctx: Ctx, lender: boolean, opts: { rules?: InsightRule[]; max?: number; skip?: string[] } = {}): { cards: InsightCard[]; fired: number } {
  const rules = opts.rules ?? INSIGHT_RULES, skip = new Set((opts.skip ?? []).map((s) => s.trim().toLowerCase()));
  const seen = new Set<string>();
  const hits = rules.filter((rule) => !(lender && rule.notForLenders) && rule.when.every((c) => { const v = ctx[c.measure]; return v != null && Number.isFinite(v) && cmp(v, c.op, c.value === "threshold" ? rule.threshold : c.value); }))
    .sort((a, b) => b.importance - a.importance)
    .map((rule) => ({ id: rule.id, importance: rule.importance, text: fill(rule.template, ctx, rule.threshold), evidence: rule.evidence.map((e) => fill(e, ctx, rule.threshold)) }))
    .filter((c) => { const k = c.text.trim().toLowerCase(); if (seen.has(k) || skip.has(k)) return false; seen.add(k); return true; });
  return { cards: hits.slice(0, opts.max ?? L.maxCards), fired: hits.length };
}

// ------------------------------------------------------------------------------------------------ ROE quality score

export type ScorePart = { key: string; label: string; max: number; points: number | null; detail: string; how: string };
export type Score = { total: number | null; parts: ScorePart[]; scaled: boolean; reason: string | null };
export function qualityScore(years: DeepYear[], lender: boolean): Score {
  const S = QUALITY_SCORE, win = years.slice(-L.cvYears), ctx = insightContext(years);
  const shares = win.map((y) => y.oneOffShare).filter((v): v is number => v != null), avgShare = shares.length ? shares.reduce((a, b) => a + b, 0) / shares.length : null;
  const [p0, p1, p2] = S.parts;
  const parts: ScorePart[] = [
    { ...p0, points: avgShare == null ? null : r(p0.max * clamp(1 - avgShare / S.oneOffNone, 0, 1), 1), detail: avgShare == null ? "one-off share not available" : `one-offs averaged ${nf(avgShare * 100, 0)}% of pre-tax profit over ${shares.length} years` },
    { ...p1, points: ctx.marginCv == null ? null : r(p1.max * clamp(1 - ctx.marginCv / S.cvNone, 0, 1), 1), detail: ctx.marginCv == null ? `needs ${L.cvMinYears} years of positive net margin` : `coefficient of variation ${nf(ctx.marginCv, 2)}` },
    { ...p2, points: lender ? null : ctx.emLatest == null ? null : r(p2.max * clamp((S.leverageNone - ctx.emLatest) / (S.leverageNone - S.leverageFull), 0, 1), 1), detail: lender ? "not scored for banks and lenders" : ctx.emLatest == null ? "equity multiplier not available" : `equity multiplier ${nf(ctx.emLatest, 2)}×` },
  ];
  const need = parts.filter((p) => !(lender && p.key === "leverage"));
  if (need.some((p) => p.points == null)) return { total: null, parts, scaled: false, reason: "Not scored: " + need.filter((p) => p.points == null).map((p) => `${p.label.toLowerCase()} (${p.detail})`).join("; ") + "." };
  const got = need.reduce((a, p) => a + (p.points as number), 0), max = need.reduce((a, p) => a + p.max, 0);
  return { total: Math.round((got / max) * 100), parts, scaled: lender, reason: null };
}

// ------------------------------------------------------------------------------------------------ extended DuPont waterfall

export type WfStep = { key: keyof FiveFactors; label: string; first: number; last: number; pp: number };
export type Waterfall = { ok: true; from: string; to: string; start: number; end: number; steps: WfStep[]; method: "log" | "substitution"; note: string } | { ok: false; reason: string };
const FIVE: [keyof FiveFactors, string][] = [["taxBurden", "Tax burden"], ["interestBurden", "Interest burden"], ["ebitMargin", "EBIT margin"], ["turnover", "Asset turnover"], ["multiplier", "Equity multiplier"]];
export function waterfall(years: DeepYear[], lender: boolean): Waterfall {
  if (lender) return { ok: false, reason: "Not shown for banks and lenders: interest is their main cost, so splitting it out of the margin does not apply. The three-factor view above is the one that fits." };
  const u = years.filter((y) => y.five && y.rawRoe != null);
  if (u.length < 2) return { ok: false, reason: "Needs pre-tax profit, finance costs and a meaningful ROE in at least two years." };
  const a = u[0], b = u[u.length - 1], fa = a.five as FiveFactors, fb = b.five as FiveFactors, ra = a.rawRoe as number, rb = b.rawRoe as number;
  const logOk = ra > 0 && rb > 0 && FIVE.every(([k]) => fa[k] > 0 && fb[k] > 0);
  let pp: number[];
  if (logOk) {
    const lm = ra === rb ? ra : (rb - ra) / Math.log(rb / ra);                   // logarithmic mean: contribution = lm x ln(factor ratio), which sums to the exact ROE change
    pp = FIVE.map(([k]) => lm * Math.log(fb[k] / fa[k]));
  } else {
    const cur = { ...fa }; let before = ra; pp = FIVE.map(([k]) => { cur[k] = fb[k]; const now = FIVE.reduce((acc, [kk]) => acc * cur[kk], 1) * 100; const d = now - before; before = now; return d; });
  }
  return { ok: true, from: a.label, to: b.label, start: ra, end: rb, method: logOk ? "log" : "substitution",
    steps: FIVE.map(([k, label], i) => ({ key: k, label, first: fa[k], last: fb[k], pp: pp[i] })),
    note: logOk ? "Log method: each factor's contribution is its share of the log change, times the ROE change, so the five add up to the whole move."
      : "A log is undefined here (a loss year or a negative factor), so each factor is switched from its first-year to its last-year value in turn, in the order shown. The five still add up to the whole move, but the split depends on that order." };
}

// ------------------------------------------------------------------------------------------------ what-if arithmetic

export const simRoe = (marginPct: number, turnover: number, multiplier: number) => marginPct * turnover * multiplier;
/** required_margin = goal ROE / (turnover x multiplier), in per cent. Null when turnover x multiplier is zero or negative. */
export const requiredMargin = (goalRoePct: number, turnover: number, multiplier: number) => (turnover * multiplier > 0 ? goalRoePct / (turnover * multiplier) : null);
/** The latest year with all three factors, with the unrounded values (so the calculator starts exactly where the table is). */
export function simStart(years: DeepYear[]): { year: DeepYear; margin: number; turnover: number; multiplier: number } | null {
  for (let i = years.length - 1; i >= 0; i--) {
    const y = years[i];
    if (y.netMargin != null && y.turnover != null && y.multiplier != null && y.pat != null && y.sales && y.baseAssets && y.baseEquity)
      return { year: y, margin: (y.pat / y.sales) * 100, turnover: y.sales / y.baseAssets, multiplier: y.baseAssets / y.baseEquity };
  }
  return null;
}

// ------------------------------------------------------------------------------------------------ table rows (shared by the table and the CSV)

export type TableRow = { key: string; label: string; kind: "pct" | "x" | "flag"; values: (number | string | null)[]; whys: (Why | null)[]; emphasis?: boolean; sub?: boolean };
export function tableRows(years: DeepYear[], view: View, lender: boolean): TableRow[] {
  const norm = view === "normalized", tag = norm ? "normalized" : "reported";
  const rows: TableRow[] = [
    { key: "margin", label: `Net margin, ${tag}${lender ? " (of total income)" : ""}`, kind: "pct", values: years.map((y) => (norm ? y.normMargin : y.netMargin)), whys: years.map((y) => y.why.netMargin) },
    { key: "turnover", label: "Asset turnover", kind: "x", values: years.map((y) => y.turnover), whys: years.map((y) => y.why.turnover) },
    { key: "multiplier", label: "Equity multiplier", kind: "x", values: years.map((y) => y.multiplier), whys: years.map((y) => y.why.multiplier) },
    { key: "roa", label: `ROA, ${tag} (margin × turnover)`, kind: "pct", values: years.map((y) => (norm ? y.normRoa : y.roa)), whys: years.map((y) => y.why.turnover ?? y.why.netMargin) },
    { key: "roe", label: "ROE, reported", kind: "pct", values: years.map((y) => y.roe), whys: years.map((y) => y.why.roe), emphasis: !norm },
    { key: "normRoe", label: "ROE, normalized", kind: "pct", values: years.map((y) => y.normRoe), whys: years.map((y) => y.why.roe), emphasis: norm },
    { key: "oneOff", label: "One-offs, % of pre-tax profit", kind: "pct", values: years.map((y) => (y.oneOffShare == null ? null : r(y.oneOffShare * 100, 0))), whys: years.map((y) => y.why.oneOff), sub: true },
    { key: "quality", label: "Earnings quality", kind: "flag", values: years.map((y) => (y.lowQuality ? "Low quality" : y.oneOffShare == null ? null : "Normal")), whys: years.map((y) => y.why.oneOff), sub: true },
  ];
  return rows;
}

// ------------------------------------------------------------------------------------------------ "How is this calculated?"

export type ExplainLine = { label: string; formula: string; working: string; result: string };
export function explain(y: DeepYear, basis: Basis, lender: boolean): ExplainLine[] {
  const rev = lender ? "total income" : "revenue", avg = y.averaged, a = y.baseAssets, e = y.baseEquity;
  const bal = avg ? "average" : "year-end";
  const L1 = (label: string, formula: string, working: string | null, value: string | null, why: Why | null): ExplainLine => ({ label, formula, working: working ?? (why ? why.long : "not available"), result: value ?? (why ? why.short : MINUS) });
  const m = y.netMargin != null && y.sales != null && y.pat != null;
  const lines: ExplainLine[] = [
    L1("Net margin", `net profit ÷ ${rev}`, m ? `${crore(y.pat as number)} ÷ ${crore(y.sales as number)}` : null, y.netMargin == null ? null : nf(y.netMargin, 2) + "%", y.why.netMargin),
    L1("Asset turnover", `${rev} ÷ ${bal} total assets`, y.turnover != null ? `${crore(y.sales as number)} ÷ ${crore(a as number)}` : null, y.turnover == null ? null : nf(y.turnover, 2) + "×", y.why.turnover),
    L1("Equity multiplier", `${bal} total assets ÷ ${bal} equity`, y.multiplier != null ? `${crore(a as number)} ÷ ${crore(e as number)}` : null, y.multiplier == null ? null : nf(y.multiplier, 2) + "×", y.why.multiplier),
    L1("ROE", "net margin × turnover × multiplier = net profit ÷ equity", y.roe != null ? `${nf(y.netMargin as number, 2)}% × ${nf(y.turnover as number, 2)} × ${nf(y.multiplier as number, 2)}, or ${crore(y.pat as number)} ÷ ${crore(e as number)}` : null, y.roe == null ? null : nf(y.roe, 2) + "%", y.why.roe),
    L1("ROA", "net margin × turnover = net profit ÷ total assets", y.roa != null ? `${crore(y.pat as number)} ÷ ${crore(a as number)}` : null, y.roa == null ? null : nf(y.roa, 2) + "%", y.why.turnover ?? y.why.netMargin),
  ];
  const rate = `${nf(y.taxRate * 100, 1)}%`;
  lines.push({ label: "Tax rate on one-offs", formula: "tax ÷ pre-tax profit, kept between 0% and 40%",
    working: y.taxRateFallback ? `tax or pre-tax profit is not usable this year, so the ${nf(L.fallbackTaxRate * 100, 0)}% fallback rate is used` : `${crore(y.tax as number)} ÷ ${crore(y.pbt as number)}${y.taxRateClamped ? ", outside the 0% to 40% band so it is cut to the band" : ""}`, result: rate });
  const e0 = y.exceptional ?? 0, d0 = y.discontinued ?? 0;
  lines.push({ label: "Normalized net profit", formula: "net profit − exceptional items × (1 − tax rate) − discontinued-operations profit",
    working: y.normPat == null ? (y.why.netMargin?.long ?? "net profit not available") : `${crore(y.pat as number)} − ${crore(e0)} × (1 − ${nf(y.taxRate, 3)}) − ${crore(d0)}`, result: y.normPat == null ? MINUS : crore(y.normPat) });
  lines.push({ label: "Normalized ROE", formula: "normalized net profit ÷ equity", working: y.normRoe != null ? `${crore(y.normPat as number)} ÷ ${crore(e as number)}` : (y.why.roe?.long ?? "not available"), result: y.normRoe == null ? (y.why.roe?.short ?? MINUS) : nf(y.normRoe, 2) + "%" });
  lines.push({ label: "One-off share", formula: "(|exceptional items| + |discontinued profit|) ÷ |pre-tax profit|", working: y.oneOffShare != null ? `(${crore(Math.abs(e0))} + ${crore(Math.abs(d0))}) ÷ ${crore(Math.abs(y.pbt as number))}` : (y.why.oneOff?.long ?? "not available"),
    result: y.oneOffShare == null ? (y.why.oneOff?.short ?? MINUS) : nf(y.oneOffShare * 100, 0) + "%" + (y.lowQuality ? " (low-quality earnings)" : "") });
  void basis;
  return lines;
}

export function thresholdNotes(): string[] {
  return [
    `Low-quality earnings: one-off items above ${nf(L.lowQualityShare * 100, 0)}% of pre-tax profit. The year is left out of the 3-year and 5-year averages.`,
    `Implausible ratio: one-off items above ${nf(L.implausibleOneOffShare * 100, 0)}% of pre-tax profit, or a net margin above ${L.implausibleMarginPct}%.`,
    `Step change: the equity multiplier or net margin moves by more than ${nf(L.stepChange * 100, 0)}% in a year.`,
    `ROE not meaningful: equity is zero or negative, or under ${nf(L.nearZeroEquityShare * 100, 0)}% of total assets.`,
    `Tax rate for one-offs: tax ÷ pre-tax profit, kept between 0% and ${nf(L.taxRateMax * 100, 0)}%; ${nf(L.fallbackTaxRate * 100, 0)}% only when that cannot be worked out.`,
  ];
}

// ------------------------------------------------------------------------------------------------ CSV

export function decodeCsv(opts: { symbol: string; years: DeepYear[]; view: View; basis: Basis; lender: boolean; day?: string }): string {
  const { years, view, basis, lender } = opts, rows = tableRows(years, view, lender);
  const head = [csvRow(["FinLit", `${opts.symbol} Decoding ROE`]), csvRow(["Balances", basis === "average" ? "average of opening and closing (first year falls back to year-end)" : "year-end"]), csvRow(["Net margin and ROA shown as", view]), ...(opts.day ? [csvRow(["Exported", opts.day])] : []), ""];
  const body = [csvRow(["Measure", ...years.map((y) => y.label)]), ...rows.map((t) => csvRow([t.label, ...t.values.map((v) => (v == null ? "" : v))]))];
  const gaps = gapList(years).map((g) => csvRow([g.labels.join("; "), g.reason.long]));
  return [...head, ...body, "", csvRow(["Why a cell is blank", ""]), ...(gaps.length ? gaps : [csvRow(["None", ""])]), "", csvRow(["Information only, not investment advice."])].join("\n");
}
