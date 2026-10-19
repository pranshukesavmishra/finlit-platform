// End-to-end checks of the real site against the real stack (dev/run_stack.sh): accounts, plans, palettes, dashboard, admin.
//   SHOWCASE_SYMBOLS=NONE dev/run_stack.sh      (so RELIANCE is trimmed to each plan like every other company)
//   node e2e/accounts.mjs http://127.0.0.1:4173
import { chromium } from "playwright";
import { createHmac } from "node:crypto";
import { execFileSync } from "node:child_process";

const base = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const DB = process.env.DATABASE_URL || "postgresql://finlit:finlit@localhost:5432/finlit_dev";
const REDIS = process.env.REDIS_URL || "redis://localhost:6379/14";
const PY = process.env.BACKEND_PY || "../backend/.venv/bin/python";
// Sign-in attempts are rate limited per address; start each run with clean counters (this also clears caches, which refill on demand).
try { execFileSync("redis-cli", ["-u", REDIS, "flushdb"]); } catch { console.log("note: could not reset redis counters"); }
const run = Date.now().toString(36);
const PW = "a-long-unusual-phrase-42";
let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const sql = (q) => execFileSync("psql", [DB, "-At", "-c", q], { encoding: "utf8" }).trim();
const mailLink = (email, re) => { const body = sql(`SELECT body FROM outbox WHERE to_email = '${email}' ORDER BY id DESC LIMIT 1`); const m = body.match(re); return m && m[0]; };

function b32(s) { const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"; let bits = ""; for (const c of s.replace(/=+$/, "")) bits += A.indexOf(c).toString(2).padStart(5, "0"); const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return Buffer.from(out); }
const totp = (secret, offset = 0) => { const step = Math.floor(Date.now() / 30000) + offset; const b = Buffer.alloc(8); b.writeBigUInt64BE(BigInt(step)); const h = createHmac("sha1", b32(secret)).update(b).digest(); const o = h[19] & 15; return String(((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000)).padStart(6, "0"); };

const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const ctx = async () => { const c = await browser.newContext({ viewport: { width: 1366, height: 900 } }); await c.addInitScript(() => { try { if (!localStorage.getItem("finlit-theme")) localStorage.setItem("finlit-theme", "light"); } catch {} }); return c; };
const page = async (c) => { const p = await c.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e))); p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) p.errs.push(m.text()); }); return p; };
const api = (p, path, init) => p.evaluate(async ([u, i]) => { const r = await fetch(u, { credentials: "same-origin", ...i }); let j = null; try { j = await r.json(); } catch {} return { status: r.status, body: j }; }, [path, init]);

async function signUpAndIn(p, email, name = "Asha Rao") {
  await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
  await p.getByLabel(/^Name/).fill(name); await p.getByLabel("Email address").fill(email);
  await p.getByLabel("Password", { exact: true }).fill(PW);
  await p.getByLabel(/I agree to the/).check();
  await p.getByRole("button", { name: "Create account" }).click();
  await p.getByText("Check your email").waitFor();
  const link = mailLink(email, /http[^\s]*verify-email\?token=[\w-]+/);
  await p.goto(link.replace(/^https?:\/\/[^/]+/, base), { waitUntil: "networkidle" });
  await p.getByText("Email confirmed").waitFor();
  await p.goto(base + "/login", { waitUntil: "networkidle" });
  await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
  await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
  await p.waitForURL(/\/dashboard/);
}

