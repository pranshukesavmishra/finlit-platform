import { describe, expect, it } from "vitest";
import { DEFAULT_WEIGHTS, HORIZONS, PARAM_LABELS, isDefault, rebalance, signedPct, totalOf, type Horizon, type Kind } from "./outlook";

describe("rebalance", () => {
  it("keeps the total at exactly 100 for every slider move", () => {
    for (const kind of ["profit", "revenue"] as const) {
      let w = { ...DEFAULT_WEIGHTS[kind].mid };
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
  it("every default column adds to 100 and names every input, per horizon", () => {
    for (const kind of ["profit", "revenue"] as Kind[]) for (const h of HORIZONS) {
      const w = DEFAULT_WEIGHTS[kind][h.key];
      expect(totalOf(w)).toBe(100);
      expect(Object.keys(w)).toEqual(Object.keys(PARAM_LABELS[kind]));
      expect(isDefault(kind, h.key, w)).toBe(true);
    }
    expect(isDefault("profit", "mid", rebalance(DEFAULT_WEIGHTS.profit.mid, "co_1y", 30))).toBe(false);
    expect(isDefault("profit", "short", DEFAULT_WEIGHTS.profit.mid)).toBe(false);
  });
  it("matches the team's table", () => {
    expect(DEFAULT_WEIGHTS.revenue.short).toEqual({ co_1y: 50, co_3y: 10, co_5y: 5, sec_1y: 25, sec_3y: 5, sec_5y: 5 });
    expect(DEFAULT_WEIGHTS.profit.long.margin).toBe(10);
    expect(HORIZONS.map((h) => h.years)).toEqual([1, 3, 5]);
    expect(Object.keys(DEFAULT_WEIGHTS.profit) as Horizon[]).toEqual(["short", "mid", "long"]);
  });
});

describe("formats", () => {
  it("signs percentages with a true minus", () => {
    expect(signedPct(4.24)).toBe("+4.2%"); expect(signedPct(-6.4)).toBe("−6.4%"); expect(signedPct(0)).toBe("0.0%"); expect(signedPct(12.345, 2)).toBe("+12.35%");
  });
});
