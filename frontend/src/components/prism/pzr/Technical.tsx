// The technical view on the Prism report: a short-term and a long-term score on a -100..+100 scale, the combined trend, every signal
// behind them, and where the numbers come from. It is an additive, independent assessment (report.technicalAssessment): it is not a part of the
// 0-100 Prism score and never changes it. Older reports without the field get a calm "recalculate" note.
// Words: the model's own rating and verdict words are never shown; lib/prismTechnical.ts maps them to descriptive trend words (Positive, Neutral...).
// Colour only decorates: every conclusion is also a word and a shape. Styles: styles/prism-technical.css (pzt-*).
import { useMemo, useState } from "react";
import { Icon } from "../../../lib/icons";
import { dateIN } from "../../../lib/format";
import type { PrismReport } from "../../../lib/prism";
import {
  FACTOR_GROUP_WORD, STAGE_WORD, TECH_NOTE, disabledFactors, factorGroup, filterTechFactors, fmtScore, isFresh, parseTechnical, ratingWord, safeText,
  scalePos, scoreBand, signalWord, verdictView,
  type FactorGroup, type TechAssessment, type TechFactor, type TechHorizon, type TrendTone, type VerdictTone,
} from "../../../lib/prismTechnical";

export const TECH_ID = "pzr-technical";
const SHAPE: Record<TrendTone, string> = { strongpos: "▲▲", pos: "▲", neutral: "◆", neg: "▼", strongneg: "▼▼", na: "–" };
const VSHAPE: Record<VerdictTone, string> = { pos: "▲", mixed: "◆", neg: "▼", na: "–" };
const FILTERS: (FactorGroup | "all")[] = ["all", "supporting", "adverse", "neutral", "unavailable"];
const STATE_WORD = { ready: "Complete", incomplete: "Incomplete: score withheld" } as const;
const minus = (s: string) => s.replace("-", "−");

/** One sentence for a screen reader: the horizon, its score, the word, and how complete it is. */
export function horizonSummary(name: string, h: TechHorizon): string {
  const w = ratingWord(h.rating, h.score);
  const have = `${h.availableCount} of ${h.requiredCount} signals available`;
  if (h.score == null) return `${name}: no score, because ${have}.`;
  return `${name}: ${fmtScore(h.score)} on a scale from minus 100 to plus 100, ${w.word.toLowerCase()}. ${have}.${h.stageCapped ? " Limited by the market stage." : ""}`;
}

/** The -100..+100 scale: five bands (their edges are the rating boundaries), a centre line and a marker. Words below say the same. */
export function TechGauge({ score, label }: { score: number | null; label: string }) {
  const tone = scoreBand(score), pos = scalePos(score);
  return (
    <div className={"pzt-gauge " + tone} role="img" aria-label={label}>
      <div className="pzt-g-bar" aria-hidden="true">
        <i className="b1" style={{ flex: 25 }} /><i className="b2" style={{ flex: 15 }} /><i className="b3" style={{ flex: 20 }} /><i className="b4" style={{ flex: 15 }} /><i className="b5" style={{ flex: 25 }} />
        <u className="pzt-g-zero" />
        {score != null && <b className="pzt-g-mk" style={{ left: `${pos}%` }}><span>{fmtScore(score)}</span></b>}
      </div>
      <div className="pzt-g-ticks" aria-hidden="true">{[[-100, "−100"], [-50, "−50"], [0, "0"], [50, "+50"], [100, "+100"]].map(([v, t]) => <span key={v} style={{ left: `${((v as number) + 100) / 2}%` }}>{t}</span>)}</div>
    </div>
  );
}

