// Small pieces of the Rotation pages: the corner glyph and badge (name + 2x2 glyph, never colour alone), the rank move, the rank sparkline, the tab pills. Styles: styles/rotation.css (rt-).
import { Link } from "react-router";
import { CORNER_POS, CORNER_WORD, rankMove, sparkPath, type RankPoint } from "../../lib/rotation";
import "../../styles/rotation.css";

/** The 2x2 glyph: the corner's own square is filled, the other three are grey. Top row gaining, bottom row slowing or slipping; left behind, right ahead. */
export function Glyph({ corner, size = 14 }: { corner: string; size?: number }) {
  const pos = CORNER_POS[corner];
  const cells: [boolean, boolean][] = [[false, true], [true, true], [false, false], [true, false]];
  const g = size / 2 - 1;
  return (
    <svg className={`rt-glyph c-${corner}`} width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" focusable="false">
      {cells.map(([ahead, gaining], i) => {
        const on = pos && pos.ahead === ahead && pos.gaining === gaining;
        return <rect key={i} x={ahead ? size / 2 + 0.5 : 0} y={gaining ? 0 : size / 2 + 0.5} width={g} height={g} rx="1.5" className={on ? "on" : "off"} />;
      })}
    </svg>
  );
}

/** The corner as glyph + name. */
export function CornerBadge({ corner, name, className = "" }: { corner: string; name?: string; className?: string }) {
  return <span className={`rt-corner c-${corner} ${className}`}><Glyph corner={corner} /><span>{name ?? CORNER_WORD[corner] ?? corner}</span></span>;
}

export function RankMove({ v, className = "" }: { v: number | null | undefined; className?: string }) {
  const m = rankMove(v);
  return <span className={`rt-move ${m.dir}${m.big ? " big" : ""} ${className}`} aria-label={m.label}><span aria-hidden="true">{m.text}</span></span>;
}

export function Spark({ hist, worst, w = 120, h = 30 }: { hist: RankPoint[]; worst: number; w?: number; h?: number }) {
  const d = sparkPath(hist, w, h, worst);
  const last = [...hist].reverse().find((p) => p.rank != null);
  const y = last ? 2 + (((last.rank as number) - 1) / Math.max(1, worst - 1)) * (h - 4) : 0;
  return <svg className="rt-spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" focusable="false"><path d={d} fill="none" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />{last && <circle cx={w - 2} cy={y} r="2.4" />}</svg>;
}

/** The two tabs at the top of both Sector pages. */
export function SectorTabs({ active }: { active: "pulse" | "rotation" }) {
  return (
    <nav className="rt-tabs" aria-label="Sector pages">
      <Link to="/sectors" aria-current={active === "pulse" ? "page" : undefined} className={active === "pulse" ? "on" : ""}>Sector Pulse</Link>
      <Link to="/sectors/rotation" aria-current={active === "rotation" ? "page" : undefined} className={active === "rotation" ? "on" : ""}>Rotation</Link>
    </nav>
  );
}
