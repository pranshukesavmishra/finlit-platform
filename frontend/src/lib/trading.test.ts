import { describe, expect, it } from "vitest";
import { priceBand, leverageText, stageText } from "./trading";
import { closeness, describe as say, fixedTarget, fmtValue, METRICS, OP_LABEL } from "./alertCatalog";

describe("the day's price band", () => {
  const q = { price: 1500, upperCircuit: 1540, lowerCircuit: 1260 };
  it("is shown only with both limits, and marks which end the price is on", () => {
    expect(priceBand(q)).toEqual({ upper: 1540, lower: 1260, at: null });
    expect(priceBand({ ...q, price: 1540 })?.at).toBe("upper");
    expect(priceBand({ ...q, price: 1260 })?.at).toBe("lower");
    expect(priceBand({ ...q, price: 1539.95 })?.at).toBeNull();
  });
  it("is absent when a limit is missing or makes no sense", () => {
    for (const bad of [{ price: 1 }, { ...q, upperCircuit: null }, { ...q, lowerCircuit: undefined }, { ...q, lowerCircuit: 1540 }, { ...q, lowerCircuit: 0 }, null, undefined]) expect(priceBand(bad)).toBeNull();
  });
});

describe("wording", () => {
  it("writes leverage without a trailing .0", () => {
    expect(leverageText(4.5)).toBe("4.5×");
    expect(leverageText(2)).toBe("2×");
    expect(leverageText(3.3)).toBe("3.3×");
  });
  it("keeps the exchange's stage text", () => {
    expect(stageText("II")).toBe("stage II");
    expect(stageText("4")).toBe("stage 4");
    expect(stageText("ASM LT Stage 2")).toBe("ASM LT Stage 2");
    expect(stageText(null)).toBeNull();
    expect(stageText("  ")).toBeNull();
  });
});

describe("the circuit alert", () => {
  it("is a live, free alert with a fixed target and neutral words", () => {
    expect(METRICS.circuit).toMatchObject({ live: true, tier: "basic", ops: ["above", "below"] });
    expect(fixedTarget("circuit", "above")).toBe(1);
    expect(fixedTarget("circuit", "below")).toBe(-1);
    expect(fixedTarget("price", "above")).toBeNull();
    const text = [say({ metric: "circuit", op: "above", value: 1 }), say({ metric: "circuit", op: "below", value: -1 }), OP_LABEL("circuit", "above"), METRICS.circuit.hint, fmtValue("circuit", 1), fmtValue("circuit", -1), fmtValue("circuit", 0)].join(" ").toLowerCase();
    expect(text).toContain("upper circuit");
    expect(text).toContain("lower circuit");
    for (const w of ["buy", "sell", "opportunity", "signal"]) expect(text).not.toContain(w);
  });
  it("shows no progress bar for it", () => {
    expect(closeness({ metric: "circuit", op: "above", value: 1, lastValue: 0 })).toBeNull();
    expect(closeness({ metric: "circuit", op: "above", value: 1, lastValue: 1 })).toBe(100);
  });
});
