// Checks the screener, compare, watchlist and dashboard against real (live-loaded) companies.
//   LIVE_DATA=1 dev/run_stack.sh      (after: python -m finlit.worker ingest-all --limit 200)
//   node e2e/live_data.mjs http://127.0.0.1:4173 [screenshot-dir]
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";

const base = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const shots = process.argv[3];
const DB = process.env.DATABASE_URL || "postgresql://finlit:finlit@localhost:5432/finlit_dev";
const REDIS = process.env.REDIS_URL || "redis://localhost:6379/14";
const PW = "a-long-unusual-phrase-42";
const email = `live-${Date.now().toString(36)}@example.com`;
let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const sql = (q) => execFileSync("psql", [DB, "-At", "-c", q], { encoding: "utf8" }).trim();
try { execFileSync("redis-cli", ["-u", REDIS, "flushdb"]); } catch {}

const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const c = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const p = await c.newPage();
const errs = [];
p.on("pageerror", (e) => errs.push(String(e)));
p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
const bad = [];
p.on("response", (r) => { if (r.status() >= 400 && r.url().includes("/api/")) bad.push(`${r.status()} ${new URL(r.url()).pathname}`); });
const shot = async (n) => { if (shots) await p.screenshot({ path: `${shots}/${n}.png`, fullPage: false }); };

// sign up, confirm by mail link, sign in, then give the member Gold directly in the database
await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
await p.getByLabel(/^Name/).fill("Live Check"); await p.getByLabel("Email address").fill(email);
await p.getByLabel("Password", { exact: true }).fill(PW); await p.getByLabel(/I agree to the/).check();
await p.getByRole("button", { name: "Create account" }).click();
await p.getByText("Check your email").waitFor();
const link = sql(`SELECT body FROM outbox WHERE to_email = '${email}' ORDER BY id DESC LIMIT 1`).match(/http[^\s]*verify-email\?token=[\w-]+/)[0];
await p.goto(link.replace(/^https?:\/\/[^/]+/, base), { waitUntil: "networkidle" });
sql(`UPDATE users SET plan = 'gold' WHERE email = '${email}'`);
await p.goto(base + "/login", { waitUntil: "networkidle" });
await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
await p.waitForURL(/\/dashboard/);

const SYMS = ["RELIANCE", "TCS", "INFY"];
const real = sql("SELECT string_agg(symbol, ',') FROM (SELECT symbol FROM scores WHERE overall IS NOT NULL AND symbol NOT LIKE 'SMP-%' ORDER BY market_cap DESC NULLS LAST LIMIT 3) t").split(",");
const pick = real.length >= 2 ? real : SYMS;
const text = async () => (await p.locator("main").innerText()).replace(/\s+/g, " ");

// screener
await p.goto(base + "/screener", { waitUntil: "networkidle" }); await p.waitForTimeout(800);
let t = await text(); await shot("screener");
check("screener: shows real companies", pick.every((s) => t.includes(s)) || t.includes("Reliance"), pick.join(","));
check("screener: no fictional SMP- companies or sample banner", !/SMP-|Sample data/.test(t));
check("screener: rows rendered", (await p.locator("tbody tr").count()) >= 20, String(await p.locator("tbody tr").count()));

// compare
await p.goto(base + `/compare?c=${pick.slice(0, 2).join(",")}`, { waitUntil: "networkidle" }); await p.waitForTimeout(800);
t = await text(); await shot("compare");
check("compare: both companies shown with scores", pick.slice(0, 2).every((s) => t.includes(s)) && /\b\d{2}\b/.test(t));
check("compare: no sample banner", !/Sample data/.test(t));

// watchlist: add through the account API with the page's own CSRF, then view
const st = await p.evaluate(async () => (await fetch("/api/me/state", { credentials: "same-origin" })).json());
check("watchlist: account state loads", !!st);
await p.goto(base + `/stocks/${pick[0]}`, { waitUntil: "networkidle" });
await p.locator("button", { hasText: /Watchlist|Add to watchlist/i }).first().click(); await p.waitForTimeout(1200);
await p.goto(base + "/watchlist", { waitUntil: "networkidle" }); await p.waitForTimeout(800);
t = await text(); await shot("watchlist");
check("watchlist: shows the added real company", t.includes(pick[0]), pick[0]);
check("watchlist: no sample banner", !/Sample data/.test(t));

// dashboard
await p.goto(base + "/dashboard", { waitUntil: "networkidle" }); await p.waitForTimeout(1500);
t = await text(); await shot("dashboard");
check("dashboard: renders widgets", (await p.locator(".dw").count()) >= 3, String(await p.locator(".dw").count()));
check("dashboard: no sample companies", !/SMP-|Sample data/.test(t));

check("no page errors", errs.length === 0, errs.slice(0, 3).join(" | "));
const failedApi = [...new Set(bad)];
check("no failing API calls", failedApi.length === 0, failedApi.join(", "));
await browser.close();
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
