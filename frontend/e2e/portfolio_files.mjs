// My portfolio: importing real broker-style files (xlsx, xls BIFF, Zerodha/Groww/ICICI layouts, CSV) takes ONLY share names.
//   PM_PASSWORD=... node e2e/portfolio_files.mjs http://localhost:4173   (members pm-silver / pm-gold; fixtures built by /tmp/claude-0/pf-fixtures/gen.mjs)
const { chromium } = await import("playwright").catch(() => import("/opt/node22/lib/node_modules/playwright/index.mjs"));
const B = process.argv[2] || "http://localhost:4173", F = "/tmp/claude-0/pf-fixtures/";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const same = (a, e) => a.length === e.length && e.every((s) => a.includes(s));
async function run(width, email, tag) {
  const ctx = await b.newContext({ viewport: { width, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const lg = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email, password: process.env.PM_PASSWORD } });
  check(`[${tag}] login ${email}`, lg.ok(), String(lg.status()));
  await p.goto(B + "/holdings", { waitUntil: "networkidle" }); await p.waitForSelector("text=Add your shares");
  await p.waitForFunction(() => document.querySelectorAll("#pf-names option").length > 0, null, { timeout: 15000 }).catch(() => {});
  const syms = async () => (await p.locator("table.hold tbody tr td:first-child b").allInnerTexts()).map((s) => s.trim());
  const clear = async () => { for (let i = 0; i < 60 && (await p.locator("table.hold tbody tr").count()); i++) { await p.locator("table.hold tbody tr").first().getByRole("button", { name: /Remove/ }).click(); await p.waitForTimeout(120); } };
  const toastText = async () => (await p.locator('[role=status], .toast').allInnerTexts()).join(" | ");
  const imp = async (file, label, exp, junk = [], opts = {}) => {
    await clear(); await p.evaluate(() => { document.querySelector(".pf-miss")?.remove?.(); });
    await p.locator("input[type=file]").setInputFiles(F + file); await p.waitForTimeout(1800);
    const got = await syms(); const miss = await p.locator(".pf-miss").innerText().catch(() => "");
    check(`[${tag}] ${label}: exactly the share names land (${exp.join(",")})`, same(got, exp), "got " + got.join(","));
    for (const j of junk) check(`[${tag}] ${label}: "${j}" listed under Not recognised`, miss.includes(j), miss.slice(0, 200));
    check(`[${tag}] ${label}: no numbers / totals / headers as shares`, !got.some((s) => /^[\d.,\s]+$/.test(s) && !/^\d{6}$/.test(s)) && !/\b(Total|Qty|Quantity|Price|Value|Symbol|Instrument|ISIN)\b/i.test(got.join(" ") + " " + miss.replace("Not recognised:", "")), miss.slice(0, 200));
    const heads = (await p.locator("table.hold thead th").allInnerTexts()).join("|");
    check(`[${tag}] ${label}: no quantity/cost/P&L columns in table`, !/Qty|Quantity|Avg|Average|Invested|P&L|Cost|Units/i.test(heads), heads);
    const names = (await p.locator("table.hold tbody tr td:first-child small").allInnerTexts()).join(" ");
    check(`[${tag}] ${label}: no quantity/price numbers shown in share cells`, !/\b\d{2,}\.\d+\b|\b3900\b|\b30000\b/.test(names), names.slice(0, 120));
    if (opts.showMiss === false) check(`[${tag}] ${label}: no Not-recognised noise`, !miss, miss);
  };
  await imp("simple.xlsx", "xlsx", ["TCS", "INFY", "ITC"], ["ZZJUNKCO"]);
  await imp("legacy.xls", "xls (BIFF8)", ["HDFCBANK", "ICICIBANK"], ["QQNOTALISTEDCO"]);
  await imp("zerodha.xlsx", "Zerodha-style (20 title rows)", ["SBIN", "LT", "WIPRO"], ["ZZFAKESTOCK"]);
  await imp("groww.xlsx", "Groww-style (ISIN, numbers)", ["TITAN", "MARUTI", "SUNPHARMA", "HINDUNILVR"], []);
  await imp("icici.xls", "ICICI HTML table saved as .xls", ["BHARTIARTL", "ASIANPAINT"], ["ZZGHOSTCORP"]);
  await imp("simple.csv", "CSV", ["RELIANCE", "MARUTI"], []);
  // no names
  await clear(); await p.locator("input[type=file]").setInputFiles(F + "nonames.csv"); await p.waitForTimeout(1200);
  let t = await toastText(); check(`[${tag}] no-names file: clear message`, /No share names found in nonames\.csv/.test(t), t.slice(0, 200)); check(`[${tag}] no-names file: nothing added`, (await syms()).length === 0, (await syms()).join(","));
  // 6 MB
  await p.locator("input[type=file]").setInputFiles(F + "big.csv"); await p.waitForTimeout(1500);
  t = await toastText(); check(`[${tag}] 6 MB file: size message`, /larger than 5 MB/.test(t), t.slice(0, 200)); check(`[${tag}] 6 MB file: nothing added`, (await syms()).length === 0);
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check(`[${tag}] no sideways page scroll`, ov <= 1, ov + "px");
  const btn = await p.getByRole("button", { name: /Choose Excel or CSV/ }).boundingBox(); check(`[${tag}] file button inside viewport`, !!btn && btn.x >= 0 && btn.x + btn.width <= width + 1);
  await clear(); check(`[${tag}] no page errors`, p.errs.length === 0, p.errs.join(" | "));
  await ctx.close();
}
await run(1366, "pm-silver@example.com", "desktop silver");
await run(390, "pm-gold@example.com", "390px gold");
await run(390, "pm-silver@example.com", "390px silver");
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
