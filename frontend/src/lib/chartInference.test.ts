import { describe, expect, it } from "vitest";
import { bandOf, BANDS_TIP, chartInference, CLOSING, pFromR, percentileRank, placeMarker, type InfInput } from "./chartInference";

const base: InfInput = { kind: "cross", n: 500, r: 0.4, p: 0.001, rho: 0.4, xName: "P/E", yName: "ROCE" };
const text = (i: ReturnType<typeof chartInference>) => [i.headline, ...i.lines.map((l) => l.text), ...i.placements.map((p) => p.text), i.closing].join(" ");

describe("bands", () => {
  it.each([[0, "negligible"], [0.099, "negligible"], [0.1, "weak"], [-0.29, "weak"], [0.3, "moderate"], [-0.49, "moderate"], [0.5, "strong"], [0.69, "strong"], [0.7, "very strong"], [-1, "very strong"]])("|r| %s is %s", (r, w) => {
    expect(bandOf(r).word).toBe(w);
  });
  it("states the bands in the tooltip", () => { for (const w of ["negligible", "weak", "moderate", "strong", "very strong"]) expect(BANDS_TIP).toContain(w); });
  it("headline gives direction and strength", () => {
    expect(chartInference({ ...base, r: -0.35 }).headline).toMatch(/moderate negative relationship \(r = −0\.35\).*higher P\/E tended to have a lower ROCE/);
    expect(chartInference({ ...base, r: 0.6 }).headline).toMatch(/strong positive.*higher ROCE/);
    expect(chartInference({ ...base, r: -0.01 }).headline).toMatch(/^Negligible relationship \(r = −0\.01\)/);
  });
});

