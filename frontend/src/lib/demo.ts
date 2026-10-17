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

export function installDemo() {
  if (!DEMO) return;
  const real = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const u = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return /\/api\//.test(u) && !u.includes("/demo/") ? demoFetch(input, init) : real(input, init);
  };
}
