// Guard for the "see-through dialog" class of bug: every floating surface must paint an opaque colour from the shared overlay tokens.
// (The browser version, which opens each overlay and measures it, is e2e/overlay_guard.mjs.)
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = __dirname;
const files = readdirSync(dir).filter((f) => f.endsWith(".css"));
const css = (f: string) => readFileSync(join(dir, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const overlay = css("overlay.css");

/** The class list of the one opaque-surface rule in overlay.css. */
const surfaceRule = overlay.match(/:root:root :is\(([^{]*?)\)\s*\{\s*--s1: var\(--ov-surface\)[^}]*background: var\(--ov-surface\)/);
const covered = new Set((surfaceRule?.[1] ?? "").match(/\.[a-zA-Z][\w-]*/g)?.map((c) => c.slice(1)));
const BACKDROPS = ["scrim", "gs-scrim", "shell-scrim", "ipo-dr-bg", "qb-scrim", "sx-back", "gx-backdrop"];

/** Rules (outside overlay.css) that float (fixed/absolute with a z-index) and have a see-through background. */
function translucentFloaters() {
  const bad: { file: string; sel: string; why: string }[] = [];
  for (const f of files) {
    if (f === "overlay.css") continue;
    for (const m of css(f).matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
      const sel = m[1].trim(), body = m[2];
      if (!/position:\s*(fixed|absolute)/.test(body) || !/z-index:\s*(\d+)/.test(body)) continue;
      if (Number(body.match(/z-index:\s*(\d+)/)![1]) < 20) continue;
      const bg = body.match(/(?:^|;)\s*background(?:-color)?:\s*([^;]+)/)?.[1] ?? "";
      const alpha = bg.match(/rgba\([^)]*,\s*(0?\.\d+)\s*\)/);
      const glass = /backdrop-filter/.test(body) && !/var\(--ov-surface\)/.test(bg);
      const why = /transparent/.test(bg) && !/linear-gradient|radial-gradient/.test(bg) ? "transparent" : alpha && Number(alpha[1]) < 1 ? "rgba " + alpha[1] : glass ? "backdrop-filter without an opaque colour" : "";
      if (why) bad.push({ file: f, sel, why });
    }
  }
  return bad;
}

describe("overlay surfaces", () => {
  it("overlay.css is the last stylesheet main.tsx imports", () => {
    const main = readFileSync(join(dir, "..", "main.tsx"), "utf8");
    const css = [...main.matchAll(/import "\.\/styles\/([\w-]+\.css)";/g)].map((m) => m[1]);
    expect(css[css.length - 1]).toBe("overlay.css");
  });

  it("defines the shared tokens for both themes and a z-index scale", () => {
    for (const t of ["--ov-surface", "--ov-backdrop", "--ov-shadow", "--z-backdrop", "--z-modal", "--z-drawer", "--z-popover", "--z-toast", "--z-dropdown", "--z-tip"]) expect(overlay).toContain(t + ":");
    expect(overlay).toMatch(/:root\[data-theme="light"\]\s*\{[^}]*--ov-surface/);
  });

  it("the overlay tokens are never remapped by a hero, band or report (they must resolve on :root only)", () => {
    for (const f of files) {
      if (f === "overlay.css") continue;
      expect(css(f), f).not.toMatch(/--ov-(surface|backdrop|text)\s*:/);
    }
  });

  it("the main dialog, menu, popover and tooltip classes all use the opaque surface rule", () => {
    for (const c of ["alx-modal", "modal", "palette", "pop", "dl-menu", "nt-p", "ddm", "alx-dd", "toast", "alx-toast", "ai", "qb-drawer", "ld-tip", "chh-p", "cb-menu", "pk-m", "sf-panel", "etf-pop", "mf-cols-pop", "scr-colmenu", "mk-dd-m", "pm-sug", "etf-tray", "mf-tray", "wl-dock", "mtabs"]) expect(covered.has(c), c).toBe(true);
  });

  it("every translucent floating rule elsewhere belongs to a class overlay.css makes opaque", () => {
    const stray = translucentFloaters().filter((b) => !(b.sel.match(/\.[a-zA-Z][\w-]*/g) ?? []).some((c) => covered.has(c.slice(1)) || BACKDROPS.includes(c.slice(1))));
    expect(stray, JSON.stringify(stray, null, 1)).toEqual([]);
  });

  it("backdrops use the shared dim token", () => {
    for (const c of ["scrim", "gs-scrim", "shell-scrim", "ipo-dr-bg", "qb-scrim", "sx-back"]) expect(overlay).toContain(c);
    expect(overlay).toMatch(/background: var\(--ov-backdrop\)/);
  });

  it("has a no-backdrop-filter and a reduced-transparency fallback", () => {
    expect(overlay).toContain("@supports not");
    expect(overlay).toContain("prefers-reduced-transparency");
  });
});

describe("crisp dialogs", () => {
  it("centred dialogs are never placed with translate(-50%) and never blur their own content", () => {
    expect(overlay).toMatch(/:is\(\.alx-modal, \.modal\)\s*\{[^}]*margin: auto;[^}]*transform: none/);
    expect(overlay).toMatch(/:is\(\.palette, \.gs, \.plf-note\)\s*\{[^}]*transform: none[^}]*backdrop-filter: none/);
    expect(css("plflags.css")).not.toMatch(/\.plf-note\s*\{[^}]*backdrop-filter/);
    expect(css("plflags.css")).not.toMatch(/animation:[^;]*\bboth\b/);
  });
});