function HorizonCard({ name, h, id }: { name: string; h: TechHorizon; id: string }) {
  const w = ratingWord(h.rating, h.score), have = h.score != null;
  return (
    <article className={"pzt-card " + w.tone} aria-labelledby={id}>
      <header className="pzt-ch">
        <div><h4 id={id}>{name}</h4>{h.horizon && <p>Trend over about {h.horizon.replace("–", " to ")}</p>}</div>
        <span className={"pzt-word " + w.tone} aria-label={`${name} trend: ${w.word}`}><i aria-hidden="true">{SHAPE[w.tone]}</i>{w.word}</span>
      </header>
      <p className="pzt-score" aria-label={have ? `${name} score ${fmtScore(h.score)} out of a range of minus 100 to plus 100` : `${name} score not available`}>
        {have ? <>{fmtScore(h.score)}<small> on −100 to +100</small></> : <>Not available<small> score withheld</small></>}
      </p>
      <TechGauge score={h.score} label={horizonSummary(name, h)} />
      <p className="pzt-legend">Strongly negative below −50 · Negative −50 to −20 · Neutral −20 to +20 · Positive +20 to +50 · Strongly positive +50 and above.</p>
      <ul className="pzt-facts">
        <li className={h.availableCount < h.requiredCount ? "warn" : ""}><Icon name={h.availableCount < h.requiredCount ? "alert" : "check"} /><span><b>{h.availableCount} of {h.requiredCount}</b> signals available. {STATE_WORD[h.status]}.</span></li>
        {h.stageCapped && <li className="warn pzt-cap"><Icon name="info" /><span><b>Limited by the market stage.</b> When a stock is in Stage 3 (topping) or Stage 4 (declining), the model limits the long-term score to +19 at most, before the trend word is chosen.</span></li>}
      </ul>
    </article>
  );
}

function VerdictChip({ a }: { a: TechAssessment }) {
  const v = verdictView(a);
  return (
    <div className={"pzt-verdict " + v.tone} role="group" aria-label={`Combined trend: ${v.word.replace("Trend: ", "")}. ${v.detail}`}>
      <span className="pzt-vk">Combined trend</span>
      <span className={"pzt-vchip " + v.tone}><i aria-hidden="true">{VSHAPE[v.tone]}</i>{v.word}</span>
      <span className="pzt-vd">{v.detail} It needs both scores and is separate from the 0 to 100 financial-health score.</span>
    </div>
  );
}

function SignalRow({ f }: { f: TechFactor }) {
  const g = factorGroup(f), s = f.signal;
  const label = safeText(f.label), detail = safeText(f.detail);
  const word = g === "unavailable" || s == null ? "Unavailable" : signalWord(s);
  return (
    <li className={"pzt-sg " + g} aria-label={`${label}: ${word.toLowerCase()}${detail ? `. ${detail}` : ""}`}>
      <span className="pzt-sg-n"><b>{label}</b>{detail && <small>{detail}</small>}</span>
      <span className="pzt-sg-b" aria-hidden="true"><i className="pzt-sg-t">{s != null && s !== 0 && <em className={s > 0 ? "up" : "dn"} style={{ width: `${Math.abs(s) * 50}%` }} />}</i></span>
      <span className="pzt-sg-w"><i aria-hidden="true">{g === "supporting" ? "▲" : g === "adverse" ? "▼" : g === "neutral" ? "◆" : "–"}</i>{word}</span>
    </li>
  );
}

function SignalList({ title, h, filter }: { title: string; h: TechHorizon; filter: FactorGroup | "all" }) {
  const rows = filterTechFactors(h.factors, filter), off = disabledFactors(h.factors);
  return (
    <section className="pzt-col" aria-label={`${title} signals`}>
      <h5>{title} signals <small>{h.availableCount} of {h.requiredCount} available</small></h5>
      {rows.length ? <ul className="pzt-sgl">{rows.map((f) => <SignalRow key={f.key} f={f} />)}</ul>
        : <p className="pzt-none">{h.factors.length ? `No ${FACTOR_GROUP_WORD[filter].toLowerCase()} signals here.` : "No signals were returned for this horizon."}</p>}
      {filter === "all" && off.length > 0 && <p className="pzt-off">Switched off in this model: {off.map((f) => safeText(f.label)).join(", ")}. It is not counted, and nothing replaces it.</p>}
    </section>
  );
}

function Signals({ a }: { a: TechAssessment }) {
  const [filter, setFilter] = useState<FactorGroup | "all">("all");
  const both = useMemo(() => [...a.shortTerm.factors, ...a.longTerm.factors], [a]);
  const count = (f: FactorGroup | "all") => filterTechFactors(both, f).length;
  return (
    <div className="pzt-sigs">
      <div className="pzr-tools pzr-noprint">
        <div className="pzr-chipsrow" role="group" aria-label="Filter signals">
          {FILTERS.map((f) => <button key={f} type="button" className={"pzr-chip" + (filter === f ? " on" : "")} aria-pressed={filter === f} onClick={() => setFilter(f)}>{FACTOR_GROUP_WORD[f]} <small>{count(f)}</small></button>)}
        </div>
      </div>
      <div className="pzt-cols"><SignalList title="Short-term" h={a.shortTerm} filter={filter} /><SignalList title="Long-term" h={a.longTerm} filter={filter} /></div>
    </div>
  );
}

