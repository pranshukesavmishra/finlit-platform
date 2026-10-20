import { useState } from "react";

/** A draggable divider between a side panel and the main area: drag, arrow keys, or double-click to hide. The width is remembered per page. */
export const SIDE = { def: 330, min: 240, max: 620 };

export function useSideWidth(key: string) {
  const [w, setW] = useState<number>(() => { try { const v = Number(localStorage.getItem("finlit.side." + key)); return Number.isFinite(v) && v >= 0 && v <= SIDE.max && localStorage.getItem("finlit.side." + key) != null ? v : SIDE.def; } catch { return SIDE.def; } });
  const set = (next: number, snap = false) => {   // a drag below half the minimum folds the panel away
    const v = next < (snap ? SIDE.min / 2 : 1) ? 0 : Math.max(SIDE.min, Math.min(SIDE.max, Math.round(next)));
    setW(v); try { localStorage.setItem("finlit.side." + key, String(v)); } catch { /* private mode: not remembered */ }
  };
  return [w, set] as const;
}

export function SplitDivider({ width, set }: { width: number; set: (w: number, snap?: boolean) => void }) {
  const toggle = () => set(width === 0 ? SIDE.def : 0);
  return (
    <div className={"scr-split" + (width === 0 ? " shut" : "")} role="separator" aria-orientation="vertical" aria-label="Resize the filters panel (drag, use the arrow keys, or double-click to hide)"
      aria-valuemin={0} aria-valuemax={SIDE.max} aria-valuenow={width} tabIndex={0}
      onPointerDown={(e) => { e.preventDefault(); const x0 = e.clientX, w0 = width || SIDE.min, el = e.currentTarget; el.setPointerCapture(e.pointerId);
        const move = (ev: PointerEvent) => set(w0 + ev.clientX - x0, true), up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); };
        el.addEventListener("pointermove", move); el.addEventListener("pointerup", up); }}
      onDoubleClick={toggle}
      onKeyDown={(e) => { if (e.key === "ArrowLeft") { e.preventDefault(); set(width - 30, true); } else if (e.key === "ArrowRight") { e.preventDefault(); set(width + 30); } else if (e.key === "Enter") toggle(); }}>
      <button type="button" className="scr-split-btn" tabIndex={-1} aria-hidden="true" onPointerDown={(e) => e.stopPropagation()} onClick={toggle} title={width === 0 ? "Show filters" : "Hide filters"}>{width === 0 ? "›" : "‹"}</button>
    </div>
  );
}
