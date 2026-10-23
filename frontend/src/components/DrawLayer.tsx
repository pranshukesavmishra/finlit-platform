// Drawing tools over any chart: a pencil button opens a small toolbar (pencil, lines, arrow, levels, boxes, circles, Fibonacci, text, eraser, colours, undo,
// redo, clear). Drawings sit on top of the chart, are saved in this browser for that exact chart view, and never touch the data. Information only.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { COLOURS, FIB_LEVELS, MAX_SHAPES, MAX_TEXT, TOOLS, WIDTHS, clampPt, fibLines, loadShapes, newId, saveShapes, thin, topHit, type ColourId, type Pt, type Shape, type ToolId } from "../lib/drawings";
import "../styles/drawlayer.css";

const ICON: Record<ToolId | "undo" | "redo" | "trash" | "done", string> = {
  pen: "M4 20l1-4L16.5 4.5a2 2 0 0 1 3 3L8 19l-4 1zM14 7l3 3",
  line: "M5 19L19 5M5 19h.01M19 5h.01",
  arrow: "M5 19L19 5M10 5h9v9",
  hline: "M3 12h18M7 9l-3 3 3 3M17 9l3 3-3 3",
  vline: "M12 3v18M9 7l3-3 3 3M9 17l3 3 3-3",
  rect: "M5 6h14v12H5z",
  ellipse: "M12 5c4.4 0 8 3.1 8 7s-3.6 7-8 7-8-3.1-8-7 3.6-7 8-7z",
  fib: "M4 5h16M4 9h16M4 13h16M4 17h16M4 21h16",
  text: "M5 6V4h14v2M12 4v16M9 20h6",
  eraser: "M8 20h11M5.5 14.5l8-8a2 2 0 0 1 3 0l2.5 2.5a2 2 0 0 1 0 3l-6 6H9.5l-4-4a1 1 0 0 1 0-1.5z",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3",
  redo: "M15 14l5-5-5-5M20 9H10a6 6 0 0 0 0 12h3",
  trash: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
  done: "M5 12.5l4.5 4.5L19 7.5",
};
const Ic = ({ n }: { n: keyof typeof ICON }) => <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d={ICON[n]} /></svg>;
const TWO_POINT: ToolId[] = ["line", "arrow", "rect", "ellipse", "fib"];

