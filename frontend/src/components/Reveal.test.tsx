import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { Reveal } from "./Reveal";

const css = (f: string) => readFileSync(new URL(`../styles/${f}`, import.meta.url), "utf8");

describe("Reveal never hides content by default", () => {
  it("renders visible markup (no hidden class) before any script runs", () => {
    const html = renderToStaticMarkup(<Reveal className="sec-h"><h2>Where to look today</h2></Reveal>);
    expect(html).toContain("Where to look today");
    expect(html).not.toContain("rv-pre");
  });
  it("the base .rv rule has no opacity:0 / translate; hiding lives only on .rv.rv-pre", () => {
    for (const f of ["site.css", "premium.css", "human-home.css"]) {
      const rules = [...css(f).matchAll(/(^|\n)\s*([^{}\n@]*\.rv[^{}]*)\{([^}]*)\}/g)];
      for (const [, , sel, body] of rules) {
        if (/rv-pre/.test(sel)) continue;
        expect(body, `${f}: ${sel}`).not.toMatch(/opacity:\s*0\b/);
        if (!/\.in\b/.test(sel)) expect(body, `${f}: ${sel}`).not.toMatch(/transform:\s*translate/);
      }
    }
  });
});