const pctText = (v: number, d = 1) => minus((v >= 0 ? "+" : "") + v.toFixed(d)) + "%";

function Observations({ a }: { a: TechAssessment }) {
  const o = a.observations;
  const items: { k: string; v: string }[] = [];
  if (o.stage) items.push({ k: "Market stage", v: STAGE_WORD[o.stage] + (o.stage === 2 && o.freshStage2 != null ? (o.freshStage2 ? ". A fresh advance: it began within the last 60 sessions after a basing phase." : ". An established advance.") : ".") });
  if (o.slope150Pct != null) items.push({ k: "150-day average", v: `The 150-day average price has moved ${pctText(o.slope150Pct)} over the last 50 sessions.` });
  if (o.benchmark) items.push({ k: "Compared with", v: `${o.benchmark}, the index picked by the company's size.${o.benchmarksUsed.length > 1 ? ` Over the comparison window the size group changed, so it also used ${o.benchmarksUsed.filter((n) => n !== o.benchmark).join(", ")}.` : ""}` });
  if (o.beta != null) items.push({ k: "Beta", v: `${o.beta.toFixed(2)}. How strongly the stock has moved with that index (126 daily returns, kept between 0.30 and 3.00).` });
  if (o.rsRatingST != null) items.push({ k: "Short-term relative strength", v: `${o.rsRatingST.toFixed(1)} out of 100. Its recent gain over the index, allowing for beta, is at or above ${Math.round(o.rsRatingST)}% of the previous 126 sessions.` });
  if (o.rsRatingLT != null) items.push({ k: "Long-term relative strength", v: `${o.rsRatingLT.toFixed(1)} out of 100. The same comparison over the previous 252 sessions.` });
  if (!items.length) return <p className="pzt-none">No market observations were returned.</p>;
  return <dl className="pzt-obs">{items.map((i) => <div key={i.k}><dt>{i.k}</dt><dd>{i.v}</dd></div>)}</dl>;
}

function Missing({ a }: { a: TechAssessment }) {
  const groups = ([["Short term", a.shortTerm], ["Long term", a.longTerm]] as const).map(([n, h]) => [n, h.factors.filter((f) => f.status === "unavailable")] as const).filter(([, rows]) => rows.length);
  const incomplete = a.status === "incomplete";
  if (!incomplete && !groups.length) return null;
  return (
    <section className="pzt-miss" aria-label="Missing inputs">
      <h4><Icon name="alert" />{incomplete ? "Some inputs are missing" : "Inputs that could not be used"}</h4>
      <p>{incomplete ? "A score is shown only when every signal it needs is available. Missing signals are listed here with the reason; none is filled in or counted as neutral." : "These signals were not available. They are listed here with the reason."}</p>
      {groups.map(([n, rows]) => (
        <div key={n}><h5>{n}</h5><ul>{rows.map((f) => <li key={f.key}><b>{safeText(f.label)}</b><span>{safeText(f.detail) || "No reason was given."}</span></li>)}</ul></div>
      ))}
      {!groups.length && <p className="pzt-none">No individual signal is listed as missing; see the notes below.</p>}
    </section>
  );
}

function Source({ a }: { a: TechAssessment }) {
  const fresh = isFresh(a);
  return (
    <section className="pzt-src" aria-label="Where this comes from">
      <h4>Where this comes from</h4>
      <ul className="pzt-srcl">
        <li><Icon name="calendar" /><span><b>Prices as of {a.asOf ? dateIN(a.asOf) : "an unknown date"}</b>, the last completed daily session.{a.provider && a.provider !== "Unavailable" ? ` Daily prices from ${a.provider}.` : ""}</span></li>
        <li className={fresh ? "" : "warn"}><Icon name={fresh ? "check" : "alert"} /><span>{fresh ? "The latest price is within 10 days of when this was calculated." : "These prices may be out of date: the model withholds a current score when the latest price is more than 10 days old, or when it cannot tell."}</span></li>
        {a.usableDailyBars != null && <li><Icon name="activity" /><span>{a.usableDailyBars.toLocaleString("en-IN")} complete daily candles were usable{a.dailyBars != null && a.dailyBars !== a.usableDailyBars ? ` of ${a.dailyBars.toLocaleString("en-IN")} received` : ""}. Missing candles are never filled in.</span></li>}
        {a.modelVersion && <li><Icon name="info" /><span>Technical model {a.modelVersion}. Weekly signals use the week before the latest session.</span></li>}
      </ul>
      {a.benchmarkSources.length > 0 && (
        <div className="pzt-tw"><table className="pzt-tbl"><caption>Index price history used for comparison</caption>
          <thead><tr><th scope="col">Index</th><th scope="col">Source</th><th scope="col">Last date</th><th scope="col">Daily closes</th></tr></thead>
          <tbody>{a.benchmarkSources.map((s) => <tr key={s.name}><th scope="row">{s.name}</th><td>{s.provider ?? "—"}</td><td>{s.asOf ? dateIN(s.asOf) : "—"}</td><td>{s.bars != null ? s.bars.toLocaleString("en-IN") : "—"}</td></tr>)}</tbody></table></div>
      )}
      {a.notes.length > 0 && <ul className="pzt-notes" aria-label="Notes from the model">{a.notes.map((n, i) => <li key={i}>{safeText(n)}</li>)}</ul>}
    </section>
  );
}

