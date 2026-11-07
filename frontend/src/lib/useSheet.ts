import { useEffect, useRef, useState } from "react";

/** Shared behaviour for anything that slides over the page on a phone (menus, drawers, filter sheets):
 *   - the page behind does not scroll while it is open (counted, so two open sheets unlock only when both close),
 *   - Escape closes it,
 *   - the phone's Back button / back-swipe closes it instead of leaving the page.
 *  For Back to work, opening adds one history entry for the same URL; closing by any other way (X, backdrop, Escape) removes it again.
 *  If the sheet closed because a link inside it navigated, the new page's entry is already on top, so nothing is removed. */
let locks = 0, saved = "", savedPad = "";
export function lockBody(): () => void {
  if (locks++ === 0) {
    const b = document.body, gap = window.innerWidth - document.documentElement.clientWidth;
    saved = b.style.overflow; savedPad = b.style.paddingRight;
    b.style.overflow = "hidden";
    if (gap > 0) b.style.paddingRight = `${gap}px`;   // no jump where a desktop scrollbar disappears
  }
  let done = false;
  return () => { if (done) return; done = true; if (--locks === 0) { document.body.style.overflow = saved; document.body.style.paddingRight = savedPad; } };
}
export const lockCount = () => locks;

const KEY = "finlitSheet";

export function useSheet(open: boolean, close: () => void, opts: { lock?: boolean; back?: boolean; focus?: () => HTMLElement | null | undefined } = {}) {
  const { lock = true, back = true } = opts;
  const focusRef = useRef(opts.focus);
  focusRef.current = opts.focus;
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!open) return;
    const unlock = lock ? lockBody() : () => undefined;
    // focus moves into the sheet (never onto a text box: that would pop the phone keyboard up) and returns to the opener after
    const opener = document.activeElement as HTMLElement | null;
    const f = window.setTimeout(() => focusRef.current?.()?.focus({ preventScroll: true }), 30);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    const id = Math.random().toString(36).slice(2);
    let popped = false;
    const onPop = () => { popped = true; closeRef.current(); };
    let pushed = false;
    // pushed a tick later: React's development double-mount opens and closes at once, and must not leave a stray entry
    const t = back ? window.setTimeout(() => {
      try { history.pushState({ ...(history.state || {}), [KEY]: id }, ""); pushed = true; } catch { /* sandboxed frame */ }
      window.addEventListener("popstate", onPop);
    }, 0) : 0;
    return () => {
      unlock();
      clearTimeout(f);
      if (opener && opener.isConnected && opener !== document.body) opener.focus({ preventScroll: true });
      document.removeEventListener("keydown", onKey);
      if (back) {
        clearTimeout(t);
        window.removeEventListener("popstate", onPop);
        // closed by X, backdrop or Escape: take our extra entry off again so Back does not need two presses
        if (pushed && !popped && history.state && history.state[KEY] === id) history.back();
      }
    };
  }, [open, lock, back]);
}

/** True while the screen is phone or tablet width (the drawer layouts); follows rotation and window resizes. */
export function useNarrow(query = "(max-width: 960px)"): boolean {
  const [m, setM] = useState(() => typeof matchMedia === "function" && matchMedia(query).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(query), on = () => setM(mq.matches);
    on(); mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [query]);
  return m;
}
