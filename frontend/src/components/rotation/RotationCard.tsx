// The rotation card on an industry page ("Against the other industries"), from GET /api/rotation/{slug}: a small path map, the 26-week rank line, rank, breadth, strength and change,
// the server's own summary sentence and the study line for the corner. Describes past prices; never advice. Past averages, not forecasts.
import { Link } from "react-router";
import { CornerBadge, RankMove } from "./Parts";
import { cornerName, failureText, mapGeometry, pts, shortDate, useRotationCard, useRotationMap, weeksText, type RotationCard as Card } from "../../lib/rotation";
import { pct } from "../../lib/sectors";

function PathMap({ c }: { c: Card }) {
  const w = 300, h = 220, g = mapGeometry([c], w, h, 8, null, { left: 8, right: 8, top: 8, bottom: 8 });
  const d = g.dots[0], last = c.tail[c.tail.length - 1], first = c.tail[0];
  return (
    <figure className="rt-pm">
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`Path of ${c.name} over the last ${c.tail.length} weekly closes, ending in ${c.corner_name}${c.this_week_reading_name ? `; this week reads ${c.this_week_reading_name}` : ""}`}>
        <rect className="rt-q bg" x={g.left} y={g.top} width={g.x0 - g.left} height={g.y0 - g.top} /><rect className="rt-q ag" x={g.x0} y={g.top} width={g.right - g.x0} height={g.y0 - g.top} />
        <rect className="rt-q bs" x={g.left} y={g.y0} width={g.x0 - g.left} height={g.bottom - g.y0} /><rect className="rt-q as" x={g.x0} y={g.y0} width={g.right - g.x0} height={g.bottom - g.y0} />
        <line className="rt-axis" x1={g.left} x2={g.right} y1={g.y0} y2={g.y0} /><line className="rt-axis" y1={g.top} y2={g.bottom} x1={g.x0} x2={g.x0} />
        <path className={`rt-tail c-${c.corner}`} d={d.path} fill="none" />
        {d.points.map((p, i) => <circle key={i} className={`rt-pt c-${c.corner}`} cx={p.x} cy={p.y} r="2" />)}
        <g className={`rt-dotg c-${c.corner}`}><circle className={"rt-dot" + (d.hollow ? " hollow" : "")} cx={d.x} cy={d.y} r="5" /></g>
        <text className="rt-qlab bg" x={g.left + 4} y={g.top + 12}>Behind but gaining</text><text className="rt-qlab ag" x={g.right - 4} y={g.top + 12} textAnchor="end">Ahead and gaining</text>
        <text className="rt-qlab bs" x={g.left + 4} y={g.bottom - 5}>Behind and slipping</text><text className="rt-qlab as" x={g.right - 4} y={g.bottom - 5} textAnchor="end">Ahead but slowing</text>
      </svg>
      <figcaption className="rt-note">The last {c.tail.length} weekly closes{first && last ? ` (${shortDate(first.date)} to ${shortDate(last.date)})` : ""}. Across: 6-month return against the average industry. Up: last month.</figcaption>
    </figure>
  );
}

