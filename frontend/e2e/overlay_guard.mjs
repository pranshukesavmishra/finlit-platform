// OVERLAY GUARD: opens every overlay surface (dialogs, drawers, menus, popovers, tips, toasts, trays) in light and dark at
// 1280, 947 and 390 px and fails when one is see-through, covered by page content, clipped off screen, lacks a dim backdrop
// or (for modals) does not close on Esc / lock page scroll / hold focus.
//
//   VITE_DEMO=1 npm run dev -- --port 5301      (demo mode answers /api/** from saved files and signs in as a Gold member)
//   npm run overlay-guard -- http://127.0.0.1:5301
//   SHOTS=/some/dir  saves a screenshot of every overlay;  ONLY=alert,leadtip  limits the run;  CHROME=/path/to/chrome
//
// Pass criteria per overlay (the "surface" is the floating box itself):
//   opaque     computed background alpha == 1 on the surface (or on an opaque ancestor layer that fully covers it)
//   on-top     elementsFromPoint on a 5x5 grid of the surface: the topmost element is the surface or one of its children,
//              so no page text/controls are painted above or visible through it
//   in-view    the surface lies inside the viewport (1px tolerance)
//   backdrop   (modals/drawers) a full-viewport scrim, alpha >= .5, painted below the surface and above the header
//   modal      Esc closes it, the page is scroll-locked while open, focus is inside it
//   no-cover   (tips) it does not sit on top of another button/link/field
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const B = (process.argv[2] || process.env.BASE || "http://127.0.0.1:5301").replace(/\/$/, "");
const SHOTS = process.env.SHOTS || "";
const ONLY = (process.env.ONLY || "").split(",").filter(Boolean);
const FULL = process.env.FULL === "1";   // adds the laptop widths 1229/1093/1055/945, GPU-off rendering and Windows scaling 125% / 150%
const SIZES = (process.env.SIZES || (FULL ? "1280x800,1229x800,1093x800,1055x800,947x800,945x800,390x800" : "1280x800,947x800,390x800")).split(",").map((s) => s.split("x").map(Number));
const THEMES = (process.env.THEMES || "dark,light").split(",");
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

let fails = 0, passes = 0, skips = 0;
const out = (ok, name, why = "") => { if (ok) passes++; else fails++; console.log((ok ? "PASS " : "FAIL ") + name + (why ? " - " + why : "")); };

/** A control that opens an overlay. `open` runs on the page; `surface` is the CSS selector of the floating box. */
const click = (sel, opts = {}) => async (p) => { const l = p.locator(sel).first(); await l.scrollIntoViewIfNeeded().catch(() => {}); await l.click({ timeout: 4000, ...opts }); };
const hover = (sel) => async (p) => { const l = p.locator(sel).first(); await l.scrollIntoViewIfNeeded().catch(() => {}); await l.hover({ timeout: 4000 }); };
const OVERLAYS = [
  { id: "alert", kind: "modal", path: "/stocks/RELIANCE", surface: ".alx-modal", open: click("button:has-text('Set alert')") },
  { id: "leadtip", kind: "tip", path: "/stocks/RELIANCE", surface: ".ld-tip", open: hover(".ld-tipw button.info") },
  { id: "download", kind: "menu", path: "/stocks/RELIANCE", surface: ".dl-menu", open: click(".dl > button") },
  { id: "chart-help", kind: "tip", path: "/stocks/RELIANCE", surface: ".chh-p:not([hidden])", coverOk: true, open: hover(".chh-b >> visible=true") },
  { id: "glossary-info", kind: "tip", path: "/stocks/RELIANCE", surface: ".pop:not([hidden])", open: hover("button.info:not(.ld-tipw button)") },
    { id: "notifications", kind: "menu", path: "/dashboard", surface: ".nt-p", open: click(".nt-btn") },
  { id: "account-menu", kind: "menu", path: "/dashboard", surface: ".ddm.open[role=menu], .ddm.open.right", open: click(".av-btn, .top .avatar, button[aria-label*='ccount']") },
  { id: "nav-menu", kind: "menu", path: "/", surface: ".ddm.open", open: hover(".top nav button.ddb"), desktopOnly: true },
  { id: "search", kind: "modal", path: "/", surface: ".gs", open: click("button[aria-label^='Search stocks']"), backdrop: ".gs-scrim" },
  { id: "assistant", kind: "drawer", path: "/", surface: ".ai", open: click(".ai-fab"), noBackdrop: true },
  { id: "compare-search", kind: "menu", path: "/compare?c=RELIANCE,TCS", surface: ".cb-menu", open: click(".cb-field input") },
  { id: "ipo-drawer", kind: "drawer", path: "/ipo", surface: ".ipo-dr-bg > *", open: click(".ipo-row, .ipo-card, table tbody tr"), backdrop: ".ipo-dr-bg" },
  { id: "query-columns", kind: "drawer", path: "/query-builder", surface: ".qb-drawer", open: click("button:has-text('All ratios'), button:has-text('Browse'), button:has-text('ratios')"), backdrop: ".qb-scrim" },
  { id: "mobile-tabs", kind: "bar", path: "/", surface: ".mtabs", open: async () => {}, mobileOnly: true },
  { id: "mobile-menu", kind: "drawer", path: "/dashboard", surface: ".side", open: click(".shell-fab"), backdrop: ".shell-scrim", mobileOnly: true },
];


