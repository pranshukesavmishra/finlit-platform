import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { initials } from "../lib/format";
import { useFocusTrap } from "../lib/focusTrap";
import { ApiError } from "../lib/api";
import {
  DISCLAIMER, NOTE, NOT_AVAILABLE, NOT_COVERED, callKey, callLabel, dayText, findCall, fyShort, loadHistory, pickYear, pushHistory, usageText, useEarningsCall, useEarningsCalls, yearsOf,
  type Answer, type CallDetail, type CallList, type CallRow, type HistoryItem, type QuestionMeta,
} from "../lib/earnings";
import { SectionHead } from "./Sections";

/* ------------------------------------------------------------------------------------------ the section on the stock page */
export function EarningsCallSection({ symbol, name }: { symbol: string; name: string }) {
  const q = useEarningsCalls(symbol);
  const [open, setOpen] = useState<{ qid?: string } | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const list = q.data;
  const latest = list?.calls[0];
  const show = (qid?: string) => { opener.current = document.activeElement as HTMLElement | null; setOpen({ qid }); };
  return (
    <section className="block ec-sec" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="earnings-call" no="Earnings call" icon="notes" tier="gold" title="What management said on the latest call"
        sub="Ten fixed questions about the company's most recent earnings call, answered from its transcript, with the quote behind every sentence." color="--gold-deep" />
      <div className="card ec-card">
        {q.isLoading ? <div className="ec-skel" role="status" aria-label="Loading the earnings call"><i /><i /><i /></div>
          : q.isError ? <div className="ec-state" role="alert"><p>Earnings calls could not be loaded right now.</p><button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></div>
          : !list || !list.available || !latest ? <div className="ec-state"><b>{NOT_AVAILABLE}</b><p>Once a company's call has been read and checked, its summary appears here.</p></div>
          : (
            <>
              <div className="ec-top">
                <div>
                  <div className="ec-when">{latest.label} earnings call</div>
                  <div className="ec-sub">{latest.filedAt ? `Transcript filed ${dayText(latest.filedAt)}` : "Transcript on file"} · {list.calls.length} {list.calls.length === 1 ? "call" : "calls"} summarised</div>
                </div>
                <button type="button" className="btn primary" onClick={() => show()}>{list.locked ? "See what is inside" : "Read the call summary"} <Icon name="arrow" /></button>
              </div>
              <ul className="ec-prev" aria-label="Questions answered for this call">
                {list.questions.map((x) => <li key={x.id}><button type="button" className="ec-chip" onClick={() => show(x.id)}>{x.label}</button></li>)}
              </ul>
              {list.locked && <p className="ec-lock"><Icon name="lock" /> The answers are part of the Gold plan. <Link to="/plans">Compare plans</Link></p>}
            </>
          )}
        <p className="ec-foot">{NOTE} {DISCLAIMER}</p>
      </div>
      {open && list && list.available && <EarningsCallDialog symbol={symbol} name={name} list={list} initialQuestion={open.qid} onClose={() => { setOpen(null); opener.current?.focus?.(); }} />}
    </section>
  );
}

/* ------------------------------------------------------------------------------------------ the dialog */
const ID = (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, "");

