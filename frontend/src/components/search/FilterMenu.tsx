// One compact dropdown of the search palette ("Sector" or "Market cap"). A button shows the active choice; it opens a list with a Clear option on top.
// Keyboard: Enter, Space or the arrow keys open it; arrows, Home and End move; Enter picks; Esc closes only this list (the palette stays open).
import { useEffect, useRef, useState } from "react";

export type FilterOption = { id: string; label: string; hint?: string; n: number };

export function FilterMenu({ name, value, options, open, onOpen, onPick, note, keyHint, clearLabel }: {
  name: string; value: string | null; options: FilterOption[]; open: boolean; onOpen: (v: boolean) => void; onPick: (id: string | null) => void;
  note?: string; keyHint?: string; clearLabel: string;
}) {
  const [at, setAt] = useState(0);                 // highlighted entry; 0 is "Clear" (shown only while a choice is active)
  const btn = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = "gs-fm-" + name.toLowerCase().replace(/\W+/g, "");
  const entries: { id: string | null; label: string; hint?: string; n?: number }[] = [...(value ? [{ id: null, label: clearLabel }] : []), ...options];
  const chosen = options.find((o) => o.id === value);

  useEffect(() => {
    if (!open) return;
    const i = entries.findIndex((e) => e.id === value);
    setAt(i >= 0 ? i : 0);
    list.current?.focus();
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) onOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => { if (open) list.current?.querySelector<HTMLElement>(`[data-k="${at}"]`)?.scrollIntoView({ block: "nearest" }); }, [at, open]);

  const choose = (i: number) => { const e = entries[i]; if (!e) return; onPick(e.id); onOpen(false); };
  const key = (e: React.KeyboardEvent) => {
    const last = entries.length - 1;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onOpen(false); btn.current?.focus(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(a + 1, last)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Home") { e.preventDefault(); setAt(0); }
    else if (e.key === "End") { e.preventDefault(); setAt(last); }
    else if (e.key === "PageDown") { e.preventDefault(); setAt((a) => Math.min(a + 6, last)); }
    else if (e.key === "PageUp") { e.preventDefault(); setAt((a) => Math.max(a - 6, 0)); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(at); }
    else if (e.key === "Tab") onOpen(false);
  };

  return (
    <div className={`gs-fm${value ? " on" : ""}`} ref={box}>
      <button ref={btn} type="button" className="gs-fb" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? id : undefined} title={keyHint ? `${name} (${keyHint})` : name}
        onClick={() => onOpen(!open)}
        onKeyDown={(e) => { if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); onOpen(true); } }}>
        <span className="gs-fl-k">{name}</span>
        <b>{chosen ? chosen.label : value ?? "All"}</b>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="gs-fp">
          <ul id={id} ref={list} role="listbox" tabIndex={-1} aria-label={name} aria-activedescendant={`${id}-${at}`} onKeyDown={key}>
            {entries.map((e, k) => (
              <li key={e.id ?? "clear"} id={`${id}-${k}`} data-k={k} role="option" aria-selected={e.id === value && e.id !== null} className={`${k === at ? "cur" : ""}${e.id === null ? " clr" : ""}`}
                onMouseMove={() => setAt(k)} onClick={() => choose(k)}>
                <span className="gs-fo-t">{e.label}{e.hint && <small>{e.hint}</small>}</span>
                {e.n != null && <em>{e.n.toLocaleString("en-IN")}</em>}
              </li>
            ))}
          </ul>
          {note && <p className="gs-fn">{note}</p>}
        </div>
      )}
    </div>
  );
}
