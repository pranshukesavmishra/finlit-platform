import { describe, expect, it } from "vitest";
import { moved, readBars, readBreakdown, readCandles, readCorrelationMatrix, readTimeSeries } from "./chartReading";
import type { Pt } from "./graphMetrics";

const yr = (vals: (number | null)[], from = 2021): Pt[] => vals.map((v, i) => ({ t: `${from + i}-03-31`, v, l: `FY${String(from + i).slice(2)}` }));
const BANNED = /\b(buy|sell|hold|reduce|avoid|accumulate|target|best|will|should)\b/i;
const text = (r: { headline: string; lines: { text: string }[]; closing: string } | null) => r ? [r.headline, ...r.lines.map((l) => l.text), r.closing].join(" ") : "";

describe("moved: the change in words", () => {
  it("quotes a percentage, a percentage-point gap for a ratio in %, and never a % of a zero or negative start", () => {
    expect(moved(100, 125, "inr")).toBe("up 25.0%");
    expect(moved(200, 150, "cr")).toBe("down 25.0%");
    expect(moved(12.5, 15, "pct")).toBe("up 2.50 percentage points");
    expect(moved(-5, 10, "cr")).toBe("up ₹15.00 Cr");
    expect(moved(3, 3, "cr")).toBe("unchanged");
  });
});

describe("time series reading", () => {
  const s = { label: "Revenue", unit: "cr" as const, pts: yr([100, 120, 90, 150, 180]) };
  it("says where it started and ended, the highest and lowest, how often it rose, and the biggest move, from the numbers", () => {
    const r = readTimeSeries([s], "annual")!;
    const t = text(r);
    expect(r.headline).toBe("Revenue ended higher than it started over FY21 to FY25.");
    expect(t).toContain("went from ₹100.00 Cr (FY21) to ₹180.00 Cr (FY25), up 80.0%");
    expect(t).toContain("Highest: ₹180.00 Cr (FY25). Lowest: ₹90.00 Cr (FY23). The latest figure is the highest in the window.");
    expect(t).toContain("It rose in 3 years and fell in 1 year out of 4.");
    expect(t).toContain("The biggest single move was +66.7% in FY24");     // 90 -> 150
    expect(t).toContain("Describes what the figures did");
    expect(t).not.toMatch(BANNED);
  });
  it("a missing period is counted and skipped, and a short history says it is a hint", () => {
    const r = readTimeSeries([{ ...s, pts: yr([100, null, 130]) }], "annual")!;
    expect(r.lines.some((l) => l.warn && /1 period have no figure|1 period has no figure|1 period have/.test(l.text) || (l.warn && /no figure and are skipped/.test(l.text)))).toBe(true);
    expect(r.lines.some((l) => l.warn && /Only 2 figures/.test(l.text))).toBe(true);
  });
  it("one point or none gives no reading at all (nothing is invented)", () => {
    expect(readTimeSeries([{ ...s, pts: yr([100]) }], "annual")).toBeNull();
    expect(readTimeSeries([{ ...s, pts: [] }], "annual")).toBeNull();
  });
  it("two series add how closely they moved, with the honest caveat", () => {
    const b = { label: "Net profit", unit: "cr" as const, pts: yr([10, 12, 9, 15, 18]) };
    const t = text(readTimeSeries([s, b], "annual"));
    expect(t).toContain("Revenue and Net profit moved together on 5 shared dates: r = 1.00");
    expect(t).toContain("not proof that one drives the other");
  });
  it("a flat series says it did not change; a ratio in % is described in percentage points", () => {
    expect(text(readTimeSeries([{ ...s, pts: yr([5, 5, 5]) }], "annual"))).toContain("it did not change");
    expect(text(readTimeSeries([{ label: "ROE", unit: "pct", pts: yr([10, 12, 15]) }], "annual"))).toContain("up 5.00 percentage points");
  });
  it("a dense price series is described by readings and the drop from its high, not year by year", () => {
    const pts: Pt[] = Array.from({ length: 200 }, (_, i) => ({ t: new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10), v: 100 + Math.sin(i / 10) * 10 + i * 0.1 }));
    const t = text(readTimeSeries([{ label: "Share price", unit: "inr", pts }], "annual"));
    expect(t).toContain("200 readings");
    expect(t).not.toContain("It rose in");
  });
});

describe("other charts", () => {
  it("a breakdown names the largest part, the top three and how concentrated it is", () => {
    const r = readBreakdown("Revenue by segment", [{ name: "Oil", value: 80 }, { name: "Retail", value: 12 }, { name: "Digital", value: 5 }, { name: "Other", value: 3 }])!;
    const t = text(r);
    expect(r.headline).toBe("Revenue by segment: 4 parts, led by Oil (80.0%).");
    expect(t).toContain("The top three together make up 97.0%");
    expect(t).toContain("the other part has 3.0%");
    expect(t).toContain("The whole rests mostly on one part.");
    expect(readBreakdown("x", [{ name: "a", value: 1 }])).toBeNull();
  });
  it("bars give the leader, the trailer and the ratio between them", () => {
    const t = text(readBars([{ label: "A", v: 10 }, { label: "B", v: 4 }], "cr"));
    expect(t).toContain("A is the highest at ₹10.00 Cr; B is the lowest at ₹4.00 Cr.");
    expect(t).toContain("2.5 times the lowest");
  });
  it("candles give the net move, the range and the largest candle", () => {
    const pts: Pt[] = [{ t: "2026-10-01", o: 100, h: 105, lo: 98, v: 104 }, { t: "2026-10-02", o: 104, h: 110, lo: 103, v: 108 }, { t: "2026-10-03", o: 108, h: 109, lo: 100, v: 101 }];
    const t = text(readCandles(pts));
    expect(t).toContain("The highest price in the window is ₹110.00");
    expect(t).toContain("lowest is ₹98.00");
    expect(t).toContain("down 2.9% from the first close");
    expect(t).toContain("largest move from open to close in one candle was 6.5%");
  });
  it("a correlation matrix names the closest and the least alike pair and the pairs too thin to judge", () => {
    const r = [[1, 0.9, null], [0.9, 1, 0.1], [null, 0.1, 1]], n = [[5, 5, 0], [5, 5, 5], [0, 5, 5]];
    const t = text(readCorrelationMatrix(["A", "B", "C"], r, n));
    expect(t).toContain("The closest pair is A and B: r = 0.90 (very strong, moving together)");
    expect(t).toContain("The least alike is B and C: r = 0.10");
    expect(t).toContain("1 pair had too few shared dates");
    expect(readCorrelationMatrix(["A"], [[1]], [[3]])).toBeNull();
  });
});