// The leadership line (and its (i) tip) needs weekly peer data that demo mode does not hold: answer that one call with a fixed payload.
const LEADERSHIP = { available: true, asOf: "2026-10-30", stale: false, held: false, peerGroup: { id: "x", name: "Petroleum", short: "petroleum", kind: "industry", ranked: 6 },
  benchmarks: { sector: { code: "NIFTYOG", name: "Nifty Oil & Gas", kind: "index", ret52: -0.02 }, market: null }, rel: { w13: -2, w26: -4, w52: -7.3, w52Market: null }, rank: 5, label: "Laggard", rawLabel: "Laggard", direction: "gaining",
  fundamentalNote: null, fundamentalRank: null, fundamentalOf: null, labelSince: null, sectorReliability: { tier: "mixed", hitRate6m: 0.6, checks: 20, from: null, to: null, periods: [] }, peers: [],
  display: { chip: "Laggard", line: "Laggard 5th of 6 petroleum peers", note: null, tooltip: "Based on price performance over the last 12 months compared with 6 petroleum companies and Nifty Oil & Gas. Describes the past; not a recommendation.",
    parts: { rank: "Laggard 5th of 6 petroleum peers", sector: { pts: "-7.3", name: "Nifty Oil & Gas", v: -7.3 }, market: null, direction: "gaining" } } };

const rgba = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return [0, 0, 0, 0]; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };

