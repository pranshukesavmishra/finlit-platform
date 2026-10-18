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
// in-app navigation (clicking links, no reload) must show the new page, not keep the old one (compared by page heading)
const h1 = async () => (await p.locator("h1").first().innerText().catch(() => "")).trim();
await go("/");
for (const [name, path] of [["Pricing", "/plans"], ["Services", "/services"]]) {
  const before = await h1();
  await p.getByRole("link", { name, exact: true }).first().click(); await p.waitForTimeout(900);
  const after = await h1();
  check(`clicking ${name} opens ${path} (heading changes)`, p.url().endsWith(path) && after !== "" && after !== before, `"${before.slice(0, 25)}" -> "${after.slice(0, 25)}"`);
}
for (const [menu, item, path] of [["Company", "About FinLit", "/about"], ["Resources", "Insights & blog", "/blog"], ["Products", "Score screener", "/score-screener"]]) {
  await go("/"); const before = await h1();
  await p.getByRole("button", { name: menu, exact: true }).first().click(); await p.getByRole("menuitem", { name: new RegExp("^" + item) }).first().click(); await p.waitForTimeout(900);
  const after = await h1();
  check(`menu ${menu} > ${item} opens ${path} (heading changes)`, p.url().includes(path) && after !== "" && after !== before, `"${before.slice(0, 25)}" -> "${after.slice(0, 25)}"`);
}
// the sign-in / create-account tabs (an earlier render loop froze them for visitors)
await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
await p.getByRole("tab", { name: "Sign in" }).click(); await p.waitForTimeout(400);
check("sign-in page: the Sign in tab switches the heading to 'Welcome back'", (await p.getByRole("heading", { name: "Welcome back" }).count()) === 1);
await p.getByRole("tab", { name: "Create account" }).click(); await p.waitForTimeout(400);
check("sign-in page: the Create account tab switches back", (await p.getByRole("heading", { name: /Create your free account/ }).count()) === 1);
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
// one sign-in for administrators: /login (with the authenticator code) opens the blog/CMS tools, no second password
if (process.env.ADMIN_EMAIL && process.env.ADMIN_PASSWORD) {
  const { createHmac } = await import("node:crypto");
  const b32 = (str) => { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const ch of str.replace(/=+$/, "")) bits += A.indexOf(ch).toString(2).padStart(5, "0"); const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(out); };
  const totp = (secret) => { const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000))); const h = createHmac("sha1", b32(secret)).update(b).digest(); const o = h[h.length - 1] & 15; return String(((h.readUInt32BE(o) & 0x7fffffff) % 1000000)).padStart(6, "0"); };
  const c4 = await browser.newContext(); const p4 = await c4.newPage();
  await p4.goto(base + "/login", { waitUntil: "networkidle" });
  await p4.getByLabel("Email address").fill(process.env.ADMIN_EMAIL); await p4.getByLabel("Password", { exact: true }).fill(process.env.ADMIN_PASSWORD);
  await p4.getByRole("button", { name: "Sign in", exact: true }).last().click();
  await p4.waitForURL(/\/(dashboard|account\/security)/, { timeout: 15000 }).catch(() => {});
  const api4 = async (path, method = "GET", body) => p4.evaluate(async ([u, m, b]) => { const csrf = (await (await fetch("/api/auth/me", { credentials: "same-origin" })).json()).csrf; const r = await fetch(u, { method: m, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf || "" }, body: b ? JSON.stringify(b) : undefined }); let j = null; try { j = await r.json(); } catch {} return { status: r.status, body: j }; }, [path, method, body]);
  const before = await api4("/api/me/cms-token", "POST");
  check("admin: the CMS token is refused until the authenticator app is set up", before.status === 403 || before.status === 401, String(before.status));
  const setup = await api4("/api/me/mfa/setup", "POST");
  const en = await api4("/api/me/mfa/enable", "POST", { code: totp(setup.body.secret) });
  check("admin: authenticator app set up once (Account > Security)", en.status === 200, String(en.status));
  const tok = await api4("/api/me/cms-token", "POST");
  check("admin: after that, /api/me/cms-token issues a CMS token (CMS_JWT_SECRET is set)", tok.status === 200 && !!tok.body.token, tok.status === 503 ? "cms_not_configured: CMS_JWT_SECRET is missing" : String(tok.status));
  if (tok.status === 200) {
    const items = await p4.evaluate(async (t) => (await fetch("/api/content/admin/items", { headers: { Authorization: "Bearer " + t } })).status, tok.body.token);
    check("admin: the site backend accepts that token (same secret)", items === 200, String(items));
  }
  await p4.goto(base + "/admin", { waitUntil: "networkidle" }); await p4.waitForTimeout(1500);
  check("admin: /admin opens the content tools with no second password", /\/admin$/.test(p4.url()) && (await p4.getByText(/Content|New|Articles|Publish/i).count()) > 0, p4.url());
  await p4.goto(base + "/admin/login", { waitUntil: "networkidle" }); await p4.waitForTimeout(1200);
  check("admin: /admin/login is no longer a password form", (await p4.locator("input[type=password]").count()) === 0, `${p4.url()} · ${await p4.locator("input[type=password]").count()} password fields`);
  await c4.close();
}
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
for (const [path, needle] of [["/score-screener", ""], ["/blog", ""], ["/portfolio", ""], ["/contact", ""], ["/ipo", ""], ["/results", ""], ["/documents", ""]]) {
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
