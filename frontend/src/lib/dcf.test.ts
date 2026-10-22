import { describe, expect, it } from "vitest";
import { around, compute, costOfCapital, defaultScenarios, impliedGrowth, impliedReturn, run, scenarios, sensitivity, validate, type DcfInputs } from "./dcf";

// The calculator's own example (terminal growth set to 5%: the 13% in the brief is above the 12% discount rate, which the model refuses).
// Expected values were worked out independently with 40-digit decimal arithmetic, step by step from the formula sheet.
const BASE: DcfInputs = { fcf0: 100, r: 12, g1: 10, g2: 10, gT: 5, marketCap: 2000, price: 100, netDebt: 1000, mos: 4 };

describe("DCF formula sheet, steps 2-12", () => {
  const res = compute(BASE);
  it("projects FCF in two stages and discounts each year", () => {
    expect(res.years).toHaveLength(10);
    expect(res.years[4].fcf).toBeCloseTo(100 * 1.1 ** 5, 9);                 // FCF_5 = FCF_0 (1 + g1)^5
    expect(res.years[9].fcf).toBeCloseTo(259.374246, 6);                     // FCF_10
    expect(res.years[0].pv).toBeCloseTo(110 / 1.12, 9);                      // PV(FCF_1) = FCF_1 / (1 + r)
    expect(res.sumPv).toBeCloseTo(906.863899, 6);
  });
  it("terminal value, enterprise value, equity, shares and value per share", () => {
    expect(res.fcf11).toBeCloseTo(259.374246 * 1.05, 5);
    expect(res.tv).toBeCloseTo(3890.613690, 5);                              // FCF_11 / (r - gT)
    expect(res.pvTv).toBeCloseTo(1252.673482, 5);                            // TV / (1 + r)^10
    expect(res.ev).toBeCloseTo(2159.537381, 5);
    expect(res.equity).toBeCloseTo(1159.537381, 5);                          // EV - net debt
    expect(res.shares).toBe(20);                                             // 2000 Cr / ₹100 = 20 crore shares
    expect(res.iv).toBeCloseTo(57.976869, 6);
    expect(res.upside).toBeCloseTo(-42.023131, 6);
    expect(res.buyPrice).toBeCloseTo(55.657794, 6);                          // IV × (1 - 4%)
    expect(res.status).toBe("overvalued");
    expect(res.tvShare).toBeCloseTo((1252.673482 / 2159.537381) * 100, 6);
    expect(res.exitMultiple).toBeCloseTo(1.05 / 0.07, 9);                    // (1 + gT) / (r - gT) for the Gordon method
    expect(res.impliedGT).toBeCloseTo(5, 9);
  });
  it("status follows step 12 exactly", () => {
    const at = (price: number) => compute({ ...BASE, price, shares: 20 });   // the same 20 crore shares at another price
    expect(at(55).status).toBe("buy");                                       // price ≤ buy price (₹55.66)
    expect(at(55.657794).status).toBe("buy");
    expect(at(57).status).toBe("fair");                                      // buy price < price ≤ intrinsic value (₹57.98)
    expect(at(compute(BASE).iv).status).toBe("fair");
    expect(at(58).status).toBe("overvalued");
    expect(compute({ ...BASE, price: 55 }).shares).toBeCloseTo(2000 / 55, 9);  // without a share count, shares = market cap ÷ price (step 8)
    expect(compute({ ...BASE, netDebt: 5000 }).status).toBe("not-meaningful");
  });
  it("uses an explicit diluted share count when given", () => {
    expect(compute({ ...BASE, shares: 25 }).iv).toBeCloseTo(1159.537381 / 25, 6);
  });
  it("mid-year convention discounts each year 0.5 years less, and the Gordon TV 9.5 years", () => {
    const m = compute({ ...BASE, midYear: true });
    expect(m.years[0].factor).toBeCloseTo(1 / 1.12 ** 0.5, 12);
    expect(m.pvTv).toBeCloseTo(m.tv / 1.12 ** 9.5, 6);
    expect(m.iv).toBeGreaterThan(compute(BASE).iv);
  });
  it("exit-multiple terminal value and the growth it implies", () => {
    const x = compute({ ...BASE, tvMethod: "exit", exitMultiple: 15 });
    expect(x.tv).toBeCloseTo(15 * 259.374246, 4);
    expect(x.pvTv).toBeCloseTo(x.tv / 1.12 ** 10, 6);                        // a price at the end of year 10, also with mid-year off or on
    expect(compute({ ...BASE, tvMethod: "exit", exitMultiple: 15, midYear: true }).pvTv).toBeCloseTo(x.tv / 1.12 ** 10, 6);
    expect(x.impliedGT).toBeCloseTo(((15 * 0.12 - 1) / 16) * 100, 9);       // (TV r - FCF) / (TV + FCF) with TV = 15 FCF
  });
});

