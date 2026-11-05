// Console > Company brief: drafts written overnight, with their flags and citation checks; a person reads, then publishes, holds back or asks for a rewrite.
// Also the annual-report addresses (not in the exchanges' feed). Every write is role, Origin and CSRF checked on the server and audited.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { BriefBody } from "../../stock/CompanyBrief";
import type { BriefReply, Brief } from "../../lib/companyBrief";

type Row = { symbol: string; name: string | null; status: string; asOf: string | null; writtenAt: string; writtenBy: string | null; parts: string[]; problems: string[]; flags: string[]; citations: number; passed: number;
  failed: number; unchecked: number; published: boolean; publishedAt: string | null; rewriteAsked: boolean; canPublish: boolean };
type Run = { id: number; at: string; status: string; detail: Record<string, unknown> };
type List = { briefs: Row[]; counts: Record<string, number>; runs: Run[] };
type Failed = { path: string; doc: string; page: number; missing: string[]; found_on: number[]; part?: string };
type One = Row & { brief: Brief; checks: { failed: Failed[]; date?: string; method?: string }; text: string; publishedBrief: Brief | null; source: { annual_report_url?: string | null; last_reason?: string | null } | null; reviewNote: string | null };
type Missing = { symbol: string; name: string; annual_report_url: string | null; last_state: string | null; last_reason: string | null };
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");
const when = (s: string) => new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const STATUS = ["", "draft", "reviewed", "published", "rejected"] as const;

function Detail({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["brief-admin-one", symbol], queryFn: () => apiGet<One>(`/api/admin/company-brief/${encodeURIComponent(symbol)}`), retry: false });
  const [note, setNote] = useState(""), [url, setUrl] = useState(""), [view, setView] = useState<"page" | "text">("page");
  const act = useMutation({ mutationFn: (a: string) => apiSend("POST", `/api/admin/company-brief/${encodeURIComponent(symbol)}/${a}`, { note: note || undefined }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["brief-admin"] }); qc.invalidateQueries({ queryKey: ["brief-admin-one", symbol] }); } });
  const src = useMutation({ mutationFn: () => apiSend("PUT", `/api/admin/company-brief/${encodeURIComponent(symbol)}/source`, { annual_report_url: url || null }), onSettled: () => qc.invalidateQueries({ queryKey: ["brief-admin-one", symbol] }) });
  if (q.isError) return <div className="formerr">{msg(q.error)} <button className="btn" onClick={onClose}>Close</button></div>;
  if (!q.data) return <div className="skeleton" style={{ height: 120 }} />;
  const o = q.data, failed = o.checks?.failed ?? [];
  const reply: BriefReply = { symbol: o.symbol, name: o.name, state: "published", brief: { ...o.brief, status: o.status }, asOf: o.asOf ?? o.brief.as_of, reviewedAt: null, stale: false, checks: { date: o.checks?.date, citations: o.citations, passed: o.passed, unchecked: o.unchecked, fixed: [], method: o.checks?.method },
    chips: Object.fromEntries(Object.entries(o.brief.docs ?? {}).map(([k, d]) => [k, ({ "Annual report": "AR", "Results filing": "RES", "Press release": "PR", "Investor presentation": "PRES", "Call transcript": "TR", "Exchange filing": "EV" } as Record<string, string>)[d.kind] ?? k])), disclaimer: o.brief.disclaimer ?? "", compliance: "" };
  return (
    <section className="card acct-c">
      <h2>{o.name ?? o.symbol} ({o.symbol}) · {o.status}</h2>
      <p className="muted">Written {when(o.writtenAt)} by {o.writtenBy ?? "the writer"} · parts: {o.parts.join(", ") || "all"} · filings to {o.asOf ?? "—"} · {o.passed} of {o.citations} citations found on their page{o.unchecked ? `, ${o.unchecked} not checked` : ""}.
        {o.published ? ` A reviewed copy is live on the company page (since ${o.publishedAt ? when(o.publishedAt) : "earlier"}).` : " Nothing is live on the company page yet."}</p>
      {o.problems.length > 0 && <div className="formerr" role="alert"><b>Blocking problems (it cannot be published):</b><ul>{o.problems.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
      {failed.length > 0 && <div className="formerr" role="alert"><b>Citations not found on their page:</b><ul>{failed.map((f, i) => <li key={i}>{f.path}: {f.doc} page {f.page} lacks {f.missing.join(", ")}{f.found_on.length ? ` (found on page ${f.found_on.join(", ")})` : ""}</li>)}</ul></div>}
      {o.flags.length > 0 && <details><summary>{o.flags.length} line(s) to read with care</summary><ul>{o.flags.map((f, i) => <li key={i}>{f}</li>)}</ul></details>}
      <label className="fld"><span>Note (kept in the audit trail)</span><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} /></label>
      <div className="row-gap">
        <button className="btn primary" disabled={act.isPending || !o.canPublish} onClick={() => act.mutate("approve")} title={o.canPublish ? "" : "Blocked: fix the problems above by asking for a rewrite"}>Approve and publish</button>
        <button className="btn" disabled={act.isPending} onClick={() => act.mutate("reviewed")}>Mark as read</button>
        <button className="btn" disabled={act.isPending} onClick={() => act.mutate("reject")}>Keep unpublished</button>
        <button className="btn" disabled={act.isPending || !o.published} onClick={() => act.mutate("unpublish")}>Take down</button>
        <button className="btn" disabled={act.isPending || o.rewriteAsked} onClick={() => act.mutate("rewrite")}>{o.rewriteAsked ? "Rewrite queued for tonight" : "Rewrite tonight"}</button>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      {(act.error || src.error) && <div className="formerr" role="alert">{msg(act.error || src.error)}</div>}
      <div className="row-gap" style={{ margin: "12px 0" }}>
        <label className="fld"><span>Annual report address (https, the company's own site)</span><input value={url} placeholder={o.source?.annual_report_url ?? "https://"} onChange={(e) => setUrl(e.target.value)} maxLength={600} /></label>
        <button className="btn" disabled={src.isPending || !url} onClick={() => src.mutate()}>Save address</button>
      </div>
      <div className="seg" role="tablist" aria-label="View" style={{ marginBottom: 12 }}>
        <button role="tab" aria-selected={view === "page"} onClick={() => setView("page")}>As readers see it</button>
        <button role="tab" aria-selected={view === "text"} onClick={() => setView("text")}>Plain text</button>
      </div>
      {view === "text" ? <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 13 }}>{o.text}</pre> : <div className="cb" style={{ margin: 0 }}><BriefBody r={reply as Extract<BriefReply, { state: "published" }>} /></div>}
    </section>
  );
}

