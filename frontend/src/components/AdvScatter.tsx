// Advanced charts scatter: one SVG drawn only with CSS variables (light and dark themes), the API's fitted line, 95% band and
// Theil-Sen line, highlighted companies with distinct shapes, edge markers for points outside the window, and a keyboard readout.
// It draws what it is given: no statistic is computed here. Geometry helpers are in lib/advanced.ts (tested).
import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import { bandPath, edgeOf, linTicks, logTicks, nearest, shapePath, viewRange, type Scale, type Shape } from "../lib/advanced";

export type ScPt = { key: string; label: string; x: number; y: number; note?: string };
export type ScSeries = { key: string; name: string; color: string; shape: Shape; pts: ScPt[]; hollow?: boolean; join?: boolean };
/** A fitted line as the API sends it: two end points in DATA units (straight on the axes drawn, log axes included), with an optional
 *  95% band for the fitted line, also in data units. */
export type ScFit = { key: string; kind: "ols" | "ts"; line: { x0: number; y0: number; x1: number; y1: number }; color?: string; band?: { x: number; lo: number; hi: number }[] | null };
/** An index reference marker: a large labelled diamond, never part of the statistics. `lines` feed the tooltip and the screen-reader readout. */
export type ScMark = { key: string; label: string; color: string; x: number; y: number; lines: string[] };
type View = { x: [number, number]; y: [number, number] };

type Props = {
  cloud: ScPt[]; series: ScSeries[]; fits: ScFit[];
  sx: Scale; sy: Scale; xLabel: string; yLabel: string;
  fmtX: (v: number) => string; fmtY: (v: number) => string; tickX: (v: number) => string; tickY: (v: number) => string;
  all: boolean; w: number; summary: string; labels?: boolean;
  /** The API's default window (1st-99th percentile, data units); without it the window is worked out from the points. */
  view?: View | null;
  marks?: ScMark[];
};

const M = { l: 58, r: 14, t: 14, b: 46 };