// ---------------------------------------------------------------- visitor
let c = await ctx(), p = await page(c);
await p.goto(base + "/", { waitUntil: "networkidle" });
check("visitor: header offers sign in and create account", (await p.getByRole("link", { name: "Create account" }).count()) === 1 && (await p.getByRole("link", { name: "Sign in", exact: true }).count()) >= 1);
check("visitor: no demo banner or plan-preview switch", (await p.locator(".demo-bar, .planseg").count()) === 0);
await p.goto(base + "/dashboard", { waitUntil: "networkidle" });
check("visitor: dashboard sends to sign in and remembers where to go back", /\/login\?next=%2Fdashboard/.test(p.url()), p.url());
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
check("visitor: stock page renders, no page errors", (await p.locator("h1").count()) >= 1 && p.errs.length === 0, p.errs.join(" | "));
const lockedCount = await p.locator(".gate.is-locked").count();
check("visitor: premium sections show lock cards", lockedCount >= 2, String(lockedCount));
const gold = await p.getByText("Unlock with Gold").first();
await gold.click();
await p.waitForURL(/\/login\?next=.*plan=gold/);
check("visitor: tapping an unlock card leads to sign in (not a fake preview)", true);
const uni = await api(p, "/api/screener/universe");
const rel = uni.body.rows.find((r) => r.symbol === "RELIANCE");
check("visitor: API withholds model scores", uni.body.rows.every((r) => r.overall == null) && rel.pe != null, `RELIANCE overall=${rel.overall}`);
check("visitor: API refuses the ranked list", (await api(p, "/api/screener/top")).status === 403);
check("visitor: admin API refused", (await api(p, "/api/admin/users")).status === 401);

// ---------------------------------------------------------------- sign-up rules
await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
await p.getByLabel("Email address").fill(`weak-${run}@example.com`); await p.getByLabel("Password", { exact: true }).fill("short1");
await p.getByLabel(/I agree to the/).check(); await p.getByRole("button", { name: "Create account" }).click();
check("sign-up: weak password explained", (await p.locator(".formerr").innerText()).includes("10"), await p.locator(".formerr").innerText());
await p.getByLabel("Password", { exact: true }).fill(PW); await p.getByLabel(/I agree to the/).uncheck(); await p.getByRole("button", { name: "Create account" }).click();
check("sign-up: terms must be accepted", /accept the Terms/.test(await p.locator(".formerr").innerText()));

// ---------------------------------------------------------------- a Basic member
const email = `asha-${run}@example.com`;
await p.goto(base + "/login?mode=signup", { waitUntil: "networkidle" });
await p.getByLabel(/^Name/).fill("Asha Rao"); await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
await p.getByLabel(/I agree to the/).check(); await p.getByRole("button", { name: "Create account" }).click(); await p.getByText("Check your email").waitFor();
await p.getByRole("button", { name: "Back to sign in" }).click();
await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill(PW);
await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
await p.locator(".formerr").waitFor();
check("sign-in: unconfirmed email is told to confirm, with a resend option", /Confirm your email/.test(await p.locator(".formerr").innerText()) && (await p.getByRole("button", { name: "Send the link again" }).count()) === 1);
await p.goto(base + "/verify-email?token=" + "x".repeat(40), { waitUntil: "networkidle" });
check("verify: a bad link says so", (await p.getByText("This link did not work").count()) === 1);
await p.goto(mailLink(email, /http[^\s]*verify-email\?token=[\w-]+/).replace(/^https?:\/\/[^/]+/, base), { waitUntil: "networkidle" });
check("verify: the real link confirms the email", (await p.getByText("Email confirmed").count()) === 1);
await p.goto(base + "/login", { waitUntil: "networkidle" });
await p.getByLabel("Email address").fill(email); await p.getByLabel("Password", { exact: true }).fill("wrong-password-123");
await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
check("sign-in: wrong password gives a generic error", /not correct/.test(await p.locator(".formerr").innerText()));
await p.getByLabel("Password", { exact: true }).fill(PW);
await p.getByRole("button", { name: "Sign in", exact: true }).last().click();
await p.waitForURL(/\/dashboard/);
check("sign-in: lands on the dashboard with a greeting", (await p.locator(".dash-h h1").innerText()).includes("Asha"));
check("header: account menu shows the Basic plan", (await p.locator(".av-btn .tier").innerText()).trim().toLowerCase() === "basic");
const cookies = await c.cookies();
const sess = cookies.find((k) => k.name === "fl_session");
check("session cookie is HttpOnly and SameSite=Lax", sess && sess.httpOnly && sess.sameSite === "Lax");
check("session token is not readable from page script", !(await p.evaluate(() => document.cookie)).includes("fl_session"));
check("dashboard: locked widgets are shown as locked", (await p.locator(".dw-lock").count()) >= 2);
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
check("basic: model score not in the page data", (await api(p, "/api/stocks/RELIANCE")).body.score.overall === null);
check("basic: stock page has no page errors with trimmed data", p.errs.length === 0, p.errs.join(" | "));
check("basic: locked sections remain behind unlock cards", (await p.locator(".gate.is-locked").count()) >= 2);
const bh = (await api(p, "/api/stocks/RELIANCE/ratios")).body; check("basic: ratio history limited to the five key ratios; valuation history withheld", Object.keys(bh.history.rows).length <= 5 && bh.valuationHistory.rows && Object.keys(bh.valuationHistory.rows).length === 0);

