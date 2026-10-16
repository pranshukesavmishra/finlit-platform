import { PageArt } from "../components/PageArt";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { COMPANY } from "../content/site";
import { sendContact } from "../lib/siteApi";
import { useDocTitle } from "../lib/title";
import { Icon } from "../lib/icons";

export function Contact() {
  useDocTitle("Contact", "Contact the FinLit team about portfolio reviews, planning and research.");
  const [f, setF] = useState({ name: "", email: "", phone: "", subject: "", message: "" });
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({ mutationFn: sendContact, onError: (e: Error) => setErr(e.message) });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (f.name.trim().length < 2) return setErr("Please enter your name.");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(f.email)) return setErr("Enter a valid email address.");
    const d = f.phone.replace(/\D/g, ""); if (f.phone && (!/^\+?[\d\s\-()]+$/.test(f.phone) || d.length < 7 || d.length > 15)) return setErr("Enter a valid mobile number.");
    if (f.message.trim().length < 10) return setErr("Please write a few words (at least 10 characters).");
    setErr(null); m.mutate({ name: f.name.trim(), email: f.email.trim(), phone: f.phone.trim() || undefined, subject: f.subject.trim() || undefined, message: f.message.trim() });
  };
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="contact" /><div className="eyebrow">Contact</div><h1>Let's talk about your portfolio.</h1><p>Share what you are looking for and the FinLit team will follow up.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap two">
        <div className="card">
          {m.isSuccess ? <div className="done"><div className="done-ic"><Icon name="check" /></div><h3 style={{ font: "400 26px var(--serif)" }}>Message sent</h3><p className="muted">Thank you. We usually reply within one working day.</p></div> : (
            <form className="form" onSubmit={submit} noValidate>
              <div className="fgrid"><label>Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" required /></label><label>Email<input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" required /></label>
                <label>Mobile (optional)<input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} autoComplete="tel" /></label><label>Subject (optional)<input value={f.subject} maxLength={200} onChange={(e) => setF({ ...f, subject: e.target.value })} /></label></div>
              <label>Message<textarea rows={6} value={f.message} maxLength={5000} onChange={(e) => setF({ ...f, message: e.target.value })} required /></label>
              {err && <div className="formerr" role="alert">{err}</div>}
              <button className="btn primary lg" disabled={m.isPending}>{m.isPending ? "Sending…" : "Send message"}</button>
            </form>)}
        </div>
        <div><div className="feat" style={{ "--ac": "var(--gold)" } as React.CSSProperties}><h3>Reach us directly</h3><p style={{ margin: "10px 0" }}><a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a></p><p><a href={COMPANY.linkedin} target="_blank" rel="noopener noreferrer">FinLit on LinkedIn</a></p><p className="faint" style={{ fontSize: 12.5, marginTop: 14 }}>{COMPANY.disclaimer}</p></div></div>
      </div></section>
    </>
  );
}
