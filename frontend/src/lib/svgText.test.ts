import { describe, expect, it } from "vitest";
import { SCALE, chartFontSize, nearestScale } from "./svgText";

describe("chart text on the type scale", () => {
  it("snaps to the nearest scale size and never goes under 11px", () => {
    expect(nearestScale(8.4)).toBe(11);
    expect(nearestScale(3.7)).toBe(11);
    expect(nearestScale(12.9)).toBe(13);
    expect(nearestScale(17.9)).toBe(18);
    expect(nearestScale(15)).toBe(14);
    expect(nearestScale(56)).toBe(56);              // display sizes stay
    for (let px = 1; px < 44; px += 0.7) expect(SCALE).toContain(nearestScale(px));
  });
  it("converts the label's scale size back to chart units, whatever the chart's scale", () => {
    expect(chartFontSize(11, 1)).toBe(11);
    expect(chartFontSize(11, 0.46)).toBeCloseTo(23.91, 1);   // phone: 11 units would be 5px on screen, so 11px needs 23.9 units
    expect(chartFontSize(11, 1.63)).toBeCloseTo(6.75, 1);    // stretched wide chart: 11 units would be 18px; 11px needs 6.75 units
    expect(chartFontSize(10.6, 1.04)).toBeCloseTo(10.58, 1); // an off-scale declared size lands on 11px
    for (const k of [0.34, 0.46, 0.87, 1, 1.63]) expect(chartFontSize(11, k) * k).toBeCloseTo(11, 1);
    expect(chartFontSize(11, 0)).toBe(11);
  });
});
