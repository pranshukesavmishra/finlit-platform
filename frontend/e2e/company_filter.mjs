// /prism company picker with two filters on, every /api/** call mocked (Gold member). Checks: the funnel names its filters, a typed company hidden by
// the filter shows greyed with the reason and Show it, Clear filters works, a BSE code / NSE code / ISIN finds a company, browse lists a company with no sector.
//   node e2e/company_filter.mjs http://127.0.0.1:5199 /path/to/out
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), out = process.argv[3] || ".";
const rows = [["TCS", "Tata Consultancy Services Ltd", "532540", 1], ["HDFCBANK", "HDFC Bank Ltd", "500180", 1], ["TATAMOTORS", "Tata Motors Ltd", "500570", 0, "TMCV"], ["RELIANCE", "Reliance Industries Ltd", "500325", 1], ["NOSEC", "Nameless Sector Ltd", "999999", 0]];
const index = { fields: ["symbol", "name", "bse", "ready", "nse"], rows, sectors: ["Information Technology", "Financial Services", "Auto", "Energy"], sec: [0, 1, 2, 3, -1], mc: [1400000, 1200000, 300000, 1900000, 0], isin: ["INE467B01029", "INE040A01034", "INE155A01022", "INE002A01018", ""] };
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0; const ok = (c, m) => { if (!c) { bad++; console.log("FAIL", m); } else console.log("ok  ", m); };
for (const [w, h, n] of [[1280, 900, "d"], [950, 900, "t"], [390, 900, "m"]]) for (const theme of ["dark", "light"]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  await ctx.route("**/api/**", (route) => {
    const u = new URL(route.request().url()).pathname, j = (b) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(b) });
    if (u.endsWith("/auth/me")) return j({ user: { id: "u", email: "g@x.in", name: "Gold", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false }, plan: "gold", limits: {}, csrf: "t", showcase: [] });
    if (u.endsWith("/stocks/search-index")) return j(index);
    if (u.endsWith("/me/state")) return j({ watchlist: { lists: [] }, portfolio: { holdings: [] }, screens: [], prefs: {} });
    return j({});
  });
  const p = await ctx.newPage(); const tag = `${n}-${theme}`;
  p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", (e.stack || String(e)).slice(0, 500)); });
  await p.goto(base + "/prism", { waitUntil: "networkidle" });
  await p.screenshot({ path: `${out}/load-${tag}.png` }); 
  const box = p.getByRole("combobox", { name: "Choose a company" });
  await box.fill("tata"); await p.waitForTimeout(300);
  ok(await p.getByRole("option").count() === 2, `${tag}: no filter, two Tata companies listed`);
  await p.getByRole("button", { name: /^Filters/ }).click();
  await p.locator(".sf-panel select").first().selectOption("Financial Services");
  await p.locator(".sf-panel select").nth(1).selectOption("mega");
  await p.getByRole("button", { name: "Done" }).click();
  ok(await p.getByRole("button", { name: /Filters: 2 active/ }).count() === 1, `${tag}: funnel says 2 active and names them`);
  ok(await p.getByTestId("active-filters").innerText().then((t) => /Sector: Financial Services · Market cap: Mega-cap/.test(t)), `${tag}: visible line names both filters`);
  await box.fill("tata"); await p.waitForTimeout(300);
  ok(await p.getByText("Hidden by your filter: Sector Financial Services").count() >= 1, `${tag}: hidden Tata shown with the reason`);
  await p.screenshot({ path: `${out}/hidden-${tag}.png` });
  await p.getByRole("button", { name: /^Show Tata Consultancy/ }).click(); await p.waitForTimeout(200);
  ok(await p.getByRole("option", { name: /TCS/ }).count() === 1, `${tag}: Show it brings TCS back as a normal row`);
  await box.press("Escape"); await p.getByTestId("active-filters").getByRole("button", { name: "Clear filters" }).click(); await p.waitForTimeout(200);
  ok(await p.getByTestId("active-filters").count() === 0, `${tag}: Clear filters removes the line`);
  for (const [q, sym] of [["532540", "TCS"], ["INE040A01034", "HDFCBANK"], ["TMCV", "TATAMOTORS"], ["nameless", "NOSEC"]]) { await box.fill(q); await p.waitForTimeout(250); ok(await p.getByRole("option", { name: new RegExp(sym) }).count() === 1, `${tag}: "${q}" finds ${sym}`); }
  await box.fill("zzzz"); await p.waitForTimeout(250);
  ok(await p.getByText(/No listed company matches “zzzz” by name, symbol or ISIN/).count() === 1, `${tag}: empty search says why`);
  await box.fill(""); await p.getByRole("button", { name: "Show sectors" }).click(); await p.waitForTimeout(300);
  await p.getByRole("button", { name: /No sector on file/ }).click();
  ok(await p.getByRole("link", { name: /NOSEC/ }).count() === 1, `${tag}: company with no sector is browsable`);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok(overflow <= 1, `${tag}: no horizontal scroll`);
  await p.screenshot({ path: `${out}/browse-${tag}.png` });
  await ctx.close();
}
await browser.close(); console.log(bad ? `${bad} problem(s)` : "all good"); process.exit(bad ? 1 : 0);
