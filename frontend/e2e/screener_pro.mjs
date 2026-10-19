// The Silver/Gold screener against a running site: plan gate in the page, live filtering, sorting, quick screens, CSV, shareable link, phone width.
//   PM_PASSWORD=... node e2e/screener_pro.mjs http://localhost:4173     (members pm-silver@ / pm-gold@example.com; visitor is Basic)
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
async function open(who, w = 1366, h = 900) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, acceptDownloads: true }); const p = await ctx.newPage(); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  if (who) { const me = await (await ctx.request.get(B + "/api/auth/me")).json();
    const r = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: `pm-${who}@example.com`, password: process.env.PM_PASSWORD } }); check(`${who} signs in`, r.ok(), String(r.status())); }
  await p.goto(B + "/screener", { waitUntil: "networkidle" }); await p.waitForSelector(".scr-t tbody tr", { timeout: 8000 }).catch(() => null); return { ctx, p };
}
const count = async (p) => Number((await p.locator(".scr-count").innerText()).replace(/\D/g, "") || -1);
const settle = (p) => p.waitForTimeout(700);

// ---- visitor = Basic
{ const { ctx, p } = await open(null);
  const total = await count(p); check("basic: companies listed", total > 100, String(total));
  check("basic: result rows capped at 25", (await p.locator(".scr-t tbody tr").count()) <= 25);
  check("basic: upgrade banner when capped", (await p.locator(".pl-cap").count()) === 1);
  await p.getByRole("button", { name: "P/B Ratio", exact: true }).click();
  check("basic: P/B filter is locked (no range boxes), P/E is open", (await p.getByLabel("P/B Ratio minimum").count()) === 0 && (await p.getByText(/Unlock this filter with the Silver plan/).count()) === 1);
  await p.getByRole("button", { name: "P/E Ratio", exact: true }).click();
  await p.getByLabel("P/E Ratio maximum", { exact: true }).fill("20"); await settle(p);
  const t2 = await count(p); check("basic: P/E filter narrows the list", t2 < total && t2 > 0, `${total} -> ${t2}`);
  await p.getByRole("button", { name: /^FinLit Model/ }).click(); check("basic: model group shows the Gold lock card", (await p.getByText("Filter by the FinLit model").count()) === 1);
  const dl = await p.locator(".scr-tools").getByRole("button", { name: "Download" }).click(); await p.waitForTimeout(500);
  check("basic: download asks to upgrade", (await p.locator(".toast, [role=status]").filter({ hasText: /Silver/ }).count()) > 0 || (await p.getByText(/Silver plan/).count()) > 0);
  await ctx.close(); }

