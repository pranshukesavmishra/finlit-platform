// Regenerates the Tools & Research Hub pictures (frontend/public/feature-bucket/<slug>-light.webp and -dark.webp).
//   cd frontend && VITE_DEMO=1 npx vite build --minify false --outDir /tmp/fb-demo
//   npx vite preview --outDir /tmp/fb-demo --port 4423 --host 127.0.0.1 &
//   node ../scripts/make-feature-shots.mjs http://127.0.0.1:4423 [slug ...]
// Demo build only: every picture is made from the recorded demo data, so no personal data can appear.
// Each page is captured at 1280 px wide (the page area right of the side rail, 940x588), shrunk to 640x400 and encoded to WebP (<= 56 KB) by the browser itself, so no extra packages are needed.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "/opt/node-tools/node_modules/playwright");
const base = (process.argv[2] || "http://127.0.0.1:4423").replace(/\/$/, "");
const only = process.argv.slice(3);
const OUT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../frontend/public/feature-bucket");
const MAX = 56 * 1024;
// slug -> page shown in the picture (several tools may share a slug's page when it is the tool's own page)
export const SHOTS = {
  "stock-radar": "/screener", "score-screener": "/advanced-score-screener", "etf-explorer": "/etfs", "fund-finder": "/funds",
  "fund-health-check": "/fund-score-screener", "chart-studio": "/graphs", "peer-compare": "/compare", "company-health-score": "/prism",
  "company-financials": "/premium/fundamentals?symbol=RELIANCE", "deep-dive-report": "/premium/report/RELIANCE", "fair-value-calculator": "/dcf",
  "forecast-builder": "/outlook/RELIANCE", "finance-calculators": "/eps-calculator", "option-chain": "/premium/options",
  "watchlists": "/watchlist", "portfolio-check-up": "/holdings", "alerts": "/alerts", "compare-funds": "/funds/compare",
  "theme-tracker": "/sectors", "market-dashboard": "/premium/markets", "newsroom": "/news", "investor-circle": "/forum",
};
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const enc = await browser.newPage();
for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); localStorage.setItem("finlit-plan", "gold"); localStorage.setItem("finlit-cookie", "1"); } catch {} }, theme);
  for (const [slug, url] of Object.entries(SHOTS)) {
    if (only.length && !only.includes(slug)) continue;
    const page = await ctx.newPage();
    await page.goto(base + url, { waitUntil: "networkidle" });
    await page.waitForTimeout(2500);
    await page.addStyleTag({ content: "*{animation:none!important;transition:none!important}.skeleton{display:none}.ai-fab,[class*=assistant],[class*=toast],[role=status]{display:none!important}" });
    const png = await page.screenshot({ clip: { x: 316, y: 112, width: 950, height: 594 } });
    await page.close();
    const b64 = png.toString("base64");
    const webp = await enc.evaluate(async ({ b64, MAX }) => {
      const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
      const c = document.createElement("canvas"); c.width = 640; c.height = 400;
      const g = c.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(img, 0, 0, 640, 400);
      for (let q = 0.85; q > 0.2; q -= 0.05) {
        const d = c.toDataURL("image/webp", q), n = Math.round((d.length - 23) * 0.75);
        if (n <= MAX) return d;
      }
      return c.toDataURL("image/webp", 0.2);
    }, { b64, MAX });
    const buf = Buffer.from(webp.split(",")[1], "base64");
    fs.writeFileSync(path.join(OUT, `${slug}-${theme}.webp`), buf);
    console.log(theme, slug, Math.round(buf.length / 1024) + " KB");
  }
  await ctx.close();
}
await browser.close();
