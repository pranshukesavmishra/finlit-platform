import fs from "node:fs";
import { BASE, browser, newPage, api, post, login, shot, check, save, failures, OUT, ADMIN_PW } from "./lib.mjs";
const b = await browser();
// ---------- 4 admin
const a = await newPage(b);
await login(a, "admin@test.example", ADMIN_PW);
let r = await api(a, "/api/prism/reports/latest?symbol=RELIANCE");
check("4 admin: sees RELIANCE stored report", r.status === 200 && r.body.rating, r.status);
r = await post(a, "/api/prism/reports", { symbol: "TCS" });
check("4 admin: generates TCS (not showcase)", r.status === 200 && r.body.rating.final != null, r.status);
r = await post(a, "/api/prism/reports", { symbol: "TCS", refresh: true });
check("4 admin: refresh works, not limited", r.status === 200, r.status);
const g = await newPage(b);
const gl = await login(g, "gold@test.example");
const cookies = (await g.context().cookies()).map((c) => `${c.name}=${c.value}`).join("; ");
for (const base of [BASE, "http://127.0.0.1:8011", "http://127.0.0.1:8010"]) {
  let res; try { res = await fetch(base + "/api/premium-reports", { method: "POST", headers: { "Content-Type": "application/json", Cookie: cookies, "X-CSRF-Token": gl.csrf, Origin: BASE }, body: JSON.stringify({ query: "TCS", statement_type: "consolidated", delivery: "inline" }), signal: AbortSignal.timeout(8000) }); } catch { console.log(`SKIP  ${base} is not reachable`); continue; }
  const t = (await res.text()).slice(0, 160);
  check(`4 member session cookie on ${base}/api/premium-reports rejected`, [401, 403, 404, 405, 422].includes(res.status) && !/"state":"ready"/.test(t), `${res.status} ${t}`);
}
const bs = await newPage(b); await login(bs, "basic@test.example");
r = await api(bs, "/api/premium-reports", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": bs.csrf }, body: JSON.stringify({ query: "TCS" }) });
check("4 basic member on proxied /api/premium-reports -> refused", [401, 403, 404, 405, 422].includes(r.status) && !r.body?.state, r.status + " " + JSON.stringify(r.body).slice(0, 120));
// ---------- 6 other groups
const p = await newPage(b);
await login(p, "gold@test.example");
const out = {};
for (const sym of ["RELIANCE", "HDFCBANK", "HDFCLIFE"]) {
  r = await post(p, "/api/prism/reports", { symbol: sym });
  check(`6 ${sym}: generated`, r.status === 200, r.status + " " + JSON.stringify(r.body).slice(0, 200));
  const rep = r.body; out[sym] = rep;
  const rt = rep.rating;
  console.log(sym, rt.group, rt.final, rt.label, rt.status, JSON.stringify(rt.parts), "factors:", rt.metrics.length);
  fs.writeFileSync(`${OUT}/6-${sym}-labels.txt`, rt.metrics.map((m) => `${m.part}\t${m.label}\t${m.value}\t${m.points}`).join("\n"));
}
check("6 groups differ: BANK / INSURANCE / not same as RELIANCE", out.HDFCBANK.rating.group !== out.RELIANCE.rating.group && out.HDFCLIFE.rating.group !== out.HDFCBANK.rating.group, [out.RELIANCE, out.HDFCBANK, out.HDFCLIFE].map((x) => x.rating.group).join(","));
const labels = (s) => out[s].rating.metrics.map((m) => m.label).join("|");
check("6 the labels never call the income line net interest or net premium income", !/Net interest income|Net premium income/i.test(labels("HDFCBANK") + labels("HDFCLIFE") + labels("RELIANCE")), "");
check("6 factor label sets differ between groups", labels("HDFCBANK") !== labels("RELIANCE") && labels("HDFCLIFE") !== labels("HDFCBANK"), "");
for (const sym of ["HDFCBANK", "HDFCLIFE"]) {
  await p.goto(BASE + "/prism/" + sym, { waitUntil: "networkidle" }); await p.waitForTimeout(2000);
  const t = await p.locator("main").innerText();
  fs.writeFileSync(`${OUT}/6-${sym}-page.txt`, t);
  await p.screenshot({ path: `${OUT}/6-${sym}-page.png`, fullPage: true });
  check(`6 ${sym} full page says Sales with the sector note`, /\bSales\b/.test(t) && (sym === "HDFCBANK" ? /net interest income: interest earned less interest paid/i.test(t) : /net premium earned/i.test(t)) && !/Net premium income/i.test(t), "");
}
check("6 no page errors", p.errs.length === 0, p.errs.join(" | "));
// ---------- 5 pages
const pages = [["/", "home"], ["/premium", "hub"], ["/prism", "prism-landing"], ["/plans", "plans"], ["/glossary", "glossary"], ["/stocks/RELIANCE", "stock"], ["/prism/RELIANCE", "prism-RELIANCE"]];
for (const [path, name] of pages) {
  await p.goto(BASE + path, { waitUntil: "networkidle" }); await p.waitForTimeout(1200);
  const t = await p.locator("body").innerText();
  if (name === "hub") check("5 Gold hub mentions FinLit Prism", /FinLit Prism/.test(t), "");
  if (name === "plans") check("5 Plans page mentions FinLit Prism", /FinLit Prism/.test(t), "");
  if (name === "glossary") { await p.goto(BASE + "/glossary#finlit-prism", { waitUntil: "networkidle" }); await p.waitForTimeout(800); check("5 glossary has FinLit Prism terms", /FinLit Prism/.test(await p.locator("body").innerText()) && /Prism/.test(await p.locator("body").innerText()), ""); }
  if (name === "prism-landing") {
    check("5 /prism landing: search box", (await p.getByRole("combobox", { name: /Choose a company/ }).count()) === 1);
    check("5 /prism landing: recent chips (RELIANCE visited)", /Recent/.test(t) && /RELIANCE/.test(t), "");
    await p.getByRole("combobox", { name: /Choose a company/ }).fill("hdfc"); await p.waitForTimeout(800);
    const opts = await p.getByRole("option").allInnerTexts();
    check("5 /prism landing: search suggests companies", opts.length > 0, JSON.stringify(opts).slice(0, 150));
    await shot(p, "5-prism-landing");
  }
  await shot(p, `5-${name}`);
  check(`5 ${name}: no console/page errors`, p.errs.length === 0, p.errs.join(" | ")); p.errs.length = 0;
}
await p.goto(BASE + "/", { waitUntil: "networkidle" });
const nav = await p.evaluate(() => [...document.querySelectorAll("a")].filter((a) => /^\/prism/.test(a.getAttribute("href") || "")).map((a) => a.textContent.trim().slice(0, 40)));
check("5 nav has FinLit Prism link", nav.some((x) => /FinLit Prism/.test(x)), JSON.stringify(nav));
// 360 overflow
const s = await newPage(b, { width: 360, height: 800 }); await login(s, "gold@test.example");
for (const path of ["/prism", "/prism/RELIANCE", "/stocks/RELIANCE"]) {
  await s.goto(BASE + path, { waitUntil: "networkidle" }); await s.waitForTimeout(2500);
  const sw = await s.evaluate(() => document.documentElement.scrollWidth);
  check(`5 360px no horizontal overflow ${path}`, sw <= 360, "scrollWidth " + sw);
}
check("5 360 no errors", s.errs.length === 0, s.errs.join(" | "));
await b.close(); save("s456");
process.exit(failures() ? 1 : 0);
