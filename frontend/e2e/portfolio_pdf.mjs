// My portfolio: importing a holdings statement saved as a PDF. The PDF is read in the browser (pdf.js), a REVIEW lists each PDF text -> company,
// "please check" rows are unticked, and only the ticked ones are added. A wrong company added, or a held company missed, is a failure.
//   PM_PASSWORD=... node e2e/portfolio_pdf.mjs http://localhost:4173     (members pm-gold / pm-silver; start the stack with dev/run_stack.sh, see docs/LAUNCH-RUNBOOK.md)
//   Fixtures and their exact expected companies: src/lib/fixtures/pdf/*.pdf + manifest.json (made by a reportlab generator, one PDF per broker / depository layout).
//   Needs Playwright: `import("playwright")`, else /opt/node-tools/node_modules/playwright (symlink it into frontend/node_modules if you like).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = await import("playwright").catch(() => import("/opt/node-tools/node_modules/playwright/index.mjs"));
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(HERE, "../src/lib/fixtures/pdf/"), DIST = path.join(HERE, "../dist/assets/");
const B = process.argv[2] || "http://localhost:4173";
const MAN = JSON.parse(fs.readFileSync(FIX + "manifest.json", "utf8"));
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + String(x).slice(0, 300) : "")); };
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const same = (a, e) => a.length === e.length && [...e].every((s) => a.includes(s));

// the live company list decides which expected companies can exist at all (a fixture may name a company this database does not hold)
const probe = await b.newContext(); const idx = await (await probe.request.get(B + "/api/stocks/search-index")).json(); await probe.close();
const live = new Set(idx.rows.map((r) => r[0]));
const LIVE_SYMBOL = { INFOEDGE: "NAUKRI" };   // Info Edge (India) Ltd trades as NAUKRI; the fixtures use the test index's own symbol
const need = (list) => list.map((s) => LIVE_SYMBOL[s] || s).filter((s) => live.has(s));
check("live company list loaded", live.size > 1000, live.size + " companies");

// files made on the fly: a 12 MB "PDF", a text file called .pdf, and a PDF with the right header but nothing inside
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "pfpdf-"));
fs.writeFileSync(TMP + "/huge.pdf", Buffer.concat([Buffer.from("%PDF-1.4\n"), Buffer.alloc(12 * 1024 * 1024, 32)]));
fs.writeFileSync(TMP + "/notpdf.pdf", "this is not a pdf, just text");
fs.writeFileSync(TMP + "/broken.pdf", "%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF");

async function session(width, email, tag, fn) {
  const ctx = await b.newContext({ viewport: { width, height: 900 } }); const p = await ctx.newPage();
  p.errs = []; p.cons = []; p.reqs = [];
  p.on("pageerror", (e) => p.errs.push(String(e).slice(0, 200)));
  p.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !/status of 429/.test(m.text())) p.cons.push(m.type() + ": " + m.text().slice(0, 200)); });
  p.on("response", (r) => { if (r.status() === 429) p.n429 = (p.n429 || 0) + 1; });
  p.on("response", (r) => { if (/pdf\.worker/.test(r.url())) p.reqs.push({ url: r.url(), status: r.status(), type: r.headers()["content-type"] || "" }); });
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const lg = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email, password: process.env.PM_PASSWORD } });
  check(`[${tag}] login ${email}`, lg.ok(), String(lg.status()));
  await p.goto(B + "/holdings", { waitUntil: "networkidle" }); await p.waitForSelector("text=Add your shares");
  await p.waitForFunction(() => document.querySelectorAll("#pf-names option").length > 0, null, { timeout: 15000 }).catch(() => {});
  await p.waitForTimeout(800);   // the company list the page matches against has loaded
  const syms = async () => (await p.locator("table.hold tbody tr td:first-child b").allInnerTexts()).map((s) => s.trim());
  const clear = async () => { for (let i = 0; i < 700 && (await p.locator("table.hold tbody tr").count()); i++) { await p.locator("table.hold tbody tr").first().getByRole("button", { name: /Remove/ }).click(); await p.waitForTimeout(25); } };
  const settled = () => p.waitForFunction(() => { const e = document.querySelector(".pdfi"); return !!e && !/Reading .* on your device/.test(e.innerText); }, null, { timeout: 30000 });
  const choose = async (file) => { await p.locator("input[type=file]").setInputFiles(file.includes("/") ? file : FIX + file); await settled(); };
  const rows = async () => p.locator(".pdfi-row").evaluateAll((els) => els.map((e) => ({ sym: e.querySelector(".co b")?.textContent?.trim() || "", name: e.querySelector(".co small")?.textContent || "", from: e.querySelector(".in")?.textContent || "", tag: e.querySelector(".tag")?.textContent || "", on: e.querySelector("input").checked, warn: e.classList.contains("warn"), done: e.classList.contains("done") })));
  const close = async () => { const c = p.locator(".pdfi").getByRole("button", { name: /^(Cancel|Close)$/ }); if (await c.count()) await c.first().click(); await p.waitForTimeout(100); };
  try { await clear(); await fn({ p, syms, clear, choose, rows, close, settled, tag, width }); } finally {
    await clear();
    if (p.n429) console.log(`NOTE [${tag}] ${p.n429} rate-limited (429) background requests from the page (company data being prepared for the added shares)`);
    check(`[${tag}] no page errors`, p.errs.length === 0, p.errs.join(" | "));
    check(`[${tag}] no console errors or warnings (CSP, worker, fonts)`, p.cons.length === 0, p.cons.slice(0, 3).join(" | "));
    await ctx.close();
  }
}

