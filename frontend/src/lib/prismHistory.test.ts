import { describe, expect, it } from "vitest";
import { changeOver, emptyReason, modelChanges, valueOf, withValue, type HistPoint } from "./prismHistory";

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
