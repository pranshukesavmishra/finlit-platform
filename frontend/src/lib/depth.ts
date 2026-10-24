// Pointer-driven 3D tilt for cards. One delegated listener for the whole site, no per-card code and no library: a card under the pointer
// gets --rx/--ry (tilt) and --tx/--ty (where the light sits), and styles/depth3d.css does the rest. Does nothing for touch screens,
// visitors who prefer reduced motion, or pages where the pointer is not hovering a card.
const SELECTOR = ".plan, .who-c, [data-tilt]";
const MAX_TILT = 6; // degrees, for a card about 380 px across; larger cards tilt less so their edges do not swing

export function initDepth(): () => void {
  if (typeof matchMedia === "undefined") return () => {};
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const calm = matchMedia("(prefers-reduced-motion: reduce)");
  if (!fine.matches || calm.matches) return () => {};

  let active: HTMLElement | null = null, raf = 0, ev: PointerEvent | null = null;
  const reset = (el: HTMLElement | null) => { if (el) { el.removeAttribute("data-depth"); el.style.removeProperty("--rx"); el.style.removeProperty("--ry"); } };
  const apply = () => {
    raf = 0;
    if (!active || !ev) return;
    const r = active.getBoundingClientRect();
    const k = Math.max(0.3, Math.min(1, 380 / Math.max(r.width, r.height))) * MAX_TILT;
    const x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
    active.style.setProperty("--rx", `${((0.5 - y) * 2 * k).toFixed(2)}deg`);
    active.style.setProperty("--ry", `${((x - 0.5) * 2 * k).toFixed(2)}deg`);
    active.style.setProperty("--tx", `${(x * 100).toFixed(1)}%`);
    active.style.setProperty("--ty", `${(y * 100).toFixed(1)}%`);
  };
  const move = (e: PointerEvent) => {
    const el = (e.target as Element | null)?.closest?.(SELECTOR) as HTMLElement | null;
    if (el !== active) { reset(active); active = el; if (el) el.setAttribute("data-depth", ""); }
    ev = e;
    if (active && !raf) raf = requestAnimationFrame(apply);
  };
  const leave = () => { reset(active); active = null; };
  document.addEventListener("pointermove", move, { passive: true });
  document.addEventListener("pointerleave", leave);
  window.addEventListener("blur", leave);
  return () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerleave", leave); window.removeEventListener("blur", leave); cancelAnimationFrame(raf); leave(); };
}
