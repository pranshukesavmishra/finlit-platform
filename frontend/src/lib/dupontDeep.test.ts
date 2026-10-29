import { describe, expect, it } from "vitest";
import type { Table } from "./api";
import { dupont } from "./dupont";
import {
  anomalies, averages, completeness, decodeCsv, deepYears, driver, evaluateInsights, explain, gapList, insightContext, move, qualityScore, requiredMargin, simRoe, simStart, tableRows, thresholdNotes, waterfall,
} from "./dupontDeep";
import { DUPONT_LIMITS, INSIGHT_RULES, QUALITY_SCORE } from "./dupontRules";
import reliance from "./__fixtures__/relianceYearly.json";

const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows }) as Table;
const RIL = reliance.yearly as { pl: Table; bs: Table };
const P8 = ["FY19", "FY20", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];
/** Eight years shaped like the founder's report: equity missing for the four oldest years, a huge one-off in Mar 2022, and a leveraged, one-off driven Mar 2023. */
const shaped = () => {
  const pl = t(P8, {
    revenue: [1000, 1100, 900, 20, 100, 1000, 1050, 1100], net_profit: [300, 980, 27, 0.6, 48, 100, 190, 210], profit_before_tax: [380, 1000, 40, 0.5, 60, 130, 240, 270],
    tax: [80, 20, 13, 0.1, 12, 30, 50, 60], exceptional_items: [null, 800, 20, 103.9, 40, null, null, null], discontinued_profit: [null, null, null, null, null, null, null, null], finance_costs: [20, 25, 30, 1, 5, 10, 12, 9],
  });
  const bs = t(P8, { total_assets: [500, 520, 530, 560, 540, 520, 510, 530], total_equity: [null, null, null, null, 100, 280, 270, 266], equity_capital: [10, 10, 10, 10, 10, 10, 10, 10] });
  return { pl, bs };
};

