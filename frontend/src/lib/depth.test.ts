import { afterEach, describe, expect, it, vi } from "vitest";
import { initDepth } from "./depth";

const listeners = () => { const add = vi.fn(), remove = vi.fn(); vi.stubGlobal("document", { addEventListener: add, removeEventListener: remove }); vi.stubGlobal("window", { addEventListener: add, removeEventListener: remove }); return add; };
afterEach(() => vi.unstubAllGlobals());

describe("initDepth", () => {
  it("does nothing without matchMedia (server, old browsers)", () => {
    expect(() => initDepth()()).not.toThrow();
  });
  it("does nothing on touch screens", () => {
    const add = listeners();
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    initDepth()();
    expect(add).not.toHaveBeenCalled();
  });
  it("does nothing for visitors who prefer reduced motion", () => {
    const add = listeners();
    vi.stubGlobal("matchMedia", () => ({ matches: true }));   // hover: hover matches, and so does reduced motion
    initDepth()();
    expect(add).not.toHaveBeenCalled();
  });
  it("listens once for a mouse user and removes its listeners when stopped", () => {
    const add = listeners();
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("hover: hover") }));
    const stop = initDepth();
    expect(add).toHaveBeenCalledWith("pointermove", expect.any(Function), { passive: true });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    expect(() => stop()).not.toThrow();
  });
});
