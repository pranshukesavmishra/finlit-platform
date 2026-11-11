// The team's inbox for "Raise a Query" and "Share Feedback" (finlit/page_feedback.py): every message with the page it was written on.
// Administrators only, signed in with the authenticator code; the server checks both on every call.
import { useState } from "react";
import { Navigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDocTitle } from "../lib/title";
import { ago } from "../lib/forum";
import "../styles/pagefeedback.css";

type Item = { id: number; kind: "query" | "feedback"; page: string; pageName: string; context: Record<string, string>; category: string; rating: number | null; message: string;
  email: string | null; member: boolean; plan: string | null; status: "new" | "read" | "resolved"; note: string | null; createdAt: string; handledAt: string | null };
type Inbox = { items: Item[]; total: number; page: number; pages: number; counts: { new: number; openQueries: number } };
type Summary = { pages: { page: string; name: string; total: number; queries: number; feedback: number; new: number; avgRating: number | null; rated: number }[] };
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");
const CATEGORY: Record<string, string> = { question: "Question", issue: "Issue", clarification: "Clarification", suggestion: "Suggestion", ui_ux: "Look and feel", praise: "What works well", other: "Other" };

export function FeedbackInbox() {
  useDocTitle("Queries and feedback");
  const { user, ready, isAdmin } = useAuth(), qc = useQueryClient();
  const [kind, setKind] = useState(""), [status, setStatus] = useState(""), [page, setPage] = useState(""), [pg, setPg] = useState(1);
  const on = isAdmin && !!user?.mfaOk;
  const list = useQuery<Inbox>({ queryKey: ["pf", "inbox", kind, status, page, pg], enabled: on, retry: false,
    queryFn: () => apiGet(`/api/admin/page-feedback?pg=${pg}${kind ? `&kind=${kind}` : ""}${status ? `&status=${status}` : ""}${page ? `&page=${encodeURIComponent(page)}` : ""}`) });
  const sum = useQuery<Summary>({ queryKey: ["pf", "summary"], enabled: on, retry: false, queryFn: () => apiGet("/api/admin/page-feedback/summary") });
  const act = useMutation({ mutationFn: (a: { id: number; status?: string; note?: string }) => apiSend("PATCH", `/api/admin/page-feedback/${a.id}`, { status: a.status, note: a.note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pf"] }) });
  if (!ready) return null;
  if (!user) return <Navigate to="/login?next=%2Fadmin%2Ffeedback" replace />;
  if (!on) return <section className="sec"><div className="wrap"><h1>Queries and feedback</h1><p className="muted">Administrators only, signed in with the authenticator code.</p></div></section>;
  const seg = (v: string, set: (s: string) => void, opts: [string, string][], label: string) => (
    <div className="seg" role="group" aria-label={label}>{opts.map(([k, l]) => <button key={k} type="button" aria-pressed={v === k} onClick={() => { set(k); setPg(1); }}>{l}</button>)}</div>);
  return (
    <section className="sec"><div className="wrap pfi">
      <div className="eyebrow">Admin</div><h1>Queries and feedback</h1>
      <p className="muted">{list.data ? `${list.data.counts.new} new · ${list.data.counts.openQueries} queries still open` : "Loading…"}. Each message is tagged with the page it was written on.</p>
      <div className="pfi-bar">
        {seg(kind, setKind, [["", "All"], ["query", "Queries"], ["feedback", "Feedback"]], "Kind")}
        {seg(status, setStatus, [["", "Any status"], ["new", "New"], ["read", "Read"], ["resolved", "Resolved"]], "Status")}
        {page && <button type="button" className="btn sm" onClick={() => { setPage(""); setPg(1); }}>Page: {page} ×</button>}
      </div>
      {sum.data && sum.data.pages.length > 0 && (
        <details className="pfi-sum"><summary>Pages people write about most</summary>
          <table><thead><tr><th scope="col">Page</th><th scope="col" className="num">Queries</th><th scope="col" className="num">Feedback</th><th scope="col" className="num">New</th><th scope="col" className="num">Average rating</th></tr></thead>
            <tbody>{sum.data.pages.map((p) => <tr key={p.page}><th scope="row"><button type="button" className="pfi-link" onClick={() => { setPage(p.page); setPg(1); }}>{p.name}</button><small className="faint"> {p.page}</small></th>
              <td className="num">{p.queries}</td><td className="num">{p.feedback}</td><td className="num">{p.new}</td><td className="num">{p.avgRating == null ? "—" : `${p.avgRating.toFixed(1)} (${p.rated})`}</td></tr>)}</tbody></table>
        </details>)}
      {list.isError && <div className="pf-err" role="alert">{msg(list.error)}</div>}
      {list.data && !list.data.items.length && <p className="muted">Nothing here yet.</p>}
      {list.data?.items.map((i) => (
        <article className={"pfi-item " + i.status} key={i.id}>
          <div className="pfi-meta"><b>{i.kind === "query" ? "Query" : "Feedback"}</b><span>{CATEGORY[i.category] ?? i.category}</span>{i.rating ? <span aria-label={`Rating ${i.rating} of 5`}>{"★".repeat(i.rating)}{"☆".repeat(5 - i.rating)}</span> : null}
            <span className={"pfi-st " + i.status}>{i.status}</span><span className="faint">{ago(i.createdAt)}</span></div>
          <p className="pfi-page">About <button type="button" className="pfi-link" onClick={() => { setPage(i.page); setPg(1); }}>{i.pageName}</button> <small className="faint">{i.page}</small>
            {Object.keys(i.context).length > 0 && <small className="faint"> · {Object.entries(i.context).filter(([k]) => k !== "title").map(([k, v]) => `${k}: ${v}`).join(" · ")}</small>}</p>
          {i.message && <p className="pfi-msg">{i.message}</p>}
          <p className="pfi-from faint">{i.email ? <>From <a href={`mailto:${i.email}`}>{i.email}</a></> : "From a signed-in member"}{i.member && i.plan ? ` (${i.plan} plan)` : ""}</p>
          {i.note && <p className="pfi-note">Team note: {i.note}</p>}
          <div className="pf-act pfi-act">
            {i.status !== "read" && <button type="button" className="btn sm" onClick={() => act.mutate({ id: i.id, status: "read" })}>Mark read</button>}
            {i.status !== "resolved" && <button type="button" className="btn sm primary" onClick={() => act.mutate({ id: i.id, status: "resolved", note: prompt("A note for the team (optional)", i.note ?? "") ?? undefined })}>Resolve</button>}
            {i.status === "resolved" && <button type="button" className="btn sm" onClick={() => act.mutate({ id: i.id, status: "new" })}>Reopen</button>}
          </div>
        </article>))}
      {act.isError && <div className="pf-err" role="alert">{msg(act.error)}</div>}
      {list.data && list.data.pages > 1 && <nav className="pfi-pager" aria-label="Pages"><button className="btn sm" disabled={pg <= 1} onClick={() => setPg(pg - 1)}>Previous</button><span>{pg} of {list.data.pages}</span><button className="btn sm" disabled={pg >= list.data.pages} onClick={() => setPg(pg + 1)}>Next</button></nav>}
    </div></section>
  );
}
