import { describe, expect, it } from "vitest";
import { age, around, compact, count, istTime, matchUnderlyings, price, signedNum, strikeText, ticks, type Row } from "./options";

const row = (strike: number, atm = false): Row => ({ strike, ce: null, pe: null, atm, ceItm: false, peItm: false });

describe("option chain formatting", () => {
  it("never shows 0 for an unknown value", () => {
    expect(price(null)).toBe("—");
    expect(count(null)).toBe("—");
    expect(signedNum(undefined)).toBe("—");
    expect(compact(null)).toBe("—");
    expect(price(0.05)).toBe("0.05");
    expect(count(0)).toBe("0");                 // a real zero OI is shown as 0
  });
  it("counts in units or exact lots", () => {
    expect(count(3786445)).toBe("37,86,445");
    expect(count(3786445, "lots", 65)).toBe("58,253");          // 3,786,445 ÷ 65, a whole number of lots
    expect(count(100, "lots", 65)).toBe("1.54");                // not whole: shown, not rounded away
    expect(count(-650, "lots", 65, true)).toBe("−10");
    expect(count(650, "lots", 65, true)).toBe("+10");
    expect(count(650, "lots", null)).toBe("650");               // no lot size: stays in units
  });
  it("strikes, prices and signed changes", () => {
    expect(strikeText(25650)).toBe("25,650");
    expect(strikeText(1422.5)).toBe("1,422.5");
    expect(price(-110.85)).toBe("−110.85");
    expect(signedNum(31.35)).toBe("+31.35");
    expect(signedNum(0)).toBe("0.00");
    expect(compact(37864450)).toBe("3.79 Cr");
    expect(compact(3786445)).toBe("37.86 L");
    expect(compact(-4500)).toBe("−4.5 K");
  });
  it("time in IST whatever the reader's zone, and age in words", () => {
    expect(istTime("2026-10-23T15:29:58+05:30")).toMatch(/23 Oct 2026, 15:29:58 IST/);
    expect(age(12)).toBe("12 s");
    expect(age(250)).toBe("4 min");
    expect(age(3 * 3600 + 5)).toBe("3 h");
    expect(age(86400)).toBe("1 day");
    expect(age(3 * 86400)).toBe("3 days");
  });
});

describe("strike window and search", () => {
  const rows = [100, 105, 110, 115, 120, 125, 130].map((k) => row(k, k === 115));
  it("keeps n strikes either side of ATM", () => {
    expect(around(rows, 115, 2).map((r) => r.strike)).toEqual([105, 110, 115, 120, 125]);
    expect(around(rows, 100, 2).map((r) => r.strike)).toEqual([100, 105, 110]);
    expect(around(rows, 115, 0)).toHaveLength(7);
    expect(around(rows, null, 2)).toHaveLength(7);
    expect(around(rows, 999, 2)).toHaveLength(7);
  });
  it("finds underlyings by key or name, exact key first", () => {
    const list = [{ key: "BANKNIFTY", name: "Nifty Bank" }, { key: "NIFTY", name: "Nifty 50" }, { key: "FINNIFTY", name: "Nifty Financial Services" },
      { key: "RELIANCE", name: "Reliance Industries" }];
    expect(matchUnderlyings(list, "nifty").map((u) => u.key)).toEqual(["NIFTY", "BANKNIFTY", "FINNIFTY"]);
    expect(matchUnderlyings(list, "reli").map((u) => u.key)).toEqual(["RELIANCE"]);
    expect(matchUnderlyings(list, "industries").map((u) => u.key)).toEqual(["RELIANCE"]);
    expect(matchUnderlyings(list, "").length).toBe(4);
  });
  it("axis ticks are round and cover the data", () => {
    expect(ticks(0, 3786445)).toEqual([0, 1000000, 2000000, 3000000, 4000000]);
    const t = ticks(-500, 3384225);
    expect(t[0]).toBeLessThanOrEqual(-500);
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(3384225);
    expect(ticks(0, 0)).toEqual([0]);
  });
});
