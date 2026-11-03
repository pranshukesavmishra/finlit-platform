import { describe, expect, it } from "vitest";
import { generateInsight, metricCfg, percentileRank, theilSen, type InsightInput } from "./corrInsight";

const X = metricCfg("P/E ratio"), Y = metricCfg("EPS growth");
const fx = (v: number) => v.toFixed(1) + "x", fy = (v: number) => v.toFixed(1) + "%";
const rng = (seed: number) => () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
const base = (over: Partial<InsightInput> = {}): InsightInput => ({ x: X, y: Y, points: [], selected: [], rho: 0, p: 0.5, outside: 0, period: "FY2025", who: "companies", fx, fy, ...over });
const line = (n: number) => Array.from({ length: n }, (_, i) => ({ s: "S" + i, x: i + 1, y: 2 * (i + 1) }));
const noise = (n: number) => { const r = rng(7); return Array.from({ length: n }, (_, i) => ({ s: "R" + i, x: r() * 50, y: r() * 50 })); };
const BANNED = /\b(undervalued|overvalued|good|bad|buy|sell|opportunity|risky)\b|leads to|causes/i;
const all = (i: ReturnType<typeof generateInsight>) => [i.cloud, i.shape, ...i.companies, ...i.comparison, ...i.caveats, i.footer].filter(Boolean).join(" ");

describe("correlation insight (spec)", () => {
  it("a strong positive relationship says so, with the direction and the tendency", () => {
    const t = generateInsight(base({ points: line(60), rho: 0.92, p: 0.0001 }));
    expect(t.cloud).toBe("Across 60 companies there is a strong positive relationship (rho = 0.92): companies with higher P/E ratio tend to have higher EPS growth.");
  });
  it("random data says no meaningful relationship and carries the weak-correlation caveat", () => {
    const t = generateInsight(base({ points: noise(300), rho: 0.03 }));
    expect(t.cloud).toContain("show no meaningful relationship (rho = 0.03)");
    expect(t.caveats).toContain("A weak correlation does not mean one measure drives the other.");
  });
  it("a relationship whose p is not below 0.05 is called not statistically reliable", () => {
    expect(generateInsight(base({ points: noise(100), rho: -0.35, p: 0.2 })).cloud).toBe("Across 100 companies there may be a moderate negative relationship (rho = −0.35), but it is not statistically reliable.");
  });
  it("under 30 points the strength wording is replaced by the small-sample message", () => {
    const t = generateInsight(base({ points: line(12), rho: 0.9, p: 0.0001 }));
    expect(t.cloud).toContain("too few points for a reliable pattern"); expect(t.cloud).not.toMatch(/strong|moderate|weak/); expect(t.caveats).toContain("Too few companies for a reliable pattern.");
  });
  it("no linear pattern but uneven spread gets the shape note", () => {
    const r = rng(3), pts = Array.from({ length: 400 }, (_, i) => { const x = i < 200 ? r() * 10 : 10 + r() * 10; return { s: "S" + i, x, y: (r() - 0.5) * (i < 200 ? 100 : 4) }; });
    expect(generateInsight(base({ points: pts, rho: 0.02 })).shape).toBe("There is no linear pattern, but EPS growth varies much more among companies with lower P/E ratio.");
  });
  it("a company in the middle of the cloud sits close to the middle; a high-high one is described by quadrant, percentiles and the trend line", () => {
    const pts = line(101);
    const mid = generateInsight(base({ points: pts, rho: 0.9, p: 0.001, selected: [{ s: "S50", name: "Mid Co", x: 51, y: 102, why: null }] }));
    expect(mid.companies[0]).toContain("Mid Co has P/E ratio of 51.0x (mid-range, higher than 50% of companies) and EPS growth of 102.0% (mid-range, higher than 50% of companies). It sits close to the middle of the cloud on both measures.");
    const hi = generateInsight(base({ points: pts, rho: 0.9, p: 0.001, selected: [{ s: "S99", name: "Top Co", x: 100, y: 200, why: null }] }));
    expect(hi.companies[0]).toContain("top quartile"); expect(hi.companies[0]).toContain("It is more expensive and faster growing than the typical company.");
  });
  it("two companies are compared: same area, or different with percentiles", () => {
    const pts = line(101), s = (n: string, k: number) => ({ s: n, name: n, x: k, y: 2 * k, why: null });
    expect(generateInsight(base({ points: pts, rho: 0.9, p: 0.001, selected: [s("A", 95), s("B", 90)] })).comparison[0]).toBe("A and B sit in the same area of the chart (more expensive and faster growing).");
    const d = generateInsight(base({ points: pts, rho: 0.9, p: 0.001, selected: [s("A", 95), { s: "B", name: "B", x: 5, y: 150, why: null }] })).comparison[0];
    expect(d).toBe("A has higher P/E ratio than B (percentile 93 vs 4), while EPS growth is higher (93 vs 73).");
  });
  it("a company with an undefined figure is only a caveat, never described with numbers", () => {
    const t = generateInsight(base({ points: line(60), rho: 0.5, p: 0.001, selected: [{ s: "Z", name: "Repro India Ltd", x: null, y: null, why: "Growth is not defined because the earlier-year EPS was zero or negative." }] }));
    expect(t.companies).toEqual([]); expect(t.caveats[0]).toBe("Repro India Ltd is not plotted: growth is not defined because the earlier-year EPS was zero or negative.");
  });
  it("outside-window, skew and identical values follow the spec; the footer has the period and the count", () => {
    const t = generateInsight(base({ points: noise(100), rho: 0.0, outside: 74 }));
    expect(t.caveats).toContain("Statistics include 74 points outside the visible window."); expect(t.footer).toBe("Based on FY2025 data, 100 companies.");
    expect(generateInsight(base({ points: Array.from({ length: 40 }, (_, i) => ({ s: "S" + i, x: 5, y: i })), rho: 0 })).cloud).toBe("No variation in P/E ratio, so no relationship can be measured.");
    const skew = [...Array.from({ length: 200 }, (_, i) => ({ s: "S" + i, x: i, y: 1 + (i % 3) })), { s: "BIG", x: 201, y: 5000 }];
    expect(generateInsight(base({ points: skew, rho: 0.0 })).caveats.join(" ")).toContain("EPS growth is heavily skewed by a few extreme values, so rank-based statistics are used.");
  });
  it("is deterministic, uses no banned word and sentence wording never implies cause", () => {
    const i = base({ points: line(80), rho: 0.8, p: 0.001, selected: [{ s: "S70", name: "A Co", x: 71, y: 142, why: null }, { s: "S10", name: "B Co", x: 11, y: 22, why: null }] });
    expect(JSON.stringify(generateInsight(i))).toBe(JSON.stringify(generateInsight(i)));
    expect(all(generateInsight(i))).not.toMatch(BANNED);
    expect(all(generateInsight(base({ points: noise(100), rho: -0.5, p: 0.0001 })))).not.toMatch(BANNED);
  });
  it("percentiles and the Theil-Sen line behave", () => {
    expect(percentileRank([1, 2, 3, 4], 3)).toBe(50);
    const ts = theilSen(line(50))!; expect(ts.slope).toBeCloseTo(2, 6); expect(ts.intercept).toBeCloseTo(0, 6);
  });
  it("the wording of an axis comes from its label, with a plain fallback", () => {
    expect(metricCfg("EV/EBITDA")).toMatchObject({ higher: "more expensive", lower: "cheaper" });
    expect(metricCfg("Debt/Equity").higher).toBe("more leveraged");
    expect(metricCfg("Dividend yield").higher).toBe("higher on Dividend yield");
  });
});
