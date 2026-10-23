// DEMO MODE (VITE_DEMO=1) for Advanced charts: answers /api/advanced from public/demo/advanced/*.json.
// The catalogue there is the backend's own catalogue. The companies are SAMPLE companies with made-up figures ("Sample ... Ltd",
// symbols SMP-*), never real companies; every statistic in the files was computed by the backend's own statistics code
// (backend/finlit/advanced/stats.py analyse()) on those sample points, so the page shows exactly what the live formulas give.
// Precomputed: every cross-section chart with the default company selection, on each scale the chart offers. Filters, your own pairs,
// company history, the forward variants and the technical charts need the live service and say so.
import { ApiError } from "./api";
import type { Catalog, CrossBody, CrossResp, Facets, Highlight, IndexPoint } from "./advanced";

const BASE = `${import.meta.env.BASE_URL}demo/advanced/`;
const cache = new Map<string, Promise<unknown>>();
const load = <T,>(f: string): Promise<T> => {
  if (!cache.has(f)) cache.set(f, fetch(BASE + f).then((r) => { if (!r.ok) throw new Error(f); return r.json(); }));
  return cache.get(f) as Promise<T>;
};
const live = (what: string) => new ApiError(400, { status: "demo", detail: `${what} work on the live site; this demo preview has the default selection of sample companies only.` });
type DemoCross = CrossResp & { excl?: Record<string, string> };

export async function demoFacets(): Promise<Facets & { samples: [string, string][] }> {
  return load("facets.json");
}

export async function demoAdvanced<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = new URL(path, "http://demo");
  if (method === "GET" && url.pathname === "/api/advanced/catalog") return load<T>("catalog.json");
  if (method === "GET" && url.pathname === "/api/advanced/history") throw live("Company history charts");
  if (method === "GET" && url.pathname === "/api/advanced/tech") throw live("Technical charts");
  if (method === "POST" && url.pathname === "/api/advanced/cross") {
    const b = body as CrossBody, u = b.universe;
    if (u.sector.length || u.industry.length || u.index.length || u.cap.length || u.mcapMin != null || u.mcapMax != null || u.sameFy || b.trim || u.lenders !== (b.pair ? "auto" : "only"))
      throw live("Filters");
    if (b.variant) throw live("Forward variants");
    const cat = await load<Catalog>("catalog.json");
    let key: string, sec: number;
    if (b.pair) { const p = cat.pairs.find((x) => x.id === b.pair); if (!p) throw new ApiError(404, { status: "unknown_pair", detail: "Unknown chart." }); sec = p.section; key = `${p.id}|${b.scale.x}|${b.scale.y}`; }
    else { const a = cat.sections.flatMap((s) => (s.alternatives ?? []).map((x) => ({ ...x, sec: s.id }))).find((x) => x.x === b.x && x.y === b.y); if (!a || u.lenders !== "only") throw live("Your own pairs"); sec = a.sec; key = `${a.x}:${a.y}|only|${b.scale.x}|${b.scale.y}`; }
    const file = await load<Record<string, DemoCross>>(`cross-${sec}.json`);
    const r = file[key];
    if (!r) throw live("This scale");
    const facets = await demoFacets(), names = new Map(facets.samples);
    const highlights: Highlight[] = (b.highlight ?? []).map((s) => {
      const p = r.points.find((x) => x.s === s);
      if (p) return { s, name: p.name, x: p.x, y: p.y, fy: p.fy ?? null, status: "included", reason: null, reasonText: null };
      const code = r.excl?.[s];
      if (code) return { s, name: names.get(s) ?? s, x: null, y: null, fy: null, status: code === "outside" ? "outside" : "excluded", reason: code, reasonText: cat.reasons[code] ?? code };
      return { s, name: s, x: null, y: null, fy: null, status: "unknown", reason: "unknown", reasonText: "This demo preview charts sample companies only (search “Sample”)." };
    });
    const { excl: _drop, ...rest } = r; // eslint-disable-line @typescript-eslint/no-unused-vars
    const fac = await demoFacets();
    const indices: IndexPoint[] = (b.indices ?? []).map((code) => ({ code, label: fac.indices.find((i) => i.code === code)?.label ?? code, x: null, y: null, membersTotal: 0, membersEligible: 0, membersUsed: 0,
      mcapCoveragePct: null, method: null, formula: null, reason: "demo", reasonText: "Index markers are computed from real member companies on the live site; this demo preview has sample companies only.", inStats: false }));
    return { ...rest, highlights, ...(indices.length ? { indices } : {}) } as T;
  }
  throw new ApiError(404, { status: "demo", detail: "Not available in the demo." });
}
