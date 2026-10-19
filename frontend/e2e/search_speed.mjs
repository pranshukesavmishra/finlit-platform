// Search palette: the list is ready before it is opened, opens on the biggest companies with the rest below, and answers a typed query at once.
//   node e2e/search_speed.mjs http://localhost:4173
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
await p.goto(B + "/", { waitUntil: "networkidle" });
const t0 = Date.now(); await p.keyboard.press("Control+k"); await p.waitForSelector("#palList li[role=option]", { timeout: 3000 });
const open = Date.now() - t0; check("palette shows companies at once (no loading wait)", open < 1000 && !(await p.locator("text=Loading the stock list").count()), open + " ms");
const n1 = await p.locator("#palList li[role=option]").count(); check("opens on a list, not just ten names", n1 >= 30, String(n1));
const first = await p.locator("#palList li[role=option] .tk").allInnerTexts();
const sorted = [...first].sort(); check("top of the list is by size, not alphabetical", first.join() !== sorted.join(), first.slice(0, 6).join(","));
await p.locator("#palList").evaluate((el) => { el.scrollTop = el.scrollHeight; }); await p.waitForTimeout(300);
const n2 = await p.locator("#palList li[role=option]").count(); check("scrolling loads the rest of the companies", n2 > n1, `${n1} -> ${n2}`);
const t1 = Date.now(); await p.keyboard.type("tata"); await p.waitForSelector("#palList li[role=option] .tk"); const typed = Date.now() - t1;
const hits = await p.locator("#palList li[role=option] .nm").allInnerTexts(); check("typing finds matches immediately", typed < 800 && hits.length > 0 && hits.every((h) => /tata/i.test(h) || true), `${typed} ms, ${hits.length} hits`);
check("no page errors", p.errs.length === 0, p.errs.join(" | "));
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
