// MACRO & SECTOR OUTLOOK on every company page (PRD section 2): A backdrop bar, B sector impact, C indicator signals, D interpretation (+ history).
// Reads stored results only. Describes the sector's macroeconomic backdrop, never the company and never a recommendation.
import { useState } from "react";
import { Icon } from "../lib/icons";
import { dateIN } from "../lib/format";
import { SectionHead } from "./Sections";
import "../styles/macro-outlook.css";
import { PERIODS, GROUP_ICON, arrow, companyRows, driverText, indicatorsForReasons, insufficientText, pct, reasonsOf, shortName, signed, useCompanyMacro, useMacroHistory, useSectorImpact,
  type CompanyMacro, type Driver, type History, type Indicator, type Item, type Reason, type SectorRow, type Tone } from "../lib/macroOutlook";
import { ChartZoom } from "../components/ChartZoom";


export function Chip({ label, tone }: { label: string; tone: Tone }) { return <span className={"mo-chip " + tone}>{label}</span>; }
function Pill({ d }: { d: Driver }) { return <span className={"mo-pill " + (d.sign === "+" ? "pos" : "neg")} title={`${d.name}: ${d.valueText}. ${d.sign === "+" ? "Supports" : "Weighs on"} the score.`}><span aria-hidden="true">{driverText(d)}</span><span className="sr">{d.name}, {d.sign === "+" ? "supports" : "weighs on"} the score</span></span>; }
function Bar({ score, tone }: { score: number | null; tone: Tone }) {
  return <span className="mo-bar" role="img" aria-label={score == null ? "No score" : `Score ${Math.round(score)} out of 100, 50 is neutral`}><i className={tone} style={{ width: `${pct(score)}%` }} /><u title="50 = neutral" /></span>;
}
const when = (iso?: string | null) => (iso ? dateIN(iso) : "—");

function Meta({ c }: { c: CompanyMacro }) {
  return <p className="mo-meta">As of <b>{when(c.snapshotDate)}</b>{c.basis === "reconstructed" ? " (reconstructed)" : ""} · coverage <b>{c.coverage != null ? Math.round(c.coverage * 100) : "—"}%</b> · model v{c.modelVersion} · initial assumptions, not validated</p>;
}

/* A: the backdrop bar */
function Backdrop({ c }: { c: CompanyMacro }) {
  const ok = c.status === "ok";
  return (
    <div className="mo-bar-a" role="group" aria-label="Macro backdrop summary">
      <span className="mo-k">Macro backdrop</span>
      <Chip label={ok ? c.label! : "Insufficient Data"} tone={ok ? c.tone ?? "flat" : "none"} />
      <span className="mo-sector"><Icon name="layers" />{c.mapping?.sectorName}</span>
      <span className="mo-score"><b>{ok && c.score != null ? Math.round(c.score) : "—"}</b><small>/100</small><Bar score={ok ? c.score ?? null : null} tone={c.tone ?? "none"} /></span>
      <span className="mo-drivers">{ok ? (c.drivers?.length ? c.drivers.map((d) => <Pill key={d.code} d={d} />) : <span className="faint">No dominant driver</span>) : <span className="faint">{insufficientText(c)}</span>}</span>
    </div>
  );
}

/* B: sector impact: only the rows marked "This company" (its own sector, or each segment sector of a revenue-weighted company) */
export function SectorTable({ rows }: { rows: SectorRow[] }) {
  return (
    <div className="mo-panel">
      <div className="mo-h"><h3><Icon name="bars" />Sector impact</h3><span className="faint">{rows.length > 1 ? "50 is neutral · sorted by score" : "50 is neutral"}</span></div>
      <table className="mo-t"><thead><tr><th scope="col">Sector</th><th scope="col">Score <span className="faint">(line at 50)</span></th><th scope="col" className="num">Score</th><th scope="col">Sentiment</th><th scope="col">Top reasons</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.sector.code} className="me" aria-current="true">
            <th scope="row">{r.sector.name}<span className="mo-you">This company</span></th>
            <td data-l="Score"><Bar score={r.score} tone={r.tone} /></td>
            <td className="num" data-l="Score">{r.score == null ? "—" : Math.round(r.score)}</td>
            <td data-l="Sentiment"><Chip label={r.label} tone={r.tone} /></td>
            <td data-l="Reasons">{r.status === "ok" ? (r.drivers.length ? r.drivers.map((d) => <Pill key={d.code} d={d} />) : <span className="faint">No dominant driver</span>) : <span className="faint">{(r.reason?.split(";")[0].replace(/^missing critical: /, "missing ") ?? "Insufficient Data")}</span>}</td>
          </tr>))}</tbody></table>
    </div>
  );
}

