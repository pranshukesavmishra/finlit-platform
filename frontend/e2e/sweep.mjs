// The market ticker needs an Upstox token on the site backend, so it is not counted.
// Opens every page as a visitor and as a Gold member; reports page errors, failing API calls and empty pages.
//   node e2e/sweep.mjs http://127.0.0.1:4173
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
const base = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const DB = process.env.DATABASE_URL || "postgresql://finlit:finlit@localhost:5432/finlit_dev";
const sql = (q) => execFileSync("psql", [DB, "-At", "-c", q], { encoding: "utf8" }).trim();
try { execFileSync("redis-cli", ["-u", process.env.REDIS_URL || "redis://localhost:6379/14", "flushdb"]); } catch {}
const PAGES = ["/", "/research", "/screener", "/score-screener", "/compare", "/ipo", "/results", "/news", "/documents", "/glossary", "/plans", "/services", "/about", "/why-we-exist", "/contact", "/portfolio", "/blog", "/legal/terms", "/legal/privacy", "/login", "/forgot-password", "/stocks/RELIANCE", "/stocks/TCS", "/stocks/5PAISA", "/stocks/NOPE123", "/nonexistent",
  "/dashboard", "/watchlist", "/account", "/account/security", "/account/plan", "/account/appearance"];
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
let failed = 0;
async function run(label, ctx, pages) {
  const p = await ctx.newPage();
  let errs = [], bad = [];
  p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 120)); });
  p.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) bad.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  for (const path of pages) {
    errs = []; bad = [];
    await p.goto(base + path, { waitUntil: "networkidle" }).catch(() => {});
    await p.waitForTimeout(500);
    const len = (await p.locator("main, #root").first().innerText().catch(() => "")).trim().length;
    const notes = [...new Set([...errs, ...bad.filter((b) => !/market-ticker|stocks\/NOPE123/.test(b))])];
    const ok = len > 80 && notes.length === 0;
    if (!ok) failed++;
    console.log(`${ok ? "ok  " : "FAIL"} ${label} ${path}${len <= 80 ? "  (blank page)" : ""}${notes.length ? "  " + notes.join(" | ") : ""}`);
  }
}
await run("visitor", await browser.newContext({ viewport: { width: 1366, height: 900 } }), PAGES.filter((x) => !/dashboard|watchlist|account/.test(x)));
// Gold member: the demo account (DEMO_PASSWORD), or a fresh sign-up when the server mails confirmation links (outbox in development)
const c = await browser.newContext({ viewport: { width: 1366, height: 900 } }); const p = await c.newPage();
if (process.env.DEMO_PASSWORD) {
  await p.goto(base + "/login", { waitUntil: "networkidle" });
  await p.getByLabel("Email address").fill("demo-gold@finlit-demo.com"); await p.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD);
} else {
  const email = `sweep-${Date.now().toString(36)}@example.com`, PW = "a-long-unusual-phrase-42";
  await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
  await p.getByLabel(/^Name/).fill("Sweep"); await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW); await p.getByLabel(/I agree to the/).check();
  await p.getByRole("button", { name: "Create account" }).click(); await p.getByText("Check your email").waitFor();
  const link = sql(`SELECT body FROM outbox WHERE to_email = '${email}' ORDER BY id DESC LIMIT 1`).match(/http[^\s]*verify-email\?token=[\w-]+/)[0];
  await p.goto(link.replace(/^https?:\/\/[^/]+/, base), { waitUntil: "networkidle" });
  sql(`UPDATE users SET plan = 'gold' WHERE email = '${email}'`);
  await p.goto(base + "/login", { waitUntil: "networkidle" });
  await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
}
await p.getByRole("button", { name: "Sign in", exact: true }).last().click(); await p.waitForURL(/\/dashboard/);
await p.close();
await run("gold   ", c, PAGES.filter((x) => /stocks|dashboard|watchlist|account|screener|compare|ipo|results|news|documents/.test(x)));
await browser.close();
console.log(failed ? `${failed} page(s) with problems` : "ALL PAGES CLEAN");
process.exit(failed ? 1 : 0);
