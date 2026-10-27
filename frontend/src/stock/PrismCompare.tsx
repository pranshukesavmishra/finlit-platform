// The right half of the stock page's first dashboard: FinLit Prism beside the FinLit score (left half, in Hero.tsx).
// Compact by design: one row each for the header, the score (prism glyph + words), the parts (tiles), the top pros and cons, and a footer.
// The left half uses the same row grid, so the two halves line up. The full lists live in PrismDetail, which the page shows under the pair
// when the person presses "Show full breakdown".
// Gold members (and everyone on a free example company) see the newest stored rating; others see a locked teaser.
// A company with no stored rating is calculated automatically when the page opens; recalculating is a button. Anything unexpected hides the half and the score fills the row.
import { useContext, useEffect, useRef } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Icon } from "../lib/icons";
import { dateIN } from "../lib/format";
import { useGold } from "../lib/premium";
import { Gate, OpenAccess } from "../components/Gate";
import { PartTile, type Tone } from "../components/prism/shared/PartTile";
import { PrismGlyph } from "../components/prism/shared/PrismGlyph";
import { LABEL, STATUS, fmtScore, generateFailure, generatePrism, pct, prismSummary, usePrismLatest, type PrismCardState, type PrismLatest } from "./PrismCard";
import { PRISM_NOTE, PRISM_PARTS, PRISM_POINTS } from "./prismWords";
import { PrismTechRow } from "./PrismTechRow";
import "../styles/prism-compare.css";

const STATUS_NOTE: Record<PrismLatest["rating"]["status"], string> = {
  RATED: "Enough of the data was available for a full rating.",
  PROVISIONAL: "Some data is missing or the record is short, so this is a first view and is shown at most as Healthy.",
  "NOT RATED": "Too little verified data to rate this company, so there is no score.",
};
/** Words for a part's score, on the same scale as the overall label. Colour is decoration; the word carries the meaning. */
const partWord = (v: number | null | undefined): [string, string] => v == null ? ["No data", "na"] : v >= 80 ? ["Strong", "strong"] : v >= 65 ? ["Healthy", "healthy"] : v >= 50 ? ["Average", "mixed"] : v >= 35 ? ["Weak", "weak"] : ["Poor", "weak"];

type Part = { key: string; name: string; weight: number; color: string; value: number | null };
/** The parts to draw, from the data: the four of the model, and a technical part the moment the model sends one. */
export function partsOf(r: PrismLatest["rating"]): { parts: Part[]; technicalSoon: boolean } {
  const w = r.partWeights ?? {};
  const rated = r.status !== "NOT RATED";   // the model withholds category scores for a company it did not rate; so do we
  const parts: Part[] = PRISM_PARTS.map(([k, name, share, color]) => ({ key: k, name, weight: Math.round((w[k] ?? share / 100) * 100), color, value: rated ? r.parts?.[k] ?? null : null }));
  const tech = rated ? r.parts?.technical : null;
  if (tech !== undefined && w.technical != null) parts.push({ key: "technical", name: "Technical", weight: Math.round(w.technical * 100), color: "--p-tech", value: tech });
  return { parts, technicalSoon: !parts.some((p) => p.key === "technical") };
}

/** One row of compact tiles: the four parts, and a fifth the moment the data has a technical part. */
function Tiles({ r, example = false }: { r: PrismLatest["rating"]; example?: boolean }) {
  const { parts } = partsOf(r);
  return (
    <div className="dk-tiles pzs-parts" style={{ "--n": parts.length } as React.CSSProperties} role="group" aria-label={example ? "The four parts of a Prism rating (example numbers)" : "The parts of the Prism rating"}>
      {parts.map((p, i) => { const [word, tone] = partWord(p.value); return <PartTile key={p.key} name={p.name} value={p.value} word={word} tone={tone as Tone} color={p.color} weight={p.weight} index={i} />; })}
    </div>
  );
}

const items = (r: PrismLatest, kind: "pros" | "cons") => (r.review?.parts ?? []).flatMap((p) => p[kind] ?? []).slice(0, 2);

