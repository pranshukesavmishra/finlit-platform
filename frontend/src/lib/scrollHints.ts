/** Sideways scroll hints for tables and chip rows on phones.
 *  Sets data-edge on every `.tw` / `.h-scroll` box: "end" (more to the right), "start" (more to the left), "both" or "none".
 *  mobile.css turns that into a soft fade at the edge that still has columns, so people know the table scrolls.
 *  One capture-phase scroll listener and one debounced DOM observer: no per-table code. */
const SEL = ".tw, .h-scroll";

export function edgeOf(el: { scrollLeft: number; scrollWidth: number; clientWidth: number }): "none" | "start" | "end" | "both" {
  const max = el.scrollWidth - el.clientWidth;
  if (max <= 2) return "none";
  const left = el.scrollLeft > 2, right = el.scrollLeft < max - 2;
  return left && right ? "both" : left ? "start" : right ? "end" : "none";
}

function mark(el: HTMLElement) {
  const e = edgeOf(el);
  if (el.dataset.edge !== e) el.dataset.edge = e;
}

/** Number boxes open the phone's number pad: type="number" alone gives some phones a full keyboard, and iOS a pad with no decimal point. */
export function numberPads(root: ParentNode = document) {
  root.querySelectorAll<HTMLInputElement>('input[type="number"]:not([inputmode])').forEach((el) => {
    const step = el.getAttribute("step");
    el.setAttribute("inputmode", step && /^\d+$/.test(step) && (el.min === "" || +el.min >= 0) ? "numeric" : "decimal");
  });
}

/** Phones: a small "back to top" button after two screens of scrolling (CSS keeps it to phones and hides it while a sheet is open). */
function installToTop(): () => void {
  const b = document.createElement("button");
  b.type = "button"; b.className = "to-top"; b.setAttribute("aria-label", "Back to top"); b.tabIndex = -1;
  b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 14 6-6 6 6"/></svg>';
  b.addEventListener("click", () => window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
  document.body.appendChild(b);
  let on = false;
  // shown after two screens; hidden again at the very end, where it would sit on the last lines
  const tick = () => { const h = window.innerHeight, v = window.scrollY > h * 2 && window.scrollY + h < document.documentElement.scrollHeight - 160; if (v !== on) { on = v; b.classList.toggle("on", v); b.tabIndex = v ? 0 : -1; } };
  window.addEventListener("scroll", tick, { passive: true });
  return () => { window.removeEventListener("scroll", tick); b.remove(); };
}

export function installScrollHints(): () => void {
  if (typeof window === "undefined" || typeof MutationObserver === "undefined") return () => undefined;
  const all = () => { document.querySelectorAll<HTMLElement>(SEL).forEach(mark); numberPads(); };
  const unTop = installToTop();
  const onScroll = (ev: Event) => { const t = ev.target; if (t instanceof HTMLElement && t.matches(SEL)) mark(t); };
  let timer = 0;
  const later = () => { clearTimeout(timer); timer = window.setTimeout(all, 150); };
  const mo = new MutationObserver(later);
  mo.observe(document.body, { childList: true, subtree: true });
  document.addEventListener("scroll", onScroll, { capture: true, passive: true });
  window.addEventListener("resize", later, { passive: true });
  later();
  return () => { unTop(); mo.disconnect(); document.removeEventListener("scroll", onScroll, { capture: true }); window.removeEventListener("resize", later); clearTimeout(timer); };
}
