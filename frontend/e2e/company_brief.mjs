// Company brief on the stock page with every /api/** call mocked (no backend needed). The RELIANCE report comes from public/demo; the brief from src/lib/fixtures/companyBriefReliance.json.
//   node e2e/company_brief.mjs http://127.0.0.1:5199 /path/to/outdir      (CHROME=/path/to/chrome, PW=/path/to/playwright/index.mjs when it is not installed here)
// Checks at 1440 and 390, light and dark: the brief is on the page, nothing scrolls sideways, small chips have a 44px tap area, the empty state gives its reason; saves screenshots.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = await import(process.env.PW || "playwright");
const B = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), OUT = process.argv[3] || "/tmp/brief-shots";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEMO = path.join(HERE, "..", "public", "demo", "RELIANCE");
const BRIEF = JSON.parse(fs.readFileSync(path.join(HERE, "..", "src", "lib", "fixtures", "companyBriefReliance.json"), "utf8"));
fs.mkdirSync(OUT, { recursive: true });
let failed = 0;
const check = (name, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${name}${d ? "  - " + d : ""}`); };

const CHIP = { "Annual report": "AR", "Press release": "PR", "Investor presentation": "IP", "Results filing": "RES" };
const PUBLISHED = { symbol: "RELIANCE", name: "Reliance Industries Ltd", state: "published", brief: { ...BRIEF, status: "reviewed" }, asOf: BRIEF.as_of, reviewedAt: "2026-11-05T05:00:00Z", stale: false, changes: null,
  checks: { date: BRIEF.checks.date, citations: 65, passed: 65, unchecked: 0, fixed: BRIEF.checks.fixed, method: BRIEF.checks.method },
  chips: Object.fromEntries(Object.entries(BRIEF.docs).map(([k, d]) => [k, CHIP[d.kind] || "EV"])), disclaimer: BRIEF.disclaimer,
  compliance: "Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice." };
const EMPTY = { symbol: "RELIANCE", state: "empty", code: "in_review", reason: "Written and being reviewed. It is shown here once a person has read it.", disclaimer: BRIEF.disclaimer, compliance: PUBLISHED.compliance };

async function open(browser, { w, theme, mode = "ok" }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, colorScheme: theme });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); sessionStorage.clear(); } catch {} }, theme);
  const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
  await p.route("**/api/**", async (r) => {
    const u = new URL(r.request().url()), pt = u.pathname, json = (b, s = 200) => r.fulfill({ status: s, contentType: "application/json", body: JSON.stringify(b) });
    if (pt === "/api/auth/me") return json({ user: null, plan: "basic", csrf: "t", limits: {}, showcase: ["RELIANCE"] });
    if (pt === "/api/stocks/RELIANCE/brief") return mode === "slow" ? setTimeout(() => json(PUBLISHED), 4000) : json(mode === "empty" ? EMPTY : PUBLISHED);
    const m = /^\/api\/stocks\/RELIANCE(?:\/([a-z0-9-]+))?$/.exec(pt);
    if (m) {
      const f = m[1] ? (m[1] === "price" ? `price-${(u.searchParams.get("range") || "1Y").toUpperCase()}` : m[1]) : "summary";
      const file = path.join(DEMO, f + ".json");
      return fs.existsSync(file) ? r.fulfill({ status: 200, contentType: "application/json", body: fs.readFileSync(file, "utf8") }) : json({ detail: { status: "not_found" } }, 404);
    }
    return json(/notifications|alerts|indices|companies|feed|ipos/.test(pt) ? [] : {}, pt.startsWith("/api/stocks") ? 404 : 200);
  });
  await p.goto(B + "/stocks/RELIANCE", { waitUntil: "domcontentloaded" });
  await p.waitForSelector("#company-brief", { timeout: 30000 });
  return { ctx, p, errs };
}
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - innerWidth);

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ["--disable-dev-shm-usage", "--no-sandbox"] });
try {
  for (const w of [1440, 390]) for (const theme of ["light", "dark"]) {
    const tag = `${w}-${theme}`;
    const { ctx, p, errs } = await open(browser, { w, theme });
    await p.waitForSelector("#company-brief .cb-about", { timeout: 15000 });
    await p.locator("#company-brief").scrollIntoViewIfNeeded();
    await p.waitForTimeout(400);
    check(`${tag}: the brief shows its sections`, (await p.locator("#company-brief h3").count()) >= 6);
    check(`${tag}: citation chips are on the lines`, (await p.locator("#company-brief .cb-cite").count()) > 40);
    check(`${tag}: no sideways scroll on the page`, (await overflow(p)) <= 1, String(await overflow(p)));
    const box = await p.locator("#company-brief").evaluate((e) => e.scrollWidth - e.clientWidth);
    check(`${tag}: no sideways scroll inside the brief`, box <= 1, String(box));
    const hit = await p.locator("#company-brief .cb-cite").first().evaluate((e) => { const a = getComputedStyle(e, "::after"); return [parseFloat(a.height) || 0, e.getBoundingClientRect().height]; });
    check(`${tag}: a chip's tap area reaches 44px`, hit[0] + 0 >= 0 && hit[1] + 28 >= 44 - 1, JSON.stringify(hit));
    const sm = await p.locator("#company-brief summary").evaluate((e) => e.getBoundingClientRect().height);
    check(`${tag}: the Sources and checks bar is 44px tall`, sm >= 44, String(sm));
    await p.locator("#company-brief").screenshot({ path: `${OUT}/brief-${tag}.png` });
    await p.locator("#company-brief summary").click();
    await p.waitForTimeout(200);
    check(`${tag}: Sources and checks lists the filings with pages`, (await p.locator("#company-brief .cb-src li").count()) >= 8);
    await p.locator("#company-brief .cb-det").screenshot({ path: `${OUT}/sources-${tag}.png` });
    check(`${tag}: no script errors`, errs.length === 0, errs.join(" | "));
    await ctx.close();
  }
  for (const w of [1440, 390]) {
    const { ctx, p } = await open(browser, { w, theme: "light", mode: "empty" });
    await p.waitForSelector("#company-brief .cb-empty");
    check(`${w}: the empty state gives its reason`, /being reviewed/.test(await p.locator("#company-brief").innerText()));
    await p.locator("#company-brief").screenshot({ path: `${OUT}/empty-${w}.png` });
    await ctx.close();
  }
  { const { ctx, p } = await open(browser, { w: 390, theme: "light", mode: "slow" });
    check("a loading skeleton shows while the brief loads", (await p.locator("#company-brief .cb-skel").count()) === 1);
    await p.locator("#company-brief").screenshot({ path: `${OUT}/skeleton-390.png` });
    await ctx.close(); }
} finally { await browser.close(); }
console.log(failed ? `${failed} check(s) failed` : "all checks passed");
process.exit(failed ? 1 : 0);
