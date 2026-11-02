import { describe, expect, it } from "vitest";
import { codeNote, isBseCode, subOf, titleOf } from "./companyLabel";

describe("company label", () => {
  it("a BSE-only company is titled by its name, and the name is not repeated underneath", () => {
    const r = { symbol: "526775", name: "Valiant Communications Ltd" };
    expect(isBseCode(r.symbol)).toBe(true); expect(titleOf(r)).toBe("Valiant Communications Ltd"); expect(subOf(r)).toBeNull(); expect(codeNote(r)).toBeUndefined();
  });
  it("with no name on file the code stays, with its reason", () => {
    const r = { symbol: "530001", name: null };
    expect(titleOf(r)).toBe("530001"); expect(subOf(r)).toBeNull(); expect(codeNote(r)).toMatch(/name is not in our data/);
  });
  it("an NSE symbol is unchanged, with its name underneath", () => {
    const r = { symbol: "NETWEB", name: "Netweb Technologies India Ltd" };
    expect(isBseCode(r.symbol)).toBe(false); expect(titleOf(r)).toBe("NETWEB"); expect(subOf(r)).toBe("Netweb Technologies India Ltd"); expect(codeNote(r)).toBeUndefined();
    expect(isBseCode("M&M")).toBe(false); expect(isBseCode("BAJAJ-AUTO")).toBe(false); expect(isBseCode("3MINDIA")).toBe(false);
  });
});
