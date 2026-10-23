// Chart drawings (the pencil tools traders use to mark up a chart): the shapes, their hit-testing, saving and checking. No React here, so it is tested on its own.
// Points are stored as fractions (0 to 1) of the chart's width and height, so a drawing keeps its place when the chart is resized.
export type Pt = [number, number];
export type ToolId = "pen" | "line" | "arrow" | "hline" | "vline" | "rect" | "ellipse" | "fib" | "text" | "eraser";
export const TOOLS: { id: ToolId; label: string; hint: string }[] = [
  { id: "pen", label: "Pencil", hint: "Draw freehand" },
  { id: "line", label: "Trend line", hint: "Drag from one point to another" },
  { id: "arrow", label: "Arrow", hint: "Drag to point at something" },
  { id: "hline", label: "Horizontal line", hint: "Click to mark a price or value level" },
  { id: "vline", label: "Vertical line", hint: "Click to mark a date or period" },
  { id: "rect", label: "Rectangle", hint: "Drag to box an area" },
  { id: "ellipse", label: "Circle", hint: "Drag to circle an area" },
  { id: "fib", label: "Fibonacci retracement", hint: "Drag from a low to a high (or the reverse)" },
  { id: "text", label: "Text note", hint: "Click, then type" },
  { id: "eraser", label: "Eraser", hint: "Click a drawing to remove it" },
];

/** The colours on offer. "ink" follows the page's text colour, so it is readable on both themes. */
export const COLOURS = { red: "#E5484D", green: "#17A05D", blue: "#2F6FEB", amber: "#E8A317", violet: "#8B5CF6", ink: "currentColor" } as const;
export type ColourId = keyof typeof COLOURS;
export const WIDTHS = [1.5, 3, 5] as const;
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] as const;

export type Shape = { id: string; c: ColourId; w: number } & (
  | { k: "pen"; pts: Pt[] }
  | { k: "line" | "arrow" | "rect" | "ellipse" | "fib"; a: Pt; b: Pt }
  | { k: "hline" | "vline"; a: Pt }
  | { k: "text"; a: Pt; t: string }
);
export const MAX_SHAPES = 200, MAX_PEN_POINTS = 1500, MAX_TEXT = 80;

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
export const clampPt = (p: Pt): Pt => [clamp01(p[0]), clamp01(p[1])];

/** A freehand stroke without the points that add nothing: any point closer than `min` pixels to the last kept one is dropped (the last point is always kept). */
export function thin(pts: readonly Pt[], w: number, h: number, min = 1.5): Pt[] {
  if (pts.length <= 2) return [...pts];
  const out: Pt[] = [pts[0]];
  for (let i = 1; i < pts.length - 1; i++) {
    const l = out[out.length - 1];
    if (Math.hypot((pts[i][0] - l[0]) * w, (pts[i][1] - l[1]) * h) >= min) out.push(pts[i]);
  }
  out.push(pts[pts.length - 1]);
  return out.length > MAX_PEN_POINTS ? out.filter((_, i) => i % Math.ceil(out.length / MAX_PEN_POINTS) === 0 || i === out.length - 1) : out;
}

/** Distance (in pixels) from a point to the segment a-b. */
export function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** The price (or value) fraction at each Fibonacci level between the two points' heights: level 0 is point a's height, level 1 is point b's. */
export function fibLines(a: Pt, b: Pt): { level: number; y: number }[] {
  return FIB_LEVELS.map((level) => ({ level, y: a[1] + (b[1] - a[1]) * level }));
}

