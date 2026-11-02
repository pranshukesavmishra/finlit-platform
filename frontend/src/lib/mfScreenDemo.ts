// DEMO MODE (VITE_DEMO=1) of the Mutual Fund Screener: answers /api/mf?extra=true and /api/mf/filters?screen=true in the browser from the 67 real AMFI schemes of the recording.
// What the recording lacks (expense ratio, fund size, SIP returns, risk, portfolio and category figures) is filled with SAMPLE values worked out from the scheme code so
// the page can be looked at and layout-tested. They are not real figures: the page says so in a banner whenever this file is in use. Never part of a live build.
import type { FundRow } from "./mf";
import { classify } from "./mfCategories";
import { NUM } from "./mfScreenDefs";
import { figureOf, parseQuery, rangeOf, type ExtraFigs, type ScreenFacets, type ScreenRow, type SQ } from "./mfScreen";

const EDGES: Record<string, number[]> = {
  aum: [0, 50, 100, 250, 500, 1000, 2000, 5000, 10000, 25000, 50000, 100000, 250000], age: [0, 1, 2, 3, 5, 7, 10, 15, 20, 30], aum_share: [0, 0.5, 1, 2, 5, 10, 20, 50, 100],
  na_chg: [-30, -10, -5, -2, 2, 5, 10, 30], r1d: [-3, -1, -0.5, 0, 0.5, 1, 3], r1m: [-10, -5, -2, 0, 2, 5, 10], r6m: [-20, -10, -5, 0, 5, 10, 20, 40],
  r1y: [-40, -20, -10, 0, 5, 10, 15, 20, 30, 40, 60], r3y: [-10, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40], r5y: [-5, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40],
  sip3y: [-10, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40], sip5y: [-5, 0, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40], ex1y: [-20, -10, -5, -2, 0, 2, 5, 10, 20, 30],
  ex3y: [-20, -10, -5, -2, 0, 2, 5, 10, 20, 30], ex5y: [-20, -10, -5, -2, 0, 2, 5, 10, 20, 30], consist: [0, 20, 35, 45, 55, 65, 80, 100], ter: [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3.5],
  ter_rel: [0, 0.5, 0.7, 1, 1.3, 1.5, 2, 3], ter_gap: [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3], fee_share: [0, 5, 10, 15, 20, 30, 50, 100], exit_pct: [0, 0.25, 0.5, 1, 1.5, 2, 3, 5],
  vol1: [0, 2, 5, 8, 12, 16, 20, 25, 30, 40, 60], vol3: [0, 2, 5, 8, 12, 16, 20, 25, 30, 40, 60], fall: [0, 2, 5, 10, 15, 20, 30, 40, 60], worst_m: [0, 0.25, 0.5, 1, 2, 4, 6, 10, 20, 40],
  worst_12m: [0, 0.5, 1, 2, 5, 10, 20, 30, 50], neg_share: [0, 10, 20, 30, 40, 50, 70, 100], below_high: [0, 10, 25, 50, 75, 100], down_cap: [0, 50, 70, 90, 100, 110, 130, 200],
  sharpe: [-2, -1, 0, 0.5, 1, 1.5, 2, 3, 5], eq_pct: [0, 10, 25, 40, 65, 80, 100], debt_pct: [0, 10, 25, 50, 75, 100], cash_pct: [0, 2, 5, 10, 25, 50, 100], other_pct: [0, 2, 5, 10, 25, 50, 100],
  n_hold: [0, 10, 25, 50, 75, 100, 150, 250, 500], top10: [0, 30, 50, 70, 100], max_hold: [0, 2, 5, 8, 12, 20, 40, 100], cf_aum_mom: [-10, -5, -2, 0, 2, 5, 10], cf_aum_yoy: [-20, 0, 10, 20, 40, 80],
  cf_folio_mom: [-3, -1, 0, 1, 2, 5], cf_share: [0, 0.5, 1, 2, 5, 10, 20, 50],
  up_m: [-5, 0, 1, 2, 4, 6, 10, 15, 20, 30], cy1: [-40, -20, -10, 0, 5, 10, 15, 20, 30, 40, 60], cy2: [-40, -20, -10, 0, 5, 10, 15, 20, 30, 40, 60], cy3: [-40, -20, -10, 0, 5, 10, 15, 20, 30, 40, 60],
  vol_rel: [0, 0.5, 0.7, 0.9, 1, 1.1, 1.3, 1.5, 2, 3], down_dev: [0, 1, 2, 4, 6, 8, 10, 15, 20, 30],
};
const rand = (seed: number) => { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; };
const r1 = (v: number, d = 1) => Math.round(v * 10 ** d) / 10 ** d;
const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };
/** The recording also holds 1M, 6M and drawdown figures that FundRow does not declare. */
const rec = (r: FundRow) => r as FundRow & { r1m?: number | null; r6m?: number | null; mdd?: number | null };
const TAGS: Record<string, string[]> = { "sectoral-thematic": ["pharma"], "index-funds": ["i_nifty50"] };

