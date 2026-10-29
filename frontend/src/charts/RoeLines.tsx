import { useEffect, useRef, useState } from "react";
import { labelEvery } from "../lib/chartAxis";

/** Width of the element in px (a default before it is measured, and where ResizeObserver does not exist). */
export function useWidth(initial = 600) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => { const nw = Math.round(e.contentRect.width); if (nw > 40) setW((o) => (Math.abs(o - nw) > 1 ? nw : o)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** Round tick values that cover [lo, hi]. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  const span = hi - lo || 1, raw = span / count, mag = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = []; for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.5; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

export type LineSeries = { key: string; label: string; values: (number | null)[]; color: string; dotted?: boolean; marker: "circle" | "square" };

/** Lines in plain SVG: one point per period, a gap wherever a value is missing, a dotted line for the secondary series, and different marker shapes so colour is never the only signal.
 *  `flags` rings a period (low-quality earnings); `notes` explains a missing value in the tooltip. Hover or focus a column to read it. */
export function RoeLines({ labels, series, fmt, flags, notes, height = 230, ariaLabel }: {
  labels: string[]; series: LineSeries[]; fmt: (v: number) => string; flags?: boolean[]; notes?: (string | null)[]; height?: number; ariaLabel: string;
}) {
  const [wrap, W] = useWidth();
  const [hv, setHv] = useState<number | null>(null);
  const n = labels.length, H = height, pl = 46, pr = 10, pt = 14, pb = 26;
  const vals = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const lo = Math.min(0, ...vals), hi = Math.max(...vals, 1), ticks = niceTicks(lo, hi), top = ticks[ticks.length - 1], bot = Math.min(lo, ticks[0]);
  const X = (i: number) => pl + (i + 0.5) * ((W - pl - pr) / n), Y = (v: number) => pt + (1 - (v - bot) / (top - bot || 1)) * (H - pt - pb);
  const every = labelEvery(n, W - pl - pr, Math.max(...labels.map((l) => l.length), 1));
  const runs = (s: LineSeries) => { const out: [number, number][][] = []; let cur: [number, number][] = []; s.values.forEach((v, i) => { if (v == null) { if (cur.length) out.push(cur); cur = []; } else cur.push([X(i), Y(v)]); }); if (cur.length) out.push(cur); return out; };
  return (
    <div className="mb dp-chart" ref={wrap} onMouseLeave={() => setHv(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={ariaLabel}>
        {ticks.map((t) => <g key={t}><line x1={pl} x2={W - pr} y1={Y(t)} y2={Y(t)} stroke="var(--border)" strokeWidth={t === 0 ? 1.4 : 1} /><text x={pl - 6} y={Y(t) + 3.5} textAnchor="end" fontSize="10" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{fmt(t)}</text></g>)}
        {hv != null && <rect x={X(hv) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="var(--row-hover)" />}
        {series.map((s) => (
          <g key={s.key}>
            {runs(s).map((r, k) => r.length > 1 && <path key={k} d={r.map(([x, y], j) => `${j ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("")} fill="none" stroke={s.color} strokeWidth={s.dotted ? 2.4 : 2.6} strokeDasharray={s.dotted ? "1.5 6" : undefined} strokeLinecap="round" strokeLinejoin="round" />)}
            {s.values.map((v, i) => v == null ? null : s.marker === "circle"
              ? <circle key={i} cx={X(i)} cy={Y(v)} r={flags?.[i] && !s.dotted ? 5.2 : 3.8} fill={flags?.[i] && !s.dotted ? "var(--s1)" : s.color} stroke={flags?.[i] && !s.dotted ? "var(--warn)" : s.color} strokeWidth={flags?.[i] && !s.dotted ? 2.4 : 1} />
              : <rect key={i} x={X(i) - 3.6} y={Y(v) - 3.6} width={7.2} height={7.2} rx={1.2} fill="var(--s1)" stroke={s.color} strokeWidth={2} />)}
          </g>
        ))}
        {labels.map((_, i) => notes?.[i] && series.every((s) => s.values[i] == null) ? <text key={"n" + i} x={X(i)} y={Y(Math.max(0, bot)) - 6} textAnchor="middle" fontSize="12" fill="var(--faint)">–</text> : null)}
        {labels.map((l, i) => ((n - 1 - i) % every === 0) && <text key={"l" + i} x={X(i)} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--faint)">{l.replace(/^(\w{3}) (\d{2})(\d{2})$/, "$1 '$3")}</text>)}
        {labels.map((l, i) => (
          <rect key={"h" + i} x={X(i) - (W - pl - pr) / n / 2} y={pt} width={(W - pl - pr) / n} height={H - pt - pb} fill="transparent" tabIndex={0} onMouseEnter={() => setHv(i)} onFocus={() => setHv(i)} onBlur={() => setHv(null)} style={{ outline: "none" }}
            aria-label={`${l}: ${series.map((s) => `${s.label} ${s.values[i] == null ? "not available" : fmt(s.values[i] as number)}`).join(", ")}${flags?.[i] ? ", low-quality earnings year" : ""}${notes?.[i] ? `. ${notes[i]}` : ""}`} />
        ))}
      </svg>
      {hv != null && (
        <div className="mb-tip" style={{ left: `${Math.min(80, Math.max(16, (X(hv) / W) * 100))}%` }}>
          <b>{labels[hv]}{flags?.[hv] ? " ⚑ low-quality earnings" : ""}</b>
          {series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}<em>{s.values[hv] == null ? "–" : fmt(s.values[hv] as number)}</em></span>)}
          {notes?.[hv] && <small className="faint">{notes[hv]}</small>}
        </div>)}
    </div>
  );
}
