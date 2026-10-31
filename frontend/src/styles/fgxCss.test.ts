import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The shared screener stylesheet owns the fgx- prefix: no other stylesheet may define an fgx- class.
const dir = new URL("./", import.meta.url);
const classes = (css: string) => new Set(css.match(/\.fgx-[a-z0-9-]+/g) ?? []);
describe("fgx stylesheet", () => {
  it("only fgx.css defines fgx- classes", () => {
    const own = classes(readFileSync(new URL("./fgx.css", import.meta.url), "utf8"));
    expect(own.size).toBeGreaterThan(40);
    const clash: string[] = [];
    for (const f of readdirSync(dir).filter((x) => x.endsWith(".css") && x !== "fgx.css")) {
      for (const c of classes(readFileSync(new URL("./" + f, import.meta.url), "utf8"))) clash.push(`${f}: ${c}`);
    }
    expect(clash).toEqual([]);
  });
});
