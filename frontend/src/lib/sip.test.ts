import { describe, expect, it } from "vitest";
import {
  DEFAULT_STATE, EQUITY_TAX_2024, delayCost, duration, equityTax, fromQuery, gainsOvertake, milestones, monthlyRate, monthsToTarget, project,
  realValue, requiredMonthly, rupees, short, sipFutureValue, sipInYear, toQuery,
} from "./sip";

// Reference values worked out independently with Python's decimal module (50 significant digits), month by month, from the formula sheet.
describe("the formula sheet", () => {
  it("₹2,500 a month, 10 years, 12%: invested ₹3,00,000, value ₹5,75,097, gained ₹2,75,097", () => {
    const r = project({ monthly: 2500, years: 10, annualReturn: 12 });
    expect(r.n).toBe(120);
    expect(r.i).toBeCloseTo(0.01, 15);
    expect(r.invested).toBe(300000);
    expect(r.value).toBeCloseTo(575096.7238, 3);
    expect(rupees(r.value)).toBe("₹5,75,097");
    expect(rupees(r.gain)).toBe("₹2,75,097");
  });
  it("month by month equals the closed formula", () => {
    for (const [P, t, rate] of [[500, 1, 8], [10000, 25, 15], [1, 40, 30], [99999, 7, 0.1], [2500, 50, 12]] as const) {
      const r = project({ monthly: P, years: t, annualReturn: rate });
      const closed = sipFutureValue(P, rate / 1200, t * 12);
      expect(Math.abs(r.value - closed) / closed).toBeLessThan(1e-11);           // under a tenth of a paisa on ₹1 crore
    }
  });
  it("more cases checked by hand", () => {
    expect(project({ monthly: 5000, years: 20, annualReturn: 12 }).value).toBeCloseTo(4946276.8269, 3);   // ₹49,46,277
    expect(project({ monthly: 10000, years: 15, annualReturn: 10 }).value).toBeCloseTo(4144703.4621, 3);   // ₹41,44,703
    expect(project({ monthly: 1000, years: 30, annualReturn: 15 }).value).toBeCloseTo(6923279.6109, 3);   // ₹69,23,280
  });
  it("0% return is exactly the money put in (no division by zero)", () => {
    const r = project({ monthly: 2500, years: 10, annualReturn: 0 });
    expect(r.value).toBe(300000);
    expect(r.gain).toBe(0);
    expect(sipFutureValue(2500, 0, 120)).toBe(300000);
  });
  it("nothing in, nothing out", () => {
    expect(project({ monthly: 0, years: 10, annualReturn: 12 }).value).toBe(0);
    expect(project({ monthly: 2500, years: 0, annualReturn: 12 }).value).toBe(0);
  });
});

describe("options", () => {
  it("paying at the start of each month adds one month's growth to every instalment", () => {
    const end = project({ monthly: 2500, years: 10, annualReturn: 12 }).value;
    const start = project({ monthly: 2500, years: 10, annualReturn: 12, timing: "start" }).value;
    expect(start).toBeCloseTo(end * 1.01, 6);
    expect(rupees(start)).toBe("₹5,80,848");
  });
  it("effective compounding makes 12% a year exactly 12% after a year", () => {
    const i = monthlyRate(12, "effective");
    expect(Math.pow(1 + i, 12)).toBeCloseTo(1.12, 14);
    expect(Math.pow(1 + monthlyRate(12), 12)).toBeCloseTo(1.126825, 6);      // the sheet's r/12 compounds to 12.68%
    expect(project({ monthly: 2500, years: 10, annualReturn: 12, compounding: "effective" }).value).toBeCloseTo(554825.1034, 3);
  });
  it("step-up raises the SIP once a year", () => {
    expect(sipInYear(1000, 1, { kind: "pct", value: 10 })).toBe(1000);
    expect(sipInYear(1000, 3, { kind: "pct", value: 10 })).toBeCloseTo(1210, 9);
    expect(sipInYear(1000, 3, { kind: "amount", value: 500 })).toBe(2000);
    const r = project({ monthly: 1000, years: 2, annualReturn: 0, stepUp: { kind: "pct", value: 10 } });
    expect(r.invested).toBeCloseTo(12000 + 13200, 9);
    expect(r.years.map((y) => y.investedInYear)).toEqual([12000, 13200]);
    // 10% step-up on ₹2,500 for 10 years at 12%: ₹8,35,229 (independently computed)
    expect(project({ monthly: 2500, years: 10, annualReturn: 12, stepUp: { kind: "pct", value: 10 } }).value).toBeCloseTo(835229.2733, 3);
  });
  it("a one-time amount grows on its own and is reported apart", () => {
    const r = project({ monthly: 2500, years: 10, annualReturn: 12, lumpSum: 100000 });
    expect(r.lumpValue).toBeCloseTo(100000 * Math.pow(1.01, 120), 6);
    expect(r.sipValue).toBeCloseTo(575096.7238, 3);
    expect(r.invested).toBe(400000);
  });
  it("part years: years and months together", () => {
    const r = project({ monthly: 1000, years: 2, months: 6, annualReturn: 12 });
    expect(r.n).toBe(30);
    expect(r.years.map((y) => y.year)).toEqual([1, 2, 2.5]);
    expect(r.value).toBeCloseTo(sipFutureValue(1000, 0.01, 30), 8);
  });
  it("inputs outside the limits are held to them", () => {
    expect(project({ monthly: -5, years: 10, annualReturn: 12 }).value).toBe(0);
    expect(project({ monthly: 2500, years: 999, annualReturn: 12 }).n).toBe(600);
    expect(project({ monthly: 2500, years: 10, annualReturn: 99 }).i).toBeCloseTo(30 / 1200, 12);
    expect(project({ monthly: Number.NaN, years: 10, annualReturn: 12 }).value).toBe(0);
  });
});

