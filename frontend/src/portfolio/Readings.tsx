import { SECTION_TAG, MODE_NOTE, READINGS_FOOT, SCORE_PARTS, FULL_AT } from "./words";
import type { Mode, PageObject } from "./types";

const jump = (id: string, open?: () => void) => (e: React.MouseEvent) => { e.preventDefault(); open?.(); setTimeout(() => document.getElementById("pf-" + id)?.scrollIntoView({ behavior: "smooth", block: "start" }), 0); };

/** "What this means": the page's five highest-priority readings for the chosen mode, written by the server's fixed rules; the tag links to the section it is about. */
export function WhatThisMeans({ page, mode, onOpenTogether }: { page: PageObject; mode: Mode; onOpenTogether: () => void }) {
  const items = page.summary[mode];
  return (
    <section className="pfx-card pfx-grow" aria-labelledby="pfx-wtm">
      <div className="pfx-h"><h2 id="pfx-wtm">What this means</h2><p className="pfx-note">{MODE_NOTE[mode]}</p></div>
      <ul className="pfx-reads">
        {items.map((x) => { const t = SECTION_TAG[x.section]; return (
          <li key={x.rule + x.text}><a href={"#pf-" + t.to} className={"pfx-tag t-" + x.section} onClick={jump(t.to, x.section === "together" ? onOpenTogether : undefined)}>{t.label}</a><span>{x.text}</span></li>); })}
        {!items.length && <li><span>No reading stands out for this list.</span></li>}
      </ul>
      <p className="pfx-fine">{READINGS_FOOT}</p>
    </section>
  );
}

/** "How the score is made": the two parts with bars, and the score with its band. */
export function ScoreMade({ page }: { page: PageObject }) {
  const s = page.score;
  const row = (label: string, v: number, text: string) => (
    <div className="pfx-part"><div className="pfx-part-h"><span>{label}</span><b>{v}</b></div><div className="pfx-bar"><i style={{ width: `${v}%` }} /></div><p>{text}</p></div>);
  return (
    <aside className="pfx-card pfx-side" aria-labelledby="pfx-how">
      <h2 id="pfx-how">How the score is made</h2>
      {row(SCORE_PARTS.comove, s.comovement, `${page.order.length} shares move like ${s.effective_stocks.toFixed(1)} independent ones; ${FULL_AT.stocks}`)}
      {row(SCORE_PARTS.sector, s.sector_spread, `About ${s.effective_sectors.toFixed(1)} effective sectors; ${FULL_AT.sectors}`)}
      <div className="pfx-total"><span>Diversification score</span><b>{s.score} · {s.band}</b></div>
    </aside>
  );
}