/** The top two pros and cons, one line each. "More" opens the full report; the full lists are in the expanded breakdown. */
function Notes({ r, symbol }: { r: PrismLatest; symbol: string }) {
  const pros = items(r, "pros"), cons = items(r, "cons");
  const col = (tone: "pro" | "con", list: typeof pros) => (
    <div className={"dk-pc " + tone}>
      <div className="dk-pc-h"><Icon name={tone === "pro" ? "check" : "alert"} /><span>{tone === "pro" ? <>Supports<span className="hide-sm"> the rating</span></> : "Weighs on it"}</span><Link to={`/prism/${encodeURIComponent(symbol)}`} aria-label={`More about what ${tone === "pro" ? "supports" : "weighs on"} the rating`}>More</Link></div>
      {list.length ? <ul>{list.map((i) => <li key={i.metric} title={`${i.label}. ${i.summary}`}><b>{i.label}</b><span>{i.summary}</span></li>)}</ul> : <p>Nothing stands out.</p>}
    </div>
  );
  return <div className="dk-notes">{col("pro", pros)}{col("con", cons)}</div>;
}

function Body({ state, symbol, statement, name }: { state: Exclude<PrismCardState, { kind: "locked" | "hidden" }>; symbol: string; statement: string; name: string }) {
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: (refresh: boolean) => generatePrism(symbol, statement, refresh),
    onSuccess: (report) => { const next: PrismCardState = { kind: "report", report }; qc.setQueryData(["prism-latest", symbol, statement], next); qc.invalidateQueries({ queryKey: ["prism", "latest", symbol] }); },
  });
  const busy = run.isPending;
  // A company with no stored rating is calculated as soon as the page opens (once per company; a failure shows its message and a retry button).
  const started = useRef("");
  const key = `${symbol}|${statement}`;
  useEffect(() => {
    if (state.kind === "none" && started.current !== key && !run.isPending) { started.current = key; run.mutate(false); }
  }, [state.kind, key]);   // eslint-disable-line react-hooks/exhaustive-deps
  const status = busy ? <p className="pz-busy" role="status"><span className="pzs-spin" aria-hidden="true" />Calculating the rating from the latest filings and prices. This usually takes under half a minute; you can keep reading.</p>
    : run.isError ? <p className="pz-err" role="alert"><Icon name="alert" />{generateFailure(run.error)}</p> : null;
  if (state.kind === "none") return (
    <div className="dk-empty">
      <PrismGlyph parts={PRISM_PARTS.map(([k, n, w, c]) => ({ key: k, name: n, weight: w, value: null, color: c }))} score={null} size={120} />
      <div className="dk-empty-t">
        <h3>No Prism rating for {name} yet</h3>
        <p>Prism rates a company's financial health in four parts: Fundamentals, Valuation, Quality and Risk. It reads the latest filings and prices, which usually takes under half a minute the first time. It is being calculated now and the result then stays stored here.</p>
        <div className="dk-empty-a">
          <button className="btn primary dk-b" disabled={busy} onClick={() => run.mutate(false)}>{busy ? "Calculating…" : run.isError ? "Try again" : "Generate the Prism rating"} <Icon name="arrow" /></button>
          <Link className="pzs-link" to={`/prism/${encodeURIComponent(symbol)}`}>Open the Prism page for {symbol}</Link>
        </div>
        {status}
      </div>
    </div>
  );
  const rep = state.report, r = rep.rating, rated = r.status !== "NOT RATED" && r.final != null, [word, tone] = LABEL[r.label];
  const { parts } = partsOf(r);
  return (
    <>
      <div className="dk-row" role="group" aria-label={prismSummary(r)}>
        <PrismGlyph parts={parts.map((p) => ({ key: p.key, name: p.name, weight: p.weight, value: p.value, color: p.color }))} score={rated ? (r.final as number) : null} size={150} />
        <div className="dk-words">
          <div className="dk-chips"><span className={"dk-st big " + tone}>{word}</span><span className={"pz-status " + r.status.toLowerCase().replace(" ", "-")}>{STATUS[r.status]}</span>{rated && <span className="dk-sc">{fmtScore(r.final as number)} out of 100</span>}</div>
          <p className={"dk-note" + (r.status === "RATED" ? " ok" : "")}>{STATUS_NOTE[r.status]}</p>
          <p className="dk-cov"><Icon name="check" />{pct(r.confidence)} of inputs available · <Link to="/glossary#coverage-prism">what this means</Link></p>
        </div>
      </div>
      <Tiles r={r} />
      <PrismTechRow report={rep} onRecalculate={() => run.mutate(true)} busy={busy} />
      <details className="dk-more">
        <summary><span>What supports and weighs on the rating, data date, recalculate</span><Icon name="arrow" className="dk-chev" /></summary>
        <Notes r={rep} symbol={symbol} />
        <div className="dk-foot">
          <span className="dk-date"><Icon name="calendar" />Calculated {dateIN(rep.completedAt || rep.createdAt)}</span>
          <button className="btn dk-b" disabled={busy} onClick={() => run.mutate(true)}>{busy ? "Calculating…" : "Recalculate"}</button>
        </div>
      </details>
      <div className="dk-cta"><Link className="btn primary dk-b" to={`/prism/${encodeURIComponent(symbol)}`}>Open the full Prism report <Icon name="arrow" /></Link></div>
      {status}
    </>
  );
}

