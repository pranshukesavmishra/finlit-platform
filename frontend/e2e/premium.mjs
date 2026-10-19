// Gold dashboards (hub, market events & index, fundamentals, premium report): content, tab speed (< 1 s), plan lock, phone width.
// FinEdge feeds are replaced by realistic sample data in the browser; the report uses the real research API.
// Needs local members pm-gold@example.com and pm-basic@example.com (finlit.auth.cli create-member) with PM_PASSWORD.
//   PM_PASSWORD=... node e2e/premium.mjs   (screenshots go to /tmp/claude-0/shots or $SHOTS)
import { chromium } from "playwright";
const B = process.argv[2] || "http://localhost:4173", OUT = process.env.SHOTS || "/tmp/claude-0/shots";
const now = new Date().toISOString(), d = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
const feed = (items) => ({ items, total: items.length, provider: "FinEdge", fetchedAt: now, cached: true });
const IDX = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100", "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA"];
const F = {
  ipo: feed([["Aurobind Precision Ltd", "EQ", "Open", -1, 2, "₹412 - ₹433", "₹1,250 Cr", "3.4x"], ["Sahyadri Renewables", "SME", "Upcoming", 3, 6, "₹96 - ₹101", "₹48 Cr", null], ["Kaveri Logistics Ltd", "EQ", "Upcoming", 5, 8, "₹220 - ₹232", "₹860 Cr", null], ["Meridian Health Ltd", "EQ", "Closed", -9, -6, "₹610 - ₹642", "₹2,100 Cr", "41.2x"]].map(([company_name, security_type, ipo_status, a, b, price_range, issue_size, subscription]) => ({ company_name, symbol: null, security_type, ipo_status, start_date: d(a), end_date: d(b), price_range, issue_size, subscription, current_bids: null, exchange: "NSE, BSE" }))),
  results: feed(["TCS", "INFY", "HDFCBANK", "RELIANCE", "WIPRO", "ICICIBANK", "HCLTECH", "BAJFINANCE"].map((s, i) => ({ symbol: s, company_name: s + " Ltd", expected_result_date: d(i + 1) }))),
  announcements: feed(Array.from({ length: 22 }, (_, i) => ({ symbol: ["RELIANCE", "TCS", "INFY", "ITC"][i % 4], category: ["Board Meeting", "Press Release", "Investor Presentation", "Outcome of Board Meeting"][i % 4], description: "Intimation under Regulation 30 of SEBI (LODR) Regulations, 2015 regarding the schedule of analyst and institutional investor meetings for the quarter.", date: d(-(i % 6)), document_url: "https://www.bseindia.com/x.pdf" }))),
  transcripts: feed(["TCS", "INFY", "HCLTECH"].map((s, i) => ({ symbol: s, category: "Earnings Call Transcript", description: `Transcript of the Q2 FY27 earnings conference call of ${s}`, date: d(-i), document_url: "https://www.bseindia.com/t.pdf" }))),
  indices: feed(IDX.map((n, i) => ({ index_symbol: n, index_name: n, quote_date: d(-1), close_price: 24000 - i * 1700 + i * 13.7, open_price: null, high_price: 24100 - i * 1700, low_price: 23880 - i * 1700, change_pct: [0.62, -0.41, 1.18, 0.07, -0.93, 0.35, -0.12, 0.88][i], points_change: [148.2, -210.5, 420.1, 12.4, -160.3, 80.9, -25.6, 190.4][i], pe: 22.4 - i, pb: 3.6 - i * 0.2, div_yield: 1.2 + i * 0.1, market_cap: null, volume: null, turnover: null }))),
  valuations: feed(Array.from({ length: 30 }, (_, i) => ({ index_symbol: "NIFTY 50", index_name: "NIFTY 50", quote_date: d(-i), close_price: 24100 - i * 19, pe: 22.4 - i * 0.03, pb: 3.61, div_yield: 1.21 }))),
};
const COMM = { items: ["Aluminium", "Basic Metals", "Cement", "Coal", "Crude Oil", "Electricity", "Fertilizers", "Natural Gas", "Refinery Products", "Steel"].map((name, i) => ({ code: String(100 + i), name, weight: 2 + i })), provider: "FinEdge", fetchedAt: now };
const HIST = { code: "100", history: Array.from({ length: 14 }, (_, i) => { const m = new Date(2026, 8 - i, 1); return { period: m.toISOString().slice(0, 7), label: m.toLocaleString("en", { month: "short" }) + "-" + m.getFullYear(), value: 162.4 - i * 0.9 }; }), changes: [], provider: "FinEdge", fetchedAt: now };
const yrs = ["Mar-26", "Mar-25", "Mar-24", "Mar-23", "Mar-22", "Mar-21"];
const row = (category, label, base, g = 1.09) => ({ category, label, history: yrs.map((period, i) => ({ period, value: Math.round(base / Math.pow(g, i)), change: null })) });
const FUND = { instrument: { symbol: "RELIANCE", name: "Reliance Industries Ltd" }, statementType: "consolidated", generatedAt: now, quote: { price: 1210, changePct: -1.09 },
  highlights: [{ label: "P/E", value: 24.6, benchmark: 18.2 }, { label: "P/B", value: 2.1, benchmark: 1.8 }, { label: "ROE", value: 9.2, benchmark: 12.4 }, { label: "ROCE", value: 10.1, benchmark: 13 }, { label: "Revenue", value: 1001122, period: "Mar-26" }, { label: "Net Profit", value: 79020, period: "Mar-26" }],
  ratios: [["P/E", 24.6, 18.2], ["P/B", 2.1, 1.8], ["ROE", 9.2, 12.4], ["ROCE", 10.1, 13], ["Debt to Equity", 0.41, 0.6], ["Current Ratio", 1.12, 1.3], ["Dividend Yield", 0.42, 1.1]].map(([name, company_value, sector_value]) => ({ name, company_value, sector_value })),
  profitabilityRatios: [row("operating_margin", "Operating margin", 17, 1.01), row("net_margin", "Net margin", 8, 1.01)],
  incomeStatement: { units_in: "₹ Cr", income_statement: [row("revenue", "Revenue", 1001122), row("operating_profit", "Operating profit", 172000), row("other_income", "Other income", 17000), row("interest", "Interest", 24000, 1.03), row("net_profit", "Net profit", 79020)] },
  balanceSheet: { units_in: "₹ Cr", balance_sheet: [row("equity", "Equity", 840000), row("borrowings", "Borrowings", 351000, 1.04), row("total_assets", "Total assets", 1950000)] },
  cashFlow: { units_in: "₹ Cr", cash_flow: [row("cfo", "Cash from operations", 178000), row("cfi", "Cash from investing", -140000), row("cff", "Cash from financing", -21000, 1.02)] },
  shareholding: [row("promoters", "Promoters", 50, 1), row("fii", "FII", 19, 1.01), row("mutual_funds", "Mutual funds", 9, 0.97), row("retail_and_other", "Retail and other", 22, 1)],
  ownershipStructure: [row("total_shares", "Total shares (Cr)", 1353, 1), row("pledged_percent", "Pledged shares %", 0, 1), row("total_shareholders", "Total shareholders", 4450000, 1.08)],
  shareholdingDetails: [{ label: "Promoter & Promoter Group", history: [{ period: "Sep-26", value: 50.1 }], children: [{ label: "Srichakra Commercials LLP", history: [{ period: "Sep-26", value: 6.8 }] }, { label: "Devarshi Commercials LLP", history: [{ period: "Sep-26", value: 6.4 }] }] }, { label: "Public - Institutions", history: [{ period: "Sep-26", value: 28.2 }], children: [{ label: "Life Insurance Corporation of India", history: [{ period: "Sep-26", value: 6.5 }] }] }],
  revenueSegments: [row("o2c", "Oil to chemicals", 600000), row("retail", "Retail", 300000, 1.15), row("digital", "Digital services", 140000, 1.14)],
  corporateActions: [{ type: "Dividend", name: "Final dividend", ex_date: "2026-08-14", amount: 5.5 }, { type: "Bonus", name: "Bonus issue 1:1", ex_date: "2024-10-28", ratio: "1:1" }],
  competitors: [{ name: "Indian Oil Corporation", symbol: "IOC", sector: "Refineries" }, { name: "Bharat Petroleum", symbol: "BPCL", sector: "Refineries" }],
};
const b = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
let fails = 0; const check = (n, ok, x = "") => { if (!ok) fails++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? " — " + x : "")); };
for (const [who, w, h] of [["gold", 1366, 900], ["gold", 390, 844], ["basic", 1366, 900]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h } }); const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  await p.route("**/api/premium/**", (r) => { const u = new URL(r.request().url()); const s = u.pathname.replace("/api/premium", "");
    const body = s.startsWith("/markets/") ? F[s.split("/")[2]] : s === "/commodities" ? COMM : s.startsWith("/commodities/") ? HIST : s === "/fundamentals" ? FUND : null;
    return body ? r.fulfill({ json: body }) : r.fulfill({ status: 404, json: {} }); });
  const me = await (await ctx.request.get(B + "/api/auth/me")).json();
  const lr = await ctx.request.post(B + "/api/auth/login", { headers: { Origin: B, "X-CSRF-Token": me.csrf || "" }, data: { email: `pm-${who}@example.com`, password: process.env.PM_PASSWORD } });
  check(`${who} signs in`, lr.ok(), String(lr.status()));
  const tag = `${who}-${w}`;
  await p.goto(B + "/premium", { waitUntil: "networkidle" }); await p.waitForTimeout(500); await p.screenshot({ path: `${OUT}/${tag}-hub.png`, fullPage: true });
  check(`${tag} hub shows three tools`, (await p.locator(".pm-card").count()) === 3);
  await p.goto(B + "/premium/markets", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
  if (who === "basic") { check(`${tag} markets locked`, (await p.getByText("This dashboard is part of the Gold plan").count()) > 0); await p.screenshot({ path: `${OUT}/${tag}-locked.png` }); await ctx.close(); continue; }
  for (const t of ["IPO calendar", "Results calendar", "Announcements", "Call transcripts", "Indices live", "Index valuation history", "Commodities"]) {
    const sel = t === "Index valuation history" ? ".pm-verdict" : ".pm-t tbody tr";   // the valuation tab is a chart with a verdict, not a table
    const t0 = Date.now(); await p.getByRole("tab", { name: t }).click(); await p.waitForSelector(sel, { timeout: 4000 }).catch(() => null);
    const ms = Date.now() - t0, rows = await p.locator(sel).count();
    check(`${tag} ${t}: ${rows} rows in ${ms} ms`, rows > 0 && ms < 1000);
    await p.screenshot({ path: `${OUT}/${tag}-m-${t.replace(/\W+/g, "")}.png`, fullPage: true });
  }
  await p.goto(B + "/premium/fundamentals?c=RELIANCE", { waitUntil: "networkidle" }); await p.waitForTimeout(500);
  for (const t of ["Snapshot", "Income statement", "Balance sheet", "Cash flow", "Ratios", "Shareholders", "Peers & actions"]) {
    await p.getByRole("tab", { name: t }).click(); await p.waitForTimeout(200);
    const has = (await p.locator(".pm-t tbody tr, .pm-kpi").count()) > 0; check(`${tag} fundamentals ${t}`, has);
    await p.screenshot({ path: `${OUT}/${tag}-f-${t.replace(/\W+/g, "")}.png`, fullPage: true });
  }
  await p.goto(B + "/premium/report/RELIANCE", { waitUntil: "networkidle" }); await p.waitForTimeout(1200);
  check(`${tag} report renders`, (await p.locator("article.pm-rep h1").count()) === 1); await p.screenshot({ path: `${OUT}/${tag}-report.png`, fullPage: true });
  const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth); check(`${tag} no sideways scroll on report`, over <= 1, String(over));
  check(`${tag} no page errors`, errs.length === 0, errs.join(" | "));
  await ctx.close();
}
await b.close(); console.log(fails ? `${fails} FAILED` : "ALL PASSED"); process.exit(fails ? 1 : 0);
