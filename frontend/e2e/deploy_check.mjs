// End-to-end check of a deployed site (website + API on one address) using the demo accounts.
//   DEMO_PASSWORD=... node e2e/deploy_check.mjs https://your-site.onrender.com
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:8010").replace(/\/$/, "");
const PW = process.env.DEMO_PASSWORD;
if (!PW) { console.error("Set DEMO_PASSWORD (the demo accounts' password)"); process.exit(2); }
let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const p = await ctx.newPage();
const errs = [], bad = [];
p.on("pageerror", (e) => errs.push(String(e).slice(0, 140)));
p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 140)); });
p.on("response", (r) => { const u = new URL(r.url()); if (r.status() >= 400 && u.pathname.startsWith("/api/") && !/market-ticker|chat|NOPE/.test(u.pathname)) bad.push(`${r.status()} ${u.pathname}`); });
const text = async () => (await p.locator("main").innerText()).replace(/\s+/g, " ");
const go = async (path, wait = 900) => { await p.goto(base + path, { waitUntil: "networkidle" }); await p.waitForTimeout(wait); };

const h = await (await ctx.request.get(base + "/api/health")).json().catch(() => ({}));
check("API health (database + cache)", h.ok === true, JSON.stringify(h));
const nf = await ctx.request.get(base + "/api/nonexistent");
check("unknown /api path is a JSON 404, not the website", nf.status() === 404 && (nf.headers()["content-type"] || "").includes("json"));
await go("/");
check("home page loads", (await p.locator("h1").count()) >= 1 && (await text()).length > 300);
// in-app navigation (clicking links, no reload) must show the new page, not keep the old one
await go("/");
for (const [name, path] of [["Plans", "/plans"], ["Services", "/services"], ["About", "/about"], ["Blog", "/blog"]]) {
  await p.getByRole("link", { name, exact: true }).first().click(); await p.waitForTimeout(800);
  check(`clicking ${name} opens ${path} (not the previous page)`, p.url().endsWith(path) && (await p.getByText("Invest with clarity").count()) === 0);
}
await p.getByRole("link", { name: "Sign in", exact: true }).first().click(); await p.waitForTimeout(600);
await p.getByRole("tab", { name: "Create account" }).click(); await p.waitForTimeout(400);
check("sign-in page: the Create account tab switches", (await p.getByRole("tab", { name: "Create account" }).getAttribute("aria-selected")) === "true");
await go("/stocks/TCS", 1500);
check("deep link works on refresh (/stocks/TCS)", /TCS|Tata Consultancy/i.test(await text()));
const u = await (await ctx.request.get(base + "/api/screener/universe")).json();
check("universe has real companies", u.rows.length >= Number(process.env.MIN_COMPANIES || 20) && !u.rows.some((r) => String(r.symbol).startsWith("SMP-")), `${u.rows.length} companies`);

// sign in as the Gold demo member through the real form
await go("/login");
await p.getByLabel("Email address").fill("demo-gold@finlit-demo.com"); await p.getByLabel("Password", { exact: true }).fill(PW);
await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
await p.waitForURL(/\/dashboard/, { timeout: 15000 }).catch(() => {});
check("sign in works and opens the dashboard", /\/dashboard/.test(p.url()), p.url());
check("signed-in member is on the Gold plan", (await p.locator(".tier, .chip").allInnerTexts()).join(" ").toLowerCase().includes("gold"));
await p.waitForTimeout(1200);
check("dashboard shows widgets", (await p.locator(".dw").count()) >= 3);
await go("/screener");
check("screener lists companies", (await p.locator("tbody tr").count()) >= Math.min(10, Number(process.env.MIN_COMPANIES || 20)), String(await p.locator("tbody tr").count()));
await go("/stocks/RELIANCE", 1500);
const st = await (await ctx.request.get(base + "/api/stocks/TCS")).json();
check("Gold sees the model score on a non-showcase company", st.score && st.score.overall != null, String(st.score && st.score.overall));
await p.locator("button", { hasText: /Watchlist|Add to watchlist/i }).first().click().catch(() => {}); await p.waitForTimeout(1200);
await go("/watchlist");
check("watchlist keeps the added stock", (await text()).includes("RELIANCE"));
await go("/compare?c=RELIANCE,TCS", 1200);
check("compare shows both companies", /RELIANCE/.test(await text()) && /TCS/.test(await text()));
await go("/ipo"); check("IPO page loads", (await text()).length > 100);
await go("/news"); check("news page loads", (await text()).length > 100);
// a brand-new visitor can create an account and sign in (needs AUTO_VERIFY_EMAIL=1 on the server: SIGNUP_TEST=1)
if (process.env.SIGNUP_TEST === "1") {
  const c3 = await browser.newContext(); const p3 = await c3.newPage();
  const email = `visitor-${Date.now().toString(36)}@example.com`, pw = "a-long-unusual-phrase-42";
  await p3.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
  await p3.getByLabel(/^Name/).fill("New Visitor"); await p3.getByLabel("Email address").fill(email); await p3.getByLabel("Password", { exact: true }).fill(pw);
  await p3.getByLabel(/I agree to the/).check(); await p3.getByRole("button", { name: "Create account" }).click();
  check("sign-up: new account is ready at once", await p3.getByText("Your account is ready").waitFor({ timeout: 10000 }).then(() => true, () => false));
  await p3.getByRole("button", { name: "Sign in", exact: true }).first().click();
  await p3.getByLabel("Email address").fill(email); await p3.getByLabel("Password", { exact: true }).fill(pw);
  await p3.getByRole("button", { name: "Sign in", exact: true }).last().click();
  await p3.waitForURL(/\/dashboard/, { timeout: 15000 }).catch(() => {});
  check("sign-up: new member signs in and reaches the dashboard", /\/dashboard/.test(p3.url()), p3.url());
  const meNew = await (await c3.request.get(base + "/api/stocks/TCS")).json();
  check("sign-up: a new member starts on Basic (no model score)", meNew.score && meNew.score.overall == null);
}
// the public pages the company site promises
for (const [path, needle] of [["/blog", ""], ["/portfolio", ""], ["/contact", ""], ["/ipo", ""], ["/results", ""], ["/documents", ""]]) {
  await go(path, 600); check(`public page ${path} renders`, (await text()).length > 100);
}
// the Basic demo member must NOT see scores
const c2 = await browser.newContext(); const p2 = await c2.newPage();
await p2.goto(base + "/login", { waitUntil: "networkidle" });
await p2.getByLabel("Email address").fill("demo-basic@finlit-demo.com"); await p2.getByLabel("Password", { exact: true }).fill(PW);
await p2.getByRole("button", { name: "Sign in", exact: true }).last().click(); await p2.waitForURL(/\/dashboard/, { timeout: 15000 }).catch(() => {});
const sb = await (await c2.request.get(base + "/api/stocks/TCS")).json();
check("Basic member does not get the model score (plans enforced on the server)", sb.score && sb.score.overall == null);
check("no page errors", errs.length === 0, errs.slice(0, 3).join(" | "));
check("no failing API calls", bad.length === 0, [...new Set(bad)].join(", "));
await browser.close();
console.log(failed ? `${failed} CHECK(S) FAILED` : "ALL CHECKS PASSED");
process.exit(failed ? 1 : 0);
