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

/** RSI gauge: a glowing progress arc with a marker, tick scale and a plain-English caption.
 *  Colours say "cold / balanced / hot", not "good / bad": an oversold stock is not automatically a bargain. */
export function RsiGauge({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  const zone = v < 30 ? "cold" : v > 70 ? "hot" : "mid";
  const { wrap, svg } = useChart((s) => {
    s.setAttribute("viewBox", "0 0 260 170");
    const cx = 130, cy = 122, r = 104, A0 = -100, A1 = 100, ang = (t: number) => A0 + (t / 100) * (A1 - A0);
    const cold = css("--info"), hot = css("--warn"), mid = css("--gold"), text = css("--text");
    const col = zone === "cold" ? cold : zone === "hot" ? hot : mid;
    const defs = el("defs", {}, s);
    const g = el("linearGradient", { id: "rsig", gradientUnits: "userSpaceOnUse", x1: cx - r, y1: 0, x2: cx + r, y2: 0 }, defs);
    const light = document.documentElement.dataset.theme === "light";
    el("stop", { offset: 0, "stop-color": cold }, g); el("stop", { offset: 0.5, "stop-color": mid }, g); el("stop", { offset: 1, "stop-color": hot }, g);
    const glow = el("filter", { id: "rsiglow", x: "-30%", y: "-30%", width: "160%", height: "160%" }, defs); el("feGaussianBlur", { stdDeviation: 5 }, glow);
    // track and faint zone bands
    el("path", { d: arcPath(cx, cy, r, A0, A1), fill: "none", stroke: css("--s3"), "stroke-width": 16, "stroke-linecap": "round" }, s);
    el("path", { d: arcPath(cx, cy, r, ang(0), ang(30)), fill: "none", stroke: cold, "stroke-width": 16, "stroke-linecap": "round", opacity: 0.28 }, s);
    el("path", { d: arcPath(cx, cy, r, ang(70), ang(100)), fill: "none", stroke: hot, "stroke-width": 16, "stroke-linecap": "round", opacity: 0.28 }, s);
    // progress (glow copy + crisp copy)
    if (v > 0.5) for (const [w, extra] of (light ? [[16, {}]] : [[16, { filter: "url(#rsiglow)", opacity: 0.55 }], [16, {}]]) as [number, Record<string, string | number>][]) {
      const p = el("path", { d: arcPath(cx, cy, r, A0, ang(v)), fill: "none", stroke: "url(#rsig)", "stroke-width": w, "stroke-linecap": "round", pathLength: 1, class: "g-prog", ...extra }, s);
      p.setAttribute("stroke-dasharray", "1");
    }
    // ticks
    for (let t = 0; t <= 100; t += 10) {
      const major = t === 30 || t === 70 || t === 0 || t === 100, [x0, y0] = polar(cx, cy, r - 15, ang(t)), [x1, y1] = polar(cx, cy, r - (major ? 24 : 20), ang(t));
      el("line", { x1: x0, y1: y0, x2: x1, y2: y1, stroke: css(major ? "--muted" : "--border-strong"), "stroke-width": major ? 1.8 : 1.2, "stroke-linecap": "round" }, s);
    }
    ([[30, "30"], [70, "70"]] as const).forEach(([t, l]) => { const [x, y] = polar(cx, cy, r - 36, ang(t)); el("text", { x, y: y + 4, "text-anchor": "middle", fill: css("--faint"), "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, s).textContent = l; });
    // marker
    const [mx, my] = polar(cx, cy, r, ang(v));
    const m = el("g", { class: "g-knob" }, s);
    el("circle", { cx: mx, cy: my, r: 15, fill: col, opacity: 0.25 }, m); el("circle", { cx: mx, cy: my, r: 10.5, fill: css("--s1"), stroke: col, "stroke-width": 4 }, m);
    // value
    el("text", { x: cx, y: cy - 4, "text-anchor": "middle", "font-family": "Newsreader, Georgia, serif", "font-size": 50, "font-weight": 300, fill: text }, s).textContent = v.toFixed(1);
    el("text", { x: cx, y: cy + 18, "text-anchor": "middle", "font-size": 10.5, "font-weight": 600, "letter-spacing": ".14em", fill: css("--faint"), "font-family": "IBM Plex Sans, sans-serif" }, s).textContent = "RSI · 14 DAYS";
    ([[0, "0"], [100, "100"]] as const).forEach(([t, l]) => { const [x, y] = polar(cx, cy, r, ang(t)); el("text", { x, y: y + 26, "text-anchor": "middle", "font-size": 10, fill: css("--faint"), "font-family": "IBM Plex Mono, monospace" }, s).textContent = l; });
  }, [value]);
  const copy = {
    cold: ["Oversold", "Sold heavily lately. Prices often bounce from here, but a falling stock can keep falling."],
    mid: ["Balanced", "Neither stretched up nor down. Momentum alone gives no strong signal."],
    hot: ["Overbought", "Bought heavily lately. Prices often cool off from here, but strong stocks can stay hot."],
  }[zone];
  return (
    <div className={"rsi rsi-" + zone}>
      <div className="gauge-wrap" ref={wrap}><svg ref={svg} role="img" aria-label={`RSI ${v.toFixed(1)}, ${copy[0]}`} /></div>
      <div className="rsi-zone"><b>{copy[0]}</b><span>{copy[1]}</span></div>
    </div>
  );
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
