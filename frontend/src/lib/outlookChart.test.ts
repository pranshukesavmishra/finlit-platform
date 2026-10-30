import { describe, expect, it } from "vitest";
import fx from "./__fixtures__/outlookReliance.json";
import { axisUnit, buildSeries, changeVs, chartCsv, chartDomain, chartSummary, fmtCr, labelIndices, niceTicks, tableRows, tooltipText } from "./outlookChart";
import type { HistoryPoint, Outlook, YearRow } from "./outlook";

const H = (vals: (number | null)[], from = 20): HistoryPoint[] => vals.map((v, i) => ({ period: `FY${from + i}`, valueCr: v, reportedCr: v, adjusted: false }));
const E = (vals: number[], from: number): YearRow[] => vals.map((v, i) => ({ period: `FY${from + i}`, valueCr: v, growthPct: 10, changeCr: 0 }));

describe("buildSeries", () => {
  it("splits reported from estimate and joins them at the last reported year", () => {
    const s = buildSeries(H([100, 110, 121]), E([133, 146], 23));
    expect(s.points.map((p) => p.status)).toEqual(["actual", "actual", "actual", "estimate", "estimate"]);
    expect(s.lastActual).toBe(2); expect(s.firstEstimate).toBe(3); expect(s.hasAlt).toBe(false);
    expect(s.points[3].period).toBe("FY23");
  });
  it("draws no estimate when there is none, or when the latest year is not reported", () => {
    expect(buildSeries(H([100, 110]), null).firstEstimate).toBe(-1);
    expect(buildSeries(H([100, 110, null]), E([120], 23)).firstEstimate).toBe(-1);   // never continue from a gap
    expect(buildSeries([], E([120], 23)).points).toHaveLength(0);
  });
  it("keeps missing years as gaps, never filled in", () => {
    const s = buildSeries(H([100, null, 121, 133]), E([146], 24));
    expect(s.points[1].value).toBeNull(); expect(s.lastActual).toBe(3); expect(changeVs(s.points, 2)).toBeNull(); expect(tooltipText(s, 1)).toBe("FY21: not reported.");
  });
  it("carries a second estimate when the lengths match", () => {
    const s = buildSeries(H([100, 110]), E([121, 133], 22), E([119, 130], 22));
    expect(s.hasAlt).toBe(true); expect(s.points[2].alt).toBe(119); expect(s.points[3].alt).toBe(130);
    expect(buildSeries(H([100, 110]), E([121, 133], 22), E([119], 22)).hasAlt).toBe(false);
  });
  it("handles a short history and a loss-making company", () => {
    const short = buildSeries(H([100]), E([110], 21));
    expect(short.points).toHaveLength(2); expect(short.lastActual).toBe(0);
    const loss = buildSeries(H([50, 10, -30, -40]), null);
    expect(changeVs(loss.points, 3)).toEqual({ abs: -10, pct: null });           // no percentage from a loss
    expect(changeVs(loss.points, 1)?.pct).toBeCloseTo(-80);
    const d = chartDomain([50, 10, -30, -40]);
    expect(d.min).toBeLessThan(0); expect(d.max).toBeGreaterThanOrEqual(50); expect(d.ticks).toContain(0);
  });
});

