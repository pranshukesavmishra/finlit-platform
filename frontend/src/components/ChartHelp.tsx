import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CHART_HELP } from "../lib/chartHelp";

const GAP = 8;      // space between the "?" and the popover
const EDGE = 8;     // minimum distance from the viewport edge

/**
 * A small "?" that explains the chart it sits next to: what it shows, both axes, how to read it and why it matters.
 * Opens on hover, keyboard focus and tap; closes on Escape, scroll, resize or a click elsewhere.
 * Renders nothing when the id has no entry in the registry.
 */
export function ChartHelp({ id }: { id: string }) {
  const entry = CHART_HELP[id];
  const uid = useId();
  const pid = "chh-" + uid.replace(/[^a-zA-Z0-9_-]/g, "");
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const leave = useRef<number>(0);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);       // opened by a click or tap, so leaving the button does not close it
  const [pos, setPos] = useState<{ left: number; top: number; above: boolean; arrow: number } | null>(null);

  const close = useCallback(() => { window.clearTimeout(leave.current); setOpen(false); setPinned(false); }, []);

  // Place the popover under the button, flip above when there is no room, and keep it inside the viewport.
  const place = useCallback(() => {
    const b = btn.current, p = pop.current;
    if (!b || !p) return;
    const r = b.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = window.innerHeight;
    const w = Math.min(p.offsetWidth, vw - EDGE * 2), h = p.offsetHeight;
    const below = vh - r.bottom - GAP - EDGE, above = r.top - GAP - EDGE;
    const flip = h > below && above > below;
    const left = Math.max(EDGE, Math.min(r.left + r.width / 2 - w / 2, vw - w - EDGE));
    const top = flip ? Math.max(EDGE, r.top - GAP - h) : Math.min(r.bottom + GAP, Math.max(EDGE, vh - h - EDGE));
    setPos({ left, top, above: flip, arrow: Math.max(12, Math.min(w - 12, r.left + r.width / 2 - left)) });
  }, []);

  useLayoutEffect(() => { if (open) place(); else setPos(null); }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { close(); btn.current?.focus({ preventScroll: true }); } };
    const onDown = (e: Event) => { const t = e.target as Node; if (!btn.current?.contains(t) && !pop.current?.contains(t)) close(); };
    const onScroll = (e: Event) => { if (!pop.current?.contains(e.target as Node)) close(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open, close]);

  useEffect(() => () => window.clearTimeout(leave.current), []);

  if (!entry) return null;
  const hold = () => { window.clearTimeout(leave.current); setOpen(true); };
  const release = () => { if (pinned) return; window.clearTimeout(leave.current); leave.current = window.setTimeout(() => setOpen(false), 140); };

  return (
    <span className="chh" onMouseEnter={hold} onMouseLeave={release}>
      <button
        ref={btn}
        type="button"
        className={"chh-b" + (open ? " on" : "")}
        aria-label="About this chart"
        aria-describedby={pid}
        aria-expanded={open}
        onFocus={hold}
        onBlur={() => { if (!pinned) release(); }}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (open && pinned) close(); else { setOpen(true); setPinned(true); } }}
      >?</button>
      {createPortal(
        <div
          ref={pop}
          id={pid}
          role="tooltip"
          hidden={!open}
          className={"chh-p" + (pos?.above ? " up" : "")}
          style={{ left: pos?.left ?? 0, top: pos?.top ?? 0, visibility: pos ? "visible" : "hidden", ["--ax" as string]: (pos?.arrow ?? 20) + "px" }}
          onMouseEnter={hold}
          onMouseLeave={release}
        >
          <b className="chh-t">{entry.title}</b>
          <p><span>What it shows</span>{entry.what}</p>
          {entry.x && <p><span>X axis (across)</span>{entry.x}</p>}
          {entry.y && <p><span>Y axis (up)</span>{entry.y}</p>}
          <p><span>How to read it</span>{entry.read}</p>
          <p><span>Why it matters</span>{entry.why}</p>
        </div>,
        document.body,
      )}
    </span>
  );
}