check("basic: price statistics withheld by the API", (await api(p, "/api/stocks/RELIANCE/stats")).body.locked === true);

// ---------------------------------------------------------------- plan request -> admin grant -> unlocked
await p.getByText("Unlock with Silver").first().click();
await p.waitForURL(/\/account\/plan\?want=silver/);
await p.getByRole("button", { name: "Request Silver" }).click();
await p.getByText("Request sent").waitFor();
check("plan: member can request a plan", true);

// admin
const adminEmail = `boss-${run}@example.com`;
execFileSync(PY, ["-m", "finlit.auth.cli", "create-admin", "--email", adminEmail], { cwd: "../backend", env: { ...process.env, DATABASE_URL: DB, REDIS_URL: REDIS, FINLIT_ADMIN_PASSWORD: PW }, encoding: "utf8" });
const ac = await ctx(), ap = await page(ac);
await ap.goto(base + "/login", { waitUntil: "networkidle" });
await ap.getByLabel("Email address").fill(adminEmail); await ap.getByLabel("Password", { exact: true }).fill(PW);
await ap.getByRole("button", { name: "Sign in", exact: true }).last().click();
await ap.waitForURL(/\/account\/security/);
check("admin: first sign-in is sent to set up two-step", await ap.getByText("Administrators sign in with two steps").first().waitFor({ timeout: 8000 }).then(() => true, () => false));
await ap.goto(base + "/console", { waitUntil: "networkidle" });
check("admin: console is closed until two-step is on", (await ap.getByText("One more step").count()) === 1);
await ap.goto(base + "/account/security", { waitUntil: "networkidle" });
await ap.getByRole("button", { name: "Set up authenticator app" }).click();
const secret = (await ap.locator(".key").innerText()).replace(/\s+/g, "");
await ap.getByLabel("Code", { exact: true }).fill(totp(secret)); await ap.getByRole("button", { name: "Turn on" }).click();
await ap.getByText("On", { exact: true }).waitFor();
await ap.goto(base + "/console", { waitUntil: "networkidle" });
check("admin: console opens after two-step", (await ap.getByText("Open requests").count()) === 1);
await ap.getByRole("tab", { name: "Data health" }).click();
check("admin: data-health panel shows universe and loaded counts", await ap.getByText("companies in the universe").waitFor({ timeout: 8000 }).then(() => true, () => false));
// calendar + news content added by an administrator shows to everyone
await ap.getByRole("tab", { name: "Calendar & news" }).click();
const soon = (n) => { const d = new Date(Date.now() + n * 86400000); return d.toISOString().slice(0, 10); };
await ap.getByLabel("Company", { exact: true }).first().fill(`Test Issue ${run} Ltd`);
await ap.getByLabel("Opens").fill(soon(2)); await ap.getByLabel("Closes").fill(soon(4)); await ap.getByLabel("Price band high (₹)").fill("120"); await ap.getByLabel("Lot size (shares)").fill("100");
await ap.getByRole("button", { name: "Add IPO" }).click();
check("admin: IPO added and listed", await ap.getByRole("cell", { name: `Test Issue ${run} Ltd` }).waitFor({ timeout: 8000 }).then(() => true, () => false));
await ap.getByRole("button", { name: "Result date" }).click();
await ap.getByLabel(/^Title/).fill(`Q2 FY27 results ${run}`); await ap.getByLabel("Company symbol").fill("TCS"); await ap.getByLabel("Results date").fill(soon(3)); await ap.getByLabel("Period").fill("Q2 FY27");
await ap.getByRole("button", { name: "Add", exact: true }).click();
check("admin: result date added", await ap.getByRole("cell", { name: `Q2 FY27 results ${run}` }).waitFor({ timeout: 8000 }).then(() => true, () => false));
const vc = await ctx(), vp = await page(vc);
await vp.goto(base + "/ipo", { waitUntil: "networkidle" });
check("visitor: IPO calendar shows the new issue with its status", (await vp.getByText(`Test Issue ${run} Ltd`).count()) >= 1 && (await vp.getByText("Upcoming").count()) >= 1);
check("visitor: IPO minimum investment is worked out (₹120 x 100)", (await vp.getByText("₹12,000").count()) >= 1);
await vp.goto(base + "/results", { waitUntil: "networkidle" });
check("visitor: results calendar lists the new date", (await vp.getByText("Q2 FY27").count()) >= 1 && (await vp.getByText("TCS").count()) >= 1);
await vp.goto(base + "/news?x=1", { waitUntil: "networkidle" });
check("visitor: news page shows exchange announcements loaded automatically", (await vp.locator(".feed-n li").count()) >= 1, String(await vp.locator(".feed-n li").count()));
await vp.goto(base + "/documents", { waitUntil: "networkidle" });
check("visitor: documents page renders", (await vp.locator("h1", { hasText: "Documents" }).count()) === 1 && vp.errs.length === 0, vp.errs.join("|"));
await vp.goto(base + "/screener", { waitUntil: "networkidle" });
check("left menu is on every product page", (await vp.locator("aside.side").count()) === 1 && (await vp.locator(".side-i", { hasText: "IPO calendar" }).count()) === 1);
await vp.locator(".side-toggle").first().click();
check("left menu can be collapsed and stays collapsed", (await vp.locator(".shell.is-collapsed").count()) === 1 && (await vp.evaluate(() => localStorage.getItem("finlit-side"))) === "1");
await ap.getByRole("tab", { name: "Plan requests" }).click();
const row = ap.locator("tr", { hasText: email });
check("admin: sees the member's plan request", (await row.count()) === 1);
await row.getByRole("button", { name: "Grant 1 year" }).click();
await ap.waitForTimeout(600);
check("admin: request leaves the queue once granted", (await ap.locator("tr", { hasText: email }).count()) === 0);
check("non-admin: console is closed", await (async () => { await p.goto(base + "/console", { waitUntil: "networkidle" }); return (await p.getByText("Administrators only").count()) === 1; })());
check("non-admin: admin API refused", (await api(p, "/api/admin/users")).status === 403);
// a second, fresh sign-in must prompt for the code
const ac2 = await ctx(), ap2 = await page(ac2);
await ap2.goto(base + "/login", { waitUntil: "networkidle" });
await ap2.getByLabel("Email address").fill(adminEmail); await ap2.getByLabel("Password", { exact: true }).fill(PW);
await ap2.getByRole("button", { name: "Sign in", exact: true }).last().click();
await ap2.getByLabel("Authenticator code").waitFor({ timeout: 8000 }).catch(async () => { console.log("DEBUG url", ap2.url(), await ap2.locator(".formerr").allInnerTexts(), ap2.errs); await ap2.screenshot({ path: "/tmp/ap2.png" }); });
await ap2.getByLabel("Authenticator code").fill("000000"); await ap2.getByRole("button", { name: "Verify and sign in" }).click(); await ap2.locator(".formerr").waitFor();
check("admin: a wrong code is refused", (await ap2.locator(".formerr").count()) === 1);
await ap2.getByLabel("Authenticator code").fill(totp(secret, 1)); await ap2.getByRole("button", { name: "Verify and sign in" }).click();
await ap2.waitForURL(/\/(dashboard|console)/);
check("admin: right code signs in", true);
await ap2.goto(base + "/admin", { waitUntil: "networkidle" });
check("admin: content tools open with the normal sign-in (no second password)", await ap2.getByRole("heading", { name: "Research publishing" }).waitFor({ timeout: 8000 }).then(() => true, () => false), ap2.url());
await ac2.close();
const vcx = await ctx(), vpx = await page(vcx);
await vpx.goto(base + "/admin/login", { waitUntil: "networkidle" });
check("visitor: /admin/login sends people to the one sign-in page", /\/login\?next=%2Fadmin|\/login\?next=\/admin/.test(vpx.url()), vpx.url());
await vpx.goto(base + "/", { waitUntil: "networkidle" });
await vpx.getByRole("button", { name: /^Products/ }).click();
check("home: Products menu lists the tools", (await vpx.getByRole("menuitem", { name: /Alerts/ }).count()) === 1 && (await vpx.getByRole("menuitem", { name: /Screener/ }).count()) === 1);
check("home: pricing and FAQ sections present", (await vpx.locator("#pricing").count()) === 1 && (await vpx.locator("#faq details").count()) >= 6);
check("home: footer has no public admin link", (await vpx.locator("footer").getByText("CMS admin").count()) === 0);
await vcx.close();

