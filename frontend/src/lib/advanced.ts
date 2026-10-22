// Advanced charts (Graph Studio > Advanced charts): sections, URL state, display rounding, axis geometry and the plain-words sentence.
// Pure helpers only (no React), so every rule here is tested in advanced.test.ts. The statistics themselves are computed by the API
// (backend advanced/stats.py); this file never recomputes r, p, slopes or bands, it only rounds them for display as the plan says:
// r and rho 2 decimals; p 3 significant figures or "< 0.001"; slope 3 significant figures.
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiSend, apiUrl, API_BASE, ApiError, type Financials } from "./api";
import { DEMO } from "./demo";
import { MINUS, nf } from "./format";
import { csvRow, ticks } from "./graphData";
import { priorIndex } from "./plFlags";

// ------------------------------------------------------------------ sections (route slugs)

export const SECTIONS = [
  { n: 1, slug: "valuation", label: "Valuation", title: "Valuation ratio correlations" },
  { n: 2, slug: "profitability", label: "Profitability", title: "Profitability correlations" },
  { n: 3, slug: "growth", label: "Growth", title: "Growth correlations" },
  { n: 4, slug: "leverage", label: "Leverage & debt", title: "Leverage and debt correlations" },
  { n: 5, slug: "cash-flow", label: "Cash flow", title: "Cash flow and earnings quality correlations" },
  { n: 6, slug: "liquidity", label: "Liquidity", title: "Liquidity and working capital correlations" },
  { n: 7, slug: "dividends", label: "Dividends", title: "Dividend and shareholder-return correlations" },
  { n: 8, slug: "market", label: "Market & technical", title: "Market price and technical indicator correlations" },
  { n: 9, slug: "warnings", label: "Warning signs", title: "Financial statement warning correlations" },
  { n: 10, slug: "sector", label: "Sector-specific", title: "Sector-specific correlations" },
] as const;
export type SectionSlug = (typeof SECTIONS)[number]["slug"];
export const sectionBySlug = (slug: string | undefined) => SECTIONS.find((s) => s.slug === slug);
export const sectionByNumber = (n: number) => SECTIONS.find((s) => s.n === n);

// ------------------------------------------------------------------ URL state (the address is the source of truth, so a link shares the chart)

export type Mode = "cross" | "history" | "tech";
export type Scale = "lin" | "log";
export type Lenders = "auto" | "exclude" | "include" | "only";
export type Universe = {
  sector: string[]; industry: string[]; index: string[]; cap: string[];
  mcapMin: number | null; mcapMax: number | null;
  /** Banks and lenders: "auto" = the pair decides (lender-sensitive metrics force them out), or exclude / include / only. */
  lenders: Lenders; sameFy: boolean;
};
export type AdvState = {
  pair: string | null;           // catalogue pair id ("1.9") or "custom"
  x: string | null; y: string | null;   // only for pair = "custom"
  mode: Mode; companies: string[]; universe: Universe;
  sx: Scale | null; sy: Scale | null;   // null = the metric's default scale
  trim: boolean; all: boolean;   // trim = leave out the most extreme 1% at each end (statistics); all = show every point (view only)
  h: number | null;              // technical charts: forward horizon in trading days
  variant: string | null;        // a pair variant from the catalogue, e.g. "forward" for 8.1-8.4 (null = the default, same-FY view)
};

export const EMPTY_UNIVERSE: Universe = { sector: [], industry: [], index: [], cap: [], mcapMin: null, mcapMax: null, lenders: "auto", sameFy: false };
export const DEFAULT_STATE: AdvState = { pair: null, x: null, y: null, mode: "cross", companies: [], universe: EMPTY_UNIVERSE, sx: null, sy: null, trim: false, all: false, h: null, variant: null };

const SYM = /^[A-Z0-9&_.-]{1,24}$/;
const PAIR = /^(\d{1,2}\.\d{1,2}[a-z]?|custom)$/;
const MID = /^[a-z][a-z0-9_]{0,31}$/;
const CAPS = new Set(["Large", "Mid", "Small"]);
const LENDERS = new Set<Lenders>(["auto", "exclude", "include", "only"]);

/** base64url of UTF-8 text, and back (null on anything malformed). */
export function b64urlEncode(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = ""; bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
export function b64urlDecode(s: string): string | null {
  try {
    const b = s.replace(/-/g, "+").replace(/_/g, "/"), pad = b + "=".repeat((4 - (b.length % 4)) % 4);
    const bin = atob(pad), bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch { return null; }
}

const strList = (v: unknown, max = 40): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x.length > 0 && x.length <= 80).slice(0, max) : []);
const posNum = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);

