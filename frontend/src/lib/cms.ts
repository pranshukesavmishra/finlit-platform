// Content-admin helpers: the CMS session, authenticated requests, uploads, and the pure rules the editor uses.
import { ApiError, apiUrl, apiSend } from "./api";
import type { ContentItem } from "./siteApi";

export type Kind = ContentItem["contentType"];
export type AdminItem = ContentItem & { articleFormat?: "MARKDOWN" | "HTML"; category?: string; tags?: string[]; inlineImageKeys?: string[] };

export const KEY = "cms_admin_token";
export const REJECTED = "cms_token_rejected";   // when the content service refused a token a moment ago: do not ask for another one in a loop
export const token = () => { try { return sessionStorage.getItem(KEY); } catch { return null; } };
export const hasSession = () => {
  const t = token(); if (!t) return false;
  try { const p = JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); return p.role === "admin" && p.exp * 1000 > Date.now(); } catch { return false; }
};

function expire(): never {
  try { sessionStorage.removeItem(KEY); sessionStorage.setItem(REJECTED, String(Date.now())); } catch { /* ignore */ }
  throw new ApiError(401, { detail: "Your session expired. Please sign in again." });
}
async function parse<T>(res: Response): Promise<T> {
  if (res.status === 401) expire();
  const text = await res.text(); let data: any = {}; try { data = text ? JSON.parse(text) : {}; } catch { /* ignore */ }
  if (!res.ok) throw new ApiError(res.status, { detail: typeof data.detail === "string" ? data.detail : "Request failed." });
  return data as T;
}
export async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(apiUrl(path), { ...init, headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${token()}`, ...(init.headers || {}) } });
  return parse<T>(res);
}
export type Uploaded = { key: string; originalFileName: string; mimeType: string; fileSize: number; fileUrl: string };
export async function adminUpload(file: File): Promise<Uploaded> {
  const body = new FormData(); body.append("file", file);
  const res = await fetch(apiUrl("/api/content/admin/upload"), { method: "POST", headers: { Accept: "application/json", Authorization: `Bearer ${token()}` }, body });
  return parse<Uploaded>(res);
}
/** Drafts are not public, so their files are fetched with the admin token and shown from a local object URL. */
export async function adminBlob(key: string): Promise<Blob> {
  const res = await fetch(apiUrl(`/api/content/admin/assets/${encodeURIComponent(key)}`), { headers: { Authorization: `Bearer ${token()}` } });
  if (res.status === 401) expire();
  if (!res.ok) throw new ApiError(res.status, { detail: "Could not load the file." });
  return res.blob();
}

/** Administrators sign in once, on the normal sign-in page. This exchanges that session for the CMS token. */
export async function openCms(): Promise<{ ok: true } | { ok: false; why: "mfa" | "not_configured" | "other" }> {
  try { const r = await apiSend<{ token: string }>("POST", "/api/me/cms-token"); sessionStorage.setItem(KEY, r.token); return { ok: true }; }
  catch (e) {
    const status = e instanceof ApiError ? String((e.body as { status?: string; detail?: { status?: string } })?.status ?? (e.body as { detail?: { status?: string } })?.detail?.status ?? "") : "";
    return { ok: false, why: status === "mfa_required" || status === "mfa_setup_required" ? "mfa" : status === "cms_not_configured" ? "not_configured" : "other" };
  }
}

// ---- rules (they mirror the content service so a mistake is caught before the upload, not after) ----
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
export const KINDS: { kind: Kind; label: string; accept: string; exts: string[] }[] = [
  { kind: "ARTICLE", label: "Article", accept: "", exts: [] },
  { kind: "PDF", label: "PDF report", accept: ".pdf,application/pdf", exts: [".pdf"] },
  { kind: "SPREADSHEET", label: "Spreadsheet", accept: ".xlsx,.xls,.csv", exts: [".xlsx", ".xls", ".csv"] },
  { kind: "IMAGE", label: "Image", accept: ".png,.jpg,.jpeg,.webp", exts: [".png", ".jpg", ".jpeg", ".webp"] },
];
export const COVER_EXTS = [".png", ".jpg", ".jpeg", ".webp"];
const ext = (name: string) => { const i = name.lastIndexOf("."); return i < 0 ? "" : name.slice(i).toLowerCase(); };
const mb = (n: number) => `${Math.round(n / 1024 / 1024)} MB`;

/** Why a file cannot be used for this kind (or cover), or null when it can. */
export function fileProblem(file: { name: string; size: number }, kind: Kind | "COVER"): string | null {
  const allowed = kind === "COVER" ? COVER_EXTS : (KINDS.find((k) => k.kind === kind)?.exts ?? []);
  if (!allowed.includes(ext(file.name))) return `Use a ${allowed.join(", ")} file.`;
  if (file.size > MAX_UPLOAD_BYTES) return `The file is larger than ${mb(MAX_UPLOAD_BYTES)}.`;
  if (file.size === 0) return "The file is empty.";
  return null;
}
/** Cover images from another site must be https. Returns an error sentence or null (blank is fine). */
export function coverUrlProblem(url: string): string | null {
  const v = url.trim(); if (!v) return null;
  if (v.length > 1000) return "That link is too long.";
  try { const u = new URL(v); return u.protocol === "https:" && u.hostname ? null : "The cover image link must start with https://"; } catch { return "That is not a valid link."; }
}
export function parseTags(raw: string): string[] {
  const seen = new Set<string>(); const out: string[] = [];
  for (const t of raw.split(",")) { const v = t.replace(/\s+/g, " ").trim().slice(0, 30); if (v && !seen.has(v.toLowerCase())) { seen.add(v.toLowerCase()); out.push(v); } }
  return out.slice(0, 12);
}
export const tagsText = (t?: string[]) => (t || []).join(", ");

export type Filters = { q: string; status: "ALL" | "DRAFT" | "PUBLISHED"; kind: "ALL" | Kind };
export function filterItems<T extends Pick<AdminItem, "title" | "excerpt" | "author" | "status" | "contentType" | "category" | "tags">>(items: T[], f: Filters): T[] {
  const q = f.q.trim().toLowerCase();
  return items.filter((c) => (f.status === "ALL" || c.status === f.status) && (f.kind === "ALL" || c.contentType === f.kind)
    && (!q || [c.title, c.excerpt, c.author, c.category, ...(c.tags || [])].join(" ").toLowerCase().includes(q)));
}

export type Draft = { title: string; excerpt: string; kind: Kind; html: string; category: string; tags: string; status: "DRAFT" | "PUBLISHED"; author: string; coverUrl: string; coverKey: string | null; fileKey: string | null };
export const emptyDraft = (): Draft => ({ title: "", excerpt: "", kind: "ARTICLE", html: "", category: "", tags: "", status: "DRAFT", author: "Nishant Jain", coverUrl: "", coverKey: null, fileKey: null });
export function draftFrom(c: AdminItem): Draft {
  return { title: c.title, excerpt: c.excerpt || "", kind: c.contentType, html: c.articleFormat === "HTML" ? c.articleBody || "" : c.articleHtml || "", category: c.category || "", tags: tagsText(c.tags),
    status: c.status, author: c.author, coverUrl: c.coverImageKey ? "" : c.coverImageUrl || "", coverKey: c.coverImageKey || null, fileKey: c.fileKey || null };
}
/** Everything that stops a save, in the order the form shows it. Empty list = ready. */
export function draftProblems(d: Draft): string[] {
  const out: string[] = []; const text = d.html.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim();
  if (d.title.trim().length < 3) out.push("Add a title of at least 3 characters.");
  if (d.kind === "ARTICLE" && !text && !/<img/i.test(d.html)) out.push("Write the article body.");
  if (d.kind !== "ARTICLE" && !d.fileKey) out.push("Upload the file for this post.");
  const c = coverUrlProblem(d.coverUrl); if (c) out.push(c);
  return out;
}
export function buildPayload(d: Draft, slug?: string) {
  return {
    title: d.title.trim(), slug: slug || undefined, excerpt: d.excerpt.trim(), contentType: d.kind,
    articleBody: d.kind === "ARTICLE" ? d.html : "", articleFormat: "HTML", author: d.author.trim() || "Nishant Jain", status: d.status,
    category: d.category.trim(), tags: parseTags(d.tags),
    coverImageKey: d.coverKey || undefined, coverImageUrl: d.coverKey ? undefined : d.coverUrl.trim() || undefined,
    fileKey: d.kind === "ARTICLE" ? undefined : d.fileKey || undefined,
  };
}

/** A PDF may go in an iframe only when the file is served from the page's own origin (the content service sends X-Frame-Options: SAMEORIGIN).
 *  Otherwise the browser would show a blank box, so the page offers "Open" and "Download" instead. */
export function canEmbedPdf(fileUrl: string, pageOrigin: string): boolean {
  try { return new URL(fileUrl, pageOrigin).origin === pageOrigin; } catch { return false; }
}
export const sizeText = (n?: number | null) => (!n ? "" : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
