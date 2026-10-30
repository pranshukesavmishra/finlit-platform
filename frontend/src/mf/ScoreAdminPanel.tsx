// Admin only (Console, Data health): the state of the Mutual Fund Health Score run, what data is missing, and the internal look back by score quintile.
// Internal, descriptive, not a forecast: nothing here is published on the public site.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "../lib/api";
import type { AdminHealth, Calibration } from "../lib/mfScoreUp";
import "../styles/mfup.css";

const bin = (h: number[]) => { const m = Math.max(1, ...h); return h.map((n, i) => <i key={i} title={`${i * 10} to ${i * 10 + 10}: ${n}`} style={{ height: `${Math.max(2, (n / m) * 100)}%` }} />); };

export function ScoreAdminPanel() {
  const h = useQuery<AdminHealth, ApiError>({ queryKey: ["admin-mfscore"], queryFn: () => apiGet("/api/admin/mf-score/health"), retry: false, staleTime: 120_000 });
  const [m, setM] = useState(12);
  const c = useQuery<Calibration, ApiError>({ queryKey: ["admin-mfscore-cal", m], queryFn: () => apiGet(`/api/admin/mf-score/calibration?months_ago=${m}`), retry: false, staleTime: 300_000 });
  if (h.isError) return <section className="card acct-c"><h2>Fund Health Score</h2><div className="formerr">Could not load the score health view.</div></section>;
  const d = h.data;
  if (!d) return <section className="card acct-c"><h2>Fund Health Score</h2><div className="skeleton" style={{ height: 120 }} /></section>;
  const lr = d.lastRun;
  return (
    <section className="card acct-c mfu-admin" aria-label="Fund Health Score health">
      <h2>Fund Health Score</h2>
      <p className="muted">Last run: {lr ? <>{String(lr.at ?? "")} · {String(lr.status ?? "")} · {String(lr.written ?? 0)} written in {String(lr.seconds ?? "?")} s</> : "never recorded"}. {d.total.toLocaleString("en-IN")} funds stored; {d.history.rows.toLocaleString("en-IN")} weekly history rows{d.history.first ? ` from ${d.history.first}` : ""}.</p>
      <div className="hstat">{Object.entries(d.status).map(([k, n]) => <div key={k}><b>{n.toLocaleString("en-IN")}</b><span>{k.toLowerCase()}</span></div>)}</div>
      <h3 className="mf-h4">Score distribution by group</h3>
      <div className="mfu-dist">{Object.entries(d.distribution.byGroup).map(([g, hh]) => <div key={g}><span className="mfu-spark" aria-label={`${g}: ${hh.join(", ")} funds per ten-point band`}>{bin(hh)}</span><small>{g}</small></div>)}</div>
      <h3 className="mf-h4">Measures that used the group value, by group</h3>
      <div className="tw"><table className="mf-cmp"><thead><tr><th scope="col">Group</th><th scope="col" className="num">Funds</th><th scope="col" className="num">With a gap</th><th scope="col" className="num">Measures filled</th></tr></thead>
        <tbody>{d.filled.map((r) => <tr key={r.group}><th scope="row">{r.group}</th><td className="num">{r.funds}</td><td className="num">{r.withAGap}</td><td className="num">{r.measuresFilled}</td></tr>)}</tbody></table></div>
      <h3 className="mf-h4">Zero-handling counters (last run)</h3>
      <p className="muted">{Object.keys(d.zeroCounters).length ? Object.entries(d.zeroCounters).map(([k, n]) => `${k}: ${n}`).join(" · ") : "No counters recorded yet."}</p>
      <h3 className="mf-h4">Not rated, by reason</h3>
      <ul className="mfu-list">{d.notRated.length ? d.notRated.map((r) => <li key={r.reason}><b>{r.n}</b> {r.reason}</li>) : <li>None.</li>}</ul>
      <h3 className="mf-h4">Inputs most often missing</h3>
      <ul className="mfu-list">{d.topMissing.length ? d.topMissing.map((r) => <li key={r.id + r.why}><b>{r.n}</b> {r.label}: {r.whyText || "no reason stored"}</li>) : <li>None.</li>}</ul>
      <h3 className="mf-h4">Peer set sizes</h3>
      <div className="tw"><table className="mf-cmp"><thead><tr><th scope="col">Peer set</th>{d.peerSizes.buckets.map((b) => <th key={b} scope="col" className="num">{b}</th>)}</tr></thead>
        <tbody>{Object.entries(d.peerSizes.byKind).map(([k, hh]) => <tr key={k}><th scope="row">{k}</th>{hh.map((n, i) => <td className="num" key={i}>{n}</td>)}</tr>)}</tbody></table></div>
      <h3 className="mf-h4">Look back by score quintile <span className="chip ghost">Internal</span></h3>
      <p className="muted">{c.data?.label ?? "Internal, descriptive, not a forecast. Do not publish."}</p>
      <label>Score stored <select value={m} onChange={(e) => setM(Number(e.target.value))}>{[6, 12, 18, 24].map((x) => <option key={x} value={x}>{x} months ago</option>)}</select></label>
      {c.data && (c.data.quintiles.length ? (
        <div className="tw"><table className="mf-cmp"><thead><tr><th scope="col">Score group</th><th scope="col" className="num">Funds</th><th scope="col" className="num">Avg score</th><th scope="col" className="num">Avg later 1Y return %</th><th scope="col" className="num">Avg return rank (0 best)</th></tr></thead>
          <tbody>{c.data.quintiles.map((r) => <tr key={r.quintile}><th scope="row">{r.quintile === 5 ? "Highest fifth" : r.quintile === 1 ? "Lowest fifth" : `Fifth ${r.quintile}`}</th><td className="num">{r.funds}</td><td className="num">{r.avgScore}</td><td className="num">{r.avgLaterReturn}</td><td className="num">{r.avgReturnRank}</td></tr>)}</tbody></table></div>
      ) : <p className="faint" role="status">{c.data.note}</p>)}
      {c.data && <p className="faint mf-fine">{c.data.how}</p>}
    </section>
  );
}