export function demoRows(rows: FundRow[]): ScreenRow[] {
  const cls = (r: FundRow) => classify(r.category);
  const group = (r: FundRow) => `${cls(r).key}|${r.plan}`;
  const med3 = new Map<string, number | null>(), med1 = new Map<string, number | null>(), med5 = new Map<string, number | null>();
  const gr = rows.filter((r) => r.active && r.optionClass === "Growth");
  for (const g of new Set(gr.map(group))) { const m = gr.filter((r) => group(r) === g); med1.set(g, median(m.filter((r) => r.r1y != null).map((r) => r.r1y!))); med3.set(g, median(m.filter((r) => r.r3y != null).map((r) => r.r3y!))); med5.set(g, median(m.filter((r) => r.r5y != null).map((r) => r.r5y!))); }
  return rows.map((r) => {
    const u = rand(r.code), c = cls(r), debt = c.tab === "debt", g = r.optionClass === "Growth" && r.active;
    const sip3y = g && r.r3y != null ? r1(r.r3y + (u() - 0.5) * 4) : null, ter = r1(debt ? 0.2 + u() * 0.7 : r.plan === "Direct" ? 0.3 + u() * 0.9 : 1.1 + u() * 1.3, 2), aum = r1(10 ** (2 + u() * 3.6), 0);
    const ex = (v: number | null, m: number | null | undefined) => (g && v != null && m != null ? r1(v - m) : null);
    const vol3 = g && r.r3y != null ? r1(debt ? 0.4 + u() * 3 : 11 + u() * 12) : null, hasPort = u() > 0.2, eq = debt ? 0 : r1(60 + u() * 38);
    const x: ExtraFigs = {
      age: r1(1 + u() * 14), launch: null, ckey: c.key, tags: TAGS[c.key] ?? [], isEtf: false, r1m: rec(r).r1m ?? null, r6m: rec(r).r6m ?? null,
      ex: { "1y": ex(r.r1y, med1.get(group(r))), "3y": ex(r.r3y ?? null, med3.get(group(r))), "5y": ex(r.r5y, med5.get(group(r))) },
      rank: { "1y": null, "3y": g && r.r3y != null ? { rank: 1 + gr.filter((o) => group(o) === group(r) && (o.r3y ?? -1e9) > r.r3y!).length, of: gr.filter((o) => group(o) === group(r) && o.r3y != null).length } : null, "5y": null },
      aumRank: null, aumShare: r1(u() * 4, 2), naChg: r1((u() - 0.4) * 20), houseAum: null, terRel: r1(0.6 + u() * 0.9, 2), terGap: r1(0.3 + u() * 1.2, 2), feeShare: r1(3 + u() * 25, 0),
      exit: { state: "nil", pct: 0, days: null },
      risk: { vol1: vol3 == null ? null : r1(vol3 * (0.8 + u() * 0.4)), vol3, worstMonth: g ? r1(debt ? u() * 0.8 : 2 + u() * 9, 2) : null, worstYear: g ? r1(debt ? u() * 3 : 8 + u() * 25) : null, negShare: g ? r1(debt ? u() * 15 : 25 + u() * 25, 0) : null,
        belowHigh: g ? r1(20 + u() * 50, 0) : null, downCapture: g ? r1(70 + u() * 50, 0) : null, sharpe: g && vol3 && r.r3y != null ? r1((r.r3y - 6) / vol3, 2) : null, consistency: g ? r1(30 + u() * 50, 0) : null,
        upMonth: g ? r1(debt ? 0.4 + u() * 0.8 : 3 + u() * 9) : null, downDev: vol3 == null ? null : r1(vol3 * (0.45 + u() * 0.25)), volRel: vol3 == null ? null : r1(0.7 + u() * 0.6, 2) },
      calYears: g ? { "1": r1(debt ? 6 + u() * 2 : -5 + u() * 35), "2": r1(debt ? 6 + u() * 2 : -5 + u() * 35), "3": r.r3y != null ? r1(debt ? 5 + u() * 3 : -10 + u() * 40) : null } : undefined,
      portfolio: hasPort ? { asOf: "2026-09-30", equity: eq, debt: r1(100 - eq - 2), cash: 2, other: 0, holdings: Math.round(25 + u() * 60), top10: r1(30 + u() * 35), largest: r1(3 + u() * 8), sector: debt ? null : "Banks", sectorPct: debt ? null : r1(12 + u() * 20) } : null,
      category: { month: "2026-09-01", flow: r1((u() - 0.3) * 6000, 0), streak: u() > 0.5 ? 3 : 0, aumMom: r1((u() - 0.3) * 6), aumYoy: r1(u() * 40), share: r1(1 + u() * 9), folioMom: r1((u() - 0.3) * 3) },
    };
    return { ...r, r3y: r.r3y ?? null, ter: g ? ter : null, terDate: null, aum: g ? aum : null, aumAsOf: "2026-09-30", aumKind: "q", sip3y, sip5y: g && r.r5y != null ? r1(r.r5y + (u() - 0.5) * 4) : null,
      fall3y: g && rec(r).mdd != null ? rec(r).mdd! : null, x } as ScreenRow;
  });
}