describe("deepYears, year-end basis", () => {
  it("matches the existing DuPont card figure for figure on Reliance", () => {
    const base = dupont(RIL.pl, RIL.bs, false), deep = deepYears(RIL.pl, RIL.bs, false, "year-end");
    expect(deep.map((y) => y.period)).toEqual(base.years.map((y) => y.period));
    deep.forEach((y, i) => { const b = base.years[i]; expect([y.netMargin, y.turnover, y.multiplier, y.roe]).toEqual([b.netMargin, b.turnover, b.multiplier, b.roe]); });
    const m = move(deep)!, f = Object.fromEntries(base.factors.map((x) => [x.key, x.shareOfMove]));
    expect(m.shares).toEqual({ netMargin: f.netMargin, turnover: f.turnover, multiplier: f.multiplier });
    expect(m.first.period).toBe("FY19"); expect(m.last.period).toBe("FY26");
  });

  it("normalizes: net profit less exceptional items taxed at the year's own rate", () => {
    const pl = t(["FY25"], { revenue: [1000], net_profit: [100], profit_before_tax: [140], tax: [40], exceptional_items: [40] });
    const y = deepYears(pl, t(["FY25"], { total_assets: [1000], total_equity: [500] }), false)[0];
    expect(y.taxRate).toBeCloseTo(40 / 140, 6);
    expect(y.normPat).toBeCloseTo(100 - 40 * (1 - 40 / 140), 6);          // 71.43
    expect(y.roe).toBeCloseTo(20, 2); expect(y.normRoe).toBeCloseTo(14.29, 2);
    expect(y.taxRateFallback).toBe(false); expect(y.oneOffShare).toBeCloseTo(40 / 140, 6); expect(y.lowQuality).toBe(false);
  });
  it("subtracts discontinued-operations profit in full (it is already after tax)", () => {
    const pl = t(["FY25"], { revenue: [1000], net_profit: [420], profit_before_tax: [300], tax: [60], discontinued_profit: [150] });
    const y = deepYears(pl, t(["FY25"], { total_assets: [1000], total_equity: [800] }), false)[0];
    expect(y.normPat).toBe(270); expect(y.normMargin).toBeCloseTo(27, 2);
  });
  it("clamps the tax rate to 0 to 40%, and falls back to 25% only when tax or pre-tax profit is unusable", () => {
    const one = (tax: number | null, pbt: number) => deepYears(t(["FY25"], { revenue: [1000], net_profit: [100], profit_before_tax: [pbt], tax: [tax], exceptional_items: [10] }), t(["FY25"], { total_assets: [1000], total_equity: [500] }), false)[0];
    expect(one(90, 100).taxRate).toBe(0.4); expect(one(90, 100).taxRateClamped).toBe(true);
    expect(one(-5, 100).taxRate).toBe(0); expect(one(null, 100).taxRate).toBe(0.25); expect(one(null, 100).taxRateFallback).toBe(true);
    expect(one(10, -50).taxRate).toBe(0.25);                                                      // loss: tax / PBT is not a rate
  });
  it("marks low-quality years (one-offs above 50% of pre-tax profit) and leaves them out of the averages, naming them", () => {
    const { pl, bs } = shaped(), ys = deepYears(pl, bs, false);
    expect(ys.filter((y) => y.lowQuality).map((y) => y.period)).toEqual(["FY20", "FY22", "FY23"]);
    const a3 = averages(ys, 3);                                                                    // FY24, FY25, FY26
    expect(a3.used).toEqual(["Mar 2024", "Mar 2025", "Mar 2026"]); expect(a3.lowQuality).toEqual([]);
    const a5 = averages(ys, 5);                                                                    // FY22 and FY23 are one-off driven; FY22 also has no equity
    expect(a5.lowQuality).toEqual(["Mar 2022", "Mar 2023"]); expect(a5.noData).toEqual([]); expect(a5.used).toEqual(["Mar 2024", "Mar 2025", "Mar 2026"]);
    expect(a5.reported).toBeCloseTo((100 / 280 + 190 / 270 + 210 / 266) / 3 * 100, 1);
    expect(a5.normalized).not.toBeNull();
  });
  it("shows why every blank is blank, and counts complete years", () => {
    const { pl, bs } = shaped(), ys = deepYears(pl, bs, false);
    expect(completeness(ys)).toMatchObject({ complete: 4, total: 8 });
    expect(ys[0].why.multiplier?.short).toBe("equity data not available"); expect(ys[0].why.roe?.short).toBe("equity data not available");
    expect(ys[0].why.multiplier?.long).toMatch(/share capital or reserves are reported/);
    expect(ys[0].why.netMargin).toBeNull(); expect(ys[0].netMargin).toBeCloseTo(30, 1);
    expect(gapList(ys)).toHaveLength(1); expect(gapList(ys)[0].labels).toEqual(["Mar 2019", "Mar 2020", "Mar 2021", "Mar 2022"]);
  });
  it("says negative equity, zero revenue and near-zero equity in words, and never gives a ROE there", () => {
    const pl = t(["FY23", "FY24", "FY25"], { revenue: [100, null, 100], net_profit: [10, 10, 10], profit_before_tax: [14, 14, 14] });
    const bs = t(["FY23", "FY24", "FY25"], { total_assets: [500, 500, 500], total_equity: [-50, 80, 5] });
    const [a, b, c] = deepYears(pl, bs, false);
    expect(a.roe).toBeNull(); expect(a.why.multiplier?.short).toBe("negative equity"); expect(a.why.roe?.short).toBe("ROE not meaningful"); expect(a.why.roe?.long).toMatch(/negative/);
    expect(b.why.netMargin?.short).toBe("no revenue"); expect(b.why.turnover?.short).toBe("no revenue"); expect(b.roe).toBeCloseTo(12.5, 2);
    expect(c.notMeaningful).toBe(true); expect(c.roe).toBeNull(); expect(c.why.roe?.long).toMatch(/under 2% of total assets/);
  });
  it("handles an empty table, a single year, all-null values and huge ratios without throwing", () => {
    expect(deepYears(undefined, undefined, false)).toEqual([]);
    const one = deepYears(t(["FY26"], { revenue: [100], net_profit: [10], profit_before_tax: [14] }), t(["FY26"], { total_assets: [200], total_equity: [100] }), false);
    expect(one).toHaveLength(1); expect(move(one)).toBeNull(); expect(driver(null)).toBeNull(); expect(waterfall(one, false).ok).toBe(false);
    expect(evaluateInsights(insightContext(one), false).cards).toEqual([]);
    const nulls = deepYears(t(["FY25", "FY26"], { revenue: [null, null], net_profit: [null, null] }), t(["FY25", "FY26"], { total_assets: [null, null], total_equity: [null, null] }), false);
    expect(nulls.every((y) => y.roe == null && !y.complete)).toBe(true); expect(completeness(nulls).complete).toBe(0); expect(averages(nulls, 3).reported).toBeNull();
    expect(qualityScore(nulls, false).total).toBeNull(); expect(simStart(nulls)).toBeNull(); expect(decodeCsv({ symbol: "X", years: nulls, view: "reported", basis: "year-end", lender: false })).toContain("Information only");
    const huge = deepYears(t(["FY26"], { revenue: [1], net_profit: [1e9], profit_before_tax: [1e9] }), t(["FY26"], { total_assets: [1e9], total_equity: [1e9] }), false)[0];
    expect(Number.isFinite(huge.netMargin as number)).toBe(true);
  });
});

