// Phone audit: every page on several phones, light and dark. Finds what goes wrong on a phone:
//   sideways page scroll, cut-off text, controls hidden under a fixed bar, tap targets that are too small,
//   text that is too small, inputs that make the iPhone zoom in, and scroll boxes inside scroll boxes.
// Usage:  node e2e/mobile_audit.mjs http://127.0.0.1:4180 [outDir]
// Env:    AUDIT_DEVICES=360,390   (subset by width)   AUDIT_ONLY=screener (substring of a path)
//         AUDIT_THEMES=light,dark  AUDIT_SHOTS=1 (full-page screenshot per case)   AUDIT_STRICT=1 (also fail on tap/text warnings)
import { chromium, devices } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const base = (process.argv[2] || "http://127.0.0.1:4180").replace(/\/$/, "");
const out = process.argv[3] || "/tmp/mobile_audit";
mkdirSync(out, { recursive: true });

export const ROUTES = [
  "/", "/dashboard", "/research", "/stocks/RELIANCE", "/stocks/TCS", "/compare", "/screener", "/score-screener", "/advanced-score-screener",
  "/query-builder", "/results", "/results/quarter", "/sectors", "/sectors/rotation", "/sectors/capital-goods", "/learn/sector-rotation",
  "/learn/sector-signals", "/graphs", "/graphs/advanced", "/prism", "/prism/RELIANCE", "/premium", "/premium/markets", "/premium/fundamentals",
  "/premium/options", "/premium/report", "/premium/report/RELIANCE", "/funds", "/funds/compare", "/funds/insights", "/funds/screener",
  "/fund-score-screener", "/methodology/mf-score", "/mf-portfolio", "/etfs", "/etfs/compare", "/etfs/compare-index-funds", "/commodities",
  "/fii-dii", "/macro", "/outlook", "/outlook/RELIANCE", "/ipo", "/news", "/dcf", "/eps-calculator", "/sip-calculator", "/portfolio", "/holdings",
  "/watchlist", "/alerts", "/baskets", "/documents", "/leadership-label", "/plans", "/pricing", "/services", "/blog", "/forum", "/glossary", "/faq",
  "/about", "/why-we-exist", "/contact", "/legal/terms", "/login", "/forgot-password", "/reset-password", "/verify-email", "/account",
  "/account/appearance", "/console", "/mcp", "/admin/login", "/no-such-page",
];

const ALL_DEVICES = [
  { name: "android-360", w: 360, d: { ...devices["Galaxy S9+"], viewport: { width: 360, height: 740 } } },
  { name: "iphone-se-375", w: 375, d: devices["iPhone SE"] },
  { name: "iphone14-390", w: 390, d: devices["iPhone 14"] },
  { name: "iphone14max-430", w: 430, d: devices["iPhone 14 Pro Max"] },
  { name: "landscape-740", w: 740, d: devices["Galaxy S9+ landscape"] },
  { name: "ipad-768", w: 768, d: devices["iPad Mini"] },
];
const wantW = (process.env.AUDIT_DEVICES || "").split(",").filter(Boolean).map(Number);
const DEVS = wantW.length ? ALL_DEVICES.filter((d) => wantW.includes(d.w)) : ALL_DEVICES;
const THEMES = (process.env.AUDIT_THEMES || "light,dark").split(",");
const routes = ROUTES.filter((r) => !process.env.AUDIT_ONLY || r.includes(process.env.AUDIT_ONLY));

