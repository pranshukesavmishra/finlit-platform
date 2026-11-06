import { MINUS } from "../lib/format";
import { bandInk, bandVar, scoreBand } from "../lib/scoreBands";
import { type Model, type Line, scoreOf } from "../lib/portfolioOverview";
import { dateText, plural, sizeLine } from "./derive";
import { SCALE_NOTE } from "./words";
import type { Meta, PageObject } from "./types";

const BANDS = [{ from: 0, w: 40, c: "lo" }, { from: 40, w: 20, c: "mo" }, { from: 60, w: 20, c: "hi" }, { from: 80, w: 20, c: "xh" }];
const modelName = (m: Model) => (m === "prism" ? "Prism" : "FinLit IQ");

/** The four tiles over the page: shares, average score of the plan's model, diversification score, how many independent stocks the list moves like. */
export function Summary({ page, metas, lines, model, n, state }: { page: PageObject | null; metas: Meta[]; lines: Line[]; model: Model; n: number; state: "loading" | "ready" | "error" | "none" }) {
  const scores = lines.map((l) => scoreOf(l.ov, model).value).filter((v): v is number => v != null);
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  const mix = { hi: 0, mid: 0, lo: 0 };
  scores.forEach((v) => { mix[scoreBand(v) as "hi" | "mid" | "lo"]++; });
  const eff = page?.score.effective_stocks ?? null, score = page?.score;
  const why = state === "loading" ? "Working out the figures…" : state === "error" ? "The figures could not be loaded." : "Needs 3 shares with a year of prices.";
  const nCorr = page?.order.length ?? 0;
  const dots = nCorr > 0 && nCorr <= 20 ? Array.from({ length: nCorr }, (_, i) => Math.max(0, Math.min(1, (eff ?? 0) - i))) : null;
  return (
    <section className="pfx-sum" aria-label="Summary">
      <div className="pfx-card pfx-k"><p className="pfx-eyebrow">Shares</p><p className="pfx-big">{n}</p>
        <p className="pfx-sub">{page ? <><span className="pfx-long">{sizeLine(page, metas)}</span><span className="pfx-compact">{sizeLine(page, metas, true)}</span></> : why}</p></div>
      <div className="pfx-card pfx-k"><p className="pfx-eyebrow"><span className="pfx-long">Average {modelName(model)} score</span><span className="pfx-compact">Avg {modelName(model)}</span></p>
        <p className="pfx-big" style={avg == null ? undefined : { color: bandInk(scoreBand(avg)) }}>{avg ?? MINUS}</p>
        {scores.length > 0 && <div className="pfx-mixbar" aria-hidden="true">{(["hi", "mid", "lo"] as const).map((b) => mix[b] > 0 && <span key={b} style={{ flex: mix[b], background: bandVar(b) }} />)}</div>}
        <p className="pfx-sub">{scores.length ? <><b className="pfx-hi">{mix.hi} green</b><span className="pfx-long"> (70+)</span> · <b className="pfx-mid">{mix.mid} orange</b><span className="pfx-long"> (50–69)</span><span className="pfx-long"> · {mix.lo} red</span></>
          : lines.length ? "No share is scored yet: scores appear as each report is ready." : MINUS}</p></div>
      <div className="pfx-card pfx-k"><p className="pfx-eyebrow"><span className="pfx-long">Diversification score</span><span className="pfx-compact">Diversification</span></p>
        <p className="pfx-big-row"><span className="pfx-big">{score ? score.score : MINUS}</span><span className="pfx-of">/ 100</span>{score && <span className="pfx-pill pfx-long">{score.band}</span>}</p>
        {score && <div className="pfx-scale" role="img" aria-label={`${score.score} out of 100: ${score.band}`}>{BANDS.map((b) => <span key={b.c} className={"s-" + b.c} style={{ flex: b.w }} />)}<i style={{ left: `${score.score}%` }} /></div>}
        <p className="pfx-sub">{score ? <><span className="pfx-compact pfx-bandword">{score.band}</span><span className="pfx-long">{SCALE_NOTE}</span></> : why}</p></div>
      <div className="pfx-card pfx-k"><p className="pfx-eyebrow">Moves like</p>
        <p className="pfx-big-row"><span className="pfx-big">{eff == null ? MINUS : eff.toFixed(1)}</span><span className="pfx-of">independent stocks<span className="pfx-compact"> of {nCorr}</span></span></p>
        {dots && <div className="pfx-dots" aria-hidden="true">{dots.map((f, i) => <span key={i}><i style={{ width: `${f * 100}%` }} /></span>)}</div>}
        {!dots && nCorr > 20 && <div className="pfx-ticks" aria-hidden="true"><i style={{ width: `${Math.min(100, ((eff ?? 0) / nCorr) * 100)}%` }} /></div>}
        <p className="pfx-sub">{page ? <>
          {page.first_k ? <>The first {page.first_k.k} of these moved like {page.first_k.effective_stocks.toFixed(1)}. The other {page.first_k.rest} added {page.first_k.added.toFixed(1)}.</>
            : <span className="pfx-long">out of {nCorr}, on {page.weeks} weekly prices to {dateText(page.to)}</span>}
          {page.first_k && <span className="pfx-long"> Out of {nCorr}, on {page.weeks} weekly prices to {dateText(page.to)}.</span>}
          {page.short_history.length > 0 && <> {plural(page.short_history.length, "share")} left out: under a year of prices.</>}</> : why}</p></div>
    </section>
  );
}
