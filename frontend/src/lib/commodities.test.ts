import { describe, expect, it } from "vitest";
import { convert, direction, group, inr, istTime, signedPct, usd } from "./commodities";

describe("digit grouping (text in, text out, no floats)", () => {
  it("groups in lakhs and crores for rupees and in thousands for dollars", () => {
    expect(group("14163329")).toBe("1,41,63,329");
    expect(group("142500")).toBe("1,42,500");
    expect(group("999")).toBe("999");
    expect(group("1000")).toBe("1,000");
    expect(group("14250.00")).toBe("14,250.00");
    expect(group("4032.30", false)).toBe("4,032.30");
    expect(group("14163329", false)).toBe("14,163,329");
    expect(inr("141633")).toBe("₹1,41,633");
    expect(inr("-5.50")).toBe("−₹5.50");
    expect(usd("4032.30")).toBe("$4,032.30");
    expect(usd("-5.50")).toBe("−$5.50");
  });
  it("never invents a number from junk", () => {
    for (const v of [null, undefined, "", "abc", "1e5", "NaN", "12,3"]) expect(inr(v as string)).toBe("—");
    expect(group("0.000")).toBe("0.000");
  });
  it("keeps the server's digits exactly: 13062.50 stays 13062.50 and 0.615 is not re-rounded", () => {
    expect(inr("13062.50")).toBe("₹13,062.50");
    expect(group("0.615")).toBe("0.615");
  });
});

describe("change", () => {
  it("shows an arrow and a sign, never colour alone", () => {
    expect(signedPct("0.62")).toBe("▲ +0.62%");
    expect(signedPct("-0.40")).toBe("▼ −0.40%");
    expect(signedPct("0.00")).toBe("0.00%");
    expect(signedPct("-0.00")).toBe("0.00%");
    expect(signedPct(null)).toBe("—");
    expect(direction("0.62")).toBe("up");
    expect(direction("-0.4")).toBe("down");
    expect(direction("0.00")).toBe("flat");
    expect(direction(null)).toBe("flat");
  });
});

describe("times are shown in Indian time", () => {
  it("21:41:58 IST from a UTC instant", () => {
    expect(istTime("2026-10-23T16:11:58+00:00")).toBe("21:41:58");
    expect(istTime("2026-10-23T21:41:58+05:30")).toBe("21:41:58");
    expect(istTime(null)).toBe("—");
    expect(istTime("junk")).toBe("—");
  });
});

describe("unit converter is exact", () => {
  // Expected values worked out independently with rational arithmetic: 1 tola = 11.6638038 g, 1 troy oz = 31.1034768 g (480 and 180 grains of 0.06479891 g).
  it("grams, tola, troy ounce, kilogram, 10 g and 8 g", () => {
    expect(convert("1", "tola", "g")).toBe("11.6638");
    expect(convert("10", "tola", "g", 6)).toBe("116.638038");
    expect(convert("1", "toz", "g", 7)).toBe("31.1034768");
    expect(convert("1", "toz", "tola")).toBe("2.6667");           // 480 / 180 grains = 8 / 3
    expect(convert("1", "kg", "tola")).toBe("85.7353");
    expect(convert("1", "kg", "toz")).toBe("32.1507");
    expect(convert("8", "g", "g8")).toBe("1.0000");
    expect(convert("1", "g10", "g8")).toBe("1.2500");
    expect(convert("100", "g", "kg")).toBe("0.1000");
  });
  it("rounds half up on the exact value, not on a binary float", () => {
    expect(convert("1.005", "g", "g", 2)).toBe("1.01");
    expect(convert("2.675", "g", "g", 2)).toBe("2.68");
    expect(convert("0", "g", "kg")).toBe("0.0000");
    expect(convert("1.5", "g", "g", 0)).toBe("2");
  });
  it("accepts Indian grouping and refuses junk", () => {
    expect(convert("1,00,000", "g", "kg", 2)).toBe("100.00");
    for (const v of ["", "abc", "-1", "1e3", "1.2.3", "1234567890123456"]) expect(convert(v, "g", "kg")).toBeNull();
  });
  it("round-trips a tola through grams", () => {
    expect(convert(convert("25", "tola", "g", 7)!, "g", "tola", 4)).toBe("25.0000");
  });
});
