// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { isBool, isFlags, isNum, readUi, writeUi } from "./persist";

beforeEach(() => localStorage.clear());

describe("versioned UI state", () => {
  it("round-trips a current-version value", () => {
    writeUi("k", 620);
    expect(readUi("k", isNum, 330)).toBe(620);
  });
  it("discards what an older release wrote (bare values) and removes it", () => {
    localStorage.setItem("k", "620");
    expect(readUi("k", isNum, 330)).toBe(330);
    expect(localStorage.getItem("k")).toBeNull();
  });
  it("discards damaged JSON, unknown versions and wrong types", () => {
    for (const raw of ["{{", "null", "[]", JSON.stringify({ v: 9, d: true }), JSON.stringify({ v: 2, d: "yes" })]) {
      localStorage.setItem("k", raw);
      expect(readUi("k", isBool, false)).toBe(false);
    }
    localStorage.setItem("g", JSON.stringify({ v: 2, d: [1] }));
    expect(readUi("g", isFlags, {})).toEqual({});
  });
});