export function EarningsCallDialog({ symbol, name, list, initialQuestion, onClose }: { symbol: string; name: string; list: CallList; initialQuestion?: string; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const uid = ID(useId());
  const first = list.calls[0];
  const [sel, setSel] = useState<{ fy: number; q: number }>({ fy: first.fiscalYear, q: first.quarter });
  const [qid, setQid] = useState<string | null>(initialQuestion ?? null);
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory(symbol));
  const [quotes, setQuotes] = useState<Set<string>>(new Set());
  useFocusTrap(box, true);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    document.addEventListener("keydown", esc);
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", esc); document.body.style.overflow = was; };
  }, [onClose]);

  const call = findCall(list.calls, sel.fy, sel.q) ?? first;
  const label = callLabel(call.fiscalYear, call.quarter);
  const detail = useEarningsCall(symbol, call.fiscalYear, call.quarter, !list.locked);
  const d = detail.data;
  const answers = useMemo(() => new Map((d?.questions ?? []).map((a) => [a.id, a])), [d]);
  // the first question that has an answer is shown until the reader picks one
  const current: Answer | undefined = d ? (qid ? answers.get(qid) : undefined) ?? d.questions.find((a) => a.ready) : undefined;
  const err = detail.error as ApiError | null;
  const limitHit = err?.status === 403 && err.body.status === "limit_reached";
  const needsGold = list.locked || (err?.status === 403 && err.body.status === "plan_required");
  const usage = d?.usage ?? (limitHit ? { used: (err!.body as { used?: number }).used ?? 0, limit: (err!.body as { limit?: number }).limit ?? null } : list.usage);

  useEffect(() => { setQuotes(new Set()); }, [call.fiscalYear, call.quarter, current?.id]);
  const ask = (id: string) => {
    setQid(id);
    setHistory(pushHistory(symbol, { fy: call.fiscalYear, q: call.quarter, qid: id }));
  };
  // a question chosen on the stock page before the dialog opened counts as asked
  useEffect(() => { if (initialQuestion) setHistory(pushHistory(symbol, { fy: first.fiscalYear, q: first.quarter, qid: initialQuestion })); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const years = yearsOf(list.calls);
  const quarterChip = (n: number) => {
    const c = findCall(list.calls, sel.fy, n);
    return <button key={n} type="button" className={"ec-q" + (call.quarter === n && call.fiscalYear === sel.fy ? " on" : "")} disabled={!c} aria-pressed={!!c && call.quarter === n && call.fiscalYear === sel.fy}
      title={c ? `Open the ${callLabel(sel.fy, n)} call` : `No ${callLabel(sel.fy, n)} call summarised`} onClick={() => setSel({ fy: sel.fy, q: n })}>Q{n}</button>;
  };
  const questions: QuestionMeta[] = d?.questions ?? list.questions;
  const readyIds = new Set((d?.questions ?? []).filter((a) => a.ready).map((a) => a.id));
  const histLabel = (h: HistoryItem) => `${callLabel(h.fy, h.q)} · ${list.questions.find((x) => x.id === h.qid)?.label ?? h.qid}`;

  return createPortal(
    <>
      <div className="ec-scrim" onClick={onClose} />
      <div className="ec-dlg" role="dialog" aria-modal="true" aria-labelledby={uid + "t"} ref={box}>
        <header className="ec-head">
          <div>
            <h3 id={uid + "t"}>{name}, {label} earnings call</h3>
            <p>{[call.filedAt ? `filed ${dayText(call.filedAt)}` : "", usageText(usage)].filter(Boolean).join(", ")}</p>
          </div>
          <button type="button" className="ec-x modal-x" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="ec-body">
          <aside className="ec-rail" aria-label="About this call">
            <div className="ec-co"><span className="ec-badge" aria-hidden="true">{initials(name)}</span><div><b>{name}</b><small>{symbol}</small></div></div>
            <div className="ec-lab" id={uid + "q"}>Quarter</div>
            <div className="ec-qs" role="group" aria-labelledby={uid + "q"}>{[1, 2, 3, 4].map(quarterChip)}</div>
            <label className="ec-lab" htmlFor={uid + "fy"}>Financial year</label>
            <select id={uid + "fy"} className="ec-sel" value={sel.fy} onChange={(e) => { const c = pickYear(list.calls, Number(e.target.value), sel.q); if (c) setSel({ fy: c.fiscalYear, q: c.quarter }); }}>
              {years.map((y) => <option key={y} value={y}>{fyShort(y)}</option>)}
            </select>
            {!list.locked && list.usage?.limit != null && <p className="ec-hint">Opening a new call uses one of your {list.usage.limit} calls this month. Calls you already opened are free.</p>}
            <div className="ec-this">
              <div className="ec-lab">This call</div>
              <dl>
                <dt>Reported</dt><dd>{dayText(call.callDate || call.filedAt) || "Not stated"}</dd>
                <dt>Length</dt><dd>{call.pages ? `${call.pages} ${call.pages === 1 ? "page" : "pages"}` : "Not stated"}</dd>
                <dt>Transcript</dt><dd>{call.transcriptUrl ? <a href={call.transcriptUrl} target="_blank" rel="noopener noreferrer">Open PDF<span className="sr"> (opens the exchange filing in a new tab)</span></a> : "Not available"}</dd>
              </dl>
            </div>
            <div className="ec-ai"><span className="ec-pill"><Icon name="spark" /> Summarised by AI</span><p>The answers come from this call's transcript.</p></div>
            {history.length > 0 && (
              <div className="ec-hist">
                <div className="ec-lab">History</div>
                <ul>{history.map((h) => (
                  <li key={`${h.fy}-${h.q}-${h.qid}`}><button type="button" onClick={() => { if (findCall(list.calls, h.fy, h.q)) { setSel({ fy: h.fy, q: h.q }); setQid(h.qid); } }}>{histLabel(h)}</button></li>))}</ul>
              </div>
            )}
          </aside>
          <div className="ec-main" aria-live="polite" aria-busy={detail.isFetching && !d}>
            <div className="ec-msg"><span className="ec-av" aria-hidden="true"><Icon name="spark" /></span>
              <p>I have read the {label} call from its transcript and summarised it. What would you like to know?</p></div>
            <ul className="ec-chips" aria-label="Questions">
              {questions.map((x) => {
                const ready = readyIds.has(x.id);
                return <li key={x.id}><button type="button" className={"ec-chip" + (current?.id === x.id ? " on" : "")} disabled={list.locked || !d || !ready} aria-pressed={current?.id === x.id}
                  title={list.locked ? "Part of the Gold plan" : d && !ready ? "The summary of this call has no answer to this one" : undefined} onClick={() => ask(x.id)}>{x.label}</button></li>;
              })}
            </ul>
            {needsGold ? (
              <div className="ec-state ec-gate" role="note"><Icon name="lock" /><b>Earnings-call summaries are part of the Gold plan</b>
                <p>Gold members read ten fixed questions for each call, with the quote behind every sentence.</p><Link className="btn primary" to="/plans" onClick={onClose}>Compare plans</Link></div>
            ) : limitHit ? (
              <div className="ec-state" role="alert"><b>You have used your {usage?.limit ?? ""} calls for this month</b>
                <p>Calls you already opened stay open: pick one of them from the quarter and year lists or from History. The count starts again next month.</p></div>
            ) : detail.isLoading ? (
              <div className="ec-skel" role="status" aria-label="Loading the summary"><i /><i /><i /></div>
            ) : err?.status === 404 ? (
              <div className="ec-state"><b>No summary of this call yet</b><p>It is prepared overnight once the transcript has been read.</p></div>
            ) : detail.isError || !d ? (
              <div className="ec-state" role="alert"><b>This summary could not be loaded</b><p>Please try again in a moment.</p><button type="button" className="btn" onClick={() => detail.refetch()}>Try again</button></div>
            ) : !current ? (
              <div className="ec-state"><b>{NOT_AVAILABLE}</b><p>This call has no checked answers yet.</p></div>
            ) : (
              <AnswerBlock key={`${callKey(call)}-${current.id}`} a={current} d={d} open={quotes} toggle={(k) => setQuotes((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; })} />
            )}
            <div className="ec-pick">
              <label htmlFor={uid + "s"}>Choose a question about the {label} call</label>
              <select id={uid + "s"} className="ec-sel" value={current?.id ?? ""} disabled={list.locked || !d || !!err} onChange={(e) => e.target.value && ask(e.target.value)}>
                <option value="" disabled>Choose a question</option>
                {questions.map((x) => <option key={x.id} value={x.id} disabled={!readyIds.has(x.id)}>{x.label}</option>)}
              </select>
            </div>
          </div>
        </div>
        <footer className="ec-foot2">
          <p>Answers come from the {label} transcript only. Where the call does not cover something, the answer says so.</p>
          <p>{NOTE} {DISCLAIMER}</p>
        </footer>
      </div>
    </>, document.body);
}

function AnswerBlock({ a, d, open, toggle }: { a: Answer; d: CallDetail; open: Set<string>; toggle: (k: string) => void }) {
  return (
    <article className="ec-ans" aria-label={a.label}>
      <p className="ec-asked">{a.label}</p>
      <div className="ec-row">
        <div className="ec-key">{a.title}</div>
        {!a.covered || a.sentences.length === 0 ? <p className="ec-none">{d.notCovered || NOT_COVERED}</p> : (
          <ul>{a.sentences.map((s, i) => {
            const k = `${a.id}:${i}`, shown = open.has(k), id = `ecq-${ID(k)}`;
            return (
              <li key={k}>
                <span>{s.text}</span>{" "}
                <button type="button" className="ec-qb" aria-expanded={shown} aria-controls={id} onClick={() => toggle(k)}>{shown ? "Hide the quote" : "Show the quote"}</button>
                {shown && <blockquote id={id}><p>{s.quote}</p>{s.quoteRef && <cite>{s.quoteRef.startsWith("page") ? `${d.label}, ${s.quoteRef}` : s.quoteRef}</cite>}</blockquote>}
              </li>
            );
          })}</ul>
        )}
      </div>
    </article>
  );
}

export type { CallRow };
