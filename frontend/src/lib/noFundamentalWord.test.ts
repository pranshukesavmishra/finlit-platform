// The owner asked for the word "Fundamental(s)" to go from every page (Nov 2026). The Prism first part is "Growth & Profitability", the whole Prism rating is
// "financial health", the basic score's former "Fundamental" is "Growth & Profitability", the statements page is "Company financials". Routes, ids and data keys keep the old
// spelling (links and saved data must not break); the finance glossary keeps "fundamental analysis" as a dictionary term.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = new URL("..", import.meta.url).pathname;
const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? (n === "__fixtures__" ? [] : files(p)) : /\.(tsx?)$/.test(n) && !/\.test\./.test(n) ? [p] : []; });
// a quoted string or a JSX text run that holds the word
const VISIBLE = /(["'`>])([^"'`<>\n]*\b[Ff]undamentals?\b[^"'`<>\n]*)(?=["'`<])/g;
const ALLOWED = /^(fundamentals?|prism_fundamental|stock-fundamentals|cmp-fundamentals|\/premium\/fundamentals.*|premium\/fundamentals|\/fundamentals.*|\.\/pages\/Fundamentals|.*\$\{.*|= \{ fundamental:.*)$/;

describe("no 'Fundamental' on any page", () => {
  it("no visible string uses the word (only routes, ids and data keys keep it)", () => {
    const hits: string[] = [];
    for (const f of files(ROOT)) {
      const src = readFileSync(f, "utf8").split("\n").filter((l) => !/^\s*(\/\/|\/\*|\*)/.test(l)).join("\n");
      for (const m of src.matchAll(VISIBLE)) if (!ALLOWED.test(m[2].trim())) hits.push(`${f.replace(ROOT, "")}: ${m[2].trim().slice(0, 80)}`);
    }
    expect(hits).toEqual([]);
  });
});