/** A one-line pointer under the hero: the two words, linking to the section. Nothing when the report has no technical view. */
export function TechPointer({ report }: { report: PrismReport }) {
  const a = parseTechnical(report.technicalAssessment);
  if (!a) return null;
  const s = ratingWord(a.shortTerm.rating, a.shortTerm.score), l = ratingWord(a.longTerm.rating, a.longTerm.score);
  return (
    <p className="pzt-ptr pzr-noprint">
      <Icon name="activity" /><span>Technical view: short term <b>{s.word.toLowerCase()}</b>, long term <b>{l.word.toLowerCase()}</b>. Separate from the score above. <a href={`#${TECH_ID}`} aria-label="Go to the technical view">See the details</a></span>
    </p>
  );
}

export function Technical({ report, onRecalculate }: { report: PrismReport; onRecalculate?: () => void }) {
  const a = parseTechnical(report.technicalAssessment);
  if (!a) {
    return (
      <section className="pzr-sec pzt" id={TECH_ID} tabIndex={-1} aria-labelledby="pzt-h">
        <header className="pzr-sh"><h3 id="pzt-h">Technical view</h3><p>Recent price and trend behaviour, short term and long term.</p></header>
        <div className="pzt-empty" role="note">
          <Icon name="activity" />
          <div><b>This stored report does not include the technical view.</b>
            <p>It was calculated before the technical view was added. {onRecalculate ? <><button type="button" className="pzr-link pzr-noprint" onClick={onRecalculate}>Recalculate</button> to add it.</> : "Recalculate to add it."} The financial-health score above is unaffected.</p></div>
        </div>
        <p className="pzr-small pzt-line">{TECH_NOTE}</p>
      </section>
    );
  }
  const v = verdictView(a);
  return (
    <section className="pzr-sec pzt" id={TECH_ID} tabIndex={-1} aria-labelledby="pzt-h" aria-describedby="pzt-lead">
      <header className="pzr-sh"><h3 id="pzt-h">Technical view</h3>
        <p id="pzt-lead">How the share price has been behaving, in the recent weeks (short term) and over the past year or so (long term). It describes past prices and does not predict them. It is calculated separately from the 0 to 100 financial-health score and does not change it. Short term is {ratingWord(a.shortTerm.rating, a.shortTerm.score).word.toLowerCase()}; long term is {ratingWord(a.longTerm.rating, a.longTerm.score).word.toLowerCase()}; {v.word.toLowerCase()}.</p></header>
      <div className="pzt-cards">
        <HorizonCard name="Short term" h={a.shortTerm} id="pzt-st" />
        <HorizonCard name="Long term" h={a.longTerm} id="pzt-lt" />
      </div>
      <VerdictChip a={a} />
      <Missing a={a} />
      <div className="pzt-blk"><h4>Every signal</h4>
        <p className="pzt-sub">Each signal scores from −1 (adverse) to +1 (supporting) and the scores are combined into the numbers above. Neutral means the signal is flat; unavailable means it could not be calculated.</p>
        <Signals a={a} /></div>
      <div className="pzt-blk"><h4>What the market shows</h4><Observations a={a} /></div>
      <Source a={a} />
      <p className="pzr-small pzt-line">{TECH_NOTE} It is not an investment recommendation.</p>
    </section>
  );
}
