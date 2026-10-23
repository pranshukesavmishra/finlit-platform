// Mutual Fund Insights (/funds/insights): where India's fund money sits and where it moved last month, from AMFI's monthly category report
// (backend/finlit/mf_insights.py). Industry totals only: no scheme is ranked or recommended. Information only, never advice.
// Charts are plain SVG built on the fund pages' geometry (lib/mf buildLines / nearestIndex): no chart library.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Link } from "react-router";
import { PageArt } from "../components/PageArt";
import { HScroll } from "../components/HScroll";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dateIN, nf } from "../lib/format";
import { buildLines, nearestIndex, niceTicks, type LineSeries } from "../lib/mf";
import {
  GROUP_COLORS, TRENDS, changeText, folios, money, monthLabel, tone, trendSeries, useMfInsights,
  type InsightGroup, type InsightsOk, type Kpi, type TrendKey,
} from "../lib/mfInsights";
import "../styles/mf.css";
import "../styles/mfinsights.css";

const LEAD = "Where India's fund money actually sits and where it moved last month — total assets, net flows by scheme category, the equity/debt/hybrid split, and folio growth. Straight from AMFI's monthly category report.";

const Head = () => (
  <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" />
    <div className="eyebrow">Mutual funds</div><h1>Mutual Fund Insights</h1><p>{LEAD}</p></div></section>
);

export function FundInsightsPage() {
  useDocTitle("Mutual Fund Insights", "India's mutual fund industry month by month from AMFI's monthly category report: total assets, net flows by category, the equity/debt/hybrid split and folios. Information only.");
  const q = useMfInsights();
  const d = q.data;
  return (
    <>
      <Head />
      <div className="wrap mf mfi">
        <p className="mfi-back"><Link to="/funds"><Icon name="arrow" />All mutual fund schemes</Link></p>
        {q.isError && !d ? (
          <div className="state card mfi-state" role="alert"><h2>The insights are unavailable right now</h2><p>The figures could not be fetched. Please try again in a moment.</p>
            <button className="btn" onClick={() => q.refetch()}>Try again</button></div>
        ) : !d ? <Skeleton /> : d.status === "empty" ? (
          <div className="state card mfi-state" role="status"><span className="mfi-state-ic"><Icon name="info" /></span><h2>Not loaded yet</h2><p>{d.reason}</p>
            <p className="faint">Source: <a href={d.sourcePage} target="_blank" rel="noopener noreferrer">{d.source}</a>. {d.disclaimer}</p></div>
        ) : <Loaded d={d} />}
      </div>
    </>
  );
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Loading the insights">
      <div className="mfi-kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="mfi-kpi"><div className="skeleton" style={{ height: 118 }} /></div>)}</div>
      <div className="card mfi-card"><div className="skeleton" style={{ height: 360 }} /></div>
      <div className="mfi-two"><div className="card mfi-card"><div className="skeleton" style={{ height: 260 }} /></div><div className="card mfi-card"><div className="skeleton" style={{ height: 260 }} /></div></div>
    </div>
  );
}

// ================================================================================================ loaded

