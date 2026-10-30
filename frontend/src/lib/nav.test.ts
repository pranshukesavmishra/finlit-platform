import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { MORE, PRICING, SECTIONS, isHere, sectionHere } from "./nav";
const RESEARCH = SECTIONS.find((x) => x.id === "research")!;

const all = [...SECTIONS, MORE].flatMap((s) => s.groups.flatMap((g) => g.items));

describe("site map", () => {
  it("has the five headings, in the agreed order, with the agreed items", () => {
    expect(SECTIONS.map((s) => s.label)).toEqual(["Workspace", "Research", "Markets", "News & events", "Funds"]);
    const names = (id: string) => SECTIONS.find((s) => s.id === id)!.groups.flatMap((g) => g.items.map((i) => i.label));
    expect(RESEARCH.groups.map((g) => g.title)).toEqual(["Find stocks", "Analyse a company", "Investment calculators", "Charts"]);
    expect(RESEARCH.groups[0].items.map((i) => i.label)).toEqual(["Stock screener", "Basic score screener", "Advanced score screener", "Query builder"]);
    expect(RESEARCH.groups[1].items.map((i) => i.label)).toEqual(["Company report", "Compare companies", "FinLit Prism", "Profit and revenue outlook", "Premium reports"]);
    expect(RESEARCH.groups[2].items.map((i) => i.label)).toEqual(["EPS & P/E calculator", "DCF valuation calculator", "SIP calculator"]);
    expect(RESEARCH.groups[3].items.map((i) => i.label)).toEqual(["Chart builder", "Correlation charts"]);
    expect(names("markets")).toEqual(["FII & DII flows", "India economy", "Commodity prices"]);
    expect(names("news")).toEqual(["Results calendar", "Latest results", "IPO calendar", "News & filings"]);
    expect(names("funds")).toEqual(["Mutual funds", "ETFs"]);
    expect(names("myfinlit")).toEqual(["Dashboard", "Watchlists", "My portfolio", "Alerts"]);
  });
  it("marks the Gold tools of the Research menu", () => {
    expect(RESEARCH.groups.flatMap((g) => g.items).filter((i) => i.gold).map((i) => i.to).sort()).toEqual(["/advanced-score-screener", "/dcf", "/outlook", "/premium/report", "/prism"]);
  });
  it("lists every address once, and every one of them is a real route", () => {
    const paths = [...all.map((i) => i.to), PRICING.to];
    expect(new Set(paths).size).toBe(paths.length);
    const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
    const routes = [...app.matchAll(/path="([^"]+)"/g)].map((m) => "/" + m[1]);
    for (const p of paths) expect(routes.some((r) => r === p || r === p + "/*"), p).toBe(true);
  });
  it("knows which heading the visitor is under", () => {
    const research = RESEARCH;
    expect(sectionHere("/screener", research)).toBe(true);
    expect(sectionHere("/graphs/advanced/valuation", research)).toBe(true);
    expect(sectionHere("/funds/123", SECTIONS.find((x) => x.id === "funds")!)).toBe(true);
    expect(sectionHere("/funds", research)).toBe(false);
    expect(isHere("/results/quarter", all.find((i) => i.to === "/results")!)).toBe(false);   // "end" items match only themselves
    expect(isHere("/graphs/advanced", all.find((i) => i.to === "/graphs")!)).toBe(false);
  });
});