describe("average balances", () => {
  const pl = t(["FY24", "FY25", "FY26"], { revenue: [1000, 1100, 1200], net_profit: [100, 110, 120], profit_before_tax: [130, 140, 150] });
  const bs = t(["FY24", "FY25", "FY26"], { total_assets: [800, 1000, 1200], total_equity: [400, 500, 600] });
  it("uses the mean of this and the previous year-end, and falls back (marked) for the first year", () => {
    const [a, b, c] = deepYears(pl, bs, false, "average");
    expect(a.fellBack).toBe(true); expect(a.averaged).toBe(false); expect(a.roe).toBeCloseTo(25, 2);
    expect(b.averaged).toBe(true); expect(b.roe).toBeCloseTo((110 / 450) * 100, 2); expect(b.turnover).toBeCloseTo(1100 / 900, 2); expect(b.multiplier).toBeCloseTo(900 / 450, 2);
    const product = ((c.netMargin as number) / 100) * (c.turnover as number) * (c.multiplier as number) * 100; expect(product).toBeCloseTo(c.roe as number, 1);
  });
  it("falls back to year-end when the previous balance sheet is missing or has negative equity", () => {
    const y = deepYears(pl, t(["FY24", "FY25", "FY26"], { total_assets: [800, 1000, 1200], total_equity: [-400, 500, 600] }), false, "average");
    expect(y[1].averaged).toBe(false); expect(y[1].fellBack).toBe(true); expect(y[2].averaged).toBe(true);
  });
});

