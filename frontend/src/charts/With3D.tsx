import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { supports3d, whenIdle } from "../three/support";
import type { Plot3DSpec } from "../three/Plot3D";

const Plot3D = lazy(() => import("../three/Plot3D"));

// Browsers allow only a limited number of WebGL canvases at once, so only the first few charts on a page are drawn in 3D; the rest stay flat.
const MAX_LIVE = 8;
let live = 0;
let preferFlat = false;                    // a visitor who switches one chart to Flat keeps that choice for the rest of the visit

/** Wraps a flat chart with a 3D version of the same data. On devices that can draw it, the chart shows in 3D with a 3D | Flat switch, a key and a
 *  plain-words hint; on every other device, or when 3D is not ready, the flat chart is shown exactly as before. */
export function With3D({ flat, spec, label, hint }: { flat: ReactNode; spec: Plot3DSpec | null; label: string; hint: string }) {
  const [ok, setOk] = useState(false), [near, setNear] = useState(false), [three, setThree] = useState(!preferFlat), [slot, setSlot] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (spec && supports3d()) return whenIdle(() => setOk(true)); }, [!!spec]);       // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ok || !box.current) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setNear(true); io.disconnect(); } }, { rootMargin: "300px" });
    io.observe(box.current); return () => io.disconnect();
  }, [ok]);
  useEffect(() => {
    if (!near || slot || live >= MAX_LIVE) return;
    live++; setSlot(true);
  }, [near, slot]);
  useEffect(() => () => { if (slot) live--; }, [slot]);
  if (!spec || !ok) return <>{flat}</>;
  if (!slot) return <div ref={box}>{flat}</div>;
  const on = three;
  const keys = [{ name: spec.level != null ? "above today's price" : "higher", css: "var(--gain)" }, { name: spec.level != null ? "below today's price" : "lower", css: "var(--loss)" }];
  return (
    <div ref={box}>
      <div className="v3d-bar">
        <span className="v3d-seg" role="group" aria-label="Chart style">
          <button type="button" aria-pressed={on} onClick={() => { preferFlat = false; setThree(true); }}>3D</button>
          <button type="button" aria-pressed={!on} onClick={() => { preferFlat = true; setThree(false); }}>Flat</button>
        </span>
        {on && keys.map((k) => <span key={k.name} className="v3d-key"><i style={{ background: k.css }} />{k.name}</span>)}
        {on && <span className="v3d-key">Drag to turn it</span>}
      </div>
      {on ? <Suspense fallback={null}><Plot3D spec={spec} label={label} /><p className="v3d-hint">{hint}</p></Suspense> : (flat ?? <p className="v3d-hint">Flat view: the table below has every number.</p>)}
    </div>
  );
}
