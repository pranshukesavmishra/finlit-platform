import { describe, expect, it } from "vitest";
import { ptsChange } from "./profitChange";

describe("ptsChange", () => {
  it("shows a signed one-decimal difference in points", () => {
    expect(ptsChange(10.2, 16.3, "Mar 2022", "Mar 2026")).toMatchObject({ text: "+6.1 pts", dir: "up", reason: null });
    expect(ptsChange(16.3, 10.2, "Mar 2022", "Mar 2026")).toMatchObject({ text: "−6.1 pts", dir: "down" });
  });
  it("calls a move that rounds to nothing flat", () => {
    expect(ptsChange(12, 12.04, "a", "b")).toMatchObject({ text: "0.0 pts", dir: "flat" });
  });
  it("handles a zero start without treating it as missing", () => {
    expect(ptsChange(0, 3, "a", "b").text).toBe("+3.0 pts");
  });
  it("gives a dash and a reason when an end year is missing", () => {
    expect(ptsChange(null, 5, "Mar 2022", "Mar 2026")).toMatchObject({ text: "—", pts: null, reason: "No Mar 2022 figure" });
    expect(ptsChange(5, null, "Mar 2022", "Mar 2026").reason).toBe("No Mar 2026 figure");
    expect(ptsChange(null, null, "Mar 2022", "Mar 2026").reason).toBe("No Mar 2022 or Mar 2026 figure");
  });
});
