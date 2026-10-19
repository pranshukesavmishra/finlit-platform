// IPO and results calendars: data beyond the old cut-off, month navigation, and the IPO counters.   node e2e/calendars.mjs http://localhost:4173
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e)));
await p.goto(B + "/ipo", { waitUntil: "networkidle" }); await p.waitForTimeout(800);
const kpis = await p.locator(".ipo-k, .kpis-p .kp, .ipo .kpi").allInnerTexts().catch(() => []);
const text = await p.locator("main").innerText();
// Real provider data (run `python -m finlit.worker refresh-calendars` with the live key first): issues that open soon are listed, none twice.
check("ipo: open or upcoming issues listed", /Open now|Opens|Upcoming/i.test(text));
const names = await p.locator("main h3, main .ipo-n, main b").allInnerTexts().catch(() => []);
check("ipo: no issue listed twice", names.filter((n) => /Ltd|Limited/i.test(n)).length === new Set(names.filter((n) => /Ltd|Limited/i.test(n))).size); check("ipo: no longer 'kept up to date by the FinLit team'", !/FinLit team/.test(text));
check("ipo: not empty", !/No issues listed yet/.test(text));
await p.goto(B + "/results", { waitUntil: "networkidle" }); await p.waitForTimeout(900);
const days = async () => p.evaluate(() => [...document.querySelectorAll(".rcal-c:not(.off)")].filter((c) => c.querySelector("span")).map((c) => Number(c.querySelector("b")?.textContent)));
const d1 = await days(); check("results: this month has entries", d1.length > 0, d1.join(","));
const today = new Date(); const last = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
check("results: entries run past the 17th to the end of the month", Math.max(...d1) > 17 || today.getDate() > 17 && Math.max(...d1) >= today.getDate(), `latest day ${Math.max(...d1)} of ${last}`);
await p.getByRole("button", { name: "Next month" }).click(); await p.waitForTimeout(900);
const d2 = await days(); check("results: next month has entries too", d2.length > 0, d2.join(","));
check("results: coming-up list present", (await p.locator(".feed-l li").count()) > 3);
check("no page errors", errs.length === 0, errs.join(" | "));
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
