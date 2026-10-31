// Inference block under the Correlation charts scatter. Demo build:  VITE_DEMO=1 npx vite --port 5199
//   node e2e/chart_inference.mjs http://localhost:5199
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:5199", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ["--disable-dev-shm-usage"] });
for (const [w, h, scheme] of [[1280, 900, "dark"], [1280, 900, "light"], [390, 844, "dark"], [390, 844, "light"]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: scheme }); const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  await p.goto(B + "/graphs/advanced/valuation", { waitUntil: "networkidle" });
  await p.waitForSelector("[data-testid=inference]", { timeout: 20000 });
  const box = p.locator("[data-testid=inference]").first();
  const t = await box.innerText();
  check(`${w} ${scheme}: inference present`, /inference/i.test(t) && /Information only, not investment advice/.test(t), t.slice(0, 120).replace(/\n/g, " "));
  check(`${w} ${scheme}: no horizontal scroll`, await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  check(`${w} ${scheme}: no advice words`, !/\b(buy|sell|overvalued|undervalued|cheap|expensive)\b/i.test(t));
  await box.scrollIntoViewIfNeeded(); await p.waitForTimeout(300);
  await p.screenshot({ path: `${OUT}/inference-${w}-${scheme}.png`, fullPage: false });
  await box.locator("summary").click(); await p.waitForTimeout(200);
  await box.screenshot({ path: `${OUT}/inference-open-${w}-${scheme}.png` });
  check(`${w} ${scheme}: no page errors`, errs.length === 0, errs.join(" | "));
  await ctx.close();
}
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASS"); process.exit(fails ? 1 : 0);
