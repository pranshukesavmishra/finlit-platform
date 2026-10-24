import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useFocusTrap } from "../lib/focusTrap";
import { useMutation } from "@tanstack/react-query";
import { SERVICES } from "../content/site";
import { sendEnquiry } from "../lib/siteApi";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";

const Ctx = createContext<(service?: string) => void>(() => {});
export const useEnquiry = () => useContext(Ctx);

const PHONE = /^\+?[\d\s\-()]+$/;

export function EnquiryProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [f, setF] = useState({ name: "", email: "", phone: "", message: "" });
  const [err, setErr] = useState<string | null>(null);
  const { toast } = useUI();
  const box = useRef<HTMLDivElement>(null);
  useFocusTrap(box, open);
  const show = useCallback((service?: string) => { setPicked(service ? [service] : []); setDone(false); setErr(null); setOpen(true); }, []);
  const m = useMutation({ mutationFn: sendEnquiry, onSuccess: () => { setDone(true); toast("Enquiry sent. The FinLit team will get back to you."); }, onError: (e: Error) => setErr(e.message) });

  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const digits = f.phone.replace(/\D/g, "");
    if (f.name.trim().length < 2) return setErr("Please enter your name.");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(f.email)) return setErr("Enter a valid email address.");
    if (!PHONE.test(f.phone) || digits.length < 7 || digits.length > 15) return setErr("Enter a valid mobile number.");
    if (!picked.length) return setErr("Choose at least one service.");
    setErr(null);
    m.mutate({ name: f.name.trim(), email: f.email.trim(), phone: f.phone.trim(), services: picked, message: f.message.trim() });
  }

  return (
    <Ctx.Provider value={show}>
      {children}
      {open && (
        <>
          <div className="scrim" onClick={() => setOpen(false)} />
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="enqTitle" ref={box}>
            <button className="modal-x" aria-label="Close" onClick={() => setOpen(false)}>×</button>
            {done ? (
              <div className="done"><div className="done-ic"><Icon name="check" /></div><h3 id="enqTitle">Thank you</h3>
                <p className="muted">Your enquiry is with the FinLit team. We usually reply within one working day.</p>
                <button className="btn primary" onClick={() => setOpen(false)}>Close</button></div>
            ) : (
              <form onSubmit={submit} noValidate>
                <div className="eyebrow">Enquiry</div>
                <h3 id="enqTitle">Tell us what you need</h3>
                <p className="muted" style={{ margin: "6px 0 16px" }}>Tell us a little about yourself and we will reply with the next steps.</p>
                <div className="fgrid">
                  <label>Name<input value={f.name} autoComplete="name" onChange={(e) => setF({ ...f, name: e.target.value })} required /></label>
                  <label>Email<input type="email" value={f.email} autoComplete="email" onChange={(e) => setF({ ...f, email: e.target.value })} required /></label>
                  <label className="span2">Mobile<input type="tel" value={f.phone} autoComplete="tel" placeholder="+91 …" onChange={(e) => setF({ ...f, phone: e.target.value })} required /></label>
                </div>
                <fieldset className="svc"><legend>Services</legend>
                  {SERVICES.map((s) => (
                    <label key={s.name} className={"opt" + (picked.includes(s.name) ? " on" : "")}>
                      <input type="checkbox" checked={picked.includes(s.name)} onChange={() => setPicked((p) => (p.includes(s.name) ? p.filter((x) => x !== s.name) : [...p, s.name]))} />{s.name}
                    </label>
                  ))}
                </fieldset>
                <label>Message (optional)<textarea rows={3} value={f.message} maxLength={5000} onChange={(e) => setF({ ...f, message: e.target.value })} /></label>
                {err && <div className="formerr" role="alert">{err}</div>}
                <button className="btn primary" style={{ width: "100%", marginTop: 14 }} disabled={m.isPending}>{m.isPending ? "Sending…" : "Send enquiry"}</button>
              </form>
            )}
          </div>
        </>
      )}
    </Ctx.Provider>
  );
}
