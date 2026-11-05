import { useState } from "react";
import { CHARTED, WINDOWS, at, chartFor, chartLabel, chartNote, csvText, fmt2, groupsOf, NAME, pc, signedPts, windowIndexes, type ChartModel, type OwnSeries } from "../../lib/ownView";

function download(name: string, text: string) {
  try {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch { /* the browser refused the download: nothing else to do */ }
}

/** One small chart: the line is an SVG path only; the share now, the start, the change, the axis numbers and the months are page text. */
function Panel({ m }: { m: ChartModel }) {
  const [hi, setHi] = useState<number | null>(null);
  const n = m.points.length, hp = hi == null ? null : m.points[hi];
  const half = 50 / Math.max(n - 1, 1);
  const move = (e: React.KeyboardEvent) => {
    const to = e.key === "ArrowLeft" ? (hi ?? n) - 1 : e.key === "ArrowRight" ? (hi ?? -1) + 1 : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : e.key === "Escape" ? null : undefined;
    if (to === undefined) return;
    e.preventDefault();
    setHi(to == null ? null : Math.max(0, Math.min(n - 1, to)));
  };
  return (
    <figure className="ow-panel" data-group={m.key}>
      <div className="ow-pt"><span className="ow-nm"><span className="ow-dot" style={{ background: m.color }} aria-hidden="true" />{m.name}</span><span className="ow-badge">{signedPts(m.change ?? 0)}</span></div>
      <div className="ow-now"><b>{pc(m.last?.value)}</b><span className="ow-small ow-muted">now, from {pc(m.first?.value)} in {m.first?.period}</span></div>
      <div className="ow-plot" tabIndex={0} role="group" aria-label={`${chartLabel(m)}. Use the arrow keys to read each filing.`} onKeyDown={move} onBlur={() => setHi(null)} onMouseLeave={() => setHi(null)}>
        {m.ticks.map((t) => <span key={t.value} className="ow-gridline" style={{ top: `${t.top.toFixed(2)}%` }}><span className="ow-tick">{t.value}%</span></span>)}
        <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true"><path d={m.path} fill="none" stroke={m.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" /></svg>
        {m.first && <span className="ow-start" data-dot="start" style={{ top: `${m.yOf(m.first.value as number).toFixed(2)}%`, left: `${m.xOf(m.points.indexOf(m.first)).toFixed(2)}%`, borderColor: m.color }} />}
        {m.last && <span className="ow-end" data-dot="end" style={{ top: `${m.yOf(m.last.value as number).toFixed(2)}%`, left: `${m.xOf(m.points.indexOf(m.last)).toFixed(2)}%`, background: m.color }} />}
        {hp && hp.value != null && (
          <>
            <span className="ow-vline" style={{ left: `${m.xOf(hi!).toFixed(2)}%` }} />
            <span className="ow-hdot" style={{ left: `${m.xOf(hi!).toFixed(2)}%`, top: `${m.yOf(hp.value).toFixed(2)}%`, background: m.color }} />
            <span className="ow-tip" role="status" style={{ left: `${Math.min(88, Math.max(12, m.xOf(hi!))).toFixed(2)}%`, top: `${m.yOf(hp.value).toFixed(2)}%` }}>{hp.period}: {hp.value.toFixed(2)}%</span>
          </>
        )}
        <div className="ow-hit" style={{ left: `${(-half).toFixed(2)}%`, width: `${(100 + 2 * half).toFixed(2)}%` }}>
          {m.points.map((p, k) => <span key={p.i} data-hi={k} onMouseEnter={() => setHi(k)} onPointerDown={() => setHi(k)} />)}
        </div>
        <span className="ow-xl" style={{ left: 0 }}>{m.points[0].period}</span><span className="ow-xl" style={{ right: 0 }}>{m.points[n - 1].period}</span>
      </div>
    </figure>
  );
}

/** "How the shareholding pattern changed": a line chart per group, 1Y / 3Y / 5Y, the numbers, the CSV. */
export function OwnCharts({ series, symbol }: { series: OwnSeries; symbol: string }) {
  const filings = series.periods.length, maxW = Math.max(1, filings - 1);
  const enabled = WINDOWS.filter((o, k) => o.w <= maxW || (k > 0 ? WINDOWS[k - 1].w < maxW : true));   // a window longer than the history is offered once, as "all of it"
  const [w, setW] = useState(() => enabled[enabled.length - 1]?.w ?? 20), [table, setTable] = useState(false);
  const win = Math.min(w, maxW), idx = windowIndexes(filings, win), keys = groupsOf(series);
  const models = CHARTED.map((k) => chartFor(series, k, win)).filter((m): m is ChartModel => !!m);
  if (!models.length) return (
    <section className="ow-card ow-mt" id="own-history" aria-labelledby="ow-trend">
      <h3 id="ow-trend" className="ow-h2">How the shareholding pattern changed</h3>
      <p className="ow-note">Not enough filings yet to draw a trend: at least two quarterly filings are needed, and this company has {filings}.</p>
    </section>
  );
  return (
    <section className="ow-card ow-mt" id="own-history" aria-labelledby="ow-trend">
      <div className="ow-sec-h ow-center-v">
        <div>
          <h3 id="ow-trend" className="ow-h2">How the shareholding pattern changed</h3>
          <p className="ow-small ow-muted ow-sub">Share of the company held by each group, every quarterly filing, {series.periods[idx[0]]} to {series.periods[filings - 1]}</p>
        </div>
        <div className="ow-seg" role="group" aria-label="Period">
          {WINDOWS.map((o) => <button key={o.w} type="button" aria-pressed={o.w === w} disabled={!enabled.includes(o)} onClick={() => setW(o.w)}>{o.label}</button>)}
        </div>
      </div>
      <div className="ow-panels">{models.map((m) => <Panel key={`${m.key}-${win}`} m={m} />)}</div>
      <div className="ow-foot-row">
        <span className="ow-small ow-muted">{chartNote(series)} Hover, tap or use the arrow keys on a chart for a quarter.</span>
        <span className="ow-actions">
          <button type="button" className="ow-btn" aria-expanded={table} aria-controls="ow-nums" onClick={() => setTable((t) => !t)}>{table ? "Hide the numbers" : "Show the numbers"}</button>
          <button type="button" className="ow-btn" onClick={() => download(`${symbol || "stock"}_shareholding.csv`, csvText(series))}>Download CSV</button>
        </span>
      </div>
      {table && (
        <div className="ow-tablewrap" id="ow-nums">
          <table className="ow-nums">
            <caption className="sr-only">Share of the company held by each group at each filing, in per cent</caption>
            <thead><tr><th scope="col">Filing</th>{keys.map((k) => <th scope="col" key={k}>{NAME[k]}</th>)}</tr></thead>
            <tbody>{[...idx].reverse().map((i) => <tr key={i}><th scope="row">{series.periods[i]}</th>{keys.map((k) => <td key={k}>{fmt2(at(series, k, i))}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
