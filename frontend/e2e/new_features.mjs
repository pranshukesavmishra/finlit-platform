// This week's features, end to end against the full local stack: quarter results page, the new stock-page sections (DuPont, Profit Reality
// Check, margin trend, Pros and cons, profitability ratios), the chart "?" help, the TATAMOTORS redirect, the profit-gap alert, the Console
// "Make admin" button and the portfolio page (insights + lab, no swaps). Every new page is also checked at 390 px for sideways scrolling.
//   LIVE_DATA=1 ADMIN_REQUIRE_MFA=0 dev/run_stack.sh   (companies loaded: RELIANCE TCS INFY HDFCBANK TMPV TMCV WIPRO ITC;
//                                                        members pm-silver@ and pm-gold@example.com, plan Silver / Gold)
//   PM_PASSWORD=... node e2e/new_features.mjs http://localhost:4173
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";

const B = (process.argv[2] || "http://localhost:4173").replace(/\/$/, "");
const PW = process.env.PM_PASSWORD;
if (!PW) { console.log("PM_PASSWORD is required"); process.exit(2); }
const DB = process.env.DATABASE_URL || "postgresql://finlit:finlit@localhost:5432/finlit_dev";
const REDIS = process.env.REDIS_URL || "redis://localhost:6379/14";
const PY = process.env.BACKEND_PY || "../backend/.venv/bin/python";
let fails = 0;
const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const run = Date.now().toString(36);

const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
async function login(email, width = 1366) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, acceptDownloads: true });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: B }).catch(() => {});
  await ctx.addInitScript(() => { try { localStorage.setItem("finlit-theme", "light"); } catch {} });
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const r = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email, password: PW } });
  if (!r.ok()) throw new Error(`login ${email} failed: ${r.status()}`);
  const p = await ctx.newPage(); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 200)));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) p.errs.push(m.text().slice(0, 200)); });
  p.bad = []; p.on("response", (x) => { if (x.status() >= 500 && x.url().includes("/api/")) p.bad.push(`${x.status()} ${new URL(x.url()).pathname}`); });
  return { ctx, p };
}
const sideways = (p) => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
// Anything positioned out of the flow that is very tall and narrow is a chart layer that has escaped its card and covers the page.
const overlays = (p) => p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => {
  const cs = getComputedStyle(e); if (cs.position === "static" || cs.display === "none") return false;
  const r = e.getBoundingClientRect(); return r.height > 1400 && r.width < 400;
}).map((e) => e.tagName + "." + String(e.className).slice(0, 40)));
const text = (p) => p.evaluate(() => document.body.innerText);