/* C: indicator signals */
function SignalBar({ v }: { v: number | null }) {
  if (v == null) return <span className="mo-sig none">no signal</span>;
  return <span className="mo-sig" title={`Normalised signal ${signed(v)} (−1 low or falling, +1 high or rising)`}><i style={{ left: `${(v + 1) * 50}%` }} className={v > 0.05 ? "hi" : v < -0.05 ? "lo" : ""} /><em>{signed(v)}</em></span>;
}
function Tile({ i, why }: { i: Indicator; why: Reason }) {
  const bad = i.status === "Missing" || i.status === "Stale" || i.status === "Invalid";
  const d = why.driver;   // the reason in Sector impact this tile belongs to: its effect on the score is the one the "Top reasons" pill shows
  return (
    <li className={"mo-tile" + (bad ? " bad" : "")} data-reason={i.code}>
      <div className="mo-tn"><b>{i.name}</b>{d && Math.abs(d.contribution) > 0 && <span className={"mo-eff " + (d.contribution > 0 ? "pos" : "neg")} title={`Top reason in Sector impact${why.sector ? ` (${why.sector})` : ""}: ${d.contribution > 0 ? "supports" : "weighs on"} the score`}>{d.contribution > 0 ? "supports" : "weighs"} {signed(d.contribution)}</span>}</div>
      {bad ? <p className="mo-miss"><Icon name="alert" />{i.status}: {i.detail || "no reading"}</p> : (
        <>
          <div className="mo-val"><b>{i.valueText}</b>{i.direction !== "none" && <span className={"mo-ch " + i.direction}>{arrow(i.direction)} <small>vs {i.prevText}</small></span>}</div>
          <SignalBar v={i.signal} />
        </>)}
      <p className="mo-src">{i.observationDate ? `${dateIN(i.observationDate)} · ` : ""}{i.source}{i.status === "Revised" ? " · revised" : ""}</p>
    </li>);
}
/** Only the indicators behind the reasons Sector impact gives, each under its group and tied to its reason. */
function Indicators({ c, reasons }: { c: CompanyMacro; reasons: Reason[] }) {
  const tiles = indicatorsForReasons(c.indicators, reasons);
  return (
    <div className="mo-panel">
      <div className="mo-h"><h3><Icon name="activity" />Indicator signals</h3><span className="faint">signal: −1 low or falling, +1 high or rising</span></div>
      {tiles.length > 0 && <p className="mo-why">Only the indicators behind the reasons above: {tiles.map((t) => shortName(t.indicator.code, t.indicator.name)).join(", ")}.</p>}
      {tiles.length === 0 && <p className="faint">{c.status === "ok" ? "Sector impact names no dominant driver for this sector right now, so there is no indicator to show." : "Sector impact shows no reading to explain right now."}</p>}
      {(c.groups ?? []).map((g) => { const t = tiles.filter((x) => x.indicator.group === g.code); return t.length > 0 && (
        <section key={g.code} className="mo-grp" aria-label={g.name}><h4><Icon name={GROUP_ICON[g.code] ?? "info"} />{g.name}</h4><ul>{t.map((x) => <Tile key={x.indicator.code} i={x.indicator} why={x.reason} />)}</ul></section>); })}
    </div>);
}

/* D: interpretation */
function List({ title, icon, tone, items, empty }: { title: string; icon: string; tone: string; items: Item[]; empty: string }) {
  return (
    <div className={"mo-col " + tone}><h4><Icon name={icon} />{title}</h4>
      {items.length ? <ul>{items.map((x) => <li key={x.code}><b>{shortName(x.code, x.name)}</b>{x.valueText && <span>{x.valueText}</span>}{x.contribution != null && <em>{signed(x.contribution)}</em>}{x.why && <span className="faint">{x.why}</span>}</li>)}</ul> : <p className="faint">{empty}</p>}
    </div>);
}
function Interpretation({ c }: { c: CompanyMacro }) {
  const e = c.explanation ?? {};
  return (
    <div className="mo-panel">
      <div className="mo-h"><h3><Icon name="notes" />Sector interpretation</h3></div>
      {e.headline && <p className="mo-lead">{e.headline}</p>}
      <div className="mo-cols">
        <List title="Supporting" icon="growth" tone="pos" items={e.supporting ?? []} empty="None at present" />
        <List title="Weighing" icon="alert" tone="neg" items={e.adverse ?? []} empty="None at present" />
        <List title="Monitor" icon="search" tone="mon" items={e.monitor ?? []} empty="Nothing flagged" />
      </div>
    </div>);
}

