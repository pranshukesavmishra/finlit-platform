// Stock screener columns: fresh visit (groups closed, P/E + 3Y P/E shown), chip select, period tab, range. /api/** mocked.
//   node e2e/screener_columns.mjs http://127.0.0.1:5199 /path/to/out
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), out = process.argv[3] || ".";
const stats = { min: 0, p10: 5, p50: 18, p90: 55, max: 120, n: 4100, lo: 0, hi: 100, hist: [4, 9, 18, 30, 24, 16, 11, 8, 6, 4, 3, 2, 2, 1, 1] };
const M = (key, label, o = {}) => ({ key, label, unit: "x", better: "lower", tier: "basic", say: label + " in plain words.", digits: 1, locked: false, hidden: false, variants: null, stats, ...o });
const V = (b) => ({ now: b, "3y": b + "_avg_3y", "5y": b + "_avg_5y", "7y": b + "_avg_7y" });
const avg = (b, l) => ["3y", "5y", "7y"].map((p) => M(`${b}_avg_${p}`, `${l}, ${p.toUpperCase()} average`, { hidden: true }));
const groups = [
  { id: "valuation", label: "Valuation", tier: "basic", metrics: [M("pe", "P/E Ratio", { variants: V("pe") }), M("pb", "P/B Ratio", { variants: V("pb") }), M("ev_ebitda", "EV/EBITDA"), M("dividend_yield", "Dividend Yield", { unit: "%", better: "higher" }), M("peg", "PEG Ratio"), M("earnings_yield", "Earnings Yield", { unit: "%" }), M("graham_value", "Graham Fair Value", { unit: "Rs" }), M("graham_upside", "Upside to Graham Value", { unit: "%" }), M("ev_cfo", "EV / CFO"), ...avg("pe", "P/E Ratio"), ...avg("pb", "P/B Ratio")] },
  { id: "profitability", label: "Profitability", tier: "basic", metrics: [M("roe", "Return on equity", { unit: "%" }), M("roce", "Return on capital employed", { unit: "%" })] },
  { id: "growth", label: "Growth", tier: "basic", metrics: [M("sales_cagr_5y", "Sales growth, 5 years a year", { unit: "%" })] },
  { id: "size", label: "Size", tier: "basic", metrics: [M("market_cap", "Market cap", { unit: "Cr" }), M("price", "Share price", { unit: "Rs" })] },
];
const catalog = { plan: "gold", total: 5813, withReport: 5000, updatedAt: "2026-10-30", sectors: [{ name: "IT", n: 300 }, { name: "Banks", n: 200 }], industries: [], indices: [], caps: [{ name: "Large", n: 100 }], bands: [], limits: { rows: null, export: true }, defaultColumns: ["market_cap", "price"], groups };
const val = (k, i) => ({ market_cap: 500000 - i * 4000, price: 120 + i * 13, pe: i % 7 === 3 ? null : 12 + (i * 3) % 40, pe_avg_3y: i % 5 === 2 ? null : 15 + (i * 2) % 30, pb: 1.2 + (i % 9) * 0.7, pb_avg_3y: 1.5 + (i % 6) * 0.6, pb_avg_5y: 1.4 + (i % 5) * 0.5 }[k] ?? 5 + ((i * 7) % 30));
async function mock(ctx) {
  await ctx.route("**/api/**", (route) => {
    const req = route.request(), u = new URL(req.url()).pathname, j = (b) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (u.endsWith("/auth/me")) return j({ user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, compare: 4, holdings: 500 }, csrf: "t", showcase: [] });
    if (u.endsWith("/screener/catalog")) return j(catalog);
    if (u.endsWith("/screener/query")) { const b = JSON.parse(req.postData() || "{}"); return j({ total: 5813, offset: 0, limit: 50, capped: false, took: 9, columns: b.columns, rows: Array.from({ length: 12 }, (_, i) => ({ symbol: "SYM" + i, name: "Company " + i + " Limited", sector: "IT", cap: "Large", band: null, full: true, v: Object.fromEntries(b.columns.map((c) => [c, val(c, i)])) })) }); }
    if (u.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    if (u.endsWith("/stocks/search-index")) return j({ rows: [], sectors: [], mc: [] });
    if (/notifications|alerts|indices|companies/.test(u)) return j([]);
    return j({});
  });
}
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0;
const heads = (p) => p.evaluate(() => [...document.querySelectorAll(".scr-t thead th")].map((t) => t.innerText.replace(/\s*[▲▼▾]$/, "").trim()));
const check = (n, ok, x = "") => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " " + x : "")); };
for (const [w, h, n] of [[1280, 900, "d"], [390, 844, "m"]]) for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  await mock(ctx);
  const p = await ctx.newPage(); p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", String(e).slice(0, 300)); });
  const tag = `${n}-${theme}`, shot = (s, full = false) => p.screenshot({ path: `${out}/${tag}-${s}.png`, fullPage: full });
  await p.goto(base + "/screener", { waitUntil: "networkidle" }); await p.waitForSelector(".scr-t tbody tr");
  console.log(tag, "fresh:", (await heads(p)).join(" | "), "|", await p.getByRole("button", { name: /^Columns/ }).innerText());
  if (n === "m") { await p.locator(".scr-main").scrollIntoViewIfNeeded(); }
  await shot("1-fresh-table", n === "m");
  if (n === "m") await p.locator(".fgx-kpi").last().click();   // open the filter panel on a phone
  await p.waitForTimeout(300);
  check(tag + " all groups closed", (await p.locator("button.fgx-hb[aria-expanded=true]").count()) === 0);
  await shot("1-fresh-panel", n === "m");
  await p.getByRole("button", { name: /^Valuation/ }).click();
  await p.getByRole("button", { name: "Dividend Yield", exact: true }).click(); await p.waitForTimeout(500);
  check(tag + " chip adds column", (await heads(p)).includes("Dividend Yield"));
  await p.getByRole("button", { name: "P/B Ratio", exact: true }).click(); await p.getByRole("tab", { name: /3Y avg/ }).click(); await p.waitForTimeout(500);
  console.log(tag, "3Y:", (await heads(p)).join(" | ")); check(tag + " period switches column", (await heads(p)).includes("P/B Ratio, 3Y average"));
  await shot("2-after-3y", n === "m");
  await p.getByLabel("P/B Ratio, 3Y average maximum", { exact: true }).fill("3").catch(() => p.locator(".pl-mm input").last().fill("3")); await p.waitForTimeout(800);
  await shot("3-range", n === "m");
  await ctx.close();
}
await browser.close(); process.exit(bad ? 1 : 0);
