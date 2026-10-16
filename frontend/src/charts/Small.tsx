import { arcPath, css, el, polar, sparkPath, vgrad } from "../lib/svg";
import { useChart } from "./useChart";
import type { Series } from "../lib/api";

export function Spark({ values, color, w = 96, h = 34 }: { values: Series; color: string; w?: number; h?: number }) {
  const v = values.filter((x) => x != null);
  if (v.length < 2) return <svg className="sp" viewBox={`0 0 ${w} ${h}`} aria-hidden="true" />;
  const { d, X, last } = sparkPath(values, w, h, 3);
  const id = "sp" + Math.abs([...color + d].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7));
  const n = values.length;
  return (
    <svg className="sp" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".35" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={`${d}L${X(n - 1)},${h}L${X(0)},${h}Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="3" fill={color} />
    </svg>
  );
}

/** RSI half-dial with oversold/neutral/overbought zones and a needle. */
export function RsiGauge({ value }: { value: number }) {
  const { wrap, svg } = useChart((s) => {
    s.setAttribute("viewBox", "0 0 260 176");
    const cx = 130, cy = 118, r = 100;
    const zone = (a: number, b: number, c: string, o: number) => el("path", { d: arcPath(cx, cy, r, -90 + a * 1.8, -90 + b * 1.8), fill: "none", stroke: css(c), "stroke-width": 16, opacity: o }, s);
    zone(0.5, 29.5, "--gain", 0.85); zone(30.5, 69.5, "--c5", 0.35); zone(70.5, 99.5, "--loss", 0.85);
    [0, 30, 70, 100].forEach((t) => { const [x, y] = polar(cx, cy, r + 18, -90 + t * 1.8); el("text", { x, y: y + 4, "text-anchor": "middle", fill: css("--faint"), "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, s).textContent = String(t); });
    const [nx, ny] = polar(cx, cy, r - 24, -90 + Math.max(0, Math.min(100, value)) * 1.8);
    el("line", { x1: cx, y1: cy, x2: nx, y2: ny, stroke: css("--text"), "stroke-width": 3, "stroke-linecap": "round" }, s);
    el("circle", { cx, cy, r: 8, fill: css("--text") }, s); el("circle", { cx, cy, r: 3, fill: css("--s1") }, s);
    el("text", { x: cx, y: cy + 36, "text-anchor": "middle", "font-family": "Newsreader, Georgia, serif", "font-size": 34, fill: css("--text") }, s).textContent = value.toFixed(1);
    const zoneTxt = value < 30 ? "OVERSOLD ZONE" : value > 70 ? "OVERBOUGHT ZONE" : "NEUTRAL ZONE";
    el("text", { x: cx, y: cy + 54, "text-anchor": "middle", "font-size": 10.5, "font-weight": 700, "letter-spacing": ".1em", fill: css(value < 30 ? "--gain" : value > 70 ? "--loss" : "--muted"), "font-family": "IBM Plex Sans, sans-serif" }, s).textContent = zoneTxt;
  }, [value]);
  return <div className="gauge-wrap" ref={wrap}><svg ref={svg} role="img" aria-label={`RSI ${value.toFixed(1)}`} /></div>;
}

/** Ownership donut. */
export function Donut({ slices, centerValue, centerLabel }: { slices: { v: number; color: string }[]; centerValue: string; centerLabel: string }) {
  const { wrap, svg } = useChart((s) => {
    s.setAttribute("viewBox", "0 0 240 240");
    const C = 120, r = 88, c = 2 * Math.PI * r; let off = 0;
    el("circle", { cx: C, cy: C, r, fill: "none", stroke: css("--s3"), "stroke-width": 30 }, s);
    slices.forEach(({ v, color }) => { const len = (v / 100) * c; el("circle", { cx: C, cy: C, r, fill: "none", stroke: css(color), "stroke-width": 30, "stroke-dasharray": `${Math.max(0, len - 3)} ${c}`, "stroke-dashoffset": -off, transform: `rotate(-90 ${C} ${C})` }, s); off += len; });
    el("circle", { cx: C, cy: C, r: 70, fill: css("--s1") }, s);
    el("text", { x: C, y: C - 2, "text-anchor": "middle", "font-family": "Newsreader, Georgia, serif", "font-size": 36, fill: css("--text") }, s).textContent = centerValue;
    el("text", { x: C, y: C + 20, "text-anchor": "middle", "font-size": 11, "font-weight": 600, "letter-spacing": ".08em", fill: css("--muted"), "font-family": "IBM Plex Sans, sans-serif" }, s).textContent = centerLabel;
  }, [slices, centerValue, centerLabel]);
  return <div className="donut-wrap" ref={wrap} style={{ maxWidth: 260 }}><svg ref={svg} role="img" aria-label={`${centerLabel} ${centerValue}`} style={{ width: "100%", height: "auto" }} /></div>;
}
void vgrad;
