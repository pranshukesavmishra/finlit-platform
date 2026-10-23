// Site-wide search: the stock list is ready before the box opens, opens on the biggest companies, answers a typed query at once,
// switches filters with Tab, and moves through results across sections with the arrow keys.
//   node e2e/search_speed.mjs http://localhost:4173
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
await p.goto(B + "/", { waitUntil: "networkidle" });
const t0 = Date.now(); await p.keyboard.press("Control+k"); await p.waitForSelector("#gsList [role=option]", { timeout: 3000 });
const open = Date.now() - t0; check("search shows companies at once (no loading wait)", open < 1000, open + " ms");
const first = await p.locator("#gsList [role=option] .gs-tk").allInnerTexts();
check("opening list is by size, not alphabetical", first.length >= 5 && first.join() !== [...first].sort().join(), first.slice(0, 6).join(","));
const t1 = Date.now(); await p.keyboard.type("tata"); await p.waitForFunction(() => [...document.querySelectorAll("#gsList [role=option] .gs-t")].some((e) => /tata/i.test(e.textContent || "")));
const typed = Date.now() - t1; check("typing finds matches immediately", typed < 800, `${typed} ms`);
check("matched text is highlighted", (await p.locator("#gsList mark").count()) > 0);
await p.keyboard.press("ArrowDown"); await p.keyboard.press("ArrowDown");
check("arrow keys move the active result", (await p.locator("input.gs-q").getAttribute("aria-activedescendant")) === "gs-o-2");
await p.keyboard.press("Tab");
check("Tab switches to the Stocks filter", (await p.locator(".gs-tabs [aria-selected=true]").innerText()) === "Stocks");
await p.keyboard.press("Escape"); check("Esc clears the box first", (await p.locator("input.gs-q").inputValue()) === "");
await p.keyboard.press("Escape"); check("then closes it", (await p.locator(".gs").count()) === 0);
check("no page errors", p.errs.length === 0, p.errs.join(" | "));
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