type Pred = [string, (r: ScreenRow) => boolean];
function predicates(q: SQ): Pred[] {
  const out: Pred[] = [];
  const subKey = (r: ScreenRow) => classify(r.category).key, tab = (r: ScreenRow) => classify(r.category).tab;
  if (q.q.trim()) { const k = q.q.trim().toLowerCase(); out.push(["q", (r) => `${r.name} ${r.amc}`.toLowerCase().includes(k)]); }
  if (q.group) out.push(["type", (r) => tab(r) === q.group]);
  if (q.subs.length) out.push(["subs", (r) => q.subs.includes(subKey(r))]);
  if (q.cap.length) { const m: Record<string, string[]> = { large: ["large-cap"], largemid: ["large-mid-cap"], mid: ["mid-cap"], small: ["small-cap"], multiflexi: ["multi-cap", "flexi-cap"] }; out.push(["cap", (r) => q.cap.some((c) => m[c].includes(subKey(r)))]); }
  if (q.style.length === 1) { const pas = (r: ScreenRow) => ["index-funds", "etf", "gold-etf"].includes(subKey(r)); out.push(["style", (r) => (q.style[0] === "passive") === pas(r)]); }
  if (q.amcs.length) out.push(["amcs", (r) => q.amcs.includes(r.amc)]);
  if (q.plans.length && q.plans.length < 3) out.push(["plans", (r) => q.plans.includes(r.plan)]);
  if (q.options.length && q.options.length < 3) out.push(["options", (r) => q.options.includes(r.optionClass)]);
  if (q.status === "active") out.push(["status", (r) => r.active]); else if (q.status === "stopped") out.push(["status", (r) => !r.active]);
  if (q.inst.length === 1) out.push(["inst", (r) => (q.inst[0] === "etf") === !!r.x?.isEtf]);
  if (q.tags.length) out.push(["tags", (r) => q.tags.some((t) => r.x?.tags.includes(t))]);
  if (q.tick.includes("has_ter")) out.push(["tick", (r) => r.ter != null]);
  if (q.tick.includes("has_port")) out.push(["tick", (r) => !!r.x?.portfolio]);
  if (q.tick.includes("has_hist5")) out.push(["tick", (r) => r.r5y != null]);
  if (q.tick.includes("noneg36")) out.push(["tick", (r) => r.x?.risk.negShare === 0]);
  for (const f of Object.keys(q.rng)) {
    const [lo, hi] = rangeOf(q, f), nd = q.nd.includes(f);
    out.push(["rng:" + f, (r) => { const v = figureOf(r, f); return v == null ? nd : (lo == null || v >= lo) && (hi == null || v <= hi); }]);
  }
  return out;
}
const run = (rows: ScreenRow[], preds: Pred[], skip: string[] = []) => rows.filter((r) => preds.every(([g, fn]) => skip.includes(g) || fn(r)));