/** Everything measured inside the page, returned as plain data. */
async function measure(p, o) {
  return p.evaluate(({ sel, kind, backdrop }) => {
    const els = [...document.querySelectorAll(sel)].filter((e) => { const r = e.getBoundingClientRect(); const c = getComputedStyle(e); return r.width > 20 && r.height > 20 && c.visibility !== "hidden" && c.display !== "none"; });
    const el = els[0]; if (!el) return null;
    const r = el.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = innerHeight;
    const layers = []; for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const c = getComputedStyle(e); layers.push({ bg: c.backgroundColor, img: c.backgroundImage, op: c.opacity, bf: c.backdropFilter, tag: e.tagName + "." + String(e.className).slice(0, 24) }); if (e === el) { /* own layer first */ } }
    const inside = (n) => n && (n === el || el.contains(n));
    const bad = []; let sampled = 0;
    const x0 = Math.max(0, r.left), x1 = Math.min(vw - 1, r.right), y0 = Math.max(0, r.top), y1 = Math.min(vh - 1, r.bottom);
    for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) {
      const x = x0 + (x1 - x0) * (0.06 + 0.88 * i / 4), y = y0 + (y1 - y0) * (0.06 + 0.88 * j / 4); sampled++;
      const top = document.elementFromPoint(x, y); if (!inside(top) && !(top && top.closest(".alx-toasts, .toast, .mtabs, .shell-fab, .ai-fab"))) bad.push((top ? top.tagName + "." + String(top.className).slice(0, 24) : "none") + "@" + Math.round(x) + "," + Math.round(y));
    }
    // a tip must not sit on another control
    const covered = []; if (kind === "tip") document.querySelectorAll("button, a[href], input, select, textarea, [role=button], [role=tab]").forEach((c) => {
      if (inside(c) || c.contains(el)) return; if (c.closest(".ld-tipw, .chh, .pcx-i, .info") && c.matches(".info, .chh-b")) { /* the anchor itself */ }
      const a = c.getBoundingClientRect(); if (a.width < 4 || a.height < 4) return;
      const ox = Math.min(a.right, r.right) - Math.max(a.left, r.left), oy = Math.min(a.bottom, r.bottom) - Math.max(a.top, r.top);
      if (ox > 4 && oy > 4 && (ox * oy) / (a.width * a.height) > 0.25) { const cs = getComputedStyle(c); if (cs.visibility !== "hidden" && !c.matches(".chh-b, .info, .pcx-i")) covered.push((c.textContent || c.getAttribute("aria-label") || c.tagName).trim().slice(0, 24)); }
    });
    let bd = null; if (backdrop || kind === "modal" || kind === "drawer") {
      const cands = [...document.querySelectorAll(backdrop || ".scrim, .shell-scrim, .qb-scrim, .sx-back, .ipo-dr-bg, .gs-scrim")];
      const s = cands.find((e) => { const b = e.getBoundingClientRect(); return b.width >= vw - 1 && b.height >= vh - 1; });
      if (s) { const c = getComputedStyle(s); bd = { bg: c.backgroundColor, z: c.zIndex }; }
    }
    const cz = getComputedStyle(el).zIndex, header = document.querySelector(".top"), hz = header ? getComputedStyle(header).zIndex : "0";
    return { rect: { l: r.left, t: r.top, r: r.right, b: r.bottom }, vw, vh, layers, bad, sampled, covered, bd, z: cz, hz, overflow: getComputedStyle(document.body).overflow, active: !!(document.activeElement && el.contains(document.activeElement)), count: els.length };
  }, { sel: o.surface, kind: o.kind, backdrop: o.backdrop || "" });
}

/** The surface is opaque when its own colour has alpha 1, or an ancestor layer under it does (and nothing in between is faded). */
function opaque(m) {
  for (const L of m.layers) { if (Number(L.op) < 1) return { ok: false, why: `${L.tag} has opacity ${L.op}` }; const [, , , a] = rgba(L.bg); if (a >= 0.999) return { ok: true }; if (a > 0 && a < 0.999) return { ok: false, why: `${L.tag} background ${L.bg}` }; if (L.img && L.img !== "none") return { ok: true, note: "image" }; }
  return { ok: false, why: "no background colour (transparent)" };
}

