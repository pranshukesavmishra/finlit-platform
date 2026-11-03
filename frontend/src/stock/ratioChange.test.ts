import { describe, expect, it } from "vitest";
import { ratioChange } from "./Sections3";
describe("ratio history change", () => {
  it("is in the ratio's own unit, with a real minus sign", () => {
    expect(ratioChange("days", 50, 19).text).toBe("+31 days");
    expect(ratioChange("%", 8.93, 8.6).text).toBe("+0.33 pts");
    expect(ratioChange("x", 1.1, 1.2).text).toBe("−0.10×");
  });
});