describe("validation", () => {
  it("refuses terminal growth at or above the discount rate (the brief's 13% vs 12%)", () => {
    const e = validate({ ...BASE, gT: 13 });
    expect(e.map((x) => x.field)).toContain("gT");
    expect(run({ ...BASE, gT: 12 }).result).toBeNull();
    expect(run({ ...BASE, gT: 13, tvMethod: "exit", exitMultiple: 12 }).result).not.toBeNull();   // no Gordon formula, no such limit
  });
  it("refuses missing numbers, a non-positive starting FCF, price or market cap, and an impossible margin of safety", () => {
    expect(validate({ ...BASE, fcf0: NaN })[0].field).toBe("fcf0");
    expect(validate({ ...BASE, fcf0: -50 })[0].field).toBe("fcf0");
    expect(validate({ ...BASE, price: 0 }).map((x) => x.field)).toContain("price");
    expect(validate({ ...BASE, marketCap: -1 }).map((x) => x.field)).toContain("marketCap");
    expect(validate({ ...BASE, mos: 100 }).map((x) => x.field)).toContain("mos");
    expect(validate({ ...BASE, shares: 0 }).map((x) => x.field)).toContain("shares");
    expect(validate({ ...BASE, tvMethod: "exit", exitMultiple: 0 }).map((x) => x.field)).toContain("exitMultiple");
    expect(validate(BASE)).toEqual([]);
  });
  it("warns about fragile assumptions without blocking the result", () => {
    const w = run({ ...BASE, gT: 10.5, g1: 35 }).warnings.map((x) => x.text).join(" ");
    expect(w).toMatch(/terminal growth of 10.5%/);
    expect(w).toMatch(/only 1.50 points/);
    expect(w).toMatch(/multiplies by 4.5×/);
    expect(w).toMatch(/comes from the terminal value/);
    expect(run(BASE).warnings.map((x) => x.field)).not.toContain("gT");
    expect(run({ ...BASE, netDebt: 5000 }).warnings.map((x) => x.field)).toContain("netDebt");
  });
});

describe("analysis", () => {
  it("sensitivity grid recomputes every cell and leaves impossible ones empty", () => {
    const rs = around(12, 1), gs = around(5, 0.5);
    expect(rs).toEqual([10, 11, 12, 13, 14]);
    expect(gs).toEqual([4, 4.5, 5, 5.5, 6]);
    const grid = sensitivity(BASE, "gT", gs, "r", rs);
    expect(grid[2][2]).toBeCloseTo(compute(BASE).iv, 9);                     // the centre is the base case
    expect(grid[0][4]).toBeLessThan(grid[4][0] as number);                   // higher r and lower g give less value
    expect(sensitivity(BASE, "gT", [12], "r", [12])[0][0]).toBeNull();
  });
  it("reverse DCF finds the growth and the return the price implies", () => {
    const g = impliedGrowth(BASE) as number;
    expect(compute({ ...BASE, g1: g }).iv).toBeCloseTo(BASE.price, 6);
    expect(g).toBeGreaterThan(BASE.g1);                                      // the price (₹100) is above the value (₹58): it needs more growth
    const r = impliedReturn(BASE) as number;
    expect(compute({ ...BASE, r }).iv).toBeCloseTo(BASE.price, 6);
    expect(r).toBeLessThan(BASE.r);
    expect(impliedGrowth({ ...BASE, gT: 13 })).toBeNull();
  });
  it("scenarios weight each case's value by its probability", () => {
    const cases = defaultScenarios(BASE);
    const s = scenarios(BASE, cases);
    const ivs = cases.map((c) => compute({ ...BASE, g1: c.g1, g2: c.g2, r: c.r }).iv);
    expect(s.weighted).toBeCloseTo(0.25 * ivs[0] + 0.5 * ivs[1] + 0.25 * ivs[2], 9);
    expect(scenarios(BASE, cases.map((c) => ({ ...c, probability: 30 }))).weighted).toBeNull();   // must add up to 100
  });
  it("CAPM cost of equity and WACC", () => {
    const c = costOfCapital({ rf: 6.8, beta: 1.2, erp: 7, kd: 9, tax: 25.17, debtWeight: 20 });
    expect(c.ke).toBeCloseTo(6.8 + 1.2 * 7, 9);
    expect(c.kdAfterTax).toBeCloseTo(9 * (1 - 0.2517), 9);
    expect(c.wacc).toBeCloseTo(0.8 * 15.2 + 0.2 * 9 * 0.7483, 9);
  });
});