/** Does a click at pixel (x, y) land on the shape? `tol` is how close counts, in pixels. */
export function hit(s: Shape, x: number, y: number, w: number, h: number, tol = 8): boolean {
  const X = (p: Pt) => p[0] * w, Y = (p: Pt) => p[1] * h;
  switch (s.k) {
    case "pen": for (let i = 1; i < s.pts.length; i++) if (distToSegment(x, y, X(s.pts[i - 1]), Y(s.pts[i - 1]), X(s.pts[i]), Y(s.pts[i])) <= tol + s.w) return true; return s.pts.length === 1 && Math.hypot(x - X(s.pts[0]), y - Y(s.pts[0])) <= tol;
    case "line": case "arrow": return distToSegment(x, y, X(s.a), Y(s.a), X(s.b), Y(s.b)) <= tol + s.w / 2;
    case "hline": return Math.abs(y - Y(s.a)) <= tol + s.w / 2;
    case "vline": return Math.abs(x - X(s.a)) <= tol + s.w / 2;
    case "rect": { const x0 = Math.min(X(s.a), X(s.b)) - tol, x1 = Math.max(X(s.a), X(s.b)) + tol, y0 = Math.min(Y(s.a), Y(s.b)) - tol, y1 = Math.max(Y(s.a), Y(s.b)) + tol; return x >= x0 && x <= x1 && y >= y0 && y <= y1; }
    case "ellipse": { const cx = (X(s.a) + X(s.b)) / 2, cy = (Y(s.a) + Y(s.b)) / 2, rx = Math.abs(X(s.b) - X(s.a)) / 2 + tol, ry = Math.abs(Y(s.b) - Y(s.a)) / 2 + tol; return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1; }
    case "fib": { const x0 = Math.min(X(s.a), X(s.b)) - tol; if (x < x0) return false; return fibLines(s.a, s.b).some((l) => Math.abs(y - l.y * h) <= tol); }
    case "text": { const tw = s.t.length * 7.5 + 8; return x >= X(s.a) - tol && x <= X(s.a) + tw + tol && y >= Y(s.a) - 18 - tol && y <= Y(s.a) + tol; }
  }
}

/** The topmost (latest) shape under the click, or null. */
export function topHit(shapes: readonly Shape[], x: number, y: number, w: number, h: number, tol = 8): Shape | null {
  for (let i = shapes.length - 1; i >= 0; i--) if (hit(shapes[i], x, y, w, h, tol)) return shapes[i];
  return null;
}

// ---------------------------------------------------------------------------------------------------------------- saving
const KEY = "finlit-drawings:";
const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const pt = (p: unknown): Pt | null => (Array.isArray(p) && p.length === 2 && finite(p[0]) && finite(p[1]) ? clampPt([p[0], p[1]]) : null);

/** Shapes read back from storage (or anywhere untrusted): anything that is not a well-formed shape is dropped, colours must be on the list. */
export function sanitize(raw: unknown): Shape[] {
  if (!Array.isArray(raw)) return [];
  const out: Shape[] = [];
  for (const r of raw.slice(0, MAX_SHAPES)) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    const c = typeof o.c === "string" && o.c in COLOURS ? (o.c as ColourId) : "red", w = finite(o.w) ? Math.min(8, Math.max(1, o.w)) : 3, id = typeof o.id === "string" && o.id ? o.id.slice(0, 24) : newId();
    const base = { id, c, w };
    if (o.k === "pen" && Array.isArray(o.pts)) { const pts = o.pts.slice(0, MAX_PEN_POINTS).map(pt).filter((p): p is Pt => !!p); if (pts.length) out.push({ ...base, k: "pen", pts }); }
    else if ((o.k === "line" || o.k === "arrow" || o.k === "rect" || o.k === "ellipse" || o.k === "fib") && pt(o.a) && pt(o.b)) out.push({ ...base, k: o.k, a: pt(o.a)!, b: pt(o.b)! });
    else if ((o.k === "hline" || o.k === "vline") && pt(o.a)) out.push({ ...base, k: o.k, a: pt(o.a)! });
    else if (o.k === "text" && pt(o.a) && typeof o.t === "string" && o.t.trim()) out.push({ ...base, k: "text", a: pt(o.a)!, t: o.t.slice(0, MAX_TEXT) });
  }
  return out;
}

let seq = 0;
export const newId = () => `${Date.now().toString(36)}${(seq++).toString(36)}`;

export function loadShapes(id: string): Shape[] {
  try { return sanitize(JSON.parse(localStorage.getItem(KEY + id) || "[]")); } catch { return []; }
}
export function saveShapes(id: string, shapes: readonly Shape[]): void {
  try { if (shapes.length) localStorage.setItem(KEY + id, JSON.stringify(shapes)); else localStorage.removeItem(KEY + id); } catch { /* private mode or full: drawings then last for this visit only */ }
}

/** A short stable id for a chart view built from any text (series, range, filters...), so each view keeps its own drawings. */
export function viewId(text: string): string {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) >>> 0;
  return h.toString(36);
}
