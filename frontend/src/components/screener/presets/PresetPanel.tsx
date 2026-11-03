// The Quick views panel with the prebuilt screens in groups (Top rated, Trend, Growth, Themes, Value and income, Safety, Ownership) and the existing four under "Prism basics".
// Each group is a button that opens and closes it; the group holding the open screen starts open.
import { useId, useState, type ReactNode } from "react";
import { Icon } from "../../../lib/icons";
import { nf } from "../../../lib/format";
import { BASICS, PLAN_OF, type Preset } from "../../../lib/presets";
import { useUI } from "../../../lib/ui";
import { Chev } from "../FilterGroup";
import { usePresetRoute, type PresetRoute } from "./usePresetRoute";
import "../../../styles/presets.css";

function Card({ p, on, onPick, plan }: { p: Preset; on: boolean; onPick: () => void; plan: string }) {
  const why = useId(), blocked = p.status === "blocked";
  const count = p.locked ? null : p.count;
  return (
    <button type="button" className={"psx-card" + (on ? " is-on" : "") + (blocked ? " is-blocked" : "") + (p.locked ? " is-locked" : "")} aria-pressed={blocked ? undefined : on} aria-disabled={blocked || undefined}
      aria-describedby={blocked ? why : undefined} onClick={() => { if (!blocked) onPick(); }}>
      <span className="psx-ct"><b>{p.name}</b>
        {blocked ? <small className="psx-n psx-soon">Coming soon</small>
          : p.locked ? <small className="psx-n"><Icon name="lock" /><span className="sr">{plan} plan</span></small>
          : count != null ? <small className="psx-n">{p.listText || `${nf(count, 0)} match`}</small> : null}</span>
      {blocked ? <span className="psx-tx" id={why}>{p.blockedReason || "Coming soon: needs data we do not hold yet."}</span> : p.cardText ? <span className="psx-tx">{p.cardText}</span> : null}
    </button>);
}

function Group({ id, name, count, open, onToggle, children }: { id: string; name: string; count?: number; open: boolean; onToggle: () => void; children: ReactNode }) {
  const body = `psx-b-${useId()}`;
  return (
    <section className={"psx-grp" + (open ? " is-open" : "")} data-psx={id}>
      <h4 className="psx-gh"><button type="button" className="psx-gb" aria-expanded={open} aria-controls={body} onClick={onToggle}>
        <span className="psx-gt">{name}</span>{count != null && <small className="psx-gc">{count} {count === 1 ? "screen" : "screens"}</small>}<Chev /></button></h4>
      <div id={body} className="psx-body" hidden={!open}>{children}</div>
    </section>);
}

/** `basics` is the Advanced page's existing list of Prism quick views (the Basic page has none). `route` lets a page that already holds the route state share it. */
export function PresetPanel({ basics, basicsActive = false, route }: { basics?: ReactNode; basicsActive?: boolean; route?: PresetRoute }) {
  const own = usePresetRoute(), r = route ?? own;
  const plan = PLAN_OF[r.tab];
  const { upgrade } = useUI();
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const activeGroup = r.groups.find((g) => g.presets.some((p) => p.id === r.id))?.id ?? null;
  const fallbackOpen = (id: string) => (activeGroup || basicsActive ? id === activeGroup || (id === "basics" && basicsActive && !activeGroup) : id === (r.groups[0]?.id ?? "basics"));
  const isOpen = (id: string) => touched[id] ?? fallbackOpen(id);
  const pick = (p: Preset) => { if (p.locked) upgrade(plan, `Prebuilt screens on this page are part of ${plan === "gold" ? "Gold" : "Silver"}.`); else r.choose(p.id); };
  return (
    <div className="psx-panel">
      {r.list.isLoading && <p className="psx-note" role="status">Loading prebuilt screens…</p>}
      {r.list.isError && <p className="psx-note" role="status">Prebuilt screens are unavailable right now.{basics ? " The Prism quick views below still work." : ""}</p>}
      {r.groups.filter((g) => g.id !== "prism-basics").map((g) => (
        <Group key={g.id} id={g.id} name={g.name} count={g.presets.length} open={isOpen(g.id)} onToggle={() => setTouched((t) => ({ ...t, [g.id]: !isOpen(g.id) }))}>
          <div className="psx-cards">{g.presets.map((p) => <Card key={p.id} p={p} on={r.id === p.id} onPick={() => pick(p)} plan={plan === "gold" ? "Gold" : "Silver"} />)}</div>
        </Group>))}
      {basics && <Group id="basics" name={BASICS} open={isOpen("basics")} onToggle={() => setTouched((t) => ({ ...t, basics: !isOpen("basics") }))}>{basics}</Group>}
    </div>);
}
