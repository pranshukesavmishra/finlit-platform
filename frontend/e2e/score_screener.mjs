// Score screener: size / sector / score-range filters on the live universe, plan rules, URL persistence, compare.
//   DEMO_PASSWORD=... node e2e/score_screener.mjs http://127.0.0.1:8010 [screenshot-dir]
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:8010").replace(/\/$/, ""), shots = process.argv[3], PW = process.env.DEMO_PASSWORD;
if (!PW) { console.error("Set DEMO_PASSWORD"); process.exit(2); }
let failed = 0; const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const errs = [];
async function ctxFor(email) {
  const c = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const p = await c.newPage();
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 140)));
  if (email) {
    await p.goto(base + "/login", { waitUntil: "networkidle" });
    await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
    await p.getByRole("button", { name: "Sign in", exact: true }).last().click(); await p.waitForURL(/\/dashboard/, { timeout: 15000 });
  }
  return p;
}
const rowsOf = (p) => p.locator(".ss-t tbody tr:has(td.stick)");
const scoreCol = async (p, col) => (await p.locator(`.ss-t tbody tr td:nth-child(${col}) .ssp`).allInnerTexts()).map(Number).filter((n) => !Number.isNaN(n));

// ---- Gold member
let p = await ctxFor("demo-gold@finlit-demo.com");
await p.goto(base + "/score-screener", { waitUntil: "networkidle" }); await p.waitForTimeout(1200);
check("gold: page loads with a table of real companies", (await rowsOf(p).count()) >= 5, `${await rowsOf(p).count()} rows`);
const found = Number((await p.locator(".ss-stat b").first().innerText()).replace(/,/g, ""));
check("gold: 'Stocks found' counts the whole universe at first", found >= 20, String(found));
if (shots) await p.screenshot({ path: `${shots}/score-screener.png` });
await p.getByRole("button", { name: /^Large cap/ }).click(); await p.getByRole("button", { name: "Apply filters" }).click(); await p.waitForTimeout(600);
const large = Number((await p.locator(".ss-stat b").first().innerText()).replace(/,/g, ""));
check("gold: Large cap filter applies and shows a chip", large > 0 && large <= 100 && large <= found && (await p.locator(".fchip", { hasText: "Large cap" }).count()) === 1, `${large} of ${found}`);
check("gold: filters are kept in the address (shareable)", /cap=Large/.test(p.url()), p.url());
await p.getByRole("group", { name: "Fundamental score" }).getByText(/78 and above/).click(); await p.getByRole("button", { name: "Apply filters" }).click(); await p.waitForTimeout(600);
const f = await scoreCol(p, 6);
check("gold: Fundamental 78+ shows only scores of 78 or more", f.length > 0 ? f.every((n) => n >= 78) : (await p.locator(".empty").count()) === 1, JSON.stringify(f.slice(0, 6)));
await p.reload({ waitUntil: "networkidle" }); await p.waitForTimeout(900);
check("gold: filters survive a reload", (await p.locator(".fchip").count()) === 2, String(await p.locator(".fchip").count()));
await p.getByRole("button", { name: "Clear all" }).first().click(); await p.waitForTimeout(500);
check("gold: Clear all removes every filter", (await p.locator(".fchip").count()) === 0 && Number((await p.locator(".ss-stat b").first().innerText()).replace(/,/g, "")) === found);
await p.getByRole("button", { name: "Sort by Overall" }).click(); await p.getByRole("button", { name: "Sort by Overall" }).click(); await p.waitForTimeout(300);
const o = await scoreCol(p, 8);
check("gold: sorting by Overall (second click = ascending) orders the table", o.length > 2 && o.every((n, i) => i === 0 || o[i - 1] <= n), JSON.stringify(o.slice(0, 5)));
await p.getByLabel("Rows per page").selectOption("5"); await p.waitForTimeout(300);
check("gold: rows per page = 5", (await rowsOf(p).count()) === 5);
await p.getByRole("button", { name: "Next page" }).click(); await p.waitForTimeout(300);
check("gold: next page shows page 2", (await p.getByText(/Page 2 of/).count()) === 1);
await p.locator(".ss-t tbody tr input[type=checkbox]").nth(0).check(); await p.locator(".ss-t tbody tr input[type=checkbox]").nth(1).check();
await p.getByRole("button", { name: /^Compare 2 companies/ }).click(); await p.waitForURL(/\/compare\?c=/, { timeout: 8000 }).catch(() => {});
check("gold: two selected companies open in Compare", /\/compare\?c=[^,]+,[^,]+/.test(p.url()), p.url());
await p.goto(base + "/score-screener", { waitUntil: "networkidle" }); await p.waitForTimeout(800);
await p.getByRole("button", { name: /How scores work/ }).click();
check("gold: 'How scores work' explains the scores", (await p.getByText(/average of four business pillars/).count()) === 1);
await p.getByRole("button", { name: /^Add .* to watchlist/ }).first().click(); await p.waitForTimeout(500);
check("gold: the watchlist button works", (await p.getByRole("button", { name: /^Remove .* from watchlist/ }).count()) >= 1);
await p.close();

// ---- Basic member: size and sector work, score filters are locked
p = await ctxFor("demo-basic@finlit-demo.com");
await p.goto(base + "/score-screener", { waitUntil: "networkidle" }); await p.waitForTimeout(1200);
check("basic: table still lists companies", (await rowsOf(p).count()) >= 5);
check("basic: score filters are locked behind Silver", (await p.getByText("Score filters are part of Silver").count()) === 1 && (await p.getByRole("group", { name: "Fundamental score" }).count()) === 0);
await p.getByRole("button", { name: /^Large cap/ }).click(); await p.getByRole("button", { name: "Apply filters" }).click(); await p.waitForTimeout(500);
check("basic: the size filter still works", (await p.locator(".fchip", { hasText: "Large cap" }).count()) === 1);
const basicScores = await p.locator(".ss-t tbody td .ssp.hi, .ss-t tbody td .ssp.mid, .ss-t tbody td .ssp.lo").count();
check("basic: the server sends no scores (except the free example company)", basicScores <= 3, String(basicScores));
await p.close();

// ---- Visitor
p = await ctxFor(null);
await p.goto(base + "/score-screener", { waitUntil: "networkidle" }); await p.waitForTimeout(1200);
check("visitor: page is open to everyone and lists companies", (await rowsOf(p).count()) >= 5);
check("visitor: no page errors", errs.length === 0, errs.slice(0, 2).join(" | "));
await browser.close();
console.log(failed ? `${failed} CHECK(S) FAILED` : "ALL CHECKS PASSED"); process.exit(failed ? 1 : 0);
