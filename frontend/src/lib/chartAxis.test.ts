import { describe, expect, it } from "vitest";
import { fromYears, labelEvery, priceFrom } from "./chartAxis";
import type { PriceRange } from "./api";

describe("label density", () => {
  it("prints every label when they fit and thins evenly when they do not", () => {
    expect(labelEvery(5, 600, 6)).toBe(1);
    expect(labelEvery(10, 600, 8)).toBe(1);
    expect(labelEvery(40, 300, 8)).toBeGreaterThan(1);
    expect(labelEvery(1, 10, 20)).toBe(1);
  });
  it("lists years from now back to 2010", () => { const y = fromYears(2026); expect(y[0]).toBe(2026); expect(y[y.length - 1]).toBe(2010); });
  it("cuts every price array at the same point", () => {
    const d = { series: { t: ["2023-12-29", "2024-01-02", "2024-01-03"], c: [1, 2, 3], v: [4, 5, 6], ema50: [7, 8, 9], ema200: [1, 1, 1] } } as unknown as PriceRange;
    const r = priceFrom(d, 2024).series;
    expect(r.t).toEqual(["2024-01-02", "2024-01-03"]); expect(r.c).toEqual([2, 3]); expect(r.ema50).toEqual([8, 9]);
    expect(priceFrom(d, 2020)).toBe(d);
  });
});
