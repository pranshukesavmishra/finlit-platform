import { afterEach, describe, expect, it, vi } from "vitest";
import { isChunkError, reloadOnce, withRetry } from "./resilience";

const store = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe("isChunkError", () => {
  it("recognises a page file that would not load, in every browser's words", () => {
    for (const m of ["Failed to fetch dynamically imported module: https://x/assets/A-1.js", "error loading dynamically imported module", "Importing a module script failed.", "Loading chunk 12 failed.", "Unable to preload CSS for /assets/x.css"])
      expect(isChunkError(new TypeError(m))).toBe(true);
    expect(isChunkError(new Error("Cannot read properties of undefined (reading 'map')"))).toBe(false);
    expect(isChunkError(null)).toBe(false);
  });
});
describe("withRetry", () => {
  it("tries a failed page file again before giving up, and returns it once it loads", async () => {
    const f = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch dynamically imported module")).mockResolvedValueOnce({ default: 1 });
    expect(await withRetry(f, [1, 1])()).toEqual({ default: 1 }); expect(f).toHaveBeenCalledTimes(2);
  });
  it("does not retry an error in the page's own code", async () => {
    const f = vi.fn().mockRejectedValue(new Error("boom"));
    await expect(withRetry(f, [1, 1])()).rejects.toThrow("boom"); expect(f).toHaveBeenCalledTimes(1);
  });
  it("throws (to the error message) when the file stays missing and a reload was just done", async () => {
    const ss = store(); ss.setItem("finlit-reload-at", String(Date.now())); vi.stubGlobal("sessionStorage", ss); vi.stubGlobal("location", { reload: vi.fn() });
    const f = vi.fn().mockRejectedValue(new TypeError("Failed to fetch dynamically imported module"));
    await expect(withRetry(f, [1])()).rejects.toThrow(/dynamically/); expect(f).toHaveBeenCalledTimes(2);
  });
});
describe("reloadOnce", () => {
  it("reloads at most once every 30 seconds", () => {
    const reload = vi.fn(); vi.stubGlobal("location", { reload }); vi.stubGlobal("sessionStorage", store());
    expect(reloadOnce(1_000_000)).toBe(true); expect(reloadOnce(1_010_000)).toBe(false); expect(reloadOnce(1_031_000)).toBe(true); expect(reload).toHaveBeenCalledTimes(2);
  });
});
