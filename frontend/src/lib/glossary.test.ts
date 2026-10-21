import { describe, expect, it } from "vitest";
import { LETTERS, TERMS, TOPICS, norm, search } from "./glossary";

describe("glossary", () => {
  it("has the 313 terms, each complete", () => {
    expect(TERMS.length).toBe(313);
    TERMS.forEach((t) => expect(t.meaning && t.why && t.how && TOPICS.includes(t.topic) && LETTERS.includes(t.letter)).toBeTruthy());
  });
  it("ignores spaces and punctuation: EV / CFO finds EV/CFO", () => {
    expect(norm("EV / CFO")).toBe("evcfo");
    expect(search("EV / CFO")[0].id).toBe("ev-sales-and-ev-cfo");
  });
  it("finds a term by its short name and tolerates a typo", () => {
    expect(search("P/E")[0].term).toMatch(/Price-to-earnings/);
    expect(search("volatilty").some((t) => t.term === "Volatility")).toBe(true);
  });
});
