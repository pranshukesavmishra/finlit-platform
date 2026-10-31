// Fund score screener, every /api/** call mocked. Screenshots at 1280 and 390, light and dark, with and without filters.
//   node e2e/fund_screener.mjs http://127.0.0.1:5199 /path/to/out
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), out = process.argv[3] || ".";
const CATS = [["large-cap", "Large Cap"], ["mid-cap", "Mid Cap"], ["small-cap", "Small Cap"], ["flexi-cap", "Flexi Cap"], ["elss", "ELSS"], ["liquid", "Liquid"]];
const LAB = ["Strong", "Healthy", "Average", "Weak", "Poor"];
const pill = (i, k) => 20 + ((i * k) % 78);
const items = Array.from({ length: 50 }, (_, i) => ({ key: "mf:" + (100 + i), kind: "mf", code: 100 + i, symbol: null, name: `Example Fund ${i + 1} Growth Direct Plan`, amc: "Sample Asset Management Mutual Fund", plan: "Direct", group: "EQ", sub: CATS[i % 6][0], categoryLabel: CATS[i % 6][1],
  final: 90 - i, label: LAB[Math.min(4, Math.floor(i / 10))], status: i % 9 === 0 ? "PROVISIONAL" : "RATED", reason: null, pillars: { performance: pill(i, 7), risk: pill(i, 3), cost: pill(i, 11), quality: pill(i, 5) }, rank: i + 1, rankOf: 400,
  aumCr: 12000 - i * 150, ageYears: 3 + (i % 15) * 0.7, ter: i % 7 === 3 ? null : 0.2 + (i % 10) / 10, r1y: 12 + (i % 5), r3y: i % 6 === 0 ? null : 15, r5y: 14, fullData: true, flags: [] }));
async function mock(ctx) {
  await ctx.route("**/api/**", (route) => {
    const u = new URL(route.request().url()).pathname;
    const j = (b) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (u.endsWith("/auth/me")) return j({ user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, compare: 4, holdings: 500 }, csrf: "t", showcase: [] });
    if (u.endsWith("/mf/score-screener/facets")) return j({ locked: false, runDate: "2026-10-30", categories: CATS.map(([sub, label], i) => ({ sub, label, group: "EQ", n: { Direct: 40 - i * 3, Regular: 30, ETF: 4 } })) });
    if (u.endsWith("/mf/score-screener")) return j({ locked: false, total: 412, runDate: "2026-10-30", items });
    if (u.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    if (u.endsWith("/stocks/search-index")) return j({ rows: [], sectors: [], mc: [] });
    if (/notifications|alerts|indices|companies/.test(u)) return j([]);
    if (process.env.DBG) console.log("UNMOCKED", u);
    return j({});
  });
}
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0;
const pages = [["plain", ""], ["active", "?labels=Strong,Healthy&cost_min=70&plan=Regular&sub=large-cap&full=1&view=lowcost&min=65"]];
for (const [w, h, n] of [[1280, 1000, "d"], [390, 900, "m"]]) for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  await mock(ctx);
  for (const [name, qs] of pages) {
    const p = await ctx.newPage();
    p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", name, (e.stack || String(e)).slice(0, 700)); });
    await p.goto(base + "/fund-score-screener" + qs, { waitUntil: "networkidle" }); await p.waitForTimeout(800);
    const tag = `fund-${name}-${n}-${theme}`;
    const overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 1) { bad++; console.log("OVERFLOW", tag, overflow, await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 2).slice(0, 5).map((e) => e.tagName + "." + e.className.toString().slice(0, 40)).join(" | "))); }
    await p.screenshot({ path: `${out}/${tag}.png` });
    if (n === "m") { await p.locator(".fgx-kpi").last().click().catch(() => {}); await p.waitForTimeout(500); await p.screenshot({ path: `${out}/${tag}-drawer.png` }); }
    else await p.screenshot({ path: `${out}/${tag}-full.png`, fullPage: true });
    await p.close();
  }
  await ctx.close();
}
await browser.close();
console.log(bad ? "PROBLEMS " + bad : "OK");
process.exit(bad ? 1 : 0);
