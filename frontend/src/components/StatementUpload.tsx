import { useRef, useState } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { hasAdminSession } from "../lib/adminSession";
import { useAuth } from "../lib/auth";
import { asOfLabel, uploadStatement, validateStatement } from "../lib/portfolioView";
import type { PortfolioReport } from "../lib/siteApi";
import "../styles/f3.css";

/** Admin only: replace the published portfolio report with the latest broker statement. Everyone else gets nothing at all. */
export function StatementUpload({ current }: { current?: PortfolioReport }) {
  const { isAdmin } = useAuth();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<PortfolioReport | null>(null);
  if (!isAdmin) return null;
  const signedIn = hasAdminSession();
  const busy = pct !== null;
  const pick = (f: File | null) => { setDone(null); setFile(f); setErr(f ? validateStatement(f) : null); };
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const bad = validateStatement(file); if (bad || !file) return setErr(bad);
    setErr(null); setDone(null); setPct(0);
    try {
      const r = await uploadStatement(file, setPct);
      qc.setQueryData(["portfolio"], r); setDone(r); setFile(null); if (input.current) input.current.value = "";
    } catch (x) { setErr((x as Error).message); }
    finally { setPct(null); }
  };
  return (
    <section className="stup" aria-labelledby="stupT">
      <h2 id="stupT">Upload latest statement <span className="stup-tag">Admin only</span></h2>
      {current && <p className="stup-now">Showing the statement as of <b>{asOfLabel(current)}</b> ({current.profile.reportPeriod}), generated {new Date(current.generatedAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}.</p>}
      {!signedIn ? <p className="stup-note">The content tools are not open in this browser session. <Link to="/admin/login">Open the content tools</Link>, then come back to this page.</p> : (
        <form onSubmit={send} noValidate>
          <p className="stup-note">Upload the broker's realised P&amp;L statement as a PDF, up to 15 MB. It replaces the report everyone sees as soon as it is read.</p>
          <div className="stup-row">
            <label className="stup-file"><span className="sr-only">Realised P&amp;L statement (PDF)</span>
              <input ref={input} type="file" accept="application/pdf,.pdf" disabled={busy} onChange={(e) => pick(e.target.files?.[0] ?? null)} aria-describedby={err ? "stupErr" : undefined} /></label>
            <button className="btn primary" disabled={busy || !file}>{busy ? "Uploading…" : "Upload statement"}</button>
          </div>
          {busy && <div className="stup-bar" role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? 0}><i style={{ width: `${pct}%` }} /><span>{pct === 100 ? "Reading the statement…" : `${pct}%`}</span></div>}
          {err && <div id="stupErr" className="formerr" role="alert">{err}</div>}
          {done && <p className="stup-ok" role="status">Published. The report is now as of <b>{asOfLabel(done)}</b> and covers {done.summary.tradeCount} realised trades.</p>}
        </form>)}
    </section>
  );
}
