// The "What it tells you" column of the Ratio history table: label chip, what happened, what it means. Every sentence comes from fixed rules over the
// numbers the ratios API already returns (lib/ratioReading/engine), so it works for every company and never makes up a figure.
import { Fragment, useMemo } from "react";
import { kindOf, readAll } from "../lib/ratioReading/engine";
import "../styles/ratio-reading.css";

export type Reading = { vd: string; label: string; tone: "g" | "a" | "r" | "n" | "b"; group: "better" | "steady" | "watch" | "weak" | "context"; l1: string; l2: string; nm: (string | null)[]; link: "dupont" | "earnings-cash" | null };
type RatiosIn = { history?: { periods: string[]; rows: Record<string, (number | null)[]> }; latest?: Record<string, { label?: string; unit?: string | null; better?: string | null } | undefined>; glossary?: Record<string, { label?: string } | undefined> };

export function useRatioReadings(ratios: RatiosIn | undefined, profile: unknown): Record<string, Reading> {
  return useMemo(() => {
    const h = ratios?.history;
    if (!h?.rows) return {};
    const meta: Record<string, { l: string; u: string; b: string | null }> = {};
    for (const k of Object.keys(h.rows)) { const m = ratios?.latest?.[k]; meta[k] = m ? { l: m.label ?? ratios?.glossary?.[k]?.label ?? k, u: m.unit ?? "", b: m.better ?? null } : { l: k, u: "", b: null }; }
    return readAll(h.periods, h.rows, meta, { kind: kindOf(profile) }) as Record<string, Reading>;
  }, [ratios, profile]);
}

const LINKS: Record<string, { href: string; text: string }> = {
  dupont: { href: "#dupont", text: "See DuPont analysis" },
  "earnings-cash": { href: "#earnings", text: "See earnings and cash quality" },
};

export function ReadingCell({ reading }: { reading?: Reading }) {
  if (!reading) return null;
  const link = reading.link ? LINKS[reading.link] : null;
  return (
    <div className="rr-cell">
      <span className={`rr-chip rr-${reading.tone}`}>{reading.label}</span>
      <b className="rr-l1">{reading.l1}</b>
      <span className="rr-l2">{reading.l2}{link && <> <a href={link.href}>{link.text} ↓</a></>}</span>
    </div>);
}

/** Used in place of the number when a year's value cannot be read (reading.nm[i] holds the reason). */
export const NotMeaningful = ({ reason }: { reason: string }) => <span className="rr-nm" title={`Not meaningful: ${reason}`}>n/m</span>;

const GROUPS: [string, string][] = [["all", "All"], ["better", "Getting better"], ["steady", "Steady"], ["watch", "Watch"], ["weak", "Weakening"], ["context", "Context"]];
export function ReadingFilter({ readings, value, onChange }: { readings: Record<string, Reading>; value: string; onChange: (g: string) => void }) {
  const list = Object.values(readings), count = (g: string) => (g === "all" ? list.length : list.filter((r) => r.group === g).length);
  return (
    <div className="rr-filter" role="group" aria-label="Filter ratios by reading"><span className="rr-filter-label">Show</span>
      {GROUPS.filter(([g]) => count(g) > 0).map(([g, label]) => <button key={g} type="button" aria-pressed={value === g} onClick={() => onChange(g)}>{label} <b>{count(g)}</b></button>)}
    </div>);
}

/** Under each ratio on phones (the column itself is hidden below 820px by the CSS). */
export const ReadingMobileRow = ({ reading, colSpan }: { reading?: Reading; colSpan: number }) =>
  reading ? <tr className="rr-mobile-row"><td colSpan={colSpan}><ReadingCell reading={reading} /></td></tr> : null;

export { Fragment };
