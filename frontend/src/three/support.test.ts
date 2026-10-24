import { afterEach, describe, expect, it, vi } from "vitest";
import { supports3d } from "./support";

afterEach(() => vi.unstubAllGlobals());

describe("supports3d", () => {
  it("is false without a browser window", () => { expect(supports3d()).toBe(false); });
  it("is false on a narrow screen", () => { vi.stubGlobal("window", { innerWidth: 390 }); expect(supports3d()).toBe(false); });
  it("is false when the visitor asked for less data", () => {
    vi.stubGlobal("window", { innerWidth: 1400 });
    vi.stubGlobal("navigator", { connection: { saveData: true }, hardwareConcurrency: 8 });
    expect(supports3d()).toBe(false);
  });
  it("is false on a weak device", () => {
    vi.stubGlobal("window", { innerWidth: 1400 });
    vi.stubGlobal("navigator", { hardwareConcurrency: 2 });
    expect(supports3d()).toBe(false);
    vi.stubGlobal("navigator", { hardwareConcurrency: 8, deviceMemory: 2 });
    expect(supports3d()).toBe(false);
  });
});

describe("markNo3d", () => {
  it("turns 3D off for the rest of the visit after a scene fails to start", async () => {
    vi.stubGlobal("window", { innerWidth: 1400 });
    vi.stubGlobal("navigator", { hardwareConcurrency: 8, deviceMemory: 8 });
    vi.stubGlobal("document", { createElement: () => ({ getContext: () => ({}) }) });
    vi.resetModules();
    const { markNo3d, supports3d: fresh } = await import("./support");
    expect(fresh()).toBe(true);
    markNo3d();
    expect(fresh()).toBe(false);
  });
});
