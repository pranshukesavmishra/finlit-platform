// Indices: live levels for every NSE/BSE index (key tiles, groups, search, sort) and the 1/3/5-year valuation history of any index.
//   PM_PASSWORD=... node e2e/indices.mjs http://localhost:4173   (needs member pm-gold@example.com; local data comes from recorded provider answers)
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const pub = await (await fetch(B + "/api/indices")).json();
check("index levels are public and NIFTY 50 comes first", pub.items?.[0]?.code === "NIF50" && pub.items.length > 200, `${pub.items?.length} indices`);
check("valuation history is Gold only", (await fetch(B + "/api/indices/NIF50/valuation")).status === 401 || (await fetch(B + "/api/indices/NIF50/valuation")).status === 403);
for (const w of [1366, 390]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const r = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: "pm-gold@example.com", password: process.env.PM_PASSWORD } });
  check(`${w}: gold signs in`, r.ok(), String(r.status()));
  const t0 = Date.now(); await p.goto(B + "/premium/markets#indices", { waitUntil: "domcontentloaded" }); await p.waitForSelector(".pm-heat .pm-tile");
  check(`${w}: index tiles shown fast`, Date.now() - t0 < 4000, (Date.now() - t0) + " ms incl. page load");
  const tiles = await p.locator(".pm-heat .pm-tile small").allInnerTexts(); check(`${w}: key indices first`, /nifty 50/i.test(tiles[0]) && tiles.some((t) => /sensex/i.test(t)) && tiles.some((t) => /bank/i.test(t)), tiles.join(" | "));
  await p.getByRole("button", { name: "Sector", exact: true }).click(); await p.waitForTimeout(200);
  const groups = await p.locator(".pm-t tbody td small").allInnerTexts(); check(`${w}: sector filter`, groups.length > 0 && groups.every((g) => g.includes("Sector")), groups.slice(0, 3).join(","));
  await p.getByRole("button", { name: "All", exact: true }).first().click(); await p.getByPlaceholder("e.g. Bank, IT, Midcap").fill("bank"); await p.waitForTimeout(200);
  const names = await p.locator(".pm-t tbody td b").allInnerTexts(); check(`${w}: search narrows`, names.length > 0 && names.every((n) => /bank/i.test(n)), names.slice(0, 4).join(","));
  await p.locator(".pm-heat .pm-tile").first().click(); await p.waitForSelector(".pm-verdict", { timeout: 8000 });
  const verdict = await p.locator(".pm-verdict").innerText(); check(`${w}: NIFTY 50 valuation verdict`, /Nifty 50 P\/E/i.test(verdict) && /median/.test(verdict), verdict.replace(/\s+/g, " ").slice(0, 140));
  check(`${w}: five years of history by default`, /trading days/.test(await p.locator(".pm-cards").last().innerText()) && Number((await p.locator(".pm-cards").last().innerText()).match(/([\d,]+) trading days/)?.[1].replace(/,/g, "")) > 1000);
  await p.getByRole("button", { name: "1Y", exact: true }).click(); await p.waitForTimeout(600);
  const n1 = Number((await p.locator(".pm-cards").last().innerText()).match(/([\d,]+) trading days/)?.[1].replace(/,/g, "")); check(`${w}: 1Y shows about a year`, n1 > 200 && n1 < 280, String(n1));
  await p.getByRole("button", { name: "P/B", exact: true }).click(); await p.waitForTimeout(200); check(`${w}: P/B view`, /P\/B/.test(await p.locator(".pm-verdict").innerText()));
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check(`${w}: no sideways scroll`, ov <= 1, ov + "px");
  await p.screenshot({ path: `${OUT}/indices_val_${w}.png`, fullPage: false });
  check(`${w}: no page errors`, p.errs.length === 0, p.errs.join(" | ")); await ctx.close();
}
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
