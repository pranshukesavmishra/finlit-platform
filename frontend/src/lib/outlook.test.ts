import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, isDefault, outlookBand, outlookWord, rangePos, rebalance, signedPct, totalOf } from "./outlook";

describe("rebalance", () => {
  it("keeps the total at exactly 100 for every slider move", () => {
    for (const kind of ["profit", "revenue"] as const) {
      let w = { ...DEFAULT_WEIGHTS[kind] };
      const letters = Object.keys(w);
      for (let n = 0; n < 200; n++) {
        const l = letters[(n * 7) % letters.length];
        w = rebalance(w, l, ((n * 37) % 1001) / 10);
        expect(totalOf(w)).toBe(100);
        expect(Object.values(w).every((x) => x >= 0 && x <= 100)).toBe(true);
      }
    }
  });
  it("shares the rest in proportion to the other groups", () => {
    const w = rebalance({ A: 50, B: 30, C: 20 }, "A", 60);
    expect(w).toEqual({ A: 60, B: 24, C: 16 });
  });
  it("sets one group to 100 and the rest to 0, and shares equally when the others hold nothing", () => {
    expect(rebalance({ A: 50, B: 30, C: 20 }, "B", 100)).toEqual({ A: 0, B: 100, C: 0 });
    expect(rebalance({ A: 100, B: 0, C: 0 }, "A", 40)).toEqual({ A: 40, B: 30, C: 30 });
  });
  it("clamps junk and ignores unknown groups", () => {
    expect(totalOf(rebalance({ A: 50, B: 50 }, "A", 250))).toBe(100);
    expect(rebalance({ A: 50, B: 50 }, "A", NaN)).toEqual({ A: 0, B: 100 });
    expect(rebalance({ A: 50, B: 50 }, "Z", 10)).toEqual({ A: 50, B: 50 });
  });
  it("defaults add to 100", () => {
    expect(totalOf(DEFAULT_WEIGHTS.profit)).toBe(100);
    expect(totalOf(DEFAULT_WEIGHTS.revenue)).toBe(100);
    expect(isDefault("profit", DEFAULT_WEIGHTS.profit)).toBe(true);
    expect(isDefault("profit", rebalance(DEFAULT_WEIGHTS.profit, "A", 30))).toBe(false);
  });
});

describe("bands and range helpers", () => {
  it("follows the site rule: green from 70, orange 50-69, red under 50", () => {
    expect(outlookBand(70)).toBe("hi"); expect(outlookBand(69.9)).toBe("mid"); expect(outlookBand(50)).toBe("mid"); expect(outlookBand(49.9)).toBe("lo"); expect(outlookBand(null)).toBe("na");
    expect(outlookWord(80)).toBe("Supportive"); expect(outlookWord(55)).toBe("Mixed"); expect(outlookWord(10)).toBe("Subdued"); expect(outlookWord(null)).toBe("Not available");
  });
  it("places and formats", () => {
    expect(rangePos(0, -10, 10)).toBe(50); expect(rangePos(99, -10, 10)).toBe(100); expect(rangePos(1, 1, 1)).toBe(50);
    expect(signedPct(4.24)).toBe("+4.2%"); expect(signedPct(-6.4)).toBe("−6.4%");
  });
});
