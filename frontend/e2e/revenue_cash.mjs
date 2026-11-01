// Revenue-to-Cash Intelligence on the stock page, in a real browser, with the saved demo report as the base and /demo/RELIANCE files replaced per case
// (a negative-cash company with a gap year, a lender, a Basic plan). Screenshots are written to OUT and looked at by eye.
//   VITE_DEMO=1 npx vite build --outDir <dir> && npx vite preview --outDir <dir> --port 5197 --host 127.0.0.1 &
//   CHROME=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome node e2e/revenue_cash.mjs http://127.0.0.1:5197 <outDir for screenshots>
import { chromium } from "playwright";
import fs from "node:fs";

const B = (process.argv[2] || "http://127.0.0.1:5197").replace(/\/$/, "");
const OUT = process.argv[3] || ".rcx-shots";
fs.mkdirSync(OUT, { recursive: true });
const real = (f) => JSON.parse(fs.readFileSync(new URL("../public/demo/RELIANCE/" + f, import.meta.url), "utf8"));
let fails = 0;
const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " - " + x : "")); };

/** The spec's company: FY26 revenue +57.9%, OCF -101 on 1,579 (-6.4%), receivables +89%, inventory +102.3%; FY24 operating cash flow missing (a gap). */
function stressFinancials() {
  const f = real("financials.json");
  const set = (t, k, vals) => { t.rows[k] = vals; };
  set(f.yearly.pl, "revenue", [800, 850, 900, 1000, 1100, 1250, 1000, 1579]);
  set(f.yearly.pl, "net_profit", [60, 62, 64, 70, 75, 80, 60, 90]);
  f.yearly.cf.periods = ["FY22", "FY23", "FY24", "FY25", "FY26"]; f.yearly.cf.periodEnds = f.yearly.cf.periods.map((p) => `20${p.slice(2)}-03-31`);
  set(f.yearly.cf, "operating", [60, 55, null, 40, -101]);
  set(f.yearly.cf, "capex", [-30, -30, -30, -40, -60]);
  set(f.yearly.cf, "free_cash_flow", [30, 25, null, 0, -161]);
  const nulls = (arr) => arr.map(() => null);
  set(f.yearly.bs, "receivables", [...nulls(f.yearly.bs.periods.slice(0, 6)), 100, 189]);
  set(f.yearly.bs, "inventories", [...nulls(f.yearly.bs.periods.slice(0, 6)), 100, 202.3]);
  return f;
}
const lenderSummary = () => { const s = real("summary.json"); s.dataQuality.isBank = true; return s; };

async function page(browser, { width, theme, plan = "gold", financials, summary }) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  await ctx.addInitScript(([th, pl]) => { try { localStorage.setItem("finlit-theme", th); localStorage.setItem("finlit-plan", pl); } catch {} }, [theme, plan]);
  if (financials) await ctx.route("**/demo/RELIANCE/financials.json", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(financials) }));
  if (summary) await ctx.route("**/demo/RELIANCE/summary.json", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(summary) }));
  const p = await ctx.newPage(); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 200)));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) p.errs.push(m.text().slice(0, 200)); });
  await p.goto(B + "/stocks/RELIANCE", { waitUntil: "networkidle" });
  await p.locator("#revenue-cash").waitFor({ timeout: 20000 });
  await p.locator("#revenue-cash").scrollIntoViewIfNeeded();
  await p.waitForTimeout(400);
  return { ctx, p };
}
const sideways = (p) => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const clipped = (p) => p.evaluate(() => { const c = document.querySelector("#revenue-cash"); const r = c.getBoundingClientRect(); return [...c.querySelectorAll("*")].filter((e) => { if (e.closest("svg") || e.closest("[role=tooltip]") || e.closest(".rcx-tblw") || e.closest(".gate")) return false; const b = e.getBoundingClientRect(); return b.width > 0 && (b.right > r.right + 1 || b.left < r.left - 1); }).slice(0, 3).map((e) => e.className || e.tagName); });
const shot = async (p, name) => p.locator("#revenue-cash").screenshot({ path: `${OUT}/${name}.png` });

const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ["--disable-dev-shm-usage", "--no-sandbox"] });
const stress = stressFinancials();

