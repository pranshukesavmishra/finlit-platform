import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { adminBlob, adminFetch, adminUpload, buildPayload, coverUrlProblem, draftFrom, draftProblems, emptyDraft, fileProblem, hasSession, KINDS, sizeText, type AdminItem, type Draft, type Kind } from "../lib/cms";
import { useAuth } from "../lib/auth";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { PostBody } from "../components/PostBody";
import { RichEditor } from "../components/RichEditor";
import "../styles/cms.css";

function useGuard() {
  const nav = useNavigate(); const { ready, user } = useAuth();
  useEffect(() => { if (ready && !hasSession()) nav(user ? "/admin/login" : "/login?next=/admin", { replace: true }); }, [ready, user, nav]);
}
const useItem = (id?: string) => useQuery({ queryKey: ["admin-item", id], queryFn: () => adminFetch<AdminItem>(`/api/content/admin/items/${id}`), enabled: !!id && hasSession(), retry: false });

/** A local address for a private file, so the editor and the preview can show a draft's image or file. */
function useBlobUrl(key: string | null | undefined) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!key || !hasSession()) { setUrl(null); return; }
    let live = true; let made: string | null = null;
    adminBlob(key).then((b) => { if (live) { made = URL.createObjectURL(b); setUrl(made); } }).catch(() => { if (live) setUrl(null); });
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [key]);
  return url;
}

export function AdminPost() {
  const { id } = useParams(); const nav = useNavigate(); const qc = useQueryClient(); const { toast } = useUI();
  useDocTitle(id ? "Edit post" : "New post"); useGuard();
  const item = useItem(id);
  const [d, setD] = useState<Draft>(emptyDraft());
  const [loaded, setLoaded] = useState(!id);
  const [errs, setErrs] = useState<string[]>([]); const [busy, setBusy] = useState<string | null>(null); const [upErr, setUpErr] = useState<{ file?: string; cover?: string }>({});
  const [fileLabel, setFileLabel] = useState(""); const coverRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (item.data && !loaded) { setD(draftFrom(item.data)); setFileLabel(item.data.originalFileName ? `${item.data.originalFileName} ${sizeText(item.data.fileSize)}` : ""); setLoaded(true); } }, [item.data, loaded]);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const coverBlob = useBlobUrl(d.coverKey);

  const upload = async (file: File | undefined, as: Kind | "COVER") => {
    if (!file) return; const slot = as === "COVER" ? "cover" : "file";
    const bad = fileProblem(file, as); if (bad) { setUpErr((e) => ({ ...e, [slot]: bad })); return; }
    setUpErr((e) => ({ ...e, [slot]: undefined })); setBusy(slot);
    try { const r = await adminUpload(file); if (as === "COVER") setD((p) => ({ ...p, coverKey: r.key, coverUrl: "" })); else { set("fileKey", r.key); setFileLabel(`${r.originalFileName} ${sizeText(r.fileSize)}`); } }
    catch (e) { setUpErr((x) => ({ ...x, [slot]: (e as Error).message })); }
    finally { setBusy(null); }
  };
  const save = useMutation({
    mutationFn: (status: Draft["status"]) => {
      const next = { ...d, status }; const p = draftProblems(next); if (p.length) { setErrs(p); throw new Error(p[0]); }
      setErrs([]);
      return id ? adminFetch<AdminItem>(`/api/content/admin/items/${id}`, { method: "PUT", body: JSON.stringify(buildPayload(next, item.data?.slug)) })
        : adminFetch<AdminItem>("/api/content/admin/items", { method: "POST", body: JSON.stringify(buildPayload(next)) });
    },
    onSuccess: (r, status) => { qc.invalidateQueries({ queryKey: ["admin-content"] }); qc.invalidateQueries({ queryKey: ["admin-item"] }); qc.invalidateQueries({ queryKey: ["content"] }); toast(status === "PUBLISHED" ? "Saved and published." : "Draft saved."); if (!id) nav(`/admin/posts/${r.id}`, { replace: true }); else set("status", status); },
    onError: (e: Error) => { if ((e as ApiError).status === 401) nav("/admin/login"); else toast(e.message); },
  });

  if (id && item.isError) return <section className="sec"><div className="wrap"><div className="state"><h2>We could not open that post</h2><p><Link to="/admin">Back to the content tools</Link></p></div></div></section>;
  if (!loaded) return <section className="sec"><div className="wrap"><div className="skeleton" style={{ height: 320 }} /></div></section>;
  const kindMeta = KINDS.find((k) => k.kind === d.kind)!;
  const coverShown = d.coverKey ? coverBlob : /^https:\/\//.test(d.coverUrl) ? d.coverUrl : null;
  const coverErr = coverUrlProblem(d.coverUrl);
  return (
    <section className="sec"><div className="wrap cms">
      <div className="cms-top"><div><div className="eyebrow">Content tools</div><h1>{id ? "Edit post" : "New post"}</h1></div>
        <div className="cms-acts"><Link className="btn" to="/admin">All posts</Link>{id && <Link className="btn" to={`/admin/posts/${id}/preview`}>Preview</Link>}</div></div>
      {errs.length > 0 && <div className="formerr" role="alert"><ul>{errs.map((e) => <li key={e}>{e}</li>)}</ul></div>}
      <div className="cms-grid">
        <form className="card form cms-main" onSubmit={(e) => { e.preventDefault(); save.mutate(d.status); }}>
          <div className="seg" role="group" aria-label="Kind of post">{KINDS.map((k) => <button type="button" key={k.kind} aria-pressed={d.kind === k.kind} disabled={!!id && k.kind !== d.kind && (k.kind === "ARTICLE" || d.kind === "ARTICLE")} onClick={() => set("kind", k.kind)}>{k.label}</button>)}</div>
          <label>Title<input value={d.title} onChange={(e) => set("title", e.target.value)} maxLength={180} required /></label>
          <label>Summary <span className="faint">(shown on the blog list, up to 500 characters)</span><textarea rows={3} value={d.excerpt} onChange={(e) => set("excerpt", e.target.value)} maxLength={500} /></label>
          {d.kind === "ARTICLE" ? <div className="fld"><span className="lbl">Body</span><RichEditor initial={d.html} resetKey={String(id) + loaded} label="Article body" onChange={(h) => set("html", h)} /></div> : (
            <div className="fld cms-file"><label htmlFor="cms-file">{kindMeta.label} file <span className="faint">({kindMeta.exts.join(", ")}, up to 15 MB)</span></label>
              <input id="cms-file" type="file" accept={kindMeta.accept} onChange={(e) => { upload(e.target.files?.[0], d.kind); e.target.value = ""; }} disabled={busy === "file"} />
              {busy === "file" && <p className="muted">Uploading…</p>}{fileLabel && d.fileKey && <p className="cms-ok">Attached: {fileLabel}</p>}
              {upErr.file && <div className="formerr" role="alert">{upErr.file}</div>}</div>)}
        </form>
        <aside className="card form cms-side">
          <div className="card-h"><h3>Publish</h3><span className={"chip " + (d.status === "PUBLISHED" ? "up" : "ghost")}>{d.status === "PUBLISHED" ? "Published" : "Draft"}</span></div>
          <div className="cms-acts">
            <button className="btn" type="button" disabled={save.isPending} onClick={() => save.mutate("DRAFT")}>{d.status === "PUBLISHED" ? "Unpublish and save" : "Save draft"}</button>
            <button className="btn primary" type="button" disabled={save.isPending} onClick={() => save.mutate("PUBLISHED")}>{d.status === "PUBLISHED" ? "Save changes" : "Publish"}</button></div>
          <label>Category<input value={d.category} onChange={(e) => set("category", e.target.value)} maxLength={60} placeholder="Basics" /></label>
          <label>Tags <span className="faint">(comma separated, up to 12)</span><input value={d.tags} onChange={(e) => set("tags", e.target.value)} placeholder="tax, sip" /></label>
          <label>Author<input value={d.author} onChange={(e) => set("author", e.target.value)} maxLength={120} /></label>
          <fieldset className="cms-cover"><legend>Cover image</legend>
            {coverShown ? <img src={coverShown} alt="Cover preview" className="cms-thumb" /> : <div className="cms-thumb empty">No cover</div>}
            <label>Link <span className="faint">(https only)</span><input value={d.coverUrl} onChange={(e) => setD((p) => ({ ...p, coverUrl: e.target.value, coverKey: null }))} placeholder="https://" inputMode="url" aria-invalid={!!coverErr} /></label>
            {coverErr && <div className="formerr" role="alert">{coverErr}</div>}
            <div className="cms-acts"><input ref={coverRef} type="file" accept=".png,.jpg,.jpeg,.webp" hidden aria-label="Upload cover image" onChange={(e) => { upload(e.target.files?.[0], "COVER"); e.target.value = ""; }} />
              <button type="button" className="btn" disabled={busy === "cover"} onClick={() => coverRef.current?.click()}>{busy === "cover" ? "Uploading…" : "Upload image"}</button>
              {(d.coverKey || d.coverUrl) && <button type="button" className="btn" onClick={() => setD((p) => ({ ...p, coverKey: null, coverUrl: "" }))}>Remove</button>}</div>
            {upErr.cover && <div className="formerr" role="alert">{upErr.cover}</div>}</fieldset>
        </aside>
      </div>
    </div></section>
  );
}

