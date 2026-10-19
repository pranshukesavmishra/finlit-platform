// My portfolio: add shares by name (ticker, company name, BSE code, pasted list, CSV), see each one's FinLit score, no quantities or prices asked.
//   PM_PASSWORD=... node e2e/portfolio.mjs http://localhost:4173   (needs member pm-silver@example.com)
import { chromium } from "playwright";
import fs from "node:fs";
const B = process.argv[2] || "http://localhost:4173";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
const me = await (await ctx.request.get(B + "/api/auth/me")).json();
await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: "pm-silver@example.com", password: process.env.PM_PASSWORD } });
await p.goto(B + "/holdings", { waitUntil: "networkidle" }); await p.waitForSelector("text=Add your shares");
check("no quantity, price or date fields", (await p.getByText(/Quantity|Average buy price|Bought on/).count()) === 0);
await p.locator(".pf-one input").fill("RELIANCE"); await p.locator(".pf-one .btn").click(); await p.waitForTimeout(400);
await p.locator(".pf-bulk textarea").fill("Bharti Airtel Ltd\nHDFC Bank\nsymbol\nZZNOTREAL, 12\n500325");   // a name, a name without 'Ltd', a header-like line, junk, a BSE code
await p.getByRole("button", { name: "Add these" }).click(); await p.waitForTimeout(600);
const rows = await p.locator("table.hold tbody tr td:first-child b").allInnerTexts();
check("ticker, company names and a BSE code are all recognised", ["RELIANCE", "BHARTIARTL"].every((s) => rows.includes(s)), rows.join(","));
check("a BSE code that is already added is not added twice", rows.filter((s) => s === "RELIANCE").length === 1);
check("unknown names are listed, not silently dropped", /ZZNOTREAL/.test(await p.locator(".pf-miss").innerText().catch(() => "")));
const head = await p.locator("table.hold thead th").allInnerTexts(); check("score and pillar columns", ["finlit score", "quality", "growth", "balance", "technical"].every((h) => head.some((x) => x.toLowerCase().includes(h))), head.join("|"));
const kpi = await p.locator(".pf-k b").first().innerText(); check("portfolio score shown", /^\d+$/.test(kpi.trim()), kpi);
fs.writeFileSync("/tmp/claude-0/pf.csv", "Symbol,Qty,Price\nTCS,10,3900\nINFY,5,1500\n");
await p.locator('input[type=file]').setInputFiles("/tmp/claude-0/pf.csv"); await p.waitForTimeout(600);
const after = await p.locator("table.hold tbody tr td:first-child b").allInnerTexts(); check("CSV: names read, quantities and prices ignored", ["TCS", "INFY"].every((s) => after.includes(s)), after.join(","));
await p.locator("table.hold tbody tr").first().getByRole("button", { name: /Remove/ }).click(); await p.waitForTimeout(300);
check("a share can be removed", (await p.locator("table.hold tbody tr").count()) === after.length - 1);
const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check("no sideways scroll on the page", ov <= 1, ov + "px");
check("no page errors", p.errs.length === 0, p.errs.join(" | "));
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
