// Sector Rotation in a real browser with every /api/** call mocked from a nightly output folder (the package's sample_site_data: sectors/, rotation/, stock files).
//   node e2e/sector_rotation.mjs http://127.0.0.1:5199 /path/to/sample_site_data /path/to/outdir      (PW=/path/to/playwright/index.mjs when it is not installed here)
// Checks at 1440 and 390, light and dark: the Rotation tab, the Sector Pulse columns, the industry card and the capital-goods redirect render with the file's numbers; corner tiles filter;
// every corner carries its name and glyph; the hollow dot and the week-in-progress note show; no sideways scroll; 44px targets on the phone; labels are limited to 6 on the phone; wording scan. Saves screenshots.
import fs from "node:fs";
import path from "node:path";

const { chromium } = await import(process.env.PW || "playwright");
const B = (process.argv[2] || "http://127.0.0.1:5199").replace(/\/$/, ""), DATA = process.argv[3], OUT = process.argv[4] || "/tmp/rot-shots";
fs.mkdirSync(OUT, { recursive: true });
const J = (...p) => JSON.parse(fs.readFileSync(path.join(DATA, ...p), "utf8"));
const MAP = J("rotation", "_map.json"), BOARD = J("sectors", "_board.json");
let failed = 0;
const check = (name, ok, d = "") => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"}  ${name}${d ? "  - " + d : ""}`); };
const BANNED = /\b(buy|sell|hold|accumulate|avoid|multibagger|top pick|signals?)\b/i;
const VENDOR = /\b(bloomberg|refinitiv|screener\.in|moneycontrol|trendlyne|tradingview|yahoo|angel|zerodha|dhan)\b/i;

