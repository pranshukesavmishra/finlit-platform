import { describe, expect, it } from "vitest";
import { dupont, dupontSummary, shareText } from "./dupont";

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

describe("share and summary wording", () => {
  const pl = { unit: "Cr", period: "yearly", periods: ["FY22", "FY26"], periodEnds: ["FY22", "FY26"], rows: { revenue: [1000, 1500], net_profit: [100, 90] } };
  const bs = { unit: "Cr", period: "yearly", periods: ["FY22", "FY26"], periodEnds: ["FY22", "FY26"], rows: { total_assets: [1000, 1200], total_equity: [500, 480] } };
  it("share text is empty when no share exists and flags offsets", () => {
    expect(shareText({ shareOfMove: null })).toBe(""); expect(shareText({ shareOfMove: 53 })).toBe("53% of the ROE move"); expect(shareText({ shareOfMove: -20 })).toBe("offsets 20% of the ROE move");
  });
  it("summary describes the move in plain words, with no advice", () => {
    const s = dupontSummary(dupont(pl, bs, false));
    expect(s).toBe("From FY22 to FY26, ROE fell from 20.00% to 18.75%. Net profit margin fell, asset turnover rose and the equity multiplier rose.");
    expect(s).not.toMatch(/\b(buy|sell|hold|target|recommend)/i);
  });
  it("summary is empty with a single year", () => { expect(dupontSummary(dupont({ ...pl, periods: ["FY26"], rows: { revenue: [1500], net_profit: [90] } }, { ...bs, periods: ["FY26"], rows: { total_assets: [1200], total_equity: [480] } }, false))).toBe(""); });
});
