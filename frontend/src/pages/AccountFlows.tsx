import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { forgotPassword, resetPassword, verifyEmail } from "../lib/account";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { PasswordField } from "./Login";

const msg = (e: unknown) => e instanceof ApiError ? (e.status === 429 ? "Too many attempts. Please wait a little and try again." : e.body.detail || "Something went wrong.") : "We could not reach FinLit. Check your connection and try again.";

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="login">
      <div className="aurora" style={{ opacity: 0.8 }} />
      <div className="wrap" style={{ display: "grid", placeItems: "center" }}>
        <div className="card login-card" style={{ width: "min(480px, 100%)" }}>
          <Link to="/" className="lg-mark" aria-label="FinLit home" style={{ height: 48, marginBottom: 14 }} />
          <h1 style={{ font: "400 28px var(--serif)", margin: "0 0 10px" }}>{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}

export function VerifyEmail() {
  useDocTitle("Confirm your email", "Confirm your email address to finish creating your FinLit account.");
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const fired = useRef(false);
  const m = useMutation({ mutationFn: () => verifyEmail(token) });
  useEffect(() => { if (token && !fired.current) { fired.current = true; m.mutate(); } }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Shell title={m.isSuccess ? "Email confirmed" : m.isError || !token ? "This link did not work" : "Confirming…"}>
      {m.isSuccess && <><p className="muted">Your account is ready. Sign in to continue.</p><Link className="btn primary" to="/login">Sign in <Icon name="arrow" /></Link></>}
      {(m.isError || !token) && <><p className="muted">{token ? msg(m.error) : "The link is incomplete."} Links work once and expire after 24 hours. Sign in and we will send a new one.</p><Link className="btn" to="/login">Go to sign in</Link></>}
      {m.isPending && <p className="muted" role="status">One moment…</p>}
    </Shell>
  );
}

export function ForgotPassword() {
  useDocTitle("Reset your password", "Reset your FinLit password by email.");
  const [email, setEmail] = useState("");
  const m = useMutation({ mutationFn: () => forgotPassword(email.trim()) });
  return (
    <Shell title="Reset your password">
      {m.isSuccess ? <><p className="muted">If an account exists for {email}, we have sent a reset link. It works once and expires in 1 hour.</p><Link className="btn" to="/login">Back to sign in</Link></> : (
        <form className="form" onSubmit={(e) => { e.preventDefault(); if (email.trim()) m.mutate(); }}>
          <p className="muted" style={{ margin: "0 0 14px" }}>Enter your email and we will send you a link to choose a new password.</p>
          <label>Email address<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          {m.isError && <div className="formerr" role="alert">{msg(m.error)}</div>}
          <button className="btn primary lg" style={{ width: "100%" }} disabled={m.isPending}>{m.isPending ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
    </Shell>
  );
}

export function ResetPassword() {
  useDocTitle("Choose a new password", "Choose a new FinLit password.");
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [pw, setPw] = useState(""), [again, setAgain] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const nav = useNavigate();
  const m = useMutation({ mutationFn: () => resetPassword(token, pw), onSuccess: () => setTimeout(() => nav("/login", { replace: true }), 1800) });
  if (!token) return <Shell title="This link did not work"><p className="muted">The reset link is incomplete. Request a new one.</p><Link className="btn" to="/forgot-password">Request a new link</Link></Shell>;
  return (
    <Shell title={m.isSuccess ? "Password changed" : "Choose a new password"}>
      {m.isSuccess ? <p className="muted">All devices were signed out. Taking you to sign in…</p> : (
        <form className="form" onSubmit={(e) => { e.preventDefault(); if (pw !== again) return setLocal("The two passwords do not match."); setLocal(null); m.mutate(); }}>
          <PasswordField label="New password" value={pw} onChange={setPw} autoComplete="new-password" hint />
          <PasswordField label="Repeat new password" value={again} onChange={setAgain} autoComplete="new-password" />
          {(local || m.isError) && <div className="formerr" role="alert">{local || msg(m.error)}</div>}
          <button className="btn primary lg" style={{ width: "100%" }} disabled={m.isPending}>{m.isPending ? "Saving…" : "Change password"}</button>
        </form>
      )}
    </Shell>
  );
}
