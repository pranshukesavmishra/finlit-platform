// Prebuilt screens on the Advanced score screener with every /api/** call mocked (the contract of /api/screener/presets).
//   node e2e/presets.mjs http://127.0.0.1:5199 /path/to/out
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), out = process.argv[3] || ".";
const chip = (id, label, d = false) => ({ id, label, default: d, description: label + ": narrows the list in plain words." });
const P = (id, name, group, o = {}) => ({ id, name, group, cardText: "One line on what " + name.toLowerCase() + " finds.", count: 37, asOf: "2026-10-31", status: "live", blockedReason: null, chips: [], howItWorks: ["Prism score 50 or more", "Price above its 50-day and 200-day average", "Within 15% of the 52-week high"], locked: false, ...o });
const G = (id, name, presets) => ({ id, name, presets });
const LIST = { asOf: "2026-10-31", groups: [
  G("top", "Top rated", [P("large", "Highest-rated large caps", "Top rated", { chips: [chip("trend", "Trend check")], count: 10 }), P("mid", "Highest-rated mid caps", "Top rated", { count: 10 }), P("small", "Highest-rated small caps", "Top rated", { count: 10 })]),
  G("trend", "Trend", [P("momentum", "Momentum leaders", "Trend", { chips: [chip("beyond", "Beyond rated stocks")] }), P("nearhigh", "Near 52-week high on volume", "Trend", { count: 10 }), P("fno", "F&O stocks, both views positive", "Trend", { count: 20 })]),
  G("growth", "Growth", [P("growers", "Consistent growers", "Growth", { chips: [chip("rated", "Rated only", true), chip("fast", "Fast growers")], count: 66 }), P("results", "Results-season standouts", "Growth", { count: 120 })]),
  G("themes", "Themes", [P("emerging", "Emerging tech", "Themes", { count: 55, chips: [chip("sub-ems", "EMS and electronics"), chip("sub-semi", "Semiconductors")] }), P("sectors", "Sector themes in play", "Themes", { count: 1 })]),
  G("value", "Value and income", [P("qarp", "Quality at a fair price", "Value and income", { count: 41 }), P("off", "Quality off its highs", "Value and income", { count: 29 }), P("cheap", "Cheaper than its own history", "Value and income", { count: 35 }), P("div", "Steady dividend payers", "Value and income", { count: 49 })]),
  G("safety", "Safety", [P("debt", "Debt-free compounders", "Safety", { count: 0 }), P("lowvol", "Low-volatility names", "Safety", { count: 38 }), P("risk", "Higher-risk list", "Safety", { count: 53 }), P("psu", "PSU stocks", "Safety", { status: "blocked", count: null, blockedReason: "Coming soon: needs a PSU flag from the shareholding pattern" })]),
  G("own", "Ownership", [P("inst", "Institutions buying", "Ownership", { count: 22 })]),
] };
const col = (key, label, format, align = "right") => ({ key, label, format, align });
const names = ["SANSERA", "SYRMA", "SONACOMS", "DIVISLAB", "ACUTAAS", "COFORGE", "UTSSAV", "SPECTRUM", "SBC", "KAYNES"];
const rows = names.map((s, i) => ({ symbol: s, name: s[0] + s.slice(1).toLowerCase() + " Limited", prism: 80 - i * 2, mom: 96 - i * 3, r3: 14 - i, r6: 20 - i, r1y: i === 4 ? null : 40 - i * 2, below: 2 + i, st: 30 - i, lt: 22 - i, sector: ["Auto parts", "Electronics", "Auto parts", "Pharma", "Defence"][i % 5], badges: i % 3 === 0 ? ["Prism-confirmed"] : i % 3 === 1 ? ["Provisional"] : [] }));
const DETAIL = { id: "momentum", name: "Momentum leaders", asOf: "2026-10-31", count: 37, shown: 10, cardText: "Rated stocks in an uptrend near their 52-week high, ranked by 3-, 6- and 12-month returns against the market.", disclaimer: "A screen narrows a list. It is not a recommendation.", howItWorks: LIST.groups[1].presets[0].howItWorks,
  columns: [col("mom", "Momentum score", "score"), col("r3", "3M return", "pct"), col("r6", "6M return", "pct"), col("r1y", "1Y return", "pct"), col("below", "Below 52-week high", "pct"), col("st", "Short-term view", "score"), col("lt", "Long-term view", "score"), col("prism", "Prism score", "score"), col("sector", "Sector", "text", "left")], rows };
