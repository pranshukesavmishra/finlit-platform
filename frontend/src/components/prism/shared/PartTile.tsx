// One compact tile of a score dashboard: a mini ring with the number, the name, the status in WORDS, the weight (when it has one) and a bar with
// tick marks at the label thresholds. Used for the five basic pillars and the four Prism parts on the stock page (the technical view is a separate row, not a part), and free for the
// full Prism page. Colour only decorates: the status word and the number carry the meaning. Styles: styles/dash-shared.css (classes dk-*).
import type { CSSProperties, ReactNode } from "react";
import "../../../styles/dash-shared.css";

export type Tone = "strong" | "healthy" | "mixed" | "weak" | "na";
/** The scores at which the words change (Prism: Poor < 35 <= Weak < 50 <= Average < 65 <= Healthy < 80 <= Strong). Drawn as ticks on every bar. */
export const TICKS = [35, 50, 65, 80];

export type PartTileProps = {
  /** Name of the part or pillar. */
  name: string;
  /** Score 0..100, or null when there is no data (the tile then says "No data" and draws an empty ring). */
  value: number | null;
  /** The status in words ("Healthy"). */
  word: string;
  /** Decides the marker shape and tone of the status word. */
  tone: Tone;
  /** Name of a CSS custom property that holds the part's colour, e.g. "--p-growth". */
  color: string;
  /** Share of the overall score in percent (draws "40%" in the corner). */
  weight?: number;
  /** One short line under the bar (optional; the stock page leaves it out in the compact row). */
  note?: string;
  /** Small icon drawn in the corner instead of the weight. */
  icon?: ReactNode;
  /** Position in the row; staggers the entrance animation. */
  index?: number;
  /** Make the tile a button (pillar tiles open a detail drawer). `pressed` is its aria-expanded. */
  onPress?: () => void;
  pressed?: boolean;
  /** Override the accessible name. Default: "Name: 74 out of 100, healthy. 40% of the score" / "Name: no data". */
  label?: string;
  ticks?: number[];
};

const R = 15;

/** The colour band of a score, as the founder set it: green from 70, orange from 50 to under 70, red under 50. Colour decorates the tile; the status word keeps
 *  the model's own labels, and the number says the rest. */
export type Band = "hi" | "mid" | "lo" | "na";
export const bandOf = (v: number | null | undefined): Band => (v == null || !Number.isFinite(v) ? "na" : v >= 70 ? "hi" : v >= 50 ? "mid" : "lo");
const BAND_COLOR: Record<Exclude<Band, "na">, string> = { hi: "var(--band-hi)", mid: "var(--band-mid)", lo: "var(--band-lo)" };

const ZONES: Record<number, string[]> = { 3: ["#E8808A", "#D4B26A", "#9BC48A", "#5FB88E"], 4: ["#E8808A", "#E0955F", "#D4B26A", "#9BC48A", "#5FB88E"] };
/** The bar's background: one faintly tinted zone per label band (red, amber, green), cut at the thresholds. A hint only; the word says the status. */
export function zoneBg(ticks: number[]): string {
  const cols = ZONES[ticks.length] ?? ZONES[4], stops = cols.map((c, i) => `color-mix(in srgb, ${c} 32%, transparent) ${i === 0 ? 0 : ticks[i - 1]}% ${i === cols.length - 1 ? 100 : ticks[i]}%`);
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

export function tileLabel(name: string, value: number | null, word: string, weight?: number): string {
  return value == null ? `${name}: no data` : `${name}: ${Math.round(value)} out of 100, ${word.toLowerCase()}.${weight != null ? ` ${weight}% of the score` : ""}`;
}

export function PartTile({ name, value, word, tone, color, weight, note, icon, index = 0, onPress, pressed, label, ticks = TICKS }: PartTileProps) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  const band = bandOf(value);
  // Every accent of the tile (tint, border, ring, bar) follows the score band; the corner icon keeps the part's own colour so the parts stay recognisable.
  const style = { "--pc": band === "na" ? `var(${color})` : BAND_COLOR[band], "--pillar": `var(${color})`, "--i": index } as CSSProperties;
  const cls = "dk-tile band-" + band;
  const inner = (
    <>
      <span className="dk-t-top">
        <span className="dk-ring" aria-hidden="true">
          <svg viewBox="0 0 38 38"><circle className="dk-ring-bg" cx="19" cy="19" r={R} /><circle className="dk-ring-fg" cx="19" cy="19" r={R} pathLength={100} strokeDasharray={`${v} 100`} /></svg>
          <b>{value == null ? "—" : Math.round(value)}</b>
        </span>
        {icon ? <span className="dk-t-ic" aria-hidden="true">{icon}</span> : weight != null ? <span className="dk-t-w" title={`${weight}% of the score`}>{weight}%</span> : null}
      </span>
      <span className="dk-t-name">{name}</span>
      <span className={"dk-st " + tone}>{word}</span>
      <span className="dk-bar" aria-hidden="true" style={{ background: zoneBg(ticks) }}>
        <i className="dk-bar-fill" style={{ width: `${v}%` }} />
        {ticks.map((t) => <u key={t} style={{ left: `${t}%` }} />)}
        {value != null && <em style={{ left: `${v}%` }} />}
      </span>
      {note ? <span className="dk-t-note">{note}</span> : null}
    </>
  );
  return onPress
    ? <button type="button" className={cls + " is-btn" + (pressed ? " hot" : "")} style={style} aria-expanded={!!pressed} onClick={onPress}>{inner}</button>
    : <div className={cls} style={style} role="group" aria-label={label ?? tileLabel(name, value, word, weight)}>{inner}</div>;
}
