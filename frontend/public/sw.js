// Offline shell and faster repeat visits. Deliberately simple and safe:
//  - never touches /api (accounts and plan-dependent data must always come from the server),
//  - hashed build files (/assets/) are cached forever, pages are network-first with the last good page as the offline fallback.
const VERSION = "finlit-v1";
const SCOPE = self.registration.scope;
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.includes("/api/")) return;
  if (url.pathname.includes("/assets/") || /\.(woff2?|png|svg|webp)$/.test(url.pathname)) {
    e.respondWith(caches.open(VERSION).then(async (c) => (await c.match(req)) || fetch(req).then((r) => { if (r.ok) c.put(req, r.clone()); return r; })));
  } else if (req.mode === "navigate") {
    e.respondWith(fetch(req).then((r) => { if (r.ok) caches.open(VERSION).then((c) => c.put(SCOPE, r.clone())); return r; }).catch(() => caches.match(SCOPE).then((r) => r || new Response("You are offline.", { status: 503 }))));
  }
});
