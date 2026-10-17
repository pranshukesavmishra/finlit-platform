// Functional checks for Screener, Compare, Watchlist, Glossary and the quarter/trends sections.
//   node e2e/tools.mjs http://127.0.0.1:4180/finlit-platform     (a demo build: VITE_DEMO=1)
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:4180/finlit-platform").replace(/\/$/, "");
const out = []; const check = (n, ok, d = "") => { out.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const mk = async (plan) => { const c = await browser.newContext({ viewport: { width: 1366, height: 900 } }); await c.addInitScript((p) => { localStorage.setItem("finlit-plan", p); localStorage.setItem("finlit-theme", "light"); }, plan); const p = await c.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e))); return p; };

const openGroup = async (p, re) => { const b = p.locator(".scr-gh", { hasText: re }).first(); if ((await b.getAttribute("aria-expanded")) !== "true") await b.click(); };
// ---- Screener (Gold)
let p = await mk("gold");
await p.goto(base + "/screener", { waitUntil: "networkidle" });
const total = Number(await p.locator(".scr-count").innerText());
check("screener: lists companies", total >= 20, String(total));
await openGroup(p, /Valuation/);
await p.getByLabel("P/E ratio maximum").fill("20");
await p.waitForTimeout(300);
const after = Number(await p.locator(".scr-count").innerText());
check("screener: P/E ≤ 20 narrows the list", after > 0 && after < total, `${total} → ${after}`);
const pes = await p.$$eval(".scr-t tbody tr td:nth-child(6)", (t) => t.map((x) => parseFloat(x.textContent)));
check("screener: every row satisfies the filter", pes.length > 0 && pes.every((x) => x <= 20.05 || Number.isNaN(x)), pes.slice(0, 5).join(","));
check("screener: filter chip shown", (await p.locator(".fchip").count()) === 1);
await p.locator(".fchip").click(); check("screener: chip removes filter", Number(await p.locator(".scr-count").innerText()) === total);
await openGroup(p, /FinLit model/);
check("screener: Gold sees model filters", (await p.getByLabel("FinLit score minimum").count()) === 1);
await p.getByLabel("FinLit score minimum").fill("78"); await p.waitForTimeout(300);
const strong = await p.$$eval(".scr-t tbody tr .vd", (t) => t.map((x) => x.className));
check("screener: model filter (score ≥ 78) returns only Strong", strong.length > 0 && strong.every((c) => c.includes("strong")), `${strong.length} rows`);
check("screener: no page errors (gold)", p.errs.length === 0, p.errs.join("|"));
// ---- Screener (Basic): model filters locked
p = await mk("basic");
await p.goto(base + "/screener", { waitUntil: "networkidle" });
await openGroup(p, /FinLit model/);
check("screener: Basic sees the Gold lock, not model inputs", (await p.getByLabel("FinLit score minimum").count()) === 0 && (await p.getByText("Unlock with Gold").count()) >= 1);
check("screener: model columns hidden for Basic", (await p.locator(".scr-t th", { hasText: "Score" }).count()) === 0);

// ---- Compare
p = await mk("bronze");
await p.goto(base + "/compare", { waitUntil: "networkidle" });
check("compare: two companies picked by default", (await p.locator(".cc").count()) === 2);
check("compare: Bronze limited to 2 (Gold prompt shown)", (await p.getByText(/Compare up to 4 · Gold/).count()) === 1);
await p.getByRole("tab", { name: "Valuation", exact: true }).click(); await p.waitForTimeout(400);
check("compare: valuation shows strips and percentile dots", (await p.locator(".strip").count()) >= 3 && (await p.locator(".mt-c .dt").count()) >= 6);
const rowsBefore = await p.locator(".mt-r").count();
await p.getByRole("button", { name: "P/B", exact: true }).click(); await p.waitForTimeout(250);
check("compare: toggling a measure removes its row", (await p.locator(".mt-r").count()) === rowsBefore - 1);
await p.getByRole("tab", { name: "Spider", exact: true }).click(); await p.waitForTimeout(400);
check("compare: spider radar draws both companies", (await p.locator(".radar .rs").count()) === 2);
await p.getByRole("tab", { name: /Build your own/ }).click(); await p.waitForTimeout(300);
await p.getByRole("button", { name: "Div. yield" }).click(); await p.waitForTimeout(200);
check("compare: build-your-own adds a measure", (await p.locator(".mt-r").count()) >= 5);
p = await mk("basic");
await p.goto(base + "/compare", { waitUntil: "networkidle" });
await p.getByRole("tab", { name: /Quality & Risk/ }).click(); await p.waitForTimeout(300);
check("compare: Basic sees the Bronze lock on model tabs", (await p.getByText("Unlock Quality & Risk").count()) >= 1);
await p.getByRole("tab", { name: "Fundamentals", exact: true }).click(); await p.waitForTimeout(300);
check("compare: Basic can use Fundamentals", (await p.locator(".mt-r").count()) >= 4);

