import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ContentItem } from "../lib/siteApi";
import { useAuth } from "../lib/auth";
import { apiSend } from "../lib/api";
import { ApiError, apiUrl } from "../lib/api";
import { dateIN } from "../lib/format";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";

// Admin session: same model as the current site (bearer token in sessionStorage, 8 h, signature checked by the server).
// The platform plan replaces this with real accounts, passkeys and server-side sessions.
const KEY = "cms_admin_token";
const REJECTED = "cms_token_rejected";   // when the content service refused a token a moment ago: do not ask for another one in a loop
const token = () => { try { return sessionStorage.getItem(KEY); } catch { return null; } };
const hasSession = () => { const t = token(); if (!t) return false; try { const p = JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); return p.role === "admin" && p.exp * 1000 > Date.now(); } catch { return false; } };

async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(apiUrl(path), { ...init, headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${token()}`, ...(init.headers || {}) } });
  if (res.status === 401) { try { sessionStorage.removeItem(KEY); sessionStorage.setItem(REJECTED, String(Date.now())); } catch { /* ignore */ } throw new ApiError(401, { detail: "Your session expired. Please sign in again." }); }
  const text = await res.text(); let data: any = {}; try { data = text ? JSON.parse(text) : {}; } catch { /* ignore */ }
  if (!res.ok) throw new ApiError(res.status, { detail: typeof data.detail === "string" ? data.detail : "Request failed." });
  return data as T;
}

/** Administrators sign in once, on the normal sign-in page. This exchanges that session for the CMS token, then opens the tools. */
async function openCms(): Promise<{ ok: true } | { ok: false; why: "mfa" | "not_configured" | "other" }> {
  try { const r = await apiSend<{ token: string }>("POST", "/api/me/cms-token"); sessionStorage.setItem(KEY, r.token); return { ok: true }; }
  catch (e) {
    const status = e instanceof ApiError ? String((e.body as { status?: string; detail?: { status?: string } })?.status ?? (e.body as { detail?: { status?: string } })?.detail?.status ?? "") : "";
    return { ok: false, why: status === "mfa_required" || status === "mfa_setup_required" ? "mfa" : status === "cms_not_configured" ? "not_configured" : "other" };
  }
}

export function AdminLogin() {
  useDocTitle("Admin");
  const nav = useNavigate(); const { user, ready, isAdmin } = useAuth(); const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    if (!user) { nav("/login?next=/admin", { replace: true }); return; }
    if (!isAdmin) { setErr("This area is for FinLit administrators."); return; }
    let recent = 0; try { recent = Number(sessionStorage.getItem(REJECTED) || 0); } catch { /* ignore */ }
    if (Date.now() - recent < 60_000) { setErr("The content service did not accept your sign-in. This happens when CMS_JWT_SECRET is not the same on both parts of the site. See the launch guide, then reload."); return; }
    openCms().then((r) => {
      if (r.ok) nav("/admin", { replace: true });
      else if (r.why === "mfa") nav("/account/security?setup=1", { replace: true });
      else setErr(r.why === "not_configured" ? "The content tools are not connected yet: CMS_JWT_SECRET is missing on the server (see the launch guide)." : "Could not open the content tools. Reload the page; if it keeps happening, sign out and in again.");
    });
  }, [ready, user, isAdmin, nav]);
  return <section className="sec"><div className="wrap" style={{ maxWidth: 460 }}>{err ? <div className="card"><div className="formerr" role="alert">{err}</div></div> : <p className="muted">Opening the content tools…</p>}</div></section>;
}

export function Admin() {
  useDocTitle("Admin");
  const nav = useNavigate(); const qc = useQueryClient(); const { toast } = useUI();
  const [form, setForm] = useState({ title: "", excerpt: "", body: "" });
  const { ready, user } = useAuth();
  useEffect(() => { if (ready && !hasSession()) nav(user ? "/admin/login" : "/login?next=/admin", { replace: true }); }, [ready, user, nav]);
  const list = useQuery({ queryKey: ["admin-content"], queryFn: () => adminFetch<ContentItem[]>("/api/content/admin/items"), enabled: hasSession(), retry: false });
  const leads = useQuery({ queryKey: ["admin-leads"], queryFn: () => adminFetch<{ id: string; name: string; email: string; phone?: string; subject?: string; message: string; created_at: string }[]>("/api/contact"), enabled: hasSession(), retry: false });
  useEffect(() => { if ((list.error as ApiError)?.status === 401) nav("/admin/login"); }, [list.error, nav]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-content"] });
  const toggle = useMutation({
    mutationFn: (c: ContentItem) => adminFetch(`/api/content/admin/items/${c.id}`, { method: "PUT", body: JSON.stringify({ title: c.title, slug: c.slug, excerpt: c.excerpt, contentType: c.contentType, articleBody: c.articleBody || "", articleFormat: (c as any).articleFormat || "HTML", author: c.author, status: c.status === "PUBLISHED" ? "DRAFT" : "PUBLISHED", fileKey: c.fileKey || undefined, coverImageKey: c.coverImageKey || undefined, coverImageUrl: c.coverImageUrl || undefined }) }),
    onSuccess: () => { refresh(); toast("Updated."); }, onError: (e: Error) => toast(e.message),
  });
  const del = useMutation({ mutationFn: (id: string) => adminFetch(`/api/content/admin/items/${id}`, { method: "DELETE" }), onSuccess: () => { refresh(); toast("Deleted."); }, onError: (e: Error) => toast(e.message) });
  const create = useMutation({
    mutationFn: () => adminFetch("/api/content/admin/items", { method: "POST", body: JSON.stringify({ title: form.title, excerpt: form.excerpt, contentType: "ARTICLE", articleFormat: "HTML", articleBody: form.body.split(/\n{2,}/).map((p) => `<p>${p.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string))}</p>`).join(""), status: "DRAFT" }) }),
    onSuccess: () => { setForm({ title: "", excerpt: "", body: "" }); refresh(); toast("Draft created."); }, onError: (e: Error) => toast(e.message),
  });
  return (
    <section className="sec"><div className="wrap">
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 20 }}><h1 style={{ font: "300 40px var(--serif)", margin: 0 }}>Research publishing</h1>
        <div style={{ display: "flex", gap: 8 }}><Link className="btn" to="/blog">View blog</Link><button className="btn" onClick={() => { try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } nav("/console"); }}>Back to console</button></div></div>
      <div className="grid g2">
        <div className="card"><div className="card-h"><h3>Content</h3><span className="s">{list.data?.length ?? 0} items</span></div>
          <div className="tw"><table className="admin-t"><thead><tr><th>Title</th><th>Status</th><th>Updated</th><th /></tr></thead>
            <tbody>{(list.data || []).map((c) => <tr key={c.id}><td><b>{c.title}</b><div className="faint" style={{ fontSize: 12 }}>{c.contentType}</div></td><td><span className={"chip " + (c.status === "PUBLISHED" ? "up" : "ghost")}>{c.status === "PUBLISHED" ? "Published" : "Draft"}</span></td><td>{c.updatedAt ? dateIN(c.updatedAt) : ""}</td>
              <td style={{ whiteSpace: "nowrap" }}><button className="btn" style={{ height: 34 }} onClick={() => toggle.mutate(c)}>{c.status === "PUBLISHED" ? "Unpublish" : "Publish"}</button> <button className="btn" style={{ height: 34, color: "var(--loss)" }} onClick={() => { if (confirm(`Delete “${c.title}”? This cannot be undone.`)) del.mutate(c.id); }}>Delete</button></td></tr>)}</tbody></table></div></div>
        <div className="card"><form className="form" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}><div className="card-h"><h3>New article</h3></div>
          <label>Title<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} /></label>
          <label>Excerpt<input value={form.excerpt} onChange={(e) => setForm({ ...form, excerpt: e.target.value })} maxLength={500} /></label>
          <label>Body (blank line = new paragraph)<textarea rows={8} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} required /></label>
          <button className="btn primary" disabled={create.isPending}>Save draft</button></form></div>
      </div>
      <div className="card" style={{ marginTop: 16 }}><div className="card-h"><h3>Contact messages</h3><span className="s">{leads.data?.length ?? 0}</span></div>
        <div className="tw"><table className="admin-t"><thead><tr><th>When</th><th>Name</th><th>Email</th><th>Subject</th><th>Message</th></tr></thead>
          <tbody>{(leads.data || []).slice(0, 50).map((l) => <tr key={l.id}><td>{dateIN(l.created_at)}</td><td>{l.name}</td><td>{l.email}</td><td>{l.subject}</td><td style={{ whiteSpace: "normal", maxWidth: 360 }}>{l.message}</td></tr>)}</tbody></table></div></div>
    </div></section>
  );
}
