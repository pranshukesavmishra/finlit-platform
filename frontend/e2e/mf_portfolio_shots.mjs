// MF portfolio screenshots with every /api/** call mocked (no backend needed):
//   node e2e/mf_portfolio_shots.mjs http://localhost:5199 /path/to/outdir
import { chromium } from "playwright";
import fs from "node:fs";
const B = process.argv[2] || "http://localhost:5199", OUT = process.argv[3] || "/tmp/mf-shots";
fs.mkdirSync(OUT, { recursive: true });
const fund = (code, name, amc, plan = "Direct", option = "Growth") => ({ code, name, amc, plan, option, active: true, navDate: "2026-10-29" });
const LOCK = { locked: true, final: null, label: null, status: null, reason: null, runDate: null, parts: null, inherited: null };
const sc = (f, p, r, c, q, label) => ({ locked: false, final: f, label, status: "RATED", reason: null, runDate: "2026-10-30", parts: { performance: p, risk: r, cost: c, quality: q }, inherited: null });
const row = (id, code, name, amc, cat, units, inv, nav, o = {}) => {
  const current = Math.round(units * nav * 100) / 100, gain = inv == null ? null : Math.round((current - inv) * 100) / 100;
  return { id, code, folio: o.folio || "", units, lots: [], name, amc, plan: "Direct", option: "Growth", category: cat, categoryLabel: cat, active: true, nav, navDate: "2026-10-29", navStale: false, navNote: null,
    invested: inv, investedWhy: inv == null ? "The amount paid is not known. Add it to see the gain." : null, current, currentWhy: null, gain, gainPct: gain == null ? null : Math.round(gain / inv * 10000) / 100,
    gainWhy: inv == null ? "The amount paid is not known. Add it to see the gain." : null, xirr: o.xirr ?? null, xirrWhy: o.xirr ? null : "Add the purchase date to see the XIRR.", xirrKind: "cagr",
    returns: { r1y: o.r1 ?? 12.4, r3y: o.r3 ?? 15.1, r5y: o.r5 ?? 16.2, asOf: "2026-10-29", why: null }, ter: o.ter ?? 0.62, terDate: null, terWhy: null, aum: o.aum ?? 41234, aumAsOf: null, aumWhy: null,
    weight: o.w, weightWhy: null, score: o.score };
};
const holdings = (locked) => [
  row("1", 100001, "Alpha Bluechip Fund - Direct Plan - Growth", "Alpha Mutual Fund", "Large Cap", 1200.5, 120000, 150.25, { w: 54.1, xirr: 14.2, score: locked ? LOCK : sc(83.4, 80, 85, 90, 77, "Strong"), folio: "1234567/89" }),
  row("2", 100002, "Beta Flexi Cap Fund - Direct Plan - Growth", "Beta Mutual Fund", "Flexi Cap", 800, 50000, 80.5, { w: 19.3, score: locked ? LOCK : sc(64.2, 60, 62, 70, 66, "Average") }),
  row("3", 100003, "Delta Small Cap Fund - Direct Plan - Growth", "Delta Mutual Fund", "Small Cap", 500, null, 120, { w: 18, r5y: null, aum: null, score: locked ? LOCK : { ...sc(null, null, null, null, null, null), final: null, status: "NOT SCORED", reason: "Not scored yet: the daily score run has not reached this scheme.", parts: null } }),
  row("4", 100004, "Gamma Liquid Fund - Direct Plan - Growth", "Gamma Mutual Fund", "Liquid", 100, 30000, 300, { w: 8.6, r3y: 6.8, r5y: 5.9, ter: 0.2, aum: 8000, score: locked ? LOCK : sc(41.0, 45, 30, 50, 40, "Weak") }),
];
const share = (a) => { const t = a.reduce((s, x) => s + x[1], 0); return a.map(([label, value]) => ({ label, value, pct: Math.round(value / t * 1000) / 10 })); };
const view = (locked, hs) => {
  const cur = hs.reduce((s, h) => s + h.current, 0);
  const costed = hs.filter((h) => h.invested != null), inv = costed.reduce((s, h) => s + h.invested, 0), cc = costed.reduce((s, h) => s + h.current, 0);
  return { plan: locked ? "silver" : "gold", scoreLocked: locked, limit: locked ? 30 : 500, count: hs.length, dataDate: "2026-10-29", holdings: hs,
    summary: { funds: hs.length, valued: hs.length, withCost: costed.length, gainFunds: costed.length, invested: inv, current: cur, gain: cc - inv, gainPct: Math.round((cc - inv) / inv * 10000) / 100, navFrom: "2026-10-29", navTo: "2026-10-29",
      notes: ["The gain covers 3 of 4 valued funds: the others have no amount paid."], xirr: 14.2, xirrFunds: 1, xirrWhy: null,
      score: locked ? { locked: true, value: null, label: null, why: null } : { locked: false, value: null, label: null, why: "1 of 4 funds has no score, so a portfolio score is not shown." } },
    allocation: { byCategory: share(hs.map((h) => [h.categoryLabel, h.current])), byAmc: share(hs.map((h) => [h.amc, h.current])) },
    concentration: { level: "concentrated", top1Pct: 54.1, top3Pct: 91.4, text: "Your largest fund, Alpha Bluechip Fund - Direct Plan - Growth, is 54.1% of the current value; the three largest together are 91.4%. The value rests on very few funds. Different funds can hold the same shares; this counts funds, not what is inside them." },
    disclaimer: "Information only, not investment advice.", scoreDisclaimer: "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation." };
};
const preview = { total: 6, counts: { matched: 2, choose: 1, not_found: 1, ignored: 1, invalid: 0, duplicate: 1 }, capacity: { limit: 30, used: 0, room: 30 }, disclaimer: "x", rows: [
  { i: 0, row: 6, name: "Axis Bluechip Fund - Direct Plan - Growth", isin: "INF846K01DP8", folio: "1234567890/12", units: 2345.678, invested: 125000, boughtOn: null, status: "matched", via: "isin", reason: "", warnings: [], fund: fund(100001, "Axis Bluechip Fund - Direct Plan - Growth", "Axis Mutual Fund"), candidates: [], existing: false },
  { i: 1, row: 7, name: "Delta Small Cap Fund", isin: "", folio: "", units: 10, invested: 500, boughtOn: "2022-03-15", status: "matched", via: "name", reason: "", warnings: [], fund: fund(100003, "Delta Small Cap Fund - Direct Plan - Growth", "Delta Mutual Fund"), candidates: [], existing: true },
  { i: 2, row: 8, name: "Alpha Bluechip Fund", isin: "", folio: "", units: 10, invested: null, boughtOn: null, status: "choose", via: "name", reason: "The name does not say Direct or Regular, or Growth or IDCW, and this fund has more than one plan or option. Choose yours.", warnings: [], fund: null, candidates: [fund(100001, "Alpha Bluechip Fund - Direct Plan - Growth", "Alpha"), fund(100002, "Alpha Bluechip Fund - Regular Plan - Growth", "Alpha", "Regular")] },
  { i: 3, row: 9, name: "Zzz Imaginary Fund", isin: "", folio: "", units: 10, invested: null, boughtOn: null, status: "not_found", via: null, reason: "No fund with this name was found. Search for it below.", warnings: [], fund: null, candidates: [] },
  { i: 4, row: 10, name: "Reliance Industries Ltd", isin: "INE002A01018", status: "ignored", reason: "A company share or bond (its ISIN starts with INE), not a mutual fund.", warnings: [], fund: null, candidates: [] },
  { i: 5, row: 11, name: "Axis Bluechip Fund - Direct Plan - Growth", isin: "INF846K01DP8", status: "duplicate", reason: "The same line as row 6 of the file (same fund, folio, units, amount and date): counted once.", warnings: [], fund: null, candidates: [] },
] };