// ---------------------------------------------------------------------------------------------------- every layout, as gold
await session(1366, "pm-gold@example.com", "desktop gold", async ({ p, syms, clear, choose, rows, close, settled, tag }) => {
  const names = Object.keys(MAN).filter((n) => n !== "large_150_rows.pdf").sort();
  let added = 0;
  // Adding makes the app prepare data for each new share (live provider, rate limited), so the full add-and-check is done for a spread of layouts and the
  // review alone (exact ticks, reasons, Cancel) for the rest.
  const ADD = new Set(["groww_holdings.pdf", "zerodha_console.pdf", "nsdl_cas.pdf", "cdsl_holdings.pdf", "lookalikes_abbrev.pdf", "lookalikes_1.pdf", "two_tables_sold_first.pdf", "wrap_hazard_top.pdf", "duplicates.pdf", "protected_cas.pdf",
    "blank_cells.pdf", "header_wrapped.pdf", "numbers_touching.pdf", "name_suffixes.pdf", "isin_first.pdf", "text_lines.pdf", "name_list_only.pdf", "two_tables_unlabelled.pdf"]);
  for (const name of names) {
    const m = MAN[name]; const exp = need(m.expected);
    const t0 = Date.now(); await choose(name === "protected_cas.pdf" ? "protected_cas.pdf" : name);
    if (name.startsWith("protected")) {
      check(`[${tag}] ${name}: asks for the password`, (await p.locator("input[aria-label='PDF password']").count()) === 1);
      await p.locator("input[aria-label='PDF password']").fill("WRONGPASS1"); await p.locator(".pdfi").getByRole("button", { name: "Open", exact: true }).click(); await p.waitForSelector("[role=alert]:has-text('not correct')");
      check(`[${tag}] ${name}: a wrong password is refused, the box stays`, (await p.locator("input[aria-label='PDF password']").count()) === 1);
      await p.locator("input[aria-label='PDF password']").fill("ABCPM1234F"); await p.locator(".pdfi").getByRole("button", { name: "Open", exact: true }).click(); await settled();
      await p.waitForSelector(".pdfi-row, .pdfi h3:has-text('Could not'), .pdfi h3:has-text('No listed')", { timeout: 20000 });
    }
    const r = await rows(); const ticked = r.filter((x) => x.on).map((x) => x.sym);
    check(`[${tag}] ${name}: exactly the held companies are ticked`, same(ticked, exp), `ticked ${ticked.sort().join(",")} | expected ${exp.sort().join(",")}`);
    check(`[${tag}] ${name}: every unticked row is marked "please check" with a reason`, r.filter((x) => !x.on && !x.done).every((x) => x.warn && x.tag.length > 8), r.filter((x) => !x.on && !(x.warn && x.tag.length > 8)).map((x) => x.sym + ":" + x.tag).join(", "));
    check(`[${tag}] ${name}: no company listed twice`, new Set(r.map((x) => x.sym)).size === r.length);
    check(`[${tag}] ${name}: each row shows the PDF's own words next to the company`, r.every((x) => x.from.trim().length > 1 && x.sym));
    if (!r.length || !ADD.has(name)) { await close(); check(`[${tag}] ${name}: Cancel closes the review and adds nothing`, (await p.locator(".pdfi").count()) === 0 && (await syms()).length === 0); continue; }
    // the person unticks one sure row and ticks one "please check" row: Add selected adds exactly the final ticks
    let want = [...ticked];
    const addExtra = name === "lookalikes_abbrev.pdf" || name === "wrap_hazard_top.pdf";
    if (addExtra) { const w = r.find((x) => !x.on && x.warn && !x.done); if (w) { await p.locator(".pdfi-row").filter({ hasText: w.sym }).first().locator("input").check(); want.push(w.sym); } }
    if (name === "groww_holdings.pdf" && ticked.length) { await p.locator(".pdfi-row").first().locator("input").uncheck(); want = want.filter((s) => s !== r[0].sym); }
    const btn = p.getByRole("button", { name: /^Add \d+ selected$/ });
    check(`[${tag}] ${name}: the Add button counts the ticked rows`, (await btn.innerText()) === `Add ${want.length} selected`, await btn.innerText());
    if (want.length) { await btn.click(); await p.waitForTimeout(250); } else { check(`[${tag}] ${name}: nothing ticked -> Add is disabled`, await btn.isDisabled()); await close(); }
    const got = await syms(); added += got.length;
    check(`[${tag}] ${name}: the portfolio table shows exactly the added companies`, same(got, want), `table ${got.sort().join(",")} | want ${want.sort().join(",")}`);
    if (want.length) check(`[${tag}] ${name}: the review is closed after adding`, (await p.locator(".pdfi").count()) === 0);
    await clear();
    if (Date.now() - t0 > 20000) check(`[${tag}] ${name}: reads in reasonable time`, false, Date.now() - t0 + " ms");
  }
  check(`[${tag}] ${names.length} layouts reviewed`, names.length >= 35, `${names.length} PDFs, ${added} shares added over the run`);

  // 150 rows: time from choosing the file to the review being on screen
  const t0 = Date.now(); await choose("large_150_rows.pdf"); const ms = Date.now() - t0;
  const big = await rows(); const tk = big.filter((x) => x.on).map((x) => x.sym);
  check(`[${tag}] 150-row statement: review is up in well under 5 s`, ms < 5000, ms + " ms");
  check(`[${tag}] 150-row statement: exactly the listed companies are ticked (${need(MAN["large_150_rows.pdf"].expected).length})`, same(tk, need(MAN["large_150_rows.pdf"].expected)), `${tk.length} ticked`);
  const lh = await p.locator(".pdfi-list").evaluate((e) => ({ sh: e.scrollHeight, ch: e.clientHeight, ov: getComputedStyle(e).overflowY }));
  check(`[${tag}] long review list scrolls inside its own box`, lh.sh > lh.ch && /auto|scroll/.test(lh.ov), JSON.stringify(lh));
  await close();

  // already-held companies are not added twice and are not ticked
  await choose("zerodha_console.pdf"); await p.getByRole("button", { name: /^Add \d+ selected$/ }).click(); await p.waitForTimeout(250);
  const first = await syms(); await choose("zerodha_console.pdf");
  const again = await rows();
  check(`[${tag}] second import of the same statement: every row is "Already in your portfolio" and none ticked`, again.length > 0 && again.every((x) => x.done && !x.on && /Already/.test(x.tag)), again.filter((x) => !x.done).map((x) => x.sym).join(","));
  check(`[${tag}] second import: Add is disabled`, await p.getByRole("button", { name: /^Add 0 selected$/ }).isDisabled());
  await close(); check(`[${tag}] portfolio unchanged by the second import`, same(await syms(), first));
  await clear();

  // password flow in detail (the cancel path too)
  await choose("protected_statement.pdf");
  check(`[${tag}] password PDF: the file's text is not shown before the password`, (await p.locator(".pdfi-row").count()) === 0);
  await p.locator("input[aria-label='PDF password']").fill("abcde1234f"); await p.locator(".pdfi").getByRole("button", { name: "Open", exact: true }).click(); await p.waitForSelector("[role=alert]:has-text('not correct')");
  check(`[${tag}] password is case sensitive (lower-case PAN refused)`, true);
  await p.locator("input[aria-label='PDF password']").fill("ABCDE1234F"); await p.locator(".pdfi").getByRole("button", { name: "Open", exact: true }).click(); await settled();
  const pr = await rows(); check(`[${tag}] right password: ITC, RELIANCE, TCS ticked`, same(pr.filter((x) => x.on).map((x) => x.sym), need(["ITC", "RELIANCE", "TCS"])), pr.map((x) => x.sym + x.on).join(","));
  const stored = await p.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  check(`[${tag}] the password is stored nowhere`, !/ABCDE1234F/i.test(stored));
  await close();
  await choose("protected_statement.pdf"); await p.getByRole("button", { name: "Cancel" }).click(); check(`[${tag}] password box can be cancelled`, (await p.locator(".pdfi").count()) === 0);

  // scanned PDF, huge PDF, not a PDF, broken PDF
  await choose("scanned.pdf");
  let msg = await p.locator(".pdfi").innerText(); check(`[${tag}] scanned PDF: clear message, nothing to review`, /no text to read/i.test(msg) && /scan or a photo/i.test(msg) && (await p.locator(".pdfi-row").count()) === 0, msg.slice(0, 200)); await close();
  await choose(TMP + "/huge.pdf"); msg = await p.locator(".pdfi").innerText(); check(`[${tag}] 12 MB PDF: size message`, /larger than 10 MB/.test(msg), msg.slice(0, 200)); await close();
  await choose(TMP + "/notpdf.pdf"); msg = await p.locator(".pdfi").innerText(); check(`[${tag}] a text file called .pdf: "could not be read"`, /could not be read/i.test(msg), msg.slice(0, 200)); await close();
  await choose(TMP + "/broken.pdf"); msg = await p.locator(".pdfi").innerText(); check(`[${tag}] a broken PDF: "could not be read", no crash`, /could not be read/i.test(msg), msg.slice(0, 200)); await close();
  await choose("boilerplate.pdf"); msg = await p.locator(".pdfi").innerText(); check(`[${tag}] notices that only mention companies: none found`, /No listed companies found/.test(msg) && (await p.locator(".pdfi-row").count()) === 0, msg.slice(0, 200)); await close();

  // the pdf.js worker is served from the built app as JavaScript, and the page used it without CSP trouble
  check(`[${tag}] the pdf.js worker was requested by the page`, p.reqs.length > 0, JSON.stringify(p.reqs.slice(0, 2)));
  check(`[${tag}] ... with status 200 and a JavaScript MIME type`, p.reqs.length > 0 && p.reqs.every((r) => r.status === 200 && /javascript/.test(r.type)), JSON.stringify(p.reqs.slice(0, 2)));
  const workers = fs.existsSync(DIST) ? fs.readdirSync(DIST).filter((f) => /^pdf\.worker\.min-.*\.mjs$/.test(f)) : [];
  check(`[${tag}] built app has dist/assets/pdf.worker.min-*.mjs`, workers.length === 1, workers.join(","));
  for (const w of workers) {
    const r = await p.request.get(B + "/assets/" + w);
    check(`[${tag}] ${w} is served as JavaScript`, r.ok() && /^(text|application)\/javascript/.test(r.headers()["content-type"] || ""), r.status() + " " + r.headers()["content-type"]);
  }
});

