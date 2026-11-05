import { useState } from "react";
import type { Ownership } from "../../lib/api";
import { CMP_OPTIONS, movesFor, seriesFromOwnership, seriesFromTable, slicesAt, type OwnInsights, type OwnSeries } from "../../lib/ownView";
import { ownershipYears, parsePeriod, selectionInfo } from "../../lib/ownershipYears";
import { SectionHead } from "../Sections";
import { OwnershipYearPicker } from "../OwnershipYearPicker";
import { OwnCharts } from "./OwnCharts";
import { OwnFacts } from "./OwnFacts";
import { OwnInsightCards } from "./OwnInsightCards";
import { OwnMoves } from "./OwnMoves";
import { OwnersToday } from "./OwnersToday";

const HEAD = { id: "ownership", no: "11 · Ownership", icon: "pie", tier: "basic" as const, title: "Who owns the company", color: "--p-balance" };

/** The series the section draws: the stored shareholding (every filing the provider has, so every year is selectable), else the insights' own 21 filings. */
export function seriesOf(o?: Ownership, ins?: OwnInsights): OwnSeries | null {
  if (o?.latest?.length && o.periods.length) return seriesFromOwnership(o);
  if (ins?.available && ins.table?.length) return seriesFromTable(ins.table);
  return null;
}

/** Section 11. `ins` is the stored ownership insights (never the premium endpoint); `insWhy` is the reason when they cannot be had. */
export function OwnershipSection({ o, ins, insWhy }: { o?: Ownership; ins?: OwnInsights; insWhy?: string | null }) {
  const [pick, setPick] = useState<number | null>(null);
  const [q, setQ] = useState(CMP_OPTIONS[1].q);
  const series = seriesOf(o, ins);
  if (!series) {
    if (!o) return <section className="block"><SectionHead {...HEAD} /><div className="skeleton" style={{ height: 260 }} /></section>;
    return <section className="block"><SectionHead {...HEAD} /><p className="faint">Shareholding data for this company has not been loaded yet.</p></section>;
  }
  const periods = series.periods, latest = periods.length - 1;
  const idx = pick != null && pick <= latest ? pick : latest;
  const years = ownershipYears(periods), info = selectionInfo(periods, idx);
  const moves = movesFor(series, idx, q, ins?.facts, latest);
  const when = periods[idx], isLatest = idx === latest;
  const stale = !!ins?.as_of && ins.as_of !== periods[latest];
  const cur = parsePeriod(when);
  return (
    <section className="block ow" style={{ "--sc": "var(--p-balance)" } as React.CSSProperties}>
      <SectionHead {...HEAD} sub={`Shareholding pattern, ${periods[latest]}`} />
      {years.length > 0 && (
        <OwnershipYearPicker years={years.map((y) => y.year)} selected={cur?.year ?? null} onPick={(y) => { const f = years.find((z) => z.year === y); if (f) setPick(f.index); }}
          cap={{ now: when, then: moves.from === when ? null : moves.from, basis: "chosen comparison", isLatest, year: info.year, isYearLatest: info.isYearLatest, yearLatest: info.yearLatest }} />
      )}
      <OwnInsightCards ins={ins} why={insWhy} stale={stale} />
      <div className="ow-row">
        <OwnersToday slices={slicesAt(series, idx)} when={when} isLatest={isLatest} />
        <OwnMoves moves={moves} q={q} sel={idx} onQ={setQ} />
      </div>
      <OwnCharts series={series} symbol={o?.meta?.symbol ?? ins?.symbol ?? ""} />
      <OwnFacts ins={stale ? undefined : ins} />
      <p className="ow-foot">pts = percentage points of the company. From quarterly shareholding filings. Information only, not advice.</p>
    </section>
  );
}
