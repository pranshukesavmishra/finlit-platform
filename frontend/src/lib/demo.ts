// DEMO MODE (VITE_DEMO=1): the site runs with no backend. Calls to /api/* are answered from saved files in
// /demo (real RELIANCE report exported from the research service, the real portfolio report, sample posts).
// Forms accept input but nothing is sent anywhere. Used to show the front end working before servers exist.
export const DEMO = import.meta.env.VITE_DEMO === "1";
const BASE = import.meta.env.BASE_URL;

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
const file = (path: string) => fetch(`${BASE}demo/${path}`).then((r) => r.text()).then((t) => new Response(t, { headers: { "Content-Type": "application/json" } }));

async function demoFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.href);
  const path = url.pathname.replace(/^.*?(\/api\/)/, "/api/");
  const method = (init?.method || "GET").toUpperCase();

  if (method !== "GET") {
    if (path === "/api/contact" || path === "/api/service-enquiry") return json({ id: "demo" }, 201);
    if (path === "/api/chat") return json({ response: "This is a demo preview, so the live assistant is switched off. Use the guided menu above to explore services and pricing." });
    if (path === "/api/content/admin/login") return json({ detail: "Admin sign-in is disabled in the demo." }, 401);
    return json({ detail: "Not available in the demo." }, 405);
  }
  if (path === "/api/stocks/search-index") return file("search-index.json");
  if (path === "/api/screener/universe") return file("screener.json");
  if (path === "/api/search/quotes") return file("search-quotes.json");
  if (/^\/api\/stocks\/[^/]+\/leadership$/.test(path)) return json(sampleLeadership());
  if (path === "/api/prism/history") return json(sampleHistory(url.searchParams.get("symbol") || "RELIANCE", url.searchParams.get("statement") || "consolidated"));
  if (path === "/api/macro") return file("macro.json");
  if (path === "/api/flows") return file("flows.json");
  if (path === "/api/indices") return file("indices.json");
  if (path === "/api/indices/NIF50/history") return file("index-nif50.json");
  if (path === "/api/screener/top") {
    const s = JSON.parse(await (await file("RELIANCE/summary.json")).text());
    return json({ rows: [{ symbol: "RELIANCE", band: s.score.band.key, overall: s.score.overall, price: s.quote.price, sector: s.profile.sector, pe: null, roe: null }] });
  }
  const m = path.match(/^\/api\/stocks\/([A-Za-z0-9&_.-]+)(?:\/([a-z0-9-]+))?$/);
  if (m) {
    const [, sym, section] = m;
    if (sym.toUpperCase() !== "RELIANCE") return json({ status: "demo", detail: "This preview includes the RELIANCE report only. The live site has every listed stock." }, 404);
    if (!section) return file("RELIANCE/summary.json");
    if (section === "intraday") return json({ status: "not_connected", detail: "Intraday prices are not available in the demo." }, 503);
    if (section === "price") return file(`RELIANCE/price-${(url.searchParams.get("range") || "1Y").toUpperCase()}.json`);
    return file(`RELIANCE/${section}.json`);
  }
  if (path === "/api/ipos") return json({ ipos: sampleIpos() });
  if (path === "/api/feed") return json({ items: sampleFeed(url.searchParams.get("kind") || "news", (url.searchParams.get("symbol") || "").split(",").filter(Boolean), (url.searchParams.get("q") || "").toLowerCase()) });
  if (path === "/api/portfolio/report") return file("portfolio.json");
  if (path === "/api/content") return file("content.json");
  const c = path.match(/^\/api\/content\/([a-z0-9-]+)$/);
  if (c) {
    const items = JSON.parse(await (await file("content.json")).text());
    const hit = items.find((i: { slug: string }) => i.slug === c[1]);
    return hit ? json(hit) : json({ detail: "Published content was not found." }, 404);
  }
  if (path === "/api/market-ticker") return json({ detail: "Live prices are not available in the demo." }, 503);
  return json({ detail: "Not available in the demo." }, 404);
}

