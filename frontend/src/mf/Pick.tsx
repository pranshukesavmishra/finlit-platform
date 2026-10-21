// A menu with a search box for long lists (96 categories, 56 fund houses): type to narrow (spaces and typos tolerated), arrow keys and Enter to choose.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { searchOptions } from "../lib/mf";

export type PickItem = { value: string; label: string; count?: number; group?: string };

export function Pick({ label, value, items, onChange, any }: { label: string; value: string; items: PickItem[]; onChange: (v: string) => void; any: string }) {
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [at, setAt] = useState(0);
  const root = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null), btn = useRef<HTMLButtonElement>(null);
  const id = useId();
  const shown = useMemo(() => searchOptions(items, q, (i) => (i.group ? `${i.group} ${i.label}` : i.label)), [items, q]);
  const current = items.find((i) => i.value === value);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const out = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", out);
    return () => document.removeEventListener("mousedown", out);
  }, [open]);
  useEffect(() => { setAt(0); }, [q]);
  useEffect(() => { document.getElementById(`${id}-${at}`)?.scrollIntoView({ block: "nearest" }); }, [at, id]);

  const choose = (v: string) => { onChange(v); setOpen(false); setQ(""); btn.current?.focus(); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(shown.length, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(at === 0 ? "" : shown[at - 1]?.value ?? ""); }
    else if (e.key === "Escape") { setOpen(false); btn.current?.focus(); }
  };
  return (
    <div className="mf-pick" ref={root}>
      <span className="label" id={`${id}-l`}>{label}</span>
      <button type="button" ref={btn} className="mf-pick-b" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${id}-l ${id}-v`} onClick={() => setOpen((o) => !o)}>
        <span id={`${id}-v`}>{current ? current.label : any}</span><span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="mf-pick-pop">
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} placeholder={`Search ${label.toLowerCase()}…`} aria-label={`Search ${label.toLowerCase()}`}
            role="combobox" aria-expanded="true" aria-controls={`${id}-list`} aria-activedescendant={`${id}-${at}`} />
          <ul id={`${id}-list`} role="listbox" aria-label={label}>
            <li id={`${id}-0`} role="option" aria-selected={!value} className={at === 0 ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); choose(""); }}>{any}</li>
            {shown.map((i, n) => (
              <li key={i.value} id={`${id}-${n + 1}`} role="option" aria-selected={i.value === value} className={at === n + 1 ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); choose(i.value); }}>
                <span>{i.label}</span>{i.count != null && <small>{i.count.toLocaleString("en-IN")}</small>}
              </li>))}
            {!shown.length && <li className="mf-pick-none" role="presentation">Nothing matches “{q}”.</li>}
          </ul>
        </div>)}
    </div>
  );
}
