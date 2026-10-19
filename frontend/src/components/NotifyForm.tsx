import { useState } from "react";
import { apiSend, ApiError } from "../lib/api";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";

/** "Tell me when it launches": one email box. The address is stored on our server (never shown to anyone else). */
export function NotifyForm({ source = "home", label = "Email address", button = "Notify me" }: { source?: string; label?: string; button?: string }) {
  const [email, setEmail] = useState(""), [trap, setTrap] = useState(""), [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle"), [msg, setMsg] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) { setState("error"); setMsg("Please enter a valid email address."); return; }
    setState("busy");
    try { if (!DEMO) await apiSend("POST", "/api/notify", { email: email.trim(), source, website: trap }); setState("done"); setEmail(""); }
    catch (er) { setState("error"); setMsg(er instanceof ApiError && er.status === 429 ? "Too many tries from this network. Please try again in a little while." : er instanceof ApiError && er.status === 422 ? "Please enter a valid email address." : "We could not save that just now. Please try again."); }
  }
  if (state === "done") return <p className="nf-done" role="status"><Icon name="check" /> Thank you. We will email you when these go live.</p>;
  return (
    <form className="nf" onSubmit={submit} noValidate>
      <label className="sr" htmlFor={`nf-${source}`}>{label}</label>
      <input id={`nf-${source}`} type="email" inputMode="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(e) => { setEmail(e.target.value); if (state === "error") setState("idle"); }} maxLength={254} aria-invalid={state === "error"} aria-describedby={state === "error" ? `nf-e-${source}` : undefined} />
      <input className="nf-trap" aria-label="Leave this field empty" tabIndex={-1} autoComplete="off" aria-hidden="true" value={trap} onChange={(e) => setTrap(e.target.value)} name="website" />
      <button className="btn primary" disabled={state === "busy"}>{state === "busy" ? "Saving…" : button}<Icon name="arrow" /></button>
      {state === "error" && <p id={`nf-e-${source}`} className="nf-err" role="alert">{msg}</p>}
    </form>
  );
}
