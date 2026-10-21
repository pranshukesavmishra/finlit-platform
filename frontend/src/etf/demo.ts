// DEMO MODE (VITE_DEMO=1): answers /api/etf calls from real recorded data for 12 ETFs (src/etf/demoData.json, taken from the live API on 21 Oct 2026).
// Search, filters and sorting are re-done here in a simple way; the live site does them on the server.
import { rebase, type EtfCompare, type EtfDetail, type EtfItem, type EtfList, type Point, type RangeKey } from "../lib/etf";
import { distance } from "../lib/metricSearch";

type Data = { meta: { asOf: string; updatedAt: string; source: string; disclaimer: string }; items: EtfItem[]; categories: { key: string; label: string; group: string; count: number }[];
  details: Record<string, { detail: Omit<EtfDetail, "series">; series: Record<RangeKey, EtfDetail["series"]> }> };
let cache: Promise<Data> | null = null;
const load = () => (cache ??= import("./demoData.json").then((m) => m.default as unknown as Data));
const words = (s: string) => s.toLowerCase().match(/[a-z0-9]+/g) ?? [];
const FIELD: Record<string, keyof EtfItem> = { price: "price", change: "changePct", ret1m: "ret1m", ret6m: "ret6m", ret1y: "ret1y", ret3y: "ret3y", ret5y: "ret5y", cagr3y: "cagr3y", cagr5y: "cagr5y", vol1y: "vol1y", mdd1y: "mdd1y", mdd3y: "mdd3y", mdd5y: "mdd5y", turnover: "avgTurnover", premium: "premium", from52: "from52" };

export async function demoGet<T>(path: string): Promise<T> {
  const d = await load();
  const url = new URL(path, "http://demo");
  const p = url.searchParams;
  if (url.pathname === "/api/etf") {
    const q = words(p.get("q") ?? "");
    let rows = d.items.filter((i) => { const hw = words(`${i.name} ${i.symbol} ${i.isin} ${i.fundHouse ?? ""} ${i.categoryLabel ?? ""}`), hay = hw.join(" "); return q.every((w) => hay.includes(w) || (w.length >= 4 && hw.some((x) => distance(w, x.slice(0, w.length)) <= 1))); });
    const cats = (p.get("category") ?? "").split(",").filter(Boolean);
    if (cats.length) rows = rows.filter((i) => cats.includes(i.category ?? "none"));
    const assets = (p.get("asset") ?? "").split(",").filter(Boolean);
    if (assets.length) rows = rows.filter((i) => assets.includes(i.assetClass ?? ""));
    let excluded = 0;
    for (const k of ["ret1y", "ret5y"] as const) {
      const lo = p.get(k + "Min"), hi = p.get(k + "Max");
      if (lo === null && hi === null) continue;
      rows = rows.filter((i) => { const v = i[k]; if (v == null) { excluded++; return false; } return (lo === null || lo === "" || v >= Number(lo)) && (hi === null || hi === "" || v <= Number(hi)); });
    }
    const sort = p.get("sort") ?? "turnover", desc = (p.get("order") ?? "desc") !== "asc";
    const val = (i: EtfItem) => (sort === "name" ? i.name.toLowerCase() : (i[FIELD[sort] ?? "avgTurnover"] as number | null));
    rows = [...rows].sort((a, b) => { const x = val(a), y = val(b); if (x == null) return y == null ? 0 : 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * (desc ? -1 : 1); });
    const limit = Math.min(100, Number(p.get("limit")) || 40), offset = Number(p.get("offset")) || 0;
    const groups = ["equity", "gold", "silver", "debt", "international"].map((k) => ({ key: k, label: k[0].toUpperCase() + k.slice(1), count: d.items.filter((i) => i.assetClass === k).length }));
    const out: EtfList = { items: rows.slice(offset, offset + limit), total: rows.length, universe: d.items.length, offset, limit, excluded, categories: d.categories, groups, ...d.meta };
    return out as T;
  }
  if (url.pathname === "/api/etf/compare") {
    const syms = (p.get("symbols") ?? "").split(",").filter((s) => d.details[s]);
    const range = (p.get("range") ?? "1Y").toUpperCase() as RangeKey;
    const lines: Record<string, Point[]> = {};
    for (const s of syms) lines[s] = d.details[s].series[range].points;
    const start = syms.map((s) => lines[s][0]?.[0] ?? "").sort().pop() || null;
    const out: EtfCompare = { symbols: syms, range, start: start ? String(start) : null, items: syms.map((s) => d.items.find((i) => i.symbol === s)!), series: start ? rebase(lines, String(start)) : {}, notes: [], ...d.meta };
    return out as T;
  }
  const sub = url.pathname.match(/^\/api\/etf\/([A-Za-z0-9&_.-]+)\/(facts|portfolio)$/);
  if (sub) {
    const why = "Fund-house disclosures are not part of the offline demo";
    return (sub[2] === "facts" ? { symbol: sub[1], isin: "", unavailable: why, facts: {}, disclaimer: d.meta.disclaimer } : { symbol: sub[1], isin: "", unavailable: why, holdings: [], exited: [], summary: null, asOf: null }) as T;
  }
  const m = url.pathname.match(/^\/api\/etf\/([A-Za-z0-9&_.-]+)$/);
  const hit = m && d.details[m[1].toUpperCase()];
  if (!hit) throw Object.assign(new Error("Not in the demo"), { status: 404, body: {} });
  const range = (p.get("range") ?? "1Y").toUpperCase() as RangeKey;
  const dt = hit.detail;
  const headline = dt.headline ?? (["1d", "1y", "5y"] as const).map((key) => {      // recorded before the returns block existed: rebuilt from the same recorded figures
    const value = key === "1d" ? dt.changePct : key === "1y" ? dt.ret1y : dt.ret5y;
    return { key, label: key === "1d" ? "1 day" : key === "1y" ? "1 year" : "5 years", value, annualised: key === "5y" ? dt.cagr5y : null, from: null, to: null,
      why: value == null ? (dt.why?.[key === "1d" ? "change" : `ret_${key}`] ?? "Not enough price history") : null,
      basis: key === "1d" ? "Change from the previous close" : "Price change, dividends not included" + (key === "5y" ? " (total over the five years, not per year)" : "") };
  });
  return { ...dt, headline, series: hit.series[range] ?? hit.series["1Y"] } as T;
}