// Demo calendar content: clearly labelled sample entries with dates relative to today, so the pages always look alive.
const iso = (offset: number) => { const d = new Date(); d.setDate(d.getDate() + offset); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
function sampleIpos() {
  const mk = (id: number, name: string, sector: string, kind: string, o: number, c: number, l: number | null, lo: number, hi: number, lot: number, size: number, lp: number | null) => {
    const status = o > 0 ? "upcoming" : c >= 0 ? "open" : l !== null && l <= 0 ? "listed" : "closed";
    return { id, name: `${name} (sample)`, symbol: null, kind, sector, status, openDate: iso(o), closeDate: iso(c), listingDate: l === null ? null : iso(l), priceLow: lo, priceHigh: hi, lotSize: lot, issueSizeCr: size, listingPrice: lp, note: "Sample entry for the demo preview.", link: null };
  };
  return [mk(1, "Sample Aarav Foods Ltd", "FMCG", "mainboard", 2, 4, 9, 210, 221, 67, 640, null), mk(2, "Sample Nova Power Ltd", "Power", "mainboard", -1, 1, 6, 98, 104, 144, 1250, null), mk(3, "Sample Vedant Labs Ltd", "Pharma", "sme", 9, 11, 16, 62, 66, 2000, 48, null),
    mk(4, "Sample Orbit Systems Ltd", "IT Services", "mainboard", -9, -6, -1, 400, 420, 35, 880, 478), mk(5, "Sample Kaveri Motors Ltd", "Auto", "mainboard", -16, -13, -8, 150, 158, 94, 520, 149), mk(6, "Sample Prisma Retail Ltd", "Retail", "sme", -5, -3, 2, 90, 95, 1200, 72, null)];
}
function sampleFeed(kind: string, symbols: string[], q: string) {
  const co: [string, string][] = [["RELIANCE", "Reliance Industries Ltd"], ["SMP-BAN1", "Sample Bank Alpha Ltd"], ["SMP-SYS1", "Sample Systems Alpha Ltd"], ["SMP-MOT1", "Sample Motors Alpha Ltd"], ["SMP-PHA1", "Sample Pharma Alpha Ltd"], ["SMP-CON1", "Sample Consumer Alpha Ltd"]];
  let id = 1; const items: Record<string, unknown>[] = [];
  const add = (k: string, title: string, i: number, off: number, category: string, extra: Record<string, unknown> = {}) => items.push({ id: id++, kind: k, title, symbol: co[i][0], company: co[i][1], source: "Sample", link: k === "document" ? "https://example.com/sample.pdf" : null, date: iso(off), category, period: null, summary: null, auto: false, ...extra });
  co.forEach((_, i) => {
    add("result", "Board meeting to approve quarterly results", i, 2 + i * 3, "Board meeting", { period: "Q2 FY27" });
    add("result", "Outcome: financial results for the quarter", i, -3 - i * 4, "Financial Results", { period: "Q1 FY27", link: "https://example.com/sample.pdf" });
    add("news", "Credit rating reaffirmed by the rating agency", i, -i, "Credit Rating"); add("news", "Intimation of analyst and investor meet", i, -2 - i, "Analyst / Investor Meet");
    add("document", "Annual report for the year", i, -20 - i, "Annual Report"); add("document", "Investor presentation for the quarter", i, -4 - i, "Investor Presentation");
  });
  return items.filter((x) => x.kind === kind && (!symbols.length || symbols.includes(String(x.symbol))) && (!q || String(x.title).toLowerCase().includes(q) || String(x.company).toLowerCase().includes(q)))
    .sort((a, b) => String(b.date).localeCompare(String(a.date)));
}

export function installDemo() {
  if (!DEMO) return;
  const real = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const u = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return /\/api\//.test(u) && !u.includes("/demo/") ? demoFetch(input, init) : real(input, init);
  };
}


/** Sample Prism history for the demo build only: 14 weekly points with one model-version change, so the chart can be seen. Not real figures. */
function sampleHistory(symbol: string, statement: string) {
  const days = Array.from({ length: 14 }, (_, i) => new Date(Date.UTC(2026, 6, 6 + i * 7)).toISOString().slice(0, 10));
  const points = days.map((day, i) => {
    const w = (a: number, b: number) => Math.round((a + Math.sin(i / 2 + b) * 4 + i * 0.3) * 10) / 10;
    return { day, modelVersion: i < 9 ? "3.6.10" : "3.6.11", final: w(58, 0), label: "AVERAGE", status: "RATED",
      parts: { fundamental: w(55, 1), valuation: w(42, 2), quality: w(79, 3), risk: w(88, 4) }, shortTerm: Math.round(Math.sin(i / 1.7) * 38), longTerm: Math.round(-20 + i * 3) };
  });
  return { symbol, statement, points, firstDay: days[0], note: "Sample data for the demo." };
}

/** Sample peer-leadership answer for the demo build only (the text of a Laggard company), so the header strip can be seen. Not real figures. */
function sampleLeadership() {
  return { available: true, asOf: "2026-10-30", stale: false, held: false, rank: 9, label: "laggard", rawLabel: "laggard", direction: "weakening", fundamentalNote: "stronger_than_price", fundamentalRank: 3, fundamentalOf: 10, labelSince: null,
    peerGroup: { id: "demo", name: "Trucks/Construction/Farm Machinery", short: "peers", kind: "industry", ranked: 10 }, benchmarks: { sector: { code: null, name: "peer average", kind: "peer_average", ret52: null }, market: { code: "MID150", name: "Nifty Midcap 150", ret52: null } },
    rel: { w13: null, w26: null, w52: -0.232, w52Market: -0.33 }, sectorReliability: { tier: "insufficient", hitRate6m: null, checks: 0, from: null, to: null, periods: [] }, peers: [],
    display: { chip: "Laggard", line: "9th of 10 Trucks/Construction/Farm Machinery peers", tooltip: "Sample data for the demo.",
      parts: { rank: "9th of 10 Trucks/Construction/Farm Machinery peers", sector: { pts: "\u221223.2", name: "peer average", v: -0.232 }, market: { pts: "\u221233.0", name: "Nifty Midcap 150", v: -0.33 }, direction: "weakening" },
      note: "Fundamentals rank 3rd of 10, stronger than the price", benchmarkNote: "There is no matching sector index, so the average return of the peers stands in for it." } };
}
