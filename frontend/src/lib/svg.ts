// Small imperative SVG helpers used by the chart modules (charts draw straight into an <svg>
// for speed and fine control; React only owns the container).
export const NS = "http://www.w3.org/2000/svg";

export function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, parent?: Element): SVGElementTagNameMap[K] {
  const node = document.createElementNS(NS, tag);
  for (const k in attrs) node.setAttribute(k, String(attrs[k]));
  if (parent) parent.appendChild(node);
  return node;
}

export const css = (v: string, scope: Element = document.documentElement) => getComputedStyle(scope).getPropertyValue(v).trim();

export const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

let gradientSeq = 0;
export function vgrad(svg: SVGSVGElement, color: string, o1: number, o2: number): string {
  const id = "g" + ++gradientSeq;
  const g = el("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 }, el("defs", {}, svg));
  el("stop", { offset: 0, "stop-color": color, "stop-opacity": o1 }, g);
  el("stop", { offset: 1, "stop-color": color, "stop-opacity": o2 }, g);
  return `url(#${id})`;
}

export function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const a = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

export function arcPath(cx: number, cy: number, r: number, a0: number, a1: number) {
  const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
  return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
}

export function drawIn(path: SVGPathElement, animate: boolean, duration = 1.4, delay = 0) {
  if (!animate || reduced()) return;
  const len = path.getTotalLength();
  path.style.strokeDasharray = String(len);
  path.style.strokeDashoffset = String(len);
  path.style.transition = `stroke-dashoffset ${duration}s cubic-bezier(.16,1,.3,1) ${delay}s`;
  requestAnimationFrame(() => requestAnimationFrame(() => (path.style.strokeDashoffset = "0")));
}

export function niceTicks(min: number, max: number, count = 4): number[] {
  const span = max - min || Math.abs(max) || 1;
  let step = Math.pow(10, Math.floor(Math.log10(span / count)));
  const err = span / count / step;
  step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const out: number[] = [];
  for (let t = Math.floor(min / step) * step; t <= max + step / 2; t += step) out.push(+t.toFixed(10));
  return out;
}

export function sparkPath(vals: (number | null)[], w: number, h: number, pad = 3) {
  const v = vals.filter((x): x is number => x != null);
  const mn = Math.min(...v), mx = Math.max(...v), n = vals.length;
  const X = (i: number) => pad + (i / Math.max(1, n - 1)) * (w - pad * 2);
  const Y = (x: number) => h - pad - ((x - mn) / (mx - mn || 1)) * (h - pad * 2);
  let d = "";
  vals.forEach((x, i) => { if (x != null) d += `${d ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}`; });
  const lastIdx = vals.map((x, i) => (x == null ? -1 : i)).filter((i) => i >= 0).pop() ?? 0;
  return { d, X, Y, last: [X(lastIdx), Y(vals[lastIdx] ?? mn)] as [number, number], n };
}
