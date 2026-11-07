// The breadth history of one industry: three lines (share of counted stocks above their 9, 20 and 50-day averages), the state of each stretch as a shaded band, and
// the thrusts and fading dates as letters. Inline SVG, like the site's other charts. Accessible: the whole chart has a plain-words summary, a focusable plot whose arrow keys
// move a marker session by session (Home / End / PageUp / PageDown jump) with the values read out below, bands carry patterns as well as colours, events are letters, and
// the same numbers are available as a table.
import { useId, useMemo, useRef, useState } from "react";
import { EVENT_WORD, chartGeometry, chartSummary, fullDate, pct, type IndustryPage } from "../../lib/sectors";
import { HScroll } from "../HScroll";
import { ChartZoom } from "../../components/ChartZoom";

const W = 920, H = 340, L = 44, R = 40, T = 30, B = 34;
const PATTERN: Record<string, string> = { washout: "w", thrust_c: "t", thrust_cap: "t", confirmed: "c", fading: "f" };

export function BreadthChart({ page }: { page: IndustryPage }) {
  const uid = useId().replace(/:/g, "");
  const n = page.history.dates.length;
  const g = useMemo(() => chartGeometry(page, L, W - R, T, H - B), [page]);
  const [cur, setCur] = useState<number>(Math.max(0, n - 1));
  const svg = useRef<SVGSVGElement>(null);
  const i = Math.min(Math.max(cur, 0), Math.max(0, n - 1));
  const monthTicks = useMemo(() => {
    const out: { i: number; label: string }[] = [];
    let last = "";
    page.history.dates.forEach((d, k) => { const m = d.slice(0, 7); if (m !== last) { last = m; out.push({ i: k, label: new Date(d + "T00:00:00").toLocaleDateString("en-IN", { month: "short", ...(d.slice(5, 7) === "01" ? { year: "2-digit" } : {}) }) }); } });
    return out;
  }, [page.history.dates]);
  if (n < 2) return <p className="sx-note" role="status">There is no breadth history to draw for {page.name} yet: it needs at least two sessions of readings.</p>;
  const key = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : e.key === "PageUp" ? -20 : e.key === "PageDown" ? 20 : 0;
    if (e.key === "Home") { setCur(0); e.preventDefault(); } else if (e.key === "End") { setCur(n - 1); e.preventDefault(); } else if (step) { setCur(Math.min(n - 1, Math.max(0, i + step))); e.preventDefault(); }
  };
  const pointer = (e: React.PointerEvent) => {
    const el = svg.current; if (!el) return;
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    setCur(Math.min(n - 1, Math.max(0, Math.round(((x - L) / (W - L - R)) * (n - 1)))));
  };
  const h = page.history, ev = page.events.find((e) => e.date === h.dates[i]);
  const state = h.state_code[i];
  const stateName = page.bands.find((b) => b.from <= h.dates[i] && h.dates[i] <= b.to)?.state ?? (state ? state.replace("_", " ") : "No reading");
  const last = n - 1;
  return (
    <ChartZoom label={"Breadth over the past year"}>
    <div className="sx-chart">
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} tabIndex={0} role="group" aria-roledescription="chart" aria-label={chartSummary(page) + " Use the left and right arrow keys to move through the sessions."}
        onKeyDown={key} onPointerMove={pointer} onPointerDown={pointer}>
        <defs>
          <pattern id={`${uid}w`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" className="pat st-washout" /></pattern>
          <pattern id={`${uid}t`} width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1.1" className="pat st-thrust_c" fill="currentColor" style={{ fill: "var(--sx-c-bd)" }} /></pattern>
          <pattern id={`${uid}c`} width="9" height="9" patternUnits="userSpaceOnUse"><line x1="0" y1="4.5" x2="9" y2="4.5" className="pat st-confirmed" /></pattern>
          <pattern id={`${uid}f`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><line x1="0" y1="0" x2="0" y2="7" className="pat st-fading" /></pattern>
        </defs>
        {g.bandRects.map((b, k) => (
          <g key={k}><rect className={`band st-${b.code}`} x={b.x} y={T} width={b.w} height={H - B - T}><title>{`${b.state}: ${fullDate(b.from)} to ${fullDate(b.to)}`}</title></rect>
            {PATTERN[b.code] && <rect x={b.x} y={T} width={b.w} height={H - B - T} fill={`url(#${uid}${PATTERN[b.code]})`} pointerEvents="none" />}</g>
        ))}
        {[0, 20, 50, 80, 100].map((v) => <g key={v}><line className={v === 0 || v === 100 ? "ax" : "guide"} x1={L} x2={W - R} y1={g.y(v)} y2={g.y(v)} /><text x={L - 6} y={g.y(v) + 4} textAnchor="end">{v}%</text></g>)}
        {monthTicks.map((t) => <text key={t.i} x={g.x(t.i)} y={H - 12} textAnchor="middle">{t.label}</text>)}
        <path className="l50" d={g.path(h.above_50)} /><path className="l20" d={g.path(h.above_20)} /><path className="l9" d={g.path(h.above_9)} />
        {g.marks.filter((m) => m.kind === "turned_fading").map((m, k) => <g key={"x" + k}><line className="ev-x" x1={m.x - 4} x2={m.x + 4} y1={H - B - 12} y2={H - B - 4} /><line className="ev-x" x1={m.x + 4} x2={m.x - 4} y1={H - B - 12} y2={H - B - 4} /></g>)}
        {g.marks.filter((m) => m.kind === "thrust_c" || m.kind === "thrust_cap").map((m, k) => {
          const w = m.kind === "thrust_cap" ? 30 : 17;
          return <g key={"t" + k}><rect className="ev-box" x={m.x - w / 2} y={5} width={w} height={17} rx={3} /><text className="ev-t" x={m.x} y={17.5}>{m.kind === "thrust_cap" ? "CAP" : "C"}</text><line x1={m.x} x2={m.x} y1={22} y2={26} stroke="var(--muted)" /></g>;
        })}
        <line className="cur" x1={g.x(i)} x2={g.x(i)} y1={T} y2={H - B} />
        {([["dot9", h.above_9[i]], ["dot20", h.above_20[i]], ["dot50", h.above_50[i]]] as const).map(([c, v]) => v != null && <circle key={c} className={c} cx={g.x(i)} cy={g.y(v)} r={4.2} stroke="var(--bg)" strokeWidth={1.5} />)}
        {([["e9", h.above_9[last], "9"], ["e20", h.above_20[last], "20"], ["e50", h.above_50[last], "50"]] as const).map(([c, v, t]) => v != null && <text key={c} className={`endl ${c}`} x={W - R + 5} y={g.y(v) + 4}>{t}</text>)}
      </svg>
      <p className="sx-readout" aria-live="polite" data-testid="chart-readout">
        <b>{fullDate(h.dates[i])}</b> · {stateName}{ev ? ` · ${EVENT_WORD[ev.kind]}` : ""} · 9-day {pct(h.above_9[i])} · 20-day {pct(h.above_20[i])} · 50-day {pct(h.above_50[i])} · {h.stocks_counted[i]} stocks counted
      </p>
      <ul className="sx-legend" aria-label="Chart key">
        <li><span className="sw st-washout" />Washout</li><li><span className="sw st-thrust" />Thrust window</li><li><span className="sw st-confirmed" />Confirmed</li><li><span className="sw st-fading" />Fading</li><li><span className="sw st-neutral" />Neutral</li>
        <li><span className="ev">C</span><span className="ev">CAP</span> Thrust day</li><li><span className="xx" aria-hidden="true">×</span> Turned Fading</li>
        <li><span className="ln l9" />9-day</li><li><span className="ln l20" />20-day</li><li><span className="ln l50" />50-day</li><li>Dotted lines: 80%, 50% and 20% guides</li>
      </ul>
      <details className="sx-chartdata"><summary>Show the chart as a table ({n} sessions)</summary>
        <HScroll label="breadth history" className="sx-scroll">
          <table className="sx-t" style={{ minWidth: 520 }}>
            <caption className="sx-visually">Breadth history of {page.name}: share of counted stocks above their averages, by session</caption>
            <thead><tr><th scope="col" style={{ minWidth: 110 }}>Session</th><th scope="col">State</th><th scope="col">9-day</th><th scope="col">20-day</th><th scope="col">50-day</th><th scope="col">Counted</th></tr></thead>
            <tbody>{[...h.dates.keys()].reverse().map((k) => <tr key={h.dates[k]}><th scope="row" className="l" style={{ fontWeight: 600, textAlign: "left", textTransform: "none", letterSpacing: 0, fontSize: 14, color: "var(--text)" }}>{fullDate(h.dates[k])}</th><td className="l">{h.state_code[k]?.replace("_", " ")}</td><td>{pct(h.above_9[k])}</td><td>{pct(h.above_20[k])}</td><td>{pct(h.above_50[k])}</td><td>{h.stocks_counted[k]}</td></tr>)}</tbody>
          </table>
        </HScroll>
      </details>
    </div>
    </ChartZoom>
  );
}
