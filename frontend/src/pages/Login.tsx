import { useId, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { resendVerification, signIn, signUp } from "../lib/account";
import { useAuth } from "../lib/auth";
import { safeNext } from "../lib/safe";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { DEMO } from "../lib/demo";

const PW_RULES: [string, (p: string) => boolean][] = [["10 or more characters", (p) => p.length >= 10], ["Not a common password", (p) => !/^(password|12345|qwerty|letmein|welcome|admin|finlit)/i.test(p)]];

export function PasswordField({ label = "Password", value, onChange, autoComplete, hint }: { label?: string; value: string; onChange: (v: string) => void; autoComplete: string; hint?: boolean }) {
  const [show, setShow] = useState(false);
  const id = useId();
  return (
    <div className="fld">
      <label htmlFor={id}>{label}</label>
      <span className="pw">
        <input id={id} type={show ? "text" : "password"} autoComplete={autoComplete} value={value} onChange={(e) => onChange(e.target.value)} required maxLength={128} />
        <button type="button" className="pw-t" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}>{show ? "Hide" : "Show"}</button>
      </span>
      {hint && value && <span className="pw-h">{PW_RULES.map(([t, ok]) => <i key={t} className={ok(value) ? "ok" : ""}><Icon name="check" />{t}</i>)}</span>}
    </div>
  );
}

