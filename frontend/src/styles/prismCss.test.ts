import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Regression (end-to-end run): the stock page's Prism half and the full Prism page used the same class names (pz-pc, pz-notes, ...) with
// different layouts, so the full page's two-column rule squeezed the stock page's pros/cons into a narrow strip. The stock page's
// classes are now pzs-*; the two stylesheets must never define the same class again.
const read = (f: string) => readFileSync(new URL(f, import.meta.url), "utf8");
const classes = (css: string) => new Set(css.match(/\.(?:pz[a-z]*|dk)-[a-z0-9-]+/g) ?? []);

describe("Prism stylesheets", () => {
  it("prism.css, prism-compare.css and dash-shared.css share no class name (pz*- and dk- prefixes)", () => {
    const a = classes(read("./prism.css")), b = new Set([...classes(read("./prism-compare.css")), ...classes(read("./dash-shared.css"))]);
    expect([...b].filter((c) => a.has(c))).toEqual([]);
  });
  it("prism-technical.css (pzt-) shares no class name with the other Prism stylesheets", () => {
    const t = classes(read("./prism-technical.css")), others = new Set([...classes(read("./prism.css")), ...classes(read("./prism-compare.css")), ...classes(read("./dash-shared.css"))]);
    expect(t.size).toBeGreaterThan(40);
    expect([...t].filter((c) => others.has(c))).toEqual([]);
    expect([...t].filter((c) => !c.startsWith(".pzt-"))).toEqual([]);
  });
  it("the stock page's Prism cards cannot widen the page at 360 px (spectrum cards use shrinkable grid columns)", () => {
    const css = read("./stock2.css");
    expect(css).toMatch(/\.spc, \.spc-bar \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  });
});
