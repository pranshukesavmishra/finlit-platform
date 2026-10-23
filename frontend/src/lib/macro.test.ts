import { describe, expect, it } from "vitest";
import { align, corrWords, correlation, cut, fmt, frac, heat, signed, toCsv, type Pt, type SeriesOut } from "./macro";

const pts = (...v: [string, number][]): Pt[] => v;
describe("macro helpers", () => {
  it("cuts to the last N months from the newest point", () => {
    const p = pts(["2024-09-30", 1], ["2025-09-30", 2], ["2025-10-31", 3], ["2026-09-30", 4]);
    expect(cut(p, 12).map((x) => x[1])).toEqual([3, 4]);               // twelve months: Oct 2025 to Sep 2026
    expect(cut(p, 13).map((x) => x[1])).toEqual([2, 3, 4]);
    expect(cut(p, 0)).toBe(p);
    expect(cut([], 12)).toEqual([]);
  });
  it("aligns by calendar month and correlates", () => {
    const a: Pt[] = Array.from({ length: 24 }, (_, i) => [`${2024 + Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, "0")}-28`, i]);
    const b: Pt[] = a.map(([d, v]) => [d.slice(0, 8) + "30", v * 2 + 1]);
    expect(align(a, b)).toHaveLength(24);
    expect(correlation(align(a, b))).toBe(1);
    expect(correlation(align(a, b.map(([d, v]) => [d, -v] as Pt)))).toBe(-1);
    expect(correlation(align(a.slice(0, 5), b))).toBeNull();                      // too few months in common
    expect(correlation(align(a, a.map(([d]) => [d, 5] as Pt)))).toBeNull();      // no variation
    expect(corrWords(0.8)).toContain("strongly together"); expect(corrWords(-0.5)).toContain("opposite"); expect(corrWords(0.05)).toContain("hardly"); expect(corrWords(null)).toContain("Not enough");
  });
  it("formats the way the page reads", () => {
    expect(fmt(5.54, "%")).toBe("5.54%"); expect(fmt(-0.29, "pp")).toBe("−0.29 pp"); expect(fmt(726.027, "US$ bn")).toBe("US$ 726.0 bn"); expect(fmt(94.9432, "₹")).toBe("₹94.94");
    expect(signed(0.71, "pp")).toBe("+0.71 pp"); expect(signed(-5.011, "US$ bn")).toBe("−5.01 bn"); expect(signed(0, "%")).toBe("0.00%");
    expect(frac(5, 0, 10)).toBe(0.5); expect(frac(-1, 0, 10)).toBe(0); expect(frac(99, 0, 10)).toBe(1);
  });
  it("colours inflation against the 2-4-6 framework", () => {
    expect(heat(null).bg).toBe("transparent");
    expect(heat(7).strong).toBe(true); expect(heat(7).bg).toContain("--loss");
    expect(heat(5).bg).toContain("--warn"); expect(heat(3).bg).toContain("--gain"); expect(heat(1).bg).toContain("--k1");
  });
  it("exports a CSV with one column per series and blanks where a series has no point", () => {
    const s: Record<string, SeriesOut> = {
      a: { label: 'A "x"', unit: "%", freq: "M", source: "", sourceUrl: null, what: null, note: null, breaks: [], points: [["2026-01-31", 1], ["2026-02-28", 2]] },
      b: { label: "B", unit: "%", freq: "M", source: "", sourceUrl: null, what: null, note: null, breaks: [], points: [["2026-02-28", 3]] },
    };
    expect(toCsv(["a", "b"], s)).toBe('Date,"A ""x"" (%)","B (%)"\n2026-01-31,1,\n2026-02-28,2,3');
  });
});
