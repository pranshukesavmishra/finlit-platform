import { beforeEach, describe, expect, it } from "vitest";
import { recents } from "./mycompanies";

const store = new Map<string, string>();
(globalThis as unknown as { localStorage: Storage }).localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k), clear: () => store.clear(), key: () => null, length: 0 };

describe("recents (companies opened in this browser)", () => {
  beforeEach(() => localStorage.clear());
  it("puts the newest first, keeps one entry per company and caps the list", () => {
    recents.add("tcs"); recents.add("INFY"); recents.add("TCS");
    expect(recents.get()).toEqual(["TCS", "INFY"]);
    for (let i = 0; i < 60; i++) recents.add("S" + i);
    expect(recents.get().length).toBe(40);
    expect(recents.get()[0]).toBe("S59");
  });
  it("survives junk in storage", () => {
    localStorage.setItem("finlit.recents", "{not json"); expect(recents.get()).toEqual([]);
    localStorage.setItem("finlit.recents", JSON.stringify([1, "A"])); expect(recents.get()).toEqual(["A"]);
  });
});
