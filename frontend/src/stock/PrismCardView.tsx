// FinLit Prism card on the stock page, the drawing of its two sections: "Fundamental analysis" (a segmented score ring, one arc per component sized by its
// weight and coloured by its band, and one card per component) and "Technical analysis" (the short-term and long-term panels and the trend alignment).
// Everything shown is read from the stored report (rating, weights, technicalAssessment); the rules (words, bands, captions) are in prismCardLogic.ts and lib/.
// Meaning is always in words and shapes (the status word, the number, the arrows); colour only decorates. The ring and the bars are hidden from screen
// readers because every component and horizon carries its numbers and words in its own accessible name. Styles: styles/prism-card.css (classes pcx-*).
import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { Icon } from "../lib/icons";
import { bandInk, bandVar, partHint, scoreBand, trendBand as toneBand, type ScoreBand } from "../lib/scoreBands";
import { TECH_NOTE, bandWidths, fmtScore, ratingWord, scalePos, trendAlignment, type TechAssessment, type TechHorizon, type TrendTone, type VerdictTone } from "../lib/prismTechnical";
import { TICKS, zoneBg } from "../components/prism/shared/PartTile";
import { LABEL, type PrismLatest } from "./PrismCard";
import { PrismTechRow, TechAsOf } from "./PrismTechRow";
import { PART_LINE, SCORE_NOTE_WITH_TECH, FUND_NOTE, TECH_SEPARATE_NOTE, TECH_SUBTITLE, alignSentence, arcPath, basedOn, fmtNum, fundSubtitle, horizonCaption, horizonLabel, partTip, partWord, polar, ringArcs, signalsLine, techEdgePos, type CardPart } from "./prismCardLogic";

const SHAPE: Record<TrendTone, string> = { strongpos: "▲▲", pos: "▲", neutral: "◆", neg: "▼", strongneg: "▼▼", na: "–" };
const VSHAPE: Record<VerdictTone, string> = { pos: "▲", mixed: "◆", neg: "▼", na: "–" };
const vBand = (t: VerdictTone): ScoreBand => (t === "pos" ? "hi" : t === "mixed" ? "mid" : t === "neg" ? "lo" : "na");

/** A small "i" that explains itself on hover and on keyboard focus. The text is also its accessible name. */
export function InfoTip({ text, end = false }: { text: string; end?: boolean }) {
  return <span className={"pcx-i" + (end ? " end" : "")} tabIndex={0} role="img" aria-label={text}>i<span className="pcx-tip" aria-hidden="true">{text}</span></span>;
}

/* ------------------------------------------------------------------ the segmented ring */
const C = 80, RA = 64, SW = 10, CAP = ((SW / 2) / RA) * (180 / Math.PI);   // centre, radius, stroke width, and the angle a round cap adds at each end

export function SegRing({ parts, score, word, tone, hot, onHot, example = false }: { parts: CardPart[]; score: number | null; word: string; tone: ScoreBand; hot: string | null; onHot: (k: string | null) => void; example?: boolean }) {
  const id = "pcr" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const arcs = ringArcs(parts.map((p) => ({ key: p.key, weight: p.weight, value: p.value })), 9);
  return (
    <span className="pcx-ring" aria-hidden="true">
      <svg viewBox="0 0 160 160">
        <defs><radialGradient id={`${id}d`} cx=".5" cy=".3" r=".85"><stop offset="0" stopColor="var(--dk-disc-1)" /><stop offset=".6" stopColor="var(--dk-disc-2)" /><stop offset="1" stopColor="var(--dk-disc-3)" /></radialGradient></defs>
        {Array.from({ length: 60 }, (_, i) => { const [x0, y0] = polar(C, C, 77.5, i * 6), [x1, y1] = polar(C, C, i % 5 === 0 ? 73.5 : 75.5, i * 6); return <line key={i} className={"pcx-tk" + (i % 5 === 0 ? " maj" : "")} x1={x0.toFixed(2)} y1={y0.toFixed(2)} x2={x1.toFixed(2)} y2={y1.toFixed(2)} />; })}
        {arcs.map((a, i) => {
          const s = a.a0 + CAP, e = Math.max(s + 0.5, a.a1 - CAP), v = a.value ?? 0;
          const [kx, ky] = polar(C, C, RA, s + ((e - s) * v) / 100);
          const p = parts[i];
          return (
            <g key={a.key} className={"pcx-arc" + (hot === a.key ? " hot" : "")} style={{ "--pc": bandVar(a.band), "--i": i } as CSSProperties} onMouseEnter={() => onHot(a.key)} onMouseLeave={() => onHot(null)}>
              <title>{partTip(p.name, p.value, partWord(p.value)[0], p.weight)}</title>
              <path className="pcx-hit" d={arcPath(C, C, RA, s, e)} />
              <path className="pcx-trk" d={arcPath(C, C, RA, s, e)} />
              {v > 0 && <><path className="pcx-fill" d={arcPath(C, C, RA, s, e)} pathLength={100} strokeDasharray={`${v} 100`} /><circle className="pcx-knob" cx={kx.toFixed(2)} cy={ky.toFixed(2)} r="3" /></>}
            </g>
          );
        })}
        <circle className="pcx-disc" cx={C} cy={C} r="49" fill={`url(#${id}d)`} />
        <circle className="pcx-disc2" cx={C} cy={C} r="44" />
        {score == null
          ? <><text className="pcx-nr" x={C} y={C + 4} textAnchor="middle">Not rated</text><text className="pcx-of" x={C} y={C + 20} textAnchor="middle">{example ? "EXAMPLE" : "NO SCORE"}</text></>
          : <><text className={"pcx-num band-" + tone} x={C} y={C + 6} textAnchor="middle">{score.toFixed(1)}</text><text className="pcx-of" x={C} y={C + 21} textAnchor="middle">{example ? "EXAMPLE" : "/ 100"}</text>{!example && <text className={"pcx-wd band-" + tone} x={C} y={C + 35} textAnchor="middle">{word.toUpperCase()}</text>}</>}
      </svg>
    </span>
  );
}

