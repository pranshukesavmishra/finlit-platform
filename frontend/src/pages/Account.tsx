import { useState } from "react";
import { Link, NavLink, Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import * as acct from "../lib/account";
import { useAuth } from "../lib/auth";
import { RANK, TIER, useUI, type Plan } from "../lib/ui";
import { PALETTES, PALETTE_IDS } from "../lib/palettes";
import { prefs, usePrefs } from "../lib/prefs";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { PasswordField } from "./Login";
import { DEMO } from "../lib/demo";

const TABS = [["", "Profile", "users"], ["security", "Security", "lock"], ["appearance", "Appearance", "spark"], ["plan", "Plan", "crown"]] as const;
const msg = (e: unknown) => e instanceof ApiError ? e.body.detail || "Something went wrong." : "We could not reach FinLit. Check your connection.";
const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function Status({ m, ok }: { m: { isError: boolean; error: unknown; isSuccess: boolean }; ok?: string }) {
  return <>{m.isError && <div className="formerr" role="alert">{msg(m.error)}</div>}{m.isSuccess && ok && <div className="formok" role="status">{ok}</div>}</>;
}

export function Account() {
  useDocTitle("Your account", "Manage your FinLit profile, security, appearance and plan.");
  const { tab = "" } = useParams();
  const { user, ready } = useAuth();
  if (!ready) return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "40px auto" }} /></div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent("/account" + (tab ? "/" + tab : ""))}`} replace />;
  return (
    <div className="wrap acct">
      <header className="acct-h">
        <div className="av lg" aria-hidden="true">{(user.name || user.email)[0].toUpperCase()}</div>
        <div><h1>{user.name || "Your account"}</h1><p className="muted">{user.email} · <span className={"tier " + user.plan}>{TIER[user.plan].n}</span></p></div>
      </header>
      <nav className="acct-tabs" aria-label="Account sections">
        {TABS.filter(([to]) => !DEMO || to === "appearance").map(([to, label, ic]) => <NavLink key={to} to={to ? `/account/${to}` : "/account"} end className={({ isActive }) => (isActive ? "on" : "")}><Icon name={ic} />{label}</NavLink>)}
        <Link to="/dashboard"><Icon name="table" />Dashboard</Link>
      </nav>
      {DEMO && <div className="card acct-c callout"><b>Demo preview.</b> Sign-in, security, sessions and plan requests are live on the real site; here you can try the appearance settings and the dashboard.</div>}
      {tab === "" && !DEMO && <Profile />}
      {tab === "security" && !DEMO && <Security />}
      {tab === "appearance" && <Appearance />}
      {tab === "plan" && !DEMO && <PlanTab />}
      {DEMO && tab !== "appearance" && <Navigate to="/account/appearance" replace />}
      {!["", "security", "appearance", "plan"].includes(tab) && <Navigate to="/account" replace />}
    </div>
  );
}

function Profile() {
  const { user, refresh, signOut } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState(user?.name || "");
  const save = useMutation({ mutationFn: () => acct.updateProfile(name.trim()), onSuccess: () => refresh() });
  return (
    <section className="card acct-c">
      <h2>Profile</h2>
      <form className="form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoComplete="name" /></label>
        <label>Email<input value={user?.email} readOnly aria-readonly="true" /></label>
        <Status m={save} ok="Saved." />
        <div className="row"><button className="btn primary" disabled={save.isPending}>Save changes</button>
          <button type="button" className="btn" onClick={async () => { await signOut(); nav("/"); }}>Sign out</button></div>
      </form>
    </section>
  );
}

function Security() {
  const { user, refresh, signOut } = useAuth();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [cur, setCur] = useState(""), [nw, setNw] = useState("");
  const pw = useMutation({ mutationFn: () => acct.changePassword(cur, nw), onSuccess: () => { setCur(""); setNw(""); qc.invalidateQueries({ queryKey: ["sessions"] }); } });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: acct.listSessions });
  const end = useMutation({ mutationFn: (id: string) => acct.endSession(id), onSuccess: () => sessions.refetch() });
  const others = useMutation({ mutationFn: acct.endOtherSessions, onSuccess: () => sessions.refetch() });
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [code, setCode] = useState("");
  const start = useMutation({ mutationFn: acct.mfaSetup, onSuccess: setSetup });
  const enable = useMutation({ mutationFn: () => acct.mfaEnable(code.trim()), onSuccess: async () => { setSetup(null); setCode(""); await refresh(); } });
  const disable = useMutation({ mutationFn: () => acct.mfaDisable(code.trim()), onSuccess: async () => { setCode(""); await refresh(); } });
  const [del, setDel] = useState(false), [delPw, setDelPw] = useState("");
  const remove = useMutation({ mutationFn: () => acct.deleteAccount(delPw), onSuccess: async () => { await signOut(); nav("/"); } });
  const mustSetUp = user?.role === "admin" && !user.mfa;
  return (
    <>
      {(mustSetUp || params.get("setup")) && !user?.mfa && <div className="card acct-c callout"><b>Administrators sign in with two steps.</b> Add an authenticator app below to unlock the admin tools.</div>}
      <section className="card acct-c">
        <h2>Two-step sign-in</h2>
        <p className="muted">After your password, enter a 6-digit code from an authenticator app (Google Authenticator, Authy, 1Password…). Even if someone learns your password they cannot sign in.</p>
        {user?.mfa ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); disable.mutate(); }}>
            <p><span className="chip gain">On</span></p>
            {user.role !== "admin" && <><label>Current code (to switch off)<input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} maxLength={8} /></label>
              <Status m={disable} /><button className="btn" disabled={disable.isPending || code.length < 6}>Turn off</button></>}
          </form>
        ) : setup ? (
          <form className="form" onSubmit={(e) => { e.preventDefault(); enable.mutate(); }}>
            <ol className="steps"><li>Open your authenticator app and add an account. On a phone, <a href={setup.uri}>tap here to add it automatically</a>.</li>
              <li>Or type this setup key by hand: <code className="key">{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</code></li>
              <li>Enter the 6-digit code the app shows.</li></ol>
            <label>Code<input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} maxLength={8} autoFocus required /></label>
            <Status m={enable} />
            <div className="row"><button className="btn primary" disabled={enable.isPending || code.length < 6}>Turn on</button><button type="button" className="btn" onClick={() => setSetup(null)}>Cancel</button></div>
          </form>
        ) : <><Status m={start} /><button className="btn primary" onClick={() => start.mutate()} disabled={start.isPending}>Set up authenticator app</button></>}
      </section>
      <section className="card acct-c">
        <h2>Password</h2>
        <form className="form" onSubmit={(e) => { e.preventDefault(); pw.mutate(); }}>
          <PasswordField label="Current password" value={cur} onChange={setCur} autoComplete="current-password" />
          <PasswordField label="New password" value={nw} onChange={setNw} autoComplete="new-password" hint />
          <Status m={pw} ok="Password changed. Your other devices were signed out." />
          <button className="btn primary" disabled={pw.isPending || !cur || !nw}>Change password</button>
        </form>
      </section>
      <section className="card acct-c">
        <div className="row between"><h2>Where you are signed in</h2>{(sessions.data?.sessions.length || 0) > 1 && <button className="btn" onClick={() => others.mutate()} disabled={others.isPending}>Sign out everywhere else</button>}</div>
        <ul className="sess">{sessions.data?.sessions.map((s) => (
          <li key={s.id}><span className="sess-i"><Icon name={/mobile|android|iphone/i.test(s.agent) ? "phone" : "table"} /></span>
            <span><b>{browser(s.agent)}</b>{s.current && <span className="chip gain" style={{ marginLeft: 8 }}>This device</span>}<small>Active {when(s.lastSeenAt)} · {s.ip || "unknown IP"}</small></span>
            {!s.current && <button className="btn" onClick={() => end.mutate(s.id)}>Sign out</button>}</li>))}</ul>
        {sessions.isError && <div className="formerr">{msg(sessions.error)}</div>}
      </section>
      <section className="card acct-c danger">
        <h2>Delete account</h2>
        <p className="muted">Removes your profile, watchlists, saved screens and preferences. This cannot be undone.</p>
        {!del ? <button className="btn" onClick={() => setDel(true)}>Delete my account…</button> : (
          <form className="form" onSubmit={(e) => { e.preventDefault(); remove.mutate(); }}>
            <PasswordField label="Confirm with your password" value={delPw} onChange={setDelPw} autoComplete="current-password" />
            <Status m={remove} />
            <div className="row"><button className="btn danger" disabled={remove.isPending || !delPw}>Delete forever</button><button type="button" className="btn" onClick={() => setDel(false)}>Keep my account</button></div>
          </form>
        )}
      </section>
    </>
  );
}
const browser = (ua: string) => { const os = /Windows/i.test(ua) ? "Windows" : /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iOS" : /Mac OS/i.test(ua) ? "macOS" : /Linux/i.test(ua) ? "Linux" : "Unknown device"; const b = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser"; return `${b} on ${os}`; };

export function Appearance() {
  const p = usePrefs();
  const { theme, toggleTheme } = useUI();
  return (
    <>
      <section className="card acct-c">
        <h2>Colour palette</h2>
        <p className="muted">Pick the look you like to read in. It applies across the whole site, and follows you when you sign in elsewhere.</p>
        <div className="pal-grid" role="radiogroup" aria-label="Colour palette">
          {PALETTE_IDS.map((id) => { const s = PALETTES[id]; return (
            <button key={id} role="radio" aria-checked={p.palette === id} className={"pal" + (p.palette === id ? " on" : "")} onClick={() => prefs.set({ palette: id })}>
              <span className="pal-sw" style={{ background: s.swatch[0] }}><i style={{ background: s.swatch[1] }} /><i style={{ background: s.swatch[2] }} /></span>
              <b>{s.label}</b><small>{s.blurb}</small>{p.palette === id && <span className="pal-ck"><Icon name="check" /></span>}
            </button>); })}
        </div>
      </section>
      <section className="card acct-c">
        <h2>Light or dark</h2>
        <div className="seg" role="group" aria-label="Theme">
          {(["light", "dark"] as const).map((t) => <button key={t} aria-pressed={theme === t} onClick={() => theme !== t && toggleTheme()}>{t === "light" ? "Light" : "Dark"}</button>)}
        </div>
        <h2 style={{ marginTop: 22 }}>Density</h2>
        <div className="seg" role="group" aria-label="Density">
          {(["comfortable", "compact"] as const).map((d) => <button key={d} aria-pressed={p.density === d} onClick={() => prefs.set({ density: d })}>{d === "comfortable" ? "Comfortable" : "Compact"}</button>)}
        </div>
        <h2 style={{ marginTop: 22 }}>Price alerts</h2>
        <label className="sw"><input type="checkbox" checked={p.alerts} onChange={(e) => prefs.set({ alerts: e.target.checked })} /><span aria-hidden="true" /><b>Email me when a watchlist stock crosses its target price</b></label>
        <p className="muted" style={{ marginTop: 6 }}>Set a target on any stock in your <Link to="/watchlist">watchlist</Link> (Bronze and Gold). You get one email when the price crosses it, at most once a day per stock.</p>
        <p className="muted" style={{ marginTop: 16 }}>Choose which widgets your dashboard shows, and in what order, from the <Link to="/dashboard?edit=1">dashboard</Link>.</p>
        <button className="btn" onClick={() => prefs.reset()}>Reset to the FinLit default</button>
      </section>
    </>
  );
}

function PlanTab() {
  const { plan, limits, refresh } = useAuth();
  const [params] = useSearchParams();
  const want = params.get("want");
  const [note, setNote] = useState("");
  const req = useMutation({ mutationFn: (p: "bronze" | "gold") => acct.requestPlan(p, note.trim() || undefined), onSuccess: () => refresh() });
  const rows: [Plan, string[]][] = [
    ["basic", ["Screener, comparison of 2 companies, glossary, latest quarter, financials, ratios, peers, charts"]],
    ["bronze", ["FinLit score and five-pillar scorecard", "Parameter history", "Watchlist: 3 lists, 30 stocks", "Model-based comparison tabs", "Data export"]],
    ["gold", ["Advanced scoring and full ratio history", "Technical analysis and segments", "Model-based screener filters", "Compare up to 4 companies", "Watchlist: up to 50 lists, 1,000 stocks"]],
  ];
  return (
    <section className="card acct-c">
      <h2>Your plan: {TIER[plan].n}</h2>
      <p className="muted">Pricing is announced at launch. Until then, ask for a plan and the FinLit team switches it on for your account and confirms by email.</p>
      <ul className="lim"><li>Watchlists <b>{limits.watchlist_lists}</b></li><li>Stocks in watchlists <b>{limits.watchlist_symbols}</b></li><li>Saved screens <b>{limits.screens}</b></li><li>Companies to compare <b>{limits.compare}</b></li></ul>
      <div className="pgrid2">
        {rows.map(([k, f]) => (
          <div key={k} className={"plan2" + (plan === k ? " cur" : "") + (want === k ? " want" : "")} style={{ "--tc": `var(${TIER[k].tc})` } as React.CSSProperties}>
            <b><Icon name={TIER[k].ic} />{TIER[k].n}</b>
            <ul>{f.map((x) => <li key={x}><Icon name="check" />{x}</li>)}</ul>
            {plan === k ? <span className="chip gold">Your plan</span> : k !== "basic" && RANK[k] > RANK[plan] ? <button className="btn" disabled={req.isPending || (req.isSuccess && req.variables === k)} onClick={() => req.mutate(k as "bronze" | "gold")}>{req.isSuccess && req.variables === k ? "Requested" : `Request ${TIER[k].n}`}</button> : null}
          </div>))}
      </div>
      <label className="form" style={{ display: "block", marginTop: 14 }}><span className="muted" style={{ fontSize: 13 }}>Anything we should know? (optional)</span><textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} rows={2} style={{ width: "100%" }} /></label>
      <Status m={req} ok="Request sent. We will confirm by email once your plan is switched on." />
    </section>
  );
}
