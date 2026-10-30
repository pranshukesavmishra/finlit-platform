// The hero of a Prism report: company, the signature prism ring (four arcs, length = weight, fill = score), chips, coverage, actions
// and a score scale with the label thresholds. Status is always written in words next to any colour.
import { Icon } from "../../../lib/icons";
import { dateIN } from "../../../lib/format";
import {
  PRISM_NAME, PRISM_NOTE, completenessNote, notRatedReason, ringWhy, STATUS_TEXT, STATUS_WORD, isRated, labelTone, partInfo, partShare, pctWhole, ringSentence, score1, statementWord,
  type PrismRating, type PrismReport,
} from "../../../lib/prism";
import { THRESHOLDS, arcSegments, partVar } from "../../../lib/prismReport";
import { fmtScore, parseTechnical, ratingWord, scalePos, type TechHorizon, type TrendTone } from "../../../lib/prismTechnical";
import { TECH_SEPARATE_NOTE, horizonCaption } from "../../../stock/prismCardLogic";

export const istTime = (iso: string | null | undefined, withDate = true) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", ...(withDate ? { day: "numeric", month: "short", year: "numeric" } : {}), hour: "numeric", minute: "2-digit" }) + " IST";
};

export type ReportActions = {
  onRecalculate?: () => void; recalculating?: boolean;
};

export function StatusChip({ status }: { status: PrismReport["rating"]["status"] }) {
  return <span className={"pzr-st " + status.replace(" ", "-").toLowerCase()}><i aria-hidden="true" />{STATUS_WORD[status]}</span>;
}
export function LabelChip({ label }: { label: PrismReport["rating"]["label"] }) {
  const t = labelTone(label);
  return <span className={"pzr-lab " + t.tone}><i aria-hidden="true" />{t.word}</span>;
}

/* ---- the prism ring */
const CX = 150, R = 118;
const CIRC = 2 * Math.PI * R;
export function PrismRing({ rating, size = 300 }: { rating: Pick<PrismRating, "status" | "final" | "label" | "parts" | "partWeights">; size?: number }) {
  const rated = isRated(rating) && rating.final != null;
  const segs = arcSegments(rating);
  const rot = (frac: number) => `rotate(${(-90 + frac * 360).toFixed(2)} ${CX} ${CX})`;
  return (
    <svg className="pzr-ring" width={size} height={size} viewBox="0 0 300 300" role="img" aria-label={ringSentence(rating)}>
      <defs>
        <radialGradient id="pzr-core" cx="50%" cy="45%" r="55%"><stop offset="0" stopColor="#F4E3B0" stopOpacity=".22" /><stop offset="1" stopColor="#F4E3B0" stopOpacity="0" /></radialGradient>
      </defs>
      <circle cx={CX} cy={CX} r={R - 28} className="pzr-ring-core" />
      <circle cx={CX} cy={CX} r={R - 28} fill="url(#pzr-core)" />
      <circle cx={CX} cy={CX} r={R + 17} className="pzr-ring-halo" />
      {segs.map((s, i) => {
        const track = s.span * CIRC, fill = s.fill * CIRC;
        return (
          <g key={s.key} transform={rot(s.start)} style={{ "--c": partVar(s.key, i) } as React.CSSProperties}>
            <circle cx={CX} cy={CX} r={R} className="pzr-arc-track" strokeDasharray={`${track.toFixed(2)} ${CIRC.toFixed(2)}`} transform={`rotate(0 ${CX} ${CX})`} />
            {fill > 0.5 && <circle cx={CX} cy={CX} r={R} className="pzr-arc-fill" strokeDasharray={`${fill.toFixed(2)} ${CIRC.toFixed(2)}`}
              style={{ "--f": fill.toFixed(2), "--len": CIRC.toFixed(2), "--i": i } as React.CSSProperties} />}
          </g>
        );
      })}
      {rated ? <>
        <text x="150" y="164" textAnchor="middle" className="pzr-ring-n">{score1(rating.final)}</text>
        <text x="150" y="190" textAnchor="middle" className="pzr-ring-u">out of 100</text>
        <text x="150" y="108" textAnchor="middle" className="pzr-ring-k">{labelTone(rating.label).word}</text>
      </> : <>
        <text x="150" y="150" textAnchor="middle" className="pzr-ring-nr">Not rated</text>
        <text x="150" y="176" textAnchor="middle" className="pzr-ring-u">{ringWhy(rating)}</text>
      </>}
    </svg>
  );
}

