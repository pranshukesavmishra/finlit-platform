import { describe, expect, it } from "vitest";
import { PALETTE_IDS, PALETTES, isPalette, paletteVars } from "./palettes";

describe("palettes", () => {
  it("the default palette leaves the stylesheet untouched", () => { expect(paletteVars("gold", "dark")).toEqual({}); expect(paletteVars("gold", "light")).toEqual({}); });
  it("every other palette sets the accent for both themes and for the dark bands", () => {
    for (const id of PALETTE_IDS.filter((p) => p !== "gold")) for (const theme of ["dark", "light"] as const) {
      const v = paletteVars(id, theme);
      expect(v["--gold"]).toMatch(/^#[0-9A-Fa-f]{6}$/); expect(v["--dk-gold"]).toBeTruthy(); expect(v["--lt-gold"]).toBeTruthy(); expect(v["--gold-soft"]).toMatch(/^rgba\(/);
    }
  });
  it("surface palettes recolour backgrounds and text in both themes", () => {
    for (const id of ["graphite", "midnight", "emerald"] as const) for (const theme of ["dark", "light"] as const) { const v = paletteVars(id, theme); expect(v["--bg"]).toBeTruthy(); expect(v["--text"]).toBeTruthy(); expect(v["--s1"]).toBeTruthy(); }
  });
  it("accepts only known ids (the server validates the same list)", () => { expect(isPalette("midnight")).toBe(true); expect(isPalette("neon")).toBe(false); expect(isPalette(undefined)).toBe(false); });
  it("each palette is described for the picker", () => { for (const id of PALETTE_IDS) { expect(PALETTES[id].label.length).toBeGreaterThan(2); expect(PALETTES[id].swatch).toHaveLength(3); } });
});
