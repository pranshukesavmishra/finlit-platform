// My portfolio page in a real browser with the API answered from the pack samples (src/portfolio/__fixtures__).
//   npx vite --port 5199 &   node e2e/my_portfolio_page.mjs sample_12 gold 1440 light   (sample_12|sample_40, silver|gold, width, light|dark)
// Real-browser check of the My portfolio page with the API answered from the pack's stored samples.
// usage: node shoot.mjs <sample_12|sample_40> <silver|gold> <w> <light|dark> <outname> [action]
import { chromium } from "playwright";
import fs from "node:fs";
const [name, plan, W, theme] = [process.argv[2], process.argv[3], process.argv[4], process.argv[5]]; const out = "chk", action = "";
const D = JSON.parse(fs.readFileSync(new URL(`../src/portfolio/__fixtures__/${name}.json`, import.meta.url), "utf8"));
const meta = D.inputs.meta, symbols = Object.keys(meta);
const px = { HDFCBANK: [774.85, 1.95], ICICIBANK: [1527.25, 1.86], SBIN: [1001.6, -0.48], BAJFINANCE: [1055.2, -1.38], INFY: [1167.8, 0.03], TCS: [2506.8, 0.44], TECHM: [1826.7, 0.22], RELIANCE: [1309.9, -0.27], SUNPHARMA: [1851.7, 1.24], SKYGOLD: [965, 1.68], KINGFA: [5995.5, -11.69], TIPSMUSIC: [764.45, 0.12] };
const ready = (s) => { const m = meta[s], p = m.prism || {}, [price, ch] = px[s] || [100 + (s.length * 37) % 900, ((s.charCodeAt(0) % 7) - 3) / 2];
  const fig = (v) => ({ value: v });
  const st = { available: true, period: "FY26", periodEnd: "2026-03-31", revenue: fig(12345), other_income: fig(210), operating_profit: fig(2100), finance_costs: fig(300), net_profit: fig(1500), eps: fig(12.5), tax_ratio: fig(24.1) };
  const base = { symbol: s, status: "ready", name: m.name, sector: m.sector, industry: m.sector, isBank: false, basis: "consolidated", reportAt: "2026-10-30", price, changePct: ch, priceAsOf: "2026-11-06", marketCapCr: m.mcap_cr,
    ratios: { pe: fig(22.1), pb: fig(3.1), roe: fig(14.2), dividend_yield: fig(1.2), debt_to_equity: { value: null, why: "Not shown for banks and lenders." } }, financials: { year: st, quarter: { ...st, period: "Q2 FY27", periodEnd: "2026-09-30" } } };
  if (plan === "gold") base.prism = { state: "rated", final: p.final, label: "Strong", status: "RATED", parts: { fundamental: p.growth_profitability, valuation: p.valuation, quality: p.quality, risk: p.risk }, shortTerm: { score: 40, word: "Uptrend" }, longTerm: { score: 22, word: "Uptrend" }, at: null, reason: null };
  else base.finlit = { overall: p.final, band: "healthy", word: "Healthy", pillars: { quality: p.quality, growth: p.growth_profitability, profitability: p.risk, balance: p.valuation, technical: p.final } };
  return base; };
const tilt = plan === "gold" ? { universe: 650, notRated: [], sentence: "This list leans towards faster-growing and lower-risk companies, and stocks in short-term uptrends. Valuation, quality and the long-term trend are close to typical.",
  parts: [["Growth & Profitability", 75, "high", "faster-growing, more profitable companies"], ["Valuation", 62, "typical"], ["Quality", 65, "typical"], ["Risk", 86, "high", "lower-risk companies"], ["Short-term technical view", 85, "high"], ["Long-term technical view", 67, "high"]].map(([part, p, lean, wording]) => ({ part, listAverage: 60, universeMedian: 55, avgPercentile: p, lean, wording: wording || null, stocks: symbols.length })) }
  : { locked: "gold", reason: "The style tilt is built from FinLit Prism ratings, which are part of the Gold plan." };
const resp = { week: "2026-W45", symbols, unknown: [], noPrices: [], page: D.page, meta: Object.fromEntries(symbols.map((s) => [s, { name: meta[s].name, sector: meta[s].sector, size: meta[s].size, mcap_cr: meta[s].mcap_cr }])), styleTilt: tilt };
if (D.page.layout === "long") D.page.first_k = { k: 12, effective_stocks: 6.3, rest: 28, added: 2.2 };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const ctx = await b.newContext({ viewport: { width: +W, height: W < 600 ? 844 : 900 }, colorScheme: theme, deviceScaleFactor: 1 });
await ctx.addInitScript(([syms, th]) => { try { localStorage.setItem("finlit-portfolio-v1", JSON.stringify({ holdings: syms.map((s, i) => ({ id: "i" + i, symbol: s, qty: 1, price: 0 })) })); localStorage.setItem("finlit-theme", th); localStorage.setItem("theme", th); document.documentElement.dataset.theme = th; } catch {} }, [symbols, theme]);
const calls = [];
await ctx.route("**/api/**", (r) => {
  const u = new URL(r.request().url()), p = u.pathname; calls.push(p);
  const j = (o, s = 200) => r.fulfill({ status: s, contentType: "application/json", body: JSON.stringify(o) });
  if (p === "/api/auth/me") return j({ user: { id: "u", email: "m@x.com", name: "M", role: "investor", plan, verified: true, mfa: false, mfaOk: false }, plan, limits: plan === "gold" ? { holdings: 500, mf_holdings: 500, compare: 4, watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, baskets: 100, earnings_calls_per_month: 5 } : { holdings: 500, mf_holdings: 30, compare: 2, watchlist_lists: 3, watchlist_symbols: 30, screens: 20, baskets: 20, earnings_calls_per_month: 0 }, csrf: "c", showcase: [] });
  if (p === "/api/stocks/search-index") return j({ fields: ["symbol", "name"], rows: symbols.map((s) => [s, meta[s].name]) });
  if (p === "/api/screener/universe") return j({ rows: symbols.map((s) => ({ symbol: s, name: meta[s].name, sector: meta[s].sector, market_cap: meta[s].mcap_cr })) });
  if (p === "/api/portfolio/overview") return j({ model: plan === "gold" ? "prism" : "finlit", plan, count: symbols.length, holdings: symbols.map(ready), disclaimer: "Information only, not investment advice." });
  if (p === "/api/portfolio/page") return j(resp);
  return j({});
});
const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200))); p.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text().slice(0, 160)); });