/** Universe filter to a short URL value; "" when it is the default (so plain links stay plain). */
export function encodeUniverse(u: Universe): string {
  const o: Record<string, unknown> = {};
  if (u.sector.length) o.s = u.sector; if (u.industry.length) o.i = u.industry; if (u.index.length) o.x = u.index; if (u.cap.length) o.c = u.cap;
  if (u.mcapMin != null) o.mn = u.mcapMin; if (u.mcapMax != null) o.mx = u.mcapMax;
  if (u.lenders !== "auto") o.l = u.lenders; if (u.sameFy) o.f = 1;
  return Object.keys(o).length ? b64urlEncode(JSON.stringify(o)) : "";
}
export function decodeUniverse(raw: string | null): Universe {
  if (!raw) return { ...EMPTY_UNIVERSE };
  const txt = b64urlDecode(raw); if (!txt) return { ...EMPTY_UNIVERSE };
  let o: Record<string, unknown>;
  try { const v = JSON.parse(txt); if (!v || typeof v !== "object" || Array.isArray(v)) return { ...EMPTY_UNIVERSE }; o = v; } catch { return { ...EMPTY_UNIVERSE }; }
  return { sector: strList(o.s), industry: strList(o.i), index: strList(o.x, 10), cap: strList(o.c, 3).filter((c) => CAPS.has(c)),
    mcapMin: posNum(o.mn), mcapMax: posNum(o.mx), lenders: LENDERS.has(o.l as Lenders) ? (o.l as Lenders) : "auto", sameFy: o.f === 1 };
}

/** Read the page state from the query string; anything invalid falls back to the default, never throws. `limit` caps the companies. */
export function decodeState(sp: URLSearchParams, limit = 6): AdvState {
  const pair = sp.get("pair"), mode = sp.get("mode"), sc = (v: string | null): Scale | null => (v === "log" || v === "lin" ? v : null);
  const h = Number(sp.get("h"));
  const cs = (sp.get("c") ?? "").split(",").map((s) => s.trim().toUpperCase()).filter((s) => SYM.test(s));
  return {
    pair: pair && PAIR.test(pair) ? pair : null,
    x: pair === "custom" && MID.test(sp.get("x") ?? "") ? sp.get("x") : null,
    y: pair === "custom" && MID.test(sp.get("y") ?? "") ? sp.get("y") : null,
    mode: mode === "history" || mode === "tech" ? mode : "cross",
    companies: [...new Set(cs)].slice(0, Math.max(0, limit)),
    universe: decodeUniverse(sp.get("u")),
    sx: sc(sp.get("sx")), sy: sc(sp.get("sy")),
    trim: sp.get("trim") === "1", all: sp.get("all") === "1",
    h: [5, 20, 60].includes(h) ? h : null,
    variant: /^[a-z][a-z0-9_-]{0,23}$/.test(sp.get("v") ?? "") ? sp.get("v") : null,
  };
}
/** The query string for a state; defaults are left out. */
export function encodeState(s: AdvState): URLSearchParams {
  const p = new URLSearchParams();
  if (s.pair) p.set("pair", s.pair);
  if (s.pair === "custom") { if (s.x) p.set("x", s.x); if (s.y) p.set("y", s.y); }
  if (s.mode !== "cross") p.set("mode", s.mode);
  if (s.companies.length) p.set("c", s.companies.join(","));
  const u = encodeUniverse(s.universe); if (u) p.set("u", u);
  if (s.sx) p.set("sx", s.sx); if (s.sy) p.set("sy", s.sy);
  if (s.trim) p.set("trim", "1"); if (s.all) p.set("all", "1");
  if (s.h) p.set("h", String(s.h)); if (s.variant) p.set("v", s.variant);
  return p;
}

// ------------------------------------------------------------------ display rounding (the only rounding the page does)

const negZero = (s: string) => (/^-0(\.0+)?$/.test(s) ? s.slice(1) : s);
const minus = (s: string) => s.replace(/^-/, MINUS);
const missing = (v: number | null | undefined): v is null | undefined => v == null || !Number.isFinite(v);

