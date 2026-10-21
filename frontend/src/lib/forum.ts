// Discussion forum: API client and the pure logic the pages use. Text is plain; links are the only thing ever made clickable, and only http(s).
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiSend } from "./api";

// Same limits as backend/finlit/forum_rules.py (a backend test checks they match; the server is what enforces them).
export const TITLE_MIN = 8, TITLE_MAX = 140;
export const BODY_MIN = 20, BODY_MAX = 4000;
export const REPLY_MIN = 2, REPLY_MAX = 2000;
export const MAX_LINKS = 2;

export type Author = { handle: string; staff: boolean };
export type Post = {
  id: number; threadId: number; kind: "thread" | "reply"; symbol: string; company: string; title: string | null; body: string | null; author: Author;
  createdAt: string; editedAt: string | null; lastActivityAt: string; upvotes: number; voted: boolean; replies: number;
  status: "visible" | "held" | "hidden" | "deleted" | "removed"; mine: boolean; note: string | null; canEdit: boolean; editableSeconds: number;
};
export type Page<T> = { total: number; page: number; per: number; pages: number } & T;
export type ForumMe = { signedIn: boolean; handle: string | null; canPost: boolean; banned: boolean; moderator: boolean };
export type QueueItem = {
  id: number; threadId: number; kind: string; symbol: string; title: string | null; body: string; status: string; flagReasons: string[]; createdAt: string;
  author: { userId: string; handle: string; banned: boolean; email: string }; reports: { reason: string; note: string | null; at: string; by: string }[];
};

export const DISCLAIMER = "Discussion is for information and opinion only. It is not investment advice, a recommendation or a solicitation to buy or sell any security. "
  + "Members are not SEBI-registered advisers unless they say so. Do your own research and consult a registered adviser before you invest.";

export const forumMe = () => useQuery<ForumMe>({ queryKey: ["forum", "me"], queryFn: () => apiGet("/api/forum/me"), staleTime: 60_000 });
export const useStats = (symbol: string) => useQuery<{ threads: number; replies: number; lastActivityAt: string | null }>({
  queryKey: ["forum", "stats", symbol], queryFn: () => apiGet(`/api/forum/stats?symbol=${encodeURIComponent(symbol)}`), staleTime: 60_000, retry: false });
export const send = apiSend;

export type Token = { t: "text"; v: string } | { t: "link"; href: string; label: string };
const URL_AT = /https?:\/\/[^\s<>"'`]+/gi;
/** Split plain text into text and http(s) links. Nothing else becomes a link, and no markup is ever produced. */
export function linkify(text: string): Token[] {
  const out: Token[] = []; let last = 0;
  for (const m of text.matchAll(URL_AT)) {
    const raw = m[0].replace(/[.,;:!?)\]}]+$/, ""), at = m.index ?? 0;
    let u: URL;
    try { u = new URL(raw); } catch { continue; }
    if ((u.protocol !== "http:" && u.protocol !== "https:") || u.username || u.password) continue;
    if (at > last) out.push({ t: "text", v: text.slice(last, at) });
    out.push({ t: "link", href: u.href, label: u.host.replace(/^www\./, "") + (u.pathname.length > 1 ? "/…" : "") });
    last = at + raw.length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

/** Quick check before sending, to save a round trip. The server decides; this only catches the obvious. */
export function draftProblem(kind: "thread" | "reply", title: string, body: string): string {
  const t = title.trim(), b = body.trim();
  if (kind === "thread" && (t.length < TITLE_MIN || t.length > TITLE_MAX)) return `The title needs ${TITLE_MIN} to ${TITLE_MAX} characters.`;
  const [lo, hi] = kind === "thread" ? [BODY_MIN, BODY_MAX] : [REPLY_MIN, REPLY_MAX];
  if (b.length < lo || b.length > hi) return `Write ${lo} to ${hi} characters.`;
  if ((`${t}\n${b}`.match(URL_AT) || []).length > MAX_LINKS) return `Please keep to ${MAX_LINKS} links or fewer.`;
  return "";
}
export const validHandle = (h: string) => /^[A-Za-z][A-Za-z0-9_]{2,19}$/.test(h);

export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
/** Page numbers to show: first, last, and two either side of the current page. */
export function pageWindow(page: number, pages: number): (number | "…")[] {
  const keep = new Set([1, pages, page - 2, page - 1, page, page + 1, page + 2].filter((n) => n >= 1 && n <= pages));
  const out: (number | "…")[] = []; let prev = 0;
  for (const n of [...keep].sort((a, b) => a - b)) { if (n - prev > 1) out.push("…"); out.push(n); prev = n; }
  return out;
}
