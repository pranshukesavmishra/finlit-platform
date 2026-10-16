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
    const g = el("linearGradient", { id: "dg", x1: 0, y1: 0, x2: 1, y2: 1 }, defs);
    el("stop", { offset: 0, "stop-color": css("--gold-2") }, g); el("stop", { offset: 1, "stop-color": css("--gold-deep") }, g);
    const rg = el("radialGradient", { id: "df" }, defs);
    el("stop", { offset: 0, "stop-color": css("--gold"), "stop-opacity": 0.12 }, rg); el("stop", { offset: 1, "stop-color": css("--gold"), "stop-opacity": 0 }, rg);
    el("circle", { cx: C, cy: C, r: 100, fill: "url(#df)" }, s);
    const dg = el("radialGradient", { id: "dd", cx: ".5", cy: ".35", r: ".75" }, defs);
    el("stop", { offset: 0, "stop-color": "#EBC46A", "stop-opacity": 0.22 }, dg); el("stop", { offset: 0.6, "stop-color": "#0F1C38", "stop-opacity": 0.96 }, dg); el("stop", { offset: 1, "stop-color": "#0A1530", "stop-opacity": 1 }, dg);
    el("circle", { cx: C, cy: C, r: 79, fill: "url(#dd)", stroke: css("--gold"), "stroke-opacity": 0.35, "stroke-width": 1.2 }, s);
    el("circle", { cx: C, cy: C, r: 72, fill: "none", stroke: css("--gold"), "stroke-opacity": 0.28, "stroke-width": 1, "stroke-dasharray": "2 6", class: "dial-spin" }, s);
    el("circle", { cx: C, cy: C, r: 114, fill: "none", stroke: css("--border-strong"), "stroke-width": 1, "stroke-dasharray": "1 7", class: "dial-spin rev" }, s);
    for (let i = 0; i < 100; i++) {
      const major = i % 25 === 0, mid = i % 5 === 0, lit = i < score;
      const [x0, y0] = polar(C, C, 96, i * 3.6), [x1, y1] = polar(C, C, major ? 85 : mid ? 89 : 92, i * 3.6);
      el("line", { x1: x0, y1: y0, x2: x1, y2: y1, stroke: lit ? css("--gold") : css("--faint"), "stroke-width": major ? 1.6 : 1, opacity: lit ? (major ? 1 : mid ? 0.85 : 0.5) : major ? 0.8 : 0.3 }, s);
    }
    el("circle", { cx: C, cy: C, r: 104, fill: "none", stroke: css("--border-strong"), "stroke-width": 1.2 }, s);
    if (score > 0) {
      const glow = el("path", { d: arcPath(C, C, 104, 0.01, Math.max(0.02, score * 3.6)), fill: "none", stroke: css("--gold"), "stroke-width": 10, "stroke-linecap": "round", opacity: 0.18 }, s);
      const comp = el("path", { d: arcPath(C, C, 104, 0.01, Math.max(0.02, score * 3.6)), fill: "none", stroke: "url(#dg)", "stroke-width": 4, "stroke-linecap": "round" }, s);
      const [ex, ey] = polar(C, C, 104, score * 3.6);
      const knob = el("circle", { cx: ex, cy: ey, r: 6, fill: css("--gold-2"), stroke: "#0A1530", "stroke-width": 2.5 }, s);
      if (first && !reduced()) {
        [comp, glow].forEach((p) => { const len = p.getTotalLength(); p.style.strokeDasharray = String(len); p.style.strokeDashoffset = String(len); p.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.16,1,.3,1) .2s"; });
        knob.style.opacity = "0"; knob.style.transition = "opacity .35s ease 1.1s";
        requestAnimationFrame(() => requestAnimationFrame(() => { comp.style.strokeDashoffset = "0"; glow.style.strokeDashoffset = "0"; knob.style.opacity = "1"; }));
      }
    }
    pillars.forEach((p, i) => {
      const a0 = i * 72 + 3, a1 = (i + 1) * 72 - 3, sc = p.score ?? 0, af = a0 + ((a1 - a0) * sc) / 100;
      const col = css(PILLAR_COLOR[p.key] || "--gold");
      el("path", { d: arcPath(C, C, 124, a0, a1), fill: "none", stroke: "#1A2A48", "stroke-width": 7, "stroke-linecap": "round" }, s);
      const seg = el("path", { d: arcPath(C, C, 124, a0, Math.max(a0 + 0.1, af)), fill: "none", stroke: col, "stroke-width": active === p.key ? 10 : 7, "stroke-linecap": "round", style: "cursor:pointer;transition:stroke-width .2s" }, s);
      if (first && !reduced()) { const len = seg.getTotalLength(); seg.style.strokeDasharray = String(len); seg.style.strokeDashoffset = String(len); seg.style.transition = `stroke-dashoffset 1s cubic-bezier(.16,1,.3,1) ${0.4 + i * 0.08}s, stroke-width .2s`; requestAnimationFrame(() => requestAnimationFrame(() => (seg.style.strokeDashoffset = "0"))); }
      seg.addEventListener("click", () => onPillar(p.key));
      const mid = (a0 + a1) / 2, [lx, ly] = polar(C, C, 146, mid);
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
