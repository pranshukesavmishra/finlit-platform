// "ph" is the page-header card (padding, border, rounded corners: styles/page-header.css). The fund and ETF pickers used "ph" for their grey placeholder text, so
// the placeholder was drawn as a page-header card inside the button and overlapped the label (owner's item 8, Nov 2026). Only the page header may use it.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = new URL("..", import.meta.url).pathname;
const files = (d: string): string[] => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? files(p) : /\.tsx$/.test(n) && !/\.test\./.test(n) ? [p] : []; });

describe("the page-header class is not reused", () => {
  it("no component but the page header puts the class 'ph' on an element", () => {
    const token = /className="(?:[^"\n]*\s)?ph(?:\s[^"\n]*)?"|"ph"|"ph "/;      // className="... ph ...", or the string "ph" used as a class
    const users = files(ROOT).filter((f) => token.test(readFileSync(f, "utf8")));
    expect(users.map((f) => f.replace(ROOT, ""))).toEqual(["components/PageHeader.tsx"]);
  });
});
