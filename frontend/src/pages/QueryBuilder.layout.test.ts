// The Rules panel opens ABOVE the query box it explains, not below it (owner, Nov 2026).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("query builder layout", () => {
  it("the rules panel comes before the query box", () => {
    const src = readFileSync(new URL("./QueryBuilder.tsx", import.meta.url), "utf8");
    const rules = src.indexOf("<QueryRules "), box = src.indexOf('className="card qb-ed"');
    expect(rules).toBeGreaterThan(0); expect(box).toBeGreaterThan(0);
    expect(rules).toBeLessThan(box);
  });
});