const THEMES = { ...DETAIL, id: "sectors", name: "Sector themes in play", count: 5, shown: 5, columns: DETAIL.columns.slice(7), rows: rows.slice(0, 5).map((r, i) => ({ ...r, badges: [] })),
  themes: [{ industry: "Pharmaceuticals", state: "in_play", b50: 43, rs3: 7.5, members: 81, leaders: names.slice(0, 3) }, { industry: "Telecom equipment", state: "emerging", b50: 50, rs3: 41.9, members: 6, leaders: [names[3]] }, { industry: "Consumer durables", state: "closest", b50: 44, rs3: 14.1, members: 32, leaders: [] }] };
const EMPTY = { ...DETAIL, id: "debt", name: "Debt-free compounders", count: 0, shown: 0, rows: [], closestMisses: ["BLS", "IEX", "KALYANKJIL", "EICHERMOT", "TIPSMUSIC"].map((s, i) => ({ symbol: s, name: s + " Limited", failed: i % 2 ? ["ROCE below 20%", "Sales growth (3 years) below 12%"] : ["Debt to equity above 0.1"] })) };
const GROWERS = { ...DETAIL, id: "growers", name: "Consistent growers", count: 66, shown: 10 };
const GOLD = { user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, compare: 4, holdings: 500 }, csrf: "t", showcase: [] };
const universe = { rows: Array.from({ length: 40 }, (_, i) => ({ symbol: "SYM" + i, name: "Company " + i, sector: "IT", overall: 50, band: null, price: 100, market_cap: 5000 + i, scored: true, prism_final: 60, prism_label: "strong" })), sample: false, as_of: "2026-10-30", prism: { total: 40, rated: 30, provisional: 2, as_of: "2026-10-30", per_night: 100 } };
async function mock(ctx, locked) {
  await ctx.route("**/api/**", (route) => {
    const u = new URL(route.request().url()), p = u.pathname;
    const j = (b, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(b) });
    if (p.endsWith("/auth/me")) return j(locked ? { ...GOLD, plan: "silver", user: { ...GOLD.user, plan: "silver" } } : GOLD);
    if (p.endsWith("/screener/presets")) return j(locked ? { ...LIST, groups: LIST.groups.map((g) => ({ ...g, presets: g.presets.map((x) => ({ ...x, count: null, locked: true })) })) } : LIST);
    const m = /\/screener\/presets\/([^/]+)$/.exec(p);
    if (m) return j({ momentum: DETAIL, sectors: THEMES, debt: EMPTY, growers: GROWERS }[m[1]] ?? { ...DETAIL, id: m[1] });
    if (p.endsWith("/screener/universe")) return j(universe);
    if (p.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    if (p.endsWith("/stocks/search-index")) return j({ rows: [], sectors: [], mc: [] });
    return j(/notifications|alerts|indices|companies/.test(p) ? [] : {});
  });
}
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0;
const shots = [["momentum", "/advanced-score-screener?preset=momentum"], ["themes", "/advanced-score-screener?preset=sectors"], ["empty", "/advanced-score-screener?preset=debt"], ["panel", "/advanced-score-screener"], ["growers-chips", "/advanced-score-screener?preset=growers&chip=rated&chip=fast"], ["invalid", "/advanced-score-screener?preset=nope"]];
for (const [w, h, n] of [[1280, 1000, "1280"], [950, 1000, "950"], [390, 900, "390"]]) for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  await mock(ctx, false);
  for (const [name, path] of shots) {
    const p = await ctx.newPage();
    p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", name, String(e).slice(0, 300)); });
    await p.goto(base + path, { waitUntil: "networkidle" }); await p.waitForTimeout(500);
    const ov = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (ov > 1) { bad++; console.log("OVERFLOW", name, n, theme, ov); }
    await p.screenshot({ path: `${out}/${name}-${n}-${theme}.png`, fullPage: true });
    await p.close();
  }
  await ctx.close();
}
{ const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } }); await mock(ctx, true); const p = await ctx.newPage(); await p.goto(base + "/advanced-score-screener", { waitUntil: "networkidle" }); await p.waitForTimeout(500); await p.screenshot({ path: `${out}/locked-1280-light.png`, fullPage: true }); await ctx.close(); }
await browser.close();
console.log(bad ? "PROBLEMS " + bad : "ok");