async function shoot(browser, plan, scenario, w, theme) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, colorScheme: theme });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
  await p.route("**/api/**", async (r) => {
    const u = new URL(r.request().url()), path = u.pathname, json = (b, s = 200) => r.fulfill({ status: s, contentType: "application/json", body: JSON.stringify(b) });
    if (path === "/api/auth/me") return json({ user: { id: "u1", email: "a@b.c", name: "Asha", role: "investor", plan, verified: true, mfa: false, mfaOk: false }, plan, csrf: "t", limits: { holdings: 30, mf_holdings: plan === "gold" ? 500 : 30 }, showcase: [] });
    if (path === "/api/me/mf-portfolio") return json(scenario === "empty" ? { ...view(plan !== "gold", []), summary: view(plan !== "gold", holdings(true)).summary, count: 0, holdings: [] } : view(plan !== "gold", holdings(plan !== "gold")));
    if (path === "/api/me/mf-portfolio/import-preview") return json(preview);
    if (path === "/api/mf") return json({ items: [fund(100009, "Search Result Fund - Direct Plan - Growth", "Sample Mutual Fund")] });
    return json({}, 404);
  });
  await p.goto(B + "/mf-portfolio", { waitUntil: "networkidle" }).catch(() => {});
  await p.waitForSelector("h1", { timeout: 15000 });
  if (scenario === "import") {
    await p.getByRole("tab", { name: "Import a file" }).click();
    fs.writeFileSync(OUT + "/cams.csv", "Folio No,Scheme Name,ISIN,Closing Unit Balance,Cost Value\n1,Axis Bluechip Fund,INF846K01DP8,10,100\n");
    await p.locator('input[type=file]').setInputFiles(OUT + "/cams.csv");
    await p.waitForSelector(".mp-review", { timeout: 10000 });
  } else if (scenario === "empty") await p.waitForSelector(".dw-empty");
  else await p.waitForSelector(".mp-t");
  await p.waitForTimeout(500);
  const over = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (over > 1) console.log(await p.evaluate(() => { let e = document.querySelector(".mp-tablewrap"), o = []; while (e && e !== document.body) { o.push(e.tagName + "." + e.className + " w" + Math.round(e.getBoundingClientRect().width) + " " + getComputedStyle(e).display + " ov" + getComputedStyle(e).overflowX); e = e.parentElement; } return o; }));
  console.log(await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > innerWidth + 2 && !e.closest(".mp-tablewrap")).slice(0, 6).map((e) => e.tagName + "." + e.className + " " + Math.round(e.getBoundingClientRect().right))));
  const name = `${scenario}-${plan}-${w}-${theme}.png`;
  await p.screenshot({ path: `${OUT}/${name}`, fullPage: true });
  console.log(name, "overflow", over, errs.length ? errs : "");
  await ctx.close();
}
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome", args: ["--disable-dev-shm-usage"] });
for (const [theme, w] of [["light", 1280], ["dark", 1280], ["light", 390], ["dark", 390]]) {
  await shoot(browser, "gold", "empty", w, theme);
  await shoot(browser, "gold", "import", w, theme);
  await shoot(browser, "gold", "full", w, theme);
  await shoot(browser, "silver", "full", w, theme);
}
await browser.close();
