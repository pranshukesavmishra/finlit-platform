import { describe, expect, it } from "vitest";
import { dupont } from "./dupont";

const t = (periods: string[], rows: Record<string, (number | null)[]>) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows });

describe("dupont", () => {
  const pl = t(["FY23", "FY26"], { revenue: [1000, 1200], net_profit: [250, 280], profit_before_tax: [330, 370], finance_costs: [20, 10], discontinued_profit: [null, null] });
  const bs = t(["FY23", "FY26"], { total_assets: [1120, 1300], total_equity: [910, 1010] });
  it("factors multiply back to net profit over equity", () => {
    const d = dupont(pl, bs, false), y = d.years[1];
    expect(y.netMargin).toBeCloseTo(23.33, 2);
    expect(y.turnover).toBeCloseTo(0.92, 2);
    expect(y.multiplier).toBeCloseTo(1.29, 2);
    expect(y.roe).toBeCloseTo(27.72, 2);                                        // 280 / 1010
    const product = (280 / 1200) * (1200 / 1300) * (1300 / 1010) * 100;
    expect(y.roe).toBeCloseTo(product, 2);
  });
  it("five factors also multiply back (not for lenders)", () => {
    const y = dupont(pl, bs, false).years[1];
    const five = (y.taxBurden as number) * (y.interestBurden as number) * ((y.ebitMargin as number) / 100) * (y.turnover as number) * (y.multiplier as number) * 100;
    expect(five).toBeCloseTo(y.roe as number, 0);
    expect(dupont(pl, bs, true).years[1].taxBurden).toBeNull();
  });
  it("describes what moved ROE in words and flags discontinued-operations profit", () => {
    const pl2 = t(["FY25"], { revenue: [1000], net_profit: [420], profit_before_tax: [300], finance_costs: [5], discontinued_profit: [150] });
    const bs2 = t(["FY25"], { total_assets: [1000], total_equity: [800] });
    const y = dupont(pl2, bs2, false).years[0];
    expect(y.flag).toMatch(/discontinued/);
    expect(y.underlyingMargin).toBeCloseTo(27, 1);                              // (420 - 150) / 1000
    expect(dupont(pl, bs, false).words[0]).toMatch(/net margin fell/);
  });
  it("is empty and safe without data or with zero equity", () => {
    expect(dupont(undefined, undefined, false).years).toEqual([]);
    const y = dupont(pl, t(["FY23", "FY26"], { total_assets: [1, 1], total_equity: [0, -5] }), false).years[1];
    expect(y.roe).toBeNull(); expect(y.multiplier).toBeNull();
  });
});
