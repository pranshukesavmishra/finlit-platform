// The "prism" glyph: the overall score ring split into one arc per part. An arc's length is its weight in the score; it is filled up to the
// part's own score; the overall number sits in the middle. Pure SVG, no chart library; the entrance animation is CSS and switches off for
// prefers-reduced-motion. Styles: styles/dash-shared.css (classes dk-gl*).
import { useId, type CSSProperties } from "react";
import { bandVar, scoreBand } from "../../../lib/scoreBands";
import "../../../styles/dash-shared.css";

export type GlyphPart = { key: string; name: string; /** share of the score, any positive number (percent or fraction) */ weight: number; /** 0..100 or null */ value: number | null; /** CSS custom property name, e.g. "--p-growth" */ color: string };
export type PrismGlyphProps = {
  parts: GlyphPart[];
  /** Overall score 0..100; null draws "Not rated" and empty arcs. */
  score: number | null;
  /** Rendered size in px (the drawing scales). Default 150. */
  size?: number;
  /** Small caption under the number. Default "out of 100"; not drawn when score is null. */
  caption?: string;
  /** Accessible name for the whole glyph. The glyph is hidden from screen readers when omitted (the caller describes the rating in words). */
  ariaLabel?: string;
  /** Draw "EXAMPLE" instead of the caption (locked teaser). */
  example?: boolean;
};

const C = 80, RA = 62, GAP = 5;
const pt = (r: number, deg: number): [number, number] => { const a = ((deg - 90) * Math.PI) / 180; return [C + r * Math.cos(a), C + r * Math.sin(a)]; };
const arc = (r: number, a0: number, a1: number) => { const [x0, y0] = pt(r, a0), [x1, y1] = pt(r, a1); return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`; };

export function PrismGlyph({ parts, score, size = 150, caption = "out of 100", ariaLabel, example }: PrismGlyphProps) {
  const id = "pg" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const total = parts.reduce((s, p) => s + p.weight, 0) || 1;
  let at = 0;
  const arcs = parts.map((p) => {
    const span = (p.weight / total) * 360, a0 = at + GAP / 2, a1 = at + span - GAP / 2;
    at += span;
    return { ...p, a0, a1, d: arc(RA, a0, Math.max(a0 + 0.5, a1)), end: pt(RA, a0 + (Math.max(a1 - a0, 0.5) * Math.max(0, Math.min(100, p.value ?? 0))) / 100) };
  });
  const ticks = Array.from({ length: 60 }, (_, i) => i);
  return (
    <span className="dk-gl" style={{ width: size, height: size }} {...(ariaLabel ? { role: "img", "aria-label": ariaLabel } : { "aria-hidden": true })}>
      <svg viewBox="0 0 160 160">
        <defs>
          <radialGradient id={`${id}d`} cx=".5" cy=".3" r=".85"><stop offset="0" stopColor="var(--dk-disc-1)" /><stop offset=".6" stopColor="var(--dk-disc-2)" /><stop offset="1" stopColor="var(--dk-disc-3)" /></radialGradient>
          <linearGradient id={`${id}n`} x1="0" y1="0" x2="0" y2="1"><stop offset=".1" stopColor="#FFF6DC" /><stop offset=".6" stopColor="#E8D29B" /><stop offset="1" stopColor="#C9A24E" /></linearGradient>
          <filter id={`${id}g`} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" /></filter>
        </defs>
        <circle className="dk-gl-halo" cx={C} cy={C} r="66" />
        {ticks.map((i) => { const [x0, y0] = pt(77, i * 6), [x1, y1] = pt(i % 5 === 0 ? 72.5 : 74.5, i * 6); return <line key={i} className={"dk-gl-tick" + (i % 5 === 0 ? " maj" : "")} x1={x0.toFixed(2)} y1={y0.toFixed(2)} x2={x1.toFixed(2)} y2={y1.toFixed(2)} />; })}
        {arcs.map((a, i) => (
          <g key={a.key} style={{ "--pc": bandVar(scoreBand(a.value)), "--i": i } as CSSProperties}>
            <path className="dk-gl-track" d={a.d} />
            {a.value != null && a.value > 0 && <>
              <path className="dk-gl-fill glow" d={a.d} pathLength={100} strokeDasharray={`${a.value} 100`} filter={`url(#${id}g)`} />
              <path className="dk-gl-fill" d={a.d} pathLength={100} strokeDasharray={`${a.value} 100`} />
              <circle className="dk-gl-end" cx={a.end[0].toFixed(2)} cy={a.end[1].toFixed(2)} r="2.6" />
            </>}
          </g>
        ))}
        {arcs.map((a) => { const [x0, y0] = pt(RA - 8, a.a0 - GAP / 2), [x1, y1] = pt(RA + 8, a.a0 - GAP / 2); return <line key={a.key + "s"} className="dk-gl-sep" x1={x0.toFixed(2)} y1={y0.toFixed(2)} x2={x1.toFixed(2)} y2={y1.toFixed(2)} />; })}
        <circle className="dk-gl-disc" cx={C} cy={C} r="48" fill={`url(#${id}d)`} />
        <circle className="dk-gl-ring2" cx={C} cy={C} r="43" />
        {score == null
          ? <text className="dk-gl-nr" x={C} y={C + 5} textAnchor="middle">Not rated</text>
          : <><text className={"dk-gl-num band-" + scoreBand(score)} x={C} y={C + 9} textAnchor="middle">{score.toFixed(1)}</text><text className="dk-gl-cap" x={C} y={C + 27} textAnchor="middle">{example ? "EXAMPLE" : caption.toUpperCase()}</text></>}
      </svg>
    </span>
  );
}
