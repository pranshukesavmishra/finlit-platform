// End-to-end check of every interactive feature against a running site + both backends.
//   node e2e/smoke.mjs http://127.0.0.1:4173      (needs: npm i -D playwright, and `npx playwright install chromium`)
const base = process.argv[2] || process.env.E2E_BASE || "http://127.0.0.1:4173";
const skip = (why) => { console.log(`SKIP  smoke checks not run: ${why}`); process.exit(0); };
let chromium;
try { ({ chromium } = await import("playwright")); } catch { skip("playwright is not installed (npm i -D playwright; npx playwright install chromium)"); }
try { await fetch(base + "/", { signal: AbortSignal.timeout(4000) }); } catch { skip(`no server is reachable at ${base} (start the stack, or pass the address as the first argument)`); }
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await ctx.addInitScript(() => { localStorage.setItem("finlit-plan", "gold"); localStorage.setItem("finlit-theme", "dark"); });

// Member-only parts need a signed-in Gold member: the demo account when DEMO_PASSWORD is set.
if (process.env.DEMO_PASSWORD) {
  await page.goto(base + "/login", { waitUntil: "networkidle" });
  await page.getByLabel("Email address").fill("demo-gold@finlit-demo.com"); await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).last().click(); await page.waitForURL(/\/dashboard/);
}

// 1. Home renders, live example loads from the research API
await page.goto(base, { waitUntil: "networkidle" });
check("home: headline", await page.locator("h1").innerText().then((t) => /research report/i.test(t)));
check("home: live score card from research API", await page.locator(".hh-card .hh-dial-n").first().textContent().then((t) => /^\d+$/.test((t || "").trim())).catch(() => false));
check("home: removed Results section is gone", await page.locator("text=Realised portfolio performance").count().then((n) => n === 0));

// 2. Search palette (Ctrl+K), typing, Enter opens the report
await page.keyboard.press("Control+k");
await page.waitForSelector(".gs input");
await page.fill(".gs input", "reliance");
await page.waitForSelector("#gsList [role=option]");
check("search: results appear", (await page.locator("#gsList [role=option]").count()) > 0);
await page.keyboard.press("Enter");
await page.waitForURL(/\/stocks\/RELIANCE/);
await page.waitForSelector(".dial svg");
check("stock: report opens from search", true);

// 3. Stock page content
check("stock: price shown", await page.locator(".px").innerText().then((t) => /\d/.test(t)));
check("stock: five pillars", (await page.locator(".dk-left button.dk-tile").count()) === 5);
await page.locator(".dk-left button.dk-tile").first().click();
check("stock: pillar drawer opens", await page.locator(".pdrawer.open").count().then((n) => n === 1));
await page.waitForSelector("section:has(#price) .chart svg path", { timeout: 8000 });
check("stock: price chart drawn", true);
await page.locator("section:has(#price) .seg button", { hasText: "6M" }).click();
await page.waitForTimeout(600);
check("stock: range switch redraws", (await page.locator("section:has(#price) .chart svg path").count()) > 0);
await page.locator("section:has(#financials) .seg button", { hasText: "Balance sheet" }).click();
await page.waitForTimeout(500);
check("stock: balance sheet chart", (await page.locator("section:has(#financials) .chart svg rect").count()) > 5);
const info = page.locator("button.info").first();
if (await info.count()) {
  await info.scrollIntoViewIfNeeded(); await info.click(); await page.waitForTimeout(250);
  check("stock: glossary popover", await page.locator("[role=tooltip], .pop:not([hidden])").count().then((n) => n > 0));
} else console.log("SKIP  stock: no glossary info button found on this page");

// 4. Plan gating is covered against the real server in e2e/accounts.mjs (the demo plan switch does not exist on the real site).

// 5. Downloads
const [dl] = await Promise.all([page.waitForEvent("download"), (async () => { await page.locator(".actions .btn", { hasText: "Download" }).click(); await page.locator(".dl-menu button", { hasText: "Data · CSV" }).click(); })()]);
check("download: CSV", /RELIANCE-FinLit-Data\.csv/.test(dl.suggestedFilename()));

// 6. Theme toggle
await page.locator(".icon-btn[aria-label*='theme']").first().click();
check("theme: switches to light", (await page.evaluate(() => document.documentElement.dataset.theme)) === "light");

// 7. Enquiry (site backend)
await page.goto(base + "/services", { waitUntil: "networkidle" });
await page.locator(".feat .btn", { hasText: "Enquire" }).first().click();
await page.fill(".modal input[autocomplete=name]", "Test User");
await page.fill(".modal input[type=email]", "test@example.com");
await page.fill(".modal input[type=tel]", "+91 98765 43210");
await page.locator(".modal button.primary, .modal button:has-text('Send enquiry')").last().click();
await page.waitForSelector(".modal .done", { timeout: 8000 });
check("enquiry: saved by site backend", true);

// 8. Contact form validation + submit
await page.goto(base + "/contact", { waitUntil: "networkidle" });
await page.locator("form button.primary").click();
check("contact: validation message", await page.locator(".formerr").count().then((n) => n === 1));
await page.fill("input[autocomplete=name]", "Test User");
await page.fill("input[type=email]", "test@example.com");
await page.fill("textarea", "Hello, I would like a portfolio review please.");
await page.locator("form button.primary").click();
await page.waitForSelector(".done", { timeout: 8000 });
check("contact: message saved by site backend", true);

// 9. Assistant guided menu
await page.goto(base, { waitUntil: "networkidle" });
await page.locator(".ai-fab").click();
await page.locator(".chips button", { hasText: "Explore Services" }).click();
check("assistant: guided menu answers", await page.locator(".bub.bot", { hasText: "five services" }).count().then((n) => n > 0));

// 10. Blog list + article from site backend
await page.goto(base + "/blog", { waitUntil: "networkidle" });
check("blog: posts listed", (await page.locator(".postcard").count()) > 0);
await page.locator(".postcard").first().click();
await page.waitForSelector(".article");
check("blog: article renders", true);

// 11. Portfolio report
await page.goto(base + "/portfolio", { waitUntil: "networkidle" });
check("portfolio: ledger rows", (await page.locator(".tbl tbody tr").count()) > 5);

// 12. Admin access (one sign-in, authenticator code, /admin without a second password) is covered in e2e/accounts.mjs and e2e/deploy_check.mjs.

// 13. Unknown stock and 404 page
await page.goto(base + "/stocks/ZZZZZZ", { waitUntil: "networkidle" });
check("stock: unknown ticker handled", await page.locator("h2", { hasText: /couldn't find/i }).count().then((n) => n > 0));
await page.goto(base + "/no-such-page", { waitUntil: "networkidle" });
check("404 page", await page.locator("h2", { hasText: /cannot find/i }).count().then((n) => n > 0));

check("no uncaught JS errors", errors.length === 0, errors.join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
