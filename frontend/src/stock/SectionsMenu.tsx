// "All sections": a button at the left end of the sticky section bar that opens a panel listing EVERY section (icon, name, one-line hint), so nothing is hidden
// however narrow the screen. Escape or a click outside closes it; focus moves in and returns to the button; arrow keys move through the grid.
import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "../lib/icons";
import { columnsOf, moveIndex, type NavItem } from "../lib/sectionNav";

export function SectionsMenu({ items, active, onPick }: { items: NavItem[]; active: string | null; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const id = "sx-" + useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null), grid = useRef<HTMLDivElement>(null);
  const close = (back: boolean) => { setOpen(false); if (back) btn.current?.focus({ preventScroll: true }); };
  const cells = () => [...(grid.current?.querySelectorAll<HTMLButtonElement>("button[data-s]") ?? [])];

  useEffect(() => {
    if (!open) return;
    const down = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down, true);
    const cs = cells(); (cs.find((c) => c.dataset.s === active) ?? cs[0])?.focus({ preventScroll: true });
    return () => document.removeEventListener("pointerdown", down, true);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const key = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); close(true); return; }
    if (e.key === "Tab") { close(false); return; }
    const cs = cells(), at = cs.indexOf(document.activeElement as HTMLButtonElement);
    if (!cs.length || at < 0) return;
    const to = moveIndex(at, e.key, cs.length, columnsOf(grid.current ? getComputedStyle(grid.current).gridTemplateColumns : ""));
    if (["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) { e.preventDefault(); cs[to]?.focus({ preventScroll: true }); }
  };

  return (
    <div className="sx" ref={box} onKeyDown={key}>
      <button type="button" ref={btn} className="sx-b" aria-expanded={open} aria-controls={id} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}>
        <Icon name="grid" /><span className="sx-l"><span className="sx-d">All sections</span><span className="sx-w">Sections</span></span>
      </button>
      <div id={id} className="sx-p" role="dialog" aria-label="All sections" hidden={!open}>
        <div className="sx-g" ref={grid}>
          {items.map(([sid, label, ic, hint]) => (
            <button key={sid} type="button" data-s={sid} className={"sx-i" + (active === sid ? " on" : "")} aria-current={active === sid ? "true" : undefined}
              onClick={() => { close(true); onPick(sid); }}>
              <span className="sx-ic"><Icon name={ic} /></span><span className="sx-t"><b>{label}</b><small>{hint}</small></span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
