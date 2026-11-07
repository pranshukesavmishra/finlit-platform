// Task #34: the company report has no "Historical trend" section any more, and the section numbers run 01 to 15 with no gap.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { NAV } from "../lib/sectionNav";

const files = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? files(p) : /\.tsx$/.test(n) && !/\.test\./.test(n) ? [p] : []; });
const numbered = () => {
  const out: [number, string][] = [];
  for (const f of files(__dirname)) for (const m of readFileSync(f, "utf8").matchAll(/\bno(?:=|:\s*)"(\d{2}) · ([^"]+)"/g)) out.push([Number(m[1]), m[2]]);
  return out;
};

describe("company report numbering", () => {
  it("has the sections 01 to 15, each number once, in one unbroken run", () => {
    const nums = [...new Set(numbered().map(([n]) => n))].sort((a, b) => a - b);
    expect(nums).toEqual(Array.from({ length: 15 }, (_, i) => i + 1));
  });
  it("no longer has the Historical trend section or its menu entry", () => {
    expect(numbered().some(([, t]) => /Historical trend/i.test(t))).toBe(false);
    expect(NAV.some(([id]) => id === "history")).toBe(false);
    expect(readFileSync(join(__dirname, "Sections3.tsx"), "utf8")).not.toContain("Margins and returns against their own history");
  });
  it("Ownership is 10, Peers 11, Gold insights 12, Segments 13, Dividends 14 and Pros & cons 15", () => {
    const m = new Map(numbered().map(([n, t]) => [t.split(" · ")[0], n]));
    expect(m.get("Ownership")).toBe(10); expect(m.get("Peers")).toBe(11); expect(m.get("Gold insights")).toBe(12);
    expect(m.get("Segments")).toBe(13); expect(m.get("Dividends & events")).toBe(14); expect(m.get("Pros, cons & Prism history")).toBe(15);
  });
});
