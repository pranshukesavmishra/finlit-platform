import { describe, expect, it, vi } from "vitest";
import { builtOn, fetchServerVersion, isStale, nextDelay, parseServerVersion, versionLine } from "./version";

describe("parseServerVersion", () => {
  it("accepts the build's file", () => expect(parseServerVersion({ version: "abc1234", builtAt: "2026-10-31T08:00:00Z" })).toEqual({ version: "abc1234", builtAt: "2026-10-31T08:00:00Z" }));
  it("rejects anything else", () => { for (const b of [null, "x", 5, {}, { version: 5 }, { version: "<html>" }, { version: "" }]) expect(parseServerVersion(b)).toBeNull(); });
});
describe("isStale", () => {
  it("is true only when versions differ", () => { expect(isStale("a1", { version: "b2", builtAt: "" })).toBe(true); expect(isStale("a1", { version: "a1", builtAt: "" })).toBe(false); });
  it("never nags a dev build or when the server answer is unknown", () => { expect(isStale("dev", { version: "b2", builtAt: "" })).toBe(false); expect(isStale("a1", null)).toBe(false); });
});
describe("nextDelay", () => {
  it("stays within +-20% of 5 minutes", () => { expect(nextDelay(() => 0)).toBe(240_000); expect(nextDelay(() => 1)).toBe(360_000); });
});
describe("fetchServerVersion", () => {
  const res = (ok: boolean, body: unknown) => ({ ok, json: async () => { if (body === "bad") throw new Error("not json"); return body; } }) as unknown as Response;
  it("bypasses caches and returns the version", async () => {
    const f = vi.fn().mockResolvedValue(res(true, { version: "x9", builtAt: "t" }));
    expect(await fetchServerVersion(f as unknown as typeof fetch, "/")).toEqual({ version: "x9", builtAt: "t" });
    expect(f.mock.calls[0][0]).toMatch(/^\/version\.json\?_=\d+$/); expect(f.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });
  it("returns null on 404, HTML, or a network error", async () => {
    expect(await fetchServerVersion(vi.fn().mockResolvedValue(res(false, {})) as unknown as typeof fetch, "/")).toBeNull();
    expect(await fetchServerVersion(vi.fn().mockResolvedValue(res(true, "bad")) as unknown as typeof fetch, "/")).toBeNull();
    expect(await fetchServerVersion(vi.fn().mockRejectedValue(new TypeError("offline")) as unknown as typeof fetch, "/")).toBeNull();
  });
});
describe("footer line", () => {
  it("formats the build date", () => { expect(builtOn("2026-10-31T08:00:00Z")).toBe("31 Oct 2026"); expect(builtOn("nope")).toBe(""); });
  it("reads like the support line", () => { expect(versionLine("abc1234", "2026-10-31T08:00:00Z")).toBe("Version abc1234 · built 31 Oct 2026"); expect(versionLine("dev", "")).toBe("Version dev"); });
});
