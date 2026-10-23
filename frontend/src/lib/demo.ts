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
  if (path === "/api/screener/top") {
    const s = JSON.parse(await (await file("RELIANCE/summary.json")).text());
    return json({ rows: [{ symbol: "RELIANCE", band: s.score.band.key, overall: s.score.overall, price: s.quote.price, sector: s.profile.sector, pe: null, roe: null }] });
  }
  const m = path.match(/^\/api\/stocks\/([A-Za-z0-9&_.-]+)(?:\/([a-z0-9-]+))?$/);
  if (m) {
    const [, sym, section] = m;
    if (sym.toUpperCase() !== "RELIANCE") return json({ status: "demo", detail: "This preview includes the RELIANCE report only. The live site has every listed stock." }, 404);
    if (!section) return file("RELIANCE/summary.json");
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
