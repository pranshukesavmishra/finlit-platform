import { describe, expect, it } from "vitest";
import { ordinal, restSentence, sectorOrder, sizeLine, squarify, short2, two, pct, heatStep } from "./derive";
import s12 from "./__fixtures__/sample_12.json";
import type { PageObject } from "./types";

const page = s12.page as unknown as PageObject;

describe("number text", () => {
  it("formats correlations the way the grid shows them", () => { expect(short2(0.78)).toBe(".78"); expect(short2(-0.01)).toBe("−.01"); expect(two(0.5)).toBe("0.50"); });
  it("never writes 62th", () => { expect([53, 62, 11, 12, 13, 21, 22, 23, 101, 112].map(ordinal)).toEqual(["53rd", "62nd", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st", "112th"]); });
  it("says under 0.1% for a tiny share, never 0.0%", () => { expect(pct(0.04)).toBe("under 0.1%"); expect(pct(33.333)).toBe("33.3%"); });
  it("steps the heat at the design's six edges", () => { expect([0.04, 0.05, 0.2, 0.35, 0.5, 0.65].map(heatStep)).toEqual([0, 1, 2, 3, 4, 5]); });
});

describe("the sample list", () => {
  it("names the sizes from the page's own counts, the absent ones last", () => {
    const metas = Object.values(s12.inputs.meta) as never[];
    expect(sizeLine(page, metas)).toBe("7 sectors · 9 large caps, 3 small caps, no mid caps");
    expect(sizeLine(page, metas, true)).toBe("7 sectors · 9 large, 3 small");
  });
  it("lists sectors largest first and keeps the list's own order for ties", () => {
    expect(sectorOrder(page, "eq")).toEqual(["Financial Services", "Information Technology", "Oil, Gas & Consumable Fuels", "Healthcare", "Consumer Durables", "Capital Goods", "Media, Entertainment & Publication"]);
  });
  it("writes the rest sentence from the figures", () => { expect(restSentence(page.avg_with_rest)).toContain("move most on their own (0.10 to 0.15)"); });
});

describe("squarify", () => {
  it("fills the box with areas proportional to the values", () => {
    const box = { x: 0, y: 0, w: 100, h: 60 };
    const out = squarify([{ value: 50, data: "a" }, { value: 30, data: "b" }, { value: 20, data: "c" }], box);
    expect(out).toHaveLength(3);
    const area = (r: { w: number; h: number }) => r.w * r.h;
    expect(out.reduce((a, r) => a + area(r), 0)).toBeCloseTo(6000, 3);
    expect(area(out[0]) / area(out[2])).toBeCloseTo(2.5, 3);
    out.forEach((r) => { expect(r.x).toBeGreaterThanOrEqual(-1e-9); expect(r.x + r.w).toBeLessThanOrEqual(100 + 1e-9); expect(r.y + r.h).toBeLessThanOrEqual(60 + 1e-9); });
  });
  it("gives nothing for an empty or zero list", () => { expect(squarify([], { x: 0, y: 0, w: 1, h: 1 })).toEqual([]); expect(squarify([{ value: 0, data: 1 }], { x: 0, y: 0, w: 1, h: 1 })).toEqual([]); });
});