const SORT_GET: Record<string, (r: ScreenRow) => number | string | null> = {
  name: (r) => r.name, aum: (r) => r.aum ?? null, r1y: (r) => r.r1y, r3y: (r) => r.r3y ?? null, r5y: (r) => r.r5y, sip3y: (r) => r.sip3y ?? null, sip5y: (r) => r.sip5y ?? null, ter: (r) => r.ter ?? null,
  fall: (r) => (r.fall3y == null ? null : -r.fall3y), age: (r) => r.x?.age ?? null, vol: (r) => r.x?.risk.vol3 ?? null, sharpe: (r) => r.x?.risk.sharpe ?? null,
  rank3y: (r) => (r.x?.rank["3y"] ? r.x.rank["3y"]!.rank / r.x.rank["3y"]!.of : null), ex3y: (r) => r.x?.ex["3y"] ?? null,
};

export function demoScreenList(all: ScreenRow[], facts: object, p: URLSearchParams) {
  const q = parseQuery(p);
  let rows = run(all, predicates(q));
  const get = SORT_GET[q.sort] ?? SORT_GET.aum, sg = q.dir === "desc" ? -1 : 1;
  rows = [...rows].sort((a, b) => { const x = get(a), y = get(b); return x == null ? (y == null ? 0 : 1) : y == null ? -1 : (x < y ? -1 : x > y ? 1 : 0) * sg; });
  if (q.family) { const seen = new Set<string>(); rows = rows.filter((r) => { const k = `${r.amc}|${r.name}`; if (seen.has(k)) return false; seen.add(k); return true; }); }
  const size = Number(p.get("size") || 50), page = q.page;
  return { ...facts, total: rows.length, page, size, pages: Math.max(1, Math.ceil(rows.length / size)), items: rows.slice((page - 1) * size, page * size) };
}