let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + String(x).slice(0, 140) : "")); };
await p.goto("http://127.0.0.1:5199/holdings", { waitUntil: "networkidle" }); await p.waitForTimeout(900);
const long = D.page.layout === "long";
check("page title and h1", (await p.locator("h1").innerText()) === "My portfolio");
check("summary shows the pack's score", (await p.locator(".pfx-sum").innerText()).includes(String(D.page.score.score)));
const eqText = await p.locator("#pfx-wtm").locator("xpath=..").innerText();
await p.getByRole("button", { name: /company value/ }).first().click(); await p.waitForTimeout(300);
const mcText = await p.locator("#pfx-wtm").locator("xpath=..").innerText();
check("Count as changes the readings and the label", eqText !== mcText && mcText.includes("sized by company value"), mcText.split("\n").slice(0,3).join("|"));
await p.getByRole("button", { name: /Equal amounts|Equal/ }).first().click();
const open0 = await p.locator("#pfx-tg-body").count();
check("What moves together is " + (long ? "closed" : "open") + " by default", long ? open0 === 0 : open0 === 1);
if (long) await p.getByRole("button", { name: "Show" }).click(); await p.waitForTimeout(300);
check("grid is drawn with every pair", (await p.locator(".pfx-gc").count()) === D.page.order.length ** 2, await p.locator(".pfx-gc").count());
await p.getByRole("button", { name: /^Same sector/ }).first().click(); await p.waitForTimeout(200);
const dim = await p.locator(".pfx-gc.dim").count();
check("Same-sector card dims the other pairs", dim > 0 && dim < D.page.order.length ** 2, dim);
await p.getByRole("button", { name: /^All pairs/ }).click();
check("grid hover text carries the number", /with .*: [0-9.\-−]+ · /.test((await p.locator(".pfx-gc:not(.d)").first().getAttribute("title")) || ""));
if (long) { await p.locator(".pfx-grow-l").nth(2).click(); await p.waitForTimeout(150); check("pick-a-share lights one row", (await p.locator(".pfx-gc.dim").count()) > 0); }
check("style tilt: " + (plan === "gold" ? "six rows" : "locked with a reason"), plan === "gold" ? (await p.locator(".pfx-tilt li").count()) === 6 : (await p.locator("#pf-style").innerText()).includes("Gold"));
if (plan === "gold") check("ordinals read right", (await p.locator("#pf-style").innerText()).includes("62nd") && !/\b62th\b/.test(await p.locator("#pf-style").innerText()));
await p.getByRole("tab", { name: "Ratios" }).click(); await p.waitForTimeout(300);
check("Ratios tab shows P/E", (await p.locator(".pfx-table thead").innerText()).includes("P/E"));
await p.getByRole("tab", { name: "Financials" }).click(); await p.waitForTimeout(300);
check("Financials tab shows net profit", (await p.locator(".pfx-table thead").innerText()).toLowerCase().includes("net profit"));
await p.getByRole("tab", { name: "Overview" }).click();
const dl = p.waitForEvent("download"); await p.getByRole("button", { name: "Export CSV" }).click(); const f = await dl; check("Export CSV downloads", /\.csv$/.test(f.suggestedFilename()), f.suggestedFilename());
await p.getByRole("button", { name: "Paste a list" }).click(); check("Paste a list opens a box", (await p.locator(".pfx-paste textarea").count()) === 1);
const n0 = await p.evaluate(() => JSON.parse(localStorage.getItem("finlit-portfolio-v1")).holdings.length);
if (long) await p.getByRole("button", { name: "Open all" }).click(); await p.waitForTimeout(200);
await p.getByRole("button", { name: /^Remove / }).first().click(); await p.waitForTimeout(300);
const n1 = await p.evaluate(() => JSON.parse(localStorage.getItem("finlit-portfolio-v1")).holdings.length);
check("remove takes one share off the saved list", n1 === n0 - 1, `${n0} -> ${n1}`);
check("no page errors", errs.filter((e) => !/403|404/.test(e)).length === 0, errs.join(" | "));
check("no sideways page scroll", (await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0);
console.log(fails ? "FAILED " + fails : "ALL PASSED");
await b.close();