// ---------------------------------------------------------------- now Silver
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
const me = await api(p, "/api/auth/me");
check("granted plan reaches the member without signing in again", me.body.plan === "silver", me.body.plan);
check("silver: score visible, ratio history partial", (await api(p, "/api/stocks/RELIANCE")).body.score.overall != null && Object.keys((await api(p, "/api/stocks/RELIANCE/ratios")).body.history.rows).length === 5);
check("silver: detailed ratios still withheld", (await api(p, "/api/stocks/RELIANCE/segments")).body.periods.length === 0);
const st2 = (await api(p, "/api/stocks/RELIANCE/stats")).body;
check("silver: price statistics delivered", st2.available === true && st2.monthly.years.length >= 1 && st2.histogram.days > 100);
await p.reload({ waitUntil: "networkidle" });
const lab = p.locator("#charts").locator("xpath=ancestor::section[1]");
await lab.scrollIntoViewIfNeeded();
check("chart lab: candles and price statistics draw for Silver", (await lab.locator("svg").count()) >= 4 && (await lab.locator(".hg").count()) === 1);
for (const t of ["Profit & loss", "Balance sheet", "Cash flow", "Ownership", "Valuation", "Events & peers"]) {
  await lab.getByRole("button", { name: t, exact: true }).click(); await p.waitForTimeout(250);
  check(`chart lab: ${t} tab renders`, (await lab.locator("svg, .hg, .tm, .db2, .rk, .gate").count()) >= 1);
  if (t === "Valuation") check("chart lab: valuation against history is Gold-only (locked for Silver)", (await lab.locator(".gate.is-locked").count()) === 1);
}
check("silver: stock page has no errors", p.errs.length === 0, p.errs.join(" | "));

