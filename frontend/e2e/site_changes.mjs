// The website changes: 7 features, tagline, coming soon + email, comparison with ✓/✕, FAQ, removed sections, score strip on reports.
//   PM_PASSWORD=... node e2e/site_changes.mjs http://localhost:4173
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
async function page(who, w = 1366) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  if (who) { const me = await (await ctx.request.get(B + "/api/auth/me")).json(); await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: `pm-${who}@example.com`, password: process.env.PM_PASSWORD } }); }
  return { ctx, p };
}
{ const { ctx, p } = await page(null);
  await p.goto(B + "/", { waitUntil: "networkidle" }); await p.waitForTimeout(800);
  const body = (await p.locator("body").innerText());
  check("features: seven cards incl. News", (await p.locator(".plat .plat-t").count()) === 7 && (await p.locator(".plat-t h3", { hasText: "News" }).count()) === 1);
  check("features: screener card shows the maths", (await p.locator(".plat-math").count()) === 1 && /AND/.test(await p.locator(".plat-math").innerText()));
  check("features: technical vs fundamental explained", (await p.locator(".split").innerText()).includes("Fundamental") && (await p.locator(".split").innerText()).includes("Technical"));
  check("tagline under the hero", /Quantify the market\s*×\s*Research deeper\s*×\s*Track what matters/.test((await p.locator(".tagline").innerText()).replace(/\n/g, " ")));
  check("coming soon block with email box", (await p.locator("#coming-soon").count()) === 1 && (await p.locator("#coming-soon input[type=email]").count()) === 1);
  check("removed: results, process, founder", !/Results, reported openly/i.test(body) && !/From research to portfolio decisions/i.test(body) && !/Meet the founder/i.test(body));
  check("pricing: comparison table with green ticks and red crosses", (await p.locator("#pricing .cmp .yes.ck").count()) > 10 && (await p.locator("#pricing .cmp .x-no").count()) > 10);
  check("pricing: equity research report marked coming soon", (await p.locator("#pricing .soon-tag").count()) === 1);
  const groups = await p.locator(".faq-g").allInnerTexts(); check("faq: five groups", groups.length === 5, groups.join(" | "));
  const qn = await p.locator(".faq details").count(); check("faq: all questions, expandable", qn >= 18, String(qn));
  await p.locator(".faq details summary").first().click(); check("faq: a question opens", (await p.locator(".faq details[open] p").count()) === 1);
  // notify form
  await p.locator("#coming-soon input[type=email]").fill("not-an-email"); await p.locator("#coming-soon button.btn").click(); check("notify: bad address is refused kindly", (await p.locator("#coming-soon .nf-err").count()) === 1);
  const addr = `site-check-${Date.now()}@example.com`; await p.locator("#coming-soon input[type=email]").fill(addr); await p.locator("#coming-soon button.btn").click(); await p.waitForTimeout(800);
  check("notify: thank-you shown after saving", (await p.locator("#coming-soon .nf-done").count()) === 1);
  await p.screenshot({ path: `${OUT}/home-top.png` }); await p.locator(".plat").scrollIntoViewIfNeeded(); await p.screenshot({ path: `${OUT}/home-features.png` });
  await p.locator("#pricing").scrollIntoViewIfNeeded(); await p.screenshot({ path: `${OUT}/home-pricing.png` });
  check("home: no page errors", p.errs.length === 0, p.errs.join(" | "));
  const nav = await p.locator("header").innerText(); check("menus: no Track record link", !/Track record/.test(nav));
  await ctx.close(); }
{ const { ctx, p } = await page(null, 390);
  await p.goto(B + "/", { waitUntil: "networkidle" }); const over = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check("home: no sideways scroll at 390px", over <= 1, String(over));
  await p.screenshot({ path: `${OUT}/home-phone.png` }); await ctx.close(); }
{ const { ctx, p } = await page(null);
  await p.goto(B + "/plans", { waitUntil: "networkidle" }); check("plans page: ticks and crosses", (await p.locator(".cmp .yes.ck").count()) > 10 && (await p.locator(".cmp .x-no").count()) > 10); await ctx.close(); }
{ const { ctx, p } = await page("silver");
  await p.goto(B + "/stocks/RELIANCE", { waitUntil: "networkidle" }); await p.waitForTimeout(900);
  const bars = await p.locator(".sstrip .ss-bars > div").count(); check("report: score strip at the top with five pillar bars", (await p.locator(".sstrip").count()) === 1 && bars === 5, String(bars));
  const first = await p.locator(".sstrip").evaluate((e) => e.getBoundingClientRect().top); check("report: strip sits right under the price row", first < 520, String(first));
  check("report: fundamental and technical shown separately", (await p.locator(".ss-split small").allInnerTexts()).join().toLowerCase() === "fundamental,technical");
  await p.screenshot({ path: `${OUT}/report-score.png` }); await ctx.close(); }
{ const { ctx, p } = await page("basic");
  await p.goto(B + "/stocks/RELIANCE", { waitUntil: "networkidle" });
  await ctx.close(); }
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