/** Runs in the page. Returns the problems found, each with a short CSS path so the cause can be found. */
function inspect() {
  const W = document.documentElement.clientWidth, H = innerHeight;
  const path = (el) => { const p = []; for (let e = el, i = 0; e && e !== document.body && i < 4; e = e.parentElement, i++) p.unshift(e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : "")); return p.join(" > "); };
  // screen-reader-only text (1px boxes, clip rects) is meant to be invisible, so it is never "cut off"
  const srOnly = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const c = getComputedStyle(e); const r = e.getBoundingClientRect(); if ((r.width <= 2 && r.height <= 2) || (c.clip && c.clip !== "auto") || (c.clipPath && c.clipPath !== "none" && /inset\(50%|inset\(100%/.test(c.clipPath))) return true; } return false; };
  const visible = (el, cs) => cs.display !== "none" && cs.visibility !== "hidden" && +cs.opacity !== 0 && !el.closest("[inert],[aria-hidden=true],.sr-only,.sr,.skip,.visually-hidden,.demo-bar") && !srOnly(el);
  const res = { sideways: [], clipped: [], covered: [], tap: [], smallText: [], zoomInput: [], nested: [] };
  res.pageWidth = document.documentElement.scrollWidth; res.screen = W;
  // 1. sideways: the widest elements whose right edge passes the screen, outside any scroll box
  if (res.pageWidth > W + 1) {
    const over = [];
    for (const el of document.querySelectorAll("body *")) {
      const b = el.getBoundingClientRect(); if (b.width <= 0 || b.right <= W + 1) continue;
      let inScroller = false; for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden" || o === "clip") { inScroller = true; break; } }
      if (!inScroller) over.push([Math.round(b.right), path(el)]);
    }
    // keep the outermost offenders
    res.sideways = over.sort((a, b) => b[0] - a[0]).slice(0, 5);
  }
  const fixed = [...document.querySelectorAll("body *")].filter((el) => { const p = getComputedStyle(el).position; return p === "fixed" || p === "sticky"; });
  for (const el of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(el); if (!visible(el, cs)) continue;
    const b = el.getBoundingClientRect(); if (b.width === 0 || b.height === 0) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    // 2. clipped text: overflow hidden, no ellipsis, content wider than the box (more than 2px)
    if (own && (cs.overflowX === "hidden" || cs.overflowX === "clip") && cs.textOverflow !== "ellipsis" && el.scrollWidth > el.clientWidth + 2 && b.right > 0 && b.left < W) res.clipped.push(path(el) + ` (${el.scrollWidth}>${el.clientWidth})`);
    // 5. small text
    if (own && b.top < document.documentElement.scrollHeight) { const fs = parseFloat(cs.fontSize); if (fs > 0 && fs < 11.5 && !el.closest("svg")) res.smallText.push(`${fs}px ${path(el)}`); }
    // 6. nested scroll: a vertical scroll box inside another vertical scroll box (page body excluded)
    if ((cs.overflowY === "auto" || cs.overflowY === "scroll") && el.scrollHeight > el.clientHeight + 4) {
      for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) { const o = getComputedStyle(p).overflowY; if ((o === "auto" || o === "scroll") && p.scrollHeight > p.clientHeight + 4) { res.nested.push(path(el) + "  in  " + path(p)); break; } }
    }
  }
  // 3/4/5b: controls
  for (const el of document.querySelectorAll("a[href], button, input, select, textarea, [role=button], [role=tab]")) {
    const cs = getComputedStyle(el); if (!visible(el, cs)) continue;
    const b = el.getBoundingClientRect(); if (b.width === 0 || b.height === 0) continue;
    if (b.bottom < 0 || b.top > H || b.right < 0 || b.left > W) { // off screen: only flag ones pushed sideways off the page
      if (b.left >= W && !el.closest("[class*=scroll], [style*=overflow]")) { let inScroller = false; for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o !== "visible") { inScroller = true; break; } } if (!inScroller) res.covered.push("off-screen " + path(el)); }
    } else {
      const cx = Math.min(W - 1, Math.max(0, b.left + b.width / 2)), cy = Math.min(H - 1, Math.max(0, b.top + b.height / 2));
      const hit = document.elementFromPoint(cx, cy);
      if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
        const cover = fixed.find((f) => f.contains(hit) && !f.contains(el));
        const atEnd = scrollY + H >= document.documentElement.scrollHeight - 2;
        // a fixed bar along the bottom (it may float a few px above the edge) only hides what is below it at the end of the page; toasts go by themselves
        const bottomBar = cover && getComputedStyle(cover).position === "fixed" && cover.getBoundingClientRect().top > H / 2;
        if (cover && cover.closest(".alx-toasts, .toast, .prep-toast")) continue;
        if (cover && !el.closest(".mtabs, header.top") && (!bottomBar || atEnd)) res.covered.push(path(el) + "  under  " + path(cover));
      }
    }
    // a pseudo-element can widen the hit area beyond the drawn box (e.g. ::after { inset: -9px })
    const pa = getComputedStyle(el, "::after"); const grow = pa.content !== "none" && pa.position === "absolute" ? Math.max(0, -parseFloat(pa.top) || 0) * 2 : 0;
    const inline = el.tagName === "A" && cs.display === "inline" && el.closest("p, li, td, small, .ffine");
    if (!inline && (b.height + grow < 24 || b.width + grow < 24) && el.type !== "hidden" && el.type !== "checkbox" && el.type !== "radio") res.tap.push(`${Math.round(b.width)}x${Math.round(b.height)} ${path(el)}`);
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) && !/^(checkbox|radio|range|button|submit|color|file|hidden)$/.test(el.type) && parseFloat(cs.fontSize) < 16) res.zoomInput.push(`${cs.fontSize} ${path(el)}`);
  }
  for (const k of ["clipped", "covered", "tap", "smallText", "zoomInput", "nested"]) res[k] = [...new Set(res[k])];
  return res;
}

