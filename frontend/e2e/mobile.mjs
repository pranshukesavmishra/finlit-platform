// Phone-width check: no page may scroll sideways.   node e2e/mobile.mjs http://127.0.0.1:4173
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const PAGES = ["/", "/research", "/screener", "/score-screener", "/premium", "/premium/markets", "/premium/fundamentals", "/premium/report", "/compare", "/graphs/advanced/valuation", "/ipo", "/results", "/news", "/documents", "/glossary", "/plans", "/services", "/about", "/contact", "/blog", "/login", "/stocks/RELIANCE", "/stocks/5PAISA"];
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true });
const p = await ctx.newPage(); let failed = 0;
for (const path of PAGES) {
  await p.goto(base + path, { waitUntil: "networkidle" }).catch(() => {}); await p.waitForTimeout(400);
  const r = await p.evaluate(() => {
    const w = document.documentElement.clientWidth, over = [];
    for (const el of document.querySelectorAll("body *")) { const b = el.getBoundingClientRect(); if (b.width > 0 && b.right > w + 1 && !el.closest("[inert], .scroll-x, .tbl, table, [style*='overflow']")) { over.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`); if (over.length >= 3) break; } }
    return { w, sw: document.documentElement.scrollWidth, over };
  });
  const ok = r.sw <= r.w + 1; if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"} ${path}  page ${r.sw}px vs screen ${r.w}px${ok ? "" : "  widest: " + r.over.join(", ")}`);
}
await browser.close(); process.exit(failed ? 1 : 0);
