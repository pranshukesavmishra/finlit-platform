// The screener filter panel's apply/clear row: it never scrolls or clips, and the apply button is a flat mint rectangle.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const tools = readFileSync(join(__dirname, "tools.css"), "utf8");
const rule = (sel: string) => tools.split("\n").find((l) => l.startsWith(sel)) ?? "";

describe("screener apply row", () => {
  it("wraps instead of scrolling and lets the text wrap instead of clipping", () => {
    expect(rule(".ss-actions {")).toMatch(/flex-wrap: wrap/);
    expect(rule(".ss-actions {")).toMatch(/overflow: visible/);
    expect(rule(".ss-actions .btn {")).toMatch(/min-width: 0/);
    expect(rule(".ss-actions .btn {")).toMatch(/white-space: normal/);
  });
  it("the apply button is a flat solid mint with dark text and no gradient glow", () => {
    const r = rule(":root:root .ss-actions .btn.primary {");
    expect(r).toMatch(/background: var\(--mint\)/);
    expect(r).toMatch(/background-image: none/);
    expect(r).toMatch(/color: var\(--on-mint\)/);
    expect(r).toMatch(/box-shadow: none/);
  });
});