describe("significance", () => {
  it("significant: p below 0.05 with the independence and 1 in 20 of 130 caveat", () => {
    const t = chartInference({ ...base, p: 0.02 }).lines.find((l) => l.id === "p")!.text;
    expect(t).toMatch(/statistically distinguishable from zero \(p = 0\.0200/);
    expect(t).toMatch(/not independent/); expect(t).toMatch(/1 in 20 of the 130 charts/);
  });
  it("not significant", () => { expect(chartInference({ ...base, r: -0.01, p: 0.803 }).lines.find((l) => l.id === "p")!.text).toMatch(/not distinguishable from zero \(p = 0\.803/); });
  it("tiny p shown as < 0.001", () => { expect(chartInference({ ...base, p: 1e-9 }).lines.find((l) => l.id === "p")!.text).toContain("p < 0.001"); });
  it("missing p says so and does not claim significance", () => {
    const t = chartInference({ ...base, p: null }).lines.find((l) => l.id === "p")!.text;
    expect(t).toMatch(/could not be worked out/); expect(t).not.toMatch(/distinguishable from zero \(/);
  });
});

describe("Pearson against Spearman", () => {
  it("rank stronger than linear", () => { expect(chartInference({ ...base, r: 0.1, rho: 0.45 }).lines.find((l) => l.id === "agree")!.text).toMatch(/rank-based correlation .* is stronger than the linear one.*curved or driven by a few extreme points/); });
  it("linear stronger than rank", () => { expect(chartInference({ ...base, r: 0.5, rho: 0.2 }).lines.find((l) => l.id === "agree")!.text).toMatch(/linear correlation .* stronger than the rank-based/); });
  it("agree", () => { expect(chartInference({ ...base, r: 0.4, rho: 0.45 }).lines.find((l) => l.id === "agree")!.text).toMatch(/agree/); });
  it("opposite directions are flagged", () => { const l = chartInference({ ...base, r: 0.3, rho: -0.3 }).lines.find((x) => x.id === "agree")!; expect(l.warn).toBe(true); expect(l.text).toMatch(/disagree on direction/); });
  it("no rho, no line", () => { expect(chartInference({ ...base, rho: null }).lines.some((l) => l.id === "agree")).toBe(false); });
});

describe("sample size and coverage", () => {
  it("warns when n < 30", () => { const l = chartInference({ ...base, n: 12 }).lines.find((x) => x.id === "small")!; expect(l.warn).toBe(true); expect(l.text).toContain("only 12"); });
  it("no small-sample warning at 30", () => { expect(chartInference({ ...base, n: 30 }).lines.some((l) => l.id === "small")).toBe(false); });
  it("reports used vs left out with the main reason, and warns under 50%", () => {
    const l = chartInference({ ...base, n: 2259, left: 3554, total: 5813, leftReason: "no P/E on file" }).lines.find((x) => x.id === "coverage")!;
    expect(l.text).toContain("2,259 of the 5,813 companies"); expect(l.text).toContain("(39%)"); expect(l.text).toContain("3,554 are left out, mainly because no P/E on file"); expect(l.warn).toBe(true);
  });
  it("no warning at high coverage", () => { const l = chartInference({ ...base, left: 100, total: 1000 }).lines.find((x) => x.id === "coverage")!; expect(l.warn).toBe(false); });
  it("nothing left out", () => { expect(chartInference({ ...base, left: 0, total: 80 }).lines.find((x) => x.id === "coverage")!.text).toMatch(/All 80/); });
  it("coverage is for cross-sections only", () => { expect(chartInference({ ...base, kind: "history", left: 5, total: 10 }).lines.some((l) => l.id === "coverage")).toBe(false); });
});

describe("outside the window", () => {
  it("mentions the toggle only while not all points are shown", () => {
    expect(chartInference({ ...base, outside: 4, allShown: false }).lines.find((l) => l.id === "outliers")!.text).toMatch(/4 extreme points lie outside.*Show every point/);
    expect(chartInference({ ...base, outside: 1 }).lines.find((l) => l.id === "outliers")!.text).toMatch(/1 extreme point lies/);
    expect(chartInference({ ...base, outside: 4, allShown: true }).lines.some((l) => l.id === "outliers")).toBe(false);
    expect(chartInference({ ...base, outside: 0 }).lines.some((l) => l.id === "outliers")).toBe(false);
  });
});

describe("placements of added companies", () => {
  const cloud = Array.from({ length: 100 }, (_, i) => ({ x: i + 1, y: i + 1 }));
  it("percentile of X and Y, descriptive", () => {
    const t = placeMarker({ name: "RELIANCE", x: 90.5, y: 50 }, cloud, { xName: "P/E", yName: "ROCE" })!;
    expect(t).toContain("RELIANCE has a higher P/E than 90% of the companies shown");
    expect(t).toContain("a ROCE close to the middle");
  });
  it("uses the trend line only when one is drawn", () => {
    const withLine = placeMarker({ name: "A", x: 50, y: 80 }, cloud, { xName: "X", yName: "Y", lineDrawn: true, fit: { slope: 1, intercept: 0 } })!;
    expect(withLine).toContain("above the trend line");
    const noLine = placeMarker({ name: "A", x: 50, y: 80 }, cloud, { xName: "X", yName: "Y", lineDrawn: false, fit: { slope: 1, intercept: 0 } })!;
    expect(noLine).not.toContain("trend line"); expect(noLine).toMatch(/above the middle value among companies with a similar X/);
  });
  it("skips a marker with no position or a tiny cloud", () => {
    expect(placeMarker({ name: "A", x: null, y: 1 }, cloud, { xName: "X", yName: "Y" })).toBeNull();
    expect(placeMarker({ name: "A", x: 1, y: 1 }, cloud.slice(0, 3), { xName: "X", yName: "Y" })).toBeNull();
  });
  it("flows into the result", () => { expect(chartInference({ ...base, markers: [{ name: "TCS", x: 5, y: 5 }], cloud }).placements[0].name).toBe("TCS"); });
  it("percentileRank counts ties as half", () => { expect(percentileRank([1, 2, 2, 3], 2)).toBe(0.5); });
});

describe("edge cases", () => {
  it("n too small: nothing is said", () => {
    for (const n of [0, 1, 2, null, undefined, NaN]) { const i = chartInference({ ...base, n }); expect(i.state).toBe("empty"); expect(i.headline).toBe("Not enough points to say anything."); expect(i.lines).toEqual([]); }
  });
  it("r NaN or null (constant series): no correlation claimed", () => {
    for (const r of [NaN, null, undefined]) { const i = chartInference({ ...base, r }); expect(i.headline).toMatch(/No correlation can be measured/); expect(i.lines.some((l) => l.id === "p")).toBe(false); }
  });
  it("perfect correlation is flagged as suspicious, not celebrated", () => {
    const i = chartInference({ ...base, r: 1, rho: 1, p: 0 });
    expect(i.headline).toMatch(/line up exactly \(r = 0\.00|r = 1\.00/); expect(i.lines.find((l) => l.id === "perfect")!.warn).toBe(true);
  });
  it("always ends with the closing line", () => {
    expect(chartInference(base).closing).toBe(CLOSING);
    expect(CLOSING).toMatch(/Correlation is not causation.*not a recommendation.*Information only, not investment advice\.$/);
    expect(chartInference({ ...base, kind: "series" }).closing).toMatch(/over time/);
  });
  it("is deterministic and never uses advice words", () => {
    const i = chartInference({ ...base, left: 10, total: 100, outside: 3, markers: [{ name: "A", x: 1, y: 1 }], cloud: Array.from({ length: 20 }, (_, k) => ({ x: k, y: k })) });
    expect(chartInference({ ...base, left: 10, total: 100, outside: 3, markers: [{ name: "A", x: 1, y: 1 }], cloud: Array.from({ length: 20 }, (_, k) => ({ x: k, y: k })) })).toEqual(i);
    expect(text(i)).not.toMatch(/\b(buy|sell|hold|overvalued|undervalued|cheap|expensive)\b/i);
  });
});

describe("pFromR", () => {
  it("matches known values", () => {
    expect(pFromR(0.5, 10)!).toBeCloseTo(0.1413, 3);
    expect(pFromR(-0.01, 2259)!).toBeCloseTo(0.63, 1);
    expect(pFromR(0, 50)!).toBeCloseTo(1, 6);
  });
  it("null when it cannot be worked out", () => { expect(pFromR(null, 10)).toBeNull(); expect(pFromR(NaN, 10)).toBeNull(); expect(pFromR(0.5, 2)).toBeNull(); });
  it("perfect correlation gives 0", () => { expect(pFromR(1, 10)).toBe(0); });
});
