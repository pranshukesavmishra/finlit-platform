// PAGE HEADERS: every feature page that uses the shared header (components/PageHeader.tsx) is opened at 1440, 1055 and 390 px, in light and dark, with /api/** mocked, and must show
//   exactly one h1, the header card, the right plan badge, no sideways scroll, no overlapping text, readable contrast (4.5:1), no placeholder numbers in the stat tiles,
//   an illustration above 760 px and none below, and quick links that open a real page (one h1, no error card).
//   node e2e/page_headers.mjs                       builds the demo site and the normal site, serves both, runs every case (exit 1 on any failure)
//   node e2e/page_headers.mjs http://127.0.0.1:5471 http://127.0.0.1:5472 [outDir]     against servers you already run (demo build, normal build)
// Env: CHROME=/path/to/chrome, PH_ONLY=substring of a page path, PH_SHOTS=1 (screenshot every case), PH_JOBS=4
import { chromium } from "playwright";
import fs from "node:fs";
import { execSync, spawn } from "node:child_process";

const out = process.argv[4] || ".page-headers";
fs.mkdirSync(out, { recursive: true });
const servers = [];
let demo = (process.argv[2] || "").replace(/\/$/, ""), api = (process.argv[3] || "").replace(/\/$/, "");
async function serve(dir, port, env) {
  execSync(`npx vite build --outDir ${dir}`, { stdio: "ignore", env: { ...process.env, ...env } });
  servers.push(spawn("npx", ["vite", "preview", "--outDir", dir, "--port", String(port), "--host", "127.0.0.1", "--strictPort"], { stdio: "ignore" }));
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 40; i++) { try { await fetch(base + "/"); break; } catch { await new Promise((r) => setTimeout(r, 250)); } }
  return base;
}
if (!demo) demo = await serve("dist-ph-demo", Number(process.env.PH_PORT || 5471), { VITE_DEMO: "1" });
if (!api) api = await serve("dist-ph-api", Number(process.env.PH_PORT || 5471) + 1, {});

const WIDTHS = [1440, 1055, 390], THEMES = ["dark", "light"];
// [path, badge text or null, build]   build "api" = the normal build with the screener endpoints mocked, "demo" = the offline demo build
const PAGES = [
  ["/screener", "Free", "api"], ["/screener", "Free", "demo"], ["/score-screener", "Silver", "api"], ["/advanced-score-screener", "Gold", "api"], ["/fund-score-screener", "Gold", "demo"],
  ["/query-builder", "Free", "demo"], ["/research", "Free", "demo"], ["/compare", "Free", "demo"], ["/prism", "Gold", "demo"], ["/outlook", "Gold", "demo"],
  ["/premium", "Gold", "demo"], ["/premium/report", "Gold", "demo"], ["/premium/fundamentals", "Gold", "demo"], ["/premium/markets", "Gold", "demo"], ["/premium/options", "Gold", "demo"],
  ["/eps-calculator", "Free", "demo"], ["/dcf", "Gold", "demo"], ["/sip-calculator", "Free", "demo"], ["/graphs", "Free", "demo"], ["/graphs/advanced/valuation", "Free", "demo"],
  ["/fii-dii", "Free", "demo"], ["/macro", "Free", "demo"], ["/commodities", "Free", "demo"], ["/results", "Free", "demo"], ["/results/quarter", "Free", "demo"], ["/ipo", "Free", "demo"], ["/news", "Free", "demo"],
  ["/funds", "Free", "demo"], ["/funds/compare", "Free", "demo"], ["/funds/insights", "Free", "demo"], ["/etfs", "Free", "demo"], ["/etfs/compare", "Free", "demo"], ["/etfs/compare-index-funds", "Free", "demo"],
  ["/watchlist", "Silver", "demo"], ["/holdings", "Silver", "demo"], ["/mf-portfolio", "Silver", "demo"], ["/alerts", "Free", "demo"], ["/baskets", "Free", "demo"],
  ["/documents", "Free", "demo"], ["/glossary", null, "demo"], ["/methodology/mf-score", null, "demo"],
];

// ---- API mock (same shapes as e2e/layout_guard.mjs api mode) ----
const SECT = ["Capital Goods", "Services", "Banks", "IT", "Auto", "Pharma", "Metals", "Energy", "FMCG", "Realty"];
const metric = (key, label, unit = "x") => ({ key, label, unit, better: "higher", tier: "basic", say: label + " in plain words.", digits: 1, locked: false, stats: { min: 0, p10: 5, p50: 15, p90: 40, max: 80, n: 3000, hist: [3, 5, 9, 12, 8, 4, 2] } });
const GROUPS = ["valuation", "profit", "growth", "health", "own", "q", "flags", "trend", "div", "eff", "size", "model"];
const catalog = { plan: "gold", total: 5816, withReport: 1200, updatedAt: "2026-10-30", sectors: SECT.map((n, i) => ({ name: n, n: 400 - i * 20 })), industries: [], indices: [{ code: "N50", label: "Nifty 50", n: 50 }], caps: [{ name: "Large", n: 100 }, { name: "Mid", n: 150 }], bands: [{ key: "strong", label: "Strong", locked: false }, { key: "watch", label: "Watch", locked: false }],
  limits: { rows: null, export: true }, defaultColumns: ["valuation_pe", "valuation_roe"],
  groups: GROUPS.map((id) => ({ id, label: id[0].toUpperCase() + id.slice(1), tier: "basic", metrics: [metric(id + "_pe", "P/E"), metric(id + "_pb", "P/B"), metric(id + "_roe", "ROE", "%")] })) };
