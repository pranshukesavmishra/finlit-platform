import { describe, expect, it } from "vitest";
import { codeNote, exchangeOf, exchangeTag, isBseCode, isBseOnly, subOf, titleOf } from "./companyLabel";

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
  it("the exchange comes from the row, else a numeric symbol means BSE; a BSE-only company is tagged with its code", () => {
    expect(exchangeOf({ symbol: "ABC", exchange: "NSE" })).toBe("NSE"); expect(exchangeOf({ symbol: "543914" })).toBe("BSE"); expect(exchangeOf({ symbol: "ABC" })).toBeNull();
    expect(exchangeTag({ symbol: "543914", name: "X Ltd", exchange: "BSE" })).toBe("BSE only, code 543914"); expect(exchangeTag({ symbol: "ABC", exchange: "NSE" })).toBeNull();
    expect(isBseOnly({ symbol: "ABC", exchange: "BSE" })).toBe(true); expect(isBseOnly({ symbol: "ABC" })).toBe(false);
  });
});
