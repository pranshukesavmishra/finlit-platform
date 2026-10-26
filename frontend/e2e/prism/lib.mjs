// FinLit Prism end-to-end checks (run order s1a, s1b, s2b, s2c, s3, s3b, s456). Needs the local stack (dev/run_stack.sh style) with members
// gold/silver/basic@test.example and admin@test.example; see docs/prism/DEPLOY.md. Not part of CI.
// E2E_BASE (default http://localhost:4175) is the site, E2E_OUT (default <tmp>/finlit-e2e) where screenshots and results go.
// With no server reachable (or no playwright installed) every script prints a SKIP line and exits 0 instead of failing.
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const require = createRequire(import.meta.url);
export const BASE = process.env.E2E_BASE || "http://localhost:4175";
export const OUT = process.env.E2E_OUT || path.join(os.tmpdir(), "finlit-e2e");
fs.mkdirSync(OUT, { recursive: true });
export const skip = (why) => { console.log(`SKIP  Prism end-to-end checks not run: ${why}`); process.exit(0); };
let chromium;
try { ({ chromium } = require("playwright")); } catch { skip("playwright is not installed (npm i -D playwright; npx playwright install chromium)"); }
try { await fetch(BASE + "/", { signal: AbortSignal.timeout(4000) }); } catch { skip(`no server is reachable at ${BASE} (start the local stack, or set E2E_BASE)`); }
export const PW = "E2e-Pass-Word-91x";
export const ADMIN_PW = "Zq7-Pass-Word-91x";
let failed = 0;
export const results = [];
export const check = (name, ok, detail = "") => { if (!ok) failed++; results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  | " + String(detail).slice(0, 300) : ""}`); };
export const failures = () => failed;
export async function browser() { return chromium.launch(); }
export async function newPage(b, { width = 1400, height = 900, errs } = {}) {
  const ctx = await b.newContext({ viewport: { width, height }, acceptDownloads: true });
  await ctx.addInitScript(() => { try { localStorage.setItem("finlit-theme", "light"); } catch {} });
  const p = await ctx.newPage();
  p.errs = errs || [];
  p.on("pageerror", (e) => p.errs.push("pageerror: " + String(e)));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) p.errs.push("console: " + m.text()); });
  return p;
}
export async function api(p, path, init = {}) {
  if (p.url() === "about:blank") await p.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  return p.evaluate(async ([u, i]) => {
    const r = await fetch(u, { credentials: "same-origin", ...i });
    const ct = r.headers.get("content-type") || "";
    let body = null; try { body = ct.includes("json") ? await r.json() : (await r.text()).slice(0, 300); } catch {}
    return { status: r.status, body, headers: Object.fromEntries(r.headers.entries()) };
  }, [path, init]);
}
import { execSync } from "node:child_process";
export async function login(p, email, pw = PW) {
  try { execSync("redis-cli -n 12 --scan --pattern 'rl:login*' | xargs -r redis-cli -n 12 del"); } catch {}
  await p.goto(BASE + "/login", { waitUntil: "domcontentloaded" });
  const r = await p.evaluate(async ([e, pw]) => {
    const res = await fetch("/api/auth/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: e, password: pw }) });
    return { status: res.status, body: await res.json() };
  }, [email, pw]);
  if (r.status !== 200) throw new Error("login failed " + JSON.stringify(r));
  p.csrf = r.body.csrf;
  return r.body;
}
export const post = (p, path, body) => api(p, path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": p.csrf || "" }, body: JSON.stringify(body) });
export const shot = (p, name, opts = {}) => p.screenshot({ path: `${OUT}/${name}.png`, ...opts });
export function save(name) { fs.writeFileSync(`${OUT}/${name}.json`, JSON.stringify(results, null, 1)); }
