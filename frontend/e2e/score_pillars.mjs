// Score screener: the Fundamental score split into its four pillars (Quality, Growth, Profitability, Balance sheet), each filterable.
//   PM_PASSWORD=... node e2e/score_pillars.mjs http://localhost:4173   (needs member pm-silver@example.com)
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
for (const w of [1366, 390]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } }); const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 160)));
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const r = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: "pm-silver@example.com", password: process.env.PM_PASSWORD } });
  check(`${w}: silver signs in`, r.ok(), String(r.status()));
  await p.goto(B + "/score-screener", { waitUntil: "networkidle" }); await p.waitForSelector(".ss-t tbody tr");
  const rows = await p.locator(".ss-prow .ss-pn").allInnerTexts(); check(`${w}: four pillar rows`, rows.join() === "Quality,Growth,Profitability,Balance sheet", rows.join());
  const heads = await p.locator(".ss-t thead th").allInnerTexts(); check(`${w}: pillar columns in the table`, ["Quality", "Growth", "Profit.", "Balance"].every((h) => heads.some((x) => x.startsWith(h))), heads.join("|"));
  const before = Number((await p.locator(".fgx-kpi b").first().innerText()).replace(/\D/g, ""));
  await p.getByRole("button", { name: "Quality 78 and above" }).click(); await p.getByRole("button", { name: "Apply filters" }).click(); await p.waitForTimeout(300);
  const after = Number((await p.locator(".fgx-kpi b").first().innerText()).replace(/\D/g, ""));
  const qcol = heads.findIndex((x) => x.startsWith("Quality"));
  const qs = (await p.locator(`.ss-t tbody tr td:nth-child(${qcol + 1})`).allInnerTexts()).map(Number).filter((n) => !Number.isNaN(n));
  check(`${w}: Quality 78+ narrows the list and every row has Quality >= 78`, after > 0 && after < before && qs.every((n) => n >= 78), `${before} -> ${after}; ${qs.slice(0, 5).join(",")}`);
  check(`${w}: chip names the pillar`, (await p.locator(".fchip").allInnerTexts()).some((c) => c.startsWith("Quality 78")), (await p.locator(".fchip").allInnerTexts()).join("|"));
  check(`${w}: filter kept in the address`, p.url().includes("q=high"), p.url());
  await p.getByRole("button", { name: /Strong on all four/ }).click(); await p.waitForTimeout(300);
  const chips = await p.locator(".fchip").allInnerTexts(); check(`${w}: 'strong on all four' applies four pillar filters`, ["Quality", "Growth", "Profitability", "Balance sheet"].every((n) => chips.some((c) => c.startsWith(n))), chips.join("|"));
  const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check(`${w}: no sideways scroll`, ov <= 1, ov + "px");
  await p.locator(".scr-side").screenshot({ path: `${OUT}/score_pillars_${w}.png` });
  check(`${w}: no page errors`, p.errs.length === 0, p.errs.join(" | ")); await ctx.close();
}
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