// ------------------------------------------------------------------------------------------------ /results/quarter as Silver
let { ctx, p } = await login("pm-silver@example.com");
await p.goto(B + "/results/quarter", { waitUntil: "networkidle" });
await p.locator(".qr-t tbody tr").first().waitFor({ timeout: 15000 }).catch(() => {});
check("quarter: heading and fiscal quarter", await p.locator("h1").innerText().then((t) => /Quarter results\s+Q\d FY\d\d/.test(t)).catch(() => false), await p.locator("h1").innerText().catch(() => ""));
check("quarter: table has the 11 column headings", await p.locator(".qr-t thead th").allTextContents().then((h) => h.join("|") === "Company|Revenue|YoY|QoQ|Op. profit|OPM|Net profit|YoY|QoQ|NPM|EPS"));
check("quarter: scoreboard tiles shown", (await p.locator(".qr-tile").count()) >= 4);
check("quarter: Silver sees figures, not the lock card", (await p.locator(".qr-cap").count()) === 0 && (await p.locator(".qr-unlock").count()) === 0);
check("quarter: companies listed", (await p.locator(".qr-r").count()) >= 5, String(await p.locator(".qr-r").count()));
check("quarter: a result row has real figures", await p.locator(".qr-r").first().innerText().then((t) => /\d/.test(t)));
// date grouping, newest first
const days = await p.locator(".qr-day b").allInnerTexts();
check("quarter: rows are grouped under date headings", days.length >= 2, days.slice(0, 4).join(" / "));
const api = await p.evaluate(() => fetch("/api/results/quarter?scope=all&sort=date&dir=desc&limit=100", { credentials: "same-origin" }).then((r) => r.json()));
const dts = (api.rows || []).map((r) => r.date), today = api.today;
const declared = dts.filter((d) => d <= today), coming = dts.filter((d) => d > today);
check("quarter: declared dates run newest first", declared.length > 1 && declared.every((d, i) => i === 0 || declared[i - 1] >= d), declared.slice(0, 3).join(","));
check("quarter: dates still to come follow, soonest first", coming.every((d, i) => i === 0 || coming[i - 1] <= d));
// the page's own labels use the browser's clock and the API's "today" is India's, so only the order is checked here, not the words
check("quarter: 'Still to declare' divider comes before the dates still to come", dts.slice(0, 50).every((d) => d <= today) ? (await p.locator(".qr-up").count()) === 0 : (await p.locator(".qr-up").count()) === 1);
check("quarter: sort button says Newest first", (await p.getByRole("button", { name: "Highest first" }).count()) === 1 && /Newest first/.test(await p.locator(".qr-dir").innerText()));
await p.locator(".qr-dir").click();
check("quarter: sort button flips to Oldest first", /Oldest first/.test(await p.locator(".qr-dir").innerText()));
await p.locator(".qr-dir").click();
// filters
await p.getByLabel("Search company or symbol").fill("TCS"); await p.getByRole("button", { name: "Search", exact: true }).click(); await p.waitForTimeout(900);
check("quarter: search narrows to TCS", (await p.locator(".qr-r").count()) >= 1 && (await p.locator(".qr-r .qr-sym", { hasText: /^TCS$/ }).count()) === 1, String(await p.locator(".qr-r").count()));
await p.getByRole("button", { name: "Clear filters" }).click(); await p.waitForTimeout(700);
check("quarter: clear filters brings the list back", (await p.locator(".qr-r").count()) >= 5);
const sectors = await p.getByLabel("Sector").locator("option").allInnerTexts();
check("quarter: sector filter has sectors", sectors.length > 2, sectors.slice(0, 4).join(","));
const sect = sectors.find((s) => /^Information Tech|^IT|Software/i.test(s)) || sectors[1];
await p.getByLabel("Sector").selectOption({ label: sect }); await p.waitForTimeout(800);
const afterSector = await p.locator(".qr-r").count();
check("quarter: sector filter applies", afterSector >= 1 && /companies?/.test(await p.locator(".qr-count").innerText()), `${sect}: ${afterSector}`);
await p.getByLabel("Sector").selectOption(""); await p.waitForTimeout(500);
await p.getByLabel("Market cap band").selectOption({ index: 1 }); await p.waitForTimeout(700);
check("quarter: market cap filter applies without errors", (await p.locator(".formerr").count()) === 0);
await p.getByLabel("Market cap band").selectOption({ index: 0 }); await p.waitForTimeout(500);
await p.getByLabel("Sort by").selectOption({ label: await p.getByLabel("Sort by").locator("option").nth(2).innerText() }); await p.waitForTimeout(700);
check("quarter: a growth sort hides the date headings", (await p.locator(".qr-day").count()) === 0);
await p.getByLabel("Sort by").selectOption("date"); await p.waitForTimeout(600);
// flagged
await p.locator(".qr-flagged .sw").click(); await p.waitForTimeout(900);
const flaggedRows = await p.locator(".qr-r.flag").count(), chips = await p.locator(".qr-flag .chip").allInnerTexts();
check("quarter: 'Only flagged' lists flagged companies (or an empty state)", flaggedRows > 0 ? chips.length === flaggedRows && chips.every((c) => /Profit and sales moved apart/.test(c)) : (await p.getByText("No companies match").count()) === 1, `${flaggedRows} flagged`);
if (flaggedRows) {
  check("quarter: flagged row explains the gap and links to the alert and report", /points apart/.test(await p.locator(".qr-flag").first().innerText()) && (await p.locator(".qr-flag a", { hasText: "Set the alert" }).count()) >= 1 && (await p.locator(".qr-flag a", { hasText: "Open the report" }).count()) >= 1);
}
await p.locator(".qr-flagged .sw").click(); await p.waitForTimeout(700);
// copy summary (needs declared companies: today's board meetings have no figures yet)
await p.getByLabel("Status").selectOption("declared"); await p.waitForTimeout(900);
const copyBtn = p.locator(".qr-copy").first();
check("quarter: copy buttons present", (await p.locator(".qr-copy").count()) >= 1);
if (await copyBtn.count()) {
  const line = await p.locator(".qr-line code").first().innerText();
  await copyBtn.click(); await p.waitForTimeout(300);
  const clip = await p.evaluate(() => navigator.clipboard.readText()).catch(() => null);
  check("quarter: Copy puts the summary line on the clipboard", clip === null ? (await copyBtn.innerText()) === "Copied" : clip.trim() === line.trim(), (clip || line).slice(0, 80));
  check("quarter: button confirms with Copied", (await copyBtn.innerText()) === "Copied");
}
// CSV export
const [dl] = await Promise.all([p.waitForEvent("download", { timeout: 15000 }).catch(() => null), p.locator(".qr-csv").click()]);
check("quarter: CSV download starts", !!dl && /^FinLit-results-.*\.csv$/.test(dl.suggestedFilename()), dl ? dl.suggestedFilename() : "no download");
if (dl) {
  const path = await dl.path(); const csv = (await import("node:fs")).readFileSync(path, "utf8").replace(/^﻿/, "");
  const lines = csv.split(/\r?\n/).filter(Boolean);
  check("quarter: CSV has a header and one line per company", lines.length > 5 && /Net profit/.test(csv) && /Revenue vs profit gap/.test(csv), `${lines.length} lines`);
}
check("quarter: quarter picker lists quarters with counts", await p.getByLabel("Quarter").locator("option").allInnerTexts().then((o) => o.length >= 1 && /out\)/.test(o[0])));
check("quarter: no page errors / 5xx", p.errs.length === 0 && p.bad.length === 0, [...p.errs, ...p.bad].join(" | "));
check("quarter: nothing overlays the page", (await overlays(p)).length === 0);
await ctx.close();