function RankLine({ c }: { c: Card }) {
  const h = c.rank_history, w = 360, ht = 130, worst = Math.max(c.ranked, c.rank_worst_26w ?? 1);
  const x = (i: number) => 28 + (h.length > 1 ? (i / (h.length - 1)) * (w - 38) : 0), y = (r: number) => 10 + ((r - 1) / Math.max(1, worst - 1)) * (ht - 24);
  let d = "", pen = false;
  h.forEach((p, i) => { if (p.rank == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(p.rank).toFixed(1)}`; pen = true; });
  const lastI = h.length - 1;
  const mid = Math.round((1 + worst) / 2);
  const worstPoint = h.find((p) => p.rank === c.rank_worst_26w);
  return (
    <div className="rt-rl">
      <h3>Rank over {h.length} weeks</h3>
      <svg width="100%" viewBox={`0 0 ${w} ${ht}`} role="img" aria-label={`Rank of ${c.name} at each of the last ${h.length} weekly closes: best ${c.rank_best_26w}, worst ${c.rank_worst_26w}, now ${c.rank}. Rank 1 is at the top.`}>
        {[1, mid, worst].map((t) => <g key={t}><line className="rt-grid-l" x1="28" x2={w - 8} y1={y(t)} y2={y(t)} /><text className="rt-tick" x="22" y={y(t) + 4} textAnchor="end">{t}</text></g>)}
        <path className="rt-rankpath" d={d} fill="none" />
        {c.rank != null && <circle className="rt-dot" style={{ fill: "var(--rt-line)" }} cx={x(lastI)} cy={y(c.rank)} r="3.5" />}
        <text className="rt-tick" x="28" y={ht - 2}>{h[0] ? shortDate(h[0].date) : ""}</text><text className="rt-tick" x={w - 8} y={ht - 2} textAnchor="end">{h[lastI] ? shortDate(h[lastI].date) : ""}</text>
      </svg>
      <p className="rt-note">Best in {h.length} weeks: {c.rank_best_26w ?? "—"}{c.rank_best_26w === c.rank ? " (now)" : ""} · worst: {c.rank_worst_26w ?? "—"}{worstPoint ? ` (${shortDate(worstPoint.date)})` : ""}</p>
    </div>
  );
}

export function RotationCard({ slug, groupName, kindLine }: { slug: string; groupName: string; kindLine?: string }) {
  const q = useRotationCard(slug);
  const map = useRotationMap();
  const c = q.data;
  if (q.isLoading) return <section className="rt-card rt-ic sx-sec" role="status" aria-label="Loading the rotation reading"><div className="sx-skel" style={{ height: 160 }} /></section>;
  if (q.isError) return <section className="rt-card rt-ic sx-sec" aria-labelledby="rt-ic"><h2 id="rt-ic">Against the other industries</h2><p className="rt-note" role="status">{failureText(q.error)}</p></section>;
  if (!c) return null;
  if (!c.reading) return <section className="rt-card rt-ic sx-sec" aria-labelledby="rt-ic"><h2 id="rt-ic">Against the other industries</h2><p className="rt-note" role="status">{c.note ?? `${groupName} has too few counted stocks for a rotation reading.`}</p></section>;
  const study = c.study, text = map.data?.study?.text?.[c.corner] as string | undefined;
  const avg = map.data?.average_industry.return_1m;
  return (
    <section className="rt-card rt-ic sx-sec" aria-labelledby="rt-ic" data-testid="rotation-card">
      <div className="rt-ich"><div><p className="rt-note" style={{ margin: 0 }}>{kindLine ?? groupName}</p><h2 id="rt-ic">Against the other industries</h2></div>
        <CornerBadge corner={c.corner} name={`${c.corner_name} · ${weeksText(c.weeks_in_corner)}, since ${shortDate(c.corner_since)}`} className="pill" /></div>
      <div className="rt-icg">
        <PathMap c={c} />
        <div className="rt-icm">
          <div className="rt-kpis">
            <div className="rt-kpi"><small>Rotation rank</small><b>{c.rank ?? "—"} of {c.ranked}</b><span className="rt-note"><RankMove v={c.rank_change_4w} /> in 4 weeks · {c.rank_change_1w === 0 ? "no change on the week" : <><RankMove v={c.rank_change_1w} /> on the week</>}</span></div>
            <div className="rt-kpi"><small>Breadth</small><b>{c.breadth_above_50 == null ? "—" : `${Math.round(c.breadth_above_50)}%`}{c.breadth_name ? ` · ${c.breadth_name}` : ""}</b><span className="rt-note">of {c.stocks_counted} counted stocks above their 50-day average</span></div>
            <div className="rt-kpi"><small>6 months vs the average industry</small><b>{pts(c.strength_pts)} pts</b><span className="rt-note">3 months {pts(c.vs_average?.["63d"])} · 12 months {pts(c.vs_average?.["252d"])}</span></div>
            <div className="rt-kpi"><small>Last month vs the average</small><b>{pts(c.change_pts)} pts</b>{avg != null && <span className="rt-note">the average industry {avg < 0 ? "fell" : "rose"} {pct(Math.abs(avg), 1)}</span>}</div>
          </div>
          <p className="rt-sum">{c.summary}</p>
        </div>
        <div className="rt-icr">
          <RankLine c={c} />
          {(text || study) && <div className="rt-ics"><b>In the {map.data?.study ? `${map.data.study.period.from.slice(0, 4)}–${map.data.study.period.to.slice(0, 4)} ` : ""}study</b>, {text ?? (study && study.next_3m != null ? `groups ${cornerName(c.corner)} did ${pts(study.next_3m)} points against the average industry over the next 3 months${study.beat_3m != null ? ` (${Math.round(study.beat_3m)}% beat it)` : ""}.` : "")} <em>Past averages, not forecasts for this industry.</em></div>}
          <Link className="sx-link" to={`/sectors/rotation?corner=${c.corner}`}>Open Sector Rotation →</Link>
        </div>
      </div>
      <p className="rt-note rt-foot">{map.data?.disclaimer ?? "Describes past prices of NSE industry groups against the average industry; not a recommendation to buy, sell or hold any security. Study results are past averages and do not predict future returns."}</p>
    </section>
  );
}
