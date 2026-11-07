import { describe, expect, it } from "vitest";
import { coverTicks } from "./RoeLines";

describe("coverTicks", () => {
  it("never ends below the highest value, so no bar or number stands above the top gridline", () => {
    for (const [lo, hi] of [[0, 11.1], [0, 10.2], [0, 1], [-3, 7.4], [0, 99.5], [0, 0.37]] as const) {
      const t = coverTicks(lo, hi);
      expect(t[t.length - 1], `${lo}..${hi}`).toBeGreaterThanOrEqual(hi);
      expect(t[0]).toBeLessThanOrEqual(lo);
    }
  });
  it("keeps equal steps", () => {
    const t = coverTicks(0, 11.1), d = t[1] - t[0];
    t.slice(1).forEach((v, i) => expect(Math.abs(v - t[i] - d)).toBeLessThan(1e-9));
  });
});
