// DEMO MODE (VITE_DEMO=1) for the mutual fund pages: answers the /api/mf calls from public/demo/mf/data.json, a recording of the real API
// (real AMFI NAVs of 67 schemes of 13 funds, with their full details). List, filters, detail and compare run here on that recording; nothing is invented.
import { ApiError } from "./api";
import { score } from "./metricSearch";
import type { FundCompare, FundDetail, FundFilters, FundRow, RangeKey } from "./mf";
import { DEMO_PORTFOLIO } from "../holdings/demo";

type Data = { facts: { dataDate: string; updatedAt: string; source: string; disclaimer: string }; rows: FundRow[]; details: Record<string, FundDetail>; filters: FundFilters };
let cache: Promise<Data> | null = null;
const load = (): Promise<Data> => (cache ||= fetch(`${import.meta.env.BASE_URL}demo/mf/data.json`).then((r) => r.json() as Promise<Data>));
const notFound = (msg: string) => new ApiError(404, { status: "not_found", detail: msg });
const num = (s: string | null) => (s == null || s === "" ? null : Number(s));

export async function demoMf<T>(path: string): Promise<T> {
  const data = await load();
  const url = new URL(path, "http://demo");
  const p = url.searchParams;
  if (url.pathname === "/api/mf/filters") return { ...data.filters } as T;
  if (url.pathname === "/api/mf/compare") {
    const range = (p.get("range") || "1Y") as RangeKey;
    const ids = (p.get("ids") || "").split(",").map(Number);
    const ds = ids.map((c) => data.details[c]);
    if (ds.some((d) => !d)) throw notFound("This preview holds 67 schemes; the live site has every scheme.");
    const sets = ds.map((d) => d.series[range]);
    let chart: FundCompare["chart"] = null;
    if (sets.every(Boolean)) {
      const common = sets.map((s) => s!.t[0]).sort().pop()!;
      chart = { from: common, range, series: sets.map((s, i) => { let k = 0; while (k + 1 < s!.t.length && s!.t[k + 1] <= common) k++; return { code: ds[i].code, t: s!.t.slice(k), v: s!.v.slice(k).map((v) => Math.round((v / s!.v[k]) * 1e6) / 1e4) }; }) };
    }
    return { ...data.facts, funds: ds.map((d) => ({ ...d, series: undefined })), chart, chartNote: chart ? null : "A rebased chart needs NAV history for every fund over this range; try a shorter one.", notAvailable: ds[0].notAvailable } as unknown as T;
  }
  const sub = url.pathname.match(/^\/api\/mf\/(\d+)\/(facts|portfolio)$/);
  if (sub?.[2] === "portfolio") return DEMO_PORTFOLIO as unknown as T;   // labelled DEMO DATA in its source line
  if (sub) return { code: Number(sub[1]), order: ["aum", "terRegular", "terDirect", "exitLoad", "benchmark", "managers", "riskometer", "launchDate", "minInvestment", "category", "amc"],
    facts: Object.fromEntries(["aum", "terRegular", "terDirect", "exitLoad", "benchmark", "managers", "riskometer", "launchDate", "minInvestment"].map((k) => [k, { unavailable: "Not loaded in this preview." }])) } as unknown as T;
  if (url.pathname === "/api/mf/hot") return { ...data.facts, basis: null, items: data.rows.filter((r) => r.optionClass === "Growth").slice(0, 10).map((r, i) => ({ ...r, rank: i + 1 })) } as unknown as T;
  const one = url.pathname.match(/^\/api\/mf\/(\d+)$/);
  if (one) { const d = data.details[one[1]]; if (!d) throw notFound("This preview holds 67 schemes; the live site has every scheme."); return d as T; }
  // list
  const q = (p.get("q") || "").trim();
  let rows = data.rows.filter((r) => (p.get("stopped") === "true" || r.active)
    && (!p.get("category") || r.category === p.get("category")) && (!p.get("amc") || r.amc === p.get("amc")) && (!p.get("plan") || r.plan === p.get("plan")) && (!p.get("option") || r.optionClass === p.get("option")));
  for (const k of ["1y", "5y"] as const) {
    const lo = num(p.get("min" + k)), hi = num(p.get("max" + k)), f = `r${k}` as "r1y";
    if (lo != null) rows = rows.filter((r) => r[f] != null && r[f]! >= lo);
    if (hi != null) rows = rows.filter((r) => r[f] != null && r[f]! <= hi);
  }
  let ranked = rows.map((r) => ({ r, s: q ? score(q, `${r.name} ${r.amc}`) : 1 })).filter((x) => x.s > 0);
  const sort = p.get("sort") as keyof FundRow | null, dir = p.get("dir") === "desc" ? -1 : 1;
  if (sort) ranked.sort((a, b) => { const x = a.r[sort], y = b.r[sort]; return x == null ? 1 : y == null ? -1 : x < y ? -dir : x > y ? dir : 0; });
  else ranked.sort((a, b) => b.s - a.s || a.r.name.localeCompare(b.r.name));
  const size = Number(p.get("size") || 50), page = Number(p.get("page") || 1);
  return { ...data.facts, total: ranked.length, page, size, pages: Math.max(1, Math.ceil(ranked.length / size)), items: ranked.slice((page - 1) * size, page * size).map((x) => x.r) } as unknown as T;
}
