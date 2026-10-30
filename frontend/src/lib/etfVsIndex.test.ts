import { describe, expect, it } from "vitest";
import { COMPARE } from "./__fixtures__/etfVsIndex";
import {
  DEFAULT_PAGE, TILES, compareQuery, dragSentence, growthOf100, lumpSentence, parsePage, readyToCompare, sectionRows, toCsv, toParams, validIso,
} from "./etfVsIndex";

describe("the address of a comparison", () => {
  it("round-trips a full comparison and keeps a plain one plain", () => {
    const s = parsePage(new URLSearchParams("index=niftynext50&etf=niftybees,junior&fund=120684,120685&plan=All&sip=5000&lump=250000&start=2021-04-01&range=5Y&risk=3Y"));
    expect(s).toEqual({ index: "niftynext50", etf: ["NIFTYBEES", "JUNIOR"], fund: [120684, 120685], plan: "All", sip: 5000, lump: 250000, start: "2021-04-01", range: "5Y", risk: "3Y" });
    expect(parsePage(toParams(s))).toEqual(s);
    expect(toParams({ ...DEFAULT_PAGE, index: "nifty50", etf: ["A"], fund: [1] }).toString()).toBe("index=nifty50&etf=A&fund=1");
  });
  it("ignores what it cannot read and never sends a bad number", () => {
    const s = parsePage(new URLSearchParams("index=%3Cscript%3E&etf=a b,<x>,OK&fund=abc,0,12.5,77&plan=Both&sip=-5&lump=1e99&start=2021-02-30&range=9Y&risk=x"));
    expect(s.index).toBe("nifty50"); expect(s.etf).toEqual(["OK"]); expect(s.fund).toEqual([77]); expect(s.plan).toBe("Direct");
    expect(s.sip).toBe(10000); expect(s.lump).toBe(100000); expect(s.start).toBe(""); expect(s.range).toBe("3Y"); expect(s.risk).toBe("");
    expect(validIso("2024-02-29")).toBe("2024-02-29"); expect(validIso("2023-02-29")).toBe(""); expect(validIso("1999-01-01")).toBe("");
  });
  it("keeps four products at most, ETFs first, and needs one of each kind", () => {
    const s = parsePage(new URLSearchParams("etf=A,B,C,D,E&fund=1,2,3"));
    expect(s.etf).toEqual(["A", "B", "C"]); expect(s.fund).toEqual([1]);
    expect(readyToCompare(s)).toBe(true); expect(readyToCompare({ ...s, fund: [] })).toBe(false); expect(readyToCompare({ ...s, etf: [] })).toBe(false);
  });
  it("sends the same query for the same comparison whatever the chart range or risk window", () => {
    const a = parsePage(new URLSearchParams("etf=A&fund=1&range=5Y&risk=1Y")), b = parsePage(new URLSearchParams("etf=A&fund=1"));
    expect(compareQuery(a)).toBe(compareQuery(b));
    expect(compareQuery({ ...b, start: "2022-01-03" })).toContain("start=2022-01-03");
  });
});

describe("growth of 100", () => {
  const chart = COMPARE.chart!;
  it("starts every line at 100 on the first date shown", () => {
    const g = growthOf100(chart, ["SAMPLEETF", "910001"], "MAX");
    expect(g.start).toBe(chart.t[0]);
    if (g.start) { expect(g.series.SAMPLEETF[0]).toEqual([chart.t[0], 100]); expect(g.index![0]).toEqual([chart.t[0], 100]); expect(g.series["910001"].length).toBe(chart.t.length); }
  });
  it("cuts a shorter range at a date that exists and rebases there", () => {
    const g = growthOf100(chart, ["SAMPLEETF"], "1Y");
    expect(g.start).not.toBeNull();
    if (g.start) {
      const last = new Date(chart.t[chart.t.length - 1] + "T00:00:00Z"); last.setUTCFullYear(last.getUTCFullYear() - 1);
      const target = last.toISOString().slice(0, 10);
      expect(g.start >= target).toBe(true); expect(chart.t[chart.t.indexOf(g.start) - 1] < target).toBe(true);   // the first plotted date on or after the one-year-ago date
      const i = chart.t.indexOf(g.start);
      expect(g.series.SAMPLEETF[0][1]).toBe(100); expect(g.series.SAMPLEETF[1][1]).toBeCloseTo((chart.v.SAMPLEETF[i + 1] / chart.v.SAMPLEETF[i]) * 100, 2);
    }
  });
  it("refuses a range longer than the history with the reason, and drops the index line it cannot start", () => {
    const g = growthOf100({ ...chart, t: chart.t.slice(-10), v: { SAMPLEETF: chart.v.SAMPLEETF.slice(-10) }, index: null, indexWhy: "no levels" }, ["SAMPLEETF"], "5Y");
    expect(g.start).toBeNull();
    if (g.start === null) expect(g.why).toContain("common history starts on");
    const h = growthOf100({ ...chart, index: chart.index!.map((x, i) => (i === 0 ? null : x)) }, ["SAMPLEETF"], "MAX");
    if (h.start) { expect(h.index).toBeNull(); expect(h.indexWhy).toContain("Index levels start after"); }
  });
});

describe("words and tables", () => {
  it("shows the arithmetic of a lump sum and of the expense ratio", () => {
    expect(lumpSentence(100000, COMPARE.lump!.SAMPLEETF)).toBe("₹1,00,000 ÷ ₹200.0000 (29 Oct 2021) = 500.0000 units × ₹360.0000 (29 Oct 2026) = ₹1,80,000.00");
    expect(dragSentence(COMPARE.costs.SAMPLEETF, 1_000_000)).toBe("0.05% × ₹10,00,000 = ₹500 a year");
    expect(dragSentence({ ...COMPARE.costs.SAMPLEETF, terPct: null }, 1_000_000)).toBeNull();
  });
  it("writes each section as CSV with blanks explained, and quotes what needs it", () => {
    const perf = sectionRows(COMPARE, "performance");
    expect(perf[0][0]).toContain("Information only, not investment advice"); expect(perf[1]).toEqual(["Measure", "SAMPLEETF", "Sample Nifty 50 Index Fund"]);
    const five = perf.find((r) => String(r[0]).startsWith("Return, 5 years"))!;
    expect(String(five[1])).toMatch(/^Not available: Common history starts on/);
    const cost = sectionRows(COMPARE, "cost");
    expect(cost.find((r) => r[0] === "Expense ratio (% a year)")).toEqual(["Expense ratio (% a year)", 0.05, 0.2]);
    expect(cost.some((r) => String(r[0]).includes("not included"))).toBe(true);
    expect(sectionRows(COMPARE, "risk", "1Y").find((r) => r[0] === "Volatility (% a year)")).toEqual(["Volatility (% a year)", 11.2, 11.3]);
    expect(sectionRows(COMPARE, "risk", "5Y").find((r) => r[0] === "Volatility (% a year)")![1]).toMatch(/^Not available: Common history/);
    const summary = sectionRows(COMPARE, "summary");
    expect(summary[1]).toEqual(["Category", "Measure", "Ahead", "Values"]); expect(summary[3][2]).toBe("SAMPLEETF"); expect(summary[2][2]).toBe("Level");
    expect(toCsv([["a,b", 'say "x"', null, "=1+1"]])).toBe('"a,b","say ""x""",,\'=1+1\r\n');
  });
  it("lists six tiles, in the mockup's order, and calls the last one a summary rather than a verdict", () => {
    expect(TILES.map((t) => t.title)).toEqual(["Performance", "Cost analysis", "Tracking quality", "Risk analysis", "Investment calculator", "Summary by category"]);
  });
});
