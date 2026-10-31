// What the plans below Gold see on the upgrade page: the screens in their groups with a lock, no counts and no companies.
import { Icon } from "../../../lib/icons";
import { orderGroups, usePresetList } from "../../../lib/presets";
import { useUI } from "../../../lib/ui";
import "../../../styles/presets.css";

export function LockedPresets() {
  const q = usePresetList(), { upgrade } = useUI();
  const groups = orderGroups(q.data?.groups ?? []);
  if (!groups.length) return null;
  return (
    <section className="card psx-locked" aria-label="Prebuilt screens in Gold">
      <h2>Prebuilt screens <span className="muted">Gold</span></h2>
      <p className="muted">Ready-made screens for the questions investors ask most, each with its rules in plain words. A screen narrows a list. It is not a recommendation.</p>
      <div className="psx-lg">{groups.map((g) => (
        <div key={g.id} className="psx-lgi"><h3>{g.name}</h3>
          <ul>{g.presets.map((p) => <li key={p.id}><Icon name="lock" /><span>{p.name}{p.status === "blocked" && <small> (coming soon)</small>}</span></li>)}</ul></div>))}
      </div>
      <button type="button" className="btn" onClick={() => upgrade("gold", "Prebuilt screens are part of Gold.")}>Unlock with Gold <Icon name="arrow" /></button>
    </section>);
}
