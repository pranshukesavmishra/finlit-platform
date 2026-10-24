import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { monthYear, ordinal, pts, rankStory, relativeSentence, tone, type LeadRun } from "./leadership";

const run = (date: string, label: LeadRun["label"], rank = 5): LeadRun => ({ date, rank, ranked: 13, label, direction: null, rel52: 0.01, rel52Market: 0.02 });

describe("leadership wording", () => {
  it("formats percentage points with a real minus sign and one decimal", () => {
    expect(pts(-0.072)).toBe("−7.2");
    expect(pts(0.012)).toBe("+1.2");
    expect(pts(0)).toBe("0.0");
    expect(pts(-0.0004)).toBe("0.0");
    expect(pts(null)).toBe("—");
    expect(pts(0.05, false)).toBe("5.0");
  });
  it("orders numbers", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101, 111].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "111th"]);
  });
  it("tones figures", () => { expect([tone(0.02), tone(-0.02), tone(0), tone(null)]).toEqual(["up", "down", "flat", "flat"]); });
  it("tells the rank story in words", () => {
    const rows = [run("2022-10-14", "leader"), run("2022-11-11", "leader"), run("2022-12-09", "in_line")];
    expect(rankStory("Persistent", rows)).toBe("Persistent has been in the leader zone in 2 of 3 checks since Oct 2022");
    expect(rankStory("X", [run("2023-01-06", "in_line")])).toBe("X has been in the middle of its peers in 1 of 1 checks since Jan 2023");
    expect(rankStory("X", [])).toBe("");
    expect(monthYear("2026-10-23")).toBe("Oct 2026");
  });
  it("states the conclusion of the relative-strength chart", () => {
    expect(relativeSentence("TCS", "Nifty IT", 107.3, "3 years")).toBe("Over 3 years, TCS has outperformed Nifty IT by 7.3 points.");
    expect(relativeSentence("TCS", "Nifty IT", 92.0, "1 year")).toBe("Over 1 year, TCS has been behind Nifty IT by 8.0 points.");
    expect(relativeSentence("TCS", "Nifty IT", null, "1 year")).toContain("not enough data");
  });
});

describe("copy rules", () => {
  // The spec forbids buy / sell / avoid wording anywhere the label appears. Comments are not shown to anyone, so they are removed before the scan.
  const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
  for (const f of ["../stock/Leadership.tsx", "../pages/LeadershipLabel.tsx", "./leadership.ts"]) {
    it(`${f} never says buy, sell or avoid`, () => {
      const text = strip(readFileSync(new URL(f, import.meta.url), "utf8"));
      expect(text.match(/\b(buy|sell|avoid|strong buy)\b/gi)).toBeNull();
    });
  }
});
