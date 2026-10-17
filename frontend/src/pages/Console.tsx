import { useState } from "react";
import { Link, Navigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import * as acct from "../lib/account";
import { useAuth } from "../lib/auth";
import { TIER, useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" }) : "—");
const stamp = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");

/** Accounts, plan requests and the audit trail. Administrators only; the server re-checks role and two-step sign-in on every call. */
export function Console() {
  useDocTitle("Admin console", "FinLit administrators: manage members, plans and the audit log.");
  const { user, ready, isAdmin } = useAuth();
  const [tab, setTab] = useState<"users" | "requests" | "data" | "audit">("requests");
  if (!ready) return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "40px auto" }} /></div>;
  if (!user) return <Navigate to="/login?next=%2Fconsole" replace />;
  if (!isAdmin) return <div className="wrap state"><h1 style={{ font: "400 28px var(--serif)" }}>Administrators only</h1><p className="muted">This area is for the FinLit team.</p><Link className="btn" to="/dashboard">Back to your dashboard</Link></div>;
  if (!user.mfaOk) return <div className="wrap state"><h1 style={{ font: "400 28px var(--serif)" }}>One more step</h1><p className="muted">Administrators sign in with an authenticator-app code. {user.mfa ? "Sign out and sign in again, entering the code when asked." : "Set up two-step sign-in to continue."}</p><Link className="btn primary" to="/account/security?setup=1">Open security settings</Link></div>;
  return (
    <div className="wrap console">
      <header className="dash-h"><div><div className="eyebrow">Admin</div><h1>Console</h1><p className="muted">Members, plan requests and the audit trail. Content and enquiries are in the <Link to="/admin">CMS</Link>.</p></div></header>
      <div className="seg" role="tablist" aria-label="Console sections" style={{ marginBottom: 18 }}>
        {([["requests", "Plan requests"], ["users", "Members"], ["data", "Data health"], ["audit", "Audit log"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "requests" && <Requests />}
      {tab === "users" && <Users />}
      {tab === "data" && <Health />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

function Requests() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-requests"], queryFn: acct.adminRequests, retry: false });
  const grant = useMutation({ mutationFn: (r: acct.PlanRequest) => acct.adminPatch(r.userId, { plan: r.plan, plan_days: 365 }), onSettled: () => qc.invalidateQueries({ queryKey: ["admin-requests"] }) });
  const decline = useMutation({ mutationFn: (id: number) => acct.adminDecline(id), onSettled: () => qc.invalidateQueries({ queryKey: ["admin-requests"] }) });
  if (q.isError) return <div className="formerr">{msg(q.error)}</div>;
  const rows = q.data?.requests || [];
  return (
    <section className="card acct-c">
      <h2>Open requests</h2>
      {!rows.length ? <p className="muted">No open requests.</p> : (
        <div className="tw"><table className="qtt"><thead><tr><th>Member</th><th>Has</th><th>Wants</th><th>Note</th><th>Asked</th><th /></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.id}><td>{r.email}</td><td><span className={"tier " + r.currentPlan}>{TIER[r.currentPlan].n}</span></td><td><span className={"tier " + r.plan}>{TIER[r.plan].n}</span></td><td>{r.note || "—"}</td><td>{day(r.createdAt)}</td>
            <td className="ra"><button className="btn primary" disabled={grant.isPending} onClick={() => grant.mutate(r)}>Grant 1 year</button> <button className="btn" disabled={decline.isPending} onClick={() => decline.mutate(r.id)}>Decline</button></td></tr>)}</tbody></table></div>
      )}
      {(grant.isError || decline.isError) && <div className="formerr">{msg(grant.error || decline.error)}</div>}
    </section>
  );
}

function Users() {
  const qc = useQueryClient();
  const { toast } = useUI();
  const [term, setTerm] = useState(""), [q, setQ] = useState(""), [page, setPage] = useState(1);
  const list = useQuery({ queryKey: ["admin-users", q, page], queryFn: () => acct.adminUsers(q, page), retry: false, placeholderData: (p) => p });
  const patch = useMutation({ mutationFn: (v: { id: string; b: Parameters<typeof acct.adminPatch>[1] }) => acct.adminPatch(v.id, v.b), onSuccess: () => { toast("Saved."); qc.invalidateQueries({ queryKey: ["admin-users"] }); }, onError: (e) => toast(msg(e)) });
  const total = list.data?.total || 0;
  return (
    <section className="card acct-c">
      <div className="row between"><h2>Members <span className="muted">({total})</span></h2>
        <form onSubmit={(e) => { e.preventDefault(); setPage(1); setQ(term.trim()); }} className="row"><input aria-label="Search members" placeholder="Search name or email" value={term} onChange={(e) => setTerm(e.target.value)} className="cs-in" /><button className="btn">Search</button></form></div>
      {list.isError && <div className="formerr">{msg(list.error)}</div>}
      <div className="tw"><table className="qtt"><thead><tr><th>Member</th><th>Plan</th><th>Until</th><th>Status</th><th>2-step</th><th>Joined</th><th>Last sign-in</th></tr></thead>
        <tbody>{list.data?.users.map((u) => (
          <tr key={u.id}><td><b>{u.email}</b>{u.name ? <small className="muted"> · {u.name}</small> : null}{u.role === "admin" && <span className="chip gold" style={{ marginLeft: 6 }}>Admin</span>}{!u.verified && <span className="chip" style={{ marginLeft: 6 }}>Unverified</span>}</td>
            <td><select aria-label={`Plan for ${u.email}`} value={u.plan} onChange={(e) => patch.mutate({ id: u.id, b: { plan: e.target.value as acct.AdminUser["plan"], plan_days: e.target.value === "basic" ? undefined : 365 } })}>{(["basic", "bronze", "gold"] as const).map((p) => <option key={p} value={p}>{TIER[p].n}</option>)}</select></td>
            <td>{day(u.planUntil)}</td>
            <td><button className="btn" onClick={() => patch.mutate({ id: u.id, b: { status: u.status === "active" ? "disabled" : "active" } })}>{u.status === "active" ? "Disable" : "Enable"}</button></td>
            <td>{u.mfa ? <Icon name="check" /> : "—"}</td><td>{day(u.createdAt)}</td><td>{day(u.lastLoginAt)}</td></tr>))}</tbody></table></div>
      <div className="row between" style={{ marginTop: 12 }}><span className="muted">Page {page} of {Math.max(1, Math.ceil(total / 25))}</span>
        <span className="row"><button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><button className="btn" disabled={page * 25 >= total} onClick={() => setPage(page + 1)}>Next</button></span></div>
    </section>
  );
}

function Audit() {
  const q = useQuery({ queryKey: ["admin-audit"], queryFn: acct.adminAudit, retry: false });
  if (q.isError) return <div className="formerr">{msg(q.error)}</div>;
  return (
    <section className="card acct-c"><h2>Recent security events</h2>
      <div className="tw"><table className="qtt"><thead><tr><th>When</th><th>Event</th><th>Target</th><th>IP</th></tr></thead>
        <tbody>{q.data?.events.map((e, i) => <tr key={i}><td>{stamp(e.at)}</td><td>{e.action.replace(/_/g, " ")}</td><td className="mono">{e.target || "—"}</td><td className="mono">{e.ip || "—"}</td></tr>)}</tbody></table></div></section>
  );
}

function Health() {
  const q = useQuery({ queryKey: ["admin-health"], queryFn: acct.adminHealth, retry: false, refetchInterval: 15_000 });
  if (q.isError) return <div className="formerr">{msg(q.error)}</div>;
  const h = q.data;
  if (!h) return <div className="skeleton" style={{ height: 160 }} />;
  const pct = h.universe ? Math.round((h.loaded / h.universe) * 100) : 0;
  return (
    <section className="card acct-c">
      <h2>Company data</h2>
      <p className="muted">How much of the market is loaded from FinEdge. Companies load in the background; any company a visitor opens is queued first.</p>
      <div className="hstat"><div><b>{h.universe.toLocaleString("en-IN")}</b><span>companies in the universe</span></div><div><b>{h.loaded.toLocaleString("en-IN")}</b><span>loaded ({pct}%)</span></div><div><b>{h.scored.toLocaleString("en-IN")}</b><span>with a FinLit score</span></div><div><b>{h.queued}</b><span>waiting in the queue</span></div></div>
      <div className="prog" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Share of companies loaded"><i style={{ width: `${pct}%` }} /></div>
      <p className="muted">Last load: {h.lastLoad ? stamp(h.lastLoad) : "never"} · last 24 hours: {Object.entries(h.runs24h).map(([k, v]) => `${v} ${k}`).join(", ") || "no runs"}.</p>
      {h.universe === 0 && <div className="formerr">The company list is empty. Run <code>python -m finlit.worker refresh-universe</code>, then <code>probe</code> and <code>ingest-all</code>.</div>}
      {h.recentProblems.length > 0 && <div className="tw"><table className="qtt"><thead><tr><th>Company</th><th>Result</th><th>When</th><th>Detail</th></tr></thead><tbody>{h.recentProblems.map((p, i) => <tr key={i}><td><b>{p.symbol}</b></td><td>{p.status}</td><td>{stamp(p.at)}</td><td className="mono">{p.detail}</td></tr>)}</tbody></table></div>}
    </section>
  );
}
