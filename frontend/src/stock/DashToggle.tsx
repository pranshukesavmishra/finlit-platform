// "Show full breakdown": the single toggle under the stock page's first dashboard (FinLit score beside FinLit Prism).
// Collapsed is the default. The choice is remembered in this browser only; storage can be missing or blocked, so every access is guarded.
import { useCallback, useState } from "react";
import { Icon } from "../lib/icons";
import { isBool, loadUi, saveUi } from "../lib/persist";

export const DASH_KEY = "dash-open";

export function readDashOpen(): boolean {
  return loadUi(DASH_KEY, 1, isBool, false);
}
export function writeDashOpen(open: boolean): void {
  saveUi(DASH_KEY, 1, open);   // false when storage is blocked: the page still works, it just forgets
}

/** [open, set]: starts from the remembered choice, saves every change. */
export function useDashOpen(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(readDashOpen);
  const set = useCallback((v: boolean) => { setOpen(v); writeDashOpen(v); }, []);
  return [open, set];
}

export function DashToggle({ open, onToggle, controls }: { open: boolean; onToggle: (next: boolean) => void; controls: string }) {
  return (
    <div className="dk-toggle">
      <button type="button" className="dk-tg" aria-expanded={open} aria-controls={controls} onClick={() => onToggle(!open)}>
        <span>{open ? "Hide full breakdown" : "Show full breakdown"}</span>
        <Icon name="arrow" className="dk-chev" />
      </button>
    </div>
  );
}
