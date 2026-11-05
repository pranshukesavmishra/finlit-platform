// Small shared pieces of the refreshed dashboard: the one card style, loading placeholders, hooks for width and phone size.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/** The one card every block uses: serif title, 13px subtitle, optional right-hand control. Placeholders (not "no data" text) belong in `children` while a call is pending. */
export function Card({ id, title, sub, right, children, className = "" }: { id: string; title: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={"dsh-card " + className} aria-labelledby={`dsh-${id}`}>
      <div className="dsh-ch"><div><h2 id={`dsh-${id}`}>{title}</h2>{sub ? <p className="dsh-sub">{sub}</p> : null}</div>{right}</div>
      {children}
    </section>
  );
}

/** Grey blocks the size of the content they stand for. */
export const Rows = ({ n = 3, h = 44 }: { n?: number; h?: number }) => <div className="dsh-sk" aria-busy="true" aria-label="Loading">{Array.from({ length: n }, (_, i) => <div key={i} className="skeleton" style={{ height: h }} />)}</div>;

/** A segmented control (chips 36px; 44px on phones). */
export function Seg<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void }) {
  return <div className="dsh-seg" role="group" aria-label={label}>{options.map(([k, l]) => <button key={k} type="button" aria-pressed={value === k} onClick={() => onChange(k)}>{l}</button>)}</div>;
}

/** Width of an element that may mount later than its component (a chart behind a loading state): a callback ref, so the observer attaches whenever it appears. */
export function useWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [w, setW] = useState(900);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    ro.current?.disconnect(); ro.current = null;
    if (!el) return;
    setW(Math.max(280, Math.round(el.getBoundingClientRect().width)));
    if (typeof ResizeObserver === "undefined") return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  }, []);
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, w];
}

/** True under 760px (the phone layout: three tabs, shorter lists). */
export function useIsPhone(): boolean {
  const q = "(max-width: 759px)";
  const [p, setP] = useState(() => typeof matchMedia === "function" && matchMedia(q).matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const m = matchMedia(q), f = () => setP(m.matches);
    f(); m.addEventListener("change", f); return () => m.removeEventListener("change", f);
  }, []);
  return p;
}

export const tone = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.005 ? "" : v > 0 ? "up" : "down");

/** "Market" (every company) or "My stocks" for the results and filings blocks; the choice is remembered in this browser. */
export type Scope = "market" | "mine";
export function useScope(id: string, hasStocks: boolean): [Scope, (s: Scope) => void] {
  const key = "finlit-dash-scope:" + id;
  const [scope, set] = useState<Scope>(() => { try { return localStorage.getItem(key) === "mine" ? "mine" : "market"; } catch { return "market"; } });
  const choose = (s: Scope) => { set(s); try { localStorage.setItem(key, s); } catch { /* private mode */ } };
  return [hasStocks ? scope : "market", choose];
}
export function ScopeSeg({ label, scope, onChange, hasStocks }: { label: string; scope: Scope; onChange: (s: Scope) => void; hasStocks: boolean }) {
  return (
    <div className="dsh-seg" role="group" aria-label={`${label}: whose companies`}>
      <button type="button" aria-pressed={scope === "mine"} disabled={!hasStocks} title={hasStocks ? "Only the stocks you follow" : "Follow a stock to use this"} onClick={() => onChange("mine")}>My stocks</button>
      <button type="button" aria-pressed={scope === "market"} onClick={() => onChange("market")}>Market</button>
    </div>
  );
}