// ------------------------------------------------------------------------------------------------ stock pages
({ ctx, p } = await login("pm-silver@example.com"));
for (const sym of ["RELIANCE", "TMPV"]) {
  await p.goto(`${B}/stocks/${sym}`, { waitUntil: "networkidle" });
  await p.getByRole("heading", { name: /DuPont analysis/ }).waitFor({ timeout: 20000 }).catch(() => {});
  await p.locator("table.pr-t").waitFor({ timeout: 20000 }).catch(() => {});
  const t = await text(p);
  check(`${sym}: DuPont analysis section`, (await p.getByRole("heading", { name: /DuPont analysis/ }).count()) === 1);
  check(`${sym}: Profit Reality Check section`, (await p.getByRole("heading", { name: /Profit Reality Check/ }).count()) === 1);
  check(`${sym}: Margin trend section`, (await p.getByRole("heading", { name: /Margin trend/ }).count()) === 1);
  check(`${sym}: Pros and cons section (and no 'How the score works')`, (await p.getByRole("heading", { name: "Pros and cons" }).count()) >= 1 && !/How the score works/.test(t));
  check(`${sym}: profitability ratios table`, (await p.getByRole("heading", { name: /Profitability ratios/ }).count()) === 1 && (await p.locator("table.pr-t").count()) >= 1 && (await p.locator("table.pr-t").first().locator("tbody tr").count()) > 3);
  check(`${sym}: profitability ratios bar chart`, (await p.locator(".pr-bars").count()) >= 1 && (await p.locator(".pr-bars").first().locator("> *").count()) > 2);
  const ov = await overlays(p); check(`${sym}: no tall narrow positioned element covering the page`, ov.length === 0, ov.join(","));
  // click each bar chip / metric in the ratios area, the chart must stay in place
  const chip = p.locator(".pr-t tbody tr:not(.pr-g) td:first-child").nth(2);
  if (await chip.count()) { await chip.click().catch(() => {}); await p.waitForTimeout(300); }
  check(`${sym}: still no overlay after choosing another ratio`, (await overlays(p)).length === 0);
  // '?' popover on hover
  const help = p.locator(".card", { has: p.getByRole("heading", { name: /DuPont analysis/ }) }).locator(".chh-b").first();
  await help.scrollIntoViewIfNeeded(); await help.hover(); await p.waitForTimeout(400);
  const pop = p.locator(".chh-p:not([hidden])"); const popVisible = await pop.first().isVisible().catch(() => false);
  check(`${sym}: '?' popover opens on hover`, popVisible && (await pop.first().innerText()).length > 40, popVisible ? (await pop.first().innerText()).slice(0, 60).replace(/\n/g, " ") : "");
  if (popVisible) { const bb = await pop.first().boundingBox(); check(`${sym}: popover stays inside the viewport`, !!bb && bb.x >= 0 && bb.x + bb.width <= 1366 && bb.y >= 0); }
  await p.mouse.move(5, 5); await p.waitForTimeout(400);
  check(`${sym}: popover closes when the pointer leaves`, (await pop.count()) === 0);
  check(`${sym}: no page errors / 5xx`, p.errs.length === 0 && p.bad.length === 0, [...p.errs, ...p.bad].join(" | ")); p.errs.length = 0;
}
// the old ticker still lands on the new one
await p.goto(B + "/stocks/TATAMOTORS", { waitUntil: "networkidle" });
await p.waitForURL(/\/stocks\/TMPV/, { timeout: 8000 }).catch(() => {});
check("TATAMOTORS redirects to /stocks/TMPV", /\/stocks\/TMPV(\?|#|$)/.test(p.url()), p.url());
check("TMPV page after redirect has a heading", (await p.locator("h1").count()) >= 1);
await ctx.close();

// ------------------------------------------------------------------------------------------------ account + alerts (Silver)
({ ctx, p } = await login("pm-silver@example.com"));
await p.goto(B + "/account/appearance", { waitUntil: "networkidle" });
const gap = p.getByLabel(/revenue and profit move 15 or more points apart/);
check("account: profit-gap preference checkbox is shown", (await gap.count()) === 1);
if (await gap.count()) {
  const before = await gap.isChecked();
  await gap.setChecked(!before, { force: true }).catch(async () => { await p.locator("label.sw", { hasText: "revenue and profit move" }).click(); });
  await p.waitForTimeout(700);
  await p.reload({ waitUntil: "networkidle" });
  const after = await p.getByLabel(/revenue and profit move 15 or more points apart/).isChecked();
  check("account: the profit-gap preference is saved", after === !before, `${before} -> ${after}`);
  await p.getByLabel(/revenue and profit move 15 or more points apart/).setChecked(before, { force: true }).catch(() => {}); await p.waitForTimeout(500);
}
await p.goto(B + "/alerts", { waitUntil: "networkidle" });
const opts = await p.locator("#alx-metric option").allInnerTexts();
check("alerts: composer offers 'Revenue vs profit growth gap'", opts.some((o) => /^Revenue vs profit growth gap/.test(o)), String(opts.length) + " metrics");
await p.locator("#alx-metric").selectOption({ label: opts.find((o) => /^Revenue vs profit growth gap/.test(o)) || "" }).catch(() => {});
check("alerts: the gap metric explains itself and offers 'above' only", /percentage points apart/.test(await text(p)) && (await p.locator("#alx-op").isDisabled()));
await ctx.close();

// ------------------------------------------------------------------------------------------------ Console, as an admin
const adminEmail = `boss-nf-${run}@example.com`, memberEmail = `asha-nf-${run}@example.com`;
let adminOk = true;
try {
  execFileSync("redis-cli", ["-u", REDIS, "flushdb"]);
  const env = { ...process.env, DATABASE_URL: DB, REDIS_URL: REDIS };
  execFileSync(PY, ["-m", "finlit.auth.cli", "create-admin", "--email", adminEmail], { cwd: "../backend", env: { ...env, FINLIT_ADMIN_PASSWORD: PW }, encoding: "utf8" });
  execFileSync(PY, ["-m", "finlit.auth.cli", "create-member", "--email", memberEmail, "--plan", "basic"], { cwd: "../backend", env: { ...env, FINLIT_MEMBER_PASSWORD: PW }, encoding: "utf8" });
} catch (e) { adminOk = false; check("console: could create an admin and a member", false, String(e.message).slice(0, 120)); }
if (adminOk) {
  try {
    ({ ctx, p } = await login(adminEmail));
    await p.goto(B + "/console", { waitUntil: "networkidle" });
    const needsMfa = (await p.getByText("One more step").count()) === 1;
    check("console: opens for the admin without an authenticator (ADMIN_REQUIRE_MFA=0)", !needsMfa && (await p.getByRole("heading", { name: "Console" }).count()) === 1, needsMfa ? "server asks for two-step: start the stack with ADMIN_REQUIRE_MFA=0" : "");
    await p.getByRole("tab", { name: "Members" }).click(); await p.waitForTimeout(900);
    const row = p.locator("tr", { hasText: memberEmail });
    check("console: Members lists the new member with a 'Make admin' button", (await row.getByRole("button", { name: "Make admin" }).count()) === 1);
    check("console: the admin's own row offers 'Remove admin'", (await p.locator("tr", { hasText: adminEmail }).getByRole("button", { name: "Remove admin" }).count()) === 1);
    p.once("dialog", (d) => d.dismiss());
    await row.getByRole("button", { name: "Make admin" }).click(); await p.waitForTimeout(500);
    check("console: dismissing the confirmation leaves the member unchanged", (await row.getByRole("button", { name: "Make admin" }).count()) === 1);
    check("console: no page errors", p.errs.length === 0, p.errs.join(" | "));
    await p.setViewportSize({ width: 390, height: 800 }); await p.goto(B + "/console", { waitUntil: "networkidle" });
    check("console @390px: no sideways page scroll", (await sideways(p)) <= 1, (await sideways(p)) + "px");
    await ctx.close();
  } catch (e) { check("console: admin flow ran", false, String(e.message).slice(0, 160)); }
}

// ------------------------------------------------------------------------------------------------ Holdings
({ ctx, p } = await login("pm-silver@example.com"));
await p.goto(B + "/holdings", { waitUntil: "networkidle" });
await p.waitForSelector("text=Add your shares");
const clearAll = async () => { for (let i = 0; i < 40 && (await p.locator("table.hold tbody tr").count()); i++) { await p.locator("table.hold tbody tr").first().getByRole("button", { name: /Remove/ }).click(); await p.waitForTimeout(120); } };
await clearAll();
await p.locator("textarea").first().fill("TCS\nINFY\nITC\nHDFCBANK\nWIPRO").catch(() => {});
await p.getByRole("button", { name: "Add these" }).click().catch(() => {});
await p.waitForTimeout(1500);
check("holdings: shares added by name", (await p.locator("table.hold tbody tr").count()) >= 3, String(await p.locator("table.hold tbody tr").count()));
await p.getByText("Portfolio insights").first().waitFor({ timeout: 10000 }).catch(() => {});
check("holdings: Portfolio insights shown", (await p.getByRole("heading", { name: "Portfolio insights" }).count()) === 1);
check("holdings: Portfolio lab shown", (await p.getByText("Portfolio lab").count()) >= 1);
const ht = (await text(p)).toLowerCase();
check("holdings: no 'swap' text anywhere on the page", !/\bswap/.test(ht) && (await p.getByRole("button", { name: /swap/i }).count()) === 0);
check("holdings: no overlay", (await overlays(p)).length === 0);
check("holdings: no page errors / 5xx", p.errs.length === 0 && p.bad.length === 0, [...p.errs, ...p.bad].join(" | "));
await clearAll();
await ctx.close();

// compare: the swap button is gone
({ ctx, p } = await login("pm-gold@example.com"));
await p.goto(B + "/compare", { waitUntil: "networkidle" });
check("compare: no 'Swap' button", (await p.getByRole("button", { name: /swap/i }).count()) === 0 && !/swap first two/i.test(await text(p)));
await ctx.close();

// ------------------------------------------------------------------------------------------------ 390 px: no sideways scroll on every new page
({ ctx, p } = await login("pm-silver@example.com", 390));
const phone = ["/results/quarter", "/results/quarter?quarter=", "/stocks/RELIANCE", "/stocks/TMPV", "/account", "/alerts", "/holdings", "/results"];
for (const path of phone) {
  await p.goto(B + path, { waitUntil: "networkidle" }); await p.waitForTimeout(600);
  if (/^\/stocks\//.test(path)) { await p.mouse.wheel(0, 3000); await p.waitForTimeout(300); }
  const over = await sideways(p);
  check(`390px ${path}: no sideways page scroll`, over <= 1, over + "px");
}
await p.goto(B + "/stocks/RELIANCE", { waitUntil: "networkidle" });
const hb = p.locator(".chh-b").first(); await hb.scrollIntoViewIfNeeded(); await hb.tap().catch(() => hb.click()); await p.waitForTimeout(400);
const bb = await p.locator(".chh-p").first().boundingBox().catch(() => null);
check("390px stock: '?' popover fits the phone screen", !!bb && bb.x >= 0 && bb.x + bb.width <= 390, bb ? `${Math.round(bb.x)}..${Math.round(bb.x + bb.width)}` : "no popover");
check("390px: no page errors", p.errs.length === 0, p.errs.join(" | "));
await ctx.close();

await browser.close();
console.log(fails ? `${fails} check(s) failed` : "all checks passed");
process.exit(fails ? 1 : 0);
