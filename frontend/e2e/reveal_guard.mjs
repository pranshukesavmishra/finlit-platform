// Reveal guard: content must never stay invisible, and no big empty band may open between sections.
//   node e2e/reveal_guard.mjs http://127.0.0.1:4173 [--shots dir]   (a demo build: VITE_DEMO=1)
// For each page x width (1280, 950, 390) x theme (dark, light) it scrolls the whole page, waits 1.5 s and fails when
//  - a heading / card / reveal block has computed opacity < 1 (own or inherited) or visibility hidden, or
//  - an empty vertical band taller than MAXGAP px sits between content (text, images, svg, canvas, controls).
import { chromium } from "playwright";
const args = process.argv.slice(2);
const base = (args.find((a) => /^https?:/.test(a)) || "http://127.0.0.1:4173").replace(/\/$/, "");
const shots = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : "";
const MAXGAP = 160;
const PAGES = process.env.PAGES ? process.env.PAGES.split(",") : ["/", "/research", "/plans", "/about", "/why-we-exist", "/services", "/faq", "/contact", "/blog", "/portfolio", "/leadership-label", "/mcp", "/glossary", "/sip-calculator", "/dcf", "/eps-calculator", "/screener", "/compare", "/ipo", "/macro", "/results", "/news", "/premium", "/stocks/RELIANCE"];
const SIZES = [[1280, 800], [950, 900], [390, 800]];
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"], executablePath: process.env.CHROMIUM_PATH || undefined });
let failed = 0, checked = 0;
for (const theme of ["dark", "light"]) for (const [w, h] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 500, hasTouch: w < 500 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-plan", "gold"); localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  const p = await ctx.newPage();
  for (const path of PAGES) {
    await p.goto(base + path, { waitUntil: "load" }).catch(() => {});
    await p.waitForTimeout(500);
    // scroll the window and every scroll container down in steps
    await p.evaluate(async (vh) => {
      const boxes = [document.scrollingElement, ...[...document.querySelectorAll("*")].filter((e) => e.scrollHeight > e.clientHeight + 40 && /auto|scroll/.test(getComputedStyle(e).overflowY))];
      for (const b of boxes) { for (let y = 0; y < b.scrollHeight; y += vh * 0.6) { b.scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } b.scrollTo(0, b.scrollHeight); }
    }, h);
    await p.waitForTimeout(1500);
    const r = await p.evaluate(() => {
      const culprit = (el) => { for (let e = el; e && e !== document.documentElement; e = e.parentElement) if (parseFloat(getComputedStyle(e).opacity) < 0.99) return `${e.tagName.toLowerCase()}.${String(e.className).split(" ")[0]}`; return ""; };
      const eff = (el) => { let o = 1; for (let e = el; e && e !== document.documentElement; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
      const hidden = [];
      for (const el of document.querySelectorAll("h1, h2, h3, .rv, .card, .scard, .plan, .feat, [class*='sec-h']")) {
        const cs = getComputedStyle(el), b = el.getBoundingClientRect();
        if (b.width === 0 || b.height === 0 || cs.display === "none") continue;
        if (el.closest("[inert], [hidden], [aria-hidden='true']")) continue;
        const o = eff(el);
        if (o < 0.99 || cs.visibility === "hidden") hidden.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ").slice(0, 2).join(".")} "${(el.textContent || "").trim().slice(0, 30)}" opacity ${o.toFixed(2)} (from ${culprit(el)}) ${cs.visibility}`);
      }
      // empty bands: union of content rects (document coordinates)
      const sy = window.scrollY, iv = [];
      const h1 = document.querySelector("h1"), foot = document.querySelector("footer");
      const from = h1 ? h1.getBoundingClientRect().top + sy : 0, to = foot ? foot.getBoundingClientRect().top + sy : Infinity;
      for (const el of document.querySelectorAll("body *")) {
        if (el.closest("script, style, [aria-hidden='true'], .aurora, .pa")) continue;
        const cs = getComputedStyle(el); if (cs.display === "none" || cs.visibility === "hidden") continue;
        const tag = el.tagName.toLowerCase();
        let own = false;
        if (cs.backgroundImage !== "none" || ["Top", "Right", "Bottom", "Left"].some((d) => parseFloat(cs["border" + d + "Width"]) > 0 && cs["border" + d + "Style"] !== "none" && cs["border" + d + "Color"] !== "rgba(0, 0, 0, 0)")) own = true; // images and bordered boxes (cards) are visible content
        else if (["img", "svg", "canvas", "input", "button", "select", "textarea", "video", "iframe", "hr"].includes(tag)) own = true;
        else for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim()) own = true;
        if (!own) continue;
        const b = el.getBoundingClientRect(); if (b.height === 0 || b.width === 0) continue;
        if (b.bottom + sy < from || b.top + sy >= to - 1) continue;
        iv.push([b.top + sy, b.bottom + sy, `${tag}.${String(el.className).split(" ")[0]}`]);
      }
      iv.sort((a, b) => a[0] - b[0]);
      let end = iv.length ? iv[0][1] : 0, worst = 0, at = 0, prev = "", next = "", pn = iv.length ? iv[0][2] : "";
      for (const [s, e, n] of iv) { if (s - end > worst) { worst = s - end; at = end; prev = pn; next = n; } if (e > end) { end = e; pn = n; } }
      return { hidden, worst: Math.round(worst), at: Math.round(at), prev, next };
    });
    const bad = r.hidden.length > 0 || r.worst > MAXGAP; checked++;
    if (bad) failed++;
    console.log(`${bad ? "FAIL" : "ok  "} ${theme} ${w} ${path}  hidden:${r.hidden.length} gap:${r.worst}px@${r.at}${r.worst > MAXGAP ? ` (${r.prev} -> ${r.next})` : ""}${r.hidden.length ? "  e.g. " + r.hidden.slice(0, 3).join(" | ") : ""}`);
    if (shots && (path === "/research" || path === "/")) { await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(100); await p.screenshot({ path: `${shots}/${theme}-${w}${path.replace(/\W/g, "_")}.png` }); }
  }
  await ctx.close();
}
await browser.close();
console.log(`${checked - failed}/${checked} ok`);
process.exit(failed ? 1 : 0);
