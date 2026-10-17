// Alerts in the demo build (VITE_DEMO=1):  node e2e/alerts.mjs http://127.0.0.1:4180/finlit-platform
import { chromium } from "playwright";
const base = (process.argv[2] || "http://127.0.0.1:4180/finlit-platform").replace(/\/$/, "");
const out = []; const check = (n, ok, d = "") => { out.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
const mk = async (plan, w = 1366) => { const c = await browser.newContext({ viewport: { width: w, height: 1000 } }); await c.addInitScript((p) => localStorage.setItem("finlit-plan", p), plan); const p = await c.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(e.message)); return p; };

let p = await mk("gold");
await p.goto(base + "/alerts", { waitUntil: "networkidle" }); await p.waitForTimeout(600);
check("seeded: sample alerts listed", (await p.locator(".alx-c").count()) === 4, String(await p.locator(".alx-c").count()));
check("seeded: bell shows 1 unread", (await p.locator(".nt-n").innerText()) === "1");
check("sidebar item carries the unread count", /1 new/.test(await p.locator('a[href$="/alerts"].side-i').innerText()));
await p.locator(".nt-btn").click();
check("bell panel lists the RSI alert", /RSI \(14\) is now 29\.4, below your target of 30/.test(await p.locator(".nt-p").innerText()));
await p.keyboard.press("Escape");

// create an alert through the form
await p.locator("#alx-stock").fill("RELI"); await p.waitForTimeout(300);
await p.locator(".alx-dd button").first().click();
await p.locator("#alx-metric").selectOption("pe"); await p.locator("#alx-op").selectOption("below"); await p.locator("#alx-val").fill("5");
check("preview sentence reads back the rule", /P\/E falls to or below 5/.test(await p.locator(".alx-sentence").innerText()));
await p.getByRole("button", { name: /Create alert/ }).click(); await p.waitForTimeout(300);
check("create: saved message", await p.locator(".alx-ok").count() === 1);
check("create: list grows to 5", (await p.locator(".alx-c").count()) === 5);
await p.getByRole("button", { name: /Create alert/ }).click(); await p.waitForTimeout(200);
check("duplicate is refused", /already have this alert/.test(await p.locator(".alx-warn").innerText()));

// fire everything
await p.getByRole("button", { name: "Make my alerts fire" }).click(); await p.waitForTimeout(500);
check("toast pops: Alert triggered / View stock", (await p.locator(".alx-toast").count()) >= 1 && /View stock/.test(await p.locator(".alx-toast").first().innerText()));
check("bell count grew", Number(await p.locator(".nt-n").innerText().then((t) => t.replace("+", ""))) > 1);
await p.getByRole("tab", { name: /Triggered/ }).click();
check("history lists notices", (await p.locator(".alx-hist li").count()) >= 3);
await p.getByRole("button", { name: "Mark all read" }).first().click(); await p.waitForTimeout(200);
check("mark all read clears the badge", (await p.locator(".nt-n").count()) === 0);
await p.getByRole("tab", { name: /My alerts/ }).click();
await p.getByLabel("Delete the RELIANCE alert").first().click(); await p.getByRole("button", { name: "Delete" }).first().click(); await p.waitForTimeout(200);
check("delete removes an alert", (await p.locator(".alx-c").count()) === 4);
await p.getByRole("button", { name: "Pause", exact: true }).first().click(); await p.waitForTimeout(200);
check("pause works", (await p.locator(".alx-c.is-paused").count()) === 1);

// stock page shortcut
await p.goto(base + "/stocks/RELIANCE", { waitUntil: "networkidle" });
await p.getByRole("button", { name: "Create an alert for RELIANCE" }).click();
check("stock page: modal opens with the symbol filled", (await p.locator(".alx-modal #alx-stock").inputValue()) === "RELIANCE");
await p.keyboard.press("Escape"); check("modal closes on Escape", (await p.locator(".alx-modal").count()) === 0);
check("no page errors (gold)", p.errs.length === 0, p.errs.join("|"));

// Basic: silver metrics are locked, basic ones work, limit of 3
p = await mk("basic");
await p.goto(base + "/alerts", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
await p.locator("#alx-stock").fill("RELI"); await p.waitForTimeout(300); await p.locator(".alx-dd button").first().click();
await p.locator("#alx-metric").selectOption("overall");
check("basic: Silver metric shows the lock message and disables create", (await p.locator(".alx-warn").count()) === 1 && await p.getByRole("button", { name: /Create alert/ }).isDisabled());
await p.close();

// phone width: no sideways scroll
p = await mk("gold", 390);
await p.goto(base + "/alerts", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
check("phone: no horizontal scroll", await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), String(await p.evaluate(() => document.documentElement.scrollWidth)));
await p.screenshot({ path: "/tmp/alx-phone.png", fullPage: false });
await browser.close();
const bad = out.filter((x) => !x).length; console.log(bad ? `\n${bad} check(s) failed` : "\nall checks passed"); process.exit(bad ? 1 : 0);