/** Pearson r or Spearman rho: 2 decimals ("0.46", "−0.12"). */
export const fmtR = (r: number | null | undefined) => (missing(r) ? "—" : minus(negZero(r.toFixed(2))));
/** p-value: "< 0.001" below one in a thousand, else 3 significant figures ("0.0734", "0.364", "1.00"). */
export function fmtP(p: number | null | undefined): string {
  if (missing(p)) return "—";
  if (p < 0.001) return "< 0.001";
  return Number(p).toPrecision(3);
}
/** Any number to 3 significant figures, plain notation with Indian grouping ("0.0912", "1,23,000", "−4.50"). */
export function sig3(v: number | null | undefined): string {
  if (missing(v)) return "—";
  if (v === 0) return "0";
  const s = Math.abs(v).toLocaleString("en-IN", { minimumSignificantDigits: 3, maximumSignificantDigits: 3, useGrouping: true });
  return (v < 0 ? MINUS : "") + s;
}
/** Share as a whole per cent for "explains 21% of the variation" (R² × 100, rounded half away from zero). */
export const pctOf = (share: number | null | undefined) => (missing(share) ? "—" : `${roundHalfEven(share * 100)}%`);
/** Round to a whole number, ties to even (as Python's round(), which the API uses for "r2pct"). */
export function roundHalfEven(v: number): number {
  const f = Math.floor(v), d = v - f;
  if (Math.abs(d - 0.5) < 1e-12) return f % 2 === 0 ? f : f + 1;
  return Math.round(v);
}

/** Words for the size of a correlation (same bands as Graph Studio's strength()). */
export function strengthWord(r: number): string {
  const a = Math.abs(r);
  return a >= 0.8 ? "very strong" : a >= 0.6 ? "strong" : a >= 0.4 ? "moderate" : a >= 0.2 ? "weak" : "very weak";
}

// ------------------------------------------------------------------ axis geometry

