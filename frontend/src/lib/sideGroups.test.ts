import { describe, expect, it } from "vitest";
import { ICONS } from "./icons";
import { MORE, SECTIONS } from "./nav";
import { SIDE_BADGES, badgeFor } from "./sideGroups";

// the rail shows the Research groups and the first group of More; "Learn and community" and "Company" are footer/header groups
const navTitles = [...SECTIONS, MORE].flatMap((s) => s.groups.map((g) => g.title).filter(Boolean)).filter((t) => t !== "Company") as string[];

describe("left rail group badges", () => {
  it("has a badge config for every titled group in nav.ts (Learn stands for 'Learn and community') and the rail's own groups", () => {
    for (const t of navTitles) expect(SIDE_BADGES[t] ?? SIDE_BADGES[t === "Learn and community" ? "Learn" : t], t).toBeTruthy();
    for (const t of ["Overview", "Find stocks", "Analyse a company", "Investment calculators", "Charts", "Markets", "News & events", "Funds", "Your workspace", "Gold dashboards", "Learn", "Account"]) expect(SIDE_BADGES[t], t).toBeTruthy();
  });
  it("gives every group an icon that exists and a palette token", () => {
    for (const [t, b] of Object.entries(SIDE_BADGES)) {
      expect(ICONS[b.icon], t + " icon").toBeTruthy();
      expect(b.tone, t + " tone").toMatch(/^--k[1-8]$/);
    }
  });
  it("falls back to a neutral badge for an unknown title", () => { expect(badgeFor("Nope").icon).toBe("grid"); });
});
