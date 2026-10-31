// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UI_PREFIX, isBool, isBoolMap, isIdList, isNumberIn, loadUi, purgeLegacy, removeUi, saveUi } from "./persist";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("loadUi / saveUi", () => {
  it("round-trips a versioned value", () => { expect(saveUi("k", 1, { a: true })).toBe(true); expect(JSON.parse(localStorage.getItem(UI_PREFIX + "k")!)).toEqual({ v: 1, data: { a: true } }); expect(loadUi("k", 1, isBoolMap, {})).toEqual({ a: true }); });
  it("returns the fallback when nothing is saved", () => expect(loadUi("none", 1, isBool, false)).toBe(false));
  it("discards corrupt JSON and removes it", () => { localStorage.setItem(UI_PREFIX + "k", "{not json"); expect(loadUi("k", 1, isBool, true)).toBe(true); expect(localStorage.getItem(UI_PREFIX + "k")).toBeNull(); });
  it("discards an old version", () => { localStorage.setItem(UI_PREFIX + "k", JSON.stringify({ v: 1, data: true })); expect(loadUi("k", 2, isBool, false)).toBe(false); expect(localStorage.getItem(UI_PREFIX + "k")).toBeNull(); });
  it("discards an unversioned legacy shape (raw '1', bare array, bare object)", () => {
    for (const raw of ["1", "true", "[\"a\"]", "{\"a\":true}", "null", "42"]) { localStorage.setItem(UI_PREFIX + "k", raw); expect(loadUi("k", 1, isBool, false)).toBe(false); expect(localStorage.getItem(UI_PREFIX + "k")).toBeNull(); }
  });
  it("discards a value of the right version whose data fails validation", () => { saveUi("k", 1, "yes"); expect(loadUi("k", 1, isBool, false)).toBe(false); expect(localStorage.getItem(UI_PREFIX + "k")).toBeNull(); });
  it("never throws when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(loadUi("k", 1, isBool, true)).toBe(true); expect(saveUi("k", 1, true)).toBe(false); expect(() => removeUi("k")).not.toThrow(); expect(() => purgeLegacy(["a"], ["b"])).not.toThrow();
  });
  it("never throws when touching localStorage itself throws", () => {
    const d = Object.getOwnPropertyDescriptor(window, "localStorage")!;
    Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("SecurityError"); } });
    try { expect(loadUi("k", 1, isBool, true)).toBe(true); expect(saveUi("k", 1, true)).toBe(false); } finally { Object.defineProperty(window, "localStorage", d); }
  });
});
describe("validators", () => {
  it("isBoolMap keeps only booleans and rejects non-objects", () => { expect(isBoolMap({ a: true, b: "x", c: 1, d: false })).toEqual({ a: true, d: false }); expect(isBoolMap([true])).toBeNull(); expect(isBoolMap(null)).toBeNull(); });
  it("isIdList drops unknown ids and rejects an empty result", () => { const f = isIdList<string>(new Set(["a", "b"])); expect(f(["a", "zz", 3, "b"])).toEqual(["a", "b"]); expect(f(["zz"])).toBeNull(); expect(f("a")).toBeNull(); });
  it("isNumberIn bounds a number", () => { const f = isNumberIn(0, 10); expect(f(5)).toBe(5); expect(f(0)).toBe(0); expect(f(11)).toBeNull(); expect(f(NaN)).toBeNull(); expect(f("5")).toBeNull(); });
});
describe("purgeLegacy", () => {
  it("removes listed keys and prefixes only", () => { localStorage.setItem("finlit-side", "1"); localStorage.setItem("finlit.side.screener", "0"); localStorage.setItem("finlit-theme", "dark"); purgeLegacy(["finlit-side"], ["finlit.side."]); expect(localStorage.getItem("finlit-side")).toBeNull(); expect(localStorage.getItem("finlit.side.screener")).toBeNull(); expect(localStorage.getItem("finlit-theme")).toBe("dark"); });
});