// ---------------------------------------------------------------- appearance + dashboard personalisation
await p.goto(base + "/account/appearance", { waitUntil: "networkidle" });
await p.getByRole("radio", { name: /Midnight/ }).click();
check("appearance: choosing Midnight recolours the page", (await p.evaluate(() => document.documentElement.dataset.palette)) === "midnight" && (await p.evaluate(() => getComputedStyle(document.body).backgroundColor)) !== "rgb(246, 241, 231)");
await p.getByRole("radio", { name: /Emerald/ }).click();
const emerald = await p.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--gold").trim());
check("appearance: palettes change the accent", emerald !== "#8A6A25" && emerald.length > 3, emerald);
await p.getByRole("radio", { name: /Graphite/ }).click(); await p.waitForTimeout(1500);
await p.reload({ waitUntil: "networkidle" });
check("appearance: choice survives a reload with no flash of the default", (await p.evaluate(() => document.documentElement.dataset.palette)) === "graphite");
await p.goto(base + "/dashboard?edit=1", { waitUntil: "networkidle" });
const before = await p.locator(".dw").count();
await p.locator(".dash-edit li", { hasText: "Term of the day" }).locator("input[type=checkbox]").uncheck({ force: true });
check("dashboard: switching a widget off removes it", (await p.locator(".dw").count()) === before - 1);
await p.locator(".dash-edit li", { hasText: "Market snapshot" }).getByRole("button", { name: /Move .* down/ }).click();
const first = await p.locator(".dw h3").first().innerText();
check("dashboard: widgets can be reordered", !/Market snapshot/.test(first), first);
await p.waitForTimeout(1500);
// a brand-new browser signs in: layout and palette arrive from the account
const c2 = await ctx(), p2 = await page(c2);
await p2.goto(base + "/login", { waitUntil: "networkidle" });
await p2.getByLabel("Email address").fill(email); await p2.getByLabel("Password", { exact: true }).fill(PW);
await p2.getByRole("button", { name: "Sign in", exact: true }).last().click(); await p2.waitForURL(/\/dashboard/); await p2.waitForTimeout(1200);
check("sync: palette follows the account to a new device", (await p2.evaluate(() => document.documentElement.dataset.palette)) === "graphite");
check("sync: dashboard layout follows the account", (await p2.locator(".dw h3", { hasText: "Term of the day" }).count()) === 0);

