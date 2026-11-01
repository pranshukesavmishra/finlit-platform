// LAYOUT GUARD: fails when a page collapses, goes blank, scrolls sideways, clips text or throws.   See docs/LAYOUT-GUARD.md
//   npm run layout-guard                           builds the demo site, serves it, runs every check (exit 1 on any failure)
//   node e2e/layout_guard.mjs http://127.0.0.1:5199 [outDir]            same checks against a server you already run (demo build)
//   GUARD_MODE=api node e2e/layout_guard.mjs http://127.0.0.1:5199      normal build, /api/** mocked: the server-side stock screener (ScreenerPro)
// Env: CHROME=/path/to/chrome, GUARD_FULL=1 (every width x theme x storage state; default samples the risky ones), GUARD_ONLY=screener (substring of a page name), GUARD_SHOTS=1 (screenshot every case)
import { chromium } from "playwright";
import fs from "node:fs";

import { execSync, spawn } from "node:child_process";
const MODE = process.env.GUARD_MODE === "api" ? "api" : "demo";
const out = process.argv[3] || ".layout-guard";
let server = null, base = (process.argv[2] || "").replace(/\/$/, "");
if (!base) {   // no address given: build the site (demo build, or the normal build for api mode) and serve it
  const dir = "dist-guard-" + MODE; base = "http://127.0.0.1:5198";
  execSync(`npx vite build --outDir ${dir}`, { stdio: "inherit", env: { ...process.env, ...(MODE === "demo" ? { VITE_DEMO: "1" } : {}) } });
  server = spawn("npx", ["vite", "preview", "--outDir", dir, "--port", "5198", "--host", "127.0.0.1", "--strictPort"], { stdio: "ignore" });
  for (let i = 0; i < 40; i++) { try { await fetch(base + "/"); break; } catch { await new Promise((r) => setTimeout(r, 250)); } }
}
const WIDTHS = [1440, 1055, 768, 390, 360];
// Windows display scaling shrinks the CSS width (1366 at 125% = 1093, at 150% = 911; 1920 at 150% = 1280; browser zoom does the same); the browser's own bars cost more.
// Extra widths run in one theme each, with the device pixel ratio cycling 1 / 1.25 / 1.5.
const EXTRA = [900, 945, 1000, 1093, 1229, 1366, 865];
const THEMES = ["dark", "light"];
const MIN_MAIN = 320;           // a results / main-content container is never narrower than this at >= 768 px
fs.mkdirSync(out, { recursive: true });

