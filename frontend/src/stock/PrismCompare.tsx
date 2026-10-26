// The right half of the stock page's first dashboard: FinLit Prism beside the FinLit score (left half, in Hero.tsx).
// Same grammar as the left: a report card, a ring with the number, and tiles with a bar per part, so the eye compares numbers, not styling.
// Gold members (and everyone on a free example company) see the newest stored rating; others see a locked teaser.
// Nothing is calculated here unless the person presses a button. Anything unexpected hides the half and the score fills the row.
import { useContext } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Icon } from "../lib/icons";
import { dateIN } from "../lib/format";
import { useGold } from "../lib/premium";
import { Gate, OpenAccess } from "../components/Gate";
import { LABEL, STATUS, fmtScore, generateFailure, generatePrism, pct, prismSummary, usePrismLatest, type PrismCardState, type PrismLatest } from "./PrismCard";
import { PRISM_NOTE, PRISM_PARTS, PRISM_POINTS } from "./prismWords";
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
  const parts: Part[] = PRISM_PARTS.map(([k, name, share, color]) => ({ key: k, name, weight: Math.round((w[k] ?? share / 100) * 100), color, value: r.parts[k] ?? null }));
  const tech = r.parts.technical;
  if (tech !== undefined && w.technical != null) parts.push({ key: "technical", name: "Technical", weight: Math.round(w.technical * 100), color: "--p-tech", value: tech });
  return { parts, technicalSoon: !parts.some((p) => p.key === "technical") };
}

