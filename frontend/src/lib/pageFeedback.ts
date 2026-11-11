// "Raise a Query" and "Share Feedback": what is captured about the page, the limits, and the call to the server (finlit/page_feedback.py).
// A message is always tagged with the page it was written on: the address (no query string), the name the page gives itself and a few short facts.
import { apiSend } from "./api";
import { pageNameFor } from "./pageHeader";

export type Kind = "query" | "feedback";
export const QUERY_MIN = 10, MESSAGE_MAX = 2000;
export const QUERY_TYPES = [["question", "A question"], ["issue", "Something is wrong"], ["clarification", "Explain this to me"]] as const;
export const FEEDBACK_TYPES = [["suggestion", "A suggestion"], ["ui_ux", "Look and feel"], ["praise", "What works well"], ["other", "Something else"]] as const;
export const RATING_WORDS = ["", "Poor", "Fair", "Good", "Very good", "Excellent"] as const;

export type PageTag = { page: string; pageName: string; context: Record<string, string> };

/** The page the member is on, as the team should see it. Pure apart from reading the document: pass `doc` in tests. */
export function pageTag(pathname: string, plan?: string | null, doc: Pick<Document, "title" | "querySelector"> | null = typeof document === "undefined" ? null : document,
  width: number = typeof window === "undefined" ? 1280 : window.innerWidth): PageTag {
  const page = ("/" + pathname.split(/[?#]/)[0].replace(/^\/+/, "")).replace(/(.)\/+$/, "$1");
  const h1 = doc?.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() ?? "";
  const title = (doc?.title ?? "").replace(/\s*[|·–—-]\s*FinLit.*$/i, "").trim();
  const pageName = pageNameFor(page) || h1 || title || page;
  const context: Record<string, string> = {};
  const sym = /^\/(?:stocks|prism|outlook|premium\/report|etfs|funds)\/([^/]+)/.exec(page);
  if (sym) context.symbol = decodeURIComponent(sym[1]).slice(0, 24);
  if (title) context.title = title.slice(0, 120);
  if (h1 && h1 !== title) context.heading = h1.slice(0, 120);
  if (plan) context.plan = plan;
  context.screen = width < 640 ? "phone" : width < 1024 ? "tablet" : "desktop";
  return { page, pageName, context };
}

export type SendArgs = { kind: Kind; tag: PageTag; category: string; message: string; rating?: number | null; email?: string };
/** Quick checks before sending, to save a trip; the server decides. */
export function draftProblem(a: Pick<SendArgs, "kind" | "message" | "rating" | "email">, signedIn: boolean): string {
  const m = a.message.trim();
  if (!signedIn && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test((a.email ?? "").trim())) return "Enter an email address so we can reply.";
  if (a.kind === "query" && m.length < QUERY_MIN) return `Please write at least ${QUERY_MIN} characters so we can help.`;
  if (a.kind === "feedback" && !m && !a.rating) return "Choose a rating or write a few words.";
  if (m && m.length < 3) return "Please write a few more words.";
  if (m.length > MESSAGE_MAX) return `Please keep it under ${MESSAGE_MAX} characters.`;
  return "";
}
export const sendPageFeedback = (a: SendArgs) => apiSend<{ status: string; id: number }>("POST", "/api/page-feedback", {
  kind: a.kind, page: a.tag.page, pageName: a.tag.pageName, context: a.tag.context, category: a.category, rating: a.kind === "feedback" ? a.rating ?? null : null,
  message: a.message.trim(), ...(a.email?.trim() ? { email: a.email.trim() } : {}),
});

/** Where the dialogs open from. A tiny shared store: the banner's button, the feedback pill and the dialog never need to know about each other. */
type Open = Kind | null;
let current: Open = null;
const subs = new Set<() => void>();
export const panel = { get: (): Open => current, set: (k: Open) => { current = k; subs.forEach((f) => f()); }, sub: (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; } };
/** How many page banners are on screen: when none is, the dock carries its own "Raise a Query" button so no page is without one. */
let banners = 0;
const bsubs = new Set<() => void>();
export const banner = { get: () => banners, add: () => { banners++; bsubs.forEach((f) => f()); return () => { banners--; bsubs.forEach((f) => f()); }; }, sub: (f: () => void) => { bsubs.add(f); return () => { bsubs.delete(f); }; } };