/** Made-up numbers shown behind the unlock panel, marked as an example. */
const EXAMPLE: PrismLatest["rating"] = { final: 68.4, label: "HEALTHY", status: "RATED", parts: { fundamental: 74, valuation: 58, quality: 71, risk: 66 }, confidence: 0.91 };

export function PrismCompare({ symbol, name, statement }: { symbol: string; name: string; statement: string }) {
  const gold = useGold();
  const open = useContext(OpenAccess);
  const q = usePrismLatest(symbol, statement, gold || open);
  const state: PrismCardState | undefined = !gold && !open ? { kind: "locked" } : q.isError ? { kind: "hidden" } : q.data;
  // The server and this page disagree about the plan: say nothing rather than show a lock to a member.
  if (state?.kind === "hidden" || (state?.kind === "locked" && gold)) return null;
  const head = (note?: string) => <header className="dk-head"><div className="dk-ht"><span className="eyebrow">FinLit Prism</span><span className="tier gold">Gold</span>{note && <span className="dk-chip">{note}</span>}</div><div className="dk-hm"><span className="hide-sm">Advanced model ·</span> <Link to="/glossary#finlit-prism">how it works</Link></div></header>;
  const ex = partsOf(EXAMPLE).parts;
  return (
    <section className="report dk-card pz-right" id="prism" aria-label={`FinLit Prism rating for ${name}`}>
      {state?.kind === "locked" ? (
        <OpenAccess.Provider value={false}>
          <Gate tier="gold" title="Unlock FinLit Prism" points={PRISM_POINTS}>
            {head("Example")}
            <div className="dk-body">
              <div className="dk-row"><PrismGlyph parts={ex.map((p) => ({ key: p.key, name: p.name, weight: p.weight, value: p.value, color: p.color }))} score={EXAMPLE.final} size={150} example />
                <div className="dk-words"><div className="dk-chips"><span className="dk-st big healthy">Healthy</span><span className="pz-status rated">Rated</span></div><p className="dk-note">Example numbers, to show the layout.</p></div></div>
              <Tiles r={EXAMPLE} example />
            </div>
          </Gate>
        </OpenAccess.Provider>
      ) : (
        <>
          {head(state?.kind === "report" ? (state.report.statementType === "standalone" ? "Standalone" : "Consolidated") : undefined)}
          <div className="dk-body">
            {!state ? <div className="dk-skel" aria-hidden="true"><div className="skeleton s-row" /><div className="skeleton s-tiles" /><div className="skeleton s-notes" /></div> : <Body state={state} symbol={symbol} statement={statement} name={name} />}
          </div>
        </>
      )}
      <p className="dk-comp disc"><Icon name="info" /><span>{PRISM_NOTE}</span></p>
    </section>
  );
}