describe("anomalies", () => {
  it("flags a net margin above 70%, an implausible one-off ratio and step changes with the neutral prompt", () => {
    const { pl, bs } = shaped(); bs.rows.total_equity = [100, 100, 100, 100, 100, 100, 100, 100];
    const a = anomalies(deepYears(pl, bs, false));
    expect(a.find((x) => x.kind === "oneoff-implausible" && x.period === "FY22")?.text).toMatch(/20,780% of pre-tax profit: an implausible ratio/);
    const fy20 = deepYears(pl, bs, false)[1]; expect(fy20.netMargin).toBeGreaterThan(70);
    expect(a.some((x) => x.kind === "margin-high" && x.period === "FY20")).toBe(true);
    const prompt = DUPONT_LIMITS.stepPrompt; expect(a.filter((x) => x.kind === "step-margin").every((x) => x.text.endsWith(prompt))).toBe(true);
    expect(a.every((x) => x.target === "financials")).toBe(true);
  });
  it("detects an equity multiplier falling from 5.03x to 1.83x", () => {
    const pl = t(["FY23", "FY24"], { revenue: [100, 100], net_profit: [10, 10], profit_before_tax: [12, 12] });
    const bs = t(["FY23", "FY24"], { total_assets: [503, 183], total_equity: [100, 100] });
    const a = anomalies(deepYears(pl, bs, false)).filter((x) => x.kind === "step-multiplier");
    expect(a).toHaveLength(1); expect(a[0].period).toBe("FY24"); expect(a[0].text).toContain("5.03× to 1.83×"); expect(a[0].text).toContain("Possible equity raise, merger or restructuring: check the cash flow and equity statements.");
  });
  it("is silent on steady, ordinary figures (Reliance)", () => { expect(anomalies(deepYears(RIL.pl, RIL.bs, false))).toEqual([]); });
});

describe("insight rules", () => {
  const ys = (r1: number[], rev: number[], assets: number[], eq: number[]) => deepYears(t(P8.slice(0, r1.length), { revenue: rev, net_profit: r1, profit_before_tax: r1.map((x) => x * 1.3) }), t(P8.slice(0, r1.length), { total_assets: assets, total_equity: eq }), false);
  it("says the leverage sentence when over 40% of a ROE fall is lower leverage", () => {
    const y = ys([100, 100], [1000, 1000], [3000, 1000], [600, 500]);    // multiplier 5 -> 2; margin and turnover unchanged -> ROE 16.7 -> 20? use explicit numbers below
    void y;
    const d = ys([60, 60], [1000, 1000], [3000, 1500], [600, 600]);     // ROE 10% both; need a fall
    void d;
    const f = ys([100, 80], [1000, 1000], [3000, 1500], [600, 600]);     // margin 10 -> 8 (-0.223), turnover 0.333 -> 0.667 (+0.693), multiplier 5 -> 2.5 (-0.693), ROE 16.7 -> 13.3
    const m = move(f)!; expect(m.shares.multiplier).toBeGreaterThan(40); expect(m.roeChange).toBeLessThan(0);
    const cards = evaluateInsights(insightContext(f), false).cards;
    expect(cards.map((c) => c.text)).toContain("Over 40% of the ROE decline is due to lower leverage, not worse operations.");
    expect(cards.find((c) => c.id === "leverage-fell")!.evidence.join(" ")).toMatch(/5\.00× to 2\.50×/);
  });
  it("covers each sentence in the brief", () => {
    const ctx = (o: Record<string, number>) => o as never;
    const say = (o: Record<string, number>, lender = false) => evaluateInsights(ctx(o), lender, { max: 20 }).cards.map((c) => c.text);
    expect(say({ marginShare: 55, turnoverShare: 20 })).toContain("Profitability, not efficiency, drove the change.");
    expect(say({ marginShare: 55, turnoverShare: 50 })).not.toContain("Profitability, not efficiency, drove the change.");
    expect(say({ emLatest: 3.4, emDelta: 0.6 })).toContain("ROE is increasingly leverage-driven. Check debt servicing.");
    expect(say({ emLatest: 3.4, emDelta: 0.6 }, true)).toEqual([]);                                  // lenders are always highly leveraged
    expect(say({ emLatest: 2.9, emDelta: 0.6 })).toEqual([]);
    expect(say({ marginCv: 0.62, marginMean: 20, marginStd: 12.4 })).toContain("Earnings are volatile, so ROE is unreliable as a trend.");
    expect(say({ marginCv: 0.5, marginMean: 20, marginStd: 10 })).toEqual([]);                        // not strictly above
    expect(say({ turnoverChange: 12, marginChange: -8 })).toContain("Growth is coming with price or margin pressure.");
    expect(say({ turnoverChange: -12, marginChange: 8 })[0]).toMatch(/^Each rupee of sales earns more/);
    expect(say({ roeChange: 4, emShare: 60 })[0]).toMatch(/^Over 40% of the ROE rise comes from a higher equity multiplier/);
  });
  it("orders by importance, caps the list, drops duplicates and sentences already shown", () => {
    const all = { roeChange: -5, emShare: 55, marginShare: 45, turnoverShare: 0, emLatest: 3.5, emDelta: 0.4, marginCv: 0.9, marginMean: 10, marginStd: 9, turnoverChange: 10, marginChange: -10, endpointOneOffPct: 80, emFirst: 5, emLast: 3.5, roeFirst: 20, roeLast: 15, marginFirst: 12, marginLast: 9, turnoverFirst: 0.5, turnoverLast: 0.7 } as never;
    const r = evaluateInsights(all, false);
    expect(r.cards).toHaveLength(DUPONT_LIMITS.maxCards); expect(r.fired).toBeGreaterThan(DUPONT_LIMITS.maxCards);
    expect(r.cards.map((c) => c.importance)).toEqual([...r.cards.map((c) => c.importance)].sort((a, b) => b - a));
    expect(new Set(r.cards.map((c) => c.text)).size).toBe(r.cards.length);
    const skipped = evaluateInsights(all, false, { max: 20, skip: ["Earnings are volatile, so ROE is unreliable as a trend."] }).cards;
    expect(skipped.some((c) => /Earnings are volatile/.test(c.text))).toBe(false);
  });
  it("lets product tune a threshold without touching code", () => {
    const rule = { ...INSIGHT_RULES.find((x) => x.id === "leverage-fell")!, threshold: 60 };
    const ctx = { roeChange: -3, emShare: 50, emFirst: 4, emLast: 3, roeFirst: 10, roeLast: 7 } as never;
    expect(evaluateInsights(ctx, false, { rules: [rule] }).cards).toEqual([]);
    expect(evaluateInsights(ctx, false, { rules: [{ ...rule, threshold: 45 }] }).cards[0].text).toMatch(/^Over 45%/);
  });
  it("uses a coefficient of variation over the last five years (population standard deviation)", () => {
    const f = ys([30, 30, 30, 30, 30], [100, 100, 100, 100, 100], [500, 500, 500, 500, 500], [250, 250, 250, 250, 250]);
    expect(insightContext(f).marginCv).toBe(0);
    const g = deepYears(t(P8.slice(0, 5), { revenue: [100, 100, 100, 100, 100], net_profit: [10, 30, 10, 30, 10] }), t(P8.slice(0, 5), { total_assets: [500, 500, 500, 500, 500], total_equity: [250, 250, 250, 250, 250] }), false);
    const mean = 18, std = Math.sqrt((4 * 64 + 2 * 144 + 0) / 5 * 0 + ((8 ** 2) * 3 + (12 ** 2) * 2) / 5);
    expect(insightContext(g).marginCv).toBeCloseTo(std / mean, 2);
  });
});