/* ------------------------------------------------------------------ one component card */
function CardRing({ value, band }: { value: number | null; band: ScoreBand }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <span className="pcx-cr" aria-hidden="true">
      <svg viewBox="0 0 38 38"><circle className="pcx-cr-bg" cx="19" cy="19" r="15" />{v > 0 && <circle className="pcx-cr-fg" cx="19" cy="19" r="15" pathLength={100} strokeDasharray={`${v} 100`} />}</svg>
      <b className={"band-" + band}>{value == null ? "—" : fmtNum(value)}</b>
    </span>
  );
}

/** The thin scale bar: soft zones per label band, the coloured fill up to the score, tick marks at the label edges (35, 50, 65, 80) and a marker. */
export function ScaleBar({ value, ticks = TICKS }: { value: number | null; ticks?: number[] }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <span className="pcx-bar" aria-hidden="true" style={{ background: zoneBg(ticks) }}>
      <i className="pcx-bar-fill" style={{ width: `${v}%` }} />
      {ticks.map((t) => <u key={t} style={{ left: `${t}%` }} />)}
      {value != null && <em style={{ left: `${v}%` }} />}
    </span>
  );
}

function PartCard({ p, index, hot, onHot, last, example }: { p: CardPart; index: number; hot: string | null; onHot: (k: string | null) => void; last: boolean; example: boolean }) {
  const band = scoreBand(p.value), [word, tone] = partWord(p.value), tip = partTip(p.name, p.value, word, p.weight), hint = partHint(p.key);
  return (
    <div className={"pcx-card band-" + band + (hot === p.key ? " hot" : "")} role="group" tabIndex={0} aria-label={tip + (hint ? " " + hint.long : "") + (example ? " Example numbers." : "")}
      style={{ "--pc": bandVar(band), "--i": index } as CSSProperties} onMouseEnter={() => onHot(p.key)} onMouseLeave={() => onHot(null)} onFocus={() => onHot(p.key)} onBlur={() => onHot(null)}>
      <span className="pcx-ct"><CardRing value={p.value} band={band} /><span className="pcx-w">{p.weight}%</span></span>
      <h5>{p.name}</h5>
      <p className="pcx-d">{PART_LINE[p.key] ?? ""}</p>
      <span className={"dk-st pcx-chip " + tone} style={band === "na" ? undefined : ({ "--tc": bandInk(band) } as CSSProperties)}>{word}</span>
      <ScaleBar value={p.value} />
      <span className={"pcx-tip" + (last ? " end" : "")} aria-hidden="true">{tip}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ section 1: Fundamental analysis */
export function FundamentalSection({ r, parts, example = false, children }: { r: PrismLatest["rating"]; parts: CardPart[]; example?: boolean; /** the status words under the ring (rated or provisional, coverage, the reason when not rated) */ children?: ReactNode }) {
  const [hot, setHot] = useState<string | null>(null);
  const rated = r.status !== "NOT RATED" && r.final != null, [word] = LABEL[r.label];
  const techIn = parts.some((p) => p.key === "technical");
  const n = parts.length, hasRisk = parts.some((p) => p.key === "risk");
  return (
    <section className="pcx-sec fund" aria-label={techIn ? "The Prism score and its components" : "Fundamental analysis"}>
      <header className="pcx-sh">
        <span className="pcx-ic" aria-hidden="true"><Icon name="coins" /></span>
        <div className="pcx-ht"><h3>{techIn ? "Prism score" : "Fundamental analysis"}</h3><p>{fundSubtitle(n)}</p></div>
        <p className="pcx-note"><Icon name="info" /><span>{techIn ? SCORE_NOTE_WITH_TECH : FUND_NOTE}</span></p>
      </header>
      <div className="pcx-fb">
        <div className="pcx-rc">
          <SegRing parts={parts} score={rated ? (r.final as number) : null} word={word} tone={rated ? scoreBand(r.final) : "na"} hot={hot} onHot={setHot} example={example} />
          <p className="pcx-cap">{techIn ? "Overall Prism score" : "Cumulative fundamental score"}<InfoTip text={`The total of the component scores, each counted by its weight. Arc length shows a component's weight; the coloured part shows its score.`} /></p>
          <p className="pcx-bo">{basedOn(n, hasRisk)}</p>
        </div>
        <div className="pcx-cs">
          <h4>{techIn ? "Components (weighted)" : "Fundamental components (weighted)"}</h4>
          <div className="pcx-grid" style={{ "--n": n } as CSSProperties} role="group" aria-label={example ? "The components of a Prism rating (example numbers)" : "The components of the Prism rating"}>
            {parts.map((p, i) => <PartCard key={p.key} p={p} index={i} hot={hot} onHot={setHot} last={i === parts.length - 1} example={example} />)}
          </div>
        </div>
        {children && <div className="pcx-fs">{children}</div>}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ section 2: Technical analysis */
function HorizonPanel({ title, h, index }: { title: string; h: TechHorizon; index: number }) {
  const w = ratingWord(h.rating, h.score), has = h.score != null, band = toneBand(w.tone), cap = horizonCaption(h), sig = signalsLine(h), widths = bandWidths(), edges = techEdgePos();
  return (
    <div className={"pcx-hz " + w.tone} role="group" aria-label={horizonLabel(title, h)} style={{ "--pc": bandVar(band), "--i": index } as CSSProperties}>
      <div className="pcx-hh">
        <div className="pcx-hn"><h4>{title}</h4>{cap && <small>{cap}</small>}</div>
        <span className={"pcx-badge band-" + band}>{has ? fmtScore(h.score) : "—"}</span>
        <span className="pcx-hw" style={has ? ({ "--tc": bandInk(band) } as CSSProperties) : undefined}><i aria-hidden="true">{SHAPE[w.tone]}</i>{w.word}</span>
      </div>
      <span className="pcx-sc" aria-hidden="true">
        <span className="pcx-zones">{widths.map((x, i) => <i key={i} className={"z" + (i + 1)} style={{ width: `${x}%` }} />)}</span>
        {edges.map((e) => <u key={e} style={{ left: `${e}%` }} />)}
        {has && <em style={{ left: `${scalePos(h.score)}%` }} />}
      </span>
      <span className="pcx-sl" aria-hidden="true"><span>Strongly negative</span><span>Neutral</span><span>Strongly positive</span></span>
      {sig && <p className={"pcx-sg" + (h.availableCount < h.requiredCount ? " warn" : "")}>{sig}</p>}
    </div>
  );
}

export function TechnicalSection({ a, report, onRecalculate, busy }: { a: TechAssessment | null; report: PrismLatest; onRecalculate?: () => void; busy?: boolean }) {
  const al = a ? trendAlignment(a.shortTerm.score, a.longTerm.score) : null;
  return (
    <section className="pcx-sec tech" aria-label="Technical analysis, separate from the Prism score">
      <header className="pcx-sh">
        <span className="pcx-ic" aria-hidden="true"><Icon name="line" /></span>
        <div className="pcx-ht"><div className="pcx-hrow"><h3>Technical analysis</h3><InfoTip text={TECH_NOTE} /></div><p>{TECH_SUBTITLE}</p></div>
        <p className="pcx-note"><Icon name="info" /><span>{TECH_SEPARATE_NOTE}</span></p>
      </header>
      {a ? (
        <>
          <div className="pcx-tp" role="group" aria-label="Technical view, separate from the Prism score: short term and long term">
            <HorizonPanel title="Technical short term" h={a.shortTerm} index={0} />
            <HorizonPanel title="Technical long term" h={a.longTerm} index={1} />
          </div>
          {al && (
            <div className={"pcx-al " + al.tone} role="group" aria-label={`Trend alignment: ${al.label}. ${alignSentence(al)}`} style={{ "--pc": bandVar(vBand(al.tone)) } as CSSProperties}>
              <span className="pcx-ai" aria-hidden="true"><Icon name="bars" /></span>
              <span className="pcx-ak">Trend alignment<InfoTip text={al.rule} /></span>
              <span className="pcx-asp" aria-hidden="true" />
              <span className="pcx-ash" aria-hidden="true">{VSHAPE[al.tone]}</span>
              <span className="pcx-at"><b>{al.label}</b><small>{alignSentence(al)}</small></span>
            </div>
          )}
          <TechAsOf asOf={report.technical?.asOf ?? a.asOf} stale={report.technical?.stale} refreshing={report.technical?.refreshing} />
        </>
      ) : <div className="pcx-tq"><PrismTechRow report={report} onRecalculate={onRecalculate} busy={busy} /></div>}
    </section>
  );
}

/** The loading shape: the same two sections, empty. */
export function CardSkeleton() {
  return (
    <div className="pcx-skel" aria-hidden="true">
      <div className="pcx-skel-sec"><div className="skeleton s-line" /><div className="pcx-skel-fb"><div className="skeleton s-ring" /><div className="pcx-skel-grid">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton s-card" />)}</div></div></div>
      <div className="pcx-skel-sec"><div className="skeleton s-line" /><div className="pcx-skel-grid two"><div className="skeleton s-panel" /><div className="skeleton s-panel" /></div></div>
    </div>
  );
}
