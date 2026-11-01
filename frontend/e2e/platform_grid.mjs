// Home "Explore our platform" grid: alignment + no-orphan check, and screenshots.
//   CHROME=/path/chrome node e2e/platform_grid.mjs http://127.0.0.1:5199 [outDir] [label] [--no-assert]
// Within every row of cards the tops of the number/badge row, title, description, preview, ticks and button must be equal,
// card heights and button bottoms equal, and every row must fill the grid width (no stranded card, no gap).
import { chromium } from "playwright";
import fs from "node:fs";
const base = (process.argv[2] || "").replace(/\/$/, "");
const out = process.argv[3] || ".platform-grid";
const label = process.argv[4] || "after";
const assert = !process.argv.includes("--no-assert");
const WIDTHS = [1440, 1280, 1100, 900, 768, 390];
const THEMES = ["light", "dark"];
const FILTERS = ["All", "Free", "Silver", "Gold"];
const EXPECT = { All: 21, Free: 10, Silver: 2, Gold: 9 };
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ["--no-sandbox"] });
let fails = 0, checks = 0;
const fail = (m) => { fails++; console.log("FAIL", m); };
for (const theme of THEMES) for (const w of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: theme });
  const page = await ctx.newPage();
  await page.goto(base + "/", { waitUntil: "networkidle" });
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  await page.addStyleTag({ content: ".reveal,[data-reveal]{opacity:1!important;transform:none!important}" });
  for (const f of FILTERS) {
    await page.getByRole("button", { name: f, exact: true }).click();
    await page.waitForTimeout(150);
    const sec = page.locator("#platform");
    await sec.scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    const tag = `${label}-${theme}-${w}-${f}`;
    await sec.screenshot({ path: `${out}/${tag}.png` });
    const m = await page.evaluate(() => {
      const grid = document.querySelector("ul.pg"); const g = grid.getBoundingClientRect();
      const cards = [...grid.querySelectorAll(":scope > li")].map((li) => {
        const r = (sel) => { const e = li.querySelector(sel); return e ? Math.round(e.getBoundingClientRect().top * 10) / 10 : null; };
        const b = li.getBoundingClientRect();
        const cta = li.querySelector(".pg-cta").getBoundingClientRect();
        return { top: Math.round(b.top), left: b.left, w: b.width, h: Math.round(b.height * 10) / 10, parts: [r(".pg-n"), r("h3"), r(".pg-d"), r(".pg-prev"), r(".pg-ticks"), r(".pg-cta")], ctaBottom: Math.round(cta.bottom * 10) / 10 };
      });
      return { gw: g.width, cards, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
    });
    if (m.cards.length !== EXPECT[f]) fail(`${tag}: ${m.cards.length} cards, expected ${EXPECT[f]}`);
    if (m.sw > m.cw + 1) fail(`${tag}: page scrolls sideways`);
    const rows = [];
    m.cards.forEach((c) => { const row = rows.find((r) => Math.abs(r[0].top - c.top) <= 3); if (row) row.push(c); else rows.push([c]); });
    for (const row of rows) {
      checks++;
      const spanW = Math.max(...row.map((c) => c.left + c.w)) - Math.min(...row.map((c) => c.left));
      if (Math.abs(spanW - m.gw) > 2) fail(`${tag}: row of ${row.length} does not fill the grid (${Math.round(spanW)} of ${Math.round(m.gw)})`);
      if (row.length > 1) {
        for (let i = 0; i < 6; i++) { const v = row.map((c) => c.parts[i]); if (Math.max(...v) - Math.min(...v) > 0.6) fail(`${tag}: part ${i} tops differ in a row: ${v}`); }
        const hs = row.map((c) => c.h); if (Math.max(...hs) - Math.min(...hs) > 0.6) fail(`${tag}: card heights differ: ${hs}`);
        const cb = row.map((c) => c.ctaBottom); if (Math.max(...cb) - Math.min(...cb) > 0.6) fail(`${tag}: CTA bottoms differ: ${cb}`);
      }
    }
  }
  await ctx.close();
}
await browser.close();
console.log(`platform grid (${label}): ${checks} rows checked, ${fails} failed`);
if (assert && fails) process.exit(1);
