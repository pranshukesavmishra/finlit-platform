import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The page header stylesheet owns the ph- prefix: no other stylesheet may define a ph- class, and it uses theme tokens only (no hard-coded colours except the one on-gold text).
const dir = new URL("./", import.meta.url);
const classes = (css: string) => new Set(css.match(/\.ph-[a-z0-9-]+/g) ?? []);
describe("page-header stylesheet", () => {
  it("only page-header.css defines ph- classes", () => {
    const own = classes(readFileSync(new URL("./page-header.css", import.meta.url), "utf8"));
    expect(own.size).toBeGreaterThan(20);
    const clash: string[] = [];
    for (const f of readdirSync(dir).filter((x) => x.endsWith(".css") && x !== "page-header.css")) {
      for (const c of classes(readFileSync(new URL("./" + f, import.meta.url), "utf8"))) clash.push(`${f}: ${c}`);
    }
    expect(clash).toEqual([]);
  });
  it("takes its colours from the theme tokens", () => {
    const css = readFileSync(new URL("./page-header.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const hard = (css.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).filter((c) => !["#1A1405", "#FFFDF6"].includes(c.toUpperCase()));
    expect(hard).toEqual([]);
    expect(css).not.toMatch(/\b(green|blue|teal|purple)\b|var\(--(k\d|c\d|gain|loss)\)/);   // one hue only: the gold accent
  });
});
