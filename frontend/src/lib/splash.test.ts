// @vitest-environment jsdom
// Task #36: the opening logo animation plays to its end before the site shows, once per browser session.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SPLASH_MIN_MS, finishSplash, splashWait } from "./splash";

const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");

describe("how long the opening animation holds the page", () => {
  it("waits for what is left of the animation, never less than none", () => {
    expect(splashWait(0)).toBe(SPLASH_MIN_MS);
    expect(splashWait(1200)).toBe(SPLASH_MIN_MS - 1200);
    expect(splashWait(SPLASH_MIN_MS)).toBe(0);
    expect(splashWait(9000)).toBe(0);                                  // a slow site: the logo does not wait any longer
  });
  it("does not wait for people who asked for less motion, or who saw it already this session", () => {
    expect(splashWait(100, { reduced: true })).toBe(0);
    expect(splashWait(100, { seen: true })).toBe(0);
  });
  it("holds the logo until it is drawn (the loop only starts to fade it after 3.4 s)", () => {
    expect(SPLASH_MIN_MS).toBeGreaterThanOrEqual(3000);
    expect(SPLASH_MIN_MS).toBeLessThan(3.4 * 1000);
  });
});

describe("finishSplash", () => {
  beforeEach(() => { vi.useFakeTimers(); document.body.innerHTML = '<div id="root"></div><div id="ll-boot"><div class="ll-splash"></div></div>'; sessionStorage.clear(); document.documentElement.removeAttribute("data-splash"); vi.stubGlobal("matchMedia", () => ({ matches: false })); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
  it("keeps the splash until the animation has played, then fades it and removes it, and remembers it for the session", () => {
    finishSplash(500);
    expect(document.getElementById("ll-boot")?.classList.contains("ll-out")).toBe(false);
    vi.advanceTimersByTime(SPLASH_MIN_MS - 500 - 1);
    expect(document.getElementById("ll-boot")?.classList.contains("ll-out")).toBe(false);          // not a moment early
    vi.advanceTimersByTime(2);
    expect(document.getElementById("ll-boot")?.classList.contains("ll-out")).toBe(true);
    expect(sessionStorage.getItem("finlit-splash")).toBe("1");
    vi.advanceTimersByTime(500);
    expect(document.getElementById("ll-boot")).toBeNull();
  });
  it("is safe to call twice and when there is no splash", () => {
    finishSplash(500); finishSplash(500); vi.advanceTimersByTime(10000);
    expect(document.getElementById("ll-boot")).toBeNull();
    expect(() => finishSplash(0)).not.toThrow();
  });
  it("goes straight away for reduced motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    finishSplash(10); vi.advanceTimersByTime(1);
    expect(document.getElementById("ll-boot")).toBeNull();
  });
});

describe("the splash in index.html", () => {
  it("sits beside the app root (React never replaces it) and is hidden at once for a session that saw it", () => {
    expect(html).toContain('<div id="root"></div>');
    expect(html).toMatch(/<div id="ll-boot"><div class="ll-splash">/);
    expect(readFileSync(resolve(process.cwd(), "public/theme-init.js"), "utf8")).toContain('data-splash');
    expect(readFileSync(resolve(process.cwd(), "src/styles/logo-loader.css"), "utf8")).toContain('html[data-splash="seen"] #ll-boot { display: none; }');
  });
  it("is centred on the screen", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles/logo-loader.css"), "utf8");
    expect(css).toMatch(/\.ll-splash \{[^}]*position: fixed; inset: 0;[^}]*place-items: center/);
  });
});
