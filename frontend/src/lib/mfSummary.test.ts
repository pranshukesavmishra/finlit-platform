import { describe, expect, it } from "vitest";
import type { FundRow } from "./mf";
import { SORT_PILLS, summarise, tintOf } from "./mfSummary";

const f = (o: Partial<FundRow>): FundRow => ({ code: 1, name: "F", amc: "A", category: "c", plan: "Direct", option: "Growth", optionClass: "Growth", nav: 10, navDate: "2026-10-23", change: 0, active: true, r1y: null, r5y: null, noReturns: null, ...o });
describe("summarise", () => {
  it("counts risers and fallers and takes medians over the figures that exist", () => {
    const s = summarise([f({ r1y: 10, r3y: 12 }), f({ r1y: -4 }), f({ r1y: 2, aum: 500, ter: 0.5 }), f({ r1y: null })]);
    expect(s.n).toBe(4); expect(s.withR1y).toBe(3); expect(s.up1y).toBe(2); expect(s.down1y).toBe(1); expect(s.median1y).toBe(2); expect(s.median3y).toBe(12);
    expect(s.largestAum).toEqual({ name: "F", aum: 500 }); expect(s.medianTer).toBe(0.5); expect(s.extrasLoading).toBe(false);
  });
  it("says the extras are still loading only when none of them is on any scheme", () => {
    expect(summarise([f({ r1y: 1 }), f({ r1y: 2 })]).extrasLoading).toBe(true);
    expect(summarise([f({ sip3y: 11 })]).extrasLoading).toBe(false); expect(summarise([]).extrasLoading).toBe(false);
    expect(summarise([f({})]).median1y).toBeNull();
  });
  it("sorts only by columns the table has, in neutral wording", () => {
    for (const p of SORT_PILLS) expect(p.label).not.toMatch(/best|top|recommend/i);
    expect(SORT_PILLS.find((p) => p.key === "ter")!.dir).toBe("asc");
  });
  it("tints in proportion to the column's largest figure", () => {
    expect(tintOf(5, 10)).toEqual({ tone: "pos", k: 0.5 }); expect(tintOf(-20, 10)).toEqual({ tone: "neg", k: 1 }); expect(tintOf(0, 10)).toBeNull(); expect(tintOf(null, 10)).toBeNull(); expect(tintOf(3, 0)).toBeNull();
  });
});
