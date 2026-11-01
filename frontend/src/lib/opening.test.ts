// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const source = readFileSync(resolve(process.cwd(), "public/opening-init.js"), "utf8");
let events: [string, EventListenerOrEventListenerObject][];
let reduced = false;
const run = () => { new Function(source)(); document.dispatchEvent(new Event("DOMContentLoaded")); };
beforeEach(() => {
  vi.useFakeTimers(); sessionStorage.clear(); events = []; reduced = false;
  history.replaceState(null, "", "/"); delete document.documentElement.dataset.introduction;
  document.body.innerHTML = '<section data-finlit-intro hidden role="dialog"><button>Skip introduction</button></section><div id="root"><main id="main"><h1>FinLit</h1></main></div>';
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: reduced, addEventListener: vi.fn() })));
  const add = window.addEventListener.bind(window);
  vi.spyOn(window, "addEventListener").mockImplementation((type, fn, options) => { if (fn) events.push([type, fn]); add(type, fn, options); });
});
afterEach(() => {
  window.dispatchEvent(new Event("pagehide"));
  for (const [type, fn] of events) window.removeEventListener(type, fn);
  vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals();
});
describe("opening introduction", () => {
  it("introduces the brand once and releases the page without waiting for data", () => {
    run(); expect(document.documentElement.dataset.introduction).toBe("on");
    expect(document.getElementById("root")!.inert).toBe(true);
    expect(document.activeElement?.textContent).toBe("Skip introduction");
    vi.advanceTimersByTime(1630);
    expect(document.documentElement.dataset.introduction).toBeUndefined();
    expect(document.getElementById("root")!.inert).toBe(false);
    expect(document.querySelector<HTMLElement>("[data-finlit-intro]")!.hidden).toBe(true);
    expect(sessionStorage.getItem("finlit-introduction-v1")).toBe("seen");
  });
  it.each(["/prism/RELIANCE", "/login", "/stocks/TCS"])("does not delay a direct visit to %s", (path) => {
    history.replaceState(null, "", path); run();
    expect(document.documentElement.dataset.introduction).toBeUndefined();
  });
  it("skips a returning visitor and respects reduced motion even for a demo replay", () => {
    sessionStorage.setItem("finlit-introduction-v1", "seen"); run();
    expect(document.documentElement.dataset.introduction).toBeUndefined();
    reduced = true; window.dispatchEvent(new Event("finlit:replay-introduction"));
    expect(document.documentElement.dataset.introduction).toBeUndefined();
  });
  it("Escape immediately releases the page and restores focus to its heading", () => {
    run(); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); vi.advanceTimersByTime(0);
    expect(document.getElementById("root")!.inert).toBe(false);
    expect(document.activeElement?.tagName).toBe("H1");
  });
  it("the skip button releases the page, and replay works after entry", () => {
    run(); document.querySelector<HTMLButtonElement>("[data-finlit-intro] button")!.click(); vi.advanceTimersByTime(0);
    expect(document.documentElement.dataset.introduction).toBeUndefined();
    vi.advanceTimersByTime(3000); window.dispatchEvent(new Event("finlit:replay-introduction"));
    expect(document.documentElement.dataset.introduction).toBe("on");
    vi.advanceTimersByTime(1630); expect(document.getElementById("root")!.inert).toBe(false);
  });
});
