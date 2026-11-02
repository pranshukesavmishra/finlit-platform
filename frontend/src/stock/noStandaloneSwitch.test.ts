// The stock report offers no Consolidated / Standalone switch: it said "publishes consolidated accounts only" while standalone figures were still loading, then showed them.
// The page still picks standalone by itself when a company's consolidated history is far shorter, and says so in words (Sections.tsx); the reader has no button for it.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const src = (f: string) => readFileSync(new URL(f, import.meta.url), "utf8");

describe("no standalone switch on the stock report", () => {
  it("neither the score card nor the financials section has the switch or its message", () => {
    for (const f of ["./ScoreCard.tsx", "./Sections.tsx", "./Hero.tsx", "./StockPage.tsx"]) {
      const t = src(f);
      expect(t, f).not.toContain("BasisToggle");
      expect(t, f).not.toContain("publishes");
      expect(t, f).not.toMatch(/>\s*Standalone\s*</);
      expect(t, f).not.toContain("Show consolidated instead");
    }
  });
  it("the automatic fallback to standalone is still explained in words", () => {
    expect(src("./Sections.tsx")).toContain("Showing standalone accounts");
  });
});