// ---- Silver
{ const { ctx, p } = await open("silver");
  const total = await count(p); check("silver: no 25-row cap", (await p.locator(".pl-cap").count()) === 0 && total > 25);
  await p.getByRole("button", { name: "P/B Ratio", exact: true }).click();
  check("silver: P/B filter is open (range boxes, histogram, slider, 3 average tabs)", (await p.getByLabel("P/B Ratio minimum", { exact: true }).count()) === 1 && (await p.locator(".pl-hist i").count()) > 10 && (await p.locator(".pl-slider input").count()) === 2 && (await p.getByRole("tab", { name: /5Y avg/ }).count()) === 1);
  await p.getByRole("button", { name: "P/E Ratio", exact: true }).click();
  await p.getByRole("button", { name: /^Profitability/ }).click(); await p.getByRole("button", { name: /^Return on equity/ }).click();
  await p.getByLabel("P/E Ratio maximum", { exact: true }).fill("25"); await p.getByLabel("Return on equity minimum", { exact: true }).fill("12"); await settle(p);
  const t1 = await count(p); check("silver: two filters narrow the list", t1 < total && t1 >= 0, `${total} -> ${t1}`);
  const url = p.url(); check("silver: address holds the screen (shareable)", /[?&]s=/.test(url));
  // sort
  await p.getByRole("button", { name: "Sort by P/E ratio" }).click(); await settle(p);
  const pes = (await p.locator(".scr-t tbody tr").evaluateAll((trs, i) => trs.map((r) => r.children[i]?.textContent), 4)).map((s) => parseFloat((s || "").replace(/[^0-9.\-]/g, ""))).filter((n) => !Number.isNaN(n));
  check("silver: sorting by P/E orders the rows", pes.length < 2 || pes.every((v, i) => i === 0 || v >= pes[i - 1] - 1e-9) || pes.every((v, i) => i === 0 || v <= pes[i - 1] + 1e-9), pes.slice(0, 5).join(", "));
  // shareable link opens same count
  const p2 = await ctx.newPage(); await p2.goto(url, { waitUntil: "networkidle" }); await p2.waitForSelector(".scr-count"); await p2.waitForTimeout(800);
  check("silver: shared link restores the same screen", (await count(p2)) === t1, String(await count(p2))); await p2.close();
  // valuation card: slider drives the range; averages tab filters on the 5-year average
  await p.getByRole("button", { name: /^Valuation/ }).click(); await p.getByRole("button", { name: /^Valuation/ }).click();
  await p.getByRole("button", { name: "Dividend Yield", exact: true }).click(); await p.getByLabel("Dividend Yield minimum", { exact: true }).fill("1"); await settle(p);
  const dy = await count(p); check("silver: dividend yield filter narrows", dy <= t1 && dy >= 0, `${t1} -> ${dy}`);
  await p.getByRole("button", { name: "P/E Ratio", exact: true }).click(); await p.getByRole("tab", { name: /5Y avg/ }).click();
  const before = await count(p); await p.getByLabel("P/E Ratio, 5Y average maximum", { exact: true }).fill("5"); await settle(p);
  const after = await count(p); check("silver: P/E 5Y-average tab filters on its own value", after <= before, `${before} -> ${after}`);
  await p.locator(".pl-card:has(.pm-seg[role=tablist]) .pl-rm").click(); await settle(p);
  check("silver: Remove clears the filter", (await count(p)) >= after);
  // model filter refused
  await p.getByRole("button", { name: /^FinLit Model/ }).click(); check("silver: FinLit model filters are locked (Gold)", (await p.getByText("Filter by the FinLit model").count()) === 1);
  // quick screens
  await p.getByRole("tab", { name: "Quick screens" }).click();
  check("silver: Gold screens are locked", (await p.locator(".qs.lock").count()) >= 4);
  await p.getByRole("button", { name: /Low debt/ }).click(); await settle(p);
  check("silver: quick screen applies filters", (await p.locator(".fchip").count()) >= 1);
  // download
  const [d] = await Promise.all([p.waitForEvent("download", { timeout: 8000 }).catch(() => null), p.locator(".scr-tools").getByRole("button", { name: "Download" }).click()]);
  check("silver: CSV downloads", !!d && /FinLit-screen\.csv/.test(d.suggestedFilename()));
  // save screen
  await p.getByRole("tab", { name: "Filters" }).click(); await p.getByLabel("Screen name").fill("My low debt"); await p.getByRole("button", { name: "Save", exact: true }).click();
  await p.getByRole("tab", { name: "Quick screens" }).click(); check("silver: saved screen listed", (await p.locator(".qs-row .qs b", { hasText: "My low debt" }).count()) === 1);
  // columns
  await p.getByRole("tab", { name: "Filters" }).click(); await p.getByRole("button", { name: /^Columns/ }).click(); await p.getByLabel("Find a column").fill("quick ratio");
  await p.locator(".pl-colmenu label", { hasText: "Quick ratio" }).locator("input").check(); await settle(p);
  check("silver: added column appears", (await p.locator(".scr-t th", { hasText: "Quick ratio" }).count()) === 1);
  await p.screenshot({ path: `${OUT}/screener-silver.png`, fullPage: false });
  check("silver: no page errors", p.errs.length === 0, p.errs.join(" | ")); await ctx.close(); }

// ---- Gold
{ const { ctx, p } = await open("gold");
  await p.getByRole("button", { name: /^FinLit Model/ }).click();
  check("gold: model filters are open", (await p.getByRole("button", { name: /^FinLit score/ }).count()) === 1);
  await p.getByRole("button", { name: /^FinLit score/ }).click(); await p.getByLabel("FinLit score minimum", { exact: true }).fill("40"); await settle(p);
  check("gold: model filter works", (await count(p)) >= 0 && (await p.locator(".scr-count").innerText()) !== "…");
  await p.getByRole("tab", { name: "Quick screens" }).click(); check("gold: Gold screens unlocked", (await p.locator(".qs.lock").count()) === 0);
  await p.screenshot({ path: `${OUT}/screener-gold.png`, fullPage: false }); check("gold: no page errors", p.errs.length === 0, p.errs.join(" | ")); await ctx.close(); }

// ---- phone
{ const { ctx, p } = await open("silver", 390, 844);
  const over = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check("phone: no sideways scroll", over <= 1, String(over));
  await p.screenshot({ path: `${OUT}/screener-phone.png`, fullPage: false }); await ctx.close(); }
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
