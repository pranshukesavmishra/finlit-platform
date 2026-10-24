import { describe, expect, it } from "vitest";
import {
  acceptCompletion, addCondition, applyFix, basketNameProblem, cleanNumber, completionAt, conditionText, draftProblem, leftOutLines, nameSet, quarterLabel, queryPreview, rankRatios,
  segments, type Problem, type Ratio,
} from "./query";

const r = (key: string, label: string, unit: string, names: string[] = []): Ratio => ({
  key, label, unit, unitLabel: unit, tier: "basic", locked: false, digits: 1, group: "g", groupLabel: "G", better: "none", names: [label, ...names], definition: "", example: "", stats: null,
});
const RATIOS = [r("pe", "P/E Ratio", "x", ["P/E", "PE", "Price to earnings"]), r("roe", "Return on equity", "%", ["ROE"]), r("market_cap", "Market cap", "Cr", ["mcap", "Market capitalization"]),
  r("div_paying", "Pays a dividend", "flag"), r("debt_to_equity", "Debt to equity", "x", ["D/E"])];
const names = nameSet(RATIOS);
const at = (t: string, c = t.length) => completionAt(t, c, names);

describe("fixes", () => {
  it("replaces a range and puts the caret after it", () => {
    expect(applyFix("Foo > 5", { start: 0, end: 3, text: "Return on equity" })).toEqual({ text: "Return on equity > 5", caret: 16 });
  });
  it("removing a dangling AND leaves clean text", () => {
    expect(applyFix("ROE > 15 AND", { start: 9, end: 12, text: "" }).text).toBe("ROE > 15");
    expect(applyFix("ROE > 15 AND\nPE < 5", { start: 9, end: 12, text: "" }).text).toBe("ROE > 15\nPE < 5");
  });
  it("inserts a missing AND", () => { expect(applyFix("PE < 15 ROE > 10", { start: 8, end: 8, text: "AND " }).text).toBe("PE < 15 AND ROE > 10"); });
});

const P = (start: number, end: number, severity: "error" | "warning" = "error"): Problem => ({ code: "x", severity, message: "m", start, end, line: 1, col: 1, text: "", fixes: [] });
describe("underline segments", () => {
  it("cuts the text around the problems", () => {
    const s = segments("Foo > 5 AND Bar < 2", [P(0, 3), P(12, 15)]);
    expect(s.map((x) => x.text)).toEqual(["Foo", " > 5 AND ", "Bar", " < 2"]);
    expect(s.filter((x) => x.problem).length).toBe(2);
  });
  it("marks the next character for a zero-width problem and the last one at the end", () => {
    expect(segments("PE < 15 ROE", [P(8, 8)]).map((x) => x.text)).toEqual(["PE < 15 ", "R", "OE"]);
    expect(segments("ROE >", [P(5, 5)]).map((x) => x.text)).toEqual(["ROE ", ">"]);
  });
  it("lets the first of two overlapping marks win and keeps all the text", () => {
    const t = "Market cap > 5%";
    const s = segments(t, [P(0, 10), P(5, 8, "warning"), P(13, 15)]);
    expect(s.map((x) => x.text).join("")).toBe(t);
    expect(s.filter((x) => x.problem).length).toBe(2);
  });
  it("is just the text when all is well", () => { expect(segments("ROE > 5", [])).toEqual([{ text: "ROE > 5" }]); });
});

describe("autocomplete", () => {
  it("suggests ratios for the word being typed", () => {
    expect(at("ROE > 15\nmar")).toMatchObject({ kind: "metric", prefix: "mar", start: 9 });
    expect(at("ROE > 15 AND d/")).toMatchObject({ kind: "metric", prefix: "d/" });
    expect(at("(PE < 5 OR ro")).toMatchObject({ kind: "metric", prefix: "ro" });
    expect(at("ROE > mc")).toMatchObject({ kind: "metric", prefix: "mc" });
  });
  it("offers comparisons after a finished ratio name and AND / OR after a finished value", () => {
    expect(at("ROE ").kind).toBe("operator");
    expect(at("Return on equity ").kind).toBe("operator");
    expect(at("P/E ").kind).toBe("operator");
    expect(at("ROE > 15 ").kind).toBe("connector");
    expect(at("Market cap > 500 Cr ").kind).toBe("connector");
  });
  it("stays quiet while a number is typed or nothing has been typed", () => {
    expect(at("ROE > 1").kind).toBe("none");
    expect(at("ROE > 15").kind).toBe("none");
    expect(at("").kind).toBe("none");
    expect(at("ROE > 15 AND ").kind).toBe("none");
    expect(at("12").kind).toBe("none");
  });
  it("completes at the caret, not at the end", () => {
    const t = "mar > 5\nROE < 2";
    expect(at(t, 3)).toMatchObject({ kind: "metric", prefix: "mar", start: 0, end: 3 });
  });
  it("ranks by name, label and short form", () => {
    expect(rankRatios(RATIOS, "mcap")[0].key).toBe("market_cap");
    expect(rankRatios(RATIOS, "p/e")[0].key).toBe("pe");
    expect(rankRatios(RATIOS, "roe")[0].key).toBe("roe");
    expect(rankRatios(RATIOS, "div")[0].key).toBe("div_paying");
    expect(rankRatios(RATIOS, "zzzzzz")).toEqual([]);
    expect(rankRatios(RATIOS, "", 3)).toHaveLength(3);
  });
  it("puts the chosen name into the text", () => {
    const c = at("ROE > 15 AND mar");
    expect(acceptCompletion("ROE > 15 AND mar", c, "Market cap")).toEqual({ text: "ROE > 15 AND Market cap ", caret: 24 });
    expect(acceptCompletion("ROE ", at("ROE "), ">")).toEqual({ text: "ROE > ", caret: 6 });
  });
});