/** The ring's key: each part with its weight and, when rated, its score. */
export function RingKey({ rating }: { rating: PrismRating }) {
  const rated = isRated(rating);
  return (
    <ul className="pzr-key" aria-label="The four parts of the ring">
      {arcSegments(rating).map((s, i) => (
        <li key={s.key} style={{ "--c": partVar(s.key, i) } as React.CSSProperties}>
          <i aria-hidden="true" /><span>{partInfo(s.key).name}</span><small>{partShare(rating.partWeights, s.key)}%</small><b>{rated && s.score != null ? score1(s.score) : "—"}</b>
        </li>
      ))}
    </ul>
  );
}

/** 0-100 scale with the label thresholds and a marker for the score. */
export function ScoreScale({ rating }: { rating: Pick<PrismRating, "status" | "final"> }) {
  const rated = isRated(rating) && rating.final != null;
  const bands = [["Poor", 0, 35], ["Weak", 35, 50], ["Average", 50, 65], ["Healthy", 65, 80], ["Strong", 80, 100]] as const;
  return (
    <div className="pzr-scale" role="img" aria-label={rated ? `Score ${score1(rating.final)} on a 0 to 100 scale. Weak starts at 35, Average at 50, Healthy at 65 and Strong at 80.` : "Score scale: no score because the company is not rated."}>
      <div className="pzr-scale-bar" aria-hidden="true">
        {bands.map(([w, a, b]) => <span key={w} style={{ flex: b - a }}><em>{w}</em></span>)}
        {rated && <i className="pzr-scale-mk" style={{ left: `${Math.max(0, Math.min(100, rating.final!))}%` }}><b>{score1(rating.final)}</b></i>}
      </div>
      <div className="pzr-scale-ticks" aria-hidden="true">{[0, ...THRESHOLDS, 100].map((t) => <span key={t} style={{ left: `${t}%` }}>{t}</span>)}</div>
    </div>
  );
}

/* ---- mini scores: the overall score and the two technical scores, small, beside the Recalculate button. Same words, shapes and numbers as the stock-page card. */
const SHAPE: Record<TrendTone, string> = { strongpos: "▲▲", pos: "▲", neutral: "◆", neg: "▼", strongneg: "▼▼", na: "–" };
const TONE_VAR: Record<TrendTone, string> = { strongpos: "--pz-strong", pos: "--pz-healthy", neutral: "--pz-average", neg: "--pz-weak", strongneg: "--pz-poor", na: "--pz-none" };

/** What a screen reader (and the tooltip) hears for a technical tile: "Technical short term +35: Positive, 5–20 sessions". */
export function miniTechLabel(title: string, h: TechHorizon): string {
  const cap = horizonCaption(h);
  if (h.score == null) return `${title}: not available${cap ? `, ${cap}` : ""}`;
  return `${title} ${fmtScore(h.score)}: ${ratingWord(h.rating, h.score).word}${cap ? `, ${cap}` : ""}`;
}
export function miniFundLabel(rating: Pick<PrismRating, "status" | "final" | "label">): string {
  return isRated(rating) && rating.final != null ? `Fundamental score ${score1(rating.final)} out of 100: ${labelTone(rating.label).word}` : "Fundamental score: not rated";
}

function TechMini({ title, h }: { title: string; h: TechHorizon }) {
  const { word, tone } = ratingWord(h.rating, h.score), has = h.score != null, label = miniTechLabel(title, h), cap = horizonCaption(h);
  return (
    <li className="pzr-mini" style={{ "--m": `var(${TONE_VAR[tone]})` } as React.CSSProperties} title={label} aria-label={label}>
      <span className="pzr-mini-k">{title}</span>
      <b className="pzr-mini-n">{fmtScore(h.score)}</b>
      <span className="pzr-mini-w"><i aria-hidden="true">{SHAPE[tone]}</i>{has ? word : "Not available"}</span>
      <span className="pzr-mini-bar pzr-mini-bar-t" aria-hidden="true">{has && <em style={{ left: `${scalePos(h.score)}%` }} />}</span>
      {cap && <small>{cap}</small>}
    </li>
  );
}

