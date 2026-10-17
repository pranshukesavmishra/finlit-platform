import { useEffect, useState } from "react";
import { arcPath, css, el, polar, reduced } from "../lib/svg";
import { useChart } from "./useChart";
import type { PillarSummary } from "../lib/api";

const PILLAR_COLOR: Record<string, string> = { quality: "--p-quality", growth: "--p-growth", profitability: "--p-profit", balance: "--p-balance", technical: "--p-tech" };
const SHORT: Record<string, string> = { quality: "QUALITY", growth: "GROWTH", profitability: "PROFIT", balance: "BALANCE", technical: "TECHNICAL" };

/** The research-score dial: 100 ticks for the overall score, one coloured arc per pillar. */
export function Dial({ overall, pillars, onPillar, active, bandLabel }: {
  overall: number | null; pillars: PillarSummary[]; onPillar: (key: string) => void; active: string | null; bandLabel: string;
}) {
  const [shown, setShown] = useState(reduced() ? overall ?? 0 : 0);
  useEffect(() => {
    if (overall == null) return;
    if (reduced()) { setShown(overall); return; }
    const t0 = performance.now() + 200;
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, Math.max(0, (now - t0) / 1100));
      setShown(Math.round(overall * (1 - Math.pow(1 - k, 4))));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [overall]);

  const { wrap, svg } = useChart((s, _w, first) => {
    const C = 150, score = overall ?? 0, anim = first && !reduced();
    s.setAttribute("viewBox", "-46 -30 392 360");
    const defs = el("defs", {}, s);
    const lg = (id: string, stops: [number, string][], x2 = 1, y2 = 1) => { const g = el("linearGradient", { id, gradientUnits: "userSpaceOnUse", x1: 40, y1: 260, x2: 260 * x2, y2: 40 * y2 }, defs); stops.forEach(([o, c]) => el("stop", { offset: o, "stop-color": c }, g)); };
    lg("dg", [[0, "#8A6A25"], [0.5, "#D4B26A"], [1, "#F3E6BF"]]);
    const disc = el("radialGradient", { id: "dd", cx: ".5", cy: ".35", r: ".8" }, defs);
    [[0, "#494130"], [0.55, "#2D281E"], [1, "#191610"]].forEach(([o, c]) => el("stop", { offset: o as number, "stop-color": c as string }, disc));
    const sheen = el("linearGradient", { id: "dsh", x1: 0, y1: 0, x2: 0, y2: 1 }, defs); el("stop", { offset: 0, "stop-color": "#fff", "stop-opacity": 0.22 }, sheen); el("stop", { offset: 1, "stop-color": "#fff", "stop-opacity": 0 }, sheen);
    const glow = el("filter", { id: "dglow", x: "-30%", y: "-30%", width: "160%", height: "160%" }, defs); el("feGaussianBlur", { stdDeviation: 5 }, glow);
    const soft = el("filter", { id: "dsoft", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs); el("feGaussianBlur", { stdDeviation: 14 }, soft);
    // ambient glow under the whole dial
    el("circle", { cx: C, cy: C, r: 120, fill: "#D4B26A", opacity: 0.1, filter: "url(#dsoft)" }, s);
    // outer ring of pillar arcs: grooved track, coloured fill with glow and end cap
    pillars.forEach((p, i) => {
      const a0 = i * 72 + 4, a1 = (i + 1) * 72 - 4, sc = p.score ?? 0, af = a0 + ((a1 - a0) * sc) / 100;
      const col = css(PILLAR_COLOR[p.key] || "--gold", s), hot = active === p.key;
      const gid = `pg${i}`; const pg = el("linearGradient", { id: gid, x1: 0, y1: 0, x2: 1, y2: 1 }, defs);
      el("stop", { offset: 0, "stop-color": col, "stop-opacity": 0.75 }, pg); el("stop", { offset: 1, "stop-color": col }, pg);
      el("path", { d: arcPath(C, C, 128, a0, a1), fill: "none", stroke: "#383326", "stroke-width": 11, "stroke-linecap": "round" }, s);
      el("path", { d: arcPath(C, C, 128, a0, a1), fill: "none", stroke: col, "stroke-width": 11, "stroke-linecap": "round", opacity: 0.1 }, s);
      const fillD = arcPath(C, C, 128, a0, Math.max(a0 + 0.1, af));
      const gl = el("path", { d: fillD, fill: "none", stroke: col, "stroke-width": 11, "stroke-linecap": "round", opacity: hot ? 0.7 : 0.4, filter: "url(#dglow)" }, s);
      const seg = el("path", { d: fillD, fill: "none", stroke: `url(#${gid})`, "stroke-width": hot ? 13 : 11, "stroke-linecap": "round", style: "cursor:pointer;transition:stroke-width .2s" }, s);
      const [ex, ey] = polar(C, C, 128, af); const dot = el("circle", { cx: ex, cy: ey, r: 3.4, fill: "#fff", opacity: 0.95 }, s);
      if (anim) { [seg, gl].forEach((q) => { const len = q.getTotalLength(); q.style.strokeDasharray = String(len); q.style.strokeDashoffset = String(len); q.style.transition = `stroke-dashoffset 1s cubic-bezier(.16,1,.3,1) ${0.35 + i * 0.09}s`; }); dot.style.opacity = "0"; dot.style.transition = `opacity .3s ease ${1.2 + i * 0.09}s`; requestAnimationFrame(() => requestAnimationFrame(() => { seg.style.strokeDashoffset = "0"; gl.style.strokeDashoffset = "0"; dot.style.opacity = "0.95"; })); }
      seg.addEventListener("click", () => onPillar(p.key));
      // label: name over a big score, placed radially
      const mid = (a0 + a1) / 2, [lx, ly] = polar(C, C, 150, mid), anchor = mid > 20 && mid < 160 ? "start" : mid > 200 && mid < 340 ? "end" : "middle";
      const dy = mid > 100 && mid < 260 ? 10 : mid < 80 || mid > 280 ? -2 : 4;
      const t1 = el("text", { x: lx + (anchor === "start" ? 4 : anchor === "end" ? -4 : 0), y: ly + dy - 8, "text-anchor": anchor, fill: col, "font-size": 10, "font-family": "IBM Plex Sans, sans-serif", "font-weight": 700, "letter-spacing": ".14em" }, s); t1.textContent = SHORT[p.key] || p.label.toUpperCase();
      const t2 = el("text", { x: lx + (anchor === "start" ? 4 : anchor === "end" ? -4 : 0), y: ly + dy + 10, "text-anchor": anchor, fill: "#F6F5F2", "font-size": 19, "font-family": "Newsreader Variable, Newsreader, Georgia, serif" }, s); t2.textContent = p.score == null ? "—" : String(p.score);
    });
    // tick ring: 100 ticks that light up to the score
    for (let i = 0; i < 100; i++) {
      const major = i % 25 === 0, mid = i % 5 === 0, lit = i < score;
      const [x0, y0] = polar(C, C, 104, i * 3.6), [x1, y1] = polar(C, C, major ? 92 : mid ? 96 : 99, i * 3.6);
      el("line", { x1: x0, y1: y0, x2: x1, y2: y1, stroke: lit ? `hsl(${42 - (i / Math.max(score, 1)) * 6} 80% ${48 + (i / Math.max(score, 1)) * 18}%)` : "#5A5444", "stroke-width": major ? 2 : 1.2, opacity: lit ? 1 : major ? 0.9 : 0.55, "stroke-linecap": "round" }, s);
    }
    [0, 25, 50, 75].forEach((n) => { const [x, y] = polar(C, C, 84, n * 3.6); el("text", { x, y: y + 3, "text-anchor": "middle", "font-size": 8.5, "font-family": "IBM Plex Mono, monospace", fill: "#97907F" }, s).textContent = String(n); });
    // score arc on the inside edge of the tick ring
    el("circle", { cx: C, cy: C, r: 110, fill: "none", stroke: "#3A3426", "stroke-width": 6 }, s);
    if (score > 0) {
      const dd = arcPath(C, C, 110, 0.01, Math.max(0.02, score * 3.6));
      const g2 = el("path", { d: dd, fill: "none", stroke: "#D4B26A", "stroke-width": 9, "stroke-linecap": "round", opacity: 0.5, filter: "url(#dglow)" }, s);
      const c2 = el("path", { d: dd, fill: "none", stroke: "url(#dg)", "stroke-width": 6, "stroke-linecap": "round" }, s);
      const [kx, ky] = polar(C, C, 110, score * 3.6);
      el("circle", { cx: kx, cy: ky, r: 11, fill: "#D4B26A", opacity: 0.28 }, s);
      const knob = el("circle", { cx: kx, cy: ky, r: 6.5, fill: "#F6ECCF", stroke: "#8A5E12", "stroke-width": 2.5 }, s);
      if (anim) { [c2, g2].forEach((q) => { const len = q.getTotalLength(); q.style.strokeDasharray = String(len); q.style.strokeDashoffset = String(len); q.style.transition = "stroke-dashoffset 1.3s cubic-bezier(.16,1,.3,1) .2s"; }); knob.style.opacity = "0"; knob.style.transition = "opacity .3s ease 1.3s"; requestAnimationFrame(() => requestAnimationFrame(() => { c2.style.strokeDashoffset = "0"; g2.style.strokeDashoffset = "0"; knob.style.opacity = "1"; })); }
    }
    // glass disc in the middle
    el("circle", { cx: C, cy: C, r: 76, fill: "url(#dd)", stroke: "#D4B26A", "stroke-opacity": 0.6, "stroke-width": 1.6 }, s);
    el("circle", { cx: C, cy: C, r: 70, fill: "none", stroke: "#D4B26A", "stroke-opacity": 0.22, "stroke-width": 1, "stroke-dasharray": "1 5", class: "dial-spin" }, s);
  }, [overall, pillars, active]);

  return (
    <div className="dial" ref={wrap} role="img" aria-label={`FinLit research score ${overall ?? "not available"} out of 100, ${bandLabel}. ${pillars.map((p) => `${p.label} ${p.score ?? "n/a"}`).join(", ")}.`}>
      <svg ref={svg} aria-hidden="true" />
      <div className="dcenter"><div className="n">{overall == null ? "—" : shown}</div><div className="of">/ 100</div></div>
      <div className="dial-band"><span className={"vd " + (bandLabel === "Strong" ? "strong" : bandLabel === "Healthy" ? "healthy" : bandLabel === "Mixed" ? "mixed" : "weak")}>{bandLabel}</span><span className="faint">overall research score</span></div>
    </div>
  );
}
