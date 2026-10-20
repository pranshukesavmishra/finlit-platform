import { chromium } from "/opt/node-tools/node_modules/playwright/index.mjs";
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
p.on("pageerror", (e) => console.log("ERR", e.message.slice(0,120)));
await p.goto("http://127.0.0.1:5200/stocks/" + (process.argv[2] || "SMP-ENE2"), { waitUntil: "networkidle" }); await p.waitForTimeout(2500);
await p.screenshot({ path: "/tmp/claude-0/g1.png" }); await p.evaluate(() => window.scrollTo(0, 2600)); await p.waitForTimeout(800); await p.screenshot({ path: "/tmp/claude-0/g2.png" });
// find fixed/absolute elements covering the viewport height
const hits = await p.evaluate(() => [...document.querySelectorAll("body *")].map((e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return { t: e.tagName + "." + String(e.className).slice(0, 40), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), pos: cs.position, bg: cs.backgroundColor }; }).filter((o) => o.h > 700 && o.w < 400 && o.w > 20).slice(0, 15));
console.log(JSON.stringify(hits));
await b.close();
