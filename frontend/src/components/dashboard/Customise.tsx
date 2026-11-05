// Customise: every block can be switched on or off, made third, half or full width, and moved by dragging or with the up and down buttons (for the keyboard). Reset layout restores
// the default. Changes save as they are made (prefs mirror to /api/me/state).
import { useState } from "react";
import { Link } from "react-router";
import { RANK, TIER, type Plan } from "../../lib/ui";
import { WIDGETS, type WidgetPref, type WidgetSize } from "../../lib/prefs";
import { moveBlock } from "../../lib/dashboard";

const SIZES: [WidgetSize, string][] = [["third", "Third"], ["half", "Half"], ["full", "Full"]];

export function Customise({ layout, plan, onChange, onReset, onDone }: { layout: WidgetPref[]; plan: Plan; onChange: (l: WidgetPref[]) => void; onReset: () => void; onDone: () => void }) {
  const meta = Object.fromEntries(WIDGETS.map((w) => [w.id, w]));
  const [drag, setDrag] = useState<number | null>(null), [over, setOver] = useState<number | null>(null), [said, setSaid] = useState("");
  const patch = (id: string, v: Partial<WidgetPref>) => onChange(layout.map((w) => (w.id === id ? { ...w, ...v } : w)));
  const move = (i: number, to: number) => { onChange(moveBlock(layout, i, to)); setSaid(`${meta[layout[i].id].label} moved to place ${to + 1} of ${layout.length}`); };
  return (
    <section className="dsh-card dsh-edit" aria-label="Customise your dashboard">
      <div className="dsh-ch"><div><h2>Make it yours</h2><p className="dsh-sub">Switch blocks on or off, choose third, half or full width, and drag them (or use the arrows) to reorder. Changes save as you go and follow your account.</p></div>
        <button type="button" className="dsh-btn dark" onClick={onDone}>Done</button></div>
      <ul>{layout.map((w, i) => { const m = meta[w.id]; return (
        <li key={w.id} draggable onDragStart={(e) => { setDrag(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", w.id); }} onDragOver={(e) => { e.preventDefault(); setOver(i); }}
          onDrop={(e) => { e.preventDefault(); if (drag != null) move(drag, i); setDrag(null); setOver(null); }} onDragEnd={() => { setDrag(null); setOver(null); }} className={(drag === i ? "dragging " : "") + (over === i && drag !== i ? "over" : "")}>
          <span className="grip" aria-hidden="true" title="Drag to move">⋮⋮</span>
          <label className="dsh-sw"><input type="checkbox" checked={w.on} onChange={(e) => patch(w.id, { on: e.target.checked })} /><span aria-hidden="true" /><b>{m.label}</b></label>
          <small>{m.blurb}{RANK[plan] < RANK[m.min] ? ` · ${TIER[m.min].n}` : ""}</small>
          <div className="dsh-seg" role="group" aria-label={`${m.label} width`}>{SIZES.map(([s, l]) => <button key={s} type="button" aria-pressed={w.size === s} onClick={() => patch(w.id, { size: s })}>{l}</button>)}</div>
          <span className="mv"><button type="button" className="dsh-ib" aria-label={`Move ${m.label} up`} disabled={i === 0} onClick={() => move(i, i - 1)}>↑</button><button type="button" className="dsh-ib" aria-label={`Move ${m.label} down`} disabled={i === layout.length - 1} onClick={() => move(i, i + 1)}>↓</button></span>
        </li>); })}</ul>
      <div className="dsh-btns"><button type="button" className="dsh-btn" onClick={onReset}>Reset layout</button><Link className="dsh-btn" to="/account/appearance">More appearance options</Link></div>
      <p className="sr-only" role="status" aria-live="polite">{said}</p>
    </section>
  );
}
