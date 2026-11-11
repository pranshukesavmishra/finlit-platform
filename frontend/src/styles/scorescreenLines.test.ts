import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "src/styles/scorescreen.css"), "utf8");

describe("Basic and Advanced score screener tables: a line between every two columns", () => {
  it("draws a vertical rule between all neighbouring cells, in the heading row and in every body row, in the strong border colour", () => {
    expect(css).toMatch(/\.sx-t thead tr:not\(\.gh\) th \+ th, \.sx-t tbody td \+ td \{ border-left: 1px solid var\(--border-strong, var\(--border\)\); \}/);
  });
  it("keeps the heavier rule where a score group starts (Basic at column 7, Advanced at columns 7 and 12)", () => {
    expect(css).toMatch(/th:nth-child\(7\), \.sx-t tbody td:nth-child\(7\) \{ border-left: 2px solid/);
    expect(css).toMatch(/th:nth-child\(12\), [^{]*td:nth-child\(12\) \{ border-left: 2px solid/);
  });
});
