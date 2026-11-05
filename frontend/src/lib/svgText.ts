// Chart text on the type scale at the size the reader actually sees.
// SVG text is sized in the chart's own units (viewBox), and the chart is then scaled to its box: an 11-unit label in a 720-unit-wide chart
// drawn 332px wide on a phone is 5px on screen, and the same label in a chart stretched to 1170px is 18px. The scale (docs/TYPE-SCALE.md)
// is about on-screen size, so each <text> is set to its declared size snapped to the scale (never below 11px), divided by the chart's scale.

export const SCALE = [11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 40];

/** The scale size nearest to `px` as drawn on screen, never below 11. Display sizes (44px and up) are left alone. */
export function nearestScale(px: number): number {
  if (px >= 44) return px;
  return SCALE.reduce((best, s) => (Math.abs(s - px) < Math.abs(best - px) ? s : best), SCALE[0]);
}

/** The font size, in chart units, that draws at the label's scale size on screen: the declared size snapped to the scale (11 stays 11, 10.5 becomes 11),
 *  whatever the chart's scale `k` (screen px per chart unit). A label is the same size on a phone and on a wide chart. */
export function chartFontSize(declared: number, k: number): number {
  if (!(k > 0) || !(declared > 0)) return declared;
  return Math.round((nearestScale(declared) / k) * 100) / 100;
}

const original = new WeakMap<SVGTextContentElement, number>();
const watched = new WeakSet<SVGSVGElement>();
let ro: ResizeObserver | null = null;
let queued = false;

function fit(svg: SVGSVGElement) {
  const m = svg.getScreenCTM();
  if (!m) return;
  const k = Math.hypot(m.a, m.b);
  if (!(k > 0)) return;
  let grown = false;
  svg.querySelectorAll<SVGTextContentElement>("text").forEach((t) => {
    let o = original.get(t);
    if (o == null) {
      t.style.removeProperty("font-size");
      o = parseFloat(getComputedStyle(t).fontSize);
      if (!(o > 0)) return;
      original.set(t, o);
    }
    const want = chartFontSize(o, k);
    if (want > o + 0.5) grown = true;
    const have = parseFloat(t.style.fontSize);
    if (Math.abs(want - o) < 0.01) { if (t.style.fontSize) t.style.removeProperty("font-size"); }
    else if (!(Math.abs(have - want) < 0.01)) t.style.fontSize = want + "px";
  });
  // Larger labels (on phones) can need a little more room than the chart's own margin: let them reach into the card padding instead of being cut.
  if (grown) svg.style.overflow = "visible";
  else if (svg.style.overflow === "visible" && svg.dataset.fitOverflow === "1") svg.style.removeProperty("overflow");
  if (grown) svg.dataset.fitOverflow = "1";
}

function run() {
  queued = false;
  document.querySelectorAll<SVGSVGElement>("svg[viewBox]").forEach((svg) => {
    if (!svg.querySelector("text")) return;
    if (ro && !watched.has(svg)) { watched.add(svg); ro.observe(svg); }
    const r = svg.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) fit(svg);
  });
}
const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(run); } };

/** Keeps every chart label on the scale as charts mount, resize and re-render. Call once at start-up. */
export function installSvgTextFit() {
  if (typeof window === "undefined" || typeof MutationObserver === "undefined") return;
  if (typeof ResizeObserver !== "undefined") ro = new ResizeObserver(schedule);
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", schedule);
  schedule();
}
