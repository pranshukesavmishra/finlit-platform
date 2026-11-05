// FinLit AMFI relay: a free Cloudflare Worker that fetches three public AMFI files for the FinLit server.
// Why: www.amfiindia.com does not answer from the AWS server's address, so the nightly "facts" job cannot read the expense ratio and the fund size.
// What it does: answers GET requests for exactly three AMFI paths by fetching the same path on www.amfiindia.com and returning the answer.
// What it never does: forward any other path, any non-GET request, or any request without the shared key. No data is stored here.
const ALLOW = [
  /^\/api\/populate-ter-month$/,
  /^\/api\/populate-te-rdata-revised$/,
  /^\/api\/average-aum-schemewise$/,
];

export default {
  async fetch(request, env) {
    if (request.method !== "GET") return new Response("method not allowed", { status: 405 });
    if (!env.RELAY_KEY || request.headers.get("X-Relay-Key") !== env.RELAY_KEY) return new Response("forbidden", { status: 403 });
    const u = new URL(request.url);
    if (!ALLOW.some((rule) => rule.test(u.pathname))) return new Response("not found", { status: 404 });
    const upstream = await fetch("https://www.amfiindia.com" + u.pathname + u.search, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; FinLitRelay/1.0)", "Accept": request.headers.get("Accept") || "*/*" },
      cf: { cacheTtl: 300, cacheEverything: true },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/octet-stream", "Cache-Control": "public, max-age=300" },
    });
  },
};