function Loaded({ d }: { d: InsightsOk }) {
  const k = d.kpis, month = monthLabel(d.month);
  const cards: { key: string; label: string; icon: string; k: Kpi; value: string; fmt: (n: number, plus?: boolean) => string; spark: (number | null)[]; bars?: boolean; note?: string }[] = [
    { key: "aum", label: "Industry net AUM", icon: "coins", k: k.aum, value: money(k.aum.value), fmt: money, spark: d.series.aum },
    { key: "flow", label: "Net flows", icon: "activity", k: k.netFlow, value: money(k.netFlow.value, true), fmt: money, spark: d.series.netFlow, bars: true,
      note: k.netFlow.mobilized != null ? `${money(k.netFlow.mobilized)} in · ${money(k.netFlow.redemption)} out` : undefined },
    { key: "folios", label: "Folios", icon: "users", k: k.folios, value: folios(k.folios.value), fmt: folios, spark: d.series.folios },
    { key: "eq", label: "Equity AUM", icon: "growth", k: k.equityAum, value: money(k.equityAum.value), fmt: money, spark: d.series.equityAum,
      note: "Equity schemes, open and close ended" },
  ];
  return (
    <>
      <div className="mfi-kpis" role="list" aria-label={`Industry figures for ${month}`}>
        {cards.map((c) => (
          <article key={c.key} className="mfi-kpi" role="listitem" aria-label={`${c.label}: ${c.value}. ${changeText(c.k, c.fmt, d.prevMonth)}`}>
            <div className="mfi-kpi-top"><span className="mfi-kpi-ic" aria-hidden="true"><Icon name={c.icon} /></span><span className="mfi-kpi-l">{c.label}</span>
              <Spark v={c.spark.slice(-24)} bars={c.bars} /></div>
            <b className={"mfi-kpi-v" + (c.key === "flow" ? " " + tone(c.k.value) : "")}>{c.value}</b>
            <Delta k={c.k} fmt={c.fmt} prevMonth={d.prevMonth} />
            {c.note && <small className="mfi-kpi-n">{c.note}</small>}
            <small className="mfi-kpi-src">{month} · {d.source}</small>
          </article>
        ))}
      </div>

      <Trend d={d} />
      <div className="mfi-two">
        <Split d={d} />
        <FlowsByGroup d={d} />
      </div>
      <CategoryTable d={d} />

      <footer className="mf-foot" aria-label="Source and disclaimer">
        <p><b>{d.disclaimer}</b></p>
        <p>Source: <a href={d.sourcePage} target="_blank" rel="noopener noreferrer">{d.source}</a>, AMFI (Association of Mutual Funds in India)
          {d.sourceUrl && <> (<a href={d.sourceUrl} target="_blank" rel="noopener noreferrer">{month} file</a>)</>}. Figures as at {dateIN(d.asOf)}
          {d.released && <>, released {dateIN(d.released)}</>}; loaded {dateIN(d.updatedAt)}. Amounts in rupees; 1 L cr is ₹1 lakh crore.</p>
        <p className="faint">{d.coverage}{d.gaps.length > 0 && <> No report could be read for {d.gaps.map((g) => monthLabel(g)).join(", ")}; the chart joins the months either side.</>}</p>
      </footer>
    </>
  );
}

/** The change against the month before: an arrow and colour for up or down (and the words, so colour is never the only cue). */
function Delta({ k, fmt, prevMonth }: { k: Kpi; fmt: (n: number, plus?: boolean) => string; prevMonth: string | null }) {
  if (k.change == null || !prevMonth) return <span className="mfi-delta">No earlier month to compare</span>;
  const up = k.change > 0, flat = k.change === 0;
  return (
    <span className={"mfi-delta " + (flat ? "" : up ? "up" : "down")}>
      <span className="mfi-pill" aria-hidden="true">{flat ? "■" : up ? "▲" : "▼"}</span>
      {fmt(k.change, true)}{k.changePct != null && <> ({(k.changePct > 0 ? "+" : k.changePct < 0 ? "−" : "") + nf(Math.abs(k.changePct), 2)}%)</>}
      <span className="mfi-vs"> vs {monthLabel(prevMonth)}</span>
    </span>
  );
}

