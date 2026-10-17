/** Only follow `next` links that stay on this site (blocks open redirects such as //evil.example). */
export function safeNext(raw: string | null, fallback = "/dashboard"): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || /[\r\n]/.test(raw)) return fallback;
  return raw;
}