async function run(browser, theme, [w, h], dpr = 1, tag = "") {
  for (const o of OVERLAYS) {
    if (ONLY.length && !ONLY.includes(o.id)) continue;
    if (o.desktopOnly && w < 900) continue; if (o.mobileOnly && w >= 900) continue;
    const name = `${o.id} @${w} ${theme}${tag}`;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme, deviceScaleFactor: dpr });
    await ctx.addInitScript((t) => { try { localStorage.setItem("theme", t); localStorage.setItem("finlit-theme", t); localStorage.setItem("fl-theme", t); } catch {} }, theme);
    await ctx.route(/\/RELIANCE\/leadership(\.json)?(\?.*)?$|\/api\/stocks\/[^/]+\/leadership(\?.*)?$/, (r) => r.fulfill({ json: LEADERSHIP }));
    const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 120)));
    try {
      await p.goto(B + o.path, { waitUntil: "load", timeout: 30000 }).catch(() => {});
      await p.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      await p.waitForTimeout(2200);
      try { await o.open(p); } catch (e) { skips++; console.log("SKIP " + name + " - could not open (" + String(e.message).split("\n")[0].slice(0, 70) + ")"); continue; }
      await p.waitForTimeout(450);
      await p.waitForFunction((sel) => { const e = document.querySelector(sel); return !e || Number(getComputedStyle(e).opacity) >= 0.99; }, o.surface, { timeout: 2500 }).catch(() => {});   // let the open animation finish
      const m = await measure(p, o);
      if (!m) { skips++; console.log("SKIP " + name + " - surface " + o.surface + " not visible"); continue; }
      const problems = [];
      const op = opaque(m); if (!op.ok) problems.push("TRANSLUCENT: " + op.why);
      if (m.bad.length) problems.push(`covered by/see-through to ${m.bad.length}/${m.sampled} points: ${m.bad.slice(0, 3).join(" ")}`);
      const tol = 1; if (m.rect.l < -tol || m.rect.t < -tol || m.rect.r > m.vw + tol || (o.kind !== "menu" && m.rect.b > m.vh + tol)) problems.push(`off-screen rect ${[m.rect.l, m.rect.t, m.rect.r, m.rect.b].map(Math.round)} in ${m.vw}x${m.vh}`);
      if (m.covered.length && !o.coverOk) problems.push("covers controls: " + m.covered.join(", "));
      if ((o.kind === "modal" || o.kind === "drawer") && !o.noBackdrop) {
        if (!m.bd) problems.push("no full-viewport backdrop"); else { const a = rgba(m.bd.bg)[3]; if (a < 0.5) problems.push("backdrop too light: " + m.bd.bg); if (Number(m.bd.z) >= Number(m.z) && !isNaN(Number(m.z))) problems.push(`backdrop z ${m.bd.z} not below surface z ${m.z}`); if (Number(m.bd.z) <= Number(m.hz)) problems.push(`backdrop z ${m.bd.z} not above header z ${m.hz}`); }
      }
      if (o.kind === "modal") {
        if (m.overflow !== "hidden") problems.push("page is not scroll-locked (body overflow " + m.overflow + ")");
        if (!m.active) problems.push("focus is not inside the dialog");
      }
      if (SHOTS) await p.screenshot({ path: `${SHOTS}/${o.id}-${w}-${theme}${tag.replace(/\W+/g, "")}.png`, timeout: 15000, animations: "disabled", caret: "initial" }).catch((e) => console.log("shot failed " + e.message.slice(0, 60)));
      if (o.kind === "modal" || o.kind === "drawer" || o.kind === "menu") {
        await p.keyboard.press("Escape"); await p.waitForTimeout(350);
        const still = await p.evaluate((sel) => [...document.querySelectorAll(sel)].some((e) => { const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 20 && getComputedStyle(e).visibility !== "hidden"; }), o.surface);
        if (still && o.kind !== "menu") problems.push("Esc does not close it");
      }
      out(problems.length === 0, name, problems.join(" | "));
    } catch (e) { out(false, name, "guard error: " + String(e.message).slice(0, 100)); }
    finally { await ctx.close(); }
  }
}

const exe = process.env.CHROME || undefined;
// GPU-off = software rendering as on remote desktops / old GPUs / hardware acceleration disabled: backdrop-filter is not honoured there
const NOGPU = ["--disable-gpu", "--disable-gpu-compositing", "--disable-software-rasterizer"];
const VARIANTS = FULL ? [{ tag: "", args: [], dpr: 1 }, { tag: " [no-gpu dpr1.25]", args: NOGPU, dpr: 1.25 }, { tag: " [no-gpu dpr1.5]", args: NOGPU, dpr: 1.5 }]
  : process.env.NOGPU === "1" ? [{ tag: " [no-gpu]", args: NOGPU, dpr: 1 }] : [{ tag: "", args: [], dpr: 1 }];
for (const v of VARIANTS) {
  const browser = await chromium.launch({ executablePath: exe, args: ["--disable-dev-shm-usage", ...v.args] });
  for (const theme of THEMES) for (const s of SIZES) await run(browser, theme, s, v.dpr, v.tag);
  await browser.close();
}
console.log(`\n${passes} passed, ${fails} failed, ${skips} skipped`);
process.exit(fails ? 1 : 0);