// ---- pages: [name, path, {table: must show a <table>, modes}] ----
const PAGES = [
  ["home", "/", {}],
  ["screener", "/screener", { table: true, split: "lite", sel: ".scr-main" }],
  ["score-screener", "/score-screener", { table: true, split: "score", sel: ".scr-main" }],
  ["advanced-score-screener", "/advanced-score-screener", { table: true, split: "score-adv", sel: ".scr-main" }],
  ["fund-score-screener", "/fund-score-screener", { table: true, sel: ".fgx-fl > :not(aside)" }],
  ["mf-screener", "/funds/screener", { table: true, sel: ".mfs-main" }],
  ["query-builder", "/query-builder", {}],
  ["stock", "/stocks/RELIANCE", {}],
  ["prism", "/prism", {}],
  ["compare", "/compare", {}],
  ["portfolio", "/portfolio", {}],
  ["holdings", "/holdings", {}],
  ["funds", "/funds", {}],
  ["fundamentals", "/premium/fundamentals", {}],
  ["plans", "/plans", {}],
  ["faq", "/faq", {}],
];
// ---- saved UI state. SPLIT = the screener's own filter-panel width key. Current format is {"v":2,"d":value} (src/lib/persist.ts). ----
// GUARD_LEGACY=1 writes the bare pre-versioning format instead ("620", "1"), to run the guard against a build from before the persist.ts change.
const v2 = (d) => (process.env.GUARD_LEGACY ? (typeof d === "boolean" ? (d ? "1" : "0") : String(d)) : JSON.stringify({ v: 2, d }));
const STATES = [
  ["plain", {}],
  ["shell-folded", { "finlit-side": v2(true) }],
  ["panel-620", { SPLIT: v2(620) }],
  ["panel-0", { SPLIT: v2(0) }],
  ["shell-folded+panel-620", { "finlit-side": v2(true), SPLIT: v2(620) }],
  // what an OLDER release left behind (bare numbers / flags, old column lists, collapsed-panel flags): must be ignored, never trusted
  ["stale-old-release", { "finlit-side": "1", SPLIT: "620", "finlit-side-groups": '{"Research":true}', "finlit.screener.cols": '["pe","roe","oldcol"]', "finlit.screener.collapsed": "1", "finlit-screener-filters": "hidden", "finlit-plan": "gold", "finlit.state": '{"v":1}' }],
  ["stale-side-0", { SPLIT: "0", "finlit-side": "0" }],
  // damaged values
  ["corrupt-json", { "finlit-side": "{{not json", SPLIT: "{", "finlit-side-groups": "[1,2", "finlit.screener.cols": "undefined", "finlit.state": "null" }],
  ["wrong-types", { "finlit-side": v2("yes"), SPLIT: v2("wide"), "finlit-side-groups": v2([1]), "finlit.screener.cols": "123" }],
  ["future-version", { "finlit-side": JSON.stringify({ v: 9, d: true }), SPLIT: JSON.stringify({ v: 9, d: 0 }) }],
  ["absurd-values", { SPLIT: v2(99999), "finlit-side": v2(true) }],
];
// ---- API mocks for GUARD_MODE=api (same shapes as e2e/screener_panel.mjs) ----
const SECT = ["Capital Goods", "Services", "Banks", "IT", "Auto", "Pharma", "Metals", "Energy", "FMCG", "Realty"];
const metric = (key, label, unit = "x") => ({ key, label, unit, better: "higher", tier: "basic", say: label + " in plain words.", digits: 1, locked: false, stats: { min: 0, p10: 5, p50: 15, p90: 40, max: 80, n: 3000, hist: [3, 5, 9, 12, 8, 4, 2] } });
const GROUPS = ["valuation", "profit", "growth", "health", "own", "q", "flags", "trend", "div", "eff", "size", "model"];
const catalog = { plan: "gold", total: 3635, withReport: 1200, updatedAt: "2026-10-30", sectors: SECT.map((n, i) => ({ name: n, n: 400 - i * 20 })), industries: [], indices: [{ code: "N50", label: "Nifty 50", n: 50 }], caps: [{ name: "Large", n: 100 }, { name: "Mid", n: 150 }], bands: [{ key: "strong", label: "Strong", locked: false }, { key: "watch", label: "Watch", locked: false }],
  limits: { rows: null, export: true }, defaultColumns: ["valuation_pe", "valuation_roe"],
  groups: GROUPS.map((id) => ({ id, label: id[0].toUpperCase() + id.slice(1), tier: "basic", metrics: [metric(id + "_pe", "P/E"), metric(id + "_pb", "P/B"), metric(id + "_roe", "ROE", "%")] })) };
const result = { total: 3635, offset: 0, limit: 50, capped: false, took: 12, columns: ["valuation_pe", "valuation_roe"], rows: Array.from({ length: 50 }, (_, i) => ({ symbol: "SYM" + i, name: "Company " + i + " Limited", sector: SECT[i % 10], cap: "Large", band: "strong", v: { valuation_pe: 20, valuation_roe: 14 } })) };
const uni = Array.from({ length: 300 }, (_, i) => { const sc = (k) => 20 + ((i * k) % 78); return { symbol: "SYM" + i, name: "Company " + i + " Limited", sector: SECT[i % 10], overall: sc(7), band: null, pillar_quality: sc(3), pillar_growth: sc(5), pillar_profitability: sc(11), pillar_balance: sc(13), pillar_technical: sc(17), price: 100 + i, market_cap: 100000 - i * 300, change_pct: 0.5, return_1m: 1, return_1y: 5, scored: true, prism_final: sc(19), prism_fundamental: sc(3), prism_valuation: sc(5), prism_quality: sc(7), prism_risk: sc(9), prism_st_score: 0, prism_lt_score: 10, prism_label: "strong" }; });
async function mockApi(ctx) {
  await ctx.route("**/api/**", (route) => {
    const u = new URL(route.request().url()).pathname;
    const j = (b) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (u.endsWith("/auth/me")) return j({ user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, compare: 4, holdings: 500 }, csrf: "t", showcase: [] });
    if (u.endsWith("/screener/universe")) return j({ rows: uni, sample: false, as_of: "2026-10-30", prism: { total: 300, rated: 120, provisional: 10, as_of: "2026-10-30", per_night: 200 } });
    if (u.endsWith("/screener/catalog")) return j(catalog);
    if (u.endsWith("/screener/query")) return j(result);
    if (u.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    if (u.endsWith("/stocks/search-index")) return j({ rows: [], sectors: [], mc: [] });
    if (/notifications|alerts|indices|companies/.test(u)) return j([]);
    return j({});
  });
}

