// Console > Macro outlook: data health, model version and settings, sensitivity matrix, company mapping, runs and the audit trail. Every write creates a new
// model version on the server (role, Origin and CSRF checked there); this page only collects the change and a reason.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend } from "../../lib/api";

type Health = { indicator_code: string; name: string; source_name: string; frequency: string; value: number | null; unit: string; observation_date: string | null; publication_date: string | null; pub_date_basis: string | null; status: string; detail: string | null; rows: number; invalid: number; revised: number };
type Overview = { config: { version: number; k: number; signalScale: number; minCoverage: number; staleAfterHours: number; note: string }; health: Health[]; versions: { model_version: number; active: boolean; k: number; min_coverage: number; change_note: string; created_by: string; effective_from: string }[];
  runs: { id: number; started_at: string; status: string; trigger: string; error: string | null }[]; counts: { mapped: number; unmapped: number; snapshots: number }; stale: { isStale: boolean; message: string | null } };
type Sens = { sector_code: string; sector: string; indicator_code: string; coefficient: number; weight: number; critical: boolean };
type Audit = { events: { id: number; at: string; actor: string; action: string; entity_key: string; old_value: unknown; new_value: unknown; model_version: number | null; note: string | null }[] };
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");
const ts = (s: string) => new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const short = (v: unknown) => (v == null ? "—" : JSON.stringify(v).slice(0, 70));