function Ring({ value, color }: { value: number | null; color: string }) {
  const r = 22, circ = 2 * Math.PI * r, c = `var(${color})`;
  return <span className="ring"><svg viewBox="0 0 54 54" aria-hidden="true"><circle cx="27" cy="27" r={r} fill="none" stroke="var(--s3)" strokeWidth="5" /><circle cx="27" cy="27" r={r} fill="none" stroke={c} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${(circ * (value ?? 0)) / 100} ${circ}`} /></svg><b>{value == null ? "—" : Math.round(value)}</b></span>;
}

function Tiles({ r, example = false }: { r: PrismLatest["rating"]; example?: boolean }) {
  const { parts, technicalSoon } = partsOf(r);
  return (
    <div className="pillars pzs-parts" role="group" aria-label={example ? "The four parts of a Prism rating (example numbers)" : "The parts of the Prism rating"}>
      {parts.map((p, i) => {
        const [word, tone] = partWord(p.value);
        return (
          <div key={p.key} className="ptile pzs-t" style={{ "--pc": `var(${p.color})` } as React.CSSProperties} role="group"
            aria-label={p.value == null ? `${p.name}: no data` : `${p.name}: ${Math.round(p.value)} out of 100, ${word.toLowerCase()}. ${p.weight}% of the score`}>
            <div className="pt-top"><span className="pt-share">{p.weight}% of score</span><Ring value={p.value} color={p.color} /></div>
            <div className="pt-name">{p.name}</div>
            <span className={"vd " + tone}>{word}</span>
            <div className="pt-bar"><i style={{ width: `${p.value ?? 0}%`, animationDelay: `${0.45 + i * 0.08}s` }} /></div>
          </div>
        );
      })}
      {technicalSoon && <div className="ptile pzs-t pz-soon" style={{ "--pc": "var(--p-tech)" } as React.CSSProperties}><div className="pt-name">Technical</div><span className="vd na">Coming soon</span><div className="pt-ev">Technical: coming soon. The model has no technical part yet.</div></div>}
    </div>
  );
}

const items = (r: PrismLatest, kind: "pros" | "cons") => (r.review?.parts ?? []).flatMap((p) => p[kind] ?? []).slice(0, 2);

function Notes({ r }: { r: PrismLatest }) {
  const pros = items(r, "pros"), cons = items(r, "cons");
  if (!pros.length && !cons.length) return null;
  const col = (tone: "pro" | "con", list: typeof pros) => (
    <div className={"pzs-pc " + tone}><div className="kt"><Icon name={tone === "pro" ? "check" : "alert"} />{tone === "pro" ? "Supports the rating" : "Holds it back"}</div>
      {list.length ? <ul>{list.map((i) => <li key={i.metric}><b>{i.label}</b><small>{i.summary}</small></li>)}</ul> : <p className="faint">Nothing stands out.</p>}</div>
  );
  return <div className="pzs-notes">{col("pro", pros)}{col("con", cons)}</div>;
}

function Body({ state, symbol, statement, name }: { state: Exclude<PrismCardState, { kind: "locked" | "hidden" }>; symbol: string; statement: string; name: string }) {
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: (refresh: boolean) => generatePrism(symbol, statement, refresh),
    onSuccess: (report) => { const next: PrismCardState = { kind: "report", report }; qc.setQueryData(["prism-latest", symbol, statement], next); },
  });
  const busy = run.isPending;
  const status = busy ? <p className="pz-busy" role="status"><span className="pzs-spin" aria-hidden="true" />Calculating the rating from the latest filings and prices. This can take up to two minutes; you can keep reading.</p>
    : run.isError ? <p className="pz-err" role="alert"><Icon name="alert" />{generateFailure(run.error)}</p> : null;
  if (state.kind === "none") return (
    <>
      <div className="pzs-empty">
        <h3>No Prism rating for {name} yet</h3>
        <p>Prism rates a company's financial health in four parts: Fundamentals, Valuation, Quality and Risk. It reads the latest filings and prices, which takes up to two minutes the first time. Nothing is calculated until you ask, and the result then stays stored here.</p>
        <button className="btn primary" disabled={busy} onClick={() => run.mutate(false)}>{busy ? "Calculating…" : "Generate the Prism rating"} <Icon name="arrow" /></button>
        {status}
      </div>
      <Link className="pzs-link" to={`/prism/${encodeURIComponent(symbol)}`}>Open the Prism page for {symbol}</Link>
    </>
  );
  const rep = state.report, r = rep.rating, rated = r.status !== "NOT RATED" && r.final != null, [word, tone] = LABEL[r.label];
  return (
    <>
      <div className="pz-main" role="group" aria-label={prismSummary(r)}>
        <div className="pz-score">{rated ? <><b>{fmtScore(r.final as number)}</b><span>out of 100</span></> : <b className="pz-nr">Not rated</b>}</div>
        <div className="pz-words">
          <div className="pzs-chips"><span className={"vd " + tone}>{word}</span><span className={"pz-status " + r.status.toLowerCase().replace(" ", "-")}>{STATUS[r.status]}</span></div>
          <p>{STATUS_NOTE[r.status]}</p>
          <p className="pzs-cov"><Icon name="check" />{pct(r.confidence)} of inputs available · <Link to="/glossary#coverage-prism">what this means</Link></p>
        </div>
      </div>
      <Tiles r={r} />
      <Notes r={rep} />
      <div className="pzs-foot">
        <span><Icon name="calendar" />Calculated {dateIN(rep.completedAt || rep.createdAt)} · {rep.statementType === "standalone" ? "Standalone" : "Consolidated"}</span>
        <span className="pz-act">
          <button className="btn" disabled={busy} onClick={() => run.mutate(true)}>{busy ? "Calculating…" : "Recalculate"}</button>
          <Link className="btn primary" to={`/prism/${encodeURIComponent(symbol)}`}>Open the full Prism report <Icon name="arrow" /></Link>
        </span>
      </div>
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
  const head = (note?: string) => <div className="rhead"><div className="l"><span className="eyebrow">FinLit Prism</span><span className="tier gold">Gold</span>{note && <span className="chip ghost">{note}</span>}</div><div className="meta">Advanced model · <Link to="/glossary#finlit-prism">how it works</Link></div></div>;
  return (
    <section className="report pz-right" id="prism" aria-label={`FinLit Prism rating for ${name}`}>
      {state?.kind === "locked" ? (
        <OpenAccess.Provider value={false}>
          <Gate tier="gold" title="Unlock FinLit Prism" points={PRISM_POINTS}>
            {head("Example")}
            <div className="pz-body"><div className="pz-main"><div className="pz-score"><b>{fmtScore(EXAMPLE.final as number)}</b><span>out of 100</span></div><div className="pz-words"><div className="pzs-chips"><span className="vd healthy">Healthy</span><span className="pz-status rated">Rated</span></div><p>Example numbers, to show the layout.</p></div></div><Tiles r={EXAMPLE} example /></div>
          </Gate>
        </OpenAccess.Provider>
      ) : (
        <>
          {head()}
          <div className="pz-body">
            {!state ? <div className="pz-skel" aria-hidden="true"><div className="skeleton" style={{ height: 96 }} /><div className="skeleton" style={{ height: 250 }} /><div className="skeleton" style={{ height: 70 }} /></div> : <Body state={state} symbol={symbol} statement={statement} name={name} />}
          </div>
        </>
      )}
      <p className="pz-comp disc"><Icon name="info" /><span>{PRISM_NOTE}</span></p>
    </section>
  );
}

/** The Prism sub-section of "Pros and cons": what holds up and what holds back each part, and what data was missing. Gold members, when a report is stored. */
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
