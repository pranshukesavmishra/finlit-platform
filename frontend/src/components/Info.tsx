// Glossary popovers: an (i) button next to any metric explains what it is, how to read it and the formula.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Glossary } from "../lib/api";

type PopState = { g: Glossary; anchor: HTMLElement } | null;
const Ctx = createContext<(g: Glossary | null, anchor?: HTMLElement) => void>(() => {});

export function InfoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PopState>(null);
  const ref = useRef<HTMLDivElement>(null);
  const show = useCallback((g: Glossary | null, anchor?: HTMLElement) => setState(g && anchor ? { g, anchor } : null), []);

  useEffect(() => {
    if (!state || !ref.current) return;
    const r = state.anchor.getBoundingClientRect(), pw = ref.current.offsetWidth, ph = ref.current.offsetHeight;
    ref.current.style.left = Math.min(Math.max(16, r.left + r.width / 2 - pw / 2), innerWidth - pw - 16) + "px";
    let top = r.top - ph - 10;
    if (top < 80) top = r.bottom + 10;
    ref.current.style.top = top + "px";
  }, [state]);
  useEffect(() => {
    const close = () => setState(null);
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    addEventListener("scroll", close, { passive: true });
    addEventListener("keydown", key);
    return () => { removeEventListener("scroll", close); removeEventListener("keydown", key); };
  }, []);

  return (
    <Ctx.Provider value={show}>
      {children}
      <div className="pop" role="tooltip" ref={ref} hidden={!state}>
        {state && (<>
          <b>{state.g.label}</b>{state.g.what}
          {state.g.read && <div className="hr">{state.g.read}</div>}
          {state.g.formula && <div className="fx">{state.g.formula}</div>}
        </>)}
      </div>
    </Ctx.Provider>
  );
}

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