describe("driver badge and quality score", () => {
  it("names the largest absolute log share", () => {
    const f = deepYears(t(["FY24", "FY25"], { revenue: [1000, 1000], net_profit: [100, 100], profit_before_tax: [130, 130] }), t(["FY24", "FY25"], { total_assets: [1000, 1000], total_equity: [200, 400] }), false);
    const d = driver(move(f))!; expect(d.key).toBe("multiplier"); expect(d.name).toBe("Leverage (multiplier)");
  });
  it("builds the score from listed parts that add up", () => {
    const { pl, bs } = shaped(), s = qualityScore(deepYears(pl, bs, false), false);
    expect(s.parts.map((p) => p.key)).toEqual(["oneOffs", "stability", "leverage"]);
    if (s.total != null) expect(s.total).toBe(Math.round(s.parts.reduce((a, p) => a + (p.points ?? 0), 0)));
    const clean = deepYears(t(P8.slice(0, 5), { revenue: [100, 100, 100, 100, 100], net_profit: [10, 10, 10, 10, 10], profit_before_tax: [13, 13, 13, 13, 13] }), t(P8.slice(0, 5), { total_assets: [200, 200, 200, 200, 200], total_equity: [100, 100, 100, 100, 100] }), false);
    const c = qualityScore(clean, false); expect(c.total).toBe(100); expect(c.parts.map((p) => p.max)).toEqual(QUALITY_SCORE.parts.map((p) => p.max));
    const lender = qualityScore(clean, true); expect(lender.total).toBe(100); expect(lender.scaled).toBe(true); expect(lender.parts[2].points).toBeNull();
  });
  it("is not scored (with the reason) when a part cannot be worked out", () => {
    const s = qualityScore(deepYears(t(["FY25", "FY26"], { revenue: [100, 100], net_profit: [10, 10], profit_before_tax: [13, 13] }), t(["FY25", "FY26"], { total_assets: [200, 200], total_equity: [100, 100] }), false), false);
    expect(s.total).toBeNull(); expect(s.reason).toMatch(/margin stability/);
  });
});

