// The left half of the stock page's first dashboard: the FinLit score. Compact by default (header row, dial + the read, one row of five
// pillar tiles, three one-line insights, a footer); `expanded` shows the full read, and ScoreDetail adds the insight cards and the pillar notes.
// Plan gating is unchanged: Hero wraps this in the Silver Gate. The right half (FinLit Prism) uses the same row grid, see PrismCompare.tsx.
import { useState } from "react";
import { Icon } from "../lib/icons";
import { dateIN, num } from "../lib/format";
import { useUI } from "../lib/ui";
import { bandInk, scoreBand } from "../lib/scoreBands";
import { Dial } from "../charts/Dial";
import { ChartHelp } from "../components/ChartHelp";
import { PartTile, type Tone } from "../components/prism/shared/PartTile";
import { scoreChange, useScoreHistory, type Ratios, type Summary } from "../lib/api";
import { BasisToggle } from "./Sections";
import { PILLAR_COLOR, PILLAR_ICON } from "./derive";

/** Where the FinLit score changes its word (45 / 62 / 78, see backend analytics/scoring.py); drawn as the ticks on every pillar bar. */
export const SCORE_TICKS = [45, 62, 78];
const bandStyle = (v: number | null | undefined) => (scoreBand(v) === "na" ? undefined : ({ "--tc": bandInk(scoreBand(v)) } as React.CSSProperties));
const toneOf = (key: string | undefined, score: number | null): Tone => score == null ? "na" : key === "strong" ? "strong" : key === "healthy" ? "healthy" : key === "mixed" ? "mixed" : "weak";

export function ScoreCard({ s, ratios, jump, two, expanded }: { s: Summary; ratios?: Ratios; jump: (id: string) => void; two: boolean; expanded: boolean }) {
  const { has, plan } = useUI();
  const hist = useScoreHistory(s.profile.symbol, has("silver") && s.score.overall != null);
  const chg = scoreChange(hist.data?.points);
  const [open, setOpen] = useState<string | null>(null);
  const cov = s.dataQuality.coverage;
  const byKey = Object.fromEntries((ratios?.score.pillars || []).map((x) => [x.key, x]));
  const know = [...s.strengths.slice(0, 2).map((n) => ({ ...n, tone: "good" as const })), ...s.watchouts.slice(0, 1).map((n) => ({ ...n, tone: "bad" as const }))];
  const ob = open ? byKey[open] : null, os = open ? s.score.pillars.find((x) => x.key === open) : null;
  const toggle = (k: string) => setOpen((o) => (o === k ? null : k));
  const thesis = s.thesis || (s.score.overall == null && !has("silver") ? "The written read of this company comes with the Silver plan, together with its FinLit score." : (cov?.state === "empty" ? "Our data provider has not sent any price or financial statements for this company, so there is nothing to score yet. We check again every night." : cov && cov.reasons.length ? `Not enough data to summarise this company yet: ${cov.reasons.join("; ")}. We check again every night.` : "Not enough data to summarise this company yet."));
  const updated = `Updated ${dateIN(s.meta.generatedAt, { day: "numeric", month: "short" })}`;
  const chipTitle = `This score is the FinLit score for every plan; Gold's advanced model is FinLit Prism, a separate rating. Data as of ${s.dataQuality.fundamentalsAsOf}, ${s.meta.statement} accounts.`;
  const bandTone = toneOf(s.score.band.key, s.score.overall);

  return (
    <article className="report dk-card dk-left" aria-labelledby="reportTitle">
      <header className="dk-head">
        <div className="dk-ht"><span className="eyebrow" id="reportTitle">{two ? "FinLit score" : "FinLit Research Report"}</span><BasisToggle symbol={s.meta.symbol} shown={s.meta.statement} /></div>
      </header>
      <div className="dk-row">
        <Dial compact overall={s.score.overall} pillars={s.score.pillars} onPillar={toggle} active={open} bandLabel={s.score.band.label} />
        <div className="dk-read">
          <div className="dk-rk">
            <span className="label">The read</span>
            <span className={"dk-st big " + bandTone} style={bandStyle(s.score.overall)}>{s.score.overall == null ? "Not scored yet" : s.score.band.label}</span>
            {chg && <span className={"dk-delta " + (chg.delta > 0 ? "up" : chg.delta < 0 ? "down" : "")} title={`Compared with ${dateIN(chg.since)}`}>{chg.delta > 0 ? "▲ +" : chg.delta < 0 ? "▼ −" : "● "}{Math.abs(chg.delta)} points since {dateIN(chg.since, { day: "numeric", month: "short" })}</span>}
          </div>
          <p className={"dk-thesis" + (expanded ? " full" : "")}>{thesis}</p>
        </div>
      </div>
      <div className="dk-tiles" style={{ "--n": s.score.pillars.length } as React.CSSProperties} role="group" aria-label="Five pillars">
        {s.score.pillars.map((pl, i) => (
          <PartTile key={pl.key} name={pl.label} value={pl.score} word={pl.score == null ? "No data" : pl.band.label} tone={toneOf(pl.band.key, pl.score)} color={PILLAR_COLOR[pl.key]} ticks={SCORE_TICKS}
            icon={<Icon name={PILLAR_ICON[pl.key]} />} index={i} pressed={open === pl.key} onPress={() => toggle(pl.key)} />
        ))}
      </div>
      <div className={"pdrawer dk-drawer" + (open ? " open" : "")}><div>
        {os && ob && (
          <div className="pd-in" style={{ "--pc": `var(${PILLAR_COLOR[os.key]})` } as React.CSSProperties}>
            <div><h4><span className="pt-ic"><Icon name={PILLAR_ICON[os.key]} /></span>{os.label} · {os.score ?? "—"}/100 <span className={"dk-st " + toneOf(os.band.key, os.score)}>{os.score == null ? "No data" : os.band.label}</span></h4>
              <p>{os.score == null && os.reason ? os.reason : "Each input scores 18 / 38 / 58 / 76 / 92 against four thresholds; the pillar is the average of the inputs available."}</p></div>
            <div className="pd-ev">{ob.inputs.map((x) => (
              <div key={x.key}><div className="k">{x.label}</div><div className="v">{x.value == null ? "—" : num(x.value)}</div>
                <div className="c">{x.score == null ? "Not reported" : `Scores ${x.score} · ${x.lowerIsBetter ? "≤" : "≥"} ${x.thresholds[3]} is great`}</div></div>
            ))}</div>
          </div>
        )}
      </div></div>
      <div className="dk-notes dk-know1">
        <div className="dk-pc-h"><Icon name="spark" /><span>What stands out</span><a href="#method" onClick={(e) => { e.preventDefault(); jump("method"); }} aria-label="See all pros and cons">See all</a></div>
        {know.length ? <ul>{know.map((n) => <li key={n.key} className={n.tone} title={`${n.title}. ${n.text}`}><Icon name={n.tone === "good" ? "check" : "alert"} /><b>{n.title}</b><span>{n.text}</span></li>)}</ul> : <p className="dk-none">Nothing stands out yet.</p>}
      </div>
      <details className="dk-more">
        <summary><span>Model, data date and help</span><Icon name="arrow" className="dk-chev" /></summary>
        <div className="dk-foot">
          <span className="dk-chip dk-live dk-fchip" title={chipTitle}><span className="dk-m">Model </span>{s.score.model} · {s.dataQuality.fundamentalsAsOf} · {updated}</span>
          <span className="dk-cap"><span className="dk-cap-t">Average of five pillars · select a ring segment or a pillar</span> <ChartHelp id="score-dial" /><ChartHelp id="score-pillars" /></span>
          <a className="dk-link" href="#method" onClick={(e) => { e.preventDefault(); jump("method"); }}>Pros &amp; cons →</a>
          {plan === "gold" && <a className="dk-link" href="#prism" title="This score is the FinLit score. Gold's advanced model, FinLit Prism, rates the company separately." onClick={(e) => { e.preventDefault(); jump("prism"); }}>Advanced model: FinLit Prism →</a>}
        </div>
      </details>
      <p className="dk-comp disc"><Icon name="info" /><span>Research summary, not a recommendation to buy or sell. FinLit Ventures is a technology company and is not registered with SEBI or AMFI.</span></p>
    </article>
  );
}

