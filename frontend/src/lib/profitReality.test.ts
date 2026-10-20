import { describe, expect, it } from "vitest";
import { profitReality } from "./profitReality";

const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows });
const P = ["FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];

describe("profitReality", () => {
  const pl = t(P, { revenue: [1000, 1100, 1200, 1300, 1400, 1500], net_profit: [100, 110, 120, 130, 140, 200], profit_before_tax: [130, 140, 150, 165, 180, 250], tax: [30, 30, 30, 35, 40, 50], other_income: [10, 10, 10, 10, 10, 10], exceptional_items: [0, 0, 0, 0, 0, 0], discontinued_profit: [0, 0, 0, 0, 0, 0] });
  const cf = t(P, { operating: [95, 105, 115, 125, 135, 130], free_cash_flow: [50, 60, 70, 80, 90, 80] });
  const bs = t(P, { receivables: [100, 110, 120, 130, 140, 190], inventories: [100, 110, 120, 130, 140, 150] });

  it("flags 'profit rose but cash did not' (headline case)", () => {
    const r = profitReality(pl, bs, cf, false);
    const y = r.years[r.years.length - 1];
    expect(y.profitGrowth).toBeCloseTo(42.9, 1);
    expect(y.profitNoCash).toBe(true);
    expect(r.headline).toMatch(/Profit rose but cash did not/);
    expect(r.verdict).toBe("Needs a closer look");
    expect(r.findings[0]).toMatch(/Profit rose but cash did not/);
    expect(r.findings.length).toBeLessThanOrEqual(4);
  });
  it("flags receivables outgrowing sales by 10+ points", () => {
    const y = profitReality(pl, bs, cf, false).years.at(-1)!;
    expect(y.receivablesGap).toBeGreaterThan(10);
    expect(y.receivablesFlag).toBe(true);
    expect(y.inventoryFlag).toBe(false);
  });
  it("normalizes: removes discontinued and after-tax exceptional gains, floors/caps the tax rate", () => {
    const p = t(["FY24", "FY25"], { revenue: [1000, 1000], net_profit: [100, 300], profit_before_tax: [130, 200], tax: [30, 100], exceptional_items: [0, 100], discontinued_profit: [0, 50], other_income: [5, 5] });
    const y = profitReality(p, undefined, undefined, false).years[1];
    expect(y.taxRate).toBeCloseTo(0.4 > 0.5 ? 0.4 : 0.4, 2);   // 100/200 = 50%, capped at 40%
    expect(y.normalized).toBeCloseTo(300 - 50 - 60, 0);
    expect(y.oneOffFlag).toBe(true);
  });
  it("treats other income above 20% of pre-tax profit as separate adjustment", () => {
    const p = t(["FY24", "FY25"], { revenue: [1000, 1000], net_profit: [80, 80], profit_before_tax: [100, 100], tax: [20, 20], other_income: [10, 60] });
    const [a, b] = profitReality(p, undefined, undefined, false).years;
    expect(a.otherIncomeAdjustment).toBeNull();
    expect(b.otherIncomeShare).toBe(60);
    expect(b.normalized).toBeCloseTo(80 - (60 - 20) * 0.8, 0);
  });
  it("counts repeated cash gaps and cumulative conversion", () => {
    const weak = t(P, { operating: [20, 25, 30, 35, 40, 45] });
    const r = profitReality(pl, bs, weak, false);
    expect(r.gapYears).toBe(6);
    expect(r.cumulative?.years).toBe(5);
    expect(r.cumulative?.ratio).toBeLessThan(0.8);
    expect(r.verdict).toBe("Needs a closer look");
  });
  it("is Strong for a clean company", () => {
    const p = t(P, { revenue: [1000, 1050, 1100, 1160, 1220, 1280], net_profit: [100, 105, 110, 116, 122, 128], profit_before_tax: [130, 135, 140, 150, 160, 170], tax: [30, 30, 30, 34, 38, 42], other_income: [5, 5, 5, 5, 5, 5], exceptional_items: [0, 0, 0, 0, 0, 0] });
    const c = t(P, { operating: [110, 115, 120, 125, 130, 140] });
    const b = t(P, { receivables: [100, 105, 110, 116, 122, 128], inventories: [50, 52, 55, 58, 61, 64] });
    expect(profitReality(p, b, c, false).verdict).toBe("Strong");
  });
  it("skips cash and working-capital tests for lenders, with a note", () => {
    const r = profitReality(pl, bs, cf, true);
    expect(r.years.every((y) => y.cfoToProfit == null && y.cfo == null && !y.receivablesFlag)).toBe(true);
    expect(r.rules.filter((x) => ["cash5", "gaps", "nocash", "wc"].includes(x.key)).every((x) => x.status === "na")).toBe(true);
    expect(r.notes.join(" ")).toMatch(/lender/);
    expect(r.headline).toBeNull();
  });
  it("handles missing years, negative profit, zero revenue and no data", () => {
    expect(profitReality(undefined, undefined, undefined, false).years).toEqual([]);
    expect(profitReality(undefined, undefined, undefined, false).verdict).toBeNull();
    const p = t(["FY24", "FY25", "FY26"], { revenue: [0, 0, 0], net_profit: [-50, null, -20], profit_before_tax: [-40, null, -10], tax: [1, null, 1] });
    const c = t(["FY24", "FY26"], { operating: [10, -5] });
    const r = profitReality(p, undefined, c, false);
    expect(r.years.length).toBe(2);
    const y = r.years[1];
    expect(y.cfoToProfit).toBeNull();        // no ratio against a loss
    expect(y.revenueGrowth).toBeNull();      // zero revenue base
    expect(y.normalized).toBe(-20);
    expect(y.taxRate).toBe(0.25);
    expect(r.cumulative).toBeNull();
    expect(JSON.stringify(r)).not.toMatch(/NaN|Infinity/);
  });
  it("does not flag a profit jump when the earlier profit was zero or negative", () => {
    const p = t(["FY25", "FY26"], { net_profit: [-10, 50] }), c = t(["FY25", "FY26"], { operating: [20, 20] });
    expect(profitReality(p, undefined, c, false).years[1].profitNoCash).toBe(false);
  });
});