export function Login() {
  useDocTitle("Sign in", "Sign in to your FinLit account or create one free: saved watchlists, your plan, and your own dashboard.");
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "signup" ? "signup" : "signin";
  const next = safeNext(params.get("next"));
  const nav = useNavigate();
  const { refresh, user } = useAuth();
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [name, setName] = useState(""), [code, setCode] = useState("");
  const [terms, setTerms] = useState(false);
  const [needCode, setNeedCode] = useState(false);
  const [unverified, setUnverified] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [created, setCreated] = useState(false);  // account was confirmed at sign-up (test deployments without email)

  const explain = (e: unknown): string => {
    if (e instanceof ApiError) {
      if (e.status === 429) return e.body.retryAfter ? `Too many attempts. Please wait ${Math.ceil(e.body.retryAfter / 60)} min and try again.` : "Too many attempts. Please wait and try again.";
      return e.body.detail || "Something went wrong. Please try again.";
    }
    return "We could not reach FinLit. Check your connection and try again.";
  };
  const login = useMutation({
    mutationFn: () => signIn({ email: email.trim(), password, code: needCode ? code.trim() : undefined }),
    onSuccess: async (r) => { await refresh(); nav(r.mfaSetupRequired ? "/account/security?setup=1" : next, { replace: true }); },
    onError: (e) => {
      setUnverified(false);
      if (e instanceof ApiError && e.body.status === "mfa_required") { setNeedCode(true); setErr(null); return; }
      if (e instanceof ApiError && e.body.status === "email_not_verified") setUnverified(true);
      setErr(explain(e));
    },
  });
  const register = useMutation({
    mutationFn: () => signUp({ email: email.trim(), password, name: name.trim() || undefined, accept_terms: terms }),
    onSuccess: (r) => { setCreated((r as { status?: string } | undefined)?.status === "created"); setSent(email.trim()); },
    onError: (e) => setErr(explain(e)),
  });
  const resend = useMutation({ mutationFn: () => resendVerification(email.trim()), onSuccess: () => { setErr(null); setUnverified(false); setSent(email.trim()); } });
  const submit = (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim())) return setErr("Enter a valid email address.");
    if (mode === "signup") { if (!terms) return setErr("Please accept the Terms and Privacy Notice to continue."); register.mutate(); } else login.mutate();
  };
  const setMode = (m: "signin" | "signup") => { setErr(null); setNeedCode(false); setUnverified(false); const p = new URLSearchParams(params); if (m === "signup") p.set("mode", "signup"); else p.delete("mode"); setParams(p, { replace: true }); };
  const busy = login.isPending || register.isPending;

  if (DEMO) return <Navigate to="/dashboard" replace />;
  if (user && !sent) return <div className="login"><div className="wrap state"><h1 style={{ font: "400 30px var(--serif)" }}>You are signed in</h1><p className="muted">{user.email}</p><Link className="btn primary" to={next}>Continue</Link></div></div>;

  return (
    <div className="login">
      <div className="aurora" style={{ opacity: 0.8 }} />
      <div className="wrap login-in">
        <div className="login-l">
          <Link to="/" className="lg-mark" aria-label="FinLit home" style={{ height: 64, marginBottom: 24 }} />
          <h1>Your research, <em>your way</em>.</h1>
          <p className="lede-xl">A free account saves what you follow and keeps your plan, your colours and your dashboard exactly as you left them, on any device.</p>
          <ul className="trustl">
            <li><span className="fi"><Icon name="wallet" /></span><div><b>Watchlists that follow you</b><span>Lists, notes and price targets are saved to your account, not just this browser.</span></div></li>
            <li><span className="fi"><Icon name="quality" /></span><div><b>Your own dashboard</b><span>Choose the widgets and the colour palette. Change them any time.</span></div></li>
            <li><span className="fi"><Icon name="users" /></span><div><b>Protected sign-in</b><span>Strong password storage, sign-out of every device, and optional authenticator-app codes.</span></div></li>
          </ul>
        </div>
        <div className="card login-card">
          {sent ? (
            <div className="done"><div className="done-ic"><Icon name="check" /></div>
              {created ? (<>
                <h3 style={{ font: "400 26px var(--serif)" }}>Your account is ready</h3>
                <p className="muted">{sent} is confirmed. Sign in with the password you just chose.</p>
                <button className="btn primary" onClick={() => { setSent(null); setCreated(false); setPassword(""); setMode("signin"); }}>Sign in</button></>) : (<>
                <h3 style={{ font: "400 26px var(--serif)" }}>Check your email</h3>
                <p className="muted">If {sent} can be used, we have sent a link to confirm it. It works once and expires in 24 hours.</p>
                <button className="btn" onClick={() => { setSent(null); setMode("signin"); }}>Back to sign in</button></>)}</div>
          ) : (
            <form className="form" onSubmit={submit} noValidate>
              <div className="seg authseg" role="tablist" aria-label="Account">
                <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => setMode("signin")}>Sign in</button>
                <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => setMode("signup")}>Create account</button>
              </div>
              <h2 style={{ font: "400 28px var(--serif)", margin: "16px 0 6px" }}>{mode === "signup" ? "Create your free account" : needCode ? "Two-step check" : "Welcome back"}</h2>
              <p className="muted" style={{ margin: "0 0 18px" }}>{mode === "signup" ? "Free forever on the Basic plan. No card needed." : needCode ? "Enter the 6-digit code from your authenticator app." : "Sign in to open your watchlists, dashboard and plan."}</p>
              {mode === "signup" && <label>Name <span className="faint">(optional)</span><input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>}
              {!needCode && <>
                <label>Email address<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></label>
                <PasswordField value={password} onChange={setPassword} autoComplete={mode === "signup" ? "new-password" : "current-password"} hint={mode === "signup"} />
              </>}
              {needCode && <label>Authenticator code<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={8} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoFocus required /></label>}
              {mode === "signup" && <label className="chk"><input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} /><span>I agree to the <Link to="/legal/terms" target="_blank">Terms</Link> and <Link to="/legal/privacy" target="_blank">Privacy Notice</Link>. FinLit research is information, not investment advice.</span></label>}
              {err && <div className="formerr" role="alert">{err}{unverified && <> <button type="button" className="linkbtn" onClick={() => resend.mutate()} disabled={resend.isPending}>Send the link again</button></>}</div>}
              <button className="btn primary lg" style={{ width: "100%", marginTop: 12 }} disabled={busy}>{busy ? "One moment…" : mode === "signup" ? "Create account" : needCode ? "Verify and sign in" : "Sign in"}</button>
              {mode === "signin" && !needCode && <p style={{ margin: "14px 0 0", fontSize: 14 }}><Link to="/forgot-password">Forgot your password?</Link></p>}
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
