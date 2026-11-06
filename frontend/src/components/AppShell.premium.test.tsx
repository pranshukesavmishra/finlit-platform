// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SECTIONS } from "../lib/nav";

describe("Premium reports and the left Workspace rail (task #14)", () => {
  it("the left rail leaves Premium reports out", () => {
    expect(readFileSync(join(__dirname, "AppShell.tsx"), "utf8")).toContain('it.to !== "/premium/report"');
  });
  it("the header menu list still has Premium reports (only the left rail changed)", () => {
    expect(SECTIONS.find((x) => x.id === "research")!.groups.flatMap((g) => g.items).some((i) => i.to === "/premium/report")).toBe(true);
  });
});
