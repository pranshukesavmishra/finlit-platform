// Basic accessibility and metadata checks on the public pages: page title, language, one main heading, image alt text,
// names on buttons/links/inputs.   node e2e/a11y_basic.mjs http://127.0.0.1:8010
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:8010").replace(/\/$/, "");
const PAGES = ["/", "/research", "/screener", "/score-screener", "/premium", "/premium/markets", "/premium/fundamentals", "/premium/report", "/compare", "/ipo", "/results", "/news", "/documents", "/glossary", "/plans", "/services", "/about", "/why-we-exist", "/contact", "/portfolio", "/blog", "/legal/terms", "/legal/privacy", "/legal/disclosures", "/login", "/forgot-password", "/stocks/RELIANCE"];
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] }); const p = await (await b.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
const titles = new Map(); let problems = 0;
for (const path of PAGES) {
  await p.goto(base + path, { waitUntil: "networkidle" }); await p.waitForTimeout(700);
  const r = await p.evaluate(() => {
    const name = (e) => (e.getAttribute("aria-label") || e.getAttribute("aria-labelledby") || e.textContent || e.getAttribute("title") || "").trim();
    const vis = (e) => e.offsetParent !== null || getComputedStyle(e).position === "fixed";
    return {
      title: document.title, lang: document.documentElement.lang, h1: document.querySelectorAll("h1").length,
      imgNoAlt: [...document.querySelectorAll("img")].filter((i) => !i.hasAttribute("alt")).length,
      btnNoName: [...document.querySelectorAll("button")].filter((e) => vis(e) && !name(e) && !e.querySelector("img[alt]")).length,
      linkNoName: [...document.querySelectorAll("a[href]")].filter((e) => vis(e) && !name(e) && !e.querySelector("img[alt]")).length,
      inputNoLabel: [...document.querySelectorAll("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea")].filter((e) => vis(e) && !e.getAttribute("aria-label") && !e.getAttribute("aria-labelledby") && !e.id && !e.closest("label") && !e.getAttribute("placeholder")).length,
    };
  });
  const issues = [];
  if (!r.title || /^(vite|finlit)$/i.test(r.title.trim())) issues.push(`weak title "${r.title}"`);
  if (!r.lang) issues.push("no html lang");
  if (r.h1 !== 1) issues.push(`${r.h1} h1 headings`);
  if (r.imgNoAlt) issues.push(`${r.imgNoAlt} images without alt`);
  if (r.btnNoName) issues.push(`${r.btnNoName} unnamed buttons`);
  if (r.linkNoName) issues.push(`${r.linkNoName} unnamed links`);
  if (r.inputNoLabel) issues.push(`${r.inputNoLabel} inputs without a label`);
  if (titles.has(r.title) && path !== "/stocks/RELIANCE") issues.push(`same title as ${titles.get(r.title)}`);
  titles.set(r.title, path);
  if (issues.length) problems++;
  console.log(`${issues.length ? "FAIL" : "ok  "} ${path}  "${r.title.slice(0, 50)}"${issues.length ? "  — " + issues.join("; ") : ""}`);
}
await b.close(); console.log(problems ? `${problems} page(s) with issues` : "ALL PAGES OK"); process.exit(problems ? 1 : 0);