export function AdminPreview() {
  const { id } = useParams(); useGuard(); useDocTitle("Preview");
  const item = useItem(id); const c = item.data;
  const fileBlob = useBlobUrl(c && c.contentType !== "ARTICLE" ? c.fileKey : null);
  const coverBlob = useBlobUrl(c?.coverImageKey);
  if (item.isError) return <section className="sec"><div className="wrap"><div className="state"><h2>We could not open that post</h2><p><Link to="/admin">Back to the content tools</Link></p></div></div></section>;
  if (!c) return <section className="sec"><div className="wrap"><div className="skeleton" style={{ height: 320 }} /></div></section>;
  const cover = c.coverImageKey ? coverBlob : c.coverImageUrl && /^https:\/\//.test(c.coverImageUrl) ? c.coverImageUrl : null;
  return (
    <>
      <div className="cms-banner" role="status"><span><b>{c.status === "PUBLISHED" ? "Published" : "Draft preview"}</b>. {c.status === "PUBLISHED" ? "This is how visitors see it." : "Only administrators can see this page."}</span>
        <span className="cms-acts"><Link className="btn" to={`/admin/posts/${c.id}`}>Back to editing</Link>{c.status === "PUBLISHED" && <Link className="btn" to={`/blog/${c.slug}`}>Open public page</Link>}</span></div>
      <section className="pagehead"><div className="wrap" style={{ maxWidth: 760 }}><span className="chip gold">{c.category || "Blog"}</span><h1 style={{ maxWidth: "none", fontSize: "clamp(30px,4.4vw,52px)" }}>{c.title}</h1><p>{c.excerpt}</p>
        <p className="faint" style={{ marginTop: 12, fontSize: 13 }}>{c.author}{(c.tags || []).length ? " · " + c.tags!.join(", ") : ""}</p>{cover && <img src={cover} alt="" className="cms-cover-big" />}</div></section>
      <section className="sec" style={{ paddingTop: 0 }}><div className="wrap"><PostBody c={c} file={fileBlob} /></div></section>
    </>
  );
}