export function BriefAdmin() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<(typeof STATUS)[number]>("");
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["brief-admin", status], queryFn: () => apiGet<List>(`/api/admin/company-brief/drafts?status=${status}`), retry: false });
  const miss = useQuery({ queryKey: ["brief-admin-missing"], queryFn: () => apiGet<{ missing: Missing[] }>("/api/admin/company-brief/sources"), retry: false });
  const [sym, setSym] = useState(""), [url, setUrl] = useState("");
  const save = useMutation({ mutationFn: () => apiSend("PUT", `/api/admin/company-brief/${encodeURIComponent(sym)}/source`, { annual_report_url: url }), onSuccess: () => { setSym(""); setUrl(""); qc.invalidateQueries({ queryKey: ["brief-admin-missing"] }); } });
  if (list.isError) return <div className="formerr">{msg(list.error)}</div>;
  if (!list.data) return <div className="skeleton" style={{ height: 160 }} />;
  const d = list.data, last = d.runs[0];
  return (
    <>
      {open && <Detail symbol={open} onClose={() => setOpen(null)} />}
      <section className="card acct-c">
        <h2>Company briefs</h2>
        <p className="muted">Written overnight from each company's own filings; nothing is shown on a company page until a person approves it. {Object.entries(d.counts).map(([k, v]) => `${v} ${k}`).join(" · ") || "No briefs yet."}
          {last ? ` Last run ${when(last.at)}: ${last.status === "not_configured" ? "not configured (no writing key on the server; nothing was written)" : `${String(last.detail.written ?? 0)} written, ${String(last.detail.nothing_new ?? 0)} with nothing new${last.detail.stopped ? `, stopped: ${String(last.detail.stopped)}` : ""}`}.` : " The job has not run yet."}</p>
        <div className="seg" role="tablist" aria-label="Status" style={{ marginBottom: 12 }}>
          {STATUS.map((s) => <button key={s} role="tab" aria-selected={status === s} onClick={() => setStatus(s)}>{s || "all"}</button>)}
        </div>
        {!d.briefs.length ? <p className="muted">Nothing here.</p> : (
          <div className="tw"><table className="qtt"><thead><tr><th>Company</th><th>Status</th><th>Filings to</th><th>Written</th><th>Citations</th><th>Flags</th><th /></tr></thead>
            <tbody>{d.briefs.map((r) => <tr key={r.symbol}><td><b>{r.symbol}</b><div className="muted">{r.name}</div></td><td>{r.status}{r.published && r.status !== "published" ? " (older copy live)" : ""}</td><td>{r.asOf ?? "—"}</td><td>{when(r.writtenAt)}</td>
              <td>{r.passed}/{r.citations}{r.failed ? <b> · {r.failed} wrong</b> : ""}</td><td>{r.problems.length ? <b>{r.problems.length} blocking</b> : r.flags.length ? `${r.flags.length} to read` : "none"}</td>
              <td><button className="btn" onClick={() => setOpen(r.symbol)}>Review</button></td></tr>)}</tbody></table></div>
        )}
      </section>
      <section className="card acct-c">
        <h2>Annual report addresses</h2>
        <p className="muted">A brief needs the company's annual report, and the exchanges' feed does not carry its address. Paste the https address of the PDF on the company's own website. Companies without one show "no annual report on file".</p>
        <div className="row-gap">
          <label className="fld"><span>Symbol</span><input value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())} maxLength={24} /></label>
          <label className="fld"><span>PDF address</span><input value={url} onChange={(e) => setUrl(e.target.value)} maxLength={600} placeholder="https://" /></label>
          <button className="btn" disabled={save.isPending || !sym || !url} onClick={() => save.mutate()}>Save address</button>
        </div>
        {save.error && <div className="formerr" role="alert">{msg(save.error)}</div>}
        {miss.data && <div className="tw"><table className="qtt"><thead><tr><th>Largest companies without an address</th><th>State</th><th /></tr></thead>
          <tbody>{miss.data.missing.slice(0, 25).map((m) => <tr key={m.symbol}><td><b>{m.symbol}</b> <span className="muted">{m.name}</span></td><td>{m.last_reason || m.last_state || "not tried yet"}</td><td><button className="btn" onClick={() => setSym(m.symbol)}>Use</button></td></tr>)}</tbody></table></div>}
      </section>
    </>
  );
}
