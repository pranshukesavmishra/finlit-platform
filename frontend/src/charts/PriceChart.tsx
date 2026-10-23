import { useRef } from "react";
import { css, drawIn, el, niceTicks, reduced, vgrad } from "../lib/svg";
import { dateIN, nf } from "../lib/format";
import { useChart } from "./useChart";
import { With3D } from "./With3D";
import type { PriceRange } from "../lib/api";

/** Close line with 50/200-day averages (computed server-side on full history) and volume bars. */
export function PriceChart({ data, showEma50, showEma200, showVol }: { data: PriceRange; showEma50: boolean; showEma200: boolean; showVol: boolean }) {
  const tip = useRef<HTMLDivElement>(null);
  const s = data.series;
  const { wrap, svg } = useChart((svgEl, W, first) => {
    const n = s.t.length;
    if (n < 2) return;
    const H = W < 520 ? 260 : 470, pl = 4, pr = 56, pt = 16, pb = 28, volH = showVol ? 46 : 0;
    svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`); svgEl.style.height = H + "px";
    const vals = [...s.c, ...(showEma50 ? s.ema50 : []), ...(showEma200 ? s.ema200 : [])].filter((v): v is number => v != null);
    let mn = Math.min(...vals), mx = Math.max(...vals); const pad = (mx - mn) * 0.1; mn -= pad; mx += pad;
    const ph = H - pt - pb - volH - (volH ? 10 : 0), li = n - 1;
    const x = (i: number) => pl + (i / li) * (W - pl - pr), y = (p: number) => pt + (1 - (p - mn) / (mx - mn)) * ph;
    const area = vgrad(svgEl, css("--area"), 0.32, 0);
    niceTicks(mn, mx, 4).forEach((p) => {
      if (p < mn || p > mx) return;
      el("line", { x1: pl, x2: W - pr, y1: y(p), y2: y(p), stroke: css("--border"), "stroke-dasharray": "3 5" }, svgEl);
      el("text", { x: W - pr + 10, y: y(p) + 4, fill: css("--faint"), "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, svgEl).textContent = "₹" + Math.round(p).toLocaleString("en-IN");
    });
    const ticks = Math.max(2, Math.min(6, Math.floor((W - pl - pr) / 100)));
    for (let i = 0; i <= ticks; i++) {
      const idx = Math.round((i / ticks) * li);
      const t = el("text", { x: x(idx), y: H - 6, fill: css("--faint"), "font-size": 11, "text-anchor": i === 0 ? "start" : i === ticks ? "end" : "middle", "font-family": "IBM Plex Mono, monospace" }, svgEl);
      t.textContent = dateIN(s.t[idx], data.range === "1M" ? { day: "numeric", month: "short" } : { month: "short", year: "2-digit" });
    }
    if (showVol) {
      const vv = s.v.map((v) => v ?? 0), vmax = Math.max(...vv, 1), base = H - pb, bw = Math.max(1.2, (W - pl - pr) / n - 1.4), vg = vgrad(svgEl, css("--c4"), 0.55, 0.15);
      vv.forEach((v, i) => el("rect", { x: x(i) - bw / 2, y: base - (v / vmax) * volH, width: bw, height: (v / vmax) * volH, rx: Math.min(2, bw / 2), fill: vg }, svgEl));
    }
    const line = s.c.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join("");
    el("path", { d: `${line}L${x(li)},${pt + ph}L${x(0)},${pt + ph}Z`, fill: area }, svgEl);
    const ema = (arr: (number | null)[], color: string, dash: string) => {
      let d = ""; arr.forEach((v, i) => { if (v != null) d += `${d ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; });
      if (d) el("path", { d, fill: "none", stroke: color, "stroke-width": 1.6, "stroke-dasharray": dash }, svgEl);
    };
    if (showEma50) ema(s.ema50, css("--c2"), "5 4");
    if (showEma200) ema(s.ema200, css("--c3"), "");
    drawIn(el("path", { d: line, fill: "none", stroke: css("--line"), "stroke-width": 2.2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svgEl), first);
    let hi = 0, lo = 0; s.c.forEach((p, i) => { if (p > s.c[hi]) hi = i; if (p < s.c[lo]) lo = i; });
    ([[hi, "High", -12, "--gain"], [lo, "Low", 20, "--loss"]] as const).forEach(([i, lab, dy, c]) => {
      el("circle", { cx: x(i), cy: y(s.c[i]), r: 3.5, fill: css(c), stroke: css("--s1"), "stroke-width": 1.5 }, svgEl);
      el("text", { x: Math.min(Math.max(x(i), 48), W - pr - 48), y: y(s.c[i]) + dy, "text-anchor": "middle", "font-size": 11, "font-weight": 600, fill: css(c), "font-family": "IBM Plex Sans, sans-serif" }, svgEl).textContent = `${lab} ₹${nf(s.c[i], 0)}`;
    });
    el("circle", { cx: x(li), cy: y(s.c[li]), r: 9, fill: css("--gold"), opacity: 0.2 }, svgEl);
    el("circle", { cx: x(li), cy: y(s.c[li]), r: 4.5, fill: css("--gold"), stroke: css("--s1"), "stroke-width": 2 }, svgEl);
    el("rect", { x: W - pr + 4, y: y(s.c[li]) - 10, width: 50, height: 20, rx: 6, fill: css("--gold") }, svgEl);
    el("text", { x: W - pr + 29, y: y(s.c[li]) + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 700, fill: "#1A1405", "font-family": "IBM Plex Sans, sans-serif" }, svgEl).textContent = nf(s.c[li], 0);

    const cross = el("line", { y1: pt, y2: pt + ph, stroke: css("--border-strong"), "stroke-dasharray": "3 3", visibility: "hidden" }, svgEl);
    const dot = el("circle", { r: 5, fill: css("--line"), stroke: css("--s1"), "stroke-width": 2, visibility: "hidden" }, svgEl);
    const first0 = s.c[0];
    svgEl.onpointermove = (ev) => {
      const r = svgEl.getBoundingClientRect(), mxp = ((ev.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(li, Math.round(((mxp - pl) / (W - pl - pr)) * li))), px = x(i), py = y(s.c[i]);
      cross.setAttribute("x1", String(px)); cross.setAttribute("x2", String(px)); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", String(px)); dot.setAttribute("cy", String(py)); dot.setAttribute("visibility", "visible");
      const t = tip.current; if (!t) return;
      const ch = (s.c[i] / first0 - 1) * 100;
      t.hidden = false; t.style.left = Math.min(Math.max((px / W) * r.width, 80), r.width - 80) + "px"; t.style.top = Math.max((py / H) * r.height, 70) + "px";
      t.replaceChildren();
      const add = (txt: string, cls = "", tag = "span") => { const e = document.createElement(tag); e.className = cls; e.textContent = txt; t.appendChild(e); };
      add((data.grain === "weekly" ? "Week of " : "") + dateIN(s.t[i]), "faint"); add("₹" + nf(s.c[i]), "", "b");
      add(`${ch >= 0 ? "▲ +" : "▼ −"}${nf(Math.abs(ch), 1)}% from start`, ch >= 0 ? "pos" : "neg");
      if (showEma50 && s.ema50[i] != null) add(`EMA 50 ₹${nf(s.ema50[i] as number)}`, "muted", "div");
      if (showEma200 && s.ema200[i] != null) add(`EMA 200 ₹${nf(s.ema200[i] as number)}`, "muted", "div");
    };
    svgEl.onpointerleave = () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); if (tip.current) tip.current.hidden = true; };
  }, [data, showEma50, showEma200, showVol]);
  const flat = <div className="chart" ref={wrap}><svg ref={svg} role="img" aria-label={`Price from ₹${nf(s.c[0])} to ₹${nf(s.c[s.c.length - 1])} over ${data.range}`} /><div className="tip" ref={tip} hidden /></div>;
  const when = (t: string) => dateIN(t, data.range === "1M" ? { day: "numeric", month: "short" } : { month: "short", year: "2-digit" });
  const extra = [...(showEma50 ? [{ label: "50-day average", values: s.ema50 }] : []), ...(showEma200 ? [{ label: "200-day average", values: s.ema200 }] : [])];
  return <With3D flat={flat} label={`Price from ₹${nf(s.c[0])} to ₹${nf(s.c[s.c.length - 1])} over ${data.range}, in 3D`}
    hint="How to read it: time runs left to right and the price becomes a solid ribbon, with rupees on the tall scale at the left. Move the pointer over it to read the price on any date."
    spec={s.t.length > 1 ? { kind: "ribbon", x: s.t.map(when), series: [{ label: "Price", values: s.c }, ...extra], fmt: (v) => "₹" + Math.round(v).toLocaleString("en-IN") } : null} />;
}
void reduced;
