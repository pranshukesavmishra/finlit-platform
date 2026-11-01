// Glossary popovers: an (i) button next to any metric explains what it is, how to read it and the formula.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { placeFloating } from "../lib/floating";
import type { Glossary } from "../lib/api";

type PopState = { g: Glossary; anchor: HTMLElement } | null;
const Ctx = createContext<(g: Glossary | null, anchor?: HTMLElement) => void>(() => {});

export function InfoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PopState>(null);
  const ref = useRef<HTMLDivElement>(null);
  const show = useCallback((g: Glossary | null, anchor?: HTMLElement) => setState(g && anchor ? { g, anchor } : null), []);

  useEffect(() => {
    if (!state || !ref.current) return;
    const pl = placeFloating(state.anchor, ref.current);
    ref.current.style.left = pl.left + "px"; ref.current.style.top = pl.top + "px"; ref.current.style.maxHeight = pl.maxH + "px"; ref.current.style.overflowY = "auto";
  }, [state]);
  useEffect(() => {
    const close = () => setState(null);
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    addEventListener("scroll", close, { passive: true, capture: true });
    addEventListener("keydown", key);
    return () => { removeEventListener("scroll", close, true); removeEventListener("keydown", key); };
  }, []);

  return (
    <Ctx.Provider value={show}>
      {children}
      <div className="pop" role="tooltip" ref={ref} hidden={!state}>
        {state && (<>
          <b>{state.g.label}</b>{state.g.what}
          {state.g.lines && <ul className="pop-lines">{state.g.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}
          {state.g.read && <div className="hr">{state.g.read}</div>}
          {state.g.formula && <div className="fx">{state.g.formula}</div>}
          {state.g.note && <div className="hr">{state.g.note}</div>}
        </>)}
      </div>
    </Ctx.Provider>
  );
}

/** Show (or, with null, hide) the shared explanation popover next to any element: for triggers that are not the (i) button, such as a table figure. */
export const useInfoPop = () => useContext(Ctx);

export function Info({ g }: { g?: Glossary | null }) {
  const show = useContext(Ctx);
  if (!g || !g.what) return null;
  return (
    <button className="info" aria-label={`What is ${g.label}?`}
      onMouseEnter={(e) => show(g, e.currentTarget)} onMouseLeave={() => show(null)}
      onFocus={(e) => show(g, e.currentTarget)} onBlur={() => show(null)}
      onClick={(e) => { e.stopPropagation(); show(g, e.currentTarget); }}>i</button>
  );
}