/** Ticks for a log10 axis: 1-2-5 steps per decade, thinned to at most `max` labels (1s only, then every other decade). */
export function logTicks(lo: number, hi: number, max = 7): number[] {
  if (!(lo > 0) || !(hi > 0) || !Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  if (lo > hi) [lo, hi] = [hi, lo];
  const e0 = Math.floor(Math.log10(lo)), e1 = Math.ceil(Math.log10(hi));
  const within = (v: number) => v >= lo * (1 - 1e-9) && v <= hi * (1 + 1e-9);
  const at = (mults: number[], step = 1) => { const out: number[] = []; for (let e = e0; e <= e1; e++) { if ((e - e0) % step) continue; for (const m of mults) { const v = +(m * 10 ** e).toPrecision(12); if (within(v)) out.push(v); } } return out; };
  let t = at([1, 2, 5]); if (t.length <= max) return t.length >= 2 ? t : at([1, 1.5, 2, 3, 5, 7]);
  t = at([1]); for (let step = 2; t.length > max; step++) t = at([1], step);
  return t;
}
/** Linear ticks (shared with Graph Studio). */
export const linTicks = (lo: number, hi: number, count = 5) => ticks(lo, hi, count);

/** Type-7 quantile (as R / numpy default) of an ascending array. */
export function quantile7(sorted: number[], p: number): number {
  if (!sorted.length) return NaN;
  const h = (sorted.length - 1) * p, lo = Math.floor(h), hi = Math.ceil(h);
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}

/** Visible range of one axis (in plot space, i.e. already log10 for a log axis). By default the 1st to 99th percentile so a few extreme
 *  companies do not squash the rest; `all` shows every point. Statistics are never affected: this is only the window. */
export function viewRange(vals: number[], all: boolean, keep: number[] = []): [number, number] {
  const v = vals.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return [0, 1];
  let lo = v[0], hi = v[v.length - 1];
  if (!all && v.length >= 20) { lo = quantile7(v, 0.01); hi = quantile7(v, 0.99); }
  for (const k of keep) if (Number.isFinite(k)) { lo = Math.min(lo, k); hi = Math.max(hi, k); }   // highlighted companies always in view
  if (lo === hi) { const pad = Math.abs(lo) || 1; return [lo - pad / 2, hi + pad / 2]; }
  const pad = (hi - lo) * 0.05;
  return [lo - pad, hi + pad];
}

/** Where a point outside the window is drawn: on the edge, with the side(s) it left by. */
export function edgeOf(px: number, py: number, [x0, x1]: [number, number], [y0, y1]: [number, number]) {
  const out = { left: px < x0, right: px > x1, below: py < y0, above: py > y1 };
  return { ...out, inside: !(out.left || out.right || out.below || out.above), x: Math.min(x1, Math.max(x0, px)), y: Math.min(y1, Math.max(y0, py)) };
}

/** SVG path of the 95% confidence band for the fitted line: upper edge left to right, lower edge back, closed. Points are plot-space. */
export function bandPath(band: { x: number; lo: number; hi: number }[], X: (v: number) => number, Y: (v: number) => number): string {
  const ok = band.filter((b) => Number.isFinite(b.x) && Number.isFinite(b.lo) && Number.isFinite(b.hi));
  if (ok.length < 2) return "";
  const f = (n: number) => n.toFixed(1);
  const up = ok.map((b, i) => `${i ? "L" : "M"}${f(X(b.x))},${f(Y(b.hi))}`).join("");
  const dn = [...ok].reverse().map((b) => `L${f(X(b.x))},${f(Y(b.lo))}`).join("");
  return up + dn + "Z";
}

/** Marker shapes for highlighted companies (paired with colours --k1..--k6 so colour is never the only cue). */
export const SHAPES = ["circle", "square", "triangle", "diamond", "cross", "star"] as const;
export type Shape = (typeof SHAPES)[number];
export function shapePath(shape: Shape, cx: number, cy: number, r: number): string {
  const f = (n: number) => n.toFixed(1);
  switch (shape) {
    case "circle": return `M${f(cx - r)},${f(cy)}a${r},${r} 0 1,0 ${f(2 * r)},0a${r},${r} 0 1,0 ${f(-2 * r)},0Z`;
    case "square": { const s = r * 0.9; return `M${f(cx - s)},${f(cy - s)}h${f(2 * s)}v${f(2 * s)}h${f(-2 * s)}Z`; }
    case "triangle": { const s = r * 1.15; return `M${f(cx)},${f(cy - s)}L${f(cx + s)},${f(cy + s * 0.8)}L${f(cx - s)},${f(cy + s * 0.8)}Z`; }
    case "diamond": { const s = r * 1.2; return `M${f(cx)},${f(cy - s)}L${f(cx + s)},${f(cy)}L${f(cx)},${f(cy + s)}L${f(cx - s)},${f(cy)}Z`; }
    case "cross": { const a = r * 0.4, b = r * 1.1; return `M${f(cx - a)},${f(cy - b)}h${f(2 * a)}v${f(b - a)}h${f(b - a)}v${f(2 * a)}h${f(a - b)}v${f(b - a)}h${f(-2 * a)}v${f(a - b)}h${f(a - b)}v${f(-2 * a)}h${f(b - a)}Z`; }
    case "star": { const pts: string[] = []; for (let k = 0; k < 10; k++) { const rr = k % 2 ? r * 0.5 : r * 1.25, t = (Math.PI / 5) * k - Math.PI / 2; pts.push(`${f(cx + rr * Math.cos(t))},${f(cy + rr * Math.sin(t))}`); } return "M" + pts.join("L") + "Z"; }
  }
}

/** Index of the point nearest to (px, py) in screen space, or -1. */
export function nearest(pts: { sx: number; sy: number }[], px: number, py: number): number {
  let k = -1, best = Infinity;
  pts.forEach((p, i) => { const d = (p.sx - px) ** 2 + (p.sy - py) ** 2; if (d < best) { best = d; k = i; } });
  return k;
}


// ------------------------------------------------------------------ API types (docs/ADVANCED-CHARTS-API.md v1)

export type Unit = "x" | "%" | "Cr" | "Rs" | "d" | "pts" | "ratio" | "n";
export type Tier = "basic" | "silver" | "gold";
export type PairStatus = "ready" | "adapted" | "unavailable";
export type CatSection = { id: number; slug: string; title: string; intro: string | null; note: string | null; pairs: string[]; alternatives?: CatAlt[] };
export type CatAlt = { id: string; xLabel: string; yLabel: string; x: string; y: string; lenders?: string; label?: string; help?: string };
export type CatPair = {
  id: string; section: number; row: number; xLabel: string; yLabel: string; help: string; status: PairStatus; source: "A" | "C" | "N";
  x: string | null; y: string | null; flags: string[]; mechanical: string | null; notes: string[]; reason: string | null;
  modes: Mode[]; tier: Partial<Record<Mode, Tier>>; lenders: "auto" | "excluded" | "only";
  scale: { x: Scale; y: Scale }; logOk: { x: boolean; y: boolean }; sameAs: string | null;
  variants: { id: string; label: string; tier: Tier }[]; alt: { x: string; y: string; label: string } | null;
  sector: string | null; preset: { kind: string; value: string } | null; tech: { kind: string; h?: number[] } | null;
};
export type CatMetric = { label: string; short?: string; unit: Unit; basis: string; digits?: number; formula?: string; source?: string; logOk?: boolean; lenders?: string; history?: Tier | null };
export type Catalog = {
  version: number; counts: Record<string, number>; sections: CatSection[]; pairs: CatPair[]; metrics: Record<string, CatMetric>;
  reasons: Record<string, string>; decisions: Record<string, string>; caveats: string[]; coverageNote: string;
};

export type AxisInfo = { id: string; label: string; unit: Unit; basis?: string; scale?: Scale };
export type Line = { x0: number; y0: number; x1: number; y1: number };
export type DecisionRule = "ok" | "few" | "no_spread" | "not_significant" | "weak" | "one_company" | "curved" | "pulled";
export type Stats = {
  n: number; space?: { x: Scale; y: Scale };
  mean?: { x: number; y: number } | null; sxx?: number | null; syy?: number | null; sxy?: number | null;
  pearson: { r: number | null; r2: number | null; t?: number | null; df?: number | null; p: number | null; ci?: [number, number] | null } | null;
  spearman: { rho: number | null; p: number | null } | null;
  ols: { slope: number | null; intercept: number | null; se?: number | null; ci?: [number, number] | null; s?: number | null; tCrit?: number | null } | null;
  theilSen: { slope: number; intercept: number } | null;
  influence?: { max: { label?: string; s?: string; name: string; cook: number | null; leverage: number } | null; without: { n: number; r: number | null; p: number | null; slope: number | null } | null } | null;
  curvature?: { c2: number | null; p: number | null; dR2: number | null } | null;
  decision: { line: "ols" | "ols_ts" | "none"; rule: DecisionRule; text: string };
  line: Line | null; tsLine?: Line | null;
  band: { x: number; lo: number; y: number; hi: number }[] | null;
  rounded?: { r?: string | null; rho?: string | null; p?: string | null; slope?: string | null; r2pct?: string | null } | null;
};
export type Excluded = { stage?: string; code: string; axis?: "x" | "y" | null; count: number; text: string };
export type CrossPoint = { s: string; name: string; sector?: string | null; x: number; y: number; fy?: string | null };
export type Highlight = { s: string; name?: string | null; x: number | null; y: number | null; fy?: string | null; status: "included" | "excluded" | "outside" | "no_report" | "unknown"; reason: string | null; reasonText: string | null };
export type CrossResp = {
  pair: string | null; variant: string | null; x: AxisInfo; y: AxisInfo; n: number; universeTotal: number; excluded: Excluded[];
  points: CrossPoint[]; highlights: Highlight[]; stats: Stats | null; fyBreakdown: { fy: string; n: number }[];
  view: { x: [number, number]; y: [number, number]; outside: number } | null;
  lenders: { mode: string; forced: boolean; count: number } | null; preset: { label: string; matched: Record<string, string[]> } | null;
  notes: string[]; caveats: string[]; coverage: { withReport: number; listed: number } | null; tableBuiltAt: string | null; method: string;
  sample?: boolean;
};
export type HistCompany = { s: string; name: string; status: "ok" | "no_report" | "unknown" | "lender_excluded"; points: { fy: string; x: number; y: number }[];
  missing: { fy: string; axis: "x" | "y"; code: string; text: string }[]; n: number; stats: Stats | null };
export type HistResp = { pair: string | null; x: AxisInfo; y: AxisInfo; companies: HistCompany[]; notes: string[]; caveats: string[]; sample?: boolean };
export type TechResp = { symbol: string; name: string; kind: string; h: number | null; pair: string | null; x: AxisInfo; y: AxisInfo;
  points: { d: string; x: number; y: number }[]; excluded: Excluded[]; n: number; stats: Stats | null; grid: string; asOf: string | null; notes: string[]; caveats: string[]; sample?: boolean };

export type CrossBody = {
  pair?: string; x?: string; y?: string; variant?: string | null;
  universe: { sector: string[]; industry: string[]; index: string[]; cap: string[]; mcapMin: number | null; mcapMax: number | null; lenders: Lenders; sameFy: boolean };
  scale: { x: Scale; y: Scale }; trim: boolean; highlight: string[];
};

/** The body of POST /cross for a page state (custom pairs send x/y; catalogue pairs send the pair id and let the server apply its rules). */
export function crossBody(st: AdvState, pair: CatPair | null, scale: { x: Scale; y: Scale }): CrossBody {
  const u = st.universe;
  const base = { universe: { sector: u.sector, industry: u.industry, index: u.index, cap: u.cap, mcapMin: u.mcapMin, mcapMax: u.mcapMax, lenders: u.lenders, sameFy: u.sameFy }, scale, trim: st.trim, highlight: st.companies };
  if (pair) return { pair: pair.id, ...(st.variant ? { variant: st.variant } : {}), ...base };
  return { x: st.x ?? undefined, y: st.y ?? undefined, ...base };
}

// ------------------------------------------------------------------ value formats by API unit

const nfx = (v: number, d: number) => Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const sgn = (v: number) => (v < 0 ? MINUS : "");
/** A point value as stored (the API sends at most 4 decimals): shown with the metric's own digits, never re-derived. */
export function fmtUnit(v: number | null | undefined, unit: Unit | undefined, digits?: number): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const d = digits ?? (unit === "Cr" ? (Math.abs(v) >= 1000 ? 0 : 2) : unit === "d" || unit === "n" ? 0 : unit === "pts" ? 1 : 2);
  switch (unit) {
    case "Cr": return `${sgn(v)}₹${nfx(v, d)} Cr`;
    case "Rs": return `${sgn(v)}₹${nfx(v, d)}`;
    case "%": return `${sgn(v)}${nfx(v, d)}%`;
    case "x": return `${sgn(v)}${nfx(v, d)}×`;
    case "d": return `${sgn(v)}${nfx(v, d)} days`;
    default: return `${sgn(v)}${nfx(v, d)}`;
  }
}
/** A short axis tick. */
export function tickUnit(v: number, unit: Unit | undefined): string {
  const a = Math.abs(v), t = (n: number, d: number) => nfx(n, d).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  const body = unit === "Cr" && a >= 1e5 ? t(a / 1e5, 1) + "L" : a >= 1e5 ? t(a / 1e3, 0) + "K" : t(a, a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : 3);
  return sgn(v) + (unit === "Cr" ? "₹" : unit === "Rs" ? "₹" : "") + body + (unit === "%" ? "%" : unit === "x" ? "×" : "");
}
const UNIT_STEP: Record<Unit, string> = { x: "×", "%": "percentage point", Cr: "₹ crore", Rs: "rupee", d: "day", pts: "point", ratio: "unit", n: "unit" };
const UNIT_AFTER: Record<Unit, (s: string) => string> = { x: (s) => `${s}×`, "%": (s) => `${s} percentage points`, Cr: (s) => `₹${s} Cr`, Rs: (s) => `₹${s}`, d: (s) => `${s} days`, pts: (s) => `${s} points`, ratio: (s) => s, n: (s) => s };

