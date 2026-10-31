// The page while a prebuilt screen is open: the screen view beside (or, on a phone, above) the list of screens, so another screen is one tap away.
import type { ReactNode } from "react";
import { TitleCard } from "../PageParts";
import { PresetPanel } from "./PresetPanel";
import { ScreenView } from "./ScreenView";
import type { PresetRoute } from "./usePresetRoute";
import "../../../styles/presets.css";

export function PresetPage({ route, basics }: { route: PresetRoute; basics: ReactNode }) {
  return (
    <div className="wrap scr-wrap" style={{ paddingTop: 22 }}>
      <TitleCard tier="gold" title="Every listed company, rated by FinLit Prism." sub="Prebuilt screens narrow the whole market with ready-made rules. Each one says what it checks, and you can change its options." learnTo="/advanced-score-screener" learnLabel="Back to all filters" />
      <div className="psx-lay">
        <div className="psx-main"><ScreenView key={route.id ?? ""} route={route} /></div>
        <aside className="psx-side card" aria-label="Prebuilt screens"><h2 className="psx-sh">Screens</h2><PresetPanel route={route} basics={basics} basicsActive={false} /></aside>
      </div>
    </div>);
}
