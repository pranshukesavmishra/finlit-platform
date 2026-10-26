import { useEffect, useState } from "react";
import { Icon } from "../lib/icons";
import { systemLoads, systemRestart, systemStatus, type SystemStatus } from "../lib/account";
import { loadsText, memoryText, uptimeText } from "../lib/systemStatus";

/** Admin-only header control: pause or resume the heavy data loads, restart the site, and a plain status. Fetches only while open. */
export function SystemControl() {
  const [open, setOpen] = useState(false);
  const [st, setSt] = useState<SystemStatus | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const load = () => systemStatus().then((s) => { setSt(s); setMsg(""); }).catch(() => setMsg("Could not read the status. Sign in with your authenticator code and try again."));
  useEffect(() => { if (open) { setConfirm(false); load(); } }, [open]);
  const toggle = async () => {
    if (!st || busy) return;
    setBusy(true);
    try { setSt(await systemLoads(!st.loadsEnabled)); setMsg(""); } catch { setMsg("The switch was not changed. Try again."); } finally { setBusy(false); }
  };
  const restart = async () => {
    setBusy(true);
    try { await systemRestart(); setConfirm(false); setMsg("Restarting. The site is back in about a minute."); } catch { setMsg("Could not restart the site."); } finally { setBusy(false); }
  };
  return (
    <div className="dd sys-dd" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button className="icon-btn" aria-haspopup="true" aria-expanded={open} aria-label="System controls" onClick={() => setOpen(!open)}><Icon name="lock" /></button>
      <div className={"ddm right sys-pop" + (open ? " open" : "")} role="dialog" aria-label="System controls">
        <b>System</b>
        {st && <>
          <label className="sys-row"><span>Heavy data loads</span>
            <input type="checkbox" role="switch" checked={st.loadsEnabled} disabled={busy} onChange={toggle} aria-label="Heavy data loads" /></label>
          <p>{loadsText(st)}</p>
          <p>{memoryText(st.memory)}</p>
          <p>Up for {uptimeText(st.uptimeSeconds)}. Last restart {new Date(st.startedAt).toLocaleString()}.</p>
        </>}
        {msg && <p role="status">{msg}</p>}
        {!confirm ? <button className="btn" disabled={busy} onClick={() => setConfirm(true)}>Restart site</button> : (
          <div className="sys-confirm" role="alertdialog" aria-label="Confirm restart"><p>Restart the whole site now? It is unavailable for about a minute.</p>
            <button className="btn primary" disabled={busy} onClick={restart}>Yes, restart</button> <button className="btn" onClick={() => setConfirm(false)}>Cancel</button></div>)}
      </div>
    </div>
  );
}
