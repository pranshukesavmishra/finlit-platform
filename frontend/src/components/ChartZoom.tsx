import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../lib/focusTrap";

/** One enlarge arrow for every real chart.
 *  <ChartZoom label="Revenue">…chart…</ChartZoom> puts a 36px arrow (44px tap area on phones) in the top-right corner of the chart.
 *  It opens the same chart, not a copy, in a full-viewport dialog: the chart's own state (range toggles, hover, selection) carries over and the chart redraws at the big size.
 *  Esc, the Restore button and a click on the dimmed page all close it, and focus returns to the arrow.
 *  Charts nested inside another ChartZoom (a card that already has the arrow) render as plain children, so one chart never gets two arrows. */
type Zoom = { inside: boolean; zoomed: boolean };
const Ctx = createContext<Zoom>({ inside: false, zoomed: false });

/** True while the chart is drawn in the enlarged dialog (charts with a fixed height can grow). */
export const useChartZoomed = () => useContext(Ctx).zoomed;

/** For a chart that is handed its pixel width by its page: put `ref` on a full-width box around the chart and draw at `width`.
 *  In the page it is `base`; in the enlarged dialog it is the dialog's width, so the chart redraws at the big size. */
export function useZoomWidth(base: number): [React.RefObject<HTMLDivElement | null>, number] {
  const zoomed = useChartZoomed();
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!zoomed || !el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => { const n = Math.round(el.getBoundingClientRect().width); setW((o) => (Math.abs(o - n) > 1 ? n : o)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, [zoomed]);
  return [ref, zoomed && w > 280 ? w : base];
}

/** The shared enlarge / restore glyph (also used by the chart builder). */
export function ZoomGlyph({ zoomed = false }: { zoomed?: boolean }) {
  return <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{zoomed
    ? <><polyline points="6,2 6,6 2,6" /><polyline points="10,14 10,10 14,10" /><line x1="6" y1="6" x2="2" y2="2" /><line x1="10" y1="10" x2="14" y2="14" /></>
    : <><polyline points="10,2 14,2 14,6" /><polyline points="6,14 2,14 2,10" /><line x1="14" y1="2" x2="9.5" y2="6.5" /><line x1="2" y1="14" x2="6.5" y2="9.5" /></>}</svg>;
}

/** What counts as a chart: a labelled picture (role="img"), a marked bar or heat-map list (data-chart), an SVG that is not an icon, or a canvas. */
const DRAWN = '[role="img"], [data-chart], svg[viewBox]:not([aria-hidden="true"]), canvas';

const subscribeNone = () => () => {};

let locks = 0, savedOverflow = "";
function lockScroll(): () => void {
  if (locks++ === 0) { savedOverflow = document.body.style.overflow; document.body.style.overflow = "hidden"; }
  return () => { if (--locks === 0) document.body.style.overflow = savedOverflow; };
}

export function ChartZoom({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  const parent = useContext(Ctx);
  if (parent.inside) return <>{children}</>;
  return <Zoomable label={label} className={className}>{children}</Zoomable>;
}

function Zoomable({ label, children, className }: { label: string; children: ReactNode; className: string }) {
  const [open, setOpen] = useState(false);
  const server = useSyncExternalStore(subscribeNone, () => false, () => true);   // true while rendering to a string: no portals there
  const host = useMemo(() => { if (typeof document === "undefined") return null; const d = document.createElement("div"); d.className = "cz-host"; return d; }, []);
  const slot = useRef<HTMLDivElement>(null), body = useRef<HTMLDivElement>(null), dlg = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  const tid = useId();
  const close = useCallback(() => setOpen(false), []);

  // One live copy of the chart: its DOM moves between the card and the dialog, so its React state is never lost.
  useLayoutEffect(() => {
    const to = open ? body.current : slot.current;
    if (to && host && host.parentNode !== to) to.appendChild(host);
  }, [open, host]);
  useEffect(() => () => { host?.remove(); }, [host]);

  // The arrow shows only while there is a drawn chart inside: a loading skeleton or a "not available" note has nothing to enlarge.
  const [has, setHas] = useState(false);
  useLayoutEffect(() => {
    if (!host) return;
    const look = () => setHas(!!host.querySelector(DRAWN));
    look();
    if (typeof MutationObserver === "undefined") return;
    const mo = new MutationObserver(look);
    mo.observe(host, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [host]);

  useEffect(() => {
    if (!open) return;
    const unlock = lockScroll();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", key, true);
    return () => { document.removeEventListener("keydown", key, true); unlock(); };
  }, [open, close]);
  useFocusTrap(dlg, open);

  if (server || !host) return <div className={"cz " + className}><div className="cz-slot"><div className="cz-host">{children}</div></div></div>;
  return (
    <div className={"cz " + className}>
      <Ctx.Provider value={{ inside: true, zoomed: open }}>
        <div className="cz-slot" ref={slot} />
        {createPortal(children, host)}
      </Ctx.Provider>
      {(has || open) && <button ref={btn} type="button" className="cz-btn" aria-label={`Enlarge chart: ${label}`} aria-haspopup="dialog" aria-expanded={open} title="Enlarge chart" onClick={() => setOpen(true)}><ZoomGlyph /></button>}
      {open && createPortal(
        <>
          <div className="cz-scrim" onClick={close} aria-hidden="true" />
          <div className="cz-modal" role="dialog" aria-modal="true" aria-labelledby={tid} tabIndex={-1} ref={dlg}>
            <div className="cz-bar">
              <h2 id={tid} className="cz-title">{label}</h2>
              <button type="button" className="cz-btn cz-restore" aria-label={`Restore chart: ${label}`} title="Restore (Esc)" onClick={close}><ZoomGlyph zoomed /><span>Restore</span></button>
            </div>
            <div className="cz-body" ref={body} />
          </div>
        </>, document.body)}
    </div>
  );
}