// ------------------------------------------------------------------ the plain-words sentence

/** The rounded display strings: the API's own ("rounded"), else the same rule applied here to the API's 6-significant-figure values. */
export function rounded(st: Stats) {
  const r = st.rounded ?? {};
  return {
    r: disp(r.r, fmtR(st.pearson?.r)), rho: disp(r.rho, fmtR(st.spearman?.rho)), p: disp(r.p, fmtP(st.pearson?.p)),
    slope: disp(r.slope, sig3(st.ols?.slope)), r2pct: disp(r.r2pct, st.pearson?.r2 != null ? pctOf(st.pearson.r2) : "—"),
  };
}
/** An API display string, typeset only: true minus, no "-0.00", plain notation instead of "1.2e+06" (same digits), "n/a" as "—". */
export function disp(s: string | null | undefined, fallback: string): string {
  if (s == null || s === "") return fallback;
  if (s === "n/a") return "—";
  let t = s.trim();
  if (/^-?\d(\.\d+)?e[+-]?\d+$/i.test(t)) t = sig3(Number(t)).replace(MINUS, "-");
  return minus(negZero(t));
}
const withSign = (s: string) => (s === "—" ? s : /^[-−]/.test(s) ? s.replace(/^-/, MINUS) : `+${s}`);
const pTxt = (p: string) => (p.startsWith("<") ? `p ${p}` : `p = ${p}`);