// ---------------------------------------------------------------------------------------------------- phone width, silver (30 shares)
await session(390, "pm-silver@example.com", "390px silver", async ({ p, syms, clear, choose, rows, close, tag, width }) => {
  const overflow = async (label) => { const ov = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth); check(`[${tag}] ${label}: no sideways page scroll`, ov <= 1, ov + "px"); };
  await overflow("page");
  await choose("groww_holdings.pdf");
  await overflow("review open");
  const r = await rows(); const exp = need(MAN["groww_holdings.pdf"].expected);
  check(`[${tag}] review at 390px: the ticked set is exact`, same(r.filter((x) => x.on).map((x) => x.sym), exp), r.filter((x) => x.on).map((x) => x.sym).join(","));
  const boxes = await p.locator(".pdfi-row").evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, h: r.height }; }));
  check(`[${tag}] every row is inside the screen width and at least 36 px tall (tappable)`, boxes.every((x) => x.l >= -1 && x.r <= 391 && x.h >= 36), JSON.stringify(boxes.filter((x) => x.l < -1 || x.r > 391 || x.h < 36).slice(0, 3)));
  const wrapped = await p.locator(".pdfi-row").first().evaluate((e) => { const k = [...e.children].map((c) => c.getBoundingClientRect()); return { stacked: k[1].top >= k[0].top, texts: e.innerText.replace(/\s+/g, " ") }; });
  check(`[${tag}] a row shows PDF text, company and reason`, /→|Exact match|Ticker|\w/.test(wrapped.texts) && wrapped.texts.length > 15, wrapped.texts);
  // tap a row's text (not the box): it toggles; the last row is reachable by scrolling the list
  const row0 = p.locator(".pdfi-row").first(); const was = await row0.locator("input").isChecked(); await row0.locator(".co").click(); check(`[${tag}] tapping a company's name toggles its tick`, (await row0.locator("input").isChecked()) !== was);
  await row0.locator(".co").click();
  await p.locator(".pdfi-list").evaluate((e) => { e.scrollTop = e.scrollHeight; }); await p.waitForTimeout(100);
  const lastBox = await p.locator(".pdfi-row").last().boundingBox(); const listBox = await p.locator(".pdfi-list").boundingBox();
  check(`[${tag}] after scrolling the list the last row is inside the list box`, !!lastBox && !!listBox && lastBox.y + lastBox.height <= listBox.y + listBox.height + 2 && lastBox.y >= listBox.y - 2, JSON.stringify({ lastBox, listBox }));
  await p.locator(".pdfi").scrollIntoViewIfNeeded();
  const add = p.getByRole("button", { name: /^Add \d+ selected$/ }); await add.scrollIntoViewIfNeeded(); const bb = await add.boundingBox();
  check(`[${tag}] the Add button fits the screen and can be reached`, !!bb && bb.x >= 0 && bb.x + bb.width <= 391 && bb.height >= 32, JSON.stringify(bb));
  await overflow("review scrolled");
  await add.click(); await p.waitForTimeout(300);
  check(`[${tag}] added exactly the ticked ones (${exp.length} of the plan's 30)`, same(await syms(), exp), (await syms()).join(","));
  await clear();

  // plan limit: the 66-company statement on a plan that holds 30
  await choose("groww_large_66.pdf");
  const big = await rows(), ticked = big.filter((x) => x.on).map((x) => x.sym);
  check(`[${tag}] 66-company statement: all ticked rows are exactly the held companies`, same(ticked, need(MAN["groww_large_66.pdf"].expected)), ticked.length + " ticked");
  const note = (await p.locator(".pf-miss").count()) ? await p.locator(".pf-miss").innerText() : "";
  check(`[${tag}] over the plan: the page says only the first 30 ticked ones will be added`, /only the first 30/.test(note), note);
  await p.getByRole("button", { name: /^Add 30 selected$/ }).click(); await p.waitForTimeout(400);
  const got = await syms();
  check(`[${tag}] exactly 30 added, all of them ticked ones, in the PDF's order`, got.length === 30 && got.every((s) => ticked.includes(s)) && same(got, ticked.slice(0, 30)), got.length + " added");
  await clear();

  // the other layouts on a phone: still exact
  for (const name of ["zerodha_console.pdf", "nsdl_cas.pdf", "two_tables_sold_first.pdf", "groww_wrapped_middle.pdf", "lookalikes_1.pdf", "text_lines.pdf"]) {
    await choose(name); const rr = await rows(); const tk = rr.filter((x) => x.on).map((x) => x.sym);
    check(`[${tag}] ${name}: ticked set exact`, same(tk, need(MAN[name].expected)), tk.sort().join(","));
    await overflow(name);
    const n = (await p.locator(".pdfi-note").count()) ? await p.locator(".pdfi-note").innerText() : ""; if (name.startsWith("two_tables")) check(`[${tag}] ${name}: note explains which table was used`, /more than one table/.test(n), n);
    await close();
  }
  // password and error panels fit the phone too
  await choose("protected_statement.pdf"); await overflow("password box");
  const inp = await p.locator("input[aria-label='PDF password']").boundingBox(); check(`[${tag}] password box fits the screen`, !!inp && inp.x >= 0 && inp.x + inp.width <= 391, JSON.stringify(inp)); await close();
  await choose("scanned.pdf"); await overflow("scan message"); await close();
});

await b.close(); fs.rmSync(TMP, { recursive: true, force: true });
console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