const result = { total: 5816, offset: 0, limit: 50, capped: false, took: 12, columns: ["valuation_pe", "valuation_roe"], rows: Array.from({ length: 50 }, (_, i) => ({ symbol: "SYM" + i, name: "Company " + i + " Limited", sector: SECT[i % 10], cap: "Large", band: "strong", v: { valuation_pe: 20, valuation_roe: 14 } })) };
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

// ---- checks, run inside the page ----
function check({ vw, badge }) {
  const bad = [];
  const vis = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  const h1s = [...document.querySelectorAll("h1")].filter(vis);
  if (h1s.length !== 1) bad.push(`H1 count is ${h1s.length} (${h1s.map((h) => '"' + h.textContent.trim().slice(0, 30) + '"').join(", ")})`);
  const ph = document.querySelector(".ph");
  if (!ph) return [...bad, "NO HEADER (.ph) on the page"];
  if (!ph.querySelector("h1.ph-title") || h1s[0] !== ph.querySelector("h1.ph-title")) bad.push("the page's h1 is not the header's title");
  if (!ph.getAttribute("aria-labelledby") || !document.getElementById(ph.getAttribute("aria-labelledby"))) bad.push("header region has no label");
  if (/Something went wrong on this page|A new version of FinLit is ready/.test(document.body.innerText)) bad.push("ERROR CARD is showing");
  const pl = ph.querySelector(".ph-plan");
  const got = pl ? pl.textContent.trim() : null;
  if ((badge ?? null) !== got) bad.push(`plan badge is ${JSON.stringify(got)}, expected ${JSON.stringify(badge)}`);
  const over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  if (over > 1) bad.push(`HORIZONTAL PAGE SCROLL ${over}px`);
  if (ph.scrollWidth > ph.clientWidth + 1) bad.push(`header content wider than its card (${ph.scrollWidth} vs ${ph.clientWidth})`);
  const pr = ph.getBoundingClientRect();
  if (pr.right > vw + 1 || pr.left < -1) bad.push(`header card sticks out of the screen (${Math.round(pr.left)}..${Math.round(pr.right)})`);
  // overlapping text: leaf boxes inside the header must not overlap one another
  const leaves = [...ph.querySelectorAll("h1, .ph-plan, .ph-eyebrow, .ph-desc, .ph-meta, .ph-lk, .ph-learn, .ph-stat, .ph-back, .ph-art-box, .ph-sub > *")].filter(vis);
  for (let i = 0; i < leaves.length; i++) for (let k = i + 1; k < leaves.length; k++) {
    const a = leaves[i], b = leaves[k]; if (a.contains(b) || b.contains(a)) continue;
    const x = a.getBoundingClientRect(), y = b.getBoundingClientRect();
    const w = Math.min(x.right, y.right) - Math.max(x.left, y.left), h = Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top);
    if (w > 2 && h > 2) bad.push(`OVERLAP ${a.className || a.tagName} with ${b.className || b.tagName} (${Math.round(w)}x${Math.round(h)}px)`);
  }
  // stat tiles: real values only
  for (const s of ph.querySelectorAll(".ph-stat")) { const v = s.querySelector("b")?.textContent.trim() ?? ""; if (!v || /^(nan|null|undefined|n\/a|[-–—?…]+)$/i.test(v)) bad.push(`placeholder stat value "${v}"`); }
  if (vw >= 761 && ph.querySelector(".ph-art-box") && !vis(ph.querySelector(".ph-art-box"))) bad.push("illustration hidden on a wide screen");
  if (vw <= 760 && [...ph.querySelectorAll(".ph-art-box")].some(vis)) bad.push("illustration shown on a narrow screen");
  if (vw <= 760) { const st = ph.querySelector(".ph-stats"); if (st) { const cols = getComputedStyle(st).gridTemplateColumns.split(" ").length; if (cols > 2) bad.push(`stat tiles in ${cols} columns on a phone`); } }
  if (!ph.querySelector("a[href], button")?.matches(":not([disabled])") && ph.querySelector(".ph-lk")) bad.push("quick links not focusable");
  // contrast >= 4.5 for text on its real background
  const cv = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  const px = (c) => { cv.clearRect(0, 0, 1, 1); cv.fillStyle = "#000"; cv.fillStyle = c; cv.fillRect(0, 0, 1, 1); const d = cv.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const over2 = (f, b) => [0, 1, 2].map((i) => f[i] * f[3] + b[i] * (1 - f[3]));
  const bg = (el) => { let col = [255, 255, 255]; const chain = []; for (let e = el; e; e = e.parentElement) chain.push(e); for (const e of chain.reverse()) { const c = px(getComputedStyle(e).backgroundColor); if (c[3] > 0) col = over2(c, col); } return col; };
  const lum = (c) => { const f = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]; };
  for (const el of ph.querySelectorAll("h1, .ph-plan, .ph-eyebrow, .ph-desc, .ph-meta, .ph-lk, .ph-learn, .ph-stat b, .ph-stat small, .ph-back")) {
    if (!vis(el)) continue;
    const f = px(getComputedStyle(el).color), b = bg(el), fg = over2(f, b), L1 = lum(fg), L2 = lum(b), r = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    if (r < 4.5) bad.push(`LOW CONTRAST ${r.toFixed(2)}:1 on ${el.className || el.tagName} "${el.textContent.trim().slice(0, 24)}"`);
  }
  return bad.slice(0, 10);
}

