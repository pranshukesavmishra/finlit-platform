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
    const C = 150, score = overall ?? 0;
    s.setAttribute("viewBox", "-46 -14 392 328");
    const defs = el("defs", {}, s);
    const g = el("linearGradient", { id: "dg", gradientUnits: "userSpaceOnUse", x1: 40, y1: 260, x2: 260, y2: 40 }, defs);
    el("stop", { offset: 0, "stop-color": "#C9952F" }, g); el("stop", { offset: 0.55, "stop-color": "#EBC46A" }, g); el("stop", { offset: 1, "stop-color": "#FBE7A8" }, g);
    const dg = el("radialGradient", { id: "dd", cx: ".5", cy: ".4", r: ".7" }, defs);
    el("stop", { offset: 0, "stop-color": "#13244A" }, dg); el("stop", { offset: 1, "stop-color": "#091226" }, dg);
    const gl = el("filter", { id: "dglow", x: "-30%", y: "-30%", width: "160%", height: "160%" }, defs); el("feGaussianBlur", { stdDeviation: 4 }, gl);
    // deep navy disc with a fine gold rim: no pale glow behind the number
    el("circle", { cx: C, cy: C, r: 80, fill: "url(#dd)", stroke: "#EBC46A", "stroke-opacity": 0.55, "stroke-width": 1.5 }, s);
    el("circle", { cx: C, cy: C, r: 74, fill: "none", stroke: "#EBC46A", "stroke-opacity": 0.18, "stroke-width": 1, "stroke-dasharray": "1 5", class: "dial-spin" }, s);
    // tick ring
    for (let i = 0; i < 100; i++) {
      const major = i % 25 === 0, mid = i % 5 === 0, lit = i < score;
      const [x0, y0] = polar(C, C, 96, i * 3.6), [x1, y1] = polar(C, C, major ? 87 : mid ? 90 : 92.5, i * 3.6);
      el("line", { x1: x0, y1: y0, x2: x1, y2: y1, stroke: lit ? "#EBC46A" : "#3A4B70", "stroke-width": major ? 1.8 : 1.1, opacity: lit ? (major ? 1 : mid ? 0.9 : 0.55) : major ? 0.9 : 0.5 }, s);
    }
    // main score arc: thick, gradient, glowing
    el("circle", { cx: C, cy: C, r: 105, fill: "none", stroke: "#16254A", "stroke-width": 9 }, s);
    if (score > 0) {
      const d = arcPath(C, C, 105, 0.01, Math.max(0.02, score * 3.6));
      const glow = el("path", { d, fill: "none", stroke: "#EBC46A", "stroke-width": 12, "stroke-linecap": "round", opacity: 0.45, filter: "url(#dglow)" }, s);
      const comp = el("path", { d, fill: "none", stroke: "url(#dg)", "stroke-width": 9, "stroke-linecap": "round" }, s);
      const [ex, ey] = polar(C, C, 105, score * 3.6);
      const knob = el("circle", { cx: ex, cy: ey, r: 7, fill: "#FBE7A8", stroke: "#091226", "stroke-width": 3 }, s);
      if (first && !reduced()) {
        [comp, glow].forEach((p) => { const len = p.getTotalLength(); p.style.strokeDasharray = String(len); p.style.strokeDashoffset = String(len); p.style.transition = "stroke-dashoffset 1.2s cubic-bezier(.16,1,.3,1) .2s"; });
        knob.style.opacity = "0"; knob.style.transition = "opacity .35s ease 1.2s";
        requestAnimationFrame(() => requestAnimationFrame(() => { comp.style.strokeDashoffset = "0"; glow.style.strokeDashoffset = "0"; knob.style.opacity = "1"; }));
      }
    }
    pillars.forEach((p, i) => {
      const a0 = i * 72 + 3, a1 = (i + 1) * 72 - 3, sc = p.score ?? 0, af = a0 + ((a1 - a0) * sc) / 100;
      const col = css(PILLAR_COLOR[p.key] || "--gold");
      el("path", { d: arcPath(C, C, 126, a0, a1), fill: "none", stroke: "#16254A", "stroke-width": 7, "stroke-linecap": "round" }, s);
      const seg = el("path", { d: arcPath(C, C, 126, a0, Math.max(a0 + 0.1, af)), fill: "none", stroke: col, "stroke-width": active === p.key ? 10 : 7, "stroke-linecap": "round", style: "cursor:pointer;transition:stroke-width .2s" }, s);
      if (first && !reduced()) { const len = seg.getTotalLength(); seg.style.strokeDasharray = String(len); seg.style.strokeDashoffset = String(len); seg.style.transition = `stroke-dashoffset 1s cubic-bezier(.16,1,.3,1) ${0.4 + i * 0.08}s, stroke-width .2s`; requestAnimationFrame(() => requestAnimationFrame(() => (seg.style.strokeDashoffset = "0"))); }
      seg.addEventListener("click", () => onPillar(p.key));
      const mid = (a0 + a1) / 2, [lx, ly] = polar(C, C, 148, mid);
      const t = el("text", { x: lx, y: ly + 3.5, "text-anchor": mid > 20 && mid < 160 ? "start" : mid > 200 && mid < 340 ? "end" : "middle", fill: col, "font-size": 10.5, "font-family": "IBM Plex Sans, sans-serif", "font-weight": 700, "letter-spacing": ".06em" }, s);
      t.textContent = `${SHORT[p.key] || p.label.toUpperCase()} ${p.score ?? "—"}`;
    });
  }, [overall, pillars, active]);

  return (
    <div className="dial" ref={wrap} role="img" aria-label={`FinLit research score ${overall ?? "not available"} out of 100, ${bandLabel}. ${pillars.map((p) => `${p.label} ${p.score ?? "n/a"}`).join(", ")}.`}>
      <svg ref={svg} aria-hidden="true" />
      <div className="dcenter"><div className="n">{overall == null ? "—" : shown}</div><div className="of">/ 100</div></div>
      <div className="dial-band"><span className={"vd " + (bandLabel === "Strong" ? "strong" : bandLabel === "Healthy" ? "healthy" : bandLabel === "Mixed" ? "mixed" : "weak")}>{bandLabel}</span><span className="faint">overall research score</span></div>
    </div>
  );
}