describe("waterfall", () => {
  it("log method: contributions add up to the ROE change exactly", () => {
    const w = waterfall(deepYears(RIL.pl, RIL.bs, false), false);
    expect(w.ok).toBe(true); if (!w.ok) return;
    expect(w.method).toBe("log"); expect(w.steps).toHaveLength(5);
    expect(w.steps.reduce((a, s) => a + s.pp, 0)).toBeCloseTo(w.end - w.start, 8);
    expect(w.start).toBeCloseTo((35163 / 405322) * 100, 6); expect(w.end).toBeCloseTo((43851 / 566235) * 100, 6);
    expect(w.from).toBe("Mar 2019"); expect(w.to).toBe("Mar 2026");
  });
  it("falls back to step-by-step substitution when a log is undefined (loss year) and still adds up", () => {
    const pl = t(["FY24", "FY25"], { revenue: [1000, 900], net_profit: [100, -50], profit_before_tax: [130, -40], finance_costs: [10, 20] });
    const bs = t(["FY24", "FY25"], { total_assets: [1000, 1000], total_equity: [500, 400] });
    const w = waterfall(deepYears(pl, bs, false), false); expect(w.ok).toBe(true); if (!w.ok) return;
    expect(w.method).toBe("substitution"); expect(w.note).toMatch(/log is undefined/);
    expect(w.steps.reduce((a, s) => a + s.pp, 0)).toBeCloseTo(w.end - w.start, 8); expect(w.end).toBeCloseTo(-12.5, 6);
  });
  it("is not shown for banks and lenders, or without two usable years", () => {
    const w = waterfall(deepYears(RIL.pl, RIL.bs, true), true); expect(w.ok).toBe(false);
    expect(waterfall([], false).ok).toBe(false);
  });
  it("the 'average balances' option feeds the waterfall too", () => {
    const a = waterfall(deepYears(RIL.pl, RIL.bs, false, "average"), false), b = waterfall(deepYears(RIL.pl, RIL.bs, false, "year-end"), false);
    expect(a.ok && b.ok).toBe(true); if (a.ok && b.ok) { expect(a.start).toBeCloseTo((35163 / 405322) * 100, 6); expect(a.from).toBe("Mar 2019"); expect(a.end).not.toBeCloseTo(b.end, 3); }
  });
});

describe("what-if arithmetic", () => {
  it("multiplies the three factors and solves the margin needed", () => {
    expect(simRoe(18.91, 0.89, 1.99)).toBeCloseTo(33.49, 1);
    expect(requiredMargin(25, 0.89, 1.99)).toBeCloseTo(14.12, 2);
    expect(requiredMargin(25, 1, 1.5)).toBeCloseTo(16.67, 2);
    expect(requiredMargin(25, 0, 1.5)).toBeNull(); expect(requiredMargin(25, 1, -1)).toBeNull();
  });
  it("starts from the latest year with all three factors", () => {
    const ys = deepYears(RIL.pl, RIL.bs, false); const st = simStart(ys)!; expect(st.year.period).toBe("FY26"); expect(simRoe(st.margin, st.turnover, st.multiplier)).toBeCloseTo(ys[ys.length - 1].rawRoe as number, 8);
  });
});

