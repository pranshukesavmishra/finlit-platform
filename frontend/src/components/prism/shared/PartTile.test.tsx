// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PartTile, bandOf } from "./PartTile";

describe("score bands: green from 70, orange from 50 to under 70, red under 50", () => {
  it("cuts exactly at 50 and 70", () => {
    expect([null, undefined, NaN].map(bandOf)).toEqual(["na", "na", "na"]);
    expect([0, 49.9, 50, 69.9, 70, 100].map(bandOf)).toEqual(["lo", "lo", "mid", "mid", "hi", "hi"]);
  });
  it("puts the band on the tile and keeps the part colour for the icon", () => {
    const tile = (v: number | null) => render(<PartTile name="Growth" value={v} word="Healthy" tone="healthy" color="--p-growth" />).container.firstElementChild as HTMLElement;
    expect(tile(75).className).toContain("band-hi");
    expect(tile(57).className).toContain("band-mid");
    expect(tile(45).className).toContain("band-lo");
    expect(tile(null).className).toContain("band-na");
    expect(tile(75).style.getPropertyValue("--pc")).toBe("var(--band-hi)");
    expect(tile(75).style.getPropertyValue("--pillar")).toBe("var(--p-growth)");
    expect(tile(null).style.getPropertyValue("--pc")).toBe("var(--p-growth)");
  });
});

describe("higher is better hint", () => {
  it("shows the caption and the full sentence on the tile", () => {
    const html = render(<PartTile name="Risk" value={74} word="Healthy" tone="healthy" color="--p-risk" hint={{ short: "Higher is better", long: "Higher is better: a higher Risk score means lower risk." }} />).container.innerHTML;
    expect(html).toContain("Higher is better");
    expect(html).toContain("a higher Risk score means lower risk");
  });
});