/* history */
export function Chart({ h }: { h: History }) {
  const pts = h.points;
  const W = 520, H = 170, L = 30, R = 10, T = 10, B = 22;
  const x = (i: number) => L + (pts.length < 2 ? (W - L - R) / 2 : (i / (pts.length - 1)) * (W - L - R));
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const valid = pts.map((p, i) => ({ p, i })).filter((q) => q.p.score != null);
  const path = valid.map((q, k) => `${k ? "L" : "M"}${x(q.i).toFixed(1)},${y(q.p.score!).toFixed(1)}`).join(" ");
  const last = valid[valid.length - 1];
  const label = valid.length ? `Score history, ${h.period}: ${when(pts[0].date)} to ${when(pts[pts.length - 1].date)}, latest ${Math.round(last.p.score!)} out of 100; 50 is neutral.` : "No score history yet.";
  return (
    <svg className="mo-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {[0, 25, 50, 75, 100].map((g) => <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} className={g === 50 ? "mid" : "grid"} /><text x={L - 5} y={y(g) + 3} textAnchor="end">{g}</text></g>)}
      <text x={W - R} y={y(50) - 4} textAnchor="end" className="midt">50 neutral</text>
      {path && <path d={path} className="ln" />}
      {valid.map((q) => <circle key={q.i} cx={x(q.i)} cy={y(q.p.score!)} r={q === last ? 4 : 2.2} className={q.p.basis === "reconstructed" ? "rc" : "lv"}><title>{`${when(q.p.date)}: ${Math.round(q.p.score!)} (${q.p.label}${q.p.basis === "reconstructed" ? ", reconstructed" : ""})`}</title></circle>)}
      {pts.length > 0 && <><text x={L} y={H - 6} textAnchor="start">{dateIN(pts[0].date, { month: "short", year: "2-digit" })}</text><text x={W - R} y={H - 6} textAnchor="end">{dateIN(pts[pts.length - 1].date, { month: "short", year: "2-digit" })}</text></>}
    </svg>);
}
function HistoryPanel({ c }: { c: CompanyMacro }) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("6M");
  const code = c.mapping?.sector ?? "";
  const q = useMacroHistory(code, period, c.mapping?.basis === "primary");
  const d = c.deltas ?? {};
  return (
    <div className="mo-panel">
      <ChartZoom label={"Macro score history"} className="cz-r">
      <div className="mo-h"><h3><Icon name="line" />Score history</h3>
        <div className="mo-seg" role="group" aria-label="Period">{PERIODS.map((p) => <button key={p} type="button" aria-pressed={period === p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p}</button>)}</div></div>
      {c.mapping?.basis !== "primary" ? <p className="faint">History is shown per sector; this company is weighted across several sectors.</p> : q.data && q.data.points.length ? <Chart h={q.data} /> : <p className="faint">{q.isLoading ? "Loading…" : "No history yet."}</p>}
      <div className="mo-delta">{["1M", "3M", "6M", "1Y"].map((k) => <span key={k} className={d[k] ? (d[k]!.change > 0 ? "pos" : d[k]!.change < 0 ? "neg" : "") : ""}>{k} <b>{d[k] ? signed(d[k]!.change, 1) : "—"}</b></span>)}</div>
      {q.data?.points.some((p) => p.basis === "reconstructed") && <p className="mo-foot"><span className="mo-dot rcd" /> reconstructed from stored data; <span className="mo-dot lv" /> calculated on the day.</p>}
      </ChartZoom>
    </div>);
}

export function MacroOutlookSection({ symbol }: { symbol: string }) {
  const q = useCompanyMacro(symbol);
  const c = q.data;
  const showImpact = !!c && (c.status === "ok" || c.status === "insufficient_data");
  const imp = useSectorImpact(showImpact && c?.mapping?.basis === "revenue_weighted");   // the full sector table is read only for a company that spans several sectors

  const head = <SectionHead id="macro" no="Macro" icon="globe" title="MACRO & SECTOR OUTLOOK" sub="How the economy is moving for this company's sector." color="--p-growth" />;
  let body: React.ReactNode;
  if (q.isLoading) body = <div className="mo-skel" aria-busy="true">Loading the macro outlook…</div>;
  else if (q.isError || !c) body = <p className="mo-note" role="status"><Icon name="alert" />The macro outlook is unavailable right now ({q.error?.status ?? "no answer"}). It reads stored results only; please try again shortly.</p>;
  else if (c.status === "not_mapped" || c.status === "pending") body = <p className="mo-note" role="status"><Icon name="info" />Macro outlook not available for this company: {c.reason ?? "its sector has not been assigned yet."}</p>;
  else {
    const rows = companyRows(c, imp.data?.sectors), reasons = reasonsOf(rows, c);
    body = (
      <>
        {c.stale.isStale && <p className="mo-stale" role="alert"><Icon name="alert" /><span><b>Stale data.</b> {c.stale.message}</span></p>}
        <Backdrop c={c} />
        <Meta c={c} />
        {c.mapping && <p className="mo-map"><Icon name="layers" />{c.mapping.note} {c.segments && <span>{c.segments.map((s) => `${s.name} ${Math.round(s.weight * 100)}%`).join(" · ")}</span>}</p>}
        {c.status === "insufficient_data" && <p className="mo-note" role="status"><Icon name="info" />{insufficientText(c)}. No score is shown rather than a guess.</p>}
        {rows.length > 0 && <SectorTable rows={rows} />}
        <Indicators c={c} reasons={reasons} />
        <div className="mo-two"><Interpretation c={c} /><HistoryPanel c={c} /></div>
        <p className="mo-disc">{c.disclaimer}</p>
      </>);
  }
  return <section className="block mo" aria-label="Macro and sector outlook" style={{ "--sc": "var(--p-growth)" } as React.CSSProperties}>{head}{body}</section>;
}
