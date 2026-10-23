// A compact FII / DII card for the dashboard: the latest session, both streaks, the 30-session total, a 30-session mini bar chart and a link to
// the full page. Hides itself when there is nothing to show; DII is replaced by one honest line when no source publishes it.
import { Link } from "react-router";
import { dateIN } from "../lib/format";
import { useFlows, type Streak } from "../lib/flows";
import { ageLabel, diiState, inr } from "../lib/flowsMath";
import { MiniBars } from "./FlowsCharts";
import "../styles/flows.css";

const cls = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "gain" : "loss");
const arrow = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲ " : "▼ ");
const streakText = (s: Streak | null) => (!s || s.side === "flat" || !s.days ? "No streak" : `${s.days} day${s.days === 1 ? "" : "s"} ${s.side}`);

export function FlowsPanel({ sessions = 30, className = "" }: { sessions?: number; className?: string }) {
  const q = useFlows(), f = q.data;
  if (q.isLoading) return <section className={`flp ${className}`} aria-busy="true" aria-label="FII and DII flows"><div className="fl-skel"><i style={{ height: 150 }} /></div></section>;
  if (!f || !f.latest) return null;
  const l = f.latest, st = diiState(f), rows = f.days.slice(-sessions);
  return (
    <section className={`flp ${className}`} aria-labelledby="flpT">
      <div className="flp-h"><h2 id="flpT">FII / DII flows</h2><span>{dateIN(l.d)} · {ageLabel(l.d, f.today)}{l.mood ? ` · ${l.mood}` : ""}</span></div>
      <div className="flp-two">
        <div><span>FII / FPI net</span><b className={cls(l.fii.net)}>{arrow(l.fii.net)}{inr(l.fii.net)}</b><small>{streakText(f.streaks.fii)}</small></div>
        <div><span>DII net</span>{l.dii?.net != null ? <><b className={cls(l.dii.net)}>{arrow(l.dii.net)}{inr(l.dii.net)}</b><small>{streakText(f.streaks.dii)}</small></> : <><b>—</b><small>Not published to us</small></>}</div>
      </div>
      <div className="flp-meta">
        <span>Last {f.last30.days} sessions: FII <b className={cls(f.last30.fii)}>{inr(f.last30.fii)}</b>{f.last30.dii != null && <> · DII <b className={cls(f.last30.dii)}>{inr(f.last30.dii)}</b></>}</span>
      </div>
      <MiniBars rows={rows.map((d) => ({ d: d.d, v: d.fii.net }))} name="FII" />
      {st !== "none" && <MiniBars rows={rows.map((d) => ({ d: d.d, v: d.dii?.net ?? null }))} name="DII" />}
      <Link to="/fii-dii" className="flp-a">Full FII/DII data: charts, calendar and history →</Link>
    </section>
  );
}