const browser = await chromium.launch({ executablePath: process.env.CHROME || process.env.CHROMIUM_PATH || undefined });
const linkCache = new Map();   // "build|href" -> problem text or ""
async function checkLink(ctx, base, href) {
  const key = base + href;
  if (linkCache.has(key)) return linkCache.get(key);
  const p = await ctx.newPage(); let res = "";
  try {
    const r = await p.goto(base + href, { waitUntil: "networkidle", timeout: 30000 });
    await p.waitForFunction(() => { const m = document.querySelector("main"); return m && (m.innerText || "").trim().length > 30; }, null, { timeout: 8000 }).catch(() => {});
    const info = await p.evaluate(() => ({ h1: [...document.querySelectorAll("h1")].filter((h) => h.getBoundingClientRect().height > 0).length, err: /Something went wrong|Page not found|not found/i.test(document.querySelector("main")?.innerText.slice(0, 400) || "") }));
    if (!r || r.status() !== 200) res = `status ${r?.status()}`; else if (info.h1 !== 1) res = `${info.h1} h1`; else if (info.err) res = "shows an error / not-found page";
  } catch (e) { res = "load failed " + String(e.message).slice(0, 60); }
  await p.close(); linkCache.set(key, res); return res;
}

const cases = [];
for (const [path, badge, build] of PAGES) for (const w of WIDTHS) for (const theme of THEMES) cases.push({ path, badge, build, w, theme });
const tagOf = (c) => `${c.build}${c.path.replace(/\//g, "_")}-${c.w}-${c.theme}`;
let fails = 0, done = 0;
async function run(c) {
  const base = c.build === "api" ? api : demo;
  const ctx = await browser.newContext({ viewport: { width: c.w, height: 900 } });
  await ctx.addInitScript(([theme]) => { try { localStorage.setItem("finlit-theme", theme); localStorage.setItem("finlit-plan", "gold"); } catch {} }, [c.theme]);
  await mockApi(ctx);
  const p = await ctx.newPage(), errs = [];
  p.on("pageerror", (e) => errs.push("PAGE ERROR " + String(e.message || e).slice(0, 160)));
  let problems = [];
  try {
    await p.goto(base + c.path, { waitUntil: "networkidle", timeout: 30000 });
    await p.waitForSelector(".ph", { timeout: 9000 }).catch(() => {});
    await p.waitForTimeout(700);
    problems = await p.evaluate(check, { vw: c.w, badge: c.badge });
    if (c.w === 1440 && c.theme === "dark") {   // the quick links open real pages (checked once per page, in one width / theme)
      const hrefs = await p.evaluate(() => [...document.querySelectorAll(".ph .ph-lk")].map((a) => a.getAttribute("href")));
      for (const h of hrefs) { const bad = await checkLink(ctx, demo, h); if (bad) problems.push(`LINK ${h}: ${bad}`); }
      const learn = await p.evaluate(() => { const a = document.querySelector(".ph .ph-learn"); return a ? (a.getAttribute("href") ?? "button") : null; });
      if (learn && learn.startsWith("#") && !(await p.evaluate(() => !!document.getElementById("faq")))) problems.push("Learn more points to #faq but the page has no #faq section");
    }
  } catch (e) { problems = ["LOAD FAILED " + String(e.message).slice(0, 120)]; }
  problems.push(...errs.slice(0, 2));
  if (problems.length || process.env.PH_SHOTS) await p.screenshot({ path: `${out}/${problems.length ? "FAIL-" : ""}${tagOf(c)}.png` }).catch(() => {});
  await ctx.close(); done++;
  if (problems.length) { fails++; console.log(`FAIL ${tagOf(c)}`); for (const x of problems) console.log("     - " + x); }
}
const queue = cases.filter((c) => !process.env.PH_ONLY || c.path.includes(process.env.PH_ONLY));
await Promise.all(Array.from({ length: Number(process.env.PH_JOBS) || 4 }, async () => { while (queue.length) await run(queue.shift()); }));
await browser.close();
console.log(`\npage headers: ${done} cases, ${fails} failed${fails ? "  (screenshots of failures in " + out + ")" : ""}`);
servers.forEach((s) => s.kill());
process.exit(fails ? 1 : 0);