const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"], executablePath: process.env.CHROME || undefined });
const rows = []; const tally = {};
let hard = 0, soft = 0;
for (const dev of DEVS) for (const theme of THEMES) {
  const ctx = await browser.newContext({ ...dev.d, colorScheme: theme });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); localStorage.setItem("finlit-plan", "gold"); } catch { /* private mode */ } }, theme);
  const page = await ctx.newPage();
  for (const r of routes) {
    await page.goto(base + r, { waitUntil: "networkidle", timeout: 30000 }).catch(() => {});
    await page.waitForFunction(() => !document.querySelector("#ll-boot"), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(500);
    // scroll through once so lazy sections render, then back to the top
    await page.evaluate(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); });
    await page.waitForTimeout(250);
    const res = await page.evaluate(inspect).catch((e) => ({ error: String(e) }));
    const bad = { sideways: res.sideways?.length ? 1 : 0, clipped: res.clipped?.length || 0, covered: res.covered?.length || 0, zoomInput: res.zoomInput?.length || 0, nested: res.nested?.length || 0 };
    const warn = { tap: res.tap?.length || 0, smallText: res.smallText?.length || 0 };
    const h = Object.values(bad).reduce((a, b) => a + b, 0), s = warn.tap + warn.smallText;
    hard += h ? 1 : 0; soft += s ? 1 : 0;
    for (const k of Object.keys(bad)) if (bad[k]) tally[k] = (tally[k] || 0) + 1;
    for (const k of Object.keys(warn)) if (warn[k]) tally[k] = (tally[k] || 0) + 1;
    rows.push({ device: dev.name, theme, route: r, ...res });
    const flag = h ? "FAIL" : s ? "warn" : "ok  ";
    console.log(`${flag} ${dev.name.padEnd(16)} ${theme.padEnd(5)} ${r.padEnd(28)} ${h ? JSON.stringify(bad) : ""} ${s ? JSON.stringify(warn) : ""}`);
    if (process.env.AUDIT_SHOTS) await page.screenshot({ path: `${out}/${dev.name}-${theme}${r.replace(/\//g, "_") || "_home"}.png`, fullPage: true }).catch(() => {});
  }
  await ctx.close();
}
await browser.close();
writeFileSync(`${out}/report.json`, JSON.stringify({ tally, rows }, null, 1));
console.log(`\n${rows.length} cases · ${hard} with hard problems · ${soft} with warnings`);
console.log("pages hit per problem:", JSON.stringify(tally));
console.log(`details: ${out}/report.json`);
process.exit(hard || (process.env.AUDIT_STRICT && soft) ? 1 : 0);