describe("table, explanation and CSV", () => {
  const ys = deepYears(RIL.pl, RIL.bs, false);
  it("ROA is margin times turnover for every year", () => {
    ys.forEach((y) => expect(y.roa).toBeCloseTo(((y.netMargin as number) / 100) * (y.turnover as number) * 100, 0));
    expect(tableRows(ys, "normalized", false).find((r) => r.key === "margin")!.label).toMatch(/normalized/);
  });
  it("explains a year with the actual numbers", () => {
    const lines = explain(ys[ys.length - 1], "year-end", false);
    expect(lines.find((l) => l.label === "Net margin")).toMatchObject({ working: "43,851 ÷ 5,24,105", result: "8.37%" });
    expect(lines.find((l) => l.label === "ROE")!.working).toContain("43,851 ÷ 5,66,235"); expect(lines.find((l) => l.label === "ROE")!.result).toBe("7.74%");
    expect(explain(deepYears(RIL.pl, RIL.bs, false, "average")[3], "average", false).find((l) => l.label === "Asset turnover")!.formula).toMatch(/average total assets/);
    expect(thresholdNotes().join(" ")).toMatch(/50%/);
  });
  it("exports exactly the table that is shown, with reasons, and escapes risky text", () => {
    const { pl, bs } = shaped(), s = deepYears(pl, bs, false), csv = decodeCsv({ symbol: "=EVIL", years: s, view: "normalized", basis: "year-end", lender: false, day: "2026-10-29" });
    const lines = csv.split("\n"); expect(lines[0]).toContain("'=EVIL");
    const head = lines.findIndex((l) => l.startsWith("Measure,")); expect(lines[head]).toBe("Measure," + s.map((y) => y.label).join(","));
    expect(lines[head + 1]).toMatch(/^"?Net margin, normalized/); expect(csv).toContain("Why a cell is blank"); expect(csv).toContain("Mar 2019; Mar 2020; Mar 2021; Mar 2022");
    expect(lines.find((l) => l.startsWith('"ROE, reported"'))).toMatch(/^"ROE, reported",,,,,/);
  });
});

describe("compliance wording", () => {
  const BAD = /\b(buy|buying|sell|selling|hold|holding|target|targets|recommend\w*|outperform\w*|undervalued|overvalued|upside|downside|accumulate|should invest)\b/i;
  it("no rule, score, reason or note uses buy, sell, hold or target language", () => {
    const { pl, bs } = shaped(), ys = deepYears(pl, bs, false), ys2 = deepYears(RIL.pl, RIL.bs, false);
    const text = [
      ...INSIGHT_RULES.flatMap((r) => [r.template, ...r.evidence]), ...thresholdNotes(), ...QUALITY_SCORE.parts.map((p) => p.how + p.label), DUPONT_LIMITS.stepPrompt,
      ...[ys, ys2].flatMap((y) => [...y.flatMap((x) => [x.why.netMargin?.long, x.why.turnover?.long, x.why.multiplier?.long, x.why.roe?.long, x.why.oneOff?.long, ...explain(x, "year-end", false).flatMap((l) => [l.label, l.formula, l.working])]), ...anomalies(y).map((a) => a.text), ...(qualityScore(y, false).parts.map((p) => p.detail)), qualityScore(y, false).reason]),
      (() => { const w = waterfall(ys2, false); return w.ok ? w.note : w.reason; })(), (() => { const w = waterfall(ys2, true); return w.ok ? w.note : w.reason; })(),
    ].filter(Boolean).join("\n");
    expect(text.length).toBeGreaterThan(500); expect(text).not.toMatch(BAD);
  });
});