export type SentenceCtx = {
  kind: "cross" | "history" | "tech";
  who: string;                       // "companies" (cross), "financial years of TCS" (history), "20-day windows of RELIANCE" (tech)
  x: { short: string; unit: Unit }; y: { short: string; unit: Unit };
  left?: number; total?: number;     // cross: companies left out / companies in the filters
  fy?: { fy: string; n: number }[]; builtAt?: string | null;
};
export const CAVEAT = "Correlation is not causation. Information only, not advice.";

/** One paragraph, in plain words, built only from the API's figures and its decision. Ends with the caveat. */
export function advSentence(st: Stats | null, c: SentenceCtx): string {
  const parts: string[] = [];
  if (!st || !st.n) {
    parts.push(c.kind === "cross" ? "No company has both figures in this selection, so there is nothing to measure." : "No period has both figures, so there is nothing to measure.");
  } else {
    const R = rounded(st), r = st.pearson?.r ?? null, logSpace = st.space?.x === "log" || st.space?.y === "log";
    const rhoTxt = R.rho !== "—" ? `; Spearman rho = ${R.rho}` : "";
    const pPart = st.pearson?.p != null || st.rounded?.p ? `; ${pTxt(R.p)}` : "";
    const head = `Across ${st.n.toLocaleString("en-IN")} ${c.who}`;
    if (st.decision.line !== "none" && r != null) {
      const dir = r > 0 ? "higher" : "lower";
      parts.push(`${head}, higher ${c.x.short} tends to go with ${dir} ${c.y.short} (Pearson r = ${R.r}, ${strengthWord(r)}${rhoTxt}${pPart}).`);
      const slope = logSpace
        ? `the slope is ${withSign(R.slope)} on the log scale (log10 of ${c.y.short} per log10 of ${c.x.short}).`
        : `on average, +1 ${UNIT_STEP[c.x.unit]} of ${c.x.short} goes with ${UNIT_AFTER[c.y.unit](withSign(R.slope))} of ${c.y.short}.`;
      parts.push(`The line explains ${R.r2pct} of the variation; ${slope}`);
      if (st.decision.rule === "pulled") parts.push(st.decision.text);
    } else {
      const rTxt = r != null ? `Pearson r = ${R.r} (${strengthWord(r)})` : "Pearson r cannot be computed";
      parts.push(`${head}: ${rTxt}${rhoTxt}${pPart}.`);
      parts.push(`No line is drawn. ${st.decision.text}`);
    }
  }
  if (c.kind === "cross" && c.left != null && c.total != null && c.left > 0) parts.push(`${c.left.toLocaleString("en-IN")} of the ${c.total.toLocaleString("en-IN")} companies in the filters are left out (reasons below).`);
  if (c.fy?.length) parts.push(`Results ${c.fy.map((f) => `${f.fy} (${f.n.toLocaleString("en-IN")})`).join(" / ")}.`);
  if (c.builtAt) parts.push(`Prices and figures as stored at ${fmtWhen(c.builtAt)}.`);
  parts.push(CAVEAT);
  return parts.join(" ");
}

