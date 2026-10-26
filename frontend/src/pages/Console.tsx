import { useState } from "react";
import { Link, Navigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend, apiUrl } from "../lib/api";
import { useIpos } from "../lib/ipo";
import { useFeed } from "../lib/feed";
import * as acct from "../lib/account";
import { useAuth } from "../lib/auth";
import { TIER, useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { fundJobLine, fundPollMs } from "../lib/fundJobs";

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" }) : "—");
const stamp = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");

/** Accounts, plan requests and the audit trail. Administrators only; the server re-checks role and two-step sign-in on every call. */
/** Email addresses people left under "Coming soon: get notified". */
function NotifyList() {
  const { data } = useQuery({ queryKey: ["admin-notify"], queryFn: () => apiGet<{ total: number; items: { email: string; source: string; at: string }[] }>("/api/admin/notify"), staleTime: 30_000 });
  return (
    <section className="card acct-c">
      <h2>Launch notification list</h2>
      <p className="muted">People who asked to be told when new features go live. Keep this list private and only use it for that purpose.</p>
      {!data ? <div className="skeleton" style={{ height: 60 }} /> : (
        <>
          <p><b>{data.total.toLocaleString("en-IN")}</b> {data.total === 1 ? "address" : "addresses"} <a className="btn" style={{ marginLeft: 12 }} href={apiUrl("/api/admin/notify?format=csv")}>Download CSV</a></p>
          {data.items.length > 0 && <div className="tw"><table className="acct-t"><thead><tr><th>Email</th><th>From</th><th>When</th></tr></thead><tbody>{data.items.slice(0, 20).map((r) => <tr key={r.email}><td>{r.email}</td><td>{r.source}</td><td>{new Date(r.at).toLocaleDateString("en-IN")}</td></tr>)}</tbody></table></div>}
        </>)}
    </section>
  );
}

/** Switches that show a feature to administrators only until they are turned on for everyone. */
function Features() {
  const qc = useQueryClient(); const { toast } = useUI();
  const q = useQuery({ queryKey: ["admin-features"], queryFn: () => apiGet<{ features: { name: string; enabled: boolean; updatedAt: string; updatedBy: string | null }[] }>("/api/admin/features"), retry: false });
  const set = useMutation({
    mutationFn: (v: { name: string; enabled: boolean }) => apiSend("PUT", `/api/admin/features/${v.name}`, { enabled: v.enabled }),
    onSuccess: (_d, v) => { qc.invalidateQueries({ queryKey: ["admin-features"] }); qc.removeQueries({ queryKey: ["leadership"] }); toast(v.enabled ? "Switched on for everyone." : "Switched off: only administrators see it."); },
    onError: (e) => toast(msg(e)),
  });
  const LABEL: Record<string, string> = { leadership: "Leader / In line / Laggard label" };
  if (q.isError) return null;
  return (
    <section className="card acct-c">
      <h2>Feature switches</h2>
      <p className="muted">A switch that is off shows the feature to administrators only, so it can be checked on the live site first.</p>
      {!q.data ? <div className="skeleton" style={{ height: 50 }} /> : q.data.features.map((f) => (
        <div key={f.name} style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", padding: "8px 0" }}>
          <b>{LABEL[f.name] || f.name}</b>
          <span className="muted">{f.enabled ? "On for everyone" : "Administrators only"}{f.updatedBy ? ` · changed by ${f.updatedBy}, ${stamp(f.updatedAt)}` : ""}</span>
          <button className={"btn" + (f.enabled ? "" : " primary")} disabled={set.isPending} onClick={() => set.mutate({ name: f.name, enabled: !f.enabled })}>{f.enabled ? "Switch off" : "Switch on for everyone"}</button>
        </div>))}
    </section>
  );
}

export function Console() {
  useDocTitle("Admin console", "FinLit administrators: manage members, plans and the audit log.");
  const { user, ready, isAdmin } = useAuth();
  const [tab, setTab] = useState<"users" | "requests" | "content" | "data" | "audit">("requests");
  if (!ready) return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "40px auto" }} /></div>;
  if (!user) return <Navigate to="/login?next=%2Fconsole" replace />;
  if (!isAdmin) return <div className="wrap state"><h1 style={{ font: "400 28px var(--serif)" }}>Administrators only</h1><p className="muted">This area is for the FinLit team.</p><Link className="btn" to="/dashboard">Back to your dashboard</Link></div>;
  if (!user.mfaOk) return <div className="wrap state"><h1 style={{ font: "400 28px var(--serif)" }}>One more step</h1><p className="muted">Administrators sign in with an authenticator-app code. {user.mfa ? "Sign out and sign in again, entering the code when asked." : "Set up two-step sign-in to continue."}</p><Link className="btn primary" to="/account/security?setup=1">Open security settings</Link></div>;
  return (
    <div className="wrap console">
      <header className="dash-h"><div><div className="eyebrow">Admin</div><h1>Console</h1><p className="muted">Members, plan requests and the audit trail. Blog posts and website enquiries are in the <Link to="/admin">content tools</Link> (no second sign-in).</p></div></header>
      <div className="seg" role="tablist" aria-label="Console sections" style={{ marginBottom: 18 }}>
        {([["requests", "Plan requests"], ["users", "Members"], ["content", "Calendar & news"], ["data", "Data health"], ["audit", "Audit log"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "requests" && <Requests />}
      {tab === "users" && <Users />}
      {tab === "content" && <ContentAdmin />}
      {tab === "data" && <><Health /><FundLoads /><Features /><NotifyList /></>}
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
          <tr key={u.id}><td><b>{u.email}</b>{u.name ? <small className="muted"> · {u.name}</small> : null}{u.role === "admin" && <span className="chip gold" style={{ marginLeft: 6 }}>Admin</span>}{!u.verified && <><span className="chip" style={{ marginLeft: 6 }}>Unverified</span> <button className="btn" style={{ marginLeft: 6, padding: "2px 10px" }} onClick={() => patch.mutate({ id: u.id, b: { verify_email: true } })}>Confirm email</button></>}</td>
            <td><select aria-label={`Plan for ${u.email}`} value={u.plan} onChange={(e) => patch.mutate({ id: u.id, b: { plan: e.target.value as acct.AdminUser["plan"], plan_days: e.target.value === "basic" ? undefined : 365 } })}>{(["basic", "silver", "gold"] as const).map((p) => <option key={p} value={p}>{TIER[p].n}</option>)}</select></td>
            <td>{day(u.planUntil)}</td>
            <td><button className="btn" onClick={() => patch.mutate({ id: u.id, b: { status: u.status === "active" ? "disabled" : "active" } })}>{u.status === "active" ? "Disable" : "Enable"}</button>{" "}<button className="btn" onClick={() => { const up = u.role !== "admin"; if (window.confirm(up ? `Make ${u.email} an administrator? They will set up their own authenticator app at their next sign-in.` : `Remove administrator access from ${u.email}?`)) patch.mutate({ id: u.id, b: { role: up ? "admin" : "investor" } }); }}>{u.role === "admin" ? "Remove admin" : "Make admin"}</button></td>
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
      <p className="muted">IPO and results calendars refresh by themselves (daily, and every few hours in market time). Results dates last refreshed: {h.calendars?.resultsAt ? stamp(h.calendars.resultsAt) : "not yet"}{h.calendars?.resultsThrough ? `, covering dates through ${h.calendars.resultsThrough}` : ""}. IPOs: {h.calendars?.ipoAt ? stamp(h.calendars.ipoAt) : "not yet"}.</p>
      {h.funds && (
        <p className="muted">
          ETFs: {h.funds.etf ? `${h.funds.etf.active} active of ${h.funds.etf.n}, last refresh ${h.funds.etf.last ? stamp(h.funds.etf.last) : "never"}` : "not set up"} ·
          Mutual funds: {h.funds.mf ? `${h.funds.mf.active} active of ${h.funds.mf.n} schemes, ${h.funds.mf.with_history} with history, last refresh ${h.funds.mf.last ? stamp(h.funds.mf.last) : "never"}` : "not set up"}.
        </p>
      )}
      {h.clientIp && (
        <p className="muted">
          How this server sees you (used for rate limits and sign-in lockouts): <span className="mono">{h.clientIp.resolved}</span>
          {h.clientIp.chain ? <> from the proxy chain <span className="mono">{h.clientIp.chain}</span></> : null}. This should be your own public address;
          if it is a Cloudflare or hosting address, add that range to <code>TRUSTED_PROXIES</code>.
        </p>
      )}
      <p className="muted">Last load: {h.lastLoad ? stamp(h.lastLoad) : "never"} · last 24 hours: {Object.entries(h.runs24h).map(([k, v]) => `${v} ${k}`).join(", ") || "no runs"}.</p>
      {h.universe === 0 && <div className="formerr">The company list is empty. Run <code>python -m finlit.worker refresh-universe</code>, then <code>probe</code> and <code>ingest-all</code>.</div>}
      {h.coverage && <div style={{ marginTop: 14 }}>
        <h3 style={{ margin: "0 0 6px", font: "600 15px var(--sans)" }}>What the provider sent against what the reports show</h3>
        <p className="muted">{Object.entries(h.coverage.byState).map(([k, v]) => `${v} ${k}`).join(" · ") || "No company checked yet"}. "Provider sent it, report lacks it" must always be zero: any line below is a fault to fix, not a data gap.</p>
        {h.coverage.mismatches.length > 0 ? <div className="formerr" role="alert"><b>{h.coverage.mismatches.length} companies where the provider sent data the report lacks:</b> {h.coverage.mismatches.map((m) => `${m.symbol} (${m.lines.join("; ")})`).join(" · ")}</div> : <p className="pos">None: every figure the provider sent is shown.</p>}
        {h.coverage.providerEmpty.length > 0 && <p className="muted">The provider sent nothing for: {h.coverage.providerEmpty.map((c) => `${c.symbol}${c.name ? " " + c.name : ""}`).join(", ")}.</p>}
      </div>}
      <div style={{ marginTop: 14 }}>
        {h.resultsLight && <p className="muted" data-testid="results-light"><b>Quarter results, last {h.resultsLight.days} days:</b> {h.resultsLight.declared} declared · {h.resultsLight.filled} with figures ({h.resultsLight.fromFullReport} from the full report, {h.resultsLight.fromLightRow} from the light path) · {h.resultsLight.awaitingProvider} waiting for the data provider · {h.resultsLight.awaitingOurs} waiting for us.</p>}
        <h3 style={{ margin: "0 0 6px", font: "600 15px var(--sans)" }}>Data integrity {h.integrity && <span className={h.integrity.level === "green" ? "pos" : "neg"}>{h.integrity.level === "green" ? "● green" : h.integrity.level === "amber" ? "● amber" : "● red"}</span>}</h3>
        {!h.integrity ? <p className="muted">The nightly audit has not run yet. It samples up to 40 companies a night and checks prices, latest quarter, profit and loss sums, declared results and risk figures.</p> : (
          <>
            <p className="muted">Last audit {stamp(h.integrity.at)}, {h.integrity.sampled} companies sampled.</p>
            <ul style={{ paddingLeft: 18 }}>{h.integrity.checks.map((c) => <li key={c.key}><b style={{ color: c.level === "green" ? "var(--gain)" : c.level === "amber" ? "var(--warn, #b7791f)" : "var(--loss)" }}>{c.level === "green" ? "Green" : c.level === "amber" ? "Amber" : "Red"}</b> · {c.label}: {c.message}{c.examples.length > 0 && <span className="muted mono"> e.g. {c.examples.join(" | ")}</span>}</li>)}</ul>
          </>
        )}
      </div>
      {h.recentProblems.length > 0 && <div className="tw"><table className="qtt"><thead><tr><th>Company</th><th>Result</th><th>When</th><th>Detail</th></tr></thead><tbody>{h.recentProblems.map((p, i) => <tr key={i}><td><b>{p.symbol}</b></td><td>{p.status}</td><td>{stamp(p.at)}</td><td className="mono">{p.detail}</td></tr>)}</tbody></table></div>}
    </section>
  );
}

const FUND_BUTTONS: { job: acct.FundJob; label: string; what: string }[] = [
  { job: "refresh-etf", label: "Load ETFs", what: "download today's ETF prices and history" },
  { job: "refresh-mf", label: "Load mutual funds", what: "download today's mutual fund NAVs" },
  { job: "backfill-mf", label: "Load fund history", what: "download up to five years of fund NAV history (the largest download)" },
];

/** Start the ETF and mutual fund loads by hand while the scheduled ones are paused. */
function FundLoads() {
  const qc = useQueryClient();
  const { toast } = useUI();
  const q = useQuery({ queryKey: ["admin-funds"], queryFn: acct.fundStatus, retry: false, refetchInterval: (query) => fundPollMs(query.state.data) });
  const [ask, setAsk] = useState<(typeof FUND_BUTTONS)[number] | null>(null);
  const run = useMutation({ mutationFn: (j: acct.FundJob) => acct.fundRun(j), onSuccess: () => { toast("Load started."); qc.invalidateQueries({ queryKey: ["admin-funds"] }); }, onError: (e) => { toast(msg(e)); qc.invalidateQueries({ queryKey: ["admin-funds"] }); } });
  const s = q.data;
  const busy = !!s?.running || run.isPending;
  return (
    <section className="card acct-c">
      <h2>ETF and mutual fund data</h2>
      {q.isError ? <div className="formerr">{msg(q.error)}</div> : !s ? <div className="skeleton" style={{ height: 60 }} /> : (
        <>
          <p className="muted">{s.scheduledPaused ? "The automatic nightly loads are paused, so these only update when you press a button." : "The automatic nightly loads are on."} {s.running ? "A load is running now; this page checks every 5 seconds." : "Nothing is running."}</p>
          <ul className="muted" style={{ paddingLeft: 18 }}>{FUND_BUTTONS.map((b) => <li key={b.job}><b>{b.label}:</b> {fundJobLine(s.jobs[b.job], stamp)}</li>)}</ul>
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            {FUND_BUTTONS.map((b) => <button key={b.job} className="btn" disabled={busy} onClick={() => setAsk(b)}>{b.label}</button>)}
          </div>
        </>
      )}
      {ask && (
        <div role="alertdialog" aria-modal="true" aria-label={ask.label} className="formerr" style={{ marginTop: 12, background: "var(--surface, transparent)", color: "inherit", border: "1px solid var(--line, currentColor)" }}>
          <p><b>{ask.label}?</b> This will {ask.what}. Downloads use bandwidth: the free Render plan allows 5 GB a month and it has already been exceeded. Only continue if you need fresh data now.</p>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary" autoFocus onClick={() => { run.mutate(ask.job); setAsk(null); }}>Start load</button>
            <button className="btn" onClick={() => setAsk(null)}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}

const num = (v: FormDataEntryValue | null) => (v === null || v === "" ? null : Number(v));
const txt = (v: FormDataEntryValue | null) => (v === null || String(v).trim() === "" ? null : String(v).trim());

function ContentAdmin() {
  const qc = useQueryClient();
  const { toast } = useUI();
  const ipos = useIpos(true);
  const [kind, setKind] = useState<"result" | "news" | "document">("result");
  const items = useFeed(kind, { limit: 60, fresh: true, manual: true });
  const done = (m: string) => { toast(m); qc.invalidateQueries({ queryKey: ["ipos"] }); qc.invalidateQueries({ queryKey: ["feed"] }); };
  const ipo = useMutation({ mutationFn: (b: Record<string, unknown>) => acct.addIpo(b), onSuccess: () => done("IPO added."), onError: (e) => toast(msg(e)) });
  const rmIpo = useMutation({ mutationFn: (id: number) => acct.deleteIpo(id), onSuccess: () => done("IPO removed."), onError: (e) => toast(msg(e)) });
  const feed = useMutation({ mutationFn: (b: Record<string, unknown>) => acct.addFeed(b), onSuccess: () => done("Added."), onError: (e) => toast(msg(e)) });
  const rmFeed = useMutation({ mutationFn: (id: number) => acct.deleteFeed(id), onSuccess: () => done("Removed."), onError: (e) => toast(msg(e)) });
  const submitIpo = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const f = new FormData(e.currentTarget); const form = e.currentTarget;
    ipo.mutate({ name: txt(f.get("name")), symbol: txt(f.get("symbol")), kind: f.get("kind"), sector: txt(f.get("sector")), open_date: f.get("open"), close_date: f.get("close"), listing_date: txt(f.get("listing")), price_low: num(f.get("low")), price_high: num(f.get("high")), lot_size: num(f.get("lot")), issue_size_cr: num(f.get("size")), listing_price: num(f.get("lp")), note: txt(f.get("note")), link: txt(f.get("link")) }, { onSuccess: () => form.reset() });
  };
  const submitFeed = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const f = new FormData(e.currentTarget); const form = e.currentTarget;
    feed.mutate({ kind, title: txt(f.get("title")), symbol: txt(f.get("symbol")), company: txt(f.get("company")), source: txt(f.get("source")), link: txt(f.get("link")), item_date: f.get("date"), category: txt(f.get("category")), period: txt(f.get("period")), summary: txt(f.get("summary")) }, { onSuccess: () => form.reset() });
  };
  return (
    <>
      <section className="card acct-c">
        <h2>IPO calendar</h2><p className="muted">Add an issue when it is announced; its status (upcoming, open, closed, listed) follows the dates automatically.</p>
        <form className="form agrid" onSubmit={submitIpo}>
          <label>Company<input name="name" required maxLength={120} /></label><label>Symbol <span className="faint">(after listing)</span><input name="symbol" maxLength={24} /></label>
          <label>Board<select name="kind"><option value="mainboard">Mainboard</option><option value="sme">SME</option></select></label><label>Sector<input name="sector" maxLength={60} /></label>
          <label>Opens<input type="date" name="open" required /></label><label>Closes<input type="date" name="close" required /></label><label>Listing date<input type="date" name="listing" /></label>
          <label>Price band low (₹)<input type="number" step="0.01" min="0" name="low" /></label><label>Price band high (₹)<input type="number" step="0.01" min="0" name="high" /></label><label>Lot size (shares)<input type="number" min="1" name="lot" /></label>
          <label>Issue size (₹ Cr)<input type="number" step="0.01" min="0" name="size" /></label><label>Listing price (₹)<input type="number" step="0.01" min="0" name="lp" /></label>
          <label className="wide">Offer document link <span className="faint">(https)</span><input name="link" maxLength={300} placeholder="https://" /></label><label className="wide">Note<input name="note" maxLength={400} /></label>
          <div className="wide"><button className="btn primary" disabled={ipo.isPending}>Add IPO</button></div>
        </form>
        {(ipos.data || []).length > 0 && <div className="tw" style={{ marginTop: 14 }}><table className="qtt"><thead><tr><th>Company</th><th>Opens</th><th>Closes</th><th>Status</th><th /></tr></thead><tbody>{ipos.data!.map((r) => <tr key={r.id}><td><b>{r.name}</b></td><td>{r.openDate}</td><td>{r.closeDate}</td><td>{r.status}</td><td className="ra"><button className="btn" onClick={() => rmIpo.mutate(r.id)}>Remove</button></td></tr>)}</tbody></table></div>}
      </section>
      <section className="card acct-c">
        <h2>Result dates, news and documents</h2>
        <div className="seg" role="group" aria-label="Kind" style={{ marginBottom: 14 }}>{([["result", "Result date"], ["news", "News item"], ["document", "Document"]] as const).map(([k, l]) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}</div>
        <form className="form agrid" onSubmit={submitFeed} key={kind}>
          <label className="wide">{kind === "result" ? "Title (for example: Q2 FY27 results)" : "Headline"}<input name="title" required minLength={3} maxLength={300} /></label>
          <label>Company symbol<input name="symbol" maxLength={24} placeholder="TCS" /></label><label>Company name<input name="company" maxLength={120} /></label>
          <label>{kind === "result" ? "Results date" : "Date"}<input type="date" name="date" required /></label>
          {kind === "result" && <label>Period<input name="period" maxLength={24} placeholder="Q2 FY27" /></label>}
          <label>Category<input name="category" maxLength={80} placeholder={kind === "document" ? "Annual report" : kind === "result" ? "Board meeting" : "Market news"} /></label><label>Source<input name="source" maxLength={80} /></label>
          <label className="wide">Link <span className="faint">(https)</span><input name="link" maxLength={400} placeholder="https://" /></label>
          {kind === "news" && <label className="wide">Summary<input name="summary" maxLength={600} /></label>}
          <div className="wide"><button className="btn primary" disabled={feed.isPending}>Add</button></div>
        </form>
        {(items.data || []).filter((i) => !i.auto).length > 0 && <div className="tw" style={{ marginTop: 14 }}><table className="qtt"><thead><tr><th>Date</th><th>Title</th><th>Company</th><th /></tr></thead><tbody>{items.data!.filter((i) => !i.auto).map((i) => <tr key={i.id}><td>{i.date}</td><td>{i.title}</td><td>{i.symbol || "—"}</td><td className="ra"><button className="btn" onClick={() => rmFeed.mutate(i.id)}>Remove</button></td></tr>)}</tbody></table></div>}
        <p className="muted" style={{ marginTop: 10 }}>Exchange announcements are added automatically when a company is loaded and are not listed here.</p>
      </section>
    </>
  );
}
