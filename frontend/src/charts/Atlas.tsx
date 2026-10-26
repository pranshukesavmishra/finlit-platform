// The chart lab's drawing kit: hand-built SVG/HTML charts that read the theme tokens, so they follow the light/dark theme and
// the member's colour palette. Each takes plain arrays; none fetches anything.
import { useId, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { MINUS, nf } from "../lib/format";

type N = number | null;
const GRID = "var(--border)", AX = "var(--faint)";
const W = 720;
const sgn = (v: number, d = 1) => (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d);
const day = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function Readout({ children }: { children: ReactNode }) { return <div className="rd" aria-live="polite">{children}</div>; }

/* ---------- candlesticks with moving averages and volume ---------- */
export function Candles({ t, o, h, l, c, v, ema50, ema200, w: W = 1000 }: { t: string[]; o: N[]; h: N[]; l: N[]; c: number[]; v: N[]; ema50?: N[]; ema200?: N[]; w?: number }) {
  const [hv, setHv] = useState<number | null>(null);
  const n = t.length, H = 330, pl = 52, pr = 10, pt = 10, ph = 236, vt = 262, vh = 44;
  const vals = [...h, ...l, ...(ema50 || []), ...(ema200 || [])].filter((x): x is number => x != null);
  if (n < 2 || !vals.length) return null;
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const step = (W - pl - pr) / n, X = (i: number) => pl + (i + 0.5) * step, Y = (x: number) => pt + (1 - (x - lo) / (hi - lo)) * ph;
  const vmax = Math.max(...v.map((x) => x ?? 0), 1), bw = Math.max(1.2, Math.min(7, step * 0.6));
  const line = (arr?: N[]) => { if (!arr) return ""; let d = ""; arr.forEach((x, i) => { if (x != null) d += `${d && arr[i - 1] != null ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}`; }); return d; };
  const ticks = [0, 1, 2, 3, 4].map((k) => lo + ((hi - lo) * k) / 4);
  const every = Math.max(1, Math.ceil(n / 7));
  const i = hv ?? n - 1;
  return (
    <div className="mb">
      <Readout><b>{day(t[i])}</b> <span>O {o[i] != null ? nf(o[i] as number) : "—"}</span> <span>H {h[i] != null ? nf(h[i] as number) : "—"}</span> <span>L {l[i] != null ? nf(l[i] as number) : "—"}</span> <span>C {nf(c[i])}</span> <span>Vol {v[i] != null ? nf(v[i] as number, 0) : "—"}</span></Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Candlestick chart with 50 and 200 day averages and volume" onMouseLeave={() => setHv(null)}>
        {ticks.map((x) => <g key={x}><line x1={pl} x2={W - pr} y1={Y(x)} y2={Y(x)} stroke={GRID} /><text x={pl - 6} y={Y(x) + 3.5} textAnchor="end" fontSize="10" fill={AX} fontFamily="var(--mono)">{nf(x, 0)}</text></g>)}
        {t.map((d, k) => { if (k % every) return null; return <text key={d} x={X(k)} y={H - 4} textAnchor="middle" fontSize="10" fill={AX}>{new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</text>; })}
        {t.map((_, k) => { const up = (c[k] ?? 0) >= (o[k] ?? c[k]), col = up ? "var(--gain)" : "var(--loss)"; const top = Y(Math.max(o[k] ?? c[k], c[k])), bot = Y(Math.min(o[k] ?? c[k], c[k]));
          return <g key={k} opacity={hv == null || hv === k ? 1 : 0.55}>{h[k] != null && l[k] != null && <line x1={X(k)} x2={X(k)} y1={Y(h[k] as number)} y2={Y(l[k] as number)} stroke={col} strokeWidth="1" />}
            <rect x={X(k) - bw / 2} y={top} width={bw} height={Math.max(1, bot - top)} fill={col} />
            <rect x={X(k) - bw / 2} y={vt + vh - ((v[k] ?? 0) / vmax) * vh} width={bw} height={((v[k] ?? 0) / vmax) * vh} fill={col} opacity=".45" /></g>; })}
        {ema200 && <path d={line(ema200)} fill="none" stroke="var(--c3)" strokeWidth="1.6" />}
        {ema50 && <path d={line(ema50)} fill="none" stroke="var(--c2)" strokeWidth="1.4" strokeDasharray="5 4" />}
        {t.map((_, k) => <rect key={k} x={X(k) - step / 2} y={pt} width={step} height={H - pt} fill="transparent" onMouseEnter={() => setHv(k)} />)}
        {hv != null && <line x1={X(hv)} x2={X(hv)} y1={pt} y2={vt + vh} stroke="var(--border-strong)" />}
      </svg>
      <div className="clg"><span><i style={{ background: "var(--gain)" }} />Up day</span><span><i style={{ background: "var(--loss)" }} />Down day</span>{ema50 && <span><i style={{ background: "var(--c2)" }} />50-day average</span>}{ema200?.some((x) => x != null) && <span><i style={{ background: "var(--c3)" }} />200-day average</span>}</div>
    </div>
  );
}

/* ---------- area / line over dates (drawdown, volatility) ---------- */
export function AreaSeries({ t, v, fmt, color = "var(--k1)", height = 210, floor, ceil, fill = true, ref: refLine }: { t: string[]; v: N[]; fmt: (x: number) => string; color?: string; height?: number; floor?: number; ceil?: number; fill?: boolean; ref?: { y: number; label: string } }) {
  const id = useId().replace(/:/g, ""), [hv, setHv] = useState<number | null>(null);
  const n = t.length, H = height, pl = 46, pr = 10, pt = 12, pb = 24;
  const nums = v.filter((x): x is number => x != null);
  if (n < 2 || !nums.length) return null;
  const lo = floor ?? Math.min(...nums), hi = ceil ?? Math.max(...nums), span = hi - lo || 1;
  const X = (i: number) => pl + (i * (W - pl - pr)) / (n - 1), Y = (x: number) => pt + (1 - (x - lo) / span) * (H - pt - pb);
  let d = ""; v.forEach((x, i) => { if (x != null) d += `${d ? "L" : "M"}${X(i).toFixed(1)},${Y(x).toFixed(1)}`; });
  const base = Y(Math.min(Math.max(0, lo), hi));
  const yearTicks = t.map((s, i) => [s.slice(0, 4), i] as const).filter(([y], i, a) => i === 0 || y !== a[i - 1][0]);
  const ticks = [lo, lo + span / 2, hi];
  const i = hv ?? n - 1;
  return (
    <div className="mb">
      <Readout><b>{day(t[i])}</b> <span>{v[i] != null ? fmt(v[i] as number) : "—"}</span></Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Line chart over time" onMouseLeave={() => setHv(null)}>
        <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".42" /><stop offset="1" stopColor={color} stopOpacity=".04" /></linearGradient></defs>
        {ticks.map((x) => <g key={x}><line x1={pl} x2={W - pr} y1={Y(x)} y2={Y(x)} stroke={GRID} /><text x={pl - 6} y={Y(x) + 3.5} textAnchor="end" fontSize="10" fill={AX} fontFamily="var(--mono)">{fmt(x)}</text></g>)}
        {yearTicks.map(([y, k]) => <text key={y} x={X(k)} y={H - 6} fontSize="10" fill={AX}>{y}</text>)}
        {refLine && <g><line x1={pl} x2={W - pr} y1={Y(refLine.y)} y2={Y(refLine.y)} stroke="var(--faint)" /><text x={W - pr} y={Y(refLine.y) - 4} textAnchor="end" fontSize="10" fill={AX}>{refLine.label}</text></g>}
        {fill && <path d={`${d}L${X(n - 1)},${base}L${X(0)},${base}Z`} fill={`url(#${id})`} />}
        <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
        {t.map((_, k) => <rect key={k} x={X(k) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="transparent" onMouseEnter={() => setHv(k)} />)}
        {hv != null && v[hv] != null && <g><line x1={X(hv)} x2={X(hv)} y1={pt} y2={H - pb} stroke="var(--border-strong)" /><circle cx={X(hv)} cy={Y(v[hv] as number)} r="4" fill={color} /></g>}
      </svg>
    </div>
  );
}

/* ---------- histogram of daily moves ---------- */
export function Histo({ counts, from, binWidth }: { counts: number[]; from: number; binWidth: number }) {
  const [hv, setHv] = useState<number | null>(null);
  const H = 210, pl = 40, pr = 8, pt = 12, pb = 26, n = counts.length, max = Math.max(...counts, 1);
  const bw = (W - pl - pr) / n, X = (i: number) => pl + i * bw, Y = (x: number) => pt + (1 - x / max) * (H - pt - pb);
  const total = counts.reduce((a, b) => a + b, 0) || 1;
  const label = (i: number) => { const a = from + i * binWidth; return `${i === 0 ? "≤ " : i === n - 1 ? "≥ " : ""}${sgn(i === n - 1 ? a : i === 0 ? a + binWidth : a, 2)}%`; };
  return (
    <div className="mb">
      <Readout>{hv == null ? <span>Each bar is how many sessions ended in that range.</span> : <><b>{label(hv)}</b> <span>{counts[hv]} sessions · {nf((counts[hv] / total) * 100, 1)}%</span></>}</Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Distribution of daily price moves" onMouseLeave={() => setHv(null)}>
        {[0, 0.5, 1].map((k) => <g key={k}><line x1={pl} x2={W - pr} y1={Y(max * k)} y2={Y(max * k)} stroke={GRID} /><text x={pl - 6} y={Y(max * k) + 3.5} textAnchor="end" fontSize="10" fill={AX} fontFamily="var(--mono)">{Math.round(max * k)}</text></g>)}
        {counts.map((x, i) => { const mid = from + (i + 0.5) * binWidth; return <rect key={i} x={X(i) + 0.5} y={Y(x)} width={Math.max(1, bw - 1)} height={H - pb - Y(x)} fill={mid < 0 ? "var(--loss)" : "var(--gain)"} opacity={hv == null || hv === i ? 0.9 : 0.45} onMouseEnter={() => setHv(i)} />; })}
        {[-4, -2, 0, 2, 4].map((x) => <g key={x}><line x1={pl + ((x - from) / binWidth) * bw} x2={pl + ((x - from) / binWidth) * bw} y1={H - pb} y2={H - pb + 4} stroke={AX} /><text x={pl + ((x - from) / binWidth) * bw} y={H - 8} textAnchor="middle" fontSize="10" fill={AX}>{x > 0 ? "+" : x < 0 ? MINUS : ""}{Math.abs(x)}%</text></g>)}
      </svg>
    </div>
  );
}

/* ---------- box plot per year ---------- */
export type BoxRow = { year: number; q1: number; median: number; q3: number; low: number; high: number; outliers: number[] };
export function Box({ years }: { years: BoxRow[] }) {
  const [hv, setHv] = useState<number | null>(null);
  const H = 250, pl = 46, pr = 8, pt = 12, pb = 24, n = years.length;
  if (!n) return null;
  const all = years.flatMap((y) => [y.low, y.high, ...y.outliers]);
  let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.05; lo -= pad; hi += pad;
  const step = (W - pl - pr) / n, X = (i: number) => pl + (i + 0.5) * step, Y = (x: number) => pt + (1 - (x - lo) / (hi - lo)) * (H - pt - pb), bw = Math.min(46, step * 0.5);
  const ticks = [lo, (lo + hi) / 2, 0, hi].filter((x, i, a) => a.indexOf(x) === i);
  const y = hv == null ? null : years[hv];
  return (
    <div className="mb">
      <Readout>{y ? <><b>{y.year}</b> <span>middle half {sgn(y.q1, 2)}% to {sgn(y.q3, 2)}%</span> <span>median {sgn(y.median, 2)}%</span> <span>range {sgn(y.low, 1)}% to {sgn(y.high, 1)}%</span></> : <span>Box: the middle half of the year's daily moves. Line: median. Dots: unusual days.</span>}</Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily moves by year" onMouseLeave={() => setHv(null)}>
        {ticks.map((x) => <g key={x}><line x1={pl} x2={W - pr} y1={Y(x)} y2={Y(x)} stroke={x === 0 ? "var(--border-strong)" : GRID} strokeDasharray={x === 0 ? "" : "3 5"} /><text x={pl - 6} y={Y(x) + 3.5} textAnchor="end" fontSize="10" fill={AX} fontFamily="var(--mono)">{sgn(x, 0)}%</text></g>)}
        {years.map((b, i) => <g key={b.year} opacity={hv == null || hv === i ? 1 : 0.5} onMouseEnter={() => setHv(i)}>
          <line x1={X(i)} x2={X(i)} y1={Y(b.high)} y2={Y(b.low)} stroke="var(--faint)" />
          <rect x={X(i) - bw / 2} y={Y(b.q3)} width={bw} height={Math.max(2, Y(b.q1) - Y(b.q3))} rx="3" fill="color-mix(in srgb, var(--k1) 18%, var(--s1))" stroke="var(--k1)" />
          <line x1={X(i) - bw / 2} x2={X(i) + bw / 2} y1={Y(b.median)} y2={Y(b.median)} stroke="var(--k1)" strokeWidth="2.2" />
          {b.outliers.map((o, k) => <circle key={k} cx={X(i)} cy={Y(o)} r="2.6" fill={o < 0 ? "var(--loss)" : "var(--gain)"} opacity=".8" />)}
          <text x={X(i)} y={H - 6} textAnchor="middle" fontSize="10.5" fill={AX}>{b.year}</text>
          <rect x={X(i) - step / 2} y={pt} width={step} height={H - pt} fill="transparent" /></g>)}
      </svg>
    </div>
  );
}

/* ---------- waterfall ---------- */
export type Step = { label: string; value: number; total?: boolean };
export function Waterfall({ steps, fmt, height = 280, w: W = 1000 }: { steps: Step[]; fmt: (x: number) => string; height?: number; w?: number }) {
  const [hv, setHv] = useState<number | null>(null);
  const H = height, pl = 12, pr = 12, pt = 24, pb = 44, n = steps.length;
  const bars = useMemo(() => { let run = 0; return steps.map((s) => { if (s.total) { run = s.value; return { from: 0, to: s.value, end: s.value }; } const from = run; run += s.value; return { from, to: run, end: run }; }); }, [steps]);
  const all = bars.flatMap((b) => [b.from, b.to, 0]);
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const step = (W - pl - pr) / n, bw = Math.min(54, step * 0.62), X = (i: number) => pl + (i + 0.5) * step, Y = (x: number) => pt + (1 - (x - lo) / span) * (H - pt - pb);
  return (
    <div className="mb">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Waterfall chart" onMouseLeave={() => setHv(null)}>
        <line x1={pl} x2={W - pr} y1={Y(0)} y2={Y(0)} stroke="var(--border-strong)" />
        {steps.map((s, i) => { const b = bars[i], top = Y(Math.max(b.from, b.to)), bot = Y(Math.min(b.from, b.to)); const col = s.total ? "var(--c1)" : s.value >= 0 ? "var(--gain)" : "var(--loss)";
          return <g key={s.label + i} opacity={hv == null || hv === i ? 1 : 0.5} onMouseEnter={() => setHv(i)}>
            {i > 0 && <line x1={X(i - 1) + bw / 2} x2={X(i) - bw / 2} y1={Y(bars[i - 1].end)} y2={Y(bars[i - 1].end)} stroke="var(--border-strong)" />}
            <rect x={X(i) - bw / 2} y={top} width={bw} height={Math.max(2, bot - top)} rx="3" fill={col} />
            <text x={X(i)} y={top - 6} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--text)" fontFamily="var(--mono)">{s.total ? fmt(s.value) : (s.value > 0 ? "+" : "") + fmt(s.value)}</text>
            <text x={X(i)} y={H - 24} textAnchor="middle" fontSize="10.5" fill={AX}>{s.label.split(" ").slice(0, 2).join(" ")}</text>
            {s.label.split(" ").length > 2 && <text x={X(i)} y={H - 11} textAnchor="middle" fontSize="10.5" fill={AX}>{s.label.split(" ").slice(2).join(" ")}</text>}
            <rect x={X(i) - step / 2} y={pt} width={step} height={H - pt} fill="transparent" /></g>; })}
      </svg>
    </div>
  );
}

/* ---------- heat grid (monthly returns, growth by line) ---------- */
export function HeatGrid({ cols, rows, fmt, cap, label }: { cols: string[]; rows: { label: string; values: N[] }[]; fmt: (x: number) => string; cap: number; label: string }) {
  return (
    <div className="hg" role="table" aria-label={label} style={{ "--cols": cols.length } as CSSProperties}>
      <div className="hg-r hg-h" role="row"><span role="columnheader" />{cols.map((c) => <span key={c} role="columnheader">{c}</span>)}</div>
      {rows.map((r) => <div className="hg-r" role="row" key={r.label}><b role="rowheader">{r.label}</b>{cols.map((c, i) => { const v = r.values[i]; const k = v == null ? 0 : Math.min(1, Math.abs(v) / cap);
        return <span role="cell" key={c} className={"hc2 " + (v == null ? "na" : v >= 0 ? "pos" : "neg")} style={{ "--k": k } as CSSProperties} title={v == null ? "" : `${r.label} ${c}: ${fmt(v)}`}>{v == null ? "" : fmt(v)}</span>; })}</div>)}
    </div>
  );
}

/* ---------- treemap (squarified) ---------- */
type TItem = { label: string; value: number; color?: string };
function squarify(items: { v: number; i: number }[], x: number, y: number, w: number, h: number, out: Map<number, [number, number, number, number]>) {
  if (!items.length) return;
  const scale = (w * h) / items.reduce((a, b) => a + b.v, 0), areas = items.map((q) => q.v * scale), side = Math.min(w, h);
  const worst = (row: number[], sum: number) => Math.max((side * side * Math.max(...row)) / (sum * sum), (sum * sum) / (side * side * Math.min(...row)));
  let k = 1, sum = areas[0], best = worst([areas[0]], sum);
  while (k < items.length) { const next = worst(areas.slice(0, k + 1), sum + areas[k]); if (next > best) break; best = next; sum += areas[k]; k++; }
  if (w >= h) { const rw = sum / h; let cy = y; for (let i = 0; i < k; i++) { const rh = areas[i] / rw; out.set(items[i].i, [x, cy, rw, rh]); cy += rh; } squarify(items.slice(k), x + rw, y, w - rw, h, out); }
  else { const rh = sum / w; let cx = x; for (let i = 0; i < k; i++) { const rw = areas[i] / rh; out.set(items[i].i, [cx, y, rw, rh]); cx += rw; } squarify(items.slice(k), x, y + rh, w, h - rh, out); }
}
export function Treemap({ items, fmt, height = 280 }: { items: TItem[]; fmt: (x: number) => string; height?: number }) {
  const total = items.reduce((a, b) => a + Math.max(0, b.value), 0) || 1;
  const boxes = useMemo(() => { const arr = items.map((it, i) => ({ v: Math.max(0, it.value), i })).filter((q) => q.v > 0).sort((a, b) => b.v - a.v); const m = new Map<number, [number, number, number, number]>(); squarify(arr, 0, 0, 100, 100, m); return m; }, [items]);
  return (
    <div className="tm" style={{ height }} role="img" aria-label="Treemap">
      {items.map((it, i) => { const b = boxes.get(i); if (!b) return null; const share = (it.value / total) * 100;
        return <div key={it.label} className="tm-c" style={{ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%`, "--tc": it.color || `var(--c${(i % 5) + 1})` } as CSSProperties} title={`${it.label}: ${fmt(it.value)} (${nf(share, 1)}%)`}>
          <span><b>{it.label}</b>{b[2] > 12 && b[3] > 14 && <small>{nf(share, 1)}%</small>}</span></div>; })}
    </div>
  );
}

/* ---------- donut ---------- */
export function Donut({ parts, center, sub }: { parts: { label: string; value: number; color: string; note?: string }[]; center: string; sub?: string }) {
  const [hv, setHv] = useState<number | null>(null);
  const total = parts.reduce((a, b) => a + b.value, 0) || 1, R = 70, r = 46, C = 90;
  let a0 = -Math.PI / 2;
  const arcs = parts.map((p, i) => { const a1 = a0 + (p.value / total) * Math.PI * 2 - (parts.length > 1 ? 0.012 : 0); const large = a1 - a0 > Math.PI ? 1 : 0;
    const pt = (rad: number, ang: number) => `${(C + rad * Math.cos(ang)).toFixed(2)},${(C + rad * Math.sin(ang)).toFixed(2)}`;
    const d = `M${pt(R, a0)}A${R},${R} 0 ${large} 1 ${pt(R, a1)}L${pt(r, a1)}A${r},${r} 0 ${large} 0 ${pt(r, a0)}Z`; a0 += (p.value / total) * Math.PI * 2; return { d, p, i }; });
  const cur = hv == null ? null : parts[hv];
  return (
    <div className="dn">
      <svg viewBox="0 0 180 180" role="img" aria-label="Share breakdown" onMouseLeave={() => setHv(null)}>
        {parts.length === 1   /* one slice is a full circle: an arc that ends where it starts draws nothing, so a single part is drawn as a ring */
          ? <circle cx={C} cy={C} r={(R + r) / 2} fill="none" stroke={parts[0].color} strokeWidth={R - r} onMouseEnter={() => setHv(0)}><title>{parts[0].label}</title></circle>
          : arcs.map(({ d, p, i }) => <path key={p.label} d={d} fill={p.color} opacity={hv == null || hv === i ? 1 : 0.45} onMouseEnter={() => setHv(i)} tabIndex={0} onFocus={() => setHv(i)} onBlur={() => setHv(null)}><title>{`${p.label}: ${nf((p.value / total) * 100, 1)}%${p.note ? " (" + p.note + ")" : ""}`}</title></path>)}
        <text x="90" y="88" textAnchor="middle" fontFamily="var(--serif)" fontSize="22" fill="var(--text)">{cur ? nf((cur.value / total) * 100, 1) + "%" : center}</text>
        <text x="90" y="106" textAnchor="middle" fontSize="10" fill={AX}>{cur ? cur.label : sub}</text>
      </svg>
      <ul className="dn-k">{parts.map((p, i) => <li key={p.label} onMouseEnter={() => setHv(i)} onMouseLeave={() => setHv(null)}><i style={{ background: p.color }} /><span>{p.label}</span><b>{nf((p.value / total) * 100, 1)}%</b></li>)}</ul>
    </div>
  );
}

/* ---------- slope: two points in time ---------- */
export function Slope({ rows, aLabel, bLabel, fmt }: { rows: { label: string; a: number; b: number; color: string }[]; aLabel: string; bLabel: string; fmt: (x: number) => string }) {
  const W = 560, H = 250, pl = 178, pr = 104, pt = 28, pb = 12;
  const all = rows.flatMap((r) => [r.a, r.b]), lo = Math.min(...all, 0), hi = Math.max(...all), span = hi - lo || 1, Y = (x: number) => pt + (1 - (x - lo) / span) * (H - pt - pb);
  return (
    <div className="mb"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Change from ${aLabel} to ${bLabel}`}>
      <text x={pl} y="14" textAnchor="middle" fontSize="11" fill={AX}>{aLabel}</text><text x={W - pr} y="14" textAnchor="middle" fontSize="11" fill={AX}>{bLabel}</text>
      {rows.map((r) => <g key={r.label}><line x1={pl} x2={W - pr} y1={Y(r.a)} y2={Y(r.b)} stroke={r.color} strokeWidth="2.4" strokeLinecap="round" />
        <circle cx={pl} cy={Y(r.a)} r="4.5" fill={r.color} /><circle cx={W - pr} cy={Y(r.b)} r="4.5" fill={r.color} />
        <text x={pl - 10} y={Y(r.a) + 4} textAnchor="end" fontSize="11.5" fill="var(--text)">{r.label} <tspan fontFamily="var(--mono)" fill={AX}>{fmt(r.a)}</tspan></text>
        <text x={W - pr + 10} y={Y(r.b) + 4} fontSize="11.5" fill="var(--text)"><tspan fontFamily="var(--mono)">{fmt(r.b)}</tspan> <tspan fill={r.b >= r.a ? "var(--gain)" : "var(--loss)"} fontFamily="var(--mono)">{r.b >= r.a ? "▲" : "▼"}{nf(Math.abs(r.b - r.a), 1)}</tspan></text></g>)}
    </svg></div>
  );
}

/* ---------- dumbbell: two values per row ---------- */
export function Dumbbell({ rows, aLabel, bLabel, fmt }: { rows: { label: string; a: number; b: number }[]; aLabel: string; bLabel: string; fmt: (x: number, label: string) => string }) {
  return (
    <ul className="db2">{rows.map((r) => { const lo = Math.min(r.a, r.b), hi = Math.max(r.a, r.b), max = Math.max(hi * 1.15, 1e-9); const p = (x: number) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`;
      return <li key={r.label}><span className="db2-l">{r.label}</span><span className="db2-t"><i className="db2-b" style={{ left: p(lo), width: `calc(${p(hi)} - ${p(lo)})` }} /><i className="db2-a" style={{ left: p(r.a) }} title={`${aLabel}: ${fmt(r.a, r.label)}`} /><i className="db2-c" style={{ left: p(r.b) }} title={`${bLabel}: ${fmt(r.b, r.label)}`} /></span>
        <span className="db2-v"><span>{fmt(r.a, r.label)}</span> → <b>{fmt(r.b, r.label)}</b></span></li>; })}
      <li className="db2-k"><span /><span><i className="db2-a" />{aLabel}<i className="db2-c" style={{ marginLeft: 14 }} />{bLabel}</span><span /></li></ul>
  );
}

/* ---------- 100% stacked area ---------- */
export function StackArea({ periods, series, w: W = 1000 }: { periods: string[]; series: { key: string; label: string; values: N[]; color: string }[]; w?: number }) {
  const [hv, setHv] = useState<number | null>(null);
  const H = 250, pl = 40, pr = 10, pt = 10, pb = 24, n = periods.length;
  if (n < 2) return null;
  const tot = periods.map((_, i) => series.reduce((a, s) => a + (s.values[i] ?? 0), 0) || 1);
  const X = (i: number) => pl + (i * (W - pl - pr)) / (n - 1), Y = (p: number) => pt + (1 - p / 100) * (H - pt - pb);
  let acc = periods.map(() => 0);
  const areas = series.map((s) => { const lo = acc.slice(); const hi = acc.map((a, i) => a + ((s.values[i] ?? 0) / tot[i]) * 100); acc = hi;
    return { s, d: `M${hi.map((p, i) => `${X(i)},${Y(p)}`).join("L")}L${lo.map((_, i) => `${X(n - 1 - i)},${Y(lo[n - 1 - i])}`).join("L")}Z` }; });
  const every = Math.ceil(n / 8), i = hv ?? n - 1;
  return (
    <div className="mb">
      <Readout><b>{periods[i]}</b> {series.map((s) => <span key={s.key}><i className="cdot" style={{ background: s.color }} />{s.label} {nf(((s.values[i] ?? 0) / tot[i]) * 100, 1)}%</span>)}</Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Ownership mix over time" onMouseLeave={() => setHv(null)}>
        {[0, 25, 50, 75, 100].map((p) => <g key={p}><line x1={pl} x2={W - pr} y1={Y(p)} y2={Y(p)} stroke={GRID} /><text x={pl - 6} y={Y(p) + 3.5} textAnchor="end" fontSize="10" fill={AX} fontFamily="var(--mono)">{p}%</text></g>)}
        {areas.map(({ s, d }) => <path key={s.key} d={d} fill={s.color} opacity=".92" />)}
        {periods.map((p, k) => k % every === 0 ? <text key={p} x={X(k)} y={H - 6} textAnchor="middle" fontSize="10" fill={AX}>{p}</text> : null)}
        {periods.map((_, k) => <rect key={k} x={X(k) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="transparent" onMouseEnter={() => setHv(k)} />)}
        {hv != null && <line x1={X(hv)} x2={X(hv)} y1={pt} y2={H - pb} stroke="var(--text)" strokeOpacity=".5" />}
      </svg>
    </div>
  );
}

/* ---------- horizontal ranked / diverging bars ---------- */
export function RankBars({ rows, fmt, diverging = false }: { rows: { label: string; value: number; self?: boolean }[]; fmt: (x: number) => string; diverging?: boolean }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9);
  return (
    <ul className="rk">{rows.map((r) => <li key={r.label} className={r.self ? "me" : ""}><span className="rk-l">{r.label}</span>
      <span className={"rk-t" + (diverging ? " dv" : "")}><i className={r.value < 0 ? "neg" : "pos"} style={diverging ? { width: `${(Math.abs(r.value) / max) * 50}%`, [r.value >= 0 ? "left" : "right"]: "50%" } : { width: `${(Math.abs(r.value) / max) * 100}%` }} /></span>
      <b className="rk-v">{fmt(r.value)}</b></li>)}</ul>
  );
}

/* ---------- event timeline ---------- */
export function Timeline({ events, w: W = 1000 }: { events: { date: string; label: string; kind: string }[]; w?: number }) {
  const [hv, setHv] = useState<number | null>(null);
  const ev = [...events].sort((a, b) => a.date.localeCompare(b.date));
  if (ev.length < 1) return null;
  const t0 = new Date(ev[0].date).getTime(), t1 = new Date(ev[ev.length - 1].date).getTime(), span = t1 - t0 || 1;
  const H = 150, pl = 24, pr = 24, X = (d: string) => pl + ((new Date(d).getTime() - t0) / span) * (W - pl - pr);
  const color: Record<string, string> = { dividend: "var(--k1)", bonus: "var(--gain)", split: "var(--c2)", rights: "var(--loss)", other: "var(--faint)" };
  const years = [...new Set(ev.map((e) => e.date.slice(0, 4)))];
  const cur = hv == null ? null : ev[hv];
  return (
    <div className="mb">
      <Readout>{cur ? <><b>{day(cur.date)}</b> <span>{cur.label}</span></> : <span>Hover a marker to read the event.</span>}</Readout>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Corporate action timeline" onMouseLeave={() => setHv(null)}>
        <line x1={pl} x2={W - pr} y1={90} y2={90} stroke="var(--border-strong)" strokeWidth="2" />
        {years.map((y) => <g key={y}><line x1={X(`${y}-01-01`)} x2={X(`${y}-01-01`)} y1={84} y2={96} stroke={AX} /><text x={Math.max(pl, X(`${y}-01-01`))} y={118} fontSize="10" fill={AX} textAnchor="middle">{y}</text></g>)}
        {ev.map((e, i) => <circle key={i} cx={X(e.date)} cy={e.kind === "dividend" ? 90 : 66} r={e.kind === "dividend" ? 5 : 7} fill={color[e.kind] || color.other} stroke="var(--s1)" strokeWidth="2" opacity={hv == null || hv === i ? 1 : 0.5} onMouseEnter={() => setHv(i)} />)}
      </svg>
      <div className="clg">{[["dividend", "Dividend"], ["bonus", "Bonus"], ["split", "Split"], ["rights", "Rights"]].filter(([k]) => ev.some((e) => e.kind === k)).map(([k, l]) => <span key={k}><i style={{ background: color[k] }} />{l}</span>)}</div>
    </div>
  );
}
