import { describe, expect, it } from "vitest";
import { ownershipAt, ownershipYears, parsePeriod } from "./ownershipYears";

const periods = ["Jun 2016", "Sep 2016", "Dec 2016", "Mar 2017", "Jun 2017", "Sep 2017", "Dec 2017", "Mar 2018", "Jun 2018"];
const series = {
  promoters: [50.1, 50.2, 50.3, 50.4, 49.0, 48.9, 48.8, 48.7, 48.0],
  fii: [20, 20.5, 21, 21.5, 22, 22.5, 23, 23.5, 24],
  public: [null, null, null, null, 5, 5.1, 5.2, 5.3, 5.4],
};
const o = { periods, series, latest: [{ key: "promoters", label: "Promoters", value: 48, change1yPts: -1.0 }, { key: "fii", label: "Foreign institutions (FII)", value: 24, change1yPts: 2 }, { key: "public", label: "Retail & others", value: 5.4, change1yPts: null }] };

describe("ownership year picker", () => {
  it("parses quarter labels", () => { expect(parsePeriod("Sep 2026")).toEqual({ year: 2026, month: 8 }); expect(parsePeriod("FY26")).toBeNull(); });
  it("lists years newest first with the latest filing of each", () => {
    expect(ownershipYears(periods)).toEqual([{ year: 2018, index: 8 }, { year: 2017, index: 6 }, { year: 2016, index: 2 }]);
  });
  it("compares with the same quarter a year earlier", () => {
    const v = ownershipAt(o, 6)!; // Dec 2017 vs Dec 2016
    expect(v.asOf).toBe("Dec 2017"); expect(v.comparedWith).toBe("Dec 2016"); expect(v.basis).toBe("same quarter a year earlier");
    expect(v.latest.find((l) => l.key === "promoters")!.change1yPts).toBe(-1.5);
  });
  it("falls back to the previous year's latest filing, and to nothing for the oldest year", () => {
    const short = { ...o, periods: ["Dec 2016", "Mar 2017", "Jun 2018", "Sep 2017"], series: { promoters: [50, 49, 48, 48.5] } };
    const v = ownershipAt(short, 3)!;
    expect(v.comparedWith).toBe("Dec 2016"); expect(v.basis).toBe("latest filing of the previous year");
    const first = ownershipAt(o, 2)!;
    expect(first.comparedWith).toBeNull(); expect(first.latest[0].change1yPts).toBeNull();
  });
  it("drops groups with no value in the chosen filing", () => { expect(ownershipAt(o, 1)!.latest.map((l) => l.key)).toEqual(["promoters", "fii"]); });
});
