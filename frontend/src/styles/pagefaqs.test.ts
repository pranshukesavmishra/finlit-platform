// The per-page FAQ panel lines up with the page's .wrap content column on every page.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(join(__dirname, "pagefaqs.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const wrap = readFileSync(join(__dirname, "finlit.css"), "utf8").match(/\n\.wrap \{([^}]*)\}/)![1];

describe("page FAQ panel alignment", () => {
  it("is as wide as the content of a .wrap (max 1260 less a 20px gutter on each side), centred", () => {
    expect(wrap).toMatch(/max-width: 1260px/);
    expect(css).toMatch(/\.pfq-in \{[^}]*width: min\(1220px, calc\(100% - 40px\)\)[^}]*margin: 0 auto/);
  });
  it("starts after the workspace sidebar exactly as the page does (280px, or 76px collapsed), and not at all on a phone", () => {
    expect(css).toMatch(/\.shell:not\(\.is-collapsed\)\) > \.pfq \{ padding-left: 280px/);
    expect(css).toMatch(/\.shell\.is-collapsed\) > \.pfq \{ padding-left: 76px/);
    expect(css).toMatch(/max-width: 960px\) \{ main:has\(\.shell\) > \.pfq \{ padding-left: 0 !important/);
  });
  it("uses the phone gutter of .wrap (14px) up to 760px", () => {
    expect(css).toMatch(/max-width: 760px\) \{ \.pfq-in \{ width: calc\(100% - 28px\)/);
  });
});
