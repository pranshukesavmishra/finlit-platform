import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router";
import { sendContact } from "../lib/siteApi";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";

/** Account sign-in. Accounts (email code, Google, passkeys) are built in the next phase on the backend;
 *  until then this page collects early-access interest through the site's contact endpoint. */
export function Login() {
  useDocTitle("Sign in", "FinLit accounts: sign in with a one-time email code, Google or a passkey. No passwords.");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({ mutationFn: () => sendContact({ name: "Early access", email: email.trim(), subject: "Early access: FinLit accounts", message: "Please let me know when FinLit accounts (watchlists, plans, saved reports) open." }), onError: (e: Error) => setErr(e.message) });
  const submit = (e: React.FormEvent) => { e.preventDefault(); if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return setErr("Enter a valid email address."); setErr(null); m.mutate(); };
  return (
    <div className="login">
      <div className="aurora" style={{ opacity: 0.8 }} />
      <div className="wrap login-in">
        <div className="login-l">
          <Link to="/" className="lg-mark" aria-label="FinLit home" style={{ height: 64, marginBottom: 24 }} />
          <h1>Research you can <em>trust</em>,<br />an account you can too.</h1>
          <p className="lede-xl">Save watchlists, unlock the research score and download reports. No password to remember, and none for anyone to steal.</p>
          <ul className="trustl">
            <li><span className="fi"><Icon name="quality" /></span><div><b>No passwords stored</b><span>Google, a one-time email code, or your device's fingerprint or face.</span></div></li>
            <li><span className="fi"><Icon name="users" /></span><div><b>You control every device</b><span>See where you're signed in and sign out any device in one tap.</span></div></li>
            <li><span className="fi"><Icon name="wallet" /></span><div><b>Payments through Razorpay</b><span>Your card or UPI details never reach FinLit's servers.</span></div></li>
          </ul>
        </div>
        <div className="card login-card">
          {m.isSuccess ? (
            <div className="done"><div className="done-ic"><Icon name="check" /></div><h3 style={{ font: "400 26px var(--serif)" }}>You're on the list</h3><p className="muted">We'll email {email} the moment accounts open. Until then every stock report is free to read.</p><Link className="btn primary" to="/research">Explore research</Link></div>
          ) : (
            <form className="form" onSubmit={submit} noValidate>
              <div className="eyebrow">Accounts</div>
              <h2 style={{ font: "400 28px var(--serif)", margin: "6px 0 6px" }}>Accounts open soon</h2>
              <p className="muted" style={{ margin: "0 0 18px" }}>Leave your email and we'll tell you the moment you can sign in. Every stock report stays free to read meanwhile.</p>
              <label>Email address<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required /></label>
              {err && <div className="formerr" role="alert">{err}</div>}
              <button className="btn primary lg" style={{ width: "100%", marginTop: 8 }} disabled={m.isPending}>{m.isPending ? "Saving…" : "Notify me"}</button>
              <p className="faint" style={{ fontSize: 12.5, marginTop: 16 }}>By continuing you agree to our <Link to="/legal/terms">Terms</Link> and <Link to="/legal/privacy">Privacy Notice</Link>. Research here is for information only and is not investment advice.</p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
