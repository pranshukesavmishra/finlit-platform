import { execSync, spawn } from "node:child_process";
import { BASE, browser, newPage, api, post, login, shot, check, save, failures, OUT } from "./lib.mjs";
const b = await browser();
const p = await newPage(b, { width: 1400, height: 900 });
const lg = await login(p, "gold@test.example");
const uid = lg.user.id;
// unknown symbol
let r = await post(p, "/api/prism/reports", { symbol: "ZZUNKNOWN", statement: "consolidated" });
check("3 unknown symbol -> 404 not_found clear message", r.status === 404 && r.body.status === "not_found" && /No listed company/.test(r.body.detail), JSON.stringify(r.body));
await p.goto(BASE + "/prism/ZZUNKNOWN", { waitUntil: "networkidle" });
await p.getByRole("button", { name: /Generate the Prism rating/ }).click();
await p.waitForTimeout(2500);
const ut = await p.locator("main").innerText();
check("3 unknown symbol UI shows clear error", /No listed company|not found|could not find/i.test(ut), ut.replace(/\n+/g, " ").slice(0, 300));
await shot(p, "3-unknown-symbol");
// invalid symbol
r = await post(p, "/api/prism/reports", { symbol: "bad symbol!", statement: "consolidated" });
check("3 invalid symbol -> 422", r.status === 422, r.status);
// concurrent: same company twice with refresh
const [a, c] = await Promise.all([post(p, "/api/prism/reports", { symbol: "MARUTI", refresh: true }), post(p, "/api/prism/reports", { symbol: "MARUTI", refresh: true })]);
check("3 two concurrent generations (same company): both 200, same report id", a.status === 200 && c.status === 200 && a.body.id === c.body.id, `${a.status}/${c.status} ${a.body.id === c.body.id}`);
const [d, e, f] = await Promise.all([post(p, "/api/prism/reports", { symbol: "NTPC" }), post(p, "/api/prism/reports", { symbol: "DLF" }), post(p, "/api/prism/reports", { symbol: "TCS" })]);
check("3 three concurrent different companies: 200s or one calm 429 busy (slots=2)", [d, e, f].every((x) => x.status === 200 || (x.status === 429 && x.body.status === "busy")), [d, e, f].map((x) => x.status).join(","));
// daily limit
const day = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10).replace(/-/g, "");
execSync(`redis-cli -n 12 set prism:day:${uid}:${day} 20 EX 3600`);
r = await post(p, "/api/prism/reports", { symbol: "HDFCBANK", refresh: true });
check("3 daily limit -> 429 limit with Retry-After", r.status === 429 && r.body.status === "limit" && Number(r.headers["retry-after"]) > 0, JSON.stringify(r.body) + " ra=" + r.headers["retry-after"]);
await p.goto(BASE + "/prism/MARUTI", { waitUntil: "networkidle" });
await p.getByRole("button", { name: /^Recalculate/ }).first().click();
await p.waitForTimeout(2000);
const lt = await p.locator("main").innerText();
check("3 daily limit UI message", /20|today|limit/i.test(lt) && /calculations|allowance|used/i.test(lt), "");
await shot(p, "3-limit");
execSync(`redis-cli -n 12 del prism:day:${uid}:${day}`);
// site backend down
execSync("pkill -f site_api_dev || true", { shell: "/bin/bash" });
await p.waitForTimeout(1500);
r = await post(p, "/api/prism/reports", { symbol: "HDFCBANK", refresh: true });
check("3 site backend down -> 502 unavailable, calm text, no internals", r.status === 502 && r.body.status === "unavailable" && !/Traceback|127\.0\.0\.1|httpx|Connect/i.test(JSON.stringify(r.body)), JSON.stringify(r.body));
const used = execSync(`redis-cli -n 12 get prism:day:${uid}:${day}`).toString().trim();
check("3 failed calculation did not use up the allowance", used === "" || used === "0", "counter=" + used);
await p.goto(BASE + "/prism/HDFCBANK", { waitUntil: "networkidle" });
await p.getByRole("button", { name: /Generate the Prism rating/ }).click().catch(() => {});
await p.waitForTimeout(2500);
const dt = await p.locator("main").innerText();
check("3 site down UI: calm 'could not finish' message", /could not finish|try again|not connected|unavailable/i.test(dt) && !/Traceback|ECONN/.test(dt), dt.replace(/\n+/g, " ").slice(0, 300));
await shot(p, "3-site-down");
// stock page with site down and stored report: still shows stored
await p.goto(BASE + "/stocks/RELIANCE", { waitUntil: "networkidle" });
check("3 site down: stock page still shows the stored Prism report", /OUT OF 100/i.test(await p.locator(".pz-right").innerText()), "");
check("3 no page errors", p.errs.length === 0, p.errs.join(" | "));
await b.close(); save("s3");
process.exit(failures() ? 1 : 0);
