import { describe, expect, it } from "vitest";
import { PRISM_PARTS } from "./prismWords";
import { PART_LINE, alignSentence, arcPath, basedOn, fundSubtitle, horizonCaption, horizonLabel, partTip, partWord, polar, ringArcs, signalsLine, techEdgePos } from "./prismCardLogic";
import { trendAlignment, type TechHorizon } from "../lib/prismTechnical";

const H = (o: Partial<TechHorizon>): TechHorizon => ({ score: 1, rating: "Hold", status: "ready", horizon: "5–20 sessions", availableCount: 14, requiredCount: 14, stageCapped: false, uncappedScore: null, divisor: null, factors: [], ...o });

describe("ring geometry", () => {
  it("sizes each arc by its weight and leaves the gaps", () => {
    const a = ringArcs([{ key: "a", weight: 40, value: 55 }, { key: "b", weight: 30, value: 42 }, { key: "c", weight: 20, value: 79 }, { key: "d", weight: 10, value: 88 }], 8);
    expect(a.map((x) => Math.round(x.share * 100))).toEqual([40, 30, 20, 10]);
    expect(a[0].a0).toBeCloseTo(4); expect(a[0].a1).toBeCloseTo(144 - 4);
    expect(a[1].a0).toBeCloseTo(144 + 4);
    expect(a[3].a1).toBeCloseTo(360 - 4);
    expect(a[0].aFill).toBeCloseTo(4 + 136 * 0.55);
  });
  it("colours by the shared band rule and treats fractions like percents", () => {
    const a = ringArcs([{ key: "a", weight: 0.4, value: 70 }, { key: "b", weight: 0.6, value: 49.9 }, { key: "c", weight: 0, value: null }]);
    expect(a.map((x) => x.band)).toEqual(["hi", "lo", "na"]);
    expect(a[0].share).toBeCloseTo(0.4);
  });
  it("clamps scores and survives no weights", () => {
    expect(ringArcs([{ key: "a", weight: 1, value: 140 }])[0].value).toBe(100);
    expect(ringArcs([{ key: "a", weight: 0, value: 5 }])[0].a1).toBeGreaterThan(0);
  });
  it("puts 0 degrees at 12 o'clock, clockwise", () => {
    const [x, y] = polar(80, 80, 10, 0); expect(x).toBeCloseTo(80); expect(y).toBeCloseTo(70);
    const [x2] = polar(80, 80, 10, 90); expect(x2).toBeCloseTo(90);
    expect(arcPath(80, 80, 10, 0, 200)).toContain(" 0 1 1 ");
  });
});

describe("words and captions", () => {
  it("maps part scores to the model's words at 35/50/65/80", () => {
    expect([null, 34.9, 35, 49.9, 50, 64.9, 65, 79.9, 80].map((v) => partWord(v)[0])).toEqual(["No data", "Poor", "Weak", "Weak", "Average", "Average", "Healthy", "Healthy", "Strong"]);
  });
  it("builds the tooltip sentence", () => {
    expect(partTip("Valuation", 42.4, "Weak", 30)).toBe("Valuation 42 of 100: Weak. Counts for 30% of the overall score.");
    expect(partTip("Risk", null, "No data", 10)).toBe("Risk: no data. Counts for 10% of the overall score.");
  });
  it("describes every part of the model, and the headline counts", () => {
    for (const [k] of PRISM_PARTS) expect(PART_LINE[k]).toBeTruthy();
    expect(fundSubtitle(4)).toContain("four areas"); expect(basedOn(4, true)).toContain("higher Risk score means lower risk"); expect(basedOn(1, false)).toBe("Based on 1 weighted component. Higher is better.");
  });
  it("uses the horizons and signal counts of the report, never invented ones", () => {
    expect(horizonCaption(H({}))).toBe("5–20 sessions"); expect(horizonCaption(H({ horizon: null }))).toBeNull();
    expect(signalsLine(H({}))).toBe("14 of 14 signals available"); expect(signalsLine(H({ requiredCount: 0 }))).toBeNull();
    expect(horizonLabel("Technical long term", H({ score: -57, rating: "Sell", horizon: "6–18 months" }))).toBe("Technical long term (6–18 months): −57 on a scale from minus 100 to plus 100, strongly negative. 14 of 14 signals available.");
    expect(horizonLabel("Technical short term", H({ score: null }))).toContain("not available");
  });
  it("writes the alignment sentence from the two bands", () => {
    expect(alignSentence(trendAlignment(1, -57)!)).toBe("The short-term trend is neutral, while the long-term trend is negative.");
    expect(alignSentence(trendAlignment(40, 60)!)).toBe("Both the short-term and the long-term trend are positive.");
  });
  it("places the band edges on the -100..+100 scale", () => { expect(techEdgePos()).toEqual([25, 40, 60, 75]); });
});
