import { describe, expect, it } from "vitest";
import { badgeFor, badgeView, dotLabel, industryText, marketCapLine, partHint, scoreBand, goldDots, type PrismInput } from "./scoreBands";

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

describe("Gold header dots (FinLit Prism)", () => {
  const rep = (over: Record<string, unknown> = {}): PrismInput => ({ kind: "report", final: 61, word: "Average", status: "RATED", parts: { fundamental: 68.8, valuation: 42.4, quality: 73.2, risk: 49.9 },
    short: { score: 1, rating: "Hold" }, long: { score: 63, rating: "Strong Buy" }, ...over } as PrismInput);
  it("six dots: four fundamental then two technical, letters F V Q R S L", () => {
    const d = goldDots(rep())!;
    expect(d.map((x) => x.letter).join("")).toBe("FVQRSL");
    expect(d.map((x) => x.group)).toEqual(["fund", "fund", "fund", "fund", "tech", "tech"]);
  });
  it("0-100 dots use the shared band rule and the Prism words", () => {
    const d = goldDots(rep())!;
    expect(d[0]).toMatchObject({ band: "mid", label: "Fundamentals 69: orange, healthy" });
    expect(d[1]).toMatchObject({ band: "lo", label: "Valuation 42: red, weak" });
    expect(d[2]).toMatchObject({ band: "hi", label: "Quality 73: green, healthy" });
    expect(d[3].band).toBe("lo");
  });
  it("technical dots use the trend bands and descriptive words, never the model's own", () => {
    const d = goldDots(rep())!;
    expect(d[4]).toMatchObject({ band: "mid", label: "Short-term technical +1: orange, neutral" });
    expect(d[5]).toMatchObject({ band: "hi", label: "Long-term technical +63: green, strongly positive" });
    expect(goldDots(rep({ short: { score: -30, rating: "Reduce" } }))![4]).toMatchObject({ band: "lo", label: "Short-term technical −30: red, negative" });
    expect(d.map((x) => x.label).join(" ")).not.toMatch(/\b(buy|sell|hold|reduce)\b/i);
  });
  it("a missing part or technical score is grey", () => {
    const d = goldDots(rep({ parts: { fundamental: 70 }, short: null }))!;
    expect(d[1]).toMatchObject({ band: "na", label: "Valuation: grey, not available" });
    expect(d[4]).toMatchObject({ band: "na", label: "Short-term technical: grey, not available" });
  });
  it("no stored rating: six grey dots; NOT RATED: grey with the report's reason; loading: nothing", () => {
    expect(goldDots({ kind: "none" })!.every((x) => x.band === "na" && x.label.endsWith("not rated yet"))).toBe(true);
    const n = goldDots(rep({ status: "NOT RATED", final: null, reason: "Industry not yet mapped to a model group." }))!;
    expect(n).toHaveLength(6); expect(n.every((x) => x.band === "na")).toBe(true);
    expect(n[0].label).toBe("Fundamentals: grey, not rated: Industry not yet mapped to a model group");
    expect(goldDots(rep({ status: "NOT RATED", reason: null }))![2].label).toBe("Quality: grey, not rated");
    for (const k of ["loading", "hidden", "locked"] as const) expect(goldDots({ kind: k })).toBeNull();
  });
});