export function AdvScatter({ cloud, series, fits, sx, sy, xLabel, yLabel, fmtX, fmtY, tickX, tickY, all, w, summary, labels = true, view, marks = [] }: Props) {
  const H = w < 600 ? 300 : 400;
  const tid = useId();
  const tx = (v: number) => (sx === "log" ? Math.log10(v) : v), ty = (v: number) => (sy === "log" ? Math.log10(v) : v);
  const okPt = (p: ScPt) => Number.isFinite(p.x) && Number.isFinite(p.y) && (sx !== "log" || p.x > 0) && (sy !== "log" || p.y > 0);

  const geo = useMemo(() => {
    const c = cloud.filter(okPt), hs = series.map((s) => ({ ...s, pts: s.pts.filter(okPt) })), mk = marks.filter((m) => okPt({ key: m.key, label: m.label, x: m.x, y: m.y }));
    const keepX = [...hs.flatMap((s) => s.pts.map((p) => tx(p.x))), ...mk.map((m) => tx(m.x))], keepY = [...hs.flatMap((s) => s.pts.map((p) => ty(p.y))), ...mk.map((m) => ty(m.y))];
    const allX = [...c.map((p) => tx(p.x)), ...keepX], allY = [...c.map((p) => ty(p.y)), ...keepY];
    const fromApi = (r: [number, number] | undefined, t: (v: number) => number, keep: number[]): [number, number] | null => {
      if (!r || all) return null;
      const a = t(r[0]), b = t(r[1]); if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
      return viewRange([a, b], true, keep);
    };
    const dx = fromApi(view?.x, tx, keepX) ?? viewRange(allX, all, keepX), dy = fromApi(view?.y, ty, keepY) ?? viewRange(allY, all, keepY);
    return { c, hs, mk, dx, dy };
  }, [cloud, series, sx, sy, all, view, marks]); // eslint-disable-line react-hooks/exhaustive-deps
  const { c, hs, mk, dx, dy } = geo;
  const pw = Math.max(40, w - M.l - M.r), ph = H - M.t - M.b;
  const X = (v: number) => M.l + ((v - dx[0]) / (dx[1] - dx[0] || 1)) * pw;
  const Y = (v: number) => M.t + (1 - (v - dy[0]) / (dy[1] - dy[0] || 1)) * ph;

  // Keyboard / pointer order: highlighted companies first, then every other point from left to right.
  const order = useMemo(() => {
    const out: { p: ScPt; s: ScSeries | null; px: number; py: number; m?: ScMark }[] = [];
    hs.forEach((s) => s.pts.forEach((p) => out.push({ p, s, px: tx(p.x), py: ty(p.y) })));
    mk.forEach((m) => out.push({ p: { key: m.key, label: m.label, x: m.x, y: m.y }, s: null, px: tx(m.x), py: ty(m.y), m }));
    [...c].sort((a, b) => a.x - b.x).forEach((p) => out.push({ p, s: null, px: tx(p.x), py: ty(p.y) }));
    return out;
  }, [c, hs, mk]); // eslint-disable-line react-hooks/exhaustive-deps
  const [hi, setHi] = useState<number | null>(null);
  const cur = hi != null ? order[Math.min(hi, order.length - 1)] : null;

  const xt = sx === "log" ? logTicks(10 ** dx[0], 10 ** dx[1]).map(Math.log10) : linTicks(dx[0], dx[1], w < 600 ? 4 : 6);
  const yt = sy === "log" ? logTicks(10 ** dy[0], 10 ** dy[1]).map(Math.log10) : linTicks(dy[0], dy[1], 5);
  const xv = (t: number) => (sx === "log" ? 10 ** t : t), yv = (t: number) => (sy === "log" ? 10 ** t : t);

  let outside = 0;
  const place = (px: number, py: number) => { const e = edgeOf(px, py, dx, dy); if (!e.inside) outside++; return e; };
  const cloudEls = c.map((p) => { const e = place(tx(p.x), ty(p.y)); return { p, e }; });
  const seriesEls = hs.map((s) => ({ s, pts: s.pts.map((p) => ({ p, e: place(tx(p.x), ty(p.y)) })) }));

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    const k = nearest(order.map((o) => { const g = edgeOf(o.px, o.py, dx, dy); return { sx: X(g.x), sy: Y(g.y) }; }), px, py);
    setHi(k >= 0 ? k : null);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!order.length) return;
    const last = order.length - 1, step = (d: number) => setHi((h) => (h == null ? (d > 0 ? 0 : last) : Math.max(0, Math.min(last, h + d))));
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); step(-1); }
    else if (e.key === "Home") { e.preventDefault(); setHi(0); }
    else if (e.key === "End") { e.preventDefault(); setHi(last); }
    else if (e.key === "Escape") setHi(null);
  };

  const fitEls = fits.map((f) => {
    const band = f.band ? bandPath(f.band.filter((b) => (sx !== "log" || b.x > 0) && (sy !== "log" || (b.lo > 0 && b.hi > 0))).map((b) => ({ x: tx(b.x), lo: ty(b.lo), hi: ty(b.hi) })), X, Y) : "";
    return { f, x1: tx(f.line.x0), x2: tx(f.line.x1), y1: ty(f.line.y0), y2: ty(f.line.y1), band };
  }).filter((g) => [g.x1, g.x2, g.y1, g.y2].every(Number.isFinite));
  const clip = `adv-clip-${tid.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const curE = cur ? edgeOf(cur.px, cur.py, dx, dy) : null;
  const readout = cur?.m ? `Index ${cur.m.label}: ${cur.m.lines.join(". ")}` : cur ? `${cur.p.label}${cur.s && cur.s.name !== cur.p.label ? ` (${cur.s.name})` : ""}: ${xLabel} ${fmtX(cur.p.x)}, ${yLabel} ${fmtY(cur.p.y)}${cur.p.note ? `. ${cur.p.note}` : ""}${curE && !curE.inside ? ". Outside the window, drawn on its edge" : ""}` : "";

  return (
    <div className="adv-plot" onPointerLeave={() => setHi(null)}>
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img" tabIndex={0} aria-label={summary} aria-describedby={`${clip}-live`} onPointerMove={onMove} onKeyDown={onKey} onBlur={() => setHi(null)}>
        <defs><clipPath id={clip}><rect x={M.l} y={M.t} width={pw} height={ph} /></clipPath></defs>
        {yt.map((t) => <g key={"y" + t}><line className="adv-gl" x1={M.l} x2={M.l + pw} y1={Y(t)} y2={Y(t)} /><text className="adv-tick" x={M.l - 6} y={Y(t) + 4} textAnchor="end">{tickY(yv(t))}</text></g>)}
        {xt.map((t) => <g key={"x" + t}><line className="adv-gl" x1={X(t)} x2={X(t)} y1={M.t} y2={M.t + ph} /><text className="adv-tick" x={X(t)} y={M.t + ph + 16} textAnchor="middle">{tickX(xv(t))}</text></g>)}
        {dy[0] < 0 && dy[1] > 0 && sy === "lin" && <line className="adv-zero" x1={M.l} x2={M.l + pw} y1={Y(0)} y2={Y(0)} />}
        {dx[0] < 0 && dx[1] > 0 && sx === "lin" && <line className="adv-zero" x1={X(0)} x2={X(0)} y1={M.t} y2={M.t + ph} />}
        <text className="adv-axt" x={M.l + pw / 2} y={H - 6} textAnchor="middle">{xLabel}{sx === "log" ? " (log scale)" : ""} →</text>
        <text className="adv-axt" transform={`translate(13 ${M.t + ph / 2}) rotate(-90)`} textAnchor="middle">{yLabel}{sy === "log" ? " (log scale)" : ""} →</text>
        <g clipPath={`url(#${clip})`}>
          {fitEls.map(({ f, band }) => band && <path key={"b" + f.key} className="adv-band" d={band} style={f.color ? { fill: f.color } : undefined} />)}
          {cloudEls.map(({ p, e }) => e.inside
            ? <circle key={p.key} className="adv-pt" cx={X(e.x)} cy={Y(e.y)} r={3.2} />
            : <path key={p.key} className="adv-edge" d={edgeMark(X(e.x), Y(e.y), e)} />)}
          {fitEls.map(({ f, x1, x2, y1, y2 }) => <line key={"l" + f.key} className={f.kind === "ts" ? "adv-ts" : "adv-ols"} x1={X(x1)} x2={X(x2)} y1={Y(y1)} y2={Y(y2)} style={f.color ? { stroke: f.color } : undefined} />)}
          {seriesEls.map(({ s, pts }) => <g key={s.key} style={{ color: s.color }}>
            {s.join && pts.length > 1 && <path className="adv-join" d={pts.map(({ e }, i) => `${i ? "L" : "M"}${X(e.x).toFixed(1)},${Y(e.y).toFixed(1)}`).join("")} />}
            {pts.map(({ p, e }) => <path key={p.key} className={"adv-hl" + (s.hollow ? " hollow" : "")} d={shapePath(s.shape, X(e.x), Y(e.y), 6)} />)}
          </g>)}
          {mk.map((m) => { const e = edgeOf(tx(m.x), ty(m.y), dx, dy); return <path key={m.key} className="adv-ix" style={{ color: m.color }} d={shapePath("diamond", X(e.x), Y(e.y), 9)} />; })}
        </g>
        {mk.map((m) => { const e = edgeOf(tx(m.x), ty(m.y), dx, dy); const lx = X(e.x), ly = Y(e.y), left = lx > M.l + pw * 0.7;
          return <text key={"ixl" + m.key} className="adv-lab adv-ixl" x={left ? lx - 13 : lx + 13} y={ly + 4} textAnchor={left ? "end" : "start"}>{m.label}</text>; })}
        {labels && w >= 600 && seriesEls.map(({ s, pts }) => { const last = pts[pts.length - 1]; if (!last) return null; const lx = X(last.e.x), ly = Y(last.e.y); const left = lx > M.l + pw * 0.75;
          return <text key={"t" + s.key} className="adv-lab" x={left ? lx - 10 : lx + 10} y={ly - 8} textAnchor={left ? "end" : "start"}>{s.name}</text>; })}
        {cur && curE && <circle className="adv-cur" cx={X(curE.x)} cy={Y(curE.y)} r={9} />}
      </svg>
      {cur?.m && curE && <div className="adv-tip" style={{ top: Math.max(4, Y(curE.y) - 90), ...(X(curE.x) > w / 2 ? { right: w - X(curE.x) + 14 } : { left: X(curE.x) + 14 }) }}>
        <b>{cur.m.label}</b><small>Index reference marker</small>{cur.m.lines.map((l) => <em key={l}>{l}</em>)}
      </div>}
      {cur && !cur.m && curE && <div className="adv-tip" style={{ top: Math.max(4, Y(curE.y) - 64), ...(X(curE.x) > w / 2 ? { right: w - X(curE.x) + 12 } : { left: X(curE.x) + 12 }) }}>
        <b>{cur.p.label}</b>{cur.s && cur.s.name !== cur.p.label && <small>{cur.s.name}</small>}
        <div><span>{xLabel}</span><strong>{fmtX(cur.p.x)}</strong></div><div><span>{yLabel}</span><strong>{fmtY(cur.p.y)}</strong></div>
        {cur.p.note && <em>{cur.p.note}</em>}{!curE.inside && <em>Outside the window: drawn on its edge.</em>}
      </div>}
      <p id={`${clip}-live`} className="sr" aria-live="polite">{readout || "Use the arrow keys to read the points, highlighted companies first."}</p>
      {outside > 0 && <p className="adv-out">{outside} point{outside === 1 ? "" : "s"} outside the window, shown as arrows on the edge. The statistics use every included point.</p>}
    </div>
  );
}

/** Small arrow on the edge of the window, pointing the way the point lies. */
function edgeMark(x: number, y: number, e: { left: boolean; right: boolean; below: boolean; above: boolean }): string {
  const s = 5, dx = e.right ? 1 : e.left ? -1 : 0, dy = e.above ? -1 : e.below ? 1 : 0;
  const n = Math.hypot(dx, dy) || 1, ux = dx / n, uy = dy / n, px = -uy, py = ux;
  const tip = [x + ux * s, y + uy * s], b1 = [x - ux * s + px * s, y - uy * s + py * s], b2 = [x - ux * s - px * s, y - uy * s - py * s];
  return `M${tip[0].toFixed(1)},${tip[1].toFixed(1)}L${b1[0].toFixed(1)},${b1[1].toFixed(1)}L${b2[0].toFixed(1)},${b2[1].toFixed(1)}Z`;
}
