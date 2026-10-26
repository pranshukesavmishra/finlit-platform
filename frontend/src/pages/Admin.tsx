import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ContentItem } from "../lib/siteApi";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { adminFetch, buildPayload, draftFrom, filterItems, type AdminItem, hasSession, KEY, KINDS, openCms, REJECTED, type Filters } from "../lib/cms";
import { dateIN } from "../lib/format";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import "../styles/cms.css";

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
  const [f, setF] = useState<Filters>({ q: "", status: "ALL", kind: "ALL" });
  const { ready, user } = useAuth();
  useEffect(() => { if (ready && !hasSession()) nav(user ? "/admin/login" : "/login?next=/admin", { replace: true }); }, [ready, user, nav]);
  const list = useQuery({ queryKey: ["admin-content"], queryFn: () => adminFetch<ContentItem[]>("/api/content/admin/items"), enabled: hasSession(), retry: false });
  const enquiries = useQuery({ queryKey: ["admin-enquiries"], queryFn: () => adminFetch<{ id: string; name: string; email: string; phone: string; services: string[]; message: string; created_at: string }[]>("/api/service-enquiry"), enabled: hasSession(), retry: false });
  const leads = useQuery({ queryKey: ["admin-leads"], queryFn: () => adminFetch<{ id: string; name: string; email: string; phone?: string; investment_size?: string; subject?: string; message: string; created_at: string }[]>("/api/contact"), enabled: hasSession(), retry: false });
  useEffect(() => { if ((list.error as ApiError)?.status === 401) nav("/admin/login"); }, [list.error, nav]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-content"] });
  const toggle = useMutation({
    mutationFn: (c: ContentItem) => adminFetch(`/api/content/admin/items/${c.id}`, { method: "PUT", body: JSON.stringify(buildPayload({ ...draftFrom(c as AdminItem), status: c.status === "PUBLISHED" ? "DRAFT" : "PUBLISHED" }, c.slug)) }),
    onSuccess: () => { refresh(); toast("Updated."); }, onError: (e: Error) => toast(e.message),
  });
  const del = useMutation({ mutationFn: (id: string) => adminFetch(`/api/content/admin/items/${id}`, { method: "DELETE" }), onSuccess: () => { refresh(); toast("Deleted."); }, onError: (e: Error) => toast(e.message) });
  const shown = useMemo(() => filterItems(list.data || [], f), [list.data, f]);
  return (
    <section className="sec"><div className="wrap">
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 20 }}><h1 style={{ font: "300 40px var(--serif)", margin: 0 }}>Research publishing</h1>
        <div style={{ display: "flex", gap: 8 }}><Link className="btn" to="/blog">View blog</Link><button className="btn" onClick={() => { try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } nav("/console"); }}>Back to console</button></div></div>
      <div className="card cms-list"><div className="card-h"><h3>Posts</h3><span className="s">{shown.length === (list.data?.length ?? 0) ? `${shown.length} items` : `${shown.length} of ${list.data?.length ?? 0}`}</span><Link className="btn primary" to="/admin/posts/new">New post</Link></div>
        <div className="filters cms-filters">
          <input className="sbox" type="search" placeholder="Search title, summary, tags" aria-label="Search posts" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
          <label className="cms-sel">Status<select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as Filters["status"] })}><option value="ALL">All</option><option value="DRAFT">Drafts</option><option value="PUBLISHED">Published</option></select></label>
          <label className="cms-sel">Kind<select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as Filters["kind"] })}><option value="ALL">All</option>{KINDS.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}</select></label>
          {(f.q || f.status !== "ALL" || f.kind !== "ALL") && <button className="btn" onClick={() => setF({ q: "", status: "ALL", kind: "ALL" })}>Clear</button>}</div>
        {list.isLoading && <div className="skeleton" style={{ height: 120 }} />}
        {list.isError && <div className="formerr" role="alert">Could not load the posts.</div>}
        {!list.isLoading && !list.isError && !shown.length && <p className="muted" style={{ padding: "8px 16px" }}>{list.data?.length ? "No posts match these filters." : "No posts yet. Start with New post."}</p>}
        {shown.length > 0 && <div className="tw"><table className="admin-t"><thead><tr><th>Title</th><th>Status</th><th>Updated</th><th /></tr></thead>
          <tbody>{shown.map((c) => <tr key={c.id}><td><Link to={`/admin/posts/${c.id}`}><b>{c.title}</b></Link><div className="faint" style={{ fontSize: 12 }}>{KINDS.find((k) => k.kind === c.contentType)?.label || c.contentType}{(c as AdminItem).category ? ` · ${(c as AdminItem).category}` : ""}</div></td>
            <td><span className={"chip " + (c.status === "PUBLISHED" ? "up" : "ghost")}>{c.status === "PUBLISHED" ? "Published" : "Draft"}</span></td><td>{c.updatedAt ? dateIN(c.updatedAt) : ""}</td>
            <td className="cms-rowacts"><Link className="btn" to={`/admin/posts/${c.id}`} aria-label={`Edit ${c.title}`}>Edit</Link> <Link className="btn" to={`/admin/posts/${c.id}/preview`} aria-label={`Preview ${c.title}`}>Preview</Link> <button className="btn" onClick={() => toggle.mutate(c)} aria-label={`${c.status === "PUBLISHED" ? "Unpublish" : "Publish"} ${c.title}`}>{c.status === "PUBLISHED" ? "Unpublish" : "Publish"}</button> <button className="btn danger" aria-label={`Delete ${c.title}`} onClick={() => { if (confirm(`Delete “${c.title}”? This cannot be undone.`)) del.mutate(c.id); }}>Delete</button></td></tr>)}</tbody></table></div>}
      </div>
      <div className="card" style={{ marginTop: 16 }}><div className="card-h"><h3>Contact messages</h3><span className="s">{leads.data?.length ?? 0}</span></div>
        <div className="tw"><table className="admin-t"><thead><tr><th>When</th><th>Name</th><th>Email</th><th>Investment size</th><th>Subject</th><th>Message</th></tr></thead>
          <tbody>{(leads.data || []).slice(0, 50).map((l) => <tr key={l.id}><td>{dateIN(l.created_at)}</td><td>{l.name}</td><td>{l.email}</td><td>{l.investment_size}</td><td>{l.subject}</td><td style={{ whiteSpace: "normal", maxWidth: 360 }}>{l.message}</td></tr>)}</tbody></table></div></div>
      <div className="card" style={{ marginTop: 16 }}><div className="card-h"><h3>Service enquiries</h3><span className="s">{enquiries.data?.length ?? 0}</span></div>
        <div className="tw"><table className="admin-t"><thead><tr><th>When</th><th>Name</th><th>Email</th><th>Phone</th><th>Services</th><th>Message</th></tr></thead>
          <tbody>{(enquiries.data || []).slice(0, 50).map((l) => <tr key={l.id}><td>{dateIN(l.created_at)}</td><td>{l.name}</td><td>{l.email}</td><td>{l.phone}</td><td style={{ whiteSpace: "normal" }}>{l.services.join(", ")}</td><td style={{ whiteSpace: "normal", maxWidth: 320 }}>{l.message}</td></tr>)}
            {enquiries.data?.length === 0 && <tr><td colSpan={6} className="muted">No enquiries yet.</td></tr>}</tbody></table></div></div>
    </div></section>
  );
}
