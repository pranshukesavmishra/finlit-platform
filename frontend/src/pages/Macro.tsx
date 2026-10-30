// India macro insights (free): the official numbers that move Indian markets (inflation, growth, jobs, interest rates, reserves, the rupee, credit)
// from MoSPI and the RBI, with the history behind each, a read of where inflation stands against the RBI's mandate, a heat-map of what is getting
// dearer, and a chart you build yourself. Everything is reproduced or derived as the notes on the page say; nothing is estimated or forecast.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { dateIN, MINUS, nf } from "../lib/format";
import { niceTicks } from "../lib/etf";
import { RANGES, align, corrWords, correlation, cut, fmt, frac, heat, signed, toCsv, useMacro, type Card, type Macro, type Pt, type RangeKey, type SeriesOut } from "../lib/macro";
import "../styles/macro.css";

const TONE = { up: "var(--loss)", down: "var(--gain)", flat: "var(--muted)" } as const;
// for these a rise is a worry (prices, joblessness); for the others it is a good sign
const RISE_IS_BAD = new Set(["cpi", "wpi", "unemployment"]);
// a move in these is a policy or price setting, not good or bad news in itself: shown without red or green
const NEUTRAL = new Set(["repo", "real_rate", "usdinr"]);
const PALETTE = ["var(--gold)", "var(--k1)", "var(--k3)", "var(--k5)", "var(--k7)", "var(--k2)"];
const ARROW = { up: "M2 11l4-4 3 3 5-6M11 4h4v4", down: "M2 5l4 4 3-3 5 6M11 12h4V8", flat: "M2 8h12M11 5l3 3-3 3" } as const;

function Arrow({ d }: { d: "up" | "down" | "flat" }) { return <svg viewBox="0 0 16 16" aria-hidden="true" className="mc-arrow"><path d={ARROW[d]} /></svg>; }
const dir = (v: number | null): "up" | "down" | "flat" => (v == null || Math.abs(v) < 0.005 ? "flat" : v > 0 ? "up" : "down");

function Spark({ pts, color }: { pts: Pt[]; color: string }) {
  if (pts.length < 2) return null;
  const v = pts.map((p) => p[1]), lo = Math.min(...v), hi = Math.max(...v), w = 120, h = 36;
  const path = pts.map((p, i) => `${i ? "L" : "M"}${((i / (pts.length - 1)) * w).toFixed(1)} ${(h - 3 - ((p[1] - lo) / (hi - lo || 1)) * (h - 6)).toFixed(1)}`).join("");
  return <svg className="mc-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true"><path d={`${path}L${w} ${h}L0 ${h}Z`} fill={color} opacity=".12" /><path d={path} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" /></svg>;
}

function StatCard({ c, onOpen }: { c: Card; onOpen: (k: string) => void }) {
  const d = dir(c.change), bad = RISE_IS_BAD.has(c.key), color = d === "flat" || NEUTRAL.has(c.key) ? TONE.flat : (d === "up") === bad ? TONE.up : TONE.down;
  const label = c.key === "gdp" ? "GDP growth (YoY)" : c.key === "iip" ? "Industrial production (YoY)" : c.label;
  return (
    <button type="button" className="mc-card" onClick={() => onOpen(c.key)} aria-label={`${label}: ${fmt(c.value, c.unit)}, ${c.period}. Open its history.`}>
      <span className="mc-card-h"><span>{label}</span><i className="mc-src">{c.key === "real_rate" ? "Derived" : c.source}</i></span>
      <b className="mc-big">{fmt(c.value, c.unit)}</b>
      <span className="mc-chg" style={{ color }}>
        {c.change != null ? <><Arrow d={d} />{signed(c.change, c.changeUnit)}{c.changePct != null && c.key !== "repo" ? ` (${signed(c.changePct, "%")})` : ""}<em> vs {c.prevPeriod}</em></> : <em>{c.period}</em>}
      </span>
      <span className="mc-per">{c.change != null ? c.period : ""}{c.yearAgo != null ? ` · a year earlier ${fmt(c.yearAgo, c.unit)}` : ""}</span>
      <Spark pts={c.spark} color={color} />
    </button>
  );
}

