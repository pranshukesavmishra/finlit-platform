// Shared filter-panel pieces for every screener: a collapsible group (serif heading, "n active" badge, chevron), checkbox rows with counts,
// a Min - Max row that is enabled by its checkbox, chip rows, radio-style quick views and a search box. Styles: styles/fgx.css (class prefix fgx-).
import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Asking a group to open and scroll into view (the toolbar buttons use this). `n` changes on every request. */
export const FgxFocus = createContext<{ id: string | null; n: number }>({ id: null, n: 0 });

export const Chev = () => <svg className="fgx-chev" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>;

type GroupProps = { id: string; title: string; active?: number; hint?: ReactNode; meta?: ReactNode; defaultOpen?: boolean; open?: boolean; onOpenChange?: (o: boolean) => void; className?: string; children: ReactNode };
export function FilterGroup({ id, title, active = 0, hint, meta, defaultOpen = false, open: ctl, onOpenChange, className = "", children }: GroupProps) {
  const [own, setOwn] = useState(defaultOpen || active > 0);
  const open = ctl ?? own;
  const set = (o: boolean) => { setOwn(o); onOpenChange?.(o); };
  const uid = useId(), body = `fgx-b-${uid}`, root = useRef<HTMLElement>(null), btn = useRef<HTMLButtonElement>(null);
  const want = useContext(FgxFocus);
  useEffect(() => {
    if (want.n && want.id === id) { setOwn(true); onOpenChange?.(true); root.current?.scrollIntoView?.({ block: "nearest" }); btn.current?.focus(); }
  }, [want.n]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <section ref={root} className={"fgx-g" + (open ? " is-open" : "") + (className ? " " + className : "")} data-fgx={id}>
      <h3 className="fgx-h"><button ref={btn} type="button" className="fgx-hb" aria-expanded={open} aria-controls={body} onClick={() => set(!open)} onKeyDown={(e) => {
          if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
          const all = Array.from(btn.current?.closest("aside, form")?.querySelectorAll<HTMLButtonElement>("button.fgx-hb") ?? []), i = all.indexOf(btn.current!);
          if (i < 0 || !all.length) return;
          e.preventDefault(); all[e.key === "Home" ? 0 : e.key === "End" ? all.length - 1 : (i + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length].focus();
        }}>
        <span className="fgx-t">{title}</span>
        {meta != null && <span className="fgx-meta">{meta}</span>}
        {active > 0 && <span className="fgx-badge">{active} active</span>}
        <Chev /></button></h3>
      <div id={body} className="fgx-body" hidden={!open}>{hint && <p className="fgx-hint">{hint}</p>}{children}</div>
    </section>);
}

export function CheckRow({ label, count, checked, onChange, disabled }: { label: ReactNode; count?: number | null; checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <label className={"fgx-row" + (checked ? " is-on" : "") + (disabled ? " is-off" : "")}>
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="fgx-lab">{label}</span>
      {count != null && <small className="fgx-n">{count}</small>}
    </label>);
}

/** A checkbox followed by Min and Max boxes. The boxes are off until the row is ticked; unticking clears them. */
export function RangeRow({ label, group, min, max, onChange, error, minPh = "Min", maxPh = "Max", step = 1, maxOnly = false }: {
  label: string; group?: string; min: number | string | null; max: number | string | null; onChange: (end: "min" | "max", v: string) => void; error?: string; minPh?: string; maxPh?: string; step?: number | string; maxOnly?: boolean }) {
  const has = (min != null && min !== "") || (max != null && max !== "");
  const [ticked, setTicked] = useState(has);
  useEffect(() => { if (has) setTicked(true); }, [has]);
  const on = ticked || has, id = useId();
  const toggle = () => { if (on) { onChange("min", ""); onChange("max", ""); setTicked(false); } else setTicked(true); };
  return (
    <div className={"fgx-rr" + (on ? " is-on" : "")} role="group" aria-label={group ?? `${label}, exact range`}>
      <label className={"fgx-row" + (on ? " is-on" : "")}><input type="checkbox" checked={on} onChange={toggle} aria-controls={id} /><span className="fgx-lab">{label}</span></label>
      <div className={"fgx-mm" + (maxOnly ? " fgx-mx" : "")} id={id}>
        {!maxOnly && <><input type="number" inputMode="decimal" step={step} placeholder={minPh} aria-label="Min" disabled={!on} value={min ?? ""} onChange={(e) => onChange("min", e.target.value)} aria-invalid={!!error} />
        <span aria-hidden="true">&ndash;</span></>}
        <input type="number" inputMode="decimal" step={step} placeholder={maxPh} aria-label="Max" disabled={!on} value={max ?? ""} onChange={(e) => onChange("max", e.target.value)} aria-invalid={!!error} />
      </div>
      {error && <p className="fgx-err" role="alert">{error}</p>}
    </div>);
}

/** A named row of small toggle chips (for example the three score bands of one pillar). The "on" state also shows a tick, so colour is not the only cue. */
export function ChipRow({ label, title, chips, onToggle, group }: { label: string; title?: string; group?: string; chips: { key: string; text: string; on: boolean; aria: string }[]; onToggle: (key: string) => void }) {
  return (
    <div className="fgx-cr" role="group" aria-label={group ?? `${label} score`}>
      <span className="fgx-cn" title={title}>{label}</span>
      <span className="fgx-chips">{chips.map((c) => <button key={c.key} type="button" className={"fgx-chip" + (c.on ? " is-on" : "")} aria-pressed={c.on} aria-label={c.aria} onClick={() => onToggle(c.key)}>{c.on && <i aria-hidden="true">&#10003;</i>}{c.text}</button>)}</span>
    </div>);
}

/** A quick view: a bordered row with a radio-style dot. It is a toggle button (pressing the chosen one again switches it off). */
export function QuickRow({ label, on, onClick, title, icon }: { label: ReactNode; on: boolean; onClick: () => void; title?: string; icon?: ReactNode }) {
  return <button type="button" className={"fgx-qr" + (on ? " is-on" : "")} aria-pressed={on} title={title} onClick={onClick}><i className="fgx-dot" aria-hidden="true" />{icon}<span>{label}</span></button>;
}

export function SearchBox({ value, onChange, placeholder, label }: { value: string; onChange: (v: string) => void; placeholder: string; label: string }) {
  return (
    <label className="fgx-find"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => e.key === "Enter" && e.preventDefault()} placeholder={placeholder} aria-label={label} /></label>);
}