describe("the Add a condition helper", () => {
  it("cleans numbers the way people type them", () => {
    expect(cleanNumber("1,00,000")).toBe("100000");
    expect(cleanNumber(" 12.5 ")).toBe("12.5");
    expect(cleanNumber("₹ 2,000")).toBe("2000");
    expect(cleanNumber("15%")).toBe("15");
    expect(cleanNumber("500 Cr")).toBe("500");
    expect(cleanNumber("abc")).toBeNull();
    expect(cleanNumber("1.2.3")).toBeNull();
    expect(cleanNumber("")).toBeNull();
  });
  it("writes the text with the right unit", () => {
    expect(conditionText({ ratio: RATIOS[1], op: ">", value: "15" })).toBe("Return on equity > 15%");
    expect(conditionText({ ratio: RATIOS[2], op: ">=", value: "1,000" })).toBe("Market cap >= 1000 Cr");
    expect(conditionText({ ratio: RATIOS[0], op: "<", value: "15" })).toBe("P/E Ratio < 15");
    expect(conditionText({ ratio: RATIOS[3], op: ">", value: "", yes: false })).toBe("Pays a dividend = no");
    expect(conditionText({ ratio: null, op: ">", value: "1" })).toBe("");
  });
  it("says what is wrong instead of writing bad text", () => {
    expect(draftProblem({ ratio: null, op: ">", value: "1" })).toMatch(/Pick a ratio/);
    expect(draftProblem({ ratio: RATIOS[0], op: ">", value: "" })).toMatch(/Type a number/);
    expect(draftProblem({ ratio: RATIOS[0], op: ">", value: "ten" })).toMatch(/not a number/);
    expect(draftProblem({ ratio: RATIOS[1], op: ">", value: "15 Cr" })).toMatch(/percentage/);
    expect(draftProblem({ ratio: RATIOS[3], op: "=", value: "" })).toBeNull();
    expect(draftProblem({ ratio: RATIOS[1], op: ">", value: "15" })).toBeNull();
  });
  it("adds on a new line, or joins with OR", () => {
    expect(addCondition("", "ROE > 15%")).toEqual({ text: "ROE > 15%", caret: 9 });
    expect(addCondition("PE < 15\n\n", "ROE > 15%").text).toBe("PE < 15\nROE > 15%");
    expect(addCondition("PE < 15", "ROE > 15%", "OR").text).toBe("PE < 15 OR ROE > 15%");
  });
});

describe("words for the page", () => {
  it("formats the quarter", () => { expect(quarterLabel(20260930)).toBe("30 Sept 2026".replace("Sept", "Sep")); expect(quarterLabel(null)).toBe(""); });
  it("says who was left out and why", () => {
    const lines = leftOutLines([{ key: "pe", label: "P/E Ratio", known: 3000, missing: 2800, leftOut: 1200 }, { key: "roe", label: "ROE", known: 5800, missing: 0, leftOut: 0 }], 5800);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain("P/E Ratio is not known for 2,800 of 5,800 companies");
    expect(lines[0]).toContain("1,200");
  });
  it("checks basket names", () => {
    expect(basketNameProblem("  ", [])).toMatch(/name/);
    expect(basketNameProblem("Value", ["value"])).toMatch(/already/);
    expect(basketNameProblem("Value", ["Value"], "Value")).toBeNull();
    expect(basketNameProblem("x".repeat(81), [])).toMatch(/80/);
    expect(basketNameProblem("Growth", ["Value"])).toBeNull();
  });
  it("previews a query on one line", () => {
    expect(queryPreview("ROE > 15\nPE < 10")).toBe("ROE > 15  ·  PE < 10");
    expect(queryPreview("x".repeat(300)).length).toBe(140);
  });
});
