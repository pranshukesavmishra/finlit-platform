// The opening logo animation (task #36). The logo in index.html builds itself on a dark or light page for about 3 s; the site shows only after it has finished,
// so a visitor never sees it cut off by the page loading. It plays once per browser session (theme-init.js reads the flag); people who ask for less motion get the
// still logo and no wait. If the site is slower than the animation, the logo simply waits for it.
import { useEffect } from "react";

/** How long the logo needs, from the start of the page load, to be fully drawn and held for a moment (the loop fades it out only after 3.4 s). */
export const SPLASH_MIN_MS = 3200;
const FADE_MS = 400;

export function splashWait(sinceLoadMs: number, opts: { reduced?: boolean; seen?: boolean } = {}): number {
  return opts.reduced || opts.seen ? 0 : Math.max(0, SPLASH_MIN_MS - sinceLoadMs);
}

/** Fade the splash away once the animation has had its time, then remove it. Safe to call more than once. */
export function finishSplash(now: number = typeof performance !== "undefined" ? performance.now() : SPLASH_MIN_MS): void {
  const boot = typeof document !== "undefined" ? document.getElementById("ll-boot") : null;
  if (!boot || boot.dataset.leaving) return;
  boot.dataset.leaving = "1";
  let reduced = false;
  try { reduced = matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { /* no matchMedia: play it */ }
  const seen = document.documentElement.getAttribute("data-splash") === "seen";
  setTimeout(() => {
    boot.classList.add("ll-out");
    try { sessionStorage.setItem("finlit-splash", "1"); } catch { /* private mode: it plays again next time */ }
    setTimeout(() => boot.remove(), reduced ? 0 : FADE_MS);
  }, splashWait(now, { reduced, seen }));
}

/** Rendered once at the top of the app: when the site is ready, hand over from the opening animation. */
export function SplashDone() {
  useEffect(() => { finishSplash(); }, []);
  return null;
}
