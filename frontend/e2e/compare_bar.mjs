// Compare page: chips with a cross, a search that opens on every company, add/remove, plan limit, and the spider tab keeping company names in view.
//   PM_PASSWORD=... node e2e/compare_bar.mjs http://localhost:4173   (needs members pm-gold@ and pm-silver@example.com)
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
async function open(who, w = 1366) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: `pm-${who}@example.com`, password: process.env.PM_PASSWORD } });
  await p.goto(B + "/compare?c=RELIANCE,BAJFINANCE", { waitUntil: "networkidle" }); await p.waitForSelector(".cb-chip"); return { ctx, p };
}
const chips = (p) => p.locator(".cb-chip b").allInnerTexts();
{ const { ctx, p } = await open("gold");
  const start = await chips(p); check("gold: two companies shown as chips", start.length === 2 && start[0] === "RELIANCE", start.join());
  await p.locator(".cb-field input").click();
  const n = Number((await p.locator(".cb-n").innerText()).replace(/\D/g, ""));
  check("search opens on the full list (all companies)", n > 500, String(n));
  const first = await p.locator(".cb-o").count(); check("list renders a window and scrolls", first > 5 && first < n, `${first} rendered of ${n}`);
  await p.locator(".cb-scroll").evaluate((el) => { el.scrollTop = 20000; }); await p.waitForTimeout(300);
  const lastSym = await p.locator(".cb-o b").last().innerText(); check("scrolling reaches companies far down the list", lastSym.length > 0 && lastSym !== "RELIANCE", lastSym);
  const probe = (await p.locator(".cb-o:not(.on)").nth(3).locator("b").innerText());
  await p.locator(".cb-scroll").evaluate((el) => { el.scrollTop = 0; });
  await p.locator(".cb-field input").fill(probe); await p.waitForTimeout(300);
  const hits = await p.locator(".cb-o b").allInnerTexts(); check("typing narrows the list", hits.length > 0 && hits.length < 10 && hits.includes(probe), hits.join(","));
  await p.locator(".cb-o", { hasText: probe }).first().click(); await p.waitForTimeout(700);
  check("click adds a company as a chip", (await chips(p)).includes(probe), (await chips(p)).join());
  await p.keyboard.press("Escape");
  await p.locator(".cb-chip", { hasText: start[1] }).getByRole("button").first().click(); await p.waitForTimeout(700);
  check("the cross removes a company", !(await chips(p)).includes(start[1]), (await chips(p)).join());
  await p.getByRole("button", { name: "Remove all companies" }).click(); await p.waitForTimeout(200);
  check("Clear empties the comparison and says what to do", (await p.getByText("Pick at least two companies").count()) >= 1);
  await p.locator(".cb-pop .cb-p").first().click({ timeout: 4000 }).catch(() => null); await p.waitForTimeout(600); if ((await chips(p)).length < 2) { await p.locator(".cb-field input").click(); await p.locator(".cb-o").nth(0).click(); await p.locator(".cb-o").nth(1).click(); await p.keyboard.press("Escape"); } await p.waitForTimeout(500);
  check("two companies are chosen again (popular pair or by search)", (await chips(p)).length === 2, (await chips(p)).join());
  await p.getByRole("tab", { name: "Spider" }).click(); await p.waitForTimeout(600);
  const head = await p.locator(".sp-h b").allInnerTexts(); check("spider tab names each company above its values", head.length === 2, head.join(","));
  await p.locator(".sp-r").last().scrollIntoViewIfNeeded(); await p.mouse.wheel(0, 300); await p.waitForTimeout(400);
  const top = await p.locator(".sp-h").evaluate((e) => e.getBoundingClientRect().top); check("spider names stay in view while scrolling", top >= 0 && top < 200, String(top));
  await p.screenshot({ path: `${OUT}/compare-spider.png` });
  await p.locator(".cb-field input").click(); await p.screenshot({ path: `${OUT}/compare-open.png` });
  check("gold: no page errors", p.errs.length === 0, p.errs.join(" | ")); await ctx.close(); }
{ const { ctx, p } = await open("silver");
  await p.locator(".cb-field input").click(); await p.locator(".cb-o:not(.on)").nth(2).click(); await p.waitForTimeout(300);
  const goes = /(plans|account\/plan)/.test(p.url()); check("silver: a third company is refused and Gold is offered (plans page opens)", goes || ((await chips(p)).length === 2 && (await p.getByText(/Gold/).count()) > 0), p.url());
  await ctx.close(); }
{ const { ctx, p } = await open("gold", 390);
  const over = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check("phone: no sideways scroll", over <= 1, String(over));
  await p.locator(".cb-field input").click(); await p.screenshot({ path: `${OUT}/compare-phone.png` }); await ctx.close(); }
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
