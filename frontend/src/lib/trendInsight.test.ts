import { describe, expect, it } from "vitest";
import { MINUS } from "./format";
import { badgeOf, insightLine, lastIndex, NEUTRAL, yearAgoIndex, yoyChange, type InsightSpec } from "./trendInsight";
import { niceTicks } from "./chartAxis";
import { trendMoney } from "../stock/Sections4";

const money = trendMoney("cr");
const spec = (values: (number | null)[], x: Partial<InsightSpec> = {}): InsightSpec => ({ kind: "flow", name: "Revenue", labels: values.map((_, i) => "FY" + (20 + i)), mode: "a", series: [{ label: "Revenue", values }], money, ...x });

describe("year-on-year change", () => {
  it("finds the newest figure and the one a year (or four quarters) earlier", () => {
    expect(lastIndex([1, 2, null])).toBe(1);
    expect(lastIndex([null, null])).toBe(-1);
    expect(yearAgoIndex([1, 2, 3, 4, 5, 6], 5, "q")).toBe(1);
    expect(yearAgoIndex([1, 2, 3], 2, "a")).toBe(1);
    expect(yearAgoIndex([1, 2, 3], 2, "q")).toBe(-1);
    expect(yearAgoIndex([null, 2, 3], 1, "a")).toBe(-1);
  });
  it("computes the per cent from the series itself", () => {
    const b = badgeOf(yoyChange([100, 111.7], "a"));
    expect(b).toMatchObject({ tone: "up", text: "+11.7% YoY" });
    expect(badgeOf(yoyChange([100, 90], "a"))).toMatchObject({ tone: "down", text: `${MINUS}10.0% YoY` });
    expect(badgeOf(yoyChange([100, 100.01], "a")).tone).toBe("flat");
  });
  it("names a move across zero instead of computing a per cent", () => {
    expect(badgeOf(yoyChange([-25956, 69197], "a"))).toMatchObject({ tone: "up", text: "Turned positive" });
    expect(badgeOf(yoyChange([500, -20], "a"))).toMatchObject({ tone: "down", text: "Turned negative" });
    expect(badgeOf(yoyChange([-50, -20], "a")).text).toBe("Negative, narrower YoY");
  });
  it("gives a reason when there is nothing to compare", () => {
    expect(badgeOf(yoyChange([5], "a"))).toMatchObject({ tone: "none", text: "YoY n/a" });
    expect(badgeOf(yoyChange([0, 5], "a")).title).toMatch(/zero/);
    expect(badgeOf(yoyChange([], "a")).tone).toBe("none");
  });
  it("uses points for ratios", () => {
    expect(badgeOf(yoyChange([10, 11.25], "a", true)).text).toBe("+1.3 pts YoY");
  });
});

describe("insight line", () => {
  it("describes growth with figures from the series only", () => {
    const l = insightLine(spec([100, 105, 110, 120, 134]));
    expect(l.tone).toBe("up");
    expect(l.text).toBe("Revenue is up 11.7% YoY, rising in 4 of the last 4 periods.");
    expect(l.text).not.toMatch(/buy|sell|hold|best|target|avoid/i);
  });
  it("describes a fall and a flat year", () => {
    expect(insightLine(spec([100, 80])).text).toBe("Revenue is down 20.0% YoY.");
    expect(insightLine(spec([100, 100])).text).toBe("Revenue is little changed YoY, at ₹100 Cr.");
  });
  it("names a turn to positive with both amounts", () => {
    const l = insightLine(spec([-25956, 69197], { name: "Free cash flow" }));
    expect(l.text).toBe(`Free cash flow turned positive, from ${MINUS}₹25,956 Cr in FY20 to ₹69,197 Cr in FY21.`);
  });
  it("compares with the first period drawn when asked", () => {
    const l = insightLine(spec([96057, 120000, 192000], { name: "Operating cash flow", since: true, labels: ["FY22", "FY24", "FY26"] }));
    expect(l.text).toBe("Operating cash flow reached ₹1.92 L Cr in FY26, up from ₹96,057 Cr in FY22.");
  });
  it("words a pair and a ratio", () => {
    const pair = insightLine(spec([], { kind: "pair", series: [{ label: "Cash", values: [100, 112] }, { label: "Borrowings", values: [200, 190] }] }));
    expect(pair.text).toBe("Cash rose 12.0% YoY, while borrowings fell 5.0% YoY.");
    expect(insightLine(spec([12, 13.5], { kind: "ratio", name: "Net margin" })).text).toBe("Net margin is 13.5%, up 1.5 points YoY.");
  });
  it("names the largest segment from the latest year", () => {
    const l = insightLine(spec([], { kind: "mix", labels: ["FY25", "FY26"], series: [{ label: "Retail", values: [10, 30] }, { label: "Digital", values: [5, 10] }, { label: "Gone", values: [9, null] }] }));
    expect(l.text).toBe("Retail is the largest of 2 segments, 75.0% of FY26 revenue.");
  });
  it("falls back to the neutral line and invents nothing", () => {
    expect(insightLine(spec([null, 50])).text).toBe(NEUTRAL);
    expect(insightLine(spec([])).text).toBe(NEUTRAL);
    expect(insightLine(spec([0, 50])).text).toBe(NEUTRAL);
    expect(insightLine({ ...spec([]), series: [] }).text).toBe(NEUTRAL);
  });
});

describe("value formatting and ticks", () => {
  it("prints amounts the way the page does", () => {
    expect(money(333000)).toBe("₹3.33 L Cr");
    expect(money(56616)).toBe("₹56,616 Cr");
    expect(trendMoney("rs")(20)).toBe("₹20.0");
    expect(trendMoney("pct")(12.34)).toBe("12.3%");
    expect(money(-25956)).toBe(`${MINUS}₹25,956 Cr`);
  });
  it("makes round axis values", () => {
    expect(niceTicks(0, 333000, 4)).toEqual([0, 100000, 200000, 300000, 400000]);
    expect(niceTicks(-25956, 69197, 4)).toEqual([-50000, -25000, 0, 25000, 50000, 75000]);
    expect(niceTicks(0, 20, 3)).toEqual([0, 10, 20]);
  });
});
