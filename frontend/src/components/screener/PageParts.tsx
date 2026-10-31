// Page parts both screeners share: title card, KPI strip (the last card opens the filters), donut + sector bars, and the search / filter-button / sort toolbar.
import type { ReactNode } from "react";
import { Icon } from "../../lib/icons";
import { TierChip } from "../Gate";
import type { Plan } from "../../lib/ui";
import { nf } from "../../lib/format";
import { Chev } from "./FilterGroup";
import { SearchBox } from "./FilterGroup";

export function TitleCard({ tier, title, sub, onLearn, learnLabel = "Learn more" }: { tier: Plan; title: string; sub: ReactNode; onLearn: () => void; learnLabel?: string }) {
  return (
    <div className="fgx-title card">
      <div className="fgx-tx"><div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}><TierChip tier={tier} /><h1>{title}</h1></div><p>{sub}</p></div>
      <button type="button" className="btn" onClick={onLearn}><Icon name="info" /> {learnLabel}</button>
    </div>);
}

export type Kpi = { icon: Parameters<typeof Icon>[0]["name"]; label: string; value: string; why?: string };
const Funnel = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 5h18l-7 8v6l-4 2v-8z" /></svg>;
export function KpiStrip({ items, active, filtersOpen, onFilters }: { items: Kpi[]; active: number; filtersOpen: boolean; onFilters: () => void }) {
  return (
    <div className="fgx-kpis" aria-label="Summary">
      {items.map((k) => <div key={k.label} className="fgx-kpi" title={k.why}><span className="fgx-ki"><Icon name={k.icon} /></span><span className="fgx-kv"><b>{k.value}</b><small>{k.label}</small></span></div>)}
      <button type="button" className="fgx-kpi" aria-expanded={filtersOpen} onClick={onFilters} aria-label={`Active filters: ${active}. ${filtersOpen ? "Hide" : "Show"} the filters`}>
        <span className="fgx-ki"><Funnel /></span><span className="fgx-kv"><b>{nf(active, 0)}</b><small>Active filters</small></span><span style={{ transform: filtersOpen ? "rotate(180deg)" : undefined, display: "inline-flex" }}><Chev /></span></button>
    </div>);
}

/** Donut of a part of a whole. Only drawn from real counts; the caller passes nothing when the whole is unknown. */
export function Donut({ part, total, partLabel, restLabel, title, note }: { part: number; total: number; partLabel: string; restLabel: string; title: string; note?: ReactNode }) {
  const pct = total > 0 ? (part / total) * 100 : 0, R = 44, C = 2 * Math.PI * R;
  return (
    <div className="fgx-card">
      <div className="fgx-don">
        <svg className="fgx-donut" viewBox="0 0 112 112" role="img" aria-label={`${nf(pct, 0)} percent ${partLabel.toLowerCase()}`}>
          <circle cx="56" cy="56" r={R} fill="none" stroke="var(--s3)" strokeWidth="13" />
          <circle cx="56" cy="56" r={R} fill="none" stroke="var(--gold)" strokeWidth="13" strokeDasharray={`${(pct / 100) * C} ${C}`} transform="rotate(-90 56 56)" />
          <text x="56" y="62" textAnchor="middle">{nf(pct, 0)}%</text></svg>
        <div><p className="fgx-big">{title}</p>{note && <p className="fgx-dm">{note}</p>}
          <ul className="fgx-leg"><li><i className="a" aria-hidden="true" />{partLabel} {nf(part, 0)} ({nf(pct, 0)}%)</li><li><i className="b" aria-hidden="true" />{restLabel} {nf(total - part, 0)} ({nf(100 - pct, 0)}%)</li></ul></div>
      </div>
    </div>);
}

export function SectorBars({ title, rows, action }: { title: string; rows: { label: string; n: number; pct: number }[]; action?: ReactNode }) {
  const top = Math.max(1, ...rows.map((r) => r.pct));
  return (
    <div className="fgx-card">
      <div className="fgx-sh"><h2>{title}</h2>{action}</div>
      {rows.length ? <ul className="fgx-sb" aria-label="Sector mix of the result">{rows.map((r) => <li key={r.label}><span>{r.label}</span>{" "}<span className="fgx-bar" aria-hidden="true"><i style={{ width: (r.pct / top) * 100 + "%" }} /></span><span className="fgx-sn"><b>{nf(r.n, 0)}</b><small>{nf(r.pct, 0)}%</small></span></li>)}</ul> : <p className="muted">No companies in this result.</p>}
    </div>);
}

export function Toolbar({ q, setQ, searchLabel, buttons, sort }: { q: string; setQ: (v: string) => void; searchLabel: string; buttons: { id: string; label: string; active: number; onClick: () => void }[]; sort?: ReactNode }) {
  return (
    <div className="fgx-tool" role="search">
      <SearchBox value={q} onChange={setQ} placeholder={searchLabel} label={searchLabel} />
      {buttons.map((b) => <button key={b.id} type="button" className="fgx-pb" onClick={b.onClick} aria-label={b.active > 0 ? `${b.label}, ${b.active} active` : b.label}>{b.label}{b.active > 0 && <span className="fgx-badge">{b.active}</span>}<Chev /></button>)}
      {sort}
    </div>);
}