async function open(browser, { w, theme }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 600 ? 900 : 844 }, colorScheme: theme, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("finlit-theme", t); } catch {} }, theme);
  const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
  await p.route("**/api/**", async (r) => {
    const pt = new URL(r.request().url()).pathname, json = (b, s = 200) => r.fulfill({ status: s, contentType: "application/json", body: JSON.stringify(b) });
    if (pt === "/api/auth/me") return json({ user: null, plan: "basic", csrf: "t", limits: {}, showcase: [] });
    if (pt === "/api/rotation") return json({ ...MAP, plan: "basic", locked: {} });
    let m = /^\/api\/rotation\/([a-z0-9-]+)$/.exec(pt);
    if (m) { const f = path.join(DATA, "rotation", m[1] + ".json"); return fs.existsSync(f) ? json(J("rotation", m[1] + ".json")) : json({ reason: "none" }, 404); }
    if (pt === "/api/sectors") return json({ ...BOARD, plan: "basic", locked: {} });
    m = /^\/api\/sectors\/([a-z0-9-]+)$/.exec(pt);
    if (m && m[1] !== "status") { const f = path.join(DATA, "sectors", m[1] + ".json"); return fs.existsSync(f) ? json({ ...J("sectors", m[1] + ".json"), plan: "basic", locked: { stocks: "silver" }, stocks: null, not_counted: null }) : json({ reason: "none" }, 404); }
    return json({}, 200);
  });
  return { ctx, p, errs };
}
const noSideways = (p) => p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
for (const w of [1440, 390]) for (const theme of ["light", "dark"]) {
  const tag = `${w}-${theme}`, phone = w < 600;
  const { ctx, p, errs } = await open(browser, { w, theme });

  // ---- the Rotation tab
  await p.goto(B + "/sectors/rotation", { waitUntil: "domcontentloaded" });
  await p.waitForSelector("[data-testid=sector-rotation] .rt-tile", { timeout: 20000 });
  const root = p.locator("[data-testid=sector-rotation]");
  check(`${tag} four corner tiles with the file's counts`, (await root.locator(".rt-tile").count()) === 4 && (await root.locator(".rt-tile .n").allTextContents()).join() === Object.values(MAP.counts).join());
  check(`${tag} every tile carries a name and a glyph`, (await root.locator(".rt-tile .rt-corner svg").count()) === 4 && (await root.locator(".rt-tile .rt-corner span").allTextContents()).join("|") === Object.keys(MAP.counts).join("|"));
  check(`${tag} week in progress note`, MAP.week_closed || (await root.locator(".rt-week").innerText()).startsWith("Week in progress: readings as of"));
  const rows = await root.locator("[data-testid=rank-table] tbody tr").count();
  check(`${tag} ranking has every group`, rows === MAP.rows.length, `${rows}`);
  const first = MAP.rows.slice().sort((a, b) => a.rank - b.rank)[0];
  check(`${tag} rank 1 is ${first.name}`, (await root.locator("[data-testid=rank-table] tbody tr").first().innerText()).includes(first.name), (await root.locator("[data-testid=rank-table] tbody tr").first().innerText()).slice(0, 80).replace(/\n/g, " "));
  check(`${tag} no group is called Capital Goods`, !(await p.locator("body").innerText()).includes("Capital Goods"));
  check(`${tag} no sideways scroll`, await noSideways(p), await p.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 4).map((e) => e.tagName + "." + String(e.className).slice(0, 30)).join(" ")));
  await p.screenshot({ path: path.join(OUT, `rotation-top-${tag}.png`) });
  // filter by tile
  await root.locator("[data-testid=tile-ahead_gaining]").click();
  await p.waitForFunction((n) => document.querySelectorAll("[data-testid=rank-table] tbody tr").length === n, MAP.counts["Ahead and gaining"]).catch(() => {});
  const filtered = await root.locator("[data-testid=rank-table] tbody tr").count();
  check(`${tag} the tile filters the ranking`, filtered === MAP.counts["Ahead and gaining"], `${filtered}`);
  check(`${tag} the filter is in the address`, p.url().includes("corner=ahead_gaining"));
  await root.locator("[data-testid=tile-ahead_gaining]").click();
  await p.waitForFunction(() => document.querySelectorAll("[data-testid=rank-table] tbody tr").length > 30);
  // the map view
  await root.getByRole("button", { name: "Map" }).click();
  await p.waitForSelector(".rt-dotg");
  const dots = await root.locator(".rt-dotg").count(), labels = await root.locator(".rt-dlab").count(), hollow = await root.locator(".rt-dot.hollow").count();
  check(`${tag} map: a dot per group`, dots === MAP.rows.length, `${dots}`);
  check(`${tag} map: labels ${phone ? "limited to 6" : "on every dot"}`, phone ? labels <= 6 && labels > 0 : labels === MAP.rows.length, `${labels}`);
  check(`${tag} map: hollow dots for this week's other reading`, hollow === MAP.rows.filter((r) => r.this_week_reading).length, `${hollow}`);
  check(`${tag} map: no sideways scroll`, await noSideways(p));
  await root.locator(".rt-dotg .rt-hit").first().dispatchEvent("click");
  check(`${tag} map: a tapped dot names the group`, (await root.locator(".rt-pick").innerText()).length > 20);
  await root.locator(".rt-stands").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(OUT, `rotation-map-${tag}.png`) });
  await root.getByRole("button", { name: "Corners" }).click();
  await root.locator(".rt-stands").screenshot({ path: path.join(OUT, `rotation-corners-${tag}.png`) });
  if (phone) {
    const small = await p.evaluate(() => [...document.querySelectorAll("[data-testid=sector-rotation] a, [data-testid=sector-rotation] button, [data-testid=sector-rotation] .rt-hit")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.height < 24 || (e.matches("button, .rt-tabs a") && r.height < 43.5)) && !e.closest(".hs-bar") && !(e.matches("a") && e.closest("p, small")); }).map((e) => (e.textContent || "").trim().slice(0, 24) + ":" + Math.round(e.getBoundingClientRect().height)));
    check(`${tag} buttons are 44px tall (links are at least 24px)`, small.length === 0, small.slice(0, 5).join(", "));
  }
  const grid = await root.locator("[data-testid=rank-grid] tbody tr").count();
  check(`${tag} rank grid has every group`, grid === MAP.rows.length);
  await root.locator("[data-testid=rank-grid]").scrollIntoViewIfNeeded();
  await p.screenshot({ path: path.join(OUT, `rotation-grid-${tag}.png`) });
  const text = await root.innerText();
  check(`${tag} wording: no advice words, no vendor names`, !BANNED.test(text.replace(/not a recommendation to buy, sell or hold any security/gi, "")) && !VENDOR.test(text), (text.match(BANNED) || text.match(VENDOR) || [""])[0]);
  check(`${tag} the data line says NSE daily data, equal-weighted industry groups`, text.includes("NSE daily data, equal-weighted industry groups"));
  check(`${tag} past averages, not forecasts`, /Past averages, not forecasts/.test(text));
  await p.screenshot({ path: path.join(OUT, `rotation-full-${tag}.png`), fullPage: true });

  // ---- Sector Pulse: the two columns and the Part A texts
  await p.goto(B + "/sectors", { waitUntil: "domcontentloaded" });
  await p.waitForSelector("[data-testid=groups-table] tbody tr", { timeout: 20000 });
  const heads = await p.locator("[data-testid=groups-table] thead th").allTextContents();
  check(`${tag} Sector Pulse has Corner and Rotation rank columns`, heads.some((h) => h.startsWith("Corner")) && heads.some((h) => h.startsWith("Rotation rank")));
  const body = await p.locator("body").innerText();
  check(`${tag} Washout wording and exponential average`, body.includes("at some point in the last 30 sessions") && body.includes("200-day exponential average") && body.includes("exponential moving averages"));
  check(`${tag} Sector Pulse: no sideways scroll`, await noSideways(p));
  await p.screenshot({ path: path.join(OUT, `pulse-${tag}.png`) });

  // ---- industry page: the card, the notes
  await p.goto(B + "/sectors/media-entertainment-publication", { waitUntil: "domcontentloaded" });
  await p.waitForSelector("[data-testid=rotation-card] .rt-kpi", { timeout: 20000 });
  const card = p.locator("[data-testid=rotation-card]");
  const mr = MAP.rows.find((r) => r.slug === "media-entertainment-publication");
  const ct = await card.innerText();
  check(`${tag} industry card: rank ${mr.rank} of ${mr.ranked}, corner and summary from the file`, ct.includes(`${mr.rank} of ${mr.ranked}`) && ct.includes(mr.corner_name) && ct.includes(mr.summary.slice(0, 60)));
  check(`${tag} industry card: study line and disclaimer`, /Past averages, not forecasts/.test(ct) && ct.includes("not a recommendation"));
  check(`${tag} industry page: history note under the chart`, await p.locator("[data-testid=history-note]").count() === 1);
  check(`${tag} industry page: no sideways scroll`, await noSideways(p));
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: path.join(OUT, `industry-card-${tag}.png`) });
  // ---- renamed group
  await p.goto(B + "/sectors/capital-goods", { waitUntil: "domcontentloaded" });
  await p.waitForURL("**/sectors/agricultural-commercial-construction-vehicles");
  check(`${tag} /sectors/capital-goods redirects to the renamed group`, p.url().endsWith("/sectors/agricultural-commercial-construction-vehicles"));
  check(`${tag} no page errors`, errs.length === 0, errs.join(" | "));
  await ctx.close();
}
await browser.close();
console.log(failed ? `${failed} FAILED` : "all passed");
process.exit(failed ? 1 : 0);