/** A tiny trend line (or bars, for flows) of the last two years, for the card's corner. Decorative: the card's text says the same. */
function Spark({ v, bars }: { v: (number | null)[]; bars?: boolean }) {
  const pts = v.map((x, i) => [i, x] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (pts.length < 2) return null;
  const w = 76, h = 26, lo = Math.min(0, ...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  const X = (i: number) => (i / (v.length - 1)) * w, Y = (x: number) => h - 2 - ((x - (bars ? lo : Math.min(...pts.map((p) => p[1])))) / ((hi - (bars ? lo : Math.min(...pts.map((p) => p[1])))) || 1)) * (h - 4);
  return (
    <svg className="mfi-spark" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      {bars ? pts.map(([i, x]) => <rect key={i} x={X(i) - 1.1} width="2.2" y={Math.min(Y(x), Y(0))} height={Math.max(0.8, Math.abs(Y(0) - Y(x)))} fill={x < 0 ? "var(--loss)" : "var(--gain)"} />)
        : <path d={pts.map(([i, x], j) => `${j ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}`).join("")} fill="none" stroke="var(--k1)" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />}
    </svg>
  );
}

// ------------------------------------------------------------------------------------------------ trend chart

const RANGES: { key: string; label: string; months: number }[] = [{ key: "1y", label: "1Y", months: 12 }, { key: "3y", label: "3Y", months: 36 }, { key: "all", label: "All", months: 0 }];

function Trend({ d }: { d: InsightsOk }) {
  const [key, setKey] = useState<TrendKey>("aum");
  const [range, setRange] = useState("all");
  const def = TRENDS.find((t) => t.key === key)!;
  const s = useMemo(() => {
    const full = trendSeries(d, key), n = RANGES.find((r) => r.key === range)!.months;
    return n && full.t.length > n ? { ...full, t: full.t.slice(-n), v: full.v.slice(-n) } : full;
  }, [d, key, range]);
  const last = s.v.length ? s.v[s.v.length - 1] : null;
  const tabId = useId();
  return (
    <section className="card mfi-card mfi-trend" aria-labelledby="mfi-trend-h">
      <div className="mfi-card-h">
        <h3 id="mfi-trend-h"><span className="ci"><Icon name="line" /></span>Industry trend</h3>
        <div className="mfi-ctl">
          <div className="mfi-tabs" role="group" aria-label="Which figure to chart">
            {TRENDS.map((t) => <button key={t.key} aria-pressed={t.key === key} aria-controls={`${tabId}-panel`} onClick={() => setKey(t.key)}>{t.label}</button>)}</div>
          <div className="seg mfi-range" role="group" aria-label="Period">
            {RANGES.map((r) => <button key={r.key} aria-pressed={r.key === range} onClick={() => setRange(r.key)}>{r.label}</button>)}</div>
        </div>
      </div>
      <div id={`${tabId}-panel`} aria-live="off">
        <p className="mfi-latest">Latest {monthLabel(d.month, true)}: <b>{last == null ? "—" : def.text(last)}</b></p>
        <TrendChart key={key + range} s={s} kind={def.kind} text={def.text} axis={def.axis} label={`${def.label}, monthly, ${monthLabel(s.t[0] || d.month)} to ${monthLabel(d.month)}`} />
        <p className="faint mf-fine">{def.caption}</p>
      </div>
    </section>
  );
}

const WIDE = { W: 760, H: 300 }, NARROW = { W: 400, H: 280 }, PAD = { l: 50, r: 12, t: 16, b: 28 };
const NARROW_Q = "(max-width: 560px)";

/** Phones get their own, taller chart geometry: the desktop one scaled down to 340 px would be barely 130 px high. */
function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(NARROW_Q).matches);
  useEffect(() => {
    const m = window.matchMedia?.(NARROW_Q);
    if (!m) return;
    const on = () => setNarrow(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return narrow;
}

/** A monthly chart: an area from zero with a soft gradient, or bars either side of zero for net flows. Point at it (crosshair and a tooltip), or
 *  focus it and use the arrow keys; the reading is announced politely. */
function TrendChart({ s, kind, text, axis, label }: { s: LineSeries; kind: "area" | "bars"; text: (n: number) => string; axis: (n: number) => string; label: string }) {
  const { W, H } = useNarrow() ? NARROW : WIDE;
  const g = useMemo(() => (s.t.length < 2 ? null : buildLines([s, { key: "zero", label: "", t: [s.t[0], s.t[s.t.length - 1]], v: [0, 0] }], W, H, PAD)), [s, W, H]);
  const [at, setAt] = useState<number | null>(null);   // index of the month being read
  const box = useRef<SVGSVGElement>(null);
  const id = useId().replace(/:/g, "");
  if (!g) return <div className="mf-chart-empty">Not enough months loaded to draw a chart.</div>;
  const xy = g.lines[0].xy, y0 = g.Y(0);
  const yTicks = niceTicks(g.lo, g.hi, 6).filter((v) => v >= g.lo && v <= g.hi);   // a little denser than the fund charts: one figure, more room
  const xs = xy.map((p) => p[0]);
  const move = (e: PointerEvent<SVGRectElement>) => {
    const r = box.current!.getBoundingClientRect();
    setAt(nearestIndex(xs, ((e.clientX - r.left) / r.width) * W));
  };
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape") { setAt(null); return; }
    const n = xs.length - 1, cur = at ?? n;
    const next = e.key === "ArrowLeft" ? cur - 1 : e.key === "ArrowRight" ? cur + 1 : e.key === "Home" ? 0 : e.key === "End" ? n : null;
    if (next == null) return;
    e.preventDefault();
    setAt(Math.max(0, Math.min(n, next)));
  };
  const bw = Math.max(1.5, ((W - PAD.l - PAD.r) / xs.length) * 0.66);
  const lo = Math.min(...s.v), hi = Math.max(...s.v);
  const summary = `${label}. From ${text(s.v[0])} in ${monthLabel(s.t[0])} to ${text(s.v[s.v.length - 1])} in ${monthLabel(s.t[s.t.length - 1])}. Lowest ${text(lo)}, highest ${text(hi)}.`;
  const area = `${g.lines[0].d}L${xs[xs.length - 1].toFixed(1)},${y0.toFixed(1)}L${xs[0].toFixed(1)},${y0.toFixed(1)}Z`;
  const tipX = at == null ? 0 : (xs[at] / W) * 100, tipY = at == null ? 0 : (Math.min(xy[at][1], y0) / H) * 100;
  const prev = at != null && at > 0 ? s.v[at - 1] : null;
  return (
    <div className="mf-chart mfi-chart" tabIndex={0} role="group" aria-label={`${label}. Use the left and right arrow keys to read each month.`} onKeyDown={key} onBlur={() => setAt(null)}>
      <svg ref={box} viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-t`} preserveAspectRatio="xMidYMid meet">
        <title id={`${id}-t`}>{summary}</title>
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--k1)" stopOpacity="0.38" /><stop offset="100%" stopColor="var(--k1)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {yTicks.map((v) => <g key={v}><line x1={PAD.l} x2={W - PAD.r} y1={g.Y(v)} y2={g.Y(v)} stroke="var(--border)" strokeDasharray="2 6" /><text x={PAD.l - 8} y={g.Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">{axis(v)}</text></g>)}
        {g.xTicks.map((t, i) => <text key={i} x={t.at} y={H - 8} textAnchor={i === 0 ? "start" : i === g.xTicks.length - 1 ? "end" : "middle"} fontSize="11" fill="var(--faint)">{t.label}</text>)}
        <line x1={PAD.l} x2={W - PAD.r} y1={y0} y2={y0} stroke="var(--border-strong)" />
        {kind === "area" ? (
          <g className="mfi-draw">
            <path d={area} fill={`url(#${id}-fill)`} />
            <path d={g.lines[0].d} fill="none" stroke="var(--k1)" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={xs[xs.length - 1]} cy={xy[xy.length - 1][1]} r="3.6" fill="var(--k1)" />
          </g>
        ) : (
          <g className="mfi-draw">{xy.map(([x, y], i) => (
            <rect key={s.t[i]} x={x - bw / 2} width={bw} y={Math.min(y, y0)} height={Math.max(1, Math.abs(y0 - y))} rx={Math.min(2, bw / 3)}
              fill={s.v[i] < 0 ? "var(--loss)" : "var(--gain)"} opacity={at == null || at === i ? 0.92 : 0.35} />
          ))}</g>
        )}
        {at != null && (
          <g pointerEvents="none">
            <line x1={xs[at]} x2={xs[at]} y1={PAD.t} y2={H - PAD.b} stroke="var(--muted)" strokeDasharray="3 4" />
            {kind === "area" && <><line x1={PAD.l} x2={W - PAD.r} y1={xy[at][1]} y2={xy[at][1]} stroke="var(--border-strong)" strokeDasharray="3 4" />
              <circle cx={xs[at]} cy={xy[at][1]} r="5" fill="var(--s1)" stroke="var(--k1)" strokeWidth="2.4" /></>}
          </g>
        )}
        <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={H - PAD.t - PAD.b} fill="transparent" onPointerMove={move} onPointerDown={move} onPointerLeave={() => setAt(null)} />
      </svg>
      {at != null && (
        <div className={"mfi-tip" + (tipX > 70 ? " left" : tipX < 22 ? " right" : "")} style={{ left: `${tipX}%`, top: `${tipY}%` }} aria-hidden="true">
          <span>{monthLabel(s.t[at])}</span><b className={kind === "bars" ? tone(s.v[at]) : ""}>{text(s.v[at])}</b>
          {prev != null && kind === "area" && <small className={tone(s.v[at] - prev)}>{(s.v[at] - prev >= 0 ? "▲ " : "▼ ") + text(Math.abs(s.v[at] - prev))} on the month</small>}
        </div>
      )}
      <div className="mf-tip sr-tip" aria-live="polite">
        {at != null ? <span><b>{monthLabel(s.t[at])}</b> {text(s.v[at])}</span>
          : <span className="faint">{s.t.length} months, {monthLabel(s.t[0])} to {monthLabel(s.t[s.t.length - 1])}. Point at the chart, or focus it and use the arrow keys.</span>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ split (donut) and flows

const TAU = Math.PI * 2;
function arc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const p = (a: number) => `${(cx + r * Math.sin(a)).toFixed(2)},${(cy - r * Math.cos(a)).toFixed(2)}`;
  return `M${p(a0)}A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${p(a1)}`;
}

function Split({ d }: { d: InsightsOk }) {
  const [hot, setHot] = useState<string | null>(null);
  const total = d.groups.reduce((a, g) => a + (g.aum || 0), 0) || 1;
  let a = 0;
  const slices = d.groups.map((g) => { const a0 = a, a1 = a + ((g.aum || 0) / total) * TAU; a = a1; return { g, a0, a1 }; });
  const sel = d.groups.find((g) => g.key === hot);
  return (
    <section className="card mfi-card" aria-labelledby="mfi-split-h">
      <div className="mfi-card-h"><h3 id="mfi-split-h"><span className="ci"><Icon name="pie" /></span>Where the money sits</h3></div>
      <div className="mfi-donut-wrap">
        <svg className="mfi-donut" viewBox="0 0 200 200" role="img" aria-label={"Share of net assets: " + d.groups.map((g) => `${g.label} ${nf(g.share ?? 0, 1)}%`).join(", ")}>
          <circle cx="100" cy="100" r="78" fill="none" stroke="var(--s3)" strokeWidth="26" />
          {slices.map(({ g, a0, a1 }) => (
            <path key={g.key} d={arc(100, 100, 78, a0 + 0.012, Math.max(a0 + 0.013, a1 - 0.012))} fill="none" stroke={GROUP_COLORS[g.key]}
              strokeWidth={hot === g.key ? 32 : 26} opacity={hot && hot !== g.key ? 0.35 : 1} className="mfi-slice"
              onPointerEnter={() => setHot(g.key)} onPointerLeave={() => setHot(null)} />
          ))}
          <text x="100" y="92" textAnchor="middle" className="mfi-donut-l">{sel ? sel.label.split(":")[0] : "All schemes"}</text>
          <text x="100" y="116" textAnchor="middle" className="mfi-donut-v">{money(sel ? sel.aum : d.kpis.aum.value)}</text>
          {sel && <text x="100" y="134" textAnchor="middle" className="mfi-donut-s">{nf(sel.share ?? 0, 1)}% of the total</text>}
        </svg>
        <ul className="mfi-legend">
          {d.groups.map((g) => (
            <li key={g.key}>
              <button className={hot === g.key ? "on" : ""} onPointerEnter={() => setHot(g.key)} onPointerLeave={() => setHot(null)} onFocus={() => setHot(g.key)} onBlur={() => setHot(null)}
                aria-label={`${g.label}: ${money(g.aum)}, ${nf(g.share ?? 0, 1)}% of net assets`}>
                <i style={{ background: GROUP_COLORS[g.key] }} aria-hidden="true" /><span>{g.label}</span>
                <b>{nf(g.share ?? 0, 1)}%</b><small>{money(g.aum)}</small></button></li>
          ))}
        </ul>
      </div>
      <p className="faint mf-fine">Share of {money(d.kpis.aum.value)} of net assets at the end of {monthLabel(d.month)}. Other: index funds, ETFs (gold and silver too) and funds of funds investing overseas.</p>
    </section>
  );
}

function FlowsByGroup({ d }: { d: InsightsOk }) {
  const max = Math.max(1, ...d.groups.map((g) => Math.abs(g.netFlow ?? 0)));
  return (
    <section className="card mfi-card" aria-labelledby="mfi-flow-h">
      <div className="mfi-card-h"><h3 id="mfi-flow-h"><span className="ci"><Icon name="bars" /></span>Net flows in {monthLabel(d.month)}</h3></div>
      <ul className="mfi-flows">
        {d.groups.map((g) => {
          const w = (Math.abs(g.netFlow ?? 0) / max) * 50;
          return (
            <li key={g.key}><span className="mfi-flows-l"><i style={{ background: GROUP_COLORS[g.key] }} aria-hidden="true" />{g.label.split(":")[0]}</span>
              <span className="mfi-track" aria-hidden="true"><i className={tone(g.netFlow)} style={(g.netFlow ?? 0) < 0 ? { right: "50%", width: `${w}%` } : { left: "50%", width: `${w}%` }} /></span>
              <b className={tone(g.netFlow)}>{money(g.netFlow, true)}</b></li>
          );
        })}
      </ul>
      <p className="faint mf-fine">Money put in minus money taken out during the month: right and green, more came in; left and red, more went out.</p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------ category table

function CategoryTable({ d }: { d: InsightsOk }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const total = d.kpis.aum.value || 0;
  const maxFlow = Math.max(1, ...d.groups.flatMap((g) => [Math.abs(g.netFlow ?? 0)]));
  const allOpen = d.groups.every((g) => open[g.key]);
  return (
    <section className="card mfi-card mfi-table" aria-labelledby="mfi-cat-h">
      <div className="mfi-card-h"><h3 id="mfi-cat-h"><span className="ci"><Icon name="table" /></span>By scheme category, {monthLabel(d.month)}</h3>
        <button className="btn mfi-expand" onClick={() => setOpen(allOpen ? {} : Object.fromEntries(d.groups.map((g) => [g.key, true])))}>{allOpen ? "Collapse all" : "Expand all"}</button></div>
      <HScroll label="Scheme categories">
        <table className="mf-table mfi-t">
          <thead><tr><th className="txt" scope="col">Category</th><th className="num mfi-opt" scope="col">Schemes</th><th className="num mfi-opt" scope="col">Folios</th>
            <th className="num" scope="col">Net flow</th><th className="num mfi-aumh" scope="col">Net AUM · share</th></tr></thead>
          <tbody>
            {d.groups.map((g) => (
              <GroupRows key={g.key} g={g} open={!!open[g.key]} onToggle={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))} total={total} maxFlow={maxFlow} />
            ))}
            <tr className="mfi-total"><th className="txt" scope="row">All schemes</th><td className="num mfi-opt">{nf(d.groups.reduce((a, g) => a + (g.schemes || 0), 0), 0)}</td>
              <td className="num mfi-opt">{folios(d.kpis.folios.value)}</td><td className={"num " + tone(d.kpis.netFlow.value)}>{money(d.kpis.netFlow.value, true)}</td>
              <td className="num">{money(d.kpis.aum.value)} <span className="mfi-sh">100%</span></td></tr>
          </tbody>
        </table>
      </HScroll>
      <p className="faint mf-fine">Open a group to see AMFI's categories in it; close-ended and interval schemes are marked. Net flow is for the month, net AUM at the month end.
        {d.fofDomestic && <> Not in the totals: fund of funds (domestic), {money(d.fofDomestic.aum)} across {nf(d.fofDomestic.schemes ?? 0, 0)} schemes, net flow {money(d.fofDomestic.netFlow, true)}. {d.fofDomestic.note}</>}</p>
    </section>
  );
}

function AumCell({ aum, total, color }: { aum: number | null; total: number; color: string }) {
  const sh = aum == null || !total ? null : (aum / total) * 100;
  return (
    <td className="num mfi-aum">
      <span className="mfi-aumv">{money(aum)} <span className="mfi-sh">{sh == null ? "—" : nf(sh, 1) + "%"}</span></span>
      <span className="mfi-inbar" aria-hidden="true"><i style={{ width: `${Math.min(100, sh ?? 0)}%`, background: color }} /></span>
    </td>
  );
}

function FlowCell({ v, max, title }: { v: number | null; max: number; title?: string }) {
  const w = Math.min(100, (Math.abs(v ?? 0) / max) * 100);
  return (
    <td className={"num mfi-flowc " + tone(v)} title={title}>
      <span>{money(v, true)}</span>
      <span className="mfi-inbar flow" aria-hidden="true"><i className={tone(v)} style={{ width: `${w}%` }} /></span>
    </td>
  );
}

function GroupRows({ g, open, onToggle, total, maxFlow }: { g: InsightGroup; open: boolean; onToggle: () => void; total: number; maxFlow: number }) {
  const rid = `mfi-g-${g.key}`;
  return (
    <>
      <tr className={"mfi-group" + (open ? " open" : "")}>
        <th className="txt" scope="row">
          <button className="mfi-toggle" aria-expanded={open} aria-controls={rid} onClick={onToggle}>
            <span className="mfi-chev" aria-hidden="true" /><i style={{ background: GROUP_COLORS[g.key] }} aria-hidden="true" /><span>{g.label}</span>
            <small>{g.items.length} categor{g.items.length === 1 ? "y" : "ies"}</small></button></th>
        <td className="num mfi-opt">{g.schemes == null ? "—" : nf(g.schemes, 0)}</td><td className="num mfi-opt">{folios(g.folios)}</td>
        <FlowCell v={g.netFlow} max={maxFlow} /><AumCell aum={g.aum} total={total} color={GROUP_COLORS[g.key]} />
      </tr>
      {open && g.items.map((it, i) => (
        <tr key={it.name + it.section + i} id={i === 0 ? rid : undefined} className="mfi-item">
          <th className="txt" scope="row"><span className="mfi-iname">{it.name}{it.section !== "open" && <span className="chip ghost">{it.sectionLabel}</span>}</span></th>
          <td className="num mfi-opt">{it.schemes == null ? "—" : nf(it.schemes, 0)}</td><td className="num mfi-opt">{folios(it.folios)}</td>
          <FlowCell v={it.netFlow} max={maxFlow} title={it.mobilized != null ? `${money(it.mobilized)} in, ${money(it.redemption)} out` : undefined} />
          <AumCell aum={it.aum} total={total} color={GROUP_COLORS[g.key]} />
        </tr>
      ))}
    </>
  );
}
