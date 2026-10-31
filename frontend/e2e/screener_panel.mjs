// Screener filter panel and page layout, with every /api/** call mocked. Screenshots at 1280 and 390, light and dark, with and without filters.
//   node e2e/screener_panel.mjs http://127.0.0.1:5199 /path/to/out
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), out = process.argv[3] || ".";
const SECT = ["Capital Goods", "Services", "Banks", "IT", "Auto", "Pharma", "Metals", "Energy", "FMCG", "Realty"];
const rows = Array.from({ length: 300 }, (_, i) => {
  const sc = (k) => (i % 11 === 0 ? null : 20 + ((i * k) % 78));
  return { symbol: "SYM" + i, name: "Company " + i + " Limited", sector: i % 17 === 0 ? null : SECT[i % SECT.length], overall: sc(7), band: null, pillar_quality: sc(3), pillar_growth: sc(5), pillar_profitability: sc(11), pillar_balance: sc(13), pillar_technical: sc(17),
    price: 100 + i, market_cap: 100000 - i * 300, pe: null, pb: null, roe: null, roce: null, dividend_yield: null, debt_to_equity: null, sales_cagr: null, profit_cagr: null, operating_margin: null, change_pct: 0.5, return_1m: 1, return_1y: 5, scored: i % 11 !== 0,
    prism_final: sc(19), prism_fundamental: sc(3), prism_valuation: sc(5), prism_quality: sc(7), prism_risk: sc(9), prism_st_score: 0, prism_lt_score: 10, prism_label: "strong" };
});
const metric = (key, label, unit = "x") => ({ key, label, unit, better: "higher", tier: "basic", say: label + " in plain words.", digits: 1, locked: false, stats: { min: 0, p10: 5, p50: 15, p90: 40, max: 80, n: 3000, hist: [3, 5, 9, 12, 8, 4, 2] } });
const catalog = { plan: "gold", total: 3635, withReport: 1200, updatedAt: "2026-10-30", sectors: SECT.map((n, i) => ({ name: n, n: 400 - i * 20 })), industries: [], indices: [{ code: "N50", label: "Nifty 50", n: 50 }], caps: [{ name: "Large", n: 100 }, { name: "Mid", n: 150 }, { name: "Small", n: 3385 }], bands: [{ key: "strong", label: "Strong", locked: false }, { key: "watch", label: "Watch", locked: false }],
  limits: { rows: null, export: true }, defaultColumns: ["pe", "roe"],
  groups: [["valuation", "Valuation"], ["profit", "Profitability"], ["growth", "Growth"], ["health", "Financial health"], ["own", "Ownership"], ["q", "Quarterly results"], ["flags", "Red flags"], ["trend", "Trend"], ["div", "Dividends"], ["eff", "Efficiency"], ["size", "Size"], ["model", "FinLit model"]].map(([id, label]) => ({ id, label, tier: "basic", metrics: [metric("pe", "P/E"), metric("pb", "P/B"), metric("roe", "ROE", "%")].map((m) => ({ ...m, key: id + "_" + m.key })) })) };
catalog.defaultColumns = ["valuation_pe", "valuation_roe"];
const result = { total: 3635, offset: 0, limit: 50, capped: false, took: 12, columns: ["valuation_pe", "valuation_roe"], rows: rows.slice(0, 50).map((r) => ({ symbol: r.symbol, name: r.name, sector: r.sector, cap: "Large", band: "strong", v: { valuation_pe: 20, valuation_roe: 14 } })) };
const cover = { total: 300, rated: 120, provisional: 10, as_of: "2026-10-30", per_night: 200 };

async function mock(ctx) {
  await ctx.route("**/api/**", (route) => {
    const u = new URL(route.request().url()).pathname;
    const j = (b) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (u.endsWith("/auth/me")) return j({ user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, compare: 4, holdings: 500 }, csrf: "t", showcase: [] });
    if (u.endsWith("/screener/universe")) return j({ rows, sample: false, as_of: "2026-10-30", prism: cover });
    if (u.endsWith("/screener/catalog")) return j(catalog);
    if (u.endsWith("/screener/query")) return j(result);
    if (u.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    if (u.endsWith("/stocks/search-index")) return j({ rows: [], sectors: [], mc: [] });
    if (/notifications|alerts|indices|companies/.test(u)) return j([]);
    return j({});
  });
}
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0;
const only = process.env.ONLY;
const pages = [["basic", "/score-screener", ""], ["basic", "/score-screener", "?sector=IT&sector=Banks&cap=Large&f=high&q=high&omin=60"],
  ["advanced", "/advanced-score-screener", ""], ["advanced", "/advanced-score-screener", "?sector=IT&zmin=50&st=pos"],
  ["full", "/screener", ""], ["full", "/screener", "?s=" + encodeURIComponent(JSON.stringify({ ranges: { valuation_pe: { max: 30 } }, sectors: ["IT"], industries: [], indices: [], caps: ["Large"], bands: [] }))]];
for (const [w, h, n] of [[1280, 1000, "d"], [390, 900, "m"]]) for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  await mock(ctx);
  for (const [name, path, qs] of pages.filter(([nm]) => !only || only.includes(nm))) {
    const p = await ctx.newPage();
    p.on("console", (m) => { if (process.env.DBG && m.type() === "error" && !/403|Failed to load/.test(m.text())) console.log("CONSOLE", m.text().slice(0, 500)); });
    p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", name, (e.stack || String(e)).slice(0, 600)); });
    await p.goto(base + path + qs, { waitUntil: "networkidle" }); await p.waitForTimeout(900);
    const tag = `${name}-${qs ? "active" : "plain"}-${n}-${theme}`;
    const overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 1) { bad++; console.log("OVERFLOW", tag, overflow, await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 2).slice(0, 5).map((e) => e.tagName + "." + e.className.toString().slice(0, 40) + ":" + Math.round(e.getBoundingClientRect().right)).join(" | "))); }
    await p.screenshot({ path: `${out}/${tag}.png`, fullPage: false });
    if (n === "m") {
      const btn = p.locator(".fgx-kpi").last(); await btn.click().catch(() => {}); await p.waitForTimeout(500);
      await p.screenshot({ path: `${out}/${tag}-panel.png` });
    } else await p.screenshot({ path: `${out}/${tag}-full.png`, fullPage: true });
    if (process.env.DBG) { console.log((await p.evaluate(() => document.body.innerText)).slice(0, 200)); process.exit(0); }
    await p.close();
  }
  await ctx.close();
}
await browser.close(); console.log(bad ? "ISSUES " + bad : "DONE");