/** Wraps a chart. `id` names the chart view (its series, range and kind), so each view keeps its own drawings. Set `enabled` false while the area shows a message instead of a chart. */
export function DrawLayer({ id, enabled = true, children }: { id: string; enabled?: boolean; children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [shapes, setShapes] = useState<Shape[]>(() => loadShapes(id));
  const [past, setPast] = useState<Shape[][]>([]), [future, setFuture] = useState<Shape[][]>([]);
  const [open, setOpen] = useState(false), [tool, setTool] = useState<ToolId>("pen"), [colour, setColour] = useState<ColourId>("red"), [width, setWidth] = useState<number>(WIDTHS[1]);
  const [draft, setDraft] = useState<Shape | null>(null);
  const [typing, setTyping] = useState<{ at: Pt; text: string } | null>(null);
  const drag = useRef<{ start: Pt; pts: Pt[] } | null>(null);
  const loaded = useRef(id);
  const typedAt = useRef(0);               // when the note box opened: the click that opened it must not close it again through a blur

  useEffect(() => {                                                                  // another chart view: its own drawings, a fresh history
    if (loaded.current === id) return;
    loaded.current = id; setShapes(loadShapes(id)); setPast([]); setFuture([]); setDraft(null); setTyping(null);
  }, [id]);
  useEffect(() => { if (loaded.current === id) saveShapes(id, shapes); }, [id, shapes]);
  useEffect(() => {
    const el = box.current; if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  const commit = useCallback((next: Shape[]) => { setPast((p) => [...p.slice(-49), shapes]); setFuture([]); setShapes(next.slice(-MAX_SHAPES)); }, [shapes]);
  const undo = () => { if (!past.length) return; setFuture((f) => [shapes, ...f]); setShapes(past[past.length - 1]); setPast(past.slice(0, -1)); };
  const redo = () => { if (!future.length) return; setPast((p) => [...p, shapes]); setShapes(future[0]); setFuture(future.slice(1)); };
  const clear = () => { if (shapes.length) commit([]); };

  const at = (e: React.PointerEvent): Pt => { const r = box.current!.getBoundingClientRect(); return clampPt([(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]); };
  const base = { id: "", c: colour, w: width };

  const down = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!open || typing || e.button > 0) return;
    const p = at(e), { w, h } = size;
    if (tool === "eraser") { const s = topHit(shapes, p[0] * w, p[1] * h, w, h); if (s) commit(shapes.filter((x) => x.id !== s.id)); return; }
    if (tool === "text") { e.preventDefault(); typedAt.current = Date.now(); setTyping({ at: p, text: "" }); return; }
    if (tool === "hline" || tool === "vline") { commit([...shapes, { ...base, id: newId(), k: tool, a: p }]); return; }
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { start: p, pts: [p] };
    setDraft(tool === "pen" ? { ...base, id: "draft", k: "pen", pts: [p] } : { ...base, id: "draft", k: tool as "line", a: p, b: p });
  };
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current; if (!d) return;
    const p = at(e);
    if (tool === "pen") { d.pts.push(p); setDraft({ ...base, id: "draft", k: "pen", pts: [...d.pts] }); }
    else if (TWO_POINT.includes(tool)) setDraft({ ...base, id: "draft", k: tool as "line", a: d.start, b: p });
  };
  const up = () => {
    const d = drag.current, s = draft; drag.current = null; setDraft(null);
    if (!d || !s) return;
    const { w, h } = size;
    if (s.k === "pen") { const pts = thin(s.pts, w, h); if (pts.length > 1 || s.pts.length > 1) commit([...shapes, { ...s, id: newId(), pts }]); }
    else if ("b" in s && Math.hypot((s.b[0] - s.a[0]) * w, (s.b[1] - s.a[1]) * h) >= 4) commit([...shapes, { ...s, id: newId() }]);   // a click without a drag draws nothing
  };
  const finishText = () => { if (typing && typing.text.trim()) commit([...shapes, { ...base, id: newId(), k: "text", a: typing.at, t: typing.text.trim().slice(0, MAX_TEXT) }]); setTyping(null); };

  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { if (typing) setTyping(null); else if (open) setOpen(false); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
  };

  const all = draft ? [...shapes, draft] : shapes;
  const info = useMemo(() => TOOLS.find((t) => t.id === tool)!, [tool]);
  const showTools = enabled;

  const strip = open && showTools && (
    <div className="dl-tools" role="toolbar" aria-label="Chart drawing tools">
      <div className="dl-row" role="group" aria-label="Tool">
        {TOOLS.map((t) => <button key={t.id} type="button" className={tool === t.id ? "on" : ""} aria-pressed={tool === t.id} aria-label={t.label} title={`${t.label}: ${t.hint}`} onClick={() => setTool(t.id)}><Ic n={t.id} /></button>)}
      </div>
      <span className="dl-sep" aria-hidden="true" />
      <div className="dl-row" role="group" aria-label="Colour and thickness">
        {(Object.keys(COLOURS) as ColourId[]).map((c) => <button key={c} type="button" className={"dl-sw" + (colour === c ? " on" : "")} aria-pressed={colour === c} aria-label={`Colour ${c}`} title={c} onClick={() => setColour(c)}><i style={{ background: COLOURS[c] === "currentColor" ? "var(--text)" : COLOURS[c] }} /></button>)}
        <span className="dl-sep" aria-hidden="true" />
        {WIDTHS.map((x, i) => <button key={x} type="button" className={"dl-wd" + (width === x ? " on" : "")} aria-pressed={width === x} aria-label={`Thickness ${["thin", "medium", "thick"][i]}`} title={["Thin", "Medium", "Thick"][i]} onClick={() => setWidth(x)}><i style={{ height: x }} /></button>)}
      </div>
      <span className="dl-sep" aria-hidden="true" />
      <div className="dl-row" role="group" aria-label="Edit">
        <button type="button" disabled={!past.length} aria-label="Undo" title="Undo (Ctrl+Z)" onClick={undo}><Ic n="undo" /></button>
        <button type="button" disabled={!future.length} aria-label="Redo" title="Redo (Ctrl+Shift+Z)" onClick={redo}><Ic n="redo" /></button>
        <button type="button" disabled={!shapes.length} aria-label="Clear all drawings" title="Clear all drawings" onClick={clear}><Ic n="trash" /></button>
        <button type="button" className="dl-done" aria-label="Done drawing" title="Done" onClick={() => setOpen(false)}><Ic n="done" />Done</button>
      </div>
      <p className="dl-hint" role="status">{info.label}: {info.hint}. Drawings stay on this chart view in this browser.</p>
    </div>
  );

  return (
    <div className="dl-outer" onKeyDown={key}>
      {strip}
      <div className={"dl" + (open ? " drawing" : "")} ref={box}>
        {children}
        {showTools && (
          <svg className="dl-svg" width={size.w} height={size.h} style={{ pointerEvents: open ? "auto" : "none", cursor: open ? (tool === "eraser" ? "pointer" : tool === "text" ? "text" : "crosshair") : "default", touchAction: open ? "none" : "auto" }}
            onPointerDown={down} onMouseDown={(e) => { if (open && tool === "text") e.preventDefault(); }} onPointerMove={move} onPointerUp={up} onPointerCancel={up} aria-hidden={!open}>
            {all.map((s) => <Mark key={s.id} s={s} w={size.w} h={size.h} />)}
          </svg>
        )}
        {typing && (
          <input className="dl-text" autoFocus maxLength={MAX_TEXT} value={typing.text} placeholder="Type, then Enter" aria-label="Note text" style={{ left: `${typing.at[0] * 100}%`, top: `${typing.at[1] * 100}%`, color: colour === "ink" ? undefined : COLOURS[colour] }}
            onChange={(e) => setTyping({ ...typing, text: e.target.value })} onBlur={() => { if (Date.now() - typedAt.current > 300) finishText(); }} onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter") finishText(); else if (e.key === "Escape") setTyping(null); }} />
        )}
        {showTools && (
          <div className="dl-bar">
            <button type="button" className={"dl-toggle" + (open ? " on" : "")} aria-pressed={open} aria-label={open ? "Close drawing tools" : "Open drawing tools"} title={open ? "Close drawing tools" : "Draw on this chart"} onClick={() => setOpen(!open)}>
              <Ic n="pen" />{!open && shapes.length > 0 && <b className="dl-n">{shapes.length}</b>}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Mark({ s, w, h }: { s: Shape; w: number; h: number }) {
  const col = COLOURS[s.c], X = (p: Pt) => p[0] * w, Y = (p: Pt) => p[1] * h;
  const common = { stroke: col, strokeWidth: s.w, fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const wrap = (el: React.ReactNode) => <g style={{ color: "var(--text)" }}>{el}</g>;
  switch (s.k) {
    case "pen": return wrap(<polyline {...common} points={s.pts.map((p) => `${X(p).toFixed(1)},${Y(p).toFixed(1)}`).join(" ")} />);
    case "line": return wrap(<line {...common} x1={X(s.a)} y1={Y(s.a)} x2={X(s.b)} y2={Y(s.b)} />);
    case "arrow": {
      const x1 = X(s.a), y1 = Y(s.a), x2 = X(s.b), y2 = Y(s.b), ang = Math.atan2(y2 - y1, x2 - x1), L = 10 + s.w * 2.2;
      const hd = (da: number) => `${x2 - L * Math.cos(ang + da)},${y2 - L * Math.sin(ang + da)}`;
      return wrap(<g {...common}><line x1={x1} y1={y1} x2={x2} y2={y2} /><polyline points={`${hd(0.45)} ${x2},${y2} ${hd(-0.45)}`} /></g>);
    }
    case "hline": return wrap(<line {...common} x1={0} x2={w} y1={Y(s.a)} y2={Y(s.a)} strokeDasharray="6 4" />);
    case "vline": return wrap(<line {...common} y1={0} y2={h} x1={X(s.a)} x2={X(s.a)} strokeDasharray="6 4" />);
    case "rect": return wrap(<rect {...common} x={Math.min(X(s.a), X(s.b))} y={Math.min(Y(s.a), Y(s.b))} width={Math.abs(X(s.b) - X(s.a))} height={Math.abs(Y(s.b) - Y(s.a))} rx={3} fill={col === "currentColor" ? "none" : col} fillOpacity={0.1} />);
    case "ellipse": return wrap(<ellipse {...common} cx={(X(s.a) + X(s.b)) / 2} cy={(Y(s.a) + Y(s.b)) / 2} rx={Math.abs(X(s.b) - X(s.a)) / 2} ry={Math.abs(Y(s.b) - Y(s.a)) / 2} fill={col === "currentColor" ? "none" : col} fillOpacity={0.08} />);
    case "fib": {
      const x0 = Math.min(X(s.a), X(s.b)), x1 = Math.max(X(s.a), X(s.b), x0 + 60), lines = fibLines(s.a, s.b);
      return wrap(<g>{lines.map((l, i) => <g key={l.level}>
        <line {...common} strokeWidth={Math.max(1, s.w / 2)} x1={x0} x2={x1} y1={l.y * h} y2={l.y * h} strokeDasharray={i === 0 || i === FIB_LEVELS.length - 1 ? undefined : "4 4"} />
        <text x={x1 + 4} y={l.y * h + 4} fill={col} fontSize={11} fontFamily="IBM Plex Mono, monospace" stroke="var(--s1)" strokeWidth={3} paintOrder="stroke">{(l.level * 100).toFixed(1).replace(".0", "")}%</text></g>)}</g>);
    }
    case "text": return wrap(<text x={X(s.a)} y={Y(s.a)} fill={col} fontSize={14} fontWeight={600} fontFamily="IBM Plex Sans, system-ui, sans-serif" stroke="var(--s1)" strokeWidth={3} paintOrder="stroke">{s.t}</text>);
  }
}
