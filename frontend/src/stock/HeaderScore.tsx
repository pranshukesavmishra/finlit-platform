// The top of a stock page, next to the company name: the fundamental dots (one per FinLit pillar, coloured by the shared band rule), a score badge that
// depends on the plan, and the labelled industry / market cap line. Pure rules are in lib/scoreBands.ts. Research summary, not a recommendation.
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { bandLegend } from "../lib/prismTechnical";
import "../styles/dash-shared.css";
import "../styles/headerscore.css";
import { BAND_NAME, GOLD_DOTS, LEGEND, badgeFor, badgeView, dotLabel, goldDots, industryText, marketCapLine, scoreBand, type BadgeView, type Plan, type PrismInput } from "../lib/scoreBands";
import type { PillarSummary, Profile } from "../lib/api";

/** The five pillars in the order the founder listed them, with the one letter drawn inside each dot. */
export const DOT_ORDER: { key: string; name: string; letter: string }[] = [
  { key: "quality", name: "Quality", letter: "Q" }, { key: "growth", name: "Growth", letter: "G" }, { key: "profitability", name: "Profitability", letter: "P" },
  { key: "balance", name: "Balance sheet", letter: "B" }, { key: "technical", name: "Technical", letter: "T" },
];

export function dotsOf(pillars: PillarSummary[]) {
  return DOT_ORDER.map((d) => { const pl = pillars.find((x) => x.key === d.key), v = pl?.score ?? null; return { ...d, value: v, band: scoreBand(v), label: dotLabel(d.name, v, pl?.band?.label) }; });
}

/** "What do the dots mean?" popover: each dot's pillar and the colour rule. Closes on Escape or a click elsewhere. `gold`: the six FinLit Prism dots. */
function DotsLegend({ gold = false }: { gold?: boolean }) {
  const [open, setOpen] = useState(false);
  const id = "hs-leg-" + useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const down = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", key); document.addEventListener("pointerdown", down, true);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", down, true); };
  }, [open]);
  return (
    <span className="hs-leg" ref={box}>
      <button type="button" className="hs-leg-b" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}><Icon name="info" /><span>What do the dots mean?</span></button>
      <div id={id} className="hs-leg-p" role="group" aria-label="What the dots mean" hidden={!open}>
        {gold ? <>
          <p><b>Six dots from FinLit Prism:</b> four fundamental, then (after the gap) two technical.</p>
          <ul className="hs-leg-g">{GOLD_DOTS.map((d) => <li key={d.key}><span className="hs-dot band-na" aria-hidden="true">{d.letter}</span><span><b>{d.name}</b>{": "}{d.what}</span></li>)}</ul>
          <p><b>Fundamental dots (0 to 100):</b></p>
          <ul className="hs-leg-c">{LEGEND.map((l) => <li key={l.band}><span className={"hs-sw band-" + l.band} aria-hidden="true" /><b>{BAND_NAME[l.band][0].toUpperCase() + BAND_NAME[l.band].slice(1)}</b>{": "}{l.rule}</li>)}</ul>
          <p><b>Technical dots (−100 to +100):</b> green is a positive trend, orange neutral, red negative, grey not available. {bandLegend()}</p>
          <p>Higher is better for all four fundamental dots; a high Risk score means lower risk. The technical dots describe recent price behaviour and are not part of the Prism score.</p>
          <p className="hs-leg-n">Research summary, not a recommendation.</p>
        </> : <>
        <p><b>One dot for each part of the FinLit score.</b> Colour follows the score of that part, out of 100.</p>
        <ul className="hs-leg-d">{DOT_ORDER.map((d) => <li key={d.key}><span className="hs-dot band-na" aria-hidden="true">{d.letter}</span>{d.name}</li>)}</ul>
        <ul className="hs-leg-c">{LEGEND.map((l) => <li key={l.band}><span className={"hs-sw band-" + l.band} aria-hidden="true" /><b>{BAND_NAME[l.band][0].toUpperCase() + BAND_NAME[l.band].slice(1)}</b>{": "}{l.rule}</li>)}</ul>
        <p>In FinLit Prism, Fundamentals, Valuation, Quality and Risk are all higher-is-better (a high Risk score means lower risk); its Technical view is separate, from −100 to +100.</p>
        <p className="hs-leg-n">Research summary, not a recommendation. The word beside each score (Strong, Healthy, Mixed, Weak) is the model's own.</p>
        </>}
      </div>
    </span>
  );
}