describe("planning tools", () => {
  it("required SIP for a goal reproduces the goal", () => {
    const need = requiredMonthly(1e7, { years: 15, annualReturn: 12 })!;
    expect(need).toBeCloseTo(20016.8062, 3);                                    // ₹20,017 a month for ₹1 crore in 15 years at 12%
    expect(project({ monthly: need, years: 15, annualReturn: 12 }).value).toBeCloseTo(1e7, 4);
    const withAll = { years: 12, annualReturn: 11, lumpSum: 200000, stepUp: { kind: "pct" as const, value: 8 }, timing: "start" as const };
    const p2 = requiredMonthly(5e6, withAll)!;
    expect(project({ ...withAll, monthly: p2 }).value).toBeCloseTo(5e6, 4);
    expect(requiredMonthly(1000, { years: 10, annualReturn: 12, lumpSum: 100000 })).toBe(0);   // the lump sum alone gets there
    expect(requiredMonthly(1e6, { years: 0, annualReturn: 12 })).toBeNull();
  });
  it("time to a goal", () => {
    expect(monthsToTarget(575096, { monthly: 2500, annualReturn: 12 })).toBe(120);
    expect(monthsToTarget(1e12, { monthly: 100, annualReturn: 1 })).toBeNull();
  });
  it("gains overtake the money put in", () => {
    const m = gainsOvertake(project({ monthly: 2500, years: 30, annualReturn: 12 }))!;
    const r = project({ monthly: 2500, years: 30, annualReturn: 12 });
    expect(r.monthly[m].value - r.monthly[m].invested).toBeGreaterThan(r.monthly[m].invested);
    expect(r.monthly[m - 1].value - r.monthly[m - 1].invested).toBeLessThanOrEqual(r.monthly[m - 1].invested);
    expect(gainsOvertake(project({ monthly: 2500, years: 5, annualReturn: 12 }))).toBeNull();
  });
  it("milestones in order, first month each is reached", () => {
    const r = project({ monthly: 10000, years: 20, annualReturn: 12 });
    const ms = milestones(r);
    expect(ms.map((x) => x.amount)).toEqual([1e5, 5e5, 1e6, 2.5e6, 5e6]);
    for (const x of ms) { expect(r.monthly[x.m].value).toBeGreaterThanOrEqual(x.amount); expect(r.monthly[x.m - 1].value).toBeLessThan(x.amount); }
  });
  it("starting later costs more than the instalments skipped", () => {
    const d = delayCost({ monthly: 5000, years: 20, annualReturn: 12 }, 5);
    expect(d.investedLess).toBe(300000);
    expect(d.lost).toBeGreaterThan(d.investedLess * 4);
    expect(d.value).toBeCloseTo(project({ monthly: 5000, years: 15, annualReturn: 12 }).value, 6);
    expect(delayCost({ monthly: 5000, years: 3, annualReturn: 12 }, 5).value).toBe(0);
  });
  it("today's money", () => {
    expect(realValue(1e6, 6, 120)).toBeCloseTo(1e6 / Math.pow(1.06, 10), 8);
    expect(realValue(1e6, 0, 120)).toBe(1e6);
  });
});

describe("equity capital gains estimate", () => {
  it("splits long and short term by holding period and applies the exemption and cess", () => {
    const inp = { monthly: 2500, years: 10, annualReturn: 12 };
    const t = equityTax(inp);
    const r = project(inp);
    expect(t.longGain + t.shortGain).toBeCloseTo(r.gain, 6);
    // long term means held MORE than 12 months: the last 13 instalments (held 0..12 months, paid at month ends) are short term
    let st = 0; for (let k = 0; k <= 12; k++) st += 2500 * (Math.pow(1.01, k) - 1);
    expect(t.shortGain).toBeCloseTo(st, 6);
    const expected = ((t.longGain - 125000) * 0.125 + t.shortGain * 0.2) * 1.04;
    expect(t.tax).toBeCloseTo(expected, 6);
    expect(t.afterTax).toBeCloseTo(r.value - expected, 6);
    expect(EQUITY_TAX_2024).toEqual({ ltcgPct: 12.5, stcgPct: 20, exemption: 125000, cessPct: 4 });
  });
  it("no tax below the exemption", () => {
    const t = equityTax({ monthly: 1000, years: 3, annualReturn: 8 });
    expect(t.longGain).toBeLessThan(125000);
    expect(t.tax).toBeCloseTo(t.shortGain * 0.2 * 1.04, 8);
  });
});

describe("words and links", () => {
  it("formats rupees the Indian way", () => {
    expect(rupees(12345678.4)).toBe("₹1,23,45,678");
    expect(short(1.25e7)).toBe("₹1.25 Cr");
    expect(short(575097)).toBe("₹5.75 L");
    expect(short(250000000)).toBe("₹25 Cr");
    expect(duration(147)).toBe("12 years 3 months");
    expect(duration(11)).toBe("11 months");
  });
  it("round-trips the share link and refuses bad values", () => {
    const s = { ...DEFAULT_STATE, monthly: 7000, years: 18, annualReturn: 13.5, timing: "start" as const, stepKind: "pct" as const, stepValue: 7, tax: true };
    expect(fromQuery(new URLSearchParams(toQuery(s)))).toEqual(s);
    expect(toQuery(DEFAULT_STATE)).toBe("");
    const bad = fromQuery(new URLSearchParams("p=abc&y=500&r=-4&t=sideways&sk=<script>&inf=99"));
    expect(bad).toMatchObject({ monthly: 2500, years: 50, annualReturn: 0, timing: "end", stepKind: "none", inflation: 20 });
  });
});
