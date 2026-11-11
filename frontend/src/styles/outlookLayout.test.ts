import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "src/styles/outlook.css"), "utf8");

describe("outlook layout with Set your own model", () => {
  it("is a two-column grid on its own (a site-wide .side rule must not make it a flex row), charts left and sliders right", () => {
    expect(css).toMatch(/\.ol-top\.side \{ display: grid; grid-template-columns: minmax\(0, 1\.6fr\) minmax\(300px, 1fr\)/);
    expect(css).toMatch(/\.ol-top\.side > \.ol-assume \{ grid-column: 2; grid-row: 1; position: sticky/);
    expect(css).toMatch(/\.ol-top\.side > \.ol-charts \{ grid-column: 1; grid-row: 1; \}/);
  });
  it("puts the two charts one above the other in that column, and keeps the sliders in view while the charts scroll", () => {
    expect(css).toMatch(/\.ol-top\.side > \.ol-charts \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  });
});
