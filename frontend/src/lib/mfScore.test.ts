import { describe, expect, it } from "vitest";
import { FLAG_TEXT, GROUP_WEIGHTS, MF_SCORE_COMPLIANCE, PILLAR_HELP, STATE_TEXT, STATUS_TEXT, confidenceText, filledText, rankText } from "./mfScore";
import { MfScoreMethodPage } from "../pages/MfScoreMethod";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const BANNED = /\b(buy|sell|hold|recommended|recommend|best[- ]to[- ]buy|should|invest in)\b/i;

describe("Mutual Fund Health Score wording", () => {
  it("has the exact compliance line", () => {
    expect(MF_SCORE_COMPLIANCE).toBe("Describes the fund's health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice.");
  });
  it("uses no advice words in any fixed text", () => {
    const all = [...Object.values(PILLAR_HELP), ...Object.values(STATUS_TEXT), ...Object.values(FLAG_TEXT), ...Object.values(STATE_TEXT), ...GROUP_WEIGHTS.map((g) => g.name)];
    for (const t of all) expect(t).not.toMatch(BANNED);
  });
  it("scans the method page and the score components", () => {
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(MfScoreMethodPage)));
    expect(html.replace(/<[^>]+>/g, " ").replace(/not a recommendation|not investment advice|Not advice|not advice/gi, "")).not.toMatch(BANNED);
    for (const f of ["../mf/ScoreCard.tsx", "../mf/ScoreCompare.tsx", "../mf/FundTable.tsx", "../pages/MfScoreMethod.tsx"]) {
      const src = readFileSync(resolve(__dirname, f), "utf8");
      const strings = (src.match(/"[^"\n]{12,}"|`[^`\n]{12,}`/g) || []).filter((s) => !/^["`](\.\.|@|\/|\w+[-:])/.test(s) && !/className/.test(s));
      for (const s of strings) expect(s.replace(/not a recommendation/gi, "")).not.toMatch(BANNED);
    }
  });
  it("weights add to 100 for every group", () => { for (const g of GROUP_WEIGHTS) expect(g.w.reduce((a, b) => a + b, 0)).toBe(100); expect(GROUP_WEIGHTS).toHaveLength(16); });
  it("writes the rank line", () => {
    expect(rankText({ rank: 12, of: 48, scope: "sub", percentile: 77, categoryLabel: "Large Cap", plan: "Direct" })).toBe("12 of 48 in Large Cap (Direct plan)");
    expect(rankText({ rank: 2, of: 14, scope: "fam", percentile: 92, categoryLabel: null, plan: "Regular" }, { key: "nifty50", index: "NIFTY 50 TRI" })).toBe("2 of 14 funds tracking NIFTY 50 TRI (Regular plan)");
    expect(confidenceText(0.83)).toBe("83% of the weight behind this score rests on real data.");
    expect(filledText({ n: 3, of: 19 })).toBe("3 of 19 measures used the group value because data was missing.");
    expect(filledText({ n: 0, of: 19 })).toBe("");
  });
});
