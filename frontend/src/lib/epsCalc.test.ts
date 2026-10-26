import { describe, expect, it } from "vitest";
import { LIMITS, around, checkCase, eps, fix2, futureEps, futurePrice, parseNum, path, pctText, pe, peg, priceReturn, project, requiredGrowth, round2, sensitivity } from "./epsCalc";

describe("reference example: 100, 0, 10, 300; growth 12%, P/E 20, 5 years", () => {
  const e = eps(100, 0, 10)!;
  it("EPS and current P/E", () => { expect(fix2(e)).toBe("10.00"); expect(fix2(pe(300, e).value!)).toBe("30.00"); });
  it("future EPS, price and return", () => {
    const r = project(e, 300, { growth: 12, targetPe: 20 }, 5)!;
    expect(fix2(r.eps)).toBe("17.62"); expect(fix2(r.price)).toBe("352.47"); expect(pctText(r.returnPct)).toBe("+17.49%");
  });
  it("price is built from unrounded EPS, not from the displayed 17.62", () => { expect(futurePrice(futureEps(10, 12, 5), 20)).toBeCloseTo(352.4683, 3); expect(17.62 * 20).not.toBeCloseTo(352.4683, 1); });
});

describe("EPS", () => {
  it("subtracts preference dividends", () => expect(eps(100, 20, 10)).toBe(8));
  it("zero, negative or missing shares give null", () => { expect(eps(100, 0, 0)).toBeNull(); expect(eps(100, 0, -1)).toBeNull(); expect(eps(100, 0, NaN)).toBeNull(); });
  it("a loss gives negative EPS and a P/E that is not meaningful", () => {
    const e = eps(-50, 0, 10)!; expect(e).toBe(-5); const p = pe(300, e); expect(p.value).toBeNull(); expect(p.reason).toMatch(/not meaningful/);
  });
  it("preference dividends larger than profit make EPS negative", () => { expect(eps(10, 25, 5)).toBe(-3); expect(pe(100, -3).value).toBeNull(); });
  it("zero EPS and bad prices give no P/E", () => { expect(pe(100, 0).value).toBeNull(); expect(pe(0, 5).value).toBeNull(); expect(pe(100, null).value).toBeNull(); });
});

describe("projection", () => {
  it("zero growth keeps EPS; the price is EPS × multiple", () => { const r = project(10, 300, { growth: 0, targetPe: 30 }, 7)!; expect(r.eps).toBe(10); expect(r.price).toBe(300); expect(r.returnPct).toBe(0); });
  it("one year", () => { const r = project(10, 100, { growth: 10, targetPe: 10 }, 1)!; expect(r.eps).toBeCloseTo(11, 10); expect(r.price).toBeCloseTo(110, 10); expect(r.returnPct).toBeCloseTo(10, 10); });
  it("negative growth shrinks EPS", () => expect(project(10, 100, { growth: -20, targetPe: 10 }, 2)!.eps).toBeCloseTo(6.4, 10));
  it("needs positive EPS and price", () => { expect(project(-1, 100, { growth: 5, targetPe: 10 }, 3)).toBeNull(); expect(project(0, 100, { growth: 5, targetPe: 10 }, 3)).toBeNull(); expect(project(5, 0, { growth: 5, targetPe: 10 }, 3)).toBeNull(); });
  it("limits on growth, multiple and years", () => {
    expect(checkCase({ growth: 12, targetPe: 20 }, 5).ok).toBe(true);
    expect(checkCase({ growth: LIMITS.growthMax + 1, targetPe: 20 }, 5).growth).toBeDefined();
    expect(checkCase({ growth: -51, targetPe: 20 }, 5).growth).toBeDefined();
    expect(checkCase({ growth: 5, targetPe: 0 }, 5).targetPe).toBeDefined();
    expect(checkCase({ growth: 5, targetPe: 20 }, 0).years).toBeDefined();
    expect(checkCase({ growth: 5, targetPe: 20 }, 31).years).toBeDefined();
    expect(checkCase({ growth: 5, targetPe: 20 }, 2.5).years).toBeDefined();
    expect(project(10, 100, { growth: 500, targetPe: 20 }, 5)).toBeNull();
  });
  it("path starts at today's EPS and ends at the projection", () => { const p = path(10, { growth: 12, targetPe: 20 }, 5); expect(p).toHaveLength(6); expect(p[0]).toMatchObject({ year: 0, eps: 10, price: 200 }); expect(p[5].eps).toBeCloseTo(17.6234, 3); });
  it("price return helper", () => expect(priceReturn(150, 100)).toBeCloseTo(50, 10));
});

describe("rounding and percent display", () => {
  it("rounds to 2 decimals, half away from zero", () => { expect(round2(1.005)).toBe(1.01); expect(round2(-1.005)).toBe(-1.01); expect(fix2(2.675)).toBe("2.68"); expect(fix2(10)).toBe("10.00"); });
  it("never shows negative zero", () => { expect(fix2(-0.001)).toBe("0.00"); expect(pctText(-0.001)).toBe("0.00%"); });
  it("signs percent with a true minus", () => { expect(pctText(17.486)).toBe("+17.49%"); expect(pctText(-3.2)).toBe("−3.20%"); expect(pctText(5, false)).toBe("5.00%"); });
  it("parses Indian-style numbers", () => { expect(parseNum("1,23,456.5")).toBe(123456.5); expect(parseNum("₹ 300")).toBe(300); expect(parseNum("20x")).toBe(20); expect(parseNum("")).toBeNaN(); expect(parseNum("abc")).toBeNaN(); });
});

describe("PEG", () => {
  it("is P/E ÷ growth", () => expect(peg(30, 12).value).toBeCloseTo(2.5, 10));
  it("needs positive growth and a P/E", () => { expect(peg(30, 0).value).toBeNull(); expect(peg(30, -5).value).toBeNull(); expect(peg(null, 10).value).toBeNull(); });
});

describe("reverse growth", () => {
  it("round-trips with the forward projection", () => {
    const g = requiredGrowth(352.4683, 20, 10, 5).value!; expect(g).toBeCloseTo(12, 3);
    const back = project(10, 300, { growth: g, targetPe: 20 }, 5)!; expect(back.price).toBeCloseTo(352.4683, 6);
  });
  it("a target below today's implied price needs negative growth", () => expect(requiredGrowth(100, 10, 20, 4).value!).toBeLessThan(0));
  it("edge cases return a reason", () => {
    expect(requiredGrowth(100, 10, -1, 5).value).toBeNull(); expect(requiredGrowth(100, 10, 0, 5).value).toBeNull(); expect(requiredGrowth(0, 10, 5, 5).value).toBeNull();
    expect(requiredGrowth(100, 0, 5, 5).value).toBeNull(); expect(requiredGrowth(100, 10, 5, 0).value).toBeNull(); expect(requiredGrowth(100, 10, null, 5).reason).toBeTruthy();
  });
});

describe("sensitivity", () => {
  it("centre cell equals the base projection; out-of-range cells are null", () => {
    const g = around(12, 3, 5, LIMITS.growthMin, LIMITS.growthMax), p = around(20, 5, 5, 1, LIMITS.peMax);
    expect(g).toEqual([6, 9, 12, 15, 18]); expect(p).toEqual([10, 15, 20, 25, 30]);
    const grid = sensitivity(10, 300, g, p, 5); expect(grid[2][2]!.price).toBeCloseTo(352.4683, 3);
    expect(sensitivity(10, 300, [500], [20], 5)[0][0]).toBeNull();
  });
  it("around drops values outside the limits", () => expect(around(2, 5, 5, 1, 200)).toEqual([2, 7, 12]));
});