// ---- measurements, run inside the page ----
function measure({ minMain, vw, sel, wantTable }) {
  const problems = [];
  const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const label = (e) => e.tagName.toLowerCase() + (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : "");
  const main = document.querySelector("main") || document.body;
  // 1. blank
  const mr = main.getBoundingClientRect(), text = (main.innerText || "").trim();
  if (mr.height < 200 || text.length < 40) problems.push(`BLANK page: main is ${Math.round(mr.height)}px tall with ${text.length} characters`);
  if (/Something went wrong on this page|A new version of FinLit is ready/.test(document.body.innerText)) problems.push("ERROR CARD is showing (a render error was caught)");
  // 2. sideways page scroll
  const over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  if (over > 1) {
    const wide = [...document.querySelectorAll("body *")].filter((e) => vis(e) && e.getBoundingClientRect().right > vw + 2 && !e.closest("[hidden],.sx-side,.side,.shell-scrim")).slice(0, 3).map((e) => `${label(e)}:${Math.round(e.getBoundingClientRect().right)}`);
    problems.push(`HORIZONTAL PAGE SCROLL ${over}px (${wide.join(", ")})`);
  }
  // 3. main content containers never squeezed under minMain (desktop/tablet only)
  if (vw >= 768) {
    for (const s of [sel, ".scr-main", ".scr-tw", ".qb-res", ".fgx-fl > :not(aside)", "main > .wrap", "main .stock-main"].filter(Boolean)) {
      for (const e of document.querySelectorAll(s)) { if (!vis(e) || e.closest("[hidden]")) continue; const w = e.getBoundingClientRect().width; if (w < minMain) problems.push(`NARROW container ${label(e)} is ${Math.round(w)}px (< ${minMain}) at ${vw}px wide`); }
    }
  }
  // 4. text squeezed to a few characters per line (the "one word per line" look), at any width
  for (const e of main.querySelectorAll("h1,h2,h3,p,b,span,small,a,button,label,li")) {
    if (!vis(e) || e.closest("table,[hidden],svg,.sr")) continue;
    const t = (e.innerText || "").trim(); if (t.length < 14 || e.children.length > 2) continue;
    const r = e.getBoundingClientRect(), lh = parseFloat(getComputedStyle(e).lineHeight) || parseFloat(getComputedStyle(e).fontSize) * 1.3;
    if (r.width < 70 && r.height > lh * 3.2) problems.push(`SQUEEZED text "${t.slice(0, 30)}" in ${label(e)}: ${Math.round(r.width)}x${Math.round(r.height)}px`);
  }
  // 5. visible text clipped outside its card
  for (const card of main.querySelectorAll(".card, article")) {
    if (!vis(card)) continue;
    const cr = card.getBoundingClientRect(), cs = getComputedStyle(card);
    for (const e of card.querySelectorAll("*")) {
      if (e.children.length || !(e.textContent || "").trim() || !vis(e)) continue;
      if (e.closest("table,[hidden],svg,.sr,.sr-only,.tape,.scr-colmenu,[role=menu],[role=listbox]")) continue;
      const pos = getComputedStyle(e).position; if (pos === "fixed" || pos === "sticky") continue;
      let scroller = false; for (let a = e.parentElement; a && a !== card; a = a.parentElement) { const o = getComputedStyle(a); if (/(auto|scroll)/.test(o.overflowX)) { scroller = true; break; } }
      if (scroller) continue;
      const r = e.getBoundingClientRect(), t = e.textContent.trim().slice(0, 28);
      if (r.right > cr.right + 2 || r.left < cr.left - 2) problems.push(`CLIPPED text "${t}" in ${label(e)} sticks out of ${label(card)} (${Math.round(r.left)}..${Math.round(r.right)} vs ${Math.round(cr.left)}..${Math.round(cr.right)})`);
      else if (/(hidden|clip)/.test(cs.overflowX) && e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).textOverflow !== "ellipsis" && getComputedStyle(e).whiteSpace === "nowrap" && !e.closest("button,a")) problems.push(`CLIPPED nowrap text "${t}" in ${label(e)}`);
    }
  }
  // 6. primary content
  if (wantTable && !main.querySelector("table")) problems.push("NO TABLE: this page must show a results table");
  return problems.slice(0, 8);
}