/** "22 Oct 2026, 15:45 IST" for an ISO timestamp; the raw text if it is not a date. */
export function fmtWhen(iso: string): string {
  const t = Date.parse(iso); if (!Number.isFinite(t)) return iso;
  return new Date(t).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }) + " IST";
}

/** One-line chart summary for screen readers (the svg's aria-label). */
export function ariaSummary(st: Stats | null, x: string, y: string, n: number, who: string): string {
  if (!st || !n) return `Scatter of ${y} against ${x}: no points.`;
  const R = rounded(st);
  const line = st.decision.line === "none" ? `no line drawn: ${st.decision.text}` : st.decision.line === "ols_ts" ? "straight line and robust line drawn" : "straight line drawn with its 95% band";
  return `Scatter of ${y} against ${x}, ${n} ${who}. Pearson r ${R.r}, ${pTxt(R.p)}; ${line}.`;
}

// ------------------------------------------------------------------ CSV (demo preview only; the live site exports from the server)

/** The export layout of the API (header block, blank line, one row per company) built from a cross response. Text cells are guarded. */
export function crossCsv(r: CrossResp, title: string): string {
  const st = r.stats, R = st ? rounded(st) : null;
  const head: (string | number | null)[][] = [["# title", title], ["# as_of", r.tableBuiltAt], ["# n", r.n], ["# universeTotal", r.universeTotal],
    ["# r", st?.pearson?.r ?? null], ["# rho", st?.spearman?.rho ?? null], ["# slope", st?.ols?.slope ?? null], ["# intercept", st?.ols?.intercept ?? null], ["# p", st?.pearson?.p ?? null],
    ["# decision", st ? `${st.decision.rule}: ${st.decision.text}` : null], ["# shown_as", R ? `r ${R.r}; rho ${R.rho}; p ${R.p}; slope ${R.slope}` : null], ["# method", r.method], ["# caveats", r.caveats.join(" ")]];
  const hl = new Set(r.highlights.map((h) => h.s));
  const rows: (string | number | null)[][] = r.points.map((p) => [p.s, p.name, p.sector ?? "", p.fy ?? "", p.x, p.y, "yes", "", hl.has(p.s) ? "yes" : "no"]);
  r.highlights.filter((h) => h.status !== "included").forEach((h) => rows.push([h.s, h.name ?? "", "", h.fy ?? "", h.x, h.y, "no", h.reason ?? h.status, "yes"]));
  return [...head.map(csvRow), "", csvRow(["symbol", "name", "sector", "fy", "x", "y", "included", "reason", "highlighted"]), ...rows.map(csvRow)].join("\n");
}

// ------------------------------------------------------------------ data (react-query); demo mode answers from public/demo/advanced

async function advGet<T>(path: string): Promise<T> {
  if (DEMO) return (await import("./advancedDemo")).demoAdvanced<T>("GET", path);
  return apiGet<T>(path);
}
async function advPost<T>(path: string, body: unknown): Promise<T> {
  if (DEMO) return (await import("./advancedDemo")).demoAdvanced<T>("POST", path, body);
  return apiSend<T>("POST", path, body);
}
const retry = (n: number, e: ApiError) => (e.status === 429 ? n < 4 : e.status >= 500 && n < 2);