for (const width of [1280, 1055, 390]) for (const theme of ["light", "dark"]) {
  const tag = `${width}-${theme}`;
  // 1. the negative-cash company
  let { ctx, p } = await page(browser, { width, theme, financials: stress });
  check(`stress ${tag}: headline -6.4% and Needs attention`, (await p.locator(".rcx-big").innerText()) === "−6.4%" && /Needs attention/.test(await p.locator(".rcx-pill").innerText()));
  check(`stress ${tag}: no sideways scroll`, (await sideways(p)) <= 1, String(await sideways(p)));
  check(`stress ${tag}: nothing pokes out of the card`, (await clipped(p)).length === 0, JSON.stringify(await clipped(p)));
  check(`stress ${tag}: two lines, FY24 gap leaves two OCF segments`, (await p.locator(".rcx-l-ocf").count()) === 2 && (await p.locator(".rcx-l-rev").count()) >= 1);
  const tiles = await p.locator(".rcx-tv").allInnerTexts();
  check(`stress ${tag}: four indicators`, tiles.join("|") === "▲ +57.9%|▼ −6.4%|▲ +89.0%|▲ +102.3%", tiles.join("|"));
  await p.locator(".rcx-hit").nth(4).focus();
  check(`stress ${tag}: focus shows the tooltip`, /FY26/.test(await p.locator(".rcx-tip").innerText()));
  if (width === 390 || width === 1280) await shot(p, `stress-${tag}-tooltip`);
  await p.locator(".rcx-hit").nth(4).blur();
  await p.locator(".rcx-i").nth(2).focus();
  check(`stress ${tag}: tooltip on the receivables indicator names the basis`, /year-end/.test(await p.locator("[role=tooltip]").nth(2).innerText()) && (await p.locator("[role=tooltip]").nth(2).isVisible()));
  if (width !== 1055) await shot(p, `stress-${tag}-indicator-tip`);
  await p.locator(".rcx-i").nth(2).blur();
  await p.getByRole("button", { name: "Show as table" }).click();
  check(`stress ${tag}: table shows n/a for the missing year`, /FY24\s*[^\n]*n\/a/.test((await p.locator(".rcx-tbl").innerText()).replace(/\t/g, " ")));
  await shot(p, `stress-${tag}`);
  check(`stress ${tag}: still no sideways scroll with the table`, (await sideways(p)) <= 1);
  check(`stress ${tag}: no page errors`, p.errs.length === 0, p.errs.join(" | "));
  await ctx.close();

  // 2. the real RELIANCE report (capital-intensive group)
  ({ ctx, p } = await page(browser, { width, theme }));
  check(`reliance ${tag}: real figure shown`, /%$/.test(await p.locator(".rcx-big").innerText()), await p.locator(".rcx-big").innerText());
  check(`reliance ${tag}: no sideways scroll`, (await sideways(p)) <= 1);
  await shot(p, `reliance-${tag}`);
  if (theme === "dark" && width === 1280) {
    await p.locator('#secnav a[data-s="revenue-cash"]').click(); await p.waitForTimeout(700);
    const top = await p.locator("#revenue-cash").evaluate((e) => Math.round(e.getBoundingClientRect().top));
    check("section bar link jumps to the card", top >= 100 && top < 260, String(top));
    check("nav order: Cash conversion sits right after Ratios", (await p.locator("#secnav nav a").allInnerTexts()).map((s) => s.trim()).join(",").includes("Ratios,Cash conversion,Ownership"));
  }
  check(`reliance ${tag}: no page errors`, p.errs.length === 0, p.errs.join(" | "));
  await ctx.close();
}

// 3. Basic plan: locked teaser, no numbers
for (const [width, theme] of [[1280, "light"], [390, "dark"]]) {
  const { ctx, p } = await page(browser, { width, theme, plan: "basic", financials: stress });
  const txt = await p.locator("#revenue-cash").innerText();
  check(`locked ${width}-${theme}: teaser with the Gold unlock`, /Unlock with Gold/.test(txt) && /Revenue-to-Cash Intelligence/.test(txt));
  check(`locked ${width}-${theme}: no figure from the report in the card`, !/57\.9|6\.4|89\.0|102\.3|crore/.test(txt), txt.replace(/\s+/g, " ").slice(0, 120));
  check(`locked ${width}-${theme}: no sideways scroll`, (await sideways(p)) <= 1);
  await shot(p, `locked-${width}-${theme}`);
  await ctx.close();
}
// 4. lender
for (const [width, theme] of [[1280, "dark"], [390, "light"]]) {
  const { ctx, p } = await page(browser, { width, theme, summary: lenderSummary() });
  const txt = await p.locator("#revenue-cash").innerText();
  check(`lender ${width}-${theme}: 'Not comparable for lenders'`, /Not comparable for lenders/.test(txt) && !(await p.locator(".rcx-big").count()));
  await shot(p, `lender-${width}-${theme}`);
  await ctx.close();
}
await browser.close();
console.log(fails ? `\n${fails} check(s) FAILED` : "\nall checks passed");
process.exit(fails ? 1 : 0);
