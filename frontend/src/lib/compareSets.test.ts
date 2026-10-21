import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_KEYS, MAX_PICK, STARTERS, bestWorst, cleanKeys, decodeKeys, encodeKeys, sets } from "./compareSets";

describe("best and worst, aware of direction", () => {
  it("higher is better", () => expect(bestWorst({ A: 10, B: 25, C: 5 }, "higher")).toEqual({ best: ["B"], worst: ["C"] }));
  it("lower is better", () => expect(bestWorst({ A: 10, B: 25, C: 5 }, "lower")).toEqual({ best: ["C"], worst: ["B"] }));
  it("negative net debt (cash) is the best when lower is better", () => expect(bestWorst({ A: -300, B: 800 }, "lower")).toEqual({ best: ["A"], worst: ["B"] }));
  it("never marks a measure with no direction", () => expect(bestWorst({ A: 1, B: 2 }, "none")).toEqual({ best: [], worst: [] }));
  it("needs two known values; missing ones are ignored, never counted as zero", () => {
    expect(bestWorst({ A: 3, B: null }, "higher")).toEqual({ best: [], worst: [] });
    expect(bestWorst({ A: 3, B: null, C: 1 }, "higher")).toEqual({ best: ["A"], worst: ["C"] });
  });
  it("equal values are not a win", () => expect(bestWorst({ A: 4, B: 4 }, "higher")).toEqual({ best: [], worst: [] }));
  it("ties share the mark", () => expect(bestWorst({ A: 9, B: 9, C: 1 }, "higher")).toEqual({ best: ["A", "B"], worst: ["C"] }));
});

describe("link and clean-up", () => {
  it("round trips and drops bad keys, repeats and unknowns", () => {
    expect(decodeKeys(encodeKeys(["pe", "roe", "ev_cfo"]))).toEqual(["pe", "roe", "ev_cfo"]);
    expect(decodeKeys("pe,PE,<script>,roe,pe,x,nope", (k) => k !== "nope")).toEqual(["pe", "roe"]);
    expect(decodeKeys(null)).toEqual([]);
    expect(cleanKeys(Array.from({ length: 200 }, (_, i) => "k" + i)).length).toBe(MAX_PICK);
  });
  it("defaults and starters are valid keys", () => {
    for (const k of [...DEFAULT_KEYS, ...STARTERS.flatMap((s) => s.keys)]) expect(k).toMatch(/^[a-z0-9_]{2,40}$/);
    expect(new Set(DEFAULT_KEYS).size).toBe(DEFAULT_KEYS.length);
  });
});

describe("saved sets", () => {
  beforeEach(() => sets.replace([]));
  it("saves, replaces by name ignoring case, removes", () => {
    sets.save("Mine", ["pe", "roe"]); sets.save("mine", ["pb"]);
    expect(sets.get()).toEqual([{ name: "mine", keys: ["pb"] }]);
    sets.remove("MINE"); expect(sets.get()).toEqual([]);
  });
  it("ignores an empty name or no measures", () => { sets.save("  ", ["pe"]); sets.save("x", []); expect(sets.get()).toEqual([]); });
  it("keeps at most the plan's number", () => { for (let i = 0; i < 5; i++) sets.save("s" + i, ["pe"], 3); expect(sets.get().map((s) => s.name)).toEqual(["s4", "s3", "s2"]); });
  it("merge: account copy first, then local-only, up to the limit", () => {
    sets.replace([{ name: "A", keys: ["pe"] }, { name: "B", keys: ["pb"] }]);
    expect(sets.merge([{ name: "a", keys: ["roe"] }], 10)).toEqual([{ name: "a", keys: ["roe"] }, { name: "B", keys: ["pb"] }]);
    expect(sets.merge([{ name: "a", keys: ["roe"] }], 1)).toHaveLength(1);
  });
});