export const useAdvCatalog = () => useQuery<Catalog, ApiError>({ queryKey: ["adv-catalog"], queryFn: () => advGet<Catalog>("/api/advanced/catalog"), staleTime: 300_000, retry });
export const useCross = (body: CrossBody, enabled: boolean) =>
  useQuery<CrossResp, ApiError>({ queryKey: ["adv-cross", body], queryFn: () => advPost<CrossResp>("/api/advanced/cross", body), enabled, staleTime: 60_000, retry });
export const useHistory = (symbols: string[], pair: string | null, x: string, y: string, enabled: boolean) => {
  const qs = new URLSearchParams({ symbols: symbols.join(",") }); if (pair) qs.set("pair", pair); else { qs.set("x", x); qs.set("y", y); }
  return useQuery<HistResp, ApiError>({ queryKey: ["adv-history", qs.toString()], queryFn: () => advGet<HistResp>(`/api/advanced/history?${qs}`), enabled, staleTime: 60_000, retry });
};
export const useTech = (symbol: string | null, kind: string, h: number | null, enabled: boolean) => {
  const qs = new URLSearchParams({ symbol: symbol ?? "", kind }); if (h) qs.set("h", String(h));
  return useQuery<TechResp, ApiError>({ queryKey: ["adv-tech", qs.toString()], queryFn: () => advGet<TechResp>(`/api/advanced/tech?${qs}`), enabled, staleTime: 300_000, retry });
};
export type Facets = { sectors: { name: string; n: number }[]; industries: { name: string; sector: string | null; n: number }[]; indices: { code: string; label: string; n: number }[]; caps: { name: string; n: number }[] };
/** Universe facets: the screener's own lists (/api/screener/catalog), so the filters match the screener exactly. */
export const useFacets = () => useQuery<Facets, ApiError>({
  queryKey: DEMO ? ["adv-facets-demo"] : ["screener-catalog"], staleTime: 300_000, retry: 1,
  queryFn: async () => (DEMO ? (await import("./advancedDemo")).demoFacets() : apiGet<Facets>("/api/screener/catalog")),
});

/** POST /export and return the CSV file the server wrote (header block + every row). */
export async function exportCsv(body: Record<string, unknown>, csrf: string | null): Promise<Blob> {
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "text/csv" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(apiUrl("/api/advanced/export"), { method: "POST", headers, credentials: API_BASE ? "include" : "same-origin", body: JSON.stringify(body) });
  if (!res.ok) {
    let b: ApiError["body"] = {};
    try { const j = await res.json(); b = j?.detail && typeof j.detail === "object" ? j.detail : j; } catch { /* not JSON */ }
    throw new ApiError(res.status, b);
  }
  return res.blob();
}

// ------------------------------------------------------------------ section 9 rule: revenue and profit up, operating cash flow down

/** The doc's high-priority warning, as a rule on the company's own yearly statements: latest FY against the FY a year earlier
 *  (matched on period end dates). Shows the reported figures only; null when any figure is missing or the rule does not hold. */
export function cfoWarning(fin: Financials | null | undefined): { period: string; against: string; text: string } | null {
  const pl = fin?.yearly?.pl, cf = fin?.yearly?.cf;
  if (!pl?.periods?.length || !cf?.periods?.length) return null;
  const i = pl.periods.length - 1, j = priorIndex(pl, i, "year");
  if (j == null) return null;
  const P = pl.periods[i], Q = pl.periods[j], ci = cf.periods.indexOf(P), cj = cf.periods.indexOf(Q);
  if (ci < 0 || cj < 0) return null;
  const v = (t: typeof pl, k: string, n: number) => { const x = t.rows?.[k]?.[n]; return typeof x === "number" && Number.isFinite(x) ? x : null; };
  const r1 = v(pl, "revenue", i), r0 = v(pl, "revenue", j), n1 = v(pl, "net_profit", i), n0 = v(pl, "net_profit", j), c1 = v(cf, "operating", ci), c0 = v(cf, "operating", cj);
  if ([r1, r0, n1, n0, c1, c0].some((x) => x == null)) return null;
  if (!(r1! > r0! && n1! > n0! && c1! < c0!)) return null;
  const cr = (x: number) => `${x < 0 ? MINUS : ""}₹${nf(x, Math.abs(x) >= 1000 ? 0 : 2)} Cr`;
  return { period: P, against: Q, text: `Revenue ${cr(r0!)} to ${cr(r1!)}, net profit ${cr(n0!)} to ${cr(n1!)}, operating cash flow ${cr(c0!)} to ${cr(c1!)}, as reported. Look at receivables, inventory, working capital and accruals before drawing conclusions.` };
}
