import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SectionsMenu } from "./SectionsMenu";
import { NAV, columnsOf, moveIndex, navFor } from "../lib/sectionNav";

describe("All sections panel", () => {
  it("lists every section with its icon, name and hint, and marks the current one", () => {
    const h = renderToStaticMarkup(<SectionsMenu items={navFor(true)} active="ratios" onPick={() => {}} />);
    for (const [id, label, , hint] of NAV) { expect(h).toContain(`data-s="${id}"`); expect(h).toContain(`<b>${label.replace("&", "&amp;")}</b>`); expect(h).toContain(hint); }
    expect(h).toContain("All sections");
    expect(h.match(/aria-current="true"/g)).toHaveLength(1);
    expect(h).toMatch(/data-s="ratios"[^>]*aria-current|aria-current="true"[^>]*data-s="ratios"|class="sx-i on"[^>]*aria-current="true"[^>]*data-s="ratios"/);
  });
  it("is closed to start with and lists Leadership only when it is shown", () => {
    const h = renderToStaticMarkup(<SectionsMenu items={navFor(false)} active={null} onPick={() => {}} />);
    expect(h).toContain("hidden"); expect(h).toContain('aria-expanded="false"'); expect(h).not.toContain('data-s="leadership"'); expect(h).toContain('data-s="plans"');
    expect(navFor(false)).toHaveLength(13); expect(navFor(true)).toHaveLength(14);
  });
});

describe("panel keyboard rule", () => {
  it("arrows step through a 3-column grid; Up and Down move a row; Home and End jump", () => {
    expect(moveIndex(0, "ArrowRight", 14, 3)).toBe(1); expect(moveIndex(13, "ArrowRight", 14, 3)).toBe(0); expect(moveIndex(0, "ArrowLeft", 14, 3)).toBe(13);
    expect(moveIndex(1, "ArrowDown", 14, 3)).toBe(4); expect(moveIndex(12, "ArrowDown", 14, 3)).toBe(12); expect(moveIndex(4, "ArrowUp", 14, 3)).toBe(1); expect(moveIndex(1, "ArrowUp", 14, 3)).toBe(1);
    expect(moveIndex(5, "Home", 14, 3)).toBe(0); expect(moveIndex(5, "End", 14, 3)).toBe(13); expect(moveIndex(5, "x", 14, 3)).toBe(5); expect(moveIndex(0, "ArrowDown", 0, 3)).toBe(-1);
    expect(moveIndex(0, "ArrowDown", 14, 1)).toBe(1);
  });
  it("reads the column count from the computed grid", () => { expect(columnsOf("250px 250px 250px")).toBe(3); expect(columnsOf("")).toBe(1); });
});
