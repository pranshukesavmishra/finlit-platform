import { useEffect, useRef } from "react";

export type YearCaption = { now: string; then: string | null; basis: string | null; isLatest: boolean; year: number | null; isYearLatest: boolean; yearLatest: string | null };

/** The big year selector at the top of the ownership section: large chips, newest first, radio semantics with arrow keys. */
export function OwnershipYearPicker({ years, selected, onPick, cap }: { years: number[]; selected: number | null; onPick: (year: number) => void; cap: YearCaption }) {
  const row = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const r = row.current, c = r?.querySelector<HTMLElement>('[aria-checked="true"]');
    if (r && c) r.scrollLeft = Math.max(0, c.offsetLeft - (r.clientWidth - c.offsetWidth) / 2);
  }, [selected]);
  const key = (e: React.KeyboardEvent, i: number) => {
    const to = e.key === "ArrowRight" || e.key === "ArrowDown" ? i + 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? years.length - 1 : null;
    if (to == null) return;
    e.preventDefault();
    const t = Math.max(0, Math.min(years.length - 1, to));
    onPick(years[t]);
    requestAnimationFrame(() => row.current?.querySelectorAll<HTMLElement>('[role="radio"]')[t]?.focus());
  };
  const idx = Math.max(0, years.indexOf(selected ?? -1));
  return (
    <div className="own-yr2">
      <div className="own-yr2-h"><span id="own-yr-l" className="own-yr2-t">Year</span><a className="own-yr2-all" href="#own-history">All filings, quarter by quarter ↓</a></div>
      <div className="own-yr2-row" role="radiogroup" aria-labelledby="own-yr-l" ref={row}>
        {years.map((y, i) => <button key={y} type="button" role="radio" aria-checked={y === selected} tabIndex={i === idx ? 0 : -1} className={"own-chip" + (y === selected ? " on" : "")} onClick={() => onPick(y)} onKeyDown={(e) => key(e, i)}>{y}</button>)}
      </div>
      <p className="own-yr2-cap" aria-live="polite">
        {cap.isYearLatest ? <>Showing the latest filing in {cap.year ?? "the year"}: <b>{cap.now}</b>{cap.isLatest ? " (most recent)" : ""}.</> : <>Showing the <b>{cap.now}</b> filing, picked from the chart. The latest filing in {cap.year} is {cap.yearLatest}.</>}{" "}
        {cap.then ? `Changes compare with the ${cap.basis}, ${cap.then}.` : "There is no earlier filing to compare with."}
      </p>
    </div>
  );
}
