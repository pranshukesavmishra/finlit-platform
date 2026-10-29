import { describe, expect, it } from "vitest";
import { barIndexes, barsSummary, buildBars, changeScale, compareIndex, diffPp, fmtPp, ownCategories, ownershipCsv, selectionInfo, toggleHidden } from "./ownershipBars";

// 9 quarters, Dec 2022 to Dec 2024, with a gap (Mar 2023 not filed for the retail group) and a government figure only in "others".
const periods = ["Dec 2022", "Mar 2023", "Jun 2023", "Sep 2023", "Dec 2023", "Mar 2024", "Jun 2024", "Sep 2024", "Dec 2024"];
const series = {
  promoters: [50, 50.1, 50.2, 50.3, 50.4, 50.5, 50.6, 50.7, 50.8],
  fii: [20, 19.5, 19, 18.5, 18, 17.5, 17, 16.5, 16],
  dii: [15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5, 19],
  public: [14.9, null, 14.7, 14.6, 14.5, 14.4, 14.3, 14.2, 14.1],
  government: [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
  others: [null, null, null, null, null, null, null, null, 0.05],
};

describe("ownership bars: which filings", () => {
  it("quarterly ranges take 4 quarters per year, All takes everything", () => {
    expect(barIndexes(periods, "quarterly", "1Y")).toEqual([5, 6, 7, 8]);
    expect(barIndexes(periods, "quarterly", "3Y")).toHaveLength(9);
    expect(barIndexes(periods, "quarterly", "All")).toHaveLength(9);
  });
  it("yearly takes the latest filing of each year, never fewer than two years", () => {
    expect(barIndexes(periods, "yearly", "All")).toEqual([0, 4, 8]);
    expect(barIndexes(periods, "yearly", "1Y")).toEqual([4, 8]);
    expect(barIndexes(periods, "yearly", "3Y")).toEqual([0, 4, 8]);
  });
  it("a stored report with only a few quarters shows what it has", () => {
    expect(barIndexes(periods.slice(0, 3), "quarterly", "5Y")).toEqual([0, 1, 2]);
    expect(barIndexes([], "yearly", "All")).toEqual([]);
  });
});

describe("ownership bars: change in percentage points", () => {
  it("compares quarterly bars with the same quarter a year earlier and yearly bars with the previous year's latest filing", () => {
    expect(compareIndex(periods, 8, "quarterly")).toBe(4);
    expect(compareIndex(periods, 8, "yearly")).toBe(4);
    expect(compareIndex(periods, 0, "quarterly")).toBe(-1);
  });
  it("falls back to the previous year's latest filing when the same quarter was not filed", () => {
    const p = ["Dec 2022", "Sep 2023", "Jun 2024"];
    expect(compareIndex(p, 2, "quarterly")).toBe(1);
  });
  it("computes the change, and leaves it empty (not zero) when a figure is missing", () => {
    const bars = buildBars({ periods, series }, "quarterly", "All");
    const dec24 = bars[8];
    expect(dec24.comparedWith).toBe("Dec 2023");
    expect(dec24.changes.promoters).toBe(0.4);
    expect(dec24.changes.fii).toBe(-2);
    expect(bars[0].changes.promoters).toBeNull();
    expect(bars[2].changes.public).toBe(-0.2); // Jun 2022 was not filed: compared with the previous year's latest, Dec 2022
    const mar24 = bars[5]; expect(mar24.values.public).toBe(14.4); expect(mar24.changes.public).toBeNull(); // Mar 2023 was not filed
    expect(diffPp(null, 3)).toBeNull(); expect(diffPp(3, 2.9)).toBe(0.1);
  });
  it("merges government and others and drops groups with no figures at all", () => {
    const cats = ownCategories({ periods, series });
    expect(cats.map((c) => c.key)).toEqual(["promoters", "fii", "dii", "public", "government"]);
    expect(cats[4].values[8]).toBe(0.15); expect(cats[4].values[0]).toBe(0.1);
    expect(ownCategories({ periods: ["Dec 2022"], series: { promoters: [null] } })).toEqual([]);
  });
  it("marks a filing with no figures as not filed", () => {
    const bars = buildBars({ periods: ["Dec 2022", "Mar 2023"], series: { promoters: [50, null] } }, "quarterly", "All");
    expect(bars.map((b) => b.filed)).toEqual([true, false]);
  });
  it("sizes a symmetric scale from the biggest visible move", () => {
    const bars = buildBars({ periods, series }, "quarterly", "All");
    expect(changeScale(bars, ["promoters"]).max).toBeGreaterThanOrEqual(0.4);
    expect(changeScale(bars, ["fii"]).max).toBeGreaterThanOrEqual(2);
    expect(changeScale([], []).max).toBeGreaterThan(0);
  });
  it("formats", () => { expect(fmtPp(0.4)).toBe("+0.40 pp"); expect(fmtPp(-2)).toBe("−2.00 pp"); expect(fmtPp(null)).toBe("no earlier figure"); });
});

describe("ownership bars: hidden holders", () => {
  const all = ["promoters", "fii", "dii"];
  it("toggles a holder group", () => { expect(toggleHidden([], "fii", all)).toEqual(["fii"]); expect(toggleHidden(["fii"], "fii", all)).toEqual([]); });
  it("never hides the last visible group", () => { expect(toggleHidden(["fii", "dii"], "promoters", all)).toEqual(["fii", "dii"]); });
});

describe("ownership bars: CSV and selection", () => {
  const bars = buildBars({ periods, series }, "quarterly", "1Y");
  const cats = [{ key: "promoters", label: "Promoters" }, { key: "public", label: "Retail, & others" }];
  it("writes the mix table with the visible groups only", () => {
    const csv = ownershipCsv(bars, cats, "mix").split("\n");
    expect(csv[0]).toBe('Period,Promoters (% of shares),"Retail, & others (% of shares)"');
    expect(csv[1]).toBe("Mar 2024,50.5,14.4");
    expect(csv).toHaveLength(6);
  });
  it("writes the change table with empty cells for missing figures and the comparison period", () => {
    const csv = ownershipCsv(bars, cats, "change").split("\n");
    expect(csv[0]).toContain("Compared with");
    expect(csv[1]).toBe("Mar 2024,0.4,,Mar 2023"); // retail not filed in Mar 2023
  });
  it("says whether the selected filing is the latest of its year", () => {
    expect(selectionInfo(periods, 8)).toEqual({ year: 2024, isYearLatest: true, yearLatest: "Dec 2024" });
    expect(selectionInfo(periods, 6)).toEqual({ year: 2024, isYearLatest: false, yearLatest: "Dec 2024" });
  });
  it("summarises, and refuses a trend from fewer than two filings", () => {
    expect(barsSummary(bars, cats, "mix")).toContain("from Mar 2024 to Dec 2024");
    expect(barsSummary(bars.slice(0, 1), cats, "mix")).toBe("Not enough filings to show a trend.");
  });
});