// ---- Watchlist (Gold)
p = await mk("gold");
await p.goto(base + "/watchlist", { waitUntil: "networkidle" }); await p.waitForTimeout(600);
const cards = await p.locator(".wc").count();
check("watchlist: demo list is populated", cards >= 5, String(cards));
check("watchlist: bucketed by industry", (await p.locator(".wl-gh").count()) >= 3);
await p.getByLabel("Bucket by").selectOption("band"); await p.waitForTimeout(300);
check("watchlist: Gold can bucket by FinLit band", (await p.locator(".wl-gh h3", { hasText: /Healthy|Mixed|Strong|Watch/ }).count()) >= 1);
await p.locator(".wc input[type=checkbox]").nth(0).check(); await p.locator(".wc input[type=checkbox]").nth(1).check();
check("watchlist: dock offers comparison", (await p.getByRole("button", { name: "Compare selected" }).count()) === 1);
await p.getByRole("button", { name: "Compare selected" }).click(); await p.waitForURL(/compare\?c=/); await p.waitForSelector(".cc");
check("watchlist: Compare selected opens /compare with both", (await p.locator(".cc").count()) === 2);
await p.goto(base + "/watchlist", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
await p.getByLabel(/target price/).first().fill("5000"); await p.getByLabel(/ note/).first().fill("test note");
await p.reload({ waitUntil: "networkidle" }); await p.waitForTimeout(500);
check("watchlist: targets and notes persist", (await p.getByLabel(/ note/).first().inputValue()) === "test note");
await p.getByRole("button", { name: /\+ New list/ }).click(); await p.getByLabel("New list name").fill("Dividend ideas"); await p.keyboard.press("Enter"); await p.waitForTimeout(300);
check("watchlist: create a named list", (await p.getByRole("button", { name: /Dividend ideas/ }).count()) === 1);
check("watchlist: no page errors", p.errs.length === 0, p.errs.join("|"));

// ---- Glossary
p = await mk("basic");
await p.goto(base + "/glossary", { waitUntil: "networkidle" });
check("glossary: A shows its terms", (await p.locator(".gl-card").count()) === 4);
await p.getByLabel("Search the glossary").fill("CAGR"); await p.waitForTimeout(250);
check("glossary: search finds CAGR with its formula", (await p.locator(".gl-card h3", { hasText: "CAGR" }).count()) === 1 && (await p.locator(".gl-f code").first().innerText()).includes("Ending Value"));
await p.getByLabel("Search the glossary").fill(""); await p.getByLabel("Filter by category").selectOption("Dividends"); await p.waitForTimeout(250);
const gt = await p.locator(".gl-card h3").allInnerTexts();
check("glossary: category filter + letters", gt.length === 2 && gt.every((t) => /Dividend|Ex-Dividend/.test(t)), gt.join(","));

// ---- Stock page: new sections
p = await mk("gold");
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
check("stock: latest quarter section with four tiles", (await p.locator("#quarter").count()) === 1 && (await p.locator(".qt").count()) === 4);
check("stock: quarter table has year-ago column", (await p.locator(".qtt th", { hasText: "year ago" }).count()) === 1);
check("stock: trends grid has cards", (await p.locator(".tr-c").count()) >= 6);
await p.getByRole("button", { name: "Annual", exact: true }).click(); await p.waitForTimeout(300);
await p.getByRole("tab", { name: "Dividends" }).click(); await p.waitForTimeout(300);
check("stock: dividend trend cards", (await p.locator(".tr-c").count()) >= 2);
check("stock: no page errors", p.errs.length === 0, p.errs.join("|"));
await browser.close();
console.log(`\n${out.filter(Boolean).length}/${out.length} passed`);
process.exit(out.every(Boolean) ? 0 : 1);
