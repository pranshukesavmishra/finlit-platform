// Earnings call section and dialog on the stock page, with every /api/** call mocked (no backend needed). The RELIANCE report comes from public/demo.
//   node e2e/earnings_call.mjs http://127.0.0.1:5199 /path/to/outdir      (CHROME=/path/to/chrome when Playwright's own browser is not installed)
// Checks: the section is in the nav, the dialog is a modal on <body> that closes on Esc, nothing scrolls sideways at 1280 / 1055 / 390, light and dark; saves screenshots.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const B = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), OUT = process.argv[3] || "/tmp/ec-shots";
const DEMO = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "demo", "RELIANCE");
fs.mkdirSync(OUT, { recursive: true });
let failed = 0;
const check = (name, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${name}${d ? "  - " + d : ""}`); };

const QS = [["strategy-moat", "Strategy & moat", "Strategy"], ["guidance-outlook", "Guidance & outlook", "Outlook"], ["margins-costs", "Margins & costs", "Margins"], ["demand-orders", "Demand & order book", "Demand"],
  ["capex-debt", "Capex & debt", "Capex and debt"], ["risks-raised", "Risks raised", "Risks"], ["management-changes", "Management changes", "Management"], ["what-changed", "What changed vs last quarter", "What changed"],
  ["capital-allocation", "Dividends & buybacks", "Capital allocation"], ["analyst-concerns", "What analysts pushed on", "Analyst questions"]].map(([id, label, title]) => ({ id, label, title }));
const call = (fy, q, o = {}) => ({ fiscalYear: fy, quarter: q, label: `Q${q} FY${String(fy % 100).padStart(2, "0")}`, callDate: "2026-10-20", filedAt: "2026-10-23", transcriptUrl: `https://nsearchives.nseindia.com/corporate/RELIANCE_${fy}${q}.pdf`, pages: 48, ...o });
const CALLS = [call(2027, 2), call(2027, 1, { callDate: "2026-07-24", filedAt: "2026-07-27", pages: 41 }), call(2026, 4, { callDate: "2026-04-25", filedAt: "2026-04-28", pages: 44 }), call(2026, 3, { callDate: "2026-01-17", filedAt: "2026-01-20", pages: 39 })];
const LIST = (locked) => ({ symbol: "RELIANCE", name: "Reliance Industries Ltd", available: true, locked, calls: CALLS, questions: QS, usage: locked ? null : { used: 1, limit: 5 },
  note: "AI-summarised from the transcript. Check the quotes.", disclaimer: "Information only, not investment advice." });
const S = (text, quote, ref) => ({ text, quote, quoteRef: ref });
const ANS = {
  "strategy-moat": [S("Management says it is pushing deeper into retail and digital services alongside its energy business.", "we continue to invest behind consumer businesses and digital services while the energy platform funds that growth", "page 4"),
    S("It points to its scale and integrated supply chain as the main source of its cost advantage.", "the scale of our integrated chain gives us a cost position that is very hard to replicate", "page 5"),
    S("Customer relationships built over many years are described as a barrier for new entrants.", "relationships we have built with our customers over two decades are not something a new player can copy quickly", "page 7")],
  "guidance-outlook": [S("Management expects the coming quarters to be steady, with growth led by consumer businesses.", "we expect the next few quarters to be steady with consumer businesses leading the growth", "page 9")],
  "risks-raised": [],
};
const DETAIL = (r, used) => ({ ...r, symbol: "RELIANCE", name: "Reliance Industries Ltd", usage: { used, limit: 5 }, summarisedByAi: true, note: LIST(false).note, notCovered: "The call did not cover this.", disclaimer: LIST(false).disclaimer,
  questions: QS.map((q) => ({ ...q, ready: q.id in ANS || ["margins-costs", "capex-debt"].includes(q.id), covered: (ANS[q.id] || []).length > 0, sentences: ANS[q.id] || [] })).map((q) => (q.id === "margins-costs" ? { ...q, covered: false } : q.id === "capex-debt" ? { ...q, covered: false } : q)) });

async function open(browser, { w, theme, plan = "gold", mode = "ok" }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, colorScheme: theme });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); sessionStorage.clear(); } catch {} }, theme);
  const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
  await p.route("**/api/**", async (r) => {
    const u = new URL(r.request().url()), pt = u.pathname, json = (b, s = 200) => r.fulfill({ status: s, contentType: "application/json", body: JSON.stringify(b) });
    if (pt === "/api/auth/me") return json({ user: { id: "u1", email: "a@b.c", name: "Asha", role: "investor", plan, verified: true, mfa: false, mfaOk: false }, plan, csrf: "t", limits: {}, showcase: ["RELIANCE"] });
    let m = /^\/api\/earnings-calls\/RELIANCE$/.exec(pt);
    if (m) return mode === "none" ? json({ ...LIST(false), available: false, calls: [] }) : json(LIST(plan !== "gold"));
    m = /^\/api\/earnings-calls\/RELIANCE\/(\d+)\/(\d)$/.exec(pt);
    if (m) {
      if (plan !== "gold") return json({ detail: { status: "plan_required", plan: "gold" } }, 403);
      if (mode === "limit") return json({ detail: { status: "limit_reached", detail: "x", used: 5, limit: 5, plan: "gold" } }, 403);
      return json(DETAIL(CALLS.find((c) => c.fiscalYear === +m[1] && c.quarter === +m[2]), 1 + CALLS.findIndex((c) => c.fiscalYear === +m[1] && c.quarter === +m[2])));
    }
    m = /^\/api\/stocks\/RELIANCE(?:\/([a-z0-9-]+))?$/.exec(pt);
    if (m) {
      const f = m[1] ? (m[1] === "price" ? `price-${(u.searchParams.get("range") || "1Y").toUpperCase()}` : m[1]) : "summary";
      const file = path.join(DEMO, f + ".json");
      return fs.existsSync(file) ? r.fulfill({ status: 200, contentType: "application/json", body: fs.readFileSync(file, "utf8") }) : json({ detail: { status: "not_found" } }, 404);
    }
    return json(/notifications|alerts|indices|companies|feed|ipos/.test(pt) ? [] : {}, pt.startsWith("/api/stocks") ? 404 : 200);
  });
  await p.goto(B + "/stocks/RELIANCE", { waitUntil: "domcontentloaded" });
  await p.waitForSelector("#earnings-call", { timeout: 30000 });
  return { ctx, p, errs };
}
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - innerWidth);

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined, args: ["--disable-dev-shm-usage", "--no-sandbox"] });
try {
  for (const w of [1280, 1055, 390]) for (const theme of ["light", "dark"]) {
    const tag = `${w}-${theme}`;
    const { ctx, p, errs } = await open(browser, { w, theme });
    await p.waitForSelector(".ec-card .ec-top", { timeout: 15000 });
    await p.locator("#earnings-call").scrollIntoViewIfNeeded();
    await p.waitForTimeout(400);
    check(`${tag}: the section is on the page and in the section bar`, (await p.locator('nav[aria-label="Sections"] a[data-s="earnings-call"]').count()) === 1);
    check(`${tag}: no sideways scroll on the page`, (await overflow(p)) <= 1, String(await overflow(p)));
    await p.screenshot({ path: `${OUT}/section-${tag}.png`, clip: undefined, fullPage: false });
    await p.getByRole("button", { name: "Read the call summary" }).click();
    const dlg = p.getByRole("dialog");
    await dlg.waitFor();
    await p.getByRole("article", { name: "Strategy & moat" }).waitFor();
    check(`${tag}: the dialog is a modal on <body>`, await p.evaluate(() => { const d = document.querySelector(".ec-dlg"); return d?.parentElement === document.body && d.getAttribute("aria-modal") === "true"; }));
    const surf = await p.evaluate(() => { const d = document.querySelector(".ec-dlg"), c = getComputedStyle(d); return { bg: c.backgroundColor, z: c.zIndex, box: d.getBoundingClientRect().toJSON() }; });
    check(`${tag}: opaque surface above the header`, /^rgb\(/.test(surf.bg) && Number(surf.z) >= 310, `${surf.bg} z${surf.z}`);
    check(`${tag}: the dialog fits the screen`, surf.box.left >= -1 && surf.box.right <= w + 1 && surf.box.bottom <= (w > 600 ? 900 : 844) + 1, JSON.stringify([surf.box.left, surf.box.right, surf.box.bottom].map(Math.round)));
    const wide = await p.evaluate(() => [...document.querySelector(".ec-dlg").querySelectorAll("*")].filter((e) => e.scrollWidth > e.clientWidth + 1 && !["auto", "scroll"].includes(getComputedStyle(e).overflowX) && e.tagName !== "SELECT" && !e.closest(".sr")).map((e) => `${e.tagName}.${e.className} ${e.scrollWidth}>${e.clientWidth}`).slice(0, 5));
    check(`${tag}: nothing in the dialog scrolls sideways`, wide.length === 0, wide.join(" | "));
    if (w < 600) await p.screenshot({ path: `${OUT}/dialog-top-${tag}.png` });
    await dlg.getByRole("button", { name: "Show the quote" }).first().click();
    await p.waitForTimeout(250);
    await p.screenshot({ path: `${OUT}/dialog-${tag}.png` });
    if (w === 1280 && theme === "light") {
      await dlg.getByRole("button", { name: /^Q1$/ }).click();
      await p.waitForFunction(() => document.querySelector(".ec-head h3")?.textContent?.includes("Q1 FY27"));
      await dlg.getByRole("button", { name: "Risks raised" }).click();
      await p.getByRole("article", { name: "Risks raised" }).waitFor();
      check(`${tag}: "not covered" is said in words`, (await p.locator(".ec-none").innerText()) === "The call did not cover this.");
      await p.screenshot({ path: `${OUT}/dialog-notcovered-${tag}.png` });
    }
    await p.keyboard.press("Escape");
    check(`${tag}: Esc closes the dialog`, await p.getByRole("dialog").count() === 0);
    check(`${tag}: no page errors`, errs.length === 0, errs.join("|"));
    await ctx.close();
  }
  // other states, light, 1280 and 390
  for (const [name, o] of [["locked", { plan: "silver" }], ["limit", { mode: "limit" }], ["none", { mode: "none" }]]) for (const w of [1280, 390]) {
    const { ctx, p, errs } = await open(browser, { w, theme: "light", ...o });
    if (name === "none") {
      await p.waitForSelector(".ec-state");
      check(`${name}-${w}: says the summaries are not available yet`, (await p.locator(".ec-card").innerText()).includes("Earnings-call summaries are not available yet"));
      await p.locator("#earnings-call").scrollIntoViewIfNeeded(); await p.waitForTimeout(300);
      await p.screenshot({ path: `${OUT}/state-${name}-${w}.png` });
    } else {
      await p.getByRole("button", { name: name === "locked" ? /See what is inside/ : /Read the call summary/ }).click();
      await p.getByRole("dialog").waitFor();
      await p.waitForSelector(name === "locked" ? ".ec-gate" : '.ec-state[role="alert"]');
      check(`${name}-${w}: shows no answer text`, !(await p.getByRole("dialog").innerText()).includes("scale of our integrated chain"));
      await p.waitForTimeout(250);
      await p.screenshot({ path: `${OUT}/state-${name}-${w}.png` });
    }
    check(`${name}-${w}: no sideways scroll, no page errors`, (await overflow(p)) <= 1 && errs.length === 0, errs.join("|"));
    await ctx.close();
  }
} finally { await browser.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