/** The right half of "Show full breakdown": every pro and con by part, and what data was missing. Gold members, when a report is stored. */
export function PrismDetail({ symbol, statement }: { symbol: string; statement: string }) {
  const gold = useGold();
  const open = useContext(OpenAccess);
  const q = usePrismLatest(symbol, statement, gold || open);
  const rep = q.data?.kind === "report" ? q.data.report : null;
  if (!rep) return null;
  const parts = rep.review?.parts ?? [], miss = rep.review?.completeness;
  return (
    <section className="report dk-card dk-detail" aria-label="FinLit Prism: full breakdown">
      <h3 className="dk-dh"><span className="eyebrow">FinLit Prism</span>Pros and cons by part</h3>
      {parts.length === 0 && <p className="faint">The stored report has no written review yet. <Link to={`/prism/${encodeURIComponent(symbol)}`}>Open the full Prism report</Link></p>}
      <div className="dk-dgrid">
        {parts.map((p) => (
          <div key={p.key} className="dk-dpart">
            <h4>{p.name}</h4>
            {(p.pros?.length ?? 0) + (p.cons?.length ?? 0) === 0 && <p className="faint">Nothing stands out here.</p>}
            {!!p.pros?.length && <ul className="pz-l pro">{p.pros.map((i) => <li key={i.metric}><Icon name="check" /><span><b>{i.label}</b> <small>{i.summary}</small></span></li>)}</ul>}
            {!!p.cons?.length && <ul className="pz-l con">{p.cons.map((i) => <li key={i.metric}><Icon name="alert" /><span><b>{i.label}</b> <small>{i.summary}</small></span></li>)}</ul>}
          </div>))}
      </div>
      {miss && !miss.complete && miss.items.length > 0 && (
        <div className="pz-miss"><h4>Data completeness: what was missing</h4><ul>{miss.items.slice(0, 8).map((i) => <li key={i.label}><b>{i.label}</b> <small>{i.treatment || i.reason}</small></li>)}</ul></div>
      )}
      {miss?.complete && <p className="faint dk-ok"><Icon name="check" />All the inputs the model uses were available.</p>}
    </section>
  );
}

/** The Prism sub-section of "Pros and cons": what holds up and what weighs on each part, and what data was missing. Gold members, when a report is stored. */
export function PrismMethod({ symbol, statement }: { symbol: string; statement: string }) {
  const gold = useGold();
  const open = useContext(OpenAccess);
  const q = usePrismLatest(symbol, statement, gold || open);
  const rep = q.data?.kind === "report" ? q.data.report : null;
  const parts = rep?.review?.parts ?? [];
  if (!rep || !parts.length) return null;
  const miss = rep.review?.completeness;
  return (
    <div className="card acc pz-method" id="prism-method" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>FinLit Prism: pros and cons by part</h3><span className="s">{prismSummary(rep.rating)}</span></div>
      <div className="pz-mgrid">
        {parts.map((p) => (
          <div key={p.key} className="pcb">
            <h4>{p.name}</h4>
            {(p.pros?.length ?? 0) + (p.cons?.length ?? 0) === 0 && <p className="faint">Nothing stands out here.</p>}
            {!!p.pros?.length && <ul className="pz-l pro">{p.pros.map((i) => <li key={i.metric}><Icon name="check" /><span><b>{i.label}</b> <small>{i.summary}</small></span></li>)}</ul>}
            {!!p.cons?.length && <ul className="pz-l con">{p.cons.map((i) => <li key={i.metric}><Icon name="alert" /><span><b>{i.label}</b> <small>{i.summary}</small></span></li>)}</ul>}
          </div>))}
      </div>
      {miss && !miss.complete && miss.items.length > 0 && (
        <div className="pz-miss"><h4>Data that was missing</h4><ul>{miss.items.slice(0, 8).map((i) => <li key={i.label}><b>{i.label}</b> <small>{i.treatment || i.reason}</small></li>)}</ul></div>
      )}
      <p className="faint" style={{ fontSize: 12.5, margin: "12px 0 0" }}>{PRISM_NOTE} <Link to={`/prism/${encodeURIComponent(symbol)}`}>Open the full Prism report</Link></p>
    </div>
  );
}