export function MiniScores({ report }: { report: PrismReport }) {
  const { rating } = report, rated = isRated(rating) && rating.final != null, tech = parseTechnical(report.technicalAssessment);
  const label = miniFundLabel(rating), t = labelTone(rating.label);
  return (
    <div className="pzr-minis" role="group" aria-label="Mini scores">
      <ul className="pzr-minis-l">
        <li className="pzr-mini pzr-mini-f" style={{ "--m": `var(${rated ? t.token : "--pz-none"})` } as React.CSSProperties} title={label} aria-label={label}>
          <span className="pzr-mini-k">Fundamental</span>
          {rated ? <b className="pzr-mini-n">{score1(rating.final)}</b> : <b className="pzr-mini-n pzr-mini-nr">Not rated</b>}
          <span className="pzr-mini-w">{rated ? t.word : "No score"}</span>
          <span className="pzr-mini-bar" aria-hidden="true">{rated && <u style={{ width: `${Math.max(0, Math.min(100, rating.final!))}%` }} />}</span>
          <small>out of 100</small>
        </li>
        <li className="pzr-mini-div" aria-hidden="true" />
        {tech ? <>
          <TechMini title="Technical short term" h={tech.shortTerm} />
          <TechMini title="Technical long term" h={tech.longTerm} />
        </> : (
          <li className="pzr-mini pzr-mini-q" style={{ "--m": "var(--pz-none)" } as React.CSSProperties}><span className="pzr-mini-k">Technical view</span><span className="pzr-mini-w">Recalculate to add</span></li>
        )}
      </ul>
      <p className="pzr-minis-n" title={TECH_SEPARATE_NOTE}>Technical is separate from the score</p>
    </div>
  );
}

export function Hero({ report, actions }: { report: PrismReport; actions: ReportActions }) {
  const { rating, company } = report;
  return (
    <section className="pzr-hero" aria-label={`${PRISM_NAME} rating for ${company.name}`}>
      <div className="pzr-hero-in">
        <div className="pzr-hero-l">
          <p className="pzr-kick"><Icon name="prism" />{PRISM_NAME} · Financial health</p>
          <h2>{company.name}</h2>
          <p className="pzr-meta">
            <span className="pzr-sym">{company.symbol}</span>
            <span>{company.industry || company.sector || "Industry unavailable"}</span>
            <span>{statementWord(report.statementType)} statements</span>
          </p>
          <div className="pzr-chips">
            <LabelChip label={rating.label} /><StatusChip status={rating.status} />
          </div>
          <p className="pzr-lede">{notRatedReason(rating) ?? STATUS_TEXT[rating.status]}</p>
          <p className="pzr-cov"><Icon name="quality" /><span><b>{pctWhole(rating.confidence)} of inputs available</b>, and {rating.judgedQuarters} of 10 comparable quarters.</span></p>
          <p className="pzr-cov-n">This is completeness of the data behind the score. It is not a probability and does not predict returns.{completenessNote(rating) ? " " + completenessNote(rating) : ""}</p>
          <div className="pzr-acts">
            <MiniScores report={report} />
            <div className="pzr-noprint pzr-acts-r"><button type="button" className="btn" onClick={actions.onRecalculate} disabled={actions.recalculating}><Icon name="refresh" />{actions.recalculating ? "Recalculating…" : "Recalculate"}</button></div>
          </div>
        </div>
        <div className="pzr-hero-r">
          <PrismRing rating={rating} />
          <RingKey rating={rating} />
        </div>
      </div>
      <ScoreScale rating={rating} />
      <div className="pzr-hero-foot">
        <span>Model {rating.modelVersion}</span>
        <span>Calculated {istTime(report.createdAt)}{report.cached ? " · stored report" : ""}</span>
        {report.technical?.asOf && <span data-testid="tech-asof">Technical view as of {dateIN(report.technical.asOf)}{report.technical.refreshing ? " (updating)" : ""}</span>}
      </div>
      <p className="pzr-note">{PRISM_NOTE}</p>
    </section>
  );
}
