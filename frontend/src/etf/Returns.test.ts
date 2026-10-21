import { describe, expect, it } from "vitest";
import { bigMove } from "./Returns";

describe("the three return figures", () => {
  it("a gain has an up arrow and a plus, a loss a down arrow and a real minus, so colour is never the only cue", () => {
    expect(bigMove(12.345)).toBe("▲ +12.35%");
    expect(bigMove(-5.6)).toBe("▼ −5.60%");
    expect(bigMove(0)).toBe("0.00%");
    expect(bigMove(-0.004)).toMatch(/^▼ −0\.00%$/);
  });
  it("groups digits the Indian way", () => {
    expect(bigMove(1234.5)).toBe("▲ +1,234.50%");
  });
});
