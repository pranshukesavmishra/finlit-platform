import { describe, expect, it } from "vitest";
import { badgeFor, badgeView, dotLabel, industryText, marketCapLine, partHint, scoreBand } from "./scoreBands";

describe("score colour bands", () => {
  it("green from 70, orange 50 to 69, red under 50, grey without a score", () => {
    expect([0, 49.9, 50, 69.9, 70, 100].map(scoreBand)).toEqual(["lo", "lo", "mid", "mid", "hi", "hi"]);
    expect([null, undefined, NaN].map(scoreBand)).toEqual(["na", "na", "na"]);
  });
  it("words the dot tooltip", () => {
    expect(dotLabel("Quality", 76, "Healthy")).toBe("Quality 76: green, healthy");
    expect(dotLabel("Growth", 44, "Watch")).toBe("Growth 44: red, watch");
    expect(dotLabel("Technical", null)).toBe("Technical: grey, not enough data");
  });
});
describe("plan badge", () => {
  const basic = { overall: 72, word: "Healthy" };
  it("chooses by plan", () => {
    expect(["basic", "silver", "gold"].map((p) => badgeFor(p as never))).toEqual(["none", "basic", "prism"]);
    expect(badgeFor("basic", true)).toBe("prism");
  });
  it("Silver sees only the basic score, never Prism", () => {
    expect(badgeView("silver", false, basic, { kind: "report", final: 80, word: "Strong", status: "RATED" })).toEqual({ kind: "basic", score: 72, word: "Healthy", band: "hi" });
  });
  it("Gold sees only Prism, never the basic score", () => {
    expect(badgeView("gold", false, basic, { kind: "report", final: 54.5, word: "Average", status: "RATED" })).toEqual({ kind: "prism", score: 54.5, word: "Average", band: "mid", provisional: false });
    expect(badgeView("gold", false, basic, { kind: "none" })).toEqual({ kind: "prism-none" });
    expect(badgeView("gold", false, basic, { kind: "report", final: null, word: "Not rated", status: "NOT RATED" })).toEqual({ kind: "prism-none" });
    expect(badgeView("gold", false, basic, { kind: "loading" })).toEqual({ kind: "none" });
  });
  it("Basic sees no badge", () => expect(badgeView("basic", false, basic, { kind: "none" })).toEqual({ kind: "none" }));
});
describe("header facts", () => {
  it("formats market cap in Indian units and joins industry", () => {
    expect(marketCapLine(123456)).toBe("Market cap ₹1,23,456 Cr · Large cap");
    expect(marketCapLine(null)).toBeNull();
    expect(industryText({ industry: "Transport Services", subIndustry: "Transport Services", sector: "X" })).toBe("Transport Services");
    expect(industryText({ industry: null, subIndustry: null, sector: "Energy" })).toBe("Energy");
  });
  it("says higher is better for the four fundamental parts, Risk explained", () => {
    expect(partHint("risk")!.long).toContain("lower risk");
    expect(partHint("valuation")!.short).toBe("Higher is better");
    expect(partHint("technical")).toBeNull();
  });
});
