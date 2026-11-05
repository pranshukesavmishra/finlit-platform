// Earnings alert: it must hide and show the edge icon, and show again, on EVERY pass between its section (05) and the next (06), however many times,
// also after the icon was used; the x dismisses it for good; Esc / outside click close a floating card; the icon is on the RIGHT edge.
// Needs a page that renders <PlFlagsLayer> inside #financials followed by #trends (the dev harness /pop-harness.html: tall empty sections, a P&L mock).
//   node e2e/plflags_scroll.mjs http://127.0.0.1:4400/pop-harness.html /path/to/out
import { chromium } from "playwright";
const url = process.argv[2] || "http://127.0.0.1:4400/pop-harness.html", out = process.argv[3] || ".";
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
let bad = 0; const ok = (c, m) => { if (!c) { bad++; console.log("FAIL", m); } else console.log("ok  ", m); };
for (const [w, h] of [[1280, 720], [390, 844]]) for (const theme of ["light", "dark"]) {
  const tag = `${w}-${theme}`, p = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
  p.on("pageerror", (e) => { bad++; console.log("PAGEERROR", String(e).slice(0, 300)); });
  await p.goto(`${url}?theme=${theme}`); await p.waitForTimeout(400);
  const card = () => p.locator(".plf-note").count(), edge = () => p.locator(".plf-edge").count();
  const at = async (id) => { await p.evaluate((i) => document.getElementById(i).scrollIntoView(), id); await p.waitForTimeout(250); };
  await at("financials");
  ok(await card() === 1 && await edge() === 0, `${tag}: in its own section the card shows`);
  for (let k = 1; k <= 6; k++) {
    await at("trends"); ok(await card() === 0 && await edge() === 1, `${tag}: pass ${k} away, card hidden and icon shown`);
    await at("financials"); ok(await card() === 1 && await edge() === 0, `${tag}: pass ${k} back, card shown again and icon gone`);
  }
  for (let k = 1; k <= 5; k++) {   // the same, but the icon is used on every pass (the reported bug)
    await at("trends"); await p.locator(".plf-edge").click(); await p.waitForTimeout(150);
    ok(await card() === 1 && await edge() === 0 && await p.locator(".plf-floating").count() === 1, `${tag}: pass ${k} icon opens the floating card`);
    await at("financials"); ok(await card() === 1 && await edge() === 0 && await p.locator(".plf-floating").count() === 0, `${tag}: pass ${k} back, the in-place card shows`);
    await at("trends"); ok(await card() === 0 && await edge() === 1, `${tag}: pass ${k} away again, hidden and icon shown`);
    await at("financials");
  }
  // wheel scrolling in small steps, with the pointer over the card
  await p.mouse.move(w < 600 ? 3 : w / 2, h / 2);
  for (let k = 0; k < 3; k++) {
    for (let i = 0; i < 12; i++) { await p.mouse.wheel(0, 120); await p.waitForTimeout(20); } await p.waitForTimeout(300);
    const away = await edge() === 1 && await card() === 0;
    for (let i = 0; i < 12; i++) { await p.mouse.wheel(0, -120); await p.waitForTimeout(20); } await p.waitForTimeout(300);
    ok(away && await card() === 1, `${tag}: wheel pass ${k + 1}`);
  }
  await at("trends"); await p.waitForTimeout(500);
  const e = await p.locator(".plf-edge").boundingBox();
  ok(e && Math.abs(e.x + e.width - w) < 1, `${tag}: the icon sits on the right edge`);
  await p.screenshot({ path: `${out}/edge-${tag}.png` });
  await p.locator(".plf-edge").click(); await p.keyboard.press("Escape"); await p.waitForTimeout(150);
  ok(await card() === 0 && await edge() === 1, `${tag}: Esc closes the floating card`);
  await p.locator(".plf-edge").click(); await p.mouse.click(5, 5); await p.waitForTimeout(150);
  ok(await card() === 0 && await edge() === 1, `${tag}: a click outside closes it`);
  await p.locator(".plf-edge").click(); await p.locator(".plf-x").click(); await p.waitForTimeout(150);
  ok(await card() === 0 && await edge() === 1, `${tag}: the x on the floating card only closes it, the icon stays`);
  await at("financials"); await p.locator(".plf-x").click(); await p.waitForTimeout(150);
  ok(await card() === 0 && await edge() === 0, `${tag}: the x on the in-place card dismisses it, no icon`);
  for (let k = 0; k < 3; k++) { await at("trends"); await at("financials"); }
  ok(await card() === 0 && await edge() === 0, `${tag}: it stays dismissed after more scrolling`);
  await p.close();
}
await browser.close(); console.log(bad ? `${bad} FAILED` : "ALL OK"); process.exit(bad ? 1 : 0);