/** The left half of "Show full breakdown": the three insights in full, and what each pillar rests on. */
export function ScoreDetail({ s, ratios }: { s: Summary; ratios?: Ratios }) {
  const byKey = Object.fromEntries((ratios?.score.pillars || []).map((x) => [x.key, x]));
  const know = [...s.strengths.slice(0, 2).map((n) => ({ ...n, tone: "good" as const })), ...s.watchouts.slice(0, 1).map((n) => ({ ...n, tone: "bad" as const }))];
  return (
    <section className="report dk-card dk-detail" aria-label="FinLit score: full breakdown">
      <h3 className="dk-dh"><span className="eyebrow">FinLit score</span>What stands out, and what each pillar rests on</h3>
      {know.length > 0 && <div className="know dk-know">
        {know.map((n) => (
          <div key={n.key} style={{ "--k": n.tone === "good" ? "var(--p-quality)" : "var(--p-tech)" } as React.CSSProperties}>
            <div className="kt"><Icon name={n.tone === "good" ? "check" : "alert"} />{n.title}</div><p>{n.text}</p>
          </div>
        ))}
      </div>}
      <ul className="dk-plist">
        {s.score.pillars.map((pl) => {
          const ev = pl.score == null && pl.reason ? pl.reason : (byKey[pl.key]?.inputs || []).filter((x) => x.value != null).slice(0, 3).map((x) => `${x.label} ${num(x.value)}`).join(" · ");
          return (
            <li key={pl.key} style={{ "--pc": `var(${PILLAR_COLOR[pl.key]})` } as React.CSSProperties}>
              <span className="pt-ic" aria-hidden="true"><Icon name={PILLAR_ICON[pl.key]} /></span>
              <b>{pl.label}</b><span className="dk-pn">{pl.score ?? "—"}</span><span className={"dk-st " + toneOf(pl.band.key, pl.score)}>{pl.score == null ? "No data" : pl.band.label}</span>
              <span className="dk-pe">{ev || "Select this pillar above to see its inputs."}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