// ---- run ----
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
const only = process.env.GUARD_ONLY, full = !!process.env.GUARD_FULL;
const pages = PAGES.filter(([n]) => (!only || n.includes(only)) && (MODE === "demo" || ["screener", "score-screener", "advanced-score-screener", "fund-score-screener", "mf-screener", "query-builder"].includes(n)));
const cases = [];
const splitKey = (name, opt) => (MODE === "api" && name === "screener" ? "screener" : opt.split);   // ScreenerPro (api build) and ScreenerLite (demo build) remember the width under different keys
const withStore = (store, split) => Object.fromEntries(Object.entries(store).map(([k, v]) => [k === "SPLIT" ? "finlit.side." + split : k, v]));
for (const [name, path, opt] of pages) {
  for (const w of WIDTHS) for (const theme of THEMES) cases.push({ name, path, opt, w, theme, dpr: 1, state: "plain", store: {} });
  EXTRA.forEach((w, i) => cases.push({ name, path, opt, w, theme: THEMES[i % 2], dpr: [1, 1.25, 1.5][i % 3], state: "plain", store: {} }));
  if (opt.split || opt.sel === ".scr-main") for (const [sn, store] of STATES.slice(1)) {
    const ws = full ? [...WIDTHS, ...EXTRA] : sn.startsWith("shell") || sn.startsWith("panel") ? [1440, 1055, 768] : [1366, 1093, 1055, 900, 390];
    ws.forEach((w, i) => cases.push({ name, path, opt, w, theme: full ? THEMES[i % 2] : "dark", dpr: [1, 1.25, 1.5][i % 3], state: sn, store: withStore(store, splitKey(name, opt)) }));
  }
}
let fails = 0, done = 0;
async function run(c) {
  let ctx; try { ctx = await browser.newContext({ viewport: { width: c.w, height: 900 }, deviceScaleFactor: c.dpr }); } catch (e) { console.log('FAIL ' + c.name + ' browser gone: ' + e.message.slice(0, 60)); fails++; return; }
  await ctx.addInitScript(([theme, store]) => { try { localStorage.setItem("finlit-theme", theme); localStorage.setItem("finlit-plan", "gold"); for (const [k, v] of Object.entries(store)) localStorage.setItem(k, v); } catch {} }, [c.theme, c.store]);
  if (MODE === "api") await mockApi(ctx);
  const p = await ctx.newPage(), errs = [];
  p.on("pageerror", (e) => errs.push("PAGE ERROR " + String(e.message || e).slice(0, 160)));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|404|403|405|401|net::ERR|favicon/i.test(m.text())) errs.push("CONSOLE " + m.text().slice(0, 160)); });
  let problems = [];
  try {
    await p.goto(base + c.path, { waitUntil: "networkidle", timeout: 30000 });
    // lazy pages: wait until the main area has content (and a table where one is expected) before measuring
    await p.waitForFunction((t) => { const m = document.querySelector("main"); return m && (m.innerText || "").trim().length > 40 && (!t || m.querySelector("table")); }, !!c.opt.table, { timeout: 9000 }).catch(() => {});
    await p.waitForTimeout(500);
    problems = await p.evaluate(measure, { minMain: MIN_MAIN, vw: c.w, sel: c.opt.sel, wantTable: !!c.opt.table });
  } catch (e) { problems = ["LOAD FAILED " + String(e.message).slice(0, 120)]; }
  problems.push(...errs.slice(0, 3));
  const tag = `${c.name}-${c.state}-${c.w}${c.dpr !== 1 ? "@" + c.dpr : ""}-${c.theme}`;
  if (problems.length || process.env.GUARD_SHOTS) await p.screenshot({ path: `${out}/${problems.length ? "FAIL-" : ""}${tag}.png` }).catch(() => {});
  await ctx.close();
  done++;
  if (problems.length) { fails++; console.log(`FAIL ${tag}`); for (const x of problems) console.log("     - " + x); }
}
const tagOf = (c) => `${c.name}-${c.state}-${c.w}${c.dpr !== 1 ? "@" + c.dpr : ""}-${c.theme}`;
const queue = cases.filter((c) => !process.env.GUARD_TAG || new RegExp(process.env.GUARD_TAG).test(tagOf(c)));
await Promise.all(Array.from({ length: Number(process.env.GUARD_JOBS) || 4 }, async () => { while (queue.length) await run(queue.shift()); }));
await browser.close();
console.log(`\nlayout guard (${MODE} mode): ${done} cases, ${fails} failed${fails ? "  (screenshots of failures in " + out + ")" : ""}`);
server?.kill();
process.exit(fails ? 1 : 0);
