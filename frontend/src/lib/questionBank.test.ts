import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { bankSuggestions } from "./questionBank";

const bank = JSON.parse(readFileSync(new URL("../../../site-api/backend/question_bank.json", import.meta.url), "utf8")) as { questions: { id: string; text: string }[] };
const BANNED = /\b(buy|sell|hold|reduce|avoid|accumulate|target|best)\b/i;

describe("the assistant's suggested bank questions", () => {
  it("a company page offers five of the bank's company questions with that company filled in", () => {
    const s = bankSuggestions("/stocks/reliance");
    expect(s).toHaveLength(5);
    expect(s[0].text).toBe("What is RELIANCE's YoY and QoQ revenue growth in the latest quarter?");
    expect(s.every((x) => !x.text.includes("{"))).toBe(true);
    expect(bankSuggestions("/stocks/M&M/")[0].text).toContain("M&M");
  });
  it("only a company page offers them", () => {
    for (const p of ["/", "/funds", "/screener", "/stocks", "/stocks/TCS/extra", "/score-screener"]) expect(bankSuggestions(p)).toEqual([]);
  });
  it("every suggestion is a question of the bank with the bank's own words (never reworded), and none advises", () => {
    const by = new Map(bank.questions.map((q) => [q.id, q.text]));
    for (const s of bankSuggestions("/stocks/TCS", 99)) {
      const original = by.get(s.id)!;
      expect(original, s.id).toBeTruthy();
      expect(s.text).toBe(original.replace(/\{company\}/g, "TCS").replace(/\{n\}/g, "5"));
      expect(s.text).not.toMatch(BANNED);
    }
  });
});
