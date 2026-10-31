// Which build is this tab running, and is the server now serving a newer one?
// The build writes dist/version.json ({version, builtAt}); the server sends it with Cache-Control: no-cache. The same version is compiled
// into the bundle (__APP_VERSION__). When the two differ, this tab is running an older release than the server has.
export const APP_VERSION: string = typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";
export const BUILT_AT: string = typeof __BUILT_AT__ !== "undefined" ? __BUILT_AT__ : "";

export type ServerVersion = { version: string; builtAt: string };

/** Parse the body of version.json; null when it is not what we expect (an HTML page, an error, a half-written file). */
export function parseServerVersion(body: unknown): ServerVersion | null {
  if (!body || typeof body !== "object") return null;
  const v = (body as { version?: unknown }).version, t = (body as { builtAt?: unknown }).builtAt;
  if (typeof v !== "string" || !/^[\w.-]{1,40}$/.test(v)) return null;
  return { version: v, builtAt: typeof t === "string" ? t.slice(0, 40) : "" };
}

/** True when the server's version differs from the one this tab runs. Development builds (and unknown versions) never ask for a refresh. */
export function isStale(local: string, server: ServerVersion | null): boolean {
  return !!server && local !== "dev" && local !== "" && server.version !== local;
}

/** Ask the server which version it serves. Bypasses every cache; null on any failure (offline, 404, not JSON). */
export async function fetchServerVersion(fetchImpl: typeof fetch = fetch, base = import.meta.env?.BASE_URL ?? "/"): Promise<ServerVersion | null> {
  try {
    const r = await fetchImpl(`${base}version.json?_=${Date.now()}`, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!r.ok) return null;
    return parseServerVersion(await r.json());
  } catch { return null; }
}

/** Time to the next check: about every 5 minutes, spread by +-20% so a roomful of laptops does not ask in the same second. */
export function nextDelay(rand: () => number = Math.random, base = 300_000): number { return Math.round(base * (0.8 + 0.4 * rand())); }

/** "31 Oct 2026" from an ISO time; empty when unknown. */
export function builtOn(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
}

/** "Version abc1234 · built 31 Oct 2026" for the footer (support quotes this line). */
export function versionLine(v = APP_VERSION, builtAt = BUILT_AT): string {
  const on = builtOn(builtAt);
  return `Version ${v}${on ? ` · built ${on}` : ""}`;
}