export function demoScreenFacets(all: ScreenRow[], filters: { amcs: unknown[]; totals: unknown } & object, p: URLSearchParams) {
  const q = parseQuery(p);
  const preds = predicates(q), res = run(all, preds);
  const count = (skip: string[], key: (r: ScreenRow) => string | string[]) => { const m: Record<string, number> = {}; for (const r of run(all, preds, skip)) for (const k of [key(r)].flat()) m[k] = (m[k] || 0) + 1; return m; };
  const numeric: ScreenFacets["numeric"] = {};
  for (const d of NUM) {
    const edges = EDGES[d.key] ?? [0, 1, 2, 3], bins = new Array(edges.length - 1).fill(0); let n = 0, m = 0;
    for (const r of run(all, preds, ["rng:" + d.key])) { m++; const v = figureOf(r, d.key); if (v == null) continue; n++; let i = 0; while (i < bins.length - 1 && v >= edges[i + 1]) i++; bins[i]++; }
    numeric[d.key] = { edges, bins, n, m };
  }
  const tabs = count(["type"], (r) => classify(r.category).tab);
  const subMap = new Map<string, { key: string; label: string; tab: string; n: number }>();
  for (const r of run(all, preds, ["subs"])) { const c = classify(r.category); const s = subMap.get(c.key) ?? { key: c.key, label: c.label, tab: c.tab, n: 0 }; s.n++; subMap.set(c.key, s); }
  const subs = [...subMap.values()].sort((a, b) => b.n - a.n);
  const amcN = count(["amcs"], (r) => r.amc);
  const capOf = (r: ScreenRow) => { const k = classify(r.category).key; return k === "large-cap" ? "large" : k === "large-mid-cap" ? "largemid" : k === "mid-cap" ? "mid" : k === "small-cap" ? "small" : k === "multi-cap" || k === "flexi-cap" ? "multiflexi" : "-"; };
  const tagN: Record<string, number> = {};
  for (const r of run(all, preds, ["tags"])) for (const t of r.x?.tags ?? []) tagN[t] = (tagN[t] || 0) + 1;
  const pts = res.filter((r) => r.r3y != null && r.x?.risk.vol3 != null).slice(0, 400);
  const screen: ScreenFacets = {
    total: res.length, numeric, type: tabs, subs, cap: count(["cap"], capOf), style: count(["style"], (r) => (["index-funds", "etf"].includes(classify(r.category).key) ? "passive" : "active")), mat: {}, struct: { open: res.length },
    amcs: Object.entries(amcN).map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n), house: {}, plans: count(["plans"], (r) => r.plan), options: count(["options"], (r) => r.optionClass), inst: { fund: res.length, etf: 0 },
    status: count(["status"], (r) => (r.active ? "active" : "stopped")), fresh: {}, aumbasis: { q: res.length, m: 0 }, aumrank: {}, exit: {}, chk: {}, chk_each: {}, rk: {},
    tick: { has_ter: res.filter((r) => r.ter != null).length, has_port: res.filter((r) => r.x?.portfolio).length, has_hist5: res.filter((r) => r.r5y != null).length, noneg36: res.filter((r) => r.x?.risk.negShare === 0).length },
    tags: [{ tag: "pharma", kind: "theme", label: "Pharma & Healthcare", n: tagN.pharma || 0 }, { tag: "i_nifty50", kind: "index", label: "Nifty 50", n: tagN.i_nifty50 || 0 }],
    sectors: [{ name: "Banks", n: res.filter((r) => r.x?.portfolio?.sector === "Banks").length }], portfolio: { latest: res.filter((r) => r.x?.portfolio).length, none: res.filter((r) => !r.x?.portfolio).length },
    cflow: { pos: res.length, neg: 0 }, cstreak: {}, csize: {},
    built: { rows: all.length, run: "2026-10-21", portfolioDate: "2026-09-30", flowMonth: "2026-09-01", tagged: 12, indexTagged: 4 },
    scatter: { points: pts.map((r) => [r.code, r.name, r.r3y!, r.x!.risk.vol3!] as [number, string, number, number]), eligible: pts.length, shown: pts.length },
    flows: [...new Set(res.map((r) => classify(r.category).key))].slice(0, 4).map((k, i) => ({ key: k, label: classify(res.find((r) => classify(r.category).key === k)!.category).label, months: ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"],
      net: [0, 1, 2, 3, 4, 5].map((j) => Math.round((rand(i * 31 + j)() - 0.35) * 9000)) })),
  };
  return { ...filters, screen };
}