export function FundamentalDots({ pillars }: { pillars: PillarSummary[] }) {
  return (
    <div className="hs-dots" role="group" aria-label="Fundamental dots: one per FinLit pillar">
      <ul>{dotsOf(pillars).map((d) => <li key={d.key}><span className={"hs-dot band-" + d.band} role="img" title={d.label} aria-label={d.label}>{d.letter}</span></li>)}</ul>
      <DotsLegend />
    </div>
  );
}

/** The six FinLit Prism dots for the Gold plan: four fundamental, a thin gap, two technical. Null while the report loads. */
export function PrismDots({ prism }: { prism: PrismInput }) {
  const dots = goldDots(prism);
  if (!dots) return null;
  return (
    <div className="hs-dots hs-gold" role="group" aria-label="FinLit Prism dots: four fundamental and two technical">
      <ul>{dots.map((d, i) => <li key={d.key} className={i > 0 && d.group !== dots[i - 1].group ? "hs-gap" : undefined}><span className={"hs-dot band-" + d.band} role="img" title={d.label} aria-label={d.label}>{d.letter}</span></li>)}</ul>
      <DotsLegend gold />
    </div>
  );
}

export function ScoreBadge({ view, symbol }: { view: BadgeView; symbol: string }) {
  if (view.kind === "none") return null;
  if (view.kind === "prism-none") return <div className="hs-badge band-na"><span className="hs-bk">FinLit Prism</span><span className="hs-bw">Prism: not rated yet</span><Link className="hs-bl" to={`/prism/${encodeURIComponent(symbol)}`}>Open the Prism page</Link></div>;
  const prism = view.kind === "prism", n = view.score == null ? null : prism ? view.score.toFixed(1) : String(Math.round(view.score));
  const text = n == null ? "FinLit score: not scored yet" : `${prism ? "FinLit Prism" : "FinLit score"} ${n} out of 100: ${view.word}${prism && view.provisional ? ", provisional" : ""}`;
  return (
    <div className={"hs-badge band-" + view.band} role="group" aria-label={text} title={text}>
      <span className="hs-bk">{prism ? "FinLit Prism" : "FinLit score"}</span>
      {n == null ? <span className="hs-bw">Not scored yet</span> : <><span className="hs-bn">{n}</span><span className="hs-bw">{view.word}{prism && view.provisional ? " · provisional" : ""}</span></>}
    </div>
  );
}

/** Labelled chips: Industry and Market cap, shown to every plan (public company facts). */
export function CompanyFacts({ p }: { p: Profile }) {
  const ind = industryText(p), cap = marketCapLine(p.marketCapCr);
  if (!ind && !cap) return null;
  return (
    <dl className="hs-facts">
      {ind && <div><dt>Industry</dt><dd>{ind}</dd></div>}
      {cap && <div><dt>Market cap</dt><dd>{cap.replace(/^Market cap /, "")}</dd></div>}
    </dl>
  );
}

type ScoreLike = { overall: number | null; band: { label: string }; pillars: PillarSummary[] };
/** Whether the pillar scores may be shown: they are part of the Silver plan (a free example company counts as Gold). */
export const showsScores = (plan: Plan, admin: boolean) => plan !== "basic" || admin;

/** Next to the company name: Silver the five FinLit pillar dots; Gold (and admin) the six FinLit Prism dots, never the pillar dots. Basic none. */
export function NameDots({ score, plan, admin, prism }: { score: ScoreLike; plan: Plan; admin: boolean; prism: PrismInput }) {
  if (badgeFor(plan, admin) === "prism") return <PrismDots prism={prism} />;
  return showsScores(plan, admin) ? <FundamentalDots pillars={score.pillars} /> : null;
}

/** Under the company name: the plan's score badge and the labelled industry / market cap chips. `plan` is the effective plan. */
export function SubLine({ profile, score, plan, admin, prism }: { profile: Profile; score: ScoreLike; plan: Plan; admin: boolean; prism: PrismInput }) {
  const view = badgeView(plan, admin, { overall: score.overall, word: score.band.label }, prism);
  return (
    <div className="hs-sub">
      <ScoreBadge view={view} symbol={profile.symbol} />
      <CompanyFacts p={profile} />
    </div>
  );
}
