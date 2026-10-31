// Stale-bundle check: a tab loaded from an OLD build meets a NEW deploy.
//   node e2e/stale_bundle.mjs            builds two versions (a few minutes) into a temp folder, serves them, drives Chromium
//   OLD_DIR=... NEW_DIR=... node e2e/stale_bundle.mjs     reuse two existing builds (made with APP_VERSION=old0001 / new0002)
// Asserts: (1) the banner appears after the server switches version (opaque, above content, role=status), and Dismiss hides it for that version;
// (2) a lazy page file that is gone after the deploy makes the tab reload ONCE and land on the new build; (3) if the file stays gone there is no
// reload loop: one reload, then the same bar asks the member to refresh.
import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stale-"));
const build = (dir, v) => { if (!dir) { dir = path.join(tmp, v); console.log(`building ${v} ...`); execSync(`npx vite build --outDir ${dir} --emptyOutDir`, { cwd: root, stdio: "ignore", env: { ...process.env, APP_VERSION: v } }); } return dir; };
const OLD = build(process.env.OLD_DIR, "old0001"), NEW = build(process.env.NEW_DIR, "new0002");

let current = OLD, block = null;            // block: a RegExp of asset paths that answer 404 (a file the new deploy no longer has)
let blockedOnce = false, indexHits = 0;
const mime = { ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".html": "text/html", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".webmanifest": "application/manifest+json" };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x"); let p = decodeURIComponent(u.pathname);
  if (p.startsWith("/api/")) { res.writeHead(404, { "content-type": "application/json", "cache-control": "no-store" }); return res.end("{}"); }
  if (block && block.test(p) && (block.permanent || !blockedOnce)) { blockedOnce = true; res.writeHead(404, { "cache-control": "no-store" }); return res.end("gone"); }
  let f = path.join(current, p);
  const isAsset = p.startsWith("/assets/");
  if (!f.startsWith(current) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { if (isAsset || path.extname(p)) { res.writeHead(404, { "cache-control": "no-store" }); return res.end("nf"); } f = path.join(current, "index.html"); }
  if (f.endsWith("index.html")) indexHits++;
  const noCache = /index\.html$|version\.json$|sw\.js$|theme-init\.js$/.test(f);
  res.writeHead(200, { "content-type": mime[path.extname(f)] || "application/octet-stream", "cache-control": isAsset ? "public, max-age=31536000, immutable" : noCache ? "no-cache" : "public, max-age=3600" });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

let failed = 0;
const check = (n, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const verOf = (p) => p.evaluate(() => (document.querySelector(".ffine .ver") || {}).textContent || "");
const shots = process.env.SHOTS;

for (const [theme, width] of [["light", 1366], ["dark", 360]]) {
  current = OLD; block = null;
  const ctx = await browser.newContext({ viewport: { width, height: 800 }, serviceWorkers: "block" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  const page = await ctx.newPage();
  await page.clock.install();
  await page.goto(base + "/", { waitUntil: "networkidle" });
  check(`[${theme} ${width}] old build is running`, /old0001/.test(await verOf(page)), await verOf(page));
  check(`[${theme} ${width}] no banner while versions match`, (await page.locator(".upd").count()) === 0);

  current = NEW;                                          // the deploy lands
  await page.clock.fastForward(40_000);                   // past the 30 s throttle, as if the member came back to the tab
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const bar = page.getByRole("status").filter({ hasText: "A new version of FinLit is available" });
  await bar.waitFor({ timeout: 8000 }).catch(() => {});
  check(`[${theme} ${width}] banner appears with the exact text`, (await bar.count()) === 1 && /Refresh to get it\./.test(await bar.innerText()));
  if ((await bar.count()) === 1) {
    const s = await bar.evaluate((el) => { const c = getComputedStyle(el), r = el.getBoundingClientRect(); return { bg: c.backgroundColor, z: +c.zIndex, pos: c.position, left: r.left, right: r.right, vw: innerWidth, sw: document.documentElement.scrollWidth }; });
    const alpha = /rgba\(.*,\s*([\d.]+)\)$/.exec(s.bg); const opaque = !alpha || +alpha[1] === 1;
    check(`[${theme} ${width}] opaque background, fixed, z-index above modals, inside the viewport, no sideways scroll`, opaque && s.pos === "fixed" && s.z >= 70 && s.left >= 0 && s.right <= s.vw && s.sw <= s.vw, JSON.stringify(s));
    if (shots) await page.screenshot({ path: path.join(shots, `banner-${theme}-${width}.png`) });
    await bar.getByRole("button", { name: /Dismiss/ }).click();
    check(`[${theme} ${width}] Dismiss hides it`, (await page.locator(".upd").count()) === 0);
    await page.clock.fastForward(400_000);
    check(`[${theme} ${width}] stays hidden for that version after the next poll`, (await page.locator(".upd").count()) === 0);
  }
  await ctx.close();
}

// 2. A page file of the old release is gone: reload once, land on the new build.
{
  current = OLD; block = null; blockedOnce = false;
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  let loads = 0; page.on("load", () => loads++);
  await page.goto(base + "/", { waitUntil: "networkidle" });
  const before = loads;
  current = NEW; block = /\/assets\/Glossary-[^/]+\.js$/; blockedOnce = false;
  await page.evaluate(() => { history.pushState({}, "", "/glossary"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.waitForLoadState("networkidle"); await page.waitForTimeout(1500);
  check("lazy-chunk failure reloads the tab once", loads === before + 1, `loads ${before} -> ${loads}`);
  check("after the reload the new build runs", /new0002/.test(await verOf(page)), await verOf(page));
  check("the reload guard is recorded in sessionStorage", !!(await page.evaluate(() => sessionStorage.getItem("finlit-reload-at"))));
  await ctx.close();
}

// 3. The file stays gone: exactly one reload, then the bar (no loop).
{
  current = OLD; block = null;
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, serviceWorkers: "block" });
  const page = await ctx.newPage();
  let loads = 0; page.on("load", () => loads++);
  await page.goto(base + "/", { waitUntil: "networkidle" });
  const before = loads;
  current = NEW; block = /\/assets\/Glossary-[^/]+\.js$/; block.permanent = true;
  await page.evaluate(() => { history.pushState({}, "", "/glossary"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.waitForTimeout(2500);
  await page.evaluate(() => { history.pushState({}, "", "/glossary"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await page.waitForTimeout(2500);
  check("no reload loop when the file stays missing", loads <= before + 1, `loads ${before} -> ${loads}`);
  await ctx.close();
}

await browser.close(); server.close();
console.log(failed ? `\n${failed} check(s) FAILED` : "\nall checks passed");
process.exit(failed ? 1 : 0);
