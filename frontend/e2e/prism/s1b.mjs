import { BASE, browser, newPage, api, post, login, shot, check, save, failures } from "./lib.mjs";
// Scenario 1b: showcase NONE: RELIANCE is locked for visitor and basic
const b = await browser();
for (const who of ["visitor", "basic", "silver"]) {
  const p = await newPage(b);
  if (who !== "visitor") await login(p, `${who}@test.example`);
  let r = await api(p, "/api/prism/reports/latest?symbol=RELIANCE");
  check(`1b ${who}: latest RELIANCE -> 403`, r.status === 403 && r.body.status === "plan_required", JSON.stringify(r.body));
  if (who !== "visitor") { r = await post(p, "/api/prism/reports", { symbol: "RELIANCE" }); check(`1b ${who}: generate RELIANCE -> 403`, r.status === 403, JSON.stringify(r.body)); }
  await p.goto(BASE + "/stocks/RELIANCE", { waitUntil: "networkidle" });
  await shot(p, `1b-${who}-stock-RELIANCE-locked`);
  const txt = await p.locator("body").innerText();
  check(`1b ${who}: stock page shows locked Prism teaser + FinLit score single column`, /Prism/.test(txt) && /FinLit score/i.test(txt) && !/Generate the Prism rating/.test(txt), "");
  const boxes = await p.evaluate(() => [...document.querySelectorAll("section, div")].filter((e) => /prism/i.test(e.className) ).slice(0, 5).map((e) => e.className + " " + Math.round(e.getBoundingClientRect().width)));
  console.log(who, boxes.join(" | "));
  check(`1b ${who}: no page errors`, p.errs.length === 0, p.errs.join(" | "));
}
await b.close();
save("s1b");
process.exit(failures() ? 1 : 0);
