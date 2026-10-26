import { BASE, browser, newPage, api, post, login, shot, check, save, failures, OUT } from "./lib.mjs";
// Scenario 2b: layout of the two halves, reload = stored, recalc, labels
const b = await browser();
for (const [w, h, tag] of [[1400, 900, "1400"], [390, 844, "390"], [360, 800, "360"]]) {
  const p = await newPage(b, { width: w, height: h });
  await login(p, "gold@test.example");
  const t0 = Date.now();
  await p.goto(BASE + "/stocks/RELIANCE", { waitUntil: "networkidle" });
  await p.waitForSelector(".pz-right .dk-row", { timeout: 15000 });
  console.log(tag, "stored report on page after ms", Date.now() - t0);
  await p.waitForTimeout(1500);
  const g = await p.evaluate(() => {
    const right = document.querySelector(".pz-right");
    const left = right.parentElement.querySelector(":scope > *:not(.pz-right)");
    const kids = [...right.parentElement.children].map((e) => e.tagName + "." + e.className);
    const L = [...right.parentElement.children].find((e) => e !== right && e.getBoundingClientRect().height > 100);
    const a = L.getBoundingClientRect(), c = right.getBoundingClientRect();
    return { kids, left: { x: a.x, y: a.y, w: a.width, h: a.height, r: a.right, b: a.bottom }, right: { x: c.x, y: c.y, w: c.width, h: c.height }, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
  });
  console.log(tag, JSON.stringify(g));
  if (w >= 1000) check(`2 ${tag}: halves side by side (same top, right of left)`, Math.abs(g.left.y - g.right.y) < 4 && g.right.x >= g.left.r - 2 && g.left.w > 400 && g.right.w > 400, JSON.stringify(g));
  else check(`2 ${tag}: halves stacked (FinLit score first, Prism below)`, g.right.y >= g.left.b - 2 && Math.abs(g.right.x - g.left.x) < 4, JSON.stringify(g));
  check(`2 ${tag}: no horizontal overflow`, g.overflow <= 0, "overflow " + g.overflow);
  const box = await p.evaluate(() => { const r = document.querySelector(".pz-right").parentElement; r.scrollIntoView(); return true; });
  const parent = p.locator(".pz-right >> xpath=..");
  await parent.screenshot({ path: `${OUT}/2-compare-${tag}.png` });
  const txt = await p.locator(".pz-right").innerText();
  check(`2 ${tag}: label, status, four parts, technical view row or note`, /AVERAGE|HEALTHY|STRONG|WEAK|POOR/i.test(txt) && /Provisional|Rated/i.test(txt) && ["Fundamentals", "Valuation", "Quality", "Risk"].every((x) => txt.includes(x)) && /Technical/i.test(txt), txt.replace(/\n+/g, " ").slice(0, 200));
  check(`2 ${tag}: four part tiles present`, (await p.locator(".pz-right .pzs-parts .dk-tile").count()) === 4);
  check(`2 ${tag}: compliance wording on the card or the page`, /not a recommendation/i.test(txt) || /not a recommendation/i.test(await p.locator("main").innerText()));
  check(`2 ${tag}: no advice words in the card`, !/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/i.test(txt), txt.match(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/i)?.[0] || "");
  check(`2 ${tag}: no page errors`, p.errs.length === 0, p.errs.join(" | "));
  if (tag === "1400") {
    const r1 = await api(p, "/api/prism/reports/latest?symbol=RELIANCE");
    check("2 reload: stored served cached:true", r1.body.cached === true, "cached=" + r1.body.cached);
    const id1 = r1.body.id;
    const r2 = await post(p, "/api/prism/reports", { symbol: "RELIANCE", statement: "consolidated" });
    check("2 POST generate again within 6h reuses stored (cached true, same id)", r2.status === 200 && r2.body.cached === true && r2.body.id === id1, `cached=${r2.body.cached}`);
    await p.getByRole("button", { name: /^Recalculate/ }).first().scrollIntoViewIfNeeded();
    await p.getByRole("button", { name: /^Recalculate/ }).first().click();
    for (let i = 0; i < 60; i++) { const cur = await api(p, "/api/prism/reports/latest?symbol=RELIANCE"); if (cur.body.id !== id1) break; await p.waitForTimeout(500); }
    const r3 = await api(p, "/api/prism/reports/latest?symbol=RELIANCE");
    check("2 Recalculate produces a new calculation id", r3.body.id !== id1, `${id1} -> ${r3.body.id}`);
    await p.waitForTimeout(800);
    check("2 after Recalculate no page errors", p.errs.length === 0, p.errs.join(" | "));
  }
}
await b.close();
save("s2b");
process.exit(failures() ? 1 : 0);
