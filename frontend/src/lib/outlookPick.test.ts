// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { QUICK_PICKS, RECENT_MAX, pushRecent, readRecent, takeaways } from "./outlookPick";
import type { Outlook } from "./outlook";

beforeEach(() => localStorage.clear());

describe("quick picks and last searched", () => {
  it("offers the five named companies in order", () => expect(QUICK_PICKS.map((p) => p.symbol)).toEqual(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]));
  it("keeps the newest first, once each, at most five", () => {
    ["A", "B", "C", "D", "E", "F"].forEach(pushRecent);
    expect(readRecent()).toEqual(["F", "E", "D", "C", "B"]); expect(RECENT_MAX).toBe(5);
    pushRecent("c"); expect(readRecent()).toEqual(["C", "F", "E", "D", "B"]);
  });
  it("ignores a bad symbol and a damaged store", () => {
    pushRecent("<script>"); expect(readRecent()).toEqual([]);
    localStorage.setItem("finlit.outlook.recent", "{nope"); expect(readRecent()).toEqual([]);
    localStorage.setItem("finlit.outlook.recent", JSON.stringify(["OK", 5, "bad one"])); expect(readRecent()).toEqual(["OK"]);
  });
});

const row = (key: string, label: string, c: number | null) => ({ key, label, who: "company" as const, weightPct: 50, effectiveWeightPct: 50, valuePct: c, rawPct: c, capped: false, contributionPts: c, status: c == null ? "unavailable" as const : "ok" as const, method: null, reason: null, detail: null });
const mk = (o: Partial<Outlook> = {}, years = 1, end = 115): Outlook => ({
  symbol: "X", statement: "consolidated", kind: "profit", mode: "model", name: "X Ltd", isLender: false, asOf: { yearly: "FY26" }, reportGeneratedAt: null, weights: {}, defaultWeights: {}, adjustedYears: [],
  horizon: { key: "short", years, label: "Short-term", span: "1 year" }, history: { unit: "Cr", points: [] },
  rate: { ratePct: 15, rows: [row("a", "Company growth", 9), row("b", "Sector growth", 4), row("c", "Missing", null)], unavailable: ["Missing"], weightLeftPct: 0 },
  forecast: { available: true, reason: null, base: { period: "FY26", valueCr: 100 }, years: Array.from({ length: years }, (_, i) => ({ period: `FY${27 + i}`, valueCr: i === years - 1 ? end : 100 + i, growthPct: 15, changeCr: 15 })), rule: "" },
  inputCapPct: 100, minPeers: 3, disclaimer: "", ...o,
});
describe("key takeaways", () => {
  it("says the change, the rate, the biggest input and what was left out", () => {
    const t = takeaways(mk(), null);
    expect(t[0]).toMatch(/grow 15\.0% in FY27/); expect(t[1]).toMatch(/15\.00% a year/); expect(t[2]).toMatch(/Company growth/); expect(t.join(" ")).toMatch(/Left out for this company: Missing/);
    expect(t.join(" ")).toMatch(/Set your own model/);
  });
  it("a longer horizon says the total change over the years", () => expect(takeaways(mk({}, 3, 150), null)[0]).toMatch(/by FY29, \+50\.0% on .* over 3 years/));
  it("a falling estimate says fall, never grow", () => expect(takeaways(mk({}, 1, 90), null)[0]).toMatch(/fall 10\.0%/));
  it("with your own weights it compares with the FinLit model, higher, lower or the same", () => {
    const mine = mk({ mode: "custom" }, 1, 120);
    expect(takeaways(mine, mk({}, 1, 100)).join(" ")).toMatch(/20\.0% higher than the FinLit model/);
    expect(takeaways(mine, mk({}, 1, 150)).join(" ")).toMatch(/20\.0% lower/);
    expect(takeaways(mine, mk({}, 1, 120)).join(" ")).toMatch(/same estimate as the FinLit model/);
    expect(takeaways(mine, null).join(" ")).not.toMatch(/model's/);
  });
  it("no estimate, no takeaways", () => expect(takeaways(mk({ forecast: { available: false, reason: "x", base: null, years: [], rule: "" } }), null)).toEqual([]));
});
