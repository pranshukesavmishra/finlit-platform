// Phone-width check (360, 390 and 430 px): no page may scroll sideways.   node e2e/mobile.mjs http://127.0.0.1:4173
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:4173").replace(/\/$/, "");
const PAGES = ["/", "/dashboard", "/research", "/stocks/RELIANCE", "/compare", "/screener", "/score-screener", "/advanced-score-screener", "/query-builder", "/results", "/results/quarter",
  "/sectors", "/sectors/rotation", "/graphs", "/graphs/advanced", "/prism", "/prism/RELIANCE", "/premium", "/premium/markets", "/premium/fundamentals", "/premium/options", "/premium/report",
  "/premium/report/RELIANCE", "/funds", "/funds/compare", "/funds/insights", "/funds/screener", "/fund-score-screener", "/mf-portfolio", "/etfs", "/etfs/compare", "/commodities", "/fii-dii",
  "/macro", "/outlook", "/ipo", "/news", "/dcf", "/eps-calculator", "/sip-calculator", "/portfolio", "/holdings", "/watchlist", "/alerts", "/baskets", "/documents", "/plans", "/services",
  "/blog", "/glossary", "/faq", "/about", "/contact", "/legal/terms", "/login", "/account", "/mcp"];
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
let failed = 0;
for (const width of [360, 390, 430]) {
const ctx = await browser.newContext({ viewport: { width, height: 800 }, isMobile: true, hasTouch: true });
const p = await ctx.newPage();
for (const path of PAGES) {
  await p.goto(base + path, { waitUntil: "networkidle" }).catch(() => {}); await p.waitForTimeout(400);
  const r = await p.evaluate(() => {
    const w = document.documentElement.clientWidth, over = [];
    for (const el of document.querySelectorAll("body *")) { const b = el.getBoundingClientRect(); if (b.width > 0 && b.right > w + 1 && !el.closest("[inert], .scroll-x, .tbl, table, [style*='overflow']")) { over.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`); if (over.length >= 3) break; } }
    return { w, sw: document.documentElement.scrollWidth, over };
  });
  const ok = r.sw <= r.w + 1; if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"} ${width} ${path}  page ${r.sw}px vs screen ${r.w}px${ok ? "" : "  widest: " + r.over.join(", ")}`);
}
await ctx.close();
}
await browser.close(); process.exit(failed ? 1 : 0);