// ------------------------------------------------------------------------------------------------------------- the chart
type Line = { key: string; color: string; dashed?: boolean; step?: boolean };
function Chart({ lines, series, months, normalize = false, height = 300 }: { lines: Line[]; series: Record<string, SeriesOut>; months: number; normalize?: boolean; height?: number }) {
  const box = useRef<HTMLDivElement>(null), svg = useRef<SVGSVGElement>(null);
  const [W, setW] = useState(900), [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = box.current; if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width)))); ro.observe(el); return () => ro.disconnect();
  }, []);
  const data = useMemo(() => lines.map((l) => cut(series[l.key]?.points || [], months)), [lines, series, months]);
  const all = data.flat();
  const H = W < 560 ? Math.round(height * 0.82) : height, L = W < 560 ? 44 : 56, R = 16, T = 18, B = 28;
  if (!all.length) return <p className="mc-empty">No data for this range.</p>;
  const t = (d: string) => Date.parse(d + "T00:00:00Z");
  const t0 = Math.min(...all.map((p) => t(p[0]))), t1 = Math.max(...all.map((p) => t(p[0])));
  const norm = lines.map((_, i) => { const v = data[i].map((p) => p[1]); return [Math.min(...v), Math.max(...v)] as const; });
  const val = (i: number, v: number) => (normalize ? ((v - norm[i][0]) / (norm[i][1] - norm[i][0] || 1)) * 100 : v);
  const vs = data.flatMap((d, i) => d.map((p) => val(i, p[1])));
  const ticks = niceTicks(Math.min(...vs, 0 > Math.min(...vs) ? Math.min(...vs) : Math.min(0, Math.min(...vs))), Math.max(...vs), 5);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const X = (d: string) => L + ((t(d) - t0) / (t1 - t0 || 1)) * (W - L - R), Y = (v: number) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  const path = (i: number, step?: boolean) => data[i].map((p, k) => {
    const x = X(p[0]).toFixed(1), y = Y(val(i, p[1])).toFixed(1);
    return k === 0 ? `M${x} ${y}` : step ? `H${x}V${y}` : `L${x} ${y}`;
  }).join("");
  const years = (t1 - t0) / 31_557_600_000, every = [1, 2, 5, 10, 20].find((k) => years / k <= Math.max(3, Math.floor(W / 90))) ?? 20;
  const y0 = new Date(t0).getUTCFullYear() + 1;
  const xt: number[] = []; for (let y = y0; y <= new Date(t1).getUTCFullYear(); y++) if ((y - y0) % every === 0) xt.push(y);
  const first = series[lines[0].key];
  const refs = !normalize && first?.unit === "%" && lines.some((l) => l.key.startsWith("cpi")) && lo <= 2 ? [[2, "2%"], [4, "4% target"], [6, "6%"]] as const : [];
  const nearest = (d: Pt[], x: number) => { let b = 0; for (let k = 1; k < d.length; k++) if (Math.abs(X(d[k][0]) - x) < Math.abs(X(d[b][0]) - x)) b = k; return d[b]; };
  const move = (e: React.PointerEvent) => { const r = svg.current!.getBoundingClientRect(); setHover(((e.clientX - r.left) / r.width) * W); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault(); const d = data[0]; const cur = hover == null ? d.length - 1 : d.findIndex((p) => X(p[0]) >= hover - 0.5);
      const k = Math.max(0, Math.min(d.length - 1, (cur < 0 ? d.length - 1 : cur) + (e.key === "ArrowRight" ? 1 : -1))); setHover(X(d[k][0]));
    } else if (e.key === "Escape") setHover(null);
  };
  const pick = hover == null ? null : lines.map((l, i) => ({ l, i, p: nearest(data[i], hover) })).filter((x) => x.p && Math.abs(X(x.p[0]) - hover) < Math.max(40, (W - L - R) / Math.max(10, data[x.i].length) * 3));
  const anchor = pick?.[0]?.p?.[0];
  return (
    <div className="mc-chart" ref={box}>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`Chart of ${lines.map((l) => series[l.key]?.label).join(" and ")}. Use the left and right arrow keys to read values.`}
        onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={key}>
        {ticks.map((v) => <g key={v} className="mc-grid"><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} className={v === 0 ? "zero" : ""} /><text x={L - 8} y={Y(v) + 4} textAnchor="end">{normalize ? v : (v < 0 ? MINUS : "") + nf(v, Math.abs(v) >= 100 ? 0 : v % 1 ? 1 : 0)}</text></g>)}
        {refs.map(([v, lab]) => <g key={v} className="mc-ref"><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} /><text x={L + 6} y={Y(v) - 4}>{lab}</text></g>)}
        {xt.map((y) => <text key={y} className="mc-xt" x={X(`${y}-01-01`)} y={H - 8} textAnchor="middle">{y}</text>)}
        {first?.breaks.filter((b) => t(b.d) > t0 && t(b.d) < t1).map((b) => <g key={b.d} className="mc-brk"><line x1={X(b.d)} x2={X(b.d)} y1={T} y2={H - B} /><text x={X(b.d) + (X(b.d) > W * 0.6 ? -5 : 5)} y={T + 10} textAnchor={X(b.d) > W * 0.6 ? "end" : "start"}>{b.label}</text></g>)}
        {lines.map((l, i) => <path key={l.key} d={path(i, l.step)} fill="none" stroke={l.color} strokeWidth={i === 0 ? 2.4 : 2} strokeDasharray={l.dashed ? "6 4" : undefined} strokeLinejoin="round" className="mc-line" />)}
        {anchor && <g className="mc-hv"><line x1={X(anchor)} x2={X(anchor)} y1={T} y2={H - B} />{pick!.map(({ l, i, p }) => <circle key={l.key} cx={X(p[0])} cy={Y(val(i, p[1]))} r="4.5" fill={l.color} />)}</g>}
      </svg>
      {pick && pick.length > 0 && anchor && (
        <div className="mc-tip" style={{ left: `${Math.min(88, Math.max(12, (X(anchor) / W) * 100))}%` }} role="status">
          <b>{series[lines[0].key]?.freq === "Q" ? dateIN(anchor, { month: "short", year: "numeric" }) : dateIN(anchor, { day: "numeric", month: "short", year: "numeric" })}</b>
          {pick.map(({ l, p }) => <span key={l.key}><i style={{ background: l.color }} />{series[l.key]?.label}<em>{fmt(p[1], series[l.key]?.unit)}</em></span>)}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- history tabs
const TABS: { id: string; label: string; lines: Line[]; step?: boolean; note: string }[] = [
  { id: "inflation", label: "Inflation", lines: [{ key: "cpi", color: PALETTE[0] }, { key: "wpi", color: PALETTE[1] }], note: "Retail (CPI) and wholesale (WPI) inflation, year on year. The RBI's target is 4% with a tolerance band of 2-6%." },
  { id: "growth", label: "GDP growth", lines: [{ key: "gdp", color: PALETTE[0] }, { key: "gdp_nominal", color: PALETTE[1], dashed: true }], note: "Real GDP growth (solid) and nominal (dashed), each quarter against the same quarter a year earlier." },
  { id: "industry", label: "Industry and jobs", lines: [{ key: "iip", color: PALETTE[0] }, { key: "unemployment", color: PALETTE[2] }], note: "Industrial production growth and the unemployment rate. Both in per cent; unemployment is published from 2025." },
  { id: "rates", label: "Interest rates", lines: [{ key: "repo", color: PALETTE[0], step: true }, { key: "cpi", color: PALETTE[1], dashed: true }], note: "The RBI repo rate (steps at each MPC decision) against CPI inflation." },
  { id: "real", label: "Real rate", lines: [{ key: "real_rate", color: PALETTE[2] }], note: "Repo rate minus CPI inflation. Below zero, prices are rising faster than the policy rate." },
  { id: "reserves", label: "Reserves and rupee", lines: [{ key: "fx_reserves", color: PALETTE[0] }], note: "Foreign exchange reserves in US$ billion (month end, then weekly)." },
  { id: "rupee", label: "Rupee", lines: [{ key: "usdinr", color: PALETTE[1] }], note: "Rupees per US dollar: monthly average of the RBI reference rate, then the daily FBIL rate." },
];

function History({ m, openId, setOpenId }: { m: Macro; openId: string; setOpenId: (s: string) => void }) {
  const [range, setRange] = useState<RangeKey>("10Y");
  const { toast } = useUI();
  const tab = TABS.find((t) => t.id === openId) || TABS[0];
  const months = RANGES.find((r) => r[0] === range)![1];
  const lines = tab.lines.map((l) => ({ ...l, step: l.step }));
  const latest = lines.map((l) => ({ l, s: m.series[l.key], last: m.series[l.key]?.points.at(-1) })).filter((x) => x.last);
  const csv = () => {
    const keys = lines.map((l) => l.key), blob = new Blob([toCsv(keys, m.series)], { type: "text/csv" }), a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `finlit-india-macro-${tab.id}.csv`; a.click(); URL.revokeObjectURL(a.href); toast("Downloaded the full history of these series.");
  };
  return (
    <section className="mc-panel" aria-labelledby="mcHist" id="history">
      <div className="mc-ph"><h2 id="mcHist">History</h2>
        <div className="mc-seg" role="radiogroup" aria-label="Range">{RANGES.map(([k]) => <button key={k} type="button" role="radio" aria-checked={range === k} className={range === k ? "on" : ""} onClick={() => setRange(k)}>{k}</button>)}</div></div>
      <div className="mc-tabs" role="tablist" aria-label="Which history">{TABS.map((t) => <button key={t.id} type="button" role="tab" aria-selected={tab.id === t.id} className={tab.id === t.id ? "on" : ""} onClick={() => setOpenId(t.id)}>{t.label}</button>)}</div>
      <p className="mc-note">{tab.note}</p>
      <Chart lines={lines} series={m.series} months={months} />
      <ul className="mc-keys">{latest.map(({ l, s, last }) => <li key={l.key}><i style={{ background: l.color }} />{s.label}: <b>{fmt(last![1], s.unit)}</b> <small>latest, {last![0].slice(0, 7)}</small></li>)}</ul>
      <ul className="mc-methods">{lines.map((l) => m.series[l.key]?.note && <li key={l.key}><b>{m.series[l.key].label}.</b> {m.series[l.key].note} <a href={m.series[l.key].sourceUrl || "#"} target="_blank" rel="noopener noreferrer">{m.series[l.key].source}</a></li>)}</ul>
      <div className="mc-acts"><button type="button" className="btn" onClick={csv}>Download these series (CSV)</button></div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- inflation target
function TargetWatch({ m }: { m: Macro }) {
  const w = m.targetWatch, cpi = m.cards.find((c) => c.key === "cpi");
  if (!cpi) return null;
  const lo = 0, hi = 10, at = (v: number) => `${frac(v, lo, hi) * 100}%`;
  const state = cpi.value > w.band[1] ? "above" : cpi.value < w.band[0] ? "below" : "inside";
  return (
    <section className="mc-panel" aria-labelledby="mcTarget">
      <div className="mc-ph"><h2 id="mcTarget">Is inflation inside the RBI's mandate?</h2></div>
      <p className="mc-note">The Government has set the RBI a CPI target of {w.target}% with a tolerance band of {w.band[0]}-{w.band[1]}% for 1 April 2026 to 31 March 2031. {w.rule}</p>
      <div className="mc-gauge" role="img" aria-label={`CPI inflation ${cpi.value}%, ${state === "inside" ? "inside" : state} the ${w.band[0]} to ${w.band[1]} per cent band`}>
        <div className="mc-g-bar"><i className="lo" style={{ width: at(w.band[0]) }} /><i className="in" style={{ left: at(w.band[0]), width: `calc(${at(w.band[1])} - ${at(w.band[0])})` }} /><i className="hi" style={{ left: at(w.band[1]), right: 0 }} />
          <u style={{ left: at(w.target) }}><span>4% target</span></u><b style={{ left: at(Math.min(hi, Math.max(lo, cpi.value))) }}><span>{fmt(cpi.value, "%")}</span></b></div>
        <div className="mc-g-k"><span>0%</span><span style={{ left: at(2) }}>2%</span><span style={{ left: at(6) }}>6%</span><span>10%</span></div>
      </div>
      <div className="mc-q">
        <p><b>Quarterly average CPI</b> (the rule counts quarters in a row outside the band)</p>
        <ul>{w.quarters.map((q) => { const out = q.avg > w.band[1] || q.avg < w.band[0]; return <li key={q.q} className={out ? "out" : ""}><span>{q.q}</span><i style={{ height: `${Math.max(8, frac(q.avg, 0, 10) * 100)}%` }} /><b>{nf(q.avg, 1)}%</b></li>; })}</ul>
        <p className="mc-verdict">{w.streak === 0 ? `The latest quarter (${w.lastQuarter}) averaged inside the band, so the three-quarter rule is not close to being triggered.` : `${w.streak} quarter${w.streak === 1 ? "" : "s"} in a row ${w.side} the band; the rule is triggered at three.`}</p>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- what is getting dearer
function Heatmap({ m }: { m: Macro }) {
  const divs = m.cpiDivisions.filter((d) => d.points.length), months = [...new Set(divs.flatMap((d) => d.points.map((p) => p[0])))].sort().slice(-12);
  const [hot, setHot] = useState<string | null>(null);
  if (!divs.length) return null;
  const last = months[months.length - 1], rank = [...divs].sort((a, b) => (new Map(b.points).get(last) ?? -99) - (new Map(a.points).get(last) ?? -99));
  const short = (s: string) => s.replace(/, water, electricity, gas and other fuels/, ", water and fuels").replace(/Furnishings, household equipment and routine household maintenance/, "Furnishings and household").replace(/Information and communication/, "Information and comms").replace(/Recreation, sport and culture/, "Recreation and culture").replace(/Restaurants and accommodation services/, "Restaurants and hotels").replace(/Personal care, social protection and miscellaneous goods and services/, "Personal care and others").replace(/Paan, tobacco and intoxicants/, "Paan, tobacco");
  return (
    <section className="mc-panel" aria-labelledby="mcHeat">
      <div className="mc-ph"><h2 id="mcHeat">What is getting dearer</h2><span className="mc-chip">CPI by division, all India, year on year</span></div>
      <p className="mc-note">Each row is one group of household spending. Blue is below 2%, green is under the 4% target, amber is above target, red is above the 6% limit. Sorted by the latest month.</p>
      <div className="mc-hw"><table className="mc-heat">
        <thead><tr><th>Division</th>{months.map((d) => <th key={d}>{dateIN(d, { month: "short" })}<small>{d.slice(2, 4)}</small></th>)}</tr></thead>
        <tbody>{rank.map((d) => { const mp = new Map(d.points); return (
          <tr key={d.key} className={hot === d.key ? "on" : ""} onMouseEnter={() => setHot(d.key)} onMouseLeave={() => setHot(null)}>
            <th scope="row">{short(d.label)}</th>{months.map((mo) => { const v = mp.get(mo) ?? null, h = heat(v); return <td key={mo} style={{ background: h.bg }} className={h.strong ? "s" : ""}>{v == null ? "·" : nf(v, 1)}</td>; })}</tr>); })}</tbody></table></div>
      <p className="mc-foot">Source: MoSPI, CPI (base 2024 = 100), as published. Percent change over the same month a year earlier.</p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- compare any two
const COMPARE = ["cpi", "wpi", "gdp", "iip", "unemployment", "repo", "real_rate", "fx_reserves", "usdinr", "cpi_rural", "cpi_urban", "wpi_fuel", "wpi_food", "iip_mfg"];
function Compare({ m }: { m: Macro }) {
  const keys = COMPARE.filter((k) => m.series[k]);
  const [a, setA] = useState("cpi"), [b, setB] = useState("repo"), [range, setRange] = useState<RangeKey>("10Y");
  const months = RANGES.find((r) => r[0] === range)![1], ida = useId(), idb = useId();
  const pa = cut(m.series[a]?.points || [], months), pb = cut(m.series[b]?.points || [], months);
  const r = a === b ? null : correlation(align(pa, pb));
  const sel = (id: string, v: string, set: (s: string) => void, label: string) => <label htmlFor={id}>{label}<select id={id} value={v} onChange={(e) => set(e.target.value)}>{keys.map((k) => <option key={k} value={k}>{m.series[k].label}</option>)}</select></label>;
  return (
    <section className="mc-panel" aria-labelledby="mcCmp">
      <div className="mc-ph"><h2 id="mcCmp">Build your own chart</h2>
        <div className="mc-seg" role="radiogroup" aria-label="Range">{RANGES.map(([k]) => <button key={k} type="button" role="radio" aria-checked={range === k} className={range === k ? "on" : ""} onClick={() => setRange(k)}>{k}</button>)}</div></div>
      <p className="mc-note">Pick any two measures. Each is drawn on its own 0-100 scale between its lowest and highest value in the range, so you can see whether they move together whatever their units.</p>
      <div className="mc-pick">{sel(ida, a, setA, "First")}{sel(idb, b, setB, "Second")}</div>
      <Chart lines={[{ key: a, color: PALETTE[0], step: a === "repo" }, { key: b, color: PALETTE[1], dashed: true, step: b === "repo" }]} series={m.series} months={months} normalize height={260} />
      <div className="mc-corr"><span>Correlation over the months both have</span><b style={{ color: r == null ? "var(--muted)" : r > 0 ? "var(--gain)" : "var(--loss)" }}>{r == null ? MINUS : (r > 0 ? "+" : "") + r.toFixed(2).replace("-", "−")}</b><em>{a === b ? "Choose two different measures." : corrWords(r)}. Correlation shows moving together, not one causing the other.</em></div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- rates and reserves
function Rates({ m }: { m: Macro }) {
  const r = m.rates;
  if (!r) return null;
  const L: [string, string][] = [["repo", "Policy repo rate"], ["sdf", "Standing deposit facility"], ["msf", "Marginal standing facility"], ["bank_rate", "Bank rate"], ["reverse_repo", "Fixed reverse repo"], ["crr", "Cash reserve ratio"], ["slr", "Statutory liquidity ratio"]];
  const ds = [...m.decisions].reverse().slice(0, 8);
  return (
    <section className="mc-panel" aria-labelledby="mcRates">
      <div className="mc-ph"><h2 id="mcRates">RBI rates today</h2><span className="mc-chip">Read from rbi.org.in on {dateIN(r.seenOn)}</span></div>
      <div className="mc-two">
        <dl className="mc-dl">{L.filter(([k]) => r.rates[k] != null).map(([k, l]) => <div key={k}><dt>{l}</dt><dd>{nf(r.rates[k], 2)}%</dd></div>)}</dl>
        <div>
          <h3>Latest rate decisions</h3>
          <ol className="mc-tl">{ds.map((d) => <li key={d.date} className={d.bp > 0 ? "up" : "down"}><span>{dateIN(d.date)}</span><b>{nf(d.rate, 2)}%</b><em>{d.bp > 0 ? "+" : MINUS}{Math.abs(d.bp)} bp</em></li>)}</ol>
          <p className="mc-foot">Repo rate decisions of the Monetary Policy Committee since April 2016. A basis point (bp) is one hundredth of a percentage point.</p>
        </div>
      </div>
      {Object.keys(r.fx).length > 0 && <p className="mc-fx">FBIL reference rates{r.fxAsOf ? ` on ${dateIN(r.fxAsOf)}` : ""}: {[["usdinr", "USD"], ["gbpinr", "GBP"], ["eurinr", "EUR"], ["jpyinr", "100 JPY"]].filter(([k]) => r.fx[k]).map(([k, l]) => <span key={k}>₹{nf(r.fx[k], 2)} <small>per {l}</small></span>)}</p>}
    </section>
  );
}

function Reserves({ m }: { m: Macro }) {
  const w = m.reserves;
  if (!w) return null;
  const t = w.reserves.total, parts: [string, string, string][] = [["fca", "Foreign currency assets", "var(--k1)"], ["gold", "Gold", "var(--gold)"], ["sdr", "SDRs", "var(--k3)"], ["imf", "Reserve position in the IMF", "var(--k7)"]];
  return (
    <section className="mc-panel" aria-labelledby="mcRes">
      <div className="mc-ph"><h2 id="mcRes">What the reserves are made of</h2><span className="mc-chip">Week ended {dateIN(w.reservesAsOf)}</span></div>
      <div className="mc-stack" role="img" aria-label={parts.map(([k, l]) => `${l} ${nf((w.reserves[k].usd / t.usd) * 100, 1)} per cent`).join(", ")}>{parts.map(([k, , c]) => <i key={k} style={{ width: `${(w.reserves[k].usd / t.usd) * 100}%`, background: c }} />)}</div>
      <div className="mc-tw"><table className="mc-t"><thead><tr><th>Component</th><th>US$ bn</th><th>Share</th><th>Week</th><th>Since end-March</th><th>Year</th></tr></thead>
        <tbody>{parts.map(([k, l, c]) => { const x = w.reserves[k]; return <tr key={k}><th scope="row"><i style={{ background: c }} />{l}</th><td>{nf(x.usd / 1000, 2)}</td><td>{nf((x.usd / t.usd) * 100, 1)}%</td><td className={x.weekUsd < 0 ? "neg" : "pos"}>{x.weekUsd < 0 ? MINUS : "+"}{nf(Math.abs(x.weekUsd) / 1000, 2)}</td><td className={x.fyUsd < 0 ? "neg" : "pos"}>{x.fyUsd < 0 ? MINUS : "+"}{nf(Math.abs(x.fyUsd) / 1000, 2)}</td><td className={x.yearUsd < 0 ? "neg" : "pos"}>{x.yearUsd < 0 ? MINUS : "+"}{nf(Math.abs(x.yearUsd) / 1000, 2)}</td></tr>; })}
          <tr className="tot"><th scope="row">Total reserves</th><td>{nf(t.usd / 1000, 2)}</td><td>100%</td><td className={t.weekUsd < 0 ? "neg" : "pos"}>{t.weekUsd < 0 ? MINUS : "+"}{nf(Math.abs(t.weekUsd) / 1000, 2)}</td><td className={t.fyUsd < 0 ? "neg" : "pos"}>{t.fyUsd < 0 ? MINUS : "+"}{nf(Math.abs(t.fyUsd) / 1000, 2)}</td><td className={t.yearUsd < 0 ? "neg" : "pos"}>{t.yearUsd < 0 ? MINUS : "+"}{nf(Math.abs(t.yearUsd) / 1000, 2)}</td></tr></tbody></table></div>
      <p className="mc-foot">Source: <a href={w.link} target="_blank" rel="noopener noreferrer">RBI, Weekly Statistical Supplement extract</a>. Changes are the RBI's own, in US$ billion. Differences in the totals are due to rounding.</p>
    </section>
  );
}

function Coverage({ m }: { m: Macro }) {
  return (
    <section className="mc-panel" aria-labelledby="mcCov">
      <div className="mc-ph"><h2 id="mcCov">Data coverage</h2><span className="mc-chip">Refreshed nightly · last run {dateIN(m.updatedAt)}</span></div>
      <div className="mc-tw"><table className="mc-t"><thead><tr><th>Series</th><th>Source</th><th>From</th><th>Latest</th><th>Observations</th><th>Age</th></tr></thead>
        <tbody>{m.coverage.map((c) => <tr key={c.key}><th scope="row">{c.label}</th><td>{c.source}</td><td>{dateIN(c.from, { month: "short", year: "numeric" })}</td><td>{dateIN(c.latest)}</td><td>{c.observations.toLocaleString("en-IN")}</td><td className={c.ageDays > 70 ? "neg" : ""}>{c.ageDays}d</td></tr>)}</tbody></table></div>
      {m.issues.length > 0 && <p className="mc-foot">{m.issues.length} early observations were left out by our range checks (see the notes under each chart).</p>}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- page
export function MacroPage() {
  useDocTitle("India macro insights", "India macro insights: CPI and WPI inflation, GDP growth, industrial production, unemployment, the RBI repo rate, forex reserves, the rupee and bank credit, from MoSPI and the RBI, with full history.");
  const q = useMacro();
  const [tab, setTab] = useState("inflation");
  const open = (k: string) => {
    const t = ({ cpi: "inflation", wpi: "inflation", gdp: "growth", iip: "industry", unemployment: "industry", repo: "rates", real_rate: "real", fx_reserves: "reserves", usdinr: "rupee", credit_yoy: "inflation" } as Record<string, string>)[k] || "inflation";
    setTab(t); document.getElementById("history")?.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  };
  const m = q.data;
  return (
    <div className="mc-page">
      <section className="mc-hero"><div className="wrap">
        <div className="eyebrow">Free · official data · refreshed nightly</div>
        <h1>India macro insights</h1>
        <p>The policy and price indicators that move Indian markets: inflation, growth, jobs, the RBI's rates, the reserve buffer and the rupee. Every figure comes from MoSPI or the RBI, with the full history behind it.</p>
        {m && <p className="mc-asof">Latest CPI: {m.cards.find((c) => c.key === "cpi")?.period} · Reserves: week ended {m.reserves ? dateIN(m.reserves.reservesAsOf) : "n/a"} · Repo rate as on {m.rates ? dateIN(m.rates.seenOn) : "n/a"}</p>}
      </div></section>
      <div className="wrap mc-wrap">
        {q.isLoading && <div className="mc-skel" aria-busy="true">{Array.from({ length: 6 }, (_, i) => <i key={i} />)}</div>}
        {q.isError && <div className="mc-panel" role="alert"><h2>The macro data is not available yet</h2><p className="mc-note">It loads every night from MoSPI and the RBI. {(q.error as { status?: number })?.status === 503 ? "The first load has not finished; please check back soon." : "Please try again in a moment."}</p><button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></div>}
        {m && <>
          {m.insights.length > 0 && <section className="mc-ins" aria-label="What the latest numbers say">{m.insights.slice(0, 4).map((i) => <div key={i.key} className={"t-" + i.tone}><h2>{i.title}</h2><p>{i.text}</p></div>)}</section>}
          <section className="mc-grid" aria-label="Latest figures">{m.cards.map((c) => <StatCard key={c.key} c={c} onOpen={open} />)}</section>
          <History m={m} openId={tab} setOpenId={setTab} />
          <TargetWatch m={m} />
          {m.insights.length > 4 && <section className="mc-ins" aria-label="More readings">{m.insights.slice(4).map((i) => <div key={i.key} className={"t-" + i.tone}><h2>{i.title}</h2><p>{i.text}</p></div>)}</section>}
          <Heatmap m={m} />
          <Compare m={m} />
          <div className="mc-cols"><Rates m={m} /><Reserves m={m} /></div>
          <Coverage m={m} />
          <section className="mc-panel mc-src-list" aria-labelledby="mcSrc"><h2 id="mcSrc">Sources</h2><ul>{m.sources.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a><span>{s.covers}</span></li>)}</ul>
            <p className="mc-foot">{m.disclaimer} <Link to="/screener">Screen companies</Link> · <Link to="/sip-calculator">SIP calculator</Link></p></section>
        </>}
      </div>
    </div>
  );
}