// ---------------------------------------------------------------- watchlist sync (Silver)
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
await p.locator("button", { hasText: /Watchlist|Add to watchlist/i }).first().click();
await p.waitForTimeout(1500);
const st = await api(p, "/api/me/state");
check("watchlist: saved to the account", JSON.stringify(st.body.watchlist).includes("RELIANCE"), JSON.stringify(st.body.watchlist).slice(0, 80));
await p2.reload({ waitUntil: "networkidle" }); await p2.waitForTimeout(800);
await p2.goto(base + "/watchlist", { waitUntil: "networkidle" });
check("watchlist: appears on the other device", (await p2.getByText("RELIANCE").count()) >= 1);

// ---------------------------------------------------------------- portfolio (Silver) + email preferences
await p.goto(base + "/holdings", { waitUntil: "networkidle" });
await p.locator(".pf-one input").fill("RELIANCE"); await p.locator(".pf-one .btn").click(); await p.waitForTimeout(400);
await p.locator(".pf-bulk textarea").fill("TCS\nINFY");
await p.getByRole("button", { name: "Add these" }).click(); await p.waitForTimeout(600);
check("portfolio: shares are added by name", (await p.locator("table.hold tbody tr").count()) === 3);
await p.waitForTimeout(1500);
const pst = await api(p, "/api/me/state");
check("portfolio: saved to the account", (pst.body.portfolio.holdings || []).length === 3, JSON.stringify(pst.body.portfolio).slice(0, 80));
await p2.goto(base + "/holdings", { waitUntil: "networkidle" }); await p2.waitForTimeout(800);
check("portfolio: appears on the other device", (await p2.locator(".hold tbody tr").count()) === 3);
await p.goto(base + "/account/appearance", { waitUntil: "networkidle" });
await p.getByLabel(/Send me .your week ahead/).check({ force: true }); await p.waitForTimeout(1500);
check("weekly email preference is saved to the account", (await api(p, "/api/me/state")).body.prefs.digest === true);

// ---------------------------------------------------------------- security: CSRF + sign out
const csrfBad = await api(p, "/api/me/prefs", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ palette: "gold" }) });
check("security: state change without the CSRF token is refused", csrfBad.status === 403, JSON.stringify(csrfBad.body));
const sessions = await api(p, "/api/me/sessions");
check("security: session list never exposes tokens", !JSON.stringify(sessions.body).includes(sess.value));
await p.goto(base + "/account/security", { waitUntil: "networkidle" });
check("security: this device is marked in the session list", (await p.getByText("This device").count()) === 1);
await p.locator(".av-btn").click(); await p.getByRole("menuitem", { name: "Sign out" }).click(); await p.waitForURL(base + "/");
check("sign-out: header returns to sign in", (await p.getByRole("link", { name: "Create account" }).count()) === 1);
await p.goto(base + "/dashboard", { waitUntil: "networkidle" });
check("sign-out: dashboard is closed again", /\/login/.test(p.url()));
check("sign-out: old session cookie is dead", (await api(p, "/api/auth/me")).body.user === null);
await p.goto(base + "/watchlist", { waitUntil: "networkidle" });
check("sign-out: personal watchlist left this browser", (await p.evaluate(() => localStorage.getItem("finlit-watchlist-v1") || "")).includes("RELIANCE") === false);

console.log(failed ? `\n${failed} check(s) failed` : "\nall checks passed");
await browser.close();
process.exit(failed ? 1 : 0);