describe("axis", () => {
  it("makes round ticks that cover the data", () => {
    for (const [lo, hi] of [[0, 43851], [27640, 44205], [-40, 50], [0, 1], [5, 5], [0, 1234567]] as const) {
      const t = niceTicks(lo, hi);
      expect(t.min).toBeLessThanOrEqual(lo); expect(t.max).toBeGreaterThanOrEqual(hi); expect(t.ticks.length).toBeGreaterThanOrEqual(3); expect(t.ticks.length).toBeLessThanOrEqual(9);
      t.ticks.slice(1).forEach((v, i) => expect(v - t.ticks[i]).toBeCloseTo(t.step, 6));
    }
    expect(niceTicks(0, 43851).ticks).toEqual([0, 20000, 40000, 60000]); expect(niceTicks(0, 9).ticks).toEqual([0, 2.5, 5, 7.5, 10]);
    expect(niceTicks(-40, 50).ticks).toContain(0);
  });
  it("starts at zero unless every value sits far above it", () => {
    expect(chartDomain([10, 20, 30]).min).toBe(0);
    expect(chartDomain([900, 950, 1000]).min).toBeGreaterThan(0);
    expect(chartDomain([]).ticks.length).toBeGreaterThan(1);
  });
  it("switches to lakh crore for large values", () => {
    const small = axisUnit(43851, 10000), big = axisUnit(850000, 200000);
    expect(small.name).toBe("₹ crore"); expect(small.fmt(40000)).toBe("40,000");
    expect(big.name).toBe("₹ lakh crore"); expect(big.fmt(400000)).toBe("4"); expect(axisUnit(850000, 25000).fmt(425000)).toBe("4.25");
    expect(small.fmt(-20000)).toBe("−20,000");
  });
  it("formats amounts", () => {
    expect(fmtCr(43851)).toBe("₹43,851 Cr"); expect(fmtCr(-4000)).toBe("−₹4,000 Cr"); expect(fmtCr(250000)).toBe("₹2.50 lakh crore"); expect(fmtCr(null)).toBe("—");
  });
  it("thins x labels so they never collide, always keeping the latest", () => {
    const all = labelIndices(8, 600, 4); expect([...Array(8).keys()].every(all)).toBe(true);
    const some = labelIndices(13, 250, 4);
    const shown = [...Array(13).keys()].filter(some);
    expect(shown.length).toBeLessThan(13); expect(shown).toContain(12);
    shown.slice(1).forEach((v, i) => expect(v - shown[i]).toBe(shown[1] - shown[0]));
  });
});

describe("text and export", () => {
  const rel = (k: string) => (fx as unknown as Record<string, Outlook>)[k];
  it("summarises in words, with the estimate named and not promised", () => {
    const d = rel("revenue:mid"), s = buildSeries(d.history.points, d.forecast.years);
    const t = chartSummary("revenue", s, "FinLit model");
    expect(t).toMatch(/^Revenue: reported ₹[\d.,]+ (Cr|lakh crore) in FY26/); expect(t).toContain("Estimate:"); expect(t).toContain("for FY27"); expect(t).toContain("for FY29"); expect(t).toContain("FinLit model");
    expect(t).toContain("not a prediction"); expect(t).not.toMatch(/\b(buy|sell|hold|target price|will reach|guarantee)/i);
    expect(chartSummary("profit", buildSeries([], null), "x")).toContain("no reported figures");
    expect(chartSummary("profit", buildSeries(H([1, 2]), null), "x")).toContain("No estimate is shown");
  });
  it("tooltips and table rows give year, type, value and change", () => {
    const s = buildSeries(H([100, 110]), E([121], 22));
    expect(tooltipText(s, 1)).toBe("FY21, reported ₹110 Cr, up ₹10 Cr (+10.0%) on the year before");
    expect(tooltipText(s, 2)).toContain("estimate ₹121 Cr");
    expect(tableRows(s)).toEqual([["FY20", "Reported", "₹100 Cr", "—"], ["FY21", "Reported", "₹110 Cr", "+₹10 Cr (+10.0%)"], ["FY22", "Estimate", "₹121 Cr", "+₹11 Cr (+10.0%)"]]);
  });
  it("exports the same numbers as csv with a note", () => {
    const d = rel("profit:short"), s = buildSeries(d.history.points, d.forecast.years);
    const csv = chartCsv("profit", "RELIANCE", s, "FinLit model", "short-term").split("\n");
    expect(csv[0]).toContain("not a prediction or advice"); expect(csv[1]).toBe("Period,Type,Value (Rs crore),Change on year before (%),Note");
    expect(csv).toHaveLength(2 + s.points.length); expect(csv.some((l) => l.startsWith("FY27,Estimate,"))).toBe(true);
    const fy20 = csv.find((l) => l.startsWith("FY20,"))!;
    expect(fy20).toContain("Adjusted for one-off items");
  });
  it("the chart and the table beside it come from one payload", () => {
    const d = rel("revenue:long"), s = buildSeries(d.history.points, d.forecast.years);
    expect(s.points.filter((p) => p.status === "estimate").map((p) => p.value)).toEqual(d.forecast.years.map((y) => y.valueCr));
    expect(s.points[s.lastActual].value).toBe(d.forecast.base?.valueCr);
    expect(d.forecast.years).toHaveLength(5);
  });
});