export function MacroAdmin() {
  const qc = useQueryClient();
  const ov = useQuery({ queryKey: ["macro-admin"], queryFn: () => apiGet<Overview>("/api/admin/macro/overview"), retry: false });
  const [sector, setSector] = useState("real_estate");
  const sens = useQuery({ queryKey: ["macro-admin-sens"], queryFn: () => apiGet<{ version: number; rows: Sens[] }>("/api/admin/macro/sensitivities"), retry: false });
  const audit = useQuery({ queryKey: ["macro-admin-audit"], queryFn: () => apiGet<Audit>("/api/admin/macro/audit?limit=30"), retry: false });
  const [note, setNote] = useState(""), [edits, setEdits] = useState<Record<string, Partial<Sens>>>({}), [cfg, setCfg] = useState<{ k?: string; signal_scale?: string; min_coverage?: string }>({});
  const [sym, setSym] = useState(""), [target, setTarget] = useState("");
  const done = { onSuccess: () => { setEdits({}); setCfg({}); setNote(""); qc.invalidateQueries({ queryKey: ["macro-admin"] }); qc.invalidateQueries({ queryKey: ["macro-admin-sens"] }); qc.invalidateQueries({ queryKey: ["macro-admin-audit"] }); } };
  const save = useMutation({ mutationFn: () => apiSend("POST", "/api/admin/macro/sector-sensitivity", { note, changes: Object.entries(edits).map(([k, v]) => { const [s, i] = k.split("/"); return { sector: s, indicator: i, ...v }; }) }), ...done });
  const conf = useMutation({ mutationFn: () => apiSend("POST", "/api/admin/macro/config", { note, ...Object.fromEntries(Object.entries(cfg).filter(([, v]) => v !== "" && v != null).map(([k, v]) => [k, Number(v)])) }), ...done });
  const recalc = useMutation({ mutationFn: () => apiSend("POST", "/api/admin/macro/recalculate"), ...done });
  const map = useMutation({ mutationFn: () => apiSend("POST", "/api/admin/macro/mapping", { symbol: sym, sector: target || null, note: note || "set in the Console" }), ...done });
  if (ov.isError) return <div className="formerr">{msg(ov.error)}</div>;
  if (!ov.data) return <div className="skeleton" style={{ height: 160 }} />;
  const o = ov.data, rows = (sens.data?.rows ?? []).filter((r) => r.sector_code === sector), sectors = [...new Map((sens.data?.rows ?? []).map((r) => [r.sector_code, r.sector])).entries()];
  const err = save.error || conf.error || recalc.error || map.error;
  return (
    <>
      <section className="card acct-c"><h2>Macro outlook: model v{o.config.version}</h2>
        <p className="muted">K {o.config.k} · signal scale {o.config.signalScale} · minimum coverage {Math.round(o.config.minCoverage * 100)}% · {o.counts.mapped} companies mapped, {o.counts.unmapped} with a stated reason · {o.counts.snapshots} snapshots. Initial assumptions, not validated. {o.stale.isStale ? <b>Stale: {o.stale.message}</b> : null}</p>
        <div className="row-gap"><button className="btn" disabled={recalc.isPending} onClick={() => recalc.mutate()}>{recalc.isPending ? "Recalculating…" : "Recalculate now"}</button>{recalc.isSuccess && <span className="muted">Done.</span>}</div>
        {err && <div className="formerr" role="alert">{msg(err)}</div>}
        <label className="fld"><span>Reason for the change (kept in the audit trail)</span><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder="e.g. calibration trial" /></label>
      </section>
      <section className="card acct-c"><h2>Data health</h2>
        <div className="tw"><table className="qtt"><thead><tr><th>Indicator</th><th>Status</th><th>Latest</th><th>Observed</th><th>Published (basis)</th><th>Source</th><th>Rows / invalid / revised</th></tr></thead>
          <tbody>{o.health.map((h) => <tr key={h.indicator_code}><td>{h.name}</td><td><b>{h.status}</b>{h.detail && <div className="muted">{h.detail}</div>}</td><td>{h.value ?? "—"} {h.value != null ? h.unit : ""}</td><td>{h.observation_date ?? "—"}</td><td>{h.publication_date ?? "—"} <span className="muted">{h.pub_date_basis?.replace(/_/g, " ")}</span></td><td>{h.source_name}</td><td>{h.rows} / {h.invalid} / {h.revised}</td></tr>)}</tbody></table></div></section>
      <section className="card acct-c"><h2>Model settings</h2>
        <div className="row-gap">{([["k", "K"], ["signal_scale", "Signal scale"], ["min_coverage", "Min coverage (0-1)"]] as const).map(([k, l]) => <label key={k} className="fld"><span>{l}</span><input inputMode="decimal" value={cfg[k] ?? ""} placeholder={String({ k: o.config.k, signal_scale: o.config.signalScale, min_coverage: o.config.minCoverage }[k])} onChange={(e) => setCfg({ ...cfg, [k]: e.target.value })} /></label>)}
          <button className="btn" disabled={conf.isPending || note.length < 3 || !Object.values(cfg).some(Boolean)} onClick={() => conf.mutate()}>Save as a new version</button></div></section>
      <section className="card acct-c"><h2>Sensitivities</h2>
        <label className="fld"><span>Sector</span><select value={sector} onChange={(e) => setSector(e.target.value)}>{sectors.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></label>
        <div className="tw"><table className="qtt"><thead><tr><th>Indicator</th><th>Coefficient (−1 to 1)</th><th>Weight</th><th>Critical</th></tr></thead>
          <tbody>{rows.map((r) => { const k = `${r.sector_code}/${r.indicator_code}`, e = edits[k] ?? {}; const set = (p: Partial<Sens>) => setEdits({ ...edits, [k]: { ...e, ...p } });
            return <tr key={k}><td>{r.indicator_code}</td><td><input aria-label={`${r.indicator_code} coefficient`} type="number" step="0.25" min="-1" max="1" value={e.coefficient ?? r.coefficient} onChange={(x) => set({ coefficient: Number(x.target.value) })} /></td>
              <td><input aria-label={`${r.indicator_code} weight`} type="number" step="0.5" min="0.5" value={e.weight ?? r.weight} onChange={(x) => set({ weight: Number(x.target.value) })} /></td><td><input aria-label={`${r.indicator_code} critical`} type="checkbox" checked={e.critical ?? r.critical} onChange={(x) => set({ critical: x.target.checked })} /></td></tr>; })}</tbody></table></div>
        <button className="btn" disabled={save.isPending || note.length < 3 || !Object.keys(edits).length} onClick={() => save.mutate()}>Save {Object.keys(edits).length || ""} change(s) as a new version</button></section>
      <section className="card acct-c"><h2>Company mapping</h2>
        <div className="row-gap"><label className="fld"><span>Symbol</span><input value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())} maxLength={24} /></label>
          <label className="fld"><span>Sector</span><select value={target} onChange={(e) => setTarget(e.target.value)}><option value="">Back to the label rules</option>{sectors.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></label>
          <button className="btn" disabled={map.isPending || !sym} onClick={() => map.mutate()}>Save mapping</button></div></section>
      <section className="card acct-c"><h2>Versions and runs</h2>
        <div className="tw"><table className="qtt"><thead><tr><th>Version</th><th>K</th><th>Coverage</th><th>Change</th><th>By</th><th>Active</th></tr></thead>
          <tbody>{o.versions.map((v) => <tr key={v.model_version}><td>v{v.model_version}</td><td>{v.k}</td><td>{Math.round(v.min_coverage * 100)}%</td><td>{v.change_note}</td><td>{v.created_by}</td><td>{v.active ? "yes" : <button className="btn" onClick={() => apiSend("POST", "/api/admin/macro/activate-version", { version: v.model_version, note: note || "rollback from the Console" }).then(() => qc.invalidateQueries())}>Activate</button>}</td></tr>)}</tbody></table></div>
        <p className="muted">{o.runs.slice(0, 5).map((r) => `${ts(r.started_at)} ${r.trigger} ${r.status}${r.error ? " (" + r.error + ")" : ""}`).join(" · ")}</p></section>
      <section className="card acct-c"><h2>Audit trail</h2>
        <div className="tw"><table className="qtt"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Item</th><th>Old</th><th>New</th></tr></thead>
          <tbody>{audit.data?.events.map((e) => <tr key={e.id}><td>{ts(e.at)}</td><td>{e.actor}</td><td>{e.action.replace(/_/g, " ")} v{e.model_version ?? "—"}</td><td className="mono">{e.entity_key}</td><td className="mono">{short(e.old_value)}</td><td className="mono">{short(e.new_value)}</td></tr>)}</tbody></table></div></section>
    </>
  );
}
