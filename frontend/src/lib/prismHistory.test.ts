import { describe, expect, it } from "vitest";
import { changeOver, emptyReason, modelChanges, toWeekly, valueOf, withValue, type HistPoint } from "./prismHistory";

const P = (day: string, final: number | null, o: Partial<HistPoint> = {}): HistPoint => ({ day, modelVersion: "3.6.10", final, label: "HEALTHY", status: "RATED", parts: { fundamental: 50, valuation: 60, quality: 70, risk: 80 }, shortTerm: null, longTerm: null, ...o });

describe("prism history helpers", () => {
  it("a day without a figure is skipped, never drawn as zero", () => {
    const pts = [P("2026-10-20", 60), P("2026-10-21", null, { shortTerm: 30 }), P("2026-10-22", 64)];
    expect(withValue(pts, "final").map((p) => p.day)).toEqual(["2026-10-20", "2026-10-22"]);
    expect(withValue(pts, "shortTerm").map((p) => p.day)).toEqual(["2026-10-21"]);
    expect(valueOf(pts[0], "risk")).toBe(80); expect(valueOf(pts[0], "fundamental")).toBe(50);
  });
  it("finds the days the model version changed, so a jump is not read as a changed business", () => {
    const pts = [P("2026-10-20", 60), P("2026-10-21", 62), P("2026-10-22", 70, { modelVersion: "3.6.11" }), P("2026-10-23", 71, { modelVersion: null }), P("2026-10-24", 72, { modelVersion: "3.6.11" })];
    expect(modelChanges(pts)).toEqual([{ day: "2026-10-22", from: "3.6.10", to: "3.6.11" }]);
    expect(modelChanges([P("2026-10-20", 60)])).toEqual([]);
  });
  it("says why there is no line: nothing recorded, one day, or a figure never worked out", () => {
    expect(emptyReason([], "final")).toMatch(/No days are recorded.*never estimated/);
    expect(emptyReason([P("2026-10-20", 60)], "final")).toMatch(/Only one day is recorded so far \(20 Oct 2026\).*at least two days/);
    expect(emptyReason([P("2026-10-20", 60), P("2026-10-21", 61)], "shortTerm")).toMatch(/not been worked out on any day recorded so far/);
    expect(emptyReason([P("2026-10-20", 60), P("2026-10-21", 61)], "final")).toBe("");
  });
  it("the change is between the first and the newest figure", () => {
    expect(changeOver([P("2026-10-20", 60), P("2026-10-21", null), P("2026-10-22", 64.4)], "final")).toEqual({ from: "2026-10-20", to: "2026-10-22", delta: 4.4 });
    expect(changeOver([P("2026-10-20", 60)], "final")).toBeNull();
  });
});

describe("weekly view", () => {
  it("keeps the last recorded day of each Monday-to-Sunday week, as recorded, in order", () => {
    const pts = [P("2026-10-26", 50), P("2026-10-30", 54), P("2026-10-27", 52), P("2026-11-02", 58), P("2026-11-03", 60)];   // given out of order
    expect(toWeekly(pts).map((p) => [p.day, p.final])).toEqual([["2026-10-30", 54], ["2026-11-03", 60]]);
  });
  it("a Sunday belongs to the week before it, and a week with one day keeps that day", () => {
    expect(toWeekly([P("2026-11-01", 41), P("2026-11-02", 43)]).map((p) => p.day)).toEqual(["2026-11-01", "2026-11-02"]);
    expect(toWeekly([])).toEqual([]);
  });
  it("a day with no figure is not turned into one", () => {
    const w = toWeekly([P("2026-10-26", 50), P("2026-10-30", null)]);
    expect(w).toHaveLength(1); expect(w[0].final).toBeNull();
  });
});
